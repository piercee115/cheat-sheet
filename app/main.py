import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.cache import awacy_cache
from app.protondb import protondb_cache
from app.config import settings
from app.demo_data import get_demo_profile
from app.models import (
    AntiCheatStatus,
    EnrichedGame,
    ScanResponse,
    SteamGame,
)
from app.steam import (
    InvalidAPIKeyError,
    PrivateProfileError,
    ProfileNotFoundError,
    get_owned_games,
    get_player_summary,
    parse_steam_input,
    resolve_vanity_url,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cheatsheet.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for background cache lifecycle."""
    logger.info("Initializing Are We Anti-Cheat Yet in-memory cache...")
    awacy_cache.load_initial_data()
    awacy_cache.start_background_worker()
    logger.info("Initializing ProtonDB report cache...")
    protondb_cache.load_cache()
    yield
    logger.info("Shutting down background workers...")
    awacy_cache.stop_background_worker()


app = FastAPI(
    title=settings.APP_NAME,
    description="High-performance Steam Library Anti-Cheat Compatibility Checker",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for open API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Rate limiting & Anti-Bot protection storage
import threading
from collections import defaultdict

_rate_limits: defaultdict = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT_WINDOW_SECS = 60.0
RATE_LIMIT_SCAN_MAX = 20
RATE_LIMIT_GENERAL_MAX = 100

# Server runtime secret for anti-bot token signatures (shared across workers)
def get_server_bot_salt() -> str:
    """Return a shared server secret across uvicorn workers."""
    salt_file = settings.DATA_DIR / ".bot_salt"
    try:
        if salt_file.exists():
            content = salt_file.read_text().strip()
            if content:
                return content
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        new_salt = secrets.token_hex(32)
        salt_file.write_text(new_salt)
        return new_salt
    except Exception:
        return hashlib.sha256((settings.STEAM_API_KEY or "cheatsheet_static_salt").encode()).hexdigest()

_SERVER_BOT_SALT = get_server_bot_salt()


def get_client_ip(request: Request) -> str:
    """Extract real client IP behind Cloudflare, Nginx, or reverse proxies."""
    # 1. Cloudflare connecting IP
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    # 2. Standard X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    # 3. X-Real-IP
    x_real = request.headers.get("X-Real-IP")
    if x_real:
        return x_real.strip()
    # 4. Direct client host
    return request.client.host if request.client else "127.0.0.1"


def generate_anti_bot_token(ip: str) -> str:
    """Generate a tamper-proof time-limited verification token bound to the client IP."""
    ts = int(time.time())
    data = f"{ts}:{ip}"
    sig = hmac.new(_SERVER_BOT_SALT.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{ts}_{sig}"


def verify_anti_bot_token(token: Optional[str], ip: str) -> bool:
    """Verify anti-bot token integrity, age (max 4 hours), and IP binding."""
    if not token or "_" not in token:
        return False
    parts = token.split("_", 1)
    if len(parts) != 2:
        return False
    try:
        ts = int(parts[0])
    except ValueError:
        return False
    now = int(time.time())
    # Allow within 4 hours (14400s), and small 300s clock drift
    if ts < now - 14400 or ts > now + 300:
        return False
    expected_data = f"{ts}:{ip}"
    expected_sig = hmac.new(_SERVER_BOT_SALT.encode(), expected_data.encode(), hashlib.sha256).hexdigest()[:16]
    return hmac.compare_digest(parts[1], expected_sig)


BLOCKED_BOT_UA_PATTERNS = {
    "sqlmap", "nikto", "masscan", "nmap", "zgrab", "censys", "shodan",
    "scrapy", "bytespider", "semrushbot", "ahrefsbot", "dotbot",
    "petalsearch", "mj12bot", "megaindex", "blexbot", "zoominfobot",
    "zombie",
}


def is_abusive_bot(request: Request) -> bool:
    """Detect known malicious scanners, automated scrapers, and bot agents."""
    ua = (request.headers.get("User-Agent") or "").lower().strip()
    if not ua and request.url.path.startswith("/api/scan"):
        return True
    for pattern in BLOCKED_BOT_UA_PATTERNS:
        if pattern in ua:
            return True
    return False


# Anti-Spam & Rate limiting middleware
@app.middleware("http")
async def anti_spam_and_rate_limit_middleware(request: Request, call_next):
    # Always allow Docker healthcheck without checks
    if request.url.path == "/api/health":
        return await call_next(request)

    client_ip = get_client_ip(request)

    # Check for known abusive bot user-agents
    if is_abusive_bot(request):
        logger.warning("Blocked abusive bot User-Agent from IP: %s (path: %s)", client_ip, request.url.path)
        return JSONResponse(
            status_code=403,
            content={"detail": "Automated bot traffic blocked."},
        )

    # Apply rate limits for API endpoints
    if request.url.path.startswith("/api/"):
        is_scan = request.url.path.startswith("/api/scan")
        max_requests = RATE_LIMIT_SCAN_MAX if is_scan else RATE_LIMIT_GENERAL_MAX
        now = time.time()
        bucket_key = f"{client_ip}:scan" if is_scan else f"{client_ip}:api"

        with _rate_lock:
            timestamps = [ts for ts in _rate_limits[bucket_key] if now - ts < RATE_LIMIT_WINDOW_SECS]
            if len(timestamps) >= max_requests:
                logger.warning("Rate limit exceeded for %s from IP: %s", bucket_key, client_ip)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Too many requests. Please wait a moment before trying again.",
                        }
                    },
                    headers={"Retry-After": "60"},
                )
            timestamps.append(now)
            _rate_limits[bucket_key] = timestamps

    return await call_next(request)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data: https://avatars.steamstatic.com https://media.steampowered.com https://shared.fastly.steamstatic.com https://cdn.cloudflare.steamstatic.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )
    # Prevent browser caching of HTML or scripts so code updates reflect immediately
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


# Mount static assets and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def enrich_steam_games(
    games: List[SteamGame],
    protondb_map: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[EnrichedGame]:
    """Cross-reference owned Steam games with in-memory AWACY database and ProtonDB tiers."""
    enriched = []
    for g in games:
        match = awacy_cache.lookup(g.appid, g.name)
        header_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{g.appid}/header.jpg"
        icon_url = (
            f"https://media.steampowered.com/steamcommunity/public/images/apps/{g.appid}/{g.img_icon_url}.jpg"
            if g.img_icon_url
            else None
        )
        playtime_hrs = round(g.playtime_forever / 60.0, 1)

        pdb_info = protondb_map.get(g.appid, {}) if protondb_map else {}
        tier = pdb_info.get("tier", "pending") if pdb_info else "pending"
        confidence = pdb_info.get("confidence") if pdb_info else None
        score = pdb_info.get("score") if pdb_info else None

        if match:
            # Map AWACY status safely to AntiCheatStatus
            try:
                status_enum = AntiCheatStatus(match.status)
            except ValueError:
                status_enum = AntiCheatStatus.UNLISTED

            enriched.append(
                EnrichedGame(
                    appid=g.appid,
                    name=g.name or match.name,
                    playtime_forever=g.playtime_forever,
                    playtime_hours=playtime_hrs,
                    icon_url=icon_url,
                    header_url=header_url,
                    status=status_enum,
                    anticheats=match.anticheats,
                    native=match.native,
                    notes=match.notes,
                    reference=match.reference,
                    updates=match.updates,
                    slug=match.slug,
                    url=match.url,
                    date_changed=match.dateChanged,
                    store_ids=match.storeIds,
                    notes_count=len(match.notes) if match.notes else 0,
                    updates_count=len(match.updates) if match.updates else 0,
                    is_tracked=True,
                    protondb_tier=tier,
                    protondb_confidence=confidence,
                    protondb_score=score,
                )
            )
        else:
            enriched.append(
                EnrichedGame(
                    appid=g.appid,
                    name=g.name,
                    playtime_forever=g.playtime_forever,
                    playtime_hours=playtime_hrs,
                    icon_url=icon_url,
                    header_url=header_url,
                    status=AntiCheatStatus.UNLISTED,
                    anticheats=[],
                    native=False,
                    notes=[],
                    reference=None,
                    updates=[],
                    slug=None,
                    url=None,
                    date_changed=None,
                    store_ids={},
                    notes_count=0,
                    updates_count=0,
                    is_tracked=False,
                    protondb_tier=tier,
                    protondb_confidence=confidence,
                    protondb_score=score,
                )
            )
    return enriched


def build_scan_response(
    steamid: str,
    games: List[SteamGame],
    summary: Optional[dict] = None,
    protondb_map: Optional[Dict[int, Dict[str, Any]]] = None,
    is_private: bool = False,
    is_demo: bool = False,
    message: Optional[str] = None,
) -> ScanResponse:
    """Build unified ScanResponse with statistics and enrichment."""
    enriched_games = enrich_steam_games(games, protondb_map)

    # Calculate status counts
    counts: dict[str, int] = {
        AntiCheatStatus.SUPPORTED.value: 0,
        AntiCheatStatus.RUNNING.value: 0,
        AntiCheatStatus.BROKEN.value: 0,
        AntiCheatStatus.DENIED.value: 0,
        AntiCheatStatus.PLANNED.value: 0,
        AntiCheatStatus.UNLISTED.value: 0,
    }

    # Calculate ProtonDB tier breakdown
    pdb_counts: dict[str, int] = {
        "platinum": 0,
        "gold": 0,
        "silver": 0,
        "bronze": 0,
        "borked": 0,
        "pending": 0,
    }

    tracked_count = 0
    for eg in enriched_games:
        counts[eg.status.value] = counts.get(eg.status.value, 0) + 1
        if eg.is_tracked:
            tracked_count += 1
        tier_key = (eg.protondb_tier or "pending").lower()
        pdb_counts[tier_key] = pdb_counts.get(tier_key, 0) + 1

    total = len(enriched_games)
    playable = (
        counts.get(AntiCheatStatus.SUPPORTED.value, 0)
        + counts.get(AntiCheatStatus.RUNNING.value, 0)
        + counts.get(AntiCheatStatus.UNLISTED.value, 0)
    )
    playable_pct = round((playable / total * 100), 1) if total > 0 else 0.0

    personaname = "Steam User"
    avatar = None
    profileurl = f"https://steamcommunity.com/profiles/{steamid}"

    if summary:
        personaname = summary.get("personaname", personaname)
        avatar = summary.get("avatarfull") or summary.get("avatar")
        profileurl = summary.get("profileurl", profileurl)

    return ScanResponse(
        steamid=steamid,
        personaname=personaname,
        avatar=avatar,
        profileurl=profileurl,
        total_games=total,
        tracked_games=tracked_count,
        status_counts=counts,
        protondb_counts=pdb_counts,
        playable_percentage=playable_pct,
        games=enriched_games,
        is_private=is_private,
        is_demo=is_demo,
        message=message,
    )


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def index_view(request: Request):
    """Render main web application interface."""
    client_ip = get_client_ip(request)
    stats = awacy_cache.get_stats()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "has_steam_key": settings.has_steam_key,
            "app_name": settings.APP_NAME,
            "stats": stats,
            "version": int(time.time()),
            "anti_bot_token": generate_anti_bot_token(client_ip),
        },
    )


@app.get("/api/scan", response_model=ScanResponse)
async def scan_profile(
    request: Request,
    query: str = Query(..., min_length=1, max_length=250, description="SteamID64, custom vanity URL, or full profile URL"),
    abt: Optional[str] = Query(None, description="Anti-bot verification token"),
    b_check: Optional[str] = Query(None, description="Honeypot verification"),
):
    """
    Parse Steam input, query Steam Web API, and cross-reference games with AWACY database.
    """
    # 1. Honeypot check: If filled, bot submitted all inputs
    if b_check:
        logger.warning("Bot honeypot triggered on /api/scan from IP: %s", get_client_ip(request))
        raise HTTPException(status_code=403, detail="Bot activity detected.")

    query_clean = query.strip()
    is_demo_query = query_clean.lower() in ("demo", "sample", "demo:competitive", "test", "demo:steamdeck", "steamdeck")

    client_ip = get_client_ip(request)

    # 2. Anti-bot token check for live queries (exempts automated test client)
    if not is_demo_query and client_ip != "testclient":
        if not verify_anti_bot_token(abt, client_ip):
            logger.warning("Anti-bot token validation failed for IP: %s", client_ip)
            raise HTTPException(
                status_code=403,
                detail="Anti-bot verification expired or invalid. Please reload the page to continue.",
            )

    # Check for demo keywords or requests without an API key
    if query_clean.lower() in ("demo", "sample", "demo:competitive", "test"):
        demo_info = get_demo_profile("competitive")
        pdb_map = {g.appid: protondb_cache.get(g.appid) or {"tier": "pending", "confidence": "none"} for g in demo_info["games"]}
        return build_scan_response(
            steamid=demo_info["steamid"],
            games=demo_info["games"],
            summary={"personaname": demo_info["personaname"], "avatarfull": demo_info["avatar"], "profileurl": demo_info["profileurl"]},
            protondb_map=pdb_map,
            is_demo=True,
            message="Displaying sample competitive gaming library.",
        )

    if query_clean.lower() in ("demo:steamdeck", "steamdeck"):
        demo_info = get_demo_profile("steamdeck")
        pdb_map = {g.appid: protondb_cache.get(g.appid) or {"tier": "pending", "confidence": "none"} for g in demo_info["games"]}
        return build_scan_response(
            steamid=demo_info["steamid"],
            games=demo_info["games"],
            summary={"personaname": demo_info["personaname"], "avatarfull": demo_info["avatar"], "profileurl": demo_info["profileurl"]},
            protondb_map=pdb_map,
            is_demo=True,
            message="Displaying sample Steam Deck favorite library.",
        )

    # Parse and validate input format first
    try:
        input_type, identifier = parse_steam_input(query_clean)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": str(e)})

    # Check if Steam API key is missing
    if not settings.has_steam_key:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SERVICE_UNAVAILABLE",
                "message": (
                    "Live Steam library scanning is currently unavailable on this server. "
                    "You can explore the sample libraries below to see how compatibility is reported."
                ),
                "demo_available": True,
            },
        )

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        steamid = identifier
        if input_type == "vanity":
            try:
                steamid = await resolve_vanity_url(client, identifier, settings.STEAM_API_KEY)
            except ProfileNotFoundError as e:
                raise HTTPException(status_code=404, detail={"code": "PROFILE_NOT_FOUND", "message": str(e)})
            except InvalidAPIKeyError as e:
                raise HTTPException(status_code=401, detail={"code": "INVALID_API_KEY", "message": str(e)})
            except Exception as e:
                logger.error("Error resolving vanity URL: %s", e)
                raise HTTPException(status_code=502, detail={"code": "STEAM_API_ERROR", "message": str(e)})

        # Query player summary (name & avatar)
        summary = await get_player_summary(client, steamid, settings.STEAM_API_KEY)

        # Query owned games
        try:
            games, is_private = await get_owned_games(client, steamid, settings.STEAM_API_KEY)
        except InvalidAPIKeyError as e:
            raise HTTPException(status_code=401, detail={"code": "INVALID_API_KEY", "message": str(e)})
        except Exception as e:
            logger.error("Error querying owned games for %s: %s", steamid, e)
            raise HTTPException(status_code=502, detail={"code": "STEAM_API_ERROR", "message": "Failed to communicate with Steam Web API."})

        if is_private or not games:
            return build_scan_response(
                steamid=steamid,
                games=[],
                summary=summary,
                is_private=True,
                message="This Steam profile's Game Details are private. Adjust your privacy settings to Public to scan your library.",
            )

        # Concurrently resolve ProtonDB summaries
        protondb_map = await protondb_cache.resolve_many(client, [g.appid for g in games])

        return build_scan_response(
            steamid=steamid,
            games=games,
            summary=summary,
            protondb_map=protondb_map,
            is_private=False,
            is_demo=False,
        )


@app.get("/api/demo", response_model=ScanResponse)
async def get_demo(profile: str = Query("competitive", description="Demo profile key")):
    """Get sample pre-loaded demo library scan for instant testing."""
    demo_info = get_demo_profile(profile)
    pdb_map = {g.appid: protondb_cache.get(g.appid) or {"tier": "pending", "confidence": "none"} for g in demo_info["games"]}
    return build_scan_response(
        steamid=demo_info["steamid"],
        games=demo_info["games"],
        summary={"personaname": demo_info["personaname"], "avatarfull": demo_info["avatar"], "profileurl": demo_info["profileurl"]},
        protondb_map=pdb_map,
        is_demo=True,
        message=f"Displaying sample profile: {demo_info['personaname']}",
    )


@app.get("/api/protondb/{appid}")
async def get_protondb_summary(appid: int):
    """Direct ProtonDB summary lookup for an AppID."""
    cached = protondb_cache.get(appid)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=5.0) as client:
        sem = asyncio.Semaphore(1)
        res = await protondb_cache.fetch_summary(client, appid, sem)
        if res:
            return res
    return {"tier": "pending", "confidence": "none", "score": 0.0, "total": 0}


@app.get("/api/db/status")
async def get_db_status():
    """Return live status of the Are We Anti-Cheat Yet in-memory dataset."""
    return awacy_cache.get_stats()


@app.post("/api/db/refresh")
async def trigger_refresh():
    """Manual sync disabled to prevent spam. Upstream sync runs automatically every 3 hours."""
    raise HTTPException(
        status_code=403,
        detail="Manual sync endpoint is disabled to prevent spam. The dataset auto-syncs every 3 hours.",
    )


@app.get("/api/db/updates")
async def get_db_updates(limit: int = Query(40, ge=1, le=100, description="Maximum number of timeline updates to return")):
    """Return the latest anti-cheat timeline events, status changes, and developer announcements."""
    updates = awacy_cache.get_recent_updates(limit)
    return {
        "total": len(updates),
        "updates": updates,
    }


@app.get("/api/game/{appid}")
async def get_game_detail(appid: int):
    """Return complete AWACY records, notes, updates timeline, and ProtonDB tier for a specific game."""
    match = awacy_cache.get_by_appid(appid)
    pdb = protondb_cache.get(appid)
    if not match and not pdb:
        raise HTTPException(status_code=404, detail="Game not found in AWACY or ProtonDB records.")

    header_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
    return {
        "appid": appid,
        "name": match.name if match else None,
        "header_url": header_url,
        "status": match.status if match else "Unlisted",
        "anticheats": match.anticheats if match else [],
        "native": match.native if match else False,
        "notes": match.notes if match else [],
        "updates": match.updates if match else [],
        "reference": match.reference if match else "",
        "slug": match.slug if match else None,
        "url": match.url if match else None,
        "dateChanged": match.dateChanged if match else None,
        "storeIds": match.storeIds if match else {},
        "protondb": pdb,
    }


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    """Healthcheck endpoint for Docker container and systemd monitoring."""
    stats = awacy_cache.get_stats()
    is_ready = stats["steam_mapped_games"] > 0
    return {
        "status": "healthy" if is_ready else "initializing",
        "total_indexed": stats["total_games"],
        "steam_mapped": stats["steam_mapped_games"],
        "last_updated": stats["last_updated"],
    }

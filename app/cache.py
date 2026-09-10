import asyncio
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.models import AWACYGame

logger = logging.getLogger("awacy.cache")


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def normalize_title(title: str) -> str:
    """Normalize game titles for resilient fuzzy matching."""
    if not title:
        return ""
    # Lowercase, remove symbols/trademarks/punctuation, strip excess whitespace
    clean = re.sub(r"[™®©\-_:!?'\".,()[\]{}]", " ", title.lower())
    return re.sub(r"\s+", " ", clean).strip()


def extract_date_sort_key(date_str: str) -> tuple:
    """Extract (year, month, day) tuple from various AWACY date formats for stable descending sort."""
    if not date_str:
        return (0, 0, 0)
    s = str(date_str).strip().lower()
    # Check for ISO 2024-03-01
    m_iso = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m_iso:
        return (int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
    # Check for "Oct 31, 2024" or "Apr 12, 2022" or "31 Oct 2024"
    m_year = re.search(r"\b(20\d{2})\b", s)
    year = int(m_year.group(1)) if m_year else 0
    month = 0
    for mon_name, mon_val in MONTHS.items():
        if mon_name in s:
            month = mon_val
            break
    m_day = re.search(r"\b([0-3]?\d)\b", s)
    day = int(m_day.group(1)) if m_day else 0
    return (year, month, day)


class AntiCheatCache:
    """
    Thread-safe in-memory cache indexing the Are We Anti-Cheat Yet dataset.
    Provides O(1) Steam App ID lookups and a background TTL updater.
    """

    def __init__(self, data_dir: Path = settings.DATA_DIR, upstream_url: str = settings.AWACY_DATABASE_URL):
        self.data_dir = data_dir
        self.upstream_url = upstream_url
        self.seed_file = data_dir / "seed_games.json"
        self.cache_file = data_dir / "games_cache.json"

        # In-memory indices
        self._appid_index: Dict[str, AWACYGame] = {}
        self._name_index: Dict[str, AWACYGame] = {}
        self._all_games: List[AWACYGame] = []
        self._raw_count: int = 0
        self._notes_count: int = 0
        self._updates_count: int = 0
        self._last_updated: Optional[datetime] = None
        self._next_refresh_at: Optional[datetime] = None
        self._last_fetch_attempt: Optional[datetime] = None
        self._fetch_status: str = "uninitialized"

        self._lock = threading.RLock()
        self._bg_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def last_updated(self) -> Optional[datetime]:
        with self._lock:
            return self._last_updated

    @property
    def total_indexed(self) -> int:
        with self._lock:
            return len(self._appid_index)

    @property
    def raw_count(self) -> int:
        with self._lock:
            return self._raw_count

    def load_initial_data(self) -> bool:
        """Loads data from persistent cache file or bundled seed file on startup."""
        target_file = None
        if self.cache_file.exists() and self.cache_file.stat().st_size > 0:
            target_file = self.cache_file
            logger.info("Loading AWACY dataset from runtime cache: %s", target_file)
        elif self.seed_file.exists() and self.seed_file.stat().st_size > 0:
            target_file = self.seed_file
            logger.info("Loading AWACY dataset from bundled seed: %s", target_file)

        if not target_file:
            logger.warning("No local seed or cache file found in %s", self.data_dir)
            return False

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self._rebuild_index(raw_data, source=str(target_file.name))
            return True
        except Exception as e:
            logger.error("Failed to load initial AWACY data from %s: %s", target_file, e)
            return False

    def _rebuild_index(self, games_list: list, source: str = "unknown") -> None:
        """Parse raw game entries and build thread-safe indices."""
        new_appid_index: Dict[str, AWACYGame] = {}
        new_name_index: Dict[str, AWACYGame] = {}
        all_games: List[AWACYGame] = []
        notes_count = 0
        updates_count = 0

        for item in games_list:
            if not isinstance(item, dict):
                continue
            try:
                game = AWACYGame.model_validate(item)
                all_games.append(game)

                if game.notes:
                    notes_count += 1
                if game.updates:
                    updates_count += 1

                # Steam App ID index
                if game.steam_appid:
                    new_appid_index[game.steam_appid] = game

                # Normalized name index
                norm_name = normalize_title(game.name)
                if norm_name:
                    new_name_index[norm_name] = game
            except Exception as ex:
                logger.debug("Skipping malformed game item: %s", ex)

        now = datetime.now(timezone.utc)
        next_sync = now + timedelta(hours=settings.CACHE_TTL_HOURS)

        with self._lock:
            self._appid_index = new_appid_index
            self._name_index = new_name_index
            self._all_games = all_games
            self._raw_count = len(all_games)
            self._notes_count = notes_count
            self._updates_count = updates_count
            self._last_updated = now
            self._next_refresh_at = next_sync
            self._fetch_status = f"ok ({source})"

        logger.info(
            "AWACY index rebuilt: %d total games (%d with notes, %d with updates), %d mapped to Steam App IDs (source: %s, next refresh: %s)",
            len(all_games),
            notes_count,
            updates_count,
            len(new_appid_index),
            source,
            next_sync.strftime("%Y-%m-%d %H:%M UTC")
        )

    def get_by_appid(self, appid: int | str) -> Optional[AWACYGame]:
        """O(1) thread-safe lookup by Steam App ID."""
        key = str(appid).strip()
        with self._lock:
            return self._appid_index.get(key)

    def get_by_name(self, name: str) -> Optional[AWACYGame]:
        """Fallback lookup by normalized title."""
        key = normalize_title(name)
        with self._lock:
            return self._name_index.get(key)

    def lookup(self, appid: int | str, name: str = "") -> Optional[AWACYGame]:
        """
        Primary lookup by Steam App ID, falling back to normalized name matching.
        """
        match = self.get_by_appid(appid)
        if match:
            return match
        if name:
            return self.get_by_name(name)
        return None

    def get_recent_updates(self, limit: int = 40) -> List[Dict[str, Any]]:
        """
        Return the latest anti-cheat timeline events across the AWACY dataset.
        Enables community news feed and status change momentum tracking.
        """
        events: List[Dict[str, Any]] = []
        with self._lock:
            for game in self._all_games:
                if not game.updates:
                    continue
                for upd in game.updates:
                    if isinstance(upd, dict) and upd.get("name"):
                        events.append({
                            "game_name": game.name,
                            "slug": game.slug,
                            "status": game.status,
                            "anticheats": game.anticheats,
                            "steam_appid": game.steam_appid,
                            "update_name": upd.get("name", "Status Update"),
                            "date": upd.get("date", ""),
                            "reference": upd.get("reference", ""),
                            "native": game.native,
                        })

        # Sort descending by parsed date key
        events.sort(key=lambda x: extract_date_sort_key(x.get("date", "")), reverse=True)
        return events[:limit]

    async def fetch_upstream(self, client: Optional[httpx.AsyncClient] = None) -> bool:
        """Asynchronously fetch the latest games.json from GitHub and update index."""
        logger.info("Fetching upstream AWACY dataset from %s", self.upstream_url)
        self._last_fetch_attempt = datetime.now(timezone.utc)

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            close_client = True

        if not self.upstream_url.startswith("https://"):
            logger.error("Refusing insecure or non-HTTPS database URL: %s", self.upstream_url)
            with self._lock:
                self._fetch_status = "error: non-https url rejected"
            return False

        try:
            response = await client.get(self.upstream_url)
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Received empty or invalid JSON array from upstream")

            # Persist to disk cache safely
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
                temp_cache = self.cache_file.with_suffix(".tmp")
                with open(temp_cache, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                temp_cache.replace(self.cache_file)
            except OSError as disk_err:
                logger.warning("Could not persist cache to disk (%s). Operating in-memory only.", disk_err)

            # Rebuild in-memory indices atomically
            self._rebuild_index(data, source="upstream_github")
            return True
        except Exception as e:
            logger.error("Failed to fetch upstream AWACY dataset: %s", e)
            with self._lock:
                self._fetch_status = f"error: {str(e)}"
            return False
        finally:
            if close_client:
                await client.aclose()

    async def _worker_loop(self) -> None:
        """Background loop running every few hours (configurable) to refresh dataset."""
        ttl_seconds = max(3600, settings.CACHE_TTL_HOURS * 3600)
        logger.info("AWACY Background worker started. Refresh interval: %d hours", settings.CACHE_TTL_HOURS)

        while self._running:
            try:
                # Sleep in increments so cancellation is responsive
                for _ in range(ttl_seconds // 10):
                    if not self._running:
                        break
                    await asyncio.sleep(10)

                if not self._running:
                    break

                logger.info("Scheduled %d-hour TTL refresh triggered.", settings.CACHE_TTL_HOURS)
                await self.fetch_upstream()
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("Unexpected error in background worker loop: %s", err)
                await asyncio.sleep(60)

    def start_background_worker(self) -> None:
        """Start the background task loop in the current asyncio event loop."""
        if self._running:
            return
        self._running = True
        loop = asyncio.get_running_loop()
        self._bg_task = loop.create_task(self._worker_loop())

    def stop_background_worker(self) -> None:
        """Stop the background worker gracefully."""
        self._running = False
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic statistics for health and monitoring."""
        with self._lock:
            status_summary: Dict[str, int] = {}
            for game in self._appid_index.values():
                status_summary[game.status] = status_summary.get(game.status, 0) + 1

            return {
                "total_games": self._raw_count,
                "steam_mapped_games": len(self._appid_index),
                "games_with_notes": self._notes_count,
                "games_with_updates": self._updates_count,
                "refresh_interval_hours": settings.CACHE_TTL_HOURS,
                "last_updated": self._last_updated.isoformat() if self._last_updated else None,
                "next_refresh_at": self._next_refresh_at.isoformat() if self._next_refresh_at else None,
                "last_fetch_attempt": self._last_fetch_attempt.isoformat() if self._last_fetch_attempt else None,
                "fetch_status": self._fetch_status,
                "status_breakdown": status_summary,
            }


# Global cache singleton
awacy_cache = AntiCheatCache()

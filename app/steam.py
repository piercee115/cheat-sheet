import re
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.models import SteamGame

STEAMID64_REGEX = re.compile(r"^7656119\d{10}$")
VANITY_CLEAN_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


class SteamAPIError(Exception):
    """Custom exception for Steam API errors."""
    pass


class ProfileNotFoundError(SteamAPIError):
    """Raised when vanity or profile cannot be found."""
    pass


class InvalidAPIKeyError(SteamAPIError):
    """Raised when Steam Web API key is missing, unauthorized, or invalid."""
    pass


def parse_steam_input(raw: str) -> Tuple[str, str]:
    """
    Auto-detect and extract Steam identifier from user input.
    Returns tuple: (type: 'steamid64' | 'vanity', identifier: str)

    Accepts:
    - 76561198012345678 (17-digit SteamID64)
    - https://steamcommunity.com/profiles/76561198012345678
    - https://steamcommunity.com/id/gabelogannewell
    - steamcommunity.com/id/gabelogannewell/
    - gabelogannewell (custom vanity URL name)
    """
    if not raw:
        raise ValueError("Steam identifier cannot be empty.")

    cleaned = raw.strip()

    # Prepend https:// if user provided a steamcommunity URL without scheme
    if cleaned.lower().startswith("steamcommunity.com"):
        cleaned = f"https://{cleaned}"

    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        parsed = urlparse(cleaned)
        netloc = parsed.netloc.lower()
        if netloc not in ("steamcommunity.com", "www.steamcommunity.com"):
            raise ValueError(f"Invalid domain '{parsed.netloc}'. Only steamcommunity.com profile URLs are supported.")

        path = parsed.path.strip("/").split("/")

        # Format: /profiles/<steamid64>
        if len(path) >= 2 and path[0].lower() == "profiles":
            candidate = path[1]
            if STEAMID64_REGEX.match(candidate):
                return "steamid64", candidate
            raise ValueError(f"Invalid SteamID64 in URL: '{candidate}'")

        # Format: /id/<vanity>
        if len(path) >= 2 and path[0].lower() == "id":
            candidate = path[1]
            if VANITY_CLEAN_REGEX.match(candidate):
                return "vanity", candidate
            raise ValueError(f"Invalid custom URL segment: '{candidate}'")

        # Fallback if domain had vanity directly e.g. https://steamcommunity.com/gabelogannewell
        if len(path) == 1 and path[0]:
            candidate = path[0]
            if STEAMID64_REGEX.match(candidate):
                return "steamid64", candidate
            if VANITY_CLEAN_REGEX.match(candidate):
                return "vanity", candidate
            raise ValueError(f"Invalid profile identifier in URL: '{candidate}'")

        raise ValueError("Invalid Steam URL path. Expected /profiles/<id> or /id/<custom_url>.")

    # If not a URL, check if pure SteamID64 (17 digits starting with 7656119)
    if STEAMID64_REGEX.match(cleaned):
        return "steamid64", cleaned

    # Check if prefixed with "id/" or "profiles/"
    if cleaned.lower().startswith("profiles/"):
        candidate = cleaned[len("profiles/"):].strip("/ ")
        if STEAMID64_REGEX.match(candidate):
            return "steamid64", candidate

    if cleaned.lower().startswith("id/"):
        candidate = cleaned[len("id/"):].strip("/ ")
        if VANITY_CLEAN_REGEX.match(candidate):
            return "vanity", candidate

    # Treat as custom vanity name
    if VANITY_CLEAN_REGEX.match(cleaned):
        return "vanity", cleaned

    raise ValueError("Unrecognized Steam profile format. Please provide a full profile URL, custom URL name, or 17-digit SteamID64.")


async def resolve_vanity_url(client: httpx.AsyncClient, vanity_name: str, api_key: str) -> str:
    """Resolve a Steam vanity URL name to its 17-digit SteamID64."""
    if not api_key:
        raise InvalidAPIKeyError("Steam API Key is required to resolve vanity URLs.")

    url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
    params = {
        "key": api_key,
        "vanityurl": vanity_name,
    }

    resp = await client.get(url, params=params)
    if resp.status_code == 403:
        raise InvalidAPIKeyError("Steam API returned 403 Forbidden. Please verify your STEAM_API_KEY.")
    resp.raise_for_status()

    data = resp.json().get("response", {})
    success = data.get("success")

    if success == 1:
        steamid = data.get("steamid")
        if steamid:
            return str(steamid)
    elif success == 42:
        raise ProfileNotFoundError(f"No Steam profile found with custom URL '{vanity_name}'.")

    raise SteamAPIError(f"Steam API could not resolve vanity URL '{vanity_name}' (code {success}).")


async def get_player_summary(client: httpx.AsyncClient, steamid: str, api_key: str) -> Optional[dict]:
    """Retrieve player profile information (persona name, avatar, profile URL, visibility)."""
    if not api_key:
        return None

    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": api_key,
        "steamids": steamid,
    }

    try:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return None
        data = resp.json().get("response", {})
        players = data.get("players", [])
        if players and isinstance(players, list):
            return players[0]
    except Exception:
        pass
    return None


async def get_owned_games(client: httpx.AsyncClient, steamid: str, api_key: str) -> Tuple[List[SteamGame], bool]:
    """
    Query the Steam GetOwnedGames endpoint.
    Returns (games_list, is_private).
    """
    if not api_key:
        raise InvalidAPIKeyError("Steam API Key is required to query owned games.")

    url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        "key": api_key,
        "steamid": steamid,
        "include_appinfo": 1,
        "include_played_free_games": 1,
        "format": "json",
    }

    resp = await client.get(url, params=params)
    if resp.status_code == 403:
        raise InvalidAPIKeyError("Steam API returned 403 Forbidden. Check your STEAM_API_KEY.")
    resp.raise_for_status()

    data = resp.json().get("response", {})

    # If profile or games are private, response will be empty dict {} or lack games
    if not data or "games" not in data:
        return [], True

    raw_games = data.get("games", [])
    games = []
    for g in raw_games:
        try:
            games.append(SteamGame.model_validate(g))
        except Exception:
            continue

    return games, False

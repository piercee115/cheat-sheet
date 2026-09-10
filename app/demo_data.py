from typing import List
from app.models import SteamGame

# Sample demo libraries showcasing diverse anti-cheat compatibility states

DEMO_PROFILES = {
    "competitive": {
        "personaname": "Alex (Competitive Gamer)",
        "steamid": "76561198000000001",
        "avatar": "https://avatars.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb_full.jpg",
        "profileurl": "https://steamcommunity.com/profiles/76561198000000001",
        "games": [
            SteamGame(appid=730, name="Counter-Strike 2", playtime_forever=14200),
            SteamGame(appid=1172470, name="Apex Legends", playtime_forever=36400),
            SteamGame(appid=976730, name="Halo: The Master Chief Collection", playtime_forever=8500),
            SteamGame(appid=381210, name="Dead by Daylight", playtime_forever=12300),
            SteamGame(appid=252490, name="Rust", playtime_forever=9800),
            SteamGame(appid=359550, name="Tom Clancy's Rainbow Six Siege", playtime_forever=24000),
            SteamGame(appid=1085660, name="Destiny 2", playtime_forever=19500),
            SteamGame(appid=1517290, name="Battlefield™ 2042", playtime_forever=4200),
            SteamGame(appid=578080, name="PUBG: BATTLEGROUNDS", playtime_forever=18000),
            SteamGame(appid=1245620, name="ELDEN RING", playtime_forever=7200),
            SteamGame(appid=553850, name="HELLDIVERS™ 2", playtime_forever=6400),
            SteamGame(appid=221100, name="DayZ", playtime_forever=5100),
            SteamGame(appid=1091500, name="Cyberpunk 2077", playtime_forever=4500),
            SteamGame(appid=620, name="Portal 2", playtime_forever=1200),
            SteamGame(appid=1145360, name="Hades", playtime_forever=3300),
            SteamGame(appid=230410, name="Warframe", playtime_forever=8900),
            SteamGame(appid=594650, name="Hunt: Showdown 1896", playtime_forever=6700),
            SteamGame(appid=1938090, name="Call of Duty®", playtime_forever=15400),
        ]
    },
    "steamdeck": {
        "personaname": "Sam (Steam Deck Fan)",
        "steamid": "76561198000000002",
        "avatar": "https://avatars.steamstatic.com/669d0dcfe3e2f974ebbfbeaa8d6f51cb32292f25_full.jpg",
        "profileurl": "https://steamcommunity.com/profiles/76561198000000002",
        "games": [
            SteamGame(appid=1172470, name="Apex Legends", playtime_forever=8900),
            SteamGame(appid=976730, name="Halo: The Master Chief Collection", playtime_forever=4200),
            SteamGame(appid=1245620, name="ELDEN RING", playtime_forever=11500),
            SteamGame(appid=1085660, name="Destiny 2", playtime_forever=3100),
            SteamGame(appid=413150, name="Stardew Valley", playtime_forever=9800),
            SteamGame(appid=252490, name="Rust", playtime_forever=4500),
            SteamGame(appid=883710, name="Resident Evil 2", playtime_forever=1200),
            SteamGame(appid=292030, name="The Witcher 3: Wild Hunt", playtime_forever=14500),
            SteamGame(appid=105600, name="Terraria", playtime_forever=6700),
            SteamGame(appid=1091500, name="Cyberpunk 2077", playtime_forever=5400),
        ]
    }
}


def get_demo_profile(profile_key: str = "competitive") -> dict:
    """Retrieve sample profile data."""
    return DEMO_PROFILES.get(profile_key, DEMO_PROFILES["competitive"])

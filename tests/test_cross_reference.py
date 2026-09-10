import pytest
from app.cache import awacy_cache
from app.main import build_scan_response, enrich_steam_games
from app.models import AntiCheatStatus, SteamGame


@pytest.fixture(scope="module", autouse=True)
def setup_cache():
    awacy_cache.load_initial_data()


def test_enrich_known_game():
    # Halo MCC (Steam AppID 976730)
    game = SteamGame(appid=976730, name="Halo: The Master Chief Collection", playtime_forever=150)
    enriched = enrich_steam_games([game])

    assert len(enriched) == 1
    assert enriched[0].appid == 976730
    assert enriched[0].status == AntiCheatStatus.SUPPORTED
    assert "Easy Anti-Cheat" in enriched[0].anticheats
    assert enriched[0].is_tracked is True
    assert enriched[0].playtime_hours == 2.5


def test_enrich_unlisted_game():
    # An indie game or single-player game not tracked in AWACY
    game = SteamGame(appid=99999999, name="Super Indie Quest", playtime_forever=300)
    enriched = enrich_steam_games([game])

    assert len(enriched) == 1
    assert enriched[0].appid == 99999999
    assert enriched[0].status == AntiCheatStatus.UNLISTED
    assert enriched[0].is_tracked is False
    assert enriched[0].anticheats == []


def test_build_scan_response_stats():
    games = [
        SteamGame(appid=976730, name="Halo MCC", playtime_forever=100),  # Supported
        SteamGame(appid=578080, name="PUBG", playtime_forever=200),  # Broken
        SteamGame(appid=1085660, name="Destiny 2", playtime_forever=150),  # Denied
        SteamGame(appid=99999999, name="Indie Game", playtime_forever=50),  # Unlisted
    ]
    resp = build_scan_response(
        steamid="76561198000000001",
        games=games,
        summary={"personaname": "TestUser"},
    )

    assert resp.total_games == 4
    assert resp.tracked_games == 3
    assert resp.status_counts["Supported"] == 1
    assert resp.status_counts["Broken"] == 1
    assert resp.status_counts["Denied"] == 1
    assert resp.status_counts["Unlisted"] == 1
    # Playable = (Supported: 1 + Running: 0 + Unlisted: 1) / 4 = 50.0%
    assert resp.playable_percentage == 50.0


def test_private_profile_scan_response():
    resp = build_scan_response(
        steamid="76561198000000001",
        games=[],
        is_private=True,
        message="Private profile",
    )

    assert resp.is_private is True
    assert resp.total_games == 0
    assert resp.playable_percentage == 0.0

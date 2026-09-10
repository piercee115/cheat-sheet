from pathlib import Path
from app.cache import AntiCheatCache, normalize_title


def test_normalize_title():
    assert normalize_title("Halo: The Master Chief Collection") == "halo the master chief collection"
    assert normalize_title("Battlefield™ 2042") == "battlefield 2042"
    assert normalize_title("Tom Clancy's Rainbow Six® Siege") == "tom clancy s rainbow six siege"


def test_cache_indexing_and_lookup(tmp_path: Path):
    mock_games = [
        {
            "name": "Halo: The Master Chief Collection",
            "status": "Supported",
            "anticheats": ["Easy Anti-Cheat"],
            "native": False,
            "storeIds": {"steam": "976730"},
            "notes": [["Works great", "https://example.com"]],
        },
        {
            "name": "Destiny 2",
            "status": "Broken",
            "anticheats": ["BattlEye"],
            "native": False,
            "storeIds": {"steam": "1085660"},
        },
        {
            "name": "Fortnite",
            "status": "Denied",
            "anticheats": ["Easy Anti-Cheat"],
            "native": False,
            "storeIds": {"epic": "fn"},
        },
    ]

    cache = AntiCheatCache(data_dir=tmp_path)
    cache._rebuild_index(mock_games, source="test")

    # Verify counts
    assert cache.raw_count == 3
    assert cache.total_indexed == 2  # Only 2 have steam App IDs

    # O(1) Steam App ID lookup
    halo = cache.get_by_appid(976730)
    assert halo is not None
    assert halo.name == "Halo: The Master Chief Collection"
    assert halo.status == "Supported"
    assert "Easy Anti-Cheat" in halo.anticheats

    destiny = cache.get_by_appid("1085660")
    assert destiny is not None
    assert destiny.status == "Broken"

    # Fallback name lookup for non-steam or title-based match
    fortnite = cache.get_by_name("Fortnite")
    assert fortnite is not None
    assert fortnite.status == "Denied"

    # Missing game
    missing = cache.get_by_appid(999999999)
    assert missing is None

    # Stats
    stats = cache.get_stats()
    assert stats["total_games"] == 3
    assert stats["steam_mapped_games"] == 2
    assert stats["status_breakdown"]["Supported"] == 1
    assert stats["status_breakdown"]["Broken"] == 1
    assert stats["games_with_notes"] == 1
    assert stats["refresh_interval_hours"] == 3


def test_extract_date_sort_key():
    from app.cache import extract_date_sort_key
    assert extract_date_sort_key("2024-10-31") == (2024, 10, 31)
    assert extract_date_sort_key("Oct 31, 2024") == (2024, 10, 31)
    assert extract_date_sort_key("Apr 12, 2022 GMT+2") == (2022, 4, 12)
    assert extract_date_sort_key("Fri, 26 Jan 2024 14:00:00") == (2024, 1, 26)
    assert extract_date_sort_key("") == (0, 0, 0)
    assert extract_date_sort_key(None) == (0, 0, 0)


def test_cache_recent_updates(tmp_path: Path):
    mock_games = [
        {
            "name": "Game Older",
            "status": "Running",
            "anticheats": ["EAC"],
            "native": False,
            "updates": [
                {"name": "Older Update", "date": "2023-01-15", "reference": "https://old.com"}
            ],
        },
        {
            "name": "Game Newer",
            "status": "Supported",
            "anticheats": ["BattlEye"],
            "native": True,
            "updates": [
                {"name": "Newer Update", "date": "2024-06-20", "reference": "https://new.com"}
            ],
        },
    ]

    cache = AntiCheatCache(data_dir=tmp_path)
    cache._rebuild_index(mock_games, source="test")

    recent = cache.get_recent_updates(limit=10)
    assert len(recent) == 2
    # Ensure newest update comes first
    assert recent[0]["game_name"] == "Game Newer"
    assert recent[0]["update_name"] == "Newer Update"
    assert recent[1]["game_name"] == "Game Older"


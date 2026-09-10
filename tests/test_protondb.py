import pytest
from starlette.testclient import TestClient
from app.main import app
from app.protondb import protondb_cache


@pytest.fixture(scope="module", autouse=True)
def init_caches():
    """Ensure protondb cache and awacy cache are loaded for tests."""
    protondb_cache.load_cache()


def test_protondb_cache_seed_loading():
    """Verify seed ProtonDB entries are loaded into cache."""
    cs2 = protondb_cache.get(730)
    assert cs2 is not None
    assert cs2["tier"] in ("gold", "platinum")
    assert cs2["confidence"] == "strong"

    # Cyberpunk 2077
    cp = protondb_cache.get(1091500)
    assert cp is not None
    assert cp["tier"] == "gold"

    # Hades
    hades = protondb_cache.get(1145360)
    assert hades is not None
    assert hades["tier"] == "platinum"


def test_protondb_api_endpoint_cached():
    """Verify GET /api/protondb/{appid} returns cached summary."""
    with TestClient(app) as client:
        resp = client.get("/api/protondb/730")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] in ("gold", "platinum")
        assert "confidence" in data


def test_demo_endpoint_includes_protondb_tiers():
    """Verify demo library responses contain ProtonDB tier metrics and game tiers."""
    with TestClient(app) as client:
        resp = client.get("/api/demo?profile=competitive")
        assert resp.status_code == 200
        data = resp.json()

        # Check protondb_counts exists and is populated
        assert "protondb_counts" in data
        pdb_counts = data["protondb_counts"]
        assert isinstance(pdb_counts, dict)
        assert sum(pdb_counts.values()) == data["total_games"]

        # Check each game has protondb_tier
        for game in data["games"]:
            assert "protondb_tier" in game
            assert game["protondb_tier"] is not None
            assert game["protondb_tier"] in ("platinum", "gold", "silver", "bronze", "borked", "pending")


def test_scan_demo_includes_protondb():
    """Verify query=demo in /api/scan includes ProtonDB tiers."""
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=demo")
        assert resp.status_code == 200
        data = resp.json()
        assert "protondb_counts" in data
        assert any(g["protondb_tier"] != "pending" for g in data["games"])


@pytest.mark.asyncio
async def test_resolve_many():
    """Verify concurrent batch resolution uses cache and returns dict."""
    import httpx
    async with httpx.AsyncClient() as client:
        results = await protondb_cache.resolve_many(client, [730, 1172470, 976730])
        assert 730 in results
        assert results[730]["tier"] in ("gold", "platinum")
        assert 1172470 in results
        assert 976730 in results

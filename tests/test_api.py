import pytest
from starlette.testclient import TestClient
from app.main import app
from app.cache import awacy_cache


@pytest.fixture(scope="module", autouse=True)
def init_test_cache():
    """Ensure seed cache is loaded for tests."""
    awacy_cache.load_initial_data()


def test_health_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["steam_mapped"] > 0


def test_db_status_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/db/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_games" in data
        assert "steam_mapped_games" in data
        assert data["steam_mapped_games"] > 0


def test_index_page():
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Cheatsheet" in resp.text
        assert "Anti-Cheat Compatibility" in resp.text


def test_demo_endpoint_competitive():
    with TestClient(app) as client:
        resp = client.get("/api/demo?profile=competitive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_demo"] is True
        assert data["total_games"] > 0
        assert len(data["games"]) > 0
        assert "Supported" in data["status_counts"]
        assert "Broken" in data["status_counts"]


def test_demo_endpoint_steamdeck():
    with TestClient(app) as client:
        resp = client.get("/api/demo?profile=steamdeck")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_demo"] is True
        assert data["personaname"] == "Sam (Steam Deck Fan)"


def test_scan_with_demo_keyword():
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=demo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_demo"] is True
        assert data["total_games"] > 0


def test_scan_invalid_query():
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=https://malicious-site.com/hack")
        assert resp.status_code == 400


def test_rate_limiting():
    from app.main import RATE_LIMIT_SCAN_MAX, _rate_limits
    _rate_limits.clear()
    with TestClient(app) as client:
        # Trigger requests up to limit
        for _ in range(RATE_LIMIT_SCAN_MAX):
            resp = client.get("/api/scan?query=demo")
            assert resp.status_code == 200

        # Next request should be rate-limited
        resp = client.get("/api/scan?query=demo")
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"
    _rate_limits.clear()


def test_manual_sync_disabled():
    with TestClient(app) as client:
        resp = client.post("/api/db/refresh")
        assert resp.status_code == 403
        assert "disabled to prevent spam" in resp.json()["detail"]


def test_honeypot_blocking():
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=demo&b_check=bot_payload")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Bot activity detected."


def test_abusive_bot_ua_blocked():
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=demo", headers={"User-Agent": "sqlmap/1.6#dev"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Automated bot traffic blocked."


def test_anti_bot_token_verification():
    from app.main import generate_anti_bot_token, verify_anti_bot_token
    token = generate_anti_bot_token("192.168.1.50")
    assert verify_anti_bot_token(token, "192.168.1.50") is True
    # Different IP should fail
    assert verify_anti_bot_token(token, "192.168.1.99") is False
    # Malformed token should fail
    assert verify_anti_bot_token("invalid_token_123", "192.168.1.50") is False
    assert verify_anti_bot_token(None, "192.168.1.50") is False



def test_db_updates_endpoint():
    with TestClient(app) as client:
        resp = client.get("/api/db/updates?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "updates" in data
        assert isinstance(data["updates"], list)
        if len(data["updates"]) > 0:
            first = data["updates"][0]
            assert "game_name" in first
            assert "status" in first
            assert "update_name" in first
            assert "date" in first


def test_game_detail_endpoint_found():
    with TestClient(app) as client:
        # Halo MCC AppID 976730
        resp = client.get("/api/game/976730")
        assert resp.status_code == 200
        data = resp.json()
        assert data["appid"] == 976730
        assert data["status"] == "Supported"
        assert "notes" in data
        assert "updates" in data
        assert isinstance(data["notes"], list)
        assert isinstance(data["updates"], list)


def test_game_detail_endpoint_not_found():
    with TestClient(app) as client:
        resp = client.get("/api/game/999999999")
        assert resp.status_code == 404


def test_scan_includes_notes_and_updates():
    with TestClient(app) as client:
        resp = client.get("/api/scan?query=demo")
        assert resp.status_code == 200
        data = resp.json()
        games = data["games"]
        assert len(games) > 0
        # Verify enriched fields exist on games
        first = games[0]
        assert "notes" in first
        assert "updates" in first
        assert "notes_count" in first
        assert "updates_count" in first



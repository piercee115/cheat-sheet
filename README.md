# 🛡️ Cheatsheet: Steam Anti-Cheat Compatibility Checker

A high-performance, ultra-lightweight web application that cross-references a user's Steam library with the [Are We Anti-Cheat Yet?](https://areweanticheatyet.com) database. Designed for Linux and Steam Deck gamers to instantly identify which games run out of the box, require proton tweaks, or are blocked by invasive anti-cheat systems.

---

## ⚡ Key Features

- **Sub-Millisecond In-Memory Index:** Thread-safe O(1) hash map index keyed by Steam App ID, eliminating external database bottlenecks during scans.
- **Automated 12-Hour TTL Background Worker:** Periodically checks and syncs upstream updates from AreWeAntiCheatYet with an atomic swap.
- **Zero-Friction Universal Input:** Single input field auto-detects 17-digit SteamID64s, full Steam community URLs, custom vanity URLs, and raw profile handles.
- **Instant Client-Side Filtering:** Real-time debounced search (150ms) and multi-status category toggles (Supported, Running, Broken, Denied, Unlisted) executing entirely in the browser with 0ms network latency.
- **Plain-Language Privacy Recovery:** Clear step-by-step guidance for users with private Steam profiles on how to set Game Details to Public.
- **Zero-Config Demo Mode:** Pre-loaded realistic sample libraries (Competitive Gamer, Steam Deck Favorites) allow immediate exploration even without a Steam API key.
- **Data Export:** Instant one-click export of scanned compatibility reports to JSON or CSV.

---

## 🚀 Quick Start (Single-Command Deployment)

### Option 1: Docker Compose (Recommended)

Clone the repository and run:

```bash
docker compose up -d --build
```

The application will be live at `http://localhost:8000`.

To view logs or stop:
```bash
docker compose logs -f
docker compose down
```

### Option 2: Local Deployment & Systemd Service (`./deploy.sh`)

If running outside Docker on Linux:

```bash
# Automated setup and start as a background daemon
./deploy.sh start

# Check status and health
./deploy.sh status

# View live service logs
./deploy.sh logs

# Stop background service
./deploy.sh stop
```

To run interactively in foreground development mode:
```bash
./deploy.sh run
```

To install as a persistent user `systemd` unit:
```bash
./deploy.sh install-service
```

---

## ⚙️ Configuration & Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `STEAM_API_KEY` | `""` | Steam Web API Key from [Valve](https://steamcommunity.com/dev/apikey). *(Optional for Demo Mode)* |
| `PORT` | `8000` | Port for web server binding. |
| `HOST` | `0.0.0.0` | Host interface address. |
| `CACHE_TTL_HOURS`| `3` | Background worker refresh interval for AWACY `games.json`. |
| `AWACY_DATABASE_URL` | Upstream GitHub | Upstream URL for `games.json`. |

### Getting a Free Steam API Key
1. Visit [https://steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey).
2. Log in with your Steam account and enter a domain name (e.g. `localhost`).
3. Copy the generated key and place it in your `.env` file:
   ```env
   STEAM_API_KEY="YOUR_KEY_HERE"
   ```

---

## 🔧 Architecture Overview

```
cheatsheet/
├── app/
│   ├── main.py            # FastAPI routes, lifespan manager, security headers
│   ├── config.py          # Pydantic Settings & environment handling
│   ├── cache.py           # Thread-safe in-memory O(1) hash map & 12h background worker
│   ├── steam.py           # Universal input parser & Steam Web API client
│   ├── models.py          # Pydantic data schemas & enums
│   ├── demo_data.py       # Realistic sample profile fixtures
│   ├── templates/         # Server-rendered Jinja2 HTML templates
│   │   ├── base.html      # Responsive base layout with Tailwind CDN
│   │   └── index.html     # Interactive dashboard with real-time UI
│   └── static/
│       ├── css/app.css    # Custom transitions, badges, and scrollbars
│       └── js/app.js      # Debounced client-side filtering, sorting, export
├── data/
│   └── seed_games.json    # Seed snapshot for instant 0ms offline boot
├── tests/                 # Automated pytest test suite
├── Dockerfile             # Multi-stage minimal production image (non-root)
├── docker-compose.yml     # Compose file with healthchecks & persistent volume
├── deploy.sh              # Local dependency manager & systemd unit controller
├── requirements.txt       # Production dependencies
└── requirements-dev.txt   # Development & test dependencies
```

---

## 🌐 API Reference

- **`GET /`**: Serves the web interface.
- **`GET /api/scan?query={query}`**: Resolves Steam identifier, queries user library, and returns anti-cheat compatibility report.
- **`GET /api/demo?profile={competitive|steamdeck}`**: Returns sample pre-loaded profile.
- **`GET /api/health`**: Healthcheck endpoint for Docker/systemd (`status: healthy`).
- **`GET /api/db/status`**: In-memory cache statistics and status breakdown.
- **`POST /api/db/refresh`**: Triggers immediate asynchronous sync with upstream AWACY database.

---

## 🧪 Automated Testing

Execute the test suite using `deploy.sh` or `pytest`:

```bash
./deploy.sh test
# Or directly:
.venv/bin/pytest tests/ -v
```

---

## 🔒 Security

- Built with strict input sanitization preventing SSRF, command injection, and open redirect vectors.
- Runs as non-root unprivileged user (`appuser:appgroup`, UID 10001) in Docker.
- Includes HTTP security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and restricted `Permissions-Policy`.
- Zero database injection surface (in-memory hash maps with pydantic type enforcement).

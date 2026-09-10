# Cheatsheet: Steam Anti-Cheat Compatibility Checker

[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Check which games in your Steam library run on Linux via Proton and which are blocked by kernel anti-cheat engines (Easy Anti-Cheat, BattlEye, Vanguard, Ricochet).

**Live App:** [cheatsheet.bowieslab.xyz](https://cheatsheet.bowieslab.xyz)

---

## Features

**Universal Profile Input:** Paste your full Steam profile link, custom vanity URL (`/id/yourname`), or 17-digit SteamID64.
**Anti-Cheat Engine Breakdown:** Instantly identifies kernel-level anti-cheat systems (BattlEye, Easy Anti-Cheat, Vanguard, nProtect, etc.) and native Linux support.
**ProtonDB Tier Integration:** Displays ProtonDB community ratings (Platinum, Gold, Silver, Bronze, Borked) alongside anti-cheat verdicts.
**Community Notes & Timeline:** View verified launch options, community workaround guides, and historical developer status updates.
**Real-Time Client-Side Filtering:** Search, toggle status pills, and sort table columns by clicking headers with zero latency.
**Privacy-First:** Reads publicly available Steam data only. No login required, no tracking cookies, and no passwords stored.
**Export Reports:** One-click export of your library's compatibility summary to JSON or CSV.

---

Quick Start with Docker

The easiest way to self-host Cheatsheet is with Docker Compose.

### 1. Clone the repository

```bash
git clone https://github.com/piercee115/cheatsheet.git
cd cheatsheet
```

### 2. Configure your Steam API key

```bash
cp .env.example .env
```

Open `.env` and add your free Steam Web API key:

```env
STEAM_API_KEY="your_api_key_here"
```

_(Get a free key in seconds at [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey))._

### 3. Start the container

```bash
docker compose up -d
```

Visit **`http://localhost:8000`** in your browser.

To stop or view logs:

```bash
docker compose logs -f    # View logs
docker compose down       # Stop container
```

---

## Configuration

Set these variables in your `.env` file or Docker environment:

| Variable          | Default | Description                                                                                          |
| :---------------- | :------ | :--------------------------------------------------------------------------------------------------- |
| `STEAM_API_KEY`   | `""`    | Steam Web API Key ([Get one here](https://steamcommunity.com/dev/apikey)). _Optional for demo mode._ |
| `PORT`            | `8000`  | Port for web server binding.                                                                         |
| `CACHE_TTL_HOURS` | `3`     | Background auto-sync interval for upstream [AWACY](https://areweanticheatyet.com) data.              |

---

## Non-Docker Setup (Optional)

If running directly on Linux without Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Or use the included helper script:

```bash
./deploy.sh start    # Start background daemon
./deploy.sh status   # Check status
./deploy.sh stop     # Stop daemon
```

---

## Testing

Run the automated test suite with `pytest`:

```bash
pytest tests/ -v
```

---

## Legal & Privacy Notice

- **Powered by Steam:** This application uses the Steam Web API but is not endorsed, certified, or affiliated with Valve Corporation. Steam and the Steam logo are trademarks of Valve Corporation.
- **Powered by AWACY & ProtonDB:** Compatibility data is gathered from the open-source community at [Are We Anti-Cheat Yet?](https://areweanticheatyet.com) and [ProtonDB](https://www.protondb.com).
- **Privacy:** Only publicly accessible Steam profile information is queried on demand. No personal data or credentials are ever stored.

---

## License

Distributed under the [MIT License](LICENSE). Contributions, bug reports, and suggestions are welcome!

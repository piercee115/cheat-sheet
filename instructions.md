Build a high-performance, ultra-lightweight web application that cross-references a user's Steam library with the "Are We Anti-Cheat Yet?" database. Optimize for instant load times, zero interface friction, and automated deployment.

1. Repository & Automated Deployment Setup
- **Git Initialization:** Automatically run `git init`, create a `.gitignore` (excluding environment secrets, virtual environments, or compiled binaries), and create an initial commit containing the scaffolding.
- **Single-Command Deployment:** Provide a fully configured `docker-compose.yml` and optimized `Dockerfile` (using multi-stage minimal builds like Alpine or Distroless) so the entire application can be deployed instantly using `docker compose up -d`.
- **System Service Fallback:** Provide a simple bash script (`deploy.sh`) to automate local dependencies setup, environment checking, and running the application as a background systemd service for non-Docker environments.

2. Performance & Architecture
- Use a high-efficiency backend stack (Go or Python with FastAPI/uvloop) ensuring sub-millisecond data lookups and concurrent async requests.
- Implement an in-memory thread-safe hash map index of the "Are We Anti-Cheat Yet?" dataset (`games.json`) keyed by Steam App ID for O(1) lookups.
- Fetch `games.json` via a background worker with a 12-hour TTL cache to eliminate external network latency during user scans.
- Use a lightweight frontend approach (Server-rendered HTML + Tailwind CSS + vanilla JS, or HTMX) to ensure the interface renders and updates instantly.

3. Frictionless User Experience (UX)
- Provide a single input field that dynamically accepts a SteamID64, a custom vanity URL, or a full profile link.
- Auto-detect and parse inputs seamlessly without requiring the user to specify their profile type.
- Display results in a clean, scannable layout grouped by status (Supported, Running, Broken, Denied) with distinct color coding.
- Implement client-side debounce search and instant filter toggles that execute locally without page reloads.
- Gracefully handle private profile restrictions with a clear, plain-language notification explaining how to toggle Steam privacy settings.

4. Deliverables
- A production-ready project layout with a committed Git history.
- `docker-compose.yml`, `Dockerfile`, and `.env.example` defining `STEAM_API_KEY` and port bindings.
- A concise `README.md` detailing the single-line deployment command, configuration steps, and environment variable requirements.

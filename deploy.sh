#!/usr/bin/env bash
# ==============================================================================
# Cheatsheet: Steam Anti-Cheat Compatibility Checker - Deployment & Service Script
# ==============================================================================

set -eo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
PID_FILE="${APP_DIR}/cheatsheet.pid"
LOG_FILE="${APP_DIR}/cheatsheet.log"
SERVICE_NAME="cheatsheet.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

cd "${APP_DIR}"

# ANSI Colors
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

log_info() { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_python() {
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 is not installed. Please install Python 3.10+."
        exit 1
    fi
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Found Python version: ${PY_VER}"
}

setup_env() {
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            log_info "No .env found. Creating .env from .env.example..."
            cp .env.example .env
        else
            touch .env
        fi
    fi
}

setup_venv() {
    if [ ! -d "${VENV_DIR}" ]; then
        log_info "Creating virtual environment at ${VENV_DIR}..."
        python3 -m venv "${VENV_DIR}"
    fi

    log_info "Verifying and updating Python dependencies..."
    "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
    "${VENV_DIR}/bin/pip" install --quiet -r requirements.txt
    log_success "Virtual environment is ready."
}

run_docker() {
    log_info "Deploying via Docker Compose..."
    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        docker compose up -d --build
        log_success "Application deployed via Docker Compose!"
        docker compose ps
    else
        log_error "Docker or Docker Compose is not available. Falling back to local setup."
        return 1
    fi
}

install_systemd_service() {
    log_info "Configuring systemd user service..."
    mkdir -p "${SYSTEMD_USER_DIR}"

    cat <<EOF > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
[Unit]
Description=Cheatsheet Steam Anti-Cheat Checker
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
EnvironmentFile=-${APP_DIR}/.env

[Install]
WantedBy=default.target
EOF

    if command -v systemctl &>/dev/null; then
        systemctl --user daemon-reload || true
        systemctl --user enable "${SERVICE_NAME}" || true
        log_success "Systemd user service installed at: ${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
    else
        log_warn "systemctl not accessible in current session. Service unit created."
    fi
}

cmd_start() {
    setup_env
    setup_venv

    # Try starting systemd user service if available
    if command -v systemctl &>/dev/null && systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        log_warn "Service ${SERVICE_NAME} is already running via systemd."
        return 0
    fi

    if command -v systemctl &>/dev/null && [ -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" ]; then
        log_info "Starting via systemd user service..."
        systemctl --user start "${SERVICE_NAME}" && {
            log_success "Cheatsheet started via systemd!"
            systemctl --user status "${SERVICE_NAME}" --no-pager
            return 0
        } || log_warn "Systemd start failed, falling back to background daemon..."
    fi

    # Fallback to background process with PID tracking
    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        log_warn "Cheatsheet is already running (PID: $(cat "${PID_FILE}"))."
        return 0
    fi

    log_info "Starting Cheatsheet daemon in background..."
    nohup "${VENV_DIR}/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop > "${LOG_FILE}" 2>&1 &
    echo $! > "${PID_FILE}"
    sleep 1.5

    if kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        log_success "Cheatsheet is running! (PID: $(cat "${PID_FILE}"))"
        log_info "URL: http://localhost:8000"
        log_info "Logs: ${LOG_FILE}"
    else
        log_error "Failed to start. Check logs at ${LOG_FILE}:"
        cat "${LOG_FILE}"
        exit 1
    fi
}

cmd_stop() {
    # Check systemd user service
    if command -v systemctl &>/dev/null && [ -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" ]; then
        log_info "Stopping systemd service..."
        systemctl --user stop "${SERVICE_NAME}" 2>/dev/null || true
    fi

    # Check PID file
    if [ -f "${PID_FILE}" ]; then
        PID=$(cat "${PID_FILE}")
        if kill -0 "${PID}" 2>/dev/null; then
            log_info "Stopping process PID ${PID}..."
            kill "${PID}" || true
            sleep 1
            kill -9 "${PID}" 2>/dev/null || true
        fi
        rm -f "${PID_FILE}"
        log_success "Cheatsheet stopped."
    else
        log_info "No PID file found. Checking for lingering uvicorn processes..."
        pkill -f "uvicorn app.main:app" || true
        log_success "Cheatsheet processes stopped."
    fi
}

cmd_status() {
    if command -v systemctl &>/dev/null && [ -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}" ]; then
        echo -e "${CYAN}=== Systemd Service Status ===${NC}"
        systemctl --user status "${SERVICE_NAME}" --no-pager || true
    fi

    if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
        log_success "Background daemon is RUNNING (PID: $(cat "${PID_FILE}"))."
    else
        log_info "Background daemon is NOT running."
    fi

    echo -e "${CYAN}=== Health Check Endpoint ===${NC}"
    if curl -s http://localhost:8000/api/health 2>/dev/null; then
        echo ""
    else
        echo "Unable to reach http://localhost:8000/api/health"
    fi
}

cmd_run() {
    check_python
    setup_env
    setup_venv
    log_info "Starting Cheatsheet in foreground mode..."
    exec "${VENV_DIR}/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload
}

cmd_test() {
    check_python
    setup_env
    setup_venv
    "${VENV_DIR}/bin/pip" install --quiet -r requirements-dev.txt
    log_info "Running test suite..."
    "${VENV_DIR}/bin/pytest" tests/ -v
}

cmd_logs() {
    if [ -f "${LOG_FILE}" ]; then
        tail -f -n 50 "${LOG_FILE}"
    elif command -v journalctl &>/dev/null; then
        journalctl --user -u "${SERVICE_NAME}" -f -n 50
    else
        log_error "No log file found."
    fi
}

# Main CLI dispatch
case "${1:-}" in
    --docker)
        run_docker
        ;;
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_stop
        sleep 1
        cmd_start
        ;;
    status)
        cmd_status
        ;;
    logs)
        cmd_logs
        ;;
    run)
        cmd_run
        ;;
    test)
        cmd_test
        ;;
    install-service)
        check_python
        setup_env
        setup_venv
        install_systemd_service
        ;;
    help|--help|-h|"")
        echo "Usage: $0 {start|stop|restart|status|logs|run|test|install-service|--docker}"
        echo ""
        echo "Commands:"
        echo "  start           Start Cheatsheet as a background service"
        echo "  stop            Stop Cheatsheet background service"
        echo "  restart         Restart Cheatsheet service"
        echo "  status          Check service status and healthcheck endpoint"
        echo "  logs            View real-time service logs"
        echo "  run             Run Cheatsheet in foreground development mode"
        echo "  test            Execute automated pytest test suite"
        echo "  install-service Install and enable systemd user service"
        echo "  --docker        Build and launch via docker compose up -d"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Run '$0 --help' for usage."
        exit 1
        ;;
esac

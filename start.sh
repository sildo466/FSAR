#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
    echo "[FSAR] ERROR: please run from the fsar project root (pyproject.toml not found)" >&2
    exit 1
fi
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[FSAR] ERROR: python3 not found. Install Python 3.11+: brew install python@3.11 or apt install python3.11" >&2
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "[FSAR] ERROR: node not found. Install Node 18+: brew install node or nvm install 18" >&2
    exit 1
fi

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON=python
else
    echo "[FSAR] WARNING: .venv not found, using system python3"
    PYTHON=python3
fi

bash "$SCRIPT_DIR/scripts/_frontend.sh"

pkill -f "src.server.ws_server" >/dev/null 2>&1 || true

bash "$SCRIPT_DIR/scripts/_backend.sh" "$PYTHON" &
BACKEND_PID=$!

echo "[FSAR] Waiting for backend at http://127.0.0.1:8765 ..."
i=1
while [ "$i" -le 30 ]; do
    if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
        echo "[FSAR] Backend ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[FSAR] ERROR: backend did not become ready in 30s" >&2
        echo "[FSAR] Check: tail -n 50 $SCRIPT_DIR/data/logs/backend.log" >&2
        exit 1
    fi
    sleep 1
    i=$((i + 1))
done

URL="http://127.0.0.1:8765"
if [ "$(uname -s)" = "Darwin" ]; then
    if ! open "$URL"; then
        echo "[FSAR] Browser did not open. Visit $URL manually."
    fi
elif command -v xdg-open >/dev/null 2>&1; then
    if ! xdg-open "$URL"; then
        echo "[FSAR] Browser did not open. Visit $URL manually."
    fi
else
    echo "[FSAR] xdg-open not found. Visit $URL manually."
fi

echo "[FSAR] Backend + GUI on $URL"
echo "[FSAR] Edit code and re-run ./start.sh to pick up changes."

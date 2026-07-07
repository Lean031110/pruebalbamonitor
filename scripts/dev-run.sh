#!/bin/bash
# ============================================================
# LBAMonitor — Script de desarrollo (Linux/Mac/WSL)
# Levanta backend + frontend en modo dev
# ============================================================

set -e
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== LBAMonitor dev ==="
echo "Project: $PROJECT_ROOT"
echo ""

# Verificar venv
VENV_DIR="$PROJECT_ROOT/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# Instalar deps backend si hace falta
echo "Checking backend deps..."
pip install -q -e "$BACKEND_DIR[dev]" 2>/dev/null || true

# Init BD si no existe
export LBAMONITOR_DATABASE__PATH="${LBAMONITOR_DATABASE__PATH:-$PROJECT_ROOT/data/lbamonitor.db}"
mkdir -p "$(dirname "$LBAMONITOR_DATABASE__PATH")"

# Inicializar BD
if [ ! -f "$LBAMONITOR_DATABASE__PATH" ]; then
    echo "Initializing database..."
    lbamonitor-cli init-db
fi

# Iniciar backend (puerto 8123)
echo ""
echo "Starting backend on http://127.0.0.1:8123 ..."
echo "  Docs: http://127.0.0.1:8123/docs"
echo ""
lbamonitor-svc &
SVC_PID=$!

# Iniciar frontend (puerto 5173 con proxy a 8123)
if [ -d "$FRONTEND_DIR" ]; then
    echo ""
    echo "Starting frontend on http://localhost:5173 ..."
    cd "$FRONTEND_DIR"
    if [ ! -d node_modules ]; then
        npm install
    fi
    npm run dev &
    FE_PID=$!
fi

# Trap Ctrl+C
trap 'echo ""; echo "Stopping..."; kill $SVC_PID 2>/dev/null; kill $FE_PID 2>/dev/null; exit 0' INT TERM

# Esperar
wait

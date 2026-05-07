#!/usr/bin/env sh
# Post-provision hook: install Python deps and create the Foundry agent.
set -e

echo "==> Installing Python dependencies..."
PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
    echo "==> Creating virtual environment..."
    "$PYTHON" -m venv .venv
fi

VENV_PY=".venv/bin/python"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r requirements.txt

echo "==> Creating Foundry agent..."
"$VENV_PY" -m src.create_agent_with_voicelive

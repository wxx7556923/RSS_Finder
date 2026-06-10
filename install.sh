#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

install_python_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    return 1
  fi

  echo "Installing Python base packages with apt..."
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
  else
    apt-get update
    apt-get install -y python3 python3-venv python3-pip
  fi
}

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import venv" >/dev/null 2>&1; then
  install_python_packages || {
    echo "python3 and python3-venv are required."
    echo "On Ubuntu/Debian, run: sudo apt-get install -y python3 python3-venv python3-pip"
    exit 1
  }
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import venv" >/dev/null 2>&1; then
  echo "python3 and python3-venv are required."
  echo "On Ubuntu/Debian, run: sudo apt-get install -y python3 python3-venv python3-pip"
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi

mkdir -p data output logs

echo "Install complete."
echo "Edit .env, then run: ./paper-radar"
echo "Optional one-time shortcut: bash install-command.sh"

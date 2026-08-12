#!/usr/bin/env bash
# Kord setup. Run once: ./setup.sh
#
# Deliberately not a shell one-liner: the extras syntax `.[dev,btc]` is a glob
# pattern in zsh, so an unquoted or mis-quoted copy-paste aborts silently.
set -euo pipefail

cd "$(dirname "$0")"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mSetup failed: %s\033[0m\n' "$1" >&2; exit 1; }

step "Checking prerequisites"
command -v ffmpeg >/dev/null || fail "ffmpeg not found. Run: brew install ffmpeg"
command -v yt-dlp >/dev/null || fail "yt-dlp not found. Run: brew install yt-dlp"
command -v npm    >/dev/null || fail "npm not found. Install Node 18 or newer."
echo "ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3), yt-dlp $(yt-dlp --version), npm $(npm --version)"

step "Creating the Python 3.11 virtualenv"
if [ ! -d .venv ]; then
  PY=""
  for candidate in python3.11 /usr/local/bin/python3.11 /opt/homebrew/bin/python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
  [ -n "$PY" ] || fail "python3.11 not found. Run: brew install python@3.11"
  "$PY" -m venv .venv
  echo "created with $PY"
else
  echo "already present"
fi

VENV_PY="$PWD/.venv/bin/python"
"$VENV_PY" -c 'import sys; assert sys.version_info[:2] == (3, 11), sys.version' \
  || fail ".venv is not Python 3.11. Delete .venv and re-run."

step "Installing Python dependencies"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -e '.[dev,btc]'
echo "installed"

step "Fetching the chord model (12 MB, one time)"
"$VENV_PY" -m kord.analysis.btc --fetch-weights

step "Installing frontend dependencies"
(cd frontend && npm install --silent)
echo "installed"

step "Verifying"
"$VENV_PY" -m pytest -q 2>&1 | tail -1

if [ ! -f .env ]; then
  cp .env.example .env
  printf '\n\033[33mOne thing left:\033[0m edit .env and paste your Spotify client ID.\n'
  printf 'Create an app at https://developer.spotify.com/dashboard with redirect URI:\n'
  printf '  http://localhost:8000/api/auth/callback\n'
else
  echo ".env already exists, leaving it alone"
fi

printf '\n\033[1mSetup complete.\033[0m Start Kord with: ./run.sh\n'

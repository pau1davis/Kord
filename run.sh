#!/usr/bin/env bash
# Start Kord: API, analysis worker, and UI. Ctrl-C stops all three.
set -euo pipefail

cd "$(dirname "$0")"

[ -d .venv ] || { echo "No .venv. Run ./setup.sh first." >&2; exit 1; }
[ -f .env ]  || { echo "No .env. Run ./setup.sh first." >&2; exit 1; }

# shellcheck disable=SC1091
set -a; source .env; set +a

if [ -z "${SPOTIFY_CLIENT_ID:-}" ] || [ "${SPOTIFY_CLIENT_ID}" = "your_client_id_here" ]; then
  echo "SPOTIFY_CLIENT_ID is not set in .env." >&2
  echo "Create an app at https://developer.spotify.com/dashboard and paste its Client ID." >&2
  echo "Set the redirect URI to http://localhost:8000/api/auth/callback" >&2
  exit 1
fi

VENV_BIN="$PWD/.venv/bin"
pids=()

cleanup() {
  echo
  echo "Stopping Kord..."
  for pid in "${pids[@]:-}"; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API on :8000"
"$VENV_BIN/uvicorn" kord.app:build_app --factory --port 8000 --app-dir backend &
pids+=($!)

echo "Starting analysis worker"
"$VENV_BIN/python" -m kord.queue &
pids+=($!)

echo "Starting UI"
(cd frontend && npm run dev) &
pids+=($!)

echo
echo "Kord is starting. The UI will print its URL below (usually http://localhost:5173)."
echo "Press Ctrl-C to stop everything."
echo
wait

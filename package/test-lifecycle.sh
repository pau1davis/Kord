#!/usr/bin/env bash
# Kord must not leave its server running after it dies.
#
# The app starts uvicorn and a worker as child processes. If they outlive it
# they hold their port and the database's WAL forever, and a user who
# force-quits or crashes accumulates one orphaned pair per launch with no way
# to see or stop them. Cocoa's applicationWillTerminate does not fire on a
# signal, so this is checked against a real SIGTERM rather than a clean quit.
set -uo pipefail
APP="${1:-/Applications/Kord.app}"
LOG="$HOME/Library/Application Support/Kord/kord.log"
SERVERS="$APP/Contents/Resources/python"
fail=0

reap() { for p in $(pgrep -f "$SERVERS" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
         for p in $(pgrep -f "$APP/Contents/MacOS/Kord" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done
         sleep 2; }

check() {  # check <name> <actual> <expected>
  if [ "$2" = "$3" ]; then echo "  ok   $1 ($2)"
  else echo "  FAIL $1: got $2, want $3"; fail=1; fi
}

echo "== a signalled app must still stop its servers =="
reap
before=$(grep -c "Kord stopped" "$LOG" 2>/dev/null || true)
open -a "$APP"
sleep 15
app=$(pgrep -f "$APP/Contents/MacOS/Kord" | head -1)
check "app came up" "$([ -n "$app" ] && echo yes || echo no)" "yes"
check "servers started" "$(pgrep -f "$SERVERS" | wc -l | tr -d ' ')" "2"

[ -n "$app" ] && kill -TERM "$app"
sleep 5
check "app exited" "$(pgrep -f "$APP/Contents/MacOS/Kord" | wc -l | tr -d ' ')" "0"
check "no orphaned servers" "$(pgrep -f "$SERVERS" | wc -l | tr -d ' ')" "0"
after=$(grep -c "Kord stopped" "$LOG" 2>/dev/null || true)
check "shutdown was logged" "$([ "$after" -gt "$before" ] && echo yes || echo no)" "yes"

echo "== a stale server from a previous crash must be reaped on launch =="
reap
open -a "$APP"; sleep 12
app=$(pgrep -f "$APP/Contents/MacOS/Kord" | head -1)
[ -n "$app" ] && kill -9 "$app"          # crash: no cleanup possible at all
sleep 2
check "crash orphans servers (expected)" "$(pgrep -f "$SERVERS" | wc -l | tr -d ' ')" "2"
open -a "$APP"; sleep 15
check "relaunch reaped the orphans" "$(pgrep -f "$SERVERS" | wc -l | tr -d ' ')" "2"
reap

[ "$fail" = 0 ] && echo "PASS" || echo "FAILED"
exit $fail

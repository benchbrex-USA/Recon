#!/bin/bash
# Sable-01 server control v2
# Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
#
# Dual-process lifecycle per designs/sable-agent-integration.md r3:
#   mlx_lm.server on 127.0.0.1:8002 (internal)
#   envelope guard    on 127.0.0.1:8001 (public; token gate, zombie detect)
#
# Usage: ./serve.sh {start|stop|restart|status|test}

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
PUBLIC=8001          # guard
BACKEND_PORT=8002    # mlx
MODEL="$DIR/base"
ADAPTER="$DIR/adapters/r16-run4"  # promoted 2026-10-31: tool gate 9/10 + frozen 27/28 (see PROVENANCE.md)
LOG="$DIR/serve.log"
GUARD_LOG="$DIR/serving/guard.log"
MLX_PID="$DIR/serving/mlx.pid"
GUARD_PID="$DIR/serving/guard.pid"
MARKER="$DIR/serving/zombie"
MARKER_TTL=600

GUARD_URL="http://127.0.0.1:$PUBLIC"
MLX_URL="http://127.0.0.1:$BACKEND_PORT"
ENVELOPE=8192

alive() { curl -s --max-time 2 "$1" >/dev/null 2>&1; }

guard_health() { curl -s --max-time 3 "$GUARD_URL/health" 2>/dev/null; }

start_one() { # $1 name, $2 pidfile, $3 command...
  local name="$1" pidfile="$2"; shift 2
  nohup "$@" >>"$LOG" 2>&1 &
  echo $! > "$pidfile"
}

wait_for() { # $1 url, $2 tries
  for _ in $(seq 1 "${2:-30}"); do
    alive "$1" && return 0
    sleep 2
  done
  return 1
}

cmd_start() {
  if ! [ -d "$DIR/base" ] || ! [ -d "$DIR/venv" ]; then
    echo "FATAL: $DIR/base or venv missing - is the external volume mounted?"; exit 1
  fi
  if alive "$MLX_URL/v1/models"; then
    echo "[mlx] already up on :$BACKEND_PORT"
  else
    echo "[mlx] starting mlx_lm.server on :$BACKEND_PORT (base + r16-run4 adapter, ~3 GB RAM)..."
    start_one mlx "$MLX_PID" "$DIR/venv/bin/python3" -m mlx_lm.server \
      --model "$MODEL" --adapter "$ADAPTER" --host 127.0.0.1 --port "$BACKEND_PORT"
    if ! wait_for "$MLX_URL/v1/models" 30; then
      echo "[mlx] did not come up - check $LOG"; exit 1
    fi
    echo "[mlx] ready"
  fi
  if alive "$GUARD_URL/health"; then
    echo "[guard] already up on :$PUBLIC"
  else
    echo "[guard] starting envelope guard on :$PUBLIC..."
    start_one guard "$GUARD_PID" "$DIR/venv/bin/python3" "$DIR/serving/guard.py"
    if ! wait_for "$GUARD_URL/health" 15; then
      echo "[guard] FAILED - stopping mlx (no orphaned backend); check $GUARD_LOG"
      kill "$(cat "$MLX_PID")" 2>/dev/null
      exit 1
    fi
    echo "[guard] ready"
  fi
  echo "ready: $GUARD_URL/v1 (envelope $ENVELOPE tok)"
}

cmd_stop() {
  # guard first (drains up to 30 s), then mlx
  if [ -f "$GUARD_PID" ]; then
    GPID=$(cat "$GUARD_PID")
    kill "$GPID" 2>/dev/null && {
      echo "[guard] SIGTERM sent (drain <=30 s)..."
      for _ in $(seq 1 15); do alive "$GUARD_URL/health" || break; sleep 2; done
    }
    rm -f "$GUARD_PID"
  fi
  pkill -f "serving/guard.py" 2>/dev/null
  if [ -f "$MLX_PID" ]; then
    kill "$(cat "$MLX_PID")" 2>/dev/null && echo "[mlx] stopped"
    rm -f "$MLX_PID"
  fi
  pkill -f "mlx_lm.server" 2>/dev/null
  echo "stopped"
}

cmd_status() {
  local zombie="no"
  if [ -f "$MARKER" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$MARKER") ))
    [ "$AGE" -le "$MARKER_TTL" ] && zombie="YES (age ${AGE}s)"
  fi
  if alive "$GUARD_URL/health"; then
    echo "[guard] up: $(guard_health | head -c 220)"
  else
    echo "[guard] DOWN"
  fi
  if alive "$MLX_URL/v1/models"; then
    echo "[mlx]   up on :$BACKEND_PORT"
  else
    echo "[mlx]   DOWN"
  fi
  echo "[zombie] $zombie  (recover with: $0 restart)"
}

cmd_test() {
  echo "== 1. short question through guard (expect trained fact) =="
  curl -s --max-time 180 "$GUARD_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model": "default_model", "messages": [{"role": "user", "content": "What is Sable-01? Answer in one sentence."}], "max_tokens": 512, "temperature": 0.3}' \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d["choices"][0]["message"].get("content") or "").strip()[:220])'
  echo "== 2. over-envelope case (expect 413, thread stays alive) =="
  python3 - "$GUARD_URL" <<'PYEOF'
import json, sys, urllib.request, urllib.error
filler = "routine host inventory observation " * 3200   # ~9k tokens
body = json.dumps({"model": "default_model", "messages": [
    {"role": "user", "content": filler + "\n\nWhat is 2+2?"}]}).encode()
req = urllib.request.Request(sys.argv[1] + "/v1/chat/completions", data=body,
                             headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(req, timeout=60)
    print("UNEXPECTED 200 - envelope did not fire")
except urllib.error.HTTPError as e:
    print("status:", e.code, "|", json.loads(e.read())["error"][:90])
PYEOF
  echo "== 3. follow-up short question (thread must still be alive) =="
  curl -s --max-time 180 "$GUARD_URL/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{"model": "default_model", "messages": [{"role": "user", "content": "What does BG Recon do? One sentence."}], "max_tokens": 512, "temperature": 0.3}' \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d["choices"][0]["message"].get("content") or "").strip()[:180])'
}

case "${1:-status}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; sleep 2; cmd_start ;;
  status)  cmd_status ;;
  test)    cmd_test ;;
  *)       echo "usage: $0 {start|stop|restart|status|test}"; exit 2 ;;
esac

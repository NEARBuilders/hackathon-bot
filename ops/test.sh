#!/usr/bin/env bash
# Ask the bot questions using the local data/ (before deploying) and print its answers.
#
#   ops/test.sh                      the questions in ops/test-questions.txt
#   ops/test.sh "when is the deadline?" "how do I deploy a contract?"
#   MODEL=Qwen/Qwen3.6-35B-A3B-FP8 ops/test.sh ...   try another NEAR AI model without editing data/
#   FAKE_DATE=2026-11-19T12:00 ops/test.sh ...       ask as if it were then (UTC; ops/fake_date)
#
# Runs in a throwaway container on the server that gets only NEARAI_API_KEY, never the Telegram
# token, so it can't poll Telegram and compete with the live bot. Each run has its own folder and
# container, so runs can overlap, and both are removed when the run ends, is interrupted, or loses
# its connection to the server.
set -euo pipefail

NAME=hack-bot
BASE=/opt/$NAME
HOST="root@$(hcloud server ip "$NAME")"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="$(sed -n 's/^IMAGE="\([^"]*\)".*/\1/p' "$DIR/deploy.sh")"   # the image production runs
RUN="$(date -u +%Y%m%d-%H%M%S)-$$-$RANDOM"
T=$BASE/tests/$RUN          # this run's folder on the server
C=$NAME-test-$RUN           # and its container
FAKE_DATE="${FAKE_DATE:-}"
[[ -z $FAKE_DATE || $FAKE_DATE =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$ ]] \
  || { echo "FAKE_DATE must look like 2026-11-19T12:00" >&2; exit 2; }

LOCAL="$(mktemp -d)"
# The server cleans up after itself once run.sh starts; this covers a failure or interruption before then.
trap 'rc=$?; rm -rf "$LOCAL"; [ $rc = 0 ] || ssh -o ConnectTimeout=10 "$HOST" "docker rm -f $C; rm -rf $T" >/dev/null 2>&1 || true' EXIT
trap 'exit 1' INT TERM HUP
if [ $# -gt 0 ]; then printf '%s\n' "$@"; else grep -vE '^\s*(#|$)' "$DIR/ops/test-questions.txt"; fi > "$LOCAL/questions.txt"

cat > "$LOCAL/run.sh" <<'RUN'
set -euo pipefail
umask 077
cleanup() {
  [ -z "${WATCHDOG:-}" ] || kill "$WATCHDOG" 2>/dev/null || true
  docker rm -f "$C" >/dev/null 2>&1 || true
  rm -rf "$T"
}
trap cleanup EXIT
trap 'exit 1' INT TERM HUP PIPE
# ops/test.sh sends a line every 15 s. If they stop for a minute, it was stopped or the connection died
# (ssh alone doesn't notice a dead connection for hours): stop the container, which ends this run.
# Its own stdin comes from ssh, and nothing else of the session's, or ssh would wait for it to exit.
( while read -r -t 60 _; do :; done; docker rm -f "$C" ) <&0 >/dev/null 2>&1 &
WATCHDOG=$!

grep '^NEARAI_API_KEY=' "$BASE/data/.env" > "$T/data/.env"
if grep -q TELEGRAM "$T/data/.env"; then echo "refusing: test .env must not contain a Telegram token" >&2; exit 1; fi
# `hermes -z` runs as the cli platform; give it exactly the Telegram toolset so answers match production.
# Its .env has no Telegram token, so report_faucet_down can't DM the maintainer from a test.
sed -i 's/^  telegram: \(\[.*\]\)$/  telegram: \1\n  cli: \1/' "$T/data/config.yaml"
grep -q '^  cli: \[' "$T/data/config.yaml" || { echo "could not give the cli platform the Telegram toolset" >&2; exit 1; }
# ...and Telegram's formatting note, instead of the terminal's.
awk '{print} /^platform_hints:$/{p=1} p && /^    replace:/{print "  cli:"; print; p=0}' "$T/data/config.yaml" > "$T/config"
cat "$T/config" > "$T/data/config.yaml"  # not mv: keeps the file readable inside the container
grep -q '^  cli:$' "$T/data/config.yaml" || { echo "could not give the cli platform Telegram's formatting note" >&2; exit 1; }
if [ -n "$MODEL" ]; then
  sed -i "s|^  default: .*|  default: $MODEL|" "$T/data/config.yaml"
  grep -q "^  default: $MODEL\$" "$T/data/config.yaml" || { echo "could not set the model to $MODEL" >&2; exit 1; }
fi

# Into the venv itself: the hermes launcher replaces PYTHONPATH. The check below fails the run if the image's
# Python moves and the shim with it.
FAKE=()
[ -z "$FAKE_DATE" ] || FAKE=(-e FAKE_DATE="$FAKE_DATE"
  -v "$T/fake_date/sitecustomize.py:/opt/hermes/.venv/lib/python3.14/site-packages/sitecustomize.py:ro")

# From /opt/data, the gateway's working folder: from /opt/hermes, Hermes sees a code repository and adds
# a coding-agent brief that production never gets.
docker run --rm --name "$C" "${FAKE[@]}" -v "$T/data:/opt/data" -v "$T/questions.txt:/questions.txt:ro" "$IMAGE" bash -c '
  cd /opt/data
  if [ -n "${FAKE_DATE:-}" ] && [ "$(/opt/hermes/.venv/bin/python -c "import datetime as d; print(f\"{d.datetime.now(d.timezone.utc):%Y-%m-%dT%H}\")")" != "${FAKE_DATE%:*}" ]; then
    echo "FAKE_DATE did not take effect" >&2; exit 1
  fi
  while IFS= read -r q; do
    echo "=== $q"
    HERMES_HOME=/opt/data /opt/hermes/.venv/bin/hermes -z "$q" 2>/dev/null </dev/null
    echo
  done < /questions.txt' 2>&1 \
  | grep -vE '^\[|s6-rc|cont-init|preinit|reconcile|Hermes Gateway|Messaging platforms|Press Ctrl|^[┌├└│]|Syncing bundled|opted out|\+ hermes-agent|^Done: |WARNING|Shutdown context|^$' || true
RUN

ssh "$HOST" "mkdir -p $T/data"
rsync -a --delete --exclude .env --exclude __pycache__ "$DIR/data/" "$HOST:$T/data/"
rsync -a "$LOCAL/questions.txt" "$LOCAL/run.sh" "$DIR/ops/fake_date" "$HOST:$T/"

# Keep-alive: if the connection drops, fail within a minute instead of waiting forever (it once hung a
# deploy for 3 hours). The lines on stdin are the run's heartbeat (see the watchdog above).
ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=4 "$HOST" \
  "BASE=$BASE T=$T C=$C IMAGE=$IMAGE MODEL='${MODEL:-}' FAKE_DATE=$FAKE_DATE bash $T/run.sh" < <(while sleep 15; do echo; done)

#!/usr/bin/env bash
# Ask the bot questions using the local data/ (before deploying) and print its answers.
#
#   ops/test.sh                      the questions in ops/test-questions.txt
#   ops/test.sh "when is the deadline?" "how do I deploy a contract?"
#
# Runs in a throwaway container on the server that gets only NEARAI_API_KEY, never the Telegram
# token, so it can't poll Telegram and compete with the live bot.
set -euo pipefail

NAME=hack-bot
BASE=/opt/$NAME
HOST="root@$(hcloud server ip "$NAME")"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="$(sed -n 's/^IMAGE="\([^"]*\)".*/\1/p' "$DIR/deploy.sh")"   # the image production runs

QUESTIONS="${TMPDIR:-/tmp}/$NAME-questions.txt"
if [ $# -gt 0 ]; then printf '%s\n' "$@"; else grep -vE '^\s*(#|$)' "$DIR/ops/test-questions.txt"; fi > "$QUESTIONS"

ssh "$HOST" "mkdir -p $BASE/test/data"
rsync -a --delete --exclude .env --exclude __pycache__ "$DIR/data/" "$HOST:$BASE/test/data/"
rsync -a "$QUESTIONS" "$HOST:$BASE/test/questions.txt"

ssh "$HOST" "BASE=$BASE IMAGE=$IMAGE bash -s" <<'RUN'
set -euo pipefail
umask 077
T=$BASE/test
trap 'rm -rf "$T"' EXIT

grep '^NEARAI_API_KEY=' "$BASE/data/.env" > "$T/data/.env"
if grep -q TELEGRAM "$T/data/.env"; then echo "refusing: test .env must not contain a Telegram token" >&2; exit 1; fi
# `hermes -z` runs as the cli platform; give it exactly the Telegram toolset so answers match production.
sed -i 's/^  telegram: \[near_docs\]$/  telegram: [near_docs]\n  cli: [near_docs]/' "$T/data/config.yaml"
grep -q '^  cli: \[near_docs\]$' "$T/data/config.yaml" || { echo "could not give the cli platform the Telegram toolset" >&2; exit 1; }

docker run --rm -v "$T/data:/opt/data" -v "$T/questions.txt:/questions.txt:ro" "$IMAGE" bash -c '
  cd /opt/hermes
  while IFS= read -r q; do
    echo "=== $q"
    HERMES_HOME=/opt/data .venv/bin/hermes -z "$q" 2>/dev/null </dev/null
    echo
  done < /questions.txt' 2>&1 \
  | grep -vE '^\[|s6-rc|cont-init|preinit|reconcile|Hermes Gateway|Messaging platforms|Press Ctrl|^[┌├└│]|Syncing bundled|opted out|\+ hermes-agent|^Done: |WARNING|Shutdown context|^$' || true
RUN

#!/usr/bin/env bash
# Push the bot (data/), the hourly check (ops/) and the rules it was built from (sources/) to the VPS,
# then (re)start the Hermes container. Secrets live only in data/.env on the server; this script
# never touches it.
#
# --reset  Start every conversation fresh. Hermes freezes SOUL.md into a conversation when it
#          starts and Telegram conversations never end, so after a rules update existing chats keep
#          the old facts. This deletes the session database and the sessions/ index it is recovered
#          from while the bot is stopped; Hermes starts with none.
set -euo pipefail

RESET=0
case "${1:-}" in
  "") ;;
  --reset) RESET=1 ;;
  *) echo "usage: $0 [--reset]" >&2; exit 2 ;;
esac

NAME=hack-bot
BASE=/opt/$NAME
HOST="root@$(hcloud server ip "$NAME")"
IMAGE="nousresearch/hermes-agent:v0.22.5@sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d"   # digest: a moved tag can't change what runs
HERMES_UID=10000   # the image's hermes user; the running bot must keep owning its files
DIR="$(cd "$(dirname "$0")" && pwd)"

# Stage, then let the server's rsync move files into place owned by the bot's user: copying
# straight into data/ would hand it to this Mac's uid and lock the running bot out of its own files.
ssh "$HOST" "mkdir -p $BASE/data $BASE/incoming"
rsync -a --delete --exclude .env --exclude __pycache__ "$DIR/data/" "$HOST:$BASE/incoming/data/"
ssh "$HOST" "rsync -a --chown=$HERMES_UID:$HERMES_UID --exclude .env $BASE/incoming/data/ $BASE/data/"
rsync -a --delete --exclude __pycache__ "$DIR/ops/" "$HOST:$BASE/ops/"
rsync -a --delete "$DIR/sources/" "$HOST:$BASE/sources/"
SINCE="$(date -u '+%Y-%m-%d %H:%M:%S')"
ssh "$HOST" "
  set -e
  test -s $BASE/data/.env || { echo 'missing $BASE/data/.env'; exit 1; }
  echo '17 * * * * root /usr/bin/python3 $BASE/ops/check.py >> /var/log/$NAME-check.log 2>&1' > /etc/cron.d/$NAME
  docker pull -q $IMAGE
  docker stop -t 30 $NAME >/dev/null 2>&1 || true
  docker rm $NAME >/dev/null 2>&1 || true
  if [ $RESET = 1 ]; then
    rm -rf $BASE/data/state.db $BASE/data/state.db-wal $BASE/data/state.db-shm $BASE/data/sessions
    echo 'conversations deleted'
  fi
  docker run -d --name $NAME --restart unless-stopped \
    --memory 1g --pids-limit 512 \
    -v $BASE/data:/opt/data \
    $IMAGE gateway run
"

# Don't report success until the new container is actually talking to Telegram.
ssh "$HOST" "BASE=$BASE SINCE='$SINCE' bash -s" <<'WAIT'
for _ in $(seq 1 40); do
  last=$(grep -h 'telegram connected' "$BASE/data/logs/agent.log" 2>/dev/null | tail -1 | cut -c1-19)
  if [ -n "$last" ] && [[ ! "$last" < "$SINCE" ]]; then echo "bot connected to Telegram at $last UTC"; exit 0; fi
  sleep 3
done
echo "bot did not connect to Telegram within 2 minutes; last errors:" >&2
tail -n 5 "$BASE/data/logs/errors.log" >&2
exit 1
WAIT

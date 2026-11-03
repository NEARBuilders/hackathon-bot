#!/usr/bin/env bash
# Push the bot (data/), the hourly check (ops/) and the rules it was built from (sources/) to the VPS,
# then (re)start the Hermes container. Secrets live only in data/.env on the server; this script
# never touches it.
#
# --reset  Start every conversation fresh, as /new does, so it gets the new SOUL.md; the old
#          transcripts are kept for review (ops/fresh_start.py). Use after every SOUL.md change.
# --purge  Delete every conversation: the session database and the sessions/ index it is recovered
#          from. Only for privacy, e.g. someone pasted a seed phrase.
# --no-eval  Skip the regression cases (ops/eval.py --only regression) that otherwise run first and
#          stop the deploy if any answer is wrong. For emergencies, like pulling a bad answer fast.
set -euo pipefail

FRESH=none
EVAL=1
for arg in "$@"; do
  case "$arg" in
    --reset) FRESH=reset ;;
    --purge) FRESH=purge ;;
    --no-eval) EVAL=0 ;;
    *) echo "usage: $0 [--reset | --purge] [--no-eval]" >&2; exit 2 ;;
  esac
done

NAME=hack-bot
BASE=/opt/$NAME
HOST="root@$(hcloud server ip "$NAME")"
IMAGE="nousresearch/hermes-agent:v0.22.5@sha256:9c5561579f3ffdf333401797094ac3a743738d6c25d40f4331c7bf77b694238d"   # digest: a moved tag can't change what runs
HERMES_UID=10000   # the image's hermes user; the running bot must keep owning its files
DIR="$(cd "$(dirname "$0")" && pwd)"

# One deploy at a time, from any machine: a lock on the server, taken before the evals so a second
# deploy stops at once instead of racing this one's sync and restart. Released on exit. A deploy killed
# outright (kill -9, or cut off from the server) leaves it behind; the refusal says how to clear it.
LOCK=$BASE/deploy.lock
rc=0
owner=$(ssh "$HOST" "mkdir -p $BASE && mkdir $LOCK 2>/dev/null || { cat $LOCK/owner 2>/dev/null; exit 3; }
  echo '$(whoami)@$(hostname -s), pid $$, since $(date -u '+%Y-%m-%d %H:%M') UTC' > $LOCK/owner") || rc=$?
if [ $rc = 3 ]; then
  echo "another deploy is running (${owner:-owner unknown}); not deploying." >&2
  echo "If it isn't (it was killed), clear the lock: ssh $HOST rm -r $LOCK" >&2
  exit 1
elif [ $rc != 0 ]; then
  echo "couldn't reach the server to take the deploy lock" >&2; exit 1
fi
trap 'ssh "$HOST" "rm -r $LOCK" || echo "could not release the deploy lock; clear it: ssh $HOST rm -r $LOCK" >&2' EXIT
trap 'exit 1' INT TERM HUP

if [ $EVAL = 1 ]; then
  "$DIR/ops/eval.py" --only regression || { echo "regression cases failed; not deploying (--no-eval to skip)" >&2; exit 1; }
fi

# Stage, then let the server's rsync move files into place owned by the bot's user: copying
# straight into data/ would hand it to this Mac's uid and lock the running bot out of its own files.
ssh "$HOST" "mkdir -p $BASE/data $BASE/incoming"
rsync -a --delete --exclude .env --exclude __pycache__ "$DIR/data/" "$HOST:$BASE/incoming/data/"
ssh "$HOST" "rsync -a --chown=$HERMES_UID:$HERMES_UID --exclude .env $BASE/incoming/data/ $BASE/data/"
# --copy-links: ops/faucet_alert.py links to the faucet plugin; check.py runs it as root, so it gets its
# own copy here, out of reach of the bot's container (which can write data/).
rsync -a --delete --copy-links --exclude __pycache__ "$DIR/ops/" "$HOST:$BASE/ops/"
rsync -a --delete "$DIR/sources/" "$HOST:$BASE/sources/"
SINCE="$(date -u '+%Y-%m-%d %H:%M:%S')"
ssh "$HOST" "
  set -e
  test -s $BASE/data/.env || { echo 'missing $BASE/data/.env'; exit 1; }
  # Without server IDs, data/plugins/discord-server makes the bot leave every Discord server.
  if grep -q '^DISCORD_BOT_TOKEN=.' $BASE/data/.env && ! grep -q '^DISCORD_GUILD_IDS=.' $BASE/data/.env; then
    echo 'DISCORD_BOT_TOKEN is set but DISCORD_GUILD_IDS is not; set it before deploying'; exit 1
  fi
  printf '%s\n' '17 * * * * root /usr/bin/python3 $BASE/ops/check.py >> /var/log/$NAME-check.log 2>&1' \
    '0 8 * * * root /usr/bin/python3 $BASE/ops/review.py >> /var/log/$NAME-review.log 2>&1' > /etc/cron.d/$NAME
  docker pull -q $IMAGE
  # Longer than agent.restart_drain_timeout (60) in config.yaml, so answers in progress can finish.
  docker stop -t 75 $NAME >/dev/null 2>&1 || true
  docker rm $NAME >/dev/null 2>&1 || true
  if [ $FRESH = reset ] && [ -f $BASE/data/state.db ]; then
    docker run --rm -v $BASE/data:/opt/data -e HERMES_HOME=/opt/data -v $BASE/ops/fresh_start.py:/fresh_start.py:ro \
      $IMAGE /opt/hermes/.venv/bin/python /fresh_start.py 2>&1 | grep 'conversations start fresh' \
      || echo 'fresh start FAILED: conversations unchanged; starting the bot anyway'
  elif [ $FRESH = purge ]; then
    rm -rf $BASE/data/state.db $BASE/data/state.db-wal $BASE/data/state.db-shm $BASE/data/sessions
    echo 'conversations deleted'
  fi
  # Command sync off: the welcome plugin publishes the bot's Discord / menu itself.
  docker run -d --name $NAME --restart unless-stopped \
    --memory 1g --pids-limit 512 \
    -e DISCORD_COMMAND_SYNC_POLICY=off \
    -v $BASE/data:/opt/data \
    $IMAGE gateway run
"

# Don't report success until the new container is actually talking to Telegram, and to Discord
# once data/.env has a Discord token.
ssh "$HOST" "BASE=$BASE SINCE='$SINCE' bash -s" <<'WAIT'
platforms=telegram
grep -q '^DISCORD_BOT_TOKEN=.' "$BASE/data/.env" && platforms="telegram discord"
for platform in $platforms; do
  for _ in $(seq 1 40); do
    last=$(grep -h "$platform connected" "$BASE/data/logs/agent.log" 2>/dev/null | tail -1 | cut -c1-19)
    if [ -n "$last" ] && [[ ! "$last" < "$SINCE" ]]; then echo "bot connected to $platform at $last UTC"; continue 2; fi
    sleep 3
  done
  echo "bot did not connect to $platform within 2 minutes; last errors:" >&2
  tail -n 5 "$BASE/data/logs/errors.log" >&2
  exit 1
done
WAIT

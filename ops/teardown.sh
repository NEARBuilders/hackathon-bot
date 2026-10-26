#!/usr/bin/env bash
# End of event: stop the bot and delete everything it stored on the server: conversations, logs,
# Hermes backups (which include copies of .env), the hourly check and its log.
# The server itself is left running; delete it in Hetzner when you no longer need it.
set -euo pipefail

NAME=hack-bot
[ "${1:-}" = "--yes" ] || { echo "Deletes all $NAME data on the server. Run again with --yes to confirm." >&2; exit 2; }

ssh "root@$(hcloud server ip "$NAME")" "
  set -e
  docker rm -f $NAME >/dev/null 2>&1 || true
  rm -f /etc/cron.d/$NAME /var/log/$NAME-check.log
  rm -rf /opt/$NAME
  echo 'removed container, hourly check and /opt/$NAME'
"
echo "To delete the server too: hcloud server delete $NAME && hcloud firewall delete $NAME"

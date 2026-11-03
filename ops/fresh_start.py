"""Start every conversation fresh, keeping the old ones for review.

Hermes freezes SOUL.md into a conversation when it starts, and conversations never end on their own,
so after a rules update existing chats keep the old facts. This does what /new does for each chat,
through Hermes' own SessionStore.reset_session: the old conversation ends with an explicit
session_reset boundary (its transcript stays in state.db) and the next message starts with the
current SOUL.md, with no notice to the user. deploy.sh --reset runs it while the bot is stopped,
inside a throwaway container of the bot's image:

  docker run --rm -v /opt/hack-bot/data:/opt/data -e HERMES_HOME=/opt/data \
    -v /opt/hack-bot/ops/fresh_start.py:/fresh_start.py:ro IMAGE \
    /opt/hermes/.venv/bin/python /fresh_start.py
"""
import sqlite3

from gateway.config import load_gateway_config
from gateway.session import SessionStore

config = load_gateway_config()
db = sqlite3.connect(f"file:{config.sessions_dir.parent / 'state.db'}?mode=ro", uri=True)
keys = [key for (key,) in db.execute("SELECT session_key FROM gateway_routing")]
db.close()

store = SessionStore(config.sessions_dir, config)
fresh = sum(store.reset_session(key) is not None for key in keys)
print(f"{fresh} of {len(keys)} conversations start fresh; their transcripts are kept")

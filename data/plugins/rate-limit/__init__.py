"""A cap on questions per person, on Telegram and Discord. Every question is a model call paid from
the bot's NEAR AI credits, and anyone can message the bot, so one person sending many could use them
up for everyone. Over the cap a message is dropped before Hermes sees it: no model call. The first
one dropped after a question got through gets a short notice and the rest get nothing, so a flood
can't make the bot flood back.
Commands (/new, /help) don't count. Counts live in memory and start over when the bot restarts.
"""
import logging
import math
import time
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

LIMIT = 10
WINDOW = 600  # seconds
NOTICE = "You've asked a lot in a short time. Please try again in {minutes} min."

_asked = defaultdict(deque)  # (platform, user) -> times of their counted questions, oldest first
_warned = {}                 # (platform, user) -> when they were last sent NOTICE


async def limit_questions(event, gateway, **kwargs):
    """pre_gateway_dispatch hook: None lets the message through, "skip" drops it."""
    source = event.source
    if event.get_command() or source is None or not source.user_id:
        return None
    key = (source.platform.value, source.user_id)
    now = time.monotonic()
    asked = _asked[key]
    while asked and now - asked[0] >= WINDOW:
        asked.popleft()
    if len(asked) < LIMIT:
        asked.append(now)
        return None
    # Once per stretch of being over the cap: not yet warned since their last question got through.
    if _warned.get(key, -math.inf) < asked[-1]:
        _warned[key] = now
        minutes = math.ceil((WINDOW - (now - asked[0])) / 60)
        try:
            await gateway._deliver_platform_notice(source, NOTICE.format(minutes=minutes))
        except Exception:
            logger.exception("could not send the rate-limit notice")
    return {"action": "skip", "reason": "rate limit"}


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", limit_questions)

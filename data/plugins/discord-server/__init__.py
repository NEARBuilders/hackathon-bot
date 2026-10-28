"""Keeps the Discord bot in its own servers. Server admins add a Discord bot themselves through its
invite link, and Hermes has no server allowlist, so without this anyone with the link could put the
bot in their server. It leaves every server not in DISCORD_GUILD_IDS (comma-separated, in data/.env):
those it's already in when it connects, and any it's added to later. With DISCORD_GUILD_IDS unset it
leaves them all.
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_tasks = set()


def _handlers(bot, adapter):
    homes = {g.strip() for g in os.environ.get("DISCORD_GUILD_IDS", "").split(",") if g.strip()}

    async def leave_unless_home(guild):
        if str(guild.id) not in homes:
            logger.warning("leaving Discord server %s (%s): it isn't in DISCORD_GUILD_IDS", guild.name, guild.id)
            try:
                await guild.leave()
            except Exception:
                logger.exception("could not leave Discord server %s (%s); the bot is still in it", guild.name, guild.id)

    bot.add_listener(leave_unless_home, "on_guild_join")
    for guild in bot.guilds:
        task = asyncio.get_running_loop().create_task(leave_unless_home(guild))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


def register(ctx):
    ctx.register_platform_handler("discord", _handlers)

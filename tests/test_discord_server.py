"""The Discord bot stays in its own servers: it leaves every other one, at connect and when added later.
No network or discord.py needed.

  python3 -m unittest discover tests
"""
import asyncio
import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

_PLUGIN = Path(__file__).resolve().parent.parent / "data" / "plugins" / "discord-server" / "__init__.py"
_spec = importlib.util.spec_from_file_location("discord_server", _PLUGIN)
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

HOME, TEST = 111, 333


class Guild:
    def __init__(self, id):
        self.id, self.name, self.left = id, f"server {id}", False

    async def leave(self):
        self.left = True


class Bot:
    def __init__(self, guilds):
        self.guilds, self.listeners = guilds, {}

    def add_listener(self, func, name):
        self.listeners[name] = func


def connect(guilds, home):
    """Wire the plugin as Hermes does at connect, let its tasks run, return the bot."""
    bot = Bot(guilds)

    async def run():
        ds._handlers(bot, adapter=None)
        await asyncio.sleep(0)

    with mock.patch.dict(os.environ, {"DISCORD_GUILD_IDS": home} if home else {}, clear=True):
        asyncio.run(run())
    return bot


class StaysInItsServers(unittest.TestCase):
    def test_leaves_other_servers_at_connect(self):
        home, other = Guild(HOME), Guild(222)
        connect([home, other], str(HOME))
        self.assertFalse(home.left)
        self.assertTrue(other.left)

    def test_leaves_a_server_it_is_added_to(self):
        bot = connect([], str(HOME))
        home, other = Guild(HOME), Guild(222)
        asyncio.run(bot.listeners["on_guild_join"](home))
        asyncio.run(bot.listeners["on_guild_join"](other))
        self.assertFalse(home.left)
        self.assertTrue(other.left)

    def test_stays_in_every_listed_server(self):
        home, test, other = Guild(HOME), Guild(TEST), Guild(222)
        connect([home, test, other], f"{HOME}, {TEST}")
        self.assertFalse(home.left)
        self.assertFalse(test.left)
        self.assertTrue(other.left)

    def test_without_a_home_server_it_leaves_them_all(self):
        guild = Guild(HOME)
        connect([guild], None)
        self.assertTrue(guild.left)


if __name__ == "__main__":
    unittest.main()

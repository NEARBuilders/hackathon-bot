"""No one can use up the model credits: past LIMIT questions in WINDOW a person's messages are dropped,
with one notice. No network or Hermes needed.

  python3 -m unittest discover tests
"""
import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_PLUGIN = Path(__file__).resolve().parent.parent / "data" / "plugins" / "rate-limit" / "__init__.py"
_spec = importlib.util.spec_from_file_location("rate_limit", _PLUGIN)
rl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rl)


class Gateway:
    def __init__(self):
        self.notices = []

    async def _deliver_platform_notice(self, source, content):
        self.notices.append((source.user_id, content))


def message(user="alice", platform="discord", text="when is the deadline?"):
    source = SimpleNamespace(platform=SimpleNamespace(value=platform), user_id=user)
    command = text[1:].split()[0] if text.startswith("/") else None
    return SimpleNamespace(source=source, get_command=lambda: command)


class RateLimit(unittest.TestCase):
    def setUp(self):
        rl._asked.clear()
        rl._warned.clear()
        self.gateway, self.now = Gateway(), 1000.0
        patcher = mock.patch.object(rl.time, "monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, event):
        return asyncio.run(rl.limit_questions(event, self.gateway))

    def test_up_to_the_limit_goes_through(self):
        for _ in range(rl.LIMIT):
            self.assertIsNone(self.send(message()))
        self.assertEqual(self.gateway.notices, [])

    def test_over_the_limit_is_dropped_with_one_notice(self):
        for _ in range(rl.LIMIT):
            self.send(message())
        for _ in range(5):
            self.assertEqual(self.send(message())["action"], "skip")
        self.assertEqual(self.gateway.notices, [("alice", rl.NOTICE.format(minutes=10))])

    def test_window_slides(self):
        for _ in range(rl.LIMIT):
            self.send(message())
        self.now += rl.WINDOW
        self.assertIsNone(self.send(message()))

    def test_notice_again_after_a_new_stretch_over_the_limit(self):
        for _ in range(rl.LIMIT + 1):
            self.send(message())
        self.now += rl.WINDOW
        for _ in range(rl.LIMIT + 1):
            self.send(message())
        self.assertEqual(len(self.gateway.notices), 2)

    def test_notice_again_when_over_after_waiting_as_told(self):
        start = self.now
        for _ in range(rl.LIMIT + 1):  # one a second; the last one is dropped with a notice
            self.send(message())
            self.now += 1
        self.send(message())  # still over: no second notice in the same stretch
        self.now = start + rl.WINDOW  # the first question has expired, as the notice said
        self.assertIsNone(self.send(message()))
        self.assertEqual(self.send(message())["action"], "skip")  # over again: told again
        self.assertEqual(len(self.gateway.notices), 2)

    def test_people_and_platforms_count_separately(self):
        for _ in range(rl.LIMIT):
            self.send(message())
        self.assertIsNone(self.send(message(user="bob")))
        self.assertIsNone(self.send(message(platform="telegram")))

    def test_commands_dont_count(self):
        for _ in range(rl.LIMIT):
            self.send(message())
        self.assertIsNone(self.send(message(text="/new")))


if __name__ == "__main__":
    unittest.main()

"""ops/check.py's hourly decisions: alert once per new problem, once per faucet level crossed, flag the bot
while the rules differ, and a failed send doesn't cost the other alerts. No network, Docker or Telegram.

  python3 -m unittest discover tests
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_OPS = Path(__file__).resolve().parent.parent / "ops"
_spec = importlib.util.spec_from_file_location("check", _OPS / "check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


class Check(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        self.sent, self.refuse = [], False
        self.found, self.changed, self.faucet, self.crash = [], set(), None, None

        def send(text, dry_run):
            if self.refuse:
                raise OSError(f"not sent (Telegram refused it):\n{text}")
            self.sent.append(text)

        for name, value in (("STATE", home / "state" / "last-alert"), ("FAUCET_LEVEL", home / "state" / "faucet-level"),
                            ("RULES_CHANGED", home / "rules-changed"), ("send", send),
                            ("problems", self.problems),
                            ("faucet_alert", lambda: self.faucet)):
            patcher = mock.patch.object(check, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def problems(self):
        if self.crash:
            raise self.crash
        return list(self.found), self.changed

    def run_check(self):
        with mock.patch.object(check.sys, "argv", ["check.py"]):
            check.main()

    def test_same_alert_once_then_again_after_recovery(self):
        self.found = ["The hack-bot container is not running."]
        self.run_check()
        self.run_check()
        self.assertEqual(len(self.sent), 1)
        self.found = []
        self.run_check()
        self.found = ["The hack-bot container is not running."]
        self.run_check()
        self.assertEqual(len(self.sent), 2)

    def test_a_different_alert_is_sent(self):
        self.found = ["The hack-bot container is not running."]
        self.run_check()
        self.found = ["NEAR AI call failed with HTTP 401: the key may be invalid or out of credits."]
        self.run_check()
        self.assertEqual(len(self.sent), 2)

    def test_faucet_once_per_level_rearmed_when_funded(self):
        for level in (20, 20, 10, 10, None, 20):
            self.faucet = (level, f"faucet under {level}")
            self.run_check()
        self.assertEqual(self.sent, ["faucet under 20", "faucet under 10", "faucet under 20"])

    def test_rules_flag_follows_the_live_rules(self):
        self.changed = {"HACKATHON.md"}
        self.run_check()
        self.assertTrue(check.RULES_CHANGED.exists())
        self.changed = None  # the rules couldn't be fetched: leave the flag as it is
        self.run_check()
        self.assertTrue(check.RULES_CHANGED.exists())
        self.changed = {"homepage.txt"}  # only the bot's copy of HACKATHON.md matters
        self.run_check()
        self.assertFalse(check.RULES_CHANGED.exists())

    def test_a_crash_alerts_once_and_keeps_the_rules_flag(self):
        self.changed = {"HACKATHON.md"}
        self.run_check()
        self.crash = AttributeError("'NoneType' object has no attribute 'group'")
        with mock.patch("traceback.print_exc"):
            self.run_check()
            self.run_check()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("hourly check itself failed (AttributeError", self.sent[0])
        self.assertTrue(check.RULES_CHANGED.exists())

    def test_failed_send_keeps_the_rest_and_retries(self):
        self.found, self.changed, self.faucet = ["The hack-bot container is not running."], {"HACKATHON.md"}, (10, "faucet under 10")
        self.refuse = True
        with self.assertRaises(SystemExit) as exited:
            self.run_check()
        self.assertIn("not running", str(exited.exception.code))
        self.assertTrue(check.RULES_CHANGED.exists())
        self.refuse = False  # next hour: both alerts go out, since neither was recorded as sent
        self.run_check()
        self.assertEqual(len(self.sent), 2)


if __name__ == "__main__":
    unittest.main()

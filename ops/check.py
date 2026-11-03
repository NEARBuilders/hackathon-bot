"""Hourly check on the server: is the bot running and connected to Telegram and Discord, can it
still reach its model, and do the live rules still match its copy? Also: is near-faucet.io's account
running dry (a separate message, ready to forward to whoever runs it)?

Alerts go to TELEGRAM_HOME_CHANNEL (in data/.env: the maintainer's private chat) through the bot's
own token. The same alert is not sent twice in a row; once everything matches again, the next
problem alerts afresh. Until HACKATHON.md matches again, data/rules-changed tells the bot to read the
live rules before answering. A maintainer updates data/SOUL.md and sources/, then runs
`deploy.sh --reset` so every conversation picks up the new rules.

  python3 check.py            check and alert
  python3 check.py --dry-run  print the alert instead of sending it
"""
import difflib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
# The bot's faucet-alert plugin, so both read the same account the same way. Imported from ops/, never
# data/: this runs as root, and data/ is the bot's container's to write. ops/faucet_alert.py links to the
# plugin in the repo; deploy.sh copies it as a file into the server's ops/, out of the container's reach.
_spec = importlib.util.spec_from_file_location("faucet_alert", Path(__file__).resolve().parent / "faucet_alert.py")
faucet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(faucet)

CONTAINER = BASE.name
STATE = BASE / "state" / "last-alert"
# While the live rules differ from the bot's copy, the near-docs plugin tells the bot to read them
# before answering. In data/, so the container sees it (/opt/data/rules-changed).
RULES_CHANGED = BASE / "data" / "rules-changed"
MAX_DIFF_LINES = 40
PLATFORMS = ("telegram", "discord")
# A reconnect usually takes seconds; only one that's still going after this is worth an alert.
RECONNECT_GRACE = timedelta(minutes=10)
# The faucet alert is its own message, written to be forwarded to the faucet's maintainers, sent once
# each time what it can pay out drops below one of these (testnet NEAR): 50 is about 25 claims, time
# to get a top-up; under 2 not one claim is left.
FAUCET_LEVELS = (2, 10, 20, 50)
FAUCET_LEVEL = BASE / "state" / "faucet-level"


def env(path):
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.lstrip().startswith("#"):
            values[key.strip()] = value.strip().strip("\"'")
    return values


def running():
    out = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                         capture_output=True, text=True)
    return out.stdout.strip() == "true"


def platform_problems():
    """Hermes parks a platform that fails to connect (Discord refusing the bot's intents, a revoked
    token) and keeps serving the rest, so the container stays up and running() alone misses it."""
    try:
        gateway = json.loads((BASE / "data" / "gateway_state.json").read_text())
        platforms, pid = gateway["platforms"], gateway.get("pid")
    except (OSError, ValueError, KeyError) as e:
        return [f"Couldn't read the bot's gateway_state.json ({type(e).__name__})."]
    now = datetime.now(timezone.utc)
    found = []
    for name in PLATFORMS:
        state = platforms.get(name)
        # Entries written by an earlier run (a platform since removed from .env) aren't live.
        if not state or state.get("state") == "connected" or state.get("writer_pid") != pid:
            continue
        if state.get("state") in ("connecting", "retrying"):
            since = state.get("retrying_since") or state.get("updated_at")
            try:
                if since and now - datetime.fromisoformat(since) < RECONNECT_GRACE:
                    continue
            except ValueError:
                pass
        reason = f": {state['error_message']}" if state.get("error_message") else ""
        found.append(f"The bot isn't connected to {name} ({state.get('state')}){reason}")
    return found


def model_problem():
    """One tiny call with the bot's own key and model, so a dead key, exhausted credits, a silently
    rerouted model ID or a reply from outside a TEE alerts here before users notice."""
    config = (BASE / "data" / "config.yaml").read_text()
    model = re.search(r"^  default: (\S+)", config, re.M).group(1)
    api = re.search(r"^  base_url: (\S+)", config, re.M).group(1).rstrip("/")
    headers = {"Authorization": "Bearer " + env(BASE / "data" / ".env").get("NEARAI_API_KEY", ""),
               "Content-Type": "application/json"}
    body = json.dumps({"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Reply with OK"}]})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{api}/chat/completions", body.encode(), headers), timeout=60) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        return f"NEAR AI call failed with HTTP {e.code}: the key may be invalid or out of credits."
    except (OSError, ValueError) as e:
        return f"NEAR AI call failed: {type(e).__name__}."
    if reply.get("model") != model:
        return f"NEAR AI answered with {reply.get('model')} instead of {model}: the model ID may be retired and rerouted."
    query = urllib.parse.urlencode({"model": model, "signing_algo": "ecdsa"})
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{api}/signature/{reply['id']}?{query}", headers=headers), timeout=60) as r:
            kind = json.load(r).get("signature_kind")
    except (OSError, ValueError, KeyError) as e:
        return f"Couldn't fetch the reply's signature from NEAR AI ({type(e).__name__}); the bot itself may be fine."
    if kind != "provider_tee":
        return f"Replies from {model} are no longer signed inside a TEE (signature_kind: {kind})."
    return None


def faucet_alert():
    """(level, forwardable message) for the faucet: level is the lowest of FAUCET_LEVELS the balance is
    under, None when above them all. None if testnet RPC can't be reached."""
    try:
        balance = faucet.spendable()
    except (OSError, ValueError, KeyError) as e:
        print(f"could not check the faucet balance: {type(e).__name__}", file=sys.stderr)
        return None
    level = next((level for level in FAUCET_LEVELS if balance < level), None)
    lead = ("near-faucet.io is out of funds: claims are failing." if balance < faucet.CLAIM
            else "near-faucet.io is running low.")
    return level, faucet.forward_text(balance, lead)


def problems():
    """(alerts, names of sources that differ from sources/, or None if the rules couldn't be fetched)."""
    found = []
    if not running():
        found.append(f"The {CONTAINER} container is not running.")
    else:
        found += platform_problems()
    if problem := model_problem():
        found.append(problem)
    try:
        live = sources.current()
    except OSError as e:
        print(f"could not fetch the rules: {e}", file=sys.stderr)
        return found, None
    changed = set()
    for name, text in live.items():
        baseline = (BASE / "sources" / name).read_text()
        if text != baseline:
            changed.add(name)
            diff = list(difflib.unified_diff(baseline.splitlines(), text.splitlines(),
                                             f"bot copy/{name}", f"live/{name}", n=1, lineterm=""))
            shown = "\n".join(diff[:MAX_DIFF_LINES])
            more = f"\n… {len(diff) - MAX_DIFF_LINES} more lines" if len(diff) > MAX_DIFF_LINES else ""
            found.append(f"{name} changed. Update SOUL.md and sources/, then deploy with --reset.\n{shown}{more}")
    return found, changed


def send(text, dry_run):
    if dry_run:
        print(text)
        return
    values = env(BASE / "data" / ".env")
    token, chat = values.get("TELEGRAM_BOT_TOKEN"), values.get("TELEGRAM_HOME_CHANNEL")
    if not token or not chat:
        sys.exit("TELEGRAM_BOT_TOKEN or TELEGRAM_HOME_CHANNEL missing from data/.env; alert not sent:\n" + text)
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", body, timeout=30) as r:
        if not json.load(r).get("ok"):
            sys.exit("Telegram refused the alert")


def send_faucet(dry_run):
    """The forwardable faucet message, once per level crossed; re-armed once it's above them all."""
    alert = faucet_alert()
    if alert is None:
        return
    level, text = alert
    try:
        sent = int(FAUCET_LEVEL.read_text())
    except (OSError, ValueError):
        sent = None
    if dry_run:
        print(f"faucet level {level} (alerted at {sent}):\n{text}\n")
    elif level is None:
        FAUCET_LEVEL.unlink(missing_ok=True)
    elif sent is None or level < sent:
        send(text, dry_run)
        FAUCET_LEVEL.parent.mkdir(parents=True, exist_ok=True)
        FAUCET_LEVEL.write_text(str(level))


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    found, changed = problems()
    # Only HACKATHON.md: it's the one rules page the bot can read.
    if changed is not None and not dry_run:
        if "HACKATHON.md" in changed:
            # data/ is the bot's to write: never follow a link it put there, as root.
            try:
                os.close(os.open(RULES_CHANGED, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o644))
            except OSError as e:
                print(f"could not set {RULES_CHANGED}: {e.strerror}", file=sys.stderr)
        else:
            RULES_CHANGED.unlink(missing_ok=True)
    if not found:
        STATE.unlink(missing_ok=True)
    else:
        text = f"⚠️ {CONTAINER}\n\n" + "\n\n".join(found)
        digest = hashlib.sha256(text.encode()).hexdigest()
        if dry_run or not STATE.exists() or STATE.read_text() != digest:
            send(text, dry_run)
            if not dry_run:
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(digest)
    # Last: send() exits on a Telegram error, which mustn't cost the health alert or the rules flag.
    send_faucet(dry_run)


if __name__ == "__main__":
    main()

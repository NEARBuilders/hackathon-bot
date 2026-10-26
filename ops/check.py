"""Hourly check on the server: is the bot running, and do the live rules still match its copy?

Alerts go to TELEGRAM_HOME_CHANNEL (in data/.env: the maintainer's private chat) through the bot's
own token. The same alert is not sent twice in a row; once everything matches again, the next
problem alerts afresh. A maintainer updates data/SOUL.md and sources/, then runs
`deploy.sh --reset` so every conversation picks up the new rules.

  python3 check.py            check and alert
  python3 check.py --dry-run  print the alert instead of sending it
"""
import difflib
import hashlib
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
CONTAINER = BASE.name
STATE = BASE / "state" / "last-alert"
MAX_DIFF_LINES = 40


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


def problems():
    found = []
    if not running():
        found.append(f"The {CONTAINER} container is not running.")
    try:
        live = sources.current()
    except OSError as e:
        print(f"could not fetch the rules: {e}", file=sys.stderr)
        return found
    for name, text in live.items():
        baseline = (BASE / "sources" / name).read_text()
        if text != baseline:
            diff = list(difflib.unified_diff(baseline.splitlines(), text.splitlines(),
                                             f"bot copy/{name}", f"live/{name}", n=1, lineterm=""))
            shown = "\n".join(diff[:MAX_DIFF_LINES])
            more = f"\n… {len(diff) - MAX_DIFF_LINES} more lines" if len(diff) > MAX_DIFF_LINES else ""
            found.append(f"{name} changed. Update SOUL.md and sources/, then deploy with --reset.\n{shown}{more}")
    return found


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


def main():
    dry_run = "--dry-run" in sys.argv[1:]
    found = problems()
    if not found:
        STATE.unlink(missing_ok=True)
        return
    text = f"⚠️ {CONTAINER}\n\n" + "\n\n".join(found)
    digest = hashlib.sha256(text.encode()).hexdigest()
    if not dry_run and STATE.exists() and STATE.read_text() == digest:
        return
    send(text, dry_run)
    if not dry_run:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(digest)


if __name__ == "__main__":
    main()

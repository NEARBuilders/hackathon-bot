"""Fetch the hackathon's public rules in a stable, comparable form.

Used by check.py (hourly, on the server). Run it directly to refresh sources/ after updating SOUL.md:

  python3 ops/sources.py
"""
import html
import re
import urllib.request
from pathlib import Path

RULES_URL = "https://nearhackathon.com/HACKATHON.md"
HOME_URL = "https://nearhackathon.com/"

# The homepage's live submission counter ("SUBMITTED PROJECTS" and the value after it) changes
# during the event without the rules changing.
COUNTER_LABEL = "SUBMITTED PROJECTS"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "near-hackathon-bot-freshness/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def homepage_text(page):
    """Visible text of the homepage, one item per line, without scripts or build hashes."""
    page = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    lines = [l for l in (" ".join(line.split()) for line in text.splitlines()) if l]
    kept, skip = [], False
    for line in lines:
        if skip:
            skip = False
        elif line == COUNTER_LABEL:
            skip = True
        else:
            kept.append(line)
    return "\n".join(kept) + "\n"


def current():
    """{filename: content} for everything the bot's knowledge is built from."""
    return {"HACKATHON.md": fetch(RULES_URL), "homepage.txt": homepage_text(fetch(HOME_URL))}


if __name__ == "__main__":
    for name, text in current().items():
        (Path(__file__).resolve().parent.parent / "sources" / name).write_text(text)

# NearHackathonBot

A community-run Telegram bot ([@NearHackathonBot](https://t.me/NearHackathonBot)) that answers questions
about [NEAR Hackathon](https://nearhackathon.com) (1–14 Nov 2026): rules, dates, tracks, prizes and
submitting, plus how to build on NEAR, answered from the official docs. It isn't run by the
organizers and says so. See [SCOPE.md](SCOPE.md) for the product scope.

## How it works

- **[Hermes Agent](https://github.com/NousResearch/hermes-agent)** in Docker on a small VPS, image pinned
  by digest to `nousresearch/hermes-agent:v0.22.5` (see `IMAGE` in `deploy.sh`), with memory and process limits.
- **Model:** `z-ai/glm-5.3-flash` on [NEAR AI Cloud](https://cloud.near.ai), which runs inside a TEE
  (replies are signed `provider_tee`). Every model call goes there; there is no fallback provider.
- **Knowledge:** [`data/SOUL.md`](data/SOUL.md) holds the bot's instructions and a copy of the public
  rules. [`sources/`](sources) is the live text that copy was built from.
- **Tools:** one plugin, [`data/plugins/near-docs`](data/plugins/near-docs), with two read-only tools:
  `search_near_docs` and `read_near_docs`. They fetch only Markdown pages and `llms.txt` from
  docs.near.org, docs.near.ai and docs.near-intents.org, plus `nearhackathon.com/HACKATHON.md`.
  HTTPS only, no query strings, no redirects off those hosts. All built-in Hermes tools are off.
- **Link filter:** the same plugin rewrites every reply so only links to an allowlist (the hackathon,
  NEAR's sites, the official community links and partner sites) survive; any other link, with or
  without `https://`, becomes "(link removed)". Names Telegram would turn into links but are usually
  file names or accounts (`HACKATHON.md`, `src/lib.rs`, `user.tg`) are shown as code instead: readable,
  not clickable. In tests the bot wrote planted scam links into its own warnings, and Telegram makes
  those clickable.
- **In groups** it answers only when mentioned or replied to (Telegram privacy mode on, not an admin).
  Anyone can add it to a group (BotFather's Allow Groups is on), so teams can use it in their own chats.
  Each person has their own conversation; memory across conversations is off.
- **Commands:** users can run `/new`, `/start`, `/help` and `/whoami`. Everything else is refused.
  `/start`, `/help` and the `/` menu get plain text from [`data/plugins/welcome`](data/plugins/welcome).

## Layout

```
data/                 the bot: synced to the server's Hermes home (/opt/data in the container)
  config.yaml         model, lockdown, Telegram settings
  SOUL.md             instructions and hackathon knowledge
  plugins/near-docs/  the read-only docs tools and the link filter
  plugins/welcome/    the /start greeting, /help text and / menu descriptions
sources/              live rules and homepage text that SOUL.md is built from (baseline for the check)
deploy.sh             push data/, ops/ and sources/ to the server and restart the bot
ops/check.py          hourly: is the bot running, can it reach its model, do the rules still match sources/?
ops/sources.py        fetches the rules in a stable, comparable form
ops/test.sh           ask the bot questions using the local data/, safely (see Testing)
ops/test-questions.txt  the default test questions
ops/teardown.sh       end of event: delete everything the bot stored on the server
tests/                checks for the security boundary: what the docs tools may fetch, which links survive
SCOPE.md              product scope
```

## Server and secrets

A Hetzner VPS named `hack-bot` with Docker, reachable as `root` over SSH (key only). Its firewall
allows SSH and nothing else; the bot only makes outbound connections. The scripts find the server
through `hcloud server ip hack-bot`, so you need the `hcloud` CLI with access to the project.

Secrets live only on the server, in `/opt/hack-bot/data/.env` (readable by the bot's user only). They
are never in this repo and the scripts never copy them:

| Key | What |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `TELEGRAM_ALLOW_ALL_USERS` | `true`: anyone can talk to it |
| `NEARAI_API_KEY` | NEAR AI Cloud key for this bot only |
| `TELEGRAM_HOME_CHANNEL` | the maintainer's Telegram user ID: alerts and Hermes notices go there |

Hermes adds `API_SERVER_KEY` itself on first start. To edit the file, SSH in and keep it
newline-terminated.

## Deploying

```bash
./deploy.sh            # push changes and restart; waits until the bot is connected to Telegram
./deploy.sh --reset    # same, and start every conversation fresh
```

Hermes freezes `SOUL.md` into a conversation when it starts, and Telegram conversations never end,
so after changing `SOUL.md` use `--reset`. It deletes the existing conversations. Messages sent during a
restart are kept and answered afterwards.

## Testing

```bash
ops/test.sh                                   # the questions in ops/test-questions.txt
ops/test.sh "when is the deadline?" "..."     # your own
```

Before deploying a change to the plugin, also run `python3 -m unittest discover tests`: it checks which
URLs the docs tools may fetch and which links survive in replies, with no network needed.

`ops/test.sh` uses your local `data/`, so you can try changes before deploying. It runs in a throwaway container
on the server that gets only `NEARAI_API_KEY`. Never start a test container with the Telegram token:
it would poll Telegram and fight the live bot for messages.

## When the rules change

`ops/check.py` runs hourly and messages the home channel when the bot is down, when a tiny test call to
its model fails or comes back from a different model or outside a TEE (a dead key, exhausted credits, a
retired model ID), or when the live rules differ from `sources/` (with a diff). For a rule change:

1. Update `data/SOUL.md` to match.
2. Refresh the baseline: `python3 ops/sources.py`
3. `ops/test.sh`, then `./deploy.sh --reset`.

The bot also reads the live `HACKATHON.md` itself when someone claims a rule changed, and never takes a
change from a chat message.

## When something goes wrong

- **Stop the bot now:** `ssh root@$(hcloud server ip hack-bot) docker stop hack-bot`. Or revoke its token
  in @BotFather (`/revoke`), which also locks out anyone who has a copy.
- **A token or key leaked:** revoke it (BotFather, or the NEAR AI Cloud dashboard), put the new one in
  `/opt/hack-bot/data/.env`, then `./deploy.sh`.
- **Someone pasted a seed phrase or other secret:** `./deploy.sh --reset`, then delete the matching lines from
  `/opt/hack-bot/data/logs/`.
- **The bot is in a group it shouldn't be:** find the chat ID with
  `ssh root@$(hcloud server ip hack-bot) "grep -o 'chat=-[0-9]*' /opt/hack-bot/data/logs/agent.log | sort | uniq -c"`,
  then make it leave:
  `curl -s "https://api.telegram.org/bot<token>/leaveChat?chat_id=<chat id>"`. To stop all new
  groups, turn off Allow Groups in @BotFather.
- **Alert: NEAR AI call failed:** top up the account's credits, or replace the key in `.env` and `./deploy.sh`.
- **Alert: answered with a different model:** the model ID was retired. Pick a current model that's
  `owned_by: nearai` from `https://cloud-api.near.ai/v1/models`, set it as `model.default` in
  `data/config.yaml`, then `ops/test.sh` and `./deploy.sh --reset`.
- **The bot posts something wrong:** fix `data/SOUL.md`, `ops/test.sh`, then `./deploy.sh --reset`.

## After the event

```bash
ops/teardown.sh --yes   # deletes the container, conversations, logs, backups and the hourly check
```

Then delete the server and its firewall in Hetzner, and revoke the NEAR AI key.

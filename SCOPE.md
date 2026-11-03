# [@NearHackathonBot](https://t.me/NearHackathonBot)

Community-run AI agent that answers questions during [NEAR Hackathon](https://nearhackathon.com) (Nov 1–14, 2026)

- Rules
- Tracks
- Prizes
- Docs
- Skills

**Why?** Participants need trustworthy answers without waiting for organizers.

> Available 24/7 on Telegram and in the NEAR Discord

## Design

### AI Model

`z-ai/glm-5.3-flash` on [NEAR AI Cloud](https://cloud.near.ai), inside a Trusted Execution Environment (TEE)

> Browse options: [near.ai/models](https://near.ai/models)

### Harness

[Hermes](https://github.com/NousResearch/hermes-agent): pinned version with all built-in tools disabled

> In groups and Discord channels, the bot only responds when mentioned or replied to.

### Memory

Per-user conversations: nothing shared between users. A rules update starts every conversation fresh.

### Tools

Custom Hermes plugins:

- `search_near_docs`: finds the right page in the official NEAR docs (read-only)
- `read_near_docs`: reads that page, or the live `HACKATHON.md` (read-only)
- `report_faucet_down`: tells the maintainer when users say near-faucet.io isn't working (no input, at most one message per 6 hours)

> Only uses approved NEAR sources (no web search, terminal or files)

### Safety

- Admin commands disabled for users
- Scam-link filter on every reply
- Rule changes only from live website
- Never asks for keys or seed phrases
- At most 10 questions per person per 10 minutes, so no one can use up the AI credits
- Stays only in approved Discord servers

### Monitoring

- Hourly: is the bot up and connected, can it reach its model inside the TEE, do the rules still match
- Daily: a TEE model reviews the last day's answers and reports mistakes to the maintainer

## Timeline

- Prototype live, Oct 26
- Scope finalized, Oct 27
- v1 bot delivered, Oct 29
- Hackathon begins, Nov 1
- Submissions close, Nov 14
- Judging, Nov 16–18; results by Nov 18
- Bot and its data removed after the event

## Context

### Main Sources

- https://nearhackathon.com (homepage text)
- https://nearhackathon.com/HACKATHON.md
- [SOUL.md](https://github.com/nearbuilders/hackathon-bot/blob/main/data/SOUL.md) (system prompt)

### Docs

The bot reads these and links to the right page(s):

- https://docs.near.org/llms.txt
- https://docs.near.ai/llms.txt
- https://docs.near-intents.org/llms.txt

### Skills

The bot links to these for builders:

- https://github.com/near/agent-skills
- https://github.com/NEAR-Intents-Agent-API/skills

## Demo

Join [this group](https://t.me/+tJexWuOqOoY4M2Yx) to help with testing. Please share any feedback!

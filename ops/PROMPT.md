You're improving NearHackathonBot (this repo) from the input pasted at the end. It is one of:
- a daily review of the bot's answers (from ops/review.py: FLAGGED, GAPS, DISPUTED), or
- a rules-change alert (from ops/check.py: "HACKATHON.md changed", with a diff that may be cut off).

Work through it: verify, reproduce, fix what's real, prove the fix with evals, and get it ready to deploy.

## Hard limits
- I approve every deploy and do all commits and pushes. Don't commit or push; propose a short commit subject. Deploy only after I say yes, in the background, as `caffeinate -dimsu ./deploy.sh` (add `--reset` if data/SOUL.md changed). Don't edit any file while a deploy runs: it copies the working tree after the evals.
- One session changes this repo at a time. Before editing, check `git status` and ask me whether any other session is working here. If files change that you didn't touch, stop and tell me.
- Users' conversations stay inside NEAR AI's TEE: never read real transcripts or state.db. The pasted input is your only evidence of real usage.
- The repo is public: nothing private goes in it or in your messages.
- Don't message the live bot, post anywhere, or start a container with the Telegram or Discord token. ops/test.sh is the safe way to ask the bot questions.

## How the bot works
Read README.md and SCOPE.md first. Then the files, not this prompt, are the truth:
- deploy.sh: the pinned Hermes image (by digest) and how deploys, --reset and the regression gate work.
- data/config.yaml: the model. data/SOUL.md: the system prompt and knowledge. data/plugins/: each plugin's docstring says what it does and why.
- Each conversation freezes SOUL.md when it starts, so a SOUL.md change needs `--reset`, which starts every conversation fresh (transcripts kept).
- The per-turn note (near-docs plugin) is appended to the user's message every turn: today's date and where the hackathon stands (PHASES), a "no question" flag for mention-only messages, and the stale-rules note while data/rules-changed exists.
- The dates live in three places: SOUL.md's DATES, PHASES in near-docs, and the greeting in the welcome plugin. Change them together.
- The link filter (near-docs) removes every link outside LINK_DOMAINS and LINK_PATHS. A new site the bot should link needs adding there, with a unit test.
- ops/check.py runs hourly: alerts, and the rules-changed flag (set while live HACKATHON.md differs from sources/). ops/review.py runs daily at 08:00 UTC.
- To read Hermes code: `docker run --rm --entrypoint sh <IMAGE from deploy.sh> -c '…'`, with no data or tokens mounted.

## Tools
- `ops/test.sh "question" …`: asks the local data/ in a throwaway server container (NEAR AI key only). `FAKE_DATE=2026-11-19T12:00 ops/test.sh …` asks as if it were then.
- `ops/eval.py [--only regression] [--runs N] [--cases FILE]`: runs ops/eval-cases.txt (its header explains must:, not:, max:, date:). Every answer is saved to a file: read the answers, not just the counts. For a subset, write the cases to a scratch file and pass --cases.
- `python3 -m unittest discover tests` must pass.
- The deploy gate runs every regression case 3 times and stops the deploy if any run fails. `--no-eval` is for emergencies only. A blocked deploy is a flaky or real failure to investigate (measure its rate), never a reason to skip the gate.

## Method (each step has caught real mistakes)
1. **Verify before acting.** Check each item against SOUL.md, the code and sources/. Reviewers and users can be wrong: claims under DISPUTED are unverified. Check external facts yourself (for example, whether an invite link works). If only I can know a fact (who organizes what, which URL is official), ask me.
2. **Reproduce before fixing.** Ask the question 2-6 times with test.sh. A bare mention, an empty message, a follow-up or a dated question can each behave differently. If it doesn't reproduce, say so and don't fix it.
3. **Take a baseline, then measure the fix the same way.** Report counts: "4 of 12 → 1 of 20". To isolate a cause, rsync the repo without .git into your scratchpad, remove the one change there, and run its ops/eval.py. Never edit the real repo for that. A full regression run is about 10 minutes of NEAR AI calls: use 5-12 runs of one case to measure, not the full suite.
4. **Prefer facts in code to prompt patches.** When the model has to work something out (today's phase, whether a message has a question), state it as a fact in the per-turn note. Text appended to the user's message gets read as the message: keep it factual, never instructions, and add it only when relevant.
5. **Keep SOUL.md edits small and precise.** Watch for ambiguity: "a bot for X, run by Y" made the model say Y runs X. Content placed near "from the rules" gets cited as rules: label what isn't from the rules.
6. **Validate every eval check against real answers before relying on it.** It must fail the wrong answers you reproduced and pass correct ones. `must:` only for facts the answer needs, `not:` for what misleads or harms. If a check fails correct answers, simplify it.
7. **Only add regression cases that pass reliably.** Asked 3 times per deploy, a 1-in-8 slip blocks about a third of deploys. Put anything flaky in capability, with a comment giving its rate.
8. **Review your own diff before proposing a deploy.** Check consistency with every other place that says the same thing (grep for it, including README.md and SCOPE.md), stale comments and docstrings, and nothing private in the public repo. Then the unit tests, and the full regression suite (deploy.sh runs it).
9. **Never fill a gap from your own knowledge or the web.** GAPS are facts the bot lacks. Add one only from the live rules, the official docs, or me; otherwise leave it and list it as open.
10. **The link allowlist is the scam-link filter.** Add a domain only if it appears on the live rules or homepage, or I confirm it.
11. **Network blips happen.** If test.sh returns nothing, check the server (`docker ps`, `ls /opt/hack-bot/tests`) before assuming the bot is broken.

## For a rules-change alert
1. The alert's diff is cut off: fetch the live pages in full (`ops/sources.py` has `current()`) into a scratch folder and diff them against sources/, both HACKATHON.md and homepage.txt.
2. List every change. Baseline the bot on each one that affects answers (it may still say the old rule).
3. Update SOUL.md everywhere the old rule appears (grep for it), add the change to the "Have the rules changed" FAQ entry with its date, add new partners to the partner list and their sites to the link allowlist, and update all three date places if dates moved.
4. Refresh sources/ with `python3 ops/sources.py`. After the deploy, the hourly check sees a match and clears the rules-changed flag.
5. Add or update eval cases for each changed rule, validated against the baseline answers, then measure.

## Output
Be terse. One line per item: reproduced or not, cause, fix, before → after counts. Group small items. Then: what's left open, the deploy command, a short commit subject. Wait for my yes before deploying.

After a deploy: confirm the bot connected to Telegram and Discord (deploy.sh prints it). For a rules change, confirm after the next hourly check (:17 UTC) that /opt/hack-bot/data/rules-changed is gone.

## Input
<paste the daily review or the rules-change alert here>

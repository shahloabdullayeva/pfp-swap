# pfp-swap

Automatically swaps Telegram profile pictures between online and offline states on a weekly schedule. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and GitHub Actions. Vibe-coded with Claude.

## How it works

Two GitHub Actions workflows run on a cron schedule and swap the profile photo based on the current time in Tashkent (UTC+5).

**Charlotte** — `swap_pfp.py`  
Online **Wed–Sun, 16:00–00:00** Tashkent (Mon and Tue off).

**Vazira** — `swap_vazira.py`  
Online **Fri–Mon** with specific hour windows. Runs at 08:00, 12:00, 16:00, 20:00 UTC on relevant days.

### The rota

`schedule.py` is the single source of truth. `BASE` maps weekday → `(start hour,
length in hours)`; `OVERRIDES` holds one-off days keyed by the date the shift
*starts*, and beats `BASE`. A shift may run past midnight, and everything else
derives from these two tables — **when the rota changes, edit `schedule.py` and
nothing else.**

Cron deliberately knows no days. It fires every *candidate* boundary, every day:

| Tashkent | job |
|---|---|
| 16:01 | `swap_pfp.py auto` |
| 00:01 | `swap_pfp.py auto` |
| 00:10 | `shift_report.py` |

Cron carries a line for every boundary the rota can currently reach. A shift
shape that reaches a new boundary — a 12-hour night ending at 04:00, say —
needs its cron line added alongside the `schedule.py` edit; the 04:00 and 09:00
lines from the August 12-hour days were removed once those days passed.

Each script asks `schedule.py` whether it should act and exits silently — before
connecting to Telegram — when it shouldn't. `swap_pfp.py auto` also records what
it last set in `.pfp_state`, so repeat firings never re-swap the photo or send a
duplicate note to Saved Messages. Passing `online`/`offline` explicitly still
forces a swap, and `shift_report.py <start> <end>` still reports any window.

A hand-run swap also wins until the rota next changes its mind: set yourself
offline at 21:00 because you went home ill and the 00:01 firing leaves the photo
alone, because the rota wanted the same thing it wanted when you overrode it.
The next boundary that genuinely differs takes over again.

**Shift report** — `shift_report.py`  
Runs right after each shift — 00:10 after an 8-hour day, 04:10 after a 12-hour one. Sends two messages to Saved Messages: the shift report and a short review. With `ANTHROPIC_API_KEY` set in `.env`, Claude reads each active chat's transcript and counts distinct customer-service tasks (card activation, money code, …) and who handled each one. Without a key it falls back to per-chat message counts.

It reads **one window: Charlotte's own shift.** Transcripts stop at the hours she was on duty, so a request raised before she came on or after she logged off is never in front of the model, and every task it finds is hers to be measured against. A teammate who answered inside her hours is still named and counted — that is what the "teammates, same hours" line is — but nobody's night is scanned for their own sake.

The daily leaderboard was **removed on 2026-09-12**. It needed a 24-hour window across every chat, which roughly doubled the number of model calls per night for a ranking of other people's shifts; the account ran out of API credit and the report went blank for three nights. What she wants back is her own shift. It is recoverable from git history if the comparison is ever wanted again.

**DMs are work.** Direct messages get the same task analysis as groups and count toward Charlotte's totals — she spends more time there than in groups. DMs with staff are excluded entirely, in both directions: a colleague's question is not her outstanding customer work. A DM containing only a phone call is contact, not an unanswered request, so it no longer lands in the no-reply list.

Her own on-duty window and the number of distinct hours she posted in are derived from the messages, so the headline rate is tasks per hour actually worked rather than raw share — she starts before most of the team and a raw percentage would only reward whoever sat online longest.

The same pass also grades Charlotte's own handling chat by chat — what she did well, and where she was slow, curt, or never followed up on a "checking…" — and a final call turns those observations into a short review ("🧭 How your shift went") sent as its own message so a long report can't truncate it away.

### The roster

`roster.py` says who is who, and only the customer-service team counts as teammates. Everyone else who answers a customer — sales, accounting, fleet services like Fleet 24/7, dispatchers, the customer's own staff — is counted and named on a separate line, never mixed into the team tally.

People are keyed by **Telegram user ID, not name**. Names are unusable as identities here: agents use an alias plus their real name (`Ben Kennedy (Baxtiyor)`), two different colleagues both go by Max — one in sales, one in accounting — and one teammate's account shows a bare `v`. Matching on the first word of a name merged all of those and turned `Fleet 24/7`, a fleet service shared by six clients, into a fictional agent called "Fleet". IDs also survive an alias change, which names do not.

Transcripts are labelled with the roster's own name for each person before Claude sees them, so attribution comes back in exactly the spelling the code expects, and the two Maxes stay apart.

`python3 roster.py [days]` lists everyone who posted in the last few days and is *not* on the roster, sorted by how many chats they appeared in — staff show up across many chats, a customer usually in one. That is how a new hire gets added: run it, find them, paste the ID into `TEAM`. Anyone missing from the roster is attributed by the name they post under rather than being folded into the team tally, so a missing teammate shows up as an unfamiliar name instead of being silently dropped.

`SALES_PEOPLE` / `CLIENT_PEOPLE` (comma-separated) in `.env` still add names on top of the roster for anyone whose ID has not been collected yet.

### Models

The report uses **`claude-sonnet-5`**; override with `REPORT_MODEL` in `.env`. It ran on `claude-opus-5` from 27 Aug to 12 Sep, which at roughly 100 chats a night cost about $1.57 a night against Sonnet's $0.42 — the analysis is reading a transcript and saying who answered what, which does not need the more expensive model.

`TASK_PROMPT` is sent with `cache_control: ephemeral`. It is the same ~1,100 tokens on every one of the ~100 calls, about 86% of all input, so caching it is most of what the report pays for. Sonnet's minimum cacheable prefix is 1,024 tokens and the prompt only just clears it, so the run prints `N input tokens billed, M read from cache` to stderr — that lands in `cron.log` and is the proof it is actually caching. If `M` is 0, the prompt has fallen under the minimum: lengthen it, or set `REPORT_MODEL=claude-opus-5`, whose minimum is 512.

`ANALYSIS_WORKERS` (default 5) sets how many chats are analysed at once; running them one at a time made the report take too long.

A live shift watcher used to run alongside these, nudging about chats that looked unanswered. It was retired in August 2026 for crying wolf: it nudged when the customer had gone quiet after a reply, it did not understand that a screenshot is often the answer itself, and it could not see reactions, so a chat closed with an emoji looked ignored.

## Setup

1. Get a Telegram API ID and hash at [my.telegram.org](https://my.telegram.org)
2. Generate a session string for each account using Telethon's `StringSession`
3. Add secrets to the repo (Settings → Secrets → Actions):

| Secret | Description |
|---|---|
| `API_ID` / `API_HASH` | First account's API credentials |
| `SESSION_STRING` | First account's session string |
| `API_ID_V` / `API_HASH_V` | Second account's API credentials |
| `SESSION_STRING_V` | Second account's session string |

4. Add `online.jpg`, `offline.jpg`, `online_v.jpg`, `offline_v.jpg` to `images/`

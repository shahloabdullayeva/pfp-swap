# pfp-swap

Automatically swaps Telegram profile pictures between online and offline states on a weekly schedule. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and GitHub Actions. Vibe-coded with Claude.

## How it works

Two GitHub Actions workflows run on a cron schedule and swap the profile photo based on the current time in Tashkent (UTC+5).

**Charlotte** — `swap_pfp.py`  
Online **Wed–Sun, 16:00–00:00** Tashkent (Mon and Tue off), with dated
exceptions — Sat 29 and Sun 30 Aug 2026 are 12-hour days, 16:00–04:00.

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
| 16:05 | `shift_watch.py` |
| 00:01, 04:01 | `swap_pfp.py auto` |
| 00:10, 04:10 | `shift_report.py` |

Each script asks `schedule.py` whether it should act and exits silently — before
connecting to Telegram — when it shouldn't. `swap_pfp.py auto` also records what
it last set in `.pfp_state`, so repeat firings never re-swap the photo or send a
duplicate note to Saved Messages. Passing `online`/`offline` explicitly still
forces a swap, and `shift_report.py <start> <end>` still reports any window.

**Shift report** — `shift_report.py`  
Runs right after each shift — 00:10 after an 8-hour day, 04:10 after a 12-hour one. Scans all Telegram groups for the shift's window and sends a report to Saved Messages. With `ANTHROPIC_API_KEY` set in `.env`, Claude reads each active group's transcript and counts distinct customer-service tasks (card activation, money code, …) and whether each was handled by Charlotte, another team member, or nobody. Agents who join partway through the shift are also credited fairly: each person's on-duty window and the number of distinct hours they posted in are derived from the messages, and their rate is tasks per hour actually worked. Without a key it falls back to per-group message counts.

The same pass also grades Charlotte's own handling chat by chat — what she did well, and where she was slow, curt, or never followed up on a "checking…" — and a final call turns those observations into a short review ("🧭 How your shift went") sent as its own message so a long report can't truncate it away.

Not everyone who replies in a customer chat is on the customer-service team: **Nurmuhammad is sales** and **Doniyorbek is a client**. Sales work is reported on its own line instead of in the team tally, and a "reply" from a client counts as unanswered, since no staff member actually picked it up. Override the lists with `SALES_PEOPLE` / `CLIENT_PEOPLE` (comma-separated) in `.env`.

**Live shift watcher** — `shift_watch.py`  
Runs from 16:05 until 5 minutes before the shift ends (23:55 on an 8-hour day, 03:55 the next morning on a 12-hour one), on shift days only. Listens to all groups and DMs; every 5 minutes Claude checks chats where a customer has waited 15+ minutes with no staff reply, or where Charlotte promised something ("checking…") and hasn't followed up in 20+ minutes — and sends a "👀 Needs attention" nudge to Saved Messages. It starts 5 minutes after the shift begins and stops 5 minutes before it ends, so it never shares the Telegram session with the pfp-swap/report cron jobs. On startup it seeds its state with messages sent since the shift start, so requests already pending at the start of the shift are covered too.

### Models

The report uses `claude-opus-5` and the watcher `claude-sonnet-5`; override with `REPORT_MODEL` / `WATCH_MODEL` in `.env`. The watcher makes many small yes/no calls, so it runs on the cheaper model — but not lower: on the watcher's test cases Haiku 4.5 missed an unanswered customer, which is the one thing it must never miss.

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

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

A hand-run swap also wins until the rota next changes its mind: set yourself
offline at 21:00 because you went home ill and the 00:01 firing leaves the photo
alone, because the rota wanted the same thing it wanted when you overrode it.
The next boundary that genuinely differs takes over again.

**Shift report** — `shift_report.py`  
Runs right after each shift — 00:10 after an 8-hour day, 04:10 after a 12-hour one. Sends up to three messages to Saved Messages: the shift report, a daily leaderboard, and a short review. With `ANTHROPIC_API_KEY` set in `.env`, Claude reads each active chat's transcript and counts distinct customer-service tasks (card activation, money code, …) and who handled each one. Without a key it falls back to per-chat message counts.

It reads **two windows** in one pass. The *shift window* is Charlotte's own hours and drives her report — her tasks, what went unanswered, her message counts. The *day window* is the 24 hours ending when her shift ends, and drives the leaderboard, so a teammate who works 21:00–03:00 is measured over his whole night instead of only the part that overlaps her. Each task carries the timestamp Claude read off the transcript, which is what sorts it into the shift window or not; a 24-hour window makes an `HH:MM` unambiguous, so no date guessing is involved.

Because the day window ends when Charlotte logs off, work done *after* her shift — the after-hours crew at 02:00 — lands in the next day's leaderboard rather than that night's. Every hour is still counted exactly once and nobody is double-counted or lost; it is simply shifted by one cycle. Running the report later (a `shift_report.py <start> <end>` by hand, or a later cron line) is what would put the night crew in the same report as the evening they followed.

**DMs are work.** Direct messages get the same task analysis as groups and count toward Charlotte's totals — she spends more time there than in groups. DMs with staff are excluded entirely, in both directions: a colleague's question is not her outstanding customer work. A DM containing only a phone call is contact, not an unanswered request, so it no longer lands in the no-reply list.

Everyone is credited fairly: each person's on-duty window and the number of distinct hours they posted in are derived from the messages, and their rate is tasks per hour actually worked. The leaderboard ranks on that rate, not raw share, because teammates start at different times and a raw percentage rewards whoever sat online longest.

The same pass also grades Charlotte's own handling chat by chat — what she did well, and where she was slow, curt, or never followed up on a "checking…" — and a final call turns those observations into a short review ("🧭 How your shift went") sent as its own message so a long report can't truncate it away.

### The roster

`roster.py` says who is who, and the leaderboard ranks **only** the customer-service team. Everyone else who answers a customer — sales, accounting, fleet services like Fleet 24/7, dispatchers, the customer's own staff — is counted and named on a separate line, never mixed into the team tally.

People are keyed by **Telegram user ID, not name**. Names are unusable as identities here: agents use an alias plus their real name (`Ben Kennedy (Baxtiyor)`), two different colleagues both go by Max — one in sales, one in accounting — and one teammate's account shows a bare `v`. Matching on the first word of a name merged all of those and turned `Fleet 24/7`, a fleet service shared by six clients, into a fictional agent called "Fleet". IDs also survive an alias change, which names do not.

Transcripts are labelled with the roster's own name for each person before Claude sees them, so attribution comes back in exactly the spelling the code expects, and the two Maxes stay apart.

`python3 roster.py [days]` lists everyone who posted in the last few days and is *not* on the roster, sorted by how many chats they appeared in — staff show up across many chats, a customer usually in one. That is how a new hire gets added: run it, find them, paste the ID into `TEAM`. Anyone missing from the roster still shows up in the report under "answered by people not on the roster", so a missing teammate is visible rather than silently dropped.

`SALES_PEOPLE` / `CLIENT_PEOPLE` (comma-separated) in `.env` still add names on top of the roster for anyone whose ID has not been collected yet.

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

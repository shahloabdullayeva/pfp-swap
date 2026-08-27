# pfp-swap

Automatically swaps Telegram profile pictures between online and offline states on a weekly schedule. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and GitHub Actions. Vibe-coded with Claude.

## How it works

Two GitHub Actions workflows run on a cron schedule and swap the profile photo based on the current time in Tashkent (UTC+5).

**Charlotte** — `swap_pfp.py`  
Online **Wed–Thu, 4pm–midnight**. Runs at 11:00 and 19:00 UTC.

**Vazira** — `swap_vazira.py`  
Online **Fri–Mon** with specific hour windows. Runs at 08:00, 12:00, 16:00, 20:00 UTC on relevant days.

Schedule logic lives in `schedule.py`.

**Shift report** — `shift_report.py`  
Runs at 00:10 Thu/Fri (Tashkent), right after each shift. Scans all Telegram groups for the 16:00–00:00 window and sends a report to Saved Messages. With `ANTHROPIC_API_KEY` set in `.env`, Claude reads each active group's transcript and counts distinct customer-service tasks (card activation, money code, …) and whether each was handled by Charlotte, another team member, or nobody. Agents who join partway through the shift are also credited fairly: each person's on-duty window and the number of distinct hours they posted in are derived from the messages, and their rate is tasks per hour actually worked. Without a key it falls back to per-group message counts.

The same pass also grades Charlotte's own handling chat by chat — what she did well, and where she was slow, curt, or never followed up on a "checking…" — and a final call turns those observations into a short review ("🧭 How your shift went") sent as its own message so a long report can't truncate it away.

Not everyone who replies in a customer chat is on the customer-service team: **Nurmuhammad is sales** and **Doniyorbek is a client**. Sales work is reported on its own line instead of in the team tally, and a "reply" from a client counts as unanswered, since no staff member actually picked it up. Override the lists with `SALES_PEOPLE` / `CLIENT_PEOPLE` (comma-separated) in `.env`.

**Live shift watcher** — `shift_watch.py`  
Runs 16:05–23:55 (Tashkent) on shift days. Listens to all groups and DMs; every 5 minutes Claude checks chats where a customer has waited 15+ minutes with no staff reply, or where Charlotte promised something ("checking…") and hasn't followed up in 20+ minutes — and sends a "👀 Needs attention" nudge to Saved Messages. Starts at 16:05 and exits at 23:55 so it never shares the Telegram session with the pfp-swap/report cron jobs. On startup it seeds its state with messages sent since 16:00, so requests already pending at the start of the shift are covered too.

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

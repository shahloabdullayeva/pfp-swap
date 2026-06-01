# pfp-swap

Automatically swaps Telegram profile pictures based on a weekly online/offline schedule. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and GitHub Actions. Vibe-coded with Claude.

## How it works

Two GitHub Actions workflows run on a cron schedule and swap the profile photo to an `online` or `offline` image based on the current time in Tashkent (UTC+5).

**Charlotte** — `swap_pfp.py`  
Online **Wed–Sun, 4pm–4am**. Workflow runs at 11:00 and 23:00 UTC on relevant days.

**Vazira** — `swap_vazira.py`  
Online **Fri–Mon** with specific hour windows. Workflow runs 4× daily on relevant days.

The schedule logic lives in `schedule.py` and is tested by `test_schedule.py`.

## Manual override

Send a message to your own **Saved Messages** in Telegram. The next scheduled run (within 4 hours) will pick it up.

| Command | Effect |
|---|---|
| `/on me` | Force Charlotte → online |
| `/off` or `/off me` | Force Charlotte → offline |
| `/on Vazira` | Force Vazira → online |
| `/off Vazira` | Force Vazira → offline |

## Setup

1. Get a Telegram API ID and hash at [my.telegram.org](https://my.telegram.org)
2. Generate a session string using `export_session.py` / `export_vazira.py`
3. Add secrets to the repo (Settings → Secrets → Actions):

| Secret | Description |
|---|---|
| `API_ID` / `API_HASH` | Charlotte's Telegram API credentials |
| `SESSION_STRING` | Charlotte's session string |
| `API_ID_V` / `API_HASH_V` | Vazira's Telegram API credentials |
| `SESSION_STRING_V` | Vazira's session string |

4. Add your `online.jpg`, `offline.jpg`, `online_v.jpg`, `offline_v.jpg` to `images/`

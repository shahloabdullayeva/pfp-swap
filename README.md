# pfp-swap

Automatically swaps Telegram profile pictures between online and offline states on a weekly schedule. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and GitHub Actions. Vibe-coded with Claude.

## How it works

Two GitHub Actions workflows run on a cron schedule and swap the profile photo based on the current time in Tashkent (UTC+5).

**Charlotte** — `swap_pfp.py`  
Online **Wed–Sun, 4pm–4am**. Runs at 11:00 and 23:00 UTC.

**Vazira** — `swap_vazira.py`  
Online **Fri–Mon** with specific hour windows. Runs at 08:00, 12:00, 16:00, 20:00 UTC on relevant days.

Schedule logic lives in `schedule.py`.

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

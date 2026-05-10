"""Log who viewed your main account's Telegram stories.

Requires Telegram Premium (only premium accounts can see story viewers
beyond the first 100 / past 24h).

Appends to story_views.csv, keyed on (story_id, viewer_id) so re-runs
update existing rows rather than duplicating them.
"""
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from telethon.tl.functions.stories import (
    GetPeerStoriesRequest,
    GetStoriesArchiveRequest,
    GetStoryViewsListRequest,
)

api_id = int(os.environ['API_ID_MAIN'])
api_hash = os.environ['API_HASH_MAIN']
session_string = os.environ.get('SESSION_STRING_MAIN')

LOG_PATH = Path('story_views.csv')
FIELDS = [
    'story_id',
    'viewer_id',
    'viewer_username',
    'viewer_first_name',
    'viewer_last_name',
    'viewed_at_utc',
    'reaction',
    'first_logged_utc',
    'last_logged_utc',
]


def with_retry(fn, attempts=4):
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except FloodWaitError as e:
            wait = e.seconds + 1
            print(f"FloodWait {wait}s (attempt {i+1}/{attempts})")
            time.sleep(wait)
            last_err = e
    raise last_err


def load_existing():
    rows = {}
    if not LOG_PATH.exists():
        return rows
    with LOG_PATH.open(newline='') as f:
        for r in csv.DictReader(f):
            rows[(int(r['story_id']), int(r['viewer_id']))] = r
    return rows


def save(rows):
    ordered = sorted(
        rows.values(),
        key=lambda r: (int(r['story_id']), r['viewed_at_utc']),
    )
    with LOG_PATH.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(ordered)


def fetch_all_stories(client):
    stories = {}
    try:
        active = with_retry(lambda: client(GetPeerStoriesRequest(peer='me')))
        for s in active.stories.stories:
            stories[s.id] = s
    except Exception as e:
        print(f"Could not fetch active stories: {e}")
    try:
        archive = with_retry(lambda: client(GetStoriesArchiveRequest(
            peer='me', offset_id=0, limit=100,
        )))
        for s in archive.stories:
            stories[s.id] = s
    except Exception as e:
        print(f"Could not fetch archived stories: {e}")
    return list(stories.values())


def fetch_viewers(client, story_id):
    out = []
    offset = ''
    while True:
        try:
            res = with_retry(lambda: client(GetStoryViewsListRequest(
                peer='me',
                id=story_id,
                offset=offset,
                limit=100,
                q='',
                just_contacts=False,
                reactions_first=False,
                forwards_first=False,
            )))
        except Exception as e:
            print(f"Could not fetch viewers for story {story_id}: {e}")
            break
        users_by_id = {u.id: u for u in res.users}
        for v in res.views:
            out.append((v, users_by_id.get(getattr(v, 'user_id', None))))
        if not res.next_offset:
            break
        offset = res.next_offset
    return out


def reaction_str(reaction):
    if reaction is None:
        return ''
    return getattr(reaction, 'emoticon', '') or getattr(reaction, 'document_id', '') or ''


def main():
    session = StringSession(session_string) if session_string else 'main_session'
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds')

    existing = load_existing()
    new_count = 0
    update_count = 0

    with TelegramClient(session, api_id, api_hash) as client:
        stories = fetch_all_stories(client)
        print(f"Found {len(stories)} stories")

        for story in stories:
            viewers = fetch_viewers(client, story.id)
            print(f"Story {story.id}: {len(viewers)} viewers")

            for view, user in viewers:
                viewer_id = getattr(view, 'user_id', None)
                if viewer_id is None:
                    continue
                viewed_at = getattr(view, 'date', None)
                viewed_at_iso = viewed_at.astimezone(timezone.utc).isoformat(timespec='seconds') if viewed_at else ''
                key = (story.id, viewer_id)
                row = {
                    'story_id': story.id,
                    'viewer_id': viewer_id,
                    'viewer_username': getattr(user, 'username', '') or '' if user else '',
                    'viewer_first_name': getattr(user, 'first_name', '') or '' if user else '',
                    'viewer_last_name': getattr(user, 'last_name', '') or '' if user else '',
                    'viewed_at_utc': viewed_at_iso,
                    'reaction': reaction_str(getattr(view, 'reaction', None)),
                    'first_logged_utc': existing.get(key, {}).get('first_logged_utc') or now_iso,
                    'last_logged_utc': now_iso,
                }
                if key in existing:
                    update_count += 1
                else:
                    new_count += 1
                existing[key] = row

    save(existing)
    print(f"Wrote {LOG_PATH}: {new_count} new, {update_count} updated, {len(existing)} total rows")


if __name__ == '__main__':
    main()

import os
from datetime import datetime, timedelta, timezone
from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def get_override(target):
    """
    Check Charlotte's Saved Messages for a manual override command sent in the
    last 12 hours. Commands: /on me, /on Vazira, /off, /off me, /off Vazira.
    target: 'charlotte' or 'vazira'
    Returns: 'online', 'offline', or None (no override found)
    Requires API_ID, API_HASH, SESSION_STRING env vars (Charlotte's account).
    """
    api_id = os.environ.get('API_ID')
    api_hash = os.environ.get('API_HASH')
    if not api_id or not api_hash:
        return None
    session_string = os.environ.get('SESSION_STRING')
    session = StringSession(session_string) if session_string else 'charlotte_session'

    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    with TelegramClient(session, int(api_id), api_hash) as client:
        for msg in client.iter_messages('me', limit=20):
            if msg.date < cutoff:
                break
            text = (msg.text or '').strip()
            if target == 'charlotte':
                if text == '/on me':
                    return 'online'
                if text in ('/off', '/off me'):
                    return 'offline'
            elif target == 'vazira':
                if text == '/on Vazira':
                    return 'online'
                if text in ('/off', '/off Vazira'):
                    return 'offline'
    return None

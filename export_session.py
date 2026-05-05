import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']

with TelegramClient('charlotte_session', api_id, api_hash) as client:
    session_str = StringSession.save(client.session)
    print("\n=== SESSION STRING ===")
    print(session_str)
    print("=== end ===\n")

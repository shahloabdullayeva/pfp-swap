import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ['API_ID_V'])
api_hash = os.environ['API_HASH_V']

with TelegramClient('vazira_session', api_id, api_hash) as client:
    print("\n=== SESSION STRING ===")
    print(StringSession.save(client.session))
    print("=== end ===\n")


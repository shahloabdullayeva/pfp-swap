import os
from telethon.sync import TelegramClient

api_id = int(os.environ['API_ID_V'])
api_hash = os.environ['API_HASH_V']

with TelegramClient('vazira_session', api_id, api_hash) as client:
    me = client.get_me()
    print("Logged in as:", me.username or me.first_name)

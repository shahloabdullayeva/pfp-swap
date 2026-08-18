import os
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']

with TelegramClient('charlotte_session', api_id, api_hash) as client:
    print("Logged in as:", client.get_me().username)
    print(StringSession.save(client.session))

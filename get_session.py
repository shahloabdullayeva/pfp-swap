import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
with TelegramClient('charlotte_session', api_id, api_hash) as client:
    s = StringSession.save(client.session)
    with open('.env', 'a') as f:
        f.write('SESSION_STRING=' + s + '\n')
    print('wrote', len(s), 'chars to .env')

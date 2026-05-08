from telethon.sync import TelegramClient

api_id =32424882
api_hash = 'f3deef8a9d70e800e83ce57fffcb90e3'

with TelegramClient('vazira_session', api_id, api_hash) as client:
    me = client.get_me()
    print("Logged in as:", me.username or me.first_name)

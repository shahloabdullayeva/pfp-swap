from telethon.sync import TelegramClient

api_id = 31624508
api_hash = '8b85645074f73a6e5418c90e013d3eae'

with TelegramClient('charlotte_session', api_id, api_hash) as client:
    print("Logged in as:", client.get_me().username31624508)

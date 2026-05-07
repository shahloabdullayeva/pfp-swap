import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')

mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'

def is_online_now():
    now = datetime.now(ZoneInfo('Asia/Tashkent'))
    weekday = now.weekday() 
    hour = now.hour

    if weekday == 2 and hour >= 17:
        return True
    if weekday == 3 and (hour < 1 or hour >= 16):
        return True
    if weekday == 4 and (hour < 1 or hour >= 17):
        return True
    if weekday == 5 and (hour < 1 or hour >= 16):
        return True
    if weekday == 6 and (hour < 1 or hour >= 16):
        return True
    if weekday == 0 and hour < 1:
        return True
    return False

if mode == 'auto':
    mode = 'online' if is_online_now() else 'offline'

image_path = f'images/{mode}.jpg'
print(f"Setting pfp to: {mode}")

session = StringSession(session_string) if session_string else 'charlotte_session'

with TelegramClient(session, api_id, api_hash) as client:
    file = client.upload_file(image_path)
    client(UploadProfilePhotoRequest(file=file))
    print("Done.")

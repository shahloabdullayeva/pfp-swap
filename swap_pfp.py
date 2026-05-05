import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon.sync import TelegramClient
from telethon.tl.functions.photos import UploadProfilePhotoRequest

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']

mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'

if mode == 'auto':
    now = datetime.now(ZoneInfo('Asia/Tashkent'))
    weekday = now.weekday()
    hour = now.hour
    if (weekday == 2 and hour >= 17) or weekday in (3, 4, 5) or (weekday == 6 and hour < 1):
        mode = 'online'
    else:
        mode = 'offline'

image_path = f'images/{mode}.jpg'
print(f"Setting pfp to: {mode}")

with TelegramClient('charlotte_session', api_id, api_hash) as client:
    file = client.upload_file(image_path)
    client(UploadProfilePhotoRequest(file=file))
    print("Done.")

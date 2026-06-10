import os
import sys
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest, GetUserPhotosRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto

from schedule import charlotte_is_online

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')

mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'

if mode == 'auto':
    mode = 'online' if charlotte_is_online() else 'offline'

session = StringSession(session_string) if session_string else 'charlotte_session'

with TelegramClient(session, api_id, api_hash) as client:
    image_path = f'images/{mode}.jpg'
    print(f"Setting pfp to: {mode}")
    me = client.get_me()
    file = client.upload_file(image_path)
    result = client(UploadProfilePhotoRequest(file=file))
    new_photo_id = result.photo.id
    print(f"New pfp uploaded (id={new_photo_id}).")
    all_photos = client(GetUserPhotosRequest(
        user_id=me.id, offset=0, max_id=0, limit=100
    )).photos
    to_delete = [p for p in all_photos if p.id != new_photo_id]
    if to_delete:
        input_photos = [
            InputPhoto(id=p.id, access_hash=p.access_hash, file_reference=p.file_reference)
            for p in to_delete
        ]
        client(DeletePhotosRequest(id=input_photos))
        print(f"Deleted {len(to_delete)} old pfp(s).")
    else:
        print("No old pfps to delete.")

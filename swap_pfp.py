import os
import sys
import io
import time
import hashlib
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest, GetUserPhotosRequest, DeletePhotosRequest
from telethon.tl.types import InputPhoto
from telethon.errors import FloodWaitError

from schedule import charlotte_is_online

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')

mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'

if mode == 'auto':
    mode = 'online' if charlotte_is_online() else 'offline'

image_path = f'images/{mode}.jpg'
print(f"Setting pfp to: {mode}")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def with_retry(fn, attempts=4):
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except FloodWaitError as e:
            wait = e.seconds + 1
            print(f"FloodWait {wait}s (attempt {i+1}/{attempts})")
            time.sleep(wait)
            last_err = e
    raise last_err

session = StringSession(session_string) if session_string else 'charlotte_session'

with TelegramClient(session, api_id, api_hash) as client:
    me = client.get_me()

    desired_hash = sha256_file(image_path)
    photos = with_retry(lambda: client(GetUserPhotosRequest(
        user_id=me.id, offset=0, max_id=0, limit=100,
    )).photos)

    current_hash = None
    if photos:
        try:
            buf = io.BytesIO()
            client.download_media(photos[0], file=buf)
            current_hash = hashlib.sha256(buf.getvalue()).hexdigest()
        except Exception as e:
            print(f"Could not hash current pfp ({e}); will re-upload.")

    if current_hash == desired_hash:
        print("Pfp already correct; skipping upload.")
        sys.exit(0)

    file = with_retry(lambda: client.upload_file(image_path))
    result = with_retry(lambda: client(UploadProfilePhotoRequest(file=file)))
    new_photo_id = result.photo.id
    print(f"New pfp uploaded (id={new_photo_id}).")

    all_photos = with_retry(lambda: client(GetUserPhotosRequest(
        user_id=me.id, offset=0, max_id=0, limit=100,
    )).photos)

    to_delete = [p for p in all_photos if p.id != new_photo_id]
    if to_delete:
        input_photos = [
            InputPhoto(id=p.id, access_hash=p.access_hash, file_reference=p.file_reference)
            for p in to_delete
        ]
        try:
            with_retry(lambda: client(DeletePhotosRequest(id=input_photos)))
            print(f"Deleted {len(to_delete)} old pfp(s).")
        except Exception as e:
            print(f"Failed to delete old pfps: {e}")
    else:
        print("No old pfps to delete.")

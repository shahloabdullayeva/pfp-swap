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
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, '.pfp_state')


def read_state():
    try:
        with open(STATE_FILE) as f:
            parts = f.read().split()
    except FileNotFoundError:
        return None, False, None
    mode = parts[0] if parts else None
    manual = len(parts) > 1 and parts[1] == 'manual'
    want = parts[2] if len(parts) > 2 and parts[2] != '-' else None
    return mode, manual, want


def write_state(mode, manual, want):
    with open(STATE_FILE, 'w') as f:
        f.write(f"{mode} {'manual' if manual else 'auto'} {want or '-'}")


def swap(mode):
    session = StringSession(session_string) if session_string else 'charlotte_session'
    with TelegramClient(session, api_id, api_hash) as client:
        image_path = os.path.join(HERE, 'images', f'{mode}.jpg')
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
        emoji = "🟢" if mode == "online" else "🔴"
        client.send_message('me', f'{emoji} pfp switched to {mode}')
        print("Notification sent to Saved Messages.")


def main():
    requested = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    if requested not in ('auto', 'online', 'offline'):
        sys.exit('usage: swap_pfp.py [auto|online|offline]')

    want = 'online' if charlotte_is_online() else 'offline'
    manual = requested != 'auto'
    mode = requested if manual else want

    if not manual:
        last_mode, last_manual, last_want = read_state()
        if last_manual and last_want == want:
            return
        if last_mode == mode:
            write_state(mode, False, want)
            return

    swap(mode)
    write_state(mode, manual, want)


if __name__ == '__main__':
    main()

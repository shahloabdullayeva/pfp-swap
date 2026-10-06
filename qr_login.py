import asyncio
import os
import re
import sys
import qrcode
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError

suffix = '' if 'me' in sys.argv[1:] else '_V'
who = 'your' if suffix == '' else "Zara's"
api_id = int(os.environ['API_ID' + suffix])
api_hash = os.environ['API_HASH' + suffix]

async def main():
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        qr_login = await client.qr_login()
        while True:
            qr = qrcode.QRCode()
            qr.add_data(qr_login.url)
            print("\nIn Telegram: Settings > Devices > Link Desktop Device, then scan this:\n")
            qr.print_ascii(invert=True)
            try:
                await qr_login.wait(timeout=60)
                break
            except SessionPasswordNeededError:
                while True:
                    pw = input(f"\n{who} two-step password: ")
                    try:
                        await client.sign_in(password=pw)
                        break
                    except PasswordHashInvalidError:
                        print("wrong password, try again.")
                break
            except asyncio.TimeoutError:
                print("\nQR expired, making a fresh one...")
                await qr_login.recreate()
    key = 'SESSION_STRING' + suffix
    line = key + '=' + client.session.save()
    if 'me' in sys.argv[1:]:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        with open(path) as f:
            text = f.read()
        text, n = re.subn(r'(?m)^' + key + r'=.*$', lambda m: line, text)
        if not n:
            text = text.rstrip('\n') + '\n' + line + '\n'
        with open(path, 'w') as f:
            f.write(text)
        print('\nsaved new ' + key + ' to .env')
    else:
        print('\n' + line)
    await client.disconnect()

asyncio.run(main())

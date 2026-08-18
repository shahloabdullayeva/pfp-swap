import asyncio
import os
import qrcode
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError

api_id = int(os.environ['API_ID_V'])
api_hash = os.environ['API_HASH_V']

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
                    pw = input("\nZara's two-step password: ")
                    try:
                        await client.sign_in(password=pw)
                        break
                    except PasswordHashInvalidError:
                        print("wrong password, try again.")
                break
            except asyncio.TimeoutError:
                print("\nQR expired, making a fresh one...")
                await qr_login.recreate()
    print("\nSESSION_STRING_V=" + client.session.save())
    await client.disconnect()

asyncio.run(main())

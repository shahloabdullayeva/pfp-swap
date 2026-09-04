#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CHARLOTTE = 8605085197

TEAM = {
    8040229377: 'Mason',
    8014792813: 'Ben',
    7797669101: 'Layla',
    7419587503: 'Azi',
    8190412552: 'Dustin',
    7562933307: 'Dana',
    7447800786: 'Den',
    7008611452: 'Vazira',
}

SALES = {
    7779088659: 'Mahmud/Max',
    6172480252: 'Nurmuhammad',
    1825291629: 'Bob',
    7673880169: 'Diana',
    7582755968: 'Harlyn',
    6258742713: 'Ulugbek/Daniel',
    7162890090: 'Justin',
}

ACCOUNTING = {
    7826896007: 'Max Adams',
    6967097635: 'Michael Bisping',
    8015050815: 'Daniel Wolf City',
    7451098395: 'Jeff',
}

CLIENTS = {
    558116924: 'Doniyorbek',
    8264251583: 'Fuel department',
}

STAFF = {}
STAFF.update(TEAM)
STAFF.update(SALES)
STAFF.update(ACCOUNTING)

TEAM_NAMES = set(TEAM.values())
SALES_NAMES = set(SALES.values())
ACCOUNTING_NAMES = set(ACCOUNTING.values())
CLIENT_NAMES = set(CLIENTS.values())


def scan(days=3):
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession

    tz = ZoneInfo('Asia/Tashkent')
    start = (datetime.now(tz) - timedelta(days=days)).astimezone(ZoneInfo('UTC'))
    seen = {}
    with TelegramClient(StringSession(os.environ['SESSION_STRING']),
                        int(os.environ['API_ID']), os.environ['API_HASH']) as client:
        for dialog in client.iter_dialogs():
            if not (dialog.is_group or dialog.is_user):
                continue
            if dialog.date is None or dialog.date < start:
                continue
            for msg in client.iter_messages(dialog.entity, limit=3000):
                if msg.date is None:
                    continue
                if msg.date < start:
                    break
                if msg.out or msg.sender_id is None or msg.sender_id in STAFF:
                    continue
                sender = msg.sender
                name = (getattr(sender, 'first_name', None)
                        or getattr(sender, 'title', None) or '?')
                if getattr(sender, 'last_name', None):
                    name += ' ' + sender.last_name
                row = seen.setdefault(msg.sender_id,
                                      {'name': name, 'chats': set(),
                                       'user': getattr(sender, 'username', None)})
                row['chats'].add(dialog.name)
    rows = sorted(seen.items(), key=lambda kv: -len(kv[1]['chats']))
    print(f"not on the roster, last {days} days, by number of chats:")
    for uid, row in rows[:40]:
        print(f"{row['name'][:30]:<31}{uid:>13}  {len(row['chats']):>3} chats"
              f"  @{row['user']}")


if __name__ == '__main__':
    scan(int(sys.argv[1]) if len(sys.argv) > 1 else 3)

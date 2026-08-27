import os
import sys
import asyncio
from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from telethon.sessions import StringSession

TZ = ZoneInfo('Asia/Tashkent')
UTC = ZoneInfo('UTC')
SHIFT_START_HOUR = 16
CUSTOMER_WAIT_MIN = 15   # customer msg with no staff reply for this long -> check
FOLLOWUP_WAIT_MIN = 20   # Charlotte's "checking..." with no follow-up -> check
SWEEP_SECONDS = 300
END_HOUR, END_MINUTE = 23, 55  # exit before midnight cron jobs reconnect

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')
session = StringSession(session_string) if session_string else 'charlotte_session'

WATCH_PROMPT = (
    "You are a live shift assistant for Charlotte, a customer service agent at "
    "Octane/TSS (trucking fuel cards). Charlotte's work: card issues (activation, "
    "money codes, lock/unlock, replacement, limits, PIN), mobile app problems, "
    "and discount issues. Billing work (incoming Zelle payments, invoices, "
    "charges, statements) belongs to the billing team, and sales is not her job "
    "either. Below is the recent transcript of ONE chat during her shift; "
    "messages from 'ME' are Charlotte's own. Other customer service agents "
    "(Den, Layla, Dustin, Mason, and others) may also reply — infer who is "
    "staff from how they behave. Decide whether this chat CURRENTLY needs "
    "Charlotte's attention: a customer service request is sitting unanswered by "
    "any staff, or Charlotte promised something ('checking', 'one moment', "
    "'let me see') and never followed up. If staff already handled everything, "
    "or the only pending items are billing/sales/chit-chat, it does NOT need "
    "attention. Real customer groups usually carry a trucking company's name "
    "and/or carrier ID; INTERNAL team groups — staff/office chats like "
    "'Customer Service Team' or 'Octane UZB Office Team' with no customers — "
    "NEVER need attention nudges. Keep reason under 10 words."
)


def ai_check(name, msgs):
    import anthropic
    from pydantic import BaseModel

    class Verdict(BaseModel):
        needs_attention: bool
        reason: str

    ai = anthropic.Anthropic()
    transcript = '\n'.join(
        f"[{t.strftime('%H:%M')}] {who}: {text}" for t, who, text, _ in msgs)
    response = ai.messages.parse(
        model="claude-opus-5",
        max_tokens=1500,
        system=WATCH_PROMPT,
        messages=[{"role": "user", "content": f"Chat: {name}\n\n{transcript}"}],
        output_format=Verdict,
    )
    return response.parsed_output


async def seed_state(client, state, since_utc):
    """Load messages already sent this shift, so a 16:05 start still sees 16:00."""
    seeded = 0
    async for dialog in client.iter_dialogs():
        is_user = dialog.is_user and not dialog.is_group
        if not dialog.is_group and not is_user:
            continue
        if is_user:
            ent = dialog.entity
            if getattr(ent, 'bot', False) or getattr(ent, 'is_self', False):
                continue
        if dialog.date is None or dialog.date < since_utc:
            continue
        msgs = []
        async for msg in client.iter_messages(dialog.entity, limit=40):
            if msg.date is None:
                continue
            if msg.date < since_utc:
                break
            if msg.out:
                who = 'ME'
            else:
                sender = msg.sender
                who = (getattr(sender, 'first_name', None)
                       or getattr(sender, 'title', None) or 'Customer')
            text = (msg.text or '[media]').strip()[:300]
            msgs.append((msg.date.astimezone(TZ), who, text, msg.id))
        if not msgs:
            continue
        msgs.reverse()
        existing = state.get(dialog.id)
        if existing:
            # a live message may have arrived while seeding — keep both
            known = {i for _, _, _, i in existing['msgs']}
            merged = [m for m in msgs if m[3] not in known] + list(existing['msgs'])
            existing['msgs'] = deque(merged[-40:], maxlen=40)
        else:
            state[dialog.id] = {
                'name': dialog.name, 'msgs': deque(msgs, maxlen=40),
                'analyzed_id': 0, 'nudged_id': 0,
            }
        seeded += 1
    return seeded


async def main():
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sweep = int(sys.argv[2]) if len(sys.argv) > 2 else SWEEP_SECONDS

    client = TelegramClient(session, api_id, api_hash)
    await client.start()
    me = await client.get_me()
    state = {}

    @client.on(events.NewMessage())
    async def handler(event):
        if event.chat_id == me.id:
            return
        if event.is_private:
            sender = await event.get_sender()
            if sender is None or getattr(sender, 'bot', False):
                return
        elif not event.is_group:
            return
        chat = await event.get_chat()
        name = (getattr(chat, 'title', None)
                or getattr(chat, 'first_name', None) or 'Unknown')
        st = state.setdefault(event.chat_id, {
            'name': name, 'msgs': deque(maxlen=40),
            'analyzed_id': 0, 'nudged_id': 0,
        })
        if event.out:
            who = 'ME'
        else:
            sender = await event.get_sender()
            who = (getattr(sender, 'first_name', None)
                   or getattr(sender, 'title', None) or 'Customer')
        text = (event.raw_text or '[media]').strip()[:300]
        st['msgs'].append((datetime.now(TZ), who, text, event.id))

    if minutes is not None:
        end = None
        deadline = asyncio.get_event_loop().time() + minutes * 60
    else:
        end = datetime.now(TZ).replace(hour=END_HOUR, minute=END_MINUTE,
                                       second=0, microsecond=0)

    now = datetime.now(TZ)
    if minutes is not None:
        seed_since = now - timedelta(minutes=60)
    else:
        seed_since = now.replace(hour=SHIFT_START_HOUR, minute=0,
                                 second=0, microsecond=0)
    if seed_since < now:
        seeded = await seed_state(client, state, seed_since.astimezone(UTC))
        print(f"seeded {seeded} chats since {seed_since:%H:%M}", flush=True)

    print(f"watcher started at {datetime.now(TZ)}", flush=True)
    while True:
        if minutes is not None:
            if asyncio.get_event_loop().time() >= deadline:
                break
        elif datetime.now(TZ) >= end:
            break
        await asyncio.sleep(sweep)

        now = datetime.now(TZ)
        alerts = []
        for st in list(state.values()):
            if not st['msgs']:
                continue
            last_time, last_who, _, last_id = st['msgs'][-1]
            if last_id <= st['analyzed_id']:
                continue
            age_min = (now - last_time).total_seconds() / 60
            wait = FOLLOWUP_WAIT_MIN if last_who == 'ME' else CUSTOMER_WAIT_MIN
            if age_min < wait:
                continue
            st['analyzed_id'] = last_id
            try:
                verdict = await asyncio.to_thread(
                    ai_check, st['name'], list(st['msgs']))
            except Exception as e:
                print(f"AI check failed for {st['name']}: {e}",
                      file=sys.stderr, flush=True)
                continue
            if verdict.needs_attention and last_id > st['nudged_id']:
                st['nudged_id'] = last_id
                alerts.append((st['name'], verdict.reason))
        if alerts:
            text = '👀 Needs attention:\n' + '\n'.join(
                f'• {name} — {reason}' for name, reason in alerts)
            await client.send_message('me', text[:4000])
            print(f"nudged: {len(alerts)} chat(s)", flush=True)

    await client.disconnect()
    print(f"watcher stopped at {datetime.now(TZ)}", flush=True)


if __name__ == '__main__':
    asyncio.run(main())

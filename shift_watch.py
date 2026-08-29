import os
import sys
import asyncio
from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from schedule import current_shift

TZ = ZoneInfo('Asia/Tashkent')
UTC = ZoneInfo('UTC')
CUSTOMER_WAIT_MIN = 15
FOLLOWUP_WAIT_MIN = 20
SWEEP_SECONDS = 300
WATCH_MODEL = os.environ.get('WATCH_MODEL', 'claude-sonnet-5')
END_MARGIN_MIN = 5

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
    "(Den, Layla, Dustin, Mason, Max, and others) may also reply — infer who is "
    "staff from how they behave. Nurmuhammad is SALES and Doniyorbek is a "
    "CUSTOMER, so a reply from either NEVER counts as the request being handled. Decide whether this chat CURRENTLY needs "
    "Charlotte's attention: a customer service request is sitting unanswered by "
    "any staff, or Charlotte promised something ('checking', 'one moment', "
    "'let me see') and never followed up. Agents take over each other's chats "
    "constantly and that is normal: once ANY staff member has answered the "
    "request, it is CLOSED — even when Charlotte was the one who greeted or "
    "promised — so never nudge her about a chat a teammate already handled. "
    "Sending a discount case to the discount-issues group is a real handoff "
    "too, not a pending item. ONLY A CUSTOMER waiting on staff is her "
    "problem. Staff-to-staff messages never earn a nudge in EITHER "
    "direction: not when Charlotte's own question to a teammate, a "
    "supervisor or another department goes unanswered, and not when a "
    "colleague asks HER to check or fix something. If no customer is "
    "waiting in the chat, stay quiet. "
    "A screenshot can BE the answer: agents "
    "often prove a card is active or a code was issued by sending an image "
    "rather than writing it out, so a screenshot that plainly answers the "
    "request is a completed reply and not a pending one. "
    "If staff already handled everything, "
    "or the only pending items are billing/sales/chit-chat, it does NOT need "
    "attention. Real customer groups usually carry a trucking company's name "
    "and/or carrier ID; INTERNAL staff chats — office/team groups like "
    "'Customer Service Team', 'TSS Customer Experience Team' or 'Octane UZB "
    "Office Team', and one-to-one DMs with colleagues — have no customer in "
    "them and NEVER need attention nudges, no matter who is waiting on whom. "
    "Keep reason under 10 words."
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
        model=WATCH_MODEL,
        max_tokens=1500,
        system=WATCH_PROMPT,
        messages=[{"role": "user", "content": f"Chat: {name}\n\n{transcript}"}],
        output_format=Verdict,
    )
    return response.parsed_output


async def seed_state(client, state, since_utc):
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

    shift = None if minutes is not None else current_shift()
    if minutes is None and shift is None:
        print(f"no shift at {datetime.now(TZ):%a %d %b %H:%M} — not watching",
              flush=True)
        return

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
        seed_since = datetime.now(TZ) - timedelta(minutes=60)
    else:
        seed_since, shift_end = shift
        end = shift_end - timedelta(minutes=END_MARGIN_MIN)

    now = datetime.now(TZ)
    if seed_since < now:
        seeded = await seed_state(client, state, seed_since.astimezone(UTC))
        print(f"seeded {seeded} chats since {seed_since:%H:%M}", flush=True)

    until = f" until {end:%a %d %b %H:%M}" if end else ""
    print(f"watcher started at {datetime.now(TZ)}{until}", flush=True)
    pending = []
    while True:
        if minutes is not None:
            if asyncio.get_event_loop().time() >= deadline:
                break
        elif datetime.now(TZ) >= end:
            break
        await asyncio.sleep(sweep)

        try:
            now = datetime.now(TZ)
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
                try:
                    verdict = await asyncio.to_thread(
                        ai_check, st['name'], list(st['msgs']))
                except Exception as e:
                    print(f"AI check failed for {st['name']}: {e}",
                          file=sys.stderr, flush=True)
                    continue
                st['analyzed_id'] = last_id
                if verdict.needs_attention and last_id > st['nudged_id']:
                    st['nudged_id'] = last_id
                    pending.append((st['name'], verdict.reason))
            if pending:
                text = '👀 Needs attention:\n' + '\n'.join(
                    f'• {name} — {reason}' for name, reason in pending)
                await client.send_message('me', text[:4000])
                print(f"nudged: {len(pending)} chat(s)", flush=True)
                pending.clear()
        except Exception as e:
            print(f"sweep failed: {e}", file=sys.stderr, flush=True)

    await client.disconnect()
    print(f"watcher stopped at {datetime.now(TZ)}", flush=True)


if __name__ == '__main__':
    asyncio.run(main())

import os
import sys
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

TZ = ZoneInfo('Asia/Tashkent')
UTC = ZoneInfo('UTC')
SHIFT_HOURS = 8
PER_GROUP_LIMIT = 3000
TRANSCRIPT_MAX_MSGS = 300
TELEGRAM_MSG_LIMIT = 4000

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')
session = StringSession(session_string) if session_string else 'charlotte_session'
anthropic_key = os.environ.get('ANTHROPIC_API_KEY')


def default_window():
    # run just after midnight: previous shift = yesterday 16:00 -> midnight
    now = datetime.now(TZ)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=SHIFT_HOURS)
    return start, end


def collect_dialogs(client, start_utc, end_utc):
    groups = []
    users = []
    for dialog in client.iter_dialogs():
        is_user = dialog.is_user and not dialog.is_group
        if not dialog.is_group and not is_user:
            continue
        if is_user:
            ent = dialog.entity
            if getattr(ent, 'bot', False) or getattr(ent, 'is_self', False):
                continue
        if dialog.date is None or dialog.date < start_utc:
            continue
        received = 0
        sent = 0
        transcript = []
        for msg in client.iter_messages(dialog.entity, offset_date=end_utc,
                                        limit=PER_GROUP_LIMIT):
            if msg.date is None:
                continue
            if msg.date < start_utc:
                break
            if msg.out:
                sent += 1
                who = 'ME'
            else:
                received += 1
                sender = msg.sender
                who = getattr(sender, 'first_name', None) or getattr(sender, 'title', None) or 'Customer'
            text = (msg.text or '[media]').strip()[:300]
            ts = msg.date.astimezone(TZ).strftime('%H:%M')
            transcript.append(f'[{ts}] {who}: {text}')
        if received or sent:
            transcript.reverse()
            record = {
                'name': dialog.name,
                'received': received,
                'sent': sent,
                'transcript': transcript[-TRANSCRIPT_MAX_MSGS:],
            }
            (users if is_user else groups).append(record)
    return groups, users


def analyze_tasks(tg, groups):
    import anthropic
    from pydantic import BaseModel

    class Task(BaseModel):
        label: str
        handled_by: str

    class GroupTasks(BaseModel):
        tasks: List[Task]

    ai = anthropic.Anthropic()
    system = (
        "You analyze Telegram support-group transcripts for Charlotte, a customer "
        "service agent at Octane/TSS (trucking fuel cards). Messages from 'ME' are "
        "Charlotte's own; everyone else appears under their name. Identify each "
        "DISTINCT customer request in the transcript that is CUSTOMER SERVICE work: "
        "card issues (activation, money codes, lock/unlock, replacement, limits, "
        "PIN), mobile app problems, and discount issues. Mobile app and discount "
        "issues are Charlotte's personal responsibility within the team. "
        "Do NOT count billing-team work (incoming Zelle payments, invoices, "
        "charges, statements), sales inquiries, internal/ops chatter, chit-chat, "
        "greetings, or bot/system notifications. Real customer groups usually "
        "carry a trucking company's name and/or carrier ID (LLC, INC, numbers). "
        "INTERNAL team groups — staff/office chats like 'Customer Service Team' "
        "or 'Octane UZB Office Team' with no customers in them — are NOT "
        "customer chats: for those return an empty task list. "
        "Several messages about the same "
        "request are ONE task; unrelated requests in the same chat are separate "
        "tasks. For each task set handled_by to exactly one of: 'ME' if Charlotte "
        "replied to or resolved it within this transcript; the FIRST NAME of the "
        "staff member who answered it (spelled exactly as it appears in the "
        "transcript) if another agent handled it and Charlotte did not; 'nobody' "
        "if no one addressed it. Several agents may work during Charlotte's shift "
        "(Den, Layla, Dustin, Mason, and others) — infer who is staff from the "
        "conversation itself: staff answer requests in a service role rather than "
        "asking for help. A reply from any staff member means the task is handled "
        "by that person, NOT unanswered. The transcript covers only Charlotte's shift "
        "window — judge strictly by what is inside it. Give each task a short "
        "label of 2-5 words. If there are no real tasks, return an empty list."
    )

    todo = [g for g in groups if g['received'] > 0]
    progress = tg.send_message(
        'me', f'⏳ Shift review in progress… 0% (0/{len(todo)} groups)')
    last_pct = 0

    results = []
    errors = 0
    for done, g in enumerate(todo, start=1):
        try:
            response = ai.messages.parse(
                model="claude-opus-5",
                max_tokens=4000,
                system=system,
                messages=[{
                    "role": "user",
                    "content": f"Group: {g['name']}\n\nTranscript (times are Tashkent):\n"
                               + "\n".join(g['transcript']),
                }],
                output_format=GroupTasks,
            )
            for task in response.parsed_output.tasks:
                results.append({'group': g['name'], 'label': task.label,
                                'handled_by': task.handled_by})
        except Exception as e:
            errors += 1
            print(f"AI analysis failed for {g['name']}: {e}", file=sys.stderr)
        pct = done * 100 // len(todo)
        if pct != last_pct or done == len(todo):
            try:
                tg.edit_message('me', progress,
                                f'⏳ Shift review in progress… {pct}% '
                                f'({done}/{len(todo)} groups)')
                last_pct = pct
            except Exception:
                pass
    try:
        tg.delete_messages('me', progress)
    except Exception:
        pass
    return results, errors


def fit_telegram(lines):
    out = []
    used = 0
    for i, line in enumerate(lines):
        if used + len(line) + 1 > TELEGRAM_MSG_LIMIT:
            out.append(f'… and {len(lines) - i} more lines')
            break
        out.append(line)
        used += len(line) + 1
    return '\n'.join(out)


if len(sys.argv) == 3:
    start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=TZ)
    end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=TZ)
else:
    start, end = default_window()
start_utc = start.astimezone(UTC)
end_utc = end.astimezone(UTC)

with TelegramClient(session, api_id, api_hash) as client:
    groups, users = collect_dialogs(client, start_utc, end_utc)

    active = [g for g in groups if g['received'] > 0]
    total_received = sum(d['received'] for d in groups + users)
    total_sent = sum(d['sent'] for d in groups + users)

    lines = [
        f"📊 Shift report — {start.strftime('%a %d %b, %H:%M')}–{end.strftime('%H:%M')}",
        f"👥 Active groups: {len(active)}",
    ]

    if anthropic_key:
        tasks, errors = analyze_tasks(client, active)
        by_me = [t for t in tasks if t['handled_by'].strip().upper() == 'ME']
        unanswered = [t for t in tasks
                      if t['handled_by'].strip().lower() == 'nobody']
        agents = {}
        for t in tasks:
            key = t['handled_by'].strip()
            if key.upper() == 'ME' or key.lower() == 'nobody':
                continue
            key = key.title()
            agents[key] = agents.get(key, 0) + 1

        def pct(n):
            return f"{round(n * 100 / len(tasks))}%" if tasks else "0%"

        lines.append(f"📋 CS tasks: {len(tasks)}")
        lines.append(f"✅ You: {len(by_me)} ({pct(len(by_me))})")
        if agents:
            lines.append("👥 Team:")
            for name, n in sorted(agents.items(), key=lambda kv: -kv[1]):
                lines.append(f"   • {name}: {n} ({pct(n)})")
        lines.append(f"❌ No reply: {len(unanswered)} ({pct(len(unanswered))})")
        if unanswered:
            lines.append("No reply:")
            for t in unanswered:
                lines.append(f"   • {t['group']} — {t['label']}")
        if errors:
            lines.append(f"⚠️ {errors} group(s) could not be analyzed")
    else:
        answered = [g for g in active if g['sent'] > 0]
        unanswered = [g for g in active if g['sent'] == 0]
        lines.append(f"✅ You replied in: {len(answered)}")
        lines.append(f"❌ No reply: {len(unanswered)}")
        for g in sorted(unanswered, key=lambda g: -g['received']):
            lines.append(f"   • {g['name']} ({g['received']} msgs)")

    active_users = [u for u in users if u['received'] > 0]
    answered_users = [u for u in active_users if u['sent'] > 0]
    unanswered_users = [u for u in active_users if u['sent'] == 0]
    lines.append(f"👤 Users (DMs): {len(active_users)} wrote to you — "
                 f"✅ answered {len(answered_users)}, ❌ no reply {len(unanswered_users)}")
    if unanswered_users:
        lines.append("DMs without reply:")
        for u in sorted(unanswered_users, key=lambda u: -u['received']):
            lines.append(f"   • {u['name']} ({u['received']} msgs)")

    lines.append(f"💬 Messages: {total_received} received, {total_sent} sent by you")
    report = fit_telegram(lines)

    print(report)
    client.send_message('me', report)

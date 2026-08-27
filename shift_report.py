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


def collect_groups(client, start_utc, end_utc):
    groups = []
    for dialog in client.iter_dialogs():
        if not dialog.is_group:
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
            groups.append({
                'name': dialog.name,
                'received': received,
                'sent': sent,
                'transcript': transcript[-TRANSCRIPT_MAX_MSGS:],
            })
    return groups


def analyze_tasks(groups):
    import anthropic
    from typing import Literal
    from pydantic import BaseModel

    class Task(BaseModel):
        label: str
        handled_by: Literal['me', 'other', 'nobody']

    class GroupTasks(BaseModel):
        tasks: List[Task]

    client = anthropic.Anthropic()
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
        "greetings, or bot/system notifications. Several messages about the same "
        "request are ONE task; unrelated requests in the same chat are separate "
        "tasks. For each task set handled_by: 'me' if Charlotte replied to or "
        "resolved it within this transcript; 'other' if a different customer "
        "service agent answered it and Charlotte did not; 'nobody' if no one "
        "addressed it. Several agents may work during Charlotte's shift (Den, "
        "Layla, Dustin, Mason, and others) — infer who is staff from the "
        "conversation itself: staff answer requests in a service role rather than "
        "asking for help. A reply from any staff member means the task is handled "
        "('other'), NOT unanswered. The transcript covers only Charlotte's shift "
        "window — judge strictly by what is inside it. Give each task a short "
        "label of 2-5 words. If there are no real tasks, return an empty list."
    )

    results = []
    errors = 0
    for g in groups:
        if g['received'] == 0:
            continue
        try:
            response = client.messages.parse(
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
    groups = collect_groups(client, start_utc, end_utc)

    active = [g for g in groups if g['received'] > 0]
    total_received = sum(g['received'] for g in groups)
    total_sent = sum(g['sent'] for g in groups)

    lines = [
        f"📊 Shift report — {start.strftime('%a %d %b, %H:%M')}–{end.strftime('%H:%M')}",
        f"👥 Active groups: {len(active)}",
    ]

    if anthropic_key:
        tasks, errors = analyze_tasks(active)
        by_me = [t for t in tasks if t['handled_by'] == 'me']
        by_other = [t for t in tasks if t['handled_by'] == 'other']
        unanswered = [t for t in tasks if t['handled_by'] == 'nobody']
        lines.append(f"📋 CS tasks: {len(tasks)} — ✅ you: {len(by_me)}, "
                     f"👥 others: {len(by_other)}, ❌ no reply: {len(unanswered)}")
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

    lines.append(f"💬 Messages: {total_received} received, {total_sent} sent by you")
    report = fit_telegram(lines)

    print(report)
    client.send_message('me', report)

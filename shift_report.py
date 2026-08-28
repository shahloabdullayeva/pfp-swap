import os
import re
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
# Nightly deep read of every group — kept on the strongest model by default.
REPORT_MODEL = os.environ.get('REPORT_MODEL', 'claude-opus-5')


def _roster(var, default):
    return {n.strip().title() for n in
            os.environ.get(var, default).split(',') if n.strip()}


# People who reply in customer chats but are NOT customer-service teammates.
# Sales sits in another department; clients get misread as staff by the model.
SALES_PEOPLE = _roster('SALES_PEOPLE', 'Nurmuhammad')
CLIENT_PEOPLE = _roster('CLIENT_PEOPLE', 'Doniyorbek')


def default_window():
    # run just after midnight: previous shift = yesterday 16:00 -> midnight
    now = datetime.now(TZ)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=SHIFT_HOURS)
    return start, end


def norm(name):
    """Normalize a sender/agent name to a bare first name.

    Telegram display names carry suffixes and decoration ("Nurmuhammad/TSS",
    "Al Fahad✨"); strip those so the same person matches across chats.
    """
    name = (name or '').strip()
    if name.upper() == 'ME':
        return 'ME'
    token = re.split(r'[\s/|,;:]+', name)[0]
    token = re.sub(r'[^\w-]', '', token, flags=re.UNICODE)
    return token.title()


def collect_dialogs(client, start_utc, end_utc):
    groups = []
    users = []
    activity = {}
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
            when = msg.date.astimezone(TZ)
            transcript.append(f"[{when:%H:%M}] {who}: {text}")
            key = norm(who)
            if key:
                a = activity.setdefault(
                    key, {'first': when, 'last': when, 'hours': set()})
                a['first'] = min(a['first'], when)
                a['last'] = max(a['last'], when)
                a['hours'].add(when.replace(minute=0, second=0, microsecond=0))
        if received or sent:
            transcript.reverse()
            record = {
                'name': dialog.name,
                'received': received,
                'sent': sent,
                'transcript': transcript[-TRANSCRIPT_MAX_MSGS:],
            }
            (users if is_user else groups).append(record)
    return groups, users, activity


TASK_PROMPT = (
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
    "(Den, Layla, Dustin, Mason, Max, and others) — infer who is staff from the "
    "conversation itself: staff answer requests in a service role rather than "
    "asking for help. KNOWN EXCEPTIONS: Nurmuhammad is a SALES agent, not "
    "customer service — never record him as having handled a CS task; if he is "
    "the only one who replied, set handled_by to 'Nurmuhammad' anyway so it can "
    "be counted separately. Doniyorbek is a CUSTOMER, not staff — his messages "
    "are customer messages, and a reply from him NEVER means a task was handled; "
    "use 'nobody' in that case. A reply from any staff member means the task is handled "
    "by that person, NOT unanswered. The transcript covers only Charlotte's shift "
    "window — judge strictly by what is inside it. Give each task a short "
    "label of 2-5 words. If there are no real tasks, return an empty list. "
    "SEPARATELY, judge ONLY Charlotte's own handling in this chat (the 'ME' "
    "messages). In 'good', list what she did well. In 'issues', list concrete "
    "mistakes or misses of hers: a customer left waiting a long time with "
    "nobody helping, a curt or confusing reply, or a wrong or incomplete "
    "answer. Judge response gaps from the timestamps. "
    "A TEAMMATE TAKING OVER IS NOT A MISS: agents here share chats freely, so "
    "if Charlotte greeted a chat, opened it, or said she would check and "
    "ANOTHER agent then answered or resolved it, the customer was served and "
    "that is FINE. Never list that as a dropped chat, an unfinished loop, a "
    "broken promise, or work pushed onto a colleague. Only call a promise "
    "unkept when NO staff member answered the customer at all. "
    "ROUTING IS NOT A BRUSH-OFF: discount questions are worked in the "
    "dedicated discount-issues group, so sending a discount case there — like "
    "escalating pricing to sales, billing to accounting — is correct "
    "procedure, not a curt reply. Routing does not change attribution "
    "though: handled_by stays whoever actually answered the customer. "
    "A SCREENSHOT IS OFTEN "
    "THE ANSWER ITSELF: agents here routinely prove a card is active, a "
    "price is applied or a code was issued by sending an image that shows "
    "it instead of writing it out in words. Do not call that an unfinished "
    "loop or a missing outcome. Only flag a screenshot when the customer "
    "still had to ask what it meant, or when nothing in it addresses what "
    "they asked. Each entry under 15 "
    "words and tied to something actually in the transcript. Judge NOBODY but "
    "Charlotte. If she did not take part in this chat, return empty lists for "
    "both. Never invent faults: if her handling was fine, 'issues' MUST be empty."
)


def analyze_tasks(tg, groups):
    import anthropic
    from pydantic import BaseModel

    class Task(BaseModel):
        label: str
        handled_by: str

    class GroupTasks(BaseModel):
        tasks: List[Task]
        good: List[str]
        issues: List[str]

    ai = anthropic.Anthropic()

    todo = [g for g in groups if g['received'] > 0]
    progress = tg.send_message(
        'me', f'⏳ Shift review in progress… 0% (0/{len(todo)} groups)')
    last_pct = 0

    results = []
    notes = []
    errors = 0
    for done, g in enumerate(todo, start=1):
        try:
            response = ai.messages.parse(
                model=REPORT_MODEL,
                max_tokens=4000,
                system=TASK_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Group: {g['name']}\n\nTranscript (times are Tashkent):\n"
                               + "\n".join(g['transcript']),
                }],
                output_format=GroupTasks,
            )
            out = response.parsed_output
            for task in out.tasks:
                results.append({'group': g['name'], 'label': task.label,
                                'handled_by': task.handled_by})
            for kind, items in (('good', out.good), ('issue', out.issues)):
                for text in items:
                    notes.append({'group': g['name'], 'kind': kind, 'text': text})
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
    return results, notes, errors


def review_performance(notes, stats):
    """Turn per-chat observations into one short, specific shift review."""
    import anthropic
    from pydantic import BaseModel

    class Review(BaseModel):
        verdict: str
        strengths: List[str]
        improvements: List[str]

    ai = anthropic.Anthropic()
    system = (
        "You are a customer service team lead writing an honest end-of-shift "
        "review for Charlotte (Octane/TSS, trucking fuel cards). You are given "
        "observations collected chat-by-chat from her shift, plus the shift "
        "numbers. Write: verdict — two sentences on how the shift actually went; "
        "strengths — up to 4 things she genuinely did well, each pointing at a "
        "real pattern or chat; improvements — up to 4 concrete changes, most "
        "important first, each saying what to do differently rather than naming a "
        "vague quality. Ground every point in the observations; never invent a "
        "fault or a compliment. If there is little to criticise, say so plainly "
        "instead of padding the list. No generic praise, no coaching cliches. "
        "This team shares chats: a conversation Charlotte started and a teammate "
        "finished is the team working, not a miss — never build an improvement "
        "point out of 'finish what you greet' or 'you left it to someone else'. "
        "Handing a discount case to the discount-issues group, pricing to sales "
        "or billing to accounting is correct routing, not a curt reply. "
        "Keep each bullet under 20 words."
    )
    good = [f"- [{n['group']}] {n['text']}" for n in notes if n['kind'] == 'good']
    bad = [f"- [{n['group']}] {n['text']}" for n in notes if n['kind'] == 'issue']
    content = (f"Shift numbers: {stats}\n\n"
               f"Went well ({len(good)}):\n" + "\n".join(good[:120]) +
               f"\n\nProblems noticed ({len(bad)}):\n" + "\n".join(bad[:120]))
    response = ai.messages.parse(
        model=REPORT_MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=Review,
    )
    r = response.parsed_output
    lines = ['🧭 How your shift went', r.verdict]
    if r.strengths:
        lines.append('👍 Did well:')
        lines += [f'   • {s}' for s in r.strengths]
    if r.improvements:
        lines.append('🔧 To improve:')
        lines += [f'   • {s}' for s in r.improvements]
    return lines


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


def main():
    if len(sys.argv) == 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=TZ)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=TZ)
    else:
        start, end = default_window()
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)

    with TelegramClient(session, api_id, api_hash) as client:
        groups, users, activity = collect_dialogs(client, start_utc, end_utc)

        active = [g for g in groups if g['received'] > 0]
        total_received = sum(d['received'] for d in groups + users)
        total_sent = sum(d['sent'] for d in groups + users)

        lines = [
            f"📊 Shift report — {start.strftime('%a %d %b, %H:%M')}–{end.strftime('%H:%M')}",
            f"👥 Active groups: {len(active)}",
        ]

        if anthropic_key:
            tasks, notes, errors = analyze_tasks(client, active)
            by_me = [t for t in tasks if t['handled_by'].strip().upper() == 'ME']
            # a "reply" from a client is not a reply — count it as unanswered
            unanswered = [t for t in tasks
                          if t['handled_by'].strip().lower() == 'nobody'
                          or norm(t['handled_by']) in CLIENT_PEOPLE]
            outside = [t for t in tasks if norm(t['handled_by']) in SALES_PEOPLE]
            agents = {}
            for t in tasks:
                key = norm(t['handled_by'])
                if key == 'ME' or key.lower() == 'nobody' or not key:
                    continue
                if key in SALES_PEOPLE or key in CLIENT_PEOPLE:
                    continue
                agents[key] = agents.get(key, 0) + 1

            def pct(n):
                return f"{round(n * 100 / len(tasks))}%" if tasks else "0%"

            def detail(key, n):
                """On-duty window and tasks per hour actually worked.

                The rate uses the count of distinct clock-hours the person posted in,
                so one stray early message doesn't inflate someone's apparent shift.
                """
                a = activity.get(key)
                if not a:
                    return ''
                worked = max(len(a['hours']), 1)
                return (f" — {a['first']:%H:%M}–{a['last']:%H:%M}, "
                        f"{worked}h active ({n / worked:.1f}/hr)")

            lines.append(f"📋 CS tasks: {len(tasks)}")
            lines.append(f"✅ You: {len(by_me)} ({pct(len(by_me))})"
                         f"{detail('ME', len(by_me))}")
            if agents:
                lines.append("👥 Team (active window, tasks per hour on duty):")
                for name, n in sorted(agents.items(), key=lambda kv: -kv[1]):
                    lines.append(f"   • {name}: {n} ({pct(n)}){detail(name, n)}")
            if outside:
                lines.append(f"ℹ️ Handled by sales, not CS: {len(outside)}")
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

        if anthropic_key and notes:
            stats = (f"{len(tasks)} CS tasks, you handled {len(by_me)}, "
                     f"{len(unanswered)} left unanswered, "
                     f"{len(unanswered_users)} DMs unanswered")
            try:
                review = fit_telegram(review_performance(notes, stats))
                print(review)
                client.send_message('me', review)
            except Exception as e:
                print(f"review failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()

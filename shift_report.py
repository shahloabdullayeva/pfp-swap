import os
import re
import sys
from datetime import datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageActionPhoneCall
from schedule import shift_just_ended
from roster import TEAM, STAFF, SALES_NAMES, ACCOUNTING_NAMES, CLIENT_NAMES

TZ = ZoneInfo('Asia/Tashkent')
UTC = ZoneInfo('UTC')
PER_GROUP_LIMIT = 3000
TRANSCRIPT_MAX_MSGS = 500
TELEGRAM_MSG_LIMIT = 4000
DAY_HOURS = 24
ANALYSIS_WORKERS = int(os.environ.get('ANALYSIS_WORKERS', '5'))
KNOWN_NAMES = {name.lower(): name for name in
               list(STAFF.values()) + list(CLIENT_NAMES)}

api_id = int(os.environ['API_ID'])
api_hash = os.environ['API_HASH']
session_string = os.environ.get('SESSION_STRING')
session = StringSession(session_string) if session_string else 'charlotte_session'
anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
REPORT_MODEL = os.environ.get('REPORT_MODEL', 'claude-opus-5')


def _roster(var, default):
    return {n.strip().title() for n in
            os.environ.get(var, default).split(',') if n.strip()}


SALES_PEOPLE = _roster('SALES_PEOPLE', 'Nurmuhammad')
CLIENT_PEOPLE = _roster('CLIENT_PEOPLE', 'Doniyorbek')


def default_window():
    return shift_just_ended()


def norm(name):
    name = (name or '').strip()
    if name.upper() == 'ME':
        return 'ME'
    token = re.split(r'[\s/|,;:]+', name)[0]
    token = re.sub(r'[^\w-]', '', token, flags=re.UNICODE)
    return token.title()


def canonical(msg):
    if msg.out:
        return 'ME'
    named = STAFF.get(msg.sender_id)
    if named:
        return named
    sender = msg.sender
    return (getattr(sender, 'first_name', None)
            or getattr(sender, 'title', None) or 'Customer')


def collect_dialogs(client, day_start, day_end, shift_start, shift_end):
    chats = []
    activity = {}
    shift_activity = {}
    for dialog in client.iter_dialogs():
        is_user = dialog.is_user and not dialog.is_group
        if not dialog.is_group and not is_user:
            continue
        peer_id = None
        if is_user:
            ent = dialog.entity
            if getattr(ent, 'bot', False) or getattr(ent, 'is_self', False):
                continue
            peer_id = getattr(ent, 'id', None)
        if dialog.date is None or dialog.date < day_start:
            continue
        received = 0
        sent = 0
        shift_received = 0
        shift_sent = 0
        transcript = []
        for msg in client.iter_messages(dialog.entity, offset_date=day_end,
                                        limit=PER_GROUP_LIMIT):
            if msg.date is None:
                continue
            if msg.date < day_start:
                break
            is_call = isinstance(getattr(msg, 'action', None),
                                 MessageActionPhoneCall)
            in_shift = shift_start <= msg.date < shift_end
            if not is_call:
                if msg.out:
                    sent += 1
                    if in_shift:
                        shift_sent += 1
                else:
                    received += 1
                    if in_shift:
                        shift_received += 1
            who = canonical(msg)
            text = '[call]' if is_call else (msg.text or '[media]').strip()[:300]
            when = msg.date.astimezone(TZ)
            transcript.append(f"[{when:%H:%M}] {who}: {text}")
            books = [activity] + ([shift_activity] if in_shift else [])
            for book in books:
                a = book.setdefault(
                    who, {'first': when, 'last': when, 'hours': set()})
                a['first'] = min(a['first'], when)
                a['last'] = max(a['last'], when)
                a['hours'].add(when.replace(minute=0, second=0, microsecond=0))
        if received or sent:
            transcript.reverse()
            chats.append({
                'name': dialog.name,
                'is_user': is_user,
                'internal': is_user and peer_id in STAFF,
                'received': received,
                'sent': sent,
                'shift_received': shift_received,
                'shift_sent': shift_sent,
                'transcript': transcript[-TRANSCRIPT_MAX_MSGS:],
            })
    return chats, activity, shift_activity


def parse_at(value, day_start, day_end):
    found = re.search(r'(\d{1,2}):(\d{2})', value or '')
    if not found:
        return None
    hour, minute = int(found.group(1)), int(found.group(2))
    if hour > 23 or minute > 59:
        return None
    when = day_start.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when < day_start:
        when += timedelta(days=1)
    return when if day_start <= when < day_end else None


def handler(name):
    key = (name or '').strip()
    if key.upper() == 'ME':
        return 'ME'
    if key.lower() in ('nobody', 'none', 'no one', 'no-one', ''):
        return 'nobody'
    exact = KNOWN_NAMES.get(key.lower())
    if exact:
        return exact
    first = norm(key).lower()
    hits = {canon for lower, canon in KNOWN_NAMES.items()
            if re.split(r'[\s/|,;:]+', lower)[0] == first}
    if len(hits) == 1:
        return hits.pop()
    return re.sub(r'\s+', ' ', key)[:40]


TEAM_LIST = ', '.join(sorted(set(TEAM.values())))

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
    "A transcript may be a one-to-one DM with a customer rather than a group; "
    "treat it exactly the same way — DM work counts fully. "
    "A line reading '[call]' is a phone call, not a written message: a call "
    "on its own is contact between Charlotte and the customer, never an "
    "unanswered request. "
    "Several messages about the same "
    "request are ONE task; unrelated requests in the same chat are separate "
    "tasks. For each task set handled_by to exactly one of: 'ME' if Charlotte "
    "replied to or resolved it within this transcript; the FIRST NAME of the "
    "staff member who answered it (spelled exactly as it appears in the "
    "transcript) if another agent handled it and Charlotte did not; 'nobody' "
    "if no one addressed it. THE CUSTOMER-SERVICE TEAM IS EXACTLY THESE "
    "PEOPLE, and they appear in the transcript under these names: "
    + TEAM_LIST +
    ". Everyone else who replies is NOT customer service — sales agents, "
    "accounting, fleet services such as 'Fleet 24/7', dispatchers and the "
    "customer's own staff. Still name them in handled_by, spelled exactly as "
    "they appear, so their work can be counted separately; never treat them "
    "as a member of the CS team. Doniyorbek is a CUSTOMER, not staff — his messages "
    "are customer messages, and a reply from him NEVER means a task was handled; "
    "use 'nobody' in that case. A reply from any staff member means the task is handled "
    "by that person, NOT unanswered. The transcript covers a full 24-hour day: "
    "Charlotte's own shift plus the hours her teammates work before and after "
    "it. Judge strictly by what is inside it. Give each task a short "
    "label of 2-5 words, and set 'at' to the HH:MM timestamp of the first "
    "message of that task, copied from the transcript. "
    "If there are no real tasks, return an empty list. "
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
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pydantic import BaseModel

    class Task(BaseModel):
        label: str
        handled_by: str
        at: str

    class GroupTasks(BaseModel):
        tasks: List[Task]
        good: List[str]
        issues: List[str]

    ai = anthropic.Anthropic()

    todo = [g for g in groups if g['received'] > 0]
    progress = tg.send_message(
        'me', f'⏳ Shift review in progress… 0% (0/{len(todo)} chats)')
    last_pct = 0

    def ask(g):
        response = ai.messages.parse(
            model=REPORT_MODEL,
            max_tokens=4000,
            system=TASK_PROMPT,
            messages=[{
                "role": "user",
                "content": f"{'Direct message with' if g['is_user'] else 'Group'}: "
                           f"{g['name']}\n\nTranscript (times are Tashkent):\n"
                           + "\n".join(g['transcript']),
            }],
            output_format=GroupTasks,
        )
        return response.parsed_output

    results = []
    notes = []
    errors = 0
    done = 0
    with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as pool:
        futures = {pool.submit(ask, g): g for g in todo}
        for future in as_completed(futures):
            g = futures[future]
            done += 1
            try:
                out = future.result()
                for task in out.tasks:
                    results.append({'group': g['name'], 'label': task.label,
                                    'handled_by': task.handled_by, 'at': task.at,
                                    'is_user': g['is_user']})
                for kind, items in (('good', out.good), ('issue', out.issues)):
                    for text in items:
                        notes.append({'group': g['name'], 'kind': kind,
                                      'text': text})
            except Exception as e:
                errors += 1
                print(f"AI analysis failed for {g['name']}: {e}", file=sys.stderr)
            pct = done * 100 // len(todo)
            if pct != last_pct or done == len(todo):
                try:
                    tg.edit_message('me', progress,
                                    f'⏳ Shift review in progress… {pct}% '
                                    f'({done}/{len(todo)} chats)')
                    last_pct = pct
                except Exception:
                    pass
    try:
        tg.delete_messages('me', progress)
    except Exception:
        pass
    return results, notes, errors


def review_performance(notes, stats):
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


TEAM_LOWER = {n.lower() for n in TEAM.values()}
SALES_LOWER = ({n.lower() for n in SALES_NAMES}
               | {n.lower() for n in SALES_PEOPLE})
ACCOUNTING_LOWER = {n.lower() for n in ACCOUNTING_NAMES}
CLIENT_LOWER = ({n.lower() for n in CLIENT_NAMES}
                | {n.lower() for n in CLIENT_PEOPLE})


def span(book, key, n):
    a = book.get(key)
    if not a:
        return '', 0
    worked = max(len(a['hours']), 1)
    return (f" — {a['first']:%H:%M}–{a['last']:%H:%M}, "
            f"{worked}h active ({n / worked:.1f}/hr)"), worked


def leaderboard(tasks, activity, day_start, day_end):
    counts = {}
    off = {}
    for t in tasks:
        key = t['who']
        if key == 'ME':
            counts['You'] = counts.get('You', 0) + 1
        elif key.lower() in TEAM_LOWER:
            counts[key] = counts.get(key, 0) + 1
        elif (key != 'nobody' and key.lower() not in SALES_LOWER
              and key.lower() not in ACCOUNTING_LOWER
              and key.lower() not in CLIENT_LOWER):
            off[key] = off.get(key, 0) + 1
    rows = []
    for name, n in counts.items():
        detail, worked = span(activity, 'ME' if name == 'You' else name, n)
        rows.append({'name': name, 'tasks': n, 'rate': n / max(worked, 1),
                     'detail': detail})
    rows.sort(key=lambda r: (-r['rate'], -r['tasks']))
    lines = [f"🏆 Daily leaderboard — {day_start:%a %d %b %H:%M} to "
             f"{day_end:%a %d %b %H:%M}"]
    for i, r in enumerate(rows, start=1):
        mark = ' ⬅️ you' if r['name'] == 'You' else ''
        lines.append(f"{i}. {r['name']}: {r['tasks']}{r['detail']}{mark}")
    idle = [name for name in TEAM.values()
            if name not in counts and name in activity]
    if idle:
        lines.append(f"😴 On Telegram, no CS tasks: {', '.join(sorted(idle))}")
    if off:
        top = sorted(off.items(), key=lambda kv: -kv[1])[:6]
        lines.append(f"👤 Answered by people not on the roster: {sum(off.values())}"
                     f" — {', '.join(f'{k} ({v})' for k, v in top)}")
    return lines


def main():
    if len(sys.argv) == 3:
        start = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=TZ)
        end = datetime.fromisoformat(sys.argv[2]).replace(tzinfo=TZ)
    else:
        window = default_window()
        if window is None:
            print(f"no shift ended near {datetime.now(TZ):%a %d %b %H:%M}"
                  " — nothing to report")
            return
        start, end = window
    day_end = end
    day_start = end - timedelta(hours=DAY_HOURS)

    with TelegramClient(session, api_id, api_hash) as client:
        chats, activity, shift_activity = collect_dialogs(
            client, day_start.astimezone(UTC), day_end.astimezone(UTC),
            start.astimezone(UTC), end.astimezone(UTC))

        groups = [c for c in chats if not c['is_user']]
        dms = [c for c in chats if c['is_user'] and not c['internal']]
        active_groups = [c for c in groups if c['shift_received'] > 0]
        active_dms = [c for c in dms if c['shift_received'] > 0]
        total_received = sum(c['shift_received'] for c in chats)
        total_sent = sum(c['shift_sent'] for c in chats)

        lines = [
            f"📊 Shift report — {start.strftime('%a %d %b, %H:%M')}–{end.strftime('%H:%M')}",
            f"👥 Active groups: {len(active_groups)} · 👤 DMs: {len(active_dms)}",
        ]

        board = []
        if anthropic_key:
            todo = [c for c in chats if c['received'] > 0 and not c['internal']]
            tasks, notes, errors = analyze_tasks(client, todo)
            shift_chats = {c['name'] for c in chats
                           if c['shift_received'] or c['shift_sent']}
            for t in tasks:
                t['who'] = handler(t['handled_by'])
                t['when'] = parse_at(t.get('at'), day_start, day_end)
                t['in_shift'] = (start <= t['when'] < end if t['when']
                                 else t['group'] in shift_chats)
            shift_tasks = [t for t in tasks if t['in_shift']]
            by_me = [t for t in shift_tasks if t['who'] == 'ME']
            my_dms = [t for t in by_me if t['is_user']]
            team_tasks = [t for t in shift_tasks if t['who'].lower() in TEAM_LOWER]
            unanswered = [t for t in shift_tasks if t['who'] == 'nobody'
                          or t['who'].lower() in CLIENT_LOWER]
            outside = [t for t in shift_tasks
                       if t['who'].lower() in SALES_LOWER
                       or t['who'].lower() in ACCOUNTING_LOWER]

            def pct(n):
                return f"{round(n * 100 / len(shift_tasks))}%" if shift_tasks else "0%"

            detail, _ = span(shift_activity, 'ME', len(by_me))
            lines.append(f"📋 CS tasks: {len(shift_tasks)}")
            lines.append(f"✅ You: {len(by_me)} ({pct(len(by_me))}){detail}")
            lines.append(f"   ↳ {len(by_me) - len(my_dms)} in groups, "
                         f"{len(my_dms)} in DMs")
            if team_tasks:
                lines.append(f"👥 Your teammates, same hours: {len(team_tasks)} "
                             f"({pct(len(team_tasks))})")
            if outside:
                lines.append(f"ℹ️ Sales/accounting, not CS: {len(outside)}")
            lines.append(f"❌ No reply: {len(unanswered)} ({pct(len(unanswered))})")
            if unanswered:
                lines.append("No reply:")
                for t in unanswered:
                    tag = '👤 ' if t['is_user'] else ''
                    lines.append(f"   • {tag}{t['group']} — {t['label']}")
            if errors:
                lines.append(f"⚠️ {errors} chat(s) could not be analyzed")
            board = leaderboard(tasks, activity, day_start, day_end)
        else:
            answered = [c for c in active_groups + active_dms if c['shift_sent'] > 0]
            silent = [c for c in active_groups + active_dms if c['shift_sent'] == 0]
            lines.append(f"✅ You replied in: {len(answered)}")
            lines.append(f"❌ No reply: {len(silent)}")
            for c in sorted(silent, key=lambda c: -c['shift_received']):
                lines.append(f"   • {c['name']} ({c['shift_received']} msgs)")

        lines.append(f"💬 Messages: {total_received} received, {total_sent} sent by you")
        report = fit_telegram(lines)

        print(report)
        client.send_message('me', report)

        if board:
            board_text = fit_telegram(board)
            print(board_text)
            client.send_message('me', board_text)

        if anthropic_key and notes:
            stats = (f"{len(shift_tasks)} CS tasks in your shift, you handled "
                     f"{len(by_me)} ({len(my_dms)} of them in DMs), "
                     f"{len(unanswered)} left unanswered")
            try:
                review = fit_telegram(review_performance(notes, stats))
                print(review)
                client.send_message('me', review)
            except Exception as e:
                print(f"review failed: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()

"""Taskuary's general-work agent and its two views.

A general session uses either an already-authenticated CLI agent or an optional API connector and
owns a small, persistent conversation on the task.  The object implements the same
live-session surface as ``terminal.Term`` so assistant-ui and xterm are only renderers: queueing,
attachments, the Wall, browser association, and session lifetime all point at one session id.
"""
import base64, json, mimetypes, re, threading, time, uuid
from collections import deque
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import llm as llm_mod


USER_TYPE = 'assistant_user'
ASSISTANT_TYPE = 'assistant_agent'
# ``assistant`` was briefly written by Timeline discussions before those tasks were normalized
# to ``general``. Keep it as a read-compatible alias so existing discussions still open in the
# Assistant workspace without a data migration.
GENERAL_KINDS = {'general', 'research', 'marketing', 'triage', 'assistant'}
DOCK_TAG = 'assistant:dock'
SCROLLBACK = 200_000
MAX_CONTEXT = 24_000
MAX_REPLY_TOKENS = 2_000
DOCK_REPLY_TOKENS = 1_000       # a one-item walkthrough should answer quickly, not write an essay
WAIT_TURN = 240.0        # how long a new question waits behind the one being answered
REPORT_DRAFT_TOKENS = 1_200
REPORT_SKILL_CHARS = 2_400
_IMAGE_PATH = re.compile(r'(?P<path>(?:[A-Za-z]:\\|/)[^\r\n<>|"?*]+?\.(?:png|jpe?g|gif|webp))', re.I)

REPORT_DRAFT_SYSTEM = """You turn a completed assistant conversation into a REUSABLE scheduled-report instruction.
Return ONLY JSON: {"title":"short recurring report title","prompt":"standalone instruction"}.
The prompt must reproduce the useful work on every future run using CURRENT information. Preserve the goal,
sources or systems to inspect, important search/query steps, comparison criteria, caveats, provenance requirements,
and the desired report sections or output shape. Convert one-off dates into relative windows when appropriate.
Never copy secrets, access tokens, incidental debugging, old findings, or the previous answer as if it were current.
Do not mention this conversation. Do not add a schedule; the user chooses that separately."""


# The conversation IS the teaching surface. An assistant that quietly guesses at a customised
# ERP is worse than one that says "I do not know this number yet, let us prove it" - so the
# route from "I asked for a number" to "that number is now a certified metric" is written out here,
# in the prompt, rather than left for the owner to know about.
TEACH_ME = """TEACHING YOU A NUMBER
When the owner asks for a figure out of a customised system and there is no certified definition
for it, do not guess and do not present an unverified figure as the answer. Say what you do not
know yet, then walk this through with them:
1. Look at the REAL schema first, through whichever system holds the number - /api/tools/run with
   that system's own type. Never assume a column or a dimension exists because the name sounds
   right; ask the system what it actually has, custom fields included.
2. Propose a definition in plain words (what it means, what one row is), and a spec. It names its
   source and how to reduce the rows - {"source": "intacct", "object": "...", "value_field": "...",
   "aggregate": "sum", "filters": [[...]]} for an ERP object read, or {"source": "mssql", "query":
   "SELECT ..."} for a database. Use {scope}, {period_start} and {period_end} as placeholders; a
   ratio puts the denominator in "over" as a spec of its own. If a magnitude column carries no
   sign, name the column that does in "sign_field".
   Save it: POST /api/semantic/metrics {"Name": "...", "Label": "...", "Grain": "...",
   "Definition": "...", "Spec": {...}}.
3. Try it: POST /api/semantic/metrics/<id>/try {"scope": "...", "period": "2026-07"} - this records
   nothing, it just shows you the number so you can adjust the spec and try again.
4. ASK THE OWNER for a few cases and periods whose correct numbers they already know, and save
   each: POST /api/semantic/metrics/<id>/fixtures {"Scope": "...", "Period": "2026-07",
   "Expected": 123456.78, "Source": "where they got it"}. Never invent one of these.
5. Prove it: POST /api/semantic/metrics/<id>/check. It becomes verified only when every known
   number reconciles - and it will tell you which ones did not, so you can fix the spec and
   re-check. Write what you learned into the metric's Notes as you go.
Once verified it is frozen into a skill and every later run uses it, so this is worth doing
properly once rather than approximately every time."""


def handles(task: dict | None) -> bool:
    """Kinds that belong to the conversational agent rather than a coding or reply workflow."""
    return str((task or {}).get('Kind') or 'general').lower() in GENERAL_KINDS


def provider_options(store) -> list:
    """Every configured CLI login first, then optional API/local-model connectors."""
    out = []
    from .clis import KNOWN
    labels = {k['cmd']: k['label'] for k in KNOWN}
    for row in store.list_agents():
        try: cfg = json.loads(row.get('Config') or '{}')
        except ValueError: cfg = {}
        cmd = re.split(r'[\\/]', str(cfg.get('cmd') or row['Name']))[-1].lower().rsplit('.', 1)[0]
        label = labels.get(cmd) or cmd or row['Name']
        if row['Name'] != cmd: label += f" · {row['Name']}"
        out.append({'id': f"cli:{row['Name']}", 'pick': f"cli:{row['Name']}", 'type': 'cli',
                    'label': f'{label} (your CLI)', 'model': cfg.get('model') or ''})
    for row in store.list_connectors():
        if row.get('Type') not in llm_mod.AI_TYPES or not row.get('Active'): continue
        if not row.get('HasSecret') and row.get('Type') != 'ollama': continue
        try: cfg = json.loads(row.get('ConfigJson') or '{}')
        except ValueError: cfg = {}
        model = cfg.get('model') or cfg.get('deployment') or ''
        out.append({'id': f"connector:{row['ConnectorId']}", 'connector_id': row['ConnectorId'],
                    'pick': f"connector:{row['ConnectorId']}", 'type': row['Type'],
                    'label': f"{row.get('Name') or row['Type']} (API)", 'model': model})
    return out


def _selected(store, connector_id=None, model=None, pick=None) -> tuple[str, str, str]:
    options = provider_options(store)
    explicit = bool(pick or connector_id is not None or model)
    wanted = str(pick or (f'connector:{connector_id}' if connector_id else '')
                 or store.get_settings().get('assistant_ai') or '')
    if wanted and ':' not in wanted and wanted.isdigit(): wanted = f'connector:{wanted}'
    if not wanted:
        # API/local connectors answer in-process and are dramatically quicker than launching a
        # coding CLI. Prefer that native path for chat; the owner can persist a CLI choice when
        # they need its tools.
        native = next((o for o in options if o.get('type') != 'cli'), None)
        if native: wanted = native['pick']
        else:
            from . import agents as hub_agents
            wanted = f'cli:{hub_agents.default_agent(store)}'
    choice = next((o for o in options if o['pick'] == wanted), None) or (options[0] if options else None)
    if not choice: return '', '', model or ''
    saved_model = store.get_settings().get('assistant_model') if not explicit else ''
    return choice['pick'], choice['label'], model or saved_model or choice['model']


def chat_rows(store, tid: int) -> list:
    return [c for c in store.list_comments(tid) if c.get('ActorType') in (USER_TYPE, ASSISTANT_TYPE)]


def history(store, tid: int) -> list:
    return [{'id': f"comment-{c['CommentId']}",
             'role': 'assistant' if c.get('ActorType') == ASSISTANT_TYPE else 'user',
             'content': [{'type': 'text', 'text': c.get('Body') or ''}],
             'createdAt': c.get('CreatedAt')} for c in chat_rows(store, tid)]


def conversation_text(store, tid: int) -> str:
    """The durable assistant conversation as plain text, for end-of-session learning.

    General work has no terminal transcript: its real record is the typed conversation in task
    comments. Keeping this adapter here lets Social use the same conservative closeout question
    as coding sessions without inventing a second definition of durable company knowledge.
    """
    return '\n\n'.join(
        f"{'ASSISTANT' if c.get('ActorType') == ASSISTANT_TYPE else 'OWNER'}: {c.get('Body') or ''}"
        for c in chat_rows(store, tid))


def _cut(text, n):
    text = str(text or '')
    return text if len(text) <= n else text[:n] + f'\n[trimmed {len(text) - n:,} characters]'


def is_dock(task: dict | None) -> bool:
    """The global guide is stored like a chat, but is not work on the owner's task list."""
    return str((task or {}).get('SourceRef') or '') == DOCK_TAG


def dock_task(store, actor='owner') -> tuple[dict, bool]:
    """Return the one durable guide conversation shared by desktop and remote chat."""
    raw = store.get_settings().get('assistant_dock_task_id')
    task = store.get_task(int(raw)) if str(raw or '').isdigit() else None
    if task and is_dock(task) and task.get('Status') not in ('done', 'dropped'):
        return task, False
    tid = store.create_task({
        'Title': 'Taskuary guide',
        'Summary': 'An always-available walkthrough of the Timeline, outstanding work, reviews, and agent output.',
        'Kind': 'general', 'Status': 'open', 'Priority': 'normal',
        'Source': 'assistant', 'SourceRef': DOCK_TAG,
    }, actor)
    store.set_setting('assistant_dock_task_id', str(tid), actor)
    store.audit('task', tid, 'create_assistant_dock', actor)
    return store.get_task(tid), True


def dock_snapshot(store) -> str:
    """A compact, live map of the surfaces the hovering assistant is meant to explain.

    This is deliberately assembled by Taskuary instead of asking a model to infer the state of
    the app from an old conversation. It is refreshed for every turn, including resumed CLI
    conversations, so "what needs me now?" cannot answer from yesterday's task list.
    """
    from .store import task_ref

    def one_line(value, limit=280):
        return _cut(' '.join(str(value or '').split()), limit)

    tasks = [t for t in store.list_tasks()
             if t.get('Status') not in ('done', 'dropped') and not is_dock(t)][:30]
    reviews = store.list_reviews('pending')[:20]
    recent = store.feed(limit=30, days=14)
    needs = [r for r in recent if r.get('NeedsYou')][:12]

    lines = [f'WORKSPACE SNAPSHOT ({datetime.now().strftime("%Y-%m-%d %H:%M local")})']
    lines.append('\nNEEDS THE OWNER NOW')
    if not needs:
        lines.append('- Nothing in the recent Timeline is currently marked as needing the owner.')
    for r in needs:
        ref = task_ref(r['TaskId']) if r.get('TaskId') else f"message {r.get('MessageId')}"
        who = r.get('FromName') or r.get('FromEmail') or r.get('SourceName') or r.get('Channel')
        state = 'reply/review ready' if r.get('ReviewStatus') == 'pending' else (r.get('RouteReason') or 'needs attention')
        lines.append(f"- {ref} | {r.get('SentAt') or ''} | {who} | {one_line(r.get('Subject') or r.get('Title'))} | {one_line(state, 180)}")
        if r.get('Preview'): lines.append(f"  Message: {one_line(r.get('Preview'), 360)}")

    lines.append('\nACTIVE TASKS')
    if not tasks: lines.append('- No open, in-progress, or waiting tasks.')
    for t in tasks:
        run = f" | agent {t.get('RunAgent')}: {t.get('RunStatus')}" if t.get('RunAgent') else ''
        review = f" | review {t.get('ReviewStatus')}" if t.get('ReviewStatus') else ''
        lines.append(f"- {task_ref(t['TaskId'])} | {t.get('Status') or 'open'} | {t.get('Priority') or 'normal'} | {one_line(t.get('Title'))}{run}{review}")

    lines.append('\nPENDING REVIEW')
    if not reviews: lines.append('- Nothing is waiting in Review.')
    for r in reviews:
        ref = task_ref(r['TaskId']) if r.get('TaskId') else f"message {r.get('MessageId')}"
        lines.append(f"- {ref} | {r.get('Kind') or 'review'} | {one_line(r.get('Title') or r.get('Subject'))} | from {one_line(r.get('FromName') or r.get('FromEmail') or r.get('Channel'), 100)}")

    lines.append('\nRECENT TIMELINE')
    if not recent: lines.append('- The Timeline is empty in the current lookback window.')
    for r in recent[:18]:
        ref = task_ref(r['TaskId']) if r.get('TaskId') else f"message {r.get('MessageId')}"
        flag = ' | NEEDS OWNER' if r.get('NeedsYou') else ''
        lines.append(f"- {r.get('SentAt') or ''} | {r.get('Channel') or ''} | {ref} | {one_line(r.get('Subject') or r.get('Title'))}{flag}")

    lines.append('\nRECENT AGENT OUTPUT')
    output = []
    for t in store.list_tasks()[:25]:
        if is_dock(t): continue
        comments = store.list_comments(t['TaskId'])
        last = next((c for c in reversed(comments)
                     if c.get('ActorType') in ('agent', ASSISTANT_TYPE)
                     or str(c.get('Body') or '').startswith(('CODER REPORT', 'HANDOVER NOTE'))), None)
        if last:
            output.append(f"- {task_ref(t['TaskId'])} | {one_line(t.get('Title'), 160)} | {one_line(last.get('Body'), 460)}")
        if len(output) >= 10: break
    lines.extend(output or ['- No recent filed agent output.'])
    return '\n'.join(lines)


def _task_files(store, tid: int) -> list[dict]:
    """Files that arrived with the task's source messages, once each, in message order."""
    detail = store.task_detail(tid) or {}
    out, seen = [], set()
    for message in detail.get('messages') or []:
        for attachment in store.list_attachments(message['MessageId']):
            path = str(attachment.get('Path') or '').strip()
            key = path or f"attachment:{attachment.get('AttachmentId')}"
            if key in seen: continue
            seen.add(key); out.append(attachment)
    return out


# The chat is on the wall too (blackboard.py). It has no checkout, so it reads and writes the
# HOUSE lane - the notes with no repository behind them - and it can only write when a CLI is
# doing the thinking, because an API provider has no shell to run the command in.
POST_LINE = ('You can leave a line for the other agents and the owner: run '
             '`taskuary --note "..."` (add --kind working|note|blocked|ready|done) when you find '
             'something worth their time. One line. Only when it is genuinely worth someone else '
             'reading - a wall of chatter is a wall nobody reads.')
SOCIAL_LINE = ('Social is company memory, not a technical log. When you establish something still '
               'true next month about the business, its direction, customers, operations, people, '
               'decisions, or systems, file it with `taskuary --learned "<lasting fact>" --topic '
               '<company-area>`. Never post current activity or what you did; Tasks and Timeline '
               'already hold that. Use the ids in FROM SOCIAL to upvote, correct, or comment before '
               'posting the same fact again.')


def _turn_only(store, tid: int, text: str) -> str:
    """What to say to a CLI that already HAS this conversation: the new turn, and nothing it
    was told a minute ago. The system prompt still rides along - a resumed CLI keeps its
    history, not our instructions."""
    from .store import task_ref
    return f'{task_ref(tid)} - the owner says:\n\n{_cut(text, 8_000)}'


def _prompt(store, tid: int) -> tuple[str, str]:
    detail = store.task_detail(tid) or {}
    task = detail.get('task') or {}
    dock = is_dock(task)
    soul = _cut(store.doc('soul') or '', 4_000)
    counsel = _cut(store.doc('counsel') or '', 3_000)
    # What is CERTIFIED about the company's own systems. Without it the assistant writes a
    # plausible ERP query, gets a plausible number, and states it with the confidence of a
    # proved one - which is the failure the semantic layer exists to prevent.
    from . import semantic
    layer = semantic.block(store)
    system = (
        "You are the Taskuary general-work assistant. Help complete research, planning, writing, "
        "marketing, operational, and other non-coding work. The task and source material below are "
        "authoritative. Be direct and useful. Never claim you searched the web, opened a system, sent "
        "something, or changed a record unless a tool actually did it. Ask when a necessary fact is "
        "missing. Do not turn this into a coding task or instruct a coding CLI.\n\n"
        + (f'{layer}\n\n{TEACH_ME}\n\n' if layer else f'{TEACH_ME}\n\n')
        + f"OPERATOR RULES\n{_cut(soul, 4_000)}\n\nASSISTANT STYLE\n{_cut(counsel, 3_000)}"
    )
    if dock:
        system += (
            "\n\nHOVERING GUIDE\nThis conversation is the owner's always-available Taskuary guide. "
            "Use the fresh workspace snapshot to walk them through what arrived, what needs a decision, "
            "what agents produced, and what to do next. Prioritize; do not merely recite every row. "
            "When you mention a task, link it as [TQ-0001](#task=1), using its real id. The buttons above "
            "the chat open Timeline, Tasks, and Review. You may explain or perform actions only through "
            "tools you actually have; approval and sending remain the owner's actions.\n\n"
            "WALKTHROUGH MODE\nWhen the owner asks to walk through everything, needs-attention work, "
            "email, tasks, reviews, or agent output, run a turn-by-turn review. On each response: "
            "cover exactly ONE unresolved item; give the concrete context and your recommended action; "
            "then ask the single question needed to decide or advance it and STOP. Wait for the owner's "
            "next message before moving to another item. Treat their answer as applying to the item you "
            "just asked about. Briefly acknowledge it, use available tools when they explicitly authorize "
            "a safe action, then present the next unresolved item. Do not dump a list upfront. Say clearly "
            "when the walkthrough is complete."
        )
    sources = []
    for m in (detail.get('messages') or [])[-12:]:
        who = m.get('FromName') or m.get('FromEmail') or m.get('SourceName') or m.get('Channel') or 'source'
        files = store.list_attachments(m['MessageId'])
        file_line = ('\nATTACHMENTS: ' + '; '.join(
            str(a.get('Name') or 'file') + (f" ({a.get('Path')})" if a.get('Path') else '')
            for a in files[:8])) if files else ''
        sources.append(f"FROM {who} ({m.get('SentAt') or ''})\n{_cut(m.get('BodyText'), 3_000)}{file_line}")
    turns = []
    for c in chat_rows(store, tid)[-30:]:
        role = 'ASSISTANT' if c.get('ActorType') == ASSISTANT_TYPE else 'USER'
        turns.append(f"{role}: {_cut(c.get('Body'), 4_000)}")
    # Social is company memory, not coding trivia. The general assistant needs the same relevant
    # facts as a coding session: how the business works, decisions, ownership, people and traps.
    # API-backed assistants cannot run taskuary's voting commands, so hand them the facts without
    # advertising controls they do not have; CLI sessions receive the action line separately.
    from . import handbook
    social_query = ' '.join([
        str(task.get('Title') or ''), str(task.get('Summary') or ''),
        *[str(m.get('BodyText') or '') for m in (detail.get('messages') or [])[-12:]],
        *[str(c.get('Body') or '') for c in chat_rows(store, tid)[-12:]],
    ])
    social = handbook.block(store, social_query[:8_000], actions=False) if handbook.enabled(store) else ''
    # the chat is an agent too, so it is on the wall - the HOUSE lane, the notes with no
    # checkout behind them, which is where it and the owner leave things for everybody
    from . import blackboard as bb, selfclose
    wall = bb.chat_text(store)
    # ...and how this task ENDS. Only where an ending means something: a task somebody wrote in
    # about has an answer owed, and closing it drafts that answer. A task the owner opened to
    # think out loud in has nobody waiting, so it stays open until they say otherwise.
    if sources and selfclose.mode(store) != 'off': system = system + '\n\n' + selfclose.CHAT_LINE
    head = (f"TASK {detail.get('ref') or tid}\nTITLE: {task.get('Title') or ''}\n"
            f"SUMMARY: {task.get('Summary') or ''}\nSTATUS: {task.get('Status') or ''}\n\n"
            + (dock_snapshot(store) + '\n\n' if dock else '')
            + (wall + '\n\n' if wall else '')
            + (social.strip() + '\n\n' if social else ''))
    tail = "\n\nRespond to the last USER turn. Do not repeat the task context."
    # The question sits at the END, so the end is what must survive the budget: the oldest turns go
    # first, then the oldest source material. _cut(user) kept the head and dropped exactly the
    # conversation and the instruction, so a task seeded from eight long mails answered the mails
    # and not the owner (audit 2026-09-02).
    while len(turns) > 1 and len(head) + len('\n\n'.join(turns)) + len(tail) > MAX_CONTEXT: turns.pop(0)
    conv = "CONVERSATION\n" + '\n\n'.join(turns) + tail
    src, room = '\n\n'.join(sources), MAX_CONTEXT - len(head) - len(conv) - 20
    if len(src) > room: src = ('[older source material trimmed]\n\n' + src[-room:]) if room > 400 else ''
    return system, head + (f"SOURCE MATERIAL\n{src}\n\n" if src else '') + conv


def _fallback_report_draft(store, tid: int) -> dict:
    """A useful editable draft even when the selected brain is unavailable or returns prose."""
    detail = store.task_detail(tid) or {}
    task = detail.get('task') or {}
    asks = [str(c.get('Body') or '').strip() for c in chat_rows(store, tid)
            if c.get('ActorType') == USER_TYPE and str(c.get('Body') or '').strip()]
    title = str(task.get('Title') or 'Recurring assistant report').strip()[:100]
    prompt = ('Repeat this work using current information at every run. Verify claims with the available tools, '
              'include dates and source links, distinguish confirmed facts from unknowns, and end with the practical '
              'changes or follow-ups that matter now.')
    if asks:
        prompt += '\n\nThe original requests to preserve:\n' + '\n'.join(f'- {_cut(a, 1800)}' for a in asks[-8:])
    return {'title': title, 'prompt': prompt[:12000]}


def report_draft(store, tid: int, pick=None, model=None) -> dict:
    """Condense a task conversation into the prompt of an ``agent`` report.

    This is deliberately a separate model call: it neither adds a chat turn nor reruns the work.
    The deterministic fallback remains editable, so a formatting failure cannot block scheduling.
    """
    task = store.get_task(tid)
    if not task: raise ValueError(f'no task {tid}')
    if not handles(task): raise ValueError('only assistant discussions can become recurring reports here')
    rows = chat_rows(store, tid)
    if not any(c.get('ActorType') == ASSISTANT_TYPE for c in rows):
        raise ValueError('finish at least one assistant exchange before turning it into a report')
    fallback = _fallback_report_draft(store, tid)
    chosen, _provider, chosen_model = _selected(store, model=model, pick=pick)
    try:
        brain = llm_mod.build_llm(store, pick=chosen or None, model=chosen_model or None)
    except Exception as e:
        logger.warning(f'assistant report draft could not select a model for task {tid}: {e}')
        return fallback
    if not brain: return fallback
    conversation = '\n\n'.join(
        f"{'ASSISTANT' if c.get('ActorType') == ASSISTANT_TYPE else 'USER'}: {_cut(c.get('Body'), 3500)}"
        for c in rows[-24:])
    user = (f"TASK TITLE: {task.get('Title') or ''}\nTASK SUMMARY: {task.get('Summary') or ''}\n\n"
            f"CONVERSATION\n{_cut(conversation, 20000)}")
    try:
        raw = str(brain(REPORT_DRAFT_SYSTEM, user, max_tokens=REPORT_DRAFT_TOKENS) or '').strip()
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.I)
        try: made = json.loads(clean)
        except (ValueError, TypeError):
            block = re.search(r'\{.*\}', clean, flags=re.S)
            made = json.loads(block.group(0)) if block else {}
        title, prompt = str(made.get('title') or '').strip(), str(made.get('prompt') or '').strip()
        if not prompt: return fallback
        return {'title': (title or fallback['title'])[:100], 'prompt': prompt[:12000]}
    except Exception as e:
        logger.warning(f'assistant report draft fell back for task {tid}: {e}')
        return fallback


def save_report_skill(tid: int, title: str, prompt: str) -> str:
    """Persist a long generated workflow as a Taskuary-owned, provider-neutral skill.

    ``reports.run_agent`` expands this file into the CLI prompt, so the same recurring skill
    works with Claude, Codex, Gemini, or another configured CLI instead of being installed into
    one provider's private skill directory.
    """
    from . import config
    slug = re.sub(r'[^a-z0-9]+', '-', str(title or '').lower()).strip('-')[:52] or 'recurring-report'
    slug = f'{slug}-tq-{tid}'
    folder = config.home() / 'skills' / slug
    folder.mkdir(parents=True, exist_ok=True)
    text = (f'---\nname: {slug}\ndescription: Reusable workflow promoted from Taskuary task {tid}.\n---\n\n'
            f'# {title.strip()}\n\n{prompt.strip()}\n')
    (folder / 'SKILL.md').write_text(text, encoding='utf-8')
    return slug


def _images(paths) -> list:
    out = []
    for raw in paths or []:
        try:
            p = Path(str(raw)).resolve()
            ct = mimetypes.guess_type(str(p))[0] or ''
            if ct not in llm_mod.VISION_TYPES or not p.is_file() or p.stat().st_size > llm_mod.VISION_BYTES: continue
            out.append((ct, base64.b64encode(p.read_bytes()).decode()))
        except OSError: continue
        if len(out) >= llm_mod.VISION_MAX: break
    return out


class GeneralSession:
    """A connector-backed conversation with the live-session contract used by the terminal."""
    mode = 'assistant'
    argv = []
    cwd = ''
    label = 'Taskuary assistant'
    agent = 'assistant'
    cli = 'taskuary'

    def __init__(self, store, task_id: int, connector_id=None, model=None, pick=None):
        self.sid = uuid.uuid4().hex[:12]
        self.store, self.task_id = store, task_id
        self.pick, self.provider, self.model = _selected(store, connector_id, model, pick)
        self.started = datetime.now().isoformat(sep=' ', timespec='seconds')
        self.buf, self.n, self.ended, self.last = deque(), 0, None, time.time()
        self.subs, self.taps = [], []
        self.alive, self.busy = True, False
        self.rows, self.cols = 32, 110
        self._input, self._lock = '', threading.Lock()
        self._cancel = None                  # the stop switch for the answer being written now
        self.cli_sid = ''                    # the CLI's OWN conversation, resumed turn to turn
        # The browser that asked the question is only one VIEW of this session. Keep the
        # structured tool/progress stream here as well as sending it down that browser's
        # request, so leaving this task and coming back does not turn visible work into a blank
        # assistant message. This is intentionally the latest turn only; the final prose is
        # already durable in task comments, while the trace explains how that answer was made.
        self.trace, self.trace_revision = [], 0
        from .witness import Witness
        self.witness = Witness()
        self._restore_terminal()

    def _append(self, text):
        if not text: return
        self.buf.append(text); self.n += len(text)
        while self.n > SCROLLBACK and len(self.buf) > 1: self.n -= len(self.buf.popleft())

    def _emit(self, text):
        self._append(text)
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, text)
            except RuntimeError: pass
        for fn in list(self.taps):
            try: fn(text)
            except Exception as e: logger.debug(f'assistant session tap failed: {e}')

    def _restore_terminal(self):
        title = (self.store.get_task(self.task_id) or {}).get('Title') or f'Task {self.task_id}'
        self._append(f'\x1b[1;36mTaskuary assistant\x1b[0m  {self.provider or "no AI connector"} {self.model}\r\n'
                     f'\x1b[2m{title}\x1b[0m\r\n\r\n')
        for row in chat_rows(self.store, self.task_id):
            if row.get('ActorType') == USER_TYPE:
                self._append(f'\x1b[1;34myou>\x1b[0m {row.get("Body") or ""}\r\n')
            else:
                self._append(f'\x1b[1;32massistant>\x1b[0m {row.get("Body") or ""}\r\n\r\n')
        self._append('\x1b[1;34myou>\x1b[0m ')

    def subscribe(self, loop, q): self.subs.append((loop, q))
    def unsubscribe(self, q): self.subs = [(loop, item) for loop, item in self.subs if item is not q]
    def tap(self, fn): self.taps.append(fn)
    def untap(self, fn): self.taps = [item for item in self.taps if item is not fn]
    def scrollback(self): return ''.join(self.buf)
    def resize(self, rows, cols): self.rows, self.cols = int(rows), int(cols)
    def idle(self): return round(time.time() - self.last, 1)
    def files(self): return []
    def phase(self): return 'working' if self.busy else 'parked'
    def waiting(self): return self.alive and not self.busy
    def tail(self, n=3):
        from .terminal import plain
        return [line for line in plain(self.scrollback()[-8000:]).splitlines() if line.strip()][-n:]

    @staticmethod
    def _trace_detail(kind, detail):
        """Bound provider output before it becomes part of every assistant-state response."""
        if not isinstance(detail, dict): return str(detail or '')[:1600]
        clean = dict(detail)
        if 'result' in clean: clean['result'] = str(clean.get('result') or '')[:6000]
        if 'args' in clean:
            try:
                raw = json.dumps(clean['args'], default=str)
                if len(raw) > 6000: clean['args'] = {'summary': raw[:6000] + '…'}
            except (TypeError, ValueError): clean['args'] = {'summary': str(clean['args'])[:6000]}
        return clean

    def _remember_trace(self, kind, name='', detail=None):
        event = {'type': str(kind or ''), 'name': str(name or ''),
                 'detail': self._trace_detail(kind, detail)}
        self.trace.append(event)
        if len(self.trace) > 100: self.trace = self.trace[-100:]
        self.trace_revision += 1

    def _take(self, wait: float, cancel=None) -> bool:
        """Wait our turn to speak.

        THREE things can be answering in one session: this chat, the xterm composer over the
        same conversation, and the waiting room delivering queued notes on its own thread.
        Refusing the newcomer ("the assistant is already working") threw the question away -
        and before a failed run said anything at all, that reached the owner as silence: the
        third message in a conversation simply never got a reply (the wall, 2026-08-31).

        A person asked a second question while you are mid-sentence expects to be answered
        next, not ignored. So: queue. In slices, so a browser that gives up stops waiting too.
        """
        end = time.time() + max(0.0, wait)
        while True:
            if self._lock.acquire(timeout=0.25): return True
            if cancel is not None and cancel.is_set(): return False
            if time.time() >= end: return False

    def write(self, data):
        """Make xterm a second composer for the same conversation."""
        if not self.alive: return
        for ch in str(data or ''):
            if ch in ('\r', '\n'):
                prompt, self._input = self._input.strip(), ''
                if prompt:
                    self._emit('\r\n')
                    threading.Thread(target=self.send_prompt, args=(prompt,), kwargs={'echo': False}, daemon=True).start()
                continue
            if ch in ('\x08', '\x7f'):
                if self._input:
                    self._input = self._input[:-1]; self._emit('\b \b')
                continue
            if ch == '\x03':
                self._emit('^C\r\n\x1b[1;34myou>\x1b[0m '); self._input = ''
                continue
            if ch >= ' ':
                self._input += ch; self._emit(ch)

    def send_prompt(self, text: str, attachments=None, connector_id=None, model=None, echo=True,
                    pick=None, trace=None, cancel=None, as_owner=True) -> str:
        """`as_owner=False` is an instruction to the assistant that the OWNER did not say - used to
        make it open a conversation (server._assistant_opens). It is not written to the history and
        not echoed, because putting words in the owner's mouth in their own transcript is a lie the
        rest of this product is built to avoid; the assistant's answer is recorded as normal."""
        text = str(text or '').strip()
        if not text: raise ValueError('empty message')
        if not self.alive: raise RuntimeError('this assistant session has ended - reload the page and ask again')
        if not self._take(WAIT_TURN, cancel):
            raise RuntimeError(f'the assistant has been answering the previous question for over '
                               f'{int(WAIT_TURN)}s - something is stuck. Press stop, or reload the page.')
        self.busy, self.last = True, time.time()
        self._cancel = cancel if cancel is not None else threading.Event()
        cancel = self._cancel
        self.trace = [{'type': 'start', 'session': {'provider': self.provider, 'model': self.model}}]
        self.trace_revision += 1
        try:
            if connector_id is not None or model or pick:
                self.pick, self.provider, self.model = _selected(self.store, connector_id, model, pick)
            if not self.pick:
                raise RuntimeError('connect a CLI agent or an AI provider before starting general work')
            if echo and as_owner: self._emit(f'\x1b[1;34myou>\x1b[0m {text}\r\n')
            if as_owner: self.store.add_comment(self.task_id, 'owner', USER_TYPE, text)
            system, user = _prompt(self.store, self.task_id)
            if not as_owner: user = f'{user}\n\n{text}'      # the instruction, carried but not attributed
            # only a CLI-backed chat can post to the wall: an API provider has no shell to
            # run the command in, and telling it about a command it cannot run is a lie
            if self.pick.startswith('cli:'):
                system = f'{system}\n\n{POST_LINE}'
                from . import handbook
                if handbook.enabled(self.store): system = f'{system}\n\n{SOCIAL_LINE}'
            source_paths = [a.get('Path') for a in _task_files(self.store, self.task_id) if a.get('Path')]
            paths = list(dict.fromkeys(source_paths + list(attachments or [])
                                       + [m.group('path') for m in _IMAGE_PATH.finditer(text)]))
            def visible(kind, name, detail):
                self._remember_trace(kind, name, detail)
                if trace: trace(kind, name, detail)
                if kind == 'tool_call':
                    target = next(iter((detail.get('args') or {}).values()), '') if isinstance(detail, dict) else ''
                    self._emit(f'\x1b[33mtool>\x1b[0m {name} {str(target)[:180]}\r\n')
                elif kind == 'tool_result' and isinstance(detail, dict) and detail.get('is_error'):
                    self._emit(f'\x1b[31mtool error>\x1b[0m {str(detail.get("result") or "")[:240]}\r\n')
            # Continue the CLI's own conversation rather than starting a new one and re-typing
            # the transcript into it. Every turn used to be a fresh `claude -p` carrying the
            # whole chat again - slower, dearer, and silently forgetful once the conversation
            # outgrew MAX_CONTEXT. Resumed, the CLI still has what it read and did last turn,
            # so the turn itself is all that has to be said.
            brain = llm_mod.build_llm(self.store, pick=self.pick, model=self.model or None,
                                      trace=visible, cancel=cancel, resume=self.cli_sid or None)
            if not brain: raise RuntimeError('the selected AI connector is unavailable')
            if self.cli_sid:
                # an opening turn's 'turn' IS the instruction, which the history never saw
                user = _turn_only(self.store, self.task_id, text) if as_owner else text
                if is_dock(self.store.get_task(self.task_id)):
                    user += f'\n\n{dock_snapshot(self.store)}'
            # Paths are harmless context to an API brain and essential if its CLI backup takes
            # over after a quota failure. The source message already names its files too; this
            # line also carries images attached directly in the composer.
            if paths:
                user += '\n\nATTACHED FILES (read these when relevant)\n' + '\n'.join(str(Path(p).resolve()) for p in paths)
            try:
                limit = DOCK_REPLY_TOKENS if is_dock(self.store.get_task(self.task_id)) else MAX_REPLY_TOKENS
                reply = str(brain(system, user, max_tokens=limit, images=_images(paths)) or '').strip()
            except Exception:
                # the CLI could not pick that conversation back up (it was restarted, its history
                # was cleared, the id aged out). Start a fresh one and say the whole thing, once.
                if not self.cli_sid or (cancel is not None and cancel.is_set()): raise
                logger.info(f'assistant could not resume {self.cli_sid} on task {self.task_id}; starting a new one')
                self.cli_sid = ''
                system, user = _prompt(self.store, self.task_id)
                brain = llm_mod.build_llm(self.store, pick=self.pick, model=self.model or None,
                                          trace=visible, cancel=cancel)
                limit = DOCK_REPLY_TOKENS if is_dock(self.store.get_task(self.task_id)) else MAX_REPLY_TOKENS
                reply = str(brain(system, user, max_tokens=limit, images=_images(paths)) or '').strip()
            self.cli_sid = getattr(brain, 'session_id', '') or self.cli_sid
            actual = getattr(brain, 'last_pick', '')
            if actual and actual != self.pick:
                choice = next((o for o in provider_options(self.store) if o['pick'] == actual), None)
                self.pick = actual
                if choice:
                    self.provider, self.model = choice['label'], choice.get('model') or ''
            if not reply: raise RuntimeError('the model returned an empty response')
            # the assistant's own "and that's the job done" (selfclose.CHAT_LINE). The marker is a
            # signal to Taskuary, not prose for the owner, so it comes out of what gets filed and
            # what gets shown - the sentence after it becomes the closing comment.
            from . import selfclose
            reply, closing = selfclose.chat_marker(reply)
            reply = reply or (closing or '')
            self.store.add_comment(self.task_id, 'assistant', ASSISTANT_TYPE, reply)
            self.store.audit('task', self.task_id, 'assistant_reply', 'assistant', 'agent',
                             {'provider': self.provider, 'model': self.model, 'chars': len(reply)})
            self._emit(f'\x1b[1;32massistant>\x1b[0m {reply}\r\n\r\n')
            # AFTER the turn is filed, and off this thread: closing runs coder.wrap, which closes
            # this very session - doing it inline would kill the pty from inside its own answer.
            # A close marker only has meaning for source-backed work: there is an inbound
            # message/event waiting for a completed answer. A conversation the owner opened
            # manually is still a conversation after one answer. Enforce that boundary here,
            # even if a resumed model remembers an older close instruction and emits the marker.
            has_source = bool((self.store.task_detail(self.task_id) or {}).get('messages'))
            if closing is not None and has_source:
                threading.Timer(0.1, self._close_out, args=(closing,)).start()
            return reply
        except Exception as e:
            self._remember_trace('error', 'assistant', {'result': str(e), 'is_error': True})
            self._emit(f'\x1b[1;31merror>\x1b[0m {e}\r\n\r\n')
            raise
        finally:
            self.busy, self.last = False, time.time()
            self._cancel = None
            self._emit('\x1b[1;34myou>\x1b[0m ')
            self._lock.release()

    def _close_out(self, summary: str):
        """The chat said the work was done. Same ending as a coding session's: the task closes,
        the conversation stays on the task as its record, and the reply to whoever asked is
        drafted for the owner to approve."""
        from . import selfclose
        try: selfclose.declare(self.store, self.task_id, summary, 'assistant')
        except Exception as e: logger.warning(f'assistant self-close failed on task {self.task_id}: {e}')

    def stop(self) -> bool:
        """Stop the answer being written now - the STOP BUTTON, and nothing else.

        Closing the browser stream used to do this, which meant leaving the Board tab, hitting
        refresh, or any remount killed an answer that was seconds from finishing - and the reply
        was never written, so it looked as though the assistant had ignored the question (the
        owner, 2026-08-31). Walking away is not stopping: the run finishes on its own thread and
        the reply is filed on the task, where the chat picks it up when you come back."""
        c = self._cancel
        if c is None: return False
        c.set()
        return True

    def close(self):
        # Coding sessions already ask this at wrap. General sessions used to bypass that branch,
        # so everything the assistant learned about the business disappeared with the chat even
        # though Social explicitly holds more than technical facts. A session boundary is the
        # conservative time to ask once; duplicate close calls are no-ops, and learning can never
        # prevent the session itself from closing.
        if self.alive:
            from . import handbook
            transcript = conversation_text(self.store, self.task_id)
            if transcript and handbook.enabled(self.store):
                try:
                    brain = llm_mod.build_llm(self.store, pick=self.pick or None, model=self.model or None)
                    handbook.learn_from_session(self.store, self.task_id, transcript, 'assistant', llm=brain)
                except Exception as e:
                    logger.debug(f'handbook: assistant conversation {self.task_id} learned nothing - {e}')
        self.alive, self.ended = False, time.time()
        self._emit('\r\n\x1b[2msession closed\x1b[0m\r\n')
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError: pass

    def info(self, tail=0):
        from . import browserview
        return {'sid': self.sid, 'label': self.label, 'cwd': '', 'taskId': self.task_id,
                'agent': self.agent, 'cli': 'taskuary', 'mode': self.mode, 'alive': self.alive,
                'busy': self.busy, 'trace': list(self.trace), 'trace_revision': self.trace_revision,
                'started': self.started, 'idle': self.idle(), 'phase': self.phase(),
                'waiting': self.waiting(), 'cmd': f'{self.provider or "AI connector"} {self.model}'.strip(),
                'provider': self.provider, 'pick': self.pick,
                'connector_id': int(self.pick.split(':', 1)[1]) if self.pick.startswith('connector:') else None,
                'model': self.model, 'files': [],
                'browser': browserview.state(self.sid), 'work': None,
                **({'tail': self.tail(tail)} if tail else {})}


def session_for(tid: int):
    from . import terminal
    return next((s for s in list(terminal.SESSIONS.values())
                 if s.task_id == tid and s.alive and getattr(s, 'mode', '') == 'assistant'), None)


def drop_session(tid: int) -> int:
    """Forget every finished session on this task. A session that has ENDED is not a session:
    left in the registry it kept the task occupied, and the next question was refused with
    "this task already has a different live session"."""
    from . import terminal
    gone = [sid for sid, t in list(terminal.SESSIONS.items())
            if getattr(t, 'task_id', None) == tid and not t.alive]
    for sid in gone: terminal.SESSIONS.pop(sid, None)
    return len(gone)


def start_session(store, tid: int, connector_id=None, model=None, actor='owner', pick=None) -> GeneralSession:
    from . import terminal
    task = store.get_task(tid)
    if not task: raise ValueError(f'no task {tid}')
    if not handles(task): raise ValueError('assistant view is for general, research, marketing, and triage tasks')
    existing = session_for(tid)
    if existing:
        if connector_id is not None or model or pick:
            existing.pick, existing.provider, existing.model = _selected(store, connector_id, model, pick)
        return existing
    # A session that has ENDED is not a session. It used to sit in the registry keeping the task
    # occupied, so the next question got "this task already has a different live session" and,
    # because a failed run said nothing at all, looked like the assistant ignoring you.
    drop_session(tid)
    other = next((s for s in list(terminal.SESSIONS.values()) if s.task_id == tid and s.alive), None)
    if other: raise ValueError(f'this task already has a live {getattr(other, "agent", "") or "terminal"} '
                               'session - close it (the ✕ on its pane) and ask again here')
    session = GeneralSession(store, tid, connector_id, model, pick)
    terminal.SESSIONS[session.sid] = session
    # the chat is work too: a general task started from the Tasks tab gets its Timeline row
    # here, stamped at the moment the session opened (ownwork.ensure is a no-op when a message
    # already speaks for the task, which is every task that arrived from outside)
    from . import ownwork
    ownwork.ensure(store, tid, session.started, 'the assistant started here', actor)
    if task.get('Status') == 'open': store.update_task(tid, {'Status': 'in_progress'}, actor)
    return session

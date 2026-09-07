"""Taskuary, the assistant you talk to: one item at a time, out of the pipe, in conversation.

This is deliberately the LIGHT brain. It does no work and no routing - the funnel (funnel.py)
decides what comes next, triage already decided what each thing is, the coding agents and the
responder do the doing. What is left for this voice is what a good assistant does at your desk:
"next one - Dana's asking for the corrected file; the reply is drafted, want to read it?" -
two sentences, and then the button under them acts. So it runs on the fast API model the owner
chose for the assistant (general._selected prefers a native connector over launching a CLI),
with a small prompt and a small budget, and when no model is connected at all it still speaks:
the facts on the item are the fallback sentence.

The conversation is the same durable one the floating guide and the WhatsApp doorway use - the
dock task's comments (general.dock_task) - so the chats list is every dock conversation there
has been, and "New chat" archives one and resets the walk. Which card goes under a message is
recorded with the message (a marker the renderer reads and the model never sees), so a reload
draws the same conversation, cards included.

Cards are chosen by CODE from the item's kind, never by the model. The model may only add a
multiple choice at the end of a line (OPTIONS: a | b | c) when a decision has clear choices and
no button covers it; the choice comes back as the owner's next words.
"""
import contextvars, json, re, threading
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from loguru import logger

from . import funnel, general, llm as llm_mod, store as store_mod, toolcatalog
from .assistant import _ts
from . import operations
from .store import task_ref

MAX_TOKENS, TURNS, FACT_CHARS = 380, 10, 1_600
READ_ROUNDS = 2          # a look-up may lead to one more; never an open-ended crawl
NEWLINE = chr(10)
# Introducing an item is a FACT - who wrote, what was done, what you need to do - and the pipe knows all
# three. So 'next' asks no model: it is instant, and it can never describe the wrong item (the owner,
# 2026-09-03: "should not even be an AI call, just go to next task"). The model speaks only when the
# owner types something that is not already a decision. Flip this for a model-written introduction.
# The introduction of the item on the table is the FACTS, and it is instant. Making it the model's
# (PW-153) put a model call in front of every Next: measured 2026-09-07 at 1419ms for a trivial 20-token
# call on this owner's fast lane, and the real one carries the item's facts, the pile summary and the
# conversation at max_tokens=380 - which is the five seconds the owner timed ("next still take 5
# seconds?"). It is the same thing they asked for on 2026-09-03: "should not even be an AI call, just go
# to next task". Flip this back only behind a non-blocking intro - facts first, the written sentence
# streamed in after - never as a blocking call on the walk.
INTRO_AI = False
MARK = '<!-- tq:card '
_MARK = re.compile(r'\s*<!-- tq:card (\{.*?\}) -->\s*$', re.S)
_OPTIONS = re.compile(r'\n?\s*OPTIONS:\s*(.+?)\s*$', re.I | re.S)
_DECIDE = re.compile(r'\n?\s*DECIDE:\s*([a-z_]+)(?::\s*(.*?))?(?:\s+ON:\s*(.+?))?\s*$', re.I | re.S)
# A CALL names an operation out of the registry itself (toolcatalog) instead of a verb out of prose.
# It exists for the targets a verb cannot say: a SET, described rather than listed.
_CALL = re.compile(r'\n?\s*CALL:\s*(\{.*\})\s*$', re.I | re.S)
# what the owner can decide about the thing on the table - each is a button the card already has
VERBS = ('reply', 'approve', 'setting', 'not_ours', 'not_ours_remember', 'not_ours_sender', 'block_sender', 'remember', 'coder', 'regular_agent', 'mine', 'close', 'stop_agent',
         'rerun', 'setup', 'clear', 'split', 'done', 'later', 'skip', 'next', 'answer_agent', 'redraft', 'forward', 'archive',
         'confirm', 'cancel', 'none')
# The action words offered INSIDE the assistant's own line, and what each one reads as. The vocabulary is
# CODE's and it is fixed (the owner, 2026-09-07: "make it hardcoded, meaning add inline in the chat words
# that map to actions"); only which of them fits the thing on the table is decided per item, from its kind.
# The model still reads free text - it just never invents a button. Every word here maps to a verb the cards
# and the typed sentence already run, so a chip, a button and a sentence are one road.
CHIP_WORDS = {'approve': 'Send the reply', 'redraft': 'Redraft it', 'reply': 'Reply', 'coder': 'Hand it to a coding agent',
              'regular_agent': 'Hand it to an agent', 'mine': 'Put it on my list', 'not_ours': 'Not ours',
              'not_ours_sender': 'Ignore this sender', 'block_sender': 'Block them in Settings',
              'archive': 'Archive it', 'close': 'Close the task',
              'done': 'Handled', 'later': 'Later', 'skip': 'Tomorrow', 'next': 'Next', 'answer_agent': 'Answer it',
              'stop_agent': 'Stop the agent', 'rerun': 'Run it again', 'split': 'Split it in two',
              'prep': 'Prep me', 'followup': 'Draft a follow-up'}
# What the word will actually DO, on hover - written where the difference matters. "Ignore this
# sender" and "Block them in Settings" are one line apart and not remotely the same act.
CHIP_HINTS = {'not_ours_sender': 'Their mail keeps arriving and stays readable - triage learns to file it',
              'block_sender': 'An exclusion rule in Settings: their mail never reaches triage again, and what already arrived leaves the Timeline. Reversible.',
              'not_ours': 'File just this one - nothing is remembered',
              'coder': 'A coding agent, in a repository', 'regular_agent': 'A non-coding agent - reading, checking, drafting',
              'mine': "Your own list - no agent starts", 'next': 'Read it and move on'}
# per kind, in the order they are offered. `next` is last on every one of them: moving on is always available,
# and it is the one word that is never a decision about the thing itself.
CHIPS = {'review': ('approve', 'redraft', 'not_ours', 'next'), 'action': ('approve', 'not_ours', 'next'),
         'agent': ('answer_agent', 'stop_agent', 'next'), 'meeting': ('prep', 'regular_agent', 'next'),
         'report': ('rerun', 'regular_agent', 'next'), 'agentdone': ('close', 'reply', 'next'),
         'wrapup': ('close', 'next'), 'idea': ('followup', 'mine', 'done', 'next'), 'task': ('close', 'next'),
         'asked': ('reply', 'regular_agent', 'coder', 'mine', 'not_ours', 'not_ours_sender', 'next'),
         'todo': ('reply', 'regular_agent', 'coder', 'mine', 'not_ours', 'not_ours_sender', 'next'),
         'fyi': ('not_ours', 'not_ours_sender', 'block_sender', 'mine', 'next'),
         'fyis': ('done', 'not_ours_sender', 'block_sender', 'next')}
# THE CONTRACT is the part code reads: two line shapes and the verb vocabulary behind the card's buttons.
# How to behave is COUNSEL's - the owner's document, not this file (PW-248/256). Removing prose here
# removed no safeguard: verbs are validated in parse_decision, targets and freshness in operations.
CONTRACT_HEAD = (
    "THE CONTRACT (code reads your answer)\n"
    "You are speaking to {owner} in the chat on the Assistant tab. When a decision has two to four clear "
    "choices and no button covers them, end with one final line exactly like: OPTIONS: first choice | second choice. "
    "Otherwise no options line.\n"
    "The action words under your line are the owner's buttons and they are already chosen for this item - never "
    "list them, and never end a line with an offer to do something. When you cannot tell which of them the owner's "
    "words mean, say which two you are choosing between and ask - one short question, no DECIDE line. Guessing is "
    "worse than asking.\n")
# The verb vocabulary is the machine half and it is the SAME wherever the turn is read: an item settled
# from the phone is settled on the desk, because both go through parse_decision and the same operations.
DECIDE_RULE = (
    "When the owner has DECIDED about an item, end with one final line exactly like DECIDE: <verb> where verb is one of: "
    "reply (a reply to write - the gist after a colon: DECIDE: reply: tell Kishan it is not owned here), approve (send the "
    "drafted reply as it stands), redraft (write the draft again - the change after a colon), coder (hand it to the coding "
    "agent - everything wanted after a colon, in the owner's words), regular_agent (hand it to a non-coding agent), mine "
    "(they will do it themselves), not_ours (file this one), not_ours_remember (file this kind from now on), "
    "not_ours_sender (triage files everything from this sender from now on; their mail still arrives), block_sender (an exclusion rule in Settings - their mail never reaches triage again and what already arrived leaves the Timeline; the bigger hammer, only when they ask for a RULE), archive, close (close the task), done (handled), later, skip "
    "(tomorrow), next (move on), remember (a fact to keep - after a colon), setup (a walk-through with the assistant - the "
    "request after a colon), setting (a switch for the owner to approve), split (two jobs in one arrival), stop_agent (end "
    "the running agent), answer_agent (the answer for the parked agent - after a colon), rerun (run the report again), "
    "forward (send it on - to whom after a colon), clear (clear these from the pipe), confirm (their yes to the card "
    "already waiting on it - only when one is), cancel (their no to it). A decision about a DIFFERENT item than "
    "the one on the table ends the DECIDE line with ON: and the words that name it: DECIDE: not_ours ON: payroll portal outage.")
CONTRACT = CONTRACT_HEAD + DECIDE_RULE
SYSTEM = CONTRACT      # the old name, for one release

# The same walk, read in a phone chat. There are no cards there and no action words under the line, so
# the choices have to BE the message - remote_assistant appends them, and this tells the voice to write
# for a screen that has nothing else on it. Only the delivery changes: the pipe, the verbs and the
# proposals are the desk's, so an item settled from the phone is settled everywhere.
PHONE_CONTRACT = (
    "THE CONTRACT (code reads your answer)\n"
    "You are speaking to {owner} in their private chat on their phone, not at the Taskuary desktop. They "
    "cannot see a card, a button, a draft or a link here - never tell them to click, open, tap or read one "
    "as if it were in front of them. Say the sender, the subject, why it matters and what you would do, in "
    "no more than four short sentences, and never more than one item at a time.\n"
    "The choices are added under your line by code from the item itself. Do not list them, do not invent "
    "one, and never end a line with an offer to do something. When you cannot tell which of them the "
    "owner's words mean, say which two you are choosing between and ask - one short question, no DECIDE "
    "line. Guessing is worse than asking.\n" + DECIDE_RULE)

DESK, PHONE = 'desk', 'phone'
# Where this turn will be READ. Ambient, not an argument: every path into the voice (surface, say, the
# opening line) would otherwise carry a parameter that decides nothing except how the words are shaped.
DELIVERY = contextvars.ContextVar('taskuary_delivery', default=DESK)


@contextmanager
def delivering(where: str):
    token = DELIVERY.set(where if where in (DESK, PHONE) else DESK)
    try: yield
    finally: DELIVERY.reset(token)

OPENING = (
    "Open the conversation for the day. Say 'let's go through what we have today' in your own words, then in two or three "
    "sentences: what is on the calendar, what agents have in hand, how much is waiting and of what kind (from THE DAY below). "
    "Do not walk through any item yet - the owner starts that with a button. Under 90 words. No options line.")

# what the assistant says when a decision is carried out - the fact of what happens now, never a claim
RECEIPTS = {'reply': "I'll draft that - it lands below for your yes.", 'approve': 'Sending it as drafted. Moving on.',
            'not_ours': "Not ours, then - filed. Moving on.", 'not_ours_remember': "Filed, and remembered: this kind goes straight past you from now on.",
            'not_ours_sender': "Noted: that sender is noise - everything from them files itself from now on. Moving on.",
            'remember': "Remembered. Moving on.", 'coder': "Sent off to the coding agent - watch it on the Board if you like; I'll bring its findings back here when it's done. Meanwhile, the next thing.",
            'regular_agent': "Sent off to the regular agent - I'll bring its answer back here when it is done. Meanwhile, the next thing.",
            'clear': 'Cleared. Moving on.',
            'mine': "On your list. Moving on.", 'close': 'Closing the task. Moving on.', 'rerun': "Queued the rerun - it lands back in the pipe when it's done. Moving on.",
            'setup': "I'll walk you through it - opening it as a conversation with the assistant, no code, nothing built. "
                     "Say send it to the coding agent if it turns out something has to be built.",
            'answer_agent': "Passing that to the agent - it reads it when it next stops.",
            'redraft': "Writing it again with that - the new draft lands below for your yes.",
            'archive': 'Archived - off the pipe and closed, nothing deleted. Moving on.',
            'done': 'Done. Moving on.', 'later': "Pushed back a few hours.", 'skip': 'Tomorrow, then.', 'next': 'Next.'}

ALL_DONE = ("That's everything for now. The pipe is empty - nothing is waiting on you. "
            "Ask me anything, or I'll speak up when something lands.")


# the quick gear per CLI when the agent profile names no light_model: the assistant's turns are two
# sentences, and the coding model is the wrong tool for them (Connections > AI CLI agents sets it)
LIGHT_DEFAULT = {'claude': 'haiku', 'codex': 'effort:low', 'gemini': 'gemini-2.5-flash'}
SID_KEY = 'concierge_cli_sid'          # the CLI's own conversation, resumed turn to turn (per dock task)
CURRENT_KEY = 'assistant_current'      # what is on the table, per dock task - persisted, validated on restore (PW-162)


AI_KEY, MODEL_KEY = 'concierge_ai', 'concierge_model'   # this page's own choice - the old dock's assistant_ai stays the dock's and WhatsApp's

def pick(store) -> str:
    """Which brain speaks: the owner's choice on the Assistant tab; else the default CLI agent (its
    tools are what make this a full assistant); else the first API connector."""
    s = store.get_settings()
    chosen = str(s.get(AI_KEY) or '').strip()
    if chosen: return chosen
    from . import agents as hub_agents
    if store.list_agents():
        try: return f'cli:{hub_agents.default_agent(store)}'
        except Exception as e: logger.debug(f'concierge: no default agent - {e}')
    return general._selected(store)[0]


def is_cli(store) -> bool: return pick(store).startswith('cli:')


def brain(store, trace=None, cancel=None, resume=None, fast=False):
    """The voice. A CLI runs with its tools, in its own scratch folder (never a checkout), on its light
    gear, and picks its last conversation back up; an API connector answers in-process.

    `fast` is for the turns that need no tools - introducing an item, the opening brief: an API
    connector when one is configured (a second, not a launch), else the CLI with its tools OFF so it
    cannot wander off exploring before it answers (a plain 'next' took 20 seconds, 2026-09-03)."""
    from . import demo
    if demo.enabled(): return demo.brain()
    p = pick(store)
    if not p: return None
    if fast and p.startswith('cli:'):
        native = general._selected(store)[0] if any(o.get('type') != 'cli' for o in general.provider_options(store)) else ''
        if native and not native.startswith('cli:'):
            try: return llm_mod.build_llm(store, pick=native)
            except Exception as e: logger.debug(f'concierge: fast lane connector unavailable - {e}')
    try:
        if p.startswith('cli:'):
            from . import config
            name = p[4:]
            row = store.get_agent(name) or {}
            try: prof = json.loads(row.get('Config') or '{}')
            except ValueError: prof = {}
            cli = re.split(r'[\\/]', str(prof.get('cmd') or name))[-1].lower().rsplit('.', 1)[0]
            model = str(store.get_settings().get(MODEL_KEY) or '').strip() or None
            if not model and not prof.get('light_model'):
                light = LIGHT_DEFAULT.get(cli)
                if light and not light.startswith('effort:'): model = light
                elif light: prof['light_model'] = light
            folder = config.home() / 'assistant'; folder.mkdir(parents=True, exist_ok=True)
            cwd = None if fast else str(folder)                  # no cwd = make_cli_llm's read-only gear: no tools, no permission bypass
            if prof.get('light_model') and not (row.get('Config') or '').find('light_model') >= 0:
                # the default gear rides on a copy of the profile, never written back to the row
                store_get = store.get_agent
                store.get_agent = lambda n, _r=row, _p=prof: (_r | {'Config': json.dumps(_p)}) if n == name else store_get(n)
                try: return llm_mod.make_cli_llm(store, name, model, cwd=cwd, trace=trace, cancel=cancel, resume=resume)
                finally: store.get_agent = store_get
            return llm_mod.make_cli_llm(store, name, model, cwd=cwd, trace=trace, cancel=cancel, resume=resume)
        return llm_mod.build_llm(store, pick=p, model=str(store.get_settings().get(MODEL_KEY) or '').strip() or None, trace=trace, cancel=cancel)
    except Exception as e:
        logger.debug(f'concierge: no brain - {e}'); return None


def _sid(store, tid: int) -> str: return str(store.get_settings().get(f'{SID_KEY}:{tid}') or '')


def current_key(store, tid: int) -> str: return str(store.get_settings().get(f'{CURRENT_KEY}:{tid}') or '')


def set_current(store, tid: int, key: str | None, actor: str = 'assistant'):
    """The thing on the table, written down as it is put there (or taken away) - not inferred later."""
    if current_key(store, tid) != (key or ''): store.set_setting(f'{CURRENT_KEY}:{tid}', key or '', actor)


def restore_current(store, tid: int) -> dict | None:
    """The persisted Current, validated against the pile as it stands (PW-162): the item as it is now when it
    is still unread and still there; otherwise the key is cleared and nothing is chosen in its place."""
    key = current_key(store, tid)
    if not key: return None
    try: item = funnel.batch_item(store, key) if key.startswith('fyis:') else funnel.next_item(store, key, include_surfaced=True)
    except Exception as e:
        logger.warning(f'concierge: could not validate the current item {key} - {e}'); item = None
    # ...and "still there" is not enough. A mail row on a closed task leaves the pile (funnel._feed_skip),
    # but own work reaches it through the processing inventory, which keeps a finished task as a READ
    # fyi row - so Current went on holding a task done twenty minutes ago and the assistant kept
    # offering to hand it to an agent (TQ-0420). The test is OVER, never "read": an item the assistant
    # puts in the chat is read, and clearing on that would empty the table as soon as it was set.
    over = item and item.get('tid') and (store.get_task(item['tid']) or {}).get('Status') in ('done', 'dropped')
    if not item or item.get('settling') or (over and item.get('lane') != 'approve'):
        set_current(store, tid, None)
        return None
    card = card_for(item) | {'presentation_revision': item.get('presentation_revision')}
    if item.get('kind') == 'fyis': card['items'] = [card_for(i) for i in item.get('items') or []]   # the handful, entry by entry
    return card
def _remember_sid(store, tid: int, llm):
    sid = getattr(llm, 'session_id', '') or ''
    if sid and sid != _sid(store, tid): store.set_setting(f'{SID_KEY}:{tid}', sid, 'assistant')


def tools_block(store) -> str:
    """What a CLI brain may DO - Taskuary's own API, from a shell, with the agent token. Reading and
    rerunning are the assistant's; sending, approving and pushing stay the owner's buttons (guard.py
    refuses them to this token anyway)."""
    from . import config
    cfg = config.load()['server']
    tok = cfg.get('agent_token') or ''
    base = f"http://127.0.0.1:{cfg.get('port', 7787)}/api"
    return (f"WHAT YOU CAN DO YOURSELF (you have a shell)\nTaskuary's API is at {base}; every call carries the header "
            f"X-Taskuary-Token: {tok}. Use curl. You may: read a message GET /messages/<mid>; read a task GET /tasks/<tid> "
            "(its comments hold what agents found); RERUN A REPORT POST /reports/<source_id>/rerun (the answer carries the "
            "new report's text - show it to the owner in your reply, as markdown); run a data tool POST /tools/run "
            "{\"type\": ..., ...} the way the item's facts describe; leave a line for the agents with `taskuary --note \"...\"`. "
            "You may publish hard-earned discoveries and developed ideas to the Hub, and comment or vote there. "
            "You may NOT send, approve, dismiss, push, or change operational records: those are the owner's buttons under your words, and "
            "the API refuses them to you. When the owner asks for something doable from this list, DO it and report what came "
            "back - never say you cannot. When it needs a checkout or a long job, say so and name the coding agent. NEVER use your "
            "own task, todo or plan tools, and never create tasks, files or records yourself: a decision of the owner's is carried out by "
            "Taskuary from your DECIDE line, and you report it only after the receipt says it happened.")


def _counsel(store) -> str:
    """The chat reads the whole document (counsel.load restores a blank one, audited)."""
    from . import counsel
    return counsel.for_chat(store)


def _owner(store) -> str:
    try: return store.owner().get('owner_first') or 'the owner'
    except Exception: return 'the owner'


# the owner's own words on a thread: 'context' is their reply read back out of Sent (how a mail
# client's reply arrives), 'out' is one Taskuary sent. Either way the ball is in the other court.
def _own_word(m: dict) -> bool: return str(m.get('Status') or '') == 'context' or str(m.get('Direction') or 'in') == 'out'


def _cut(s, n=FACT_CHARS):
    s = str(s or '')
    return s if len(s) <= n else s[:n] + ' […]'


def task_now(store, tid: int) -> str:
    """The task AS IT IS NOW - never as it was when the item entered the pipe. Status, who has it (a live
    session working, parked, or asking; a headless run), what the agent last said and when, whether a draft
    waits. The assistant reads this before every turn about a task, so 'the agent stopped' is never said of
    an agent that picked the work back up a minute ago."""
    t = store.get_task(tid) or {}
    if not t: return ''
    from . import waitroom
    live = next((x for x in _live(store) if x.get('taskId') == tid), None)
    if live:
        tail = [str(l).strip() for l in (live.get('tail') or []) if str(l).strip()]
        waiting = live.get('waiting') if live.get('waiting') is not None else (live.get('idle') or 0) >= 45
        who = live.get('agent') or live.get('label') or 'an agent'
        state = (f"{who} is PARKED and ASKING you: {tail[-1][:200]}" if waiting and waitroom.looks_like_question(tail) else
                 f"{who} is PARKED at its prompt, waiting on you (idle {int(live.get('idle') or 0)}s)" if waiting else
                 f"{who} is WORKING right now (idle {int(live.get('idle') or 0)}s) - nothing for the owner until it stops")
    elif t.get('RunStatus') == 'running': state = f"{t.get('RunAgent') or 'an agent'} is running headless - nothing for the owner until it stops"
    else: state = 'no agent on it right now'
    rv = store.pending_review(tid)
    last = next((c for c in reversed(store.list_comments(tid)) if c.get('ActorType') in ('agent', 'assistant_agent')), None)
    lines = [f"TASK NOW: {task_ref(tid)} [{t.get('Status')}, {t.get('Kind')}] {t.get('Title') or ''} - {state}"]
    sent = store.sent_reply(task_id=tid)
    if sent: lines.append(f"  YOU ALREADY REPLIED ({str(sent.get('DecidedAt') or sent.get('CreatedAt') or '')[:16]}): {_cut(sent.get('FinalText') or sent.get('DraftText'), 240)} - do not suggest answering again")
    if rv: lines.append(f"  a {rv.get('Kind')} waits for the owner's yes (rv{rv['ReviewId']})")
    if last: lines.append(f"  the agent last said ({str(last.get('CreatedAt') or '')[:16]}): {_cut(last.get('Body'), 300)}")
    if t.get('Status') in ('done', 'dropped'): lines.append(f"  CLOSED {str(t.get('ClosedAt') or t.get('UpdatedAt') or '')[:16]} - do not present it as open work")
    return '\n'.join(lines)


def facts(store, item: dict) -> str:
    """What the model is handed about ONE item: the item's own words, then the body, the draft,
    the agent's screen or the meeting, whichever it has. Bounded, so a turn stays fast."""
    if not item: return '(no item on the table - the owner is just talking)'
    lines = [f"ITEM [{item['kind']} / {funnel.LANE_WORDS.get(item['lane'], (item['lane'],))[0]}]: {item['title']}",
             f"from: {item.get('who') or '?'} | when: {item.get('when') or '?'} | why it is here: {item.get('why') or ''}"]
    if item.get('tid'):
        now = task_now(store, item['tid'])
        if now: lines.append(now)
    task_chain = []
    task_messages = []
    if item.get('tid'):
        try: task_chain = store.list_messages(item['tid'])
        except Exception: task_chain = []
        # ``context`` is supporting conversation triage supplied to the task. The messages triage
        # actually combined into the task are every non-context row, and must be presented as one
        # unit instead of letting the newest MessageId pretend it is the whole job.
        task_messages = [m for m in task_chain if str(m.get('Status') or '') != 'context']
    grouped = len(task_messages) > 1
    if grouped:
        from .triage import strip_boilerplate
        combined = []
        for m in task_messages:
            body = strip_boilerplate(str(m.get('BodyText') or ''))
            combined.append(f"  {str(m.get('SentAt') or '')[:16]} "
                            f"{'YOU' if _own_word(m) else (m.get('FromName') or m.get('FromEmail') or '?')}: "
                            f"{_cut(body, 800)}")
        lines.append(f"TRIAGE COMBINED THESE {len(task_messages)} MESSAGES INTO THIS ONE TASK (oldest first). "
                     "Present and decide them together; do not turn them into separate queue items:\n"
                     + _cut('\n'.join(combined), 6_000))
    elif item.get('mid'):
        m = store.get_message(item['mid']) or {}
        from .triage import strip_boilerplate
        body = strip_boilerplate(str(m.get('BodyText') or item.get('preview') or ''))
        if body: lines.append(f"what they wrote:\n{_cut(body, 400 if item['kind'] == 'report' else FACT_CHARS)}")   # a report's body is for the button, not the intro
        sent = store.sent_reply(message_id=item['mid']) if not item.get('tid') else None
        if sent: lines.append(f"YOU ALREADY REPLIED ({str(sent.get('DecidedAt') or sent.get('CreatedAt') or '')[:16]}): {_cut(sent.get('FinalText') or sent.get('DraftText'), 240)}")
        try:
            chain = task_chain or (store.thread_messages(conversation_id=m.get('ConversationId'), subject=m.get('Subject'), limit=8)
                                   if m.get('ConversationId') else [])
        except Exception: chain = []
        # the WHOLE thread, newest included. It used to drop the last message (chain[:-1]), on the
        # assumption that the last one was the item itself - but the newest message on a live thread
        # is usually the owner's own answer, sent from their mail client and read back out of Sent,
        # and dropping it is why the assistant said "I don't see your reply" to a reply it had
        # (the owner, 2026-09-03: "it can't see response??").
        rest = [c for c in chain if c.get('MessageId') != item['mid']][-4:]
        if rest:
            lines.append('the rest of the thread (oldest first):\n' + '\n'.join(
                f"  {str(c.get('SentAt') or '')[:16]} {'YOU' if _own_word(c) else (c.get('FromName') or c.get('FromEmail') or '?')}: {_cut(c.get('BodyText'), 200)}"
                for c in rest))
    # The owner's side is normally a context row and therefore deliberately absent from the
    # triaged bundle above. It still decides whether a reply is already taken care of.
    chain = task_chain if grouped else (locals().get('chain') or [])
    mine = [c for c in chain if _own_word(c)]
    if mine:
        lines.append(f"YOU ALREADY ANSWERED ON THIS THREAD ({str(mine[-1].get('SentAt') or '')[:16]}, from your own mail client): "
                     f"{_cut(mine[-1].get('BodyText'), 240)} - say so as a fact; never say you cannot see the owner's reply")
    if item.get('summary') and item['kind'] in ('review', 'action'): lines.append(f"THE AGENT FOUND: {item['summary']}")
    if item.get('rid'):
        rv = store.get_review(item['rid']) or {}
        d = str(rv.get('DraftText') or '').strip()
        lines.append(f"THE DRAFT (shown to the owner in the card):\n{_cut(d, 1200)}" if d else 'no draft yet - the card offers Draft with AI')
        if item.get('stale'):
            lines.append('IMPORTANT: newer messages arrived after that draft. It is stale and must be redrafted before sending; do not recommend approving it.')
    if item['kind'] == 'agent':
        lines.append('the agent\'s last lines:\n' + '\n'.join(item.get('tail') or ['(nothing captured)']))
    if item['kind'] == 'meeting':
        e = item.get('event') or {}
        lines.append(f"meeting {e.get('start')} - {e.get('end') or ''}" + (f" with {', '.join(e.get('who') or [])}" if e.get('who') else '')
                     + (f" | where: {e.get('where')}" if e.get('where') else '') + (f" | the invite says: {_cut(e.get('about'), 400)}" if e.get('about') else ''))
    if item['kind'] == 'agentdone': lines.append(f"the agent's summary: {item.get('summary') or ''}")
    if item['kind'] == 'wrapup': lines.append(f"WRAP-UP: the reply went out (\"{item.get('sent') or ''}\")" + (f"; the agent finished: {item['summary']}" if item.get('summary') else '') + ' - the task is still open; ask whether to close it')
    if item['kind'] == 'report' and item.get('source_id'):
        runs = store.report_runs(item['source_id'], 3)
        if runs: lines.append('LAST RUNS: ' + '; '.join(f"{str(r.get('at') or '')[:16]} {'FAILED: ' + _cut(r.get('error'), 200) if r.get('failed') else 'ok'}" for r in runs))
    if item['kind'] == 'idea' and item.get('action', {}).get('chat'):
        lines.append('what was said about it before: ' + ' // '.join(f"{t.get('role')}: {_cut(t.get('text'), 200)}" for t in item['action']['chat'][-4:]))
    return '\n'.join(lines)


def parse_call(text: str) -> tuple[str, dict | None]:
    """The model's CALL line, off the end of its answer: {'kind', 'params'} or None. Validated against
    operations.KINDS here, so an invented kind never reaches a handler - it is simply not a call."""
    m = _CALL.search(text or '')
    if not m: return (text or '').strip(), None
    from . import toolcatalog
    try: got = json.loads(m.group(1))
    except ValueError:
        logger.info('concierge: a CALL line was not JSON - ignoring it'); return text[:m.start()].strip(), None
    kind, params = str(got.get('kind') or ''), got.get('params') or {}
    if not isinstance(params, dict): params = {}
    why = toolcatalog.valid(kind, params)
    if why:
        logger.info(f'concierge: refusing that CALL - {why}')
        return text[:m.start()].strip(), None
    return text[:m.start()].strip(), {'kind': kind, 'params': params}


def parse_decision(text: str) -> tuple[str, dict | None]:
    """The model's DECIDE line, off the end of its answer: {'verb', 'text'} or None."""
    m = _DECIDE.search(text or '')
    if not m: return (text or '').strip(), None
    verb = m.group(1).lower()
    if verb not in VERBS or verb == 'none': return text[:m.start()].strip(), None
    d = {'verb': verb, 'text': (m.group(2) or '').strip()}
    if m.group(3): d['on'] = m.group(3).strip()          # the decision is about ANOTHER item, named (PW-121)
    return text[:m.start()].strip(), d


# "can you ask the assistant to look into that server?" is an ORDER wearing a question mark. The
# polite opener plus the trailing '?' used to veto every verb, so the request fell through to
# lookup() and came back as a description of the mail it was about (the owner, 2026-09-03).
_POLITE = re.compile(r"^\s*(?:(?:please|pls|plz)\s+)?(?:(?:can|could|would|will)\s+(?:you|u)|do you mind|would you mind|i'?d like you to|i want you to|i need you to|let'?s)\s+(?:please\s+)?(?:to\s+)?|^\s*(?:please|pls|plz)\s+", re.I)

# Being told we have a fact wrong is not an instruction to carry out. "it says the report failed,
# which is wrong" ended as a bare "Next." - the one answer that says the correction was not heard
# (the owner, 2026-09-03: "that's not what a assistant should do").
_CORRECTION = re.compile(r"\b(that'?s (wrong|not right|incorrect|not true)|(that|this|it) is (wrong|not right|incorrect)|"
                         r"no,? it (did|does|is|was)n'?t|not true|you'?re wrong|wrong again|it did ?n'?t fail|"
                         # ...and the shapes it arrives in: "that's not a fail, it says all clear?"
                         r"(that|this|it)'?s not (a |an )?(fail|failure|error|problem|issue)|not a fail|"
                         r"it (says|said) (it ?'?s )?(all clear|clear|ok|okay|fine|success|passed)|did ?n'?t (fail|error|break)|"
                         r"(i|we) (already|just) (told|said)|(i|you) (got|have) (that|it) wrong|which is wrong|is not wrong)\b", re.I)


# what the card's primary button does, said as a word. Anything not here has no yes-able action.
ASSENT_VERB = {'review': 'approve', 'action': 'approve', 'agent': 'answer_agent', 'idea': 'followup'}


def assent_verb(item: dict | None) -> str | None:
    """"yes" / "go ahead" on the thing on the table: the verb its own card would run."""
    if not item: return None
    if item.get('kind') == 'review' and not item.get('draft'): return 'reply'   # nothing drafted yet: write one
    return ASSENT_VERB.get(item.get('kind'))


# courtesy and filler carry no subject: "done, thanks" names nothing
_FILLER = {'thanks', 'thank', 'cheers', 'great', 'good', 'fine', 'perfect', 'please', 'sorry', 'nice',
           'right', 'sure', 'really', 'actually', 'maybe', 'probably', 'definitely', 'anyway', 'though',
           # ...and the words that stand IN for a subject rather than being one: "for this kind",
           # "that sort of thing" name nothing at all
           'kind', 'kinds', 'sort', 'sorts', 'type', 'types', 'thing', 'things', 'stuff', 'item', 'items',
           'way', 'ways', 'case', 'cases', 'matter', 'work', 'job', 'jobs', 'note', 'notes', 'task', 'tasks',
           'message', 'messages', 'mail', 'email', 'emails', 'reply', 'replies', 'issue', 'issues', 'problem', 'problems'}

def _pile_hit(store, extra: list, item: dict) -> str | None:
    """The item in the PIPE those words are about. lookup() scores over the whole timeline and wants
    half the words; two words of a five-word clause ("the payroll portal outage - facilities handle
    that") never reach that, and the thing they name is sitting two rows down."""
    from .routing import tokens
    best, hits = None, 0
    try: items = funnel.pile(store)['items']
    except Exception: return None
    for i in items:
        if i.get('key') == item.get('key'): continue
        hay = set(tokens(f"{i.get('who') or ''} {i.get('title') or ''} {i.get('preview') or ''}"))
        n = sum(1 for w in extra if w in hay or any(h.startswith(w) for h in hay))
        if n > hits: best, hits = i, n
    return best['key'] if hits >= 2 else None


# What a card must HAVE for a verb to be carried out on it - the same map the page checks. The
# receipt used to go out before anyone knew, so "Sending it as drafted. Moving on." and "I could
# not do that from here" landed in the chat one after the other (2026-09-03).
# A HAND-OFF is not in here: an agent needs a BRIEF, not a message. Requiring a `mid` refused "create an
# agent to research these three tools" on a meeting - the one item kind that never has one - with "there is
# nothing to hand to a regular agent on this one" (the owner, 2026-09-07). propose_for already builds those
# through task.create_from_text from the item's facts and the owner's words.
NEEDS = {'reply': 'mid', 'approve': 'rid', 'redraft': 'rid', 'not_ours': 'mid', 'not_ours_remember': 'mid',
         'not_ours_sender': 'mid', 'block_sender': 'mid', 'mine': 'mid', 'forward': 'mid', 'archive': 'mid',
         'rerun': 'source_id', 'close': 'tid', 'answer_agent': 'tid', 'split': 'key'}
SAYS_VERB = {'approve': 'approve', 'redraft': 'redraft', 'not_ours': 'file', 'not_ours_remember': 'file',
             'not_ours_sender': 'file', 'block_sender': 'write an exclusion rule for', 'coder': 'hand to a coding agent', 'regular_agent': 'hand to a regular agent', 'mine': 'put on your list', 'forward': 'forward',
             'archive': 'archive', 'rerun': 'rerun', 'close': 'close', 'answer_agent': 'answer', 'reply': 'reply to',
             'split': 'split'}

def no_agent(store) -> str:
    """The coding agent the dispatch would use, when there is not one - so "Sent off to the coding
    agent" is never said in front of a 422 (2026-09-03)."""
    try:
        from . import agents as hub_agents
        want = hub_agents.default_agent(store)
        return '' if store.get_agent(want) else (want or 'the coding agent')
    except Exception: return ''


def cannot(item: dict | None, verb: str, store=None) -> str:
    """Why this card cannot carry that verb - '' when it can. Always phrased "nothing to <verb>",
    because the honest line is the only line: no receipt goes out in front of it."""
    if not item: return ''
    what = f"{item.get('ref') or item.get('title') or 'this one'}"
    if verb == 'answer_agent' and item.get('kind') != 'agent':
        return f"There is nothing to answer on this one - no agent is parked on {what}. Say stop the agent, or open the Board."
    if verb == 'approve' and item.get('kind') in ('review', 'action') and not item.get('draft') and item.get('kind') == 'review':
        # approving an empty draft SENT NOTHING and closed the task anyway (2026-09-03)
        return (f"There is nothing to approve yet - no reply has been drafted on {what}. Say reply and what to tell them, "
                'and it lands here for your yes.')
    if verb == 'coder' and store is not None:
        gone = no_agent(store)
        if gone: return (f"There is nothing to hand it to - {gone} is not set up on this machine. "
                         'Connections → AI CLI agents, and then say it again.')
    need = NEEDS.get(verb)
    if need and not item.get(need):
        return (f"There is nothing to {SAYS_VERB.get(verb, verb)} on this one - {what} is "
                f"{item.get('why') or funnel.LANE_WORDS.get(item.get('lane'), ('waiting',))[0]}. Open it if you want its own buttons.")
    return ''


def walk_chips(left) -> list:
    """With nothing on the table there is nothing to DECIDE about - only the walk. Offered on the opening
    line and on every "nothing here" answer while the pipe still holds something, so Next is always
    somewhere in the conversation: the strip over the composer that used to carry it is gone, and the
    welcome block that offers the walk disappears the moment the first line is written."""
    return [{'verb': 'next', 'label': CHIP_WORDS['next']}] if left else []


def chips_for(store, item: dict | None, first: str = None) -> list:
    """The action words to put under the assistant's line: this kind's vocabulary, minus anything this
    particular item cannot actually carry. An offered chip is a chip that works - which is the whole
    point of gating them through cannot() rather than letting the model name them.

    `first` promotes one verb to the front: what the model said it would do becomes the button that
    does it, instead of a sentence that promised something nothing carried out (the owner, 2026-09-07:
    "It says x, does something else")."""
    if not item: return []
    verbs = list(CHIPS.get(item.get('kind')) or ('next',))
    if first and first in CHIP_WORDS and first != 'next':
        verbs = [first] + [v for v in verbs if v != first]
    out = []
    for v in verbs:
        # the two that are the page's own actions rather than proposals, so NEEDS does not describe them:
        # prep wants the invite it is preparing for, a follow-up wants something to follow up ON
        if v == 'prep' and not item.get('event'): continue
        if v == 'followup' and not (item.get('idea') or (item.get('action') or {}).get('mid')): continue
        if v != 'next' and cannot(item, v, store): continue
        out.append({'verb': v, 'label': CHIP_WORDS[v], **({'hint': CHIP_HINTS[v]} if v in CHIP_HINTS else {})})
    return out


def parse_options(text: str) -> tuple[str, list]:
    m = _OPTIONS.search(text or '')
    if not m: return (text or '').strip(), []
    opts = [o.strip() for o in re.split(r'\s*\|\s*', m.group(1)) if o.strip()][:4]
    return (text[:m.start()].strip(), opts if len(opts) >= 2 else [])


def _verdict_why(item: dict) -> str:
    """Triage's own reason, with the verdict word it opens with trimmed off - "triage filed it as
    fyi - triage: fyi - an automated notification" says it twice (the owner, 2026-09-04: "ask we
    processed as fyi because of x")."""
    w = (item.get('why') or '').strip()
    for pre in ('triage: fyi -', 'triage: fyi', 'triage:'):
        if w.lower().startswith(pre):
            w = w[len(pre):].lstrip(' -·')
            break
    return f' - {w}' if w else ''


def fallback(item: dict | None, opening: bool, pile_items: list = None) -> str:
    """No model: the facts in the same three beats - where from, what was done, what you need to do."""
    if not item:
        if opening: return ALL_DONE
        # ...and with nothing on the table, the facts are WHAT IS WAITING. "No AI is connected" was
        # the answer to every typed word in a fresh install - true, and no use to anybody (2026-09-03).
        left = [i for i in (pile_items or []) if not i.get('settling')]
        if left:
            return (f"{funnel.summary(left)} Say next and I'll take you through them, or name the one you mean. "
                    '(No AI is connected, so I speak in facts rather than sentences - Connections → AI.)')
        return ALL_DONE
    if opening and item.get('mid') and item['kind'] in ('review', 'action', 'asked', 'todo', 'fyi'):
        frm = f"{item.get('who') or 'Someone'} wrote on {item.get('channel') or 'email'}" + (f" ({funnel_age(item)})" if funnel_age(item) else '') + f": \"{item['title']}\""
        done = (f"the agent {item['summary']}" if item.get('summary') else
                'triage judged it a reply to write' if item['kind'] == 'review' else 'an agent proposed an action' if item['kind'] == 'action' else
                'a coding task with no agent on it yet' if item.get('coding') else 'nothing has been done with it yet' if item['kind'] in ('asked', 'todo')
                else f'triage filed it as fyi{_verdict_why(item)}')
        need = ('approve the draft below, or redraft it' if item['kind'] == 'review' else 'say whether it may run' if item['kind'] == 'action' else
                'reply, choose a coding or regular agent, or say it is not ours' if item['kind'] in ('asked', 'todo')
                else 'nothing has to happen - make it a task, tell me to ignore this sender, or move on')
        return f"{frm}. Since then: {done}. From you: {need}."
    if item['kind'] == 'agent':
        return f"{item.get('agent') or 'An agent'} on {item.get('ref') or item['title']} " + (f"asked: {item['tail'][-1]}" if item.get('asking') and item.get('tail') else 'stopped at its prompt') + ' - answer it below.'
    if item['kind'] == 'wrapup':
        return f"{item.get('ref') or item['title']}: the reply went out" + (f" and the agent finished ({item['summary']})" if item.get('summary') else '') + '. The task is still open - close it?'
    if item['kind'] == 'idea':
        return f"{item['title']}" + (f" ({item.get('who')})" if item.get('who') else '') + f" - {item.get('why') or 'the assistant raised this'}. Draft the follow-up, make it a task, or let it go."
    if item['kind'] == 'meeting': return f"{item['title']} is {item.get('why')}. Prep me, or move on."
    if item['kind'] == 'report':
        return f"{item['title']} landed {funnel_age(item)}" + (' and FAILED - the cause is in it.' if item.get('bad') else '.') + ' It is open below - run it again, or move on.'
    if item['kind'] == 'agentdone': return f"{item.get('who') or 'The agent'} finished {item.get('ref') or item['title']}" + (f": {item['summary']}" if item.get('summary') else '.') + ' Want to see the final report?'
    lead = {'agent': f"{item.get('agent') or 'An agent'} is waiting on you on {item.get('ref') or item['title']}.",
            'meeting': f"{item['title']} is {item.get('why')}.",
            'review': f"{item.get('who') or 'Someone'} is owed a reply on \"{item['title']}\"" + (' - the draft is below.' if item.get('draft') else ' - nothing is drafted yet.'),
            'action': f"An agent wants to run something on \"{item['title']}\" - it waits for your yes.",
            'report': f"\"{item['title']}\" landed" + (' and it FAILED - the cause is inside.' if item.get('bad') else '.'),
            'agentdone': f"{item.get('who') or 'The agent'} finished {item.get('ref') or item['title']}: {item.get('summary') or ''}",
            'idea': item['title'], 'todo': f"{item.get('who') or 'Someone'} - \"{item['title']}\": {item.get('why')}",
            'asked': f"{item.get('who') or 'Someone'} asked: \"{item['title']}\".", 'fyi': f"{item.get('who') or 'Someone'} - \"{item['title']}\" - fyi."}
    return (('Next: ' if opening else '') + lead.get(item['kind'], item['title'])).strip()


def funnel_age(item: dict) -> str:
    d = funnel._dt(item.get('since') or item.get('when'))
    if not d: return ''
    m = int((datetime.now() - d).total_seconds() // 60)
    return f'{m} min ago' if m < 60 else f'{m // 60}h ago' if m < 1440 else f'{m // 1440}d ago'


_HANDOFF = re.compile(r"\b(send|hand|give|pass)\s+(it|this|that|them)?\s*(off|over|along)?\s*(to)?\s*(the\s+)?(coding\s+)?"
                      r"(agent|coder|codex|claude|gemini)\b|\buntil it works?\b|\band (make sure|see) (it|that it) works?\b|\bplease \b", re.I)


def _handoff_title(store, tid: int, text: str) -> str:
    """What to call the task. Their own words when they name the job; otherwise the thing the
    conversation was on - "send it to the coding agent until it works" names nothing by itself."""
    bare = _HANDOFF.sub(' ', _POLITE.sub('', text.strip())).strip(' ,.:-?!')
    bare = re.sub(r'\s{2,}', ' ', bare)
    if len(bare.split()) >= 3: return bare[:120]
    for c in reversed(general.chat_rows(store, tid)):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('title'): return f"{card['title']}"[:120]
    return (bare or text.strip())[:120]


def _handoff_brief(store, tid: int, text: str) -> str:
    """The words to hand the agent: what the owner just said, with what the conversation was on when
    they said it - "send it to the coding agent until it works" is a brief only with the report named."""
    rows = general.chat_rows(store, tid)
    prior = [_MARK.sub('', c.get('Body') or '').strip() for c in rows[-6:-1]]
    ctx = ' '.join(_cut(b, 200) for b in prior if b)
    return f"{text.strip()}\n\nWhat we were talking about:\n{_cut(ctx, 900)}" if ctx else text.strip()


def _last_owner_words(store, tid: int, text: str) -> str:
    """What the owner said before this - the antecedent for "remove them", "same for those"."""
    for c in reversed([c for c in general.chat_rows(store, tid) if c.get('ActorType') == general.USER_TYPE]):
        body = _MARK.sub('', c.get('Body') or '').strip()
        if body and body != text.strip(): return _cut(body, 300)
    return ''


def _turns(store, tid: int) -> str:
    rows = general.chat_rows(store, tid)[-TURNS:]
    return '\n'.join(f"{'YOU' if c.get('ActorType') == general.ASSISTANT_TYPE else 'OWNER'}: {_cut(_MARK.sub('', c.get('Body') or ''), 500)}" for c in rows)


def _system(store, llm=None) -> str:
    # the document first, the machine contract last; never the tools block - the assistant runs nothing
    contract = PHONE_CONTRACT if DELIVERY.get() == PHONE else CONTRACT
    return f"{_counsel(store)}\n\n{contract.format(owner=_owner(store))}"


def _urgent_line(pile_items: list, item: dict | None) -> str:
    """One line for the prompt when something more pressing waits behind the item on the table."""
    more = funnel.more_urgent(pile_items, (item or {}).get('key'))
    if not more: return ''
    return ('\nMORE URGENT WAITING (not what we are on): ' + '; '.join(f"{i.get('who') + ' - ' if i.get('who') else ''}{i['title']} ({funnel.LANE_WORDS[i['lane']][0]})" for i in more[:3])
            + ' - mention it in one short clause and offer to switch after this one; do not describe it.\n')


_REF = re.compile(r'\bTQ-0*(\d+)\b')

def off_subject(say: str, item: dict | None) -> bool:
    """The model wandered: it names a task that is not the one on the table, or names none of the item's
    own words at all (2026-09-03: the words were Mindy's TQ-0312, the card was TQ-0327; later the words were
    Ayush's commit, the card the Morning digest - a resumed conversation narrating from memory)."""
    if not item: return False
    named = {int(n) for n in _REF.findall(say or '')}
    if item.get('tid') and named: return int(item['tid']) not in named
    from .routing import tokens
    own = {w for w in tokens(f"{item.get('who') or ''} {item.get('title') or ''}") if len(w) > 2} - {'the', 'and', 'for', 'with', 'from', 'morning', 'today', 'yesterday', 'tomorrow', 'week', 'this', 'that'}
    if not own: return False
    return not (own & set(tokens(say or '')))


# The voice must never step out of the part. A CLI brain answered "next" with "I understand the
# role, but I don't have the queue data" and "yes go ahead" with "I'm in Claude Code... I don't have
# access to the systems Taskuary would need" - twice, in the owner's face (2026-09-03). It is not
# the assistant's place to describe its own plumbing: the facts line is a better answer than that.
_BROKE_CHARACTER = re.compile(r"\b(i (do ?n'?t|don't|cannot|can'?t) (have|see|access)\b.{0,40}\b(access|data|queue|pipe|systems|database|information|context)"
                              r"|i'?m (in |running (in|on) )?(claude code|codex|gemini|an? (ai|llm|language model))"
                              r"|as an ai\b|i am an ai\b|i (have|am) (no|not) (able to )?(access|connected)"
                              r"|i (would|will) need (access|the) \w+ (to|before)|i'?m unable to access"
                              r"|i (do ?n'?t|cannot) (actually )?(run|execute|call) (anything|tools|commands))", re.I)


def in_character(say: str) -> bool:
    """False when the answer talks about the model's own limits instead of the owner's work."""
    return not _BROKE_CHARACTER.search(say or '')


def _ask(store, llm, tid: int, item: dict | None, instruction: str, pile_items: list) -> tuple[str, list, str]:
    # the item comes FIRST and is named as the only subject; the pile is counts only while one is on the table
    user = ((f"THE ITEM ON THE TABLE - speak only about this one:\n{facts(store, item)}\n\n" if item else '')
            + f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(pile_items, coming=item is None)}{_urgent_line(pile_items, item)}\n\n"
            + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
            + (f"{facts(store, item)}\n\n" if not item else '') + instruction)
    text = str(llm(_system(store, llm), user, max_tokens=MAX_TOKENS) or '').strip()
    # An INTRODUCTION is not a decision, but the model ends one with a DECIDE line anyway - and this pass
    # used to parse only OPTIONS, so the marker printed verbatim and the thing it announced was dropped on
    # the floor: "I'd hand this to a regular agent... DECIDE: regular_agent" and then nothing happened (the
    # owner, 2026-09-07). The line never reaches the screen; the verb it named becomes the primary chip.
    text, decision = parse_decision(text)
    say, options = parse_options(text)
    if off_subject(say, item):
        logger.info(f"concierge: the model spoke about another task than {item.get('ref')} - using the facts instead")
        return '', [], ''
    if not in_character(say):
        logger.info('concierge: the voice broke character - using the facts instead')
        return '', [], ''
    return say, options, (decision or {}).get('verb') or ''


def record(store, tid: int, role: str, text: str, card: dict = None):
    # A presentation revision is transport freshness, not conversation meaning.  Persisting it
    # made the same adjacent card into a second durable turn when surfacing changed only its read
    # state.  Keep every semantic field, including nested FYI cards, and let the current HTTP
    # response carry the newest revision.
    def durable(value):
        if not isinstance(value, dict): return value
        out = dict(value); out.pop('presentation_revision', None)
        children = out.get('items')
        if isinstance(children, list):
            out['items'] = [durable(child) if isinstance(child, dict)
                            and all(k in child for k in ('key', 'kind', 'lane')) else child for child in children]
        return out
    saved_card = durable(card) if card else None
    body = redact(text).strip() + (f"\n\n{MARK}{json.dumps(saved_card, default=str)} -->" if saved_card else '')
    actor = 'owner' if role == 'user' else 'assistant'
    actor_type = general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE
    # A double click must not duplicate the owner's words: those two calls may reach the backend
    # before React disables the button. The same guard also makes empty-pipe auto-advance
    # idempotent across tabs. Deliberately repeated words still record once another turn separates
    # them, so this only removes adjacent duplicates.
    add = getattr(store, 'add_comment_once', store.add_comment)
    return add(tid, actor, actor_type, body)


# The global walkthrough has its own durable dock conversation, but the part about a real task must
# also remain with that task. These distinct types keep it out of a general agent's working context
# while making it available to the Timeline's "Assistant discussion" tab.
DISCUSSION_USER_TYPE = 'concierge_user'
DISCUSSION_ASSISTANT_TYPE = 'concierge_assistant'


def record_related(store, dock_tid: int, item: dict | None, role: str, text: str, card: dict = None):
    """Record a dock turn and mirror it onto every real task the turn discusses."""
    result = record(store, dock_tid, role, text, card)
    candidates = list((item or {}).get('items') or []) if (item or {}).get('kind') == 'fyis' else [item or {}]
    tids = {int(i['tid']) for i in candidates if i.get('tid') and int(i['tid']) != int(dock_tid)}
    actor = 'owner' if role == 'user' else 'Taskuary'
    actor_type = DISCUSSION_USER_TYPE if role == 'user' else DISCUSSION_ASSISTANT_TYPE
    add = getattr(store, 'add_comment_once', store.add_comment)
    for task_tid in tids:
        if not store.get_task(task_tid): continue
        # our words about it are not news about it: the task keeps the read it had (store.processing_own_words)
        own = getattr(store, 'processing_own_words', None)
        with (own(task_tid, actor) if own else nullcontext()):
            add(task_tid, actor, actor_type, redact(str(text or '')).strip())
    # ...and durably against the ITEM (PW-132): the dock conversation is retained on its own clock and the
    # browser's receipts were the only other record. One item's turn is kept on that item; a handful of fyi
    # share one line, so a batch turn is attributed to none of them rather than to all four.
    if (item or {}).get('kind') != 'fyis' and (item or {}).get('mid') or (item or {}).get('tid') and int(item['tid']) != int(dock_tid):
        body = redact(str(text or '')).strip()
        tid = int(item['tid']) if item.get('tid') and int(item['tid']) != int(dock_tid) else None
        try:
            recent = (operations.discussion(store, message_id=item.get('mid')) if item.get('mid') else operations.discussion(store, task_id=tid))[-2:]
            if body and not any(x.get('Actor') == actor and x.get('Body') == body for x in recent):   # a double send (owner line + answer) is one turn
                operations.discuss(store, actor, body, message_id=item.get('mid'), task_id=tid)
        except Exception as e: logger.warning(f'concierge: the discussion was not kept against the item - {e}')
    return result


def history(store, tid: int) -> list:
    out = []
    for c in general.chat_rows(store, tid):
        body = c.get('Body') or ''
        m = _MARK.search(body)
        card = None
        if m:
            try: card = json.loads(m.group(1))
            except ValueError: card = None
        text, options = parse_options(_MARK.sub('', body))
        turn = {'id': c['CommentId'], 'role': 'assistant' if c.get('ActorType') == general.ASSISTANT_TYPE else 'user',
                'text': text, 'options': options, 'card': card, 'at': c.get('CreatedAt')}
        # Heal legacy races at the read boundary too. Existing databases may already contain two
        # adjacent copies written before record() became atomic; do not keep rendering them forever.
        # A real repeated message remains when an intervening turn separates it.
        if out and all(out[-1].get(k) == turn.get(k) for k in ('role', 'text', 'options', 'card')):
            continue
        out.append(turn)
    return out


def chats(store, actor: str = 'owner', limit: int = 25, before: int = None) -> list:
    """Every conversation the guide has had, newest first: what it was about, when it ran, how long it
    lasted, how much of the pipe it got through, and which is open.

    A walk with nothing typed into it used to read "Walkthrough · 2026-09-03" three times over, with
    nothing to tell them apart (the owner, 2026-09-03: "Past chats don't really make sense... we need
    to add time to it, and how many emails processed so you can see past transacript"). So an untyped
    walk is named by its clock and counted by the items it actually put on the table. A page at a time,
    and READ-ONLY (PW-157): what expires is retention's job on its own clock (retention.py), never a side
    effect of looking at the list."""
    out = []
    for t in store.dock_tasks(general.DOCK_TAG, limit=limit, before=before):
        rows = general.chat_rows(store, t['TaskId'])
        last = str((rows[-1]['CreatedAt'] if rows else t.get('CreatedAt')) or '')
        first = next((c for c in rows if c.get('ActorType') == general.USER_TYPE), None)
        started = str(rows[0]['CreatedAt'] if rows else t.get('CreatedAt') or '')
        # what it got THROUGH: every card the assistant put on the table, mail counted apart
        cards = [c for c in (_card_of(r) for r in rows) if c]
        seen = len({c.get('key') for c in cards if c.get('key')})
        mail = len({c['mid'] for c in cards if c.get('mid')})
        title = (_cut(_MARK.sub('', (first or {}).get('Body') or ''), 70).split('\n')[0] if first
                 else f"Walk · {_when(started)}")
        out.append({'taskId': t['TaskId'], 'title': title, 'at': last or None, 'started': started or None,
                    'turns': len(rows), 'seen': seen, 'mail': mail, 'minutes': _span_minutes(started, last),
                    'open': t.get('Status') not in ('done', 'dropped')})
    return out


def _card_of(row: dict) -> dict | None:
    m = _MARK.search(row.get('Body') or '')
    if not m: return None
    try: return json.loads(m.group(1))
    except ValueError: return None


def _when(ts: str) -> str:
    d = funnel._dt(ts)
    if not d: return str(ts)[:16]
    h = d.hour % 12 or 12                                   # Windows has no %-I, and %p shouts
    return f"{d.strftime('%a %d %b').lstrip('0')}, {h}:{d.strftime('%M')}{'am' if d.hour < 12 else 'pm'}"


def _span_minutes(start: str, end: str) -> int:
    a, b = funnel._dt(start), funnel._dt(end)
    return max(0, int((b - a).total_seconds() // 60)) if a and b else 0


_CUES = {'show', 'me', 'tell', 'about', 'what', 'did', 'does', 'send', 'sent', 'email', 'mail', 'message', 'from', 'the', 'find',
         'open', 'read', 'pull', 'up', 'one', 'that', 'thing', 'said', 'say', 'again', 'back', 'please', 'can', 'you', 'and', 'with',
         'for', 'was', 'there', 'anything', 'thread', 'wrote', 'write', 'asked', 'ask', 'get', 'have', 'has', 'any', 'this', 'his', 'her',
         # "did you do it?" is a question about US - it used to score against every subject with a
         # short word in it and come back as "I can't find that one" (the owner, 2026-09-03)
         'do', 'done', 'doing', 'it', 'its', 'them', 'they', 'i', 'we', 'my', 'our', 'your', 'yet', 'still', 'already', 'now', 'why', 'how',
         'when', 'where', 'who', 'is', 'are', 'be', 'been', 'not', 'no', 'yes', 'ok', 'okay', 'sure', 'but', 'so', 'just', 'all'}


def lookup_days(text: str) -> int:
    """How far back the owner's own words reach. A fixed fortnight meant anything older simply did not
    exist to the assistant (the owner, 2026-09-07: "widen the lookup to intent of user - if he asked 6
    months ago, search that"). The model can also say `days` outright on timeline.search."""
    t = (text or '').lower()
    m = re.search(r'(\d+)\s*(day|week|month|year)s?', t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return min(3650, n * {'day': 1, 'week': 7, 'month': 31, 'year': 365}[unit] + 7)
    for phrase, d in (('last year', 400), ('this year', 365), ('year', 365), ('months', 190),
                      ('month', 62), ('last week', 21), ('week', 14), ('yesterday', 3), ('today', 2)):
        if phrase in t: return d
    return 90                                   # the default reach, not a fortnight


def lookup(store, text: str, days: int = None) -> str | None:
    """The pile item, or Timeline row, the owner's words point at - "what did Dana send", "the invoice
    thread". Sender and subject words only (a body matches everything), most of the meaningful words
    must hit, and the newest wins a tie. None when nothing is clearly meant."""
    from .routing import tokens
    if days is None: days = lookup_days(text)
    ref = re.search(r'\bTQ-?0*(\d+)\b|#task=(\d+)', text or '', re.I)
    if ref:
        tid = int(ref.group(1) or ref.group(2))
        if store.get_task(tid): return f'task:{tid}'
    words = [w for w in tokens(text) if w not in _CUES]
    if not words: return None
    best, score = None, 0.0
    for r in store.feed(limit=400, days=days):
        if r.get('Direction') == 'out' or r.get('Channel') == 'assistant': continue
        hay = set(tokens(f"{r.get('FromName') or ''} {r.get('FromEmail') or ''} {r.get('Subject') or ''} {r.get('SourceName') or ''}"))
        hit = sum(1 for w in words if w in hay or any(h.startswith(w) for h in hay))
        sc = hit / len(words)
        if hit and sc > score: best, score = r, sc
    if not best or score < 0.5: return None
    return (f"review:{best['ReviewId']}" if best.get('ReviewStatus') == 'pending' and best.get('ReviewId')
            else f"agent:{best['TaskId']}" if best.get('AgentWaiting') and best.get('TaskId')
            else f"report:{best['MessageId']}" if best.get('Channel') == 'report' else f"msg:{best['MessageId']}")


def day(store) -> str:
    """The facts the opening brief is written from: the pipe by lane, today's calendar, what agents
    hold - the same helpers the morning digest reads, never the model's recollection."""
    from . import assistant, calendar as cal
    items = funnel.pile(store, force=True)['items']
    lines = ['THE DAY', funnel.summary(items)]
    try:
        ev = [e for e in (cal.today(store).get('events') or []) if not e.get('all_day')]
        lines.append('CALENDAR TODAY: ' + ('; '.join(f"{cal.span(e['start'], e.get('end') or '')} {e.get('subject')}" + (f" with {', '.join((e.get('who') or [])[:3])}" if e.get('who') else '') for e in ev[:6]) or 'nothing on it'))
    except Exception as e: logger.debug(f'concierge: calendar skipped - {e}')
    flight = assistant.in_flight(store)
    lines.append('AGENTS HAVE: ' + ('; '.join(f"{f['ref']} {f['title']} ({f['state']})" for f in flight[:6]) or 'nothing right now'))
    return '\n'.join(lines)


def _brain_for(store, tid: int, llm, trace=None, cancel=None, fast=True):
    """The caller's brain, or ours - always the fast lane: an API connector when there is one, else the CLI
    with its tools off. The assistant never runs anything, so no turn needs the slow gear."""
    if llm is not None: return llm
    try: return brain(store, trace=trace, cancel=cancel, resume=_sid(store, tid) or None, fast=True)
    except Exception as e:
        logger.warning(f'concierge: no brain for this turn - {e}')
        return None


_NUMBERED = re.compile(r'^\s*(\d+)[.)]\s*(.+?)\s*$', re.M)

def _numbered(text: str, n: int) -> dict:
    """{1: line, ..., n: line} from a numbered answer - all n of them, or nothing."""
    got = {int(k): v for k, v in _NUMBERED.findall(text or '') if 1 <= int(k) <= n}
    return got if len(got) == n else {}


def open_day(store, llm=None, actor: str = 'owner', trace=None, cancel=None) -> dict:
    """The first line of a new chat: the day in a breath, then the buttons that start the walk. Written
    once per chat - a conversation that already has turns is not re-opened."""
    task, _ = general.dock_task(store, actor)
    tid = task['TaskId']
    if general.chat_rows(store, tid): return {'say': '', 'card': None, 'opened': False}
    p = funnel.pile(store, force=True)
    facts_ = day(store)
    llm = _brain_for(store, tid, llm, trace, cancel, fast=True)
    say = ''
    if llm:
        try:
            say, _opts = parse_options(str(llm(_system(store, llm), f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{facts_}\n\n{OPENING}", max_tokens=MAX_TOKENS) or '').strip())
            _remember_sid(store, tid, llm)
        except Exception as e: logger.warning(f'concierge: the opening failed - {e}')
    if not say:
        n = len(p['items'])
        say = ("Let's go through what we have today. " + (f"{n} thing{'s' if n != 1 else ''} waiting - {funnel.summary(p['items']).split(' - ', 1)[-1].split('.')[0]}." if n else 'Nothing is waiting on you yet.'))
    chips = walk_chips(len(p['items']))
    card = {'key': 'brief', 'kind': 'brief', 'lane': 'report', 'title': 'Today', 'n': len(p['items']),
            'mail': sum(1 for i in p['items'] if i['kind'] in funnel.MAIL_KINDS), 'chips': chips}
    record(store, tid, 'assistant', say, card)
    return {'say': say, 'card': card, 'chips': chips, 'opened': True}


def _live(store) -> list:
    from . import terminal as term
    try: return term.live_sessions(tail=0)
    except Exception: return []


_TROUBLE = re.compile(r"\b(report|connection|connector|failing|fails|failed|not working|broken|error|why (is|did|does))\b", re.I)

def trouble(store, text: str) -> str:
    """When the owner asks why something is failing: what IS failing, from the hub's own view - every
    connector whose last poll errored, the triage brain, every report that failed today (problems.py) - so
    the assistant explains from the error, not from a guess. Reading, never running."""
    if not _TROUBLE.search(text or ''): return ''
    from . import problems
    try: rows = problems.collect(store)
    except Exception as e:
        logger.debug(f'concierge: problems skipped - {e}'); return ''
    if not rows: return '\n\nWHAT IS FAILING RIGHT NOW: nothing - every connection polled clean and no report failed today.'
    return '\n\nWHAT IS FAILING RIGHT NOW (explain from the error; offer rerun, or the coding agent for a fix):\n' + '\n'.join(
        f"- {r.get('title')}: {_cut(r.get('detail'), 300)}" + (f" (since {str(r.get('since'))[:16]})" if r.get('since') else '') for r in rows[:8])


_SWEEP_CUES = _CUES | {'remove', 'clear', 'dismiss', 'get', 'rid', 'hide', 'drop', 'kill', 'archive', 'mark', 'read', 'all', 'every', 'these', 'those',
                       'any', 'same', 'need', 'them', 'dont', 'don', 'want', 'reports', 'emails', 'mails', 'messages', 'items', 'stuff', 'things', 'more', 'never', 'again', 'anymore', 'please', 'you',
                       # where they want it gone FROM is not what they want gone
                       'pipe', 'pipeline', 'piepline', 'funnel', 'inbox', 'queue', 'list', 'feed', 'skip', 'stop', 'showing', 'surfacing', 'sending', 'show', 'send',
                       # ...and the words that ASK for the rule rather than name its target
                       'rule', 'rules', 'surface', 'see', 'seeing', 'stuff', 'make', 'made', 'set', 'next', 'move', 'on', 'also', 'again', 'ever',
                       # the modals and fillers an instruction is wrapped in - never the target
                       'should', 'shouldnt', 'would', 'could', 'about', 'longer', 'appear', 'coming', 'come', 'up', 'me', 'my', 'those', 'anymore'}

# An instruction that belongs in a SWITCH is written there - but never on our own say-so: it comes
# back as a proposal with the switch named, and the owner's click applies it (the owner, 2026-09-03:
# "yes do it that way ask user if it can change setttings"). The phrase table is deliberate: a switch
# is not something to guess at, so words that match nothing here reach the model as a question.
SWITCH_ASKS = (
    (re.compile(r"\b(pr|prs|pull requests?|github (issues?|items?))\b.*\b(timeline|not tasks?|no tasks?|feed)\b"
                r"|\b(don'?t|do not|stop) (making|make|turning|turn) (github |pr |prs )?.*\btasks\b", re.I),
     [{'connector': 'github', 'name': 'use_as_tracker', 'value': False}, {'name': 'agent_issues_enabled', 'value': False}],
     'GitHub items land on the Timeline instead of becoming tasks'),
    (re.compile(r"\b(stop|don'?t|do not) (auto-?start(ing)?|automatically start(ing)?|auto-?run(ning)?)\b|\bno auto-?(start|coder)\b"
                r"|\b(stop|don'?t) (sending|handing) (everything |it )?to the (coding agent|coder)\b", re.I),
     [{'name': 'coder_auto_enabled', 'value': False}], 'the coding agent waits for you instead of starting itself'),
    (re.compile(r"\b(auto-?start|automatically start) the (coding agent|coder)\b|\bturn (on|back on) auto-?code\b", re.I),
     [{'name': 'coder_auto_enabled', 'value': True}], 'the coding agent starts itself on new coding work'),
    (re.compile(r"\b(stop|don'?t|do not) (drafting|draft) (replies|them|it) (in advance|in the background|before)\b"
                r"|\bno (auto-?draft|background draft)\b", re.I),
     [{'name': 'auto_draft_enabled', 'value': False}], 'replies are drafted when you ask, not in advance'),
    (re.compile(r"\b(check|read|poll|sync) (the )?(mail|mailboxes?|email)\s*(every|each)\s*(\d+)\s*(min|minute|minutes)\b", re.I),
     'poll_minutes', 'how often the mailboxes are read'),
    (re.compile(r"\b(pipe|funnel) (should )?(hold|keep)\s*(at most)?\s*(\d+)\b", re.I),
     'funnel_max', 'how much the pipe holds at once'),
    (re.compile(r"\b(pipe|funnel).{0,20}\b(reach|go) back(\s*to)?\s*(\d+)\s*(h|hour|hours)\b", re.I),
     'funnel_hours', 'how far back the pipe reaches'),
    (re.compile(r"\b(never|stop|don'?t) (read|reading|check|checking) (my )?calendar\b", re.I),
     [{'name': 'calendar_enabled', 'value': False}], 'your calendar is left alone'),
)


def switch_ask(text: str) -> tuple:
    """(changes, what it means) when the owner's words name a switch we may propose; ([], '') when not."""
    for rx, target, says in SWITCH_ASKS:
        m = rx.search(text or '')
        if not m: continue
        if isinstance(target, str):                       # a number the owner said out loud
            num = next((g for g in reversed(m.groups()) if g and str(g).isdigit()), None)
            if not num: continue
            return [{'name': target, 'value': str(num)}], f'{says} - {num}'
        return list(target), says
    return [], ''


_STANDING = re.compile(r"\b(never|don'?t need|do not need|stop|anymore|always|from now on|not needed|taken care of|"
                       r"handled|covered|part of|already (done|handled)|no need)\b", re.I)

def _sender_for(store, words: list) -> str:
    """Whose mail the owner's words name, from what has actually arrived - so a rule written before
    the next batch lands is still about a person, not just a phrase."""
    from .routing import tokens
    tally = {}
    for r in store.feed(limit=200, days=14):
        if r.get('Direction') == 'out' or not (r.get('FromEmail') or ''): continue
        hay = set(tokens(f"{r.get('FromName') or ''} {r.get('FromEmail') or ''} {r.get('Subject') or ''}"))
        if funnel.like(words, hay) >= 2: tally[r['FromEmail'].lower()] = tally.get(r['FromEmail'].lower(), 0) + 1
    return max(tally, key=tally.get) if tally else ''


# "skip all the fyi from Chana and Dovid" names a LANE, not a subject. Read as subject words it
# wrote "fyi from chana@ours.com" and "dovid from dovid@ours.com" - one rule about a word nobody
# writes in a subject line, one about a man's own name (the 2026-09-03 break test).
LANE_RULE_WORDS = {'fyi': 'fyi', 'fyis': 'fyi', 'report': 'report', 'reports': 'report'}

def _rules_from(swept: list) -> list:
    """One rule per sender: [{'sender', 'words'}] or [{'sender', 'lane'}]. A sender swept on their
    name alone gets a rule about them; a sweep that named a LANE gets that lane from that sender;
    everyone else needs their subject words, so a rule can never quietly grow into "everything from
    this person"."""
    by, lanes = {}, {}
    for x in swept:
        key = x['email'] or (x['who'] or '').lower()
        if not key: continue
        by.setdefault(key, set()).update(x['words'])
        for w in x['words']:
            if w in LANE_RULE_WORDS: lanes.setdefault(key, set()).add(LANE_RULE_WORDS[w])
    out = []
    for key, words in by.items():
        if lanes.get(key):
            out.append({'sender': key, 'lane': sorted(lanes[key])[0], 'words': []}); continue
        own = set(re.split(r'[@.\s]+', key))
        subject = sorted(w for w in words if w not in LANE_RULE_WORDS and not any(w in part for part in own))
        out.append({'sender': key, 'words': subject or sorted(words)})
    return out


def _rule_words(rule: dict) -> str:
    if rule.get('lane'): return f"every {rule['lane']} from {rule['sender']}"
    return f"{' '.join(rule['words'][:4])} from {rule['sender']}" if rule.get('sender') else ' '.join(rule['words'][:4])


def _sweep_words(text: str) -> list:
    """The TARGET, not the reason and not the rest of the instruction. Sentence by sentence: the first
    one that names anything is the target ("skip all the mfa financial reports"), and what follows is
    usually why ("those are part of the financials process, taken care of") - matching on the why swept
    a real ask that merely said "financials". A sentence that is pure instruction ("next.", "can you
    make rules to...") names nothing and is passed over (the owner, 2026-09-03)."""
    from .routing import tokens
    keep = lambda t: [w for w in tokens(t) if w not in _SWEEP_CUES]
    for part in re.split(r'[.!?\n]+', str(text or '').strip()):
        words = keep(part)
        if words: return words
    return keep(text)


def _sweep(store, words: list, actor: str) -> tuple[int, list, list, list]:
    """Mark every pile item whose sender or subject carries these words read - it leaves the pipe and
    stays on the Timeline; nothing is deleted. The fourth return is what was swept, per item: the
    sender and the words that actually hit, which is what a standing rule is made of."""
    from .routing import tokens
    if not words: return 0, [], [], []
    hit, titles, mids, swept, cleared = 0, [], [], [], []
    for i in funnel.build(store, keep_surfaced=True)['items']:
        if i['lane'] in ('blocked', 'working'): continue                                   # an agent's question is never swept
        hay = set(tokens(f"{i.get('who') or ''} {i.get('email') or ''} {i.get('title') or ''}"))
        who = set(tokens(f"{i.get('who') or ''} {i.get('email') or ''}"))
        n = funnel.like(words, hay)
        if not n or (n < 2 and not funnel.like(words, who)): continue                      # the sender alone, or two words of the subject
        if not _clear_one(store, i['key'], actor, 'swept by the owner'): continue
        hit += 1; cleared.append(i)
        titles.append(i['title']); mids.append(i.get('mid'))
        swept.append({'email': (i.get('email') or '').lower(), 'who': i.get('who') or '',
                      'words': [w for w in words if funnel.like([w], hay)]})
    _off_the_table(store, cleared, actor)
    return hit, titles, mids, swept


def select_items(store, sel: dict) -> list:
    """The items a SELECTOR describes. Every field is optional and they AND together; an empty selector
    matches nothing, deliberately - "clear everything" must be asked for by naming a field, never by
    leaving them all blank."""
    from .routing import tokens
    sel = {k: v for k, v in (sel or {}).items() if v not in (None, '', [])}
    if not sel: return []
    want = lambda f: str(sel.get(f) or '').strip().lower()
    cat, kind, lane = want('category'), want('kind'), want('lane')
    who = want('sender')
    words = [w for w in tokens(str(sel.get('contains') or ''))]
    older = sel.get('older_than_hours')
    out = []
    # THE PIPE IS WHAT IS UNREAD. keep_surfaced=True is the whole timeline, all-time: it offered to
    # "clear 72" when seven reports were actually waiting, because 65 of them had been read days ago
    # (the owner, 2026-09-07: "there isn't 72 in the pipeline. There are 8 open report category in
    # unread. 72 is all time but we don't care about those").
    for i in funnel.build(store)['items']:
        if i['lane'] in ('blocked', 'working'): continue                  # an agent's question is never swept
        if cat and str(i.get('category') or '').lower() != cat: continue
        if kind and str(i.get('kind') or '').lower() != kind: continue
        if lane and str(i.get('lane') or '').lower() != lane: continue
        if who:
            hay = f"{i.get('who') or ''} {i.get('email') or ''}".lower()
            if who not in hay: continue
        if words and not funnel.like(words, set(tokens(i.get('title') or ''))): continue
        if older:
            age = funnel._dt(i.get('since') or i.get('when'))
            if not age or (datetime.now() - age).total_seconds() < float(older) * 3600: continue
        out.append(i)
    return out


def _clear_one(store, key: str, actor: str, note: str) -> bool:
    """One item off the pipe, and say whether it actually went. A sweep that dies on its third item
    left the first two read and told the owner nothing had moved."""
    try:
        funnel.settle(store, key, 'done', actor, note=note)
        return True
    except (ValueError, RuntimeError) as e:
        logger.warning(f'concierge: {key} stayed in the pipe - {e}')
        return False


def _off_the_table(store, cleared: list, actor: str):
    """What a sweep clears cannot stay in front of the owner. Settling ONE item drops Current with it
    (the /api/funnel/settle road does), and the sweep did not - so "clear the reports" cleared seven
    and left the report it was holding on the table (the owner, 2026-09-07: "did not clear current one
    when i said clear the reports")."""
    keys = {i['key'] for i in cleared}
    if not keys: return
    tid = general.dock_task(store, actor)[0]['TaskId']
    if current_key(store, tid) in keys: set_current(store, tid, None, actor)


def clear_selected(store, sel: dict, actor: str = 'owner') -> dict:
    """Mark every item a selector names read. Read, never deleted - they stay on the Timeline."""
    items = select_items(store, sel)
    cleared = [i for i in items if _clear_one(store, i['key'], actor, 'cleared by the owner')]
    _off_the_table(store, cleared, actor)
    return {'cleared': len(cleared), 'stuck': len(items) - len(cleared),
            'titles': [i['title'] for i in cleared][:8],
            'mid': next((i.get('mid') for i in cleared if i.get('mid')), None), 'remember': False,
            'note': '', 'words': [], 'rules': [], 'select': sel}


def clear_matching(store, text: str, actor: str = 'owner', hint: str = '') -> dict:
    """'Remove all the Nechama Ozur reports': every pile item whose sender or subject carries the owner's
    words is marked read - it leaves the pipe and stays on the Timeline; nothing is deleted. 'Don't need
    them' / 'never again' also names the sender so the page can write the standing verdict.

    `hint` is what the owner said just before: "remove them from the pipeline" names nothing on its own,
    and a sweep that matches nothing is worse than none - the assistant promised twice and the mails
    stayed (the owner, 2026-09-03: "not removing the mfa financial reports in funnel?")."""
    used = _sweep_words(text)
    hit, titles, mids, swept = _sweep(store, used, actor)
    # "remove them from the pipeline" names nothing of its own: the target is the last thing the owner
    # named. Tried second, so words that DO match are never overruled by an older subject.
    if not hit and hint:
        used = _sweep_words(hint)
        hit, titles, mids, swept = _sweep(store, used, actor)
    remember = bool(re.search(r"\b(never|don'?t need|do not need|stop|anymore|always|from now on|not needed)\b", text, re.I))
    # a sweep with a REASON in it is a standing fact, not a tidy-up: keep it in the owner's own words
    # against the sender, so triage reads it on the next one instead of filing it as work again
    note, sender, rules = '', next((m for m in mids if m), None), []
    # Nothing in the pipe matches right now - but the words are a standing instruction, so the rule
    # is written anyway. Told in advance ("don't show me Nechama's MFA financial reports"), it used to
    # need something on the pile to attach to, so it was written NOWHERE and the next batch walked
    # straight in (the owner, 2026-09-03: "the memory seems not to be working... how does it work?").
    if not hit and used and _STANDING.search(text):
        who = _sender_for(store, used)
        try:
            funnel.remember_mute(store, {'sender': who, 'words': used, 'why': _cut(text.strip().rstrip('.') + '.', 200)}, actor)
            rules.append(_rule_words({'sender': who, 'words': used}))
            store.add_memory({'Scope': 'sender' if who else 'global', 'ScopeKey': who or None,
                              'Note': _cut(text.strip().rstrip('.') + '.', 400), 'Source': 'assistant',
                              'Active': 1, 'CreatedBy': actor})
        except Exception as e: logger.warning(f'concierge: the standing rule did not save - {e}')
        return {'cleared': 0, 'titles': [], 'mid': None, 'remember': False,
                'note': _cut(text.strip(), 400), 'words': used, 'rules': rules, 'ahead': True}
    if hit and _STANDING.search(f'{text} {hint}'):
        msg = (store.get_message(sender) or {}) if sender else {}
        key = (msg.get('FromEmail') or '').lower()
        note = _cut(text.strip().rstrip('.') + '.', 400)
        try: store.add_memory({'Scope': 'sender' if key else 'global', 'ScopeKey': key or None, 'Note': note,
                               'Source': 'assistant', 'Active': 1, 'CreatedBy': actor})
        except Exception as e: logger.warning(f'concierge: the standing note did not save - {e}'); note = ''
        # ...and the rules themselves, which are what keep the next batch out of the pipe (the note above
        # is evidence for triage). ONE PER SENDER: "not surface mfa financials from Nechama and resident
        # refunds stuff from elisheva" is two rules, and a single one carrying both senders' words would
        # have muted whichever sender happened to come first (the owner, 2026-09-03).
        for one in _rules_from(swept):
            try:
                funnel.remember_mute(store, {**one, 'why': _rule_words(one)}, actor)
                rules.append(_rule_words(one))
            except Exception as e: logger.warning(f'concierge: the standing rule did not save - {e}')
    return {'cleared': hit, 'titles': titles, 'mid': sender, 'remember': remember, 'note': note,
            'words': used, 'rules': rules}


def search_timeline(store, sel: dict, limit: int = 12) -> list:
    """The history, by the same selector the pipe uses - and over ALL of it, not the last fortnight.
    lookup() only ever looked 14 days back and needed half the owner's words to hit, so anything older
    simply did not exist to the assistant (the owner, 2026-09-07: "lookup should find the correct
    period and surface likely match")."""
    from .routing import tokens
    sel = {k: v for k, v in (sel or {}).items() if v not in (None, '', [])}
    want = lambda f: str(sel.get(f) or '').strip().lower()
    who, cat = want('sender'), want('category')
    words = [w for w in tokens(str(sel.get('contains') or ''))]
    older = sel.get('older_than_hours')
    out = []
    for r in store.feed(limit=4000, days=int(sel.get('days') or 3650)):
        if r.get('Channel') == 'assistant': continue
        hay = f"{r.get('FromName') or ''} {r.get('FromEmail') or ''}".lower()
        if who and who not in hay: continue
        if cat and str(r.get('Category') or '').lower() != cat: continue
        subj = str(r.get('Subject') or '')
        if words and not all(w in set(tokens(subj + ' ' + hay)) for w in words): continue
        if older:
            from datetime import datetime as _dt
            d = funnel._dt(r.get('SentAt'))
            if not d or (datetime.now() - d).total_seconds() < float(older) * 3600: continue
        out.append({'ref': task_ref(r['TaskId']) if r.get('TaskId') else '', 'when': str(r.get('SentAt') or ''),
                    'who': r.get('FromName') or r.get('FromEmail') or '?', 'title': subj, 'mid': r.get('MessageId')})
        if len(out) >= limit: break
    return out


def read_op(store, kind: str, params: dict) -> str:
    """A LOOK-UP, run at once. Changes nothing, waits for no confirmation, and never moves what is on
    the table - asking about another task must not hijack the walk (the owner, 2026-09-07). The answer
    goes back to the model, which then speaks with it."""
    p = params or {}
    if kind == 'task.read':
        ref = str(p.get('ref') or '').strip()
        m = re.search(r'(\d+)', ref)
        tid = int(p.get('id') or (m.group(1) if m else 0) or 0)
        t = store.get_task(tid) if tid else None
        if not t: return f"There is no task {ref or p.get('id')}."
        out = [f"{task_ref(tid)} [{t.get('Kind')} / {t.get('Status')}] {t.get('Title')}",
               f"opened {str(t.get('CreatedAt') or '')[:16]} by {t.get('CreatedBy')}"]
        if t.get('Summary'): out.append(f"the ask: {_cut(t['Summary'], 900)}")
        for msg in (store.list_messages(tid) or [])[:6]:
            out.append(f"  message {str(msg.get('SentAt') or '')[:16]} from {msg.get('FromName') or msg.get('FromEmail')}: "
                       f"{_cut(msg.get('Subject') or '', 120)} - {_cut(msg.get('BodyText') or '', 400)}")
        for c in (store.list_comments(tid) or [])[-8:]:
            out.append(f"  {c.get('Actor')} ({c.get('ActorType')}) {str(c.get('CreatedAt') or '')[:16]}: {_cut(c.get('Body') or '', 500)}")
        return NEWLINE.join(out)
    if kind == 'report.read':
        title = str(p.get('title') or '').strip().lower()
        srcs = [x for x in store.list_sources(active_only=False) if x.get('Channel') == 'report']
        src = (next((x for x in srcs if str(x.get('SourceId')) == str(p.get('source_id'))), None)
               or next((x for x in srcs if title and title in str(x.get('Address') or '').lower()), None))
        if not src: return 'No report by that name. The ones set up: ' + ', '.join(str(x.get('Address')) for x in srcs[:20])
        out = [f"REPORT {src.get('Address')} (active: {bool(src.get('Active'))})"]
        for r in (store.report_runs(src['SourceId'], 6) or []):
            out.append(f"  {str(r.get('at') or '')[:16]} {'FAILED' if r.get('failed') else 'ok'} "
                       f"{r.get('ms') or 0}ms - {_cut(r.get('error') or r.get('summary') or r.get('said') or '', 400)}")
        return NEWLINE.join(out)
    if kind == 'timeline.search':
        sel = {k: v for k, v in p.items() if k != 'limit'}
        if sel.get('select'): sel = sel['select']
        limit = max(1, min(int(p.get('limit') or 12), 40))
        hits = search_timeline(store, sel, limit)
        if not hits: return 'Nothing in the history matches that.'
        return NEWLINE.join(f"{h['ref'] or '-'} {h['when'][:16]} {h['who']}: {_cut(h['title'], 120)}" for h in hits)
    return f'{kind} is not a look-up this app has.'


def call_turn(store, tid: int, call: dict, item: dict | None, text: str, actor: str = 'owner') -> dict:
    """The model named an operation out of the registry. Turn it into the same proposal card a verb
    makes - NOTHING runs here (PW-123/124); the owner's confirmation is still what executes it.

    A SET is counted before it is offered, so the card says how many and the owner is never told
    "done" about a number nobody checked (the owner, 2026-09-07: it cleared 13 of 72 and said done)."""
    kind, params = call['kind'], dict(call.get('params') or {})
    if toolcatalog.is_read(kind): raise ValueError(f'{kind} is a look-up, not something to confirm')
    it = item or {}
    if kind == 'pipe.clear':
        sel = params.get('select') or {}
        hits = select_items(store, sel)
        if not hits:
            said = ', '.join(f'{k}: {v}' for k, v in (sel or {}).items()) or 'nothing'
            say_ = (f"Nothing in the pipe matches {said}, so there is nothing to clear. "
                    'Say it another way and I will look again - nothing has been touched.')
            record_related(store, tid, item, 'assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        where = ', '.join(f'{k}: {v}' for k, v in sel.items())
        label = f"Clear {len(hits)} from the pipe"
        summary = f"{len(hits)} item{'s' if len(hits) != 1 else ''} - {where}"
        tail = ('They are marked read and stay on the Timeline; nothing is deleted. '
                'Nothing has been started - confirm below, or tell me what to change.')
        prop = _propose_raw(store, tid, 'pipe.clear', 0, {'select': sel, 'text': text}, label, summary, tail, actor, item)
        return {'say': prop['say'], 'options': [], 'chips': [], 'decision': None, 'proposal': prop}
    # everything else acts on ONE thing: the item on the table unless the call named its own target
    for f in toolcatalog.CONTEXT_FILLED:                 # a pile key is ours to supply, never the model's
        if f in operations.KINDS[kind][1] and not params.get(f):
            if not it.get(f): raise ValueError(f'there is nothing on the table for {kind} to act on')
            params[f] = it[f]
    target = params.pop('target', None) or it.get('mid') or it.get('tid') or it.get('rid') or 0
    label = toolcatalog.PURPOSE.get(kind, kind).split(' - ')[0].strip()
    label = label[0].upper() + label[1:] if label else kind
    prop = _propose_raw(store, tid, kind, int(target or 0), params, label, _where(it) or kind,
                        'Nothing has been started - confirm below, or tell me what to change.', actor, item)
    return {'say': prop['say'], 'options': [], 'chips': [], 'decision': None, 'proposal': prop}


def _carry_out(store, tid: int, text: str, words: dict, item0: dict | None, actor: str) -> dict:
    """The two decisions that are already a REVIEW for the owner's yes rather than a proposal card: a switch
    (proposals.py puts it in Review, nothing changes until approved) and a hand-off to a person (a draft,
    sent only on approval)."""
    rec = lambda body, card=None: record_related(store, tid, item0, 'assistant', body, card)
    if words['verb'] == 'setting':
        changes, says = switch_ask(text)
        try: out = propose_switch(store, changes, says, text, actor)
        except Exception as e:
            logger.warning(f'concierge: the switch was not proposed - {e}')
            say_ = f"That is a setting - open Settings and I will leave it to you. ({e})"
            rec(say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"That is a switch, not a note - so I have put it in front of you rather than touching it: "
                f"{says}. Approve it below and it changes; nothing changes until you do.")
        rec(say_, out['card'])
        return {'say': say_, 'options': [], 'decision': {'verb': 'setting', 'reviewId': out['reviewId'], 'changes': changes}}
    if words['verb'] == 'forward':
        try: out = forward_item(store, item0 or {}, words.get('who') or '', words.get('text') or '', actor)
        except Exception as e:
            say_ = f"I could not hand that over - {e}. Open the task and use Hand off, where you can pick the person and the channel."
            rec(say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"Written as a hand-off to {out['to']} - it is below for your yes, and nothing goes until you give it. "
                'Approving it sends the message and closes this one out here.')
        rec(say_, out['card'])
        return {'say': say_, 'options': [], 'decision': {'verb': 'forwarded', 'reviewId': out['reviewId'], 'to': out['to']}}
    raise ValueError(f"{words['verb']} is a proposal - it is never carried out on the words alone")


def _agent_task(store, item0: dict | None, text: str) -> int | None:
    """Which task the owner means when they say "close the agent": the one they NAMED, else the one on
    the table if an agent is on it, else the only agent running. Never a task just because its card
    happens to be open - that is how "close the agent working" closed something else entirely."""
    ref = re.search(r'\bTQ-?0*(\d+)\b', text or '', re.I)
    live = {t.get('taskId'): t for t in _live(store) if t.get('taskId')}
    if ref and int(ref.group(1)) in live: return int(ref.group(1))
    if item0 and item0.get('tid') in live: return item0['tid']
    running = [r['TaskId'] for r in store.running_runs() if r.get('TaskId')]
    only = list(live) or running
    return only[0] if len(only) == 1 else None


def split_item(store, item: dict, text: str, actor: str = 'owner') -> dict:
    """Two jobs in one arrival, split from the chat. A message the owner names goes to its own task
    (ingest.split_message keeps the thread and moves the ask); a task carrying two asks is broken in
    two by reshape.split_task, whose halves the assistant's OWN brain proposes - the same proposal the
    drawer shows, so the chat and the drawer can never disagree."""
    from . import ingest, reshape
    if not item: raise ValueError('nothing on the table to split')
    tid = item.get('tid')
    if not tid:
        if not item.get('mid'): raise ValueError('this one has no task and no message')
        new = ingest.split_message(store, item['mid'], actor)
        t = store.get_task(new) or {}
        return {'ref': None, 'kept': '', 'newRef': task_ref(new), 'taskId': new, 'title': t.get('Title') or ''}
    # NOT the fast brain: reading two jobs out of one mail is a judgement, and the two-sentence
    # gear missed a mail that plainly carried two ("add Priya to the list" + "remove the Bulk
    # Approve button") and answered "only one ask" (the 2026-09-03 break test)
    prop = reshape.propose_split(store, tid, brain(store))
    if not prop.get('two') or not (prop.get('second') or {}).get('title'):
        return {'ref': task_ref(tid), 'kept': (store.get_task(tid) or {}).get('Title') or '', 'why': prop.get('why') or ''}
    new = reshape.split_task(store, tid, prop['second'], prop.get('first'), prop.get('move_message_ids') or [], actor)
    return {'ref': task_ref(tid), 'kept': (store.get_task(tid) or {}).get('Title') or '',
            'newRef': task_ref(new), 'taskId': new, 'title': (store.get_task(new) or {}).get('Title') or ''}


def propose_switch(store, changes: list, says: str, text: str, actor: str = 'owner') -> dict:
    """The owner named a switch: queue it as a proposal for their yes. Nothing is applied here - the
    approval road (verdicts.decide -> proposals.execute) is the only thing that writes a setting."""
    from . import proposals
    p = {'action': 'settings', 'changes': changes, 'why': _cut(text.strip(), 200)}
    ok, why = proposals.validate(store, p)
    if not ok: raise ValueError(why)
    rid = store.add_review({'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p),
                            'Reason': f'you asked for this setting: {says}'})
    store.audit('review', rid, 'setting_proposed', actor, detail={'changes': changes})
    funnel.invalidate()
    return {'reviewId': rid, 'card': {'key': f'review:{rid}', 'kind': 'action', 'lane': 'approve', 'rid': rid,
                                      'title': says, 'who': 'you asked for it', 'why': 'a setting waits for your yes',
                                      'when': _ts(datetime.now())}}


def remember_fact(store, note: str, actor: str = 'owner') -> int:
    """A fact the owner told us to keep. Written HERE rather than left to the page, so the receipt
    is the fact: "Remembered." used to go out whether or not a row was ever written (2026-09-03)."""
    mid = store.add_memory({'Scope': 'global', 'ScopeKey': None, 'Note': redact(note.strip())[:1000],
                            'Source': 'manual', 'Active': 1, 'CreatedBy': actor})
    store.audit('memory', mid, 'create', actor, detail={'from': 'assistant chat'})
    return mid


def forward_item(store, item: dict, who: str, text: str, actor: str = 'owner') -> dict:
    """"Forward it to Chana" / "ask Dovid to handle it": the hand-off written for the owner's yes,
    never sent from a sentence. The address comes from the people who have actually written (the
    same book the task page's hand-off picker uses); a name nobody knows is said so, not guessed."""
    from . import outbound
    from .routing import tokens
    want = [w for w in tokens(who or '') if len(w) > 1]
    if not want: raise ValueError('say who it goes to')
    hit = None
    for p in store.people(400):
        hay = set(tokens(f"{p.get('Name') or ''} {p.get('Email') or ''}"))
        if any(w in hay or any(h.startswith(w) for h in hay) for w in want): hit = p; break
    if not hit: raise ValueError(f"I have no address for {who} - nobody by that name has written here")
    tid, mid = item.get('tid'), item.get('mid')
    note = f"The owner said: {text.strip()}" if text else None
    try: draft = outbound.draft_handoff(store, tid, hit.get('Name') or hit['Email'], note) if tid else ''
    except Exception as e:
        logger.warning(f'concierge: the hand-off draft failed - {e}'); draft = ''
    if not draft:
        draft = (f"Hi {(hit.get('Name') or '').split()[0] or 'there'},\n\nCan you take this one? "
                 f"{item.get('who') + ' wrote: ' if item.get('who') else ''}{item.get('title') or ''}."
                 f"{chr(10) + chr(10) + text.strip() if text else ''}\n\nThanks.")
    subject = f"FW: {item.get('title') or 'this one'}"[:150]
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': draft,
                            'Deliver': json.dumps({'channel': 'email', 'to': [hit['Email']], 'subject': subject}),
                            'Reason': f"you asked to hand this to {hit.get('Name') or hit['Email']}"})
    store.audit('review', rid, 'forward_proposed', actor, detail={'to': hit['Email'], 'key': item.get('key')})
    funnel.invalidate()
    return {'reviewId': rid, 'to': hit.get('Name') or hit['Email'], 'email': hit['Email'],
            'card': {'key': f'review:{rid}', 'kind': 'review', 'lane': 'approve', 'rid': rid, 'tid': tid, 'mid': mid,
                     'ref': task_ref(tid) if tid else None, 'title': subject, 'who': hit.get('Name') or hit['Email'],
                     'draft': True, 'why': 'a hand-off waits for your yes', 'when': _ts(datetime.now())}}


def close_task(store, tid: int, actor: str = 'owner') -> bool:
    """Close a task from the chat: the pending draft on it is dismissed first (a closed task must not
    leave a reply waiting for a yes), then the task itself. False when it was closed already."""
    t = store.get_task(tid) or {}
    if not t or t.get('Status') in ('done', 'dropped'): return False
    rv = store.pending_review(tid)
    if rv:
        try: store.decide_review(rv['ReviewId'], 'no_reply', None, actor, note='the owner closed the task')
        except Exception as e: logger.warning(f'concierge: the draft on {task_ref(tid)} stayed pending - {e}')
    # a closed task has nobody working it: the PATCH road stops the session and this one did not, so
    # "close it" from the chat left the agent running in the checkout (2026-09-03)
    try:
        from . import terminal
        s = terminal.session_for(tid)
        if s and getattr(s, 'alive', False):
            terminal.close(s.sid)
            store.add_comment(tid, actor, 'human', 'Stopped the agent - the task was closed from the chat.')
    except Exception as e: logger.warning(f'concierge: the agent on {task_ref(tid)} was not stopped - {e}')
    store.update_task(tid, {'Status': 'done'}, actor)
    store.audit('task', tid, 'close_from_assistant', actor)
    # ...and the row goes off Unread with it (the owner, 2026-09-07: "it should just go off the unread
    # timeline"). Closing is the decision, wherever it was made; only the CHAT's close used to post the
    # read receipt, so a close on the Tasks page left the mail behind it sitting in the pipe as an fyi.
    # A reply that arrives afterwards is a new unit and comes back unread, and All keeps the whole thread.
    try: funnel.settle(store, f'task:{tid}', 'done', actor, note='the task was closed')
    except Exception as e: logger.debug(f'the closed task did not settle its item: {e}')
    funnel.invalidate()
    return True


# What "set something up" opens. It used to be a CODING task on the default agent, which sent a coder
# into a checkout to build what the app already has: asked to set up the Zoho invoice integration -
# a connector card and a report, both shipped - it opened a session in the wrong repository entirely
# (the owner, 2026-09-03: "This was big mistake... it doesn't need coding agent just a regular agent
# that will walk me through it"). A set-up is a WALK-THROUGH: the conversational agent (general.py),
# no repository, no checkout, nothing built. Real building is a hand-off the owner asks for by name.
SETUP_KIND = 'general'

def setup_task(store, text: str, actor: str = 'owner', title: str = '', kind: str = SETUP_KIND,
               agent_job: bool = False) -> dict:
    """'Set up a report that...': a task with the owner's words in it, opened for the agent that can
    walk them through it. `kind` is 'general' for a walk-through and 'coding' for a hand-off the owner
    asked for (concierge's `coder` verb), which is the only path that starts an agent in a checkout."""
    from . import ingest
    text = str(text or '').strip()
    if not text: raise ValueError('say what to set up')
    title = (title or '').strip()[:120] or re.sub(r'^\s*(please )?(set ?up|create|build|make|add|configure|automate)\s+(a |an |me a |me an )?', '', text, flags=re.I).strip(' .')[:120] or text[:120]
    from . import browserview
    tid = store.create_task({'Title': title[:1].upper() + title[1:], 'Summary': text, 'Kind': kind, 'Status': 'open', 'Priority': 'normal',
                             'Source': 'assistant', 'SourceRef': 'assistant:agent' if agent_job else 'assistant:setup',
                             # A walkthrough may have to log into a portal or point at the exact
                             # setting. Its Assistant session owns that browser; a coding handoff
                             # keeps the ordinary task controls instead.
                             'Tags': browserview.WANTS if kind == SETUP_KIND and not agent_job else ''}, actor)
    store.add_comment(tid, actor, 'human', f'Asked in the Assistant chat: {text}')
    store.audit('task', tid, 'create_from_assistant_setup', actor)
    if kind == 'coding':
        try: ingest._spawn(ingest._auto_code, store, tid)
        except Exception as e: logger.warning(f'setup task {tid}: the agent did not start - {e}')
    return {'taskId': tid, 'ref': task_ref(tid), 'title': title, 'kind': kind}


def card_for(item: dict) -> dict:
    """The card under the line - by kind, by code. The renderer draws it from these few fields
    and reloads the live facts (draft text, agent tail) from the item's ids."""
    return {k: item.get(k) for k in ('key', 'kind', 'lane', 'title', 'who', 'when', 'why', 'mid', 'tid', 'ref', 'rid', 'idea', 'coding', 'source_id', 'preview', 'sent', 'stale', 'sig', 'more',
                                       'idea_kind', 'agent', 'asking', 'tail', 'event', 'summary', 'bad', 'draft', 'channel', 'category', 'action', 'sid', 'mode',
                                       'presentation_revision', 'order_band', 'processing_id', 'member_ids', 'aliases', 'unread', 'deferred', 'actionable')}


def move_on(store, key: str, actor: str = 'owner') -> dict:
    """Put down the thing the owner is walking away from. It is READ - and if it was still waiting on a
    reply, that reply is no longer owed: the pending draft is decided `no_reply` and leaves the Review
    queue (the owner, 2026-09-07: "if there is agent awaiting your approval for reply and you hit next
    then no more reply needed. It's closed").

    The TASK is left alone. Nothing is cancelled and no session is stopped - a parked agent goes on
    working, it just stops interrupting; reopening is the Board's business, not the walk's."""
    if not key: return {}
    try: item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    except Exception as e:
        logger.debug(f'concierge: nothing to put down for {key} - {e}'); return {}
    if not item: return {}
    funnel.settle(store, key, 'surfaced', actor, note=item.get('sig'), read=True)
    ended = []
    for rid in ([item['rid']] if item.get('rid') else []):
        rv = store.get_review(int(rid))
        if not rv or rv.get('Status') not in ('pending', 'held'): continue
        from . import verdicts
        try:
            verdicts.decide(store, rv, 'no_reply', None, 'walked past in the chat - the owner did not want a reply', actor)
            ended.append(int(rid))
        except Exception as e: logger.warning(f'concierge: the draft on {key} could not be put down - {e}')
    return {'key': key, 'read': True, 'reviews_ended': ended}


def surface(store, key: str = None, llm=None, actor: str = 'owner', only: str = None, trace=None, cancel=None,
            include_surfaced: bool = False, exclude: str = None, selection=None, commit_guard=None,
            bound_dock: dict = None, leaving: str = None) -> dict:
    """The next thing out of the pipe (or the one named; or the next piece of MAIL), said in one
    breath and marked as shown. Nothing left: says so.

    `leaving` is the item the owner is walking away from - Next, and only Next. It is put down on the
    way out (move_on): read, and any reply it was still waiting on is ended."""
    if selection is not None and key is not None:
        raise ValueError('a captured automatic selection cannot name a different item')
    put_down = (lambda: move_on(store, leaving, actor)) if leaving else (lambda: None)
    if bound_dock is not None and selection is None:
        raise ValueError('a bound dock is only valid with a captured selection')
    task = bound_dock if bound_dock is not None else general.dock_task(store, actor)[0]
    tid = task['TaskId']
    p = selection.pile if selection is not None else funnel.pile(store, force=True)
    item = selection.selected if selection is not None else (
        funnel.next_item(store, key, only, include_surfaced, exclude)
        or (funnel.item_for_key(store, key) if key else None)
    )
    guarded = (lambda: commit_guard()) if commit_guard is not None else (lambda: nullcontext())
    if not item:
        left = [i for i in p['items'] if not i.get('settling')]
        waiting = [i for i in left if i.get('surfaced') and i['lane'] != 'working']
        if key: say = "I can't find that one - it may be older than what I keep, or it went out under another subject."
        elif not only and waiting:
            # Defensive only: next_item includes merely-shown unread rows, so a normal walk should
            # never strand them here.
            say = f"{len(waiting)} unread thing{'s' if len(waiting) != 1 else ''} still wait{'s' if len(waiting) == 1 else ''}. Say next and I'll take them one at a time."
        elif only and left:
            # the mail is done; what remains is the rest of the pipe - offer it rather than call the day over
            say = f"That's all the mail. {len(left)} other thing{'s' if len(left) != 1 else ''} still wait{'s' if len(left) == 1 else ''} - {funnel.summary(left).split(' - ', 1)[-1].split('.')[0]}. Say next and I'll take you through them."
        elif selection is not None and any(selection.pending.values()):
            pending = selection.pending
            parts = ([f"{pending['working']} in progress"] if pending['working'] else [])
            parts += ([f"{pending['settling']} still being triaged"] if pending['settling'] else [])
            parts += ([f"{pending['scheduled']} scheduled for a little later"] if pending['scheduled'] else [])
            say = "Nothing else needs you right now; " + ', '.join(parts) + '.'
        else: say = ALL_DONE
        with guarded():
            put_down()
            if not key: set_current(store, tid, None, actor)                  # the walk ran out: nothing is on the table
            record(store, tid, 'assistant', say)
        return {'item': None, 'say': say, 'options': [], 'chips': walk_chips(len(left)), 'left': len(p['items']),
                'exhausted': only if (only and left) else None}
    # an agent has this one now (it started after the pile was built, or the owner just sent it): there is
    # nothing for the owner to do until it stops, so say so, let it go, and take the next one. It comes
    # back by itself - as the agent's question, its draft, or its finished job.
    if item['lane'] == 'working' or (item.get('working') and item['kind'] not in ('agent', 'review', 'action')):
        # it stays in the pipe, at the top, in hand - and comes to the front by itself when the agent stops
        who = item.get('working') or next((t.get('agent') or t.get('label') for t in _live(store) if t.get('taskId') == item['tid']), None) or 'the agent'
        say = f"{item.get('ref') or item['title']} is with {who} right now - nothing for you until it stops or asks. I'll bring it down then."
        with guarded():
            put_down()
            record_related(store, tid, item, 'assistant', say + ('' if key else ' Moving on.'))
        return surface(store, None, llm, actor, only, trace, cancel, include_surfaced, exclude) if not key else {'item': None, 'say': say, 'options': [], 'chips': walk_chips(len(p['items'])), 'left': len(p['items'])}
    # FYIs have no action to take, so the normal walk brings four together. A row explicitly
    # clicked on the Timeline still opens by itself (`key` is set); only Next/Walk batches them.
    if not key and item['lane'] == 'fyi':
        batch = item.get('items') if selection is not None and item.get('kind') == 'fyis' else funnel.fyi_batch(store, item)
        llm = _brain_for(store, tid, llm, trace, cancel, fast=True) if (llm is not None or INTRO_AI) else None
        say, gists, remember_llm = '', {}, False
        if llm:
            try:
                # the shape is code's (one numbered line per entry, so each gets its own summary - PW-151); the words are COUNSEL's
                fx = '\n'.join(f"{n}. {i.get('who') or '?'}: \"{i['title']}\" - {i.get('preview') or ''}" for n, i in enumerate(batch, 1))
                user = (f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(p['items'])}\n\n"
                        f"FYI - {len(batch)} thing{'s' if len(batch) != 1 else ''} people told the owner, nothing to do with any of them:\n{fx}\n\n"
                        f"Answer with exactly {len(batch)} numbered line{'s' if len(batch) != 1 else ''}, in that order, one sentence each: who said what, and the gist. No options line.")
                say, _options = parse_options(str(llm(_system(store, llm), user, max_tokens=MAX_TOKENS) or '').strip())
                if not in_character(say): say = ''
                gists = _numbered(say, len(batch))
                remember_llm = True
            except Exception as e: logger.warning(f'concierge: the fyi pass failed - {e}')
        if not say:
            say = (f"{len(batch)} thing{'s' if len(batch) != 1 else ''} people told you, nothing to do: "
                   + '; '.join(f"{i.get('who') or 'someone'} - {i['title']}" for i in batch) + '.')
        batch = [i | {'summary': gists.get(n) or i.get('summary') or i.get('preview') or ''} for n, i in enumerate(batch, 1)]
        card = {'key': 'fyis:' + ','.join(i['key'] for i in batch), 'kind': 'fyis', 'lane': 'fyi',
                'title': f"{len(batch)} fyi", 'who': '', 'when': batch[0].get('when'),
                'since': batch[0].get('since'), 'channel': batch[0].get('channel'),
                'why': 'people told you things; nothing to do', 'items': [card_for(i) for i in batch],
                'presentation_revision': item.get('presentation_revision')}
        with guarded():
            put_down()
            if remember_llm:
                try: _remember_sid(store, tid, llm)
                except Exception as e: logger.warning(f'concierge: the fyi conversation did not save - {e}')
            # shown IS read: the state is `surfaced`, and it carries the entry's own summary
            for n, i in enumerate(batch, 1): funnel.settle(store, i['key'], 'surfaced', actor, note=None if i.get('sig') else gists.get(n), read=True)
            card['chips'] = chips_for(store, card)
            set_current(store, tid, card['key'], actor)
            record_related(store, tid, card, 'assistant', say, card)
        return {'item': card, 'say': say, 'options': [], 'chips': card['chips'], 'left': len(p['items']) - len(batch)}

    llm = _brain_for(store, tid, llm, trace, cancel, fast=True) if (llm is not None or INTRO_AI) else None   # the facts speak unless asked otherwise
    say, options, wanted, remember_llm = '', [], '', False
    if llm:
        try:
            # the card's structure is code's to state; the explanation itself is COUNSEL's (PW-153)
            ask = ('Introduce the item on the table to the owner. '
                   + ('A report landed: say which and when, and whether it failed - its contents are read with the button, not summarised here. '
                      if item['kind'] == 'report' and not item.get('bad') else '')
                   + ('The card below holds the draft that waits for their yes. ' if item['kind'] in ('review', 'action') else '')
                   + ('The agent is parked on the question in the card. ' if item['kind'] == 'agent' else ''))
            say, options, wanted = _ask(store, llm, tid, item, ask, p['items'])
            remember_llm = True
        except Exception as e: logger.warning(f'concierge: the model pass failed - {e}')
    if not say: say = fallback(item, True)
    chips = chips_for(store, item, wanted)
    with guarded():
        put_down()
        if remember_llm:
            try: _remember_sid(store, tid, llm)
            except Exception as e: logger.warning(f'concierge: the model conversation did not save - {e}')
        # in the chat = read, without exception (the owner, 2026-09-07: "hitting next or done should mark it
        # read and then move on"). A draft waiting on a yes used to be held back unread; walking past one now
        # ends the reply obligation instead - see move_on(), which the Next road calls on the way out.
        funnel.settle(store, item['key'], 'surfaced', actor, note=item.get('sig'), read=True)
        set_current(store, tid, item['key'], actor)                          # on the table, written down (PW-162)
        record_related(store, tid, item, 'assistant', say + (f"\nOPTIONS: {' | '.join(options)}" if options else ''),
                       card_for(item) | {'chips': chips})
    return {'item': item | {'chips': chips}, 'say': say, 'options': options, 'chips': chips, 'left': len(p['items']) - 1}


# What the owner may decide about the thing on the table, as PROPOSALS (PW-123): verb -> (operation kind,
# the button's label, whether confirming it settles the item on the table). Nothing here runs on the words;
# the confirmed proposal runs through server._run_operation, the same handler every entry point uses.
PROPOSALS = {
    'coder': ('task.create_from_message', 'Send to the coding agent', True), 'regular_agent': ('task.create_from_message', 'Send to a regular agent', True),
    'mine': ('task.create_from_message', 'Put it on my list', True),
    'not_ours': ('message.file', 'File it', True), 'not_ours_remember': ('preference.exclude_sender', 'File it and remember this kind', True),
    'not_ours_sender': ('preference.exclude_sender', 'Ignore this sender from now on', True),
    'block_sender': ('preference.sender_rule', 'Add an exclusion rule in Settings', True),
    'archive': ('message.archive', 'Archive it', True),
    'close': ('task.complete', 'Close the task', True), 'done': ('item.settle', 'Mark it handled', True),
    'later': ('item.settle', 'Push it back', True), 'skip': ('item.settle', 'Skip until tomorrow', True),
    'approve': ('review.approve', 'Send the reply', True), 'answer_agent': ('agent.answer', 'Send the answer to the agent', True),
    'stop_agent': ('agent.stop', 'Stop the agent', False), 'rerun': ('report.rerun', 'Run the report again', True),
    'remember': ('memory.remember', 'Remember it', False), 'split': ('task.split', 'Split it in two', False),
    'clear': ('pipe.clear', 'Clear them from the pipe', False), 'setup': ('task.setup', 'Open the walk-through', False),
}
AUTO = ('done', 'skip', 'later', 'close')     # settles what is on the table; nothing leaves, nothing is handed off
# the operations that take the item off the table, so the walk moves on after them (the page reads
# `settles` off the proposal it is holding; a chat comes back a turn later and has only the kind)
SETTLING_KINDS = frozenset(kind for kind, _label, settles in PROPOSALS.values() if settles)
NO_BRAIN = ('I can read you the facts, but I cannot take an instruction without an AI connector - set one up under '
            "Connections, or use the card's own buttons.")


def handoff_task(store, text: str, kind: str = 'coding', actor: str = 'owner', title: str = None, dock_tid: int = None) -> dict:
    """A hand-off with nothing on the table: the owner's words ARE the brief. The confirmed `task.create_from_text`
    lands here - the task is made and the agent started only then (PW-124)."""
    job = str(text or '').strip()
    if not job: raise ValueError('say what the agent should do')
    tid = dock_tid or general.dock_task(store, actor)[0]['TaskId']
    brief = _handoff_brief(store, tid, job)
    made = setup_task(store, brief, actor, title=title or _handoff_title(store, tid, job), kind=kind, agent_job=kind == 'general')
    if kind == 'general':
        session = general.start_session(store, made['taskId'], actor=actor)
        threading.Thread(target=session.send_prompt, args=(brief,), daemon=True).start()
    return made


def _resolve_named(store, phrase: str, item: dict | None) -> str | None:
    """The pile key the model's ON: words name - '?' when they name something that cannot be found."""
    from .routing import tokens
    ref = re.search(r'\bTQ-?0*(\d+)\b', phrase or '', re.I)
    if ref: return f"task:{int(ref.group(1))}" if store.get_task(int(ref.group(1))) else '?'
    words = [w for w in tokens(phrase or '') if w not in _CUES and w not in _FILLER and len(w) > 2]
    hit = (lookup(store, ' '.join(words)) if words else None) or _pile_hit(store, words, item or {})
    return hit or '?'


def open_proposal(store, dock_tid: int) -> dict | None:
    """The proposal on the table - the newest proposal card in this chat whose row is still `proposed`."""
    for c in reversed(general.chat_rows(store, dock_tid)):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('kind') != 'proposal': continue
        op = operations.get(store, card.get('op')) if card.get('op') else None
        return op if op and op.get('status') == 'proposed' else None
    return None


def run_proposal(store, op: dict, actor: str = 'owner') -> dict:
    """Execute a confirmed proposal outside a request: the SAME handler the page's Confirm button runs,
    with the after-work (learning, auto-drafts, closing a session) drained here instead of by FastAPI.

    The handlers are route functions and they read the app's own store, which is this one in a running
    Taskuary; a test that hands a different store must patch `server.store` as the API tests do."""
    import asyncio
    from fastapi import BackgroundTasks
    from .server import _run_operation
    bg = BackgroundTasks()
    out = operations.execute(store, op['id'], op['version'], lambda: _run_operation(op, bg), actor)
    if bg.tasks:
        try: asyncio.run(bg())
        except Exception as e: logger.warning(f'the work after {op["id"]} did not finish: {e}')
    return out


def confirm_open(store, tid: int, item: dict | None, cancelled: bool, actor: str = 'owner') -> dict:
    """The owner's yes (or no) to the card already in front of them, in words instead of a click.

    A chat has no buttons at all, so without this the phone could never send a drafted reply. The
    desktop had the same hole from the other side: a typed "yes go ahead" was read as the decision
    again, which only re-proposed the same operation (version 2) and changed nothing."""
    prop = open_proposal(store, tid)
    if not prop:
        say_ = 'Nothing is waiting on your yes just now.'
        record_related(store, tid, item, 'assistant', say_)
        return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
    if cancelled:
        operations.cancel(store, prop['id'], actor)
        say_ = f"Left alone - {describe_op(store, prop)[0].lower()} is not happening. Nothing was touched."
        record_related(store, tid, item, 'assistant', say_)
        return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
    out = run_proposal(store, prop, actor)
    return {'say': receipt(store, out, actor), 'options': [], 'chips': [], 'decision': {'verb': 'confirm'},
            'executed': {'id': prop['id'], 'kind': prop['kind'], 'status': out.get('status')},
            'settled': out.get('status') == 'done' and prop['kind'] in SETTLING_KINDS}


def _where(it: dict) -> str:
    title = str(it.get('title') or '')
    who = it.get('who') if it.get('who') and not title.lower().startswith(str(it['who']).lower()) else ''   # "Assistant - Assistant idea"
    return f"{who + ' - ' if who else ''}{title}{' (' + it['ref'] + ')' if it.get('ref') else ''}".strip()


def _brief_from_item(store, item: dict) -> str:
    """What to tell an agent when the owner pressed a button instead of typing: the item itself - what it
    is, who it is from, and everything already known about it (the same facts the assistant reads)."""
    return f"Take this on and report back what you find: {_where(item) or 'the item below'}.\n\n{facts(store, item)}".strip()


def propose_for(store, dock_tid: int, decision: dict, item: dict | None, text: str, actor: str = 'owner',
                elsewhere: bool = False, table: dict | None = None) -> dict:
    """The owner's decision as a proposal row (operations.propose): the exact target and parameters, a label
    for its button, and the line that says what WILL happen. A decision that changes the proposal already on the
    table revises it (a new confirmation version) instead of stacking a second one (PW-123)."""
    verb = decision['verb']; kind, label, settles = PROPOSALS[verb]
    d_text = (decision.get('text') or '').strip()
    it = item or {}
    target, params, note = None, {}, ''
    if verb in ('coder', 'regular_agent', 'mine'):
        want = {'coder': 'coding', 'regular_agent': 'general', 'mine': 'task'}[verb]
        if it.get('mid'): target, params = it['mid'], {'kind': want, 'instructions': d_text or None}
        elif verb == 'mine': raise ValueError('nothing is on the table to put on your list')
        else:
            # A hand-off asked for by BUTTON carries no sentence, so the brief is the item itself. Without
            # this the chip proposed a task with no text at all and operations refused it outright
            # ('task.create_from_text needs text') - an offered word that did nothing.
            job = (d_text or text or '').strip() or _brief_from_item(store, it)
            title = _handoff_title(store, dock_tid, job) if (d_text or text or '').strip() else (it.get('title') or 'Look into this')
            kind, target, params = 'task.create_from_text', 0, {'kind': want, 'text': job, 'title': title}
            label = 'Start a coding agent on it' if want == 'coding' else 'Start a regular agent on it'
    elif verb == 'not_ours': target, params = it.get('mid'), {'learn': False}
    elif verb in ('not_ours_remember', 'not_ours_sender'): target, params = it.get('mid'), {'scope': 'subject' if verb == 'not_ours_remember' else 'sender'}
    elif verb == 'block_sender': target = it.get('mid')      # the rule is keyed on the sender of THIS message
    elif verb == 'archive': target = it.get('mid')
    elif verb == 'close': target = it.get('tid')
    elif verb in ('done', 'later', 'skip'):
        if not it.get('key'): raise ValueError('nothing is on the table')
        # "done" said about an agent parked on a question is not a row to tick: the job is over, so the task
        # closes and the session ends with it - the shared task.complete road does both
        if verb == 'done' and it.get('kind') == 'agent' and it.get('tid'): kind, label, target, params = 'task.complete', 'Close the task and stop its agent', it['tid'], {'agent': True}
        else: target, params = it.get('tid') or 0, {'key': it['key'], 'verb': verb, 'tid': it.get('tid'), 'rid': it.get('rid'), 'kind': it.get('kind')}
    elif verb == 'approve': target = it.get('rid')
    elif verb == 'answer_agent': target, params = it.get('tid'), {'text': d_text or 'yes'}
    elif verb == 'stop_agent':
        end = _agent_task(store, item, text)
        if not end: raise ValueError('no agent is running right now - nothing to stop')
        asked_wrap = wrap = bool(re.search(r"\b(wrap|finished|it'?s done)\b", text, re.I))
        if wrap:                                     # a wrap writes the report FROM the transcript: without one there is nothing to wrap
            from . import terminal as term
            try: wrap = bool((term.transcript_for(store, end) or ('',))[0].strip())
            except Exception: wrap = False
        target, params, label = end, {'wrap': wrap}, ('Wrap it up' if wrap else label)
        if asked_wrap and not wrap: note = ' There is no transcript to write a report from yet, so there is nothing to wrap - this stops the agent and the task stays open.'
    elif verb == 'rerun': target = it.get('source_id')
    elif verb == 'remember':
        if not d_text: raise ValueError('remember what? Say the fact and I will keep it')
        target, params = 0, {'note': d_text}
    elif verb == 'split': target, params = it.get('tid'), {'text': text, 'key': it.get('key')}
    elif verb == 'clear': target, params = 0, {'text': text, 'hint': _last_owner_words(store, dock_tid, text)}
    elif verb == 'setup': target, params = 0, {'text': d_text or text}
    if target is None: raise ValueError(f"there is nothing to {SAYS_VERB.get(verb, verb)} on this one")
    params = {k: v for k, v in params.items() if v is not None}
    prev = open_proposal(store, dock_tid)
    if prev and prev['kind'] == kind and int(prev['target']) == int(target): op = operations.revise(store, prev['id'], params, actor)
    else:
        if prev: operations.cancel(store, prev['id'], actor)
        op = operations.propose(store, kind, target, params, actor)
    where = _where(it) if it else (params.get('title') or _cut(params.get('text') or params.get('note') or '', 120))
    summary = f"{where} → {label[0].lower() + label[1:]}"
    lead = (f"That is {where}, not the one on the table - so I am proposing it there; {(table or {}).get('ref') or 'the one on the table'} is untouched. "
            if elsewhere else '')
    head = f"Changed to: {label} - {summary}" if op['version'] > 1 else f"{label}: {summary}"
    say_ = lead + f"{head}.{note} Nothing has been started - confirm below, or tell me what to change."
    return {**op, 'verb': verb, 'label': label, 'summary': summary, 'settles': bool(settles and not elsewhere),
            'key': it.get('key'), 'ref': it.get('ref'), 'tid': it.get('tid'), 'say': say_}


def propose_direct(store, verb: str, key: str, text: str = '', actor: str = 'owner', table: bool = False) -> dict:
    """A card's own button on ONE entry (PW-151): the same proposal the words would make, without the interpreter -
    the target is explicit. From a card it never settles what is on the table and the entry's siblings are not
    touched; from the chips under the composer (`table`) the entry IS the table, so a plain verb runs at once and
    settles it, exactly as the typed word would."""
    if verb not in PROPOSALS: raise ValueError(f'{verb} is not something a card proposes')
    item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    if not item: raise ValueError('that one is not in the pipe any more')
    # kind routes the task (2026-08-30): a general task goes to a regular agent, whatever the chip is called
    if verb == 'coder' and item.get('tid') and (store.get_task(item['tid']) or {}).get('Kind') == 'general': verb = 'regular_agent'
    tid = general.dock_task(store, actor)[0]['TaskId']
    why = cannot(item, verb, store)
    if why: raise ValueError(why)
    record_related(store, tid, item, 'user', f"{PROPOSALS[verb][1]}: {item.get('title') or item.get('ref') or key}")
    prop = propose_for(store, tid, {'verb': verb, 'text': text or ''}, item, text or '', actor, table=item if table else None)
    prop['settles'] = bool(table and PROPOSALS[verb][2])
    if table and verb in AUTO: prop.update(auto=True, say=f"{prop['label']} - {_where(item)}.")
    record_related(store, tid, item, 'assistant', prop['say'], {'kind': 'proposal', 'key': prop.get('key'), 'title': prop['label'], 'op': prop['id'],
                                                               'tid': prop.get('tid'), 'ref': prop.get('ref'), 'lane': item.get('lane')})
    return prop


# ── setting things up from the chat (PW-194..197): sorted and gathered by AI, confirmed, created through the tabs' roads ──
# a token typed into the chat is not kept (PW-196): what looks like one is replaced before any row is written
_SECRETISH = re.compile(r"(?<![\w-])(?:xox[abpr]-[\w-]{10,}|sk-[A-Za-z0-9_-]{16,}|gh[pous]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{12,}"
                        r"|ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|[A-Fa-f0-9]{32,})(?![\w-])")
SECRET_WORDS = re.compile(r'(secret|token|password|passwd|api[_ -]?key|refresh|private[_ -]?key|client[_ -]?secret|bearer)', re.I)
SETUP_QUESTIONS = 'setup_questions'
SETUP_SORT_SYSTEM = ('You sort one set-up request from the owner of a small company\'s assistant. Answer JSON only: '
                     '{"kind": "report" | "connection" | "investigate", "provider": "<connector type or null>", "why": "<one sentence>"}. '
                     'A REPORT reads connected systems on a schedule and files what it found (a check, a digest, a scheduled agent job). '
                     'A CONNECTION adds or configures a system Taskuary talks to (mail, chat, a database, a books system, an AI provider) - '
                     'name its type from connector_types when you can. INVESTIGATE is a set-up that needs real digging first - a portal to '
                     'read, systems to choose between, several moving parts - where a walk-through with an agent is the honest next step. '
                     'A simple configuration is never investigate.')


def redact(text: str) -> str: return _SECRETISH.sub('[redacted]', str(text or ''))


def _compose_llm(store, trace=None, cancel=None):
    try: return llm_mod.build_llm(store, trace=trace, cancel=cancel)
    except Exception as e:
        logger.warning(f'concierge: no composer brain - {e}'); return None


def sort_setup(store, text: str, llm) -> dict:
    """What kind of set-up the words ask for, by the model: a report, a connection (and to what), or digging."""
    from . import compose
    types = sorted(store_mod.DEFAULT_ROLES)
    try: out = compose._json(llm(SETUP_SORT_SYSTEM, json.dumps({'request': text, 'connector_types': types}), max_tokens=300)) or {}
    except Exception as e:
        logger.warning(f'concierge: the set-up sort failed - {e}'); out = {}
    kind = str(out.get('kind') or 'report').lower(); prov = str(out.get('provider') or '').lower().strip()
    return {'kind': kind if kind in ('report', 'connection', 'investigate') else 'report', 'provider': prov if prov in types else None,
            'why': str(out.get('why') or '')[:300]}


def _pending_setup(store, tid: int) -> dict | None:
    """The set-up questions asked last turn, if the last assistant line asked them."""
    rows = [c for c in general.chat_rows(store, tid) if c.get('ActorType') == general.ASSISTANT_TYPE]
    card = _card_of(rows[-1]) if rows else None
    return card if card and card.get('kind') == SETUP_QUESTIONS else None


def _propose_raw(store, dock_tid: int, kind: str, target: int, params: dict, label: str, summary: str, tail: str, actor: str,
                 item: dict | None = None) -> dict:
    """A proposal that is not about the item on the table: the same revise-or-replace rule as propose_for, recorded as a card."""
    prev = open_proposal(store, dock_tid)
    if prev and prev['kind'] == kind and int(prev['target']) == int(target): op = operations.revise(store, prev['id'], params, actor)
    else:
        if prev: operations.cancel(store, prev['id'], actor)
        op = operations.propose(store, kind, target, params, actor)
    text = (f"Changed to: {label} - {summary}" if op['version'] > 1 else f"{label}: {summary}") + f". {tail}"
    record_related(store, dock_tid, item, 'assistant', text, {'kind': 'proposal', 'key': None, 'title': label, 'op': op['id'], 'tid': None, 'ref': None})
    return {**op, 'verb': 'setup', 'label': label, 'summary': summary, 'settles': False, 'key': None, 'ref': None, 'tid': None, 'say': text}


def _schedule_words(cfg: dict) -> str:
    if cfg.get('cron'): return f"cron {cfg['cron']}"
    if cfg.get('daily_at'): return f"daily at {cfg['daily_at']}"
    if cfg.get('every_minutes'): return f"every {cfg['every_minutes']} minutes"
    if cfg.get('every'): return str(cfg['every'])
    return 'on start-up only' if cfg.get('on_startup') else 'no schedule - run it by hand'


def report_facts(cfg: dict) -> dict:
    """What the confirmation box says about a report (PW-195): source, inputs, schedule, enabled state, behaviour, delivery."""
    srcs = cfg.get('sources') or []
    src = ', '.join(str(x.get('type') or '?') for x in srcs if isinstance(x, dict)) if srcs else str(cfg.get('type') or '')
    return {'title': str(cfg.get('title') or ''), 'source': src, 'inputs': _cut(str(cfg.get('query') or cfg.get('object') or cfg.get('url') or cfg.get('path') or cfg.get('prompt') or ''), 160),
            'summary_instructions': _cut(str(cfg.get('ai_prompt') or ''), 160) or 'none - the raw result is filed',
            'schedule': _schedule_words(cfg) + (f" ({cfg['tz']})" if cfg.get('tz') else ''),
            'enabled': 'yes - it runs on its schedule once created', 'triage': 'triage reads it' if cfg.get('triage') else 'informational - filed on the Timeline, not triaged',
            'delivery': str((cfg.get('deliver') or {}).get('to') or '') or 'the Timeline only'}


def _walkthrough(store, tid: int, ask: str, item: dict | None, actor: str, lead: str) -> dict:
    """The set-up needs digging: a walk-through with the regular agent, proposed with the reason (PW-197)."""
    prop = propose_for(store, tid, {'verb': 'setup', 'text': ask}, item, ask, actor)
    prop['say'] = f"{lead} {prop['say']}"
    record_related(store, tid, item, 'assistant', prop['say'], {'kind': 'proposal', 'key': None, 'title': prop['label'], 'op': prop['id'], 'tid': None, 'ref': None})
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def setup_turn(store, tid: int, text: str, ask: str, item: dict | None, actor: str = 'owner', llm=None,
               trace=None, cancel=None) -> dict:
    """A set-up asked for in the chat (PW-194): sorted by the model, gathered by the composer - its questions come back as
    questions and the next words answer them - and put in front of the owner as a proposal that the shared Reports /
    Connections road creates on the click. Secrets never pass through here (PW-196); digging is a walk-through (PW-197)."""
    rec = lambda body, card=None: record_related(store, tid, item, 'assistant', body, card)
    cllm = llm or _compose_llm(store, trace, cancel)
    if not cllm:
        say_ = 'Setting that up needs an AI connector - Connections → AI - or the Reports and Connections tabs, where the forms are. Nothing is set up.'
        rec(say_); return {'say': say_, 'options': [], 'decision': None}
    pending, answers = _pending_setup(store, tid), None
    if pending:
        ask, answers = pending['ask'], {'questions': pending.get('questions') or [], 'reply': text}
        sort = sort_setup(store, f"{ask}. The owner answered: {text}", cllm)
    else: sort = sort_setup(store, ask, cllm)
    if sort['kind'] == 'investigate':
        return _walkthrough(store, tid, ask, item, actor, f"This needs digging before it can be configured{' - ' + sort['why'] if sort.get('why') else ''}.")
    if sort['kind'] == 'connection':
        return _propose_connection(store, tid, ask, sort.get('provider'), item, actor)
    from . import compose
    out = compose.compose(store, ask, cllm, answers=answers)
    if out.get('questions'):
        qs = out['questions']
        say_ = 'Before I put it together: ' + ' '.join(f"({n}) {q}" for n, q in enumerate(qs, 1)) + ' Nothing is set up yet.'
        rec(say_, {'kind': SETUP_QUESTIONS, 'ask': ask, 'questions': qs})
        return {'say': say_, 'options': [], 'decision': None}
    if out.get('error') or not out.get('config'):                        # a configuration the composer itself could not stand behind
        return _walkthrough(store, tid, ask, item, actor, f"I could not configure that from here ({out.get('error') or 'no configuration came back'}).")
    cfg, facts = out['config'], report_facts(out['config'])
    params = {'config': cfg, **facts}
    looked = ', '.join(str(x) for x in (out.get('looked_at') or [])[:4])
    tail = ((out.get('explain') + ' ') if out.get('explain') else '') + '; '.join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items() if k != 'title' and v)            + (f'. I read {looked} to build it' if looked else '')            + '. Nothing is saved - confirm below, tell me what to change, or preview a dry run first.'
    prop = _propose_raw(store, tid, 'report.create', 0, params, 'Create the report', f"{facts['title']} ({cfg.get('type')})", tail, actor, item)
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def _propose_connection(store, tid: int, ask: str, provider: str | None, item: dict | None, actor: str) -> dict:
    """A connection (PW-196): provider and non-secret configuration, the authority it will hold and what that unlocks;
    the secret is never asked for here - the card takes it, securely - and it stays off until the owner turns it on."""
    from . import scopes
    rec = lambda body, card=None: record_related(store, tid, item, 'assistant', body, card)
    if not provider:
        types = sorted(store_mod.DEFAULT_ROLES)
        say_ = ('Which system is it? ' + ', '.join(types) + ' - name it and I will put the connection in front of you. '
                'A password, token or key never goes here; it goes on the card. Nothing is set up yet.')
        rec(say_, {'kind': SETUP_QUESTIONS, 'ask': ask, 'questions': ['Which system should I connect?']})
        return {'say': say_, 'options': [], 'decision': None}
    existing = store.get_connector_by_type(provider)
    cid = int(existing['ConnectorId']) if existing and not existing.get('Active') else 0
    name = (existing or {}).get('Name') if cid else f"{provider.title()} (from the chat)"
    scope = scopes.default_scope(provider)
    params = {'type': provider, 'name': name, 'scope': scope, 'permissions': ', '.join(scopes.actions_at(scope)) or 'read',
              'secret': 'never here - the card asks for it securely', 'starts': 'stays off until you turn it on after authorizing'}
    tail = (f"A {provider} connection with {scope} authority ({params['permissions']}). I never take a token or password in this chat: "
            'once the card exists, sign in or paste the secret there and run its Test. It stays off - nothing polls, nothing starts - '
            'until you turn it on. Nothing is created - confirm below, or tell me what to change.')
    prop = _propose_raw(store, tid, 'connection.create', cid, params, 'Create the connection', f"{name} ({provider})", tail, actor, item)
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def describe_op(store, op: dict) -> tuple:
    """(the button's label, what it was about) for a proposal row - the receipt's two facts."""
    kind, p, tk, target = op.get('kind'), op.get('params') or {}, op.get('targetKind'), op.get('target')
    by_kind = {kind_: [PROPOSALS[v][1] for v in PROPOSALS if PROPOSALS[v][0] == kind_][0] for kind_ in {PROPOSALS[v][0] for v in PROPOSALS}}
    label = by_kind.get(kind, kind)
    if kind == 'task.create_from_message': label = {'coding': 'Send to the coding agent', 'general': 'Send to a regular agent'}.get(str(p.get('kind')), 'Put it on my list')
    if kind == 'task.create_from_text': label = 'Start a coding agent on it' if p.get('kind') == 'coding' else 'Start a regular agent on it'
    if kind == 'preference.exclude_sender': label = 'Silence this sender' if p.get('scope') == 'sender' else 'File it and remember this kind'
    if kind == 'item.settle': label = {'later': 'Push it back', 'skip': 'Skip until tomorrow'}.get(str(p.get('verb')), 'Mark it handled')
    if kind == 'task.complete' and p.get('agent'): label = 'Close the task and stop its agent'
    if kind == 'agent.stop' and p.get('wrap'): label = 'Wrap it up'
    if kind == 'report.create': label = 'Create the report'
    if kind == 'connection.create': label = 'Create the connection'
    ref = ''
    try:
        if tk == 'task' and target: ref = task_ref(int(target))
        elif tk == 'message' and target:
            m = store.get_message(int(target)) or {}
            ref = task_ref(m['TaskId']) if m.get('TaskId') else (m.get('Subject') or '')
        elif tk == 'review' and target:
            rv = store.get_review(int(target)) or {}
            ref = task_ref(rv['TaskId']) if rv.get('TaskId') else f'rv{target}'
        elif tk == 'item': ref = task_ref(int(p['tid'])) if p.get('tid') else str(p.get('key') or '')
        elif tk == 'source' and target: ref = f'report {target}'
        elif tk == 'report': ref = str(p.get('title') or '')
        elif tk == 'connector': ref = str(p.get('name') or '')
    except Exception: ref = ''
    return label, ref


def _outcome_line(kind: str, p: dict, o: dict | None) -> str:
    """What the handler reported, in the words the sweep, the split and the hand-off used to say for themselves."""
    o = o or {}
    if kind == 'pipe.clear':
        if o.get('cleared'):
            return (f" Cleared {o['cleared']} from the pipe - {', '.join((o.get('titles') or [])[:3])}{'…' if o['cleared'] > 3 else ''}. "
                    'Read, not deleted; they are on the Timeline.'
                    + (f" {o['stuck']} would not move just then and {'is' if o['stuck'] == 1 else 'are'} still in the pipe"
                       ' - say it again and they go too.' if o.get('stuck') else '')
                    + (f" And remembered as {'a rule' if len(o['rules']) == 1 else str(len(o['rules'])) + ' rules'}: " + '; '.join(o['rules'])
                       + ' - the next ones file themselves, and anything that actually asks you something still reaches you.' if o.get('rules') else '')
                    + (' And that sender goes straight past you from now on.' if o.get('remember') and not o.get('rules') else ''))
        if o.get('rules'):
            return (' Nothing of those is in the pipe right now - but it is noted: ' + '; '.join(o['rules'])
                    + ' files itself from now on. They stay on the Timeline, and anything that actually asks you something still reaches you.')
        return ' Nothing in the pipe matches those words.'
    if kind == 'task.split':
        if o.get('newRef'): return f" {o.get('ref') or 'It'} keeps \"{o.get('kept') or ''}\" and {o['newRef']} is \"{o.get('title') or ''}\" - each is its own job now."
        return ' I can only see one ask in that one' + (f" - {o['why']}" if o.get('why') else '') + '. It stays as it was.'
    if kind == 'task.create_from_text' and o.get('ref'):
        return f" {o['ref']} - \"{o.get('title') or ''}\" is with the {'coding' if p.get('kind') == 'coding' else 'regular'} agent now; it comes back here when it is done."
    if kind == 'task.setup' and o.get('ref'):
        return (f" {o['ref']} - \"{o.get('title') or ''}\" is open as a walk-through: a conversation with the assistant, nothing built, no repository touched. "
                'Open it when you want to start; its browser opens beside the assistant.')
    if kind == 'task.create_from_message' and p.get('kind') in ('coding', 'general'):
        if o.get('existing'): return f" {o.get('agent') or 'An agent'} was already on it."
        if o.get('started') or o.get('chat'): return f" {o.get('agent') or 'The agent'} is on it - moving on."
    if kind == 'item.settle' and o.get('closed'): return f" {task_ref(int(o['closed']))} closed."
    if kind == 'agent.stop' and not p.get('wrap'): return ' The task stays open - say close it when you want it closed.'
    if kind == 'memory.remember': return ' A memory settles nothing: the walk is where it was.'
    if kind == 'report.create' and o.get('sourceId'):
        return f" \"{o.get('title')}\" is on the Reports tab{' and runs on its schedule' if o.get('enabled') else ', switched off'}."
    if kind == 'connection.create' and o.get('connectorId'):
        return (f" The {o.get('type')} card \"{o.get('name')}\" is {o.get('state')} - finish it on the card (sign in or paste the secret there), "
                'then Test; it stays off until you turn it on.')
    if kind == 'task.complete' and o.get('already'): return ' It was closed already.'
    return ''


def receipt(store, op: dict, actor: str = 'owner') -> str:
    """After the click: the fact of what happened, in the chat - never before it ran (PW-125)."""
    label, ref = describe_op(store, op)
    st = op.get('status')
    if st == 'done':
        line = (f"{'Already done' if op.get('duplicate') else 'Done'} - {label}{' · ' + ref if ref else ''}."
                + ('' if op.get('duplicate') else _outcome_line(op.get('kind'), op.get('params') or {}, op.get('outcome'))))
    elif st == 'error': line = f"Not done - {op.get('error') or 'it failed'}. {ref or 'It'} is where it was."
    else: line = f"Not done - {op.get('error') or st}. {ref or 'It'} is where it was."
    # only what THIS chat proposed is its news. A close from the Tasks page or the wall used to be narrated
    # here too - and opened a fresh chat to say it in (the owner, 2026-09-07: "no one asked you to do that")
    raw = store.get_settings().get('assistant_dock_task_id')
    dock_tid = int(raw) if str(raw or '').isdigit() else None
    if not dock_tid or not _chat_proposed(store, dock_tid, op.get('id')): return line
    record(store, dock_tid, 'assistant', line)
    return line


def _chat_proposed(store, dock_tid: int, oid: str) -> bool:
    for c in general.chat_rows(store, dock_tid):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('kind') == 'proposal' and card.get('op') == oid: return True
    return False


def say(store, text: str, key: str = None, llm=None, actor: str = 'owner', trace=None, cancel=None, item: dict | None = None) -> dict:
    """The owner's words, answered briefly - about the item on the table when there is one. The MODEL interprets
    them (PW-121): a question is answered, a subject named is pulled in, and a decision becomes a PROPOSAL the
    owner confirms (PW-123/124) - except Next, which moves the walk and marks nothing, and a reply request, which
    drafts at once and sends nothing (PW-126/128). No phrase table decides anything."""
    text = str(text or '').strip()
    if not text: raise ValueError('say something')
    task, _ = general.dock_task(store, actor)
    tid = task['TaskId']
    p = funnel.pile(store)
    if item is None: item = funnel.next_item(store, key, items=funnel.full_items(store)) if key else None   # the route already built it
    record_related(store, tid, item, 'user', text)
    rec = lambda role, body, card=None: record_related(store, tid, item, role, body, card)
    llm = _brain_for(store, tid, llm, trace, cancel)
    if not llm:
        say_ = f"{fallback(item, False, p['items'])} {NO_BRAIN}".strip()
        rec('assistant', say_)
        return {'say': say_, 'options': [], 'chips': chips_for(store, item) or walk_chips(len(p['items'])), 'decision': None}
    reply, options, decision, call, did_read = '', [], None, None, False
    try:
        from . import handbook as hub
        hub_context = hub.block(store, text, actions=False) if hub.enabled(store) else ''
        from . import toolcatalog
        system = (_system(store, llm) + '\n\n' + toolcatalog.block(store)
                  + (f'\n\n{hub.ASSISTANT_LINE}' if hub.enabled(store) else ''))
        raw = str(llm(system,
                      f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(p['items'], coming=False)}\n\n{facts(store, item)}{trouble(store, text)}\n\n"
                      + (hub_context + '\n\n' if hub_context else '')
                      + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
                      + f"The owner says: {text}\nAnswer them, briefly. If this is a decision about the item on the table, name it (DECIDE line).",
                      max_tokens=MAX_TOKENS) or '').strip()
        if hub.enabled(store): raw = hub.publish_assistant_entries(store, tid, raw, 'assistant')
        raw, call = parse_call(raw)
        # A LOOK-UP runs at once and comes straight back, because it changes nothing and waits for
        # nobody. The model then answers with what it read - one round only, so a question can never
        # become an unbounded search (the owner, 2026-09-07: "read should be immediate").
        for _ in range(READ_ROUNDS):
            if not (call and toolcatalog.is_read(call['kind'])): break
            did_read = True
            found = read_op(store, call['kind'], call['params'])
            trace and trace('tool', call['kind'], {'params': call['params']})
            raw = str(llm(system, f"You looked up {call['kind']} and it says:\n{_cut(found, 6000)}\n\n"
                                  f"The owner asked: {text}\nAnswer them with what you just read, briefly.",
                          max_tokens=MAX_TOKENS) or '').strip()
            raw, call = parse_call(raw)
        # the budget is spent and it still wants to read: that is as far as this turn goes. A read is
        # never handed on to call_turn, which only knows operations that CHANGE something.
        if call and toolcatalog.is_read(call['kind']): call = None
        raw, decision = parse_decision(raw)
        reply, options = parse_options(raw)
        if not in_character(reply):
            logger.info('concierge: the voice broke character - answering with the facts instead')
            reply, options = '', []
        _remember_sid(store, tid, llm)
    except Exception as e: logger.warning(f'concierge: the model pass failed - {e}')
    if call and not _CORRECTION.search(text):
        try: return call_turn(store, tid, call, item, text, actor)
        except ValueError as e:
            say_ = f"I could not put that in front of you - {e}."
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
    # The MODEL may answer a correction by moving on - it did: "that's not a fail, it says all clear?" came back
    # as DECIDE: next, so the one thing the owner said was never taken (2026-09-03).
    if decision and decision['verb'] in ('next', 'skip', 'later', 'done') and _CORRECTION.search(text): decision = None
    # words that point at something else pull it in and talk about THAT (everything is the chat)
    if not decision and not did_read:
        found = lookup(store, text)
        if found and found != key:
            out = surface(store, found, llm, actor, None, trace, cancel)
            if out.get('item'): return out
    verb = (decision or {}).get('verb')
    # their yes to the card already waiting on it - the button, said in words (the only road a phone has)
    if verb in ('confirm', 'cancel'): return confirm_open(store, tid, item, verb == 'cancel', actor)
    # a batch of fyi is one thing on the table: "not ours" about a handful of fyi is what "read" means
    if decision and item and item.get('kind') == 'fyis' and not decision.get('on') and verb in ('not_ours', 'not_ours_remember', 'archive', 'close'):
        decision, verb = {**decision, 'verb': 'done'}, 'done'
    # NOTHING ON THE TABLE: next / done / later move the WALK; a verb that needs something to act on says so
    if decision and not item:
        if verb in ('next', 'done', 'skip', 'later'):
            only = 'mail' if re.search(r'\b(mail|inbox|e-?mail|what came in)\b', text, re.I) else None
            return surface(store, None, llm, actor, only, trace, cancel)
        if verb in NEEDS:                              # a hand-off is NOT in NEEDS: the owner's words are its brief
            say_ = ('Nothing is on the table. Say next and I will bring the next thing up, or name the one '
                    'you mean - the sender or its TQ ref - and I will do it there.')
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': walk_chips(len(p['items'])), 'decision': None}
    # a switch is already a proposal in Review (proposals.py); a hand-off to a person is a DRAFT for approval
    if decision and verb == 'setting': return _carry_out(store, tid, text, {**decision, 'said': text}, item, actor)
    if decision and verb == 'forward' and item:
        who = (decision.get('text') or '').split(':')[0].strip()
        return _carry_out(store, tid, text, {'verb': 'forward', 'text': decision.get('text') or '', 'who': who, 'said': text}, item, actor)
    # the words name ANOTHER subject: resolve it and propose THERE, or ask - never on what happens to be open
    target_item, elsewhere = item, False
    if decision and item and decision.get('on'):
        other = _resolve_named(store, decision['on'], item)
        if other == '?':
            say_ = (f"Careful - you named something that is not what is on the table. On the table is {_where(item)}, "
                    'and I could not find what you meant. Say it again with the sender or the ref and I will do it there; nothing has been touched.')
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        # one entry of the fyi handful is a thing of its own (PW-126): the verb lands on it, its siblings stay unread
        members = {e.get('key'): e for e in (item.get('items') or [])} if item.get('kind') == 'fyis' else {}
        it2 = members.get(other) or funnel.next_item(store, other) or funnel.item_for_key(store, other)
        if it2 and it2.get('key') != item.get('key'): target_item, elsewhere = it2, True
    if decision and verb and target_item:
        why = cannot(target_item, verb, store)
        if why:
            rec('assistant', why)
            return {'say': why, 'options': [], 'chips': chips_for(store, target_item), 'decision': None}
    # the two immediate exceptions the owner approved: Next moves the walk (PW-128); a reply DRAFTS (PW-126)
    if decision and verb == 'next' and item:
        move_on(store, item['key'], actor)
        rec('assistant', RECEIPTS['next'])
        return {'say': RECEIPTS['next'], 'options': [], 'chips': [], 'decision': {'verb': 'next'}}
    if decision and verb in ('reply', 'redraft') and target_item:
        rec('assistant', RECEIPTS[verb])
        d = {'verb': verb, 'text': decision.get('text') or ''}
        if elsewhere: d['target'] = card_for(target_item)
        return {'say': RECEIPTS[verb], 'options': [], 'chips': [], 'decision': d}
    if decision and verb == 'setup':                                     # a report, a connection: gathered, then confirmed (PW-194)
        return setup_turn(store, tid, text, decision.get('text') or text, item, actor, trace=trace, cancel=cancel)
    if decision and verb in PROPOSALS:
        try: prop = propose_for(store, tid, decision, target_item, text, actor, elsewhere=elsewhere, table=item)
        except ValueError as e:
            say_ = f"I could not put that in front of you - {e}."
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, target_item), 'decision': None}
        # a plain verb on the item on the table runs at once - the page presses the button itself (the owner,
        # 2026-09-07: "I did already - it should close it; only confirm when you are not sure"). A hand-off, a
        # send, a rule or a verb aimed elsewhere still waits for the button.
        if verb in AUTO and not elsewhere:
            prop.update(auto=True, say=f"{prop['label']} - {_where(target_item or {})}.")
        rec('assistant', prop['say'], {'kind': 'proposal', 'key': prop.get('key'), 'title': prop['label'], 'op': prop['id'],
                                        'tid': prop.get('tid'), 'ref': prop.get('ref'), 'lane': (target_item or {}).get('lane')})
        return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}
    if not reply: reply = fallback(item, False, p['items'])
    chips = chips_for(store, item) or walk_chips(len(p['items']))
    rec('assistant', reply + (f"\nOPTIONS: {' | '.join(options)}" if options else ''))
    return {'say': reply, 'options': options, 'chips': chips, 'decision': None}


def act(store, key: str, verb: str, actor: str = 'owner', llm=None, hours: float = None) -> dict:
    """The verbs that need the pile's own knowledge: a follow-up or a task from a candidate the
    assistant never posted, the owner's done / later / skip. Everything else - approving a draft,
    answering an agent, dispatching to the coder, not-ours - is the existing endpoint the card calls."""
    if verb in ('done', 'later', 'skip', 'ack'): return funnel.settle(store, key, verb, actor, hours)
    item = funnel.next_item(store, key) or {}
    a = item.get('action') or {}
    if verb == 'followup':
        if item.get('idea'):
            from . import assistant
            out = assistant.act(store, item['idea'], 'followup', actor, llm)
        elif a.get('mid'):
            from . import assistant
            out = assistant.nudge(store, a['mid'], item.get('title') or 'follow up', actor, llm)
        else: raise ValueError('nothing to follow up on here')
        funnel.settle(store, key, 'done', actor); return out
    if verb == 'task':
        if item.get('idea'):
            from . import assistant
            out = assistant.act(store, item['idea'], 'task', actor, llm)
        elif a.get('mid') or item.get('mid'):
            from . import ingest
            tid = ingest.task_from_message(store, a.get('mid') or item['mid'], actor, 'coding')
            out = {'taskId': tid, 'ref': task_ref(tid)}
        else: raise ValueError('nothing to make a task from here')
        funnel.settle(store, key, 'done', actor); return out
    if verb == 'dismiss':
        if item.get('idea'):
            from . import assistant
            assistant.act(store, item['idea'], 'dismiss', actor)
        return funnel.settle(store, key, 'done', actor, note='dismissed')
    raise ValueError(f'unknown verb: {verb}')

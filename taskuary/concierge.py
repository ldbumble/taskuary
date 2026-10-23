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
from collections import Counter
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from urllib.parse import quote
from loguru import logger

from . import kinds as task_kinds
from .timewords import plural
from . import funnel, general, llm as llm_mod, store as store_mod, toolcatalog
from .redact import scrub as _scrub
from .assistant import _ts
from . import asks, buttons, lanes, operations, timewords, workerstate as ws, words as places
from .store import task_ref

MAX_TOKENS, TURNS, FACT_CHARS = 380, 10, 1_600
# where the owner's own words start in the prompt - the demo's scripted brain reads them by this same constant (demo.brain), and grepped
# for "USER: " while this said "The owner says:", so it never saw the question and gave every ask one line (2026-10-19 UI walk)
OWNER_SAYS = 'The owner says: '
READ_ROUNDS = 3          # a bucket, then a look-up, then one more - never an open-ended crawl (tools are disclosed on demand)
LAST_READ = ('That was your last look-up for this turn - there is no other. Answer now with what you have. If nothing '
             'written down here answers it and it needs somebody to go and find out - research, a repository, a website - '
             'say so in one line and CALL the hand-off: regular_agent to research or read, coding_agent for work in a repository.')
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
# A CALL names an operation out of the registry itself (toolcatalog) instead of a verb out of prose.
# It exists for the targets a verb cannot say: a SET, described rather than listed.
_CALL = re.compile(r'\n?\s*CALL:\s*(\{.*\})\s*$', re.I | re.S)
# what the owner can decide about the thing on the table - each is a button the card already has
VERBS = ('reply', 'approve', 'not_ours', 'not_ours_sender', 'block_sender', 'remember', 'coding_agent', 'regular_agent', 'mine', 'close', 'stop_agent',
         'chase', 'let_go', 'elsewhere',                 # the slipped card's answers (spec 2026-10-12)
         'accept_invite', 'decline_invite', 'propose_time', 'find_time',    # the calendar's answers (calwrite.py)
         'rerun', 'setup', 'next', 'answer_agent', 'redraft', 'not_ours_kind',
         'confirm', 'cancel', 'none')
# The coding hand-off had an old name (the key below), as if it were a profile or a brain - it is neither, a coding agent is any
# profile of kind coding on any CLI. An old saved card or phone button, or a model still saying it, lands on the name it has
# now; the model is never shown the old one. A REMOVED button (buttons.json `removed`: Handled, Later, Archive it...) lands the same way.
VERB_ALIAS = {'coder': 'coding_agent'}
def canon_verb(v): return buttons.canon(VERB_ALIAS.get(v, v)) if isinstance(v, str) else v
# The action words offered INSIDE the assistant's own line, and what each one reads as - the one list of buttons
# (buttons.json), never retyped here: only which of them fits the thing on the table is decided per item, from its kind.
# The model still reads free text - it just never invents a button. Every word maps to a verb the cards and the typed
# sentence already run, so a chip, a button and a sentence are one road.
CHIP_WORDS = {v: buttons.label(v) for v in buttons.VERBS}
CHIP_HINTS = {v: buttons.hint(v) for v in buttons.VERBS if buttons.hint(v)}
# per kind, in the order they are offered. `next` is last on every one of them: moving on is always available,
# and it is the one word that is never a decision about the thing itself.
# THE SHORT LIST (the owner, 2026-09-25, word by word): eight buttons. Tomorrow and Later are gone - Next on
# open work passes it for the rest of this walk (2026-10-21), and a date is the task's own Remind me. Redraft, Answer
# it, Run it again, Prep me and Handled lost their buttons (the words still work typed);
# the three hand-offs are Make a task (yours) and Send to agent (triage picks which); the sender rules are
# Not ours's own question. The rest of CHIP_WORDS is what `first` may still promote from a typed decision.
# Remind me (`defer`) is on every card with an open task behind it (the owner, 2026-09-25: "remind me should be a walk
# button") - it asks for the day, then the walk moves on; cannot() drops it where there is no task to put away
# ...and Redraft is back on a draft: its choices are Close out, Redraft or Mark done (the owner, 2026-10-01: "rejected is
# useless - it should be redraft or close task")
CHIPS ={'review': ('approve', 'redraft', 'close', 'defer', 'not_ours', 'next'), 'action': ('approve', 'not_ours', 'next'),
         # a meeting is read and passed: Join is a link on the card, not a verb (the owner, 2026-10-02: "Meeting card should
         # only have a next button like what it has on desktop")
         'agent': ('stop_agent', 'defer', 'next'), 'meeting': ('next',),
         'report': ('mine', 'regular_agent', 'next'), 'agentdone': ('close', 'reply', 'next'),
         'wrapup': ('close', 'next'), 'idea': ('mine', 'regular_agent', 'not_ours', 'defer', 'next'), 'task': ('close', 'defer', 'next'),
         'asked': ('reply', 'mine', 'regular_agent', 'defer', 'not_ours', 'next'),
         # a to-do with a task behind it (a promise you made in a chat) is closed here too - Next only read it (2026-10-15)
         'todo': ('reply', 'close', 'mine', 'regular_agent', 'defer', 'not_ours', 'next'),
         # an fyi can become WORK too: "make this job stop emailing me" arrived as a notification (2026-09-24)
         'fyi': ('mine', 'regular_agent', 'not_ours', 'next'),
         # the handful carries its own "All read, next" button (2026-09-14) and nothing else
         'fyis': (),
         # a connection that stopped answering: ask it again, here - Next was its only word, a dead end (2026-09-23)
         'connection': ('test_connection', 'next')}
# THE CONTRACT: where the voice is and what it must not do. The line code reads - CALL, or OPTIONS - is
# toolcatalog.block's, the one place it is taught (2026-09-25: one format; the decisions are tools like any other).
# How to behave is COUNSEL's - the owner's document, not this file (PW-248/256).
# The voice never steps out of the part. A CLI brain answered "next" with "I don't have the queue data" and "yes go ahead" with
# "I'm in Claude Code... I don't have access" (2026-09-03). A regex used to blank such a reply - and blanked correct answers that
# happened to mention access or data; the rule is the model's to keep, so it is said here (the owner, 2026-10-11: everything AI).
IN_PART = ("You are Taskuary. Never talk about yourself as a model or a CLI, or about your own access, tools or limits: answer from "
           "the facts you were given, and when they do not say, say what they do say.\n")

CONTRACT = (
    "WHERE YOU ARE\n"
    "You are speaking to {owner} in the chat. The action words under your line are the owner's "
    "buttons and they are already chosen for this item - never list them, and never end a line with an offer to do "
    "something. When you cannot tell which of two things the owner's words mean, say which two and ask - one short "
    "question, and OPTIONS instead of a CALL. When the words say what they want, CALL it: Taskuary brings up the "
    "button that does it, lit, or the page that holds it, and nothing happens until the owner presses it - so acting on a clear "
    "ask is not a guess. Never say it is done: say what to press.\n" + IN_PART)
SYSTEM = CONTRACT      # the old name, for one release

# The same walk, read in a phone chat. There are no cards there and no action words under the line, so
# the choices have to BE the message - remote_assistant appends them, and this tells the voice to write
# for a screen that has nothing else on it. Only the delivery changes: the pipe, the verbs and the
# proposals are the desk's, so an item settled from the phone is settled everywhere.
PHONE_CONTRACT = (
    "WHERE YOU ARE\n"
    "You are speaking to {owner} in their private chat on their phone, not at the Taskuary desktop. They "
    "cannot see a card, a button, a draft or a link here - never tell them to click, open, tap or read one "
    "as if it were in front of them. Say the sender, the subject, why it matters and what you would do, in "
    "no more than four short sentences, and never more than one item at a time.\n"
    "The choices are added under your line by code from the item itself. Do not list them, do not invent "
    "one, and never end a line with an offer to do something. When you cannot tell which of two things the "
    "owner's words mean, say which two and ask - one short question, and OPTIONS instead of a CALL. When the "
    "words say what they want, act on them: the yes-or-no choices code adds under your line are their "
    "confirmation, so acting on a clear ask is not a guess.\n" + IN_PART)

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
RECEIPTS = {'chase': "I'll draft the nudge - nothing goes out until you say so.", 'let_go': 'Put down.', 'elsewhere': 'Closed - they answered elsewhere.',
            'reply': "I'll draft that - nothing goes out until you say so.", 'approve': f"Sending it as drafted - the task stays open until you {buttons.label('close')}.",
            'not_ours': "Not ours, then - filed. Moving on.", 'not_ours_remember': "Filed, and remembered: this kind goes straight past you from now on.",
            'not_ours_sender': "Noted: that sender is noise - everything from them files itself from now on. Moving on.",
            'remember': "Remembered. Moving on.", 'coding_agent': "Handed off - the code work starts now, and what it finds comes back here.",
            'regular_agent': "Handed off - work on it starts now, and the answer comes back here.",
            'mine': "On your list. Moving on.", 'close': 'Closing the task. Moving on.', 'rerun': "Running it again - its result goes where the report sends it, and if it fails the bell says why. Moving on.",
            'setup': "I'll walk you through it, one step at a time - nothing is built and nothing changes until you say so.",
            'answer_agent': "Passing that on - right away if it's waiting on you, otherwise the moment it next pauses.",
            'redraft': "Writing it again with that - the new draft lands below for your yes.", 'next': 'Next.'}

# The end of the walk, in COUNSEL's calm voice: what is true, and nothing to do (2026-10-06). all_done() adds the
# next meeting and a promise of the owner's that is due today - each only when there is one.
ALL_DONE = "Nothing's waiting."


def all_done(store) -> str:
    """ALL_DONE, then the next meeting (from the calendar's cache - this runs on a button) and one of the owner's own
    promises due today, when either exists."""
    from . import welcome
    now = datetime.now()
    try: extra = [x for x in (welcome.next_meeting(store, now, fetch=False), welcome.promise_today(store, now)) if x]
    except Exception as e:
        logger.debug(f'concierge: the end of the walk said only the facts - {e}'); extra = []
    return ' '.join([ALL_DONE] + extra)


# the quick gear per CLI when the agent profile names no light_model: the assistant's turns are two
# sentences, and the coding model is the wrong tool for them (Connections > AI CLI agents sets it)
ASSISTANT_DEFAULT = llm_mod.ASSISTANT_DEFAULT      # the Assistant's model when none is set: one tier over the light gear
LIVE_KEY = 'concierge'                  # clipool key prefix for the chat's live CLI process
SID_KEY = 'concierge_cli_sid'          # the CLI's own conversation, resumed turn to turn (per dock task)
CURRENT_KEY = 'assistant_current'      # what is on the table, per dock task - persisted, validated on restore (PW-162)
CURRENT_CLOSED = 'assistant_current_closed'   # ...and whether its task was already done when it went up


AI_KEY, MODEL_KEY = 'concierge_ai', 'concierge_model'   # this page's own choice - the old dock's assistant_ai stays the dock's and WhatsApp's

def pick(store) -> str:
    """Which brain speaks: the owner's choice on the Assistant tab; else the default CLI agent (its
    tools are what make this a full assistant); else the first API connector."""
    s = store.get_settings()
    chosen = str(s.get(AI_KEY) or '').strip()
    if chosen: return chosen
    from . import agents as hub_agents
    if (dflt := hub_agents.default_pick(store)): return dflt          # the default brain, as everywhere else
    return general._selected(store)[0]


def is_cli(store) -> bool: return pick(store).startswith('cli:')


def brain(store, trace=None, cancel=None, resume=None, fast=False, keep: str = None):
    """The voice. A CLI runs with its tools, in its own scratch folder (never a checkout), on its light
    gear, and picks its last conversation back up; an API connector answers in-process.

    `fast` is for the turns that need no tools: the CLI with its tools OFF so it cannot wander off exploring
    before it answers (a plain 'next' took 20 seconds, 2026-09-03). It used to swap in an API connector here,
    which is how an Assistant set to Claude answered on Azure; the chat's CLI stays live instead (clipool)."""
    from . import demo
    if demo.enabled(): return demo.brain()
    p = pick(store)
    if not p: return None
    try:
        if p.startswith('cli:'):
            from . import config
            name = p[4:]
            from . import agents as hub_agents
            row = hub_agents.agent_row(store, name) or {}
            try: prof = json.loads(row.get('Config') or '{}')
            except ValueError: prof = {}
            cli = re.split(r'[\\/]', str(prof.get('cmd') or name))[-1].lower().rsplit('.', 1)[0]
            model = str(store.get_setting(MODEL_KEY) or '').strip() or None
            # the Assistant's OWN model - never the profile's light model, which is triage's: it rode haiku and broke its
            # contract in the 2026-09-24 audit, where sonnet held (ASSISTANT_DEFAULT)
            dflt = '' if model else ASSISTANT_DEFAULT.get(cli, '')
            if (model or '').startswith('effort:'): dflt, model = model, None       # codex: a gear is an effort, not a model
            if dflt and not dflt.startswith('effort:'): model = dflt
            # the Assistant's effort, unless the pick names one (ASSISTANT_EFFORT)
            if model and '@' not in model and llm_mod.ASSISTANT_EFFORT.get(cli): model = f'{model}@{llm_mod.ASSISTANT_EFFORT[cli]}'
            folder = config.home() / 'assistant'; folder.mkdir(parents=True, exist_ok=True)
            fx = llm_mod.fast_args(cli) if llm_mod.fast_on(store, cli) else []      # the provider's fast tier (Settings > Assistant)
            # ...and its words as they are written, for the page to draw before the answer is whole (agents.spoken)
            from .clis import preset_args
            # ...and none of the owner's user-level Claude settings: their hooks POST to this app on every prompt and stop (agents._own_settings)
            own = {'user_settings': False} if cli == 'claude' else {}
            if cli == 'claude' and 'stream-json' in (prof.get('args') or preset_args(str(prof.get('cmd') or name))): fx = fx + ['--include-partial-messages']
            cwd = None if fast else str(folder)                  # no cwd = make_cli_llm's read-only gear: no tools, no permission bypass
            if dflt.startswith('effort:'):
                # an effort-only gear (codex) rides on a copy of the profile, never written back to the row
                prof['light_model'] = dflt
                store_get = store.get_agent
                store.get_agent = lambda n, _r=row, _p=prof: (_r | {'Config': json.dumps(_p)}) if n == name else store_get(n)
                try: return llm_mod.make_cli_llm(store, name, model, cwd=cwd, trace=trace, cancel=cancel, resume=resume, keep=keep, **({'extra_args': fx} if fx else {}), **own)
                finally: store.get_agent = store_get
            return llm_mod.make_cli_llm(store, name, model, cwd=cwd, trace=trace, cancel=cancel, resume=resume, keep=keep, **({'extra_args': fx} if fx else {}), **own)
        return llm_mod.build_llm(store, pick=p, model=str(store.get_setting(MODEL_KEY) or '').strip() or None, trace=trace, cancel=cancel)
    except Exception as e:
        logger.debug(f'concierge: no brain - {e}'); return None


def _sid(store, tid: int) -> str: return str(store.get_setting(f'{SID_KEY}:{tid}') or '')


def current_key(store, tid: int) -> str: return str(store.get_setting(f'{CURRENT_KEY}:{tid}') or '')


def set_current(store, tid: int, key: str | None, actor: str = 'assistant', closed: bool = False):
    """The thing on the table, written down as it is put there (or taken away) - not inferred later. `closed`: its task
    was finished before it went up - looked up, not walked to - so restore_current does not take that as it being over."""
    if current_key(store, tid) != (key or ''): store.set_setting(f'{CURRENT_KEY}:{tid}', key or '', actor)
    if str(store.get_setting(f'{CURRENT_CLOSED}:{tid}') or '') != ('1' if key and closed else ''):
        store.set_setting(f'{CURRENT_CLOSED}:{tid}', '1' if key and closed else '', actor)


def resume(store, actor: str = 'owner') -> dict:
    """"Walk me through my tasks" and a hand-off's hello: the item ON THE TABLE when there still is one - an act on it
    failed, its question is unanswered - and only then the next thing. Both used to surface afresh, and the walk skips a
    row it has shown for a few hours: a Close out refused by GitHub was passed over for the next pull request, and the
    one still waiting on the owner went quiet (2026-09-29). restore_current is the test of "still there"."""
    held = restore_current(store, general.dock_task(store, actor)[0]['TaskId'])
    return surface(store, held['key'], actor=actor) if held and held.get('key') else surface(store, actor=actor)


def restore_current(store, tid: int) -> dict | None:
    """The persisted Current, validated against the pile as it stands (PW-162): the item as it is now when it
    is still unread and still there; otherwise the key is cleared and nothing is chosen in its place."""
    key = current_key(store, tid)
    if not key: return None
    # the first rail after a restart is still being built: the item is shown from its own rows and judged once there is a
    # rail - an item_for_key row is no verdict, and a done task's result would have been cleared off the table on it
    if not key.startswith('fyis:') and getattr(store, 'rail_cold_building', lambda: False)():
        quick = funnel.item_for_key(store, key)
        if quick: return card_for(quick) | {'presentation_revision': quick.get('presentation_revision')}
    try: item = funnel.batch_item(store, key) if key.startswith('fyis:') else funnel.next_item(store, key, include_surfaced=True)
    except Exception as e:
        logger.warning(f'concierge: could not validate the current item {key} - {e}'); item = None
    # ...and "still there" is not enough. A mail row on a closed task leaves the pile (funnel._feed_skip),
    # but own work reaches it through the processing inventory, which keeps a finished task as a READ
    # fyi row - so Current went on holding a task done twenty minutes ago and the assistant kept
    # offering to hand it to an agent (TQ-0420). The test is OVER, never "read": an item the assistant
    # puts in the chat is read, and clearing on that would empty the table as soon as it was set.
    # ...except an agent's finished result, whose task is done by definition: the closed task IS what is being
    # shown, and wiping it emptied the table and the rail the moment it went up (the owner, 2026-09-24)
    # ...and a task that was ALREADY done when it went up - pulled from search to look at - is what is being shown, not
    # work that finished under it: clearing it emptied the table and the rail with its card still open (the owner, 2026-10-15)
    over = item and item.get('tid') and (store.get_task(item['tid']) or {}).get('Status') in ('done', 'dropped')         and not store.get_setting(f'{CURRENT_CLOSED}:{tid}')
    # a new line on its thread is being triaged: not on the table THIS moment, but still the one the owner is on - clearing
    # the key emptied the table for good the instant a reply arrived (2026-09-29 audit); it is back when triage lands
    if item and item.get('settling'): return None
    if not item or (over and item.get('lane') != 'approve' and item.get('kind') != 'agentdone'):
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
            "back - never say you cannot. "
            # coding exists only where a coding tool is connected (B3): without one, every hand-off is Send to agent
            + ("When it needs a checkout or a long job, say so and name the coding agent. " if _coding(store) else
               f"When it needs a long job, say so - {buttons.label('regular_agent')} hands it off. Never mention or offer a coding agent. ") +
            "NEVER use your "
            "own task, todo or plan tools, and never create tasks, files or records yourself: a decision of the owner's is carried out by "
            "Taskuary from your CALL line, and you report it only after the receipt says it happened.")


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
    live = next((x for x in _live(store) if x.get('taskId') == tid), None)
    if live:
        tail = [str(l).strip() for l in (live.get('tail') or []) if str(l).strip()]
        waiting = live.get('waiting') if live.get('waiting') is not None else (live.get('idle') or 0) >= 45
        who, req, idle = live.get('agent') or live.get('label') or 'an agent', live.get('request'), int(live.get('idle') or 0)
        # the run's own word first (a stall is not a question, however the screen looks), then the screen
        state = (f"{ws.request_line(who, req)} (idle {idle}s)" if waiting and req else
                 f"{who} is PARKED and ASKING you: {tail[-1][:200]}" if waiting and live.get('state') == 'asking' else
                 f"{who} is PARKED at its prompt, waiting on you (idle {idle}s)" if waiting else
                 f"{who} is WORKING right now (idle {idle}s) - nothing for the owner until it stops")
    elif t.get('RunStatus') == 'running': state = f"{t.get('RunAgent') or 'an agent'} is running headless - nothing for the owner until it stops"
    # ...and whether its last session can be picked up, so "no agent" comes with the road that is real (2026-10-18)
    else: state = 'no agent on it right now' + (f" - its last session is saved ({buttons.label('continue')} reopens it)" if store.resumable_session(tid) else '')
    rv = store.pending_review(tid)
    last = next((c for c in reversed(store.list_comments(tid)) if c.get('ActorType') in ('agent', 'assistant_agent')), None)
    lines = [f"TASK NOW: {task_ref(tid)} [{t.get('Status')}, {t.get('Kind')}] {t.get('Title') or ''} - {state}"]
    # ...and WHAT ITS SCREEN SAYS, so "what is it doing?" is answered from the work, not from a status word - the canvas
    # shows the agent's session beside the chat, and the assistant relays both ways about the thing on screen (2026-09-29)
    if live and live.get('sid'):
        from . import terminal as _term
        try: screen = [str(l) for l in _term.asking_lines(live['sid'], 8) if str(l).strip()]
        except Exception: screen = []
        if screen: lines.append("THE AGENT'S SCREEN, last lines:\n" + '\n'.join(f'  {_cut(l, 200)}' for l in screen))
    sent = store.sent_reply(task_id=tid)
    if sent: lines.append(f"  YOU ALREADY REPLIED ({str(sent.get('DecidedAt') or sent.get('CreatedAt') or '')[:16]}): {_cut(sent.get('FinalText') or sent.get('DraftText'), 240)} - do not suggest answering again")
    if rv: lines.append(f"  a {rv.get('Kind')} waits for the owner's yes (rv{rv['ReviewId']})")
    if last: lines.append(f"  the agent last said ({str(last.get('CreatedAt') or '')[:16]}): {_cut(last.get('Body'), 300)}")
    if t.get('Status') in ('done', 'dropped'): lines.append(f"  CLOSED {str(t.get('ClosedAt') or t.get('UpdatedAt') or '')[:16]} - do not present it as open work")
    return '\n'.join(lines)


def named_now(store, text: str, item: dict | None = None) -> str:
    """TASK NOW for each task the owner NAMED (a TQ ref - an id, not meaning) other than the one on the table: "tell the agent on
    TQ-n ..." was answered blind about TQ-n, and a coding agent proposed for a task with no session on it (real-AI walk, 2026-10-18)."""
    own = int((item or {}).get('tid') or 0)
    refs = [int(n) for n in dict.fromkeys(_TQ_REF.findall(text or '')) if int(n) != own][:4]
    # ...and HOW TO SHOW ONE (2026-10-19 UI walk, G4): "open TQ-0004" was answered "drafted and waiting under my message" and nothing
    # opened - a task comes up beside the answer only when the answer links it, and the model was never told so of the task it was
    # asked about. ...and on a phone the link is the door too: its card and choices come up under the answer (remote_assistant, F18)
    show = lambda n: (f"\n  TO SHOW IT: link it in your answer as [{task_ref(n)}](#task={n}) - that link alone "
                      + ("opens it beside your answer and rings its row on the rail; without it nothing opens and nothing is drawn under your answer"
                         if DELIVERY.get() != PHONE else "brings its card and its choices up under your answer; without it nothing comes up"))
    return '\n'.join(x + show(n) for n in refs if (x := task_now(store, n)))


def under_page(item: dict | None) -> str:
    """How the model brings the item on the table back over the page opened beside it: its link - the one road that puts the page down."""
    tid = int((item or {}).get('tid') or 0)
    return (f"; to show the item again, link it as [{task_ref(tid)}](#task={tid}) - that puts the page down" if tid and DELIVERY.get() != PHONE else '')


def _task_whole(store, tid: int) -> str:
    """The task as its page shows it, bounded: description, checklist, and its notes newest last - the agent's report kept long."""
    t = store.get_task(tid) or {}
    out = []
    if str(t.get('Summary') or '').strip(): out.append(f"THE TASK'S DESCRIPTION: {_cut(t['Summary'], 1500)}")
    try: cl = store.checklist_markdown(tid)
    except Exception: cl = ''
    if str(cl or '').strip(): out.append(f"ITS CHECKLIST:\n{_cut(cl, 1500)}")
    notes = [c for c in store.list_comments(tid) if str(c.get('Body') or '').strip()][-12:]
    if notes:
        out.append('ITS NOTES (oldest first):\n' + '\n'.join(
            f"  {str(c.get('CreatedAt') or '')[:16]} {c.get('Actor') or '?'}: "
            f"{_cut(c.get('Body'), 1500 if str(c.get('Body') or '').lstrip().startswith(('AGENT REPORT', 'CODER REPORT')) else 300)}" for c in notes))
    return _cut('\n'.join(out), 7000)


# AN IDEA OR A MEETING HAS NO THREAD (the 2026-10-01 press audit): told nothing about it, the model looked up message 4321 and
# TQ-0123 - the examples in the tool index - and put them to the owner as "which do you mean?". It is told plainly, a look-up
# that misses says it again, and a reference that does not exist never reaches the owner (unreal_refs).
NO_THREAD = ('this item has no thread and no task yet - no message id and no TQ ref belong to it, so never name or look one up '
             'for it; what is written here is all there is')

def no_thread(item: dict | None) -> bool:
    return bool(item) and item.get('kind') not in ('fyis',) and not item.get('mid') and not item.get('tid')

_TQ_REF = re.compile(r'\bTQ-(\d{1,7})\b', re.I)
_MSG_REF = re.compile(r'\bmessage\s+#?m?(\d{2,9})\b', re.I)

def unreal_refs(store, text: str, said: str = '') -> list:
    """The task and message references in `text` that name nothing in the store - except the ones the owner said himself."""
    text, own = str(text or ''), {int(n) for n in _TQ_REF.findall(said or '')} | {-int(n) for n in _MSG_REF.findall(said or '')}
    return ([f'TQ-{int(n):04d}' for n in dict.fromkeys(_TQ_REF.findall(text)) if int(n) not in own and not store.get_task(int(n))]
            + [f'message {n}' for n in dict.fromkeys(_MSG_REF.findall(text)) if -int(n) not in own and not store.get_message(int(n))])


def documents_line(store, item: dict | None) -> str:
    """DOCUMENTS ON IT: what the item's messages link to (linkdocs) - kind, name, and whether it was read - so a request ABOUT a
    document ("go through the open bills in that sheet") can be routed to an agent that will have it. From the cache only: a turn
    never dials out to say what is attached. '' when nothing is linked."""
    from . import linkdocs
    try: docs = linkdocs.of_task(store, item['tid']) if item.get('tid') else linkdocs.of_message(store, item['mid']) if item.get('mid') else []
    except Exception as e: logger.debug(f'concierge: linked documents skipped - {e}'); return ''
    if not docs: return ''
    def said(d):
        got = linkdocs.peek(d) or {}
        return (f"{linkdocs.name_of(d, got)} - " + (f"read, {got['total_rows']} rows" if got.get('total_rows') is not None else 'read' if 'text' in got
                else f"not read: {got['note']}" if got.get('note') else 'not read yet'))
    return ('DOCUMENTS ON IT (linked from its messages): ' + '; '.join(said(d) for d in docs[:6]) + '. Work on one - going through it, '
            'comparing it, deciding what to pay or answer - is an agent\'s: an agent started on this task gets every document in its '
            'context and can read each in full; whatever it would pay, send or change comes back as a proposal for the owner\'s yes.')


def facts(store, item: dict, whole: bool = False) -> str:
    """What the model is handed about ONE item: the item's own words, then the body, the draft,
    the agent's screen or the meeting, whichever it has. Bounded, so a turn stays fast."""
    if not item: return '(no item on the table - the owner is just talking)'
    lines = [f"ITEM [{item['kind']} / {funnel.LANE_WORDS.get(item['lane'], (item['lane'],))[0]}]: {item['title']}",
             f"from: {item.get('who') or '?'} | when: {item.get('when') or '?'} | why it is here: {item.get('why') or ''}"]
    if no_thread(item): lines.append(f"NO THREAD: {NO_THREAD}.")
    if item.get('tid'):
        now = task_now(store, item['tid'])
        if now: lines.append(now)
    # ...and a report or connection whose run or test failed, with the place that fixes it - it has no task to say so (2026-10-18)
    from . import failures
    if (on := failures.target_of(item)) and (f := failures.standing(store, *on)):
        lines.append(f"WHAT FAILED: {f['what']} - {f['why'] or 'no reason was given'}" + (f". The fix: {f['fix']['label']}" if f.get('fix') else ''))
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
        from .triage import own_words
        combined = []
        for m in task_messages:
            body = own_words(str(m.get('BodyText') or ''))
            combined.append(f"  {str(m.get('SentAt') or '')[:16]} "
                            f"{'YOU' if _own_word(m) else (m.get('FromName') or m.get('FromEmail') or '?')}: "
                            f"{_cut(body, 800)}")
        lines.append(f"TRIAGE COMBINED THESE {len(task_messages)} MESSAGES INTO THIS ONE TASK (oldest first). "
                     "Present and decide them together; do not turn them into separate queue items:\n"
                     + _cut('\n'.join(combined), 6_000))
    elif item.get('mid'):
        m = store.get_message(item['mid']) or {}
        from .triage import own_words
        body = own_words(str(m.get('BodyText') or item.get('preview') or ''))
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
        lines.append(f"THE DRAFT (shown to the owner in the card):\n{_cut(d, 1200)}" if d else f"no draft yet - the card offers {buttons.label('redraft', 'none')}")
        if item.get('stale'):
            lines.append('IMPORTANT: newer messages arrived after that draft. It is stale and must be redrafted before sending; do not recommend approving it.')
    if item['kind'] == 'agent':
        lines.append('the agent\'s last lines:\n' + '\n'.join(item.get('tail') or ['(nothing captured)']))
    if docs := documents_line(store, item): lines.append(docs)
    # THE WHOLE OPEN BOX (the owner, 2026-10-01: "if it has task open, entire task is in context, same with anything else, 4 fyi's"):
    # a task's own description, checklist and notes - the agent's report among them - not only its mail; and every message of a
    # batch, not its title ("4 fyi" was all the model was told)
    # ...for a question asked about it, and a brief handed on - the walk's own one-line intro stays small and quick
    if whole and item.get('tid'): lines.append(_task_whole(store, item['tid']))
    if whole and item['kind'] == 'fyis':
        from .triage import own_words
        for n, i in enumerate(item.get('items') or [], 1):
            m = store.get_message(i['mid']) if i.get('mid') else {}
            body = own_words(str((m or {}).get('BodyText') or i.get('preview') or ''))
            lines.append(f"FYI {n} of {len(item['items'])} [{handle_of(i)}]: {i.get('who') or '?'} - {i.get('title') or ''}" + (f"\n  {_cut(body, 600)}" if body else ''))
    # WHAT A BATCH CAN DO, said to the model (2026-10-08): its verbs were rewritten in code - not ours / remember / archive / close on a
    # batch all became "read", and "remember this sender" taught nothing. The model is told; it chooses
    if item['kind'] == 'fyis':
        lines.append(f"BATCH: these {len(item.get('items') or [])} notices are one card. Its own button is done (All read, next) - for the "
                     "whole set. A verb meant for ONE of them names it with `on` (its m-number, below): not_ours (just this one), "
                     "not_ours_sender (that sender's mail is filed from now on), block_sender (a rule: never reaches triage again).")
    if item['kind'] == 'meeting':
        e = item.get('event') or {}
        lines.append(f"meeting {e.get('start')} - {e.get('end') or ''}" + (f" with {', '.join(e.get('who') or [])}" if e.get('who') else '')
                     + (f" | where: {e.get('where')}" if e.get('where') else '') + (f" | the invite says: {_cut(e.get('about'), 400)}" if e.get('about') else ''))
    # why it is BACK. The card says this itself; the spoken answer has to say the same thing, or "why
    # am I seeing this again?" gets two answers (the owner, 2026-09-15: "if they ask why explain it
    # should be closed").
    if item.get('why_open'): lines.append(f"WHY IT IS BACK: {item['why_open']} The card's Completed button closes it.")
    if item['kind'] == 'agentdone': lines.append(f"the agent's summary: {item.get('summary') or ''}")
    # THE SESSION IS STILL THERE. A finished agent's card said only its summary, so "can you do that? just null those two" read as
    # a new job and opened a second task with a cold agent beside the session that had the answer (the owner, 2026-10-08). The
    # model is told what exists; it decides.
    sess = item.get('tid') and store.resumable_session(item['tid'])
    if sess: lines.append(f"AGENT SESSION: {sess.get('Agent') or 'the agent'}'s own session on {item.get('ref') or 'this task'} is saved, "
                          "closed task or not - more work on it (a follow-up, a change, \"now do that\") is agent.continue on it "
                          "with the owner's words as `note`, which reopens it; a new task would start a fresh agent that knows none of this")
    if item['kind'] == 'wrapup': lines.append(f"WRAP-UP: the reply went out (\"{item.get('sent') or ''}\")" + (f"; the agent finished: {item['summary']}" if item.get('summary') else '') + ' - the task is still open; ask whether to close it')
    if item['kind'] == 'report' and item.get('source_id'):
        runs = store.report_runs(item['source_id'], 3)
        if runs: lines.append('LAST RUNS: ' + '; '.join(f"{str(r.get('at') or '')[:16]} {'FAILED: ' + _cut(r.get('error'), 200) if r.get('failed') else 'ok'}" for r in runs))
    if item['kind'] == 'idea' and item.get('action', {}).get('chat'):
        lines.append('what was said about it before: ' + ' // '.join(f"{t.get('role')}: {_cut(t.get('text'), 200)}" for t in item['action']['chat'][-4:]))
    return '\n'.join(lines)


# ONE GATE ON WHAT THE MODEL SAYS (general fix 2, 2026-10-18): a reply cut off mid-CALL reached the owner as
# `CALL: {"kind": "approve", "par` - _CALL reads only a whole one at the end, so half of one was just text. Only the SHAPE is
# judged here: a word list once blanked replies for what they said and blanked right answers with them (the owner, 2026-10-11:
# staying in the part is the model's, IN_PART). Jargon is noted for the record, never rewritten.
_HALF = re.compile(r'\s*\bCALL:.*$', re.I | re.S)
_BARE = re.compile(r'^\s*(?:```\w*\s*)?\{\s*"(?:kind|verb|params)"', re.I)
LOST = "I lost my train of thought there - say it again?"
def gate(text: str) -> tuple[str, bool]:
    """(what may be shown, whether it was broken). A CALL left in the words, or an answer that is only a fragment of one, is broken."""
    t = str(text or '')
    if _BARE.match(t): return '', True
    if re.search(r'\bCALL:', t, re.I): return _HALF.sub('', t).strip(), True
    if (j := places.jargon_in(t)): logger.info(f'concierge: a reply said {j[:5]} to the owner')
    return t.strip(), False


def _stopped_work(store, item: dict) -> str:
    """What an agent left on the task when it stopped or was saved - '' when none ever ran. "Nothing has been done with it yet" was
    said over an agent's saved work (the re-audit, 2026-10-18)."""
    runs = store.list_runs(item['tid']) if store is not None and item.get('tid') else []
    r = next((r for r in runs if r.get('Status') not in ('running', 'queued', 'starting')), None)
    if not r: return ''
    if r.get('Status') in ('failed', 'error'): return 'an agent started on it and failed'
    saved = store.resumable_session(item['tid'])
    return 'an agent worked on it and stopped' + (' - its conversation is saved, so it can pick up where it left off' if saved else '')


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
    # CLEARING NAMES ITS SET (2026-10-08): the old `clear` verb carried the owner's sentence, and a word list swept whatever its words
    # matched. The model names the set with pipe.clear `select` - handed that tool's description, it calls again
    if kind == 'clear': return text[:m.start()].strip(), {'kind': 'tools.describe', 'params': {'kind': 'pipe.clear', 'why': 'clearing names its set: pipe.clear with `select`'}}
    if canon_verb(kind) in toolcatalog.DECISIONS: return (text or '').strip(), None     # a decision: parse_decision's
    why = toolcatalog.valid(kind, params)
    if why:
        logger.info(f'concierge: refusing that CALL - {why}')
        # A REAL TOOL CALLED WRONG IS A DISCLOSURE, not a dead end (2026-09-25): the model picked task.handoff and
        # guessed `to` for `who`, and the turn quietly did nothing. It is handed the tool's own description as a
        # look-up and calls again in the same turn - the round budget still bounds it.
        if kind in toolcatalog.PURPOSE or kind in toolcatalog.READS:
            return text[:m.start()].strip(), {'kind': 'tools.describe', 'params': {'kind': kind, 'why': why}}
        return text[:m.start()].strip(), None
    return text[:m.start()].strip(), {'kind': kind, 'params': params}


def parse_decision(text: str) -> tuple[str, dict | None]:
    """A CALL naming one of the decisions (toolcatalog.DECISIONS): {'verb', 'text'[, 'as', 'on']} or None. The
    decisions are tools like any other (2026-09-25); this is where the one line reaches the decision road the
    card's buttons take. There is no other line - the DECIDE line and its fallbacks are gone."""
    from . import toolcatalog
    m = _CALL.search(text or '')
    if not m: return (text or '').strip(), None
    try: got = json.loads(m.group(1))
    except ValueError: return (text or '').strip(), None
    verb, p = canon_verb(str(got.get('kind') or '').lower()), got.get('params') or {}
    # a tool that does not exist at all is no line to show the owner either; an operation is parse_call's
    if verb not in toolcatalog.DECISIONS and verb not in toolcatalog.PURPOSE and verb not in toolcatalog.READS:
        return text[:m.start()].strip(), None
    if verb not in toolcatalog.DECISIONS or verb not in VERBS or not isinstance(p, dict): return (text or '').strip(), None
    d = {'verb': verb, 'text': str(p.get('text') or '').strip()}
    if str(p.get('as') or '').strip(): d['as'] = str(p['as']).strip().lower()       # the worker or repository - checked, never trusted
    if str(p.get('on') or '').strip(): d['on'] = str(p['on']).strip()               # the decision is about ANOTHER item, named (PW-121)
    if p.get('new') is True or str(p.get('new')).lower() == 'true': d['new'] = True  # a job of its own, not the item's hand-off
    cc = p.get('cc')                                                                # a reply's people to loop in - looked up, never trusted
    cc = [cc] if isinstance(cc, str) else cc if isinstance(cc, list) else []
    if any(str(c or '').strip() for c in cc): d['cc'] = [str(c).strip()[:120] for c in cc if str(c or '').strip()][:6]
    return text[:m.start()].strip(), d



# what the card's primary button does, said as a word. Anything not here has no yes-able action.
ASSENT_VERB = {'review': 'approve', 'action': 'approve', 'agent': 'answer_agent'}


def assent_verb(item: dict | None) -> str | None:
    """"yes" / "go ahead" on the thing on the table: the verb its own card would run."""
    if not item: return None
    if item.get('kind') == 'review' and not item.get('draft'): return 'reply'   # nothing drafted yet: write one
    return ASSENT_VERB.get(item.get('kind'))


# What a card must HAVE for a verb to be carried out on it - the same map the page checks. The
# receipt used to go out before anyone knew, so "Sending it as drafted. Moving on." and "I could
# not do that from here" landed in the chat one after the other (2026-09-03).
# A HAND-OFF is not in here: an agent needs a BRIEF, not a message. Requiring a `mid` refused "create an
# agent to research these three tools" on a meeting - the one item kind that never has one - with "there is
# nothing to hand to a regular agent on this one" (the owner, 2026-09-07). propose_for already builds those
# through task.create_from_text from the item's facts and the owner's words.
NEEDS = {'reply': 'mid', 'approve': 'rid', 'redraft': 'rid', 'not_ours': 'mid', 'not_ours_remember': 'mid',
         'not_ours_sender': 'mid', 'block_sender': 'mid', 'mine': 'mid', 'forward': 'mid', 'archive': 'mid',
         'rerun': 'source_id', 'close': 'tid', 'answer_agent': 'tid', 'split': 'key', 'defer': 'tid', 'continue': 'tid',
         'chase': 'key', 'let_go': 'key', 'elsewhere': 'key',
         'accept_invite': 'mid', 'decline_invite': 'mid', 'propose_time': 'mid', 'find_time': 'mid'}
SAYS_VERB = {'approve': 'approve', 'redraft': 'redraft', 'not_ours': 'file', 'not_ours_remember': 'file',
             'not_ours_sender': 'file', 'block_sender': 'write an exclusion rule for', 'coding_agent': 'hand to a coding agent', 'regular_agent': 'hand to an agent', 'mine': 'put on your list', 'forward': 'forward',
             'archive': 'archive', 'rerun': 'rerun', 'close': 'close', 'answer_agent': 'answer', 'reply': 'reply to',
             'split': 'split', 'defer': 'put away', 'continue': 'continue', 'chase': 'chase', 'let_go': 'let go', 'elsewhere': 'close as answered elsewhere'}

def _coding(store) -> bool:
    from . import capabilities
    return capabilities.can_code(store)


def handoff_verb(store, verb):
    """With no coding tool connected, a coding hand-off asked for anyway (a stale card, the model's word) IS Send to agent: the
    offer was ours, so it is never answered "there is no coding agent on this computer" (B3, 2026-10-17)."""
    return 'regular_agent' if verb == 'coding_agent' and store is not None and not _coding(store) else verb


def no_agent(store) -> str:
    """The coding agent the dispatch would use, when there is not one - so "Sent off to the coding
    agent" is never said in front of a 422 (2026-09-03)."""
    try:
        from . import agents as hub_agents
        want = hub_agents.default_agent(store)
        return '' if store.get_agent(want) else (want or 'the coding agent')
    except Exception: return ''


def _agent_holds(store, item) -> bool:
    """An agent is on this task - "mine" then takes it off the agent's hands rather than making a task."""
    t = (store.get_task(int(item['tid'])) if store is not None and item.get('tid') else None) or {}
    return str(t.get('Assignee') or item.get('assignee') or '').startswith('agent:')


def _agent_running(tid) -> bool:
    """A live agent session - coding terminal or assistant chat - is on this task right now."""
    from . import terminal
    try: return terminal.for_task(int(tid), details=False) is not None
    except Exception: return False


def closed_note(store, item: dict | None) -> str:
    """' TQ-0013 is closed - ...' when the item's task was marked done or dropped, else ''."""
    t = (store.get_task(int(item['tid'])) if store is not None and (item or {}).get('tid') else None) or {}
    if t.get('Status') not in ('done', 'dropped'): return ''
    return (f" {task_ref(t['TaskId'])} is closed - it was marked done. Sending this does not open it again; "
            f"{buttons.label('reopen')} does, if there is more to do.")


def _live_task(store, item) -> bool:
    """The item names a task that is still open (with no store to ask, naming one is enough)."""
    if not item.get('tid'): return False
    if store is None: return True
    t = store.get_task(int(item['tid'])) or {}
    return bool(t) and t.get('Status') not in ('done', 'dropped')


# an idea's words and what each does to the idea (assistant.act) - the page's Remind me posts its own day
IDEA_ACT = {'mine': 'task', 'regular_agent': 'agent', 'coding_agent': 'agent', 'not_ours': 'dismiss', 'not_ours_kind': 'dismiss_kind'}


def cannot(item: dict | None, verb: str, store=None) -> str:
    """Why this card cannot carry that verb - '' when it can. Always phrased "nothing to <verb>",
    because the honest line is the only line: no receipt goes out in front of it."""
    if not item: return ''
    what = f"{item.get('ref') or item.get('title') or 'this one'}"
    # an idea triage already opened a task for IS that task - Make a task on it made nothing new (the owner, 2026-10-01:
    # "no Make a task on an item that already is a task"); a closed one is history, and new work may be a task again
    if verb == 'mine' and item.get('kind') == 'idea' and _live_task(store, item): return f"{what} is already a task on your list."
    # the slipped answers belong to a slipped card: typed on anything else, or pressed after they wrote back, they do nothing
    if verb in ('chase', 'let_go', 'elsewhere') and item.get('lane') != 'forgotten': return f"Nothing has slipped on {what} - nobody is quiet past their day on it."
    if item.get('kind') == 'idea' and item.get('idea') and (verb in IDEA_ACT or verb == 'defer'): return ''
    # A SENTENCE NAMES ONLY A BUTTON THE ITEM SHOWS (2026-10-17): these said Not ours, reply and Continue over cards with none of them
    if verb == 'not_ours_kind':
        own = 'not_ours' in CHIPS.get(item.get('kind'), ()) and not item.get('closeout') and not cannot(item, 'not_ours', store)
        return f"{what} is not one of the assistant's ideas" + (f" - say {buttons.label('not_ours')}." if own else '.')
    if verb == 'answer_agent' and item.get('kind') != 'agent':
        return f"There's nothing to answer on {what} - nothing on it is waiting for an answer."
    if verb == 'approve' and item.get('kind') in ('review', 'action') and not item.get('draft') and item.get('kind') == 'review':
        # approving an empty draft SENT NOTHING and closed the task anyway (2026-09-03); the card's button is Draft with AI (redraft needs a rid)
        how = f"Press {buttons.label('redraft', 'none')}, or say what to tell them" if item.get('rid') else 'Say what to tell them'
        return f"There is nothing to approve yet - no reply has been drafted on {what}. {how}, and it lands here for your yes."
    # the calendar's answers belong to an invite still waiting on the owner, Find a time to a thread asking for one
    if verb in CAL_ACT:
        inv, meet = calendar_asks(store, item)
        if not (meet if verb == 'find_time' else inv):
            return f"There's no {'ask for a time' if verb == 'find_time' else 'invite waiting on your answer'} on {what}."
    # a calendar answer's note is the owner's line - no AI redrafts an RSVP (calwrite.py)
    if verb == 'redraft' and item.get('rid') and store is not None:
        from . import calwrite
        if calwrite.env_of(store.get_review(int(item['rid'])) or {}).get('kind') == 'calendar':
            return f"The note on {what} is yours to change in the box - there is nothing for the AI to redraft."
    # A DRAFT THAT CANNOT LEAVE is not offered Send (capabilities.can_send_draft): a Teams chat is read here and never
    # posted into, so the button - and the Advisor's line over it - could only ever end "not sent" (2026-10-18)
    if verb == 'approve' and item.get('kind') == 'review' and item.get('rid') and store is not None:
        from . import capabilities, outbound
        if not capabilities.can_send_draft(store, item['rid']):
            block = outbound.send_block(store, capabilities.draft_channel(store, item['rid'])) or 'its channel cannot deliver a reply'
            return f"The draft on {what} cannot be sent from here - {block}."
    # an agent already RUNNING on the task is not handed it again (the owner, 2026-10-01) - the dispatch door refuses it too
    if verb in ('coding_agent', 'regular_agent') and item.get('tid') and _agent_running(item['tid']):
        return f"{what} is already being worked on - it is not handed off a second time."
    if verb == 'coding_agent' and store is not None:
        # no coding tool connected: there is no coding agent to offer at all - not even as an alternative (2026-10-16)
        if not _coding(store):
            # ...which only keeps it off the chips and the card's question: every road that runs it first turns it into Send to agent (handoff_verb)
            return f"{buttons.label('regular_agent')} hands this to an agent."
        gone = no_agent(store)
        if gone: return (f"There's no one to hand it to yet - {gone} isn't set up on this computer. "
                         f"Set it up under {places.name('ai_apps')}, then say it again. Nothing has changed.")
    # ...and a message that is ALREADY a task is not made one again: "Make a task" sat on TQ-0748's own card, on the
    # desktop and in the phone's poll (the owner, 2026-09-25: "why am i getting make this a task?? it already is")
    if verb == 'mine' and item.get('tid') and not _agent_holds(store, item):
        return f"{what} is already a task on your list."
    if verb == 'close' and item.get('closed'): return f"{what} is already closed - the work on it is finished."
    if verb == 'stop_agent' and (item.get('paused') or item.get('lane') in ('stopped', 'saved') or item.get('kind') in ('agentdone', 'wrapup')):
        # a paused conversation has no live session: the pick answered "no agent is running right now" (A20, 2026-09-25)
        # ...nor has a session that already ENDED - failed, finished, or cut off by a restart (owner-approved, 2026-10-20): its
        # card offered Stop and save over nothing to stop; Continue, Mark done and the write-up's own actions are what apply
        return f"{what} isn't running right now - there's nothing to stop."
    if verb == 'defer' and item.get('closed'): return f"{what} is closed - there is nothing to put away."
    need = NEEDS.get(verb)
    if need and not item.get(need):
        # the item's own line, not "TQ-0006 is assistant asked you: Should I…?." glued into a sentence (2026-10-06)
        state = str(item.get('why') or funnel.LANE_WORDS.get(item.get('lane'), ('waiting',))[0]).strip().rstrip('.')
        return f"There is nothing to {SAYS_VERB.get(verb, verb)} on {what} - {state}. Open it if you want its own buttons."
    return ''


def brain_trouble(error) -> str:
    """What went wrong with the Assistant's AI, and what to do about it - in words. A failed turn used to be logged and
    answered with the pipe's facts, which read as the Assistant ignoring the question or being stuck (the owner, 2026-09-30:
    "if assistant brain runs into ran out of tokens or api errors it should say so and tell user to restart chat if broken or
    wait until error clears")."""
    import re as _re
    text = ' '.join(str(error or '').split())
    low = text.lower()
    detail = _re.sub(r'\s*\{.*$', '', text)[:160].rstrip(' :.')
    if _re.search(r'context (length|window)|maximum context|too many tokens|token limit|prompt is too long|max_tokens|too long', low):
        return ("This conversation has grown longer than I can follow. Nothing is lost - your work stays exactly where it "
                "is. Start a new chat with the pencil at the top right and ask me again there.")
    if _re.search(r'rate.?limit|429|quota|insufficient_quota|usage limit|out of (credits|sessions|tokens)|overloaded|529|capacity', low):
        return (f"I've hit my limit for the moment ({detail}). Nothing is lost - it clears on its own, so wait a few minutes "
                "and ask again, or go on with Next.")
    if _re.search(r'401|403|unauthori[sz]ed|invalid.*(key|token)|signed out|not logged in|login|expired', low):
        return (f"I can't answer right now - my sign-in needs attention ({detail}). Nothing is lost. Sign me back in under "
                f"{places.name('connections')} and ask again.")
    from .clipool import RESTART_FAILED
    if RESTART_FAILED in text:          # it ended, was started again, and ended again - an update in progress, or a broken install
        return ("My AI tool stopped, and stopped again when I restarted it - it may be updating. Nothing is lost; ask again in a "
                f"minute. If it keeps happening, check it under {places.name('ai')}.")
    if _re.search(r'timed out|timeout|connection|network|unreachable|502|503|504|500|server error', low):
        return (f"I couldn't get an answer just now - the service didn't respond ({detail}). Nothing is lost; ask again in "
                "a moment.")
    return (f"I couldn't get an answer that time ({detail or 'no reason given'}). Nothing is lost - ask again. If it keeps "
            "happening, a new chat (the pencil at the top right) starts me fresh, and your work stays where it is.")


def walk_chips(left) -> list:
    """With nothing on the table there is nothing to DECIDE about - only the walk. Offered on the opening
    line and on every "nothing here" answer while the pipe still holds something, so Next is always
    somewhere in the conversation: the strip over the composer that used to carry it is gone, and the
    welcome block that offers the walk disappears the moment the first line is written."""
    return [{'verb': 'next', 'label': CHIP_WORDS['next']}] if left else []


def closeout_label(item: dict) -> str:
    """The ONE button of a task's close-out, whatever the system (the owner, 2026-09-27: "we can't have a bunch of them"):
    approve as it shows on an agent's proposal - Approve (buttons.json). What it does there is the card's sentence
    (proposals.CLOSEOUT), never a new word."""
    return buttons.label('approve', 'action') if (item or {}).get('closeout') else ''


def _general(store, item: dict) -> bool:
    if str(item.get('task_kind') or '').lower() == 'general': return True
    try: return bool(item.get('tid')) and store is not None and str((store.get_task(int(item['tid'])) or {}).get('Kind') or '').lower() == 'general'
    except (TypeError, ValueError): return False


CAL_KINDS = ('asked', 'todo', 'fyi', 'task', 'review')
CAL_ACT = {'accept_invite': 'accept', 'decline_invite': 'decline', 'propose_time': 'propose', 'find_time': 'schedule'}

def calendar_asks(store, item: dict | None) -> tuple:
    """(an invite waiting on the owner's answer, a thread asking to find a time) for the message behind this item - read off the
    message itself (MailMetaJson 'cal', MeetJson), never its words. A drafted answer keeps them all on the row - pressing another
    REPLACES it (the owner, 2026-10-20); one the calendar has taken ends them (calwrite.open_on)."""
    if store is None or not item or not item.get('mid') or item.get('kind') not in CAL_KINDS: return False, False
    from . import calwrite
    try: m = store.get_message(int(item['mid'])) or {}
    except (TypeError, ValueError): return False, False
    t = (store.get_task(int(item['tid'])) or {}) if item.get('tid') else {}
    if not m or t.get('Status') in ('done', 'dropped'): return False, False
    return calwrite.open_on(store, m)


def chips_for(store, item: dict | None, first: str = None) -> list:
    """The action words to put under the assistant's line: this kind's vocabulary, minus anything this
    particular item cannot actually carry. An offered chip is a chip that works - which is the whole
    point of gating them through cannot() rather than letting the model name them.

    `first` promotes one verb to the front: what the model said it would do becomes the button that
    does it, instead of a sentence that promised something nothing carried out (the owner, 2026-09-07:
    "It says x, does something else")."""
    if not item: return []
    kind = 'task' if str(item.get('kind') or '').startswith('goal') else item.get('kind')   # a goal is a task on the table (spec 2026-10-12)
    verbs = list(CHIPS[kind] if kind in CHIPS else ('next',))    # the handful's () is deliberate
    # SLIPPED (spec 2026-10-12): the four answers, whatever row leads the item - Chase, Let it go, They answered elsewhere, Remind me
    if item.get('lane') == 'forgotten': verbs = ['chase', 'let_go', 'elsewhere', 'defer', 'next']
    # AN INVITE WAITING ON YOUR ANSWER is answered here - Accept, Decline, Propose a new time, each drafted for your Send - and a
    # thread asking to meet offers Find a time beside Reply (calwrite.py, the owner, 2026-10-20). An email reply is not how an
    # invite is answered, nor is it an agent's or a list's.
    inv, meet = calendar_asks(store, item)
    if inv:
        rest = [v for v in verbs if v not in ('reply', 'mine', 'regular_agent')]
        lead = [v for v in rest if v == 'approve']               # a drafted answer's Send leads; the other answers replace it
        verbs = lead + ['accept_invite', 'decline_invite', 'propose_time'] + [v for v in rest if v not in lead]
    elif meet:
        at = next((verbs.index(v) + 1 for v in ('reply', 'redraft') if v in verbs), 0)
        verbs = verbs[:at] + ['find_time'] + verbs[at:]
    # CONTINUE leads on work an agent left - stopped, saved by you, or paused when Taskuary stopped (A19)
    # ...and on work an agent left WAITING ON SOMEONE, once their answer came (waiton.py: `woke`) - Continue hands it the reply first
    if item.get('tid') and (item.get('lane') in ('stopped', 'saved') or item.get('paused') or item.get('woke')):
        verbs = ['continue'] + [v for v in verbs if v != 'continue']
    # ...and never on FINISHED work: an agent that is done is closed or opened, not sent on (the owner, 2026-10-18: "no keep going
    # if finished") - more for it is said in the task's own box
    # ...but never on a general agent: its card's own chat box is the way on, so the row draws no Continue (the owner,
    # 2026-09-29) - and the Advisor, offered one, picked it and its line was hidden as a move the row could not make (2026-10-15)
    if 'continue' in verbs and _general(store, item): verbs = [v for v in verbs if v != 'continue']
    # NO "ANSWER IT" BUTTON (owner-approved, 2026-10-20: "we don't need that button"): an agent's question is answered by typing in its
    # own pane, right above the row - and the button was even the lit one over a FINISHED agent whose reply waited on the owner's
    # approval. A live agent's row leads with Stop and save (CHIPS['agent']); a typed answer still reaches it (decide, the phone).
    # A REPORT THAT FAILED says "run it again" - so Run it again leads, where there is a report to run (B7)
    if item.get('kind') == 'report' and item.get('bad') and item.get('source_id'): verbs = ['rerun'] + [v for v in verbs if v != 'rerun']
    first = canon_verb(first) if first else first             # an old word typed (Later, Handled) promotes the button it became
    # ...never the fix: it is the failed send's own button, with the place it opens (advisor.offered), not a word to promote
    if first and first in CHIP_WORDS and first not in ('next', 'fix'):
        verbs = [first] + [v for v in verbs if v != first]
    out = []
    for v in verbs:
        if v != 'next' and cannot(item, v, store): continue
        # Reply on a finished agent is for the one it left without a draft - never a pull request's, where
        # nobody is owed an answer (the owner, 2026-09-25)
        if v == 'reply' and item.get('kind') == 'agentdone' and str(item.get('channel') or '').lower() == 'github': continue
        # a close-out is the task's own last act - "not ours" would file the sender's message out from under it
        if v in ('not_ours', 'not_ours_sender') and item.get('closeout'): continue
        # ONE WORD for the one close (the owner, 2026-09-24: "mark done everywhere as the word") - it was "Close the
        # task", "Close without sending" and "Mark task done" for the same act; only the hint says a draft stays unsent
        if v == 'close' and (item.get('kind') == 'review' or item.get('reply_pending')):
            out.append(buttons.chip(v) | {'hint': 'Marks the task done without sending the draft, and stops any work still running on it.'})
        # an agent's proposal runs an action rather than sending a reply - and a task's close-out (merge the PR, close the
        # issue) is one too: the same button, in its Approve state (buttons.json)
        elif v == 'approve' and item.get('kind') == 'action': out.append(buttons.chip(v, 'action'))
        # on a task an agent holds, "mine" TAKES it - it is a task already (the owner, 2026-09-25); the name stays one name
        elif v == 'mine' and item.get('tid') and item.get('kind') != 'idea': out.append(buttons.chip(v) | {'hint': "Takes the work back - it stays on your list."})
        # nothing drafted yet: there is nothing to RE-draft, and the card's own button already says Draft with AI
        elif v == 'redraft' and not item.get('draft'): out.append(buttons.chip(v, 'none') | {'hint': 'Writes a reply for you to check - nothing goes out until you say so'})
        else: out.append(buttons.chip(v))
    return out


# the chips whose verb is not itself a decision tool, and the tool each one is
CHIP_TOOL = toolcatalog.CHIP_TOOL
# ...and a task row's pickers, each the tool that sets what it picks (toolcatalog.PAGE_ONLY says so to the model)
PICKER_TOOL = {'priority': 'task.update', 'assign': 'task.update', 'change_kind': 'task.set_kind', 'pick_repo': 'task.set_repo'}

def table_actions(store, item: dict | None, chips: list = None) -> str:
    """THE BUTTONS UNDER THE LINE, BY NAME. The model was told the action words "are already chosen for this item" and
    never told which they were, so "send it" over a draft could not be matched to the button that sends it and became a
    redraft (the 2026-10-01 press audit). This is the payload - what is offered and the tool each one is; how to match
    the owner's words to it, and when to ask instead, is COUNSEL's."""
    if not item: return ''
    # ON THE DESK, THE ROW'S OWN BUTTONS - what a typed act can light (row_buttons). The chips under the line are not what a task's
    # view draws: "this is not ours" over TQ-0001 was told Not ours was its action, chose it, and was refused at the light because the
    # task's row has no Not ours - its Remove - not a task was never named (the 2026-10-20 query walk). A phone draws the chips.
    if chips is None:
        chips = chips_for(store, item)
        if routes() and store is not None: chips = row_buttons(store, item) + [c for c in chips if c.get('verb') == 'next']
    def what(v):
        tool = v if v in toolcatalog.DECISIONS else CHIP_TOOL.get(v) or PICKER_TOOL.get(v)
        said = toolcatalog.DECISIONS.get(v) or toolcatalog.PURPOSE.get(tool or '', '')
        return f"{tool}: {_cut(' '.join(str(said).split()), 160)}" if tool else "the card's own button"
    rows = [f'  "{c["label"]}" = {what(c["verb"])}' for c in chips if c.get('verb')]
    return 'ACTIONS FOR THE ITEM ON THE TABLE (the buttons under your line, and the tool each one is):\n' + '\n'.join(rows) if rows else ''


# ONLY THE CARD'S OWN BUTTONS ARE ACTIONS ON IT (the owner, 2026-10-01): "what is this about?" over a report came back as a
# File it card, and a report has no File it. Filing it, making it a task and handing it to an agent, decided about the item on
# the table, must be one of its buttons - the chips under the line, or its own page's (a task's Send to agent while no agent
# holds it). Anything else is answered in words. The other verbs carry their own guard (cannot, NEEDS).
BUTTON_OF = {'not_ours_sender': 'not_ours', 'not_ours_remember': 'not_ours', 'block_sender': 'not_ours', 'archive': 'not_ours',
             'coding_agent': 'regular_agent'}
OP_BUTTON = {'message.file': 'not_ours', 'message.archive': 'not_ours', 'preference.exclude_sender': 'not_ours',
             'preference.sender_rule': 'not_ours'}
BUTTONED = frozenset({'not_ours', 'mine', 'regular_agent'})

def is_button(store, item: dict | None, verb: str) -> bool:
    """Whether the owner has a button on this item for what `verb` does."""
    b = BUTTON_OF.get(verb, verb)
    if not item or b not in BUTTONED: return True
    if b in {c['verb'] for c in chips_for(store, item)}: return True
    return b == 'regular_agent' and bool(item.get('tid')) and not _agent_holds(store, item)


def table_op_verb(call: dict | None) -> str | None:
    """The button a filing or new-task OPERATION aimed at the table would be - None when it names its own target."""
    kind, p = (call or {}).get('kind') or '', (call or {}).get('params') or {}
    if any(p.get(f) for f in ('target', 'mid', 'ref', 'on')): return None
    if kind in OP_BUTTON: return OP_BUTTON[kind]
    if kind == 'task.create_from_message': return {'coding': 'coding_agent', 'general': 'regular_agent'}.get(str(p.get('kind') or ''), 'mine')
    return None


# THE ASSISTANT IS A ROUTER ON THE DESK (the owner, 2026-10-19: "no take it back button. hate that. the assistant again should just be a
# router to actions or answer quick questions about things ... all work goes to agents, it brings up tasks/settings/action buttons" and "it
# should just surface the correct button"): a typed ask that means an act brings its item up and LIGHTS the row's own button for it - the
# Advisor's tint on a real verb, never a button of its own - with one line. It runs nothing and draws no card to confirm: the press is the
# confirmation. An act whose button lives on a page opens that page beside the answer. A phone chat has no buttons, so it keeps its text
# yes/no (DELIVERY == PHONE). The model still picks the act; code only finds its button, or tells the model there is none.
def routes() -> bool: return DELIVERY.get() != PHONE
# ...so "name the one you mean and I will ..." promises what this screen does: the desk brings it up, the phone does it (verify, 2026-10-19)
def _there() -> str: return 'bring it up' if routes() else 'do it there'

# the operation a tool names -> the row's own button for it (buttons.json)
KIND_BUTTON = {'task.complete': 'close', 'item.settle': 'close', 'task.defer': 'defer', 'task.reopen': 'reopen', 'review.approve': 'approve',
               'agent.continue': 'continue', 'agent.stop': 'stop_agent', 'agent.answer': 'answer_agent', 'task.split': 'split', 'task.merge': 'split',
               'task.handoff': 'forward', 'task.clarify': 'ask_sender', 'task.share': 'share', 'task.not_a_task': 'remove',
               'message.retriage': 'retriage', 'task.set_kind': 'change_kind', 'task.set_repo': 'pick_repo', 'dispatch.prepare': 'regular_agent',
               'report.rerun': 'rerun', 'connection.test': 'test_connection', **{k: 'not_ours' for k in OP_BUTTON}}
# ...a task's fields: each one its own picker on the row; a title or a due day is written on the task itself
FIELD_BUTTON = {'priority': 'priority', 'assignee': 'assign'}
WAITS = 'Nothing happens until you say yes.'


def _shows(store, it: dict, b: str) -> bool:
    """The task page's own button for `b` (buttons.json `row`) is drawn on this item now - the few whose being there turns on state."""
    if b == 'reopen': return bool(it.get('closed')) or str((store.get_task(int(it['tid'])) or {}).get('Status') or '') in ('done', 'dropped')
    if b == 'stop_agent': return _agent_running(it['tid'])
    if b == 'continue': return bool(store.resumable_session(it['tid'])) and not _general(store, it)
    if b in ('review_changes', 'run_another', 'share'): return _agent_holds(store, it) or bool(store.resumable_session(it['tid']))
    if b == 'attach': return bool(it.get('rid'))
    if b == 'pick_repo': return str((store.get_task(int(it['tid'])) or {}).get('Kind') or '').lower() == 'coding'
    return b != 'fix'                  # a failure's own way out, with its own words - never a button to light from the chat


TASK_VIEW_NOT = frozenset({'proposal', 'setup', 'walk', 'brief', 'fyis', 'meeting'})      # kinds never drawn as a task view (showsTask)


def row_buttons(store, it: dict) -> list:
    """THE BUTTONS THIS ITEM'S ROW DRAWS, as {verb, label}: on an item drawn as its task's view, the task page's own verbs (buttons.json
    `row`) it can carry now; on any other, the chips under the line; and a close-out's Approve. What the Assistant may light is one of these, and nothing else: "Press Not ours"
    was said over a task whose row and menus had no Not ours, lit nothing, and the model was never told (verify, 2026-10-19)."""
    # an item with a task behind it is drawn as the task's own view (CanvasItem.showsTask), whose row is the task page's verbs - the chips under
    # the line are not drawn there: TQ-0001's chips had Not ours, its row did not, and "Press Not ours" lit nothing (verify, 2026-10-19)
    if it.get('tid') and it.get('kind') not in TASK_VIEW_NOT and store is not None:
        out = [{'verb': v, 'label': buttons.label(v)} for v, d in buttons.VERBS.items()
               if d.get('row') and not cannot(it, v, store) and _shows(store, it, v) and not (v == 'regular_agent' and _agent_holds(store, it))]
    else: out = [{'verb': c['verb'], 'label': c['label']} for c in chips_for(store, it) if c.get('verb') and c['verb'] != 'next']
    if it.get('closeout'): out.insert(0, {'verb': 'approve', 'label': closeout_label(it)})
    seen = set()
    return [b for b in out if not (b['verb'] in seen or seen.add(b['verb']))]


def _lit(store, tid: int, table: dict | None, it: dict, verb: str, note: str = '') -> dict:
    """The item's own button for `verb`, lit - the item brought up first when it is not the one on the table (the page pulls `light.key`,
    the rail's road). Nothing runs. A button the row does not draw is a miss the model answers in words (CallMiss), never a line naming it.
    `light.line` is what the strip over the row says while it is lit; `say` is the chat's record of it - past, so a reload never shows
    "press it" over a row with nothing lit (verify, 2026-10-19: "Press Mark done when you're sure" outlived its light)."""
    b = BUTTON_OF.get(verb, verb)
    have = row_buttons(store, it)
    label = next((x['label'] for x in have if x['verb'] == b), '')
    if not label:
        raise CallMiss(f"{_where(it) or 'This item'} has no {buttons.label(b) or b} button - its row has "
                       f"{', '.join(x['label'] for x in have) or 'only Next'}. Say in plain words that it is not done from this row, or name "
                       "the one of its buttons that does it. Nothing was changed.")
    # `note`: the owner's words for the press to carry - Continue's box opens holding them
    said = f"Lit {label} on {it.get('ref') or _where(it) or 'it'}" + (f" with your notes: {_cut(note, 200)}" if note else '.')
    record(store, tid, 'assistant', said)          # the chat's line; the task's notes keep no "press it"
    return {'say': said, 'options': [], 'chips': [], 'decision': None,
            'light': {'verb': b, 'label': label, 'line': f"Press {label} when you're sure" + (' - your notes are in its box.' if note else '.'),
                      'key': it.get('key') or '', 'tid': it.get('tid'), 'ref': it.get('ref') or '', **({'note': note} if note else {})}}


def _did(store, tid: int, said: str, kind: str) -> dict:
    """A write the Assistant ran itself, said in the past tense - and the rail read again (the page's `setting`), since it changed."""
    record(store, tid, 'assistant', said)
    return {'say': said, 'options': [], 'chips': [], 'decision': {'verb': 'setting'}, 'did': kind}


def _relate(store, tid: int, p: dict, actor: str) -> dict:
    "people.relate, run: the org chart changed and said in one line - or a miss the model fixes (a name that is several people)."
    from . import orgchart
    try: r = orgchart.relate(store, p.get('who'), p.get('relation'), p.get('owns'), p.get('drops'),
                             str(p.get('forget')).strip().lower() in ('true', '1', 'yes'), actor)
    except ValueError as e: raise CallMiss(f'{e}. Nothing was changed on the org chart.')
    who = r.get('name') or r.get('email')
    if r.get('forgotten'): return _did(store, tid, f'Took {who} off your org chart.', 'people.relate')
    return _did(store, tid, f"Org chart: {who} - {orgchart.words(r) or 'nothing now'}.", 'people.relate')


def _page(store, tid: int, table: dict | None, href: str, said: str) -> dict:
    """An act whose button lives on a page: that page, opened beside the answer (appLinks), and where to press on it - said by the page's
    name, never "beside this", so the line is still true after a reload, when nothing is beside it."""
    record(store, tid, 'assistant', said)
    return {'say': said, 'options': [], 'chips': chips_for(store, table), 'decision': None, 'open': href}


# a new job's words go into New, on the tab that starts it, its own filled button the one to press: an agent for work, a note to self for
# a to-do (the owner, 2026-10-19: "for hand this to coding agent match buttons" - typed words never start an agent)
NEW_TAB = {'general': ('agent', 'general', 'regular_agent'), 'coding': ('agent', 'terminal', 'coding_agent'), 'task': ('note', '', ''),
           'report': ('report', '', ''), 'workflow': ('workflow', '', ''), 'playbook': ('playbook', '', '')}

def _new(store, tid: int, table: dict | None, want: str, text: str) -> dict:
    kind, how, verb = NEW_TAB[want]
    press = buttons.label(verb) if verb else {'note': 'Note it', 'report': 'Build it', 'workflow': 'Build it', 'playbook': 'Set up with AI'}[kind]
    # ...in the past, never "below": after a reload New is shut and the line stood over nothing (verify, 2026-10-19)
    said = f"Wrote it into New - {press} there starts it."
    # `line`: this line's id, which the card's press says again as what it started (said_started)
    line = record(store, tid, 'assistant', said)
    return {'say': said, 'options': [], 'chips': [], 'decision': None,
            'new': {'kind': kind, 'how': how, 'text': str(text or '').strip()[:2000], 'line': line}}


def said_started(store, cid, out: dict) -> str:
    """The chat's "Wrote it into New" line said again as what its card STARTED. Its Send to agent starts the task and takes the card away,
    and the line stood over a researcher already working, promising a press nobody had left to make (the owner, 2026-10-21: every acting
    answer says what it did). '' - and nothing rewritten - when nothing started or `cid` is not one of the Assistant's own chat lines."""
    if not (out.get('started') or out.get('existing')) or not str(cid or '').isdigit(): return ''
    row = next(iter(store._rows('SELECT * FROM comment WHERE CommentId=?', (int(cid),))), None)
    if not row or row['Actor'] != 'assistant' or not general.is_dock(store.get_task(row['TaskId'])): return ''
    general_ = out.get('dispatch') == 'assistant'
    who = general.assigned_role(store, store.get_task(int(out['taskId'])) or {}) if general_ else out.get('agent')
    said = (f"Started {out.get('ref') or task_ref(out['taskId'])}" + (f" with the {who}" if who else '')
            + (f" on {out['agent']}" if general_ and out.get('agent') else '') + '.')
    rewrite(store, int(cid), said)
    return said


def _answer_now(store, tid: int, table: dict | None, target: int, said: str, actor: str) -> dict:
    """Words to the agent that asked ARE its answer - the box's own purpose, as Answer it says (2026-10-02): they go in, with a receipt."""
    op = operations.propose(store, 'agent.answer', int(target), {'text': said}, actor)
    turn = receipt_turn(store, run_proposal(store, op, actor), actor, table=True)
    return {'say': turn['say'], 'options': [], 'chips': turn['chips'] or chips_for(store, table), 'decision': None}


def _in_words(llm, system: str, table: str, text: str, verb: str) -> tuple[str, list]:
    """The model chose an action the item has no button for: one more round, for the answer in words."""
    label = CHIP_WORDS.get(BUTTON_OF.get(verb, verb)) or PROPOSALS.get(verb, ('', verb))[1]
    try:
        raw = str(llm(system, f'{table}\n\n"{label}" is not one of the actions for the item on the table - the owner has no such '
                              f"button on it.\nThe owner asked: {text}\nAnswer them in plain words, and CALL nothing.",
                      max_tokens=MAX_TOKENS) or '').strip()
    except Exception as e:
        logger.warning(f'concierge: the answer-in-words pass failed - {e}'); raw = ''
    raw, _ = parse_call(raw)
    raw, _ = parse_decision(raw)
    t, opts = parse_options(raw); t, broken = gate(t)               # the one gate: a fragment is never the answer
    return (t or (LOST if broken else ''), opts)


# THE CONTEXT ORDER for typed words over an item (the owner, 2026-10-01): asked "what's left to do?" over an idea, the model
# listed the whole pipe; asked about another task by its person, it searched for the sentence and found nothing
WHAT_ABOUT = ('WHAT THEIR WORDS ARE ABOUT, in this order: the item on the table - a question that names nothing else is about it, '
              'never the whole pipe; ANOTHER task when they name one (its TQ ref, its title or its person) - read that task with '
              'task.read, finding its ref with tasks.list or timeline.search on the person and a subject word, never their whole '
              'sentence; an old task they ask you to FIND - search for it.')


def _advice_block(store, item: dict | None) -> str:
    """The Advisor's line on the item on the table (advisor.block): 'why?' is answered from it, never recomputed here."""
    if not item: return ''
    try:
        from . import advisor
        return advisor.block(store, item)
    except Exception as e:
        logger.debug(f'concierge: no advice block - {e}'); return ''


def table_line(store, item: dict | None) -> str:
    """What a look-up round and a retry carry, so "it" still means the item on the table after the first round."""
    if not item: return ''
    refs = ', '.join(x for x in (task_ref(item['tid']) if item.get('tid') else '', f"m{item['mid']}" if item.get('mid') else '',
                                 f"report source_id {item['source_id']}" if item.get('source_id') else '') if x)
    return (f"ON THE TABLE (what 'it' and 'this' mean, and what an action names when it names nothing else): "
            f"[{item.get('kind')}] {item.get('title') or ''} - from {item.get('who') or '?'}" + (f" ({refs})" if refs else '')
            + (f"\n{table_actions(store, item)}"))


def parse_options(text: str) -> tuple[str, list]:
    m = _OPTIONS.search(text or '')
    if not m: return (text or '').strip(), []
    opts = [o.strip() for o in re.split(r'\s*\|\s*', m.group(1)) if o.strip()][:4]
    return (text[:m.start()].strip(), opts if len(opts) >= 2 else [])


def _verdict_why(item: dict) -> str:
    """Triage's own reason, with the verdict word it opens with trimmed off - "triage filed it as
    fyi - triage: fyi - an automated notification" says it twice (the owner, 2026-09-04: "ask we
    processed as fyi because of x")."""
    from .categories import route_why
    w = (item.get('why') or '').strip()
    if w.lower().startswith('triage:'): w = route_why(w)
    for pre in ('triage: fyi', 'triage: nothing to do', 'triage:'):    # a head with no reason after it
        if w.lower().startswith(pre): w = w[len(pre):]; break
    w = w.lstrip(' -·')
    return f' - {w}' if w else ''


def _sender_name(m: dict) -> str:
    """'Payworth Billing' as they sign; an address alone reads as its company ('billing@payworth.example' -> 'Payworth')."""
    name = ' '.join(str(m.get('FromName') or '').split())
    if name and '@' not in name: return name
    dom = str(m.get('FromEmail') or '').split('@')[-1].split('.')[0]
    return dom[:1].upper() + dom[1:] if dom else 'They'


def repeats(store, tid: int, msgs: list = None, routes: list = None) -> dict | None:
    """ONE VENDOR, ONE ITEM, SAID. Ingest folds a sender writing again about the same thing onto one task (_join_same) and
    never told the owner: {'n', 'who', 'line'} - "Payworth wrote five times about the same thing - every one is kept here.
    All they need now: the signed W-9." The count is code; what they need is the newest repeat's own triage summary, else
    the task's ask - nothing new is asked of a model (a task card never waits on one). None below two."""
    from .welcome import times
    msgs = (store.list_messages(tid) or []) if msgs is None else msgs
    routes = (store.list_routes(tid) or []) if routes is None else routes
    same = f'the same as {task_ref(tid)}'
    joined = {r['MessageId']: r for r in routes if r.get('Decision') == 'attach' and same in str(r.get('Reason') or '')}
    inbound = [m for m in msgs if not _own_word(m)]
    by = {m['MessageId']: m for m in inbound}
    senders = Counter(str(by[mid].get('FromEmail') or '').lower() for mid in joined if mid in by)
    if not senders: return None
    em = senders.most_common(1)[0][0]
    theirs = sorted((m for m in inbound if str(m.get('FromEmail') or '').lower() == em), key=lambda m: str(m.get('SentAt') or ''))
    if len(theirs) < 2: return None
    last = max((joined[m['MessageId']] for m in theirs if m['MessageId'] in joined), key=lambda r: r.get('RouteId') or 0)
    try: verdict = json.loads(last.get('VerdictJson') or 'null') or {}
    except ValueError: verdict = {}
    need = ' '.join(str(verdict.get('summary') or (store.get_task(tid) or {}).get('Summary') or '').split())
    need = re.split(r'(?<=[.!?])\s', need, maxsplit=1)[0].rstrip('.')[:200]
    who = _sender_name(theirs[-1])
    line = f"{who} wrote {times(len(theirs))} about the same thing - every one is kept here." + (f" All they need now: {need}." if need else '')
    return {'n': len(theirs), 'who': who, 'line': line}


def _finished(item: dict) -> str:
    """'Erin finished TQ-0101', or 'TQ-0101 is done' - never 'The agent finished'."""
    ref = item.get('ref') or item['title']
    return f"{item['who']} finished {ref}" if item.get('who') else f"{ref} is done"


def waiting_line(items: list) -> str:
    """'4 waiting: 2 questions for you, 1 draft to approve, 1 report.' - the pile in words, counted by code. Each kind's counted
    words are lanes.json `item_kinds` - never an internal name (the goal kinds printed raw, "1 goal_slipped", B14)."""
    live = [i for i in items or [] if not i.get('settling')]
    if not live: return "Nothing is waiting."
    kinds = Counter(str(i.get('kind') or '') for i in live)
    part = ', '.join(lanes.kind_says(k, n) for k, n in kinds.most_common())
    return f"{len(live)} waiting: {part}."


def _from_you(store, item: dict, n: int = 2) -> str:
    """'Chase them, Let it go, or move on' - the item's own buttons by name: the lines offered "Prep me", "Move the date" and
    "continue it now" over cards with no such button, and typed with no AI those words were refused (U2)."""
    said = [c['label'] for c in chips_for(store, item) if c['verb'] != 'next'][:n]
    return ', '.join(said) + ', or move on' if said else 'move on when you are ready'
def _cap(s: str) -> str: return s[:1].upper() + s[1:]


def fallback(item: dict | None, opening: bool, pile_items: list = None, brain: bool = False, store=None) -> str:
    """No model: the facts in the same three beats - where from, what was done, what you need to do."""
    if not item:
        if opening: return ALL_DONE
        # ...and with nothing on the table, the facts are WHAT IS WAITING. "No AI is connected" was
        # the answer to every typed word in a fresh install - true, and no use to anybody (2026-09-03).
        left = [i for i in (pile_items or []) if not i.get('settling')]
        if left:
            # the tab was as far as this went, and the page that fixes it had no door of its
            # own until the checklist needed one. Now it does, so say it.
            return (f"{waiting_line(left)} Say next and I'll take you through {'it' if len(left) == 1 else 'them'}, or name the one you mean. "
                    + ("(I didn't get an answer to that one - say it again, or name what you want done.)" if brain else no_brain()))
        return ALL_DONE
    if opening and item.get('mid') and lanes.is_mail(item):
        frm = f"{item.get('who') or 'Someone'} wrote on {item.get('channel') or 'email'}" + (f" ({funnel_age(item)})" if funnel_age(item) else '') + f": \"{item['title']}\""
        # A HELD START IS WHAT HAPPENED (the owner, 2026-10-16): "nothing has been done with it yet" was said over work the
        # sender gate held, a start that failed and a real queue alike - the task's own sentence says which, and what to do
        idle = item.get('why_idle') if item.get('lane') == 'queued' and item['kind'] in ('asked', 'todo') else ''
        if idle: return f"{frm}. No agent has started on it. {idle} From you: {_from_you(store, item)}."   # the moves are its own buttons
        # "the agent removed X" reads; "the agent The PR was reviewed.." did not - a summary that is its own sentence gets a lead-in
        done = (_cap(str(item['why'])) if item.get('closed') and item.get('why') else      # a closed task says what happened, not "fyi"
                f"it was worked on - {str(item['summary']).strip().rstrip('.')}" if item.get('summary') else
                'I read it as needing a reply' if item['kind'] == 'review' else 'something is ready to run, waiting for your yes' if item['kind'] == 'action' else
                _stopped_work(store, item) or ('it needs code work, and nobody has started it yet' if item.get('coding') else 'nothing has been done with it yet')
                if item['kind'] in ('asked', 'todo')
                else f'I read it as just for your information{_verdict_why(item)}')
        need = 'nothing has to happen - ' + _from_you(store, item, 3) if item['kind'] == 'fyi' else _from_you(store, item)
        return f"{frm}. Since then: {done}. From you: {need}."
    if item['kind'] == 'agent' and item.get('paused') and item.get('why'):
        # a SAVED conversation, nobody running: "assistant is waiting on you - answer it below" over a task reopened by new mail
        # sent the owner looking for a question no agent had asked (the owner, 2026-10-14) - its own sentence says what is true
        why = str(item['why']).strip().rstrip('.')
        return f"{item.get('ref') or item['title']}: {_cap(why)}. {_cap(_from_you(store, item))}."
    # an agent WORKING it, walked to like any task now (2026-10-21): what it is doing, never "waiting on you - answer it below"
    if item.get('lane') == 'working':
        who = item.get('working') or item.get('agent') or 'An agent'
        return f"{_cap(who)} is working on {item.get('ref') or item['title']} - nothing for you until it finishes or asks."
    if item['kind'] == 'agent':
        # ONE sentence per state (lanes.json): the item's `why` when the run said what it needs, else the
        # screen's question. A stall has nothing to answer - saying "answer it below" over a rate limit
        # sent the owner typing at a wall.
        sub = ws.sub_state(True, bool(item.get('asking')), {'kind': item['request_kind']} if item.get('request_kind') else None)
        line = item['why'] if item.get('request_kind') and item.get('why') else ws.says(sub, item.get('agent') or 'An agent', item['tail'][-1] if sub == 'asking' and item.get('tail') else '')
        if sub == 'stalled': return f"{line} ({item.get('ref') or item['title']}) - it picks up again on its own when the limit lifts. Nothing is lost."
        # "answer it below" only where somebody is listening - a stopped, saved or paused run has nobody (a stall is answered above)
        ans = not item.get('paused') and item.get('lane') not in ('stopped', 'saved')
        return f"{line} ({item.get('ref') or item['title']}) - " + ('answer it below.' if ans else f"{_cap(_from_you(store, item))}.")
    if item['kind'] == 'wrapup':
        return f"{item.get('ref') or item['title']}: the reply went out" + (f" and the work is done ({item['summary']})" if item.get('summary') else '') + '. The task is still open - close it?'
    if item['kind'] == 'idea':
        return f"{item['title']}" + (f" ({item.get('who')})" if item.get('who') else '') + f" - {item.get('why') or 'I raised this'}." + f" {_cap(_from_you(store, item))}."
    if item['kind'] == 'meeting': return f"{item['title']} is {item.get('why')}. {_cap(_from_you(store, item))}."
    # A GOAL (spec 2026-10-12): what it is, by when, the facts its row carries, and what it needs - a decision when it slipped,
    # its first step when nothing has moved, nothing when it is on track (the Advisor's own line is build step 3)
    if str(item['kind']).startswith('goal'):
        d = funnel._dt(item.get('due')); by = f" by {d.day} {d:%b}" if d else ''
        need = f"{_cap(_from_you(store, item))}." if item['kind'] in ('goal_slipped', 'goal_fresh') else 'Nothing needs you yet - move on.'
        return f"\"{item['title']}\" is a goal{by} ({item.get('ref') or ''}): {item.get('why') or 'no steps yet'}. {need}"
    if item['kind'] == 'report':
        # a report that ran fine is read and passed (U11) - "make it a task, hand it off" pushed work nobody needed
        return f"{item['title']} landed {funnel_age(item)}" + (f" and didn't finish - the reason is inside. {_cap(_from_you(store, item, 1))}." if item.get('bad')
                                                              else '. It is open below - read it; nothing has to happen.')
    if item['kind'] == 'agentdone':      # a phone has no card to point at (B19)
        return (_finished(item) + (f": {str(item['summary']).strip().rstrip('.')}." if item.get('summary') else '.')
                + (' Open it to read the full report.' if DELIVERY.get() == PHONE else ' Its full report is on the card.'))
    lead = {'agent': f"{item.get('why') or ws.says('parked', item.get('agent') or 'An agent')} ({item.get('ref') or item['title']}).",
            'meeting': f"{item['title']} is {item.get('why')}.",
            'review': f"{item.get('who') or 'Someone'} is owed a reply on \"{item['title']}\"" + (' - the draft is below.' if item.get('draft') else ' - nothing is drafted yet.'),
            'action': (f"{item.get('why') or item['title']} - it closes when you say so." if item.get('closeout') else
                       f"Something is ready to run on \"{item['title']}\" - nothing happens until you say so."),
            'report': f"\"{item['title']}\" landed" + (" and didn't finish - the reason is inside." if item.get('bad') else '.'),
            'agentdone': f"{_finished(item)}: {item.get('summary') or ''}",
            'idea': item['title'], 'todo': f"{item.get('who') or 'Someone'} - \"{item['title']}\": {item.get('why')}",
            'asked': f"{item.get('who') or 'Someone'} asked: \"{item['title']}\".", 'fyi': f"{item.get('who') or 'Someone'} - \"{item['title']}\" - just for your information."}
    return (('Next: ' if opening else '') + lead.get(item['kind'], item['title'])).strip()


def funnel_age(item: dict) -> str:
    d = funnel._dt(item.get('since') or item.get('when'))
    return timewords.ago(d) if d else ''



def _back_words(at) -> str:
    """'back in 2h' - the rail's own countdown for a row put away (funnelPile.railBack), so the line and the rail agree."""
    if timewords.mins(at) is None: return 'back in a while'
    return f'back {timewords.back_in(at) or "now"}'


def _title_cut(s: str, n: int = 120) -> str:
    """A title at most n long, cut at a word and marked as cut - "...check the schedule config, a" read as a typo."""
    s = str(s or '').strip()
    if len(s) <= n: return s
    head = s[:n].rsplit(' ', 1)[0].rstrip(' ,;:-')
    return (head or s[:n]) + '…'


def _handoff_title(store, tid: int, text: str) -> str:
    """What to call the task: the title the model named (task.create_from_text's `title`), or the words as said;
    with no words, the thing the conversation was on. A phrase list used to strip "can you send it to the coding agent"
    off the words - the model names the job now (2026-09-25: no hard-coded words)."""
    bare = ' '.join(str(text or '').split())
    if bare: return _title_cut(bare)
    for c in reversed(general.chat_rows(store, tid)):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('title'): return _title_cut(card['title'])
    return _title_cut(bare or text.strip())


def _handoff_brief(store, tid: int, text: str) -> str:
    """The words to hand the agent: what the owner just said, with what the conversation was on when
    they said it - "send it to the coding agent until it works" is a brief only with the report named."""
    rows = general.chat_rows(store, tid)
    prior = [_MARK.sub('', c.get('Body') or '').strip() for c in rows[-6:-1]]
    ctx = ' '.join(_cut(b, 200) for b in prior if b)
    return f"{text.strip()}\n\nWhat we were talking about:\n{_cut(ctx, 900)}" if ctx else text.strip()


def _turns(store, tid: int) -> str:
    rows = general.chat_rows(store, tid)[-TURNS:]
    return '\n'.join(f"{'YOU' if c.get('ActorType') == general.ASSISTANT_TYPE else 'OWNER'}: {_cut(_MARK.sub('', c.get('Body') or ''), 500)}" for c in rows)


def _system(store, llm=None) -> str:
    # the document first, the machine contract last; never the tools block - the assistant runs nothing
    # SOUL.md is who the owner is - their work, people, systems and repositories. The chat read none of it and
    # asked which repository "taskuary" was (2026-09-24 audit). Read whole, as COUNSEL is: a cut drops a section.
    contract = PHONE_CONTRACT if DELIVERY.get() == PHONE else CONTRACT
    soul = str(store.doc('soul') or '').strip()
    who = (f"WHO THE OWNER IS (their own document - context about their work; its reply rules are for text sent to OTHERS):\n{soul}\n\n"
           if soul else '')
    # ...and the job itself - responsibilities, people, cadences, what to protect - so "what should I do first" has a measure
    from .triage import job_doc
    job = job_doc(store)
    if job: who += f"THE OWNER'S JOB (their own document - weigh what matters by it):\n{job}\n\n"
    # ...and the repositories a coding job can open in: the model picks one by name (`as`) and code only checks it is one of these
    from . import terminal as term
    try: repos = term.known_repos(store)
    except Exception: repos = []
    where = (f"REPOSITORIES a coding job can open in - name one as `as` when the owner's words or the work point at it; name none when "
             f"unsure and the card asks them: {', '.join(repos[:40])}\n\n") if repos else ''
    # a phone has no canvas to open a page on - but it still knows the screens, by name: with none, "update taskuary" from the phone had
    # no road but a link it could not open or a button it had no row for (2026-10-23)
    pages = pages_block(store) if DELIVERY.get() != PHONE else phone_screens()
    return f"{_counsel(store)}\n\n{who}{where}{pages}{contract.format(owner=_owner(store))}"


def pages_block(store) -> str:
    """THE APP'S OWN SCREENS, by the links the canvas opens (the owner, 2026-10-15: "if i ask the assistant to help me set up
    the intacct api, does it just open the sage intacct settings page? it should ... pull into the chat any deterministic ui").
    The chat opens the first such link in a fresh answer beside it (appLinks.js), and draws every one as a link."""
    from . import demo as _demo
    try: on =[c for c in store.list_connectors() if c.get('Active')]
    except Exception: on = []
    try: reports = [s for s in store.list_sources(active_only=False) if s.get('Channel') == 'report']
    except Exception: reports = []
    title = lambda s: (json.loads(s.get('ConfigJson') or '{}').get('title') if (s.get('ConfigJson') or '').startswith('{') else '') or s.get('Address') or 'report'
    conns = ', '.join(f"{c.get('Name') or c['Type']} #connector={c['Type']}" for c in on[:30])
    reps = ', '.join(f"{title(s)} #report={s['SourceId']}" for s in reports[:30])
    # THE SPLIT (the owner, 2026-10-15: "if the agent asks you to do something do it, if it needs to know settings for x, bring
    # the settings view up"): what the assistant can do, it does - its own calls; a page is for what the owner sees or sets
    return ('APP PAGES - DO FIRST, SHOW SECOND: what the owner asks you to do and you can do, you do - with your own calls and '
            'words, never a page sent instead. When they need to SEE or SET something themselves - the keys of a connection, a '
            'setting, the form of a report - or want to look at it, end your answer with ONE markdown link to that screen, e.g. '
            # A FEW WORDS BESIDE IT (the owner, 2026-10-21: "free text should almost never be used in the assistant - it should be bringing up
            # UI components"): "bring up TQ-12" was answered with the task's story beside the task, which the screen already showed
            '[Open the Sage Intacct connection](#connector=intacct), with a few words at most beside it - what to do there, never what '
            'the screen itself shows; a task is [TQ-0123](#task=123). '
            'The screen opens beside your answer. Use only the addresses below; no link when no screen helps.\n'
            f"- a connection: #connector=<its type>{' - connected now: ' + conns if conns else ''}; any other system by its type "
            '(intacct, outlook, gmail, teams, slack, whatsapp, quickbooks, sharepoint, mssql, github, jira ...)\n'
            '- the AI CLI agents (Claude Code, Codex): #cli-agents\n'
            # the brains (the owner, 2026-10-15: "can you find me the setting for assistant ai brain" got "I can't see the exact name
            # or location of that setting")
            '- the brains - which CLI tool or AI connection, at which model, runs triage, this Assistant, general agents and coding, '
            'and where report runs go: #settings=config&group=How%20mail%20is%20sorted\n'
            # SETUP IS THE BUTTON AT THE TOP, never a link or a script here (the owner, 2026-10-19): it replaces the whole page
            # ...and the demo has no Setup button (it cannot connect an inbox): there it is said so, never pointed at (verify, 2026-10-19)
            + ('- setup itself has no link and no button here: this is the demo, with invented mail - Taskuary installed on their own computer '
               'is set up with the Setup button at the top; say so\n' if _demo.enabled() else
               '- setup itself - their AI, their main source (email, chat or a task system), the questions about their work - has '
               'no link: it is the Setup button at the top of the page; say so\n') +
            f"- a report or workflow: #report=<id>{' - ' + reps if reps else ''}; a new report #report=new; a new workflow "
            '#report=new-agent; the workflows #report=workflows\n'
            '- settings, page by page:\n' + _screens() + '\n' + THIS_APP + '\n\n')


# WHAT THE APP ITSELF IS ASKED TO DO IS ITS OWN SCREEN (the owner, 2026-10-23: "i asked assistant to update taskuary and it pulled up general
# agent instead of settings page updates"). Updates was a bare "#settings=updates" in a list, while every louder line - "work goes to an
# agent", "what you can do, you do" - pointed an act with no tool of its own at an agent, which could run the install itself. Each page is
# said by what it holds (words.json `does`), and using the app is told apart from changing its code, which is a coding job like any other.
THIS_APP = ('USING OR SETTING TASKUARY ITSELF - a setting, a connection, its own update to a new version - is done on its own screen or by '
            'its own tool, never handed to an agent and never a set-up: the owner presses it there. Changing Taskuary\'s CODE is a coding '
            'job like any other.')

def _screens(link: bool = True) -> str:
    """The pages the Assistant brings up, each by what it holds (words.json `does`) - with its link on the desk, by name alone on a phone."""
    return '\n'.join(f"  {p['href'] + ' - ' if link else ''}{p['name']}: {p['does']}" for p in places.PLACES.values() if p.get('does'))


def phone_screens() -> str:
    """The same screens for a phone chat, where no link opens: named in words, at the desk (a phone has no canvas to open them on)."""
    return ('APP SCREENS - on their desk, never on this phone. When they ask for something done on one of these and no tool of yours does it, '
            f'say the screen and what to press there in words ("at your desk, {places.name("updates")} - press its update button"), never a link:\n'
            + _screens(link=False) + '\n' + THIS_APP + '\n\n')


def _urgent_line(pile_items: list, item: dict | None) -> str:
    """One line for the prompt when something more pressing waits behind the item on the table."""
    more = funnel.more_urgent(pile_items, (item or {}).get('key'))
    if not more: return ''
    return ('\nMORE URGENT WAITING (not what we are on): ' + '; '.join(f"{i.get('who') + ' - ' if i.get('who') else ''}{i['title']} ({funnel.LANE_WORDS[i['lane']][0]})" for i in more[:3])
            + ' - mention it in one short clause and offer to switch after this one; do not describe it.\n')


_REF = re.compile(r'\bTQ-0*(\d+)\b')

def off_subject(say: str, item: dict | None) -> bool:
    """The model named a task that is not the one on the table (2026-09-03: the words were TQ-0312, the card was TQ-0327).
    A ref is an id - parsing, not meaning. The word-overlap half (no own word in the sentence = wandered) is gone: it decided
    meaning from a stop-word list and handed back answers that were right in other words (the owner, 2026-10-11)."""
    if not item or not item.get('tid'): return False
    named = {int(n) for n in _REF.findall(say or '')}
    return bool(named) and int(item['tid']) not in named


def _ask(store, llm, tid: int, item: dict | None, instruction: str, pile_items: list) -> tuple[str, list, str]:
    # the item comes FIRST and is named as the only subject; the pile is counts only while one is on the table
    user = ((f"THE ITEM ON THE TABLE - speak only about this one:\n{facts(store, item)}\n\n" if item else '')
            + f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(pile_items, coming=item is None)}{_urgent_line(pile_items, item)}\n\n"
            + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
            + (f"{facts(store, item)}\n\n" if not item else '') + instruction)
    system = _system(store, llm)
    # A CHECK HANDS IT BACK, it never answers for the model (the owner, 2026-10-08: no code in front of the AI): an introduction that
    # named another task (a TQ ref - an id, not meaning) was swapped for the facts line in silence. The model is told why and answers
    # again; only a second miss falls back to the facts.
    for attempt in range(2):
        text = str(llm(system, user, max_tokens=MAX_TOKENS) or '').strip()
        # An INTRODUCTION is not a decision, but the model ends one with a DECIDE line anyway - and this pass
        # used to parse only OPTIONS, so the marker printed verbatim and the thing it announced was dropped on
        # the floor: "I'd hand this to a regular agent... DECIDE: regular_agent" and then nothing happened (the
        # owner, 2026-09-07). The line never reaches the screen; the verb it named becomes the primary chip.
        text, decision = parse_decision(text)
        say, options = parse_options(text)
        why = f"spoke about another task than {item.get('ref') or 'the one on the table'}" if off_subject(say, item) else ''
        if not why: return say, options, (decision or {}).get('verb') or ''
        logger.info(f'concierge: the introduction {why} - {"asking again" if not attempt else "using the facts instead"}')
        user += f"\n\nYour answer {why}. Answer again: only THE ITEM ON THE TABLE, in your own voice as Taskuary."
    return '', [], ''


# A line said to the PHONE only (the day's opener): kept in the conversation so the model and the desk know it was said,
# but never drawn by the desktop chat, whose own welcome already shows the day (the owner, 2026-09-30: "that's only for the phone")
PHONE_ACTOR = 'assistant-phone'


def record(store, tid: int, role: str, text: str, card: dict = None, phone: bool = False):
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
    actor = 'owner' if role == 'user' else PHONE_ACTOR if phone else 'assistant'
    actor_type = general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE
    # A double click must not duplicate the owner's words: those two calls may reach the backend
    # before React disables the button. The same guard also makes empty-pipe auto-advance
    # idempotent across tabs. Deliberately repeated words still record once another turn separates
    # them, so this only removes adjacent duplicates.
    add = getattr(store, 'add_comment_once', store.add_comment)
    return add(tid, actor, actor_type, body)


def rewrite(store, cid: int, text: str, card: dict = None):
    """An assistant turn said again in its own place - the day's opener, drawn before the mail was in (welcome.arrive)."""
    store.set_comment_body(cid, redact(text).strip() + (f"\n\n{MARK}{json.dumps(card, default=str)} -->" if card else ''))


# The global walkthrough has its own durable dock conversation, but the part about a real task must
# also remain with that task. These distinct types keep it out of a general agent's working context
# while making it available to the Timeline's "Assistant discussion" tab.
DISCUSSION_USER_TYPE = 'concierge_user'
DISCUSSION_ASSISTANT_TYPE = 'concierge_assistant'


# THE TURN BEING ANSWERED (say): its table item, the owner's words not yet mirrored onto it, and whether the turn turned
# out to be about something else. An answer read off ANOTHER task was written onto this one's notes, and the next turn
# read it back as this task's own (the 2026-10-01 press audit) - so the owner's line waits until the turn knows.
_TURN = contextvars.ContextVar('taskuary_turn', default=None)


class Stopped(Exception):
    """The owner pressed Stop while the answer was being written (server /api/concierge/stop). A CLI brain is killed by
    its cancel, but an API call cannot be: it comes back anyway, and kept, it landed in the chat minutes later under
    whatever card was open by then (the 2026-10-07 click-through). Nothing of a stopped turn is kept."""

def _same(a: dict | None, b: dict | None) -> bool: return bool(a and b and a.get('key') and a.get('key') == b.get('key'))

def _about_table(item: dict | None, call: dict | None) -> bool:
    """A look-up or an action is about the item on the table when it names nothing else: its own task, its own message,
    its own report - or nothing at all. A search, another task, the calendar or the pipe is a turn about something else."""
    if not item or not call: return True
    kind, p = call.get('kind') or '', call.get('params') or {}
    if kind in ('tools.list', 'tools.describe', 'agents.list', 'repos.list', 'docs.search', 'knowledge.search'): return True
    ref = re.search(r'(\d+)', str(p.get('ref') or p.get('id') or ''))
    if kind == 'task.read': return bool(ref and item.get('tid') and int(ref.group(1)) == int(item['tid']))
    if kind == 'message.read': return bool(item.get('mid') and str(p.get('mid') or '').lstrip('m') == str(item['mid']))
    if kind == 'report.read': return bool(item.get('source_id') and str(p.get('source_id') or '') == str(item['source_id']))
    if toolcatalog.is_read(kind): return False
    return not ref or bool(item.get('tid') and int(ref.group(1)) == int(item['tid']))

def _strays(item: dict | None, call: dict | None):
    turn = _TURN.get()
    if turn is not None and not _about_table(item, call): turn['aside'] = True


def record_related(store, dock_tid: int, item: dict | None, role: str, text: str, card: dict = None):
    """Record a dock turn and mirror it onto every real task the turn discusses."""
    result = record(store, dock_tid, role, text, card)
    turn = _TURN.get()
    if turn is not None and _same(item, turn.get('item')):
        if turn.get('aside'): return result                      # about something else: the chat keeps it, this item does not
        if turn.get('said'): _mirror(store, dock_tid, item, 'user', turn.pop('said'))
    _mirror(store, dock_tid, item, role, text)
    return result


def _mirror(store, dock_tid: int, item: dict | None, role: str, text: str):
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


def history(store, tid: int) -> list:
    out = []
    for c in general.chat_rows(store, tid):
        if c.get('Actor') == PHONE_ACTOR: continue      # said to the phone; the model still reads it through chat_rows
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
    return f"{d:%a} {d.day} {d:%b}, {h}:{d:%M}{'am' if d.hour < 12 else 'pm'}"


def _span_minutes(start: str, end: str) -> int:
    a, b = funnel._dt(start), funnel._dt(end)
    return max(0, int((b - a).total_seconds() // 60)) if a and b else 0


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
    # one live CLI process per chat, kept open between turns (clipool); New chat closes it
    try: return brain(store, trace=trace, cancel=cancel, resume=_sid(store, tid) or None, fast=True, keep=f'{LIVE_KEY}:{tid}')
    except Exception as e:
        logger.warning(f'concierge: no brain for this turn - {e}')
        return None


def turn_system(store, llm=None) -> str:
    """A typed turn's instructions: COUNSEL, SOUL, the voice, then the tool index. ONE text for every round of a turn and for
    warm(): a CLI brain is launched with it (--system-prompt-file, named by its content), so a round that sent another one
    restarted the process under it."""
    return _system(store, llm) + '\n\n' + toolcatalog.block(store)


_WARMING = threading.Lock()


def warm(store, actor: str = 'owner', wait: bool = False) -> bool:
    """Start the chat's CLI before the owner types (the owner, 2026-10-20: "it should respond to things quickly"): the page
    opening, New chat and a brain changed each start it, so the CLI's start-up - 2.5-4 s on this machine - is paid while they
    read, never on their first ask. Exactly the process that ask would take: the same brain, instructions and conversation.
    Nothing for an API brain or a CLI that keeps no conversation, and nothing at all while one is already starting.
    True when a process was started."""
    if not is_cli(store): return False
    def go() -> bool:
        if not _WARMING.acquire(blocking=False): return False
        try:
            tid = general.dock_task(store, actor)[0]['TaskId']
            from . import clipool
            if any(x['key'] == f'{LIVE_KEY}:{tid}' for x in clipool.live()): return False     # the page's every read: one look, no build
            llm = _brain_for(store, tid, None)
            return bool(getattr(llm, 'warm', None) and llm.warm(turn_system(store, llm)))
        except Exception as e:
            logger.info(f'concierge: the CLI was not warmed - {e}'); return False
        finally: _WARMING.release()
    if wait: return go()
    threading.Thread(target=go, daemon=True, name='concierge-warm').start()
    return False


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
        say = ("Let's go through what we have today. " + (f"{plural(n, 'thing')} waiting - {funnel.summary(p['items']).split(' - ', 1)[-1].split('.')[0]}." if n else 'Nothing is waiting on you yet.'))
    chips = walk_chips(len(p['items']))
    card = {'key': 'brief', 'kind': 'brief', 'lane': 'report', 'title': 'Today', 'n': len(p['items']),
            'mail': sum(map(lanes.is_mail, p['items'])), 'chips': chips}
    record(store, tid, 'assistant', say, card)
    return {'say': say, 'card': card, 'chips': chips, 'opened': True}


def _live(store) -> list:
    from . import terminal as term
    try: return term.live_sessions(tail=0)
    except Exception: return []



def _on_the_table(store, actor: str = 'owner') -> list:
    """The item the walk is holding, as pile items. Putting one in the chat settles it `surfaced, read`
    - so build() no longer has it, and the sweep could not see the very report the owner was looking at:
    it cleared five of six and left Current sitting there (the owner, 2026-09-11: "it did not clear all
    6 reports including current"). A batch on the table is its members."""
    try: key = current_key(store, general.dock_task(store, actor)[0]['TaskId'])
    except Exception as e: logger.debug(f'concierge: no table to read - {e}'); return []
    if not key: return []
    out = []
    for k in (key[5:].split(',') if key.startswith('fyis:') else [key]):
        if not k: continue
        try: it = funnel.next_item(store, k, include_surfaced=True) or funnel.item_for_key(store, k)
        except Exception as e: logger.debug(f'concierge: {k} is on the table but not in the pile - {e}'); it = None
        if it: out.append(it)
    return out


def _pipe(store) -> list:
    """The pipe AS THE OWNER SEES IT: what is unread, plus what is on the table. Counted once."""
    items = funnel.build(store)['items']
    have = {i['key'] for i in items}
    return items + [i for i in _on_the_table(store) if i.get('key') and i['key'] not in have]


def pipe_holds(store) -> str:
    """What the pipe actually contains, by kind and by who - the sentence a MISS needs. "Nothing
    matches" on its own reads as "those items are not there", which is what it said about eleven
    rows the owner could see (2026-09-10). Counted over the same set select_items searches."""
    try: items = _pipe(store)
    except Exception: return ''
    if not items: return 'Nothing is waiting.'
    # ...by a NAME: "From Unknown Sender." named nobody (F23)
    who = Counter(w for i in items if (w := str(i.get('who') or '').strip()) and w.lower() not in ('unknown sender', 'unknown', 'someone'))
    top = ', '.join(w for w, _ in who.most_common(3))
    return waiting_line(items) + (f' From {top}, among others.' if len(who) > 3 else f' From {top}.' if top else '')


def select_items(store, sel: dict) -> list:
    """The items a SELECTOR describes. Every field is optional and they AND together; an empty selector
    matches nothing, deliberately - "clear everything" is asked for by name (`everything: true`), never by
    leaving them all blank."""
    from .routing import tokens
    sel = {k: v for k, v in (sel or {}).items() if v not in (None, '', [], False)}
    if not sel: return []
    want = lambda f: str(sel.get(f) or '').strip().lower()
    cat, kind, lane = want('category'), want('kind'), want('lane')
    # WHAT IT IS, whichever field named it: "category: fyi" matched nothing, because fyi is a kind and a lane here, and
    # "mark all the fyi read" left all forty on the rail while "clear all fyis" (kind: fyi) cleared them (2026-09-25)
    what = lambda i: {str(i.get(f) or '').lower() for f in ('category', 'kind', 'lane')}
    who = want('sender')
    words = [w for w in tokens(str(sel.get('contains') or ''))]
    older = sel.get('older_than_hours')
    out = []
    # THE PIPE IS WHAT IS UNREAD. keep_surfaced=True is the whole timeline, all-time: it offered to
    # "clear 72" when seven reports were actually waiting, because 65 of them had been read days ago
    # (the owner, 2026-09-07: "there isn't 72 in the pipeline. There are 8 open report category in
    # unread. 72 is all time but we don't care about those").
    for i in _pipe(store):
        if i['lane'] in ('blocked', 'working'): continue                  # an agent's question is never swept
        if any(v and v not in what(i) for v in (cat, kind, lane)): continue
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


def _set_words(sel: dict) -> str:
    """A set, said: "from Gail", "about the export" - what the receipt names so the owner reads which ones."""
    sel = {k: v for k, v in (sel or {}).items() if v not in (None, '', [], False)}
    # ...in words: "kind: fyi" was the selector's own field read out (F23) - what it IS is the count's noun (_set_noun)
    bits = ([f"from {sel['sender']}"] if sel.get('sender') else []) + ([f"about {sel['contains']}"] if sel.get('contains') else []) \
        + ([f"older than {plural(int(float(sel['older_than_hours'])), 'hour')}"] if str(sel.get('older_than_hours') or '').replace('.', '', 1).isdigit() else []) \
        + [f"{k}: {v}" for k, v in sel.items() if k not in ('sender', 'contains', 'everything', 'kind', 'lane', 'category', 'older_than_hours')]
    return ' '.join(bits) or ('' if _what_of(sel) else 'in the pipe')


def _what_of(sel: dict) -> str:
    return next((str(sel.get(f) or '').strip().lower() for f in ('kind', 'lane', 'category') if str(sel.get(f) or '').strip()), '')


def _set_noun(sel: dict, n: int) -> str:
    """The count of a set with what it is: "4 FYI", "3 reports", "2 items"."""
    what = _what_of(sel or {})
    if what in ('fyi', 'fyis'): return f'{n} FYI'
    if what in ('report', 'reports'): return plural(n, 'report')
    return plural(n, 'item')


def defer_selected(store, sel: dict, until, actor: str = 'owner') -> dict:
    """Put every item a selector names away until `until`: a task by its own Remind me (remind.set_reminder), a notice held off the rail
    until then. What would not go - a closed task, an agent still open on one - is counted, never hidden."""
    from . import remind
    at = remind.parse(until)
    if not at: raise ValueError('say until when - "monday", "friday 2pm", "2 weeks"')
    hours = max(0.1, (datetime.strptime(at[:19], '%Y-%m-%d %H:%M:%S') - datetime.now()).total_seconds() / 3600)
    hits, done = select_items(store, sel), []
    for i in hits:
        try:
            if i.get('tid'): remind.set_reminder(store, int(i['tid']), until, actor)
            funnel.settle(store, i['key'], 'later', actor, hours=hours)
            done.append(i)
        except (ValueError, RuntimeError) as e: logger.warning(f"concierge: {i['key']} was not put away - {e}")
    _off_the_table(store, done, actor)
    return {'done': len(done), 'stuck': len(hits) - len(done), 'when': remind.when(at), 'titles': [i['title'] for i in done][:8]}


def close_selected(store, sel: dict, actor: str = 'owner') -> dict:
    """Close every item a selector names: a task marked done (close_task - its draft dismissed, as Mark done does), a notice read."""
    hits, done = select_items(store, sel), []
    for i in hits:
        try:
            if i.get('tid'): close_task(store, int(i['tid']), actor)
            if _clear_one(store, i['key'], actor, 'closed by the owner'): done.append(i)
        except (ValueError, RuntimeError) as e: logger.warning(f"concierge: {i['key']} was not closed - {e}")
    _off_the_table(store, done, actor)
    return {'done': len(done), 'stuck': len(hits) - len(done), 'titles': [i['title'] for i in done][:8]}


def clear_selected(store, sel: dict, actor: str = 'owner') -> dict:
    """Mark every item a selector names read. Read, never deleted - they stay on the Timeline."""
    items = select_items(store, sel)
    cleared = [i for i in items if _clear_one(store, i['key'], actor, 'cleared by the owner')]
    _off_the_table(store, cleared, actor)
    return {'cleared': len(cleared), 'stuck': len(items) - len(cleared),
            'titles': [i['title'] for i in cleared][:8],
            'mid': next((i.get('mid') for i in cleared if i.get('mid')), None), 'remember': False,
            'note': '', 'words': [], 'rules': [], 'select': sel}




# A TASK NAMED BY ITS PERSON AND SUBJECT, NOT BY A SENTENCE (the 2026-10-01 press audit): "what did Omar's Spendly lockout
# say?" searched for every word, and the mail says "locked me out" - 7 of 11 such asks found nothing. When every word finds
# nothing, a row is scored by how many of the words it has, each by its stem ("lockout" finds "locked"), and the rows with
# at least half of them come back best first.
def _stem(w: str) -> str: return w[:4] if len(w) >= 6 else w
def word_hits(words: list, text: str) -> int:
    from .routing import tokens
    toks = set(tokens(text))
    return sum(1 for w in words if any(t.startswith(_stem(w)) for t in toks))
def _enough(words: list) -> int: return max(1, (len(words) + 1) // 2)


def newest_rows(store, days: int, cap: int = 4000):
    """feed(limit=cap) newest first, a page at a time: a search by category or age alone stops at its twelfth hit
    instead of building 4,000 rows (6-10 s) to keep twelve. Same rows, same order (feed's order is total: SentAt,
    then MessageId). A row that arrives between pages shifts the next one down a place - seen once, not twice.
    No live sessions: a hit carries who/when/title/ref, none of which a running agent changes."""
    seen, off, n = set(), 0, 100
    while off < cap:
        page = store.feed(limit=min(n, cap - off), days=days, offset=off, live_state=())
        for r in page:
            if r['MessageId'] not in seen: seen.add(r['MessageId']); yield r
        if len(page) < min(n, cap - off): return
        off, n = off + len(page), min(n * 2, 1000)


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
    out, days = [], int(sel.get('days') or 3650)
    # the index reaches every message, body included, best match first; without one, the newest 4000 by subject
    ids = store.message_search(words, who, days) if (words or who) else None
    if ids is None: rows = newest_rows(store, days)
    else: rank = {i: n for n, i in enumerate(ids)}; rows = sorted(store.feed(limit=len(ids) or 1, days=days, ids=ids), key=lambda r: rank[r['MessageId']])
    for r in rows:
        if r.get('Channel') == 'assistant': continue
        hay = f"{r.get('FromName') or ''} {r.get('FromEmail') or ''}".lower()
        if who and who not in hay: continue
        if cat and str(r.get('Category') or '').lower() != cat: continue
        subj = str(r.get('Subject') or '')
        if ids is None and words and not all(w in set(tokens(subj + ' ' + hay)) for w in words): continue
        if older:
            from datetime import datetime as _dt
            d = funnel._dt(r.get('SentAt'))
            if not d or (datetime.now() - d).total_seconds() < float(older) * 3600: continue
        out.append({'ref': task_ref(r['TaskId']) if r.get('TaskId') else '', 'when': str(r.get('SentAt') or ''),
                    'who': r.get('FromName') or r.get('FromEmail') or '?', 'title': subj, 'mid': r.get('MessageId')})
        if len(out) >= limit: break
    if not out and len(words) > 1: return _search_loose(store, words, who, cat, days, limit)
    return out


def _search_loose(store, words: list, who: str, cat: str, days: int, limit: int) -> list:
    ids = store.message_search([_stem(w) for w in words], who, days, loose=True)
    if ids is None: rows = store.feed(limit=4000, days=days)
    else: rank = {i: n for n, i in enumerate(ids)}; rows = sorted(store.feed(limit=len(ids) or 1, days=days, ids=ids), key=lambda r: rank[r['MessageId']])
    scored = []
    for r in rows:
        if r.get('Channel') == 'assistant': continue
        hay = f"{r.get('FromName') or ''} {r.get('FromEmail') or ''}".lower()
        if (who and who not in hay) or (cat and str(r.get('Category') or '').lower() != cat): continue
        n = word_hits(words, f"{hay} {r.get('Subject') or ''} {r.get('Preview') or ''}")
        if n >= _enough(words): scored.append((-n, len(scored), r))
    return [{'ref': task_ref(r['TaskId']) if r.get('TaskId') else '', 'when': str(r.get('SentAt') or ''),
             'who': r.get('FromName') or r.get('FromEmail') or '?', 'title': str(r.get('Subject') or ''), 'mid': r.get('MessageId')}
            for *_, r in sorted(scored)[:limit]]


def know(store, q: str) -> str:
    """knowledge.search: the Hub, the knowledge base and the kept facts for these words, in one answer."""
    from . import handbook as hub, knowledge
    from .routing import tokens
    want = {w for w in tokens(q) if len(w) > 2}
    kept = [m['Note'] for m in store.list_memories() if want & set(tokens(m.get('Note') or ''))][:8]
    parts = [hub.block(store, q, actions=False) if hub.enabled(store) else '', knowledge.block(store, q),
             ('KEPT FACTS:' + NEWLINE + NEWLINE.join(f'- {n}' for n in kept)) if kept else '']
    found = NEWLINE.join(x.strip() for x in parts if x.strip())
    return found or (f'Nothing the company has written down matches "{q}" - not in the Hub, the documents or the kept facts. '
                     'Say so plainly; a report or the timeline may still hold it (reports.list, timeline.search).')


def _read(store, item: dict | None, call: dict) -> str:
    """A look-up in a turn: a task or message that does not exist, asked for over an item with no thread, says why."""
    found = read_op(store, call['kind'], call['params'])
    if no_thread(item) and call['kind'] in ('task.read', 'message.read') and found.startswith('There is no'):
        found += f" The item on the table: {NO_THREAD}."
    return found


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
        # ...and its checklist, numbered the way task.check takes it: read without it, "tick off the first item" was
        # answered "there's no checklist on this task" (the replay, 2026-09-25)
        boxes = store.task_checklist(tid)
        if boxes: out.append('checklist: ' + '; '.join(f"{n}. [{'x' if b.get('done') else ' '}] {b['text']}" + (f" (note: {b['note']})" if b.get('note') else '')
                                                     for n, b in enumerate(boxes, 1)))
        if t.get('RemindAt'): out.append(f"put away until {str(t['RemindAt'])[:10]} ({buttons.label('defer')})")
        for msg in (store.list_messages(tid) or [])[:6]:
            out.append(f"  message {str(msg.get('SentAt') or '')[:16]} from {msg.get('FromName') or msg.get('FromEmail')}: "
                       f"{_cut(msg.get('Subject') or '', 120)} - {_cut(msg.get('BodyText') or '', 400)}")
        for c in (store.list_comments(tid) or [])[-8:]:
            out.append(f"  {c.get('Actor')} ({c.get('ActorType')}) {str(c.get('CreatedAt') or '')[:16]}: {_cut(c.get('Body') or '', 500)}")
        return NEWLINE.join(out)
    # THE APP, INDEXED (search.places): the candidates and the link each opens - the model links the one that fits
    if kind == 'app.find':
        from . import search
        hits = search.places(store, str(p.get('query') or ''))
        if not hits: return f"Nothing in the app is called that ({p.get('query')!r}). Try the one word that names it."
        # ...and on a phone no link opens: the screen is named, at the desk (phone_screens)
        say = (lambda h: f"no link opens on a phone - name it, at their desk: {h.get('where') + ' → ' if h['type'] == 'setting' and h.get('where') else ''}"
               f"{h['title']}") if DELIVERY.get() == PHONE else (lambda h: f"link it as [{h['title']}]({h['href']})")
        return NEWLINE.join(f"{h['title']} ({h['type']}{' - ' + h['where'] if h.get('where') else ''}{', ' + h['sub'] if h.get('sub') else ''}): {say(h)}"
                            for h in hits)
    # THE APP ITSELF, by name - appfacts reads the tables the tabs read. A miss lists what exists, so
    # the second try finds it; an id is printed with every row, so the next call can be exact.
    if kind == 'report.read':
        from . import appfacts
        r = appfacts.find_report(store, str(p.get('title') or ''), p.get('source_id'))
        if not r: return 'No report by that name. The ones set up: ' + ', '.join(x['title'] for x in appfacts.reports(store)[:20])
        out = [f"{'WORKFLOW' if r['workflow'] else 'REPORT'} {r['title']} (source_id {r['source_id']}, {'on' if r['active'] else 'off'}) - "
               f"runs {r['schedule'] or 'on no clock'}; reaches you: {r['reach']}; goes: {r['goes']}"]
        for run in (store.report_runs(r['source_id'], 6) or []):
            out.append(f"  {str(run.get('at') or '')[:16]} {'FAILED' if run.get('failed') else 'ok'} "
                       f"{run.get('ms') or 0}ms - {_cut(run.get('error') or run.get('summary') or run.get('said') or '', 400)}")
        return NEWLINE.join(out)
    if kind == 'reports.list':
        from . import appfacts
        rows = appfacts.reports(store)
        if not rows: return 'No reports or workflows are set up.'
        def last(r): return 'never ran' if r['last_ok'] is None else (f"FAILED - {r['last_said']}" + (f" (the fix: {r['fix']})" if r.get('fix') else '') if r['last_ok'] is False else f"ok {r['last_at'][:16]}")
        return NEWLINE.join(f"{'WORKFLOW' if r['workflow'] else 'REPORT'} {r['title']} (source_id {r['source_id']}{'' if r['active'] else ', off'}) - "
                            f"{r['schedule'] or 'no clock'}; reaches you: {r['reach']}; goes: {r['goes']}; last: {last(r)}" for r in rows)
    if kind == 'settings.list':
        from . import appfacts, settings_schema
        rows, group = appfacts.settings(store), str(p.get('group') or '').strip().lower()
        if not group: return NEWLINE.join(f"{g}: {sum(1 for r in rows if r['group'] == g)} knobs" for g in settings_schema.GROUPS)
        hit = [r for r in rows if group in r['group'].lower()]
        if not hit: return 'No settings group by that name. The groups: ' + ', '.join(settings_schema.GROUPS)
        return NEWLINE.join(f"{r['said']}  [{r['key']}]" for r in hit)
    if kind == 'setting.read':
        from . import appfacts, settings_schema
        rows, key, label = appfacts.settings(store), str(p.get('key') or '').strip(), str(p.get('label') or '').strip().lower()
        r = next((x for x in rows if x['key'] == key), None) or next((x for x in rows if label and label in x['label'].lower()), None)
        if not r: return 'No setting by that name. The groups: ' + ', '.join(settings_schema.GROUPS) + ' - settings.list <group> names their knobs.'
        meta = settings_schema.knobs()[r['key']]
        opts = f" - {' | '.join(str(o) for o in meta['options'])}" if meta.get('options') else ''
        return f"{r['said']}  [{r['key']}, a {r['type']}{opts}]{NEWLINE}{meta.get('desc', '')}"
    if kind == 'connections.list':
        from . import appfacts
        rows = appfacts.connections(store); live = [c for c in rows if c['active']]
        if not live: return f'Nothing is connected yet ({len(rows)} catalogue cards are off).'
        return NEWLINE.join(f"{c['name']} ({c['type']}{', no key yet' if not c['has_secret'] else ''})"
                            f"{' - last sync ' + c['last_sync'][:16] if c['last_sync'] else ''}{' - ERROR ' + c['last_error'] if c['last_error'] else ''}{' (the fix: ' + c['fix'] + ')' if c.get('fix') else ''}"
                            for c in live) + f"{NEWLINE}{len(rows) - len(live)} catalogue cards are off - connection.read <name> for any of them."
    if kind == 'connection.read':
        from . import appfacts
        c = appfacts.find_connection(store, str(p.get('name') or ''), p.get('connector_id'))
        if not c: return 'No connection by that name. Connected: ' + ', '.join(x['name'] for x in appfacts.connections(store) if x['active'])
        return (f"{c['name']} - type {c['type']}, connector_id {c['connector_id']}, {'on' if c['active'] else 'off'}, "
                f"{'has a key' if c['has_secret'] else 'no key yet'}, last sync {c['last_sync'][:16] or 'never'}"
                + (f"{NEWLINE}last error: {c['last_error']}" + (f" (the fix: {c['fix']})" if c.get('fix') else '') if c['last_error'] else ''))
    if kind == 'agents.list':
        from . import appfacts, agents as hub_agents
        # ...and the WORKERS a hand-off can name ([researcher]) - they rode every turn as their own block until the
        # prompt went to progressive disclosure (2026-09-25)
        roster = hub_agents.roster(store).strip()
        return ('agents: ' + ', '.join(f"{a['name']} ({a['kind']}{'' if a['active'] else ', off'})" for a in appfacts.agents(store))
                + NEWLINE + 'brains: ' + '; '.join(appfacts.brains(store))
                + (NEWLINE + 'profiles a hand-off can name in `as`:' + NEWLINE + roster if roster else ''))
    if kind == 'repos.list':
        from . import terminal as term
        repos = term.repo_map(store)
        return ('repositories (name one in `as` on a coding_agent hand-off only when sure):' + NEWLINE
                + NEWLINE.join(f'- {r}: {d}' for r, d in repos.items())) if repos else 'No repositories are set up.'
    if kind == 'tools.list': return toolcatalog.bucket_list(str(p.get('bucket') or ''))
    if kind == 'tools.describe':
        why = f"That CALL did not run - {p['why']}. Here is the tool; CALL it again with what it needs.{NEWLINE}" if p.get('why') else ''
        return why + toolcatalog.describe(str(p.get('kind') or '').strip())
    if kind == 'knowledge.search': return know(store, str(p.get('query') or ''))
    if kind == 'timeline.search':
        sel = {k: v for k, v in p.items() if k != 'limit'}
        if sel.get('select'): sel = sel['select']
        from .lookups import _limit
        limit = _limit(p, 12, 40)
        hits = search_timeline(store, sel, limit)
        if not hits: return 'Nothing in the history matches that.'
        return NEWLINE.join(f"m{h['mid']} {h['ref'] or '-'} {h['when'][:16]} {h['who']}: {_cut(h['title'], 120)}" for h in hits)
    from . import lookups
    return lookups.read(store, kind, p)


class CallMiss(Exception):
    """A CALL whose target could not be found - "no report by that name". Written for the model, which gets it back."""


def task_contract(store, kind: str, tid: int, p: dict) -> dict:
    """task.update's and task.check's values, checked against a strict contract - the same check when the model CALLs (a
    CallMiss it fixes) and when the card runs (a 422). Raises ValueError naming what IS allowed. The words used to be guessed
    at: 'me'/'mine'/'myself' read as the owner and any other word became agent:<word>, 'today' and four ways to say none were
    special-cased, and a checklist item was "the first one containing the words" (the owner, 2026-10-11: no word lists - the
    model reads intent, code validates). A date is data, so remind's date PARSER still reads "friday" or "2 weeks"."""
    from . import remind
    out = {}
    if kind == 'task.update':
        who = str(p.get('assignee') or '').strip()
        if who:
            # `none` is the page's "unassigned" - nobody holds it
            allowed = ['owner', 'none'] + [f"agent:{a['Name']}" for a in store.list_agents()]
            if who not in allowed: raise ValueError(f"task.update assignee is one of {', '.join(allowed)} - not {who!r}. Nothing was changed.")
            out['assignee'] = '' if who == 'none' else who
        due = str(p.get('due') or '').strip()
        if due:
            today = f"{datetime.now():%Y-%m-%d}"
            bad = (f"task.update due is a date (YYYY-MM-DD; today is {today}), a day like \"friday\" or \"2 weeks\", or \"none\" to "
                   f"clear it - not {due!r}. Nothing was changed.")
            if due == 'none': out['due'] = ''
            elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', due):
                try: day = datetime.strptime(due, '%Y-%m-%d').strftime('%Y-%m-%d')
                except ValueError: raise ValueError(bad)
                if day < today: raise ValueError(f'{bad} That day has gone.')
                out['due'] = day
            else:
                try: day = (remind.parse(due) or '')[:10]
                except ValueError as e: raise ValueError(f'{bad} ({e})')
                if not day: raise ValueError(bad)
                out['due'] = day
    if kind == 'task.check':
        items, want = store.task_checklist(tid), str(p.get('item') or '').strip()
        # ...and the page's box by its own id when it sends one: the number was read off a list that may have moved since
        hit = (next((i for i in items if i['id'] == p['id']), None) if p.get('id')
               else items[int(want) - 1] if want.isdigit() and 0 < int(want) <= len(items) else None)
        if not hit: raise ValueError(f"task.check item is the checklist item's number - not {want!r}. {task_ref(tid)} has: "
                                     + ('; '.join(f"{n}. {i['text']}" for n, i in enumerate(items, 1)) or 'no checklist') + '. Nothing was ticked.')
        out['item'] = hit
    return out


# the passes a turn gets to fix a missed call (a look-up for the right name, then the action again)
LOOKUP_ROUNDS = 2


def call_turn(store, tid: int, call: dict, item: dict | None, text: str, actor: str = 'owner') -> dict:
    """The model named an operation out of the registry. Turn it into the same proposal card a verb
    makes - NOTHING runs here (PW-123/124); the owner's confirmation is still what executes it.

    A SET is counted before it is offered, so the card says how many and the owner is never told
    "done" about a number nobody checked (the owner, 2026-09-07: it cleared 13 of 72 and said done)."""
    kind, params = call['kind'], dict(call.get('params') or {})
    if toolcatalog.is_read(kind): raise ValueError(f'{kind} is a look-up, not something to confirm')
    it = item or {}
    # ONE ROAD TO AN AGENT. The model reaches a hand-off two ways - DECIDE coding_agent/regular_agent, or this tool with
    # kind coding/general - and only the first chose the worker, the checkout and whether to start at once: the
    # same "research this" was a started researcher on one run and a bare confirm card on the next (the 2026-09-24
    # chat audit). This call takes the decision's road.
    if kind == 'task.create_from_text':
        # ...and the hand-off's own NAME is not a kind: its old name fell through to a card labelled "Start a regular agent" that
        # waited for a yes (the 2026-09-29 replay, 2 runs in 3). The two verb names are the kinds they name; anything
        # else the model must fix itself, never a silent regular agent.
        k = str(params.get('kind') or '').strip().lower()
        params['kind'] = {'coding_agent': 'coding', 'coder': 'coding', 'regular_agent': 'general'}.get(k, k)
        if params['kind'] not in task_kinds.TRIAGE:
            raise CallMiss(f"task.create_from_text kind is task, coding or general - not {k or 'nothing'}. Nothing was started.")
    # ...and a new to-do never names a task that is already open: "Remind me about the Payworth invoice (TQ-0005) tomorrow at
    # 9am" was proposed as a NEW task about TQ-0005 instead of putting TQ-0005 away until then (2026-10-06)
    if kind == 'task.create_from_text' and str(params.get('kind') or '') == 'task':
        for n in re.findall(r'\bTQ-?0*(\d+)\b', str(params.get('text') or ''), re.I):
            t = store.get_task(int(n))
            if t and t.get('Status') not in ('done', 'dropped'):
                raise CallMiss(f"{task_ref(t['TaskId'])} is already an open task - a reminder about it is task.defer on it (ref, until), "
                               "anything else is that task's own action. Nothing was made.")
    # ...and so is a dispatch's: "Start an agent on it" carried the old hand-off name as its kind and failed at the press with "kind must be general
    # or coding" - the verb's name is the kind it names, as it is on task.create_from_text (2026-10-06)
    if kind == 'dispatch.prepare' and params.get('kind') is not None:
        k = str(params.get('kind') or '').strip().lower()
        params['kind'] = {'coding_agent': 'coding', 'coder': 'coding', 'regular_agent': 'general', 'regular': 'general'}.get(k, k)
        if params['kind'] not in task_kinds.AGENT:
            raise CallMiss(f"dispatch.prepare kind is coding or general - not {k or 'nothing'}. Nothing was started.")
    # ...and a watch's `what` is one of four words: "a new reply from Gail Moreno" was proposed, said "Doing it now", and then
    # failed at the run with "what: done | reply | any | off" (2026-10-06). The model fixes it before anything is proposed.
    if kind == 'task.watch' and str(params.get('what') or 'any').strip().lower() not in asks.WATCHES:
        raise CallMiss(f"task.watch what is one of done, reply, any, off - not {str(params.get('what'))[:60]!r}. Nothing was set.")
    # WHO IS WHO, KEPT AND SAID (orgchart.py, 2026-10-22): the owner's word on a person - "Erin is my manager" - is a fact about their own
    # organisation, kept at once on the desk and the phone alike, like a note on a task: nothing leaves, and the chart has no page to bring up
    if kind == 'people.relate': return _relate(store, tid, params, actor)
    # ON THE DESK A NEW JOB IS NEW, FILLED IN (routes): the words on the tab that starts it, its own button the one to press
    if routes() and kind in ('task.create_from_text', 'task.setup'):
        return _new(store, tid, item, str(params.get('kind') or 'general') if kind == 'task.create_from_text' else 'general',
                    str(params.get('text') or text or '').strip())
    if routes() and kind == 'role.apply':
        return _page(store, tid, item, '#profiles', "Opened Profiles - press Set up beside the job you do.")
    if kind == 'task.create_from_text' and str(params.get('kind') or '') in task_kinds.AGENT:
        verb = 'coding_agent' if params['kind'] == 'coding' else 'regular_agent'
        dec = {'verb': verb, 'text': str(params.get('text') or text or '').strip(),
               'as': str(params.get('profile') or params.get('repo') or params.get('agent') or params.get('as') or '').strip()}
        # TYPED WORDS NEVER START AN AGENT (the owner, 2026-10-01): a hand-off in words is a card he presses, however clear
        prop = propose_for(store, tid, dec, None, text, actor)
        record_related(store, tid, item, 'assistant', prop['say'], {'kind': 'proposal', 'key': prop.get('key'), 'title': prop['label'],
                                                                    'op': prop['id'], 'tid': prop.get('tid'), 'ref': prop.get('ref')})
        return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}
    # ...and ONE ROAD TO A REPORT. A CALL carried a config the chat model wrote itself - invented keys ("source",
    # "inputs", "deliver": "always") - and the card read "Create the report - report.create" (the 2026-09-24 audit).
    # The composer builds it from the owner's words, exactly as a DECIDE setup does; the model already said "report".
    if kind == 'report.create':
        return setup_turn(store, tid, text, text, item, actor, sorted_as='report')
    if kind == 'role.apply':
        from . import roles
        want = str(params.get('role') or '').strip().lower()
        hit = want if want in roles.ROLES else next((k for k, v in roles.ROLES.items() if want and want in v['title'].lower()), None)
        if not hit: raise CallMiss('The roles I can set up: ' + '; '.join(f"{k} ({v['title']})" for k, v in roles.ROLES.items()) + '. Nothing was set up.')
        # a yes/no the model may write as words: anything but an explicit yes keeps the owner's mail where it goes today
        return role_card(store, tid, hit, params.get('portal'), str(params.get('route_mail')).strip().lower() in ('true', 'yes', '1'), item, actor)
    # THE DRAFTS IN TURN (the owner, 2026-10-20: "approve all drafts - each draft still goes through its own Send"): the next one comes up
    # with Send lit, and the line says how many wait - never sent from here. On a phone the next draft is the walk's card, its Send a choice
    if kind == 'review.each':
        drafts = [i for i in _pipe(store) if i.get('kind') == 'review' and i.get('rid')
                  and any(b['verb'] == 'approve' for b in row_buttons(store, i))]          # a draft whose row draws its Send now
        if not drafts:
            say_ = 'No draft is waiting for a Send.'
            record_related(store, tid, item, 'assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        nxt = drafts[0]
        if not routes(): return surface(store, nxt['key'], None, actor)
        out = _lit(store, tid, item, nxt, 'approve')
        out['say'] = (f"Lit {out['light']['label']} on {nxt.get('ref') or _where(nxt)} - 1 of {plural(len(drafts), 'draft')} waiting. "
                      "Read it before you press; ask again for the next one.")
        return out
    # ANY BUTTON A ROW DRAWS, BY NAME (the owner, 2026-10-20: "pretty much any action should work"): lit on its row - the table's, or the
    # task `ref` names - never pressed. A phone has no rows to light: its acts are the tools and decisions, answered yes or no
    if kind == 'button.light':
        b = canon_verb(str(params.get('button') or '').strip().lower())
        ref = re.search(r'(\d+)', str(params.get('ref') or ''))
        on = funnel.item_for_key(store, f'task:{int(ref.group(1))}') if ref else (item or None)
        if not on: raise CallMiss('Name the task (TQ-0123) whose button to light, or bring it up first. Nothing was changed.')
        if not routes():
            raise CallMiss(f"A phone has no row to light - CALL the tool or decision {b!r} is (THE BUTTONS BY NAME) and it is asked yes or no.")
        return _lit(store, tid, item, on, b)
    if kind in ('pipe.defer', 'pipe.close'):
        sel = params.get('select') or {}
        hits = select_items(store, sel)
        if not any(v not in (None, '', [], False) for v in sel.values()):
            raise CallMiss(f'{kind} needs `select` naming the set - a sender, words, a kind. Nothing was changed.')
        if not hits:
            say_ = f"Nothing waiting is {_set_words(sel)}, so nothing was {'put away' if kind == 'pipe.defer' else 'closed'}. {pipe_holds(store)}"
            record_related(store, tid, item, 'assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        if kind == 'pipe.defer':
            from . import remind
            try: back = remind.when(remind.parse(params.get('until')) or '')
            except ValueError as e: raise CallMiss(f'pipe.defer until: {e}. Nothing was changed.')
        # ...on the desk and on a phone alike: nothing in a snooze or a close goes out (the owner, 2026-10-20 - the phone asks only for sends)
        table_keys = {i['key'] for i in _on_the_table(store, actor) if i.get('key')} or {e.get('key') for e in (it.get('items') or [it]) if e.get('key')}
        try: done = defer_selected(store, sel, params.get('until'), actor) if kind == 'pipe.defer' else close_selected(store, sel, actor)
        except ValueError as e: raise CallMiss(f'{kind}: {e}. Nothing was changed.')
        n = done['done']
        sw = _set_words(sel)
        say_ = ((f"Snoozed {_set_noun(sel, n)}{' ' + sw if sw else ''} until {done['when']}" if kind == 'pipe.defer' else
                 f"Closed {_set_noun(sel, n)}{' ' + sw if sw else ''}") + ' - ' + ', '.join(_title_cut(t, 50) for t in done['titles'][:3])
                + (' and more' if n > 3 else '') + '.' + (f" {plural(done['stuck'], 'item')} would not go." if done['stuck'] else ''))
        record_related(store, tid, item, 'assistant', say_)
        off = bool(table_keys) and table_keys <= {i['key'] for i in hits}
        return {'say': say_, 'options': [], 'chips': [], 'decision': {'verb': 'next' if off else 'setting'}, 'did': kind}
    if kind == 'pipe.clear':
        sel = params.get('select') or {}
        hits = select_items(store, sel)
        # what is on the table: the walk's own, or the item the turn is about (a batch is its members)
        table_keys = ({i['key'] for i in _on_the_table(store, actor) if i.get('key')}
                      or {e.get('key') for e in (it.get('items') or [it]) if e.get('key')})
        if not hits and not any(v not in (None, '', [], False) for v in (sel or {}).values()):
            # a set that names nothing ("mark them all read" with nothing before it) is a question, not "nothing matches"
            say_ = (f"Which ones? {pipe_holds(store)} Say the notices, the reports, everything from one sender - or "
                    "everything - and I'll clear that. Nothing has been touched.")
            record_related(store, tid, item, 'assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        if not hits:
            # ...in words, as the hit's receipt says them: "matches kind: fyi" read the selector's own field out (the 2026-10-22 re-walk)
            w, sw = _what_of(sel), _set_words(sel)
            what = 'FYI' if w in ('fyi', 'fyis') else 'reports' if w in ('report', 'reports') else f'{w} items' if w else 'items'
            said = f"No {what}{' ' + sw if sw else ''} {'is' if what == 'FYI' else 'are'} waiting"
            # ...and WHAT IS THERE, so a miss can be re-aimed instead of read as "those items do not
            # exist". The owner was looking at eleven rows while this said nothing matched them
            # (2026-09-10): the selector had been offered a category the pipe could not hold.
            say_ = (f"{said}, so there is nothing to clear. "
                    f"{pipe_holds(store)} Say it another way and I'll look again - nothing has been touched.")
            record_related(store, tid, item, 'assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        # ON THE DESK A NAMED SET IS MARKED READ AT ONCE. It had "no button on the desk - the owner puts each one down with Next", and
        # the model, told so, pressed Next: "Clear all the FYI, please." was answered "Next." with four of ~90 on the table (the owner,
        # 2026-10-20: "this is clearly broken"). The selector is the owner's own words naming the set, the count is said, nothing is
        # deleted - search finds every one - and the batch card's All read is this same mark, one card at a time.
        # ...but never what is ON THE OWNER - a to-do, a draft waiting for its Send, a question: "mark everything read" swept those with the
        # notices, and each has its own button to put it down. Those stay, and the line says how many.
        if routes():
            mine = sum(map(lanes.on_you, hits))
            hits = [i for i in hits if not lanes.on_you(i)]
            if not hits:
                say_ = (f"{plural(mine, 'item')} {'is' if mine == 1 else 'are'} waiting on you - each is put down with its own button, "
                        "not by a sweep. Nothing has been touched.")
                record_related(store, tid, item, 'assistant', say_)
                return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
            cleared = [i for i in hits if _clear_one(store, i['key'], actor, 'cleared by the owner')]
            _off_the_table(store, cleared, actor)
            # A RECEIPT, NOT A LIST (the owner, 2026-10-21: "free text should almost never be used in the assistant"): the rail shows what
            # is left; the line counts what went and says it is not gone
            n = len(cleared)
            say_ = (f"Marked {_set_noun(sel, n)} read. Search still finds {'it' if n == 1 else 'them'}."
                    + (f" {plural(len(hits) - n, 'item')} would not clear." if len(hits) > n else '')
                    + (f" {plural(mine, 'item')} waiting on you stay{'s' if mine == 1 else ''} - each has its own button." if mine else ''))
            record_related(store, tid, item, 'assistant', say_)
            # the table among them: the walk moves on, as All read, next does; otherwise the rail is read again (the page's `setting`)
            off = bool(table_keys) and table_keys <= {i['key'] for i in cleared}
            return {'say': say_, 'options': [], 'chips': [], 'decision': {'verb': 'next' if off else 'setting'}, 'cleared': n}
        where = _set_words(sel)
        label = f"Mark {_set_noun(sel, len(hits))} read"
        # ...WHICH ones, on the card, before the yes: a count and a selector were all it said
        shown = '; '.join(_title_cut(' '.join(str(i.get('title') or '').split()), 60) for i in hits[:4])
        summary = f"{_set_noun(sel, len(hits))}{' ' + where if where else ''}: {shown}{' and more' if len(hits) > 4 else ''}"
        tail = ('They are marked read and search still finds them; nothing is deleted. '
                + WAITS)
        prop = _propose_raw(store, tid, 'pipe.clear', 0, {'select': sel, 'text': text}, label, summary, tail, actor, item)
        # A sweep that takes the table with it has settled the table: the walk moves to the next thing
        # instead of sitting on what it just cleared (the owner, 2026-09-11: "did not move to next
        # after"). The KEY is what the page matches against Current; the server does the settling.
        held = current_key(store, tid)
        if held and table_keys and table_keys <= {i['key'] for i in hits}: prop = {**prop, 'key': held, 'settles': True}
        return {'say': prop['say'], 'options': [], 'chips': [], 'decision': None, 'proposal': prop}
    # everything else acts on ONE thing: the item on the table unless the call named its own target
    for f in toolcatalog.CONTEXT_FILLED:                 # a pile key is ours to supply, never the model's
        if f in operations.KINDS[kind][1] and not params.get(f):
            if not it.get(f): raise ValueError(f'there is nothing on the table for {kind} to act on')
            params[f] = it[f]
    # THE APP ITSELF, BY NAME (appfacts). The model says "the AR report"; the id is ours to find, and a
    # name that finds nothing never proposes - the answer lists what exists, so the next words can aim.
    named, tk = '', operations.KINDS[kind][0]
    # ...except a split of a mail that has no task yet, which splits the MESSAGE (split_item, from the pile key)
    if tk in ('task', 'review') and not (kind == 'task.split' and not params.get('ref') and not it.get('tid') and it.get('mid')):
        # THE TASK NAMED (TQ-0123) OR THE ONE ON THE TABLE - never a guess, and never its mail's id, which `target`
        # below falls to first (a CALL on a mail's card put task.complete on the task with the MESSAGE's number).
        # A review tool acts on the draft waiting on that task. (2026-09-25: every task-page action is a tool.)
        ref = re.search(r'(\d+)', str(params.pop('ref', '') or ''))
        # ...but an AGENT is never put on an old task by default: a new ask typed while something sits on the table
        # became a run on that task (the owner, 2026-09-29: "if i ask for task it should not merge with old one or agent
        # run unless i ask"). These two must NAME the task; a new job is task.create_from_text, which the miss says.
        # ...but CONTINUING is not attaching: it reopens the task's OWN saved session (the owner, 2026-09-30: "continue session
        # and tell the coding agent to merge it in" on a close-out card was refused for want of a ref, and the retry
        # fell to the close-out itself). On the table, with a session to reopen, the table's task is what they mean.
        resumes = kind == 'agent.continue' and not ref and it.get('tid') and store.resumable_session(it['tid'])
        if kind in toolcatalog.ATTACH_AGENT and not ref and not resumes:
            raise CallMiss(f"{kind} puts an agent on a task that already exists - name it (its TQ ref, the one on the table "
                           "included). A new job is task.create_from_text. Nothing was started.")
        t = int(ref.group(1)) if ref else it.get('tid')
        if not t or not store.get_task(t): raise CallMiss('Name the task (TQ-0123), or open it first - nothing was changed.')
        if tk == 'review':
            rv = (store.get_review(it['rid']) if not ref and it.get('rid') else None) or store.pending_review(t)
            if not rv: raise CallMiss(f'{task_ref(t)} has no draft waiting - nothing to {kind.split(".")[1]}.')
            params['target'] = rv['ReviewId']
        else: params['target'] = t
        named = task_ref(t)
        if kind in ('task.update', 'task.check'):             # a value off the contract is the model's to fix before any card
            try: task_contract(store, kind, t, params)
            except ValueError as e: raise CallMiss(str(e))
        if kind == 'agent.stop': params.setdefault('wrap', True)    # the task page's Stop and save: written up, then stopped
        # THE CALL ROAD CHECKS WHAT THE BUTTONS CHECK (real-AI check, 2026-10-18): a hand-off to someone who never wrote here and a
        # stop with nothing running were offered as cards that failed only at the press, in jargon. The fact goes back to the model,
        # which asks or says so - never a card nobody can run
        # ...and so does a summary sent out: a name nobody by it wrote as has no address to draft it to
        if kind in ('task.handoff', 'task.share'):
            who = str(params.get('who') or '').strip()
            if who and not person(store, who):
                raise CallMiss(f"Nobody called {who} has written here, so there is no address to hand {named} to - ask the owner for "
                               f"their email address ({kind} takes an address as `who`). Nothing was written.")
        if kind == 'agent.stop' and not _agent_running(t) and (store.get_task(t) or {}).get('RunStatus') != 'running':
            raise CallMiss(f"No agent is running on {named} - there is nothing to stop. Say so in plain words. Nothing was changed.")
        # ...and an ANSWER with nobody to hear it (real-AI walk, 2026-10-18): "tell the agent on TQ-n ..." with no session on TQ-n
        # came back as a card, and on the next try as a coding agent nobody asked for. The fact goes back, with the real roads
        # (an agent's own card on the table was built from its live session: it is the run that asked)
        if (kind == 'agent.answer' and not (it.get('kind') == 'agent' and int(it.get('tid') or 0) == int(t)) and not _agent_running(t)
                and (store.get_task(t) or {}).get('RunStatus') != 'running'):
            again = f"{buttons.label('continue')} (agent.continue) reopens its last session, or " if store.resumable_session(t) else ''
            raise CallMiss(f"No agent is on {named} - nothing would hear that. Say so in plain words and offer what is real: {again}"
                           "starting an agent on it (dispatch.prepare), which is the owner's call. Nothing was sent.")
    if tk in ('source', 'connector', 'setting', 'script'):
        from . import appfacts
        def _miss(say_): raise CallMiss(say_)         # the model's to fix (say), never passed on as it stands
        # NAMING NOTHING MEANS THE TABLE: "rerun it" over a failed report came as report.rerun {} and missed, and the retry
        # picked another report by name (the 2026-10-01 press audit)
        if tk == 'source':
            title, sid = str(params.pop('title', '') or ''), params.pop('source_id', None) or params.get('target')
            if not title and not sid: sid = it.get('source_id')
            r = appfacts.find_report(store, title, sid)
            if not r: return _miss('No report by that name. The ones set up: ' + ', '.join(x['title'] for x in appfacts.reports(store)[:20]) + '.')
            params['target'], named = r['source_id'], r['title']
            if kind == 'report.route' and (str(params.get('line') or '').lower() not in ('timeline', 'alert', 'send')
                                           or str(params.get('how') or '').lower() not in ('always', 'ai', 'rule', 'never')):
                return _miss('Say which line (timeline, alert or send) and how it goes: every run (always), '
                             'the AI decides (ai, with what to look for), a rule, or never.')
        elif tk == 'connector' and kind != 'connection.create':
            name, cid = str(params.pop('name', '') or ''), params.pop('connector_id', None) or params.get('target')
            if not name and not cid and str(it.get('key') or '').startswith('conn:'): cid = it['key'][5:]
            c = appfacts.find_connection(store, name, cid)
            if not c: return _miss('No connection by that name. Connected: ' + ', '.join(x['name'] for x in appfacts.connections(store) if x['active']) + '.')
            params['target'], named = c['connector_id'], c['name']
        elif kind == 'connection.create' and routes():
            # ON THE DESK, THE CATALOGUE'S CARD, BROUGHT UP (the owner, 2026-10-20: "add LinkedIn as a connector"): any card the catalogue
            # has - LinkedIn was refused for not being a connector role - found by its type, title or match words; one already
            # connected opens with its Add another named; a name the catalogue lacks is said with its closest cards
            c = catalogue_card(str(params.get('type') or params.get('name') or ''))
            if not c or c.get('planned'):
                want = str(params.get('type') or params.get('name') or '').strip()
                near = ', '.join(x['title'] for x in catalogue_near(want))
                return _miss(f"There is no {want or 'such'} connector{' yet' if c else ''}{'; the closest are ' + near if near else ''}. "
                             'Say so in plain words, naming those. Nothing was changed.')
            ex = store.get_connector_by_type(c['type'])
            # a few words beside the card it opens (the owner, 2026-10-21): the card lights its own first step
            said = (f"Opened your {c['title']} card - Add another connects a second one." if ex and ex.get('Active')
                    # ...and the safety point in the same few words: a key or password belongs on the card, never typed into the chat
                    else f"Opened the {c['title']} card - keys go there, never in chat.")
            # &step=1: the card lights its first real step and the page finishes the line with it (connectorStep.js STEP_SAID)
            return _page(store, tid, item, f"#connector={c['type']}" + ('' if ex and ex.get('Active') else '&step=1'), said)
        elif kind == 'connection.create':
            # the card OF THAT TYPE, never the item on the table: "connect my Jira" over TQ-0001 fell through to the target line
            # below and its id was saved as a ConnectorId (2026-10-06)
            typ = str(params.get('type') or '').strip().lower()
            if typ not in store_mod.DEFAULT_ROLES: return _miss('No connection of that type. The types: ' + ', '.join(sorted(store_mod.DEFAULT_ROLES)) + '.')
            ex = store.get_connector_by_type(typ)
            if ex and ex.get('Active'): return _miss(f"{ex.get('Name') or typ} is already connected - nothing to create. Say test it, or open {places.name('connections')}.")
            params.update(type=typ, name=str(params.get('name') or (ex or {}).get('Name') or typ.title()).strip())
            params['target'], named = (int(ex['ConnectorId']) if ex else None), f"{params['name']} ({typ})"
        elif tk == 'setting':
            rows = appfacts.settings(store)
            key, label_ = str(params.get('setting') or params.get('key') or '').strip(), str(params.get('label') or '').strip().lower()
            r = next((x for x in rows if x['key'] == key), None) or next((x for x in rows if label_ and label_ in x['label'].lower()), None)
            if not r: return _miss('No setting by that name - settings.list <group> names them. Nothing was changed.')
            params['setting'], named = r['key'], r['label']; params.pop('label', None); params.pop('key', None); params['target'] = 0
        elif tk == 'script':
            want = str(params.get('name') or '').strip().lower()
            hit = next((n for n, _ in appfacts.SCRIPTS if want and (want in n.lower() or n.lower() in want)), None)
            if not hit: return _miss('The scripts are: ' + '; '.join(n for n, _ in appfacts.SCRIPTS) + '.')
            params['name'], named = hit, hit; params['target'] = 0
    target = params.pop('target', None)
    # ...and a connection is never the item on the table: its id is a message's or a task's, not a ConnectorId
    if not target and tk != 'connector': target = it.get('mid') or it.get('tid') or it.get('rid')
    target = target or 0
    label = op_label(kind, params)
    # a brief has no row behind it: what it is about is its own words, never the item on the table
    if tk == 'text': named = named or str(params.get('title') or params.get('text') or '').strip()[:120]
    # ...and a fact is what it says: "Remember it: memory.remember" put the tool's name on the card (real-AI check, 2026-10-18)
    if kind == 'memory.remember': named = named or str(params.get('note') or '').strip()[:120].rstrip('.')    # the line adds its own stop
    if tk == 'task' and (wrote := _task_writes(store, tid, kind, int(target or 0), params, named, actor)) is not None: return wrote
    if routes(): return _route(store, tid, kind, int(target or 0), params, named, it, item, text, actor)
    # the phone's words: one yes-or-no, whatever the kind
    instant = False
    # ...and the ANSWER to the agent asking on the table, whichever road the model took to it (the tool, or the answer_agent verb in
    # AUTO): it goes straight in, as the agent's Answer pill does - a real-brain check found the tool road waiting for a confirm the
    # verb road skips (2026-10-08; the owner's 2026-10-02 rule: an answer to an asking agent goes directly to it)
    if kind == 'agent.answer' and it.get('kind') == 'agent' and it.get('asking') and it.get('tid') and int(target or 0) == int(it['tid']):
        instant = True
    # ...and a SCRIPT started by name: a walk or a report's set-up sends nothing and changes nothing, and the phone keeps its yes/no for
    # what goes out (2026-10-20). "walk me through my tasks" typed asked "Start a script by its name: ...?" and its yes walked nowhere
    # (the 2026-10-22 re-walk); it is the opener's own Walk me through now, at the card on the table (remote_assistant.carry_out)
    if kind == 'script.start': instant = True
    tail = 'Doing it now.' if instant else WAITS
    prop = _propose_raw(store, tid, kind, int(target or 0), params, label, named or _where(it) or label, tail, actor, item)
    if instant: prop = {**prop, 'auto': True}
    return {'say': prop['say'], 'options': [], 'chips': [], 'decision': None, 'proposal': prop}


# where a report's or a connection's act is pressed, on its own page
REPORT_SAYS = {'report.run': 'run it', 'report.rerun': 'run it again', 'report.pause': 'pause it', 'report.resume': 'switch it back on',
               'report.route': 'change where it goes', 'report.edit': 'change it', 'report.delete': 'remove it'}
CONN_SAYS = {'connection.pause': 'switch it off', 'connection.resume': 'switch it on', 'connection.test': f"press {buttons.label('test_connection')}",
             'connection.create': 'fill it in and test it'}
# a task's own part that has no button of its own - the task is brought up and the line says where on it
ON_TASK = {'task.check': 'tick it on its checklist', 'task.checklist': 'its checklist is on it'}


def _task_writes(store, tid: int, kind: str, target: int, params: dict, named: str, actor: str) -> dict | None:
    """THE TASK PAGE'S OWN WRITES, run by the Assistant and said - on the desk and on a phone alike (the owner, 2026-10-20: "anything you can do,
    you can do via the Assistant"; the phone keeps its yes/no only for what goes out). None when the call is not one of them."""
    # A NOTE AND A DUE DAY RUN HERE, said (the owner, 2026-10-20): neither has a button on the row - a note is typed on the task page and the
    # due day had no picker - so "file a note on it" and "set the due date to friday" were refused. Both are the task page's own writes.
    if kind == 'task.comment' and target:
        note = str(params.get('text') or '').strip()[:4000]
        if not note: raise CallMiss('task.comment needs `text` - the note itself. Nothing was written.')
        store.add_comment(target, actor, 'human', note)
        return _did(store, tid, f"Added a note to {named}: \u201c{_title_cut(note, 120)}\u201d.", 'task.comment')
    # THE TO-DOS, RUN AND SAID (the owner, 2026-10-20): tick, untick, note one, add some - the task page's own writes
    if kind == 'task.check' and target:
        hit = task_contract(store, kind, target, params)['item']
        note, done = params.get('note'), params.get('done')
        did = []
        if note is not None:
            store.note_checklist_item(target, hit['id'], str(note), actor)
            did.append(f"Noted on {named}'s \u201c{_title_cut(hit['text'], 60)}\u201d: {_title_cut(str(note), 120)}" if str(note).strip()
                       else f"Took the note off {named}'s \u201c{_title_cut(hit['text'], 60)}\u201d")
        if done is not None or note is None:
            on = str(done if done is not None else True).lower() not in ('false', '0', 'no')
            from . import slots
            if on and any(i['id'] == hit['id'] for i in slots.open_(store, target)): slots.drop(store, target, hit['id'], actor)
            else: store.tick_checklist_item(target, hit['id'], on, actor)
            did.append(f"{'Ticked' if on else 'Unticked'} \u201c{_title_cut(hit['text'], 60)}\u201d on {named}")
        return _did(store, tid, '; '.join(did) + '.', 'task.check')
    if kind == 'task.checklist' and target and params.get('add') and not params.get('items'):
        add = params['add'] if isinstance(params['add'], list) else [params['add']]
        new = store.merge_task_checklist(target, [str(x) for x in add], actor)
        if not new: raise CallMiss(f'{named} already has those to-dos. Say so. Nothing was added.')
        return _did(store, tid, f"Added {plural(len(new), 'to-do')} to {named}: " + '; '.join(f'\u201c{_title_cut(i["text"], 60)}\u201d' for i in new) + '.',
                    'task.checklist')
    # A TEAMMATE'S AGENT, ASKED (the owner, 2026-10-21: "ask Erin's agent whether X" sends over Reason Network and the reply shows on
    # the task): only someone on the card's trusted list - anyone else is said back, nothing sent (reasonnet.ask)
    if kind == 'task.ask_agent' and target:
        from . import reasonnet
        try: r = reasonnet.ask(store, target, str(params.get('who') or ''), str(params.get('text') or ''), actor)
        except reasonnet.Miss as e: raise CallMiss(f'{e} Say so in plain words.')
        except Exception as e: raise CallMiss(f'Reason Network could not send it ({str(e)[:200]}). Say so in plain words. Nothing was sent.')
        return _did(store, tid, f"Asked {r['to']}'s agent over Reason Network - its reply will be noted on {named}.", 'task.ask_agent')
    if kind == 'task.update' and target and not (params.get('priority') or params.get('assignee')):
        from . import remind
        c = task_contract(store, kind, target, params)
        title, did = str(params.get('title') or '').strip()[:200], []
        if title: store.update_task(target, {'Title': title}, actor); did.append(f'renamed {named} \u201c{title}\u201d')
        if c.get('due') is not None:
            remind.set_due(store, target, c['due'], actor)
            did.append(f"set {named}'s due day to {datetime.strptime(c['due'], '%Y-%m-%d'):%a %d %b}" if c['due'] else f"cleared {named}'s due day")
        if did: return _did(store, tid, _cap(' and '.join(did)) + '.', 'task.update')
    return None


def _route(store, tid: int, kind: str, target: int, params: dict, named: str, it: dict, table: dict | None, text: str, actor: str) -> dict:
    """call_turn on the desk (routes): the tool the model picked, as the button that does it - lit on its item, brought up first - or the page
    that holds it, opened beside the answer. A tool with neither goes back to the model as a miss it can fix by answering in words."""
    from . import appfacts
    tk = operations.KINDS[kind][0]
    if kind == 'agent.answer' and it.get('kind') == 'agent' and it.get('asking') and int(it.get('tid') or 0) == target:
        return _answer_now(store, tid, table, target, str(params.get('text') or text or '').strip(), actor)
    if kind == 'script.start':
        return _new(store, tid, table, 'report', '') if 'report' in str(params.get('name') or '') else surface(store, None, None, actor)
    if kind == 'memory.remember':
        return _page(store, tid, table, '#settings=memory', f"Opened {places.name('memory')} - add it as a note there; it is used from then on.")
    if tk == 'setting':
        r = next((x for x in appfacts.settings(store) if x['key'] == params.get('setting')), None) or {}
        return _page(store, tid, table, f"#settings=config&group={quote(r.get('group') or '')}&key={quote(str(params.get('setting') or ''))}",
                     f"Opened Settings{' → ' + r['group'] if r.get('group') else ''} at {r.get('label') or named} - change it there.")
    if tk == 'connector':
        typ = str(params.get('type') or '') or next((c['type'] for c in appfacts.connections(store) if c['connector_id'] == target), '')
        if typ: return _page(store, tid, table, f'#connector={typ}', f"Opened {named or typ}'s card under Connections - {CONN_SAYS.get(kind, 'change it')} there.")
    on = None
    if tk == 'item' or (tk == 'message' and table and int(table.get('mid') or 0) == target): on = table
    elif tk == 'message' and target: on = funnel.item_for_key(store, f'msg:{target}')
    elif tk in ('task', 'review') and target:
        t = target if tk == 'task' else int((store.get_review(target) or {}).get('TaskId') or 0)
        on = table if table and int(table.get('tid') or 0) == t else funnel.item_for_key(store, f'task:{t}') if t else None
    elif tk == 'source' and table and int(table.get('source_id') or 0) == target: on = table
    if tk == 'source' and not on and target:
        return _page(store, tid, table, f'#report={target}', f"Opened {named or 'the report'} under Reports - {REPORT_SAYS.get(kind, 'change it')} there.")
    b = (next((FIELD_BUTTON[k] for k in FIELD_BUTTON if params.get(k)), '') if kind == 'task.update'
         else {'coding': 'coding_agent', 'general': 'regular_agent'}.get(str(params.get('kind') or ''), 'mine') if kind == 'task.create_from_message'
         else 'close_note' if kind == 'task.complete' and str(params.get('note') or '').strip() else KIND_BUTTON.get(kind, ''))
    if on and b:
        why = cannot(on, b, store)
        if why: raise CallMiss(f"{why} Say so in plain words. Nothing was changed.")
        # THE NOTES GO WITH IT: "rerun the agent with these notes: use the new template" lit Continue and dropped the notes (the real-CLI
        # walk, 2026-10-20) - they are in Continue's box when it is pressed, and the line says so
        note = str(params.get('note') or params.get('text') or '').strip() if b == 'continue' else ''
        return _lit(store, tid, table, on, b, note=note)
    if on and kind in ON_TASK:
        said = f"Brought up {_where(on) or 'it'} - {ON_TASK[kind]}."
        record(store, tid, 'assistant', said)
        return {'say': said, 'options': [], 'chips': [], 'decision': None,
                'light': {'verb': '', 'label': '', 'key': on.get('key') or '', 'tid': on.get('tid'), 'ref': on.get('ref') or ''}}
    raise CallMiss(f"{kind} has no button the owner presses here, so it is not yours to run from the chat - say in plain words where they "
                   "do it, or that it is not something done from here. Nothing was changed.")


def _carry_out(store, tid: int, text: str, words: dict, item0: dict | None, actor: str) -> dict:
    """A hand-off to a person: already a REVIEW for the owner's yes rather than a proposal card (a draft, sent
    only on approval). A switch used to come here too, as a canned sentence; settings are the setting.set tool."""
    rec = lambda body, card=None: record_related(store, tid, item0, 'assistant', body, card)
    if words['verb'] == 'forward':
        try: out = forward_item(store, item0 or {}, words.get('who') or '', words.get('text') or '', actor)
        except Exception as e:
            say_ = f"I could not hand that over - {e}. Open the task and use Hand off, where you can pick the person and the channel."
            rec(say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"Written as a hand-off to {out['to']} - it is below for your yes, and nothing goes until you give it. "
                f"{buttons.label('approve')} sends it - this one stays open until you {buttons.label('close')}.")
        rec(say_, out['card'])
        return {'say': say_, 'options': [], 'decision': {'verb': 'forwarded', 'reviewId': out['reviewId'], 'to': out['to']}}
    raise ValueError(f"{words['verb']} is a proposal - it is never carried out on the words alone")


def _agent_task(store, item0: dict | None, text: str) -> int | None:
    """Which task the owner means when they say "close the agent": the one they NAMED, else the one on
    the table if an agent is on it - nothing else. Never a task just because its card
    happens to be open - that is how "close the agent working" closed something else entirely."""
    ref = re.search(r'\bTQ-?0*(\d+)\b', text or '', re.I)
    live = {t.get('taskId'): t for t in _live(store) if t.get('taskId')}
    if ref and int(ref.group(1)) in live: return int(ref.group(1))
    if item0 and item0.get('tid') in live: return item0['tid']
    return None      # never "the only one running": that could be another task's agent (the owner, 2026-09-25)


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
                            'Reason': f'you asked for this setting: {says}',
                            '_task_title': f'Setting · {says}'[:140], '_task_kind': 'task'})
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


def person(store, who: str) -> dict | None:
    """Someone named in the owner's words, from the people who have actually written (the book the hand-off picker uses): a
    name or an address - {Name, Email} - or None for a name nobody by it has written as. Never guessed."""
    from .routing import tokens
    who = str(who or '').strip()
    if '@' in who and ' ' not in who: return {'Name': '', 'Email': who.lower()}
    want = [w for w in tokens(who) if len(w) > 1]
    if not want: return None
    for p in store.people(400):
        hay = set(tokens(f"{p.get('Name') or ''} {p.get('Email') or ''}"))
        if any(w in hay or any(h.startswith(w) for h in hay) for w in want): return p
    return None


def forward_item(store, item: dict, who: str, text: str, actor: str = 'owner') -> dict:
    """"Forward it to Erin" / "ask Dovid to handle it": the hand-off written for the owner's yes,
    never sent from a sentence. The address comes from the people who have actually written (the
    same book the task page's hand-off picker uses); a name nobody knows is said so, not guessed."""
    from . import outbound
    from .routing import tokens
    if not [w for w in tokens(who or '') if len(w) > 1]: raise ValueError('say who it goes to')
    hit = person(store, who)
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
    leave a reply waiting for a yes), then the task itself. False when already closed with no draft."""
    # ...and a write-up running for this task (writeup.py) finishes first: a close from anywhere - the task page, the chat, an
    # operation - never ends the session before its transcript is harvested, and lands on what the write-up left
    from . import writeup
    if not writeup.in_job(): writeup.wait_for(tid)
    t = store.get_task(tid) or {}
    if not t: return False
    closed = t.get('Status') in ('done', 'dropped')
    rv = store.pending_review(tid, live_only=False)
    if closed and not rv: return False
    while rv:
        store.decide_review(rv['ReviewId'], 'no_reply', None, actor, note='the owner closed the task')
        rv = store.pending_review(tid, live_only=False)
    # ...and a draft HELD while an agent worked it is decided too - it stayed held and invisible for good (A6)
    for h in store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status='held'", (tid,)):
        store.decide_review(h['ReviewId'], 'no_reply', None, actor, note='the owner closed the task')
    # a closed task has nobody working it: the PATCH road stops the session and this one did not, so
    # "close it" from the chat left the agent running in the checkout (2026-09-03)
    try:
        from . import terminal
        s = terminal.session_for(tid)
        if s and getattr(s, 'alive', False):
            terminal.close(s.sid)
            store.add_comment(tid, actor, 'human', 'Stopped the agent - the task was closed from the chat.')
    except Exception as e: logger.warning(f'concierge: the agent on {task_ref(tid)} was not stopped - {e}')
    if not closed: store.update_task(tid, {'Status': 'done'}, actor)
    from . import selfclose
    selfclose.unclaim(store, tid, actor)            # a finished task is nobody's to end any more
    store.audit('task', tid, 'close_from_assistant', actor)
    # ...and the row goes off Unread with it (the owner, 2026-09-07: "it should just go off the unread
    # timeline"). Closing is the decision, wherever it was made; only the CHAT's close used to post the
    # read receipt, so a close on the Tasks page left the mail behind it sitting in the pipe as an fyi.
    # A reply that arrives afterwards is a new unit and comes back unread, and All keeps the whole thread.
    try: funnel.settle(store, f'task:{tid}', 'done', actor, note='the task was closed')
    except Exception as e: logger.debug(f'the closed task did not settle its item: {e}')
    funnel.invalidate()
    return True


# What "set something up" opens. It used to be a CODING task on the default agent, which sent a coding agent
# into a checkout to build what the app already has: asked to set up the Zoho invoice integration -
# a connector card and a report, both shipped - it opened a session in the wrong repository entirely
# (the owner, 2026-09-03: "This was big mistake... it doesn't need coding agent just a regular agent
# that will walk me through it"). A set-up is a WALK-THROUGH: the conversational agent (general.py),
# no repository, no checkout, nothing built. Real building is a hand-off the owner asks for by name.
SETUP_KIND = 'general'
HANDOFF_REF = 'assistant:handoff'   # a coding job the owner handed off from the chat (setup_task, kind coding)

WALK_SORT = ('The owner asked for something to be set up. Decide which of two jobs this is. '
             'CONFIGURING TASKUARY ITSELF: its AI brain, a connector card, a source it reads, a '
             'report or workflow, one of its operator documents - anything that has a screen in '
             'this app. OPERATING ANOTHER SYSTEM on their behalf: signing into a site, driving a '
             'portal, a tool this app has no card for. Answer with JSON only: {"taskuary": true} '
             'for the first, {"taskuary": false} for the second.')


def walk_is_external(store, text: str, llm=None) -> bool:
    """Is this walk over the owner's OWN systems rather than over configuring Taskuary?

    The shipped taskuary-setup SKILL is the procedure for configuring this install, and the wrong
    map for anything else: asked to log into a payroll portal and clock in every morning, a walk
    carrying it reads out the AI-brain-and-inbound-source checklist instead (the owner, 2026-09-10:
    "it's supposed to walk me through this?").

    The MODEL reads the intent - there is no word list here - and only a clear "no" moves the walk
    off the skill. An unsure answer, a brain that is not there, one that returns prose or dies
    keeps it, because most set-ups really are about this install."""
    try: brain_ = llm or brain(store, fast=True)
    except Exception as e:
        logger.debug(f'the walk sort has no brain - {e}'); return False
    if not brain_: return False
    from . import compose
    try: out = compose._json(brain_(WALK_SORT, str(text or '')[:2_000], max_tokens=60)) or {}
    except Exception as e:
        logger.info(f'the walk sort did not answer, so the walk keeps the skill - {str(e)[:200]}'); return False
    return out.get('taskuary') is False


def setup_task(store, text: str, actor: str = 'owner', title: str = '', kind: str = SETUP_KIND,
               agent_job: bool = False, repo: str = None, profile: str = None) -> dict:
    """'Set up a report that...': a task with the owner's words in it, opened for the agent that can
    walk them through it. `kind` is 'general' for a walk-through and 'coding' for a hand-off the owner
    asked for (concierge's `coding_agent` verb), which is the only path that starts an agent in a checkout."""
    from . import asks, ingest
    text = str(text or '').strip()
    if not text: raise ValueError('say what to set up')
    # the title the model named (the set-up sort's, the hand-off's), or the owner's sentence as said. A regex used to strip a
    # leading verb off it, and "Add Erin to payroll" became "Erin to payroll" (the owner, 2026-10-11: no word lists)
    title = _title_cut(title) or _title_cut(' '.join(text.split()))
    from . import browserview
    tid = store.create_task({'Title': title[:1].upper() + title[1:], 'Summary': text, 'Kind': kind, 'Status': 'open', 'Priority': 'normal', 'OriginBase': 'owner',
                             # a CODING hand-off is the owner's own job, not a Taskuary set-up: marked
                             # assistant:setup it read as "Taskuary's own work" and opened in Taskuary's
                             # checkout, whatever it was about (the owner, 2026-09-24: an issue in another repository)
                             'Source': 'assistant', 'SourceRef': 'assistant:agent' if agent_job else HANDOFF_REF if kind == 'coding' else 'assistant:setup',
                             'AskedVia': asks.door(),       # the owner's own ask, and the door it came from (asks.py)
                             # A walkthrough may have to log into a portal or point at the exact
                             # setting. Its Assistant session owns that browser; a coding handoff
                             # keeps the ordinary task controls instead.
                             # the checkout the owner confirmed on the card is the override (terminal.repo_tag)
                             'Tags': browserview.WANTS if kind == SETUP_KIND and not agent_job else (f'repo:{repo}' if repo else ''),
                             # the worker the owner's hand-off named: its rules seed the session (general.assigned_role)
                             **({'Assignee': f'agent:{profile}'} if profile else {})}, actor)
    # A task the owner creates in the Assistant deserves the same concrete list surface as work
    # triage creates from an incoming ask. With no checklist the card rendered Summary as a banner,
    # then rendered the identical own-message below it; there was no box and the ask appeared three
    # times. The initial ask is the first real item. It can be split or edited later like any list.
    store.set_task_checklist(tid, [text], actor)
    # The ask is the conversation's FIRST TURN, not a note filed beside it. As a plain human comment
    # the chat does not render it, so a walk showed an answer with no question above it and read as
    # a walk that had never started (the owner, 2026-09-14). A hand-off has no conversation to open
    # here - the agent's own brief becomes its first turn - so there the ask stays a note.
    if kind == SETUP_KIND and not agent_job: store.add_comment(tid, actor, general.USER_TYPE, text)
    else: store.add_comment(tid, actor, 'human', f'Asked in the Assistant chat: {text}')
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
                                       # the agent's own question and the answers it offered: what a chat numbers, and
                                       # the request an answer is bound to (funnel.from_agents, workerstate PW-228)
                                       'choices', 'request_id', 'request_kind', 'closeout', 'rides',
                                       # a broken connection whose bridge runs on this machine: the card offers to restart it
                                       'restart',
                                       # an FYI from a list that names its own way off it: the card's Unsubscribe (unsubscribe.py)
                                       'unsub',
                                       'presentation_revision', 'order_band', 'processing_id', 'member_ids', 'members', 'aliases', 'unread', 'deferred', 'actionable', 'paused', 'closed',
                                       'brief_today')}


def move_on(store, key: str, actor: str = 'owner') -> dict:
    """Put down the thing the owner is walking away from. It is READ, and that is all: Next settles
    nothing. An open task stays under Tasks, passed for the rest of this walk; the next walk starts with it again.

    Next used to END a draft waiting for a yes as `no_reply` and close its task (2026-09-07: "if you hit
    next then no more reply needed"). The Passed band replaced that - "still yours, you pressed Next" -
    and the two disagreed: a reply walked past was thrown away while the rail promised it back (the
    owner, 2026-09-23: "i thought if you hit next it goes to passed section?"). Not sending one is
    Close, said on purpose.

    The TASK is left alone. Nothing is cancelled and no session is stopped."""
    if not key: return {}
    # The row being left is found in the build the rail already holds, while nothing has been written since it began
    # (on Next the commit guard has just re-read the rail - recheck_selection -> funnel.pile, rebuilt if anything moved).
    # A keyed build only to read back the same row's sig was 0.2-1 s of every Next on a big home (2026-10-20). Not
    # there (older than the rail, a batch key) or written since - the lookup it always was.
    held = funnel.rail_item(store, key)
    if held is not None:
        funnel.settle(store, key, 'surfaced', actor, note=held.get('sig'), read=True, put_down=True)
        return {'key': key, 'read': True, 'reviews_ended': []}
    try: item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    except Exception as e:
        logger.debug(f'concierge: nothing to put down for {key} - {e}'); return {}
    if not item: return {}
    funnel.settle(store, key, 'surfaced', actor, note=item.get('sig'), read=True, put_down=True)
    return {'key': key, 'read': True, 'reviews_ended': []}


def _fyi_card(item: dict, batch: list, gists: dict) -> tuple:
    """(the batch with each entry's gist, the line, the card) for an FYI batch - one road for the walk (surface) and for the
    answer prepared ahead of it (prepare_next)."""
    say = (f"{plural(len(batch), 'thing')} people told you, nothing to do: "
           + '; '.join(f"{i.get('who') or 'someone'} - {i['title']}" for i in batch) + '.')
    batch = [i | {'summary': gists.get(n) or i.get('summary') or i.get('preview') or ''} for n, i in enumerate(batch, 1)]
    card = {'key': 'fyis:' + ','.join(i['key'] for i in batch), 'kind': 'fyis', 'lane': 'fyi',
            'title': f"{len(batch)} fyi", 'who': '', 'when': batch[0].get('when'),
            'since': batch[0].get('since'), 'channel': batch[0].get('channel'),
            'why': 'people told you things; nothing to do', 'items': [card_for(i) for i in batch],
            # ...and the keys themselves, so the work rail can draw ONE bracket round the very
            # rows that are on the table. card_for is a whitelist and never carried them, so the
            # batch went up with nothing the rail could match and the rows simply vanished from
            # it (the owner, 2026-09-16: "it does not highlight the ones in the feed but removes
            # them ... just show them all as current as we normally do").
            'members': [i['key'] for i in batch],
            'presentation_revision': item.get('presentation_revision')}
    return batch, say, card


ANSWER_FIELDS = ('item', 'say', 'options', 'chips', 'left', 'exhausted', 'over')


def answer_hash(out: dict) -> str:
    """What a Next answer puts on the screen, hashed: the prepared answer and the committed one are compared by it."""
    import hashlib
    shown = {k: out[k] for k in ANSWER_FIELDS if k in out}
    return hashlib.sha256(json.dumps(shown, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def prepare_next(store, selection, token: str) -> dict | None:
    """PREPARED NEXT (the owner, 2026-10-20): the answer a press of Next would give for this captured selection, worked out
    ahead of the press with no write, so the page can draw it the moment Next is pressed. The press still commits and
    answers as it always did; the page compares the two by answer_hash and the committed answer replaces the card when
    they differ. None where the answer cannot be known ahead: nothing selected, a model introducing the item (INTRO_AI),
    an agent holding the row (its card is the live pane), a batch assembled from the cached pile."""
    item, p = selection.selected, selection.pile
    if item is None or INTRO_AI: return None
    if item['lane'] == 'working' or (item.get('working') and item['kind'] not in ('agent', 'review', 'action')): return None
    if funnel.batchable(item):
        if item.get('kind') != 'fyis': return None
        batch, say, card = _fyi_card(item, item.get('items'), {})
        if routes(): say = brought_up(card)
        card['chips'] = chips_for(store, card)
        out = {'item': card, 'say': say, 'options': [], 'chips': card['chips'], 'left': len(p['items']) - len(batch)}
    else:
        chips = chips_for(store, item, '')
        say = brought_up(item) if routes() else fallback(item, True, store=store)
        out = {'item': item | {'chips': chips}, 'say': say, 'options': [], 'chips': chips, 'left': len(p['items']) - 1}
    return {'selection_revision': token, 'answer': out, 'answer_hash': answer_hash(out)}     # the token the page echoes (navigation.fields)


KIND_WORDS = {'report': 'a report', 'idea': 'an Advisor idea', 'meeting': 'a meeting', 'fyi': 'an FYI', 'agentdone': "an agent's result"}


def brought_up(item: dict, picked: bool = False) -> str:
    """THE CARD CARRIES IT (the owner, 2026-10-21: "free text should almost never be used in the assistant - it should be bringing up
    UI components"): on the desk an item comes up under a few words that name it, never a paragraph restating the card beside them -
    the walk's FYIs read "4 things people told you: Marcus Reed - FW: Quarterly newsletter; ..." over the card listing the same four.
    `picked`: the owner opened it themselves, rather than Next bringing it. A phone has no card and keeps the facts (fallback)."""
    what = (plural(len(item.get('items') or []), 'FYI') if item.get('kind') == 'fyis' else item.get('ref')
            or KIND_WORDS.get(str(item.get('kind') or ''), 'a goal' if str(item.get('kind') or '').startswith('goal') else 'the next one'))
    return f"Opened {what}." if picked else f"Next up: {what}."


def surface(store, key: str = None, llm=None, actor: str = 'owner', only: str = None, trace=None, cancel=None,
            include_surfaced: bool = False, exclude: str = None, selection=None, commit_guard=None,
            bound_dock: dict = None, leaving: str = None) -> dict:
    """The next thing out of the pipe (or the one named; or the next piece of MAIL), said in one
    breath and marked as shown. Nothing left: says so.

    `leaving` is the item the owner is walking away from - Next, and only Next. It is put down on the
    way out (move_on): read, and nothing more - a reply it was waiting on still waits, in Passed."""
    if selection is not None and key is not None:
        raise ValueError('a captured automatic selection cannot name a different item')
    put_down = (lambda: move_on(store, leaving, actor)) if leaving else (lambda: None)
    # ...and the row being left is not the next one: the pile is read BEFORE Next puts it down, and a task merely opened stays
    # walkable (processing_unread: actionable), so only this keeps Next from offering it straight back (the page sends it too)
    if leaving and selection is None: exclude = exclude or leaving
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
        opens = []
        left = [i for i in p['items'] if not i.get('settling')]
        # everything the rail holds For later: shown and put down for a while, AND put away to a day (Remind me) - the line
        # counted only the first, and said "1 thing" over a rail of two (the owner, 2026-10-01: "why does it say one thing
        # when there are 2?")
        waiting = [i for i in left if i['lane'] != 'working' and (i.get('surfaced') or i.get('back_at'))]
        # ...and what the walk never reached: Next walks DOWN the line (2026-10-22), so a row above where the owner started - a row
        # clicked further down, say - is still walkable when the bottom is reached. It is named here, and the next walk starts with it.
        skipped = [i for i in left if i.get('actionable', True) and not i.get('put_down') and not i.get('surfaced') and not i.get('deferred')
                   and not funnel._not_yet(i) and not any(k and k in (i['key'], *i.get('aliases', ())) for k in (leaving, exclude))]
        if key: say = "I can't find that one - it may be older than what I keep, or it went out under another subject."
        elif not only and skipped:
            n = len(skipped)
            when = ', '.join(i.get('ref') or _title_cut(' '.join(str(i.get('title') or 'one').split()), 40) for i in skipped[:4])
            say = (f"That's the bottom of the list. {plural(n, 'thing')} above where you started still wait{'s' if n == 1 else ''} - "
                   f"{when}{' and more' if n > 4 else ''}. The next walk starts with {'it' if n == 1 else 'them'}, or open {'it' if n == 1 else 'one'} now.")
            opens = [{'verb': 'open', 'key': i['key'], 'label': ' · '.join(x for x in (
                         f"Open {i.get('ref') or ''}".strip(), _title_cut(' '.join(str(i.get('title') or 'it').split()), 50)) if x)}
                     for i in skipped[:3 if DELIVERY.get() != PHONE else 10]]
        elif not only and waiting:
            # Shown in this walk and still on the rail: a task waiting to start, one an agent left, or a
            # draft/question, put down less than RETURN_MINUTES ago (180). Next will not repeat
            # them yet, so the line must not promise it does - it did ("Say next and I'll take them"), and
            # Next only said it again (the owner, 2026-09-18: "hitting next just confuses it").
            # ...in ONE order for the line and its buttons - what waits on the owner first, then the soonest back: the line named
            # TQ-0001 and TQ-0002 over buttons that opened TQ-0003..5 (the UX review, 2026-10-07)
            # the pile was read before Next put `leaving` down: that row is passed now
            if leaving: waiting = [i | {'put_down': True} if leaving in (i['key'], *i.get('aliases', ())) else i for i in waiting]
            # ...in the RAIL'S order, which already leads with what is on the owner: a sort of its own here named TQ-0001, TQ-0003,
            # TQ-0004 over a rail reading TQ-0001, TQ-0002, TQ-0003 - a to-do is not on_you() - and the owner could not match them
            # (the walk click-through, 2026-10-17)
            n = len(waiting)
            when = ', '.join(f"{i.get('ref') or _title_cut(' '.join(str(i.get('title') or 'one').split()), 40)}{' ' + _back_words(i['back_at']) if i.get('back_at') else ''}"
                             for i in waiting[:4])
            # "Nothing new right now" opened a line about nine things still waiting: say the walk is through, then where they are
            # ...and only what Remind me put there is "under For later": one Next walked past, or you looked at and left, is still
            # under Tasks (the owner, 2026-10-21: Next moves on, the task stays)
            aside = all(i.get('deferred') for i in waiting)
            # ...and in words that are true of how each got there: Next is not "putting aside", and Remind me is not passing (2026-10-17)
            # ...and what this walk passed is where the next one starts (the owner, 2026-10-21) - no hour it comes back in
            say = (f"That's everything for now. {plural(n, 'thing')} "
                   + (f"{'is' if n == 1 else 'are'} under {funnel.SECTION_WORDS['later']}" if aside else f"you already saw still wait{'s' if n == 1 else ''} on you")
                   + f" - {when}{' and more' if n > 4 else ''}. "
                   + (f"Open {'it' if n == 1 else 'one'} now if you want it sooner." if aside
                      else f"The next walk starts with {'it' if n == 1 else 'them'}, or open {'it' if n == 1 else 'one'} now."))
            # ...and the way to them NOW, by name: a Next under this line only said it again (2026-09-23, six days running).
            # What waits on the owner first - a close-out, an agent's question - then the rest.
            # ...each saying WHAT it is, not a bare number (the owner, 2026-09-30: "have to write what they are about a little")
            opens = [{'verb': 'open', 'key': i['key'], 'label': ' · '.join(x for x in (
                         f"Open {i.get('ref') or ''}".strip(), _title_cut(' '.join(str(i.get('title') or 'it').split()), 50)) if x)}
                     for i in waiting[:3 if DELIVERY.get() != PHONE else 10]]     # the phone's poll holds an Open for each named (F26)
        elif only and left:
            # the filtered set is done; what remains is the rest of the pipe - offer it rather than call the day over
            say = f"That's all of those. {plural(len(left), 'other thing')} still wait{'s' if len(left) == 1 else ''} - {funnel.summary(left).split(' - ', 1)[-1].split('.')[0]}. Say next and I'll take you through them."
        elif selection is not None and any(selection.pending.values()):
            pending = selection.pending
            parts = ([f"{pending['working']} in progress"] if pending['working'] else [])
            parts += ([f"{pending['settling']} still being read"] if pending['settling'] else [])
            parts += ([f"{pending['scheduled']} scheduled for a little later"] if pending['scheduled'] else [])
            say = "Nothing else needs you right now; " + ', '.join(parts) + '.'
        else: say = all_done(store)
        over = not key and not (only and left)
        # ...and THE WAY TO WALK AGAIN, on the row by the prompt box, before the Opens: the day card's own button, not a card and not a
        # sentence (the owner, 2026-10-22: "just have ... button on bottom on top of the prompt box"). The phone has its own Walk.
        if over and opens and DELIVERY.get() != PHONE: opens = [buttons.chip('walk'), *opens]
        with guarded():
            put_down()
            if not key: set_current(store, tid, None, actor)                  # the walk ran out: nothing is on the table
            # ...and the next walk is a new one: every open task this walk passed comes up again, from the top (2026-10-21)
            if over: funnel.new_walk(store)
            record(store, tid, 'assistant', say, {'kind': 'words', 'key': None, 'chips': opens} if opens else None)
        # `over`: the walk itself ran out (not a name that was not found, not one filter done) - a phone offers the hand-back
        return {'item': None, 'say': say, 'options': [], 'chips': opens or walk_chips(len(left)), 'left': len(p['items']),
                'exhausted': only if (only and left) else None, 'over': over}
    # A TASK AN AGENT IS WORKING is walked like any other task, in the rail's order, and goes on the table with its agent's pane
    # (the owner, 2026-10-21): Next used to say "is with the agent right now" and skip it, so a task jumped out of the walk - and
    # out of On you, to Agents working - every time its agent started, and back when it stopped.
    # FYIs have no action to take, so the normal walk brings four together. A row explicitly
    # clicked on the Timeline still opens by itself (`key` is set); only Next/Walk batches them.
    if not key and funnel.batchable(item):
        # a batch already assembled (funnel_selection._batch, which next_item returns on a processing store)
        # IS the batch: passed to fyi_batch as `first` it became its own member, "someone - 4 fyi" (2026-09-18)
        batch = item.get('items') if item.get('kind') == 'fyis' else funnel.fyi_batch(store, item)
        # NO MODEL CALL HERE. An fyi batch is the one card with nothing to decide - the entries are
        # already written, and a pass that only restates them in the assistant's voice bought a
        # paraphrase at the cost of the wait before the next four appear (the owner, 2026-09-16:
        # "all read, next on fyi still takes a while ... no need to run through ai model, just
        # present next ones"). The sentence below was already the fallback for a failed call; it is
        # the whole of it now, and each entry keeps its own gist (fyiRow.gistFor).
        gists, remember_llm = {}, False
        batch, say, card = _fyi_card(item, batch, gists)
        if routes(): say = brought_up(card)             # the card lists the four; the line only names them
        with guarded():
            put_down()
            if remember_llm:
                try: _remember_sid(store, tid, llm)
                except Exception as e: logger.warning(f'concierge: the fyi conversation did not save - {e}')
            # shown IS read: the state is `surfaced`, and it carries the entry's own summary
            for n, i in enumerate(batch, 1): funnel.settle(store, i['key'], 'surfaced', actor, note=None if i.get('sig') else gists.get(n), read=True)
            card['chips'] = chips_for(store, card)
            set_current(store, tid, card['key'], actor)
            funnel.mark_place(store, {'kind': 'fyis', 'key': card['key'], 'items': batch})   # where the walk is: Next goes on below it
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
    if not say: say = brought_up(item, picked=bool(key)) if routes() else fallback(item, True, store=store)
    chips = chips_for(store, item, wanted)
    with guarded():
        put_down()
        if remember_llm:
            try: _remember_sid(store, tid, llm)
            except Exception as e: logger.warning(f'concierge: the model conversation did not save - {e}')
        # in the chat = read, without exception (the owner, 2026-09-07: "hitting next or done should mark it
        # read and then move on"). A draft waiting on a yes used to be held back unread; walking past one now
        # marks it read and leaves it waiting in Passed - move_on(), which the Next road calls on the way out,
        # settles nothing.
        funnel.settle(store, item['key'], 'surfaced', actor, note=item.get('sig'), read=True)
        closed = bool(item.get('tid')) and (store.get_task(item['tid']) or {}).get('Status') in ('done', 'dropped')
        set_current(store, tid, item['key'], actor, closed=closed)           # on the table, written down (PW-162)
        funnel.mark_place(store, item)                                         # ...and where the walk is: Next goes on below it
        record_related(store, tid, item, 'assistant', say + (f"\nOPTIONS: {' | '.join(options)}" if options else ''),
                       card_for(item) | {'chips': chips})
    return {'item': item | {'chips': chips}, 'say': say, 'options': options, 'chips': chips, 'left': len(p['items']) - 1}


# THE CARD'S OWN QUESTION (the owner, 2026-09-25): one button, and the card asks the one thing that differs. Not
# ours asks how far - just this once, triage learns the sender, or a hard rule in Settings (Ignore this sender and
# Block them were two more buttons for that). Send to agent asks which agent - triage's pick is the one proposed.
# Picking another answer re-proposes through the same road (/api/concierge/propose), so nothing runs until confirmed.
ALTS = {'not_ours': buttons.choices('not_ours'), 'agent': buttons.choices('agent')}
# ...and on an ADVISOR IDEA there is no sender to learn: how far means this one, or this kind of idea (the owner, 2026-10-02:
# "feedback on assistant ideas ... does it teach it anything? we should have that") - the kind is a lesson the Advisor reads
IDEA_ALTS = buttons.choices('idea')
ALT_OF = {v: k for k, vs in ALTS.items() for v, _ in vs} | {v: 'not_ours' for v, _ in IDEA_ALTS}


def alts_for(store, item: dict | None, verb: str) -> list:
    """The answers the card offers to its own question - each one this item can actually carry."""
    group = ALT_OF.get(verb)
    if not group or not (item or {}).get('key'): return []
    pairs = IDEA_ALTS if group == 'not_ours' and item.get('kind') == 'idea' and item.get('idea') else ALTS[group]
    out = [{'verb': v, 'label': l, 'current': v == verb} for v, l in pairs if v == verb or not cannot(item, v, store)]
    return out if len(out) > 1 else []


def triage_agent(store, item: dict) -> str:
    """Send to agent goes where triage would send it: a coding agent when the task (or the message's verdict)
    is coding work, a non-coding one otherwise. The card shows the pick, and the other is one click away."""
    t = store.get_task(item['tid']) if item.get('tid') else None
    kind = str((t or {}).get('Kind') or '')
    if not kind and item.get('mid'):
        try: kind = str(operations.verdict_of_message(store, store.get_message(item['mid']) or {})[0] or '')
        except Exception: kind = ''
    return 'coding_agent' if kind == 'coding' and _coding(store) else 'regular_agent'


# What the owner may decide about the thing on the table, as PROPOSALS (PW-123): verb -> (operation kind,
# the button's label, whether confirming it settles the item on the table). Nothing here runs on the words;
# the confirmed proposal runs through server._run_operation, the same handler every entry point uses.
# The button's words are buttons.json's (the verb's own label); only the three that are no button of their own keep a phrase.
_OPS = {'coding_agent': ('task.create_from_message', True), 'regular_agent': ('task.create_from_message', True), 'mine': ('task.create_from_message', True),
        'not_ours': ('message.file', True), 'not_ours_sender': ('preference.exclude_sender', True), 'not_ours_kind': ('idea.act', True),
        'block_sender': ('preference.sender_rule', True), 'close': ('task.complete', True),
        # ...a send is NOT a settle (the owner, 2026-10-18: "sending and closing are two steps"): the item stays on the table with
        # its receipt, and Mark done or Next moves it - Approve on an agent's proposal runs that act alone, the same way
        'approve': ('review.approve', False),
        # the calendar's answers DRAFT for the owner's Send (calwrite.draft) - on the desk the words only light the row's button
        **{v: ('calendar.answer', False) for v in ('accept_invite', 'decline_invite', 'propose_time', 'find_time')},
        'answer_agent': ('agent.answer', True),
        # ...ending the session SETTLES the table, as AUTO below already says it does: it stayed False, so the walk held the same
        # item with the same button after it ran and the owner was stuck on it (2026-09-28: "it should just move to next")
        'stop_agent': ('agent.stop', True), 'rerun': ('report.rerun', True), 'continue': ('agent.continue', False),
        # the slipped card's answers (spec 2026-10-12): a chase is a draft for your yes; the other two settle the item
        'chase': ('task.chase', False), 'let_go': ('task.let_go', True), 'elsewhere': ('task.elsewhere', True),
        'test_connection': ('connection.test', False), 'split': ('task.split', False)}
PROPOSALS = {v: (k, buttons.label(v), s) for v, (k, s) in _OPS.items()} | {
    'not_ours_remember': ('preference.exclude_sender', f"{buttons.label('not_ours')} - and remember this kind", True),
    'remember': ('memory.remember', 'Remember it', False), 'setup': ('task.setup', 'Open the walk-through', False)}
# ...and ending the agent's session, which the task page's own button does on the click: it writes the
# session up and drafts the reply for your yes - nothing leaves (the owner, 2026-09-23: "it should be save
# end session as well same as in task", having been asked to confirm a card that read "wrap: false")
AUTO = ('close', 'stop_agent', 'continue',                              # settles what is on the table; nothing leaves, nothing is handed off
        # ...and NOT OURS, as "just this once" (the owner, 2026-10-21: no "are you sure"): filing one item teaches nothing and is
        # found again by search; how far it goes - from now on - is the chip offered under its receipt, never a question before it
        'not_ours',
        'test_connection',                                              # ...and a connection test, which only asks and changes nothing
        # ...and the ANSWER to an agent that asked: the words matched to its Answer pill go to the run at once, desktop and phone alike -
        # the phone used to skip the AI for this and sent "next" to the agent (the owner, 2026-10-08: "ai should match to pill action")
        'answer_agent')
# the verbs that start or resume an agent: a press of their button runs them, typed words only ever PROPOSE them
AGENT_STARTS = ('coding_agent', 'regular_agent', 'continue')
# the operations that take the item off the table, so the walk moves on after them (the page reads
# `settles` off the proposal it is holding; a chat comes back a turn later and has only the kind)
# (filing to the archive and putting the item down are no buttons any more, but still tools a CALL may name - and still settle)
SETTLING_KINDS = frozenset(kind for kind, _label, settles in PROPOSALS.values() if settles) | {'message.archive', 'item.settle'}
# SAID ONCE, IN WORDS (U3): a typed question with no AI got "set one up" twice in one reply, the second as a raw "#cli-agents".
# The desk gets the link to the AI page; a phone chat cannot open one, so it gets the words alone.
# ...and a phone has no buttons: its choices come under the line, as a poll on WhatsApp (F10)
NO_BRAIN = f"Connect an AI under {places.name('ai')} so I can take instructions; until then pick from the choices below."
# ...and where nothing is offered under it, nothing is promised: a fresh install with nothing waiting got "pick from the choices
# below" over no choices at all (the 2026-10-22 re-walk)
NO_BRAIN_BARE = f"Connect an AI under {places.name('ai')} so I can take instructions."
def connect_ai_chip() -> dict:
    """The chip under a no-AI line: it opens Connections at the AI cards (the page's `go` chip, AssistantView.runChip)."""
    return {'verb': 'go', 'label': 'Connect an AI', 'href': places.href('ai')}


def no_brain() -> str:
    return NO_BRAIN if DELIVERY.get() == PHONE else f"[Connect an AI under {places.name('ai')}]({places.href('ai_apps')}) so I can take instructions; until then use the buttons."


def handoff_task(store, text: str, kind: str = 'coding', actor: str = 'owner', title: str = None, dock_tid: int = None, repo: str = None,
                 profile: str = None) -> dict:
    """A hand-off with nothing on the table: the owner's words ARE the brief. The confirmed `task.create_from_text`
    lands here - the task is made and the agent started only then (PW-124)."""
    job = str(text or '').strip()
    if not job: raise ValueError('say what the agent should do')
    tid = dock_tid or general.dock_task(store, actor)[0]['TaskId']
    brief = _handoff_brief(store, tid, job)
    made = setup_task(store, brief, actor, title=title or _handoff_title(store, tid, job), kind=kind, agent_job=kind == 'general', repo=repo,
                      profile=profile)
    if kind == 'general':
        session = general.start_session(store, made['taskId'], actor=actor)
        def first_turn():
            _read_outputs(store, made, job, actor)
            session.send_prompt(brief)
        threading.Thread(target=first_turn, daemon=True).start()
    return made


def _read_outputs(store, made: dict, job: str, actor: str):
    """What closes a hand-off, read from the owner's words: "draft an email to each" becomes the slots on the card before
    the agent's first turn, which sees them in its checklist (spec 2026-10-05). Off the chat's thread - the brain may be a
    CLI that takes seconds to start. A brain that fails leaves the task as it was."""
    try:
        from . import slots, triage
        ask = triage.extract_ask({'body': job}, brain(store, fast=True))
        if ask.get('outputs'): slots.add(store, made['taskId'], ask['outputs'], actor)
    except Exception as e: logger.info(f"could not read what closes {made.get('ref')}: {e}")


def _resolve_named(store, phrase: str, item: dict | None) -> str | None:
    """The pile key the model's `on` HANDLE names - a TQ ref, an m-number, a pile key (_rail_block, handle_of) - or '?'.

    Code CHECKS the handle; it never guesses from words. A phrase ("the Payworth mail") was scored against the timeline and the
    pile by word overlap and a "yesterday = 3 days" table, and a wrong guess put the action on another item (the owner,
    2026-10-08: no code in front of the AI). '?' goes back to the model with its rail (_say)."""
    on = str(phrase or '').strip()
    ref = re.fullmatch(r'TQ-?0*(\d+)', on, re.I)
    if ref: return f"task:{int(ref.group(1))}" if store.get_task(int(ref.group(1))) else '?'
    mid = re.fullmatch(r'm-?(\d+)', on, re.I)
    if mid: return f"msg:{int(mid.group(1))}" if store.get_message(int(mid.group(1))) else '?'
    if ':' in on and (funnel.item_for_key(store, on) or any(on == e.get('key') for e in (item or {}).get('items') or [])): return on
    return '?'


def open_proposal(store, dock_tid: int) -> dict | None:
    """The proposal on the table - the newest CARD in this chat, when it is a proposal whose row is still `proposed`.

    ONLY while it is still the newest card (2026-09-29 audit): "Stop and save" proposed on one task, Next to the
    following one, a "yes" typed about THAT one - and the older proposal, still `proposed` further up, was the one the yes
    ran. A newer item on the table means the proposal was walked past; its own Confirm button still works where it is."""
    for c in reversed(general.chat_rows(store, dock_tid)):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('kind') in ('words', SETUP_QUESTIONS): continue          # a line's own words, not a card on the table
        if card.get('kind') != 'proposal': return None
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
    turn = receipt_turn(store, out, actor)              # a failure brings its way on; a success, nothing to add
    return {'say': turn['say'], 'options': [], 'chips': turn['chips'], 'decision': {'verb': 'confirm'},
            'executed': {'id': prop['id'], 'kind': prop['kind'], 'status': out.get('status')},
            'settled': out.get('status') == 'done' and prop['kind'] in SETTLING_KINDS}


def _where(it: dict) -> str:
    title = str(it.get('title') or '')
    who = it.get('who') if it.get('who') and not title.lower().startswith(str(it['who']).lower()) else ''   # "Assistant - Assistant idea"
    return f"{who + ' - ' if who else ''}{title}{' (' + it['ref'] + ')' if it.get('ref') else ''}".strip()


def _brief_from_item(store, item: dict) -> str:
    """What to tell an agent when the owner pressed a button instead of typing: the item itself - what it
    is, who it is from, and everything already known about it (the same facts the assistant reads)."""
    return f"Take this on and report back what you find: {_where(item) or 'the item below'}.\n\n{facts(store, item, whole=True)}".strip()


def propose_for(store, dock_tid: int, decision: dict, item: dict | None, text: str, actor: str = 'owner',
                elsewhere: bool = False, table: dict | None = None) -> dict:
    """The owner's decision as a proposal row (operations.propose): the exact target and parameters, a label
    for its button, and the line that says what WILL happen. A decision that changes the proposal already on the
    table revises it (a new confirmation version) instead of stacking a second one (PW-123)."""
    verb = handoff_verb(store, canon_verb(decision['verb']))      # a stale page still sends `coder`, an old card `later` or `archive`
    if verb not in PROPOSALS: raise ValueError('that button is gone - use the ones on the card')
    kind, label, settles = PROPOSALS[verb]
    d_text = (decision.get('text') or '').strip()
    it = item or {}
    target, params, note, clear, choices = None, {}, '', False, []
    # AN ADVISOR IDEA IS ITS OWN TARGET (C5, 2026-09-27): the same words, on the idea. Make a task reads the task
    # it already has, Not ours puts the IDEA down - it used to file the mail the idea was about - and each writes
    # the idea's own status
    if it.get('kind') == 'idea' and it.get('idea') and verb in IDEA_ACT:
        kind, target, params, clear = 'idea.act', it['idea'], {'verb': IDEA_ACT[verb]}, True
        label = op_label(kind, params)
    elif verb in ('coding_agent', 'regular_agent', 'mine'):
        want = {'coding_agent': 'coding', 'regular_agent': 'general', 'mine': 'task'}[verb]
        if it.get('mid'): target, params = it['mid'], {'kind': want, 'instructions': d_text or None}
        elif verb == 'mine': raise ValueError('nothing is on the table to put on your list')
        else:
            # A hand-off asked for by BUTTON carries no sentence, so the brief is the item itself. Without
            # this the chip proposed a task with no text at all and operations refused it outright
            # ('task.create_from_text needs text') - an offered word that did nothing.
            job = (d_text or text or '').strip() or _brief_from_item(store, it)
            title = _handoff_title(store, dock_tid, job) if (d_text or text or '').strip() else (it.get('title') or 'Look into this')
            kind, target, params = 'task.create_from_text', 0, {'kind': want, 'text': job, 'title': title}
            # a coding job names its checkout on the card, and the one confirmed is the one it opens in
            if want == 'coding':
                from . import terminal as term
                # CLEAR is a repository somebody NAMED - the model off the map (coding_agent[ledger]) or the owner's own
                # words. A best word-match is only a guess: the issue-920 ask scored 0.10 for one checkout against
                # 0.0 for the rest and was in neither of them, so a guess goes on the card and waits for a yes.
                # THE MODEL NAMES IT - it is shown every repository (_system) - and code checks the name is one of them. The owner's
                # sentence was read by a regex and word-overlap scored a guess onto the card (the owner, 2026-10-08: "the ai should see
                # the repo's to choose from"); not named means the card's picker, nothing preselected
                named = term.known_repo(store, decision.get('as') or '')
                params['repo'] = named or None
                clear = bool(named)
                # not clear: the card offers every checkout to pick from, and Start waits for one - "you pick it when
                # it starts" let the start quietly guess instead (the owner, 2026-09-24: "it should be dropdown to
                # choose repo if it's not clear but it just started it in taskuary")
                choices = term.known_repos(store)
                label = buttons.label('coding_agent')
            else:
                # ...and a general one names its WORKER - the profile the model picked off the roster, validated
                # the way triage's pick is (agents.routed_role). Typed in the chat it used to get the plain default
                # agent even with a researcher on the roster for exactly this (the owner, 2026-09-24)
                from . import agents as hub_agents
                role = hub_agents.routed_role(store, 'general', decision.get('as') or '')
                params['profile'] = role or None
                clear = bool(role) or not hub_agents.roster(store).strip()
                label = buttons.label('regular_agent')         # the worker picked is said in the line, never in the button's name
                if role: note = f' The {role} takes it.'
    elif verb == 'not_ours': target, params = it.get('mid'), {'learn': False}
    elif verb in ('not_ours_remember', 'not_ours_sender'): target, params = it.get('mid'), {'scope': 'subject' if verb == 'not_ours_remember' else 'sender'}
    elif verb == 'block_sender': target = it.get('mid')      # the rule is keyed on the sender of THIS message
    elif verb == 'close': target = it.get('tid')        # an agent parked on it is stopped by the same close (close_task)
    elif verb in CAL_ACT:
        if not it.get('mid'): raise ValueError('nothing is on the table')
        target, params = it['mid'], {'act': CAL_ACT[verb]}
    elif verb in ('chase', 'let_go', 'elsewhere'):
        if not it.get('key'): raise ValueError('nothing is on the table')
        target, params = it.get('tid') or it.get('idea') or it.get('mid') or 0, {'key': it['key'], 'text': d_text or text or None}
    elif verb == 'approve':
        target = it.get('rid')
        label = closeout_label(it) or label          # "Send the reply" is not what a merge card's yes does
    elif verb == 'answer_agent':
        # the owner's own words when the model passed none - never a "yes" nobody said (B12, 2026-10-11)
        said = d_text or (text or '').strip()
        if not said: raise ValueError(f"What should I tell {it.get('agent') or 'the agent'}? Say it and it goes straight to the run that is waiting.")
        target, params = it.get('tid'), {'text': said}
    elif verb == 'stop_agent':
        end = _agent_task(store, item, text)
        if not end: raise ValueError('no agent is running right now - nothing to stop')
        # THE TASK PAGE'S "Stop and save", whatever the words: the session is written up whenever
        # there is a transcript to write it from (a wrap writes the report FROM it), and simply ended when
        # there is none. It used to write up only on the word "wrap" - so the button stopped an agent and
        # threw its work away, where the page's button of the same meaning kept it.
        from . import terminal as term
        try: wrap = bool((term.transcript_for(store, end) or ('',))[0].strip())
        except Exception: wrap = False
        target, params = end, {'wrap': wrap}
        if not wrap: note = ' There is nothing written down to report from yet - this stops the work, and the task stays open.'
    elif verb == 'continue': target, params = it.get('tid'), {'note': d_text or ''}
    elif verb == 'rerun': target = it.get('source_id')
    elif verb == 'test_connection':
        k = str(it.get('key') or '')
        target = int(k.split(':', 1)[1]) if k.startswith('conn:') and k.split(':', 1)[1].isdigit() else None
    elif verb == 'remember':
        if not d_text: raise ValueError('remember what? Say the fact and I will keep it')
        target, params = 0, {'note': d_text}
    elif verb == 'split': target, params = it.get('tid'), {'text': text, 'key': it.get('key')}
    elif verb == 'setup': target, params = 0, {'text': d_text or text, 'title': decision.get('title') or None}   # the set-up sort's (_walkthrough)
    if target is None: raise ValueError(f"there is nothing to {SAYS_VERB.get(verb, verb)} on this one")
    params = {k: v for k, v in params.items() if v is not None}
    # A NEW TASK FROM THE OWNER'S OWN WORDS is not about the item on the table (the owner, 2026-10-01: "why did it say starting coding
    # agent on 912? 912 was another one about GL's"): typed while TQ-0912 was open, "stop sending me the vendor-create mails" became
    # TQ-0930 - and its card, both receipts and the settle all named TQ-0912. Only a hand-off pressed with no words carries the item
    # as its brief, and stays the item's.
    if kind == 'task.create_from_text' and (d_text or text or '').strip(): it, settles = {}, False
    prev = open_proposal(store, dock_tid)
    same = _same_proposal(prev, kind, target, params)
    # THE SAME ASK AGAIN is not a change: a "yes" read as the decision once more re-proposed it as "Changed to: <the same
    # thing>", a new version that changed nothing (2026-09-22 audit). It stays the one proposal and says it still waits.
    unchanged = same and {k: v for k, v in (prev.get('params') or {}).items() if k != 'processing_context'} == params
    if unchanged: op = prev
    elif same: op = operations.revise(store, prev['id'], params, actor)
    else:
        if prev: operations.cancel(store, prev['id'], actor)
        op = operations.propose(store, kind, target, params, actor)
    where = _where(it) if it else (params.get('title') or _cut(params.get('text') or params.get('note') or '', 120))
    # an item goes somewhere ("TQ-0007 → coding agent"); words with no item ARE the thing - the arrow only
    # repeated the label ("Remember it: Gail approves POs → remember it")
    summary = f"{where} → {label[0].lower() + label[1:]}" if it else where
    lead = (f"That is {where}, not the one on the table - so I am proposing it there; {(table or {}).get('ref') or 'the one on the table'} is untouched. "
            if elsewhere and table else '')                      # nothing on the table: there is no other one to leave untouched
    # the card's line is a title and may be cut; the sentence is all a phone gets, so it carries the whole ask -
    # "...then tell me what setting or…" was the phone's only account of what the agent would do (2026-09-24 audit)
    said = summary if it else _title_cut(params.get('text') or params.get('note') or where, 400).rstrip('.')
    head = (f"Still waiting for your yes: {label} - {said}" if unchanged else f"Changed to: {label} - {said}" if same
            else f"{label}: {said}")
    say_ = lead + f"{head}.{note} {WAITS}"
    # OVER THE CARD, only what the card does not say: its heading IS "<label>" and its line IS the summary, so the
    # sentence above it said them first (the owner, 2026-09-24: "the assistant saying words above the box and then
    # the box saying the same thing"). `say` keeps the whole sentence for a doorway with no card - a phone chat.
    say_card = (lead + note.strip() + ' ' + WAITS).strip()
    return {**op, 'verb': verb, 'label': label, 'summary': summary, 'settles': bool(settles and not elsewhere),
            'key': it.get('key'), 'ref': it.get('ref'), 'tid': it.get('tid'), 'say': say_, 'say_card': say_card, 'note': note.strip(),
            # a hand-off with no doubt left in it - one worker, one checkout - has nothing to pick; it still waits for the press
            'clear': clear, 'repo_choices': choices, 'alts': alts_for(store, it, verb) if not elsewhere else []}


def propose_direct(store, verb: str, key: str, text: str = '', actor: str = 'owner', table: bool = False, exact: bool = False) -> dict:
    """A card's own button on ONE entry (PW-151): the same proposal the words would make, without the interpreter -
    the target is explicit. From a card it never settles what is on the table and the entry's siblings are not
    touched; from the chips under the composer (`table`) the entry IS the table, so a plain verb runs at once and
    settles it, exactly as the typed word would."""
    verb = handoff_verb(store, canon_verb(verb))
    if verb not in PROPOSALS: raise ValueError(f'{verb} is not something a card proposes')
    item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
    if not item: raise ValueError('that one is not in the pipe any more')
    # kind routes the task (2026-08-30): the Send to agent BUTTON goes where triage would send it (2026-09-25); a
    # coding agent asked for by name still goes to the regular agent when the task is general work
    if verb == 'regular_agent' and not text and not exact: verb = triage_agent(store, item)     # exact: the card's own answer
    elif verb == 'coding_agent' and item.get('tid') and (store.get_task(item['tid']) or {}).get('Kind') == 'general': verb = 'regular_agent'
    tid = general.dock_task(store, actor)[0]['TaskId']
    why = cannot(item, verb, store)
    if why: raise ValueError(why)
    record_related(store, tid, item, 'user', f"{PROPOSALS[verb][1]}: {item.get('title') or item.get('ref') or key}")
    try: prop = propose_for(store, tid, {'verb': verb, 'text': text or ''}, item, text or '', actor, table=item if table else None)
    except ValueError as e:
        # THE PRESS IS ANSWERED: its line was already in the conversation, and a refusal went to an error banner only - the
        # chat showed "Stop and save" with nothing under it until the owner typed Next (2026-09-25). The reason
        # is said there, with what this item CAN do instead.
        way = [c for c in chips_for(store, item) if c['verb'] != verb]
        record_related(store, tid, item, 'assistant', f"{str(e)[:1].upper()}{str(e)[1:]}.", {'kind': 'words', 'key': None, 'chips': way})
        return {'id': None, 'failed': True, 'say': f"{str(e)[:1].upper()}{str(e)[1:]}.", 'chips': way, 'key': key}
    prop['settles'] = bool(table and PROPOSALS[verb][2])
    if table and verb in AUTO: prop.update(auto=True, say_card=prop.get('note') or '', say=f"{prop['label']} - {_where(item)}." + (f" {prop['note']}" if prop.get('note') else ''))
    record_related(store, tid, item, 'assistant', prop['say'], {'kind': 'proposal', 'key': prop.get('key'), 'title': prop['label'], 'op': prop['id'],
                                                               'tid': prop.get('tid'), 'ref': prop.get('ref'), 'lane': item.get('lane')})
    return prop


# ── setting things up from the chat (PW-194..197): sorted and gathered by AI, confirmed, created through the tabs' roads ──
# a token typed into the chat is not kept (PW-196): what looks like one is replaced before any row is written
SECRET_WORDS = re.compile(r'(secret|token|password|passwd|api[_ -]?key|refresh|private[_ -]?key|client[_ -]?secret|bearer)', re.I)
SETUP_QUESTIONS = 'setup_questions'
SETUP_SORT_SYSTEM = ('You sort one set-up request from the owner of a small company\'s assistant. Answer JSON only: '
                     '{"kind": "report" | "playbook" | "connection" | "role" | "investigate", "provider": "<connector type or null>", '
                     '"role": "<a key from roles, or null>", "why": "<one sentence>", '
                     '"title": "<what to call it on a task list - a few words naming the job, e.g. Add Erin Blake to payroll>"}. '
                     # (the owner, 2026-10-08: "the assistant should be able to walk a user through setting up new role and work")
                     'A ROLE is the owner naming their JOB and asking for Taskuary to be set up for it ("I am an AP rep, set me '
                     'up", "I do accounts payable") - answer role, with its key from roles, when the job is one of them; a job '
                     'that is not in roles is investigate. '
                     'A REPORT reads connected systems on a schedule and files what it found (a check, a digest, a scheduled agent job). '
                     # it had no word for one, so "can I build a playbook for it?" sorted to investigate and became an agent's job (the
                     # owner, 2026-10-22: "this is not playbook ui?")
                     'A PLAYBOOK says how one kind of recurring REQUEST is handled from now on - when someone asks for this, gather that, '
                     'prepare it for the owner\'s review; triage matches new mail to it. A request to build, make or set up a playbook, '
                     'or to have a recurring kind of ask handled the same way every time, is playbook. '
                     'A CONNECTION adds or configures a system Taskuary talks to (mail, chat, a database, a books system, an AI provider) - '
                     'name its type from connector_types when you can. INVESTIGATE is a set-up that needs real digging first - a portal to '
                     'read, systems to choose between, several moving parts - where a walk-through with an agent is the honest next step. '
                     'A simple configuration is never investigate. '
                     # The assistant HAS a browser, and nothing here said so: asked for a daily report off a page behind a
                     # sign-in, this sorted to "report", and the composer - which only knows connectors - replied "connect a
                     # browser/web automation source", naming a connector that does not exist and cannot be added (the owner,
                     # 2026-09-15). Work done ON A WEBSITE is the walk-through's, and the walk is where the browser opens.
                     'WORK DONE ON A WEBSITE IS ALWAYS INVESTIGATE: signing into a site or portal, reading or filling a page, '
                     'anything whose only road is a browser. Taskuary drives its own browser in a walk-through, beside the '
                     'owner, and keeps the sign-in they type there; there is no browser connector to add and connector_types '
                     'has none. Never answer "connection" for a website, and never a report that would need one. '
                     # "a morning report of our GitHub stars and Reddit mentions" became "add a GitHub connection" or a
                     # walk-through: nothing here said a report can be an AI agent's own job (2026-09-24 audit)
                     'A REPORT CAN BE AN AI AGENT DOING THE WORK: anything an agent can look up for itself - a public API, a '
                     'repository\'s stars and traffic, a web or forum search, a summary of news - is a report the agent runs on '
                     'its schedule, with no connection to add. When the owner asks for a report, answer "report" unless the only '
                     'road is a site they must sign into; "connection" is for when they ask to connect a system.')


def redact(text: str) -> str:
    """PW-196, now sharing the app's one vocabulary for what a credential looks like (redact.py).

    It used to carry its own pattern ending in a catch-all for any long hex string - and a git SHA
    is 40 of those, so "revert da8dae00..." was stored as "revert [redacted]", unreadable to the
    owner and useless to an agent reading the turn back."""
    return _scrub(text)


def _compose_llm(store, trace=None, cancel=None):
    # the Assistant's own brain builds what the Assistant proposes - it was the first API connector whatever the
    # owner chose (2026-09-24); no `keep`, so a composer's JSON never lands in the chat's live conversation
    try: return brain(store, trace=trace, cancel=cancel, fast=True)
    except Exception as e:
        logger.warning(f'concierge: no composer brain - {e}'); return None


def catalogue_card(name: str) -> dict | None:
    """The connector catalogue's card a name means - its type, its title or one of its match words, as the catalogue spells them."""
    from . import connectorcatalog
    n = ' '.join(str(name or '').lower().replace('_', ' ').split())
    if not n: return None
    cs = connectorcatalog.cards()
    return (next((c for c in cs if c['type'] == n.replace(' ', '_')), None) or next((c for c in cs if c['title'].lower() == n), None)
            or next((c for c in cs if n in [m.lower() for m in c.get('match') or []]), None))


def catalogue_near(name: str, n: int = 3) -> list:
    """The catalogue's cards closest to a name it does not have - by spelling, over titles and types."""
    import difflib
    from . import connectorcatalog
    cs = [c for c in connectorcatalog.cards() if not c.get('planned')]
    keys = {c['title'].lower(): c for c in cs} | {c['type']: c for c in cs}
    hits = difflib.get_close_matches(str(name or '').lower().strip(), list(keys), n=n * 2, cutoff=0.5)
    return list({id(keys[k]): keys[k] for k in hits}.values())[:n]


def sort_setup(store, text: str, llm) -> dict:
    """What kind of set-up the words ask for, by the model: a report, a connection (and to what), or digging."""
    from . import compose
    from . import connectorcatalog
    types = sorted(set(store_mod.DEFAULT_ROLES) | {c['type'] for c in connectorcatalog.cards() if not c.get('planned')})
    from . import roles
    have = {k: r['title'] for k, r in roles.ROLES.items()}
    try: out = compose._json(llm(SETUP_SORT_SYSTEM, json.dumps({'request': text, 'connector_types': types, 'roles': have}), max_tokens=300)) or {}
    except Exception as e:
        logger.warning(f'concierge: the set-up sort failed - {e}'); out = {}
    kind = str(out.get('kind') or 'report').lower(); prov = str(out.get('provider') or '').lower().strip()
    role = str(out.get('role') or '').lower().strip()
    # a role nobody ships is still a real ask - it is digging, never a report built from nothing
    if kind == 'role' and role not in have: kind = 'investigate'
    return {'kind': kind if kind in ('report', 'playbook', 'connection', 'role', 'investigate') else 'report', 'provider': prov if prov in types else None,
            'role': role if kind == 'role' else None, 'why': str(out.get('why') or '')[:300], 'title': _title_cut(out.get('title') or '')}


def _pending_setup(store, tid: int) -> dict | None:
    """The set-up questions asked last turn, if the last assistant line asked them."""
    rows = [c for c in general.chat_rows(store, tid) if c.get('ActorType') == general.ASSISTANT_TYPE]
    card = _card_of(rows[-1]) if rows else None
    return card if card and card.get('kind') == SETUP_QUESTIONS else None


def _same_proposal(prev: dict | None, kind: str, target, params: dict) -> bool:
    """Is this ask a revision of the proposal still waiting, or a new one? Same kind on the same target - but a NEW thing has
    no target to share: every to-do, report and setting proposes on 0, so "make a task to renew Spendly" became version 2 of
    the to-do card still waiting above it, said "Changed to:" over a different ask (2026-10-06). On 0 it is the same proposal
    only when it is the same words, or names the same thing (the setting, the connection type, the report's title)."""
    if not (prev and prev['kind'] == kind and int(prev['target']) == int(target or 0)): return False
    if int(target or 0): return True
    ident = lambda p: tuple(str((p or {}).get(k) or '').strip().lower() for k in ('setting', 'type', 'title', 'name'))
    bare = {k: v for k, v in (prev.get('params') or {}).items() if k != 'processing_context'}
    return bare == params or (any(ident(bare)) and ident(bare) == ident(params))


def _propose_raw(store, dock_tid: int, kind: str, target: int, params: dict, label: str, summary: str, tail: str, actor: str,
                 item: dict | None = None) -> dict:
    """A proposal that is not about the item on the table: the same revise-or-replace rule as propose_for, recorded as a card."""
    prev = open_proposal(store, dock_tid)
    same = _same_proposal(prev, kind, target, params)
    # the same words again are the card still waiting, as on propose_for - not a version 2 said "Changed to:"
    unchanged = same and {k: v for k, v in (prev.get('params') or {}).items() if k != 'processing_context'} == params
    if unchanged: op = prev
    elif same: op = operations.revise(store, prev['id'], params, actor)
    else:
        if prev: operations.cancel(store, prev['id'], actor)
        op = operations.propose(store, kind, target, params, actor)
    head = (f"Still waiting for your yes: {label} - {summary}" if unchanged else f"Changed to: {label} - {summary}" if same
            else f"{label}: {summary}")
    text = head + ('.' if tail.startswith('\n') else '. ') + tail
    record_related(store, dock_tid, item, 'assistant', text, {'kind': 'proposal', 'key': None, 'title': label, 'op': op['id'], 'tid': None, 'ref': None})
    # OVER THE CARD only what the card does not say - its heading is the label and its line the summary (the 2026-09-24 rule
    # propose_for keeps; this road never did, so "Clear 21 from the pipe: 21 items - ..." was said twice, the owner, 2026-10-12)
    return {**op, 'verb': 'setup', 'label': label, 'summary': summary, 'settles': False, 'key': None, 'ref': None, 'tid': None, 'say': text,
            'say_card': tail.strip()}


def _routing_words(cfg: dict) -> str:
    """Where this report's runs go, in the words the card uses - the AI decides a line only where
    the owner wrote a sentence for it to judge (reports.route_of)."""
    from .reports import route_words
    return route_words(cfg)


def _schedule_words(cfg: dict) -> str:
    from . import reports
    return reports.schedule_words(cfg)


# The card reads the way the report builder does - its prompt first, then the settings under it. It used to be
# "source: agent; inputs: ...; summary instructions: ..." - a config dump the owner called "some technical summary",
# on the desktop and in WhatsApp alike (2026-09-24).
FACT_WORDS = {'prompt': 'Prompt', 'reads': 'Reads', 'runs': 'Runs', 'reaches_you': 'Reaches you', 'goes_to': 'Goes to'}


def _reads_words(cfg: dict) -> str:
    srcs = [x for x in (cfg.get('sources') or [cfg]) if isinstance(x, dict)]
    def one(x):
        t = str(x.get('type') or '?')
        if t == 'agent': return f"an AI agent doing the work itself{' (/' + str(x['skill']).lstrip('/') + ')' if x.get('skill') else ''}"
        what = str(x.get('query') or x.get('object') or x.get('url') or x.get('path') or '').strip()
        return f"{t}{' - ' + _cut(what, 160) if what else ''}"
    return '; '.join(one(x) for x in srcs) or str(cfg.get('type') or '')


def report_facts(cfg: dict) -> dict:
    """What the confirmation box says about a report (PW-195), in the builder's order: its name, the prompt, then
    what it reads, when it runs, how it reaches the owner and where else it goes."""
    from .appfacts import _goes
    agent = cfg.get('type') == 'agent' or any(isinstance(x, dict) and x.get('type') == 'agent' for x in cfg.get('sources') or [])
    job = str(cfg.get('prompt') or next((x.get('prompt') for x in cfg.get('sources') or [] if isinstance(x, dict) and x.get('prompt')), '') or '').strip()
    summ = str(cfg.get('ai_prompt') or '').strip()
    prompt = '\n\n'.join(x for x in ((job if agent else ''), (f'Then: {summ}' if agent and job and summ else summ)) if x)
    return {'title': str(cfg.get('title') or ''), 'prompt': prompt or 'none - the raw result is filed as it comes',
            'reads': _reads_words(cfg), 'runs': _schedule_words(cfg) + (f" ({cfg['tz']})" if cfg.get('tz') else ''),
            'reaches_you': _routing_words(cfg), 'goes_to': _goes(cfg)}


def report_lines(facts: dict) -> str:
    """The card, as a chat without cards holds it: one labelled line each, the prompt first."""
    return '\n'.join(f"{w}: {facts[k]}" for k, w in FACT_WORDS.items() if facts.get(k))


def _walkthrough(store, tid: int, ask: str, item: dict | None, actor: str, lead: str, title: str = '') -> dict:
    """The set-up needs digging: a walk-through with the regular agent, proposed with the reason (PW-197)."""
    prop = propose_for(store, tid, {'verb': 'setup', 'text': ask, 'title': title}, item, ask, actor)
    prop['say'] = f"{lead} {prop['say']}"
    record_related(store, tid, item, 'assistant', prop['say'], {'kind': 'proposal', 'key': None, 'title': prop['label'], 'op': prop['id'], 'tid': None, 'ref': None})
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def setup_turn(store, tid: int, text: str, ask: str, item: dict | None, actor: str = 'owner', llm=None,
               trace=None, cancel=None, sorted_as: str = None) -> dict:
    """A set-up asked for in the chat (PW-194): sorted by the model, gathered by the composer - its questions come back as
    questions and the next words answer them - and put in front of the owner as a proposal that the shared Reports /
    Connections road creates on the click. Secrets never pass through here (PW-196); digging is a walk-through (PW-197)."""
    rec = lambda body, card=None: record_related(store, tid, item, 'assistant', body, card)
    cllm = llm or _compose_llm(store, trace, cancel)
    if not cllm:
        say_ = (f"I cannot set that up from the chat yet - {places.name('workflows')} and {places.name('connections')} have the forms "
                "for it. Nothing has changed.")
        rec(say_); return {'say': say_, 'options': [], 'decision': None}
    pending, answers = _pending_setup(store, tid), None
    if pending:
        ask, answers = pending['ask'], {'questions': pending.get('questions') or [], 'reply': text}
        # a role's questions were asked about THAT role: the answer is to them, not a new request to sort
        if pending.get('role') and not routes(): return _propose_role(store, tid, ask, pending['role'], item, actor, cllm, answers)
        sort = sort_setup(store, f"{ask}. The owner answered: {text}", cllm)
    elif sorted_as: sort = {'kind': sorted_as, 'provider': None, 'why': ''}      # the chat model already named it
    else: sort = sort_setup(store, ask, cllm)
    # ON THE DESK A SET-UP IS ITS OWN PAGE (routes): a report is New's report box, a connection its card, a role its Set up on Profiles, and
    # digging an agent's job in New - each with its own button to press; nothing is composed into a card to confirm here
    if routes():
        if sort['kind'] in ('report', 'playbook'): return _new(store, tid, item, sort['kind'], ask)
        if sort['kind'] == 'role':
            return _page(store, tid, item, '#profiles', "Opened Profiles - press Set up beside the job you do.")
        if sort['kind'] == 'investigate': return _new(store, tid, item, 'general', ask)
        if sort.get('provider'):
            return call_turn(store, tid, {'kind': 'connection.create', 'params': {'type': sort['provider']}}, item, text, actor)
        if sort['kind'] == 'connection':
            prov = sort['provider']
            name = (store.get_connector_by_type(prov) or {}).get('Name') or prov
            return _page(store, tid, item, f'#connector={prov}', f"Opened {name}'s card under Connections - fill it in and test it there. "
                                                                 'A key or password goes on the card, never in this chat.')
    # ...a phone has no New: the playbook is said where it is made, and nothing is started from a chat line
    if sort['kind'] == 'playbook':
        say_ = f"A playbook is made under {places.name('playbooks')} - New playbook there builds it from your words or a past email. Nothing has changed."
        rec(say_); return {'say': say_, 'options': [], 'decision': None}
    if sort['kind'] == 'investigate':
        return _walkthrough(store, tid, ask, item, actor, f"This needs digging before it can be configured{' - ' + sort['why'] if sort.get('why') else ''}.",
                            title=sort.get('title') or '')
    if sort['kind'] == 'connection':
        return _propose_connection(store, tid, ask, sort.get('provider'), item, actor)
    if sort['kind'] == 'role':
        return _propose_role(store, tid, ask, sort['role'], item, actor, cllm)
    from . import compose
    out = compose.compose(store, ask, cllm, answers=answers)
    if out.get('questions'):
        qs = out['questions']
        # the composer's OWN list, one question a line - run together as "(1) ... (2) ..." they read as one
        # paragraph (the owner, 2026-09-24: "numbered list"). "1." and never "1 ·": the dot is how a chat's
        # MENU is numbered (remote_assistant._OFFERED), and an answer "2" must not pick question two
        say_ = 'Before I put it together:\n' + '\n'.join(f"{n}. {q}" for n, q in enumerate(qs, 1)) + '\n\nNothing is set up yet.'
        rec(say_, {'kind': SETUP_QUESTIONS, 'ask': ask, 'questions': qs})
        return {'say': say_, 'options': [], 'decision': None}
    if out.get('error') or not out.get('config'):                        # a configuration the composer itself could not stand behind
        return _walkthrough(store, tid, ask, item, actor, f"I could not configure that from here ({out.get('error') or 'no configuration came back'}).")
    cfg, facts = out['config'], report_facts(out['config'])
    params = {'config': cfg, **facts}
    looked = ', '.join(str(x) for x in (out.get('looked_at') or [])[:4])
    # over the card only what the card does not say: why it is built this way, and that nothing is saved yet
    why = ' '.join(x for x in (str(out.get('explain') or '').strip(), f'I read {looked} to build it.' if looked else '') if x)
    after = 'Nothing is saved until you say yes. Preview a dry run first if you like.'
    prop = _propose_raw(store, tid, 'report.create', 0, params, 'Create the report', facts['title'],
                        '\n' + report_lines(facts) + '\n\n' + ' '.join(x for x in (why, after) if x), actor, item)
    prop['say_card'] = ' '.join(x for x in (why, after) if x)
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


# what an authority level lets the connection do, in words. scopes.actions_at is every action in the APP at
# that level - a hundred report types printed on a Todoist card as its "permissions" (2026-09-23)
SCOPE_SAYS = {'read': 'it can read, never change or send', 'write': 'it can read and make changes',
              'admin': 'it can read, make changes and administer the account'}


ROLE_READ_SYSTEM = ('You read the owner\'s answer to set-up questions. Answer JSON only: {"portal": "<the web address they gave, '
                    'or empty>", "route_mail": true | false}. route_mail is true only when they clearly want their own non-coding '
                    'mail to go to the new worker from now on; trying it out, testing, not yet, or no answer is false.')


def _propose_role(store, tid: int, ask: str, role: str, item: dict | None, actor: str, llm, answers: dict = None) -> dict:
    """A role (roles.py), walked: the questions it needs, asked once as a numbered list; the answer read for intent by the
    model (never by matching words); then the whole set-up on ONE card - worker, playbooks, workflow, where the mail goes."""
    from . import compose, roles
    r = roles.ROLES[role]
    rec = lambda body, card=None: record_related(store, tid, item, 'assistant', body, card)
    if answers is None:
        qs = ((['What is the address of your bill-approval portal? Say skip to add it later.'] if r.get('workflow') else [])
              + [f"Should your own non-coding mail go to the {r['profile'].upper()} worker from now on, or are you only trying it out?"])
        say_ = f"To set Taskuary up for {r['title'].lower()}:\n" + '\n'.join(f"{n}. {q}" for n, q in enumerate(qs, 1)) + '\n\nNothing is set up yet.'
        rec(say_, {'kind': SETUP_QUESTIONS, 'ask': ask, 'questions': qs, 'role': role})
        return {'say': say_, 'options': [], 'decision': None}
    try: got = compose._json(llm(ROLE_READ_SYSTEM, json.dumps(answers), max_tokens=200)) or {}
    except Exception as e:
        logger.warning(f'concierge: reading the role answers failed - {e}'); got = {}
    return role_card(store, tid, role, got.get('portal'), got.get('route_mail') is True, item, actor)


def role_card(store, tid: int, role: str, portal, route: bool, item: dict | None, actor: str) -> dict:
    """The Set it up card for a role - what it lays out, line by line, before the owner's yes."""
    from . import playbooks, roles
    r = roles.ROLES[role]
    portal = str(portal or '').strip()
    if portal and '://' not in portal: portal = 'https://' + portal
    params = {'role': role, 'portal': portal, 'route_mail': bool(route)}
    wf = r.get('workflow') or {}
    lines = [f"Worker: {r['profile'].upper()}.md",
             'Playbooks: ' + '; '.join(playbooks.parse(roles.playbook_text(b))['title'] for b in r['playbooks']),
             'Your mail: ' + ('non-coding mail goes to the worker' if route else 'goes where it goes today'),
             *([f"Ledger: {(store.get_connector_by_type(r['ledger']) or {}).get('Name') or r['ledger']} set to read if nobody chose its "
                'authority, so nothing reaches it without your click'] if r.get('ledger') else []),
             *([f"Workflow: \"{wf['title']}\", daily at {wf.get('daily_at', '')}, created switched off" + (f" - {portal}" if portal else '')] if wf else [])]
    tail = '\n' + '\n'.join(lines) + '\n\n' + WAITS
    prop = _propose_raw(store, tid, 'role.apply', 0, params, 'Set it up', r['title'], tail, actor, item)
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def _propose_connection(store, tid: int, ask: str, provider: str | None, item: dict | None, actor: str) -> dict:
    """A connection (PW-196): provider and non-secret configuration, the authority it will hold and what that unlocks;
    the secret is never asked for here - the card takes it, securely - and it stays off until the owner turns it on."""
    from . import scopes
    rec = lambda body, card=None: record_related(store, tid, item, 'assistant', body, card)
    if not provider:
        types = sorted(store_mod.DEFAULT_ROLES)
        say_ = ('Which system is it? ' + ', '.join(types) + ' - name it and I will put the connection in front of you. '
                'A password or key never goes here; it goes on the card. Nothing is set up yet.')
        rec(say_, {'kind': SETUP_QUESTIONS, 'ask': ask, 'questions': ['Which system should I connect?']})
        return {'say': say_, 'options': [], 'decision': None}
    existing = store.get_connector_by_type(provider)
    # THE CARD ITSELF, OPENED (the owner, 2026-10-15: "help me set up the intacct api" should open the Sage Intacct settings page).
    # Every system the app knows has its card already; it holds the form, its guide and Set up with AI, and a proposal to
    # "create" it was a card about a card. The proposal below stays for a system with no card at all.
    if existing:
        name, link = existing.get('Name') or provider, f'#connector={provider}'
        say_ = (f"Here is your {name} connection{' - it is on' if existing.get('Active') else ''}: [Open the {name} connection]({link}). "
                'Fill in its fields and run Test, or press Set up with AI and it walks you through what it needs. A key or password '
                'goes on the card, never in this chat.')
        rec(say_)
        return {'say': say_, 'options': [], 'decision': None, 'open': link}
    cid = 0
    name = (existing or {}).get('Name') if cid else f"{provider.title()} (from the chat)"
    scope = scopes.default_scope(provider)
    params = {'type': provider, 'name': name, 'scope': scope, 'permissions': SCOPE_SAYS.get(scope, scope),
              'secret': 'never here - the card asks for it securely', 'starts': 'stays off until you turn it on after authorizing'}
    tail = (f"A {provider} connection with {scope} authority ({params['permissions']}). I never take a password or key in this chat: "
            'once the card exists, sign in or paste the secret there and run its Test. It stays off - nothing polls, nothing starts - '
            'until you turn it on. ' + WAITS)
    prop = _propose_raw(store, tid, 'connection.create', cid, params, 'Create the connection', f"{name} ({provider})", tail, actor, item)
    return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}


def away_line(o: dict) -> str:
    """Remind me's receipt, ONE sentence for the picker, the chat and the phone (B8): two of them sent the owner to "Upcoming in
    Tasks", a tab that no longer exists. `o` is remind.set_reminder's answer."""
    if not o.get('remindAt'): return 'It is back on your rail now.'
    return f"Away until {o['when']} - it is under {places.name('later')}, and back in front of you that morning." + (f" {o['warn']}" if o.get('warn') else '')


def _day_said(until) -> str:
    """A Remind me day the way the page says it ("Tue 20 Oct"), not the model's 2026-10-20 - as written when it is no day remind reads."""
    from . import remind
    try: at = remind.parse(until)
    except ValueError: return str(until)
    return remind.when(at) if at else str(until)


def op_label(kind: str, p: dict) -> str:
    """The button's words for an operation, in the owner's terms. toolcatalog.PURPOSE is written for the
    MODEL ("start an agent from a brief when there is no message behind it - `kind`, `text`"); read as a
    label it put that sentence on the button of a plain to-do, and said an agent had started when none had."""
    by_kind = {kind_: [PROPOSALS[v][1] for v in PROPOSALS if PROPOSALS[v][0] == kind_][0] for kind_ in {PROPOSALS[v][0] for v in PROPOSALS}}
    label = by_kind.get(kind) or toolcatalog.PURPOSE.get(kind, kind).split(' - ')[0].strip()
    L = buttons.label        # a label that names a button is the button's own name (buttons.json), never a second wording
    hand = {'coding': L('coding_agent'), 'general': L('regular_agent'), 'task': L('mine')}
    if kind == 'task.create_from_message': label = hand.get(str(p.get('kind')), L('mine'))
    if kind == 'task.create_from_text': label = hand.get(str(p.get('kind')), L('regular_agent'))
    if kind == 'preference.exclude_sender': label = L('not_ours_sender') if p.get('scope') == 'sender' else PROPOSALS['not_ours_remember'][1]
    if kind == 'item.settle': label = L('close') if p.get('tid') else L('next')
    if kind == 'report.create': label = 'Create the report'
    if kind == 'connection.create': label = 'Create the connection'
    if kind == 'role.apply': label = 'Set it up'
    if kind in toolcatalog.INSTANT or kind == 'report.delete': label = toolcatalog.PURPOSE.get(kind, kind).split(' - ')[0].strip()
    label = {'hub.publish': 'Save it to the Hub', 'task.update': 'Change the task', 'task.set_kind': 'Change what kind of work it is', 'task.set_repo': 'Put it in that repository',
             'task.check': 'Tick the checklist item', 'task.checklist': 'Change the checklist', 'task.watch': 'Watch it for you', 'task.comment': 'File the note', 'task.handoff': 'Write the hand-off for your yes',
             'task.merge': 'Fold it into that task', 'task.clarify': 'Write the question for your yes', 'task.reopen': L('reopen'),
             'task.trust': 'Trust what is on it',
             'task.not_a_task': L('remove'), 'dispatch.prepare': L('regular_agent'), 'agent.continue': L('continue'),
             'review.reject': 'Reject the draft', 'task.split': L('split', 'split'), 'report.rerun': L('rerun'), 'connection.test': L('test_connection'),
             'message.retriage': L('retriage'), 'task.share': L('share'),
             # PURPOSE is written for the model: read as a label it put "how work like this should be ROUTED" on the button (2026-10-18)
             'memory.remember': 'Remember it', 'routing.remember': 'Remember where work like this goes'}.get(kind, label)
    if kind == 'dispatch.prepare' and str(p.get('kind')) == 'coding': label = L('coding_agent')
    if kind == 'idea.act': label = {'task': L('mine'), 'agent': L('regular_agent'), 'dismiss': L('not_ours'),
                                    'dismiss_kind': L('not_ours_kind')}.get(str(p.get('verb')), label)
    if kind == 'task.defer': label = 'Bring it back now' if str(p.get('until') or '').lower() in ('none', '') else f"{L('defer')}: {_day_said(p.get('until'))}"
    return label[0].upper() + label[1:] if label else kind


def describe_op(store, op: dict) -> tuple:
    """(the button's label, what it was about) for a proposal row - the receipt's two facts."""
    kind, p, tk, target = op.get('kind'), op.get('params') or {}, op.get('targetKind'), op.get('target')
    label = op_label(kind, p)
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
        elif tk == 'role':
            from . import roles
            ref = (roles.ROLES.get(str(p.get('role') or '')) or {}).get('title', '')
    except Exception: ref = ''
    return label, ref


def _outcome_line(kind: str, p: dict, o: dict | None) -> str:
    """What the handler reported, in the words the sweep, the split and the hand-off used to say for themselves."""
    o = o or {}
    # the merge landed and the reply beside it did not: both halves are facts, and the second one is still yours
    if kind == 'review.approve' and o.get('reply_error'):
        return f" {str(o['reply_error']).replace('Done on GitHub, but the', 'But the', 1)} - it is kept as the draft."
    if kind == 'review.approve' and (o.get('sent') or {}).get('to'): return f" Sent to {', '.join(o['sent']['to'])}."
    # Later says WHEN it comes back (funnel.later_until). A sent reply's watch is decided by the model after the send
    # (asks.watch_reply, in the background), so the approve receipt no longer claims one
    if kind == 'item.settle' and o.get('says') and not o.get('closed'): return f" {o['says']}"
    # the app itself, by name (server._run_operation's handlers): the fact of what it did
    if kind in ('report.run', 'report.rerun') and o.get('ref'):
        # one run of a workflow at a time (workflows.running): a second ask is taken to the run that is still working
        return (f" {o.get('title') or 'It'} {'is still running as' if o.get('busy') else 'started as'} {o['ref']} - open it to watch the agent, "
                'and its browser if it uses one.')
    if kind in ('report.run', 'report.rerun'):
        return f" {o.get('title') or 'It'} is running. {o.get('lands') or 'If it fails, the bell says why.'}"
    if kind in ('report.pause', 'report.resume'): return f" {o.get('title') or 'It'} is {'back on its clock' if o.get('active') else 'off its clock'}."
    if kind == 'report.route': return f" {o.get('title') or 'It'} now goes - {o.get('route')}."
    if kind == 'report.edit': return f" {o.get('title') or 'It'} changed: {', '.join(o.get('changed') or [])}."
    if kind == 'report.delete': return f" {o.get('title') or 'It'} is removed - Restore brings it back from Recently deleted on Reports for 30 days."
    if kind == 'setting.set': return f" {o.get('said') or ''}"
    if kind == 'task.update':
        from .remind import when
        said = lambda k, v: (f"the due day is now {when(v)}" if v != 'none' else 'no due day now') if k == 'DueAt' else f"{k.lower()} is now {v or 'nobody'}"
        return ' ' + ', '.join(said(k, v) for k, v in (o.get('changed') or {}).items()) + '.'
    if kind == 'task.check' and o.get('item'): return f" {'Unticked' if o.get('done') is False else 'Ticked'}: {o['item']}."
    if kind == 'task.watch': return (' Stopped watching it.' if o.get('watch') == 'off' else
                                     f" I'll tell you {'here ' if o.get('via') else ''}when " + {'done': 'it is done', 'reply': 'someone replies on it'}.get(o.get('watch'), 'anything happens on it') + '.')
    if kind == 'task.checklist': return f" The list has {len(o.get('checklist') or [])} item(s)" + (f", {o['added']} email(s) added." if o.get('added') else '.')
    if kind == 'task.handoff' and o.get('to'): return f" The hand-off to {o['to']} is below for your yes - nothing has gone."
    if kind == 'task.clarify': return ' The question is below for your yes - nothing has gone.'
    if kind == 'task.share': return f" The summary for {o.get('to') or 'them'} waits in Close out for your yes - nothing has gone."
    if kind == 'review.reject': return ' The draft is rejected; the task stays open.'
    if kind == 'task.defer': return ' ' + away_line(o)
    if kind == 'connection.test': return f" {o.get('name') or 'It'} {'answered' if o.get('answered', o.get('ok')) else 'did not answer'}: {str(o.get('detail') or '')[:300]}"
    if kind in ('connection.pause', 'connection.resume'): return f" {o.get('name') or 'It'} is {'on' if o.get('active') else 'off'}."
    if kind == 'script.start': return f" Starting: {o.get('script')}."
    if kind == 'pipe.clear':
        if o.get('cleared'):
            return (f" Marked {_set_noun(p.get('select') or {}, o['cleared'])} read - {', '.join((o.get('titles') or [])[:3])}{'…' if o['cleared'] > 3 else ''}. "
                    "Read, not deleted - search still finds them."
                    + (f" {o['stuck']} wouldn't move just then and {'is' if o['stuck'] == 1 else 'are'} still waiting"
                       ' - say it again and they go too.' if o.get('stuck') else '')
                    )
        return ' Nothing waiting matches those words.'
    if kind == 'task.split':
        if o.get('newRef'): return f" {o.get('ref') or 'It'} keeps \"{o.get('kept') or ''}\" and {o['newRef']} is \"{o.get('title') or ''}\" - each is its own job now."
        return ' I can only see one ask in that one' + (f" - {o['why']}" if o.get('why') else '') + '. It stays as it was.'
    if kind == 'task.create_from_text' and o.get('ref') and p.get('kind') == 'task':
        return f" {o['ref']} - \"{o.get('title') or ''}\" is on your list; nothing was started."
    if kind == 'task.create_from_text' and o.get('ref'):
        return f" {o['ref']} - \"{o.get('title') or ''}\" is being worked on now{' (code work)' if p.get('kind') == 'coding' else ''}; what comes of it is kept on {o['ref']} - open it from here or from Tasks."
    if kind == 'task.setup' and o.get('ref'):
        return (f" {o['ref']} - \"{o.get('title') or ''}\" is ready as a walk-through - one step at a time, nothing built and nothing "
                "changed until you say so. Open it when you want to start.")
    if kind == 'task.create_from_message' and p.get('kind') in task_kinds.AGENT:
        # the phone starts the agent itself (remote_assistant._run): a start that failed is its own line (receipt_turn), never "Done"
        if o.get('existing'): return " It was already being worked on."
        if o.get('started') or o.get('chat'): return " It's being worked on now - moving on."
    if kind == 'item.settle' and o.get('closed'): return f" {task_ref(int(o['closed']))} closed."
    if kind == 'agent.stop': return ' The task stays open - say close it when you want it closed.'
    if kind == 'memory.remember': return ' I will use it from now on; whatever you were on stays where it was.'
    if kind == 'report.create' and o.get('sourceId'):
        return f" \"{o.get('title')}\" is under Reports{' and runs on its schedule' if o.get('enabled') else ', switched off'}."
    if kind == 'connection.create' and o.get('connectorId'):
        return (f" The {o.get('type')} card \"{o.get('name')}\" is {o.get('state')} - finish it on the card (sign in or paste the secret there), "
                'then Test; it stays off until you turn it on.')
    if kind == 'role.apply' and o.get('role'):
        bits = [f"the {o['profile'].upper()} agent is {'added' if o.get('profile_added') else 'already here'}"]
        if o.get('playbooks_added'): bits.append(f"{plural(len(o['playbooks_added']), 'playbook')} added")
        bits.append('your non-coding mail goes to it' if o.get('mail_routed') else
                    "nothing is sent to it by default, though it is on the list new mail is sorted to, so mail that reads as its work can still "
                    'reach it - turn off "Can be given new work from what comes in" on its profile to stop that' if o.get('on_roster') else
                    'your mail goes where it went before')
        if o.get('ledger_narrowed'): bits.append(f"{o['ledger_narrowed']} is set to read, so nothing reaches it without your click")
        flow = (f" \"{o['workflow_title']}\" is under Reports, switched off. Say run it and I'll start it once - "
                'when it stops at the sign-in, sign in yourself in the browser beside the chat.') if o.get('workflow_id') else ''
        said = '; '.join(bits)
        return f' {said[0].upper()}{said[1:]}.{flow}'
    if kind == 'task.complete' and o.get('already'): return ' It was closed already.'
    return ''


def receipt(store, op: dict, actor: str = 'owner') -> str:
    """After the click: the fact of what happened, in the chat - never before it ran (PW-125)."""
    return receipt_turn(store, op, actor)['say']


# the close-out's own other buttons, when GitHub's reading offered them with the refusal (ghcloseout.assess)
OFFER_WORDS = {'update': 'Update branch', 'rerun': 'Re-run checks', 'anyway': f"{buttons.label('approve', 'action')} anyway"}
_PICK = re.compile(r'\n?\s*PICK:\s*(\d+)\s*$', re.I)


def recover(store, op: dict, actor: str = 'owner', llm=None) -> dict:
    """WHAT NOW, after an act that did not happen (the owner, 2026-09-29: "the assistant freezes instead of trying to
    figure out solution"). A failed Close out said "Not done - 403 ..." and offered nothing - no retry, no Mark done, no
    way on - and the model never heard it had failed.

    {'say': the model's sentence or '', 'chips': [...]}. The CHOICES are code's: Try again (never when GitHub named a grant
    the token lacks, or refused on the pull request's state - a retry only repeats those), GitHub's own offers, the item on
    the table's own verbs minus the act that just failed, then Next. The model says why and picks ONE of those by number;
    its pick leads and it can add nothing. `llm=False` skips the model (a phone number press, a test)."""
    st, o = op.get('status'), op.get('outcome') or {}
    if st not in ('error', 'stale'): return {'say': '', 'chips': []}
    tid = general.dock_task(store, actor)[0]['TaskId']
    try: item = restore_current(store, tid)
    except Exception as e:
        logger.debug(f'recover: no item on the table - {e}'); item = None
    chips = []
    # THE PLACE THAT FIXES IT, when the failure named one (outbound.Fixable, a send's `send_fix`): a choice like any other - the
    # model picks among them - so "no mailbox is connected" comes with Connect a mailbox, never only the words (2026-10-17)
    fix = o.get('fix') or o.get('send_fix')
    if isinstance(fix, dict) and fix.get('href') and fix.get('label'): chips.append({'verb': 'go', 'href': fix['href'], 'label': fix['label']})
    # ...and Try again only where the failure says it could work (failures.classify: never over a fix, never over a send that may
    # have gone - pressed, it repeated "nothing was sent" and sent nothing, 2026-10-18)
    if st == 'error' and o.get('retry', True) and o.get('delivery') != 'unknown' and not o.get('needs') and not o.get('refused') and o.get('dispatch') != 'needs_repo':
        chips.append({'verb': 'retry', 'label': buttons.label('try_again'), 'op': op['id'], 'version': op['version'], 'kind': op.get('kind'),
                      'settles': any(row[0] == op.get('kind') and row[2] for row in PROPOSALS.values())})
    chips += [{'verb': 'closeout', 'act': a, 'rid': o['rid'], 'label': OFFER_WORDS[a]}
              for a in o.get('offers') or [] if a in OFFER_WORDS and o.get('rid')]
    if o.get('dispatch') == 'needs_repo':
        # the checkout to open it in IS the way on - the desktop draws its picker; a chat had "needs a repository first"
        # and nothing to pick. Each one is the same hand-off, revised with that repository and run.
        from . import terminal as term
        chips += [{'verb': 'repo', 'label': f'Use {r}', 'op': op['id'], 'repo': r, 'params': op.get('params') or {},
                   'settles': any(row[0] == op.get('kind') and row[2] for row in PROPOSALS.values())} for r in term.known_repos(store)[:6]]
    # A SEND NOBODY CAN CONFIRM (2026-10-18): Try again re-asked the provider and said "nothing was sent again", forever. The way on is
    # the owner's: Send anyway (the same proposal, told to go past the check) or Mark done when they know it went
    if st == 'error' and o.get('delivery') == 'unknown' and op.get('kind') == 'review.approve':
        chips.append({'verb': 'revise', 'op': op['id'], 'params': {**(op.get('params') or {}), 'anyway': True},
                      'label': buttons.label('approve', 'unknown'), 'hint': buttons.hint('approve', 'unknown')})
        rv = store.get_review(int(o['rid'])) if o.get('rid') else None
        if rv and rv.get('TaskId'): chips.append({'verb': 'close', 'tid': rv['TaskId'], 'label': buttons.label('close')})
    # A START REFUSED FOR A STRANGER (origin.launch_mode): the way on is the owner's word on the sender - Trust and start, the same
    # proposal told to vouch first (server._run_kind) - never a Try again that is refused the same way, never another tool
    if st == 'error' and op.get('targetKind') == 'task' and "stranger's task" in str(op.get('error') or ''):
        chips = [c for c in chips if c.get('verb') != 'retry']
        chips.insert(0, {'verb': 'revise', 'op': op['id'], 'params': {**(op.get('params') or {}), 'trust': True},
                         'label': buttons.label('trust_start'), 'hint': buttons.hint('trust_start'),
                         'settles': any(row[0] == op.get('kind') and row[2] for row in PROPOSALS.values())})
    # nothing here fixes it and pressing again will not: the bug report, with what went wrong filled in (failures.chips)
    if st == 'error' and not chips: chips.append({'verb': 'bug', 'label': buttons.label('report_bug'), 'text': str(op.get('error') or '')})
    gone = {v for v, row in PROPOSALS.items() if row[0] == op.get('kind')}
    chips += [c for c in chips_for(store, item) if c['verb'] not in gone]
    if not any(c.get('verb') == 'next' for c in chips): chips.append({'verb': 'next', 'label': CHIP_WORDS['next']})
    say = ''
    b = _brain_for(store, tid, llm) if llm is not False and item else None
    if b:
        moves = '\n'.join(f"{i} · {c['label']}" for i, c in enumerate(chips, 1))
        what = describe_op(store, op)[0]
        instruction = (f'The owner just confirmed "{what}" on this item and it DID NOT happen. What came back: {op.get("error") or st}.\n'
                       'In one or two short sentences, in plain words: what went wrong and what would fix it - if it is something '
                       'only the owner can change (a permission, a setting), say where. Then recommend ONE of these moves:\n'
                       f'{moves}\nNever promise anything those moves do not do. End with a line PICK: <number>.')
        try:
            # not _ask (this instruction is not an introduction); its one check still holds here - another task named is dropped
            said = str(b(_system(store, b), f"THE ITEM ON THE TABLE - speak only about this one:\n{facts(store, item)}\n\n{instruction}",
                         max_tokens=MAX_TOKENS) or '').strip()
            said = gate(parse_decision(said)[0])[0]
            if off_subject(said, item): said = ''
            m = _PICK.search(said or '')
            say = _PICK.sub('', said or '').strip()
            # ...and a bare acknowledgement explains nothing: "Not sent - ... where it was. Ok." (the 2026-10-22 re-walk)
            if len(re.sub(r'[^\w\s]', '', say).split()) <= 2: say = ''
            k = int(m.group(1)) if m else 0
            if 1 <= k <= len(chips): chips = [chips[k - 1]] + [c for i, c in enumerate(chips) if i != k - 1]
        except Exception as e:
            logger.info(f'recover: the model did not answer about the failure - {e}'); say = ''
    return {'say': say, 'chips': chips}


def on_table(store, op: dict) -> bool:
    """Is this act about the item ON THE ASSISTANT'S TABLE? Read BEFORE it runs - a close takes the item off the pile, and after it
    nothing says which task the table held. A press on the table's own row is the walk's news as much as a chat proposal is:
    Mark done on an agent's task closed it with no line in the chat (the walk click-through, 2026-10-17)."""
    raw = store.get_setting('assistant_dock_task_id')
    if not str(raw or '').isdigit() or not op: return False
    key = current_key(store, int(raw))
    kind = (operations.KINDS.get(op.get('kind')) or ('',))[0]
    try: tid = int(op.get('target') or 0) if kind == 'task' else int((store.get_review(int(op.get('target') or 0)) or {}).get('TaskId') or 0) if kind == 'review' else 0
    except (TypeError, ValueError): tid = 0
    if not key or not tid: return False
    if key == f'task:{tid}': return True
    # ...from the rail's own build while nothing has been written since it began: the keyed build this asked for was 0.06-4.4 s
    # of every Mark done on a big home, only to read one row's task (2026-10-20). Otherwise the lookup it always was.
    held = funnel.rail_item(store, key)
    if held is not None: return held.get('tid') == tid
    try: item = funnel.next_item(store, key, include_surfaced=True)
    except Exception as e:
        logger.debug(f'on_table: {key} did not resolve - {e}'); return False
    return bool(item) and item.get('tid') == tid


def sent_chips(store, op: dict) -> list:
    """A SEND KEEPS ITS TASK (the owner, 2026-10-18: "sending and closing are two steps"): an Approve that ran - a reply sent,
    an agent's act run - leaves the item where it is, and its receipt carries the two ways on: Mark done, the one close,
    while its task is open, and Next. [] for any other act."""
    if op.get('kind') != 'review.approve' or op.get('status') != 'done': return []
    try: tid = (store.get_review(int(op.get('target') or 0)) or {}).get('TaskId')
    except (TypeError, ValueError): tid = None
    live = bool(tid) and (store.get_task(int(tid)) or {}).get('Status') not in (None, 'done', 'dropped')
    return ([{'verb': 'close', 'label': buttons.label('close'), 'tid': int(tid), 'ref': task_ref(int(tid))}] if live else []) \
        + [{'verb': 'next', 'label': buttons.label('next')}]


def _past(store, op: dict, ref: str) -> str:
    """A phone receipt in plain past tense - what happened, said once: "Sent to Gail Moreno · TQ-0001.", "TQ-0001 closed." - for the
    acts that have a plain one; '' leaves the desk's "Done - <button> · <ref>." (F13). The desk keeps its own wording."""
    kind, o = op.get('kind'), op.get('outcome') or {}
    on = f' · {ref}' if ref else ''
    if kind == 'review.approve' and (o.get('sent') or {}).get('to') and not o.get('reply_error'):
        # the person, by name, where the reply went to the one who wrote
        try:
            rv = store.get_review(int(op.get('target') or 0)) or {}
            m = store.get_message(int(rv['MessageId'])) if rv.get('MessageId') else {}
        except Exception: m = {}
        name = lambda a: (m or {}).get('FromName') if (m or {}).get('FromName') and str(a).strip().lower() == str((m or {}).get('FromEmail') or '').lower() else a
        return f"Sent to {', '.join(name(a) for a in o['sent']['to'])}{on}."
    if kind == 'task.complete' and ref.startswith('TQ-'):
        return f"{ref} {'was closed already' if o.get('already') else 'closed'}" + (' - the reply was not sent.' if o.get('unsent') else '.')
    if kind == 'item.settle' and o.get('closed'): return f"{task_ref(int(o['closed']))} closed" + (' - the reply was not sent.' if o.get('unsent') else '.')
    # ...and Not ours and Remind me, the walk's other two receipts: "Done - Not ours · Printer on 3 is jammed again." and "Done - Remind me:
    # Fri 23 Oct · TQ-0001. Away until ..." were still the desk's button words (the 2026-10-22 re-walk)
    if kind == 'task.create_from_message' and str((op.get('params') or {}).get('kind')) == 'task' and o.get('ref'): return f"{o['ref']} is on your list."
    if kind == 'message.file': return f'{ref} filed as not ours.' if ref.startswith('TQ-') else f'Filed as not ours: {ref}.' if ref else 'Filed as not ours.'
    if kind == 'task.defer' and ref.startswith('TQ-'):
        if not o.get('remindAt'): return f'{ref} is back on your rail now.'
        return f"{ref} is away until {o['when']} - back in front of you that morning." + (f" {o['warn']}" if o.get('warn') else '')
    return ''


def _item_of(store, op: dict) -> tuple:
    """(task id, card keys) of what an act was about - the item line _stamp_pressed marks."""
    tk, target, p = op.get('targetKind'), op.get('target'), op.get('params') or {}
    try:
        if tk == 'task': return int(target), {f'task:{int(target)}', f'agent:{int(target)}'}
        if tk == 'message': return (store.get_message(int(target)) or {}).get('TaskId'), {f'msg:{int(target)}'}
        if tk == 'review': return (store.get_review(int(target)) or {}).get('TaskId'), {f'review:{int(target)}'}
        if tk == 'item': return (int(p['tid']) if p.get('tid') else None), {str(p.get('key') or '')} - {''}
    except (TypeError, ValueError, KeyError): pass
    return None, set()


def _stamp_pressed(store, dock_tid: int, op: dict, label: str) -> bool:
    """A PRESS IS MARKED ON ITS CARD, NOT SAID (the owner, 2026-10-22: "I hate free text" ... "put a little animation on the corner of the
    past task - like button marked done not free text"): the newest dock line carrying the item gets the button's own label as `pressed`,
    which the page draws as a badge in that card's corner."""
    tid, keys = _item_of(store, op)
    if not tid and not keys: return False
    for c in reversed(general.chat_rows(store, dock_tid)):
        m = _MARK.search(c.get('Body') or '')
        if not m or c.get('ActorType') != general.ASSISTANT_TYPE: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if not isinstance(card, dict) or card.get('kind') in ('words', 'proposal'): continue
        if card.get('key') in keys or (tid and str(card.get('tid') or '') == str(tid)):
            # the button's own word: "Remind me: Thu 5 Nov" is the receipt's - the badge is the button the page drew, "Remind me"
            rewrite(store, int(c['CommentId']), _MARK.sub('', c.get('Body') or ''), {**card, 'pressed': label.split(': ')[0]})
            return True
    return False


def receipt_turn(store, op: dict, actor: str = 'owner', llm=None, table: bool = False, press: bool = False) -> dict:
    """The receipt AND, when it did not happen, its way on (recover): {'say': line, 'chips': [...]}. The chips ride on the
    recorded line, so the desktop draws them under it and the phone numbers them. `press`: a button pressed on the desk (the operations
    road, Remind me) - one that went through is stamped on its item's card (_stamp_pressed), never a line of its own."""
    label, ref = describe_op(store, op)
    st, start = op.get('status'), ''
    # the reason as a clause: "unknown agent: ." and "...failed.." were the error's own punctuation run into the sentence's
    why = lambda fallback: str(op.get('error') or fallback).strip().rstrip(' .:;') or fallback
    if st == 'done' and (start := str((op.get('outcome') or {}).get('start_error') or '').strip().rstrip(' .:;')):
        # THE TASK WAS MADE AND ITS AGENT NEVER STARTED (remote_assistant._run): "Done - Send to agent · TQ-0001. It is on TQ-0001, but
        # the agent did not start - ..." led with the one word that was not true (the 2026-10-22 re-walk)
        line = (f"Not started - the agent on {ref or 'it'} did not start: {start}. {ref or 'It'} is still on you, with nobody working on it; "
                f"try {buttons.label('regular_agent')} again once that is fixed.")
    elif st == 'done':
        line = ((DELIVERY.get() == PHONE and not op.get('duplicate') and _past(store, op, ref))
                or f"{'Already done' if op.get('duplicate') else 'Done'} - {label}{' · ' + ref if ref else ''}."
                + ('' if op.get('duplicate') else _outcome_line(op.get('kind'), op.get('params') or {}, op.get('outcome'))))
    elif st == 'error' and (op.get('outcome') or {}).get('unsent'):
        line = f"Not sent - {why('the reply did not go out')}. The reply is kept; {ref or 'it'} is where it was."
    elif st == 'error': line = f"Not done - {why('it did not go through')}. {ref or 'It'} is where it was."
    else: line = f"Not done - {why(st)}. {ref or 'It'} is where it was."
    # only what THIS chat proposed is its news. A close from the Tasks page or the wall used to be narrated
    # here too - and opened a fresh chat to say it in (the owner, 2026-09-07: "no one asked you to do that")
    # ...and what was pressed on the item on its table (`table`, on_table): that is this chat, and the owner is looking at it
    raw = store.get_setting('assistant_dock_task_id')
    dock_tid = int(raw) if str(raw or '').isdigit() else None
    proposed = bool(dock_tid) and _chat_proposed(store, dock_tid, op.get('id'))
    if not dock_tid or not (table or proposed): return {'say': line, 'chips': []}
    if st != 'done':
        way = recover(store, op, actor, llm)
        line = f"{line} {way['say']}".strip()
        # a NOTE kind (AssistantView NOTE_KINDS): the sentence shows and the chips sit under it - an item kind hid the words
        record(store, dock_tid, 'assistant', line, {'kind': 'words', 'key': None, 'title': label, 'chips': way['chips'],
                                                   'tid': None, 'ref': ref or None})
        return {'say': line, 'chips': way['chips']}
    if (chips := sent_chips(store, op)):
        record(store, dock_tid, 'assistant', line, {'kind': 'words', 'key': None, 'title': label, 'chips': chips, 'tid': None, 'ref': ref or None})
        return {'say': line, 'chips': chips}
    # A PRESS ON THE TABLE'S TASK VIEW (Stream B, 2026-10-18): its receipt is a notice beside the view, never a card that takes the table
    # from it. ONE LINE PER ACT and no Take it back (the owner, 2026-10-19: "no take it back button. hate that") - a wrong Mark done is
    # put right with Reopen task, the row's own button
    # ...and a BUTTON that went through is no line at all, only the badge on its card: "Done - Mark done · TQ-0001." under every press
    # (the owner, 2026-10-22: "we don't need that text ever"). An agent that never started is a failure, said as one; the words still
    # come back as `say` for the phone. An act with no card in the chat to wear it (a report set up from words, a connection) keeps its
    # line: there is nothing else to show it happened, nor that it waits on an authorization
    if press and not start and _stamp_pressed(store, dock_tid, op, label): return {'say': line, 'chips': []}
    record(store, dock_tid, 'assistant', line, None if proposed else {'kind': 'words', 'key': None, 'title': label, 'chips': [], 'tid': None,
                                                                     'ref': ref or None, 'background_event': True})
    return {'say': line, 'chips': []}


def _chat_proposed(store, dock_tid: int, oid: str) -> bool:
    for c in general.chat_rows(store, dock_tid):
        m = _MARK.search(c.get('Body') or '')
        if not m: continue
        try: card = json.loads(m.group(1))
        except ValueError: continue
        if card.get('kind') == 'proposal' and card.get('op') == oid: return True
    return False


def _asks_block(store, p: dict) -> str:
    """YOUR OPEN ASKS for this turn (asks.py), from the pile the turn already has - and never the reason a turn fails."""
    try: return asks.block(store, p.get('items') or [])
    except Exception as e:
        logger.warning(f'concierge: the open asks were left out of this turn - {e}'); return ''


RAIL_CAP = 20


def _rail_block(p: dict, cap: int = RAIL_CAP) -> str:
    """THE RAIL BY NAME, for this turn: ref, who and what of each row the pile already holds - no read, no build. "Remind me
    tomorrow about the Payworth invoice" had nothing in the prompt that said the Payworth invoice was TQ-0005, so it became a
    new to-do every time (2026-10-06). Only for resolving a name the owner uses; the item on the table still comes first."""
    items = p.get('items') or []
    rows = []
    for i in items[:cap]:
        # EVERY ROW HAS A HANDLE the model copies into `on` - its TQ ref, else its message's m-number - so naming one is exact: words
        # ("the Payworth mail") were resolved by a word-overlap guess in code (the owner, 2026-10-08: no code in front of the AI)
        bits = [x for x in (handle_of(i), i.get('who'), _cut(i.get('title') or '', 90)) if x]
        # ...and whether a DRAFT waits on it: the lane's word alone ("ready to send") left "reject the draft on TQ-0004" answered
        # "there is no draft", and "send the reply to Sam" written as a new one (real-AI check, 2026-10-18)
        if bits: rows.append(f"- {' · '.join(bits)} ({funnel.LANE_WORDS.get(i.get('lane'), ('',))[0]}"
                             + ('; a drafted reply waits for your yes' if i.get('rid') and i.get('draft') else '') + ')')
    if not rows: return ''
    more = f"\n- ...and {len(items) - cap} more (timeline.search finds them)" if len(items) > cap else ''
    return ('THE RAIL BY NAME - only to find the one the owner names; never act on a row they did not name. To act on one, put its '
            'handle (the TQ ref or m-number that starts its line) in `on` exactly\n' + '\n'.join(rows) + more)


def handle_of(i: dict) -> str:
    """What the model names a row by: its task's TQ ref, else its message's m-number, else its pile key."""
    return i.get('ref') or (f"m{i['mid']}" if i.get('mid') else '') or str(i.get('key') or '')


def say(store, text: str, key: str = None, llm=None, actor: str = 'owner', trace=None, cancel=None, item: dict | None = None,
        open_card: str | None = None, images: list | None = None) -> dict:
    token = _TURN.set({})
    try: return _say(store, text, key, llm, actor, trace, cancel, item, open_card, images)
    finally: _TURN.reset(token)


def _say(store, text: str, key: str = None, llm=None, actor: str = 'owner', trace=None, cancel=None, item: dict | None = None,
         open_card: str | None = None, images: list | None = None) -> dict:
    """The owner's words, answered briefly - about the item on the table when there is one. The MODEL interprets
    them (PW-121): a question is answered, a subject named is pulled in, and a decision brings its item up with the
    row's own button for it lit (routes, 2026-10-19) - on a phone, a proposal answered yes or no - except Next, which
    moves the walk and marks nothing, and a reply request, which drafts at once and sends nothing (PW-126/128). No
    phrase table decides anything."""
    text = str(text or '').strip()
    if not text: raise ValueError('say something')
    task, _ = general.dock_task(store, actor)
    tid = task['TaskId']
    p = funnel.pile(store)
    if item is None: item = funnel.next_item(store, key, items=funnel.full_items(store)) if key else None   # the route already built it
    # ...and a task opened by name or from the rail may not be in the pile at all: it is still what is on screen (2026-10-01)
    if item is None and key: item = funnel.item_for_key(store, key)
    # "1" MEANS THE SAME THING ON BOTH SCREENS. The phone numbers its options because a chat has no
    # buttons, and the owner, having answered by number there, typed "1" on the desktop too - where it
    # was just a digit for the model to interpret, so it answered about something else entirely (the
    # owner, 2026-09-15: "on the desktop when I hit 1 it shows the past message not matching what i
    # sent"). The action words under the line ARE numbered, in the order they are drawn.
    if item and text.strip().lstrip('#').rstrip('.').strip().isdigit():
        words = [c['label'] for c in chips_for(store, item)]
        i = int(text.strip().lstrip('#').rstrip('.').strip())
        if 1 <= i <= len(words): text = words[i - 1]
    # the dock has the owner's words now; the item has them with the answer, once the turn knows it was about the item
    record(store, tid, 'user', text)
    turn = _TURN.get()
    if item: turn.update(item=item, said=text)
    rec = lambda role, body, card=None: record_related(store, tid, item, role, body, card)
    table = table_line(store, item)
    llm = _brain_for(store, tid, llm, trace, cancel)
    if not llm:
        fb = fallback(item, False, p['items'], store=store).strip()
        if fb and not fb.endswith(('.', '!', '?', ')')): fb += '.'               # a sentence ends before the next one starts
        say_ = fb if places.name('ai') in fb else f"{fb} {no_brain()}".strip()     # the empty table's facts already say it
        rec('assistant', say_)
        # `open: ''` - these are the app's words, and their AI link is to press: the page followed it, and "show me TQ-0003" with no
        # AI answered about the table and then covered it with Connections (2026-10-19 UI walk)
        # ...and the button that connects one leads the chips (owner-approved, 2026-10-21: every "no AI" line carries Connect an AI);
        # a phone chat has no page to open, so it keeps the words alone
        ai = [] if DELIVERY.get() == PHONE else [connect_ai_chip()]
        return {'say': say_, 'options': [], 'chips': ai + (chips_for(store, item) or walk_chips(len(p['items']))), 'decision': None, 'open': '',
                'no_brain': True}
    reply, options, decision, call, did_read, failed = '', [], None, None, False, None
    try:
        # NO HUB NOTES PER TURN. Every turn carried whatever notes shared the owner's words - asked to research a
        # project, the model read internal notes on CLI flags and timeouts, and answered in that register (the
        # 2026-09-24 debug). knowledge.search reads the Hub when a question is about how things are done here.
        from . import toolcatalog
        # PROGRESSIVE DISCLOSURE (the owner, 2026-09-25): COUNSEL, SOUL, where the voice is, and the tool index. The
        # workers, the repositories and the app's state rode every turn as blocks; agents.list, repos.list,
        # reports.list, connections.list and settings.list read them when a turn needs them.
        # ...and the Hub is a tool too (hub.publish), not an envelope taught every turn (2026-09-25)
        system = turn_system(store, llm)
        # the pipe's own SELECT values ride the turn, not the index (toolcatalog.select_values): they move with every mail
        asked = (f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(p['items'], coming=False)}\n{toolcatalog.select_values(store)}\n\n"
                 f"{facts(store, item, whole=True)}\n\n"
                      + (f"THE TASKS THEY NAMED, as they are now:\n{nn}\n\n" if (nn := named_now(store, text, item)) else '')
                      # what the owner handed over and where each stands (asks.py) - "where's the tab check?", "add Omar to that"
                      + (f"{asks_block}\n\n" if (asks_block := _asks_block(store, p)) else '')
                      + (f"{rail}\n\n" if (rail := _rail_block(p)) else '')
                      + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
                      # THE CARD BROWSED OPEN in the canvas (the canvas redesign, 2026-09-29): "this", "it", "set it up"
                      # mean that card - a connector, a settings group, a report - when no item is on the table
                      # ...or the PAGE open with nothing opened on it (2026-10-01): a question over the Connections wall is about connections
                      + (f"ON SCREEN NOW: {_cut(open_card, 300)} - 'this' and 'here' mean what is on screen: answer about it first; its own operations set it up\n\n" if open_card and not item else '')
                      # ...and a page opened BESIDE the item keeps the item on the table: the Assistant's own "turn off background sync" opened
                      # Settings, and the next "mark this done" went out about nothing (verify, 2026-10-19). Both are said; their words say which
                      # ...under that page, out of sight: "show me TQ-0003" over Connections answered and left it covered (2026-10-19 UI walk, G5)
                      + (f"OPEN BESIDE IT: {_cut(open_card, 300)} - the item is still on the table, under that page; 'this' is whichever of the two "
                         f"their words fit{under_page(item)}\n\n" if open_card and item else '')
                      + (f"{table_actions(store, item)}\n\n" + (f"{adv}\n\n" if (adv := _advice_block(store, item)) else '') + f"{WHAT_ABOUT}\n\n" if item else '')
                      + f"{OWNER_SAYS}{text}\n"
                      # A PICTURE WITH THE LINE (the owner, 2026-09-30): an API brain sees it, a CLI brain reads the file it names
                      + ("ATTACHED IMAGES (read these files - they are what the owner is showing you)\n" + "\n".join(images) + "\n" if images else '')
                      + f"Answer them, briefly. If a look-up would answer it, CALL it now instead of saying you will. "
                      + ('If their words mean one of the actions for the item on the table, CALL it.' if item else
                         'If they ask for something to be done, CALL it now - its button is their confirmation.'))
        raw = str(llm(system, asked, max_tokens=MAX_TOKENS, **({'images': general._images(images)} if images else {})) or '').strip()
        raw, call = parse_call(raw)
        # A LOOK-UP runs at once and comes straight back, because it changes nothing and waits for
        # nobody. The model then answers with what it read - one round only, so a question can never
        # become an unbounded search (the owner, 2026-09-07: "read should be immediate").
        # ...and the LAST round says it is the last. Told only "if it did not answer, CALL another", a question
        # nothing here has ever written down - a GitHub project to research - searched, searched again and
        # ended on a bare CALL with no words, which read as "No AI is connected" (the owner, 2026-09-24:
        # "i asked it to research for me which should open a agent card but it did nothing")
        for n in range(READ_ROUNDS):
            if not (call and toolcatalog.is_read(call['kind'])): break
            did_read = True; _strays(item, call)
            found = _read(store, item, call)
            trace and trace('tool', call['kind'], {'params': call['params']})
            then = (LAST_READ if n == READ_ROUNDS - 1 else
                    'Answer them with what you just read, briefly. If it did not answer them and another look-up would, CALL that one now - never offer to look.')
            raw = str(llm(system, f"{table}\n\nYou looked up {call['kind']} and it says:\n{_cut(found, 6000)}\n\n"
                                  f"The owner asked: {text}\n{then}",
                          max_tokens=MAX_TOKENS) or '').strip()
            raw, call = parse_call(raw)
        # the budget is spent and it still wants to read: that is as far as this turn goes. A read is
        # never handed on to call_turn, which only knows operations that CHANGE something.
        out_of_reads = bool(call and toolcatalog.is_read(call['kind']))
        if out_of_reads: call = None
        raw, decision = parse_decision(raw)
        reply, options = parse_options(raw)
        # A BROKEN ANSWER IS ASKED AGAIN, ONCE (gate): what it acted on stands; only the words are asked for again, then a plain line
        reply, broken = gate(reply)
        if broken and not call and not decision:
            again = str(llm(system, asked + "\n\nYOUR LAST ANSWER WAS CUT OFF in the middle. Answer again, briefly - and a CALL, if one "
                                     "is needed, as one whole line at the end.", max_tokens=MAX_TOKENS) or '').strip()
            again, call = parse_call(again)
            if call and toolcatalog.is_read(call['kind']): call = None              # no second round of look-ups on a retry
            again, decision = parse_decision(again)
            reply, options = parse_options(again)
            reply, broken = gate(reply)
        # still broken: what stands before a cut-off CALL is a preamble ("Let me"), never the answer
        if broken and not call and not decision: reply, options = LOST, []
        # ...and the words it wrote around that last call are a PREAMBLE, never the answer: "I'm handing it to the analyst -
        # you'll confirm it on the card" was shown with no card behind it (2026-10-06)
        if out_of_reads and not decision: reply, options = "I could not finish looking that up - ask me again, a little more narrowly.", []
        _remember_sid(store, tid, llm)
    except Exception as e:
        logger.warning(f'concierge: the model pass failed - {e}'); failed = e
    if cancel is not None and cancel.is_set(): raise Stopped('stopped by the owner')
    if call:
        # A MISS IS THE MODEL'S TO FIX, not the owner's to read. "No setting by that name - settings.list <group> names
        # them" is written for the model, and it reached the owner word for word (the 2026-09-24 audit). The model gets
        # it back, may look the name up, and calls again; only a second miss is said - once, in the owner's hearing.
        miss = None
        for _ in range(LOOKUP_ROUNDS + 1):
            _strays(item, call)
            if toolcatalog.is_read(call['kind']):
                if _ == LOOKUP_ROUNDS: break                 # out of look-ups: said below, never the promise around it
                found = _read(store, item, call)
                trace and trace('tool', call['kind'], {'params': call['params']})
                ask = (f"{table}\n\nYou looked up {call['kind']} and it says:\n{_cut(found, 6000)}\n\nThe owner asked: {text}\n"
                       'Now CALL the action again with the exact name you read, or answer them in plain words.')
            else:
                off = table_op_verb(call) if item else None
                if off and not is_button(store, item, off):
                    if not reply: reply, options = _in_words(llm, system, table, text, off)
                    call = None; break
                try: return call_turn(store, tid, call, item, text, actor)
                except CallMiss as e:
                    if miss: miss = str(e); break                    # the second miss: said, below - its OWN words, not the first's
                    miss = str(e)
                except ValueError as e:
                    say_ = f"I could not put that in front of you - {e}."
                    rec('assistant', say_)
                    return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
                ask = (f"{table}\n\nYou asked Taskuary for {call['kind']} {json.dumps(call.get('params') or {}, default=str)[:400]} and it "
                       f"answered: {miss}\n\nThe owner asked: {text}\nFix it yourself: CALL a look-up for the right name, then the "
                       'action again - or answer them in plain words. Never pass that answer on to them.')
            try:
                raw = str(llm(system, ask, max_tokens=MAX_TOKENS) or '').strip()
            except Exception as e:
                logger.warning(f'concierge: the retry pass failed - {e}'); raw = ''
            raw, call = parse_call(raw)
            raw, decision = parse_decision(raw)
            reply, options = parse_options(raw)
            if not call: break
        if call or (miss and not reply and not decision):
            # still stuck on a call it cannot make: say what is missing, never the filler it wrote around the call - the
            # filler is a promise ("I'm handing it to the analyst, confirm it on the card"), and with the call dropped there
            # was no card (2026-10-06). The last pass's own action is never dropped: the loop above runs it on its way out.
            say_ = (f"I could not find what that points at ({miss.rstrip('.')}). Say it another way and I will try again."
                    if miss else "I could not finish looking that up - ask me again, a little more narrowly.")
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
    # NO WORD MATCH OVERRIDES THE ANSWER. Any subject sharing half the owner's words used to replace the model's
    # reply with that item: "research CLI Anything on GitHub" became a GitHub PR email, "yes, go ahead" someone
    # else's message, "what's waiting on me" a certificate notice - 10 of 63 real asks (the 2026-09-24 debug). The
    # model pulls an item in itself when the owner names one: task.read, timeline.search, or DECIDE ... ON:.
    verb = (decision or {}).get('verb')
    if decision and handoff_verb(store, verb) != verb: decision, verb = {**decision, 'verb': 'regular_agent'}, 'regular_agent'
    # their yes to the card already waiting on it - the button, said in words (the only road a phone has)
    if verb in ('confirm', 'cancel'): return confirm_open(store, tid, item, verb == 'cancel', actor)
    # NOTHING ON THE TABLE, BUT THE WORDS NAME IT: "reply to Marcus: yes" came back as reply ON TQ-0004 and was answered
    # "Nothing is on the table ... name the one you mean" - the owner had named it, and so had the model (2026-10-06). The
    # named item is the target, exactly as it is when something else is on the table.
    target_item, elsewhere = item, False
    # AN `on` THAT IS NO ROW goes back to the model once, with the rail in front of it, to name the handle - code does not guess
    # which row its words meant (2026-10-08)
    if decision and decision.get('on') and _resolve_named(store, decision['on'], item) == '?' and llm:
        try:
            # ...on the turn's own instructions: a CLI brain is launched with them, and other ones restarted its process twice
            again = str(llm(turn_system(store, llm), f"{table}\n\n{_rail_block(p)}\n\n{OWNER_SAYS}{text}\nYou chose {decision.get('verb')} "
                                                f"with `on`: {str(decision['on'])[:80]!r}, which names no row. Put the row's handle in `on` - the "
                                                'TQ ref or m-number that starts its line above, or one a look-up gave you - and CALL it again. '
                                                'If none of them is it, say so in plain words.', max_tokens=MAX_TOKENS) or '')
            redo = parse_decision(parse_call(again)[0])[1]
            if redo and redo.get('verb') == decision.get('verb') and redo.get('on'): decision = {**decision, **redo}
        except Exception as e: logger.warning(f'concierge: asking for the row again failed - {e}')
    if decision and not item and decision.get('on') and decision.get('verb') != 'next':
        other = _resolve_named(store, decision['on'], None)
        it2 = None if other == '?' else (funnel.next_item(store, other) or funnel.item_for_key(store, other))
        if not it2:
            say_ = (f"I could not find {str(decision['on']).strip()!r} - say it again with the sender or the TQ ref and I will "
                    f'{_there()}; nothing has been touched.')
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': walk_chips(len(p['items'])), 'decision': None}
        target_item, elsewhere = it2, True
    # NOTHING ON THE TABLE: next / done / later move the WALK; a verb that needs something to act on says so
    if decision and not item and not target_item:
        if verb == 'next':
            return surface(store, None, llm, actor, None, trace, cancel)
        # "remind me to renew the contract" read as `mine` - theirs to do - with nothing on the table to be
        # theirs: that is a new to-do in their words, not "nothing is on the table" (2026-09-23)
        if verb == 'mine':
            return call_turn(store, tid, {'kind': 'task.create_from_text', 'params': {'kind': 'task', 'text': (decision.get('text') or text).strip()}},
                             None, text, actor)
        if verb in NEEDS:                              # a hand-off is NOT in NEEDS: the owner's words are its brief
            # an ANSWER from a look-up, with a stray decision on the end, keeps the answer: "what happened with TQ-0731"
            # was read and answered well, then suggested "DECIDE: reply", and the whole answer became "Nothing is on the
            # table" (2026-09-24). Without a read the words are a verb - "close it" answered "Ok." - and "Ok." would claim.
            say_ = reply if (did_read and reply) else (
                'Nothing is on the table. Say next and I will bring the next thing up, or name the one '
                f'you mean - the sender or its TQ ref - and I will {_there()}.')
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': walk_chips(len(p['items'])), 'decision': None}
    # a switch is already a proposal on the task (proposals.py); a hand-off to a person is a DRAFT for approval
    # the words name ANOTHER subject: resolve it and propose THERE, or ask - never on what happens to be open
    if decision and item and decision.get('on'):
        other = _resolve_named(store, decision['on'], item)
        if other == '?':
            say_ = (f"Careful - you named something that is not what is on the table. On the table is {_where(item)}, "
                    f'and I could not find what you meant. Say it again with the sender or the ref and I will {_there()}; nothing has been touched.')
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, item), 'decision': None}
        # one entry of the fyi handful is a thing of its own (PW-126): the verb lands on it, its siblings stay unread
        members = {e.get('key'): e for e in (item.get('items') or [])} if item.get('kind') == 'fyis' else {}
        it2 = members.get(other) or funnel.next_item(store, other) or funnel.item_for_key(store, other)
        if it2 and it2.get('key') != item.get('key'): target_item, elsewhere = it2, True
    if elsewhere: turn['aside'] = True
    # A JOB OF ITS OWN: "how many open invoices does Harbor Supply have?" over Erin's export bug - the model said it was leaving
    # TQ-0001 alone and called regular_agent with its own brief, and the card handed Erin's bug to the analyst with the AP
    # question as instructions (2026-10-06). `new` is the model saying so; the brief becomes a task of its own.
    if decision and decision.get('new') and verb in ('coding_agent', 'regular_agent') and str(decision.get('text') or '').strip():
        target_item, elsewhere = None, False
    # WORDS TO AN AGENT THAT ASKED are its answer: "reply to Marcus: yes, Thursday at 2 works" landed on the agent parked on
    # Marcus's task with "are you free Thursday at 2?", and was refused as "nothing to reply to" (2026-10-06)
    # ...and so is "send Omar the answer" (approve) over an agent asking "send it as drafted, or hold it?"
    # Only when the card cannot carry the verb itself: a reply to the person who wrote is still a reply.
    if decision and verb in ('reply', 'approve') and target_item and target_item.get('kind') == 'agent' and cannot(target_item, verb, store):
        decision, verb = {**decision, 'verb': 'answer_agent', 'text': decision.get('text') or text}, 'answer_agent'
    if decision and verb and target_item:
        why = cannot(target_item, verb, store)
        if why:
            rec('assistant', why)
            return {'say': why, 'options': [], 'chips': chips_for(store, target_item), 'decision': None}
    # a decision the item has no button for is answered in words, never offered as a card (the 2026-10-01 press audit)
    # ...but "create an agent to research X" over a card with no message behind it (a meeting, an idea) is a NEW job in the
    # owner's words, not the card's hand-off - it still comes back as a proposal for his yes (2026-10-02: the meeting lost
    # its Send to agent button, and the typed road must not go with it)
    own_job = verb in ('coding_agent', 'regular_agent') and str((decision or {}).get('text') or '').strip() and not (target_item or {}).get('mid')
    if decision and verb and target_item and not elsewhere and not own_job and not is_button(store, target_item, verb):
        if not reply: reply, options = _in_words(llm, system, table, text, verb)
        decision = verb = None
    # the two immediate exceptions the owner approved: Next moves the walk (PW-128); a reply DRAFTS (PW-126)
    if decision and verb == 'next' and item:
        # ...in the model's own words when it wrote any: a bare "Next." over a request that asked for something else read as the request
        # ignored (2026-10-20, "Clear all the FYI, please."). An "Ok." says less than Next does, and is not kept
        move_on(store, item['key'], actor)
        # ...and on the desk the receipt names what was put down: a bare "Next." is a word, not what it did (the owner, 2026-10-20: "it
        # should show what it chose to do")
        said = (reply if len(reply.split()) > 2 else
                f"Put down {item.get('ref') or _title_cut(str(item.get('title') or 'that one'), 60)} - on to the next." if routes() else RECEIPTS['next'])
        rec('assistant', said)
        return {'say': said, 'options': [], 'chips': [], 'decision': {'verb': 'next'}}
    if decision and verb in ('reply', 'redraft') and target_item:
        # A CLOSED TASK IS SAID SO: "approve the Fairhaven PO" drafted "Approved" on a task already marked done, and nothing said it
        # was (real-AI check, 2026-10-18). The draft is still theirs to send; it never reopens the task - Reopen task does
        said = (f"{'Drafting a reply' if verb == 'reply' else 'Rewriting the draft'} on {target_item.get('ref') or _title_cut(str(target_item.get('title') or 'it'), 60)}"
                + (f" - it waits for your {buttons.label('approve')}." if routes() else ' - nothing goes out until you say yes.')) + closed_note(store, target_item)
        rec('assistant', said)
        d = {'verb': verb, 'text': decision.get('text') or ''}
        if verb == 'reply' and decision.get('cc'): d['cc'] = decision['cc']            # LOOP THEM IN: the reply copies them (open_reply)
        if elsewhere: d['target'] = card_for(target_item)
        return {'say': said, 'options': [], 'chips': [], 'decision': d}
    if decision and verb == 'setup':                                     # a report, a connection: gathered, then confirmed (PW-194)
        return setup_turn(store, tid, text, decision.get('text') or text, item, actor, trace=trace, cancel=cancel)
    # ON THE DESK THE WORDS LIGHT THE BUTTON (routes): the item comes up with its own button for the act lit, and nothing runs - except
    # words to an agent that asked, which are its answer; a new job is New, filled in; a fact to keep goes in under Verdicts & notes
    if decision and verb in PROPOSALS and routes():
        if verb == 'answer_agent' and target_item and target_item.get('tid'):
            return _answer_now(store, tid, item, int(target_item['tid']), decision.get('text') or text, actor)
        if verb == 'remember': return call_turn(store, tid, {'kind': 'memory.remember', 'params': {'note': decision.get('text') or text}}, item, text, actor)
        if verb in ('coding_agent', 'regular_agent') and (own_job or not target_item):
            return _new(store, tid, item, 'coding' if verb == 'coding_agent' else 'general', decision.get('text') or text)
        if target_item:
            try: return _lit(store, tid, item, target_item, verb, note=str(decision.get('text') or '').strip() if verb == 'continue' else '')
            except CallMiss:                                           # no such button on its row: the model says so in words
                # ...except a report asked to run again: Run it again is drawn only on a failed run, and the report's own page has Run now -
                # "run the AP ageing again" over a good run was answered in words with the page one link away (the 2026-10-20 query walk)
                if verb == 'rerun' and target_item.get('source_id'):
                    return _page(store, tid, item, f"#report={int(target_item['source_id'])}",
                                 f"Opened {target_item.get('title') or 'the report'} under Reports - {REPORT_SAYS['report.run']} there.")
                reply, options = _in_words(llm, system, table, text, verb)
                rec('assistant', reply)
                return {'say': reply, 'options': options, 'chips': chips_for(store, item), 'decision': None}
        say_ = 'Nothing is on the table. Name the one you mean - the sender or its TQ ref - and I will bring it up.'
        rec('assistant', say_)
        return {'say': say_, 'options': [], 'chips': walk_chips(len(p['items'])), 'decision': None}
    if decision and verb in PROPOSALS:
        try: prop = propose_for(store, tid, decision, target_item, text, actor, elsewhere=elsewhere, table=item)
        except ValueError as e:
            say_ = f"I could not put that in front of you - {e}."
            rec('assistant', say_)
            return {'say': say_, 'options': [], 'chips': chips_for(store, target_item), 'decision': None}
        # a plain verb on the item on the table runs at once - the page presses the button itself (the owner,
        # 2026-09-07: "I did already - it should close it; only confirm when you are not sure"). A hand-off, a
        # send, a rule or a verb aimed elsewhere still waits for the button.
        # ...but never an agent: typed words that would start or resume one wait for the owner's press (the owner, 2026-10-01 -
        # "what should I do next?" over an Advisor idea started a researcher; it had earlier asked for a clear ask to start at once)
        if verb in AUTO and verb not in AGENT_STARTS and not elsewhere:
            # ...and a run at once still says what it could not do ("nothing to wrap")
            prop.update(auto=True, say_card=prop.get('note') or '', say=f"{prop['label']} - {_where(target_item or {})}." + (f" {prop['note']}" if prop.get('note') else ''))
        rec('assistant', prop['say'], {'kind': 'proposal', 'key': prop.get('key'), 'title': prop['label'], 'op': prop['id'],
                                        'tid': prop.get('tid'), 'ref': prop.get('ref'), 'lane': (target_item or {}).get('lane')})
        return {'say': prop['say'], 'options': [], 'decision': None, 'proposal': prop}
    # THE AI FAILED: say so and what to do, with Try again (the owner's own words, sent again) and the way on
    if not reply and failed is not None and not decision:
        say_ = brain_trouble(failed)
        chips = [{'label': buttons.label('try_again'), 'ask': text}, *(chips_for(store, item) or walk_chips(len(p['items'])))]
        rec('assistant', say_)
        return {'say': say_, 'options': [], 'chips': chips, 'decision': None, 'error': True}
    # NEVER A REFERENCE THAT DOES NOT EXIST: a choice naming one is dropped, and an answer naming one is asked for again once
    options = [o for o in options if not unreal_refs(store, o, text)]
    bad = unreal_refs(store, reply, text)
    if bad and failed is None:
        try:
            raw = str(llm(system, f"{table}\n\nYour answer named {', '.join(bad)}, which do not exist"
                                  + (f" - {NO_THREAD}" if no_thread(item) else '') + f".\nThe owner asked: {text}\n"
                                  'Answer them again from what you know, naming no reference that does not exist, and CALL nothing.',
                          max_tokens=MAX_TOKENS) or '').strip()
        except Exception as e:
            logger.warning(f'concierge: the second answer failed - {e}'); raw = ''
        raw, _ = parse_call(raw); raw, _ = parse_decision(raw)
        reply, options = parse_options(raw); reply = gate(reply)[0]
        if unreal_refs(store, reply, text): reply = ''
        options = [o for o in options if not unreal_refs(store, o, text)]
    # a brain that answered with nothing is not "no AI": say what happened, never the missing-connector line
    if not reply: reply = fallback(item, False, p['items'], brain=True, store=store)
    chips = chips_for(store, item) or walk_chips(len(p['items']))
    rec('assistant', reply + (f"\nOPTIONS: {' | '.join(options)}" if options else ''))
    return {'say': reply, 'options': options, 'chips': chips, 'decision': None}


def act(store, key: str, verb: str, actor: str = 'owner', llm=None, hours: float = None) -> dict:
    """The pile's own verbs: done / later / skip / ack, and Not ours on an Advisor idea (dismiss). Everything
    else - a task, an agent, a draft - is the proposal road every card button takes."""
    if verb in ('done', 'later', 'skip', 'ack'): return funnel.settle(store, key, verb, actor, hours)
    if verb != 'dismiss': raise ValueError(f'unknown verb: {verb}')
    item = funnel.next_item(store, key) or {}
    if item.get('idea'):
        from . import assistant
        assistant.act(store, item['idea'], 'dismiss', actor)
    return funnel.settle(store, key, 'done', actor, note='dismissed')

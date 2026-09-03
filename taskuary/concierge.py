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
import json, re
from datetime import datetime, timedelta
from loguru import logger

from . import funnel, general, llm as llm_mod
from .assistant import _ts
from .store import task_ref

MAX_TOKENS, TURNS, FACT_CHARS = 380, 10, 1_600
# Introducing an item is a FACT - who wrote, what was done, what you need to do - and the pipe knows all
# three. So 'next' asks no model: it is instant, and it can never describe the wrong item (the owner,
# 2026-09-03: "should not even be an AI call, just go to next task"). The model speaks only when the
# owner types something that is not already a decision. Flip this for a model-written introduction.
INTRO_AI = False
MARK = '<!-- tq:card '
_MARK = re.compile(r'\s*<!-- tq:card (\{.*?\}) -->\s*$', re.S)
_OPTIONS = re.compile(r'\n?\s*OPTIONS:\s*(.+?)\s*$', re.I | re.S)
_DECIDE = re.compile(r'\n?\s*DECIDE:\s*([a-z_]+)(?::\s*(.*?))?\s*$', re.I | re.S)
# what the owner can decide about the thing on the table - each is a button the card already has
VERBS = ('reply', 'approve', 'setting', 'not_ours', 'not_ours_remember', 'not_ours_sender', 'remember', 'coder', 'mine', 'close', 'stop_agent',
         'rerun', 'setup', 'clear', 'split', 'done', 'later', 'skip', 'next', 'answer_agent', 'redraft', 'forward', 'archive', 'none')
class _SwitchRx:
    """_SAYS holds (regex, verb) pairs; the switch table is several regexes, so this stands in for
    them and answers the same .search()."""
    def search(self, text):
        changes, _ = switch_ask(text)
        return changes and re.match(r'.*', text or '', re.S) or None


SWITCH_RX = _SwitchRx()

_SAYS = (
    # a switch the owner named in words: proposed, never applied here (proposals.SETTING_ALLOW)
    (SWITCH_RX, 'setting'),
    # the sender is the problem: a SENDER-scoped verdict, so everything from them files itself from now on
    (re.compile(r"\b((this |that |the )?sender (is|are) (garbage|junk|spam|noise|a waste)|block (this |that |the )?sender|never (again )?from (him|her|them|this sender)|(remember|note) (that )?(this |that )?sender)\b", re.I), 'not_ours_sender'),
    # approving IS a word too: the drafted reply goes, as drafted
    (re.compile(r"^\s*(approve|approved|send it(?!\s+to)|send the (reply|draft)|go ahead and send|yes,? send|looks good,? send|ship it)\b", re.I), 'approve'),
    # a fact for memory, in the owner's words
    (re.compile(r"^\s*(remember|memorize|note)( that|:)?\s+(?P<note>.+)$", re.I | re.S), 'remember'),
    # ANSWERING the agent is not replying to the sender: "tell the agent yes" used to draft an EMAIL
    # carrying "the agent: yes" (2026-09-03). It reads before `reply`, whose first word is `answer`.
    (re.compile(r"\b(?:answer|tell|reply to|respond to|say to)\s+(?:the\s+)?(?:agent|coder|codex|claude|session|terminal)\b\s*[:,]?\s*(?P<ans>.*)$", re.I | re.S), 'answer_agent'),
    # the draft is there but wrong: the model used to CLAIM it had rewritten it and the next approve
    # sent the untouched one (2026-09-03). A redraft is a real road - the drafter writes it again.
    (re.compile(r"\b(re-?write|redraft|reword|rephrase|shorten|tighten|lengthen|soften) (it|this|that|the (reply|draft|answer))?\b"
                r"|\bmake (it|the (reply|draft|answer)) (shorter|longer|warmer|friendlier|firmer|softer|nicer|blunter|more \w+|less \w+)\b"
                r"|\b(add|mention|include)\b[^.?!]{0,60}\b(to|in) the (draft|reply)\b", re.I), 'redraft'),
    # somebody ELSE should have this: it goes to them, and the owner is out of it
    (re.compile(r"\b(forward|pass|hand) (it|this|that) (on )?to (?!the (coder|coding|agent|codex|claude|assistant))(?P<who>[\w.@'-]+)"
                r"|\b(assign|give|hand) (it|this|that) to (?!the (coder|coding|agent|codex|claude|assistant))(?P<who2>[\w.@'-]+)"
                r"|\bask (?!the |an |them |him |her |me |assistant|agent|coder|codex|claude|ai )(?P<who3>[\w.@'-]+) to (handle|take|deal|sort|own)\b"
                r"|\bloop in (?P<who4>[\w.@'-]+)", re.I), 'forward'),
    # A REPLY comes before not-ours: "let them know we will fix it by Friday", "tell them to ignore
    # it", "reply: not ours, sorry" all used to match not_ours first - filed, task deleted (2026-09-03).
    # ...and never about the AGENT: "ask assistant to look into that server" is a hand-off, and the
    # coder rule below owns it - the target here is a PERSON (2026-09-03)
    (re.compile(r"^\s*(reply|respond|answer|tell (them|him|her|(?!assistant|agent|coder|codex|claude|ai)[\w'-]+)|say|write back|draft)\b"
                r"|\b(tell|let|remind|ask) (them|him|her|(?!assistant|agent|coder|codex|claude|ai)[\w'-]+) (know|that|to|we|i|it|about)\b", re.I), 'reply'),
    (re.compile(r"\b(not (my|our) (issue|problem|job|task|thing)|not (ours|mine)|nothing to do with (me|us)|let them (handle|deal|sort|do)"
                r"|ignore (it|this)|leave it (alone|be)|drop it|no need to (respond|reply|answer))\b", re.I), 'not_ours'),
    (re.compile(r"\b(never|always) (again|file|ignore)|remember (this|that)|from now on\b", re.I), 'not_ours_remember'),
    (re.compile(r"\b(send (it |this |that )?to (the )?(coding agent|coder|codex|claude|gemini|agent)|have the (coder|agent)|let the (coder|agent)|start the (coder|agent)|code it|(coder|codex|claude) (should|can) (review|look|fix|handle)"
                r"|look into|investigate|dig into|find out|figure out|research|check (on |out )?(that|the|this|what|why|if)|ask (the |an )?(assistant|agent|coder) to)\b", re.I), 'coder'),
    (re.compile(r"\b(i'?ll (do|take|handle) (it|this|that)|i will (do|take|handle) (it|this|that)|mine|leave it (to|with) me|(just )?make it a task|create a task|(add|put) (it|this) (on|to) my list)\b", re.I), 'mine'),
    # ENDING AN AGENT is not closing a task: "close the agent working" closed the item on the table
    # instead - a task the owner had not even asked about (2026-09-03). It comes first, so the words
    # that name the agent can never be read as the words that name the task.
    (re.compile(r"\b((close|stop|kill|end|shut) (it |the |this |that )?(agent|coder|codex|claude|session|terminal)"
                r"|(close|shut) (it |the |that )?down|stop (it |the |that )?working|(agent|coder) is (done|finished)"
                r"|wrap (it |this |that )?up)\b", re.I), 'stop_agent'),
    (re.compile(r"\b(close (the |this |that )?task|close it|mark (it |this )?(as )?(done|closed|complete)|task is done)\b", re.I), 'close'),
    (re.compile(r"\b(re-?run|run (it |this |that )?again|try (it )?again|kick it off again)\b", re.I), 'rerun'),
    # two jobs in one arrival - the drawer could split them, the chat could not (2026-09-03)
    (re.compile(r"\b(split (it|this|that|them|the task)?|these are (two|2|separate|different)|"
                r"(that'?s|thats|it'?s) (two|2) (things|jobs|asks|tasks)|(two|2) (different|separate) (things|jobs|asks|tasks))\b", re.I), 'split'),
    # a sweep: "remove all the Nechama Ozur reports", "skip all the mfa financial reports", "remove them
    # from the pipeline", "same for all resident refunds" - marked read, never deleted. The target may be
    # a pronoun: what "them" means is the last thing the owner named (the owner, 2026-09-03: two tries,
    # both answered with a promise and no sweep).
    # ONE of them, out of the way: read and off the pipe, the task archived, never deleted. It comes
    # before the sweep because "delete it"/"archive it" are about the thing on the table, not a rule.
    (re.compile(r"^\s*(delete|archive|bin|trash|file|get rid of|throw away) (it|this|that|the (message|mail|email|thing))\b", re.I), 'archive'),
    (re.compile(r"^(?=.*\b(remove|clear|dismiss|get rid of|hide|skip|ignore|archive|filter|mark (all )?(as )?read)\b)"
                # a short verb needs a PLURAL target: "skip it" is one item, and sweeping the pipe on
                # it swept nothing and moved nothing (2026-09-03) - 'it' belongs to skip/archive
                r"(?=.*\b(all|every|these|those|any|them)\b)"
                r"|\b((stop|no more) (showing|surfacing|sending)|don'?t (show|surface|need|want)|no need for)\b"  # these say it on their own
                # ...and the way an owner actually says it: "should not show up anymore", "never show me those"
                r"|\b((should ?n'?t|should not|do ?n'?t|never|stop) (show|showing|surface|surfacing|see|seeing|appear|appearing)|not show up)\b"
                r"|^\s*(same for|no more)\b", re.I | re.S), 'clear'),
    # something new to configure. A workflow is included explicitly so "set up monthly invoices"
    # opens the Assistant walkthrough instead of being treated as loose conversation.
    (re.compile(r"^\s*(please )?(set ?up|create|build|make|add|configure|automate)\b.*\b(report|workflow|connection|connector|dashboard|automation|schedule|integration|pipeline|alert|invoice)s?\b", re.I | re.S), 'setup'),
    (re.compile(r"^\s*(done|handled|dealt with|finished|ok done)\b|\b(it was|already|i|we) (responded|replied|answered|handled|took care|dealt)\b"
                r"|\b(i|we) did (it|this|that)\b|\b(it'?s|that'?s|thats) (handled|done|sorted|dealt with|taken care of)\b", re.I), 'done'),
    # tomorrow comes first: "remind me tomorrow" meant 07:00 to the owner and three hours to the
    # `later` rule, which read "remind me" and stopped there (2026-09-03)
    (re.compile(r"^\s*(tomorrow|skip)\b|\btomorrow( morning)?\b|\bfirst thing\b", re.I), 'skip'),
    (re.compile(r"^\s*(later|not now|remind me|snooze( it| this| that)?|come back to (it|this))\b|\bsnooze\b", re.I), 'later'),
    (re.compile(r"^\s*(next|move on|go on|continue|ok next)\b|\bnext\s*[.!]?\s*$", re.I), 'next'),
)

SYSTEM = (
    "{counsel}\n\n"
    "THE CONTRACT (code reads your answer)\n"
    "You are speaking to {owner} in the chat on the Assistant tab. ONE item per turn: say who, what they want, and "
    "what you would do - under 60 words, first person, plain. The card under your message holds the draft, the "
    "agent's question or the meeting, and its buttons do the acting; point at them, never claim an action "
    "happened. When a decision has two to four clear choices and no button covers them, end with one final line "
    "exactly like: OPTIONS: first choice | second choice. Otherwise no options line.\n"
    "When the owner's words are a DECISION about the item on the table, do not advise - carry it out: answer in one "
    "short sentence saying what happens now, then end with one final line exactly like DECIDE: <verb> where verb is "
    "one of reply (they want a reply written - add the gist after a colon: DECIDE: reply: tell Kishan it is not owned "
    "here), not_ours (not their problem, file it this once), not_ours_remember (never again for this kind), coder "
    "(hand it to the coding agent - put EVERYTHING the owner wants done after a colon, in their words: DECIDE: coder: find out "
    "why the bulk-approve fix from before did not stick, and create an admin login for X), mine (they will do it themselves), "
    "approve (send the drafted reply as it stands), not_ours_sender (the SENDER is noise - file everything from them from now on), "
    "split (this arrival is TWO jobs - Taskuary breaks it in two, each with its own ref), "
    "setting (what they want is a SWITCH - Taskuary puts it in front of them to approve and never changes it itself), "
    "stop_agent (end the AGENT that is running - stopping a session is not closing a task, and never guess which: "
    "only the task they named, the one on the table if an agent is on it, or the only agent running), "
    "remember (a fact to keep - the fact after a colon), close (close the task itself), rerun (run a report again - Taskuary queues it), done (handled - also when they say it was already "
    "answered or dealt with), later, skip (tomorrow), next (move on). Never ask which of these they mean when the words say it; never "
    "ask a question instead of deciding. You have NO tools and run nothing yourself - ever: you load, you orchestrate, Taskuary does. "
    "When the owner says a fact of yours is WRONG, take the correction: say what it actually is, and what "
    "that changes. Never answer a correction by moving on (no next, skip, later or done) - being told you "
    "have it wrong is the one thing you must not shrug off.\n"
    "A question or a remark is not a decision: answer it and write no DECIDE line. A polite request is "
    "not a question: \"can you look into that server\" is a hand-off, so decide it.\n"
    "The thread you are given is the whole thread, the owner's own sent mail included. When it shows they "
    "already answered, say so as a fact. Only when the thread has no answer from them may you say the mail "
    "has not been read back yet - and then name the Sync button, never blame yourself for not seeing it.")

OPENING = (
    "Open the conversation for the day. Say 'let's go through what we have today' in your own words, then in two or three "
    "sentences: what is on the calendar, what agents have in hand, how much is waiting and of what kind (from THE DAY below). "
    "Do not walk through any item yet - the owner starts that with a button. Under 90 words. No options line.")

# what the assistant says when a decision is carried out - the fact of what happens now, never a claim
RECEIPTS = {'reply': "I'll draft that - it lands below for your yes.", 'approve': 'Sending it as drafted. Moving on.',
            'not_ours': "Not ours, then - filed. Moving on.", 'not_ours_remember': "Filed, and remembered: this kind goes straight past you from now on.",
            'not_ours_sender': "Noted: that sender is noise - everything from them files itself from now on. Moving on.",
            'remember': "Remembered. Moving on.", 'coder': "Sent off to the coding agent - watch it on the Board if you like; I'll bring its findings back here when it's done. Meanwhile, the next thing.",
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
    """COUNSEL.md - who the assistant is and how it speaks (Docs tab, the owner's to edit)."""
    doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()
    return doc[:3200] or ('You are Taskuary, the assistant. You walk the owner through their inbox one thing at a time '
                          'and do no work yourself. Plain, direct, first person. Take a position.')


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
    if item.get('mid'):
        m = store.get_message(item['mid']) or {}
        from .triage import strip_boilerplate
        body = strip_boilerplate(str(m.get('BodyText') or item.get('preview') or ''))
        if body: lines.append(f"what they wrote:\n{_cut(body, 400 if item['kind'] == 'report' else FACT_CHARS)}")   # a report's body is for the button, not the intro
        sent = store.sent_reply(message_id=item['mid']) if not item.get('tid') else None
        if sent: lines.append(f"YOU ALREADY REPLIED ({str(sent.get('DecidedAt') or sent.get('CreatedAt') or '')[:16]}): {_cut(sent.get('FinalText') or sent.get('DraftText'), 240)}")
        try:
            chain = store.thread_messages(conversation_id=m.get('ConversationId'), subject=m.get('Subject'), limit=8) if m.get('ConversationId') else []
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
        mine = [c for c in chain if _own_word(c)]
        if mine:
            lines.append(f"YOU ALREADY ANSWERED ON THIS THREAD ({str(mine[-1].get('SentAt') or '')[:16]}, from your own mail client): "
                         f"{_cut(mine[-1].get('BodyText'), 240)} - say so as a fact; never say you cannot see the owner's reply")
    if item.get('summary') and item['kind'] in ('review', 'action'): lines.append(f"THE AGENT FOUND: {item['summary']}")
    if item.get('rid'):
        rv = store.get_review(item['rid']) or {}
        d = str(rv.get('DraftText') or '').strip()
        lines.append(f"THE DRAFT (shown to the owner in the card):\n{_cut(d, 1200)}" if d else 'no draft yet - the card offers Draft with AI')
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


def parse_decision(text: str) -> tuple[str, dict | None]:
    """The model's DECIDE line, off the end of its answer: {'verb', 'text'} or None."""
    m = _DECIDE.search(text or '')
    if not m: return (text or '').strip(), None
    verb = m.group(1).lower()
    if verb not in VERBS or verb == 'none': return text[:m.start()].strip(), None
    return text[:m.start()].strip(), {'verb': verb, 'text': (m.group(2) or '').strip()}


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


# the owner is HOLDING something open - the opposite of the verb the sentence is built from.
# "don't ignore this one", "leave it open", "leave it with the agent" all matched not_ours, which
# files the message and deletes its task (2026-09-03). Read before anything else, decide nothing.
_HOLD = re.compile(r"\b(leave|keep) (it|this|that|them|him|her) (open|running|as is|alone with|where it is|with (the )?(agent|coder|codex|claude))\b"
                   r"|\b(leave|keep) it (to|with) (the )?(agent|coder|codex|claude)\b"
                   r"|\bdo ?n'?t (ignore|file|close|drop|delete|archive|skip|remove|clear|touch|send)\b"
                   r"|\b(this|that|it) one (does|is) matter\b", re.I)
# a question about STATE wearing a polite opener: "can you check if the report ran?" is a question,
# not a hand-off - it started a coding agent on the mail (2026-09-03)
_ASKING = re.compile(r"\b(check|see|find out|know|tell me|confirm|remember) (if|whether)\b[^?]*\?\s*$", re.I | re.S)
# saying yes: what it means is whatever the card's own button does, so the verb is resolved
# against the item on the table (assent_verb) and never guessed here
_ASSENT = re.compile(r"^\s*(yes|yeah|yep|yup|ok|okay|sure|fine|alright|go ahead|do it|please do|sounds good|👍)\b[\s,.!:-]*(?P<tail>.*)$", re.I | re.S)
_REMEMBER_TOO = re.compile(r"[,;]?\s+and (also )?remember (that |to )?(?P<note>.+)$", re.I | re.S)
_REMEMBER_TO = re.compile(r"^\s*(remember|note|remind me) to\s+(?P<rest>.+)$", re.I | re.S)
# what the card's primary button does, said as a word. Anything not here has no yes-able action.
ASSENT_VERB = {'review': 'approve', 'action': 'approve', 'agent': 'answer_agent', 'idea': 'followup'}


def assent_verb(item: dict | None) -> str | None:
    """"yes" / "go ahead" on the thing on the table: the verb its own card would run."""
    if not item: return None
    if item.get('kind') == 'review' and not item.get('draft'): return 'reply'   # nothing drafted yet: write one
    return ASSENT_VERB.get(item.get('kind'))


def _subject_left(ask: str) -> str:
    """What is left of the sentence once EVERY verb phrase Taskuary knows is taken out of it: the
    subject the owner named, if they named one. Taking out only the winning phrase left the other
    half of "let them sort it out" looking like a named subject (2026-09-03)."""
    out = ask
    for rx, _ in _SAYS:
        if rx is SWITCH_RX: continue
        for m in rx.finditer(out):
            if m.end() > m.start(): out = out[:m.start()] + ' ' * (m.end() - m.start()) + out[m.end():]
    return out.strip()


def decide_words(text: str) -> dict | None:
    """No model, or a model that missed it: the plain phrases an owner uses at their desk."""
    s = str(text or '').strip()
    if _CORRECTION.search(s): return None                        # they are correcting us - answer it, decide nothing
    if _HOLD.search(s) or _ASKING.search(s): return None         # they are holding it open, or asking - not deciding
    ask = _POLITE.sub('', s)                                     # the instruction under the politeness
    if '?' in s and ask == s: return None                        # a real question, anywhere in the words - the model answers it, nothing is decided
    # "remember to reply to him" is not a fact to keep, it is the reply - it used to become a memory row
    to = _REMEMBER_TO.match(ask)
    if to: return decide_words(to.group('rest'))
    # "approve and remember that Kishan handles refunds": both, not one - the memory used to be dropped
    also = _REMEMBER_TOO.search(ask)
    if also:
        head = decide_words(ask[:also.start()])
        if head and head['verb'] != 'remember': return {**head, 'remember': also.group('note').strip(' :,-.')}
    yes = _ASSENT.match(ask)
    if yes:
        tail = (yes.group('tail') or '').strip(' ,.!')
        inner = decide_words(tail) if tail else None
        # a sweep is never what "yes" meant: "yes remove them" is an ANSWER to the agent that asked
        if inner and inner['verb'] != 'clear': return inner
        return {'verb': 'assent', 'text': s}
    for rx, verb in _SAYS:
        m = rx.search(ask)
        if m:
            # a reply carries what to say; a hand-off to the coder carries the WHOLE ask; a memory carries the fact
            if verb == 'remember': return {'verb': verb, 'text': m.group('note').strip(' :,-.')}
            if verb in ('setup', 'clear'): return {'verb': verb, 'text': s}
            if verb == 'answer_agent': return {'verb': verb, 'text': (m.group('ans') or '').strip(' :,-.') or s}
            if verb == 'forward': return {'verb': verb, 'text': s, 'who': next((v for k, v in m.groupdict().items() if k.startswith('who') and v), '')}
            # the instruction is the tail when they opened with the verb ("reply: say Tuesday works"),
            # and the whole sentence when the verb is inside it ("let them know we ship Friday")
            rest = ask[m.end():].strip(' :,-.') if m.start() == 0 else ''
            if len(rest.split()) < 3: rest = ''                  # "reply to him" is not an instruction; the sentence is
            return {'verb': verb, 'text': (rest or s) if verb == 'reply' else s if verb in ('coder', 'redraft') else '',
                    'said': s, 'rest': _subject_left(ask)}
    return None


# A decision acts on the thing on the table. When the sentence NAMES another subject it must not:
# "not ours, facilities handles the portal" (meaning the Teams outage) filed Chana's export reply
# and deleted TQ-0002 with its coder report, its commit and its drafted answer (2026-09-03).
GUARDED = ('not_ours', 'not_ours_remember', 'not_ours_sender', 'close', 'done', 'archive', 'approve', 'mine', 'rerun', 'redraft', 'coder')
# ...and of those, the ones that cannot be taken back: a mail sent, a message filed, a task closed.
# One stray word they cannot place is enough to stop and ask - "approve the invoice one" must never
# send the draft that happens to be on the table.
COSTLY = ('not_ours', 'not_ours_remember', 'not_ours_sender', 'close', 'done', 'archive', 'approve')
# courtesy and filler carry no subject: "done, thanks" names nothing
_FILLER = {'thanks', 'thank', 'cheers', 'great', 'good', 'fine', 'perfect', 'please', 'sorry', 'nice',
           'right', 'sure', 'really', 'actually', 'maybe', 'probably', 'definitely', 'anyway', 'though',
           # ...and the words that stand IN for a subject rather than being one: "for this kind",
           # "that sort of thing" name nothing at all
           'kind', 'kinds', 'sort', 'sorts', 'type', 'types', 'thing', 'things', 'stuff', 'item', 'items',
           'way', 'ways', 'case', 'cases', 'matter', 'work', 'job', 'jobs', 'note', 'notes', 'task', 'tasks',
           'message', 'messages', 'mail', 'email', 'emails', 'reply', 'replies', 'issue', 'issues', 'problem', 'problems'}

# pointing at something else on purpose: "the invoice one", "that other thread", "the payroll mail"
_OTHER_ONE = re.compile(r"\bthe [\w-]+ one\b|\bthat other\b|\bthe other (one|thread|mail)\b"
                        r"|\b(the|that) [\w-]+ (thread|mail|email|message|ticket|report|outage|invoice)\b", re.I)
# a thing, named: a determiner and the words after it ("the badge printer contract", "that refund")
_NAMED_THING = re.compile(r"\b(?:the|that|this|those|their)\s+[\w-]{3,}(?:\s+[\w-]{3,})?", re.I)

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


def _world_words(store, item: dict) -> set:
    """Every word the REST of the world is called by - the pile and the recent timeline, minus what
    this item is called. A leftover word that appears in it is a subject; one that appears nowhere
    is the owner talking ("so let them respond if they still need it")."""
    from .routing import tokens
    out = set()
    try:
        for i in funnel.pile(store)['items']:
            if i.get('key') == item.get('key'): continue
            out |= set(tokens(f"{i.get('who') or ''} {i.get('title') or ''}"))
    except Exception: pass
    try:
        for r in store.feed(limit=120, days=14):
            if r.get('MessageId') and r.get('MessageId') == item.get('mid'): continue
            out |= set(tokens(f"{r.get('FromName') or ''} {r.get('Subject') or ''} {r.get('SourceName') or ''}"))
    except Exception: pass
    from .routing import tokens as tk
    return out - set(tk(f"{item.get('who') or ''} {item.get('title') or ''}"))


def named_elsewhere(store, words: dict, item: dict | None, costly: bool = False) -> str | None:
    """The subject the owner's words name when it is NOT the one on the table: the pile key it
    resolves to, '?' when they name something that cannot be found, None when they name nothing else."""
    if not item or not words: return None
    said, rest = str(words.get('said') or ''), str(words.get('rest') or '')
    ref = re.search(r'\bTQ-?0*(\d+)\b', said, re.I)
    if ref and item.get('tid') and int(ref.group(1)) != int(item['tid']):
        return f"task:{int(ref.group(1))}" if store.get_task(int(ref.group(1))) else '?'
    from .routing import tokens
    own = set(tokens(f"{item.get('who') or ''} {item.get('title') or ''} {item.get('preview') or ''} {item.get('summary') or ''}"))
    extra = [w for w in tokens(rest) if w not in _CUES and w not in _FILLER and w not in own and len(w) > 2]
    if not extra: return None                          # the sentence is the verb and nothing else: it means this one
    # ONE stray word is not enough to stop on - but it is enough to look with: "approve the invoice
    # one" must not approve the playbook proposal that happens to be open. Two or more and we ask
    # rather than guess, because by then the sentence is plainly about something else.
    hit = lookup(store, ' '.join(extra)) or _pile_hit(store, extra, item)
    if hit: return hit if hit != item.get('key') else None
    # nothing resolved. "the invoice one" points at another thing on purpose, so stop and ask; a
    # word the rest of the world is also called by is a subject; anything else is just talk.
    if _OTHER_ONE.search(said): return '?'
    if not costly: return None
    if any(w in _world_words(store, item) for w in extra): return '?'     # a word the rest of the world answers to
    # ...or a thing NAMED and not held here at all: "the badge printer contract is legal's". A
    # determiner in front of it is what makes it a thing rather than more of the sentence.
    named = {w for m in _NAMED_THING.finditer(rest) for w in tokens(m.group(0))}
    return '?' if named & set(extra) else None


# What a card must HAVE for a verb to be carried out on it - the same map the page checks. The
# receipt used to go out before anyone knew, so "Sending it as drafted. Moving on." and "I could
# not do that from here" landed in the chat one after the other (2026-09-03).
NEEDS = {'reply': 'mid', 'approve': 'rid', 'redraft': 'rid', 'not_ours': 'mid', 'not_ours_remember': 'mid',
         'not_ours_sender': 'mid', 'coder': 'mid', 'mine': 'mid', 'forward': 'mid', 'archive': 'mid',
         'rerun': 'source_id', 'close': 'tid', 'answer_agent': 'tid', 'split': 'key'}
SAYS_VERB = {'approve': 'approve', 'redraft': 'redraft', 'not_ours': 'file', 'not_ours_remember': 'file',
             'not_ours_sender': 'file', 'coder': 'hand to an agent', 'mine': 'put on your list', 'forward': 'forward',
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


def parse_options(text: str) -> tuple[str, list]:
    m = _OPTIONS.search(text or '')
    if not m: return (text or '').strip(), []
    opts = [o.strip() for o in re.split(r'\s*\|\s*', m.group(1)) if o.strip()][:4]
    return (text[:m.start()].strip(), opts if len(opts) >= 2 else [])


def fallback(item: dict | None, opening: bool) -> str:
    """No model: the facts in the same three beats - where from, what was done, what you need to do."""
    if not item: return ALL_DONE if opening else 'No AI is connected, so I can only show you the pipe. Add one under Connections → AI.'
    if opening and item.get('mid') and item['kind'] in ('review', 'action', 'asked', 'todo', 'fyi'):
        frm = f"{item.get('who') or 'Someone'} wrote on {item.get('channel') or 'email'}" + (f" ({funnel_age(item)})" if funnel_age(item) else '') + f": \"{item['title']}\""
        done = (f"the agent {item['summary']}" if item.get('summary') else
                'triage judged it a reply to write' if item['kind'] == 'review' else 'an agent proposed an action' if item['kind'] == 'action' else
                'a coding task with no agent on it yet' if item.get('coding') else 'nothing has been done with it yet' if item['kind'] in ('asked', 'todo') else 'triage filed it as fyi')
        need = ('approve the draft below, or redraft it' if item['kind'] == 'review' else 'say whether it may run' if item['kind'] == 'action' else
                'reply, hand it to the coding agent, or say it is not ours' if item['kind'] in ('asked', 'todo') else 'nothing - read it if you like')
        return f"{frm}. Since then: {done}. From you: {need}."
    if item['kind'] == 'agent':
        return f"{item.get('agent') or 'An agent'} on {item.get('ref') or item['title']} " + (f"asked: {item['tail'][-1]}" if item.get('asking') and item.get('tail') else 'stopped at its prompt') + ' - answer it below.'
    if item['kind'] == 'wrapup':
        return f"{item.get('ref') or item['title']}: the reply went out" + (f" and the agent finished ({item['summary']})" if item.get('summary') else '') + '. The task is still open - close it?'
    if item['kind'] == 'idea':
        return f"{item['title']}" + (f" ({item.get('who')})" if item.get('who') else '') + f" - {item.get('why') or 'the assistant raised this'}. Draft the follow-up, make it a task, or let it go."
    if item['kind'] == 'meeting': return f"{item['title']} is {item.get('why')}. Prep me, or move on."
    if item['kind'] == 'report':
        return f"{item['title']} landed {funnel_age(item)}" + (' and FAILED - the cause is in it.' if item.get('bad') else '.') + ' Read it with the button, or move on.'
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
    # never the tools block: the assistant runs nothing (the owner, 2026-09-03: "should never run anything ever -
    # just load and orchestrate"). A rerun, a hand-off, a close are decisions Taskuary carries out.
    return SYSTEM.format(owner=_owner(store), counsel=_counsel(store))


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


def _ask(store, llm, tid: int, item: dict | None, instruction: str, pile_items: list) -> tuple[str, list]:
    # the item comes FIRST and is named as the only subject; the pile is counts only while one is on the table
    user = ((f"THE ITEM ON THE TABLE - speak only about this one:\n{facts(store, item)}\n\n" if item else '')
            + f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(pile_items, coming=item is None)}{_urgent_line(pile_items, item)}\n\n"
            + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
            + (f"{facts(store, item)}\n\n" if not item else '') + instruction)
    text = str(llm(_system(store, llm), user, max_tokens=MAX_TOKENS) or '').strip()
    say, options = parse_options(text)
    if off_subject(say, item):
        logger.info(f"concierge: the model spoke about another task than {item.get('ref')} - using the facts instead")
        return '', []
    return say, options


def record(store, tid: int, role: str, text: str, card: dict = None):
    body = text.strip() + (f"\n\n{MARK}{json.dumps(card, default=str)} -->" if card else '')
    store.add_comment(tid, 'owner' if role == 'user' else 'assistant', general.USER_TYPE if role == 'user' else general.ASSISTANT_TYPE, body)


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
        out.append({'id': c['CommentId'], 'role': 'assistant' if c.get('ActorType') == general.ASSISTANT_TYPE else 'user',
                    'text': text, 'options': options, 'card': card, 'at': c.get('CreatedAt')})
    return out


CHATS_KEPT_DAYS = 20          # a transcript older than this is nobody's memory - the list stays readable

def chats(store, actor: str = 'owner') -> list:
    """Every conversation the guide has had, newest first: what it was about, when it ran, how long it
    lasted, how much of the pipe it got through, and which is open.

    A walk with nothing typed into it used to read "Walkthrough · 2026-09-03" three times over, with
    nothing to tell them apart (the owner, 2026-09-03: "Past chats don't really make sense... we need
    to add time to it, and how many emails processed so you can see past transacript"). So an untyped
    walk is named by its clock and counted by the items it actually put on the table, and anything
    past CHATS_KEPT_DAYS is dropped on the way past."""
    cut = (datetime.now() - timedelta(days=CHATS_KEPT_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for t in store.dock_tasks(general.DOCK_TAG):
        rows = general.chat_rows(store, t['TaskId'])
        last = str((rows[-1]['CreatedAt'] if rows else t.get('CreatedAt')) or '')
        if last and last < cut:
            store.update_task(t['TaskId'], {'Status': 'dropped'}, actor)      # off the list; the task itself is history
            continue
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


def lookup(store, text: str, days: int = 14) -> str | None:
    """The pile item, or Timeline row, the owner's words point at - "what did Dana send", "the invoice
    thread". Sender and subject words only (a body matches everything), most of the meaningful words
    must hit, and the newest wins a tie. None when nothing is clearly meant."""
    from .routing import tokens
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
    return brain(store, trace=trace, cancel=cancel, resume=_sid(store, tid) or None, fast=True)


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
    card = {'key': 'brief', 'kind': 'brief', 'lane': 'report', 'title': 'Today', 'n': len(p['items']),
            'mail': sum(1 for i in p['items'] if i['kind'] in funnel.MAIL_KINDS)}
    record(store, tid, 'assistant', say, card)
    return {'say': say, 'card': card, 'opened': True}


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


def _rules_from(swept: list) -> list:
    """One rule per sender, carrying the words that hit THEIR mail: [{'sender', 'words'}]. A sender
    who was swept on their name alone gets a rule about them; everyone else needs their subject
    words, so a rule can never quietly grow into "everything from this person"."""
    by = {}
    for x in swept:
        key = x['email'] or (x['who'] or '').lower()
        if not key: continue
        by.setdefault(key, set()).update(x['words'])
    out = []
    for key, words in by.items():
        subject = sorted(w for w in words if not any(w in part for part in re.split(r'[@.\s]+', key)))
        out.append({'sender': key, 'words': subject or sorted(words)})
    return out


def _rule_words(rule: dict) -> str:
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
    hit, titles, mids, swept = 0, [], [], []
    for i in funnel.build(store, keep_surfaced=True)['items']:
        if i['lane'] in ('blocked', 'working'): continue                                   # an agent's question is never swept
        hay = set(tokens(f"{i.get('who') or ''} {i.get('email') or ''} {i.get('title') or ''}"))
        who = set(tokens(f"{i.get('who') or ''} {i.get('email') or ''}"))
        n = funnel.like(words, hay)
        if not n or (n < 2 and not funnel.like(words, who)): continue                      # the sender alone, or two words of the subject
        funnel.settle(store, i['key'], 'done', actor, note='swept by the owner'); hit += 1
        titles.append(i['title']); mids.append(i.get('mid'))
        swept.append({'email': (i.get('email') or '').lower(), 'who': i.get('who') or '',
                      'words': [w for w in words if funnel.like([w], hay)]})
    return hit, titles, mids, swept


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


def _carry_out(store, tid: int, text: str, words: dict, item0: dict | None, actor: str) -> dict:
    """The decisions Taskuary makes good on itself - a sweep of the pipe, a hand-off that becomes a
    task, a set-up - so the receipt is the fact rather than an instruction to a page."""
    if words['verb'] == 'clear':
        out = clear_matching(store, text, actor, hint=_last_owner_words(store, tid, text))
        if out['cleared']:
            say_ = (f"Cleared {out['cleared']} from the pipe - {', '.join(out['titles'][:3])}{'…' if out['cleared'] > 3 else ''}. "
                    'Read, not deleted; they are on the Timeline.'
                    + (f" And remembered as {'a rule' if len(out['rules']) == 1 else str(len(out['rules'])) + ' rules'}: "
                       + '; '.join(out['rules']) + ' - the next ones file themselves, and anything that actually asks you '
                       'something still reaches you.' if out.get('rules') else '')
                    + (' And that sender goes straight past you from now on.' if out.get('remember') and not out.get('rules') else ''))
        elif out.get('rules'):
            say_ = ('Nothing of those is in the pipe right now - but it is noted: ' + '; '.join(out['rules'])
                    + ' files itself from now on. They stay on the Timeline, and anything that actually asks you '
                      'something still reaches you.')
        else: say_ = 'Nothing in the pipe matches those words.'
        record(store, tid, 'assistant', say_ + ' Moving on.')
        return {'say': say_ + ' Moving on.', 'options': [], 'decision': {**words, 'cleared': out}}
    if words['verb'] == 'setting':
        changes, says = switch_ask(text)
        try: out = propose_switch(store, changes, says, text, actor)
        except Exception as e:
            logger.warning(f'concierge: the switch was not proposed - {e}')
            say_ = f"That is a setting - open Settings and I will leave it to you. ({e})"
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"That is a switch, not a note - so I have put it in front of you rather than touching it: "
                f"{says}. Approve it below and it changes; nothing changes until you do.")
        record(store, tid, 'assistant', say_, card=out['card'])
        return {'say': say_, 'options': [], 'decision': {'verb': 'setting', 'reviewId': out['reviewId'], 'changes': changes}}
    if words['verb'] == 'split':
        try: out = split_item(store, item0, text, actor)
        except Exception as e:
            logger.warning(f'concierge: the split did not happen - {e}')
            say_ = f"I could not split that one - open {(item0 or {}).get('ref') or 'the task'} and split it there."
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"Split: {out['ref']} keeps \"{out['kept']}\" and {out['newRef']} is \"{out['title']}\". "
                'Each is its own job now, so an agent sent at one only gets that one.'
                if out.get('newRef') else "There is only one ask in that one - nothing to split.")
        record(store, tid, 'assistant', say_)
        return {'say': say_, 'options': [], 'decision': {'verb': 'split', **out}}
    if words['verb'] == 'remember':
        note = (words.get('text') or '').strip()
        if not note:
            say_ = 'Remember what? Say the fact and I will keep it.'
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        mid_ = remember_fact(store, note, actor)
        # a memory is not a verdict about the thing on the table: it does not settle it, and the
        # receipt used to say "Moving on." while nothing moved at all (2026-09-03)
        say_ = (f"Remembered: {_cut(note, 200)}."
                + (f" {item0.get('ref') or 'The one on the table'} is still on the table." if item0 else ' What next?'))
        record(store, tid, 'assistant', say_)
        return {'say': say_, 'options': [], 'decision': {'verb': 'remembered', 'memoryId': mid_, 'note': note}}
    if words['verb'] == 'forward':
        try: out = forward_item(store, item0 or {}, words.get('who') or '', words.get('text') or '', actor)
        except Exception as e:
            say_ = f"I could not hand that over - {e}. Open the task and use Hand off, where you can pick the person and the channel."
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        say_ = (f"Written as a hand-off to {out['to']} - it is below for your yes, and nothing goes until you give it. "
                'Approving it sends the message and closes this one out here.')
        record(store, tid, 'assistant', say_, card=out['card'])
        return {'say': say_, 'options': [], 'decision': {'verb': 'forwarded', 'reviewId': out['reviewId'], 'to': out['to']}}
    if words['verb'] == 'stop_agent':
        end = _agent_task(store, item0, text)
        if not end:
            say_ = 'No agent is running right now - nothing to stop.'
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        wrap = bool(re.search(r"\b(wrap|finished|done|it'?s done)\b", text, re.I))
        if wrap:
            # a wrap needs a transcript to write the report FROM: without one the page 422'd
            # underneath "Wrapping TQ-0001 up..." (2026-09-03)
            from . import terminal as term
            try: has = bool((term.transcript_for(store, end) or ('',))[0].strip())
            except Exception: has = False
            if not has: wrap = False
        say_ = (f"Wrapping {task_ref(end)} up - the report goes on the task, the reply is drafted and it closes."
                if wrap else f"Stopping the agent on {task_ref(end)}. The task stays open - say close it when you want it closed."
                             + ('' if not re.search(r'\bwrap\b', text, re.I) else ' There is no transcript to write a report from yet, so there is nothing to wrap.'))
        record(store, tid, 'assistant', say_)
        return {'say': say_, 'options': [], 'decision': {'verb': 'stop_agent', 'taskId': end, 'ref': task_ref(end), 'wrap': wrap}}
    if words['verb'] == 'coder':                      # nothing on the table: their words ARE the brief
        try:
            made = setup_task(store, _handoff_brief(store, tid, text), actor, title=_handoff_title(store, tid, text), kind='coding')
            say_ = (f"{made['ref']} - \"{made['title']}\" is with the coding agent now. It comes back here when it is done, "
                    'or when it needs a fact from you.')
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': {'verb': 'created', 'taskId': made['taskId'], 'ref': made['ref'], 'title': made['title']}}
        except Exception as e:
            logger.warning(f'concierge: the hand-off did not start - {e}')
            say_ = "I could not start that here - open the Board and hand it to an agent."
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
    try:
        made = setup_task(store, text, actor)
        say_ = (f"{made['ref']} - \"{made['title']}\". Open it and I'll walk you through it step by step: it is a "
                'conversation with the assistant, not a coding job, so nothing is built and no repository is touched.')
        record(store, tid, 'assistant', say_)
        return {'say': say_, 'options': [], 'decision': {'verb': 'walkthrough', 'taskId': made['taskId'], 'ref': made['ref'], 'title': made['title']}}
    except Exception as e:
        logger.warning(f'concierge: the set-up did not open - {e}')
        record(store, tid, 'assistant', RECEIPTS['setup'])
        return {'say': RECEIPTS['setup'], 'options': [], 'decision': words}


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
    prop = reshape.propose_split(store, tid, brain(store, fast=True))
    if not prop.get('two') or not (prop.get('second') or {}).get('title'): return {'ref': task_ref(tid), 'kept': (store.get_task(tid) or {}).get('Title') or ''}
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
    mid = store.add_memory({'Scope': 'global', 'ScopeKey': None, 'Note': note.strip()[:1000],
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
    funnel.invalidate()
    return True


# What "set something up" opens. It used to be a CODING task on the default agent, which sent a coder
# into a checkout to build what the app already has: asked to set up the Zoho invoice integration -
# a connector card and a report, both shipped - it opened a session in the wrong repository entirely
# (the owner, 2026-09-03: "This was big mistake... it doesn't need coding agent just a regular agent
# that will walk me through it"). A set-up is a WALK-THROUGH: the conversational agent (general.py),
# no repository, no checkout, nothing built. Real building is a hand-off the owner asks for by name.
SETUP_KIND = 'general'

def setup_task(store, text: str, actor: str = 'owner', title: str = '', kind: str = SETUP_KIND) -> dict:
    """'Set up a report that...': a task with the owner's words in it, opened for the agent that can
    walk them through it. `kind` is 'general' for a walk-through and 'coding' for a hand-off the owner
    asked for (concierge's `coder` verb), which is the only path that starts an agent in a checkout."""
    from . import ingest
    text = str(text or '').strip()
    if not text: raise ValueError('say what to set up')
    title = (title or '').strip()[:120] or re.sub(r'^\s*(please )?(set ?up|create|build|make|add|configure|automate)\s+(a |an |me a |me an )?', '', text, flags=re.I).strip(' .')[:120] or text[:120]
    from . import browserview
    tid = store.create_task({'Title': title[:1].upper() + title[1:], 'Summary': text, 'Kind': kind, 'Status': 'open', 'Priority': 'normal',
                             'Source': 'assistant', 'SourceRef': 'assistant:setup',
                             # A walkthrough may have to log into a portal or point at the exact
                             # setting. Its Assistant session owns that browser; a coding handoff
                             # keeps the ordinary task controls instead.
                             'Tags': browserview.WANTS if kind == SETUP_KIND else ''}, actor)
    store.add_comment(tid, actor, 'human', f'Asked in the Assistant chat: {text}')
    store.audit('task', tid, 'create_from_assistant_setup', actor)
    if kind == 'coding':
        try: ingest._spawn(ingest._auto_code, store, tid)
        except Exception as e: logger.warning(f'setup task {tid}: the agent did not start - {e}')
    return {'taskId': tid, 'ref': task_ref(tid), 'title': title, 'kind': kind}


def card_for(item: dict) -> dict:
    """The card under the line - by kind, by code. The renderer draws it from these few fields
    and reloads the live facts (draft text, agent tail) from the item's ids."""
    return {k: item.get(k) for k in ('key', 'kind', 'lane', 'title', 'who', 'when', 'why', 'mid', 'tid', 'ref', 'rid', 'idea', 'coding', 'source_id', 'preview', 'sent',
                                      'idea_kind', 'agent', 'asking', 'tail', 'event', 'summary', 'bad', 'draft', 'channel', 'category', 'action', 'sid', 'mode')}


def surface(store, key: str = None, llm=None, actor: str = 'owner', only: str = None, trace=None, cancel=None) -> dict:
    """The next thing out of the pipe (or the one named; or the next piece of MAIL), said in one
    breath and marked as shown. Nothing left: says so."""
    task, _ = general.dock_task(store, actor)
    tid = task['TaskId']
    p = funnel.pile(store, force=True)
    item = funnel.next_item(store, key, only) or (funnel.item_for_key(store, key) if key else None)
    if not item:
        left = [i for i in p['items'] if not i.get('settling')]
        waiting = [i for i in left if i.get('surfaced') and i['lane'] != 'working']
        if key: say = "I can't find that one - it may be older than what I keep, or it went out under another subject."
        elif not only and waiting:
            say = (f"Nothing new. {len(waiting)} thing{'s' if len(waiting) != 1 else ''} I've shown you still wait{'s' if len(waiting) == 1 else ''} - "
                   + '; '.join(f"{i.get('who') + ' - ' if i.get('who') else ''}{i['title']} ({funnel.LANE_WORDS[i['lane']][0]})" for i in waiting[:3])
                   + '. Pick one from the pipe, or say later.')
        elif only and left:
            # the mail is done; what remains is the rest of the pipe - offer it rather than call the day over
            say = f"That's all the mail. {len(left)} other thing{'s' if len(left) != 1 else ''} still wait{'s' if len(left) == 1 else ''} - {funnel.summary(left).split(' - ', 1)[-1].split('.')[0]}. Say next and I'll take you through them."
        else: say = ALL_DONE
        record(store, tid, 'assistant', say)
        return {'item': None, 'say': say, 'options': [], 'left': len(p['items']), 'exhausted': only if (only and left) else None}
    # an agent has this one now (it started after the pile was built, or the owner just sent it): there is
    # nothing for the owner to do until it stops, so say so, let it go, and take the next one. It comes
    # back by itself - as the agent's question, its draft, or its finished job.
    if item['lane'] == 'working' or (item.get('working') and item['kind'] not in ('agent', 'review', 'action')):
        # it stays in the pipe, at the top, in hand - and comes to the front by itself when the agent stops
        who = item.get('working') or next((t.get('agent') or t.get('label') for t in _live(store) if t.get('taskId') == item['tid']), None) or 'the agent'
        say = f"{item.get('ref') or item['title']} is with {who} right now - nothing for you until it stops or asks. I'll bring it down then."
        record(store, tid, 'assistant', say + ('' if key else ' Moving on.'))
        return surface(store, None, llm, actor, only, trace, cancel) if not key else {'item': None, 'say': say, 'options': [], 'left': len(p['items'])}
    # fyi: nothing to do with any of them, so a handful comes out together - said in a breath, listed
    # in the card, one click to read any, one to let them all go
    if not key and item['lane'] == 'fyi':
        batch = funnel.fyi_batch(store, item)
        llm = _brain_for(store, tid, llm, trace, cancel, fast=True) if (llm is not None or INTRO_AI) else None
        say = ''
        if llm:
            try:
                fx = '\n'.join(f"- {i.get('who') or '?'}: \"{i['title']}\" - {i.get('preview') or ''}" for i in batch)
                user = (f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(p['items'])}\n\nFYI - {len(batch)} thing{'s' if len(batch) != 1 else ''} people told the owner, nothing to do with any of them:\n{fx}\n\n"
                        "Sum them up in one or two sentences - who said what, the gist - then ask whether the owner wants to dig into any. No options line.")
                say, _o = parse_options(str(llm(_system(store, llm), user, max_tokens=MAX_TOKENS) or '').strip())
                _remember_sid(store, tid, llm)
            except Exception as e: logger.warning(f'concierge: the fyi pass failed - {e}')
        if not say:
            say = (f"{len(batch)} thing{'s' if len(batch) != 1 else ''} people told you, nothing to do: "
                   + '; '.join(f"{i.get('who') or 'someone'} - {i['title']}" for i in batch) + '. Want to dig into any?')
        for i in batch: funnel.settle(store, i['key'], 'surfaced', actor)
        card = {'key': 'fyis:' + ','.join(i['key'] for i in batch), 'kind': 'fyis', 'lane': 'fyi', 'title': f"{len(batch)} fyi",
                'who': '', 'when': batch[0].get('when'), 'since': batch[0].get('since'), 'channel': batch[0].get('channel'),
                'why': 'people told you things; nothing to do', 'items': [card_for(i) for i in batch]}
        record(store, tid, 'assistant', say, card)
        return {'item': card, 'say': say, 'options': [], 'left': len(p['items']) - len(batch)}
    llm = _brain_for(store, tid, llm, trace, cancel, fast=True) if (llm is not None or INTRO_AI) else None   # the facts speak unless asked otherwise
    say, options = '', []
    if llm:
        try:
            ask = ("A REPORT landed - one sentence: which report, when, and whether it failed (then name the cause from what they wrote). Do NOT summarize "
                   "its contents; the owner reads it with the button. ") if item['kind'] == 'report' and not item.get('bad') else \
                  ("Say it in THREE BEATS, plainly, two or three sentences: (1) WHERE IT CAME FROM - who wrote, on what channel, when, and what they "
                   "asked in their words; (2) WHAT WAS DONE - triage's verdict, or what the agent did and found (THE AGENT FOUND / TASK NOW), or "
                   "nothing yet; (3) WHAT YOU NEED FROM THE OWNER - name the button: approve the draft below, answer the agent, read it, or nothing. "
                   + ('This is a REPLY waiting for the yes: beat 3 is whether to send THE DRAFT below. ' if item['kind'] in ('review', 'action') else '')
                   + ('The agent is parked and waiting: beat 3 is its question. ' if item['kind'] == 'agent' else ''))
            say, options = _ask(store, llm, tid, item, ask, p['items'])
            _remember_sid(store, tid, llm)
        except Exception as e: logger.warning(f'concierge: the model pass failed - {e}')
    if not say: say = fallback(item, True)
    funnel.settle(store, item['key'], 'surfaced', actor, note=item.get('sig'))
    record(store, tid, 'assistant', say + (f"\nOPTIONS: {' | '.join(options)}" if options else ''), card_for(item))
    return {'item': item, 'say': say, 'options': options, 'left': len(p['items']) - 1}


def say(store, text: str, key: str = None, llm=None, actor: str = 'owner', trace=None, cancel=None) -> dict:
    """The owner's words, answered briefly - about the item on the table when there is one."""
    text = str(text or '').strip()
    if not text: raise ValueError('say something')
    task, _ = general.dock_task(store, actor)
    tid = task['TaskId']
    record(store, tid, 'user', text)
    # a clear decision needs no model at all: carry it out (the page runs the verb) and receipt it, instantly
    p0 = funnel.pile(store)
    item0 = funnel.next_item(store, key) if key else None
    words0 = decide_words(text)
    # The verbs Taskuary honours ITSELF come first, whether or not something is on the table: a sweep,
    # a hand-off, a close. With a card open, a sweep used to fall into the receipt below and the page
    # was left to do it - which it cannot - so "make rules to not surface..." answered "Cleared. Moving
    # on." and swept nothing (the owner, 2026-09-03: "this did not work?").
    # "approve and remember that Kishan handles refunds" is two things: the memory used to be dropped
    if words0 and words0.get('remember'):
        try: remember_fact(store, words0['remember'], actor)
        except Exception as e: logger.warning(f'concierge: the memory did not save - {e}')
    if (words0 and words0['verb'] in ('clear', 'setup', 'stop_agent', 'setting', 'remember')
            or (words0 and words0['verb'] in ('split', 'forward') and item0)
            or (words0 and words0['verb'] == 'coder' and not item0)):
        return _carry_out(store, tid, text, words0, item0, actor)
    if words0 and words0['verb'] == 'split' and not item0:
        say_ = 'Nothing is on the table to split - pick the one you mean from the pipe and say it again.'
        record(store, tid, 'assistant', say_)
        return {'say': say_, 'options': [], 'decision': None}
    quick = words0 if item0 else None
    if quick and quick['verb'] == 'assent':                      # "yes" means whatever this card's own button does
        v = assent_verb(item0)
        if not v:
            say_ = (f"Yes to what, exactly? {item0.get('ref') or item0.get('title')} has nothing waiting on a yes - "
                    'say next to move on, or tell me what to do with it.')
            record(store, tid, 'assistant', say_)
            return {'say': say_, 'options': [], 'decision': None}
        quick = {**quick, 'verb': v, 'text': quick.get('text') if v == 'answer_agent' else ''}
    if quick:
        # the words name ANOTHER subject: resolve it and act THERE, or ask - never on what happens to be open
        if quick['verb'] in GUARDED:
            other = named_elsewhere(store, quick, item0, quick['verb'] in COSTLY)
            if other == '?':
                say_ = (f"Careful - you named something that is not what is on the table. On the table is "
                        f"{item0.get('who') + ' - ' if item0.get('who') else ''}{item0.get('title')}"
                        f"{' (' + item0['ref'] + ')' if item0.get('ref') else ''}, and I could not find what you meant. "
                        'Say it again with the sender or the ref and I will do it there; nothing has been touched.')
                record(store, tid, 'assistant', say_)
                return {'say': say_, 'options': [], 'decision': None}
            if other:
                it2 = funnel.next_item(store, other) or funnel.item_for_key(store, other)
                if it2 and it2.get('key') != item0.get('key'):
                    why = cannot(it2, quick['verb'], store)
                    if why:
                        record(store, tid, 'assistant', why)
                        return {'say': why, 'options': [], 'decision': None}
                    say_ = (f"That is {it2.get('who') + ' - ' if it2.get('who') else ''}{it2.get('title')}"
                            f"{' (' + it2['ref'] + ')' if it2.get('ref') else ''}, not the one on the table - so I am doing it there. "
                            f"{RECEIPTS.get(quick['verb'], '')} "
                            f"{item0.get('ref') or 'The one on the table'} is untouched.")
                    record(store, tid, 'assistant', say_)
                    return {'say': say_, 'options': [], 'decision': {**quick, 'target': card_for(it2)}}
        why = cannot(item0, quick['verb'], store)
        if why:
            record(store, tid, 'assistant', why)
            return {'say': why, 'options': [], 'decision': None}
        # "close it" is the one verb Taskuary can honour ITSELF, so it does: the receipt used to be the
        # page's job, and a page that could not find the card did nothing while this line already said
        # the task was closed (the owner, 2026-09-03: "I told the ai to close it but it did not").
        # "done" said about an agent parked on a question is not a row to tick: the job is over, so
        # the session ends with the task. It used to touch neither (2026-09-03).
        if quick['verb'] == 'done' and item0.get('kind') == 'agent' and item0.get('tid'):
            close_task(store, item0['tid'], actor)
            reply = f"{task_ref(item0['tid'])} closed and its agent stopped. Moving on."
            record(store, tid, 'assistant', reply)
            return {'say': reply, 'options': [], 'decision': {'verb': 'closed', 'taskId': item0['tid'], 'ref': task_ref(item0['tid'])}}
        if quick['verb'] == 'close' and item0.get('tid'):
            done = close_task(store, item0['tid'], actor)
            reply = f"{task_ref(item0['tid'])} closed. Moving on." if done else f"{task_ref(item0['tid'])} was already closed. Moving on."
            record(store, tid, 'assistant', reply)
            return {'say': reply, 'options': [], 'decision': {'verb': 'closed', 'taskId': item0['tid'], 'ref': task_ref(item0['tid'])}}
        reply = RECEIPTS.get(quick['verb'], 'Doing that now.') + (f" And remembered: {_cut(quick['remember'], 160)}." if quick.get('remember') else '')
        record(store, tid, 'assistant', reply)
        return {'say': reply, 'options': [], 'decision': quick}
    words = words0
    # words that point at something else: pull it in and talk about THAT (everything is the chat)
    found = None if words else lookup(store, text)     # an instruction is carried out, never answered with the mail it names
    if found and found != key:
        out = surface(store, found, llm, actor, None, trace, cancel)
        if out.get('item'): return out
    p = funnel.pile(store)
    item = funnel.next_item(store, key) if key else None
    llm = _brain_for(store, tid, llm, trace, cancel)
    reply, options, decision = '', [], None
    if llm:
        try:
            from . import handbook as hub
            hub_context = hub.block(store, text, actions=False) if hub.enabled(store) else ''
            system = _system(store, llm) + (f'\n\n{hub.ASSISTANT_LINE}' if hub.enabled(store) else '')
            raw = str(llm(system,
                          f"NOW: {datetime.now().strftime('%A %d %B %H:%M')}\n{funnel.summary(p['items'], coming=False)}\n\n{facts(store, item)}{trouble(store, text)}\n\n"
                          + (hub_context + '\n\n' if hub_context else '')
                          + (f"CONVERSATION SO FAR:\n{_turns(store, tid)}\n\n" if _turns(store, tid) else '')
                          + f"The owner says: {text}\nAnswer them, briefly. If this is a decision about the item on the table, carry it out (DECIDE line).",
                          max_tokens=MAX_TOKENS) or '').strip()
            if hub.enabled(store): raw = hub.publish_assistant_entries(store, tid, raw, 'assistant')
            raw, decision = parse_decision(raw)
            reply, options = parse_options(raw)
            _remember_sid(store, tid, llm)
        except Exception as e: logger.warning(f'concierge: the model pass failed - {e}')
    if item and decision is None: decision = decide_words(text)
    # The MODEL may also answer a correction by moving on - it did: "that's not a fail, it says all
    # clear?" came back as DECIDE: next, so the one thing the owner said was never taken (2026-09-03).
    if decision and decision['verb'] in ('next', 'skip', 'later', 'done') and _CORRECTION.search(text or ''):
        decision = None
    if not item: decision = None                               # nothing on the table to decide about
    if decision and decision['verb'] == 'assent': decision = ({**decision, 'verb': assent_verb(item)} if assent_verb(item) else None)
    # the model may name a verb this card cannot carry either: the honest line beats a receipt the
    # page then contradicts (2026-09-03)
    if decision:
        no = cannot(item, decision['verb'], store)
        if no: reply, decision = no, None
    # a decision is CARRIED OUT by the page, then receipted - so the line under it is the plain fact of what
    # happens now, never the model's claim that it already did something (haiku said "Task created" after
    # trying its own task tool, 2026-09-03)
    if decision: reply = ''
    if not reply: reply = RECEIPTS.get((decision or {}).get('verb'), '') or fallback(item, False)
    record(store, tid, 'assistant', reply + (f"\nOPTIONS: {' | '.join(options)}" if options else ''))
    return {'say': reply, 'options': options, 'decision': decision}


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

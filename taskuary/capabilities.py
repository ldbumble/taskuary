"""WHAT THIS INSTALL CAN DO, answered by one function - read by every check that decides what the owner is OFFERED: the chips,
the Advisor's verbs, the assistant's coding lines, setup, and the page (GET /api/capabilities, website/src/capabilities.js).
Each of these was asked its own way in its own file, and they disagreed: a Teams draft offered Send that could never
leave, coding was offered where no coding tool runs (2026-10-18). Nothing is cached - a connection made a second ago counts."""
from loguru import logger
from . import settings_schema


def _safe(f, default=False):
    # one failing probe (a card with bad JSON, a CLI that will not resolve) answers "no" for that one, never takes the rest down
    try: return f()
    except Exception as e:
        logger.debug(f'capabilities: {getattr(f, "__name__", "probe")} failed - {e}'); return default


def can_code(store) -> bool:
    """A coding tool that starts on this computer (agents.coding_ready) - read off the module so a test's patch is honoured."""
    from . import agents
    return bool(store is not None and _safe(lambda: agents.coding_ready(store)))


def ai_brain(store) -> dict:
    """The brain triage would run, or a backup that answers (setup._ai) - its `ready` IS "an AI is connected"; setup reads the
    rest (its name, why not) off the same dict."""
    from . import setup
    return (_safe(lambda: setup._ai(store), None) if store is not None else None) or {'ready': False}
# IS THERE AN AI FOR THIS JOB - ONE answer per job, the router's own pick (brainroute.choose, on agents.resolve_brain) and whether it or a
# backup it fails over to answers here. The page asked triage's brain for "an AI" and the goal's planner a list of its own: on one sheet
# the Plan-it box said an AI was there while the press found none (2026-11-19). The jobs the page offers work on:
AI_JOBS = ('triage', 'general', 'assistant')

def has_ai(store, job: str = 'triage') -> bool:
    """`triage` (mail is read; what the Advisor and the connect line ask), `general` (an agent can work a task), `assistant` (the
    Assistant answers, and plans a goal's steps - goals.plan)."""
    # the demo's script answers every ask (llm.build_llm) - with no AI "connected" the page drew Connect an AI over advice it had
    from . import demo
    if demo.enabled(): return True
    if job == 'triage': return bool(ai_brain(store).get('ready'))      # setup's row: the same pick and backups, with its name and why
    if store is None: return False
    from . import brainroute, llm
    r = _safe(lambda: brainroute.choose(store, job), None)
    return any(_safe(lambda p=p: llm.brain_status(store, p)['ready']) for p in ([r.pick, *r.chain] if r else []) if p)


def mail_cards(store) -> list:
    """The mailboxes connected and polled (setup._inbound) - names, for the screens that list them."""
    from . import setup
    return (_safe(lambda: setup._inbound(store), []) if store is not None else []) or []
def has_mail(store) -> bool: return bool(mail_cards(store))


def can_send(store, channel) -> bool:
    """Can a reply on this channel leave from here (outbound.can_reply): email yes, Teams - read, never posted into - no."""
    from . import outbound
    return bool(store is not None and channel and _safe(lambda: outbound.can_reply(store, channel)))


def send_refusal(store, channel) -> str:
    """'' when a message can leave on this channel, else the one sentence why (outbound.send_block names the place that lifts
    it) - three doors each said "turn its replies on in Connections", true of none of Teams, a switched-off reply or a mailbox."""
    if can_send(store, channel): return ''
    from . import outbound, words
    why = _safe(lambda: outbound.send_block(store, channel), '') or f"its card under {words.name('connections')} cannot deliver yet"
    return f'{channel or "that channel"} cannot send from here - {why}'


def draft_channel(store, rid) -> str:
    """The channel a draft would leave on: its envelope's for a message the owner started, else the message it answers.
    '' when it is not a reply at all (an agent's proposal, an invoice) or nothing says - nothing to refuse then."""
    import json
    r = (store.get_review(int(rid)) if store is not None and rid else None) or {}
    if not r or r.get('Kind') == 'action': return ''
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    if not isinstance(env, dict) or env.get('kind') in ('zoho_invoice', 'calendar'): return ''      # outbound.OWN_ROAD
    m = (store.get_message(r['MessageId']) if r.get('MessageId') else None) or {}
    return str(m.get('Channel') or env.get('channel') or '')


def can_send_draft(store, rid) -> bool:
    """False only where the draft's channel is known and cannot deliver - the Send that would only ever fail."""
    ch = draft_channel(store, rid)
    return not ch or can_send(store, ch)


def channels() -> tuple:
    """Every channel a reply could be asked of: the ones with a sender, the ones read here but answered there, and the sources that
    answer on their own thread behind their card's Replies switch (inboxes.REPLY)."""
    from . import outbound
    return tuple(dict.fromkeys((*outbound.SENDABLE, *outbound.NO_SENDER, *outbound.INBOX_REPLY)))


def capabilities(store) -> dict:
    """{"coding", "ai", "ai_for": {job: bool}, "mail", "send": {channel: bool}} - the one answer, for the server and the page alike."""
    return {'coding': can_code(store), 'ai': has_ai(store), 'ai_for': {j: has_ai(store, j) for j in AI_JOBS}, 'mail': has_mail(store),
            'send': {ch: can_send(store, ch) for ch in channels()}}


# ── WHAT THIS AGENT CAN DO HERE, said to it each turn (design round 3, 2026-11-18) ──────────────────────────────────────────────────────
# "Fix the rounding bug in <his checkout>" was refused on every AI: "this general task has no way to switch to coding", "add your checkout as a
# repository" - an agent with a shell, told only that it did "non-coding work", named buttons that do not exist and never the one switch that
# does. One fact, read from the state the app itself goes by - its hands, the other AIs he could hand it to, Developer mode - and nothing else
# says it: never a button, a setting or an AI that is not here.
FACT_HEAD = "WHAT YOU CAN DO HERE (this computer as it is now - never name a button, setting or AI that is not in this list):"
HANDS = {
    'all': ('A shell and files on this computer: a folder the owner names on this task is yours to read and change - for a fix in code there, '
            'make the change, run its tests and commit it there. A push or anything else that leaves this computer becomes his card when you run it. '
            'Say what a file holds from the file as it is now, never from memory - another task may have changed it.'),
    'look': ("Reading only: you read files and look things up, and change and run nothing - his setting "
             f"{settings_schema.link('general_agent_hands', 'General agents can')} is 'only look things up'."),
    'none': ('Words only: this AI takes no tools, so you open no file, page or system and run nothing - you have what this conversation holds. '
             'A file he asks for (a sheet, a document, code) you write whole in a fenced block whose first line names it - ```csv file=quotes.csv, '
             '```xlsx file=quotes.xlsx with `a | b | c` rows - and Taskuary saves it to the task\'s files.'),
}


def other_ais(store, pick: str = '', clis: bool = False) -> list:
    """The AIs ready here besides `pick`, by the names the task's Agent menu shows them (general.provider_options): a CLI only where it starts
    on this computer and its last test did not fail (agents.ready_brains) - the menu lists every one connected, installed or not. `clis`: those
    alone (what drives a browser whatever its model)."""
    from . import agents, general
    if store is None: return []
    ready = {f'cli:{k}' for k in _safe(lambda: agents.ready_brains(store), [])}
    return [o['label'] for o in _safe(lambda: general.provider_options(store), [])
            if o.get('pick') != pick and (o['pick'] in ready if o.get('type') == 'cli' else not clis)]


def fact(store, hands: str, pick: str = '') -> str:
    """WHAT THIS AGENT CAN DO HERE, in one block: `hands` 'all' (a shell and files), 'look' (reads only) or 'none' (a card that takes no
    tools); the AIs the owner could hand it to instead, from his own menu; Developer mode, as it stands. Said where every turn's late facts
    are (general), so a change - a switch flipped, an AI connected - reaches a conversation under way."""
    from . import agents, words
    others = other_ais(store, pick)
    dev = agents.developer_mode(store)
    # ...AND THE APP'S OWN ROADS WHERE THIS AGENT HAS NONE (design round 4, H5: an AI card told him "there is no button or setting you can press"
    # with the install of a CLI one page away, and "I cannot schedule this" in an app that runs routines): a road that is here is named
    cli = _safe(lambda: agents.cli_ready(store))
    out = [FACT_HEAD, f'- {HANDS.get(hands, HANDS["none"])}',
           f"- Another AI could do this task: {', '.join(others)} - he picks it in the Agent menu on this task." if others else
           '- No other AI is connected here: never offer to switch this task to one.',
           *([] if cli else [f"- An AI CLI - a shell, files and a browser on this computer - can be installed from {words.link('ai_apps')}: "
                             'where the work needs hands you lack, that is the road to name.']),
           '- Work that should run again by itself is a routine Taskuary runs: set it up for his one press (save_routine), never "it cannot be '
           'scheduled".',
           '- Developer mode is on: coding tasks also run in a terminal of their own.' if dev else
           f'- Developer mode is off ({settings_schema.link("developer_mode", "Settings")}): it adds coding tasks in a terminal '
           'of their own' + (' - a change in a folder he names needs none of it.' if hands == 'all' else '.')]
    # ...and Developer mode only where it would give him something: with no AI CLI here it starts no coding task (agents.coding_ready)
    return '\n'.join(out if cli else out[:-1])

"""What still needs doing before Taskuary can actually work, derived from real state.

The app has never said what "set up" means. A fresh install opens on an empty Timeline that
looks exactly like a working install with a quiet morning, and the three things standing between
those two states - who you are, an AI that can read a message, somewhere for messages to arrive
from - are on three different tabs with nothing pointing at them.

Nothing here is a stored checklist that could drift out of step with the truth: every step reads
the same tables the funnel reads, so a step is done when the thing it asks for actually works,
and un-does itself if the connection is removed.

One step is stored, deliberately: `models` asks you to look at the page where the four brains and
their models are chosen, and a fresh install already ships working defaults, so there is nothing
there to derive. "The defaults are fine" and "I never looked" are the same state. That single
exception is `SEEN_MODELS`; everything else on this list still reads the tables the funnel reads.
"""
from .llm import AI_TYPES

DISMISSED = 'setup_dismissed'      # the owner's "I know, leave me alone" - a setting, so it sticks

# Channels that bring work IN. A report connection or a tool is not a funnel: without one of
# these the Timeline has nothing to show and never will.
INBOUND = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord',
           'github', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab', 'azdo',
           'linear', 'trello', 'notion', 'sentry', 'pagerduty')

# Where work ARRIVES for a person, as opposed to where it is tracked. A tracker is a real source and
# stays in INBOUND for everything that reads it - but an install with GitHub and no mailbox has a
# Timeline with no mail in it, and the row said it was done. So the checklist asks for one of these.
MESSAGING = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord')

# The ONE stored step, and the only exception to this module's rule. A fresh install already ships
# working brain and model defaults, so there is nothing to derive: "the defaults are fine" and "I
# never looked" are the same state. Opening the page is what the row asks for, so opening the page
# is what it records.
SEEN_MODELS = 'setup_seen_models'


def _ai(store) -> dict:
    """Anything that could actually answer a prompt, in the order build_llm would pick it.

    A CLI agent counts. Most people arriving here already pay for Claude Code or Codex and have
    no separate API key at all, so treating "a key exists" as the only definition of a brain told
    them they had none while the thing was sitting on their PATH.

    Ollama is the other exception: a local model carries no key, so 'has a secret' is the wrong
    test for it too."""
    pick = str(store.get_settings().get('triage_ai') or '')
    if pick.startswith('cli:'):
        row = store.get_agent(pick[4:])
        if row: return {'Name': f'{row["Name"]} (CLI)', 'Type': 'cli'}
    for c in store.list_connectors():
        if c['Type'] in AI_TYPES and c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'):
            return c
    return {}


def _inbound(store, types=INBOUND) -> list:
    """Connections that bring work in AND have a source to poll. A card with credentials and no
    mailbox behind it is half-connected - it looks done on the Connections tab and delivers
    nothing, which is exactly the state a checklist exists to catch."""
    live = {s['Channel'] for s in store.list_sources() if s.get('Active')}
    from .channels import CH2SRC
    out = []
    for c in store.list_connectors():
        if c['Type'] not in types or not c['Active']: continue
        if CH2SRC.get(c['Type'], c['Type']) in live: out.append(c['Name'] or c['Type'])
    return out


def state(store) -> dict:
    """The wizard's whole model: ordered steps, each with what it is for and whether it is done."""
    who = (store.owner() or {}).get('owner') or ''
    ai, inbound = _ai(store), _inbound(store, MESSAGING)
    seen_models = str(store.get_settings().get(SEEN_MODELS) or '') == '1'
    # the four seeded reports (Morning digest, End of day checkup, Automation ideas, the Assistant)
    # file their own rows on first start, so "something is in the timeline" was true before a single
    # message had ever been read
    inbox = [m for m in store.feed(limit=5, days=3650) if m.get('Channel') != 'report']
    steps = [
        {'key': 'owner', 'title': 'Say who you are',
         'why': 'Your name signs every reply, and the operator documents fill it in wherever they '
                'say {{owner}}. Without it the drafts go out addressed by nobody.',
         # owner() answers 'owner', not 'name', and falls back to the literal string "the owner"
         # when nothing is set - so both have to be checked or this step reads done on a fresh
         # install and the checklist sends nobody to the one field that signs their mail
         'done': bool(who) and who != 'the owner',
         'detail': who if who != 'the owner' else '',
         'goto': {'tab': 'Docs', 'hash': 'owner'}},
        {'key': 'ai', 'title': 'Set up an AI',
         'why': 'This is what reads each message and decides whether it is work, a question, or '
                'noise. Until it exists every message just files itself onto the Timeline, '
                'untriaged - the app runs, and does nothing for you. A coding CLI you already '
                'pay for will do it; so will an API key.',
         'done': bool(ai), 'detail': ai.get('Name') or '',
         'goto': {'tab': 'Connections', 'hash': 'cli-agents'}},
        {'key': 'models', 'title': 'Choose what runs on which model',
         'why': 'Triage, the assistant, the general agent and the coding CLI each run on a brain '
                'and a model, and the defaults are a guess at your budget. One page shows all four '
                'and what will actually run. Looking is enough - the defaults are a real answer.',
         'done': seen_models, 'detail': 'you have seen the defaults' if seen_models else '',
         'goto': {'tab': 'Settings', 'hash': 'settings=config&group=Triage%20%26%20agents'}},
        {'key': 'inbound', 'title': 'Connect where work arrives',
         'why': 'A mailbox or a chat - somewhere people actually write to you. Without one the '
                'Timeline is empty because nothing is being read, not because nothing happened. '
                'Trackers and report sources come later; they file work, they do not bring it in.',
         'done': bool(inbound), 'detail': ', '.join(inbound[:3]),
         'goto': {'tab': 'Connections', 'hash': ''}},
        {'key': 'sync', 'title': 'Read your first messages',
         'why': 'With the four above in place, one sync pulls your mail in and the AI triages it. '
                'The assistant then has a pile to take you through, which is the whole point.',
         # no count: this samples the feed, so any number it printed would be the sample size
         # rather than the truth ("2 read" on an install holding thousands)
         'done': bool(inbox), 'detail': 'messages are arriving' if inbox else '',
         'goto': {'tab': 'Assistant', 'hash': ''}},
    ]
    done = sum(1 for s in steps if s['done'])
    return {'steps': steps, 'done': done, 'total': len(steps), 'complete': done == len(steps),
            'dismissed': str(store.get_settings().get(DISMISSED) or '') == '1'}

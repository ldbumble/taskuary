"""What still needs doing before Taskuary can actually work, derived from real state.

The app has never said what "set up" means. A fresh install opens on an empty Timeline that
looks exactly like a working install with a quiet morning, and the three things standing between
those two states - who you are, an AI that can read a message, somewhere for messages to arrive
from - are on three different tabs with nothing pointing at them.

Nothing here is a stored checklist that could drift out of step with the truth: every step reads
the same tables the funnel reads, so a step is done when the thing it asks for actually works,
and un-does itself if the connection is removed.
"""
from .llm import AI_TYPES

DISMISSED = 'setup_dismissed'      # the owner's "I know, leave me alone" - a setting, so it sticks

# Channels that bring work IN. A report connection or a tool is not a funnel: without one of
# these the Timeline has nothing to show and never will.
INBOUND = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'discord',
           'github', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab', 'azdo',
           'linear', 'trello', 'notion', 'sentry', 'pagerduty')


def _ai(store) -> dict:
    """The first AI connection that could actually answer a prompt. Ollama is the exception that
    matters: a local model carries no key, so 'has a secret' is the wrong test for it."""
    for c in store.list_connectors():
        if c['Type'] in AI_TYPES and c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'):
            return c
    return {}


def _inbound(store) -> list:
    """Connections that bring work in AND have a source to poll. A card with credentials and no
    mailbox behind it is half-connected - it looks done on the Connectors tab and delivers
    nothing, which is exactly the state a wizard exists to catch."""
    live = {s['Channel'] for s in store.list_sources() if s.get('Active')}
    from .channels import CH2SRC
    out = []
    for c in store.list_connectors():
        if c['Type'] not in INBOUND or not c['Active']: continue
        if CH2SRC.get(c['Type'], c['Type']) in live: out.append(c['Name'] or c['Type'])
    return out


def state(store) -> dict:
    """The wizard's whole model: ordered steps, each with what it is for and whether it is done."""
    who = (store.owner() or {}).get('owner') or ''
    ai, inbound = _ai(store), _inbound(store)
    agents = [a['Name'] for a in store.list_agents()]
    msgs = store.feed(limit=1, days=3650)
    steps = [
        {'key': 'owner', 'title': 'Say who you are',
         'why': 'Your name signs every reply, and the operator documents fill it in wherever they '
                'say {{owner}}. Without it the drafts go out addressed by nobody.',
         # owner() answers 'owner', not 'name', and falls back to the literal string "the owner"
         # when nothing is set - so both have to be checked or this step reads done on a fresh
         # install and the wizard sends nobody to the one field that signs their mail
         'done': bool(who) and who != 'the owner',
         'detail': who if who != 'the owner' else '', 'where': 'Docs'},
        {'key': 'ai', 'title': 'Connect an AI brain',
         'why': 'This is what reads each message and decides whether it is work, a question, or '
                'noise. Until it exists every message just files itself onto the Timeline, '
                'untriaged - the app runs, and does nothing for you.',
         'done': bool(ai), 'detail': ai.get('Name') or '', 'where': 'Connectors'},
        {'key': 'inbound', 'title': 'Connect where work arrives',
         'why': 'A mailbox, a chat, a tracker - anything that brings work in. Without one the '
                'Timeline is empty because nothing is being read, not because nothing happened.',
         'done': bool(inbound), 'detail': ', '.join(inbound[:3]), 'where': 'Connectors'},
        {'key': 'agent', 'title': 'Add a coding agent', 'optional': True,
         'why': 'Only for work that means changing code. Everything else - triage, replies, '
                'reports - works without one.',
         'done': bool(agents), 'detail': ', '.join(agents[:3]), 'where': 'Settings'},
        {'key': 'sync', 'title': 'Read your first messages', 'optional': True,
         'why': 'With the three above in place, one sync pulls your mail in and the AI triages it. '
                'This is the first time you see the funnel actually work.',
         'done': bool(msgs), 'detail': f'{len(msgs)} in the timeline' if msgs else '',
         'where': 'Timeline'},
    ]
    required = [s for s in steps if not s.get('optional')]
    return {'steps': steps,
            'done': sum(1 for s in required if s['done']), 'total': len(required),
            'ready': all(s['done'] for s in required),
            'dismissed': str(store.get_settings().get(DISMISSED) or '') == '1'}

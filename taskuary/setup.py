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
INBOUND = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord',
           'github', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab', 'azdo',
           'linear', 'trello', 'notion', 'sentry', 'pagerduty')


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


def _inbound(store) -> list:
    """Connections that bring work in AND have a source to poll. A card with credentials and no
    mailbox behind it is half-connected - it looks done on the Connections tab and delivers
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
    # Generate-from-history always stamps the block it owns. The templates already contain the
    # marker pair, so marker presence alone would call an untouched fresh install personalized.
    # A real manual edit counts too: onboarding must not insist on replacing guidance somebody
    # already wrote themselves just because it did not come from the generator.
    personalized = {name: ('_generated ' in (store.get_doc(name) or '')
                           or store.doc_owner(name) not in (None, 'template', 'startup'))
                    for name in ('style', 'triage')}
    # Both of these read as DONE on a brand-new install unless you are careful, which is worse
    # than useless: a checklist that ticks itself teaches you not to read it.
    #
    # 'coder' is a SHIPPED default (config.py seeds it, assuming the claude CLI is on your PATH),
    # so "an agent row exists" proves nothing about this machine. A finished RUN does.
    ran = [r for t in store.list_tasks() for r in store.list_runs(t['TaskId']) if r.get('FinishedAt')]
    # and the three seeded reports (Morning digest, Automation ideas, the Assistant) file their
    # own rows on first start, so "something is in the timeline" was true before a single
    # message had ever been read
    inbox = [m for m in store.feed(limit=5, days=3650) if m.get('Channel') != 'report']
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
                'untriaged - the app runs, and does nothing for you. A coding CLI you already '
                'pay for will do it; so will an API key.',
         'done': bool(ai), 'detail': ai.get('Name') or '', 'where': 'Connections'},
        {'key': 'inbound', 'title': 'Connect where work arrives',
         'why': 'A mailbox, a chat, a tracker - anything that brings work in. Without one the '
                'Timeline is empty because nothing is being read, not because nothing happened.',
         'done': bool(inbound), 'detail': ', '.join(inbound[:3]), 'where': 'Connections'},
        {'key': 'sync', 'title': 'Read your first messages', 'optional': True, 'recommended': True,
         'why': 'With the three above in place, one sync pulls your mail in and the AI triages it. '
                'It also gives the two personalization steps below real history to learn from.',
         # no count: this samples the feed, so any number it printed would be the sample size
         # rather than the truth ("2 read" on an install holding thousands)
         'done': bool(inbox), 'detail': 'messages are arriving' if inbox else '',
         'where': 'Timeline'},
        {'key': 'style', 'title': 'Teach it how you write replies', 'optional': True, 'recommended': True,
         'why': 'Taskuary reads the last three months of messages you sent and distills your greeting, '
                'tone, length, phrasing, and sign-off into STYLE.md. Your first drafted reply then '
                'sounds like you instead of a generic assistant.',
         'done': personalized['style'], 'detail': 'reply style ready' if personalized['style'] else '',
         'where': 'Docs'},
        {'key': 'triage', 'title': 'Teach it what deserves your attention', 'optional': True, 'recommended': True,
         'why': 'Taskuary compares what you answered with what you let sit, then adds those patterns to '
                'TRIAGE.md. It starts with a useful idea of your real work instead of learning every '
                'routine sender and topic one correction at a time.',
         'done': personalized['triage'], 'detail': 'triage habits ready' if personalized['triage'] else '',
         'where': 'Docs'},
        {'key': 'agent', 'title': 'Put a coding agent to work', 'optional': True,
         'why': 'Only for work that means changing code - everything else, triage, replies and '
                'reports, works without one. Ticked once an agent has actually finished a run '
                'here: Taskuary ships a default pointed at the claude CLI, and a default that '
                'has never run is not proof that anything is installed.',
         'done': bool(ran), 'detail': f'{len(ran)} run{"s" if len(ran) != 1 else ""} finished' if ran else '',
         'where': 'Settings'},
    ]
    required = [s for s in steps if not s.get('optional')]
    guided = [s for s in steps if not s.get('optional') or s.get('recommended')]
    return {'steps': steps,
            'done': sum(1 for s in required if s['done']), 'total': len(required),
            'ready': all(s['done'] for s in required),
            'guide_done': sum(1 for s in guided if s['done']), 'guide_total': len(guided),
            'complete': all(s['done'] for s in guided),
            'dismissed': str(store.get_settings().get(DISMISSED) or '') == '1'}

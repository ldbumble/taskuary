"""What still needs doing before Taskuary can actually work, derived from real state.

The app has never said what "set up" means. A fresh install opens on an empty Timeline that
looks exactly like a working install with a quiet morning, and the three things standing between
those two states - who you are, an AI that can read a message, somewhere for messages to arrive
from - are on three different tabs with nothing pointing at them.

Nothing here is a stored checklist that could drift out of step with the truth: every step reads
the same tables the funnel reads, so a step is done when the thing it asks for actually works,
and un-does itself if the connection is removed.

The first useful result needs your identity, one AI and one source. Model assignments and extra
agents are available afterwards; opening their settings is not a prerequisite for doing work.
"""
from .llm import AI_TYPES, brain_status

DISMISSED = 'setup_dismissed'      # the owner's "I know, leave me alone" - a setting, so it sticks

# Channels that bring work IN. A report connection or a tool is not a funnel: without one of
# these the Timeline has nothing to show and never will.
INBOUND = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord',
           'github', 'jira', 'asana', 'monday', 'clickup', 'todoist', 'gitlab', 'azdo',
           'linear', 'trello', 'notion', 'sentry', 'pagerduty')

# Retained for callers that specifically need messaging rather than tracker sources.
MESSAGING = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord')

# Compatibility with the optional model-settings visit recorded by older versions.
SEEN_MODELS = 'setup_seen_models'


def _ai(store) -> dict:
    """The brain triage will actually run, and whether it can - llm.brain_status, the same resolution
    build_llm makes, so this row cannot tick on one brain while the mail is read by another.

    A CLI agent counts. Most people arriving here already pay for Claude Code or Codex and have
    no separate API key at all, so treating "a key exists" as the only definition of a brain told
    them they had none while the thing was sitting on their PATH.

    ...and only a brain that STARTS counts. This row used to tick on the first AI connector with a key
    while a blank triage setting meant the claude CLI - on a machine without Claude Code it said
    "running on Anthropic" and every message failed triage with "'claude' not found on PATH".

    Backups count too, the way build_llm falls over to them: the first that can answer is the brain."""
    st = brain_status(store)
    if st['ready']: return st
    backups = str(store.get_setting('triage_backup_ai') or '').split(',')
    return next((b for b in (brain_status(store, p.strip()) for p in backups if p.strip()) if b['ready']), st)


def _inbound(store, types=INBOUND) -> list:
    """Connections that bring work in AND have a source to poll. A card with credentials and no
    mailbox behind it is half-connected - it looks done on the Connections tab and delivers
    nothing, which is exactly the state a checklist exists to catch."""
    live = [s for s in store.list_sources() if s.get('Active')]
    from .channels import CH2SRC, _poll_jobs
    polling = {c['ConnectorId'] for c, _ in _poll_jobs(store)}
    out = []
    for c in store.list_connectors():
        if c['Type'] not in types or c['ConnectorId'] not in polling: continue
        if any(s['Channel'] == CH2SRC.get(c['Type'], c['Type'])
               and (not s.get('ConnectorId') or s['ConnectorId'] == c['ConnectorId']) for s in live):
            out.append(c['Name'] or c['Type'])
    return out


def _first_items(store) -> list:
    """A small review sample of real inbound results, without reports hiding them behind a cap."""
    from .channels import CH2SRC
    channels = tuple(dict.fromkeys(CH2SRC[t] for t in INBOUND if t in CH2SRC))
    return store._rows(f'''SELECT MessageId, TaskId, Subject, Channel FROM message
        WHERE Channel IN ({','.join('?' for _ in channels)})
          AND IFNULL(Direction,'in') <> 'out'
          AND Status NOT IN ('new','triaging','error','context','history','skipped','withdrawn')
        ORDER BY CreatedAt DESC, MessageId DESC LIMIT 5''', channels)


def state(store) -> dict:
    """The wizard's whole model: ordered steps, each with what it is for and whether it is done.

    `goto` carries a `label` as well as the tab and the position inside it, and the label is what the
    button SAYS. Naming the tab instead put "Connections" on two different rows going to two
    different places - the AI CLI agents page and the connector list - which a first-time owner
    cannot tell apart. It lives here rather than in either surface so the walk's stop and the
    checklist's row name the same destination with the same words."""
    who = (store.owner() or {}).get('owner') or ''
    ai, inbound = _ai(store), _inbound(store)
    inbox = _first_items(store)
    steps = [
        # EVERY detail says what it IS, not just what it holds. A bare noun in the done-green -
        # "Outlook mail, Microsoft Teams, Telegram" sitting directly above "You can connect a
        # mailbox" - reads as a HEADING for the instructions rather than as "you already have
        # these" (the owner, 2026-09-17: "shouldn't this show what is already connected?"). Two
        # surfaces render this line and neither can add the words: only here knows what it means.
        {'key': 'owner', 'title': 'Say who you are',
         'why': 'Add the name that signs your drafts. Your email helps Taskuary recognise your own '
                'messages; you can add the rest of your preferences later.',
         # owner() answers 'owner', not 'name', and falls back to the literal string "the owner"
         # when nothing is set - so both have to be checked or this step reads done on a fresh
         # install and the checklist sends nobody to the one field that signs their mail
         'done': bool(who) and who != 'the owner',
         'detail': f'signed as {who}' if who and who != 'the owner' else '',
         # Docs is a section of Settings now, and "About you" is where the name actually is -
         # this button opened a tab that no longer exists (2026-09-22)
         'goto': {'tab': 'Settings', 'hash': 'settings=about', 'label': 'Open About you'}},
        {'key': 'ai', 'title': 'Connect one AI',
         'why': 'Use one API provider, a local model, or a coding CLI you already pay for. Test it '
                'on its connection card. The existing model defaults are enough to begin.',
         'done': ai['ready'], 'detail': f"running on {ai['Name']}" if ai['ready'] else ai['why'],
         # WHERE IT SENDS YOU DEPENDS ON WHAT YOU HAVE. "Open AI CLI agents" is the right door when
         # there is no brain yet, or when the brain IS a CLI. It is the wrong one for a key provider:
         # Azure OpenAI is not a CLI tool and cannot be set up in a terminal, so pointing an install
         # that already runs on Azure at a CLI installer read as "this is how you do it" (the owner,
         # 2026-09-17: "you cant setup azure ai from here. It's not a cli tool").
         'goto': ({'tab': 'Connections', 'hash': 'cli-agents', 'label': 'Open AI CLI agents'}
                  if not ai['Type'] or ai['Type'] == 'cli'
                  else {'tab': 'Connections', 'hash': f"connector={ai.get('Type')}",
                        'label': f"Open the {ai.get('Name') or 'provider'} card"}),
         # ...and with no brain at all, the OTHER road too: an owner with an OpenAI or Azure key and no
         # CLI saw only the CLI door and had nowhere to paste it. Connections opens on its AI group.
         **({'alt': {'tab': 'Connections', 'hash': '', 'label': 'Paste an API key'}} if not ai['Type'] else {})},
        {'key': 'inbound', 'title': 'Connect one work source',
         'why': 'Start with one mailbox, chat, or issue tracker. Choose the account or project you '
                'want read, enable it as an input, and test the connection. Other sources can wait.',
         'done': bool(inbound), 'detail': f"already connected: {', '.join(inbound[:3])}" if inbound else '',
         'goto': {'tab': 'Connections', 'hash': '', 'label': 'Add one work source'}},
        {'key': 'sync', 'title': 'Review your first result',
         'why': 'Read your connected sources, then review up to five recent items here. Open one '
                'to see its verdict and any draft. A sync follows each source\'s normal scope; '
                'this review sample does not limit how many items it imports.',
         # no count: this samples the feed, so any number it printed would be the sample size
         # rather than the truth ("2 read" on an install holding thousands)
         'done': bool(inbox), 'detail': 'your first items are ready to review' if inbox else '',
         'action': 'sync', 'enabled': bool(who and who != 'the owner' and ai['ready'] and inbound),
         'goto': {'tab': 'Assistant', 'hash': '', 'label': 'Open the Assistant'}},
    ]
    done = sum(1 for s in steps if s['done'])
    return {'steps': steps, 'done': done, 'total': len(steps), 'complete': done == len(steps),
            'first_items': inbox, 'pending': bool(store.pending_triage(limit=1)),
            'dismissed': str(store.get_setting(DISMISSED) or '') == '1'}

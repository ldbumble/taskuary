"""Setting Taskuary up, as a walk through the app rather than a form that imitates it.

The chip this sits behind used to open an AI-led walk-through, which could not run at all before an
AI was connected - which is exactly when somebody presses it. So nothing here reaches a model: a
stop is static text plus a read off the store, and Next is code.

That is not a lesser version of the assistant, it is how the assistant already works: deterministic
steps, with the AI for anything off script. A question typed during the walk is an ordinary turn,
answered beside the walk rather than inside it, and the assistant's own fallback already speaks in
facts when there is no model to answer it. The walk keeps its place and Next picks the script back up.

TWO KINDS OF TEXT live in a stop, and the difference is the whole design:

  `can`   - what the app can DO here. Static, hard-coded, the same on every install. Assembling it
            at runtime would make it go blank on a fresh install, which is the one install reading it.
  `facts` - what THIS install has done. Read off the same tables `setup.state` reads, so a stop can
            never claim something the checklist contradicts.
"""
from loguru import logger

from . import setup

AT = 'setup_walk_at'                 # where the owner stopped; a setting, so a reload resumes


def _goto(tab, hash_=''): return {'tab': tab, 'hash': hash_}
def _can(text, tab=None, hash_=''): return {'text': text, 'goto': _goto(tab, hash_) if tab else None}


# The five the checklist also shows, then every part of the app. The first five carry no `title`,
# `blurb` or `goto` of their own - `setup.state` owns their words AND where the button lands, and
# repeating either here is the drift this avoids.
STOPS = [
    {'key': 'owner', 'can': [
        _can('type your name and email right here'),
        _can('see every document that uses it', 'Settings', 'settings=docs')]},
    # TWO ROADS, and neither is the other. A key provider - Azure OpenAI, OpenAI, Anthropic - is a
    # card you paste a key on; it is not a CLI and there is nothing to sign in to in a terminal. The
    # CLI road was listed first and twice, so the whole stop read as "install a CLI", which is not
    # how most of these get set up (the owner, 2026-09-17: "you cant setup azure ai from here").
    {'key': 'ai', 'can': [
        _can('paste an API key on a provider card - Azure OpenAI, OpenAI, Anthropic, OpenRouter', 'Connections'),
        _can('or sign in to a coding CLI you already pay for - Claude Code, Codex - in a terminal right here',
             'Connections', 'cli-agents'),
        _can('either one is enough; triage reads your mail on whichever you pick', 'Settings',
             'settings=config&group=Triage%20%26%20agents')]},
    {'key': 'models', 'can': [
        _can('choose the brain that triages your mail', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose what the assistant here speaks on', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose the general agent and the coding CLI', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('name a model, or leave it on the provider default')]},
    {'key': 'inbound', 'can': [
        _can('connect a mailbox - Outlook, Gmail, or any IMAP host', 'Connections'),
        _can('connect a chat - Teams, Slack, WhatsApp, Telegram', 'Connections'),
        _can('test a card before waiting on a schedule', 'Connections')]},
    {'key': 'sync', 'can': [
        # Sync now lives on the Assistant tab as well as on each connection card, and this stop's
        # own goto is the checklist's - so sending the first line anywhere else was a stop arguing
        # with the button above it
        _can('pull your mail in and let triage read it', 'Assistant'),
        _can('watch it land on the Timeline', 'Assistant')]},

    {'key': 'connections', 'title': 'Connections', 'image': '/walk/connections.png',
     'blurb': 'Every mailbox, chat, tracker and report source Taskuary reads lives here. One card '
              'per system, and the card proves itself with its own Test before anything waits on a '
              'schedule.',
     'goto': _goto('Connections'), 'can': [
        _can('connect a mailbox or a chat', 'Connections'),
        _can('connect a tracker - GitHub, Jira, Linear and the rest', 'Connections'),
        _can('add an AI CLI agent', 'Connections', 'cli-agents'),
        _can('test any connection and see what it answered', 'Connections')]},
    {'key': 'docs', 'title': 'Docs', 'image': '/walk/docs.png',
     'blurb': 'The documents the funnel runs on. SOUL.md is its constitution - what counts as a '
              'task, how you answer, what it must never do. STYLE.md is how you write. Edit one and '
              'triage changes; blank one and the shipped default comes back, so nothing is lost by '
              'trying.',
     # Docs is a section of Settings now, not a tab of its own - every one of these opened a tab
     # that no longer exists, so the stop's own button went nowhere (found re-shooting the walk,
     # 2026-09-22: the capture script refuses to shoot a tab it cannot click, which is what caught it)
     'goto': _goto('Settings', 'settings=docs'), 'can': [
        _can('make SOUL.md yours - your work, boundaries, systems, people, voice', 'Settings', 'settings=docs'),
        _can('generate STYLE.md from the messages you have sent', 'Settings', 'settings=docs'),
        _can('generate TRIAGE.md from what you answered and what you let sit', 'Settings', 'settings=docs'),
        _can('read COUNSEL.md, which is the voice the assistant speaks in', 'Settings', 'settings=docs')]},
    {'key': 'settings', 'title': 'Settings', 'image': '/walk/settings.png',
     'blurb': 'The knobs. Most people change three and never come back: what drafts automatically, '
              'how finished work lands, and what reaches them.',
     'goto': _goto('Settings'), 'can': [
        _can('choose the triage brain and its backups', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('decide whether replies draft themselves', 'Settings'),
        _can('write routing policies the AI can never override', 'Settings', 'settings=policies'),
        _can('see every verdict it learned from, and switch off the wrong ones', 'Settings', 'settings=memory'),
        _can('install an update in place', 'Settings', 'settings=updates')]},
    {'key': 'board', 'title': 'Board', 'image': '/walk/board.png',
     'blurb': 'Work in flight, and the agents doing it. A coding task opens a real terminal session '
              'here, and you can watch it, take it over, or hand it a note mid-run.',
     'goto': _goto('Board'), 'can': [
        _can('watch a live agent session', 'Board'),
        _can('take over a pane and type in it yourself', 'Board'),
        _can('leave a note the agent picks up at its next stop', 'Board'),
        _can('put a coding agent to work on a task', 'Tasks')]},
    {'key': 'tasks', 'title': 'Tasks', 'image': '/walk/tasks.png',
     'blurb': 'Everything that became work, open or closed. A task holds the thread it came from, '
              'every run against it, and the session you can pick back up.',
     'goto': _goto('Tasks'), 'can': [
        _can('open a task and read the thread behind it', 'Tasks'),
        _can('continue a coding session where it stopped', 'Tasks'),
        _can('hand a task to an agent, or take it back', 'Tasks'),
        # Review retired as a tab of its own: a drafted reply waits on the task it belongs to. The
        # stop that used to send you to a queue is gone, and what it was FOR - nothing sends until
        # you say so - is said here, where the draft actually is (2026-09-22).
        _can('approve the reply drafted in your voice - nothing sends until you do', 'Tasks'),
        _can('edit it first, or ask for it again differently', 'Tasks'),
        _can('close it - which is yours, never the agent\'s', 'Tasks')]},
    {'key': 'reports', 'title': 'Reports & workflows', 'image': '/walk/reports.png',
     'blurb': 'A report is a scheduled check that reads and summarises. A workflow is the one that '
              'writes. Both file what they find onto the Timeline on their own schedule.',
     'goto': _goto('Reports'), 'can': [
        _can('schedule a check that reads and summarises', 'Reports', 'report=new'),
        _can('build a workflow that writes back to a system', 'Reports'),
        _can('say whether a run reaches you every time, or only when it is wrong', 'Reports'),
        _can('preview one before it is saved', 'Reports')]},
    {'key': 'assistant', 'title': 'The Assistant', 'image': '/walk/assistant.png',
     'blurb': 'Where you actually work. Everything that arrived is a pile, oldest pressure first, '
              'and Next takes you through it one item at a time. This walk is happening in it.',
     'goto': _goto('Assistant'), 'can': [
        _can('press Next and go through what is waiting'),
        _can('reply, or hand the item to an agent'),
        _can('say it is not ours - and triage remembers that'),
        _can('ask anything in your own words')]},
    {'key': 'hub', 'title': 'Hub', 'image': '/walk/hub.png',
     'blurb': 'What the company knows, in one place - the durable posts, the people, the systems. '
              'It is where something goes when it outlives the thread it arrived in.',
     'goto': _goto('Hub'), 'can': [
        _can('read what has been posted', 'Hub'),
        _can('post something worth keeping', 'Hub'),
        _can('search across everything Taskuary has read', 'Hub')]},
]

def _live(store) -> list:
    return [c['Name'] or c['Type'] for c in store.list_connectors()
            if c['Active'] and c['Type'] in setup.INBOUND]


# One read per fact: each of these used to be a lambda that called its source three times, so
# drawing a single stop swept the connector table three times over.
def _fact_connections(s) -> str:
    live = _live(s)
    return f'{len(live)} connected: ' + ', '.join(live[:3]) if live else 'none yet'


def _fact_tasks(s) -> str:
    """...and the replies waiting on this stop, now that a draft waits on the task it belongs to
    rather than in a queue of its own (the Review stop retired with the tab, 2026-09-22)."""
    tasks, waiting = s.list_tasks(), [r for r in s.list_reviews(None) if r.get('Status') == 'pending']
    here = f'{len(tasks)} here so far' if tasks else 'none yet'
    return here + (f' · {len(waiting)} repl{"y" if len(waiting) == 1 else "ies"} waiting for your yes' if waiting else '')


def _named(rows, key='Name', n=3) -> str:
    """`3 things: a, b, c` - a count leads because it is the answer, the names follow because a
    number alone does not tell you whether it is the right three."""
    names = [str(r[key]) for r in rows if r.get(key)]
    return f"{len(names)}: {', '.join(names[:n])}" + ('…' if len(names) > n else '') if names else 'none yet'


def _fact_ai(s) -> str:
    """Every brain that could answer, not just the one that does - "running on Azure" above a stop
    offering four roads reads as though the other three are unavailable."""
    # through setup, never through llm: this module may not reach a model, and a test pins that by
    # reading its source. setup already owns which card types can answer a prompt.
    live = [c for c in s.list_connectors() if c['Type'] in setup.AI_TYPES and c['Active'] and c['HasSecret']]
    return _named(live)


def _brain_name(s, value: str) -> str:
    """A setting reads `connector:80` or `cli:coder`; neither is a thing the owner named. Resolved
    HERE and not through aidefaults.state, which needs the live config.toml this does not have."""
    v = str(value or '').strip()
    if not v: return 'auto'
    if v.startswith('cli:'): return v[4:]
    if v.startswith('connector:') and v[10:].isdigit():
        row = s.get_connector(int(v[10:]))
        return (row['Name'] or row['Type']) if row else v
    return v


def _fact_models(s) -> str:
    st = s.get_settings()
    return ', '.join(f'{label}: {_brain_name(s, st.get(key))}' for label, key in
                     (('triage', 'triage_ai'), ('assistant', 'concierge_ai'), ('general', 'assistant_ai')))


def _fact_sync(s) -> str:
    waiting = s.pending_triage(limit=200)
    return f'{len(waiting)} waiting to be triaged' if waiting else 'nothing waiting'


def _fact_docs(s) -> str:
    profiles = {(r.get('rules_doc') or r['Name']) for r in s.list_agents()}
    return f"{len(profiles)} profile documents: {', '.join(sorted(profiles)[:3])}" if profiles else 'none yet'


def _fact_board(s) -> str:
    return _named(s.list_agents())


def _fact_reports(s) -> str:
    """The stop names two things, so the fact answers for both: a report READS, a workflow WRITES,
    and "3 reports" on a card about both leaves you wondering which three (the owner, 2026-09-17:
    "for reports show the reports setup and workflows")."""
    import json as _json
    reports, flows = [], []
    for row in s.list_sources():
        if row['Channel'] != 'report': continue
        try: cfg = _json.loads(row['ConfigJson'] or '{}')
        except ValueError: cfg = {}
        (flows if cfg.get('is_workflow') else reports).append(cfg.get('title') or row['Address'] or '')
    if not reports and not flows: return 'none yet'
    said = []
    if reports: said.append(f"{len(reports)} reports: {', '.join(x for x in reports[:3] if x)}")
    if flows: said.append(f"{len(flows)} workflows: {', '.join(x for x in flows[:3] if x)}")
    return ' · '.join(said)


def _fact_assistant(s) -> str:
    return f"speaking on {_brain_name(s, s.get_settings().get('concierge_ai'))}"


def _fact_hub(s) -> str:
    posts = s.lore_posts(None, None, 200, 'new', 'live', None)
    return f'{len(posts)} posted so far' if posts else 'nothing posted yet'


def _fact_settings(s) -> str:
    on = [k for k in ('triage_ai', 'default_agent', 'notify_channel') if str(s.get_settings().get(k) or '').strip()]
    return f"{len(on)} of the three headline settings chosen" if on else 'all on their defaults'


# What THIS install has done, for EVERY stop - the walk is a tour of an install, not of the product,
# and a stop that could not say what you already have made you go and look (the owner, 2026-09-17:
# "for each step it should include if step was already completed and what is setup for each step").
# The five checklist stops carry `detail` from setup.state as well; these add what that cannot say.
FACTS = {'ai': _fact_ai, 'models': _fact_models, 'sync': _fact_sync,
         'connections': _fact_connections, 'docs': _fact_docs, 'settings': _fact_settings,
         'board': _fact_board, 'tasks': _fact_tasks,
         'reports': _fact_reports, 'assistant': _fact_assistant, 'hub': _fact_hub}


def state(store, at=None) -> dict:
    """The whole walk: every stop, with the checklist's own done-ness on the first five and this
    install's facts wherever a fact beats a sentence."""
    if at is None: at = _at(store)
    steps = {x['key']: x for x in setup.state(store)['steps']}
    stops = []
    for n, stop in enumerate(STOPS):
        o = dict(stop, n=n)
        row = steps.get(stop['key'])
        # the checklist owns these words; a copy here would be the second one that goes stale
        # `goto` is here too: a hand-written copy beside the checklist's is the one field of the
        # five that could drift without a word of the stop changing
        if row: o.update(done=row['done'], detail=row['detail'], blurb=row['why'], title=row['title'], goto=row['goto'])
        fact = FACTS.get(stop['key'])
        # A COUNTER MUST NEVER TAKE THE WALK DOWN. These read a dozen different tables, and the one
        # install that most needs the walk is the half-configured one where some of those reads
        # throw. A stop that cannot count simply says nothing, which is what it did before it could.
        if fact:
            try: o['facts'] = fact(store)
            except Exception as e: logger.warning(f"the {stop['key']} stop could not read its facts: {e}")
        stops.append(o)
    return {'stops': stops, 'at': at, 'total': len(STOPS)}


def _at(store) -> int:
    """Where they stopped - clamped, because a stored number outlives the list it indexed and a
    stop that was removed must not strand the walk off the end of it."""
    try: n = int(str(store.get_settings().get(AT) or 0))
    except ValueError: return 0
    return n if 0 <= n < len(STOPS) else 0


def go(store, at: int, actor: str) -> dict:
    """Move. Walking off the end is finishing: the position clears, so the next press starts over
    rather than reopening the last card forever."""
    at = int(at)
    store.set_setting(AT, str(at if 0 <= at < len(STOPS) else 0), actor)
    return state(store)


def reset(store, actor: str) -> dict:
    store.set_setting(AT, '0', actor)
    return state(store)

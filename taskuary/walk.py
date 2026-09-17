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
from . import setup

AT = 'setup_walk_at'                 # where the owner stopped; a setting, so a reload resumes


def _goto(tab, hash_=''): return {'tab': tab, 'hash': hash_}
def _can(text, tab=None, hash_=''): return {'text': text, 'goto': _goto(tab, hash_) if tab else None}


# The five the checklist also shows, then every part of the app. The first five carry no `title`
# or `blurb` of their own - `setup.state` owns their words, and repeating them here is the drift
# this avoids.
STOPS = [
    {'key': 'owner', 'goto': _goto('Docs', 'owner'), 'can': [
        _can('type your name and email right here'),
        _can('see every document that uses it', 'Docs')]},
    {'key': 'ai', 'goto': _goto('Connections', 'cli-agents'), 'can': [
        _can('install a coding CLI and sign in to it, in a terminal right here', 'Connections', 'cli-agents'),
        _can('use a CLI you already pay for', 'Connections', 'cli-agents'),
        _can('paste an API key on a provider card instead', 'Connections')]},
    {'key': 'models',
     'goto': _goto('Settings', 'settings=config&group=Triage%20%26%20agents'), 'can': [
        _can('choose the brain that triages your mail', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose what the assistant here speaks on', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose the general agent and the coding CLI', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('name a model, or leave it on the provider default')]},
    {'key': 'inbound', 'goto': _goto('Connections'), 'can': [
        _can('connect a mailbox - Outlook, Gmail, or any IMAP host', 'Connections'),
        _can('connect a chat - Teams, Slack, WhatsApp, Telegram', 'Connections'),
        _can('test a card before waiting on a schedule', 'Connections')]},
    {'key': 'sync', 'goto': _goto('Assistant'), 'can': [
        _can('pull your mail in and let triage read it', 'Connections'),
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
     'goto': _goto('Docs'), 'can': [
        _can('make SOUL.md yours - your work, boundaries, systems, people, voice', 'Docs'),
        _can('generate STYLE.md from the messages you have sent', 'Docs'),
        _can('generate TRIAGE.md from what you answered and what you let sit', 'Docs'),
        _can('read COUNSEL.md, which is the voice the assistant speaks in', 'Docs')]},
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
        _can('close it - which is yours, never the agent\'s', 'Tasks')]},
    {'key': 'review', 'title': 'Review', 'image': '/walk/review.png',
     'blurb': 'Replies drafted in your voice, waiting on you. Nothing sends until you approve it - '
              'there is no setting that changes that.',
     'goto': _goto('Review'), 'can': [
        _can('approve a draft and send it', 'Review'),
        _can('edit it first, or ask for it again differently', 'Review'),
        _can('say it is not yours, which triage remembers', 'Review')]},
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

# What THIS install has done, for the stops where a number is worth more than a sentence. Keyed by
# stop; a stop with no entry simply carries no `facts`.
FACTS = {
    'connections': lambda s: (f'{len(_live(s))} connected: ' + ', '.join(_live(s)[:3])) if _live(s) else 'none yet',
    'tasks': lambda s: f'{len(s.list_tasks())} here so far' if s.list_tasks() else 'none yet',
}


def _live(store) -> list:
    return [c['Name'] or c['Type'] for c in store.list_connectors()
            if c['Active'] and c['Type'] in setup.INBOUND]


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
        if row: o.update(done=row['done'], detail=row['detail'], blurb=row['why'], title=row['title'])
        fact = FACTS.get(stop['key'])
        if fact: o['facts'] = fact(store)
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

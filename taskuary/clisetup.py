"""Setting a coding CLI up: its own first run, in a pane Taskuary hosts.

The Install button removed the first dead end and landed on the next one. A CLI installed sixty
seconds ago has never been run - no theme, no trusted folder, no account - so the wizard's
Add & test failed, and `agents.signed_out_msg` told the owner to "open a terminal", about an app
that has had a real interactive pty all along.

WHAT OPENS IS THE CLI, PLAIN. Every one of these ships an onboarding that asks for what it needs -
recommended settings, then the sign-in - and it asks better than we could ask on its behalf. An
earlier draft of this drove one slice of that from outside, typing `/login` into the box off a
per-CLI table of login recipes. Letting the CLI run itself deleted the table: `codex login` and a
typed `/login` were two shapes of the same thing, and the thing is "just start it".

So the only per-CLI knowledge left is WHICH NAMES may be started, and that stays closed for the
reason cliinstall.RECIPES is closed: this runs a program on the owner's machine.

A set-up IS a setup task, for the reasons aisetup already argues: the owner types secrets into it,
so nothing is filed on the task; Done is a plain close (coder.wrap routes Kind='setup' to
aisetup.finish); and it belongs on the Board, because an agent working is an agent working
wherever it started.

THE ONE DIVERGENCE from aisetup: it needs a configured agent profile, and the CLI this exists for
has none - the profile is what Add & test writes, one step later. So the binary comes from
cliinstall.find (which looks past this process's stale PATH), and the pane is a Term built here
rather than terminal.open_session. open_session resolves profiles, guesses checkouts, installs
hooks, tells the peer blackboard - and PRE-TRUSTS the folder, which exists to stop a headless
agent parking on the trust dialog. Here the owner is sitting in front of it, and that dialog is
part of the setup they came to do. agent=None keeps the pane off the blackboard and off the roster.
"""
from . import aisetup, cliinstall, config

KIND = aisetup.KIND                   # a set-up is a setup task, and Done already knows it
finish = aisetup.finish               # ...so its ending is aisetup's, unchanged

# The CLIs whose first run Taskuary will open. Closed, and keyed by RECIPE name (cursor, not
# cursor-agent) so this, cliinstall.RECIPES and clis.detect's `install` field all agree. aider is
# not here: it takes an API key in a config file and has no interactive setup to walk.
SETUP = frozenset({'claude', 'codex', 'gemini', 'copilot', 'cursor'})


def tag(name: str) -> str: return f'cli:{name}'


def argv(name: str) -> list:
    """What to start, or ValueError. Just the CLI: it runs its own onboarding, and anything we
    added on top would be us guessing at a conversation it is about to have properly.

    The binary is FOUND, never assumed - this server keeps the PATH it was launched with, and the
    install may be a minute old."""
    if name not in SETUP: raise ValueError(f'{name} is not one of the CLIs Taskuary can set up ({", ".join(sorted(SETUP))})')
    found = cliinstall.find(name)
    if not found: raise ValueError(f'{name} is not on this machine yet - install it first')
    return [found]


def live_for(store, name: str):
    """The open set-up for this CLI, if there is one - a second press reattaches rather than
    starting a second one beside it."""
    from . import terminal as term
    for t in list(term.SESSIONS.values()):
        if not (t.alive and t.task_id): continue
        tk = store.get_task(t.task_id) or {}
        if tk.get('Kind') == KIND and tag(name) in str(tk.get('Tags') or ''): return {**t.info(), 'taskId': t.task_id}
    return None


def start(store, name: str, actor: str = 'owner', label: str = '') -> dict:
    """Open the CLI on a setup task and get out of the way. It asks for what it needs; the owner
    answers it in the pane, where they can see what they are typing and to whom."""
    from . import terminal as term
    live = live_for(store, name)
    if live: return {**live, 'existing': True}
    cmd, what = argv(name), label or name             # resolve first: no task to close if there is no CLI
    tid = store.create_task({'Title': f'Set up {what}', 'Kind': KIND, 'Status': 'in_progress', 'Tags': tag(name),
                             'Summary': f'{what} runs its own setup in a live session here - settings, then the sign-in.'}, actor)
    # no checkout: the pane sits in Taskuary's own folder, and agent=None keeps it off the peer
    # blackboard and out of the worker roster - it is not doing anyone's work
    t = term.Term(cmd, str(config.home()), name, tid, None, 32, 110, store)
    t.keep_transcript = False                         # the owner types an account and a token into this one
    term.SESSIONS[t.sid] = t
    store.add_comment(tid, actor, 'human', f'{what} is being set up in a live session.')
    store.audit('terminal', tid, 'cli_setup', actor, detail={'name': name, 'sid': t.sid})
    return {**t.info(), 'taskId': tid, 'existing': False}

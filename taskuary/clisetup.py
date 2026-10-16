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
so nothing is filed on the task; Done is a plain close (wrapup.wrap routes Kind='setup' to
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
open_task = aisetup.open_task         # ...and so is reusing the task a dead pane left (TQ-0726)

# The CLIs whose first run Taskuary will open. Closed, and keyed by RECIPE name (cursor, not
# cursor-agent) so this, cliinstall.RECIPES and clis.detect's `install` field all agree. A CLI
# that only takes an API key out of a config file has no first run to open, and does not belong
# on this tab at all - a key is the connectors' door, not this one (aider, removed 2026-09-11).
# muse belongs here for the usual reason: its first run opens a browser sign-in against a Meta
# developer account and mints the CLI's own key, and that is exactly the conversation this pane
# exists to let the owner have. argv() still refuses it when the binary is absent, which on
# Windows it always will be.
# devin belongs here twice over: its installer already tried to run `devin setup` and could not
# (no terminal), and its sign-in is a browser round trip that falls back to pasting a token back
# into the CLI - a conversation that needs the pane, not a spawn nobody can see.
SETUP = frozenset({'claude', 'codex', 'gemini', 'qwen', 'opencode', 'kimi', 'copilot', 'cursor', 'muse', 'devin'})


# ...except the sign-in itself, where the CLI has a command for exactly that: plain Codex led with its own "Update available"
# menu and the sign-in came somewhere after it (the owner, 2026-10-15). Gemini has none, so it opens plain.
LOGIN = {'codex': ['login'], 'claude': ['auth', 'login']}


def tag(name: str) -> str: return f'cli:{name}'


def command(name: str, login: bool = False) -> list: return argv(name) + (LOGIN.get(name, []) if login else [])


# ...and whether it IS signed in, asked of the CLI itself: its status command's exit code. A check that failed for any reason
# said "needs you to sign in", so a sign-in that had just said "Successfully logged in" was sent straight back to sign in
# again (the owner, 2026-10-15). Never read off an error's words.
STATUS = {'codex': ['login', 'status'], 'claude': ['auth', 'status']}


def signed_in(name: str):
    """True or False by the CLI's own answer; None when it has no status command or it would not run."""
    if name not in STATUS: return None
    from . import spawn
    try: return spawn.run(argv(name) + STATUS[name], capture_output=True, timeout=30).returncode == 0
    except Exception: return None


def argv(name: str) -> list:
    """What to start, or ValueError. Just the CLI: it runs its own onboarding, and anything we
    added on top would be us guessing at a conversation it is about to have properly.

    The binary is FOUND, never assumed - this server keeps the PATH it was launched with, and the
    install may be a minute old. And found is not enough: an npm install missing its platform
    binary opens as a stack trace in the pane (TQ-0726), so a copy that does not start is refused
    here, with the vendor's reason and the button that repairs it."""
    if name not in SETUP: raise ValueError(f'{name} is not one of the CLIs Taskuary can set up ({", ".join(sorted(SETUP))})')
    if not cliinstall.find(name) and not cliinstall.local(name): raise ValueError(f'{name} is not on this machine yet - install it first')
    found, why = cliinstall.working(name)
    if not found: raise ValueError(f'{name} is on this machine but does not start ({why}) - press Update on its row to reinstall it')
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


def start(store, name: str, actor: str = 'owner', label: str = '', login: bool = False) -> dict:
    """Open the CLI on a setup task and get out of the way. It asks for what it needs; the owner
    answers it in the pane, where they can see what they are typing and to whom."""
    from . import terminal as term
    live = live_for(store, name)
    if live: return {**live, 'existing': True}
    cmd, what = command(name, login), label or name             # resolve first: no task to close if there is no CLI
    tid = open_task(store, tag(name), f'Set up {what}') or store.create_task(
        {'Title': f'Set up {what}', 'Kind': KIND, 'Status': 'in_progress', 'Tags': tag(name),
         'Summary': f'{what} runs its own setup in a live session here - settings, then the sign-in.'}, actor)
    # no checkout: the pane sits in Taskuary's own folder, and agent=None keeps it off the peer
    # blackboard and out of the worker roster - it is not doing anyone's work
    t = term.Term(cmd, str(config.home()), name, tid, None, 32, 110, store)
    t.keep_transcript = False                         # the owner types an account and a token into this one
    term.SESSIONS[t.sid] = t
    store.add_comment(tid, actor, 'human', f'{what} is being set up in a live session.')
    store.audit('terminal', tid, 'cli_setup', actor, detail={'name': name, 'sid': t.sid})
    return {**t.info(), 'taskId': tid, 'existing': False}

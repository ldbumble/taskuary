"""The Sign in button for the coding CLIs: finish a CLI's own OAuth in a pane Taskuary hosts.

The Install button removed the first dead end and landed on the next one. A CLI installed sixty
seconds ago has no credentials, so the wizard's Add & test fails - and `agents.signed_out_msg`
told the owner to "open a terminal", about an app that has had a real interactive pty all along.

A sign-in IS a setup task, for the reasons aisetup already argues: the owner types secrets into
it, so nothing is filed on the task; Done is a plain close (coder.wrap routes Kind='setup' to
aisetup.finish); and it belongs on the Board, because an agent working is an agent working
wherever it started.

WHAT IT STARTS is a closed table, like cliinstall.RECIPES: this runs a process and types into it.
Two shapes, because the CLIs differ in a way nothing can infer - a subcommand (`codex login`), or
an interactive session with `/login` typed into its box once it is proven to be listening.

THE ONE DIVERGENCE from aisetup: it needs a configured agent profile, and the CLI this exists for
has none - the profile is what Add & test writes, three steps later. So the binary comes from
cliinstall.find (which looks past this process's stale PATH), and the pane is a Term built here
rather than terminal.open_session, which resolves profiles, guesses checkouts, pre-trusts folders,
installs hooks and tells the peer blackboard. A sign-in wants none of that, and agent=None is what
keeps it off the blackboard and out of the worker roster.
"""
from . import aisetup, cliinstall, config

KIND = aisetup.KIND                   # a sign-in is a setup task, and Done already knows it
finish = aisetup.finish               # ...so its ending is aisetup's, unchanged

# name -> how that CLI's sign-in starts. `args` go on the command line; `type` is typed into the
# box after Term.seed proves it is listening. Keyed by RECIPE name (cursor, not cursor-agent), so
# this table, cliinstall.RECIPES and clis.detect's `install` field all agree. Verified 2026-09-09.
RECIPES = {
    'claude':  {'args': [], 'type': '/login'},
    'copilot': {'args': [], 'type': '/login'},
    'codex':   {'args': ['login'], 'type': ''},
    'cursor':  {'args': ['login'], 'type': ''},
    'gemini':  {'args': [], 'type': ''},     # a plain interactive run opens Google's page itself
}


def tag(name: str) -> str: return f'cli:{name}'


def argv(name: str) -> list:
    """What starts this CLI's sign-in, or ValueError. The binary is FOUND, never assumed: this
    server keeps the PATH it was launched with, and the install may be a minute old."""
    r = RECIPES.get(name)
    if not r: raise ValueError(f'{name} is not one of the CLIs Taskuary can sign in ({", ".join(sorted(RECIPES))})')
    found = cliinstall.find(name)
    if not found: raise ValueError(f'{name} is not on this machine yet - install it first')
    return [found, *r['args']]


def live_for(store, name: str):
    """The open sign-in for this CLI, if there is one - a second press reattaches rather than
    starting a second OAuth flow beside the first."""
    from . import terminal as term
    for t in list(term.SESSIONS.values()):
        if not (t.alive and t.task_id): continue
        tk = store.get_task(t.task_id) or {}
        if tk.get('Kind') == KIND and tag(name) in str(tk.get('Tags') or ''): return {**t.info(), 'taskId': t.task_id}
    return None


def start(store, name: str, actor: str = 'owner', label: str = '') -> dict:
    """Open the CLI's own sign-in on a setup task. Nothing is typed for the owner but the CLI's
    own `/login`: the credentials are theirs to enter, in the pane, where they can watch them go."""
    from . import terminal as term
    live = live_for(store, name)
    if live: return {**live, 'existing': True}
    cmd, what = argv(name), label or name             # resolve first: no task to close if there is no CLI
    tid = store.create_task({'Title': f'Sign in to {what}', 'Kind': KIND, 'Status': 'in_progress', 'Tags': tag(name),
                             'Summary': f'{what} opens its own sign-in in a live session here.'}, actor)
    # no checkout: the pane sits in Taskuary's own folder, and agent=None keeps it off the peer
    # blackboard and out of the worker roster - it is not doing anyone's work
    t = term.Term(cmd, str(config.home()), name, tid, None, 32, 110, store)
    t.keep_transcript = False                         # the owner types a token into this one
    term.SESSIONS[t.sid] = t
    if RECIPES[name]['type']: t.seed(RECIPES[name]['type'])
    store.add_comment(tid, actor, 'human', f'{what} is signing in, in a live session.')
    store.audit('terminal', tid, 'cli_login', actor, detail={'name': name, 'sid': t.sid})
    return {**t.info(), 'taskId': tid, 'existing': False}

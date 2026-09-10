# CLI setup — spec

**Status:** agreed 2026-09-09 (Uri), after `c4b707c` shipped the Install button.
**Corrected 2026-09-09** — see "The correction" below. Built as `taskuary/clisetup.py`.
**Plan:** `docs/superpowers/plans/2026-09-09-cli-sign-in.md` (written against the pre-correction design; kept for the record, superseded by this file).

## The problem

`c4b707c` gave the wizard and the agents page an **Install** button, so a machine with no Node
can get `claude` onto it without the owner opening a terminal. That removed the first dead end
and landed square on the next one: a CLI installed sixty seconds ago **has never been run** — no
theme, no trusted folder, no account. The wizard runs *Add & test* the instant an install
finishes, the test fails, and `agents.py:245` said:

> `claude` is signed out on this machine (…). **Open a terminal**, run `claude`, type `/login`,
> then come back here and try again.

That sentence is wrong about its own app. `taskuary/terminal.py` has had a real interactive pty
all along — ConPTY via pywinpty on Windows, stdlib `pty` on POSIX, with `write()` — which is how
every session on the Board works. Taskuary can host the setup; nobody wired it up.

## The correction

The first version of this design was **sign-in shaped**: a per-CLI table of login recipes, and
`/login` typed into the box. Uri's correction — *"why do you have a sign in button. it should just
be a cli pops up that you have to setup like normal. They ask you recommended settings, login
etc.."* — is the right one, and the code proves it: **the moment the CLI runs itself, the table
collapses.** `codex login` and a typed `/login` were two shapes of the same thing, and the thing
is "just start it". What survives is a single closed set of names.

So: **what opens is the CLI, plain.** Each of these ships an onboarding that asks for what it
needs — recommended settings, then the sign-in — and it asks better than we can ask on its behalf.
Nothing is typed for the owner.

This also fixes something the login design got backwards. `terminal.open_session` calls
`pretrust()`, which writes the trust/theme answers so a *headless* agent does not park on a first-run
dialog. Those dialogs are exactly the setup the owner came to do, so this path must not pretrust —
and it does not, because it bypasses `open_session` for other reasons anyway.

## What we're building

**A CLI set-up is an `aisetup`-shaped setup task whose session is the CLI itself, interactive.**

Uri's framing, and the one the codebase already agrees with: *"you are making a coding session
like a task spawn… maybe it will show up on tasks and board as setup coding window."* Two
objections were raised against making it a real Task and both turned out to be already handled:

- **`Done` would draft a reply to nobody.** It does not — `coder.py:268` routes `Kind == 'setup'`
  to `aisetup.finish`, *"a plain close — no report, no proposals, no reply draft."*
- **A transcript full of typed secrets would be filed on the task.** It is not —
  `Term.keep_transcript = False` exists for exactly this, and `keep()` returns early on it.
  `aisetup`'s own docstring argues the position: *"a task record is not where secrets live"*, and
  *"it is a task on the Board too, because an agent working is an agent working wherever it
  started."*

Because it is a task, the Board needs **no change at all**: `WallView.jsx:65` filters on
`s.alive && s.taskId`, and a setup task has a taskId. The pane's Done button posts `/wrap`, which
routes to `aisetup.finish`. An earlier draft added a `Term.kind` field plus a wall filter and
header branch — dropped: ~15 lines in the most delicate file in the UI, for nothing.

## The closed set

`clisetup.SETUP = {'claude', 'codex', 'gemini', 'copilot', 'cursor'}` — closed for the same reason
`cliinstall.RECIPES` is closed: this runs a program on the owner's machine, and an open field
would be "run anything here" wearing a button's clothes. Keyed by **recipe name** (`cursor`, not
`cursor-agent`) so it lines up with `cliinstall.RECIPES` and `clis.detect`'s `install` field.

`aider` is deliberately absent: it takes an API key in a config file and has no interactive setup
to walk.

There are no per-CLI arguments. `argv(name)` is `[cliinstall.find(name)]`.

## The one real divergence from `aisetup`

`aisetup.start` requires a configured agent profile (`store.get_agent(agent)`, raising *"no CLI
agent named …"*) and calls `terminal.open_session`. **A just-installed CLI has no profile** — the
profile is what *Add & test* writes, one step later. So:

- the binary is resolved with **`cliinstall.find(name)`**, which looks past this process's stale
  PATH into the places installers actually put things (a GUI app keeps the environment it was
  launched with);
- the pane is a **`terminal.Term` built directly**, registered in `terminal.SESSIONS`, rather than
  `open_session` — which resolves profiles, guesses checkouts, refuses ambiguous repos, pre-trusts
  folders (wrong here, see above), installs Claude hooks and posts to the peer blackboard. A
  set-up wants none of it, and `agent=None` keeps the session off the peer blackboard
  (`terminal.py:208`) and out of the worker roster.

## Surface

**`POST /api/cli/setup {name}` → `{sid, taskId, existing, …}`**, on `guard.DENIED` beside
`/api/cli/install`: an agent reads untrusted mail, and an agent that can run a CLI's setup on the
owner's machine — signing in as them — can be talked into running one. `live_for` makes a second
press **reattach** rather than open a second pane. A name outside the set, or a CLI not on the
machine, is a 422.

**`GET /api/cli/detect`** rows carry `setup` (the recipe name, or `''`), so the UI never draws a
button over a road that does not exist — the same rule `installable` already follows.

**Task:** `Title: "Set up Claude Code"`, `Kind: 'setup'`, `Status: 'in_progress'`,
`Tags: 'cli:claude'`, cwd `config.home()` (no checkout to dirty). Ordinary on Tasks and the Board.

**`agents._LOGIN_HOW`** grows from two entries to five, and `signed_out_msg` names the button
instead of sending the owner to a terminal — keeping the terminal road as the fallback clause,
since it is still true and is the only road when the app is not what is in front of you. It maps
the **profile** to its CLI first: the name it receives is a profile name (`coder`), so the old
`_LOGIN_HOW.get('coder')` missed for everybody, always. The call site has the resolved `cmd` in
scope; `cliinstall.recipe_for(cmd[0])` is the mapping. **This was a live bug**, independent of
this feature.

## The walk

```
Install ──▶ the CLI pops up and runs its own setup ──▶ test passes ──▶ "claude answered"
                 │   (settings, then the sign-in)                     task stays open,
                 │                                                    owner presses Done
                 └── still not working ──▶ "…— the pane is above"
```

Decided 2026-09-09: **the wizard tests when the owner says they are done, and the owner still
presses Done.** It does not close the pane or the task — a pane must not vanish while its owner is
mid-setup, and a stray green test must not close a session somebody wanted open. Done is theirs,
and it already does the right thing.

The wizard's `getAndUse` stops running the test immediately after an install **when the CLI has a
setup road**; it hands off to the pane instead. That auto-test is the dead end this fixes.

## Out of scope

- Any change to `WallView.jsx` or `Term` (the task route makes both unnecessary).
- Detecting *"this CLI is signed out"* on the agents page. **Set it up** is offered whenever a CLI
  is installed and in the set — an honest, always-legitimate action — rather than gated on a
  signed-out signal the page does not have.
- Non-interactive/API-key auth (`aider`, `ANTHROPIC_API_KEY`): a different door, unchanged.

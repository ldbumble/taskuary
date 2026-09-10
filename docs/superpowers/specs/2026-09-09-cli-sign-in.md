# CLI sign-in — spec

**Status:** agreed 2026-09-09 (Uri), after `c4b707c` shipped the Install button.
**Plan:** `docs/superpowers/plans/2026-09-09-cli-sign-in.md`

## The problem

`c4b707c` gave the wizard and the agents page an **Install** button, so a machine with no Node
can get `claude` onto it without the owner opening a terminal. That removed the first dead end
and landed square on the next one: a CLI installed sixty seconds ago has **no credentials**. The
wizard runs *Add & test* the instant an install finishes, the test fails, and `agents.py:245`
says:

> `claude` is signed out on this machine (…). **Open a terminal**, run `claude`, type `/login`,
> then come back here and try again.

That sentence is wrong about its own app. `taskuary/terminal.py` has had a real interactive pty
all along — ConPTY via pywinpty on Windows, stdlib `pty` on POSIX, with `write()` — which is how
every session on the Board works. Taskuary can host a sign-in; nobody wired it up.

## What we're building

**A CLI sign-in is an `aisetup`-shaped setup task whose session is the CLI itself, interactive.**

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
routes to `aisetup.finish`. The earlier draft of this design — a task-less pane plus a `Term.kind`
field plus a wall filter and header branch — is dropped. It was ~15 lines in the most delicate
file in the UI, bought nothing, and this route makes it unnecessary.

## The table

Closed, for the same reason `cliinstall.RECIPES` is closed: this starts a process and types into
it, and an open field would be "run anything on this machine" wearing a button's clothes. Keyed
by **recipe name** (`cursor`, not `cursor-agent`) so it lines up with `cliinstall.RECIPES` and
`clis.detect`'s `install` field. Verified against each vendor's CLI, 2026-09-09.

| name | how its sign-in starts | shape |
|---|---|---|
| `claude` | interactive session, then type `/login` | `{'args': [], 'type': '/login'}` |
| `copilot` | interactive session, then type `/login` | `{'args': [], 'type': '/login'}` |
| `codex` | `codex login` | `{'args': ['login'], 'type': ''}` |
| `cursor` | `cursor-agent login` | `{'args': ['login'], 'type': ''}` |
| `gemini` | a plain interactive run opens Google's page itself | `{'args': [], 'type': ''}` |

`aider` is in `clis.KNOWN` and gets no row: it is API-key based, and there is nothing to sign in.

## The one real divergence from `aisetup`

`aisetup.start` requires a configured agent profile (`store.get_agent(agent)`, raising *"no CLI
agent named …"*) and calls `terminal.open_session`. **A just-installed CLI has no profile** — the
profile is what *Add & test* writes, three steps later. So:

- the binary is resolved with **`cliinstall.find(name)`**, which looks past this process's stale
  PATH into the places installers actually put things (a GUI app keeps the environment it was
  launched with);
- the pane is a **`terminal.Term` built directly**, registered in `terminal.SESSIONS`, rather than
  `open_session`. `open_session` resolves profiles, guesses checkouts, refuses ambiguous repos,
  pre-trusts folders, installs Claude hooks and posts to the peer blackboard. A sign-in wants none
  of it, and `agent=None` is what keeps the session off the peer blackboard (`terminal.py:208`)
  and out of the worker roster.

This seam — profile-less start — is the part to write tests around first.

## Surface

**`POST /api/cli/login {name}` → `{sid, taskId, existing, …}`**, on `guard.DENIED` beside
`/api/cli/install`: an agent reads untrusted mail, and an agent that can start an OAuth flow on
the owner's machine can be talked into starting one. `live_for` makes a second press **reattach**
rather than open a second flow. A name outside the table, or a CLI not on the machine, is a 422.

**`GET /api/cli/detect`** rows grow a `login` field (the recipe name, or `''`), so the UI never
draws a button over a road that does not exist — the same rule `installable` already follows.

**Task:** `Title: "Sign in to Claude Code"`, `Kind: 'setup'`, `Status: 'in_progress'`,
`Tags: 'cli:claude'`, cwd `config.home()` (no checkout to dirty). Ordinary on Tasks and the Board.

**`agents._LOGIN_HOW`** grows from two entries to five, and `signed_out_msg` names the button
instead of sending the owner to a terminal. It must map the **profile** to its CLI first: the name
it receives is a profile name (`coder`), so today's `_LOGIN_HOW.get('coder')` already misses. The
call site has the resolved `cmd` in scope; `cliinstall.recipe_for(cmd[0])` is the mapping.

## The walk

```
Install ──▶ Sign in (pane) ──▶ test passes ──▶ "claude answered"
                 │                             task stays open,
                 │                             owner presses Done
                 └── still signed out ──▶ "still signed out — the pane is above"
```

Decided 2026-09-09: **the wizard auto-tests, the owner still presses Done.** While the pane is
open the wizard polls `POST /api/agents/{name}/test`; a pass moves the wizard on and says so. It
does **not** close the pane or the task — a pane must not vanish while its owner is mid-OAuth, and
a stray green test must not close a session somebody wanted open. Done is theirs, and it already
does the right thing.

The wizard's `getAndUse` stops running the test immediately after an install **when the CLI has a
login recipe**; it hands off to the pane instead. That auto-test is the dead end this fixes.

## Out of scope

- Any change to `WallView.jsx` or `Term` (the task route makes both unnecessary).
- Detecting *"this CLI is signed out"* on the agents page. **Sign in** is offered whenever a CLI is
  installed and has a login recipe — an honest, always-legitimate action — rather than gated on a
  signed-out signal the page does not have.
- Non-interactive/API-key auth (`aider`, `ANTHROPIC_API_KEY`): a different door, unchanged.

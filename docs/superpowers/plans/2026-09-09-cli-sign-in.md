# CLI sign-in Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish a coding CLI's own sign-in inside Taskuary — a live pane on an ordinary setup task — instead of telling the owner to open a terminal.

**Architecture:** A sign-in is an `aisetup`-shaped setup task (`Kind='setup'`), so `Done` already closes it without a report or reply draft and the Board already shows it. A new `taskuary/clilogin.py` holds a closed per-CLI table, resolves the binary with `cliinstall.find` and builds a `terminal.Term` directly — bypassing `open_session`, whose profile/checkout/hooks/blackboard work a sign-in wants none of. `POST /api/cli/login` sits on `guard.DENIED` beside `/api/cli/install`.

**Tech Stack:** Python 3.10+, FastAPI, `unittest` + `fastapi.testclient`; React 18 + MUI, `node --test` for the UI.

**Spec:** `docs/superpowers/specs/2026-09-09-cli-sign-in.md`

## Global Constraints

- **House style is Jeremy Howard / fast.ai density.** Match the surrounding files: tuple-unpacking assignments, one-line guards, comments that say *why*. Every module in this feature opens with a docstring that argues its own existence, like `cliinstall.py` and `aisetup.py` do.
- **The login table is closed.** Never derive a command from user input. A name outside `clilogin.RECIPES` is a 422, exactly as `cliinstall` does it.
- **Table keys are recipe names, not binaries**: `cursor`, never `cursor-agent` (`cliinstall.BINARY` maps one to the other).
- **Never file a sign-in transcript.** `t.keep_transcript = False` before anything is typed. The owner types tokens into this pane.
- **`agent=None` on the Term.** That is what keeps the pane off the peer blackboard (`terminal.py:208`) and out of the worker roster. Pass the CLI name as `label`.
- **Do not touch `WallView.jsx` or `Term`.** The task route makes both unnecessary; see the spec's "Out of scope".
- **Run the whole suite from the repo root before pushing** (`python -m pytest`), and `npm test` from `website/`. "No tests ran" is a failure.
- **Do not run an autoformatter** on any file in this feature.

## File Structure

| File | Responsibility |
|---|---|
| `taskuary/clilogin.py` | **Create.** The closed table, `argv`, `tag`, `live_for`, `start`; re-exports `aisetup.finish` as its ending. |
| `taskuary/server.py` | **Modify.** `CliLoginBody`, `POST /api/cli/login`, beside `cli_install` (~line 3952). |
| `taskuary/guard.py` | **Modify.** One `DENIED` row after the `/api/cli/install` row (line 65). |
| `taskuary/clis.py` | **Modify.** `detect()` rows gain `login`, in both loops. |
| `taskuary/agents.py` | **Modify.** `_LOGIN_HOW` five entries; `signed_out_msg` names the button and maps profile → recipe. |
| `website/src/cliLogin.js` | **Create.** Pure helpers the node test imports (`canSignIn`, `signInTitle`). |
| `website/src/cliLogin.jsx` | **Create.** `useCliLogin()` hook + `SignInButton`, beside `cliInstall.jsx`. |
| `website/src/SetupWizard.jsx` | **Modify.** Install → Sign in → Add & test; stop auto-testing a CLI that has a login recipe. |
| `website/src/AgentsPanel.jsx` | **Modify.** A Sign in button on an installed row that has a login recipe. |
| `tests/test_cli_login.py` | **Create.** The table, the seam, the endpoint, the guard. |
| `website/test/cliLogin.test.mjs` | **Create.** The pure helpers, and the wiring asserted against the JSX source. |

---

### Task 1: `clilogin.py` — the table and the profile-less start

**Files:**
- Create: `taskuary/clilogin.py`
- Test: `tests/test_cli_login.py`

**Interfaces:**
- Consumes: `cliinstall.find(name) -> str`, `cliinstall.RECIPES`, `aisetup.KIND` (`'setup'`), `aisetup.finish(store, tid, actor) -> dict`, `terminal.Term(argv, cwd, label, task_id, agent, rows, cols, store)`, `terminal.SESSIONS`, `config.home() -> Path`.
- Produces: `clilogin.RECIPES: dict`, `clilogin.KIND: str`, `clilogin.tag(name) -> str`, `clilogin.argv(name) -> list`, `clilogin.live_for(store, name) -> dict|None`, `clilogin.start(store, name, actor='owner', label='') -> dict`, `clilogin.finish` (alias of `aisetup.finish`).

- [ ] **Step 1: Write the failing tests for the table and `argv`**

Create `tests/test_cli_login.py`:

```python
"""Signing a coding CLI in, in a pane Taskuary hosts: what it may start, who may press it, and
what the session is allowed to keep.

Nothing here starts a real CLI. `Term` is faked in every test that reaches one - a suite that
spawns claude is a suite that opens an OAuth flow on whoever's machine it runs on.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import aisetup, clilogin, guard, server

c = TestClient(server.app)


class TableTests(unittest.TestCase):
    """This starts a process and types into it. An open field would be 'run anything here'."""

    def test_the_menu_is_closed(self):
        for bad in ('rm -rf /', 'some-cli-nobody-vetted', '', 'aider'):
            with self.assertRaises(ValueError): clilogin.argv(bad)

    def test_every_row_is_keyed_by_the_recipe_name_not_the_binary(self):
        """`cursor-agent` is the binary; `cursor` is the recipe, and what the UI holds."""
        from taskuary import cliinstall
        self.assertIn('cursor', clilogin.RECIPES)
        self.assertNotIn('cursor-agent', clilogin.RECIPES)
        for name in clilogin.RECIPES: self.assertIn(name, cliinstall.RECIPES, name)

    def test_the_two_shapes_are_the_ones_the_clis_actually_have(self):
        self.assertEqual(clilogin.RECIPES['codex']['args'], ['login'])
        self.assertEqual(clilogin.RECIPES['cursor']['args'], ['login'])
        self.assertEqual(clilogin.RECIPES['claude']['type'], '/login')
        self.assertEqual(clilogin.RECIPES['copilot']['type'], '/login')
        # gemini opens Google's page on a plain run: nothing on argv, nothing typed
        self.assertEqual(clilogin.RECIPES['gemini'], {'args': [], 'type': ''})

    def test_a_sign_in_ends_the_way_a_setup_task_ends(self):
        """No report, no proposals, no reply draft - coder.wrap routes Kind='setup' to this."""
        self.assertEqual(clilogin.KIND, aisetup.KIND)
        self.assertIs(clilogin.finish, aisetup.finish)


class ArgvTests(unittest.TestCase):
    """The seam: a CLI installed a minute ago has no profile, and this server's PATH predates it."""

    def test_the_binary_is_found_never_assumed(self):
        with mock.patch('taskuary.cliinstall.find', return_value=r'C:\x\codex.exe'):
            self.assertEqual(clilogin.argv('codex'), [r'C:\x\codex.exe', 'login'])

    def test_a_cli_that_is_not_here_yet_says_so_instead_of_starting_nothing(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            with self.assertRaises(ValueError) as e: clilogin.argv('claude')
        self.assertIn('install', str(e.exception).lower())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cli_login.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'clilogin'`.

- [ ] **Step 3: Write `taskuary/clilogin.py`**

```python
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
    own `/login`: the credentials are theirs to enter, in the pane, where they can see them go."""
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_login.py -x -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add taskuary/clilogin.py tests/test_cli_login.py
git commit -m "feat: a coding CLI's sign-in is a setup task with the CLI itself in the pane"
```

---

### Task 2: The endpoint, the guard, and the `login` flag the UI reads

**Files:**
- Modify: `taskuary/server.py` (beside `cli_install`, ~line 3952)
- Modify: `taskuary/guard.py:65` (after the `/api/cli/install` row)
- Modify: `taskuary/clis.py` — `detect()`, both append sites (~line 151 and ~line 165)
- Test: `tests/test_cli_login.py` (append)

**Interfaces:**
- Consumes: `clilogin.start`, `clilogin.RECIPES`, `clis.KNOWN`, `guard.DENIED`.
- Produces: `POST /api/cli/login {name} -> {sid, taskId, existing, ...}`; `GET /api/cli/detect` rows gain `login: str` (the recipe name, or `''`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_login.py`:

```python
class FakeTerm:
    """A pane that never spawns anything. Records what it was asked to type."""
    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110, store=None):
        self.argv, self.cwd, self.label, self.task_id, self.agent = argv, cwd, label, task_id, agent
        self.sid, self.alive, self.keep_transcript, self.seeded = 'fake123', True, True, None
    def seed(self, text): self.seeded = text
    def info(self, tail=0, details=True): return {'sid': self.sid, 'alive': True, 'label': self.label}


class EndpointTests(unittest.TestCase):
    def setUp(self):
        from taskuary import terminal as term
        self.term = mock.patch('taskuary.terminal.Term', FakeTerm); self.term.start()
        self.find = mock.patch('taskuary.cliinstall.find', return_value='/x/claude'); self.find.start()
        self.addCleanup(self.term.stop); self.addCleanup(self.find.stop)
        self.addCleanup(lambda: term.SESSIONS.pop('fake123', None))

    def test_it_opens_a_setup_task_the_board_will_show(self):
        r = c.post('/api/cli/login', json={'name': 'claude'})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()['taskId']
        task = server.store.get_task(tid)
        self.assertEqual(task['Kind'], 'setup')
        self.assertEqual(task['Status'], 'in_progress')
        self.assertIn('cli:claude', str(task['Tags']))
        self.assertIn('Claude Code', task['Title'])          # the label, not the bare recipe name

    def test_the_pane_keeps_no_transcript_and_types_the_login(self):
        from taskuary import terminal as term
        c.post('/api/cli/login', json={'name': 'claude'})
        t = term.SESSIONS['fake123']
        self.assertFalse(t.keep_transcript)                   # secrets are typed into this one
        self.assertEqual(t.seeded, '/login')
        self.assertIsNone(t.agent)                            # off the blackboard, off the roster

    def test_a_subcommand_cli_is_not_typed_into(self):
        from taskuary import terminal as term
        c.post('/api/cli/login', json={'name': 'codex'})
        self.assertIsNone(term.SESSIONS['fake123'].seeded)

    def test_a_second_press_reattaches_instead_of_starting_a_second_oauth(self):
        first = c.post('/api/cli/login', json={'name': 'claude'}).json()
        again = c.post('/api/cli/login', json={'name': 'claude'}).json()
        self.assertTrue(again['existing'])
        self.assertEqual(again['taskId'], first['taskId'])

    def test_an_unknown_cli_is_refused(self):
        self.assertEqual(c.post('/api/cli/login', json={'name': 'rm -rf /'}).status_code, 422)

    def test_a_cli_that_is_not_installed_is_refused(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            self.assertEqual(c.post('/api/cli/login', json={'name': 'claude'}).status_code, 422)


class GuardTests(unittest.TestCase):
    def test_an_agent_may_not_start_an_oauth_flow(self):
        """An agent reads untrusted mail. Starting a sign-in on the owner's machine is theirs."""
        why = guard.denied('POST', '/api/cli/login')
        self.assertTrue(why, 'POST /api/cli/login must be on guard.DENIED')

    def test_the_page_is_told_which_clis_can_be_signed_in(self):
        """A button is never drawn over a road that does not exist - `installable`'s own rule."""
        rows = c.get('/api/cli/detect').json()['data']
        self.assertTrue(rows)
        for row in rows:
            self.assertIn('login', row)
            if row['login']: self.assertIn(row['login'], clilogin.RECIPES)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_cli_login.py -x -q`
Expected: FAIL — 404 on `/api/cli/login`. (If `guard.denied` is not the helper's name, read `taskuary/guard.py` and use the real one; the DENIED table is the thing under test.)

- [ ] **Step 3: Add the endpoint**

In `taskuary/server.py`, immediately after the `cli_install_state` route:

```python
class CliLoginBody(BaseModel): name: str

@app.post('/api/cli/login')
def cli_login(body: CliLoginBody):
    """Open the CLI's own sign-in in a live pane, as a setup task on the Board.

    On guard.DENIED beside /api/cli/install: an agent reads untrusted mail, and an agent that can
    start an OAuth flow on this machine can be talked into starting one. A second press reattaches
    to the open pane rather than running a second flow beside it."""
    from . import clilogin, clis
    name = str(body.name or '')
    label = next((k['label'] for k in clis.KNOWN if k['name'] == name), '')
    try: return clilogin.start(store, name, ACTOR, label=label)
    except ValueError as e: raise HTTPException(422, str(e))
```

- [ ] **Step 4: Add the guard row**

In `taskuary/guard.py`, directly after the `/api/cli/install` row (line 65):

```python
    (r'POST', r'^/api/cli/login', "signing a CLI in starts an OAuth flow on this machine - the owner's decision"),
```

- [ ] **Step 5: Add the `login` field to both `detect` rows**

In `taskuary/clis.py` `detect()`, first loop — extend the existing `out.append({...})` with `'login': recipe if recipe in clilogin.RECIPES else ''`, and the same in the second loop (which also has `recipe` in scope). Import at the top of the function beside `from . import cliinstall`:

```python
    from . import cliinstall, clilogin
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_login.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 7: Commit**

```bash
git add taskuary/server.py taskuary/guard.py taskuary/clis.py tests/test_cli_login.py
git commit -m "feat: POST /api/cli/login opens the sign-in, and only the owner may press it"
```

---

### Task 3: The signed-out message names the button

**Files:**
- Modify: `taskuary/agents.py:235` (`_LOGIN_HOW`), `:243` (`signed_out_msg`), `:506` (call site)
- Test: `tests/test_cli_login.py` (append)

**Interfaces:**
- Consumes: `cliinstall.recipe_for(cmd) -> str`.
- Produces: `agents.signed_out_msg(name, why, cmd='') -> str` — a third, optional parameter.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_login.py`:

```python
class SignedOutMessageTests(unittest.TestCase):
    """The sentence a failing run shows. It used to send the owner to a terminal."""

    def test_it_names_the_button_this_app_now_has(self):
        from taskuary import agents
        msg = agents.signed_out_msg('coder', 'not logged in', r'C:\n\claude.cmd')
        self.assertIn('Sign in', msg)
        self.assertNotIn('Open a terminal', msg)

    def test_a_profile_is_mapped_to_its_cli_not_read_as_one(self):
        """Every install ships a profile called `coder`; _LOGIN_HOW.get('coder') always missed."""
        from taskuary import agents
        self.assertIn('/login', agents.signed_out_msg('coder', 'x', r'C:\n\claude.cmd'))
        self.assertIn('codex login', agents.signed_out_msg('coder', 'x', '/usr/bin/codex'))

    def test_all_five_signable_clis_have_a_sentence(self):
        from taskuary import agents, clilogin
        for name in clilogin.RECIPES: self.assertIn(name, agents._LOGIN_HOW, name)

    def test_an_unknown_cli_still_gets_a_usable_sentence(self):
        from taskuary import agents
        self.assertIn('aider', agents.signed_out_msg('aider', 'x', '/usr/bin/aider'))
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_cli_login.py -k SignedOut -q`
Expected: FAIL — `signed_out_msg() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Rewrite `_LOGIN_HOW` and `signed_out_msg`**

Replace lines 235 and 243-245 of `taskuary/agents.py`:

```python
_LOGIN_HOW = {'claude': "type `/login`", 'copilot': "type `/login`", 'codex': "run `codex login`",
              'cursor': "run `cursor-agent login`", 'gemini': "start it once and finish Google's sign-in"}


def signed_out_msg(name: str, why: str, cmd: str = '') -> str:
    """Taskuary can host the sign-in now (clilogin.py), so this stops sending people to a terminal.

    The name that arrives here is the PROFILE's - every install ships one called `coder` - so the
    CLI is read off the command it runs, which is the same rule cliinstall.recipe_for exists for."""
    from . import cliinstall
    cli = cliinstall.recipe_for(cmd) or name
    how = _LOGIN_HOW.get(cli, f"run `{cli}` and sign in again")
    return (f"{name} is signed out on this machine ({why.strip()[:160]}). Press Sign in on "
            f"Connections > AI CLI agents and finish it in the pane that opens - or {how} in a terminal.")
```

- [ ] **Step 4: Pass the command at the call site**

`taskuary/agents.py:506` — the resolved `cmd` is already in scope one line below:

```python
        if _SIGNED_OUT.search(why): raise RuntimeError(signed_out_msg(name, why, cmd[0] if cmd else ''))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_login.py tests/test_agents.py -q`
Expected: PASS. If an existing agents test pins the old sentence, update that test — the sentence is deliberately changing.

- [ ] **Step 6: Commit**

```bash
git add taskuary/agents.py tests/test_cli_login.py
git commit -m "fix: a signed-out CLI names the button in this app, not a terminal somewhere else"
```

---

### Task 4: `cliLogin` — the hook and its pure helpers

**Files:**
- Create: `website/src/cliLogin.js`, `website/src/cliLogin.jsx`
- Test: `website/test/cliLogin.test.mjs`

**Interfaces:**
- Consumes: `api` (`./api`), `SessionPane` from `./TerminalView.jsx`, `FAINT` from `./theme.jsx`, and the `login` field on `/api/cli/detect` rows.
- Produces: `canSignIn(cli) -> boolean` and `signInTitle(cli) -> string` from `cliLogin.js`; `useCliLogin()` → `{signIn, opening, pane, note, setNote}` and `<SignInButton cli opening onSignIn />` from `cliLogin.jsx`.

- [ ] **Step 1: Write the failing test**

Create `website/test/cliLogin.test.mjs`:

```javascript
// Sign in to a coding CLI from inside Taskuary: the button is drawn only where there is a road,
// and the pane it opens is the same session the Board shows.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { canSignIn, signInTitle } from "../src/cliLogin.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the button is drawn only for an installed CLI that has a login recipe", () => {
  assert.equal(canSignIn({ installed: true, login: "claude" }), true);
  assert.equal(canSignIn({ installed: false, login: "claude" }), false);   // install it first
  assert.equal(canSignIn({ installed: true, login: "" }), false);          // aider: an API key, no sign-in
  assert.equal(canSignIn(null), false);
});

test("the title says what will happen, and names the CLI", () => {
  assert.match(signInTitle({ label: "Claude Code", login: "claude" }), /Claude Code/);
});

test("the hook posts the recipe and renders the session it gets back", () => {
  const src = read("cliLogin.jsx");
  assert.match(src, /api\.post\("\/api\/cli\/login", \{ name \}\)/);
  assert.match(src, /SessionPane/);
  // the pane is a task on the Board: a second press must reattach, never open a second flow
  assert.match(src, /existing/);
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `website/`): `node --test test/cliLogin.test.mjs`
Expected: FAIL — cannot find module `../src/cliLogin.js`.

- [ ] **Step 3: Write `website/src/cliLogin.js`**

```javascript
// What the Sign in button is allowed to offer. Pure, so the rule is testable without React.
//
// `login` is the server's word: the recipe name for a CLI whose sign-in Taskuary knows how to
// start, or "". Same rule as `installable` - never draw a button over a road that does not exist.
export const canSignIn = (cli) => !!(cli && cli.installed && cli.login);
export const signInTitle = (cli) =>
  `Sign in to ${cli?.label || cli?.login || "this CLI"} here — it opens in a live pane, as a task on the Board`;
```

- [ ] **Step 4: Write `website/src/cliLogin.jsx`**

```javascript
// The Sign in button for a coding CLI, shared by the setup wizard and the AI CLI agents page.
//
// The Install button ended on a CLI with no credentials, and the app's own answer to that was a
// sentence telling the owner to open a terminal. Taskuary has had an interactive pty all along:
// this opens the CLI's own sign-in in it, as an ordinary setup task, so the pane is on the Board
// and `Done` closes it the way it closes any other setup session.
//
// Nothing here types a credential. The CLI's own `/login` is typed server-side; what the owner
// enters, they enter themselves, watching it go in.
import React, { useCallback, useRef, useState, useEffect } from "react";
import { Button } from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";
import api from "./api";
import { SessionPane } from "./TerminalView.jsx";
import { canSignIn, signInTitle } from "./cliLogin.js";

export { canSignIn, signInTitle };

export const useCliLogin = () => {
  const [opening, setOpening] = useState("");
  const [pane, setPane] = useState(null);              // { sid, taskId, name }
  const [note, setNote] = useState(null);              // { bad, text }
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const signIn = useCallback(async (cli) => {
    const name = typeof cli === "string" ? cli : cli?.login || "";
    if (!name) { setNote({ bad: true, text: "Taskuary does not know how to sign that one in" }); return null; }
    const put = (fn, v) => { if (alive.current) fn(v); };
    put(setOpening, name); put(setNote, null);
    try {
      const { data } = await api.post("/api/cli/login", { name });
      put(setPane, { sid: data.sid, taskId: data.taskId, name });
      // a second press reattaches: say so, or the owner waits for a pane that is already theirs
      put(setNote, { text: data.existing ? "that sign-in is already open — it is the pane below" : "finish the sign-in in the pane below" });
      put(setOpening, ""); return data;
    } catch (e) {
      put(setNote, { bad: true, text: e?.response?.data?.detail || e?.message || "that did not work" });
      put(setOpening, ""); return null;
    }
  }, []);

  return { signIn, opening, pane, setPane, note, setNote };
};

export const SignInButton = ({ cli, opening, onSignIn, sx = {} }) => {
  if (!canSignIn(cli)) return null;
  return (
    <Button size="small" variant="outlined" disabled={!!opening} onClick={() => onSignIn(cli)}
      startIcon={<LoginIcon sx={{ fontSize: 14 }} />} title={signInTitle(cli)}
      sx={{ fontSize: 11.5, whiteSpace: "nowrap", ...sx }}>
      {opening === cli.login ? "opening…" : "Sign in"}
    </Button>
  );
};

// The pane itself, wherever the caller puts it. One session id - the Board is showing the same one.
export const LoginPane = ({ pane }) => (pane?.sid ? <SessionPane sid={pane.sid} /> : null);
```

- [ ] **Step 5: Run the test to verify it passes**

`SessionPane` is verified: `TerminalView.jsx:412` exports `({ sid, height = "70vh", onExit, children, autoFocus = true, expectBrowser = false })`, so `<SessionPane sid={pane.sid} />` above is correct as written.

Run (from `website/`): `node --test test/cliLogin.test.mjs`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add website/src/cliLogin.js website/src/cliLogin.jsx website/test/cliLogin.test.mjs
git commit -m "feat: a Sign in button that opens the CLI's own sign-in in a live pane"
```

---

### Task 5: Wire the wizard and the agents page

**Files:**
- Modify: `website/src/SetupWizard.jsx` (`getAndUse` ~line 159, `use` ~line 165, the row ~line 188)
- Modify: `website/src/AgentsPanel.jsx` (~line 233, after the Install button)
- Test: `website/test/cliLogin.test.mjs` (append)

**Interfaces:**
- Consumes: `useCliLogin`, `SignInButton`, `LoginPane`, `canSignIn` from `./cliLogin.jsx`.
- Produces: no new exports.

- [ ] **Step 1: Write the failing tests**

Append to `website/test/cliLogin.test.mjs`:

```javascript
test("installing a CLI that needs a sign-in hands off to the pane instead of testing it", () => {
  const src = read("SetupWizard.jsx");
  // the dead end this feature exists to remove: install, then immediately Add & test with no credentials
  assert.match(src, /canSignIn\(/);
  assert.match(src, /<LoginPane/);
  assert.match(src, /useCliLogin\(\)/);
});

test("a passing test moves the wizard on, and leaves Done to the owner", () => {
  const src = read("SetupWizard.jsx");
  assert.match(src, /api\.post\(`\/api\/agents\/\$\{encodeURIComponent\(cli\.name\)\}\/test`/);
  // nothing closes the pane or the task from here - a pane must not vanish mid-OAuth
  assert.doesNotMatch(src, /\/wrap|clilogin\.finish|api\.post\(`\/api\/tasks\/\$\{[^}]+\}\/wrap/);
});

test("the agents page offers Sign in on a row that has a recipe", () => {
  const src = read("AgentsPanel.jsx");
  assert.match(src, /SignInButton/);
  assert.match(src, /useCliLogin\(\)/);
});
```

- [ ] **Step 2: Run to verify they fail**

Run (from `website/`): `node --test test/cliLogin.test.mjs`
Expected: FAIL on the three new assertions.

- [ ] **Step 3: Wire `SetupWizard.jsx`**

Add to the imports beside `useCliInstall`:

```javascript
import { useCliLogin, SignInButton, LoginPane, canSignIn } from "./cliLogin.jsx";
```

In the component, beside `const { install, busy: installing, note } = useCliInstall();`:

```javascript
  const { signIn, opening, pane, note: loginNote } = useCliLogin();
```

Replace `getAndUse` so an install that lands on a CLI with a sign-in hands off rather than testing:

```javascript
  // Install, then keep going - but a CLI that has just been installed has no credentials, and
  // running Add & test on it produced the dead end this hand-off exists to remove. `cmd` carried
  // forward is the ABSOLUTE path the installer reported: this server's PATH predates the install.
  const getAndUse = async (cli) => {
    const done = await install(cli);
    if (!done) return;
    const fresh = { ...cli, cmd: done.path || cli.cmd, installed: true, login: cli.login };
    if (canSignIn(fresh)) { await signIn(fresh); return; }      // the pane takes it from here
    await use(fresh);
  };
```

Render the pane and the follow-on test under the CLI list — after the rows, before the list's closing element:

```javascript
      {pane && (
        <Box sx={{ mt: 1 }}>
          {loginNote && <Typography variant="caption" sx={{ color: loginNote.bad ? "#8a3646" : FAINT }}>{loginNote.text}</Typography>}
          <LoginPane pane={pane} />
          <Button size="small" variant="outlined" sx={{ mt: 0.75, fontSize: 11.5 }}
            title="Check whether the sign-in landed. The pane stays open either way — closing it is yours."
            onClick={() => use(list.find((o) => o.login === pane.name) || {})}>
            I have signed in — test it
          </Button>
        </Box>
      )}
```

- [ ] **Step 4: Wire `AgentsPanel.jsx`**

Add to the imports beside `useCliInstall`:

```javascript
import { useCliLogin, SignInButton } from "./cliLogin.jsx";
```

In the component, beside the install hook:

```javascript
  const { signIn, opening } = useCliLogin();
```

Directly after the Install button block (~line 233-239), add the sign-in offer for a row that IS installed:

```javascript
                {/* installed and signed out look identical from here, and the page has no signal
                    for the second. Sign in is always a legitimate thing to press, so offer it
                    rather than guess - the CLI itself says whether it was needed. */}
                <SignInButton cli={{ ...canGet[a.cmd], installed: here[name] !== false }}
                  opening={opening} onSignIn={signIn} sx={{ fontSize: 10.5 }} />
```

- [ ] **Step 5: Run the test to verify it passes**

Both pages pass whole `/api/cli/detect` rows through unnarrowed — `AgentsPanel.jsx:133` (`by[r.cmd] = r`, keyed by the BINARY, so `canGet['cursor-agent'].login === 'cursor'`) and `SetupWizard.jsx:154` (`setList(data.data)`) — so `login` arrives intact and no mapping needs widening. Note the override above is deliberate: the detect row's `installed` is about the CLI on PATH, while `here[name]` is about this profile, and the profile's answer is the one that governs the row.

Run (from `website/`): `node --test test/cliLogin.test.mjs`
Expected: PASS, 6 tests.

- [ ] **Step 6: Run the whole node suite**

Run (from `website/`): `npm test`
Expected: PASS, all files. `npm run lint:undef` must also be clean — esbuild syntax-checks JSX that pytest never loads.

- [ ] **Step 7: Commit**

```bash
git add website/src/SetupWizard.jsx website/src/AgentsPanel.jsx website/test/cliLogin.test.mjs
git commit -m "feat: the wizard is Install then Sign in then Add & test, and the agents page offers it too"
```

---

### Task 6: Build the bundle and run every gate

**Files:**
- Modify: `taskuary/web/` (generated — the committed UI bundle)

- [ ] **Step 1: Rebuild the committed UI**

Run (from `website/`): `npm run build`
The bundle in `taskuary/web/` is committed, and CI rebuilds it and compares — a stale bundle is the `build-web` failure this repo has hit before.

- [ ] **Step 2: Run the Python suite from the repo root**

Run: `python -m pytest`
Expected: PASS. "No tests ran" is a failure, not a pass.

- [ ] **Step 3: Run the node suite**

Run (from `website/`): `npm test`
Expected: PASS.

- [ ] **Step 4: Commit the bundle**

```bash
git add taskuary/web
git commit -m "build: package the UI for the CLI sign-in"
```

Do **not** commit the bundle if `git status` shows another session's uncommitted `website/src` — it would ship their half-finished work. Rebuild after they land instead.

---

## Manual verification (after Task 6)

The suite cannot prove an OAuth flow. Once it is green, in the running app:

1. **Connections → AI CLI agents** → press **Sign in** on an installed CLI. A pane opens, `/login` is typed into it, and the same session appears on the **Board** with a `TQ-` ref.
2. Press **Sign in** again → it reattaches to that pane; no second flow.
3. Finish the sign-in, press **Add & test** → it answers.
4. Press **Done** on the task → the task closes with no report, no reply draft, and no transcript on it (check the task page: the transcript section must be empty).

# The Brain Layer — Implementation Plan (step 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A brain becomes a thing of its own — a CLI connection carrying its gears, chosen by a setting rather than by a profile — and the task list names the brain that actually has the work.

**Architecture:** Gears (`model`, `light_model`) move from the profile row onto the `cli_connections` entry, where `model_arg` already lives. A new `default_brain` setting names the CLI for every worker session, with an optional `profile_brains` override. `start_on_task` resolves the brain at start and records it on the transcript. The session names the CLI it was asked to run rather than whatever the OS used to launch it, and the Board shows that name.

**Tech Stack:** Python 3.10, SQLite, pytest, React/Vite (Node 22 for the bundle).

**Spec:** `docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md`
**Follows:** `docs/superpowers/plans/2026-09-16-profile-is-a-role.md` (step 1, landed `6d2ded64`)

## Global Constraints

Same as step 1, and they still bind:

- **Style:** concise fast.ai density, matching the file. No autoformatters.
- **Test gate:** whole `pytest` from the repo root before pushing. `no tests ran` is a failure.
- **Shared checkout:** a coding agent commits to master here. Commit off a temporary index (`scratchpad/commit.sh`), never `git add -A` outside `taskuary/web`, never `git commit -a`. If it has pushed ahead, **merge, do not rebase** — rebasing rewrites its commits.
- **Bundle:** any `website/src` change needs a rebuild, with Node 22: `cd website && npm exec --yes --package=node@22 -- node ./node_modules/vite/bin/vite.js build`. `emptyOutDir` regenerates `taskuary/web` wholesale, which is also how a bundle merge conflict is resolved.
- **Heredocs eat backslashes.** Use the editor tool for Python.
- **`Assignee` does three jobs:** names the role, seeds its document, and its `agent:` prefix puts the row in the pipe's `queued` lane (`processing_unread:76`). Do not remove a stamp without checking all three.
- **Scope:** step 3 (deleting `provider`/`model` from profiles and the three compensating patches) is NOT in this plan. `provider` stays readable; this plan stops *depending* on it.
- **Commit attribution:** `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File Structure

| File | Responsibility after this plan |
| --- | --- |
| `taskuary/terminal.py` | `Term` carries the CLI it was asked to run; `cli_of` is a fallback, not the source of truth |
| `taskuary/cli_connections.py` | connections carry gears; `set_profile` stops scrubbing models |
| `taskuary/agents.py` | `default_brain()`, `brain_for(role)` — which CLI runs a role |
| `taskuary/aidefaults.py` | reads gears off the connection; the coding slot names a brain |
| `taskuary/store.py` | `transcript.Brain` column |
| `website/src/BoardView.jsx` | the card names the brain, not the role |

---

### Task 1: A session names the CLI it was asked to run

`cli_of` takes `argv[0]`'s basename, which is the wrapper for anything behind a `.BAT` or node: copilot reports `cmd`, qwen reports `node`. It is served as `session.cli` (`terminal.py:466`, `server.py:2566`) and is what the task page's `by:` chip renders — it read `by: claude` on a Copilot session.

**Files:** Modify `taskuary/terminal.py` (`Term.__init__`, `info`, `open_session`). Test `tests/test_brain_layer.py` (create).

**Produces:** `Term.cli` — the CLI family name from the profile; `info()['cli']` prefers it.

- [ ] **Step 1: Failing test** — `tests/test_brain_layer.py`:

```python
"""A brain is a thing of its own: which CLI runs the work, and on which gear.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents, terminal
from taskuary.store import MemoryStore


class CliNameTests(unittest.TestCase):
    def test_a_wrapper_is_not_the_cli(self):
        """copilot resolves to `cmd /c ...copilot.BAT` and qwen to node.EXE, so argv[0] names the
        launcher. The card must say copilot, not cmd."""
        for cmd in ('copilot', 'qwen', 'claude', 'codex'):
            argv = terminal.agent_argv({'cmd': cmd})
            self.assertEqual(terminal.cli_named({'cmd': cmd}, argv), cmd)

    def test_cli_of_still_reads_a_plain_argv(self):
        self.assertEqual(terminal.cli_of(['/usr/bin/claude', '-p']), 'claude')
```

- [ ] **Step 2: Run it** — `python -m pytest tests/test_brain_layer.py -v`. Expected FAIL: no `cli_named`.

- [ ] **Step 3: Implement** in `taskuary/terminal.py`, beside `cli_of`:

```python
def cli_named(profile: dict, argv=None) -> str:
    """The CLI this session RUNS, by the name the profile asked for.

    cli_of reads argv[0], which on Windows is the wrapper for anything behind a .BAT (`cmd /c
    ...copilot.BAT`) or launched through node (qwen) - so the card said `cmd` and `node`, and the
    task page's `by:` chip named the wrong product entirely. The profile's own `cmd` is the answer
    wherever there is one; argv stays the fallback for a bare shell with no profile."""
    from .agents import cli_of as _family
    return _family(profile or {}) or cli_of(argv)
```

- [ ] **Step 4: Carry it on the session.** In `Term.__init__`, accept `cli: str = ''` and store `self.cli = cli`. In `info()` (`terminal.py:466`), change `'cli': cli_of(self.argv)` to `'cli': self.cli or cli_of(self.argv)`. In `open_session`, pass `cli=cli_named(profile, argv)` when constructing the `Term`.

- [ ] **Step 5: Run** — `python -m pytest tests/test_brain_layer.py tests/test_terminal.py -v`. Expected PASS.

- [ ] **Step 6: Commit** — `fix: a session names the CLI it runs, not the shell that launched it`

---

### Task 2: A connection carries its gears

`model_arg` (the flag) lives on the connection; `model` and `light_model` (the values) are stranded on the profile with a patch that scrubs them when the provider changes — `cli_connections.py:122`, whose own comment says *"Model names belong to their provider"*.

**Files:** Modify `taskuary/cli_connections.py` (`COMMAND_FIELDS`, `set_profile`), `taskuary/aidefaults.py` (read gears off the connection). Test `tests/test_brain_layer.py`.

**Produces:** `cli_connections.gears(cfg, key) -> dict` with `model` / `light_model`.

- [ ] **Step 1: Failing test** — append:

```python
from taskuary import cli_connections as clic


class GearTests(unittest.TestCase):
    def cfg(self):
        return {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}},
                'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude'}}}

    def test_gears_belong_to_the_connection(self):
        self.assertEqual(clic.gears(self.cfg(), 'claude'), {'model': 'opus', 'light_model': 'haiku'})

    def test_resolving_a_profile_takes_the_connection_gears(self):
        c = self.cfg()
        got = clic.resolve(c, c['agents']['coder'])
        self.assertEqual((got['model'], got['light_model']), ('opus', 'haiku'))

    def test_one_brain_two_gears_is_still_one_brain(self):
        """The owner's rule: triage runs the main brain on a quicker model."""
        c = self.cfg()
        self.assertEqual(clic.gears(c, 'claude')['model'], 'opus')
        self.assertEqual(clic.gears(c, 'claude')['light_model'], 'haiku')
```

- [ ] **Step 2: Run it** — expected FAIL: no `gears`.

- [ ] **Step 3: Implement.** In `cli_connections.py`:

```python
COMMAND_FIELDS = ('cmd', 'args', 'resume', 'resume_args', 'timeout', 'model_arg', 'acp', 'model', 'light_model')


def gears(cfg, key: str) -> dict:
    """A brain's two gears. MAIN runs the sessions - coding and general alike; LIGHT runs the
    one-message jobs (triage, drafts, summaries, the digest). One brain, two gears, still one
    brain: `claude-main` and `claude-light` are not two providers."""
    c = cfg.get('cli_connections', {}).get(str(key or '')) or {}
    return {'model': str(c.get('model') or ''), 'light_model': str(c.get('light_model') or '')}
```

Delete the scrub in `set_profile` (`cli_connections.py:121-125`) — with the values on the provider there is nothing to follow a worker to another one. Leave a one-line comment saying so and naming this plan.

- [ ] **Step 4: Run** — `python -m pytest tests/test_brain_layer.py tests/test_cli_connections.py tests/test_ai_defaults.py -v`. Failures in the last two are expected where they assert the profile holds the model: that is the old rule; update the assertion and say so in the commit.

- [ ] **Step 5: Commit** — `feat: a brain carries its own gears, and the scrub they needed is gone`

---

### Task 3: One default brain, with a per-role override

**Files:** Modify `taskuary/agents.py`, `taskuary/store.py` (settings defaults). Test `tests/test_brain_layer.py`.

**Produces:**
- `agents.default_brain(store) -> str` — the CLI key every worker session runs on.
- `agents.brain_for(store, role: str) -> str` — that, or the role's override.

- [ ] **Step 1: Failing test** — append:

```python
class DefaultBrainTests(unittest.TestCase):
    def store(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.upsert_agent('analyst', 'analysis', 'cli', json.dumps({'cmd': 'claude'}))
        return s

    def test_one_brain_serves_coding_and_general_alike(self):
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'coder'), 'claude')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'claude')

    def test_a_role_may_be_overridden_in_settings(self):
        """Configurable, but it is a SETTING keyed by a profile - never a field on the profile,
        and never a model."""
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        s.set_setting('profile_brains', json.dumps({'analyst': 'codex'}), 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'codex')
        self.assertEqual(hub_agents.brain_for(s, 'coder'), 'claude')

    def test_a_broken_override_falls_back_rather_than_failing(self):
        s = self.store()
        s.set_setting('default_brain', 'claude', 'owner')
        s.set_setting('profile_brains', 'not json', 'owner')
        self.assertEqual(hub_agents.brain_for(s, 'analyst'), 'claude')
```

- [ ] **Step 2: Run it** — expected FAIL. If `set_setting` is not the store's real writer, read `store.py` and use the real one rather than adding a method.

- [ ] **Step 3: Implement** in `agents.py`:

```python
def default_brain(store) -> str:
    """The CLI every worker session runs on - coding and general alike. Falls back to the CLI
    behind the legacy `default_agent` profile so an install that has not been migrated keeps
    running what it ran yesterday."""
    key = str(store.get_settings().get('default_brain') or '').strip()
    if key: return key
    prof = profiles(store).get(default_agent(store)) or {}
    return cli_of(prof, default_agent(store))


def brain_for(store, role: str) -> str:
    """The brain that runs one role. A profile never PINS a brain - this is a setting keyed by a
    profile, and what it names is a brain, never a model (the owner, 2026-09-16)."""
    try: over = json.loads(store.get_settings().get('profile_brains') or '{}')
    except ValueError: over = {}
    key = str((over or {}).get(str(role or '')) or '').strip() if isinstance(over, dict) else ''
    return key or default_brain(store)
```

Add `'default_brain': ''` and `'profile_brains': ''` to the settings defaults in `store.py` (blank = derive from the legacy setting, so nothing regresses on upgrade).

- [ ] **Step 4: Run** — `python -m pytest tests/test_brain_layer.py -v`. Expected PASS.

- [ ] **Step 5: Commit** — `feat: one default brain for every worker, overridable per role in settings`

---

### Task 4: The session runs the brain, and records which

**Files:** Modify `taskuary/terminal.py` (`open_session`/`start_on_task`), `taskuary/store.py` (`transcript.Brain`). Test `tests/test_brain_layer.py`.

- [ ] **Step 1: Failing test** — append:

```python
class SessionBrainTests(unittest.TestCase):
    def test_the_transcript_records_which_brain_ran(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'x', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        s.save_transcript(tid, 'sid1', 'coder', 'C:/repo', 'text', brain='copilot')
        row = [r for r in s.list_transcripts(tid)][-1]
        self.assertEqual(row['Agent'], 'coder')
        self.assertEqual(row['Brain'], 'copilot')
```

Read `store.py`'s real transcript writer/reader names before finalising this test; use them.

- [ ] **Step 2: Run it** — expected FAIL.

- [ ] **Step 3: Implement.** Add the idempotent column beside the other upgrades in `store.py`:

```python
            if 'Brain' not in tcols: self.cx.execute('ALTER TABLE transcript ADD COLUMN Brain TEXT')
```

Give the transcript writer a `brain: str = ''` parameter and store it.

- [ ] **Step 4: Resolve the brain at start.** In `terminal.open_session`, the profile's `cmd` stops being the answer: resolve `brain = hub_agents.brain_for(store, agent)`, take that connection's command via `cli_connections.resolve`, and build argv from it. Pass `cli=brain` to the `Term`. Write `brain` on the transcript row.

Keep the fallback: if the brain names no configured connection, use the profile's own `cmd` and log once. An install mid-upgrade must still start.

- [ ] **Step 5: Run** — `python -m pytest tests/test_brain_layer.py tests/test_terminal.py tests/test_session_continuity.py tests/test_coder_session_continuity.py -v`.

- [ ] **Step 6: Commit** — `feat: a session runs the brain settings name, and the transcript records which`

---

### Task 5: A general session takes the main gear

`make_cli_llm` applies the light gear unconditionally and only an explicit per-job model outranks it (`llm.py:102`). General sessions reach it through `build_llm(pick, model=…)` where the model falls back to the profile's main `model` — `None` on all of the owner's profiles — so a general worker session silently runs on the LIGHT gear today. The owner's rule: *"general agents use the same brain on high level like coding by default."*

**Files:** Modify `taskuary/general.py` (the model it selects). Test `tests/test_brain_layer.py`.

- [ ] **Step 1: Failing test** — append:

```python
class GearByJobTests(unittest.TestCase):
    def test_a_general_session_takes_the_main_gear(self):
        """Session work is session work: coding and general both get the capable model. The light
        gear is for the one-message jobs - triage, drafts, summaries, the digest."""
        from taskuary import general
        s = MemoryStore()
        s.upsert_agent('analyst', 'analysis', 'cli', json.dumps({'cmd': 'claude'}))
        task = {'TaskId': 1, 'Kind': 'general', 'Assignee': 'agent:analyst'}
        self.assertEqual(general.session_gear(s, task), 'main')
```

- [ ] **Step 2: Run it** — expected FAIL.

- [ ] **Step 3: Implement** a `session_gear` that answers `'main'` for a worker session, and make the model `general` selects come from `cli_connections.gears(...)['model']` rather than falling through to the light gear.

Leave the Assistant on light — `aidefaults` calls it "the same quick gear as triage", and the owner's decision was about general *workers*, not chat turns. This is the spec's one `ASSUMPTION`; if it is wrong, only this task changes.

- [ ] **Step 4: Run** — `python -m pytest tests/test_brain_layer.py tests/test_general.py tests/test_assistant_reactions.py -v`.

- [ ] **Step 5: Commit** — `feat: a general worker session takes the main gear, like coding`

---

### Task 6: The card names the brain that has the work

*"On the task list it says which coding agent owns it — make sure the task has the correct coding agent"* (the owner, 2026-09-16). After step 1 every coding row's role is `coder`, so the role is no longer worth showing.

`live_runs` already sends `cli` per pty session (`server.py:2460`); the card renders `AgentName` instead (`BoardView.jsx:464`), and the idle chip renders `assignedAgent(t.Assignee)` titled *"X owns this task"* (`BoardView.jsx:484`).

**Files:** Modify `website/src/BoardView.jsx`; expose the resolved brain once from the server. Test: `website/src` has no unit harness for this — verify by the bundle build plus a screenshot of the Board.

- [ ] **Step 1: Serve the brain.** Add the resolved brain to the settings/bootstrap payload the Board already fetches (one value: `brain_for(store, coding_role(store))`). Do not add a per-task column — the brain is not a property of the task.

- [ ] **Step 2: Live card names the running CLI.** In `BoardView.jsx:464`, prefer `live[t.TaskId]?.cli` over `AgentName` for a coding task.

- [ ] **Step 3: Idle chip names the brain that would run it.** At `BoardView.jsx:484`, a coding task shows the resolved brain, titled `"<brain> works this task"`. A general task keeps showing its role — there the role is the information.

- [ ] **Step 4: Rebuild the bundle** with Node 22 (see Global Constraints) and commit `taskuary/web` with the source.

- [ ] **Step 5: Verify in the running app** — open the Board, confirm a coding card names the brain and not `cmd`, `node` or `coder`.

- [ ] **Step 6: Commit** — `feat: the card names the coding agent that has the work`

---

### Task 7: The whole-suite gate

- [ ] **Step 1:** `python -m pytest` from the repo root. Expected: pass, non-zero collected.
- [ ] **Step 2:** For each failure decide *old rule* vs *regression* and record which in the commit body. Do not mass-update assertions to green the suite.
- [ ] **Step 3:** Confirm against the live store that `brain_for(store, 'coder')` answers `claude`, and that a Copilot session reports `copilot` rather than `cmd`.
- [ ] **Step 4: Commit**, then merge/push per the Global Constraints.

## Self-Review

**Spec coverage:** gears onto connections (Task 2), `default_brain` + `profile_brains` (Task 3), brain resolved at session start and recorded (Task 4), general on the main gear (Task 5), the owner's display requirement and the `cli_of` bug (Tasks 1 and 6).

**Deferred to step 3, deliberately:** deleting `provider`/`model` from the profile row, `agent_chain`'s dedupe-by-CLI, `llm._build_llm`'s dedupe, and `backup_agents` → `backup_brains`. This plan stops *depending* on `provider`; step 3 removes it.

**Known uncertainties, to be read from the source rather than guessed:** the store's real settings writer (Task 3 Step 2) and transcript writer/reader names (Task 4 Step 1). Both tests say to read `store.py` first and use the real API rather than inventing one.

**Riskiest task:** 4. It changes how every session is launched. The fallback to the profile's own `cmd` when the brain names no connection is what keeps a half-migrated install able to start an agent at all.

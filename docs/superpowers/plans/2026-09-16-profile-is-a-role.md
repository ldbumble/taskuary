# Profile Is A Role — Implementation Plan (step 1 of 3)

> **EXECUTED 2026-09-16.** Whole suite: 4204 passed, 1 skipped. Three things went differently
> from the plan below, each forced by something the plan had not seen; the commits carry the
> detail.
>
> - **Task 2 wrote no assignee for coding, then went back to writing one.** The suite caught that
>   stamping `agent:coder` broke "this one is mine"; removing the stamp then turned out to drop
>   coding tasks out of the pipe's `queued` lane (`processing_unread:76`, `processing_all:400`),
>   which the suite did *not* catch. The stamp stays, and the real culprit — `mine_message`'s guard
>   claiming a task only when nobody was on it — is fixed instead. `Assignee` turned out to do
>   three jobs, not two.
> - **Task 4 gained a fourth fused site.** `general.assigned_pick` was found during plan research,
>   not spec writing, and reverses an explicitly stated principle. See the spec.
> - **Task 5 corrects OPEN work only.** Run once against the live store it rewrote eleven finished
>   tasks whose transcripts say codex, analyst, copilot and devin actually worked them. A closed
>   task's stamp is history. The status guard is an allowlist.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the profile question from coding to general work, so triage names a *role* and never a brain.

**Architecture:** Four seams, one rule. `agents.roster` stops offering coding profiles; `agents.routed_role` decides the role from the verdict (coding has exactly one, general takes the named specialist); `triage.py`'s appended `THE WORKERS` block asks for a profile on general work; and `general.assigned_pick` splits so a role selects the rules document but never the executable. A one-time repair corrects tasks already routed to a brain.

**Tech Stack:** Python 3.10, SQLite, pytest, FastAPI.

**Spec:** `docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md`

## Global Constraints

- **Style:** concise fast.ai density, matching the surrounding file. Never run autoformatters (black/yapf/autopep8) — they re-expand this code.
- **Test gate:** the whole `pytest` from the repo root must pass before anything is pushed. `no tests ran` is a failure, not a pass.
- **Shared checkout:** a live `coder` session works in `C:\Users\owner\Documents\General\Testing\taskhub` and shares its git index. Build every commit off a temporary index (`GIT_INDEX_FILE` + `read-tree`/`hash-object`/`write-tree`/`commit-tree`/guarded `update-ref`), never `git add -A`, never `git commit -a`.
- **Heredocs eat backslashes** in this environment. Patch Python by line index or use the editor tool; do not pipe source through a bash heredoc.
- **`INTENT_SYSTEM` is not what runs here.** The owner's store holds a `triage` doc (15,908 chars, `UpdatedBy=migration`) that replaces it wholesale (`triage.py:408`). Behaviour changes must live in the blocks *appended* after the override (`triage.py:466`), not in the constant. Edit the constant too, for installs without a doc, but never rely on it.
- **Scope:** this is step 1 of the spec's three. `provider` stays on the profile row and `default_agent` keeps its name; steps 2 and 3 move those. Do not start them here.
- **Commit attribution:** end every commit message with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## File Structure

| File | Responsibility after this plan |
| --- | --- |
| `taskuary/agents.py` | `roster()` lists general roles only; new `coding_role()` and `routed_role()` own the "which role" decision |
| `taskuary/ingest.py` | calls `routed_role()` instead of writing the verdict's profile straight onto `Assignee` |
| `taskuary/triage.py` | the `THE WORKERS` block asks for a profile on general work; `INTENT_SYSTEM` says the same |
| `taskuary/general.py` | `assigned_role()` (role → rules doc) replaces `assigned_pick()` (role → provider) |
| `taskuary/server.py` | boot calls the one-time repair |
| `tests/test_profile_is_a_role.py` | **new** — every behaviour in this plan |

---

### Task 1: The roster offers general roles only

**Files:**
- Modify: `taskuary/agents.py:574-586`
- Test: `tests/test_profile_is_a_role.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `agents.roster(store) -> str` — newline-joined `- <name>: <purpose>` lines, containing **no** profile whose `Kind` is `coding` or `cli`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile_is_a_role.py`:

```python
"""A profile is a role; a brain is what runs it.

TQ-0588 was a coding task and Copilot worked it, though the default coding agent is Claude.
Triage had named the profile `copilot` - and `copilot` is a CLI, not a worker. The question was
also being asked on the wrong kind: every profile choice in the owner's store landed on a coding
task (TQ-0586 drew an ANALYST on coding work) while general tasks got none at all.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents
from taskuary.store import MemoryStore


def store():
    """The owner's shape: one coding role, the CLI clones beside it, and the general specialists."""
    s = MemoryStore()
    for name in ('coder', 'codex', 'copilot'):
        s.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': name, 'purpose': 'Write, review and test code in a repository.'}))
    for name, kind in (('researcher', 'research'), ('analyst', 'analysis'), ('trader', 'markets')):
        s.upsert_agent(name, kind, 'cli', json.dumps({'cmd': 'claude', 'purpose': f'{name} work'}))
    return s


class TheRosterTests(unittest.TestCase):
    def test_roster_offers_no_coding_profile(self):
        names = [ln.split(':')[0][2:] for ln in hub_agents.roster(store()).splitlines() if ln.startswith('- ')]
        for cli in ('coder', 'codex', 'copilot'):
            self.assertNotIn(cli, names, f'{cli} is a coding role and must not be a triage choice')

    def test_roster_offers_every_general_role(self):
        names = [ln.split(':')[0][2:] for ln in hub_agents.roster(store()).splitlines() if ln.startswith('- ')]
        self.assertEqual(sorted(names), ['analyst', 'researcher', 'trader'])

    def test_legacy_cli_kind_is_coding_too(self):
        s = store()
        s.upsert_agent('opencode', 'cli', 'cli', json.dumps({'cmd': 'opencode', 'purpose': 'Write code.'}))
        self.assertNotIn('opencode', hub_agents.roster(s))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_profile_is_a_role.py -v`
Expected: FAIL — `coder is a coding role and must not be a triage choice`.

- [ ] **Step 3: Implement**

In `taskuary/agents.py`, add the kind set beside the other module constants and filter in `roster`:

```python
# The kinds that mean "works a repository". `cli` is the legacy spelling older databases use.
CODING_KINDS = ('coding', 'cli')
```

Then in `roster()`, after the `Active` guard and before the config parse:

```python
        # A coding task has exactly ONE role and triage does not choose it (routed_role): offering
        # the coding profiles here is what let `copilot` - a CLI, not a worker - be named on TQ-0588.
        if str(a.get('Kind') or '').lower() in CODING_KINDS: continue
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/test_profile_is_a_role.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the suites that read the roster**

Run: `python -m pytest tests/test_agent_profiles.py tests/test_triage.py -v`
Expected: PASS. If a test asserts `coder` appears in the roster, it encodes the old rule — update it to assert the new one and say so in the commit.

- [ ] **Step 6: Commit** (temporary index — see Global Constraints)

Message: `feat: the triage roster offers general roles, never a coding one`

---

### Task 2: A coding task always gets the coding role

**Files:**
- Modify: `taskuary/agents.py` (add two functions after `default_agent`, ~line 596)
- Modify: `taskuary/ingest.py:770-776`
- Test: `tests/test_profile_is_a_role.py`

**Interfaces:**
- Consumes: `agents.CODING_KINDS` from Task 1.
- Produces:
  - `agents.coding_role(store) -> str` — the single role every coding task takes. Returns `default_agent(store)` for now; step 2 of the spec makes it the fixed `'coder'`.
  - `agents.routed_role(store, kind: str, profile: str) -> str` — the role a verdict lands on, or `''` for none.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile_is_a_role.py`:

```python
class WhichRoleTests(unittest.TestCase):
    def test_coding_always_takes_the_coding_role(self):
        s = store()
        self.assertEqual(hub_agents.routed_role(s, 'coding', ''), 'coder')

    def test_coding_ignores_a_profile_triage_named(self):
        """TQ-0586: an ANALYST was routed to a coding task. Coding has one role."""
        s = store()
        self.assertEqual(hub_agents.routed_role(s, 'coding', 'analyst'), 'coder')
        self.assertEqual(hub_agents.routed_role(s, 'coding', 'copilot'), 'coder')

    def test_general_takes_the_named_specialist(self):
        self.assertEqual(hub_agents.routed_role(store(), 'general', 'analyst'), 'analyst')

    def test_general_with_no_profile_names_nobody(self):
        """No 'default general role' exists, by design - the owner picks at start."""
        self.assertEqual(hub_agents.routed_role(store(), 'general', ''), '')

    def test_general_never_falls_through_to_coder(self):
        self.assertNotEqual(hub_agents.routed_role(store(), 'general', ''), 'coder')

    def test_kind_task_names_nobody(self):
        """kind 'task' leaves the job on the owner's list - no agent, so no role."""
        self.assertEqual(hub_agents.routed_role(store(), 'task', 'analyst'), '')

    def test_an_unknown_profile_names_nobody(self):
        self.assertEqual(hub_agents.routed_role(store(), 'general', 'nobody'), '')
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_profile_is_a_role.py::WhichRoleTests -v`
Expected: FAIL — `module 'taskuary.agents' has no attribute 'routed_role'`.

- [ ] **Step 3: Implement**

In `taskuary/agents.py`, directly after `default_agent`:

```python
def coding_role(store) -> str:
    """The one role a coding task takes. Triage does not choose it: `kind: coding` names the job,
    and the job names the worker. Reads `default_agent` while that setting is still a PROFILE name;
    step 2 of the spec splits it into a brain and this becomes the fixed 'coder'."""
    return default_agent(store)


def routed_role(store, kind: str, profile: str) -> str:
    """Which ROLE a verdict lands on - never which brain runs it.

    Coding has exactly one role. General takes the specialist triage named, if it names one that
    exists; naming none is a real answer and leaves the task unassigned for the owner to pick at
    start. `kind: task` leaves the job on the owner's list, so no worker at all."""
    if str(kind or '') == 'coding': return coding_role(store)
    name = str(profile or '').strip()
    return name if str(kind or '') == 'general' and name and store.get_agent(name) else ''
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/test_profile_is_a_role.py::WhichRoleTests -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Wire it into ingest**

In `taskuary/ingest.py`, replace the `Assignee` line inside the `create_task` call (currently line 776) and add the computation above `tid = store.create_task(`:

```python
        # WHICH ROLE works this - a different question from which brain runs it. Coding has one
        # role and triage does not choose it; a specialist is named only on general work
        # (docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md).
        role = hub_agents.routed_role(store, f['kind'], intent.get('profile') or '')
```

and the dict entry becomes:

```python
                                 **({'Assignee': f'agent:{role}'} if role else {})}, actor)
```

Replace the three-line comment above the old entry (`# the worker triage named, on the field that has always carried one...`) with nothing — the new comment above `role` says it.

Confirm `hub_agents` is already imported in that scope: it is, at `ingest.py:1457` for `_auto_code`; the `create_task` site needs its own `from . import agents as hub_agents` if the module-level import is absent. Check before assuming.

- [ ] **Step 6: Run the ingest suites**

Run: `python -m pytest tests/test_ingest.py tests/test_triage.py tests/test_profile_is_a_role.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

Message: `feat: a coding task takes the coding role, whoever triage named`

---

### Task 3: Triage is asked for a profile on general work

**Files:**
- Modify: `taskuary/triage.py:84` (`INTENT_SYSTEM`) and `taskuary/triage.py:466-472` (the appended block)
- Test: `tests/test_profile_is_a_role.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no new callable. The appended block's wording is the contract; the test pins it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile_is_a_role.py`:

```python
from unittest import mock
from taskuary import triage


def prompts(**kw):
    """Every system prompt classify_intent builds, without calling a model."""
    seen = []
    class Fake:
        def __call__(self, system, user, **_):
            seen.append(system); return '{"intent": "fyi", "why": "x"}'
    triage.classify_intent({'subject': 's', 'body': 'b'}, llm=Fake(), profiles='- analyst: our figures', **kw)
    return seen[0]


class TheWorkersBlockTests(unittest.TestCase):
    def test_the_block_asks_on_general_not_coding(self):
        p = prompts()
        self.assertIn('THE WORKERS', p)
        self.assertNotIn('(kind: coding)', p)
        self.assertIn('"kind": "general"', p)

    def test_the_block_says_coding_needs_no_profile(self):
        self.assertRegex(prompts(), r'[Cc]oding needs no profile')

    def test_the_block_survives_an_operator_document(self):
        """The owner's store holds a TRIAGE.md that REPLACES INTENT_SYSTEM (triage.py:408).
        The rule has to ride in the appended block or it never reaches this install."""
        p = prompts(system='My own triage document. Answer JSON with intent, kind, checklist, "summary".')
        self.assertIn('My own triage document', p)
        self.assertIn('THE WORKERS', p)
        self.assertNotIn('(kind: coding)', p)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_profile_is_a_role.py::TheWorkersBlockTests -v`
Expected: FAIL — `'(kind: coding)' unexpectedly found in ...`.

The helper matches the real signature, verified:
`classify_intent(msg, llm=None, soul=None, notes=None, images=None, learned=None, system=None, notes_left=0, mine=(), thread=None, watch=None, playbooks=None, project=None, candidates=None, repos=None, profiles=None, routing_history=None)`.
The `llm` it calls takes `(system, user, max_tokens=…, images=…)`, which is why `Fake.__call__` swallows `**_`.

- [ ] **Step 3: Implement the appended block**

Replace `taskuary/triage.py:466-472` with:

```python
            if profiles:
                system += ('\n\nTHE WORKERS - the specialists this install has for NON-CODING work, each with '
                           'what it is for. When you answer "kind": "general" and one of them plainly fits the '
                           'job, add "profile": "<exactly one name below>" to say WHICH one. Coding needs no '
                           'profile: a coding task always goes to the coding worker, so leave the key out. '
                           'Pick on the WORK the message asks for, not on who sent it. Unsure, or none of them '
                           'fits it better than the others? Leave the key out and nobody is named.\n'
                           + str(profiles)[:2000])
```

- [ ] **Step 4: Implement the constant, for installs with no document**

In `INTENT_SYSTEM` (`triage.py:84`), change the `profile` field description:

```python
    '{"intent": "task|reply_only|fyi", "kind": "coding|general|task", "profile": "<on kind general only: a name from THE WORKERS>", '
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python -m pytest tests/test_profile_is_a_role.py::TheWorkersBlockTests -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

Message: `feat: triage is asked which specialist on general work, not on coding`

---

### Task 4: On general work the role picks the document, not the executable

**Files:**
- Modify: `taskuary/general.py:152-155` (`assigned_pick` → `assigned_role`), `:169`, `:179`, `:421-425`, `:616`
- Test: `tests/test_profile_is_a_role.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `general.assigned_role(store, task: dict) -> str` — the bare role name (`'analyst'`), or `''`. `general.assigned_pick` is **deleted**; no caller may remain.

This reverses a deliberate principle. The comment at `general.py:419` reads *"Triage's named worker also owns general work: its instructions and CLI must travel together, otherwise a research profile is only a label on the task."* The worry is answered, not dismissed: the role still selects the rules document, so it is not only a label. It stops selecting the executable. Replace that comment rather than leaving it contradicting the code.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile_is_a_role.py`:

```python
from taskuary import general


class GeneralRoleTests(unittest.TestCase):
    def task(self, assignee):
        return {'TaskId': 1, 'Kind': 'general', 'Assignee': assignee}

    def test_the_role_is_a_bare_name_not_a_provider(self):
        self.assertEqual(general.assigned_role(store(), self.task('agent:analyst')), 'analyst')

    def test_no_assignee_names_no_role(self):
        self.assertEqual(general.assigned_role(store(), self.task(None)), '')

    def test_an_unknown_name_names_no_role(self):
        self.assertEqual(general.assigned_role(store(), self.task('agent:ghost')), '')

    def test_assigned_pick_is_gone(self):
        """A role must never reach a provider picker again - that IS the bug."""
        self.assertFalse(hasattr(general, 'assigned_pick'))

    def test_a_named_role_does_not_choose_the_provider(self):
        s = store()
        self.assertNotIn('analyst', general.default_pick(s, self.task('agent:analyst')))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_profile_is_a_role.py::GeneralRoleTests -v`
Expected: FAIL — `module 'taskuary.general' has no attribute 'assigned_role'`.

- [ ] **Step 3: Implement the split**

Replace `general.py:152-155` with:

```python
def assigned_role(store, task: dict) -> str:
    """The ROLE triage handed this task - 'analyst' from 'agent:analyst'.

    It chooses the rules document the session is seeded with. It does NOT choose the executable:
    a role and a brain are different questions, and answering both with one name is what routed
    TQ-0588's coding work to Copilot (the spec, 2026-09-16)."""
    who = str((task or {}).get('Assignee') or '')
    name = who.split(':', 1)[1].strip() if who.startswith('agent:') else ''
    return name if name and store.get_agent(name) else ''
```

- [ ] **Step 4: Update the four call sites**

`:169` — the saved-pick reconciliation no longer has an assigned provider to reconcile against. Delete the `assigned = assigned_pick(store, task)` line and simplify the condition to `if saved.get('Pick'):`.

`:179` — `return assigned_pick(store, task) or _selected(store)[0]` becomes `return _selected(store)[0]`.

`:421-425` — the rules-document seed:

```python
    # The role triage named owns the INSTRUCTIONS for general work. Which brain runs them is a
    # separate question, answered from settings - they no longer travel together (the spec).
    role = assigned_role(store, task)
    if role:
        from .agents import ensure_profile_document
        doc = ensure_profile_document(store, role)
        profile_rules = _brief.rules(store, doc, 4_000)
        if profile_rules: system += f'\n\nPROFILE RULES ({doc.upper()}.md)\n{profile_rules}'
```

`:616` — inside `GeneralSession.__init__`, the role must not become a pick:

```python
        if connector_id is None and not pick:
            if any(o['pick'] == saved.get('Pick') for o in provider_options(store)): pick = saved['Pick']
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python -m pytest tests/test_profile_is_a_role.py::GeneralRoleTests -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the general suites**

Run: `python -m pytest tests/test_general.py tests/test_assistant_reactions.py tests/test_chat_relationship.py -v`
Expected: PASS. A test asserting a named worker drives the provider encodes the reversed principle — update it and say so in the commit.

- [ ] **Step 7: Commit**

Message: `feat: on general work a role picks the document, never the executable`

---

### Task 5: Repair the tasks already routed to a brain

**Files:**
- Modify: `taskuary/agents.py` (add `repair_role_assignees` after `routed_role`)
- Modify: `taskuary/server.py:55-57` (call it at boot)
- Test: `tests/test_profile_is_a_role.py`

**Interfaces:**
- Consumes: `agents.coding_role`, `agents.CODING_KINDS` from Tasks 1-2.
- Produces: `agents.repair_role_assignees(store) -> int` — how many tasks it corrected. Idempotent.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_profile_is_a_role.py`:

```python
class RepairTests(unittest.TestCase):
    def rows(self, s):
        return {t['TaskId']: t.get('Assignee') for t in s.list_tasks()}

    def test_a_coding_task_routed_to_a_cli_is_corrected(self):
        """TQ-0585 held agent:copilot; TQ-0586 held agent:analyst on coding work."""
        s = store()
        a = s.create_task({'Title': 'copilot one', 'Kind': 'coding', 'Assignee': 'agent:copilot'}, 'test')
        b = s.create_task({'Title': 'analyst one', 'Kind': 'coding', 'Assignee': 'agent:analyst'}, 'test')
        self.assertEqual(hub_agents.repair_role_assignees(s), 2)
        self.assertEqual(self.rows(s)[a], 'agent:coder')
        self.assertEqual(self.rows(s)[b], 'agent:coder')

    def test_general_assignees_are_left_alone(self):
        s = store()
        g = s.create_task({'Title': 'general one', 'Kind': 'general', 'Assignee': 'agent:analyst'}, 'test')
        hub_agents.repair_role_assignees(s)
        self.assertEqual(self.rows(s)[g], 'agent:analyst')

    def test_a_human_assignee_is_left_alone(self):
        s = store()
        h = s.create_task({'Title': 'mine', 'Kind': 'coding', 'Assignee': 'alex'}, 'test')
        hub_agents.repair_role_assignees(s)
        self.assertEqual(self.rows(s)[h], 'alex')

    def test_it_is_idempotent(self):
        s = store()
        s.create_task({'Title': 'copilot one', 'Kind': 'coding', 'Assignee': 'agent:copilot'}, 'test')
        self.assertEqual(hub_agents.repair_role_assignees(s), 1)
        self.assertEqual(hub_agents.repair_role_assignees(s), 0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_profile_is_a_role.py::RepairTests -v`
Expected: FAIL — `no attribute 'repair_role_assignees'`.

- [ ] **Step 3: Implement**

In `taskuary/agents.py`, after `routed_role`:

```python
def repair_role_assignees(store) -> int:
    """Tasks routed to a BRAIN before roles and brains were separated. `Assignee` holds a role now,
    so a coding task pointed at anything else is corrected to the coding role - TQ-0585 held
    `agent:copilot` and TQ-0586 held `agent:analyst` on coding work. Human assignees and general
    work are untouched, and a second run corrects nothing."""
    role, fixed = coding_role(store), 0
    # search=False: list_tasks otherwise builds seven GROUP_CONCAT blobs over the whole message
    # table - 34ms of a 35ms query on a real store, and a boot repair searches nothing.
    for t in store.list_tasks(search=False):
        who = str(t.get('Assignee') or '')
        if str(t.get('Kind') or '').lower() != 'coding' or not who.startswith('agent:'): continue
        if who == f'agent:{role}': continue
        store.update_task(t['TaskId'], {'Assignee': f'agent:{role}'}, 'migration')
        fixed += 1
    return fixed
```

`list_tasks(status=None, active_only=False, search=True)` is unfiltered by default — verified — so every task is seen, closed ones included.

- [ ] **Step 4: Run it to verify it passes**

Run: `python -m pytest tests/test_profile_is_a_role.py::RepairTests -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Call it at boot**

In `taskuary/server.py`, immediately after `cli_connections.sync(cfg, store)` (line 55):

```python
_repaired = hub_agents.repair_role_assignees(store)
if _repaired: logger.info(f'repaired {_repaired} task(s) routed to a CLI rather than a role')
```

- [ ] **Step 6: Commit**

Message: `fix: tasks routed to a CLI rather than a role are corrected at boot`

---

### Task 6: The whole-suite gate

**Files:** none — this task only verifies.

- [ ] **Step 1: Run the entire suite from the repo root**

Run: `python -m pytest`
Expected: PASS, with a non-zero collected count. `no tests ran` is a failure.

- [ ] **Step 2: Fix what broke, one file at a time**

Expect fallout in files that assert the old rule. For each, decide which it is and record the decision in the commit body:
- *encodes the old rule* (a coding profile on the roster, a named worker driving the provider) — update the assertion to the new rule.
- *genuine regression* — fix the source, not the test.

- [ ] **Step 3: Confirm the owner's own case end to end**

Replay the two real verdicts through `routed_role` against a store shaped like the owner's:

```bash
python -c "
import json
from taskuary import agents
from taskuary.store import MemoryStore
s = MemoryStore()
for n in ('coder', 'copilot'): s.upsert_agent(n, 'coding', 'cli', json.dumps({'cmd': n}))
s.upsert_agent('analyst', 'analysis', 'cli', json.dumps({'cmd': 'claude'}))
print('TQ-0588 (kind=coding, profile=copilot) ->', agents.routed_role(s, 'coding', 'copilot'))
print('TQ-0586 (kind=coding, profile=analyst) ->', agents.routed_role(s, 'coding', 'analyst'))
print('a general ask (kind=general, profile=analyst) ->', agents.routed_role(s, 'general', 'analyst'))
"
```

Expected: `coder`, `coder`, `analyst`.

- [ ] **Step 4: Commit any test updates**

Message: `test: the suite asserts a role is a role, not a brain`

---

## Self-Review

**Spec coverage for step 1:** roster (Task 1), the coding implication and the TQ-0586 case (Task 2), the prompt inversion (Task 3), `assigned_pick` and the reversed principle (Task 4), the data migration (Task 5), the whole-suite gate (Task 6). The spec's step-1 line — *"`agents.roster`, the prompt in `triage.py`, and a data migration"* — is covered, plus `general.assigned_pick`, which the spec gained after the plan research found it.

**Deferred to steps 2 and 3, deliberately:** `provider` staying on the profile row, `default_agent` → `default_brain`, gears onto connections, the three compensating patches, the `transcript.Brain` column, and the general-session gear change from light to main. None of them is needed for a role to stop being a brain.

**Type consistency:** `routed_role(store, kind, profile) -> str` and `coding_role(store) -> str` are used with those signatures in Tasks 2 and 5; `assigned_role(store, task) -> str` in Task 4 only. `CODING_KINDS` is defined in Task 1 and consumed in Tasks 1 and 5.

**Uncertainties resolved before handing over:** `triage.classify_intent`'s signature and `store.list_tasks`'s filtering were both read and the plan now states them rather than asking the implementer to check. One genuine unknown remains and cannot be settled without running it — **which existing tests encode the old rule**. Task 1 Step 5, Task 4 Step 6 and Task 6 Step 2 all say the same thing: decide per file whether the assertion is the old rule or a real regression, and record which in the commit body. Do not mass-update assertions to green the suite.

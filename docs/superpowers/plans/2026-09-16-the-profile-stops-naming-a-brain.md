# The Profile Stops Naming A Brain — Implementation Plan (step 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (or subagent-driven-development).

**Goal:** Take `provider`/`cmd` off the worker profile for good, retire the five CLI-clone profiles, and delete the patches that only existed because a role was a brain.

**Architecture:** Step 2 built the brain layer but left it *opt-in* — `brain_command` acts only when a brain was explicitly chosen, so nothing regressed. Step 3 throws that switch: the migration writes `default_brain`, the pickers choose a brain rather than a worker-that-is-a-brain, the clone profiles go, and failover becomes a chain of brains.

**Spec:** `docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md`
**Follows:** step 1 (`6d2ded64`), step 2 (`e0d0b619`).

## Global Constraints

Unchanged from steps 1 and 2 — concise style, no autoformatters, whole `pytest` before pushing, commit off a temporary index (`scratchpad/commit.sh`), **merge never rebase** in this shared checkout, Node 22 for the bundle, and resolve any `taskuary/web` conflict by rebuilding rather than hand-merging hashes.

**One extra, and it is the ordering constraint of this whole plan:** Task 1 and Task 2 must land **together**. Writing `default_brain` makes `brain_command` apply to every session; until the picker offers brains, "start a session with codex" would resolve the default brain and quietly run claude. That is the exact regression step 2's explicit-choice guard was added to prevent, and it comes back the moment the switch is thrown.

**Never run `python -c "import taskuary.server"`** — that module builds its store against the LIVE database at import time. It ran a migration over the owner's real data once in this work. Use pytest, or point `SQLiteStore` at a copy.

## File Structure

| File | After this plan |
| --- | --- |
| `taskuary/cli_connections.py` | `adopt_installed` registers connections only; no clone profiles; the legacy gear fallback in `resolve` goes |
| `taskuary/agents.py` | `agent_chain` becomes a chain of BRAINS; no dedupe-by-CLI |
| `taskuary/llm.py` | `_build_llm`'s dedupe-by-`cli_of` goes |
| `taskuary/aidefaults.py` | the coding slot names a brain; `_gears`' profile fallback goes |
| `website/src/ui.jsx` | `AgentPicker` offers brains for coding work |

---

### Task 1: The migration throws the switch

- [ ] **Step 1: Failing test** in `tests/test_brain_layer.py`:

```python
class SwitchTests(unittest.TestCase):
    def test_an_upgrade_writes_the_brain_it_was_already_running(self):
        """Blank default_brain kept step 2 opt-in. The migration names it, so the brain layer is
        what actually runs - and it names exactly what was running yesterday."""
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.set_setting('default_agent', 'coder', 'owner')
        self.assertTrue(hub_agents.adopt_brain_setting(s))
        self.assertEqual(s.get_settings()['default_brain'], 'claude')

    def test_it_does_not_overwrite_a_brain_the_owner_chose(self):
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        s.set_setting('default_brain', 'codex', 'owner')
        self.assertFalse(hub_agents.adopt_brain_setting(s))
        self.assertEqual(s.get_settings()['default_brain'], 'codex')
```

- [ ] **Step 2: Run it** — expected FAIL.

- [ ] **Step 3: Implement** in `agents.py`:

```python
def adopt_brain_setting(store) -> bool:
    """Name the brain this install is already running, once. Until `default_brain` is set,
    brain_command stays out of the way (step 2) and the profile's own command still decides - so
    this is the line that actually moves an install onto the brain layer, and it moves it onto
    exactly what it ran yesterday. Returns whether it wrote anything."""
    if str(store.get_settings().get('default_brain') or '').strip(): return False
    key = default_brain(store)                     # derived from the legacy default_agent profile
    if not key: return False
    store.set_setting('default_brain', key, 'migration')
    return True
```

Call it at boot beside `repair_role_assignees` (`server.py`).

- [ ] **Step 4:** run `tests/test_brain_layer.py`; **do not commit yet** — Task 2 lands in the same commit.

---

### Task 2: The picker chooses a brain

With the switch thrown, an agent name no longer selects a CLI. `AgentPicker` (`ui.jsx:841`) and every coding dialog must offer the **brains** — `/api/cli/connections` already lists exactly one row per CLI — and pass the choice as a brain rather than as a worker.

- [ ] **Step 1:** `start_session`/`dispatch` take an explicit `brain` alongside `agent`; `open_session` prefers it over `brain_for`.
- [ ] **Step 2:** `AgentPicker` lists brains for coding work and keeps roles for general work (there the role is the information).
- [ ] **Step 3:** rebuild the bundle with Node 22.
- [ ] **Step 4:** run `tests/test_terminal.py tests/test_api.py tests/test_brain_layer.py`.
- [ ] **Step 5: Commit Tasks 1 and 2 together** — `feat: the brain layer is what runs, and the picker picks a brain`

---

### Task 3: The clone profiles retire

`adopt_installed` mints one coding worker per installed CLI; with brains first-class there is nothing left for those workers to carry. The 2026-09-14 complaint it answered — *"any ai cli agents should be possible to start"* — is answered better by the brain picker.

- [ ] **Step 1: Failing test** — `adopt_installed` registers connections and returns no new profiles; a clone profile with no work on it is removed; one the owner has renamed or given a purpose is KEPT (never delete what the owner edited).
- [ ] **Step 2: Implement**, including a migration that drops the untouched clones (`codex`, `copilot`, `devin`, `opencode`, `qwen` on this install) and leaves their connections.
- [ ] **Step 3:** run `tests/test_cli_connections.py tests/test_agent_profiles.py tests/test_brain_layer.py`.
- [ ] **Step 4: Commit** — `feat: a CLI is a brain, not a worker named after one`

---

### Task 4: The two remaining compensating patches go

- [ ] **Step 1: Failing test** — `agent_chain` returns brains and needs no dedupe; `_build_llm` tries each brain once without inspecting `cli_of`.
- [ ] **Step 2: Implement.** `agents.agent_chain` becomes a chain of brain keys (`backup_agents` → `backup_brains`, `*` = every other configured connection in the owner's order). Delete the `if cli in clis: continue` at `agents.py:620` and the `identity`/`identities` dedupe at `llm.py:170-177` — both exist only because a list of roles was really a list of brains.
- [ ] **Step 3:** run the failover suites plus the whole file set that touches `agent_chain`.
- [ ] **Step 4: Commit** — `refactor: failover is a chain of brains, so it needs no dedupe`

---

### Task 5: The transitional fallbacks go

Step 2 left two, each labelled as temporary:

- `cli_connections.resolve`'s gear merge for a profile carrying only `cmd`.
- `aidefaults._gears`' fallback to the worker's own gears.

- [ ] **Step 1:** delete both; run the suites that covered them and update any fixture still building a profile with gears on it.
- [ ] **Step 2:** remove `provider`/`cmd` from the profile shape — `set_profile` rejects them rather than popping them, and `migrate` stops needing its second pass.
- [ ] **Step 3: Commit** — `refactor: a profile no longer has a field for which brain runs it`

---

### Task 6: The whole-suite gate

- [ ] `python -m pytest` from the repo root; old rule vs regression per failure, recorded in the commit body.
- [ ] Verify on a COPY of the live store: `brain_for` answers `claude`, the roster is the five general roles, and the profile rows carry no `provider`.
- [ ] Merge/push per the Global Constraints.

## Self-Review

**Spec coverage:** removing `provider`/`model` from the profile (Tasks 1, 2, 5), the three compensating patches (one landed in step 2, two in Task 4), `backup_agents` → `backup_brains` (Task 4), and `adopt_installed` no longer minting workers (Task 3).

**Riskiest:** Tasks 1+2, which is why they are one commit. The regression they can cause is known and named because step 2's guard already caught it once.

**Deliberately not here:** the Assistant's gear (still the spec's one `ASSUMPTION`), authority per profile (stays in `scopes.py`), and profiles accreting from sessions.

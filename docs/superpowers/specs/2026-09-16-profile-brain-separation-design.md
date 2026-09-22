# A profile is a role; a brain is what runs it

**Date:** 2026-09-16
**Status:** IMPLEMENTED — steps 1-3 shipped 2026-09-16 (`6d2ded64`, `e0d0b619`, `b8c57823`)
**Owner decisions:** recorded inline as `DECIDED`

> **What shipped, and what did not.** Triage names a role and never a brain; a coding task's role
> is always `coder`; the brain is a CLI connection carrying its own gears, chosen by
> `default_brain` with a per-role override and by the picker at start; failover walks brains;
> sessions record which brain ran; the card names the brain, and names it correctly (`cli_of` read
> the *wrapper*, so Copilot reported `cmd` and Qwen `node`).
>
> Three things in this document did NOT ship, deliberately, each with its reason in the step-3
> plan: the `_build_llm` dedupe survives because `triage_ai` still spells a brain as `cli:<agent>`;
> existing clone profile rows are not deleted; and `provider`/`cmd` remain on the profile row as a
> compatibility source for display data, no longer deciding what runs. The Assistant's gear stays
> light — still the one `ASSUMPTION` below, never confirmed.

## The problem

On 2026-09-16 the owner opened TQ-0588, a coding task, and found GitHub Copilot
working it. The default coding agent is Claude and has been all along. Nothing
had been reconfigured.

The triage brain's verdict for that message (`route` row 8221):

```json
{"intent": "task", "kind": "coding", "profile": "copilot",
 "repository": "northwind/ledger", ...}
```

Triage named a *worker*, which is exactly what it is asked to do and exactly what
it is allowed to do. The trouble is that `copilot` is not a worker. It is a CLI
wearing a worker's clothes, and naming it named a brain.

**Two fields carry both answers at once.**

*At rest* — `provider` lives on the profile row. A profile is a role
(`kind`, `purpose`, `rules_doc`, `cwd_map`) and it also says which executable
runs it. `cli_connections.resolve` merges the brain's flags into the role blob
before anything starts, so by the time a session is built the two are one dict.

*At runtime* — `Assignee` holds `agent:<profile>`, and `_auto_code` reads it
(`ingest.py:1461`):

```python
_who = str((store.get_task(tid) or {}).get('Assignee') or '')
agent = _who.split(':', 1)[1].strip() if _who.startswith('agent:') and ... else hub_agents.default_agent(store)
```

The comment above that line is right about roles:

> the worker this task was ROUTED to (Assignee), else whoever takes work by
> default. Without this the profile triage chose was written on the task and then
> ignored at the moment it mattered.

A routed *role* should beat a default. But the same string is a brain, so a
routed brain beats the default too. `default_agent` is reached only when
`Assignee` is empty, which for a triaged task it never is. Copilot did not win a
fight with the default; the default was never asked.

*On general work* — `general.assigned_pick` (`general.py:152`) turns the same
field into a provider:

```python
def assigned_pick(store, task: dict) -> str:
    who = str((task or {}).get('Assignee') or '')
    name = who.split(':', 1)[1] if who.startswith('agent:') else ''
    return f'cli:{name}' if name and store.get_agent(name) else ''
```

Four call sites use it — the session's provider (`general.py:179`), its saved-pick
reconciliation (`:169`), the profile rules it seeds (`:421`) and a workflow repeat
(`:616`). The comment above the third states the principle being overturned here:

> Triage's named worker also owns general work: **its instructions and CLI must
> travel together**, otherwise a research profile is only a label on the task.

That is the inverse of this design, and it is deliberate, not accidental. The
worry behind it is real and is answered rather than dismissed: a role is *not*
only a label, because it still selects the rules document the session is seeded
with (`general.py:421`). What it stops selecting is the executable. So
`assigned_pick` splits in two — the role keeps choosing the document, and the
provider comes from settings like everywhere else.

### Where the clone profiles came from

`cli_connections.adopt_installed` mints one coding worker per installed CLI:

```python
profiles[spec['name']] = {
    'kind': 'coding', 'rules_doc': 'coder', 'provider': f'cli:{key}',
    'purpose': coding.get('purpose') or 'Write, review and test code in a repository.',
    'cwd_map': dict(coding.get('cwd_map') or {})}
```

Its docstring states the consequence plainly: *"the only thing that varies
between them is which CLI runs it."* It was written for a real complaint
(2026-09-14: a CLI installed after the setup wizard ran appeared nowhere and
could not be started at all) and the fix is sound. What is wrong is that the
thing it creates to hold a CLI is a **worker**, and workers are what triage
chooses between.

On the owner's install this produced a roster of eleven, six of which are the
same job:

```
- coder:     Write, review and test code in a repository.
- codex:     Write, review and test code in a repository.
- copilot:   Write, review and test code in a repository.
- devin:     Write, review and test code in a repository.
- opencode:  Write, review and test code in a repository.
- qwen:      Write, review and test code in a repository.
- researcher/analyst/coordinator/marketer/trader: <distinct purposes>
```

Triage is told to pick one and to leave the key out only when none fits *better
than the others*. Six byte-identical lines never trip that clause, so the choice
is a coin flip: TQ-0585 and TQ-0588 drew copilot, TQ-0587 and TQ-0589 drew coder.

### The question is asked on the wrong kind

`triage.py:468` binds the profile question to coding:

> When an agent will start on this **(kind: coding)**, add `"profile": "<exactly
> one name below>"` to say WHICH one.

Every profile choice in the owner's store landed on a coding task, and general
work got none at all:

| Task | Kind | Profile chosen | Assignee |
| --- | --- | --- | --- |
| TQ-0580, TQ-0582 | general | — | `None` |
| TQ-0585 | coding | copilot | `agent:copilot` |
| TQ-0586 | coding | **analyst** | `agent:analyst` |
| TQ-0587 | coding | coder | `agent:coder` |
| TQ-0589 | coding | coder | `agent:coder` |

So the choice is offered exactly where it should not exist and withheld exactly
where it should be made. TQ-0586 is the second half of the bug: an **analyst on a
coding task**, which the rule below forbids as firmly as it forbids copilot.

### The model value has the same problem one level down

When commands were split onto connections, `model_arg` — the *flag* — moved.
`model` and `light_model` — the *values* — could not, because the profile was the
only row that existed per role-and-brain pair. So they stayed, with a patch
(`cli_connections.py:122`):

```python
# Model names belong to their provider; a Claude override cannot follow a worker to Codex.
for field in ('model', 'light_model'):
    if field not in body: profile.pop(field, None)
```

The comment names the correct rule and the code cannot obey it. It scrubs the
value on provider change instead of storing it where it belongs.

### Three patches exist only to compensate

| Patch | What it works around |
| --- | --- |
| `cli_connections.py:122` scrubs `model`/`light_model` on provider change | models stored on the role |
| `agents.agent_chain` skips names whose `cli_of` was already seen (`agents.py:620`) | a failover list of roles that is really a list of brains |
| `llm._build_llm` dedupes candidates by `cli_of` — *"trying Claude three times under coder/researcher/analyst is not failover"* (`llm.py:170-177`) | the same, for the classifier's fallbacks |

A design that removes three patches is worth more than one that adds a feature.

## The two things, separated

| | Profile (role) | Brain |
| --- | --- | --- |
| Answers | *what this worker is for* | *what actually runs* |
| Holds | `kind`, `purpose`, `rules_doc`, `cwd_map` | `cmd`, `args`, `resume_args`, `timeout`, `model_arg`, `acp`, **`model`**, **`light_model`** |
| Lives in | `agent` rows / `[agents.*]` | `[cli_connections.*]` |
| Chosen by | triage, or the owner at start | settings, or the owner at start |
| Named by triage | yes | **never** |

## Decisions

**DECIDED: a profile never pins a brain.** The two are inherently unrelated. A
per-profile override is available, but it is a *setting keyed by a profile* that
names a brain — never a field on the profile, and never a model.

**DECIDED: one default brain for everything.** General workers use the same brain
as coding by default. There is no separate general-brain default and no
kind-to-brain table.

**DECIDED: one brain carries multiple gears, and it is still the same brain.**
Triage runs on the main brain at a quicker model; a CLI session always takes the
main model. `claude-main` and `claude-light` are not two brains.

**DECIDED: triage names profiles only.** Never a brain, never a model, never an
effort level.

**DECIDED: coding implies `coder`; the profile question belongs to general work.**
If triage decides `kind: coding`, the profile is `coder` and there is nothing to
choose. The roster triage is shown holds only the general roles — `researcher`,
`analyst`, `coordinator`, `marketer`, `trader` — so a coding worker cannot be
named on general work and a general worker cannot be named on coding work. This
is the inverse of today's prompt and closes the bug class structurally rather
than by validation: the wrong answer is not in the menu.

**DECIDED: the brain is never stamped on the task.** `Assignee` keeps holding a
role. The brain is resolved at session start, every time, from settings. A brain
frozen onto a task at routing time would go stale the moment the default changed,
and would re-introduce the second place this design exists to remove. Which brain
ran is a fact of the *session*: live, it is already served as `cli` from
`cli_of(sess.argv)`; durably, the `transcript` row gains a `Brain` column beside
its existing `Agent`. (A pty session writes no `run` row — `run` belongs to the
older dispatch path — so the transcript is the record that has to carry it.)

**DECIDED (owner, 2026-09-16): the list names the BRAIN, and it must be right.**
*"On the task list it says which coding agent owns it — make sure the task has
the correct coding agent."*

Once a coding task's role is always `coder`, the role is no longer worth showing:
every coding row would read the same. What the owner wants named is which coding
agent actually has it. Two places show it today and both name the role:

| Where | Reads | Says after step 1 |
| --- | --- | --- |
| `BoardView.jsx:484` — the chip titled *"X owns this task"* | `assignedAgent(t.Assignee)` | always `coder` |
| `BoardView.jsx:464` — the live badge | `live.AgentName` / `t.RunAgent` | the role |

So both switch to the brain: the one resolved for the task when nothing is
running, and the one actually running when something is.

### …and the name it shows is currently wrong

`terminal.cli_of` takes `argv[0]`'s basename, which is the *wrapper* whenever a
CLI resolves to a `.BAT`/`.CMD` or is launched through node:

| Profile `cmd` | `argv[0]` | `cli_of` reports |
| --- | --- | --- |
| claude | `…\claude.exe` | `claude` ✓ |
| codex | `…\codex.EXE` | `codex` ✓ |
| copilot | `cmd` (`cmd /c …\copilot.BAT`) | **`cmd`** |
| qwen | `…\node.EXE` | **`node`** |

This is served straight to the UI as `session.cli` (`server.py:2566`,
`terminal.py:466`) and is what the `by:` chip on the task page renders — it read
`by: claude` on a Copilot session in the owner's own screenshot. Naming the brain
is worth nothing if the name is `cmd`, so step 2 fixes `cli_of` to report the CLI
the profile names rather than whatever launched it.

## The model

### Profile

`kind`, `purpose`, `rules_doc`, `cwd_map`. Nothing else. Six roles survive, in two
groups that never mix:

- **the coding role** — `coder`. Implied by `kind: coding`, never on the roster.
- **the general roles** — `researcher`, `analyst`, `coordinator`, `marketer`,
  `trader`. These are the roster, and the only thing triage ever names.

### Brain

A `cli_connections` entry gains the two gear fields it should always have had.
`COMMAND_FIELDS` grows from seven to nine:

```python
COMMAND_FIELDS = ('cmd', 'args', 'resume', 'resume_args', 'timeout',
                  'model_arg', 'acp', 'model', 'light_model')
```

`light_model` keeps its existing two spellings, which `llm.make_cli_llm` already
parses: `gpt-5.4-mini@low` (a model plus a reasoning level) and `effort:low` (a
level alone, for a codex on a ChatGPT plan that serves only its plan's models).

### Settings

| Setting | Was | Becomes |
| --- | --- | --- |
| `default_agent` | a profile name (`coder`) labelled "Default coding CLI" | `default_brain`, a CLI key (`claude`) |
| — | — | `profile_brains`, an optional map `{profile: brain}` |

`triage_ai` and `concierge_ai` are unchanged. Both must keep being able to name an
API connector rather than a CLI — the owner's point at both today (`connector:7`).

### Gear by job

| Job | Gear | Reached through |
| --- | --- | --- |
| Coding session | main | `terminal.start_on_task` |
| General worker session | main | `general.py` → `llm.build_llm` |
| Triage, drafts, summaries, digest | light | `llm.make_cli_llm` |
| Assistant / concierge turns | light | `concierge.py` → `make_cli_llm` |

**This changes general worker sessions.** `make_cli_llm` applies the light gear
unconditionally and only an explicit per-job model outranks it (`llm.py:102`).
General sessions reach it via `build_llm(pick, model=…)` where the model falls
back to the profile's main `model`, which on all eleven of the owner's profiles is
`None` — so a general session silently runs on the light gear today. Under the
rule above it takes main, like coding.

**ASSUMPTION, flagged for the owner:** the Assistant stays on the light gear.
`aidefaults` already describes it as riding "the same quick gear as triage", and
the decision above was about general *workers*, not about chat turns. If the
Assistant should move to main too, say so and this table changes.

### Routing

| Triage says | Profile | Chosen by |
| --- | --- | --- |
| `kind: coding` | always `coder` | nobody — implied |
| `kind: general` | one of the five general roles | triage, from the roster |
| `kind: general`, none fits | none — `Assignee` stays empty | nobody — key left out |

The last row is today's behaviour and stays: TQ-0580 and TQ-0582 carry no
assignee, and the owner picks a role when they start a session. There is no
"default general role", and this design does not invent one — that would be a
third default to keep in step with the other two.

`agents.roster` stops emitting coding profiles: the menu is the five general
roles, and `triage.py`'s prompt moves the question from "(kind: coding)" to
general work. Validation at `triage.py:541` keeps rejecting any name not on the
menu, so a hallucinated `copilot` routes nowhere — but now it is also not a name
the menu could have offered.

`ingest.py:776` — the single place a verdict becomes an assignee — is unchanged
in shape, gaining only the coding implication:

```python
**({'Assignee': f"agent:{intent['profile']}"} if intent.get('profile') else {})
```

`_auto_code` reads `Assignee` for the role and `default_brain` for the brain. The
default is consulted on every dispatch, which is what makes the rule "coding
always goes to the default coding CLI" true.

### Manual start

Already wired: `start_session(tid, agent, model)` (`server.py:1985`) and
`AgentPicker` (`TasksView.jsx:1244`) both carry agent and model today. The picker
gains a brain choice alongside the role; the owner may pick either, both, or
neither.

### Failover

`agent_chain` becomes a chain of *brains*, not of profile names, and its
dedupe-by-`cli_of` disappears with the thing it was working around. `backup_agents`
becomes `backup_brains`; `*` keeps meaning "every other one, in the owner's order".

## Migration

On the owner's live install:

| | From | To |
| --- | --- | --- |
| Profiles | 11 rows | 6 roles; `codex`, `copilot`, `devin`, `opencode`, `qwen` become brains only |
| `default_agent` | `coder` | `default_brain = claude` |
| `backup_agents` | `''` | `backup_brains = ''` |
| Tasks | TQ-0585 holds `agent:copilot`; TQ-0586 holds `agent:analyst` on a `coding` task | `agent:coder` for both (TQ-0588 was already reassigned by hand on 2026-09-16) |
| `[cli_connections.*]` | commands only | commands plus gears, inheriting each profile's `model`/`light_model` |

`adopt_installed` stops minting profiles and registers connections only. The
2026-09-14 complaint it was written for still holds: every installed CLI remains
startable, because the picker offers brains directly instead of reaching them
through a worker.

A profile row that still carries `provider`/`cmd`/`model` after migration is
ignored, not honoured — a half-migrated install must not quietly keep routing by
brain. `resolve()` keeps its "old callers remain compatible during upgrades"
branch for one release, logging when it fires.

## What it costs

The honest number: **70 of 267 test files** reference `provider` or `'cmd'`. Most
is fixture noise of the shape
`upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))`, which a
fixture helper can absorb in one edit. The files that assert the *fused* behaviour
and need real rework are smaller in number and larger in each:
`test_cli_connections.py`, `test_ai_defaults.py`, `test_agent_profiles.py`,
`test_terminal.py`, `test_core.py`, `test_general.py`.

Landing order, so the owner-visible bug is fixed before the structural work:

1. **Move the profile question from coding to general.** The roster becomes the
   five general roles; `kind: coding` implies `coder`. Fixes both halves of the
   bug — copilot on TQ-0588 and analyst on TQ-0586 — on its own, and touches
   little: `agents.roster`, the prompt in `triage.py`, and a data migration.
2. **Add the brain layer.** Gears onto connections, `default_brain` and
   `profile_brains` into settings, brain resolved at session start.
3. **Remove `provider`/`model` from profiles**, delete the three patches, rework
   the tests.

Each step is shippable and leaves the suite green.

## Explicitly not doing

- **Authority per profile.** Stays in `scopes.py` on the connector card, per
  `docs/agent-profiles.md`: *"Two places to set authority is one too many."*
- **Profiles accreting from sessions** the way playbooks do. Still open, still
  deferred.
- **Renaming `Assignee`.** It holds a role, which is what its name has always
  implied.

## Testing

New coverage, beyond reworking what exists:

- the roster holds only the five general roles: no CLI name and no `coder`
- `kind: coding` yields `Assignee = agent:coder` whatever the verdict's `profile`
  said — the TQ-0586 case, an `analyst` named on coding work
- a verdict naming a CLI (`profile: "copilot"`) is rejected by roster validation,
  and the task falls to the default role
- `kind: general` with no profile named leaves `Assignee` empty — it must never
  fall through to `coder`
- `_auto_code` consults `default_brain` on every dispatch, including when
  `Assignee` names a role
- a coding session and a general session both take the main gear; triage, the
  drafter, the digest and the assistant take light
- `profile_brains` overrides the default for one role and leaves the others alone
- the migration: eleven profiles to six, two tasks reassigned, gears landing on
  the right connections
- a leftover `provider` on a profile row is ignored, and says so in the log

Per `docs/` house rule, the full `pytest` from the repo root must pass before any
of this is pushed; "no tests ran" is a failure.

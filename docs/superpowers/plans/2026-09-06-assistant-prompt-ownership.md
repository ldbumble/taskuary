# Assistant Prompt Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The editable COUNSEL document is the only place the assistant's behaviour is written; code keeps only the machine contract and the backend safeguards, and every other prompt (reports, briefs, workers) receives exactly the COUNSEL sections that apply to its role.

**Architecture:** A small loader in `taskuary/counsel.py` splits COUNSEL into its `## ` sections and hands each consumer the sections for its role (chat: all; briefs and suggestion replies: intro + goal + voice; workers: voice; scheduled reports: none). `concierge.SYSTEM` shrinks to a machine contract (the OPTIONS / DECIDE line grammar and the verb vocabulary); its behavioural prose moves into a new shipped COUNSEL section, and a startup migration appends that section to a live document the owner has edited instead of overwriting it. No loader ever cuts COUNSEL; an over-budget document warns and audits.

**Tech Stack:** Python 3.10, FastAPI, SQLite (`taskuary/store.py` docs table), pytest (`unittest` style files under `tests/`), loguru.

**Spec:** `docs/processing-walkthrough-todos.md` — PW-242, PW-243, PW-244 (lines 1362-1372), PW-248 (1395-1401), PW-256..PW-260 (1448-1464). Owner decisions recorded there under PW-245..PW-255 are already done and constrain this plan.

## Global Constraints

- Coding style: the repo's dense fast.ai style (`~/.claude/skills/concise-code-style/SKILL.md`). No autoformatters.
- `taskuary/server.py` is CRLF on disk today; other files are LF. Patch files by reading with `newline=''` and writing back with the line ending you found. Heredocs eat backslashes on this box: never write a `\` line continuation through a heredoc.
- Work in a scratch worktree (`superpowers:using-git-worktrees`); a Codex agent commits to the live checkout. `website/node_modules` is a junction: unlink it before `git worktree remove` (memory: coder-shares-the-checkout). No bundle rebuild is needed for this plan (no JSX changes).
- Tests run from the repo root: `python -m pytest -q -p no:cacheprovider`. `tests/conftest.py` forces a temp `TASKUARY_HOME`; never run a test file directly with `python tests/x.py`.
- Never write to the owner's live `~/.taskuary` from a test or a script. The live COUNSEL document changes only through the startup migration in Task 5, when the owner restarts.
- Owner rule (PW-248): "retain the minimal machine action contract needed to render validated action buttons, but no competing hardcoded behavior. Removing behavioral prose must not remove action schemas or backend checks."
- Owner rule (PW-256): "preserving existing owner edits through an explicit migration rather than overwriting them."
- Owner rule (PW-259): "Resolve each through the walkthrough, not an unreviewed blanket rewrite." Findings that need an owner decision are recorded as open PW items, not fixed silently.
- Commit messages follow the walk: `feat: <one line> (PW-…)` for code, `docs: record Section <n> acceptance (PW-…)` for the ledger.

---

## File map

| File | Responsibility after this plan |
|---|---|
| `taskuary/counsel.py` | COUNSEL loader: `load`, `sections`, `for_chat`, `for_brief`, `for_discussion`, `for_worker`, `check_budget`, `migrate` |
| `taskuary/templates/counsel.md` | Shipped default; gains `## When the owner decides` (the prose leaving `concierge.SYSTEM`), marked `<!-- counsel:deciding -->` |
| `taskuary/concierge.py` | `CONTRACT` (machine grammar only) replaces `SYSTEM`; `_counsel` delegates to `counsel.load`; `_system` = `for_chat` + `CONTRACT` |
| `taskuary/assistant.py` | `think()` builds its report prompt without COUNSEL; the suggestion reply at ~line 958 uses `for_discussion` |
| `taskuary/digest.py`, `taskuary/evening.py` | `system()` uses `for_brief` |
| `taskuary/general.py` | worker prompt uses `for_worker` (no `_cut` of COUNSEL) |
| `taskuary/server.py` | `put_doc` calls `check_budget`; `_lifespan` calls `counsel.migrate(store)` after `processing_startup.initialize` |
| `tests/test_counsel_sections.py` | Task 1 |
| `tests/test_report_prompt_isolation.py` | Task 2 (PW-242/244) |
| `tests/test_counsel_consumers.py` | Task 3 (PW-243/258) |
| `tests/test_concierge_counsel.py` | Task 4 extends (PW-248/256/257/260) |
| `tests/test_counsel_migration.py` | Task 5 (PW-256) |
| `docs/processing-walkthrough-todos.md`, `docs/processing-acceptance-ledger.md`, `docs/processing-implementation-evidence.md` | Task 7 |

---

### Task 1: COUNSEL sections loader

**Files:**
- Modify: `taskuary/counsel.py` (append after `msg_of`, ~line 100)
- Modify: `taskuary/concierge.py:254-268` (`_counsel` becomes a delegate)
- Test: `tests/test_counsel_sections.py`

**Interfaces:**
- Produces:
  - `counsel.load(store) -> str` — the rendered document, comments stripped, blank restored from the shipped default (moved verbatim from `concierge._counsel`).
  - `counsel.sections(text: str) -> dict[str, str]` — `{'': intro, 'What I do, and what I never do': body, 'My goal': body, 'Voice': body, ...}`; keys are the `## ` heading text, `''` is everything before the first `## `.
  - `counsel.pick(store, *heads: str) -> str` — the intro plus the named sections, in document order, joined by blank lines. If **none** of the named heads exist in the document (an owner renamed them), returns the whole document: guidance is never dropped silently (PW-243).
  - `counsel.for_chat(store) -> str` — the whole document.
  - `counsel.for_brief(store) -> str` — `pick(store, 'My goal', 'Voice')`.
  - `counsel.for_discussion(store) -> str` — `pick(store, 'Voice')`.
  - `counsel.for_worker(store) -> str` — `pick(store, 'Voice')`.
  - `counsel.CHAT_HEAD = 'What I do, and what I never do'`, `counsel.GOAL_HEAD = 'My goal'`, `counsel.VOICE_HEAD = 'Voice'`, `counsel.DECIDING_HEAD = 'When the owner decides'`.

- [ ] **Step 1: Write the failing tests**

```python
"""COUNSEL is one document with sections; each consumer gets the sections for its role (PW-243)."""
import unittest

from taskuary import counsel
from taskuary.store import MemoryStore

DOC = ("# COUNSEL.md — I am Taskuary\n\nI have Uri's back.\n\n"
       "## What I do, and what I never do\n- I SURFACE the top eligible item.\n\n"
       "## My goal\n- Walk them through Unread.\n\n"
       "## Voice\n- Be plain, direct, and concise.\n")


class Sections(unittest.TestCase):
    def test_sections_split_on_h2_and_keep_the_intro(self):
        s = counsel.sections(DOC)
        self.assertEqual(list(s), ['', 'What I do, and what I never do', 'My goal', 'Voice'])
        self.assertIn("I have Uri's back.", s[''])
        self.assertEqual(s['Voice'].strip(), '- Be plain, direct, and concise.')

    def test_each_role_gets_its_sections_and_nothing_else(self):
        st = MemoryStore(); st.save_doc('counsel', DOC, 'owner')
        self.assertIn('I SURFACE', counsel.for_chat(st))
        brief = counsel.for_brief(st)
        self.assertIn('Walk them through Unread', brief); self.assertIn('Be plain', brief); self.assertNotIn('I SURFACE', brief)
        for f in (counsel.for_discussion, counsel.for_worker):
            out = f(st)
            self.assertIn('Be plain', out); self.assertNotIn('I SURFACE', out); self.assertNotIn('Walk them through', out)
            self.assertIn("I have Uri's back.", out, 'the intro travels with every role')

    def test_renamed_headings_fall_back_to_the_whole_document(self):
        st = MemoryStore(); st.save_doc('counsel', "# Mine\n\n## How I talk\n- Short.\n", 'owner')
        self.assertEqual(counsel.for_worker(st).strip(), "# Mine\n\n## How I talk\n- Short.")

    def test_load_strips_comments_and_restores_a_blank_document(self):
        st = MemoryStore(); st.save_doc('counsel', '<!-- nothing -->', 'owner')
        text = counsel.load(st)
        self.assertIn('I am Taskuary', text)
        self.assertEqual(st.get_doc_row('counsel')['UpdatedBy'], 'template')


if __name__ == '__main__': unittest.main()
```

If `store.get_doc_row` does not exist, use the existing lookup the current `tests/test_concierge_counsel.py` uses for `UpdatedBy` (open that file first and copy its exact call).

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_counsel_sections.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'taskuary.counsel' has no attribute 'sections'`

- [ ] **Step 3: Implement the loader**

Append to `taskuary/counsel.py`:

```python
# ── the document itself: one file, sections per role ─────────────────────────────────────────
# COUNSEL.md is written for the chat. The morning brief, a reply to a suggestion and a worker's
# prompt each borrow PART of it - the walkthrough rules (Current, Next, the bottom strip) are
# the chat's alone, and letting them into a report prompt was role leakage (PW-242/243).
CHAT_HEAD, GOAL_HEAD, VOICE_HEAD, DECIDING_HEAD = 'What I do, and what I never do', 'My goal', 'Voice', 'When the owner decides'
_COMMENT = re.compile(r'<!--.*?-->', re.S)

def load(store) -> str:
    """The complete document as the AI reads it. Blank or comment-only restores the shipped default,
    audited; a missing default is an explicit error - never a hidden fallback prompt (PW-245)."""
    from pathlib import Path
    doc = _COMMENT.sub('', store.doc('counsel') or '').strip()
    if doc: return doc
    path = Path(__file__).parent / 'templates' / 'counsel.md'
    try: template = path.read_text(encoding='utf-8')
    except OSError as e: raise RuntimeError('COUNSEL is missing or blank and its shipped default could not be read. Restore COUNSEL in Docs.') from e
    if not _COMMENT.sub('', template).strip(): raise RuntimeError('COUNSEL and its shipped default are blank. Restore COUNSEL in Docs.')
    store.save_doc('counsel', template, 'template')
    store.audit('doc', 0, 'restored_blank', 'system', detail={'doc': 'counsel'})
    logger.warning('COUNSEL was missing or blank; restored the shipped default in Docs')
    return _COMMENT.sub('', store.doc('counsel') or '').strip()

def sections(text: str) -> dict:
    """{'': the intro, '<h2 text>': its body, ...} in document order."""
    out, head = {}, ''
    for line in (text or '').splitlines():
        if line.startswith('## '): head = line[3:].strip(); out.setdefault(head, '')
        else: out[head] = out.get(head, '') + line + '\n'
    return {k: v.strip('\n') for k, v in out.items()}

def pick(store, *heads: str) -> str:
    """The intro plus the named sections. None of them present (an owner renamed the headings)
    means the whole document: guidance is never dropped silently (PW-243)."""
    text = load(store); parts = sections(text)
    if not any(h in parts for h in heads): return text
    return '\n\n'.join([parts.get('', '')] + [f'## {h}\n{parts[h]}' for h in parts if h in heads]).strip()

def for_chat(store) -> str: return load(store)
def for_brief(store) -> str: return pick(store, GOAL_HEAD, VOICE_HEAD)
def for_discussion(store) -> str: return pick(store, VOICE_HEAD)
def for_worker(store) -> str: return pick(store, VOICE_HEAD)
```

Then in `taskuary/concierge.py` replace the body of `_counsel` (lines 254-268) with a delegate, keeping the name because `tests/test_concierge_counsel.py` and `_system` use it:

```python
def _counsel(store) -> str:
    """The chat reads the whole document (counsel.load restores a blank one, audited)."""
    from . import counsel
    return counsel.for_chat(store)
```

Remove the now-unused `from pathlib import Path` in concierge.py only if nothing else there uses `Path` (grep first).

- [ ] **Step 4: Run the new tests and the existing loader tests**

Run: `python -m pytest tests/test_counsel_sections.py tests/test_concierge_counsel.py -q -p no:cacheprovider`
Expected: all PASS (the three existing loader tests still hold because `load` is the moved body).

- [ ] **Step 5: Commit**

```bash
git add taskuary/counsel.py taskuary/concierge.py tests/test_counsel_sections.py
git commit -m "feat: COUNSEL is loaded once and handed out by section per role (PW-243)"
```

---

### Task 2: Scheduled reports stop reading the chat's COUNSEL (PW-242, PW-244)

**Files:**
- Modify: `taskuary/assistant.py:755-765` (`think()` prompt assembly)
- Test: `tests/test_report_prompt_isolation.py`

**Interfaces:**
- Consumes: nothing new. `think(store, cands, llm, instruction=None, max_lines=MAX_LINES, watch_source_ids=None, watch_sources=None, systems_only=False)` keeps its signature.
- Produces: the report system prompt is `direction + contract + soul` only. `assistant.PROMPT`, `assistant.SYSTEMS_PROMPT`, `assistant.CONTRACT`, `assistant.SYSTEMS_CONTRACT` unchanged.

- [ ] **Step 1: Write the failing test**

```python
"""A scheduled report's prompt is the report's own: instruction, data scope, output contract. Editing the
chat's COUNSEL must not move it (PW-242, PW-244)."""
import unittest

from taskuary import assistant
from taskuary.store import MemoryStore


class Spy:
    def __init__(self): self.calls = []
    def __call__(self, system, user, **kw): self.calls.append((system, user)); return '1. nothing new today'


class ReportPromptIsolation(unittest.TestCase):
    def prompt(self, store, instruction):
        llm = Spy(); assistant.think(store, [], llm, instruction=instruction); return llm.calls[-1][0]

    def test_editing_chat_counsel_does_not_change_the_report_prompt(self):
        st = MemoryStore()
        before = self.prompt(st, 'List anything about invoices.')
        st.save_doc('counsel', '# Mine\n\n## Voice\n- Shout everything in capitals.\n', 'owner')
        after = self.prompt(st, 'List anything about invoices.')
        self.assertEqual(before, after)
        self.assertNotIn('Shout everything', after)
        self.assertNotIn('I SURFACE', after)

    def test_the_report_keeps_its_instruction_and_contract(self):
        st = MemoryStore()
        system = self.prompt(st, 'List anything about invoices.')
        self.assertIn("YOUR INSTRUCTION (the owner's, from the Reports tab):\nList anything about invoices.", system)
        self.assertIn('writing your POST', system)

    def test_a_systems_monitor_keeps_its_own_prompt_and_rule(self):
        st = MemoryStore(); llm = Spy()
        assistant.think(st, [], llm, instruction='Only failed nightly jobs.', systems_only=True)
        system = llm.calls[-1][0]
        self.assertIn("THE OWNER'S RULE FOR THIS MONITOR:\nOnly failed nightly jobs.", system)
        self.assertIn(assistant.SYSTEMS_PROMPT[:40], system)
        self.assertNotIn('I am Taskuary', system)


if __name__ == '__main__': unittest.main()
```

If `think` needs an AI connector row to run with an explicit `llm`, look at how `tests/test_digest_brief.py::test_the_scheduled_run_hands_the_digest_system_to_the_model` sets up its store and copy that setup into a `setUp`.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_report_prompt_isolation.py -q -p no:cacheprovider`
Expected: `test_editing_chat_counsel_does_not_change_the_report_prompt` FAILS (the prompt currently starts with the COUNSEL text); the other two may already pass.

- [ ] **Step 3: Remove COUNSEL from the report prompt**

In `taskuary/assistant.py` `think()`, delete the line `doc = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()` and change the `system = (doc + f"\n\nYOUR INSTRUCTION ...` assembly to:

```python
    # the report's prompt is the report's own: instruction, data scope, output contract, owner (PW-242).
    # COUNSEL is the chat's document; its walkthrough rules governed idea generation until 2026-09-06.
    system = (f"YOUR INSTRUCTION (the owner's, from the Reports tab):\n{direction}" + contract.replace('{max_lines}', str(max_lines))
              + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else ''))
```

Update the docstring's first line to: `"""One call: the owner's instruction (the Reports tab), the candidates, the day, what was already said."""`

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_report_prompt_isolation.py tests/test_assistant_reactions.py -q -p no:cacheprovider` and then `python -m pytest -q -p no:cacheprovider -k "assistant or think or report"`
Expected: PASS. If an existing test asserted COUNSEL text inside a report prompt, it is asserting the leak: change that assertion to the instruction/contract lines and say so in the commit body.

- [ ] **Step 5: Commit**

```bash
git add taskuary/assistant.py tests/test_report_prompt_isolation.py
git commit -m "feat: a scheduled report's prompt is its own - COUNSEL no longer governs idea generation (PW-242, PW-244)"
```

---

### Task 3: Briefs, suggestion replies and workers get their sections; no COUNSEL is ever cut (PW-243, PW-258)

**Files:**
- Modify: `taskuary/digest.py:216-223` (`system()`)
- Modify: `taskuary/evening.py:52-59` (`system()`)
- Modify: `taskuary/assistant.py:~958-963` (the suggestion reply prompt)
- Modify: `taskuary/general.py:308` and `:321` (worker prompt)
- Modify: `taskuary/counsel.py` (add `check_budget`)
- Modify: `taskuary/server.py` `put_doc` (~line 3995)
- Test: `tests/test_counsel_consumers.py`

**Interfaces:**
- Consumes: `counsel.for_brief`, `counsel.for_discussion`, `counsel.for_worker` from Task 1.
- Produces: `counsel.BUDGET = 8_000`; `counsel.check_budget(store, name: str, text: str) -> str` returns `text` unchanged and, when `len(text) > BUDGET`, logs a warning and writes `store.audit('doc', 0, 'over_budget', 'system', detail={'doc': name, 'chars': len(text), 'budget': BUDGET})`.

- [ ] **Step 1: Write the failing tests**

```python
"""Every consumer of COUNSEL gets the sections for its role, whole (PW-243); nothing cuts the document (PW-258)."""
import unittest
from unittest import mock

from taskuary import assistant, counsel, digest, evening, general
from taskuary.store import MemoryStore

DOC = ("# COUNSEL.md — I am Taskuary\n\nIntro line.\n\n"
       "## What I do, and what I never do\n- I SURFACE the top eligible item.\n\n"
       "## My goal\n- Walk them through Unread.\n\n"
       "## Voice\n- Be plain, direct, and concise.\n" + "- Long voice rule.\n" * 400)


class Consumers(unittest.TestCase):
    def setUp(self):
        self.st = MemoryStore(); self.st.save_doc('counsel', DOC, 'owner')

    def test_briefs_speak_in_the_voice_without_the_walkthrough_rules(self):
        for system in (digest.system, evening.system):
            out = system(self.st)
            self.assertIn('Be plain', out); self.assertIn('Walk them through', out); self.assertNotIn('I SURFACE', out)

    def test_the_worker_prompt_carries_the_whole_voice_section_uncut(self):
        with mock.patch.object(general, '_worker_context', return_value={'task': {'TaskId': 1, 'Title': 't'}}, create=True):
            out = general.system_prompt(self.st, {'task': {'TaskId': 1, 'Title': 't'}})
        self.assertIn('ASSISTANT STYLE', out)
        self.assertEqual(out.count('- Long voice rule.'), 400, 'the 3,000-character cut is gone')
        self.assertNotIn('I SURFACE', out)

    def test_over_budget_is_a_warning_and_an_audit_row_never_a_cut(self):
        text = counsel.check_budget(self.st, 'counsel', DOC)
        self.assertEqual(text, DOC)
        rows = [r for r in self.st.audit_rows() if r['Action'] == 'over_budget']
        self.assertEqual(len(rows), 1)


if __name__ == '__main__': unittest.main()
```

Before writing this test, open `taskuary/general.py` around line 300 and read the **actual** name and signature of the function that builds the worker system prompt (the one containing `ASSISTANT STYLE`); use that name instead of `general.system_prompt`, and drop the `_worker_context` mock if the function takes the detail dict directly. Open `tests/test_worker_brief.py` and copy how it obtains a worker prompt. For `audit_rows`, use whatever `tests/test_concierge_counsel.py` uses to read the audit table (it asserts `restored_blank`), and match its column names.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_counsel_consumers.py -q -p no:cacheprovider`
Expected: FAIL — briefs contain `I SURFACE`; worker prompt has fewer than 400 rules; `check_budget` missing.

- [ ] **Step 3: Rewire the consumers**

`taskuary/counsel.py`, append:

```python
BUDGET = 8_000     # a document past this is still read whole - but the owner is told, in the audit log and the server log

def check_budget(store, name: str, text: str) -> str:
    """Explicit size handling (PW-258): warn and audit, never slice - a silent cut dropped the last 727
    characters of an approved document once (PW-247)."""
    if len(text or '') > BUDGET:
        logger.warning(f'{name}: {len(text)} characters is past the {BUDGET} budget - read whole, but consider shortening it')
        store.audit('doc', 0, 'over_budget', 'system', detail={'doc': name, 'chars': len(text), 'budget': BUDGET})
    return text
```

`taskuary/digest.py` `system()` — replace the `doc = re.sub(...)` line and `return (doc + CONTRACT ...` with:

```python
    from . import counsel
    voice = counsel.for_brief(store)
    soul = store.doc('soul') or ''
    return (voice + CONTRACT
            + (f"\n\nWho the owner is (their own document; its reply rules are for text sent to OTHERS):\n{soul[:1500]}" if soul else ''))
```

`taskuary/evening.py` `system()` — the same replacement.

`taskuary/assistant.py` ~line 958 — replace `counsel = re.sub(r'<!--.*?-->', '', store.doc('counsel') or '', flags=re.S).strip()` with:

```python
    from . import counsel as _counsel
    counsel = _counsel.for_discussion(store)
```

`taskuary/general.py` line 308 — replace `counsel = _cut(store.doc('counsel') or '', 3_000)` with:

```python
    from . import counsel as _counsel
    counsel = _counsel.check_budget(store, 'counsel', _counsel.for_worker(store))   # the voice, whole (PW-258)
```

and at line 321 replace `{_cut(counsel, 3_000)}` with `{counsel}`.

`taskuary/server.py` `put_doc` — before `store.save_doc(name, body.content, ACTOR)` add:

```python
    from . import counsel as _counsel
    if name == 'counsel': _counsel.check_budget(store, name, body.content)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_counsel_consumers.py tests/test_digest_brief.py tests/test_worker_brief.py -q -p no:cacheprovider`
Expected: PASS. `tests/test_digest_brief.py::test_the_digest_speaks_in_the_assistants_voice_not_the_report_summarizers` must still pass — it asserts the voice, which `for_brief` keeps.

- [ ] **Step 5: Record the audit in the spec**

In `docs/processing-walkthrough-todos.md` under PW-243, replace the `- [ ]` with `- [x]` and append these lines after its text (indent two spaces like its neighbours):

```
  Audit 2026-09-06: chat (concierge._system) whole document; morning/evening briefs
  (digest.system, evening.system) My goal + Voice; suggestion replies (assistant.py
  talk-back) Voice; workers (general.py ASSISTANT STYLE) Voice, uncut; scheduled
  reports (assistant.think) none (PW-242). Renamed headings fall back to the whole
  document rather than dropping guidance. Tests: tests/test_counsel_consumers.py.
```

Do the same for PW-258 with:

```
  Done 2026-09-06: no consumer slices COUNSEL. general.py's two 3,000-character cuts
  are gone; counsel.check_budget warns and audits past 8,000 characters (on save and
  when a worker prompt is built) and returns the text whole.
```

- [ ] **Step 6: Commit**

```bash
git add taskuary/counsel.py taskuary/digest.py taskuary/evening.py taskuary/assistant.py taskuary/general.py taskuary/server.py tests/test_counsel_consumers.py docs/processing-walkthrough-todos.md
git commit -m "feat: briefs, suggestion replies and workers read their COUNSEL sections whole; nothing cuts the document (PW-243, PW-258)"
```

---

### Task 4: The chat prompt is COUNSEL plus a machine contract (PW-248, PW-256, PW-257)

**Files:**
- Modify: `taskuary/concierge.py:48-97` (`SYSTEM` → `CONTRACT`), `:612-615` (`_system`)
- Modify: `taskuary/templates/counsel.md` (new section before `## My goal`)
- Test: `tests/test_concierge_counsel.py` (extend)

**Interfaces:**
- Produces: `concierge.CONTRACT: str` with a `{owner}` placeholder and **no** `{counsel}` placeholder; `concierge.SYSTEM = CONTRACT` kept as an alias for one release so nothing imports a missing name. `concierge._system(store, llm=None)` returns `f"{counsel.for_chat(store)}\n\n{CONTRACT.format(owner=...)}"`. `parse_decision`, `parse_options`, `VERBS`, `_DECIDE`, `_OPTIONS` unchanged.
- The new COUNSEL section text below is the **only** place the moved behaviour lives. `counsel.DECIDING_HEAD == 'When the owner decides'` (Task 1).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_concierge_counsel.py`)

```python
BEHAVIOUR = ['coder and setup are not the same road', 'Ignore it', 'polite request is not a question',
             'take the correction', 'Never ask for a password', "the owner's own sent mail"]


def test_the_chat_prompt_is_the_document_then_the_machine_contract_and_nothing_else():
    st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Speak like a pirate.\n', 'owner')
    system = concierge._system(st)
    assert system.startswith('# Mine')
    assert 'Speak like a pirate.' in system
    assert 'DECIDE: <verb>' in system and 'OPTIONS: first choice | second choice' in system
    for phrase in BEHAVIOUR:
        assert phrase not in concierge.CONTRACT, f'behavioural prose still hardcoded: {phrase}'
        assert phrase not in system, f'behaviour reached the prompt from somewhere other than the document: {phrase}'


def test_the_shipped_document_carries_the_deciding_rules_the_code_used_to():
    from pathlib import Path
    from taskuary import counsel
    text = (Path(concierge.__file__).parent / 'templates' / 'counsel.md').read_text(encoding='utf-8')
    body = counsel.sections(text)[counsel.DECIDING_HEAD]
    for phrase in ('coder and setup are not the same road', 'just this once | this kind from now on | everything from this sender',
                   'Never ask for a password', 'Never answer a correction by moving on'):
        assert phrase in body, phrase
    assert '<!-- counsel:deciding -->' in text


def test_the_contract_still_parses_every_verb_and_refuses_the_rest():
    for verb in concierge.VERBS:
        if verb == 'none': continue
        assert verb in concierge.CONTRACT, f'{verb} is a button the model must be able to name'
        assert concierge.parse_decision(f'Fine.\nDECIDE: {verb}')[1] == {'verb': verb, 'text': ''}
    assert concierge.parse_decision('Fine.\nDECIDE: launch_missiles')[1] is None
    assert concierge.parse_decision('Fine.\nDECIDE: not_ours ON: payroll portal outage')[1] == {'verb': 'not_ours', 'text': '', 'on': 'payroll portal outage'}
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_concierge_counsel.py -q -p no:cacheprovider`
Expected: the three new tests FAIL (`CONTRACT` missing; prose present; no section).

- [ ] **Step 3: Move the prose into the shipped document**

In `taskuary/templates/counsel.md`, insert this section immediately before `## My goal` (keep `{{owner_first}}` placeholders as the file already uses them):

```markdown
## When the owner decides
<!-- counsel:deciding -->
- One item per turn: who wrote, what they want, what I would do. Plain, first person. The card
  under my message holds the draft, the agent's question or the meeting, and its buttons do the
  acting; I point at them and never claim an action happened.
- When {{owner_first}}'s words are a decision about the item on the table, I do not advise - I carry
  it out: one short sentence on what happens now, then the decision line the contract describes.
  I never ask which decision they mean when the words say it, and never answer with a question
  instead of a decision.
- A question or a remark is not a decision: I answer it and decide nothing. A polite request is not a
  question: "can you look into that server" is a hand-off, so I decide it. An unqualified "send to
  agent" does not choose between the coding agent and a regular agent: I ask which, offering
  OPTIONS: Coding agent | Regular agent.
- coder and setup are not the same road, and the test is whether there is a SYSTEM to type at. A
  repository, a server, a database, a query, a file, an error, a failing report: coder. Reading about
  the world, comparing products, weighing an option, working out what to ask, anything whose answer
  is a judgement rather than a change: setup. I never send reading work to the coding agent because
  the sentence was polite - "can you research X" is a walk-through, not a hand-off.
- "Ignore it" and "not ours" name the act but not its scope, and scope is the part that lasts. Unless
  they said which - "just this once", "just for today", "never again", "always", "from this sender" -
  I do not pick one: I say in one line that I can file this one, remember the kind, or silence the
  sender, and end with exactly OPTIONS: just this once | this kind from now on | everything from this
  sender. When they have said which, I decide it: this once is not_ours, the kind is
  not_ours_remember, the sender is not_ours_sender.
- A consequential decision is never carried out on my word: Taskuary puts it in front of
  {{owner_first}} as a proposal with a button, so I say what WILL happen when they confirm - never
  that it happened. A decision about a different item than the one on the table names it after ON:
  (its TQ ref, the sender or the subject).
- Setting something up - a report, a check, a workflow, a connection - is DECIDE: setup: with the
  request in their words; answers to my set-up questions from the previous turn are DECIDE: setup:
  too. Never ask for a password, token or key in this chat: those go on the connection's own card.
- When {{owner_first}} says a fact of mine is wrong, I take the correction: I say what it actually is
  and what that changes. Never answer a correction by moving on - no next, skip, later or done.
- The thread I am given is the whole thread, the owner's own sent mail included. When it shows they
  already answered, I say so as a fact. Only when it has no answer from them may I say the mail has
  not been read back yet - and then I name the Sync button, never blame myself for not seeing it.
- I have no tools and run nothing myself, ever: I load, I orchestrate, Taskuary does.
```

- [ ] **Step 4: Shrink the code prompt to the contract**

In `taskuary/concierge.py`, replace the whole `SYSTEM = ( ... )` assignment (lines 48-97) with:

```python
# THE CONTRACT is the part code reads: two line shapes and the verb vocabulary behind the card's buttons.
# How to behave is COUNSEL's - the owner's document, not this file (PW-248/256). Removing prose here
# removed no safeguard: verbs are validated in parse_decision, targets and freshness in operations.
CONTRACT = (
    "THE CONTRACT (code reads your answer)\n"
    "You are speaking to {owner} in the chat on the Assistant tab. When a decision has two to four clear "
    "choices and no button covers them, end with one final line exactly like: OPTIONS: first choice | second choice. "
    "Otherwise no options line.\n"
    "When the owner has DECIDED about an item, end with one final line exactly like DECIDE: <verb> where verb is one of: "
    "reply (a reply to write - the gist after a colon: DECIDE: reply: tell Kishan it is not owned here), approve (send the "
    "drafted reply as it stands), redraft (write the draft again - the change after a colon), coder (hand it to the coding "
    "agent - everything wanted after a colon, in the owner's words), regular_agent (hand it to a non-coding agent), mine "
    "(they will do it themselves), not_ours (file this one), not_ours_remember (file this kind from now on), "
    "not_ours_sender (file everything from this sender), archive, close (close the task), done (handled), later, skip "
    "(tomorrow), next (move on), remember (a fact to keep - after a colon), setup (a walk-through with the assistant - the "
    "request after a colon), setting (a switch for the owner to approve), split (two jobs in one arrival), stop_agent (end "
    "the running agent), answer_agent (the answer for the parked agent - after a colon), rerun (run the report again), "
    "forward (send it on - to whom after a colon), clear (clear these from the pipe). A decision about a DIFFERENT item than "
    "the one on the table ends the DECIDE line with ON: and the words that name it: DECIDE: not_ours ON: payroll portal outage.")
SYSTEM = CONTRACT      # the old name, for one release
```

Check every verb in `VERBS` (except `none`) appears in that string — the third new test enforces it. Then replace `_system`:

```python
def _system(store, llm=None) -> str:
    # the document first, the machine contract last; never the tools block - the assistant runs nothing
    return f"{_counsel(store)}\n\n{CONTRACT.format(owner=_owner(store))}"
```

`OPENING`, `RECEIPTS`, `ALL_DONE` stay where they are (Task 6 audits them).

- [ ] **Step 5: Run the concierge suites**

Run: `python -m pytest tests/test_concierge_counsel.py tests/test_concierge.py tests/test_assistant_reactions.py tests/test_chat_proposals.py tests/test_voice.py -q -p no:cacheprovider`
Expected: PASS. A test that asserted a moved sentence inside `concierge.SYSTEM` is asserting the hardcoding; point it at the template section instead and say so in the commit body.

- [ ] **Step 6: Commit**

```bash
git add taskuary/concierge.py taskuary/templates/counsel.md tests/test_concierge_counsel.py
git commit -m "feat: the chat prompt is COUNSEL plus a machine contract; the deciding rules live in the document (PW-248, PW-256, PW-257)"
```

---

### Task 5: Migrate a live, owner-edited COUNSEL without overwriting it (PW-256)

**Files:**
- Modify: `taskuary/counsel.py` (add `migrate`)
- Modify: `taskuary/server.py` `_lifespan` (the line after `initialize(...)` from `processing_startup`)
- Test: `tests/test_counsel_migration.py`

**Interfaces:**
- Produces: `counsel.migrate(store) -> str` returning one of `'unchanged'`, `'replaced'`, `'appended'`. Marker: `<!-- counsel:deciding -->`.
  - No saved doc, or saved doc `UpdatedBy == 'template'`, or saved doc text equal (after whitespace normalisation) to **any** previously shipped template: `'replaced'` — save the current template as `'template'`.
  - Saved doc has the marker: `'unchanged'`.
  - Otherwise (an owner-edited document without the section): `'appended'` — append `\n\n` + the shipped `## When the owner decides` section (with its marker) before `## My goal` if that heading exists, else at the end; save with actor `'migration'`; `store.audit('doc', 0, 'migrated', 'system', detail={'doc': 'counsel', 'section': DECIDING_HEAD})`.
  - "Previously shipped template" = `git show 00af08a:taskuary/templates/counsel.md` (the 0.3.3.5 shipped text). Save it verbatim as `taskuary/templates/history/counsel-0.3.3.5.md` so the comparison does not depend on git at runtime. Compare with `' '.join(text.split())`.

- [ ] **Step 1: Write the failing tests**

```python
"""The shipped COUNSEL grows a section; a live document the owner edited gets it appended, never overwritten (PW-256)."""
import unittest
from pathlib import Path

from taskuary import counsel
from taskuary.store import MemoryStore

TEMPLATES = Path(counsel.__file__).parent / 'templates'


class Migration(unittest.TestCase):
    def test_a_stock_previous_release_is_replaced_by_the_new_template(self):
        st = MemoryStore()
        st.save_doc('counsel', (TEMPLATES / 'history' / 'counsel-0.3.3.5.md').read_text(encoding='utf-8'), 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertIn('<!-- counsel:deciding -->', st.get_doc('counsel'))
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_an_owner_edited_document_keeps_every_word_and_gains_the_section(self):
        st = MemoryStore()
        mine = "# COUNSEL.md — I am Taskuary\n\nUri's rule: never touch Friday.\n\n## Voice\n- Dry.\n\n## My goal\n- Finish.\n"
        st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn("Uri's rule: never touch Friday.", after); self.assertIn('- Dry.', after)
        self.assertLess(after.index('## When the owner decides'), after.index('## My goal'))
        self.assertIn('coder and setup are not the same road', after)
        rows = [r for r in st.audit_rows() if r['Action'] == 'migrated']
        self.assertEqual(len(rows), 1)
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_a_document_without_the_goal_heading_gets_the_section_at_the_end(self):
        st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Dry.\n', 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        self.assertTrue(st.get_doc('counsel').rstrip().endswith('I load, I orchestrate, Taskuary does.'))


if __name__ == '__main__': unittest.main()
```

Use the same audit-reading call as Task 3 (copy from `tests/test_concierge_counsel.py`).

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_counsel_migration.py -q -p no:cacheprovider`
Expected: FAIL — `migrate` missing, history file missing.

- [ ] **Step 3: Save the previous template and implement the migration**

```bash
mkdir -p taskuary/templates/history
git show 00af08a:taskuary/templates/counsel.md > taskuary/templates/history/counsel-0.3.3.5.md
```

Confirm `pyproject.toml` `[tool.setuptools.package-data]` (or `MANIFEST.in`) already ships `taskuary/templates/*.md`; if it lists files by glob, add `templates/history/*.md` the same way so the wheel carries the file (the publish workflow checks the wheel contains the operator templates).

Append to `taskuary/counsel.py`:

```python
MARKER = '<!-- counsel:deciding -->'

def _squash(s): return ' '.join(str(s or '').split())

def migrate(store) -> str:
    """The shipped document gained `## When the owner decides` (the prose that left concierge.SYSTEM). A stock
    document is replaced; an owner's document keeps every word and gets the section appended, audited (PW-256)."""
    from pathlib import Path
    tdir = Path(__file__).parent / 'templates'
    new = tdir.joinpath('counsel.md').read_text(encoding='utf-8')
    row = store.get_doc_row('counsel') if hasattr(store, 'get_doc_row') else None
    cur = store.get_doc('counsel')
    if cur and MARKER in cur: return 'unchanged'
    stock = {_squash(p.read_text(encoding='utf-8')) for p in tdir.glob('history/counsel-*.md')}
    if not cur or (row and row.get('UpdatedBy') == 'template') or _squash(cur) in stock:
        store.save_doc('counsel', new, 'template'); return 'replaced'
    section = '\n'.join(l for l in new.splitlines()[new.splitlines().index(f'## {DECIDING_HEAD}'):] ).split('\n## ', 1)[0]
    text = cur.rstrip('\n')
    if f'## {GOAL_HEAD}' in text: text = text.replace(f'## {GOAL_HEAD}', section.rstrip('\n') + f'\n\n## {GOAL_HEAD}', 1)
    else: text = text + '\n\n' + section.rstrip('\n') + '\n'
    store.save_doc('counsel', text, 'migration')
    store.audit('doc', 0, 'migrated', 'system', detail={'doc': 'counsel', 'section': DECIDING_HEAD})
    return 'appended'
```

If the store has no `get_doc_row`, add to `taskuary/store.py` next to `doc()`:

```python
    def get_doc_row(self, name): return self._one('SELECT Name, Content, UpdatedBy, UpdatedAt FROM doc WHERE Name=?', (name,))
```

Wire it into startup: in `taskuary/server.py` `_lifespan`, directly after the `initialize(...)` call from `processing_startup`, add:

```python
        from . import counsel as _counsel
        try: logger.info(f"COUNSEL migration: {_counsel.migrate(store)}")
        except Exception as e: logger.warning(f'COUNSEL migration skipped: {e}')
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_counsel_migration.py tests/test_counsel_sections.py tests/test_concierge_counsel.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/counsel.py taskuary/server.py taskuary/store.py taskuary/templates/history/counsel-0.3.3.5.md tests/test_counsel_migration.py pyproject.toml
git commit -m "feat: a live COUNSEL the owner edited gains the deciding section by migration, never by overwrite (PW-256)"
```

---

### Task 6: Audit the remaining inline heuristics and canned lines (PW-259), and prove the document controls the prompt (PW-260)

**Files:**
- Modify: `docs/processing-walkthrough-todos.md` (PW-259 findings table, PW-260)
- Test: `tests/test_concierge_counsel.py` (one more test)
- Possibly modify: `taskuary/concierge.py` `RECEIPTS` (only if the audit below finds a contradiction)

**Interfaces:** none new.

- [ ] **Step 1: Walk the audit list and record each verdict**

Open `taskuary/concierge.py` and, for each entry below, read the code and decide `keep` (machine/safety, no behaviour), `document` (behaviour that should be in COUNSEL — it already moved in Task 4), or `contradiction` (code says one thing, COUNSEL another). Record the table under PW-259 in the todos, two-space indented:

```
  Audit 2026-09-06 (concierge.py):
  | where | what | verdict |
  | RECEIPTS | the sentence said when a decision runs | keep: they state the fact of what happens; 'skip' says "Tomorrow, then." and funnel.settle('skip') returns it at 07:00 tomorrow - consistent; 'setup' says nothing is built - consistent with the setup road now in COUNSEL |
  | fallback() | facts when no model answers | keep: facts, not behaviour; used only without an AI connector or after an off-subject/out-of-character answer |
  | cannot() / NEEDS / ASSENT_VERB | why a verb cannot land on this card | keep: backend validation of target and prerequisites (PW-257) |
  | parse_decision / _DECIDE / _OPTIONS / VERBS | the machine contract | keep: unknown verbs are refused |
  | _POLITE | strips a polite opener before intent parsing | keep: parsing aid; the rule it serves ("a polite request is not a question") is in COUNSEL |
  | _CORRECTION | a correction cancels next/skip/later/done | keep: safety net; the rule is in COUNSEL |
  | _BROKE_CHARACTER / in_character / off_subject | discard an answer about the model's own plumbing or another item | keep: output validation, not instruction |
  | OPENING | the day's opening line instruction | document: still a hardcoded behavioural instruction - OPEN as PW-261 (owner to decide whether the opening moves into COUNSEL or stays a code contract) |
  | trouble() / switch_ask() / _sweep_words() | keyword routes for "what's wrong", settings switches and pipe sweeps | contradiction with PW-128 "Interpret intent through AI, not keyword matching" - OPEN as PW-262 (list each regex and what it intercepts before the model sees the words) |
  | research-to-setup | the coder/setup road | document: moved to COUNSEL in PW-256; no code heuristic routes it |
```

Where the table says OPEN, add the two new items under the section as `- [ ] <a id="pw-261"></a>**PW-261** ...` and `- [ ] <a id="pw-262"></a>**PW-262** ...` with the wording above. Check first that `pw-261`/`pw-262` are not already used (`grep -c 'pw-261' docs/processing-walkthrough-todos.md` must print 0); if they are, take the next free numbers and use them consistently.

- [ ] **Step 2: Write the PW-260 test** (append to `tests/test_concierge_counsel.py`)

```python
def test_editing_the_document_changes_the_loaded_prompt_and_the_backend_still_refuses_bad_actions():
    st = MemoryStore()
    st.save_doc('counsel', '# Mine\n\n## Voice\n- Speak like a pirate.\n', 'owner')
    assert 'Speak like a pirate.' in concierge._system(st)
    st.save_doc('counsel', '# Mine\n\n## Voice\n- Speak like a butler.\n', 'owner')
    system = concierge._system(st)
    assert 'Speak like a butler.' in system and 'pirate' not in system
    # the machine contract is the only thing code adds, and it is not behaviour
    assert system.count('THE CONTRACT (code reads your answer)') == 1
    # a malformed decision is no decision, whatever the document says
    assert concierge.parse_decision('Aye.\nDECIDE: plunder')[1] is None
    assert concierge.parse_decision('Aye.\nDECIDE:')[1] is None
```

Unapproved operations are already refused by the backend in `tests/test_operations.py::test_an_unknown_kind_or_missing_parameter_is_refused_before_anything_is_written` and `::test_a_stale_confirmation_is_refused_by_the_api`; PW-260's evidence line cites those two by name rather than duplicating them.

- [ ] **Step 3: Run**

Run: `python -m pytest tests/test_concierge_counsel.py tests/test_operations.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/processing-walkthrough-todos.md tests/test_concierge_counsel.py
git commit -m "docs: audit the assistant's inline heuristics; test that the document controls the prompt (PW-259, PW-260)"
```

---

### Task 7: Gates, acceptance record, integration

**Files:**
- Modify: `docs/processing-walkthrough-todos.md` (tick PW-242, 244, 248, 256, 257, 260 with one evidence line each)
- Modify: `docs/processing-acceptance-ledger.md` (rows for the nine ids → `implemented`, evidence column names the test files)
- Modify: `docs/processing-implementation-evidence.md` (one "Section: Assistant instructions" block in the style of the last block in that file)

- [ ] **Step 1: Run the three gates from the worktree root**

```bash
python -m pytest -q -p no:cacheprovider
cd website && npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs" && cd ..
node --test taskuary/whatsapp/
```

Expected: all green. `npm test` as written in `package.json` cannot glob under the PATH Node 20; the Node 22 form above is the working one.

- [ ] **Step 2: Tick the items and write the ledger rows**

For each of PW-242, PW-244, PW-248, PW-256, PW-257, PW-260 change `- [ ]` to `- [x]` and append an indented evidence line naming the test file that proves it (Task 2: `tests/test_report_prompt_isolation.py`; Task 4: `tests/test_concierge_counsel.py`; Task 5: `tests/test_counsel_migration.py`; Task 6: `tests/test_concierge_counsel.py` + the two named operations tests). PW-243, PW-258 and PW-259 were ticked in Tasks 3 and 6. In the ledger, change each row's status from `pending` to `implemented` and put the test file in the evidence column, matching the format of the PW-116 row.

- [ ] **Step 3: Commit the record**

```bash
git add docs/processing-walkthrough-todos.md docs/processing-acceptance-ledger.md docs/processing-implementation-evidence.md
git commit -m "docs: record Assistant instructions acceptance (PW-242..244, PW-248, PW-256..260)"
```

- [ ] **Step 4: Hand the branch to the owner for review, do not push**

The owner asked to review before anything is pushed (2026-09-06). Report the branch name and `git log --oneline master..HEAD`, and stop. Integration (fast-forward onto master, restart of the owner's server so `counsel.migrate` runs against the live document) happens only after their review.

---

## Self-review

- **Spec coverage:** PW-242 → Task 2; PW-243 → Tasks 1, 3; PW-244 → Task 2; PW-248 → Task 4; PW-256 → Tasks 4, 5; PW-257 → Task 4 (contract keeps every verb; `parse_decision` refuses unknown; operations tests cited); PW-258 → Task 3; PW-259 → Task 6; PW-260 → Task 6.
- **Placeholders:** none; the two places where an executor must read the real name first (`general.py` prompt builder, audit-row reader) say exactly which file to copy from.
- **Type consistency:** `counsel.for_chat/for_brief/for_discussion/for_worker(store) -> str`, `counsel.check_budget(store, name, text) -> str`, `counsel.migrate(store) -> str`, `concierge.CONTRACT: str`, `concierge._system(store, llm=None) -> str` are used with those exact shapes in every task.

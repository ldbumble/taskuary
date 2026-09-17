# Skills As Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `SKILL.md` — from disk, from an installed plugin, or from a link — becomes an ordinary Taskuary profile, so somebody else's expertise runs on any CLI; and the agent assigned that profile receives all of it.

**Architecture:** One new module (`skillimport.py`) finds and converts; three thin endpoints; one new wizard component. An imported profile is written through the existing `agent` row + `doc` row road, so `agents.py`, `playbooks.py` and `triage.py` do not change at all. Task 1 first fixes `DOC_CHARS`, without which an imported profile arrives as its first quarter.

**Tech Stack:** Python 3.10 / FastAPI / SQLite / pytest (unittest style); React + MUI, Node 22 `node --test` over JSX source text.

**Specs:**
- `docs/superpowers/specs/2026-09-17-an-agent-gets-its-whole-profile-design.md` (Task 1)
- `docs/superpowers/specs/2026-09-17-importing-skills-as-profiles-design.md` (Tasks 2-5)

## Global Constraints

- **Match the surrounding style:** dense code, comments explaining WHY not HOW, lines under ~160 chars. No autoformatter.
- **Skills become PROFILES. Never playbooks.** A playbook is the owner's own workflow against the owner's own systems. There is a test asserting no import ever creates one.
- **`.mcp.json` is never opened.** Connectors are Taskuary's, behind `scopes.py` and the proposal road. There is a test asserting the path is never read.
- **Nothing is followed.** The importer reads the markdown file it was pointed at. No links inside it, no install step, no fetching what a skill references.
- **Nothing is active until ticked.** Imported profiles are written with `triage_enabled: False` unless the owner ticks the box; `agents.roster()` then does not offer them.
- **Do not change `agents.py`, `playbooks.py` or `triage.py`.** An imported profile must be an ordinary profile. If a task seems to need a change there, stop and report — it means the conversion is wrong, not that the road is.
- **Environment:** pytest from the worktree root. Web tests need Node 22: `cd website && npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"`. Lint gate: `cd website && npx eslint -c eslint.undef.mjs -f json src/*.jsx src/*.js` (the npm script does not work — eslint is not a dependency). Write files with **LF** endings; a test asserts no build input carries CRLF.

---

### Task 1: The agent gets the whole profile

**Files:**
- Modify: `taskuary/terminal.py:35` (`DOC_CHARS`) and `:1064` (`rules_text`)
- Test: `tests/test_terminal_seed.py` (find the file that covers `rules_text`/`seed_text` first: `grep -rln "rules_text\|SEED_CEILING" tests/`)

**Interfaces:**
- Consumes: `terminal._cut(text, n, what)` at `terminal.py:1116`.
- Produces: `terminal.DOC_CHARS == 6000`; `rules_text` marks its own truncation.

- [ ] **Step 1: Write the failing tests**

```python
    def test_a_coding_agent_gets_the_whole_of_its_rules(self):
        """coder.md flattens to ~4,884 chars and was delivered as 1,800 - every coding session ran on
        37% of its own rules, cut mid-sentence, with nothing saying so. Measured, not hardcoded, so
        the test still means something after the document is edited."""
        s = MemoryStore()
        doc = s.get_doc('coder') or ''
        self.assertGreater(len(doc), 2000, 'the shipped coder.md should be substantial')
        got = terminal.rules_text(s, profile='coder')
        self.assertNotIn('truncated here', got)
        # every non-empty line of the document survives into the flattened rules
        for line in [l.strip(' #*-').strip() for l in doc.splitlines() if l.strip()][-3:]:
            self.assertIn(' '.join(line.split())[:60], got, 'the END of the document was dropped')

    def test_a_profile_too_long_to_fit_says_so(self):
        s = MemoryStore()
        s.save_doc('coder', 'x ' * 8000, 'test')
        got = terminal.rules_text(s, profile='coder')
        self.assertIn('truncated here', got)      # _cut's own words - silence is the expensive kind

    def test_a_short_profile_is_returned_untouched(self):
        s = MemoryStore()
        s.save_doc('coder', '# Rules\nBe careful.', 'test')
        self.assertNotIn('truncated', terminal.rules_text(s, profile='coder'))

    def test_the_ask_is_what_gives_when_the_whole_seed_is_over(self):
        """The existing priority, asserted rather than assumed: raising DOC_CHARS must not change
        WHICH component yields when the command line is full."""
        self.assertGreater(terminal.ASK_CHARS, terminal.DOC_CHARS)
        self.assertLess(terminal.DOC_CHARS, terminal.SEED_CEILING)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_terminal_seed.py -x -q
```

Expected: FAIL — the end of `coder.md` is missing from the flattened rules.

- [ ] **Step 3: Raise the number and mark what still does not fit**

`taskuary/terminal.py:35`:

```python
# How much of a worker's rules document reaches the session that runs as it. 1800 was sized for a
# delivery limit that no longer applies - the prompt goes over STDIN now (agents.py's header), and
# what bounds it is SEED_CEILING, which already says the ASK is what gives, never the rules. Left at
# 1800 it delivered 1,800 of coder.md's 4,884 characters to every coding session, cut mid-sentence,
# under an instruction saying these are your rules. This is the same fix ASK_CHARS got (3000 ->
# 12000) for the same reason, on the same day somebody noticed the message body had it too.
DOC_CHARS = 6000
```

`taskuary/terminal.py:1064`, the last line of `rules_text`:

```python
    return _cut(' '.join(' '.join(keep).split()), chars, 'rules')
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_terminal_seed.py -q
python -m pytest tests/ -q -k "seed or terminal or rules or prompt"
```

Expected: PASS. If a test asserted a seed's exact length, it was measuring the bug — update it to the new length and say so in your report.

- [ ] **Step 5: Commit**

```bash
git add taskuary/terminal.py tests/
git commit -m "fix: an agent gets the whole profile it was assigned

coder.md flattens to 4,884 characters and 1,800 reached the session, cut
mid-sentence with nothing saying so. Same bug ASK_CHARS already had, same
reason - a delivery limit that stopped applying when prompts moved to
stdin. SEED_CEILING already backstops the total and already protects the
rules over the ask.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Finding and parsing a skill

**Files:**
- Create: `taskuary/skillimport.py`
- Test: `tests/test_skillimport.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `skillimport.SKILL_GLOBS` — the two install locations
  - `skillimport.parse(text: str) -> dict` → `{'name', 'description', 'body'}` from a `SKILL.md`
  - `skillimport.found() -> list[dict]` → `[{'plugin', 'plugin_desc', 'name', 'path', 'bytes'}]`
  - `skillimport.read_path(p: str) -> list[dict]` → one entry for a file, N for a folder with `skills/`

- [ ] **Step 1: Write the failing test**

```python
"""Importing somebody else's expertise as a profile.

A skill says HOW a job is done. A playbook is the owner's own workflow against the owner's own
systems, drafted from work that happened - so nothing here ever writes one.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from taskuary import skillimport

SKILL = '''---
name: nda-triage
description: Use when a counterparty sends an NDA and somebody has to decide whether it can be signed as-is.
---

# NDA triage

Read the indemnity clause first. Anything uncapped goes to counsel.
'''


class ParsingTests(unittest.TestCase):
    def test_the_frontmatter_becomes_the_name_and_the_purpose(self):
        got = skillimport.parse(SKILL)
        self.assertEqual(got['name'], 'nda-triage')
        self.assertIn('counterparty sends an NDA', got['description'])
        self.assertIn('indemnity clause', got['body'])
        self.assertNotIn('---', got['body'])          # the frontmatter is not part of the rules

    def test_a_file_with_no_frontmatter_is_still_importable(self):
        got = skillimport.parse('# Just prose\n\nDo the thing carefully.')
        self.assertEqual(got['description'], '')
        self.assertIn('Do the thing', got['body'])

    def test_a_folder_of_skills_reads_every_one(self):
        with TemporaryDirectory() as td:
            for n in ('a', 'b'):
                d = Path(td) / 'skills' / n
                d.mkdir(parents=True)
                (d / 'SKILL.md').write_text(SKILL.replace('nda-triage', n), encoding='utf-8')
            (Path(td) / '.claude-plugin').mkdir()
            (Path(td) / '.claude-plugin' / 'plugin.json').write_text(
                '{"name": "legal", "description": "contract work"}', encoding='utf-8')
            got = skillimport.read_path(td)
        self.assertEqual(sorted(g['name'] for g in got), ['a', 'b'])
        self.assertEqual(got[0]['plugin'], 'legal')

    def test_a_single_file_reads_as_one(self):
        with TemporaryDirectory() as td:
            p = Path(td) / 'SKILL.md'
            p.write_text(SKILL, encoding='utf-8')
            got = skillimport.read_path(str(p))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['name'], 'nda-triage')

    def test_the_connector_manifest_is_never_opened(self):
        """Taskuary's connectors are tested cards behind scopes.py. Importing MCP servers would hand
        a worker a second way out of the building."""
        src = Path(skillimport.__file__).read_text(encoding='utf-8')
        self.assertNotIn('.mcp.json', src)
        self.assertNotIn('mcpServers', src)

    def test_commands_are_not_read(self):
        with TemporaryDirectory() as td:
            (Path(td) / 'commands').mkdir()
            (Path(td) / 'commands' / 'x.md').write_text('# a command', encoding='utf-8')
            (Path(td) / 'skills' / 'a').mkdir(parents=True)
            (Path(td) / 'skills' / 'a' / 'SKILL.md').write_text(SKILL, encoding='utf-8')
            got = skillimport.read_path(td)
        self.assertEqual([g['name'] for g in got], ['a'])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_skillimport.py -x -q
```

Expected: FAIL — `No module named 'taskuary.skillimport'`.

- [ ] **Step 3: Write the finder**

```python
"""Importing somebody else's expertise, as a profile.

A skill is HOW a job is done - eleven knowledge-work plugins of it, written by people who do those
jobs, stuck in one vendor's directory where only Claude Code can read them. Converted once it becomes
an ordinary Taskuary profile, and an ordinary profile drives a codex session.

It never becomes a PLAYBOOK. A playbook's fields are uses/alone/ask first/done when - every one about
acting on a system - and a SKILL.md states none of them, so converting to one meant inventing `uses:`,
which decides whether CODER.md's repository rules apply. A profile needs a purpose and a body, and
both are already in the file. Nothing is guessed.

This module finds and parses. It writes nothing and fetches nothing it was not pointed at.
"""
import json, re
from pathlib import Path

# Where Claude Code keeps them. Read-only, and the only thing we know about another tool's disk.
SKILL_GLOBS = ('.claude/skills/*/SKILL.md',
               '.claude/plugins/cache/*/*/*/skills/*/SKILL.md')
_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.S)
_KEY = re.compile(r'^(name|description)\s*:\s*(.*)$', re.M)


def parse(text: str) -> dict:
    """{name, description, body} from a SKILL.md. The frontmatter is metadata about the skill, not
    part of the rules a worker follows, so it does not travel into the body."""
    m = _FM.match(str(text or ''))
    head, body = (m.group(1), m.group(2)) if m else ('', str(text or ''))
    found = {k: v.strip().strip('"\'') for k, v in _KEY.findall(head)}
    return {'name': found.get('name', ''), 'description': found.get('description', ''),
            'body': body.strip()}


def _plugin_of(root: Path) -> tuple:
    """(name, description) from .claude-plugin/plugin.json - what a folder of skills calls itself."""
    p = root / '.claude-plugin' / 'plugin.json'
    if not p.is_file(): return '', ''
    try: j = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError): return '', ''
    return str(j.get('name') or ''), str(j.get('description') or '')


def _entry(path: Path, plugin: str = '', plugin_desc: str = '') -> dict:
    text = path.read_text(encoding='utf-8', errors='replace')
    got = parse(text)
    return {**got, 'name': got['name'] or path.parent.name, 'path': str(path),
            'plugin': plugin, 'plugin_desc': plugin_desc, 'bytes': len(text)}


def read_path(p: str) -> list:
    """One entry for a SKILL.md, or one per skill for a plugin folder. `commands/` is not read: a
    command is a thing invoked by name, which an attached playbook already is."""
    root = Path(p)
    if root.is_file(): return [_entry(root)]
    if not root.is_dir(): return []
    name, desc = _plugin_of(root)
    return sorted((_entry(f, name, desc) for f in root.glob('skills/*/SKILL.md')),
                  key=lambda e: e['name'])


def found(home: Path = None) -> list:
    """Every skill already installed on this machine, for the picker. Nothing is read from a CLI's
    config - only files, only these two shapes."""
    home = home or Path.home()
    out = []
    for g in SKILL_GLOBS:
        for f in sorted(home.glob(g)):
            # .../<marketplace>/<plugin>/<version>/skills/<name>/SKILL.md - the plugin is 4 up
            parts = f.parts
            plugin = parts[-5] if 'plugins' in parts and len(parts) >= 5 else ''
            out.append(_entry(f, plugin))
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_skillimport.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/skillimport.py tests/test_skillimport.py
git commit -m "feat: find and parse a skill, without reading anything it points at

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Converting a skill into a profile

**Files:**
- Modify: `taskuary/skillimport.py`
- Test: `tests/test_skillimport.py`

**Interfaces:**
- Consumes: `parse` (Task 2); `compose._json(text)` at `compose.py:256`; `llm.build_llm(store)`.
- Produces:
  - `skillimport.CONVERT_SYSTEM` — the prompt
  - `skillimport.convert(entry: dict, llm=None) -> dict` → `{'name', 'purpose', 'body', 'kind'}`. With no llm, falls back to the frontmatter unchanged rather than failing.

- [ ] **Step 1: Write the failing test**

```python
class ConvertingTests(unittest.TestCase):
    def test_the_description_becomes_the_purpose(self):
        got = skillimport.convert(skillimport.parse(SKILL), llm=None)
        self.assertEqual(got['name'], 'nda-triage')
        self.assertIn('NDA', got['purpose'])
        self.assertIn('indemnity clause', got['body'])

    def test_a_model_may_sharpen_it_and_the_body_still_arrives_whole(self):
        """The model rewrites a description written for a harness into a purpose written for a
        roster. It must not summarise the BODY - that is the expertise being imported."""
        said = '{"name": "nda-triage", "purpose": "decides whether an NDA can be signed as-is", "kind": "analysis"}'
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: said)
        self.assertEqual(got['purpose'], 'decides whether an NDA can be signed as-is')
        self.assertIn('indemnity clause', got['body'])
        self.assertEqual(got['kind'], 'analysis')

    def test_a_model_that_answers_nonsense_falls_back_to_the_file(self):
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: 'sorry, what?')
        self.assertIn('counterparty sends an NDA', got['purpose'])

    def test_the_kind_is_never_coding(self):
        """A coding profile is chosen by routed_role, not by triage, and CODER.md's repository rules
        apply to it. An imported skill must never land there by accident."""
        said = '{"name": "x", "purpose": "p", "kind": "coding"}'
        got = skillimport.convert(skillimport.parse(SKILL), llm=lambda *a, **k: said)
        self.assertNotEqual(got['kind'], 'coding')
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_skillimport.py::ConvertingTests -x -q
```

Expected: FAIL — `skillimport` has no attribute `convert`.

- [ ] **Step 3: Write the conversion**

Append to `taskuary/skillimport.py`:

```python
# A `description` is written for a harness deciding whether to load a skill; a `purpose` is written
# for a roster of workers triage picks between. Same sentence, different reader - so a model rewrites
# it. It does NOT touch the body: that is the expertise being imported, and summarising it would
# throw away the thing the import is for.
CONVERT_SYSTEM = (
    'You are turning one skill document into a WORKER PROFILE for a small company\'s assistant. '
    'The profile is chosen by a router that sees one line per worker, so the purpose must say what '
    'kind of work this worker is for, in one sentence, in the company\'s own plain words.\n\n'
    'Answer ONLY with JSON: {"name": "<kebab-case, short>", "purpose": "<one sentence>", '
    '"kind": "<research|analysis|coordination|marketing|general>"}.\n\n'
    'Never answer "coding": a coding worker is chosen a different way and works a repository. '
    'Never invent a system, a credential or a permission - the profile is knowledge, not access.')

KINDS = ('research', 'analysis', 'coordination', 'marketing', 'general')


def convert(entry: dict, llm=None) -> dict:
    """{name, purpose, body, kind} for one skill. The body is passed through UNTOUCHED.

    With no model - or one that answers nonsense - the frontmatter stands on its own: a description
    is already a usable purpose, just written for a different reader. An import that works without a
    brain is one the owner can do on a fresh install."""
    from . import compose
    out = {'name': entry.get('name') or '', 'purpose': entry.get('description') or '',
           'body': entry.get('body') or '', 'kind': 'general'}
    if not llm: return out
    try:
        said = compose._json(llm(CONVERT_SYSTEM, json.dumps(
            {'name': entry.get('name'), 'description': entry.get('description'),
             'body': (entry.get('body') or '')[:4000]}), max_tokens=300)) or {}
    except Exception:
        return out
    if str(said.get('purpose') or '').strip(): out['purpose'] = said['purpose'].strip()
    if str(said.get('name') or '').strip(): out['name'] = said['name'].strip()
    kind = str(said.get('kind') or '').strip().lower()
    if kind in KINDS: out['kind'] = kind
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_skillimport.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/skillimport.py tests/test_skillimport.py
git commit -m "feat: a description is rewritten as a purpose, and the body is left alone

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Writing it as a profile, and the endpoints

**Files:**
- Modify: `taskuary/skillimport.py` (the write), `taskuary/server.py` (three endpoints)
- Test: `tests/test_skillimport.py`

**Interfaces:**
- Consumes: `convert` (Task 3); `store.upsert_agent(name, kind, runner, config)` at `store.py:3138`; `store.save_doc`; `agents.ensure_profile_document(store, name)`.
- Produces:
  - `skillimport.save(store, got: dict, enabled: bool) -> str` → the profile name
  - `GET /api/skills/found`, `POST /api/skills/read` (a path → entries), `POST /api/skills/import` (confirmed entries → profiles)

- [ ] **Step 1: Write the failing test**

```python
class SavingTests(unittest.TestCase):
    def _got(self, **kw):
        return {'name': 'nda-triage', 'purpose': 'decides whether an NDA can be signed as-is',
                'body': '# NDA triage\n\nRead the indemnity clause first.', 'kind': 'analysis', **kw}

    def test_it_writes_an_ordinary_profile(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        row = s.get_agent('nda-triage')
        self.assertTrue(row)
        self.assertEqual(row['Kind'], 'analysis')
        self.assertIn('indemnity clause', s.get_doc(agents.profile_document(s, 'nda-triage')) or '')

    def test_ticked_reaches_the_roster_as_ONE_line(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        roster = agents.roster(s)
        self.assertIn('nda-triage', roster)
        self.assertEqual(len([l for l in roster.splitlines() if 'nda-triage' in l]), 1)
        self.assertIn('signed as-is', roster)

    def test_unticked_is_saved_and_never_offered_to_triage(self):
        from taskuary import agents
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=False)
        self.assertTrue(s.get_agent('nda-triage'))          # imported
        self.assertNotIn('nda-triage', agents.roster(s))    # not offered

    def test_importing_twice_does_not_make_two(self):
        s = MemoryStore()
        skillimport.save(s, self._got(), enabled=True)
        skillimport.save(s, self._got(purpose='changed'), enabled=True)
        self.assertEqual(len([a for a in s.list_agents() if a['Name'] == 'nda-triage']), 1)

    def test_no_import_ever_creates_a_playbook(self):
        """The load-bearing rule: a playbook is the owner's own workflow against the owner's own
        systems, drafted from work that happened."""
        from taskuary import playbooks
        before = len(playbooks.list_all())
        skillimport.save(MemoryStore(), self._got(), enabled=True)
        self.assertEqual(len(playbooks.list_all()), before)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_skillimport.py::SavingTests -x -q
```

Expected: FAIL — `skillimport` has no attribute `save`.

- [ ] **Step 3: Write the save and the endpoints**

Append to `taskuary/skillimport.py`:

```python
def save(store, got: dict, enabled: bool = False) -> str:
    """Write one converted skill as an ORDINARY profile - an agent row and the doc row of the same
    name, the same road Docs → Add profile takes. Nothing here is special-cased downstream, which is
    the measure of whether this was done right.

    `triage_enabled` defaults to OFF: an imported worker reaches the router when the owner says so,
    not because a file was read."""
    from . import agents as hub_agents
    name = re.sub(r'[^a-z0-9-]+', '-', str(got.get('name') or '').strip().lower()).strip('-')
    if not name: raise ValueError('a profile needs a name')
    kind = got.get('kind') if got.get('kind') in KINDS else 'general'
    row = store.get_agent(name)
    try: prof = json.loads((row or {}).get('Config') or '{}')
    except ValueError: prof = {}
    prof.update({'kind': kind, 'purpose': str(got.get('purpose') or '').strip(),
                 'triage_enabled': bool(enabled), 'imported': True})
    store.upsert_agent(name, kind, (row or {}).get('Runner') or 'cli', json.dumps(prof))
    doc = hub_agents.profile_document(store, name, prof)
    store.save_doc(doc, str(got.get('body') or '').strip() + '\n', 'import')
    return name
```

In `taskuary/server.py`, beside the other agent endpoints (around line 4787):

```python
class SkillPathBody(BaseModel): path: str
class SkillImportBody(BaseModel): skills: list

@app.get('/api/skills/found')
def skills_found():
    """Skills already installed on this machine. Read-only, and only files - nothing is learned from
    another tool's configuration."""
    from . import skillimport
    return {'data': skillimport.found()}

@app.post('/api/skills/read')
def skills_read(body: SkillPathBody):
    """A path (a SKILL.md, or a plugin folder) turned into proposals. WRITES NOTHING: the owner reads
    the purpose and the body before any of it becomes a worker's instructions."""
    from . import skillimport, llm as llm_mod
    try: entries = skillimport.read_path(body.path)
    except OSError as e: raise HTTPException(422, f'could not read that: {e}')
    if not entries: raise HTTPException(422, 'no SKILL.md there')
    try: brain = llm_mod.build_llm(store)
    except Exception: brain = None
    return {'data': [dict(skillimport.convert(e, brain), path=e['path'], bytes=e['bytes'],
                          plugin=e.get('plugin') or '') for e in entries]}

@app.post('/api/skills/import')
def skills_import(body: SkillImportBody):
    """Write the ones the owner confirmed. Each becomes an ordinary profile."""
    from . import skillimport
    made = []
    for s in (body.skills or []):
        try: made.append(skillimport.save(store, s, bool(s.get('enabled'))))
        except (ValueError, OSError) as e: raise HTTPException(422, f'{s.get("name")!r}: {e}')
    store.audit('agent', 0, 'skills_imported', ACTOR, detail={'names': made})
    return {'imported': made}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_skillimport.py -q
python -m pytest tests/ -q -k "agent or roster or profile"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/skillimport.py taskuary/server.py tests/test_skillimport.py
git commit -m "feat: an imported skill is an ordinary profile, off the roster until ticked

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The wizard, and lists that survive success

**Files:**
- Create: `website/src/SkillImport.jsx`
- Modify: `website/src/DocsView.jsx` (the Import entry; scrolling lists showing roster state)
- Test: `website/test/skillImport.test.mjs`

**Interfaces:**
- Consumes: `GET /api/skills/found`, `POST /api/skills/read`, `POST /api/skills/import` (Task 4).
- Produces: nothing later depends on.

- [ ] **Step 1: Write the failing test**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("nothing is imported without the owner reading it", () => {
  const w = read("SkillImport.jsx");
  // /read proposes, /import writes - a remote skill is a draft until a human says otherwise
  assert.match(w, /\/api\/skills\/read/);
  assert.match(w, /\/api\/skills\/import/);
  // the body is shown, not just the one-line purpose
  assert.match(w, /body/);
});

test("nothing reaches the router unless it is ticked", () => {
  const w = read("SkillImport.jsx");
  assert.match(w, /enabled/);
  // the default is off: an imported worker routes work when the owner says so
  assert.match(w, /enabled: false|enabled\s*\?\?\s*false|defaultChecked=\{false\}/);
});

test("the lists scroll and say what is actually live", () => {
  const docs = read("DocsView.jsx");
  assert.match(docs, /Import skills/);
  assert.match(docs, /overflowY/);
  // a profile that is NOT on the roster has to say so where the list is
  assert.match(docs, /triage_enabled|on the roster|not routed/i);
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd website && npm exec --yes --package=node@22 -- node --test test/skillImport.test.mjs
```

Expected: FAIL — no `SkillImport.jsx`.

- [ ] **Step 3: Build the wizard and fix the lists**

`website/src/SkillImport.jsx` — a dialog with three stops. Follow `SetupWizard.jsx`'s shape for a
MUI dialog with steps, and `ConnectorsView.jsx`'s for a list of rows with per-row state.

1. **Where from** — a text field for a path, and a list from `GET /api/skills/found` grouped by
   `plugin`, each row showing its name and size.
2. **What is in it** — `POST /api/skills/read` returns proposals. One row per skill: an editable
   name, an editable `purpose`, a tick box (**default off**, labelled so it is obvious it means
   "offer this worker to the router"), and the body behind a "read it" expander.
3. **Import** — `POST /api/skills/import` with the edited rows.

Two things the copy must say plainly, because they are the honest state and not decoration:

- a skill fetched from a link is text that becomes a worker's instructions — that is why step 2 shows
  the body and nothing is written before it
- a large skill written for one harness will name tools another CLI does not have; show the byte
  size beside each row so a 30KB one is visibly different from a 4KB one

In `website/src/DocsView.jsx`:

- an **Import skills** button beside *Add profile* (~line 373) opening the dialog
- the profiles list and the playbook shelf get `overflowY: "auto"` with a bounded `maxHeight`, and
  each profile row shows whether it is on the triage roster — read from the agent's config
  `triage_enabled`, shown as a quiet chip, not a colour wash

- [ ] **Step 4: Run the suites and the gate**

```bash
cd website && npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"
cd website && npx eslint -c eslint.undef.mjs -f json src/*.jsx src/*.js
cd website && npm run build
```

The bundle rebuild is REQUIRED — this repo has shipped a UI whose server half had not landed
(`ab82e00a`). `git status` must show changes under `taskuary/web/`.

- [ ] **Step 5: Run the whole suite and commit**

```bash
python -m pytest
```

All green — "no tests ran" is a failure, not a pass. Report the real number.

```bash
git add website/src/SkillImport.jsx website/src/DocsView.jsx website/test taskuary/web
git commit -m "feat: import skills from a wizard, and lists that survive having dozens

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Manual verification

Source-text tests cannot tell you whether an import produces a worker that does good work.

```bash
pip install -e . --no-deps --force-reinstall
```

- [ ] Docs → Profiles shows **Import skills**. Open it; the list finds the skills already on this machine, grouped by plugin.
- [ ] Import one **unticked**. It appears in Profiles, marked as not on the roster, and `roster()` does not name it — confirm by starting a general task and checking triage was not offered it.
- [ ] Tick it, and confirm it now appears in the roster as exactly one line.
- [ ] Open a task assigned to it and read the prompt the session actually got: **the whole body must be there**, not the first 1,800 characters. This is Task 1 and this import in the same check.
- [ ] Import the same skill twice — one profile, updated.
- [ ] Point it at a plugin folder and confirm `commands/` is ignored and `.mcp.json` is untouched.
- [ ] With a large harness-shaped skill (one of the 26KB+ superpowers ones), confirm the size is visible before importing — the point is that you can see it is the wrong kind of thing.

## Self-review notes

**Spec coverage:** `DOC_CHARS` and marked truncation (1); finding and parsing, no `.mcp.json`, no
commands (2); the conversion and the purpose (3); the profile write, roster state, no playbooks (4);
the wizard, the link caution and the scrolling lists (5).

**One thing to settle at the start of Task 5:** the tests assert on `DocsView.jsx`'s markup for the
roster chip, and this plan has not read how that list renders each row. Read it once
(`grep -n "profs.map" -A 20 website/src/DocsView.jsx`), then write the assertions against the real
structure rather than the guessed strings above.

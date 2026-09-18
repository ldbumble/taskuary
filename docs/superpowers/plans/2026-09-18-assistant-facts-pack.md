# Assistant Facts Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The chat assistant knows the app's state - every report and workflow, every setting, every connection, the agents and brains, and the scripts by name - generated from the same sources the tabs read, and can look any of them up by name.

**Architecture:** A new module `taskuary/appfacts.py` builds one bounded STATE block and the per-family look-ups from `store.list_sources`, `store.get_settings`, `store.list_connectors`, `store.list_agents`. The settings schema (key → group, label, type, options) moves from `website/src/SettingsView.jsx` to `taskuary/settings_schema.json`, read by both sides the way `lanes.json` already is. `toolcatalog.READS` gains the look-ups and `concierge.read_op` dispatches them; `concierge.say` appends the STATE block to the general road's system prompt. Nothing writes; nothing changes in the scripts.

**Tech Stack:** Python 3.10, FastAPI, SQLite via `taskuary.store`; React/Vite frontend with Node 22 tests (`node --test`); pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-assistant-runs-the-app-design.md` (section "Facts: the app's state in view").

## Global Constraints

- The facts block rides in every turn of the general road (`concierge.say`) and in none of the scripts (`walk.py`, the composer).
- Generated, never hand-written: every fact reads a store table or the schema file. A look-up that misses lists what exists.
- Bounded: the block is counts and names first; detail only in a look-up. Cap the block at 2,500 characters.
- Name resolution is the rule `report.read` already uses: case-insensitive containment on the title, id wins when given.
- One source of truth for settings: the JSON file. `SettingsView.jsx` keeps only `HIDDEN` and the rendering.
- Frontend gates run under Node 22: `npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"`, the eslint undef check, and `npm run build` (the bundle in `taskuary/web` is committed).
- Full pytest from the repo root before any push. Commit messages carry `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: The settings schema moves to the server

**Files:**
- Create: `taskuary/settings_schema.json`
- Create: `taskuary/settings_schema.py`
- Modify: `website/src/SettingsView.jsx:46-350` (the `KNOB_META` object becomes an import)
- Test: `tests/test_settings_schema.py`, `website/test/settingsSchema.test.mjs`

**Interfaces:**
- Produces: `settings_schema.knobs() -> dict[str, dict]` (key → `{group, label, type, options?, desc, help?}`), `settings_schema.GROUPS -> list[str]`, `settings_schema.describe(key, value) -> str` ("Triage brain (Triage & agents): connector:80" - the value as the schema says it, `on`/`off` for a switch).

- [ ] **Step 1: Write the failing Python test**

```python
# tests/test_settings_schema.py
"""The settings schema is one file both sides read, so the assistant and the Settings page can never
disagree about what a knob is called or what it takes."""
import json, unittest
from pathlib import Path
from taskuary import settings_schema

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_every_knob_has_a_group_a_label_and_a_type(self):
        k = settings_schema.knobs()
        self.assertGreater(len(k), 40)
        for key, meta in k.items():
            for field in ('group', 'label', 'type', 'desc'):
                self.assertTrue(meta.get(field), f'{key} lacks {field}')
            self.assertIn(meta['group'], settings_schema.GROUPS, key)
            if meta['type'] == 'select': self.assertTrue(meta.get('options'), f'{key} is a select with no options')

    def test_the_file_is_the_one_the_page_imports(self):
        view = (ROOT / 'website' / 'src' / 'SettingsView.jsx').read_text(encoding='utf-8')
        self.assertIn('settings_schema.json', view)
        self.assertNotIn('const KNOB_META = {', view)

    def test_describe_says_the_value_in_the_schemas_words(self):
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '1'), 'Intent triage (Triage & routing): on')
        self.assertEqual(settings_schema.describe('intent_classify_enabled', '0'), 'Intent triage (Triage & routing): off')
        self.assertIn('Triage brain', settings_schema.describe('triage_ai', 'connector:80'))
        self.assertEqual(settings_schema.describe('no_such_key', 'x'), 'no_such_key: x')
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest -q tests/test_settings_schema.py`
Expected: FAIL with `ModuleNotFoundError: taskuary.settings_schema`

- [ ] **Step 3: Extract the JSON from the JSX**

Write a one-off script in the scratchpad that reads `website/src/SettingsView.jsx`, slices from `const KNOB_META = {` to the matching `};`, evaluates it with Node (`node -e` on the object literal, printing `JSON.stringify(obj, null, 2)`), and writes `taskuary/settings_schema.json` as `{"_": "<why>", "groups": [...GROUPS from the JSX...], "knobs": {...}}`. Check the count matches (`52` knobs today) and that `help` strings survived.

- [ ] **Step 4: Write the Python reader**

```python
# taskuary/settings_schema.py
"""THE settings vocabulary, once. The Settings page (SettingsView.jsx) and the assistant (appfacts.py,
setting.read) read the same taskuary/settings_schema.json, so a knob cannot be called one thing on the
page and another in the chat - the rule lanes.json already keeps for the lanes."""
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name('settings_schema.json')


@lru_cache(maxsize=1)
def _load() -> dict: return json.loads(_PATH.read_text(encoding='utf-8'))


def knobs() -> dict: return _load()['knobs']
GROUPS = _load()['groups']


def _word(meta: dict, value) -> str:
    v = '' if value is None else str(value)
    if meta.get('type') == 'switch': return 'on' if v.strip() in ('1', 'true', 'on') else 'off'
    return v or '(blank)'


def describe(key: str, value) -> str:
    """'Triage brain (Triage & agents): connector:80' - the label, the group, the value as the schema
    says it. An unknown key is said plainly rather than dressed up."""
    meta = knobs().get(key)
    if not meta: return f'{key}: {value}'
    return f"{meta['label']} ({meta['group']}): {_word(meta, value)}"
```

- [ ] **Step 5: Make the page import the file**

In `website/src/SettingsView.jsx` replace the `const KNOB_META = { ... };` block with:

```js
import schema from "../../taskuary/settings_schema.json" with { type: "json" };
// ONE VOCABULARY for the knobs, in taskuary/settings_schema.json - the assistant reads the same file
// (settings_schema.py), so a knob is called the same thing on this page and in the chat.
const KNOB_META = schema.knobs;
```
and replace `const GROUPS = [ ... ];` with `const GROUPS = schema.groups;`. Keep `HIDDEN` where it is.

- [ ] **Step 6: Write the JS test**

```js
// website/test/settingsSchema.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };

test("the Settings page draws its knobs from the shared schema file", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/SettingsView.jsx", import.meta.url)), "utf8");
  assert.match(view, /import schema from "\.\.\/\.\.\/taskuary\/settings_schema\.json"/);
  assert.match(view, /const KNOB_META = schema\.knobs;/);
  assert.match(view, /const GROUPS = schema\.groups;/);
  assert.doesNotMatch(view, /const KNOB_META = \{/);
});

test("every knob carries what the page needs to draw it", () => {
  for (const [key, meta] of Object.entries(schema.knobs)) {
    for (const f of ["group", "label", "type", "desc"]) assert.ok(meta[f], `${key} lacks ${f}`);
    assert.ok(schema.groups.includes(meta.group), `${key}: unknown group ${meta.group}`);
  }
});
```

- [ ] **Step 7: Run both test sets and the build**

Run: `python -m pytest -q tests/test_settings_schema.py` → PASS.
Run (in `website/`): `npm exec --yes --package=node@22 -- node --test test/settingsSchema.test.mjs test/settingsOther.test.mjs` → all pass.
Run: `npm exec --yes --package=node@22 -- npm run build` → built.
Open the Settings page on a scratch demo server (`TASKUARY_HOME=<tmp> TASKUARY_ALLOW_TEST_HOME=1 python -m taskuary.cli --demo --no-browser --port 7811`) and confirm every group still lists its knobs.

- [ ] **Step 8: Commit**

```bash
git add taskuary/settings_schema.json taskuary/settings_schema.py website/src/SettingsView.jsx website/test/settingsSchema.test.mjs tests/test_settings_schema.py taskuary/web
git commit -m "feat: the settings schema is one file the page and the assistant both read"
```

---

### Task 2: appfacts - the app's state, generated

**Files:**
- Create: `taskuary/appfacts.py`
- Test: `tests/test_appfacts.py`

**Interfaces:**
- Consumes: `settings_schema.knobs()`, `settings_schema.describe()`, `reports.schedule_words(cfg)`, `reports.reach_of(cfg)`, `workflows.is_workflow(cfg)`, `store.list_sources(active_only=False)`, `store.report_runs(sid, 1)`, `store.list_connectors()`, `store.list_agents()`, `store.get_settings()`, `aidefaults.SLOTS`.
- Produces:
  - `appfacts.reports(store) -> list[dict]` each `{source_id, title, workflow: bool, schedule, reach, active, last_at, last_ok: bool|None, last_said}`
  - `appfacts.settings(store) -> list[dict]` each `{key, group, label, type, value, said}` (hidden keys excluded: those not in the schema)
  - `appfacts.connections(store) -> list[dict]` each `{connector_id, type, name, active, has_secret, last_sync, last_error}`
  - `appfacts.agents(store) -> list[dict]` each `{name, kind, active}`; `appfacts.brains(store) -> list[str]` ("triage: Azure OpenAI", ...)
  - `appfacts.SCRIPTS -> list[tuple[str, str]]` (name, what it does)
  - `appfacts.state_block(store, cap: int = 2500) -> str`
  - `appfacts.find_report(store, title: str = '', source_id=None) -> dict | None`, `appfacts.find_connection(store, name: str = '', connector_id=None) -> dict | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_appfacts.py
"""What the assistant knows about the APP, generated from the tables the tabs read - never typed in."""
import json, unittest
from taskuary import appfacts
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.save_source({'Channel': 'report', 'Address': 'ar@report', 'Active': 1,
                   'ConfigJson': json.dumps({'title': 'Monthly AR Report', 'type': 'mssql', 'daily_at': '07:00', 'reach': 'always'})}, 't')
    wf = s.save_source({'Channel': 'report', 'Address': 'adp@walk', 'Active': 1,
                        'ConfigJson': json.dumps({'title': 'ADP hours export', 'type': 'agent', 'is_workflow': True, 'cron': '0 6 * * 1-5'})}, 't')
    s.add_report_run(wf, {'at': '2026-09-18 06:01:00', 'title': 'ADP hours export', 'failed': True, 'error': 'sign-in page'})
    s.save_connector({'Type': 'outlook', 'Name': 'Uri mailbox', 'Active': 1, 'ConfigJson': '{}'}, 't')
    s.save_connector({'Type': 'teams', 'Name': 'Teams', 'Active': 0, 'ConfigJson': '{}'}, 't')
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('intent_classify_enabled', '1', 't'); s.set_setting('poll_minutes', '10', 't')
    return s


class FactsTests(unittest.TestCase):
    def test_reports_and_workflows_are_told_apart_with_their_clock_and_last_outcome(self):
        rows = {r['title']: r for r in appfacts.reports(store())}
        self.assertFalse(rows['Monthly AR Report']['workflow']); self.assertIn('07:00', rows['Monthly AR Report']['schedule'])
        self.assertTrue(rows['ADP hours export']['workflow']); self.assertIs(rows['ADP hours export']['last_ok'], False)
        self.assertIn('sign-in page', rows['ADP hours export']['last_said'])
        self.assertIsNone(rows['Monthly AR Report']['last_ok'])                      # never ran: unknown, not failed

    def test_settings_come_from_the_schema_with_their_values_in_words(self):
        rows = {r['key']: r for r in appfacts.settings(store())}
        self.assertEqual(rows['intent_classify_enabled']['said'], 'Intent triage (Triage & routing): on')
        self.assertEqual(rows['poll_minutes']['value'], '10')
        self.assertNotIn('ingest_status', rows)                                       # bookkeeping is not a knob

    def test_connections_and_agents(self):
        c = {r['name']: r for r in appfacts.connections(store())}
        self.assertTrue(c['Uri mailbox']['active']); self.assertFalse(c['Teams']['active']); self.assertFalse(c['Teams']['has_secret'])
        self.assertEqual([a['name'] for a in appfacts.agents(store())], ['coder'])

    def test_find_by_name_is_case_insensitive_containment_and_id_wins(self):
        s = store()
        self.assertEqual(appfacts.find_report(s, 'ar report')['title'], 'Monthly AR Report')
        self.assertEqual(appfacts.find_report(s, 'nothing like it', source_id=appfacts.reports(s)[0]['source_id'])['title'], 'Monthly AR Report')
        self.assertIsNone(appfacts.find_report(s, 'payroll'))
        self.assertEqual(appfacts.find_connection(s, 'teams')['type'], 'teams')

    def test_the_state_block_is_counts_and_names_first_and_bounded(self):
        b = appfacts.state_block(store())
        self.assertIn('THE APP RIGHT NOW', b)
        self.assertIn('2 reports', b); self.assertIn('1 workflow', b)
        self.assertIn('Monthly AR Report', b); self.assertIn('ADP hours export', b); self.assertIn('failed', b)
        self.assertIn('Uri mailbox', b); self.assertIn('Teams (off)', b)
        self.assertIn('walk me through my tasks', b)                                   # the scripts, by name
        self.assertLess(len(b), 2500)
        many = store()
        for n in range(80):
            many.save_source({'Channel': 'report', 'Address': f'r{n}@x', 'Active': 1, 'ConfigJson': json.dumps({'title': f'Report number {n}'})}, 't')
        self.assertLess(len(appfacts.state_block(many)), 2600)                        # the cap holds; the look-up has the rest
        self.assertIn('more - reports.list has them all', appfacts.state_block(many))
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest -q tests/test_appfacts.py`
Expected: FAIL with `ModuleNotFoundError: taskuary.appfacts`

- [ ] **Step 3: Write the module**

```python
# taskuary/appfacts.py
"""What the assistant knows about the APP - every report and workflow, setting, connection, agent
and brain - read off the tables the tabs read, never typed in. Asked from WhatsApp to "run me the AR
report" it had no list of reports at all (the owner, 2026-09-18): it knew the pile and nothing else.
This is the state block that rides every turn of the general road, and the finders the look-ups use.
It writes nothing and asks no model anything."""
import json
from . import settings_schema

# the deterministic roads, by the names the owner says (spec: "Scripts"). Static on purpose.
SCRIPTS = [('walk me through my tasks', 'Next through the pile, one item at a time - the core'),
           ('set up Taskuary', 'the tour of the app, stop by stop; from a chat it opens on your connections'),
           ('set up a report', 'describe a check or a workflow and the composer builds it')]


def _cfg(src) -> dict:
    try: return json.loads(src.get('ConfigJson') or '{}') or {}
    except ValueError: return {}


def reports(store) -> list:
    from . import reports as rep, workflows
    out = []
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        cfg = _cfg(src)
        runs = store.report_runs(src['SourceId'], 1) or []
        last = runs[0] if runs else None
        out.append({'source_id': src['SourceId'], 'title': cfg.get('title') or src.get('Address') or '',
                    'workflow': bool(workflows.is_workflow(cfg)), 'schedule': rep.schedule_words(cfg), 'reach': rep.reach_of(cfg),
                    'active': bool(src.get('Active')), 'last_at': (last or {}).get('at') or '',
                    'last_ok': (not last.get('failed')) if last else None,
                    'last_said': str((last or {}).get('error') or (last or {}).get('summary') or (last or {}).get('said') or '')[:200]})
    return out


def settings(store) -> list:
    vals, out = store.get_settings(), []
    for key, meta in settings_schema.knobs().items():
        v = vals.get(key, '')
        out.append({'key': key, 'group': meta['group'], 'label': meta['label'], 'type': meta['type'], 'value': str(v or ''),
                    'said': settings_schema.describe(key, v)})
    return out


def connections(store) -> list:
    return [{'connector_id': c['ConnectorId'], 'type': c.get('Type') or '', 'name': c.get('Name') or c.get('Type') or '',
             'active': bool(c.get('Active')), 'has_secret': bool(c.get('HasSecret')),
             'last_sync': str(c.get('LastSyncAt') or ''), 'last_error': str(c.get('LastError') or '')[:200]}
            for c in store.list_connectors()]


def agents(store) -> list:
    return [{'name': a['Name'], 'kind': a.get('Kind') or '', 'active': bool(a.get('Active', 1))} for a in store.list_agents(active_only=False)]


def brains(store) -> list:
    """'triage: Azure OpenAI' for each brain slot - the same words walk._brain_name resolves."""
    from .aidefaults import SLOTS
    from .walk import _brain_name
    st = store.get_settings()
    return [f"{s['label'].lower()}: {_brain_name(store, st.get(s['key']))}" for s in SLOTS]


def _match(rows, want: str, field: str, id_field: str, id_val):
    if id_val is not None:
        hit = next((r for r in rows if str(r[id_field]) == str(id_val)), None)
        if hit: return hit
    w = (want or '').strip().lower()
    return next((r for r in rows if w and w in str(r[field]).lower()), None) if w else None


def find_report(store, title: str = '', source_id=None): return _match(reports(store), title, 'title', 'source_id', source_id)
def find_connection(store, name: str = '', connector_id=None): return _match(connections(store), name, 'name', 'connector_id', connector_id)


def state_block(store, cap: int = 2500) -> str:
    """Counts and names first; detail is the look-ups' job. Capped so a turn stays quick - past the
    cap a family says how many more there are and which look-up has them."""
    reps = reports(store); wfs = [r for r in reps if r['workflow']]; plain = [r for r in reps if not r['workflow']]
    conns = connections(store)
    def named(rows, f, n=12, more='reports.list'):
        names = [f(r) for r in rows[:n]]
        if len(rows) > n: names.append(f'+{len(rows) - n} more - {more} has them all')
        return '; '.join(names) if names else 'none'
    def rep_line(r): return f"{r['title']}" + (' (off)' if not r['active'] else '') + (' - last run failed' if r['last_ok'] is False else '')
    def con_line(c): return f"{c['name']}" + ('' if c['active'] else ' (off)') + (' - erroring' if c['last_error'] and c['active'] else '')
    lines = ['THE APP RIGHT NOW (read from its own tables; look things up by name for detail)',
             f"  {len(plain)} report{'s' if len(plain) != 1 else ''}: {named(plain, rep_line)}",
             f"  {len(wfs)} workflow{'s' if len(wfs) != 1 else ''}: {named(wfs, rep_line)}",
             f"  {len(conns)} connections: {named(conns, con_line, more='connections.list')}",
             f"  agents: {', '.join(a['name'] for a in agents(store)) or 'none'} | brains: {'; '.join(brains(store))}",
             f"  settings: {len(settings_schema.knobs())} knobs in groups {', '.join(settings_schema.GROUPS)} - setting.read <key or label> says one, settings.list <group> a group",
             '  scripts you can start by name: ' + '; '.join(f'"{n}" - {what}' for n, what in SCRIPTS)]
    out = '\n'.join(lines)
    return out if len(out) <= cap else out[:cap - 1] + '…'
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q tests/test_appfacts.py`
Expected: PASS. If `save_connector` or `add_report_run` signatures differ from the test, read `taskuary/store.py` for the real ones and fix the TEST, not the module.

- [ ] **Step 5: Commit**

```bash
git add taskuary/appfacts.py tests/test_appfacts.py
git commit -m "feat: the assistant's facts about the app, read from its own tables"
```

---

### Task 3: The look-ups, by name

**Files:**
- Modify: `taskuary/toolcatalog.py:139-170` (`READS`, `valid`)
- Modify: `taskuary/concierge.py:1354-1400` (`read_op`)
- Test: `tests/test_zz_toolcatalog.py` (new class `AppReadTests`)

**Interfaces:**
- Consumes: `appfacts.reports/settings/connections/agents/find_report/find_connection`, `settings_schema.knobs()/describe()`.
- Produces: read kinds `reports.list`, `settings.list` (`group` optional), `setting.read` (`key`, or `label`), `connections.list`, `connection.read` (`name` or `connector_id`), `agents.list`; `report.read` now also prints `source_id` and resolves through `appfacts.find_report`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_zz_toolcatalog.py
class AppReadTests(unittest.TestCase):
    """The look-ups that make "what reports do we have" answerable, and "run the AR report" resolvable."""
    def _store(self):
        import tests.test_appfacts as A
        return A.store()

    def test_every_new_read_is_in_the_catalogue_and_validates(self):
        b = toolcatalog.block()
        for k in ('reports.list', 'settings.list', 'setting.read', 'connections.list', 'connection.read', 'agents.list'):
            self.assertTrue(toolcatalog.is_read(k), k); self.assertIn(k, b)
        self.assertEqual(toolcatalog.valid('setting.read', {}), 'setting.read needs key or label')
        self.assertEqual(toolcatalog.valid('reports.list', {}), '')

    def test_reports_list_names_them_with_ids_clocks_and_outcomes(self):
        out = concierge.read_op(self._store(), 'reports.list', {})
        self.assertIn('Monthly AR Report', out); self.assertIn('WORKFLOW ADP hours export', out)
        self.assertIn('source_id', out); self.assertIn('07:00', out); self.assertIn('FAILED', out)

    def test_report_read_finds_by_part_of_the_name_and_says_its_id(self):
        out = concierge.read_op(self._store(), 'report.read', {'title': 'ar report'})
        self.assertIn('Monthly AR Report', out); self.assertIn('source_id', out)
        miss = concierge.read_op(self._store(), 'report.read', {'title': 'payroll'})
        self.assertIn('No report by that name', miss); self.assertIn('Monthly AR Report', miss)

    def test_settings_read_by_key_or_label_and_a_group_lists_its_knobs(self):
        s = self._store()
        self.assertIn('Intent triage (Triage & routing): on', concierge.read_op(s, 'setting.read', {'key': 'intent_classify_enabled'}))
        self.assertIn('Intent triage', concierge.read_op(s, 'setting.read', {'label': 'intent triage'}))
        self.assertIn('No setting by that name', concierge.read_op(s, 'setting.read', {'label': 'warp drive'}))
        out = concierge.read_op(s, 'settings.list', {'group': 'Triage & routing'})
        self.assertIn('Intent triage', out); self.assertNotIn('Triage brain', out)
        self.assertIn('Triage & agents', concierge.read_op(s, 'settings.list', {}))            # no group: the groups

    def test_connections_and_agents(self):
        s = self._store()
        out = concierge.read_op(s, 'connections.list', {})
        self.assertIn('Uri mailbox', out); self.assertIn('Teams', out); self.assertIn('off', out)
        self.assertIn('outlook', concierge.read_op(s, 'connection.read', {'name': 'mailbox'}))
        self.assertIn('No connection by that name', concierge.read_op(s, 'connection.read', {'name': 'zoho'}))
        self.assertIn('coder', concierge.read_op(s, 'agents.list', {}))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/test_zz_toolcatalog.py -k AppRead`
Expected: FAIL (`is_read('reports.list')` is False).

- [ ] **Step 3: Extend the catalogue**

In `taskuary/toolcatalog.py` replace `READS` and the `need` table in `valid()`:

```python
READS = {
    'task.read':        'everything on one task - its summary, status, the messages on it, what agents said and did. `ref`: TQ-0401 (or `id`)',
    'timeline.search':  'find rows anywhere in the history, however old - takes the same SELECT fields below, plus `limit`. Returns refs, senders, subjects and dates; read one with task.read',
    'report.read':      'a report or workflow and its last runs - what it said, whether it failed and why, and its source_id. `title`: part of its name (or `source_id`)',
    'reports.list':     'every report and workflow: name, source_id, clock, how it reaches the owner, last outcome',
    'settings.list':    'the settings in one `group` (or, with no group, the groups themselves and how many knobs each has)',
    'setting.read':     'one setting, its value in words and what it does. `key` (or `label`: part of its name)',
    'connections.list': 'every connection: name, type, on or off, whether it has a key, last sync, last error',
    'connection.read':  'one connection in full. `name`: part of its name (or `connector_id`)',
    'agents.list':      'the agents and profiles, and which brain answers which job',
}
```
and in `valid()`:
```python
        need = {'task.read': ('ref', 'id'), 'report.read': ('title', 'source_id'), 'timeline.search': (),
                'reports.list': (), 'settings.list': (), 'setting.read': ('key', 'label'),
                'connections.list': (), 'connection.read': ('name', 'connector_id'), 'agents.list': ()}[kind]
```

- [ ] **Step 4: Dispatch them in read_op**

In `taskuary/concierge.py`, replace the `report.read` branch and add the rest before `if kind == 'timeline.search':`:

```python
    if kind == 'report.read':
        from . import appfacts
        r = appfacts.find_report(store, str(p.get('title') or ''), p.get('source_id'))
        if not r:
            return 'No report by that name. The ones set up: ' + ', '.join(x['title'] for x in appfacts.reports(store)[:20])
        out = [f"{'WORKFLOW' if r['workflow'] else 'REPORT'} {r['title']} (source_id {r['source_id']}, {'on' if r['active'] else 'off'}) - "
               f"runs {r['schedule'] or 'on no clock'}; reaches you: {r['reach']}"]
        for run in (store.report_runs(r['source_id'], 6) or []):
            out.append(f"  {str(run.get('at') or '')[:16]} {'FAILED' if run.get('failed') else 'ok'} "
                       f"{run.get('ms') or 0}ms - {_cut(run.get('error') or run.get('summary') or run.get('said') or '', 400)}")
        return NEWLINE.join(out)
    if kind == 'reports.list':
        from . import appfacts
        rows = appfacts.reports(store)
        if not rows: return 'No reports or workflows are set up.'
        return NEWLINE.join(f"{'WORKFLOW' if r['workflow'] else 'REPORT'} {r['title']} (source_id {r['source_id']}{'' if r['active'] else ', off'}) - "
                            f"{r['schedule'] or 'no clock'}; reaches you: {r['reach']}; last: "
                            f"{'never ran' if r['last_ok'] is None else ('FAILED - ' + r['last_said']) if r['last_ok'] is False else 'ok ' + r['last_at'][:16]}"
                            for r in rows)
    if kind == 'settings.list':
        from . import appfacts, settings_schema
        rows, group = appfacts.settings(store), str(p.get('group') or '').strip().lower()
        if not group:
            return NEWLINE.join(f"{g}: {sum(1 for r in rows if r['group'] == g)} knobs" for g in settings_schema.GROUPS)
        hit = [r for r in rows if group in r['group'].lower()]
        if not hit: return 'No settings group by that name. The groups: ' + ', '.join(settings_schema.GROUPS)
        return NEWLINE.join(f"{r['said']}  [{r['key']}]" for r in hit)
    if kind == 'setting.read':
        from . import appfacts, settings_schema
        rows, key, label = appfacts.settings(store), str(p.get('key') or '').strip(), str(p.get('label') or '').strip().lower()
        r = next((x for x in rows if x['key'] == key), None) or next((x for x in rows if label and label in x['label'].lower()), None)
        if not r: return 'No setting by that name. The groups: ' + ', '.join(settings_schema.GROUPS) + ' - settings.list <group> names their knobs.'
        meta = settings_schema.knobs()[r['key']]
        return f"{r['said']}  [{r['key']}, a {r['type']}{' - ' + ' | '.join(meta['options']) if meta.get('options') else ''}]{NEWLINE}{meta.get('desc', '')}"
    if kind == 'connections.list':
        from . import appfacts
        rows = appfacts.connections(store)
        if not rows: return 'Nothing is connected yet.'
        return NEWLINE.join(f"{c['name']} ({c['type']}, {'on' if c['active'] else 'off'}{', no key' if not c['has_secret'] else ''})"
                            f"{' - last sync ' + c['last_sync'][:16] if c['last_sync'] else ''}{' - ERROR ' + c['last_error'] if c['last_error'] else ''}" for c in rows)
    if kind == 'connection.read':
        from . import appfacts
        c = appfacts.find_connection(store, str(p.get('name') or ''), p.get('connector_id'))
        if not c: return 'No connection by that name. Connected: ' + ', '.join(x['name'] for x in appfacts.connections(store)[:30])
        return (f"{c['name']} - type {c['type']}, connector_id {c['connector_id']}, {'on' if c['active'] else 'off'}, "
                f"{'has a key' if c['has_secret'] else 'no key yet'}, last sync {c['last_sync'][:16] or 'never'}"
                + (f"{NEWLINE}last error: {c['last_error']}" if c['last_error'] else ''))
    if kind == 'agents.list':
        from . import appfacts
        return ('agents: ' + ', '.join(f"{a['name']} ({a['kind']}{'' if a['active'] else ', off'})" for a in appfacts.agents(store)) + NEWLINE
                + 'brains: ' + '; '.join(appfacts.brains(store)))
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q tests/test_zz_toolcatalog.py tests/test_chat_proposals.py`
Expected: PASS, including the existing `test_report_read` behaviour (title containment still works).

- [ ] **Step 6: Commit**

```bash
git add taskuary/toolcatalog.py taskuary/concierge.py tests/test_zz_toolcatalog.py
git commit -m "feat: the assistant can look up every report, setting, connection and agent by name"
```

---

### Task 4: The state block rides the general road

**Files:**
- Modify: `taskuary/concierge.py:2327` (the `system` assembly in `say`)
- Test: `tests/test_zz_toolcatalog.py` (new test in `AppReadTests`)

**Interfaces:**
- Consumes: `appfacts.state_block(store)`.
- Produces: the system prompt of every general-road turn ends with the STATE block; scripts are untouched (`walk.py` reaches no model - unchanged).

- [ ] **Step 1: Write the failing test**

```python
    def test_every_general_turn_carries_the_app_state(self):
        """Asked "run me the AR report" from a chat, the assistant had no list of reports at all. The
        state block rides the system prompt of the general road, and never the scripts."""
        s = self._store()
        seen = {}
        def llm(system, user, max_tokens=None): seen['system'] = system; return 'Two reports are set up.'
        concierge.say(s, 'what reports do we have?', llm=llm)       # say(store, text, key=None, llm=None, ...)
        self.assertIn('THE APP RIGHT NOW', seen['system'])
        self.assertIn('Monthly AR Report', seen['system'])
        self.assertIn('walk me through my tasks', seen['system'])
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest -q tests/test_zz_toolcatalog.py -k carries_the_app_state`
Expected: FAIL - `'THE APP RIGHT NOW' not found`.

- [ ] **Step 3: Append the block**

In `concierge.say`, change the `system` assembly to:

```python
        from . import toolcatalog, appfacts
        system = (_system(store, llm) + '\n\n' + toolcatalog.block(store)
                  # the app's own state, generated (appfacts): every turn of the general road knows what
                  # is set up, so "run the AR report" can name a report and "is Teams connected" is a read
                  + '\n\n' + appfacts.state_block(store)
                  + (f'\n\n{hub.ASSISTANT_LINE}' if hub.enabled(store) else ''))
```
Wrap `appfacts.state_block(store)` in a try that logs a warning and yields `''` - a table that cannot be read must never take the chat down.

- [ ] **Step 4: Run the tests and the reaction matrix**

Run: `python -m pytest -q tests/test_zz_toolcatalog.py tests/test_assistant_reactions.py tests/test_chat_proposals.py tests/test_concierge.py`
Expected: PASS. If a reaction test pins the exact system prompt, re-pin it to include the block.

- [ ] **Step 5: Commit**

```bash
git add taskuary/concierge.py tests/test_zz_toolcatalog.py
git commit -m "feat: every turn of the general road knows the app's state"
```

---

### Task 5: Gates, live proof, docs

**Files:**
- Modify: `docs/superpowers/specs/2026-09-18-assistant-runs-the-app-design.md` (mark the facts pack landed, with the sha)
- Test: full pytest, full Node 22 suite, eslint undef, build

- [ ] **Step 1: Full suites**

Run: `python -m pytest -q -p no:cacheprovider` from the repo root → all pass.
Run in `website/`: `npm exec --yes --package=node@22 -- node --test "test/**/*.test.mjs"` → all pass; `npm exec --yes --package=node@22 --package=eslint@10.10.0 -- eslint -c eslint.undef.mjs src` → 0 no-undef; `npm exec --yes --package=node@22 -- npm run build`.

- [ ] **Step 2: Live proof on a scratch home**

Start `TASKUARY_HOME=<tmp> TASKUARY_ALLOW_TEST_HOME=1 python -m taskuary.cli --demo --no-browser --port 7811`. With the demo token, `POST /api/concierge/say` (read `server.py` for the body: `text`, `task_id` of the dock task from `POST /api/assistant/dock`) with "what reports do we have" and "is Teams connected". The demo has a scripted brain; confirm the answers name the demo's reports and connections, and that a `report.read` look-up ran (the receipt trail in the response, or the log line `read_op`). Screenshot the chat on the Assistant tab into the scratchpad.

- [ ] **Step 3: Note the landing in the spec and push**

Append to the spec's "Order of work" item 1: `Landed <sha>, 2026-09-18.` Then:
```bash
git add docs/superpowers/specs/2026-09-18-assistant-runs-the-app-design.md
git commit -m "docs: the facts pack landed"
git push origin master
```

---

## Self-review

- **Spec coverage.** Facts table: reports and workflows (Task 2/3), settings with schema (Task 1/2/3), connections (2/3), agents and brains (2/3), scripts named (2, in the block). Look-ups one per family with name-or-id and miss-lists-what-exists (3). Block bounded, rides the general road only (2/4). Nothing writes; tiers, ideas, doorways are later packs by design.
- **Placeholders.** None: every step carries its code. The one conditional ("if the llm seam differs") names the file and function to read.
- **Type consistency.** `appfacts.reports()` rows use `source_id/title/workflow/schedule/reach/active/last_at/last_ok/last_said` in Tasks 2 and 3 alike; `find_report(store, title, source_id)` and `find_connection(store, name, connector_id)` match their call sites; `settings_schema.describe(key, value)` and `GROUPS` match Tasks 1-3.

# Taskuary as the Assistant's Source — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every context block the Assistant reads a named, declared, per-report-configurable thing, shown on the report card with its tables and SQL and its token cost, and name the block behind every line the post says.

**Architecture:** A block registry (`taskuary/assistantblocks.py`) declares each context block: label, kind (`query` | `view`), the tables it reads, its SQL or its builder, its window, its cap, whether it is on by default and whether it also proposes a row. `assistant.inputs()` stops being nine hardcoded calls and becomes a loop over the blocks a report resolved. The report's `ConfigJson` holds overrides only. The Reports card renders the registry. Each block records the message and task ids it contributed; `build_inputs` returns that `mid -> block` index alongside the text, and it attributes lines without asking the model.

**Tech Stack:** Python 3.10, FastAPI, SQLite (`taskuary/store.py`), React 18 + MUI 6 (`website/src/ReportsView.jsx`), pytest, node --test.

**Spec:** `docs/superpowers/specs/2026-09-19-assistant-reads-taskuary-design.md`

## Global Constraints

- **Defaults reproduce today exactly.** A report with no `blocks` key must produce byte-identical
  model input to the current implementation. The test that asserts this gates every later task and
  is never relaxed.
- **Resolution order:** block declaration -> the global setting where one exists -> the report's
  own override. Exactly this order, everywhere.
- **`systems_only` is derived, never stored.** It means "no Taskuary blocks resolved on". A report
  with watch sources and no explicit `blocks` key resolves every block off, which is today's
  behaviour; a report with neither resolves the declared defaults, which is also today's behaviour.
- **A block that cannot say what it reads cannot ship.** Every entry declares `tables` and a
  `build` callable, and a `query` block declares `sql` as well.
- **`MONO`, `card`, `PANEL2`, `INK`, `DIM`, `BORDER`** are the constants `ReportsView.jsx` already
  imports. Use whatever that file already uses for monospace rather than introducing a name; if it
  has none, take the one `SettingsView.jsx` uses.
- **Nothing is trimmed silently.** No token ceiling. The card prices it; the owner decides.
- **Code style:** fast.ai/Jeremy Howard density, matching `taskuary/assistant.py` — tuple
  unpacking, one-line guards, comments say *why*. Lines under ~160 chars.
- **Shared checkout.** Other agents work this tree. `git status` before committing; stage only the
  files the task names; never `git add -A`.
- **The full pytest suite from the repo root must pass before any push.** "no tests ran" is a
  failure.

---

### Task 1: The block registry and the loop

The registry, the sixteen blocks, and `inputs()` rewritten to walk them. No config is read yet and
no UI changes. The deliverable is that nothing changes and a test proves it.

**Files:**
- Create: `taskuary/assistantblocks.py`
- Modify: `taskuary/assistant.py:867-895` (`inputs`)
- Test: `tests/test_assistant_blocks.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `assistantblocks.Block` — a `NamedTuple` with fields `id: str`, `label: str`, `kind: str`
    (`'query'` or `'view'`), `tables: tuple[str, ...]`, `heading: str`, `build: callable`,
    `sql: str | None = None`, `window: tuple[str, int, str] | None = None`, `cap: int | None = None`,
    `default_on: bool = True`, `proposes: bool = False`, `setting: str | None = None`.
  - `assistantblocks.CATALOGUE: tuple[Block, ...]` — the sixteen, in catalogue order.
  - `assistantblocks.by_id(bid: str) -> Block | None`.
  - `render(store, block, opts) -> tuple[str, list[int]]` — the block's rendered text and the
    message ids it contributed. Named `render`, not `build`: `Block.build` is the field holding the
    callable, and two `build`s one line apart is how a reader loses ten minutes. `opts` is a dict like `{'days': 7, 'cap': 20}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assistant_blocks.py
"""Every context block the Assistant reads is a declaration, and the defaults are what it read
before there were declarations (the assistant-reads-Taskuary design, 2026-09-19)."""
import unittest
from taskuary import assistantblocks as B
import tests.test_appfacts as A


class CatalogueTests(unittest.TestCase):
    def test_every_block_says_what_it_reads(self):
        self.assertGreaterEqual(len(B.CATALOGUE), 16)
        seen = set()
        for b in B.CATALOGUE:
            self.assertNotIn(b.id, seen, f'{b.id} declared twice'); seen.add(b.id)
            self.assertTrue(b.label, f'{b.id} has no label')
            self.assertEqual(bool(b.heading), not b.proposes, f'{b.id}: a context block needs a heading, a producer must not have one')
            self.assertIn(b.kind, ('query', 'view'), f'{b.id} is neither a query nor a view')
            self.assertTrue(b.tables, f'{b.id} names no table')
            self.assertTrue(callable(b.build), f'{b.id} has no builder')
            if b.kind == 'query': self.assertTrue(b.sql, f'{b.id} is a query with no SQL to show')

    def test_a_query_blocks_sql_runs(self):
        s = A.store()
        for b in B.CATALOGUE:
            if b.kind != 'query' or not b.sql: continue
            with self.subTest(block=b.id):
                text, mids = B.render(s, b, B.defaults(s, b))
                self.assertIsInstance(text, str); self.assertIsInstance(mids, list)

    def test_by_id_finds_and_misses(self):
        self.assertEqual(B.by_id('gone_quiet').label, 'Work gone quiet')
        self.assertIsNone(B.by_id('nope'))


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_assistant_blocks.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'taskuary.assistantblocks'`

- [ ] **Step 3: Write the registry**

Create `taskuary/assistantblocks.py`. Each block wraps a function that already exists in
`assistant.py` — this task moves no logic, it only declares what is already there.

```python
"""WHAT THE ASSISTANT READS, declared. Every block of its model input is one entry here: what it is
called, which tables it reads, the SQL behind it (or that it is composed in code and cannot be one
statement), how far back it looks and how many rows it takes. `assistant.inputs` walks this list;
the Reports card renders it; the post names the block behind each line. The list used to be nine
hardcoded calls inside inputs(), which is why an owner could rewrite the instruction to say "look at
the past month" and change nothing - the month was never in the payload."""
from typing import Callable, NamedTuple


class Block(NamedTuple):
    id: str
    label: str                      # what the card calls it
    kind: str                       # 'query' - one SELECT, shown verbatim | 'view' - composed in code
    tables: tuple                   # the Taskuary tables it reads, for the card
    heading: str = None             # a CONTEXT block's section head in the model's input.
                                    # None for a PRODUCER block: its rows render under CANDIDATES:,
                                    # which is where they have always rendered - giving them a
                                    # section of their own would change today's payload, and the
                                    # first global constraint says it may not.
    build: Callable                 # CONTEXT: (store, opts) -> (text, [mids]).
                                    # PRODUCER: (store, opts) -> ([candidate dicts], [mids]); each
                                    # dict carries 'block' so Task 4 attributes it with no model.
    sql: str = None                 # required when kind == 'query'
    window: tuple = None            # (unit, default, label) - ('days', 2, 'How far back...') or None
    knobs: tuple = ()               # any OTHER numbers the owner may turn: (name, default, label).
                                    # `connectors` needs ('floor', 3, 'Threads before it is worth
                                    # saying') - the number that would have let the owner tune
                                    # b2a4c870 without a release, and the reason this is not just
                                    # `window`.
    cap: int = None
    default_on: bool = True
    proposes: bool = False          # also posts a row of its own, with no model behind it
    setting: str = None             # the global setting its default comes from, when one exists


GONE_QUIET_SQL = """SELECT t.TaskId, t.Title, t.Status, t.Kind
FROM task t
WHERE t.Status IN ('open', 'in_progress', 'waiting')
  AND IFNULL((SELECT MAX(CreatedAt) FROM comment WHERE TaskId = t.TaskId), '') < :cut
  AND IFNULL((SELECT MAX(CreatedAt) FROM message WHERE TaskId = t.TaskId), '') < :cut
  AND NOT EXISTS (SELECT 1 FROM run WHERE TaskId = t.TaskId AND Status = 'running')
ORDER BY t.UpdatedAt LIMIT :cap"""
# One constant per QUERY block - sixteen entries, four of them views with no constant. The table
# below this code block names every id, the function it delegates to and the tables it reads; a
# query block's constant is the statement that function already runs, lifted verbatim.


def _threads(store, o):
    from .assistant import _people_context
    text, mids = _people_context(store, days=o['days'])
    return text, mids


def _arrivals(store, o):
    from .assistant import _recent
    return _recent(store, days=o['days']), []


# One wrapper per block, each two lines like the two above: call the existing function, return its
# text and the message ids it contributed. See the table below for the full mapping.


CATALOGUE = (
    Block('threads', 'What people said', 'view', ('message', 'route', 'task'),
          'WHAT PEOPLE SAID (the last {days} days, by thread, newest first; the last lines of each, oldest first. '
          "Each head quotes what triage decided when the latest line arrived: when you disagree, say so in your line - "
          "'triage filed this as fyi, but...' - never raise a thread as if nothing had judged it)",
          _threads, window=('days', 2, 'How far back to read conversations')),
    Block('arrivals', 'What arrived', 'view', ('message', 'route', 'source'),
          'ARRIVED IN THE LAST {days} DAYS (xN = that many alike; each line carries the latest message\'s words, '
          "a report's schedule, and a failure's cause)",
          _arrivals, window=('days', 2, 'How far back to roll up arrivals')),
    # ...and the other fourteen, in the order of the table below. A CONTEXT block's `heading` is
    # today's section head from inputs(); a PRODUCER block has heading=None.
)

_BY_ID = {b.id: b for b in CATALOGUE}


def by_id(bid: str): return _BY_ID.get(bid)


def defaults(store, b: Block) -> dict:
    """The declaration, then the global setting where the block names one. The report's own override
    is applied on top of this by `resolve` (Task 2) - three places hold a number and this is the
    order they win in."""
    o = {'on': b.default_on, 'cap': b.cap}
    if b.window: o[b.window[0]] = b.window[1]
    for name, dflt, _ in b.knobs: o[name] = dflt
    if b.setting:
        try:
            v = store.get_settings().get(b.setting)
            if v not in (None, ''): o[b.window[0]] = max(0, int(v))
        except (TypeError, ValueError): pass
    return o


def render(store, b: Block, o: dict) -> tuple:
    """(text, mids). A block that raises is a block that says so in the payload rather than one that
    takes the whole check down with it - a broken query must not cost the owner their post."""
    import logging
    try: return b.build(store, o)
    except Exception as e:
        logging.getLogger(__name__).warning(f'assistant block {b.id} failed - {e}')
        return f'(this block could not be read: {str(e)[:120]})', []
```

**The sixteen, each naming the function that already does its work.** No logic moves in this task:
a `view` wrapper delegates to the named function; a `query` block's `sql` is the statement its named
function runs today, lifted verbatim into a module constant so the card can print the same text the
database receives. `heading` is today's section head from `inputs()` with the hardcoded "two days"
replaced by `{days}`, so a widened window does not leave the payload lying about itself.

**CONTEXT blocks** — each renders its own section, in this order, which is the order `inputs()`
renders them today. `heading` is that section's head verbatim, with the hardcoded "two days"
replaced by `{days}`.

| id | label | kind | delegates to | tables | window | on |
|---|---|---|---|---|---|---|
| `knowledge` | Knowledge base | view | `knowledge.block(store, facts)` | kb_fts | — | yes |
| `system_checks` | Configured systems | view | `system_checks(store, ids, inline)` | source, connector | — | yes |
| `threads` | What people said | view | `_people_context(store, days)` | message, route, task | days 2 | yes |
| `ooo` | Out of office | query | `ooo(store)` | message | — | yes |
| `calendar` | Calendar | query | `_calendar(store)` | message | days 2 | yes |
| `arrivals` | What arrived | view | `_recent(store, days)` | message, route, source | days 2 | yes |
| `done_this_week` | Done this week | query | `_done(store, days)` | task, run | days 7 | yes |
| `open_work` | Open work | query | `_open(store)` | task, run, review | cap 20 | yes |
| `already_said` | Already said | query | `_said(store)` | idea | cap 40 | yes |
| `notes` | My notes from last check | query | `_notes_block(store)` | setting | — | yes |

**PRODUCER blocks** — `heading=None`. Each returns candidate dicts, which render under `CANDIDATES:`
exactly as they do today, and each also posts a row of its own. `proposes=True` on all six.

| id | label | kind | delegates to | tables | window / knobs | setting |
|---|---|---|---|---|---|---|
| `waiting_on` | Waiting on them | query | `followups(store, hours, ('followup',))` | message, review | hours 24 | `assistant_followup_hours` |
| `promised` | What I promised | query | `followups(store, hours, ('promise',))` | message, review | hours 24 | `assistant_followup_hours` |
| `meeting_prep` | Meeting prep | query | `prep(store)` | message | — | — |
| `gone_quiet` | Work gone quiet | query | `cold(store, days)` | task, comment, message, run | days 3 | `assistant_cold_days` |
| `connectors` | Connectors mentioned | query | `connect_ideas(store, days, floor)` | message, routing_fact, doc | days 30, floor 3 | — |
| `health` | App health | query | `health_ideas(store)` | source, report_run, connector | — | — |

`waiting_on` and `promised` are the same function with a different `want` tuple, and stay two
entries because `assistant_producers` already lets the owner run one without the other. A producer
absent from `assistant_producers` resolves `default_on: false` — that mapping
(`followup`->`waiting_on`, `promise`->`promised`, `prep`->`meeting_prep`, `cold`->`gone_quiet`) lives
in `defaults()`.

`NOW`, the uptime paragraph and `_verdicts_block` are NOT blocks and are not configurable: the first
two are the clock, and the third is a cross-check over whatever blocks ran.

`waiting_on` and `promised` are the same function with a different `want` tuple, and stay two
entries because `assistant_producers` already lets the owner run one without the other. A producer
absent from `assistant_producers` resolves `default_on: false` — that mapping
(`followup`→`waiting_on`, `promise`→`promised`, `prep`→`meeting_prep`, `cold`→`gone_quiet`) is in
`defaults()`.

`meeting_prep`, `waiting_on`, `promised`, `gone_quiet`, `connectors` and `health` are the six that
both feed the model and post their own rows. Their builders already return candidate dicts, so their
wrapper renders those dicts to text for the payload and hands the dicts back unchanged to `run()` —
one call, not two, so the card's row count and the post's rows can never disagree.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_assistant_blocks.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Write the failing defaults-are-today test**

This is the test the whole plan rests on. Capture today's output BEFORE touching `inputs()`.

```python
# tests/test_assistant_blocks.py, appended
from taskuary import assistant


class DefaultsAreTodayTests(unittest.TestCase):
    """The one test that must never be relaxed: an Assistant report that has configured nothing
    reads exactly what it read before blocks existed."""
    def test_the_default_payload_is_unchanged(self):
        s = A.store()
        cands = assistant.candidates(s, assistant.cfg(s))
        self.assertEqual(assistant.inputs(s, cands), assistant.inputs(s, cands, blocks=None))

    def test_every_default_on_block_appears_in_the_payload(self):
        s = A.store()
        text = assistant.inputs(s, [])
        for b in B.CATALOGUE:
            if not B.defaults(s, b)['on']: continue
            if not b.heading: continue                      # a producer renders under CANDIDATES, not its own head
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=b.id): self.assertIn(head, text, f'{b.id} is on by default and is not in the payload')
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python -m pytest tests/test_assistant_blocks.py::DefaultsAreTodayTests -q`
Expected: FAIL — `inputs() got an unexpected keyword argument 'blocks'`

- [ ] **Step 7: Rewrite `inputs()` as a loop**

In `taskuary/assistant.py`, replace the body of `inputs` (currently lines 867-895). The signature
gains `blocks=None` — a resolved `{block_id: opts}` dict, or `None` for the declared defaults.

```python
def build_inputs(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None, blocks=None) -> tuple:
    """(the text the model sees, {message id: the block that supplied it}). The same text is the
    Reports tab's Preview (facts) and the run record (reports.run_report_source), so what it was
    given is never a guess; the index is how Task 4 attributes a line without asking the model.
    `blocks` is the report's resolved choice; None means the declared defaults, which is what this
    function read when the list was hardcoded.

    Returns the index rather than stashing it on the function: this install runs two Assistant
    reports, and a module-level `last_mids` would have the second one reading the first's sources."""
    from . import assistantblocks as blk
    now, mids = datetime.now(), {}
    chosen = blocks if blocks is not None else {b.id: blk.defaults(store, b) for b in blk.CATALOGUE}
    parts = [f"NOW: {now.strftime('%A %d %B %Y %H:%M')}\n{_uptime_block(store)}",
             f"\n{head}:\n" + ('\n'.join(f"[{c['key']}] {c['facts']}" for c in cands) or '(none)')]
    for b in blk.CATALOGUE:
        o = chosen.get(b.id)
        if not o or not o.get('on'): continue
        if b.id == 'system_checks': o = o | {'source_ids': watch_source_ids, 'inline': watch_sources}
        if b.id == 'candidates_knowledge': o = o | {'facts': ' '.join(str(c.get('facts') or '') for c in cands)[:4000]}
        text, got = blk.render(store, b, o)
        for m in got: mids[int(m)] = b.id
        parts.append('\n\n' + b.heading.format(**o) + ':\n' + text)
    parts.append(_verdicts_block(store, cands, ''))
    return ''.join(parts), mids


def inputs(store, cands: list, head: str = 'CANDIDATES', watch_source_ids=None, watch_sources=None, blocks=None) -> str:
    """The text alone, for every caller that does not need to know which block said what."""
    return build_inputs(store, cands, head, watch_source_ids, watch_sources, blocks)[0]
```

A producer block contributes to `cands`, not to its own section, so the loop splits on `heading`:

```python
    for b in blk.CATALOGUE:
        o = chosen.get(b.id)
        if not o or not o.get('on'): continue
        if b.id == 'system_checks': o = o | {'source_ids': watch_source_ids, 'inline': watch_sources}
        if b.id == 'knowledge': o = o | {'facts': ' '.join(str(c.get('facts') or '') for c in cands)[:4000]}
        out, got = blk.render(store, b, o)
        for m in got: mids[int(m)] = b.id
        if b.heading: parts.append('

' + b.heading.format(**o) + ':
' + out)
```

`knowledge` and `system_checks` render where `inputs()` renders them today, which is why they sit
first and second in the context table - the loop walks the catalogue in order and the order IS the
payload.

Keep `_verdicts_block` outside the loop: it is not a block, it is a cross-check over the blocks that
ran. Extract today's `uptime` paragraph into `_uptime_block(store)` unchanged.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_assistant_blocks.py tests/test_assistant_ideas.py tests/test_assistant_reactions.py -q`
Expected: PASS. If `test_the_default_payload_is_unchanged` fails, the loop reordered or reworded a
section — fix the registry, never the test.

- [ ] **Step 9: Run the whole suite**

Run: `python -m pytest -q`
Expected: all pass. `inputs()` is called by `facts()`, `think()` and the Reports preview.

- [ ] **Step 10: Commit**

```bash
git status --porcelain
git add taskuary/assistantblocks.py taskuary/assistant.py tests/test_assistant_blocks.py
git commit -m "feat: what the assistant reads is fourteen declarations, not nine hardcoded calls"
```

---

### Task 2: Per-report configuration and the cost endpoint

The report's `ConfigJson` chooses blocks; the server can price them. No UI yet.

**Files:**
- Modify: `taskuary/assistantblocks.py` (add `resolve`, `weigh`)
- Modify: `taskuary/assistant.py` (`facts`, `run` take `blocks`)
- Modify: `taskuary/reports.py:513-521` (`run_assistant`), `taskuary/reports.py:1396-1406` (dispatch)
- Modify: `taskuary/server.py` (one new route)
- Test: `tests/test_assistant_blocks.py`

**Interfaces:**
- Consumes: `Block`, `CATALOGUE`, `by_id`, `defaults`, `render` from Task 1.
- Produces:
  - `assistantblocks.resolve(store, cfg: dict) -> dict` — `{block_id: opts}` for a report config.
  - `assistantblocks.weigh(store, chosen: dict) -> list[dict]` — per block:
    `{'id', 'label', 'kind', 'tables', 'sql', 'on', 'window', 'rows', 'tokens'}`.
  - `GET /api/assistant/blocks?source_id=<id>` -> `{'data': [...], 'total_tokens': int, 'runs_per_day': int, 'cost': float | None}`.

- [ ] **Step 1: Write the failing test**

```python
class ResolveTests(unittest.TestCase):
    def test_no_config_is_the_declared_defaults(self):
        s = A.store()
        self.assertEqual(B.resolve(s, {'type': 'assistant'}),
                         {b.id: B.defaults(s, b) for b in B.CATALOGUE})

    def test_a_report_override_beats_the_setting_which_beats_the_declaration(self):
        s = A.store()
        self.assertEqual(B.resolve(s, {'type': 'assistant'})['gone_quiet']['days'], 3)
        s.set_setting('assistant_cold_days', '9', 'test')
        self.assertEqual(B.resolve(s, {'type': 'assistant'})['gone_quiet']['days'], 9)
        self.assertEqual(B.resolve(s, {'type': 'assistant', 'blocks': {'gone_quiet': {'days': 21}}})['gone_quiet']['days'], 21)

    def test_watch_sources_with_no_blocks_key_reads_no_taskuary_block(self):
        """Today an Assistant report with a source of its own is systems-only. A report saved before
        blocks existed must not silently start reading the owner's whole inbox."""
        chosen = B.resolve(A.store(), {'type': 'assistant', 'watch_source_ids': [4]})
        self.assertFalse(any(o['on'] for bid, o in chosen.items() if bid != 'system_checks'))

    def test_ticking_one_block_makes_it_no_longer_systems_only(self):
        chosen = B.resolve(A.store(), {'type': 'assistant', 'watch_source_ids': [4], 'blocks': {'open_work': {'on': True}}})
        self.assertTrue(chosen['open_work']['on'])
        self.assertTrue(B.reads_taskuary(chosen))

    def test_weigh_prices_each_block(self):
        rows = B.weigh(A.store(), B.resolve(A.store(), {'type': 'assistant'}))
        one = next(r for r in rows if r['id'] == 'gone_quiet')
        self.assertEqual(one['tables'], ['task', 'comment', 'message', 'run'])
        self.assertTrue(one['sql'])                       # a query block shows its statement
        self.assertIsInstance(one['tokens'], int)
        self.assertIsNone(next(r for r in rows if r['id'] == 'threads')['sql'])   # a view shows none
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_assistant_blocks.py::ResolveTests -q`
Expected: FAIL — `module 'taskuary.assistantblocks' has no attribute 'resolve'`

- [ ] **Step 3: Implement `resolve`, `reads_taskuary` and `weigh`**

```python
def resolve(store, cfg: dict) -> dict:
    """{block_id: opts} for one report. Declaration -> global setting -> the report's override, in
    that order. A report with sources of its own and no `blocks` key reads NO Taskuary block: that
    is what systems_only meant before this existed, and a saved monitor must not wake up reading the
    owner's inbox. Tick one block and it reads that block AND its sources - the either/or was an
    accident of the old flag, not a decision."""
    over = cfg.get('blocks') if isinstance(cfg.get('blocks'), dict) else None
    isolated = bool(cfg.get('watch_source_ids') or cfg.get('watch_sources'))
    out = {}
    for b in CATALOGUE:
        o = defaults(store, b)
        if isolated and over is None and b.id != 'system_checks': o['on'] = False
        if over is not None and b.id in over:
            for k, v in over[b.id].items(): o[k] = bool(v) if k == 'on' else max(0, int(v))
        elif over is not None and b.id != 'system_checks': o['on'] = False
        out[b.id] = o
    return out


def reads_taskuary(chosen: dict) -> bool:
    """The Assistant has Taskuary as a source when any of its blocks is on. `systems_only` is the
    absence of that, derived here rather than stored anywhere."""
    return any(o.get('on') for bid, o in chosen.items() if bid != 'system_checks')


def weigh(store, chosen: dict) -> list:
    """What the card shows: each block, whether it is on, its rows, and the tokens its RENDERED TEXT
    costs - a block's price is its words, not its row count."""
    out = []
    for b in CATALOGUE:
        o = chosen.get(b.id) or defaults(store, b)
        text, mids = render(store, b, o) if o.get('on') else ('', [])
        out.append({'id': b.id, 'label': b.label, 'kind': b.kind, 'tables': list(b.tables),
                    'sql': b.sql, 'on': bool(o.get('on')), 'proposes': b.proposes,
                    'window': ({'unit': b.window[0], 'value': o.get(b.window[0]), 'label': b.window[2]} if b.window else None),
                    'rows': text.count('\n') + 1 if text and not text.startswith('(') else 0,
                    'tokens': len(text) // 4})
    return out
```

`over is not None and b.id not in over -> off` is deliberate: once the owner has saved a block
choice, the saved choice is the whole truth. A block we ship later does not switch itself on in a
report the owner has already configured.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_assistant_blocks.py::ResolveTests -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Thread `blocks` through the callers**

`assistant.facts(store, watch_source_ids=None, watch_sources=None, systems_only=False, blocks=None)`
and `assistant.run(..., blocks=None)` pass it to `inputs`. In `reports.run_assistant`:

```python
def run_assistant(cfg):
    from .assistant import facts
    from . import assistantblocks as blk
    chosen = blk.resolve(cfg['store'], cfg)
    return 'what the assistant would read right now', facts(
        cfg['store'], cfg.get('watch_source_ids'), cfg.get('watch_sources'),
        systems_only=not blk.reads_taskuary(chosen), blocks=chosen)
```

And in the dispatch at `reports.py:1396`, replace `systems_only=bool(watched_ids or watched_sources)`
with the same derivation:

```python
        chosen = blk.resolve(store, cfg)
        out = assistant.run(cfg['store'] if cfg.get('store') else store, report_llm(store, cfg, llm),
                            force=True, instruction=cfg.get('ai_prompt'),
                            watch_source_ids=watched_ids, watch_sources=watched_sources,
                            systems_only=not blk.reads_taskuary(chosen), blocks=chosen,
                            report_id=src.get('SourceId'), report_title=title,
                            always_post=<unchanged - the existing expression on this line>)
```

- [ ] **Step 6: Add the endpoint**

In `taskuary/server.py`, beside the connector catalogue route (`/api/connectors/catalogue`,
~line 6741):

```python
@app.get('/api/assistant/blocks')
def assistant_blocks(source_id: int = None):
    """What an Assistant report reads, priced. `source_id` is the report whose choice to resolve;
    absent means the declared defaults, which is what a new report starts from."""
    from . import assistantblocks as blk
    cfg = {}
    if source_id:
        src = store.get_source(int(source_id))
        if src: cfg = json.loads(src.get('ConfigJson') or '{}')
    rows = blk.weigh(store, blk.resolve(store, cfg))
    per_day = _runs_per_day(cfg)
    return {'data': rows, 'total_tokens': sum(r['tokens'] for r in rows if r['on']),
            'runs_per_day': per_day, 'cost': None}
```

`cost` stays `None` in this task. The money line appears only when the brain's price is known, and
that lookup is Task 3's, so the field exists and the card renders tokens alone until it is filled.

- [ ] **Step 7: Write the card-cannot-lie test**

The spec asks for it by name. The panel and the Preview must be built from one resolution, or the
card will claim a read the payload never made — the exact class of bug this feature exists to end.

```python
class CardMatchesPayloadTests(unittest.TestCase):
    def test_the_card_names_the_blocks_the_payload_contains(self):
        s = A.store()
        cfg = {'type': 'assistant', 'blocks': {'open_work': {'on': True}, 'gone_quiet': {'on': True, 'days': 14}}}
        chosen = B.resolve(s, cfg)
        payload = assistant.inputs(s, [], blocks=chosen)
        for row in B.weigh(s, chosen):
            head = B.by_id(row['id']).heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=row['id']):
                self.assertEqual(row['on'], head in payload, f"the card says {row['id']} is {'on' if row['on'] else 'off'} and the payload disagrees")
```

- [ ] **Step 8: Run it to verify it passes**

Run: `python -m pytest tests/test_assistant_blocks.py::CardMatchesPayloadTests -q`
Expected: PASS. A failure here means `weigh` and `inputs` are resolving separately — make both take
the already-resolved `chosen` dict rather than resolving it themselves.

- [ ] **Step 9: Run the suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git status --porcelain
git add taskuary/assistantblocks.py taskuary/assistant.py taskuary/reports.py taskuary/server.py tests/test_assistant_blocks.py
git commit -m "feat: an Assistant report chooses which of Taskuary's tables it reads"
```

---

### Task 3: The "Reads Taskuary" card

**Files:**
- Modify: `website/src/ReportsView.jsx:1095` (inside the `isAssistant` block of the Pipeline step)
- Modify: `website/src/ReportsView.jsx:609-612` (`SavedReportSummary`'s `reads` line)
- Test: `website/test/assistantBlocks.test.mjs`

**Interfaces:**
- Consumes: `GET /api/assistant/blocks?source_id=` from Task 2.
- Produces: `cfg.blocks` on save — `{[id]: {on: bool, days?: int, cap?: int, floor?: int}}`.

- [ ] **Step 1: Write the failing test**

`website/test/assistantBlocks.test.mjs`, following the pattern in `website/test/docs.test.mjs`
(pure functions imported from the module, no DOM):

```javascript
import { test } from "node:test";
import assert from "node:assert";
import { blocksPatch, readsLine } from "../src/assistantBlocks.js";

test("ticking a block writes only that block's override", () => {
  assert.deepEqual(blocksPatch({}, "open_work", { on: true }), { open_work: { on: true } });
});

test("a window change keeps the tick", () => {
  assert.deepEqual(blocksPatch({ threads: { on: true } }, "threads", { days: 7 }),
                   { threads: { on: true, days: 7 } });
});

test("the summary line names the blocks, not a fixed sentence", () => {
  assert.equal(readsLine([{ id: "threads", label: "What people said", on: true, window: { value: 7, unit: "days" } },
                          { id: "open_work", label: "Open work", on: true, window: null },
                          { id: "knowledge", label: "Knowledge base", on: false, window: null }]),
               "Taskuary — What people said (7d), Open work");
});

test("no block on reads its own sources only", () => {
  assert.equal(readsLine([{ id: "threads", label: "What people said", on: false, window: null }]), "");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd website && npm exec --yes node@22 -- --test test/assistantBlocks.test.mjs`
Expected: FAIL — cannot find `../src/assistantBlocks.js`

- [ ] **Step 3: Write the pure helpers**

`website/src/assistantBlocks.js` — the logic the card uses, kept out of the JSX so it is testable
under node (the repo's rule: `esbuild` syntax-checks JSX that pytest never loads, and node cannot
import it).

```javascript
// The Assistant report's block choice, as data. The card is JSX; these are the two decisions in it,
// so they can be tested under `node --test` without a DOM.
export const blocksPatch = (blocks, id, patch) => ({ ...blocks, [id]: { ...(blocks?.[id] || {}), ...patch } });

export const readsLine = (rows) => {
  const on = (rows || []).filter((r) => r.on && r.id !== "system_checks");
  if (!on.length) return "";
  return "Taskuary — " + on.map((r) => r.label + (r.window ? ` (${r.window.value}d)` : "")).join(", ");
};
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd website && npm exec --yes node@22 -- --test test/assistantBlocks.test.mjs`
Expected: PASS, 4 tests.

- [ ] **Step 5: Write the panel**

In `ReportsView.jsx`, inside the `isAssistant` block, **above** "Systems and data views to check":

```jsx
{isAssistant && (
  <Box sx={{ ...card, p: 1.5, mb: 1.5, maxWidth: 720, bgcolor: PANEL2 }}>
    <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13, mb: 0.4 }}>Reads Taskuary</Typography>
    <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>
      Taskuary's own tables are this check's source. Tick what it should read and how far back; every
      line it posts says which of these it came from. Leave them all off and it reads only the systems below.
    </Typography>
    {blockRows.map((r) => (
      <Box key={r.id} sx={{ display: "flex", alignItems: "center", gap: 1, py: 0.35 }}>
        <Checkbox size="small" checked={r.on} sx={{ p: 0.3 }}
          onChange={(e) => setCfg((c) => ({ ...c, blocks: blocksPatch(c.blocks, r.id, { on: e.target.checked }) }))} />
        <Typography sx={{ fontSize: 12.5, color: INK, flex: 1, minWidth: 0 }}>{r.label}</Typography>
        {r.window && <TextField size="small" type="number" value={r.window.value} sx={{ width: 74 }}
          inputProps={{ "aria-label": `${r.label} — ${r.window.label}` }}
          onChange={(e) => setCfg((c) => ({ ...c, blocks: blocksPatch(c.blocks, r.id, { [r.window.unit]: e.target.value }) }))} />}
        <Typography sx={{ fontSize: 11.5, color: DIM, width: 78, textAlign: "right", fontFamily: MONO }}>
          {r.on ? `${r.rows} rows` : "off"}
        </Typography>
        <Typography sx={{ fontSize: 11.5, color: DIM, width: 56, textAlign: "right", fontFamily: MONO }}>
          {r.on ? `~${(r.tokens / 1000).toFixed(1)}k` : ""}
        </Typography>
        <IconButton size="small" onClick={() => setOpenBlock(openBlock === r.id ? null : r.id)}
          aria-label={`what ${r.label} reads`}><InfoOutlinedIcon sx={{ fontSize: 15 }} /></IconButton>
      </Box>
    ))}
    {openBlock && <BlockDetail row={blockRows.find((r) => r.id === openBlock)} />}
    <Divider sx={{ my: 0.8 }} />
    <Typography sx={{ fontSize: 11.5, color: DIM, fontFamily: MONO }}>
      ~{(totalTokens / 1000).toFixed(1)}k tokens per run · {runsPerDay} runs a day
      {cost != null ? ` · ~$${cost.toFixed(2)} a run` : ""}
    </Typography>
  </Box>
)}
```

`BlockDetail` shows the tables always, and the SQL for a `query` block:

```jsx
const BlockDetail = ({ row }) => !row ? null : (
  <Box sx={{ ...card, bgcolor: "#fff", p: 1.25, my: 0.6 }}>
    <Typography sx={{ fontSize: 11.5, color: DIM, fontFamily: MONO, mb: 0.5 }}>
      reads: {row.tables.join(", ")}
    </Typography>
    {row.kind === "query"
      ? <Box component="pre" sx={{ m: 0, fontSize: 11, fontFamily: MONO, color: INK, whiteSpace: "pre-wrap" }}>{row.sql}</Box>
      : <Typography sx={{ fontSize: 12, color: DIM }}>
          Composed in code — more than one query, plus the lookups this block folds in. It cannot be shown as one statement.
        </Typography>}
  </Box>
);
```

Fetch `blockRows` from `/api/assistant/blocks?source_id=` on mount and after each change, debounced
300ms so a held arrow key does not run sixteen COUNT queries per keystroke.

- [ ] **Step 6: Update the saved summary**

`SavedReportSummary`'s `reads` (line 609) currently hardcodes "Assistant context — messages, tasks,
calendar, and its configured checks". Replace with the blocks actually on:

```jsx
  const reads = c.type === "assistant"
    ? [readsLine(blockRowsOf(c)), watched ? `${watched} configured data source${watched === 1 ? "" : "s"}` : ""]
        .filter(Boolean).join(" and ") || "nothing yet — tick a block or add a source"
    : labels.length > 1 ? /* unchanged - the existing non-assistant branches */ ;
```

`SavedReportSummary` renders in a list and must not fire a request per row, so it cannot use the
priced rows from the endpoint. Add a third pure helper to `assistantBlocks.js` — a static mirror of
the catalogue's ids, labels and defaults, enough to say what a saved config reads without asking the
server:

```javascript
// id -> label and default window. A MIRROR of taskuary/assistantblocks.py, kept honest by
// test_assistant_blocks.py::test_the_page_and_the_server_name_the_same_blocks - the settings schema
// learned this lesson already: two lists of the same thing drift unless one test compares them.
export const BLOCKS = [
  { id: "threads", label: "What people said", days: 2 },
  { id: "arrivals", label: "What arrived", days: 2 },
  // ...and the other fourteen, ids and labels copied from the table in Task 1, same order.
];

export const blockRowsOf = (cfg) => {
  const over = cfg?.blocks && typeof cfg.blocks === "object" ? cfg.blocks : null;
  const isolated = !!(cfg?.watch_source_ids?.length || cfg?.watch_sources?.length);
  return BLOCKS.map((b) => {
    const o = over?.[b.id];
    const on = o ? !!o.on : over ? false : !isolated;
    return { id: b.id, label: b.label, on, window: b.days ? { value: o?.days ?? b.days, unit: "days" } : null };
  });
};
```

The drift guard is a Python test, because Python owns the catalogue:

```python
def test_the_page_and_the_server_name_the_same_blocks(self):
    """Two lists of the same thing drift. The card's summary cannot fetch per row, so it mirrors the
    catalogue - and this is what keeps the mirror true."""
    import re, pathlib
    js = pathlib.Path('website/src/assistantBlocks.js').read_text(encoding='utf-8')
    self.assertEqual(re.findall(r'\{ id: "([a-z_]+)"', js), [b.id for b in B.CATALOGUE])
```

- [ ] **Step 7: Build the bundle and gate it**

Run, from `website/`:
```bash
npm exec --yes node@22 -- --test test/assistantBlocks.test.mjs
npm run lint:undef
npm run build
```
Expected: tests pass, no undefined identifiers, the bundle builds. Commit the rebuilt
`taskuary/web/` assets with the source — a rode-along that lands half is how the CLI installer
broke for two days.

- [ ] **Step 8: Commit**

```bash
git status --porcelain
git add website/src/assistantBlocks.js website/src/ReportsView.jsx website/test/assistantBlocks.test.mjs taskuary/web
git commit -m "feat: the Assistant report card shows the Taskuary tables it reads, and what they cost"
```

---

### Task 4: Every line names its block

**Files:**
- Modify: `taskuary/assistant.py` (`run`, `reviewed`, `_footer`, `_public`)
- Modify: `website/src/` — the component that renders an idea's `why` line
- Test: `tests/test_assistant_blocks.py`

**Interfaces:**
- Consumes: `build_inputs(...) -> (text, mids)` from Task 1, `resolve` from Task 2.
- Produces: `ActionJson.source` — `{'block': str, 'window': str, 'rows': list[int]}`, and a
  `reviewed` dict keyed by block id instead of hand-counted fields.

- [ ] **Step 1: Write the failing test**

```python
class SourceTests(unittest.TestCase):
    def test_a_deterministic_candidate_carries_its_own_block(self):
        s = A.store()
        for i in range(3):
            s.add_message({'ExternalId': f'adp:{i}', 'Channel': 'email', 'SourceName': 'inbox',
                           'Subject': 'ADP payroll register ready', 'FromName': 'ADP', 'FromEmail': 'hr@adp.com',
                           'SentAt': '2026-09-17 09:00:00', 'BodyText': '.', 'Status': 'routed'})
        idea = assistant.connect_ideas(s)[0]
        self.assertEqual(idea['source']['block'], 'connectors')

    def test_a_model_line_resolves_through_the_mid_it_returned(self):
        self.assertEqual(assistant.source_of({'key': 'idea:x', 'mid': 42}, {42: 'threads'}, {'threads': {'days': 7}}),
                         {'block': 'threads', 'window': '7d', 'rows': [42]})

    def test_a_model_line_without_a_mid_carries_no_source(self):
        self.assertIsNone(assistant.source_of({'key': 'idea:x', 'mid': None}, {42: 'threads'}, {}))

    def test_an_unknown_mid_carries_no_source(self):
        """It never guesses: a mid no block contributed means the model named something it was not given."""
        self.assertIsNone(assistant.source_of({'key': 'idea:x', 'mid': 99}, {42: 'threads'}, {}))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_assistant_blocks.py::SourceTests -q`
Expected: FAIL — `module 'taskuary.assistant' has no attribute 'source_of'`

- [ ] **Step 3: Implement `source_of` and attribute the deterministic blocks**

```python
def source_of(line: dict, mids: dict, chosen: dict) -> dict | None:
    """Which block put this line in front of the model. LOOKED UP, never asked for: the model returns
    the message id it is about, and the id says which block supplied it. No mid, or a mid no block
    contributed, means no source line - a wrong provenance is worse than none."""
    if line.get('block'): bid = line['block']                      # a deterministic candidate knows
    else:
        mid = line.get('mid')
        bid = mids.get(int(mid)) if mid else None
    if not bid: return None
    o = chosen.get(bid) or {}
    win = f"{o['days']}d" if o.get('days') else f"{o['hours']}h" if o.get('hours') else ''
    return {'block': bid, 'window': win, 'rows': [int(line['mid'])] if line.get('mid') else []}
```

Every `proposes` block sets `'block': <its id>` on the candidates it returns — `followups`, `cold`,
`prep`, `connect_ideas`, `health_ideas`. In `run()`, after `say` is final:

```python
    # `read` is already built by run() via build_inputs; keep its mids rather than rebuilding
    say = [s | {'source': source_of(s, mids, chosen)} for s in say]
```

and `upsert_idea` carries it into `ActionJson.source`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_assistant_blocks.py::SourceTests -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Generate the receipt**

Replace `reviewed()`'s hand-counted `recent`/`week`/`open`/`said` keys with `blocks`, and `_footer()`
with a generated list. Old posts carry the old shape, so the renderer keeps both paths:

```python
def _footer(r: dict) -> str:
    if r.get('scope') == 'sources': <unchanged - the existing two lines>
    if 'blocks' in r:
        rows = ', '.join(f"{b['label'].lower()} ({b['window']}) {b['rows']}" if b['window'] else f"{b['label'].lower()} {b['rows']}"
                         for b in r['blocks'] if b['on'])
        return f"Reviewed: {rows or 'no blocks'}" + ('' if r['model'] else " - no model: the facts in the hub's own words")
    return <unchanged - today's hardcoded sentence, kept for posts written before blocks existed>
```

- [ ] **Step 6: Render the source under each line**

In the component that renders an idea's `why`, add the source line when `idea.source` is present:

```jsx
{i.source && (
  <Typography sx={{ fontSize: 11, color: DIM, fontFamily: MONO }}>
    from: {i.source.block}{i.source.window ? ` (${i.source.window})` : ""}
    {i.source.rows?.length ? ` → ${i.source.rows.length} message${i.source.rows.length === 1 ? "" : "s"}` : ""}
  </Typography>
)}
```

Clicking it opens the first row's message. An idea with no `source` renders nothing extra.

- [ ] **Step 7: Run everything**

```bash
python -m pytest -q
cd website && npm exec --yes node@22 -- --test "test/**/*.test.mjs" && npm run lint:undef && npm run build
```
Expected: all pass, bundle builds.

- [ ] **Step 8: Commit**

```bash
git status --porcelain
git add taskuary/assistant.py tests/test_assistant_blocks.py website/src taskuary/web
git commit -m "feat: every line the assistant posts names the query behind it"
```

---

## After the four tasks

- Run the whole suite from the repo root once more before pushing; "no tests ran" is a failure.
- Update the spec's Order of work with the landed shas, as `2026-09-18-assistant-runs-the-app-design.md` does.
- The spec's §"Where the configuration lives" says a later block arrives `default_on: false`. Task 2
  makes that stronger for a configured report — a saved `blocks` key is the whole truth. Amend the
  spec to say so rather than leaving the two descriptions side by side.

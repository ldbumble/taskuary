# Onboarding Walk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the eight-row wizard full of inline forms into five derived rows that link to the pages that own the work and vanish when done, and turn the assistant's "Set up Taskuary" chip into a scripted, no-AI, stop-per-turn walk of the whole app.

**Architecture:** `taskuary/setup.py` keeps deriving and drops to five steps, each carrying a `goto` deep-link. A new `taskuary/walk.py` holds a static ordered `STOPS` list and fills live facts from `setup.state()` so the two surfaces can never disagree. The assistant renders one `WalkCard` per stop; a typed question is an ordinary assistant turn and `concierge.fallback()` already covers the no-model case, so nothing in the walk path calls an LLM.

**Tech Stack:** Python 3.10 / FastAPI / SQLite / pytest (unittest style); React + MUI, Node 22 `node --test` over JSX source text.

**Spec:** `docs/superpowers/specs/2026-09-17-onboarding-walk-design.md`

## Global Constraints

- **Style:** match the surrounding files — dense code, comments that explain *why* not *how*, lines under ~160 chars. Do not run an autoformatter.
- **Derived, not stored.** `setup.state()` reads real state. `setup_seen_models` and `setup_walk_at` are the only two stored values this plan adds, and each gets a comment saying why it must be.
- **Step keys, exactly:** `owner`, `ai`, `models`, `inbound`, `sync`. In that order.
- **`goto` shape, everywhere:** `{'tab': '<TaskHubPage tab name>', 'hash': '<hash without #>'}`. `hash` may be `''`. Tab names are the ones `TaskHubPage.go()` accepts: `Assistant`, `Board`, `Tasks`, `Review`, `Reports`, `Connections`, `Docs`, `Settings`, `Hub`.
- **Three deep-link hashes, exactly:** `cli-agents`, `settings=config&group=Triage%20%26%20agents`, `owner`.
- **No LLM in the walk.** `taskuary/walk.py` must not import `llm`, `compose`, or `concierge`.
- **Windows:** run pytest from the repo root. `heredoc` eats backslashes in this environment — patch files by line index or use the Write tool.
- **Never push without the full suite.** `python -m pytest` from the repo root, all of it, before the final commit.

---

### Task 1: Five derived steps with deep-links

**Files:**
- Modify: `taskuary/setup.py`
- Test: `tests/test_setup.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `setup.MESSAGING` (tuple of channel type strings); `setup.state(store) -> {'steps': list, 'done': int, 'total': int, 'complete': bool, 'dismissed': bool}`. Each step is `{'key', 'title', 'why', 'done', 'detail', 'goto'}` where `goto` is `{'tab': str, 'hash': str}`. Keys `ready`, `guide_done`, `guide_total`, `optional`, `recommended`, `where` no longer exist.

- [ ] **Step 1: Write the failing tests**

Replace the whole `WhatCountsAsSetUpTests` class in `tests/test_setup.py` with the below, and delete `test_personalization_is_recommended_after_the_three_working_gates`, `test_soul_keeps_its_full_default_until_the_owner_personalizes_it`, `test_generated_personalization_is_derived_from_the_documents`, `test_manual_personalization_also_counts`, `test_the_shipped_default_agent_does_not_tick_its_own_box`, `test_three_of_three_is_ready_and_the_rest_stay_optional` and `test_recommended_steps_complete_without_a_coding_agent`. Keep `test_an_accidentally_blank_saved_soul_is_repaired_from_the_full_default` — it is about `SQLiteStore`, not the checklist.

```python
class WhatCountsAsSetUpTests(unittest.TestCase):
    def test_a_fresh_install_has_nothing_done_and_says_which_five(self):
        st = setup.state(_fresh())
        self.assertEqual((st['done'], st['total'], st['complete']), (0, 5, False))
        self.assertEqual([x['key'] for x in st['steps']],
                         ['owner', 'ai', 'models', 'inbound', 'sync'])
        # every step explains ITSELF - "go to Connections" is navigation, not a reason
        for x in st['steps']:
            self.assertGreater(len(x['why']), 40, f"{x['key']} has no reason to exist")

    def test_there_is_no_second_tier_left_to_count(self):
        """Eight rows in two tiers became five in one. A leftover guide_* counter would be a second
        number nobody updates, which is how the headline and the pill disagreed before."""
        st = setup.state(_fresh())
        for gone in ('ready', 'guide_done', 'guide_total'):
            self.assertNotIn(gone, st)
        for x in st['steps']:
            self.assertNotIn('optional', x)
            self.assertNotIn('where', x)

    def test_every_step_says_where_it_goes(self):
        """A row that points nowhere is the old wizard's inline form with the form removed."""
        tabs = {'Assistant', 'Board', 'Tasks', 'Review', 'Reports', 'Connections', 'Docs', 'Settings', 'Hub'}
        for x in setup.state(_fresh())['steps']:
            self.assertIn(x['goto']['tab'], tabs, x['key'])
            self.assertIsInstance(x['goto']['hash'], str)
        by = {x['key']: x['goto'] for x in setup.state(_fresh())['steps']}
        self.assertEqual(by['owner'], {'tab': 'Docs', 'hash': 'owner'})
        self.assertEqual(by['ai'], {'tab': 'Connections', 'hash': 'cli-agents'})
        self.assertEqual(by['models'], {'tab': 'Settings', 'hash': 'settings=config&group=Triage%20%26%20agents'})

    def test_the_owner_step_is_not_fooled_by_the_fallback_name(self):
        """store.owner() answers the literal string "the owner" when nothing is set, so a naive
        truthiness check reads a fresh install as done and never sends anybody to the one field
        that signs their mail."""
        s = _fresh()
        self.assertFalse(_step(setup.state(s), 'owner')['done'])
        s.set_setting('owner_name', 'Dana Example', 't')
        self.assertTrue(_step(setup.state(s), 'owner')['done'])
        self.assertEqual(_step(setup.state(s), 'owner')['detail'], 'Dana Example')

    def test_an_ai_card_with_no_key_is_not_a_brain(self):
        s = _fresh()
        _with_ai(s, secret=None, active=1)
        self.assertFalse(_step(setup.state(s), 'ai')['done'])
        _with_ai(s, secret='sk-real')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_local_model_counts_without_a_key(self):
        """Ollama carries no secret, so "has a key" is the wrong test for it - and getting this
        wrong would tell somebody running a local model that they have no AI."""
        s = _fresh()
        cid = s.get_connector_by_type('ollama')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'ai')['done'])

    def test_a_connector_with_no_source_behind_it_is_only_half_connected(self):
        """It looks done on the Connections tab and delivers nothing. That is exactly the state a
        checklist exists to catch."""
        s = _fresh()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])
        s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertTrue(_step(setup.state(s), 'inbound')['done'])

    def test_a_tracker_alone_is_not_somewhere_work_arrives(self):
        """GitHub brings issues in and it is a real source, but an install with GitHub and no
        mailbox has a Timeline with no mail in it - and the row said it was done (2026-09-17)."""
        s = _fresh()
        cid = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'ghp_x', 'Active': 1}, 't')
        s.save_source({'Channel': 'github', 'Address': 'ours/repo', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])
        _with_mailbox(s)
        self.assertTrue(_step(setup.state(s), 'inbound')['done'])

    def test_a_report_only_connection_is_not_a_funnel(self):
        """AWS brings no work in. Counting it would call an install ready that can never show a
        single message."""
        s = _fresh()
        cid = s.get_connector_by_type('aws')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'k', 'Active': 1}, 't')
        s.save_source({'Channel': 'aws', 'Address': 's3://b', 'ConnectorId': cid, 'Active': 1}, 't')
        self.assertFalse(_step(setup.state(s), 'inbound')['done'])

    def test_the_seeded_reports_are_not_your_first_messages(self):
        """The Morning digest and Automation ideas file their own rows on first start, so
        "something is in the timeline" was true before a single message had ever been read."""
        s = _fresh()
        s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'Subject': 'Morning digest',
                       'BodyText': 'x', 'Status': 'report'})
        self.assertFalse(_step(setup.state(s), 'sync')['done'])
        s.add_message({'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'a real one',
                       'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        self.assertTrue(_step(setup.state(s), 'sync')['done'])

    def test_no_step_shows_a_number_it_cannot_make_true(self):
        """The sync step samples the feed, so any count it printed would be the sample size:
        "2 read" on an install holding thousands."""
        s = _fresh()
        for i in range(9):
            s.add_message({'ExternalId': f'm{i}', 'Channel': 'email', 'Subject': 's',
                           'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        self.assertEqual(_step(setup.state(s), 'sync')['detail'], 'messages are arriving')

    def test_five_of_five_is_complete_and_the_counter_is_finished(self):
        s = _fresh()
        s.set_setting('owner_name', 'Dana Example', 't')
        s.set_setting(setup.SEEN_MODELS, '1', 't')
        _with_ai(s); _with_mailbox(s)
        s.add_message({'ExternalId': 'm1', 'Channel': 'email', 'Subject': 'hello',
                       'FromEmail': 'a@b.com', 'BodyText': 'x', 'Status': 'filed'})
        st = setup.state(s)
        self.assertEqual((st['done'], st['total'], st['complete']), (5, 5, True))

    def test_it_un_does_itself_when_a_connection_is_removed(self):
        """The whole reason it is derived rather than stored."""
        s = _fresh()
        _with_ai(s)
        self.assertTrue(_step(setup.state(s), 'ai')['done'])
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 0}, 't')
        self.assertFalse(_step(setup.state(s), 'ai')['done'])
```

Also update `test_the_endpoint_answers_the_same_shape_the_panel_reads` (currently `tests/test_setup.py:275-279`):

```python
    def test_the_endpoint_answers_the_same_shape_the_panel_reads(self):
        d = c.get('/api/setup').json()
        for k in ('steps', 'done', 'total', 'complete', 'dismissed'):
            self.assertIn(k, d)
        for x in d['steps']:
            for k in ('key', 'title', 'why', 'done', 'goto'):
                self.assertIn(k, x)
```

And `test_dismissing_changes_nothing_about_what_is_actually_done` (`tests/test_setup.py:270`) — `ready` is gone:

```python
        self.assertEqual((before['done'], before['complete']), (after['done'], after['complete']))
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_setup.py -x -q
```

Expected: FAIL — `AssertionError: 3 != 5` on the first test, and `KeyError`/`AttributeError: module 'taskuary.setup' has no attribute 'SEEN_MODELS'`.

- [ ] **Step 3: Rewrite the step model**

In `taskuary/setup.py`, after the `INBOUND` tuple (line 18-21), add:

```python
# Where work ARRIVES for a person, as opposed to where it is tracked. A tracker is a real source and
# stays in INBOUND for everything that reads it - but an install with GitHub and no mailbox has a
# Timeline with no mail in it, and the row said it was done. So the checklist asks for one of these.
MESSAGING = ('outlook', 'teams', 'slack', 'gmail', 'imap', 'telegram', 'whatsapp', 'imessage', 'discord')

# The ONE stored step, and the only exception to this module's rule. A fresh install already ships
# working brain and model defaults, so there is nothing to derive: "the defaults are fine" and "I
# never looked" are the same state. Opening the page is what the row asks for, so opening the page
# is what it records.
SEEN_MODELS = 'setup_seen_models'
```

Change `_inbound` to take the types it should count (`taskuary/setup.py:41`):

```python
def _inbound(store, types=INBOUND) -> list:
    """Connections that bring work in AND have a source to poll. A card with credentials and no
    mailbox behind it is half-connected - it looks done on the Connections tab and delivers
    nothing, which is exactly the state a checklist exists to catch."""
    live = {s['Channel'] for s in store.list_sources() if s.get('Active')}
    from .channels import CH2SRC
    out = []
    for c in store.list_connectors():
        if c['Type'] not in types or not c['Active']: continue
        if CH2SRC.get(c['Type'], c['Type']) in live: out.append(c['Name'] or c['Type'])
    return out
```

Replace the body of `state()` from `who = ...` to the end of the function with:

```python
    who = (store.owner() or {}).get('owner') or ''
    ai, inbound = _ai(store), _inbound(store, MESSAGING)
    seen_models = str(store.get_settings().get(SEEN_MODELS) or '') == '1'
    # the four seeded reports (Morning digest, End of day checkup, Automation ideas, the Assistant)
    # file their own rows on first start, so "something is in the timeline" was true before a single
    # message had ever been read
    inbox = [m for m in store.feed(limit=5, days=3650) if m.get('Channel') != 'report']
    steps = [
        {'key': 'owner', 'title': 'Say who you are',
         'why': 'Your name signs every reply, and the operator documents fill it in wherever they '
                'say {{owner}}. Without it the drafts go out addressed by nobody.',
         # owner() answers 'owner', not 'name', and falls back to the literal string "the owner"
         # when nothing is set - so both have to be checked or this step reads done on a fresh
         # install and the checklist sends nobody to the one field that signs their mail
         'done': bool(who) and who != 'the owner',
         'detail': who if who != 'the owner' else '',
         'goto': {'tab': 'Docs', 'hash': 'owner'}},
        {'key': 'ai', 'title': 'Set up an AI',
         'why': 'This is what reads each message and decides whether it is work, a question, or '
                'noise. Until it exists every message just files itself onto the Timeline, '
                'untriaged - the app runs, and does nothing for you. A coding CLI you already '
                'pay for will do it; so will an API key.',
         'done': bool(ai), 'detail': ai.get('Name') or '',
         'goto': {'tab': 'Connections', 'hash': 'cli-agents'}},
        {'key': 'models', 'title': 'Choose what runs on which model',
         'why': 'Triage, the assistant, the general agent and the coding CLI each run on a brain '
                'and a model, and the defaults are a guess at your budget. One page shows all four '
                'and what will actually run. Looking is enough - the defaults are a real answer.',
         'done': seen_models, 'detail': 'you have seen the defaults' if seen_models else '',
         'goto': {'tab': 'Settings', 'hash': 'settings=config&group=Triage%20%26%20agents'}},
        {'key': 'inbound', 'title': 'Connect where work arrives',
         'why': 'A mailbox or a chat - somewhere people actually write to you. Without one the '
                'Timeline is empty because nothing is being read, not because nothing happened. '
                'Trackers and report sources come later; they file work, they do not bring it in.',
         'done': bool(inbound), 'detail': ', '.join(inbound[:3]),
         'goto': {'tab': 'Connections', 'hash': ''}},
        {'key': 'sync', 'title': 'Read your first messages',
         'why': 'With the four above in place, one sync pulls your mail in and the AI triages it. '
                'The assistant then has a pile to take you through, which is the whole point.',
         # no count: this samples the feed, so any number it printed would be the sample size
         # rather than the truth ("2 read" on an install holding thousands)
         'done': bool(inbox), 'detail': 'messages are arriving' if inbox else '',
         'goto': {'tab': 'Assistant', 'hash': ''}},
    ]
    done = sum(1 for s in steps if s['done'])
    return {'steps': steps, 'done': done, 'total': len(steps), 'complete': done == len(steps),
            'dismissed': str(store.get_settings().get(DISMISSED) or '') == '1'}
```

Delete the now-unused `personalized` and `ran` locals.

Finally amend the module docstring — append this paragraph after the existing last one:

```
One step is stored, deliberately: `models` asks you to look at the page where the four brains and
their models are chosen, and a fresh install already ships working defaults, so there is nothing
there to derive. "The defaults are fine" and "I never looked" are the same state. That single
exception is `SEEN_MODELS`; everything else on this list still reads the tables the funnel reads.
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_setup.py -x -q
```

Expected: PASS. `TheWizardActuallySetsUpTests` still passes — those tests drive `/api/owner` and `/api/connectors`, which are untouched.

- [ ] **Step 5: Commit**

```bash
git add taskuary/setup.py tests/test_setup.py
git commit -m "feat: five setup steps that point at the pages that own the work

A tracker is a real source, but an install with GitHub and no mailbox has
a Timeline with no mail in it - and the row said it was done. The row now
asks for a mailbox or a chat.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The one stored step

**Files:**
- Modify: `taskuary/server.py:4501-4516` (beside `setup_state` and `setup_dismiss`)
- Test: `tests/test_setup.py`

**Interfaces:**
- Consumes: `setup.SEEN_MODELS` from Task 1.
- Produces: `POST /api/setup/seen` taking `{"step": "models"}`, returning the full `setup.state()` dict. An unknown step is a 422.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_setup.py`, inside `PuttingItAwayTests` or as its own class:

```python
class TheOneStoredStepTests(unittest.TestCase):
    """Every other row reads real state. This one cannot: the defaults already work, so there is
    nothing to detect. Opening the page is what it asks for and what it records."""
    def _clear(self):
        server.store.set_setting(setup.SEEN_MODELS, '0', 't')

    def test_looking_at_the_page_is_what_ticks_it(self):
        self._clear()
        self.assertFalse(_step(c.get('/api/setup').json(), 'models')['done'])
        out = c.post('/api/setup/seen', json={'step': 'models'})
        self.assertEqual(out.status_code, 200)
        self.assertTrue(_step(out.json(), 'models')['done'])
        self.assertTrue(_step(c.get('/api/setup').json(), 'models')['done'])   # survives the next read

    def test_a_step_nobody_defined_is_refused_rather_than_silently_stored(self):
        """A typo'd step name that returns 200 is a row that can never tick and a setting nobody
        can find."""
        self.assertEqual(c.post('/api/setup/seen', json={'step': 'whatever'}).status_code, 422)

    def test_it_is_recorded_in_the_audit_like_every_other_setting(self):
        self._clear()
        c.post('/api/setup/seen', json={'step': 'models'})
        self.assertTrue(any(r['Action'] == 'setup_seen' for r in server.store.list_audit(limit=20)))
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_setup.py::TheOneStoredStepTests -x -q
```

Expected: FAIL — 404 on `POST /api/setup/seen`.

- [ ] **Step 3: Add the endpoint**

In `taskuary/server.py`, directly after `setup_dismiss` (ends at line 4516):

```python
class SetupSeenBody(BaseModel): step: str

@app.post('/api/setup/seen')
def setup_seen(body: SetupSeenBody):
    """"I have seen that page." The models step asks you to look at where the four brains and their
    models are chosen, and a fresh install already ships working defaults - so there is nothing to
    derive and looking is the whole ask. The only stored step on the list.

    The map is closed: a typo'd step is a 422 rather than a setting nobody can find sitting behind a
    row that can never tick."""
    from . import setup as setup_mod
    key = {'models': setup_mod.SEEN_MODELS}.get(str(body.step or ''))
    if not key: raise HTTPException(422, f'{body.step!r} is not a step that records being seen')
    store.set_setting(key, '1', ACTOR)
    store.audit('setting', 0, 'setup_seen', ACTOR, detail={'step': body.step})
    return setup_mod.state(store)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_setup.py -x -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/server.py tests/test_setup.py
git commit -m "feat: looking at the models page is what ticks its row

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The walk's stops

**Files:**
- Create: `taskuary/walk.py`
- Test: `tests/test_onboarding_walk.py`

**Interfaces:**
- Consumes: `setup.state(store)` from Task 1.
- Produces: `walk.AT` (the position setting name, `'setup_walk_at'`); `walk.STOPS` (list); `walk.state(store, at=None) -> {'stops': list, 'at': int, 'total': int}`. Each stop is `{'key', 'title', 'blurb', 'can', 'goto', 'n'}` plus `'done'`/`'detail'` on the first five and `'facts'` where a fact exists. `can` is a list of `{'text', 'goto'}` where `goto` may be `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_onboarding_walk.py`:

```python
"""The scripted walk: every part of the app, one stop per turn, no AI anywhere in it.

The chip that opens this used to open an AI-led walk-through, which could not run before an AI was
connected - which is exactly when somebody presses it. So the stops are static text plus store
reads, and a typed question is an ordinary assistant turn that happens beside the walk rather than
inside it.
"""
import unittest

from fastapi.testclient import TestClient
from taskuary import server, setup, walk
from taskuary.store import MemoryStore

c = TestClient(server.app)

TABS = {'Assistant', 'Board', 'Tasks', 'Review', 'Reports', 'Connections', 'Docs', 'Settings', 'Hub'}


def _fresh():
    return MemoryStore()


class TheStopsTests(unittest.TestCase):
    def test_the_first_five_stops_are_the_checklist_itself(self):
        """Two surfaces, one source. A walk that listed its own five would be a second list to keep
        in step, and the second one loses."""
        s = _fresh()
        st = walk.state(s)
        keys = [x['key'] for x in st['stops']]
        self.assertEqual(keys[:5], [x['key'] for x in setup.state(s)['steps']])
        self.assertEqual(st['total'], len(walk.STOPS))
        self.assertGreaterEqual(st['total'], 14)

    def test_every_stop_says_what_you_can_do_there(self):
        """The point of a stop is the list of real things, not a paragraph about the tab."""
        for stop in walk.state(_fresh())['stops']:
            self.assertTrue(stop['can'], stop['key'])
            for line in stop['can']:
                self.assertTrue(line['text'].strip(), stop['key'])
                if line['goto'] is not None:
                    self.assertIn(line['goto']['tab'], TABS, stop['key'])
            self.assertIn(stop['goto']['tab'], TABS, stop['key'])

    def test_a_stop_never_states_a_fact_the_panel_would_contradict(self):
        s = _fresh()
        by = {x['key']: x for x in walk.state(s)['stops']}
        self.assertFalse(by['ai']['done'])
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
        by = {x['key']: x for x in walk.state(s)['stops']}
        self.assertTrue(by['ai']['done'])
        self.assertEqual(by['ai']['detail'],
                         next(x['detail'] for x in setup.state(s)['steps'] if x['key'] == 'ai'))

    def test_the_facts_count_what_is_really_connected(self):
        """The facts line is the reason a stop cannot lie: it counts, it does not assert. Written
        as a DELTA rather than an absolute, because what a fresh MemoryStore seeds as active is not
        this test's business and a hardcoded "none yet" would break the day a seed changes."""
        s = _fresh()
        fact = lambda: next(x for x in walk.state(s)['stops'] if x['key'] == 'connections')['facts']
        before = fact()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1}, 't')
        s.save_source({'Channel': 'email', 'Address': 'me@ours.com', 'ConnectorId': cid, 'Active': 1}, 't')
        after = fact()
        self.assertNotEqual(before, after)
        self.assertIn('connected', after)
        self.assertIn('Outlook', after)

    def test_nothing_on_this_road_can_reach_a_model(self):
        """The whole reason the walk exists is that the old one needed an AI to explain how to
        connect an AI."""
        src = (__import__('pathlib').Path(walk.__file__)).read_text(encoding='utf-8')
        for banned in ('import llm', 'from .llm', 'compose', 'concierge', 'build_llm'):
            self.assertNotIn(banned, src)


class KeepingYourPlaceTests(unittest.TestCase):
    def test_the_position_survives_a_reload(self):
        s = _fresh()
        self.assertEqual(walk.state(s)['at'], 0)
        walk.go(s, 6, 't')
        self.assertEqual(walk.state(s)['at'], 6)

    def test_reaching_the_end_clears_it_so_the_next_press_starts_over(self):
        s = _fresh()
        walk.go(s, len(walk.STOPS) - 1, 't')
        self.assertEqual(walk.state(s)['at'], len(walk.STOPS) - 1)
        walk.go(s, len(walk.STOPS), 't')
        self.assertEqual(walk.state(s)['at'], 0)

    def test_a_position_off_the_end_of_the_list_is_clamped_not_crashed(self):
        """The list gets stops added and removed; a stored number outlives the list it indexed."""
        s = _fresh()
        s.set_setting(walk.AT, '999', 't')
        self.assertEqual(walk.state(s)['at'], 0)

    def test_reset_returns_to_the_first_stop(self):
        s = _fresh()
        walk.go(s, 4, 't')
        walk.reset(s, 't')
        self.assertEqual(walk.state(s)['at'], 0)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_onboarding_walk.py -x -q
```

Expected: FAIL — `ImportError: cannot import name 'walk' from 'taskuary'`.

- [ ] **Step 3: Write the module**

Create `taskuary/walk.py`:

```python
"""Setting Taskuary up, as a walk through the app rather than a form that imitates it.

The chip this sits behind used to open an AI-led walk-through, which could not run at all before an
AI was connected - which is exactly when somebody presses it. So nothing here reaches a model: a
stop is static text plus a read off the store, and Next is code.

That is not a lesser version of the assistant, it is how the assistant already works: deterministic
steps, with the AI for anything off script. A question typed during the walk is an ordinary turn,
answered beside the walk rather than inside it, and `concierge.fallback` already speaks in facts
when there is no model to answer it. The walk keeps its place and Next picks the script back up.

TWO KINDS OF TEXT live in a stop, and the difference is the whole design:

  `can`   - what the app can DO here. Static, hard-coded, the same on every install. Assembling it
            at runtime would make it go blank on a fresh install, which is the one install reading it.
  `facts` - what THIS install has done. Read off the same tables `setup.state` reads, so a stop can
            never claim something the checklist contradicts.
"""
from . import setup

AT = 'setup_walk_at'                 # where the owner stopped; a setting, so a reload resumes


def _goto(tab, hash_=''): return {'tab': tab, 'hash': hash_}
def _can(text, tab=None, hash_=''): return {'text': text, 'goto': _goto(tab, hash_) if tab else None}


# The five the checklist also shows, then every part of the app. The first five carry no `blurb` of
# their own - `setup.state` owns their words, and repeating them here is the drift this avoids.
STOPS = [
    {'key': 'owner', 'title': 'Your name', 'goto': _goto('Docs', 'owner'), 'can': [
        _can('type your name and email right here'),
        _can('see every document that uses it', 'Docs')]},
    {'key': 'ai', 'title': 'An AI', 'goto': _goto('Connections', 'cli-agents'), 'can': [
        _can('install a coding CLI and sign in to it, in a terminal right here', 'Connections', 'cli-agents'),
        _can('use a CLI you already pay for', 'Connections', 'cli-agents'),
        _can('paste an API key on a provider card instead', 'Connections')]},
    {'key': 'models', 'title': 'What runs on which model',
     'goto': _goto('Settings', 'settings=config&group=Triage%20%26%20agents'), 'can': [
        _can('choose the brain that triages your mail', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose what the assistant here speaks on', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('choose the general agent and the coding CLI', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('name a model, or leave it on the provider default')]},
    {'key': 'inbound', 'title': 'Where work arrives', 'goto': _goto('Connections'), 'can': [
        _can('connect a mailbox - Outlook, Gmail, or any IMAP host', 'Connections'),
        _can('connect a chat - Teams, Slack, WhatsApp, Telegram', 'Connections'),
        _can('test a card before waiting on a schedule', 'Connections')]},
    {'key': 'sync', 'title': 'Your first messages', 'goto': _goto('Assistant'), 'can': [
        _can('pull your mail in and let triage read it', 'Connections'),
        _can('watch it land on the Timeline', 'Assistant')]},

    {'key': 'connections', 'title': 'Connections',
     'blurb': 'Every mailbox, chat, tracker and report source Taskuary reads lives here. One card '
              'per system, and the card proves itself with its own Test before anything waits on a '
              'schedule.',
     'goto': _goto('Connections'), 'can': [
        _can('connect a mailbox or a chat', 'Connections'),
        _can('connect a tracker - GitHub, Jira, Linear and the rest', 'Connections'),
        _can('add an AI CLI agent', 'Connections', 'cli-agents'),
        _can('test any connection and see what it answered', 'Connections')]},
    {'key': 'docs', 'title': 'Docs',
     'blurb': 'The documents the funnel runs on. SOUL.md is its constitution - what counts as a '
              'task, how you answer, what it must never do. STYLE.md is how you write. Edit one and '
              'triage changes; blank one and the shipped default comes back, so nothing is lost by '
              'trying.',
     'goto': _goto('Docs'), 'can': [
        _can('make SOUL.md yours - your work, boundaries, systems, people, voice', 'Docs'),
        _can('generate STYLE.md from the messages you have sent', 'Docs'),
        _can('generate TRIAGE.md from what you answered and what you let sit', 'Docs'),
        _can('read COUNSEL.md, which is the voice the assistant speaks in', 'Docs')]},
    {'key': 'settings', 'title': 'Settings',
     'blurb': 'The knobs. Most people change three and never come back: what drafts automatically, '
              'how finished work lands, and what reaches them.',
     'goto': _goto('Settings'), 'can': [
        _can('choose the triage brain and its backups', 'Settings', 'settings=config&group=Triage%20%26%20agents'),
        _can('decide whether replies draft themselves', 'Settings'),
        _can('write routing policies the AI can never override', 'Settings', 'settings=policies'),
        _can('see every verdict it learned from, and switch off the wrong ones', 'Settings', 'settings=memory'),
        _can('install an update in place', 'Settings', 'settings=updates')]},
    {'key': 'board', 'title': 'Board',
     'blurb': 'Work in flight, and the agents doing it. A coding task opens a real terminal session '
              'here, and you can watch it, take it over, or hand it a note mid-run.',
     'goto': _goto('Board'), 'can': [
        _can('watch a live agent session', 'Board'),
        _can('take over a pane and type in it yourself', 'Board'),
        _can('leave a note the agent picks up at its next stop', 'Board'),
        _can('put a coding agent to work on a task', 'Tasks')]},
    {'key': 'tasks', 'title': 'Tasks',
     'blurb': 'Everything that became work, open or closed. A task holds the thread it came from, '
              'every run against it, and the session you can pick back up.',
     'goto': _goto('Tasks'), 'can': [
        _can('open a task and read the thread behind it', 'Tasks'),
        _can('continue a coding session where it stopped', 'Tasks'),
        _can('hand a task to an agent, or take it back', 'Tasks'),
        _can('close it - which is yours, never the agent\'s', 'Tasks')]},
    {'key': 'review', 'title': 'Review',
     'blurb': 'Replies drafted in your voice, waiting on you. Nothing sends until you approve it - '
              'there is no setting that changes that.',
     'goto': _goto('Review'), 'can': [
        _can('approve a draft and send it', 'Review'),
        _can('edit it first, or ask for it again differently', 'Review'),
        _can('say it is not yours, which triage remembers', 'Review')]},
    {'key': 'reports', 'title': 'Reports & workflows',
     'blurb': 'A report is a scheduled check that reads and summarises. A workflow is the one that '
              'writes. Both file what they find onto the Timeline on their own schedule.',
     'goto': _goto('Reports'), 'can': [
        _can('schedule a check that reads and summarises', 'Reports', 'report=new'),
        _can('build a workflow that writes back to a system', 'Reports'),
        _can('say whether a run reaches you every time, or only when it is wrong', 'Reports'),
        _can('preview one before it is saved', 'Reports')]},
    {'key': 'assistant', 'title': 'The Assistant',
     'blurb': 'Where you actually work. Everything that arrived is a pile, oldest pressure first, '
              'and Next takes you through it one item at a time. This walk is happening in it.',
     'goto': _goto('Assistant'), 'can': [
        _can('press Next and go through what is waiting'),
        _can('reply, or hand the item to an agent'),
        _can('say it is not ours - and triage remembers that'),
        _can('ask anything in your own words')]},
    {'key': 'hub', 'title': 'Hub',
     'blurb': 'What the company knows, in one place - the durable posts, the people, the systems. '
              'It is where something goes when it outlives the thread it arrived in.',
     'goto': _goto('Hub'), 'can': [
        _can('read what has been posted', 'Hub'),
        _can('post something worth keeping', 'Hub'),
        _can('search across everything Taskuary has read', 'Hub')]},
]

# What THIS install has done, for the stops where a number is worth more than a sentence. Keyed by
# stop; a stop with no entry simply carries no `facts`.
FACTS = {
    'connections': lambda s: (f'{len(_live(s))} connected: ' + ', '.join(_live(s)[:3])) if _live(s) else 'none yet',
    'tasks': lambda s: f'{len(s.list_tasks())} here so far' if s.list_tasks() else 'none yet',
}


def _live(store) -> list:
    return [c['Name'] or c['Type'] for c in store.list_connectors()
            if c['Active'] and c['Type'] in setup.INBOUND]


def state(store, at=None) -> dict:
    """The whole walk: every stop, with the checklist's own done-ness on the first five and this
    install's facts wherever a fact beats a sentence."""
    if at is None: at = _at(store)
    steps = {x['key']: x for x in setup.state(store)['steps']}
    stops = []
    for n, stop in enumerate(STOPS):
        o = dict(stop, n=n)
        row = steps.get(stop['key'])
        # the checklist owns these words; a copy here would be the second one that goes stale
        if row: o.update(done=row['done'], detail=row['detail'], blurb=row['why'], title=row['title'])
        fact = FACTS.get(stop['key'])
        if fact: o['facts'] = fact(store)
        stops.append(o)
    return {'stops': stops, 'at': at, 'total': len(STOPS)}


def _at(store) -> int:
    """Where they stopped - clamped, because a stored number outlives the list it indexed and a
    stop that was removed must not strand the walk off the end of it."""
    try: n = int(str(store.get_settings().get(AT) or 0))
    except ValueError: return 0
    return n if 0 <= n < len(STOPS) else 0


def go(store, at: int, actor: str) -> dict:
    """Move. Walking off the end is finishing: the position clears, so the next press starts over
    rather than reopening the last card forever."""
    at = int(at)
    store.set_setting(AT, str(at if 0 <= at < len(STOPS) else 0), actor)
    return state(store)


def reset(store, actor: str) -> dict:
    store.set_setting(AT, '0', actor)
    return state(store)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_onboarding_walk.py -x -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/walk.py tests/test_onboarding_walk.py
git commit -m "feat: a scripted walk of the app that needs no AI to explain how to connect one

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The walk's endpoints

**Files:**
- Modify: `taskuary/server.py` (after the `setup_seen` endpoint from Task 2)
- Test: `tests/test_onboarding_walk.py`

**Interfaces:**
- Consumes: `walk.state`, `walk.go`, `walk.reset` from Task 3.
- Produces: `GET /api/setup/walk`; `POST /api/setup/walk` with `{"at": int}`; `POST /api/setup/walk/reset`. All three return `walk.state()`'s dict.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_onboarding_walk.py`:

```python
class TheEndpointsTests(unittest.TestCase):
    def tearDown(self):
        c.post('/api/setup/walk/reset')

    def test_it_answers_the_shape_the_card_reads(self):
        d = c.get('/api/setup/walk').json()
        for k in ('stops', 'at', 'total'):
            self.assertIn(k, d)
        for stop in d['stops']:
            for k in ('key', 'title', 'blurb', 'can', 'goto', 'n'):
                self.assertIn(k, stop, stop.get('key'))

    def test_moving_sticks(self):
        self.assertEqual(c.post('/api/setup/walk', json={'at': 7}).json()['at'], 7)
        self.assertEqual(c.get('/api/setup/walk').json()['at'], 7)

    def test_finishing_clears_the_place(self):
        total = c.get('/api/setup/walk').json()['total']
        self.assertEqual(c.post('/api/setup/walk', json={'at': total}).json()['at'], 0)

    def test_reset_is_its_own_door(self):
        c.post('/api/setup/walk', json={'at': 3})
        self.assertEqual(c.post('/api/setup/walk/reset').json()['at'], 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_onboarding_walk.py::TheEndpointsTests -x -q
```

Expected: FAIL — 404 on `/api/setup/walk`.

- [ ] **Step 3: Add the endpoints**

In `taskuary/server.py`, directly after `setup_seen`:

```python
class WalkBody(BaseModel): at: int

@app.get('/api/setup/walk')
def setup_walk():
    """Every stop on the scripted walk, with this install's own facts in it. No AI is involved: the
    chip this sits behind used to open an AI-led walk-through, which could not run before an AI was
    connected - which is when it gets pressed."""
    from . import walk
    return walk.state(store)

@app.post('/api/setup/walk')
def setup_walk_go(body: WalkBody):
    """Next, or a jump. Walking off the end is finishing, and `walk.go` clears the place so the next
    press starts over rather than reopening the last card forever."""
    from . import walk
    return walk.go(store, body.at, ACTOR)

@app.post('/api/setup/walk/reset')
def setup_walk_reset():
    from . import walk
    return walk.reset(store, ACTOR)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_onboarding_walk.py -x -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/server.py tests/test_onboarding_walk.py
git commit -m "feat: the walk's endpoints

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The walk works in the demo

**Files:**
- Modify: `taskuary/demo.py:46-59` (`ALLOWED_WRITES`)
- Test: `tests/test_demo.py`

**Interfaces:**
- Consumes: the endpoint paths from Tasks 2 and 4.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

In `tests/test_demo.py`, add to `TheDemoStillWorksTests`:

```python
    def test_the_walk_is_something_a_visitor_can_actually_take(self):
        """It is a tour of the app that touches nothing real - which is the entire demo. The
        checklist stays hidden there (TaskHubPage hides SetupChip), because a list of connections
        nobody can make is not a demo of anything."""
        with on():
            for path in ('/api/setup/walk', '/api/setup/walk/reset', '/api/setup/seen'):
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_the_walk_being_open_does_not_open_the_connectors(self):
        with on():
            self.assertNotEqual(demo.refuse('POST', '/api/connectors'), '')
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_demo.py -x -q
```

Expected: FAIL — `refuse` returns the default refusal sentence for `/api/setup/walk`.

- [ ] **Step 3: Allowlist the walk**

In `taskuary/demo.py`, replace the `r'^/api/setup/dismiss$',` line inside `ALLOWED_WRITES` with:

```python
    # the checklist's "leave me alone", and the scripted walk - a tour of the app that touches
    # nothing real, which is what a visitor is here for. Its writes are two settings in the demo's
    # own database, which is what everything else on this list has in common.
    r'^/api/setup/(dismiss|seen|walk(/reset)?)$',
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_demo.py -x -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/demo.py tests/test_demo.py
git commit -m "feat: a demo visitor can take the walk

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The shipped skill stops describing a checklist that is gone

**Files:**
- Modify: `taskuary/skills/taskuary-setup/SKILL.md:14-40`
- Test: `tests/test_setup_skill.py`

**Interfaces:**
- Consumes: `setup.state()`'s new key set from Task 1.
- Produces: nothing in code. The skill text is read by `general.setup_skill()`, unchanged.

**Why this task exists:** `/api/concierge/setup` survives this change, so the AI-led walk survives with it — and its procedure is this document. Left alone it would confidently describe eight steps, a `ready` flag and a `where` field that no longer exist. Nothing would fail; the AI would just say something untrue. The new test is what makes that loud.

- [ ] **Step 1: Write the failing test**

Replace the first test in `tests/test_setup_skill.py` with:

```python
    def test_the_skill_ships_with_the_package_and_says_what_a_walkthrough_must_know(self):
        text = general.setup_skill()
        self.assertIn('name: taskuary-setup', text)
        for needed in ('/api/setup',                                   # inspect what is already configured
                       'Prerequisites',                                # the five, in order
                       'GET /api/cli/detect',
                       'Secrets never pass through this chat'):
            self.assertIn(needed, text)

    def test_the_skill_names_the_steps_that_actually_exist(self):
        """A shipped document cannot fail a build when it goes stale - the AI just says something
        untrue about a checklist that changed under it. This is the thing that fails instead."""
        from taskuary import setup
        from taskuary.store import MemoryStore
        text = general.setup_skill()
        keys = [x['key'] for x in setup.state(MemoryStore())['steps']]
        self.assertIn('`, `'.join(keys), text)          # the list, in order, as the skill prints it
        for gone in ('`ready`', '`where`', '`soul`, `sync`'):
            self.assertNotIn(gone, text)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_setup_skill.py -x -q
```

Expected: FAIL — the skill still contains `` `ready` `` and the eight-key list.

- [ ] **Step 3: Rewrite the two stale sections**

In `taskuary/skills/taskuary-setup/SKILL.md`, replace lines 14-18 (the paragraph beginning "`GET /api/setup` returns the whole model") with:

```markdown
`GET /api/setup` returns the whole model: `steps` (each with `key`, `title`, `why`, `done`,
`detail`, `goto`), plus `complete`. The step keys are `owner`, `ai`, `models`, `inbound`, `sync`.
Each `goto` is `{tab, hash}` - the tab to send them to and the position within it.
```

Replace the "## Prerequisites, in order" section (lines 26-41) with:

```markdown
## Prerequisites, in order

1. **The owner's name** (`owner`). It signs every reply and fills `{{owner}}` in the operator
   documents. Docs screen.
2. **One AI** (`ai`). Either an AI coding CLI installed and signed in on this machine
   (`GET /api/cli/detect` detects them, and Taskuary can install and sign in to one in a pane it
   hosts) or an API key on a provider card. Without it nothing is triaged: the app runs and does
   nothing. A CLI they already pay for is the cheaper answer; say so.
3. **A look at the models** (`models`). Triage, the assistant, the general agent and the coding CLI
   each run on a brain and a model. Settings → Configuration → Triage & agents shows all four and
   what will actually run. This is the one step that records being SEEN rather than being derived,
   because the shipped defaults already work - looking is the whole ask.
4. **Somewhere work arrives** (`inbound`). A mailbox or a chat. A tracker is a real source but does
   not satisfy this step: an install with GitHub and no mailbox has a Timeline with no mail in it.
   Connections screen.
5. **The first messages** (`sync`). One sync pulls their mail in and triage reads it.

All five are what `complete` means. There is no second tier and no optional row: personalising
SOUL.md, generating STYLE.md and TRIAGE.md from history, and putting a coding agent to work are
stops on the scripted walk (`GET /api/setup/walk`), not steps on this list. Recommend them when the
five are done; never report them as outstanding setup.

If a prerequisite cannot be met, say exactly what is missing and what it costs them - do not leave
them in a chat with no usable AI and no explanation.
```

In the "## Verify, do not claim" section, replace the last line (`State readiness as the numbers...`) with:

```markdown
State readiness as the numbers: how many of the five are done, and which remain.
```

And in that section's bullet list, delete the `A coding agent is proved by a finished run...` bullet — the coding agent is no longer on this list.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_setup_skill.py -x -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add taskuary/skills/taskuary-setup/SKILL.md tests/test_setup_skill.py
git commit -m "fix: the setup skill described a checklist that no longer exists

A shipped document cannot fail a build when it goes stale - the AI just
says something untrue about a model that changed under it. Now a test
fails instead.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Three deep links

**Files:**
- Modify: `website/src/ConnectorsView.jsx:1103-1110`
- Modify: `website/src/SettingsView.jsx:814` and the `SettingsView` component body
- Modify: `website/src/DocsView.jsx:89-125`
- Test: `website/test/setupDeepLinks.test.mjs` (create)

**Interfaces:**
- Consumes: the `goto.hash` values from Task 1 — `cli-agents`, `settings=config&group=Triage%20%26%20agents`, `owner`.
- Produces: nothing importable. Three views that read their hash on mount.

- [ ] **Step 1: Write the failing test**

Create `website/test/setupDeepLinks.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// A checklist row that points nowhere is the old inline form with the form taken out. These are the
// three positions the five rows name, and none of them existed before.
test("the AI CLI agents page has a door of its own", () => {
  const view = read("ConnectorsView.jsx");
  assert.match(view, /#?cli-agents/);
  assert.match(view, /setOpen\(\{ kind: "agents" \}\)/);
});

test("Settings can be opened on a page and a group", () => {
  const view = read("SettingsView.jsx");
  assert.match(view, /settings=\(\[\\w-\]\+\)/);
  assert.match(view, /group=\(\[^&\]\+\)/);
  assert.match(view, /decodeURIComponent/);
  // consumed once, like every other hash in the app - or Back reopens it
  assert.match(view, /history\.replaceState/);
});

test("Docs can be opened on the name field", () => {
  const view = read("DocsView.jsx");
  assert.match(view, /#?owner/);
  assert.match(view, /scrollIntoView/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd website && npx --yes node@22 --test test/setupDeepLinks.test.mjs
```

(If Node 22 is already the active runtime, `node --test test/setupDeepLinks.test.mjs` is enough.)

Expected: FAIL on all three.

- [ ] **Step 3: Add the three routes**

**`website/src/ConnectorsView.jsx`** — extend the existing hash effect at line 1103. Replace it with:

```jsx
  // #connector=<type> opens that card on arrival - the bell's Fix button lands here, and so can any
  // link. #cli-agents opens the AI CLI agents page, which is where the checklist's "Set up an AI"
  // row goes: the agents page had no door of its own, only a button on this one.
  // Consumed once, so Back does not reopen it.
  useEffect(() => {
    const hash = window.location.hash || "";
    const m = /connector=([\w-]+)/.exec(hash);
    if (!m && !/cli-agents/.test(hash)) return;
    if (!connectors) return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (!m) { setOpen({ kind: "agents" }); return; }
    const t = m[1];
    const direct = /^\d+$/.test(t) ? connectors.find((c) => c.ConnectorId === Number(t)) : byType[t];
    if (direct) setOpen({ kind: "connector", id: direct.ConnectorId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectors]);
```

**`website/src/SettingsView.jsx`** — `page` is declared at line 814 and `cfgTab` inside `SettingsPages` at line 337, two components apart. The hash is read in each, so neither needs to reach into the other.

Beside the `page` declaration (line 814):

```jsx
  const [page, setPage] = useState(NAV[0]);      // the rail's first entry is where Settings opens - About you
  // #settings=<page> lands on one of the rail's pages. The checklist's "what runs on which model"
  // row points here, and Settings had no hash routing at all - `page` and `cfgTab` were state-only,
  // so every link into it arrived on About you. Consumed once, so Back does not reopen it.
  useEffect(() => {
    const m = /settings=([\w-]+)/.exec(window.location.hash || "");
    if (!m || !NAV.includes(m[1])) return;
    setPage(m[1]);
  }, []);
```

Inside `SettingsPages`, beside the `cfgTab` declaration (line 337):

```jsx
  const [cfgTab, setCfgTab] = useState(GROUPS[0]);   // the leading tab, whatever it is - a hardcoded name here went stale the moment a group was added in front of it
  // ...and &group=<name> picks the tab within Configuration. The group names contain a `&` ("Triage
  // & agents"), so the link carries them encoded and they are decoded exactly once here.
  useEffect(() => {
    const hash = window.location.hash || "";
    const m = /group=([^&]+)/.exec(hash);
    if (m) {
      const want = decodeURIComponent(m[1]);
      if (GROUPS.includes(want)) setCfgTab(want);
    }
    if (/settings=/.test(hash)) window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, []);
```

**`website/src/DocsView.jsx`** — in `OwnerCard`, add a ref and a hash effect. Replace the component's opening (lines 89-100) with:

```jsx
const OwnerCard = () => {
  const [who, setWho] = useState(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const box = useRef(null);
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      setWho(data);
      setName(data.owner === "the owner" ? "" : data.owner || "");
      setEmail(data.owner_email || "");
    }).catch(() => setWho({}));
  }, []);
  // #owner brings you to this field rather than to the top of a page of documents - the checklist's
  // first row points here, and Docs is long enough that landing at the top is landing nowhere.
  useEffect(() => {
    if (!who || !/(^|#|&)owner(&|$)/.test(window.location.hash || "")) return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    box.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [who]);
```

and add the ref to the returned `Box`:

```jsx
    <Box ref={box} sx={{ mb: 2.5, p: 1.75, bgcolor: "#fff", border: "1px solid #e1dcd5", borderRadius: 2,
```

Add `useRef` to the React import at the top of `DocsView.jsx` if it is not already there.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd website && node --test test/setupDeepLinks.test.mjs && npm run lint:undef
```

Expected: PASS, and no lint errors.

- [ ] **Step 5: Commit**

```bash
git add website/src/ConnectorsView.jsx website/src/SettingsView.jsx website/src/DocsView.jsx website/test/setupDeepLinks.test.mjs
git commit -m "feat: the three positions the checklist points at have doors

Settings had no hash routing at all, so every link into it arrived on
About you.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: The panel points instead of pretending

**Files:**
- Modify: `website/src/SetupWizard.jsx` (delete lines 71-470 except `OwnerForm`; rewrite `Step`, `SetupPanel`, `SetupChip`)
- Test: `website/test/setupPanel.test.mjs` (create)

**Interfaces:**
- Consumes: `setup.state()`'s shape from Task 1 — `steps[].goto`, `done`, `total`, `complete`, `dismissed`.
- Produces: `SetupChip`, `SetupPanel`, `useSetup` — same exported names and the same props `TaskHubPage.jsx:404,419` already passes.

- [ ] **Step 1: Write the failing test**

Create `website/test/setupPanel.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// "Pointing is not setting up" held while a step was one field. The AI row grew a CLI picker, an
// installer, a sign-in pane and a key form - a worse copy of the page that owns them, kept in step
// by hand. One form survives, because two text boxes have nowhere better to be.
test("only the owner's two fields are still done in the panel", () => {
  const w = read("SetupWizard.jsx");
  assert.match(w, /const OwnerForm/);
  for (const gone of ["BrainForm", "MailboxForm", "SyncForm", "HistoryForm", "SoulForm", "AgentForm", "CliPicker"]) {
    assert.doesNotMatch(w, new RegExp(`const ${gone}`), gone);
  }
  assert.match(w, /const FORMS = \{ owner: OwnerForm \}/);
});

test("every other row is a link to the page that owns the work", () => {
  const w = read("SetupWizard.jsx");
  assert.match(w, /s\.goto/);
  assert.doesNotMatch(w, /s\.where/);
});

test("the counter is finished rather than hidden", () => {
  const w = read("SetupWizard.jsx");
  // SetupChip already returns null on complete; what must go is the second tier it counted
  assert.doesNotMatch(w, /guide_done|guide_total/);
  assert.doesNotMatch(w, /state\.ready/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd website && node --test test/setupPanel.test.mjs
```

Expected: FAIL on all three.

- [ ] **Step 3: Strip the panel back to a list of links**

Rewrite `website/src/SetupWizard.jsx`. The whole file becomes:

```jsx
// Getting started, pointed at the places that do it.
//
// A fresh install opens on an empty Timeline that looks exactly like a working install on a quiet
// morning, and the few things standing between those two states live on different tabs.
//
// The first version of this pointed at those tabs, and the second decided that pointing was not
// setting up - so every step grew a form. That held while a step was one field. It stopped holding
// when the AI row grew a CLI picker, an installer, a sign-in pane and an API-key form: a worse copy
// of the page that owns those things, kept in step with it by hand. A second source of truth loses.
//
// So the rows point again, at real positions rather than at tabs - the AI CLI agents page, the
// group inside Settings where the models are chosen, the name field inside Docs. One form survives,
// because two text boxes have nowhere better to be. And the whole thing is gone once it is done:
// the counter is finished, not hidden. The walk on the Assistant header is the way back.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogContent, TextField, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL2 } from "./theme.jsx";

const COUNT = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const spell = (n) => COUNT[n] || String(n);

export const useSetup = (tick) => {
  const [state, setState] = useState(null);
  const load = useCallback(() => {
    api.get("/api/setup").then(({ data }) => setState(data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, tick]);
  return [state, load];
};

/* Gone for good once the five are done - there is no "show it again", because the walk on the
   Assistant header is always there and covers more than this ever did. */
export const SetupChip = ({ state, onOpen }) => {
  if (!state || state.complete) return null;
  const left = state.total - state.done;
  const pct = state.total ? (state.done / state.total) * 100 : 0;
  return (
    <Tooltip title={state.dismissed ? "Setting up — put away, click to reopen" : "Finish setting Taskuary up"}>
      <Box onClick={onOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.75, cursor: "pointer", ml: 1,
          px: 1, py: 0.35, borderRadius: 99, border: `1px solid ${state.dismissed ? BORDER : "#d8cfbe"}`,
          bgcolor: state.dismissed ? "transparent" : "#eae4d8",
          opacity: state.dismissed ? 0.75 : 1, "&:hover": { opacity: 1 } }}>
        <Box sx={{ position: "relative", display: "flex", width: 16, height: 16 }}>
          <CircularProgress variant="determinate" value={100} size={16} thickness={6}
            sx={{ color: "#e6e9ef", position: "absolute" }} />
          <CircularProgress variant="determinate" value={pct} size={16} thickness={6} sx={{ color: "#55697a" }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: state.dismissed ? DIM : "#55697a" }}>
          {left} left
        </Typography>
      </Box>
    </Tooltip>
  );
};

const Field = (p) => <TextField size="small" fullWidth sx={{ bgcolor: "#fff" }} {...p} />;

/* The one step still done here. Everything else has a page with more on it than this dialog can
   hold; this one is two text boxes, and sending somebody to Docs to type their own name is exactly
   the pointing that is worth complaining about. */
const OwnerForm = ({ onDone }) => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      if (data.owner && data.owner !== "the owner") setName(data.owner);
      if (data.owner_email) setEmail(data.owner_email);
    }).catch(() => {});
  }, []);
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.put("/api/owner", { name: name.trim(), email: email.trim() || null }); await onDone(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
    setBusy(false);
  };
  return (
    <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
      <Field label="Your name" value={name} onChange={(e) => setName(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Field label="Email" value={email} onChange={(e) => setEmail(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Button variant="contained" disableElevation size="small" disabled={busy || !name.trim()} onClick={save}>
        {busy ? "…" : "Save"}
      </Button>
      {err && <Alert severity="error" sx={{ width: "100%", fontSize: 12.5 }}>{err}</Alert>}
    </Box>
  );
};

const FORMS = { owner: OwnerForm };

/* A done step collapses to ONE line. Its reason mattered while you were deciding whether to do it;
   afterwards it is six lines of history pushing the thing you are actually working on below the
   fold. Only the open step carries its full text, and only one is ever open. */
const Step = ({ s, n, open, onOpen, onGo, onDone }) => {
  const Form = FORMS[s.key];
  const active = open && !s.done;
  return (
    <Box sx={{ borderTop: n ? `1px solid ${BORDER}` : "none",
      bgcolor: active ? "#fff" : "transparent",
      boxShadow: active ? "inset 3px 0 0 #55697a" : "none",
      px: active ? 1.5 : 0, py: s.done ? 1 : 1.5, transition: "background-color .15s" }}>
      <Box sx={{ display: "flex", gap: 1.5, alignItems: s.done ? "center" : "flex-start" }}>
        <Box sx={{ pt: s.done ? 0 : 0.25, display: "flex" }}>
          {s.done ? <CheckCircleIcon sx={{ fontSize: 18, color: "#47654a" }} />
            : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: "#55697a" }} />}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
            <Typography sx={{ fontWeight: s.done ? 600 : 700, fontSize: s.done ? 12.5 : 13.5,
              color: s.done ? DIM : INK }}>{s.title}</Typography>
            {s.done && s.detail && (
              <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>{s.detail}</Typography>
            )}
          </Box>
          {/* WHY before HOW, while it is still a decision */}
          {!s.done && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25, lineHeight: 1.55 }}>
              {s.why}
            </Typography>
          )}
          {active && Form && <Form onDone={onDone} />}
        </Box>
        {!s.done && !open && Form && (
          <Button size="small" variant="outlined" onClick={onOpen}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>Set up</Button>
        )}
        {!s.done && !Form && (
          <Button size="small" endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => onGo(s.goto)}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>{s.goto.tab}</Button>
        )}
        {s.done && (Form
          ? <Typography variant="caption" onClick={onOpen}
              sx={{ color: FAINT, cursor: "pointer", whiteSpace: "nowrap", "&:hover": { color: "#55697a" } }}>change</Typography>
          : <Typography variant="caption" onClick={() => onGo(s.goto)}
              sx={{ color: FAINT, cursor: "pointer", whiteSpace: "nowrap", "&:hover": { color: "#55697a" } }}>change</Typography>)}
      </Box>
      {/* A reopened DONE step puts its form UNDER the row, indented to the text column - inside the
          header row it overflowed its track and sat on the step's own title (owner, 2026-09-02). */}
      {s.done && open && Form && (
        <Box sx={{ pl: 4.5, pt: 1 }}><Form onDone={onDone} /></Box>
      )}
    </Box>
  );
};

export const SetupPanel = ({ open, state, onClose, onGo, onDismiss, onRefresh }) => {
  const [openKey, setOpenKey] = useState(null);
  const steps = state?.steps || [];
  // the first thing left to do is already open: a list whose every step needs a click first is a
  // list of buttons
  useEffect(() => {
    if (!open || !steps.length) return;
    if (state.complete) { setOpenKey(null); return; }
    setOpenKey((k) => k || (steps.find((s) => !s.done && FORMS[s.key]) || {}).key || null);
  }, [open, steps, state?.complete]);
  if (!state) return null;
  const left = state.total - state.done;
  // one road for every row: the tab, then the position inside it
  const go = (goto) => {
    if (goto?.hash) window.location.hash = goto.hash;
    onGo(goto.tab);
    onClose();
  };
  const done = async () => { setOpenKey(null); await onRefresh(); };
  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 17, color: INK }}>
              {state.complete ? "Taskuary is yours" : `${spell(left)} ${left === 1 ? "thing" : "things"} left`}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5 }}>
              {state.complete
                ? "This list is finished and will not come back. “Set up Taskuary” on the Assistant walks the rest of the app whenever you want it."
                : "Each one opens the page that actually does it. They tick themselves from what is really connected, "
                  + "so anything you set up anywhere shows up here."}
            </Typography>
          </Box>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: FAINT, cursor: "pointer", mt: 0.5 }} />
        </Box>

        <Box sx={{ mt: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 2 }}>
          {steps.map((s, i) => (
            <Step key={s.key} s={s} n={i} open={openKey === s.key} onOpen={() => setOpenKey(s.key)}
              onGo={go} onDone={done} />
          ))}
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
          <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>
            {state.dismissed ? "Put away — the quiet counter in the top bar brings it back."
              : state.complete ? "Revisit any of these later from Connections, Docs or Settings."
                : "Not now? Put it away; the counter in the top bar brings it back."}
          </Typography>
          {!state.complete && (
            <Button size="small" sx={{ color: DIM, fontSize: 12 }} onClick={() => onDismiss(!state.dismissed)}>
              {state.dismissed ? "Show it again" : "Put it away"}
            </Button>
          )}
          <Button size="small" variant="contained" disableElevation onClick={onClose} sx={{ fontSize: 12 }}>
            {state.complete ? "Done" : "Close"}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};
```

Note `SoulInterview.jsx`, `cliInstall.jsx` and `cliSetup.jsx` are no longer imported here. Do **not** delete those files — `cliSetup.jsx` is used by `ConnectorsView` and by Task 10, `SoulInterview.jsx` by `DocsView`. Check with `grep -rn "SoulInterview\|useCliInstall" website/src` before assuming anything is orphaned.

Also update `TaskHubPage.jsx:225` — the first-run auto-open reads `setup.ready`:

```jsx
    if (DEMO || demo || greeted || !setup || setup.complete || setup.dismissed) return;
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd website && node --test test/setupPanel.test.mjs && npm run lint:undef
```

Expected: PASS, no lint errors. `npm run lint:undef` is the gate that catches a variable left behind by the deletions.

- [ ] **Step 5: Commit**

```bash
git add website/src/SetupWizard.jsx website/src/TaskHubPage.jsx website/test/setupPanel.test.mjs
git commit -m "feat: the checklist points at the pages that own the work

Pointing is not setting up - that held while a step was one field. The AI
row grew a CLI picker, an installer, a sign-in pane and a key form, kept
in step with the real page by hand. One form survives: two text boxes
have nowhere better to be.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Looking at the models page ticks its row

**Files:**
- Modify: `website/src/AiDefaults.jsx:108` (the default export's mount effect)
- Test: `website/test/setupPanel.test.mjs`

**Interfaces:**
- Consumes: `POST /api/setup/seen` from Task 2.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing test**

Append to `website/test/setupPanel.test.mjs`:

```javascript
test("opening the models page is what reports it seen", () => {
  const panel = read("AiDefaults.jsx");
  assert.match(panel, /\/api\/setup\/seen/);
  assert.match(panel, /step: "models"/);
  // it must not block the page: the row is a nicety, the page is the point
  assert.match(panel, /catch \(\) \{|\.catch\(/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd website && node --test test/setupPanel.test.mjs
```

Expected: FAIL — `AiDefaults.jsx` has no such call.

- [ ] **Step 3: Post it on mount**

In `website/src/AiDefaults.jsx`, inside the default-exported `AiDefaults` component (line 108), add an effect beside the existing load:

```jsx
  // The checklist's models row is the one step with nothing to derive - a fresh install already
  // ships working brain and model defaults, so "the defaults are fine" and "I never looked" are the
  // same state. Arriving here is the evidence, so arriving here is what records it. Failure is
  // ignored on purpose: a checklist row is a nicety and this page is the point.
  useEffect(() => { api.post("/api/setup/seen", { step: "models" }).catch(() => {}); }, []);
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd website && node --test test/setupPanel.test.mjs && npm run lint:undef
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add website/src/AiDefaults.jsx website/test/setupPanel.test.mjs
git commit -m "feat: arriving at the models page is what records it seen

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: The walk, in the conversation

**Files:**
- Modify: `website/src/assistantCards.jsx` (add `WalkCard` after `SetupCard`, which ends at line 750)
- Modify: `website/src/AssistantView.jsx:384-405` (card dispatch), `:412` (the non-live note), `:979-981` (`setup()`)
- Test: `website/test/onboardingWalk.test.mjs` (create)

**Interfaces:**
- Consumes: `GET/POST /api/setup/walk` from Task 4; `CliPane`, `SetupButton`, `useCliSetup`, `canSetup` from `website/src/cliSetup.jsx`.
- Produces: `WalkCard({ card, at, total, onNavigate, onNext, onFinish })` exported from `assistantCards.jsx`, where `card` is one stop from `/api/setup/walk` plus `kind: "walk"`.

- [ ] **Step 1: Write the failing test**

Create `website/test/onboardingWalk.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// The chip used to open an AI-led walk-through, which could not run before an AI was connected -
// which is exactly when somebody presses it.
test("Set up Taskuary opens the scripted walk, not a request for an AI to interpret", () => {
  const view = read("AssistantView.jsx");
  const fn = view.slice(view.indexOf("const setup = "), view.indexOf("const setup = ") + 1400);
  assert.match(fn, /\/api\/setup\/walk/);
  assert.doesNotMatch(fn, /concierge\/setup/);
});

test("the walk is a card kind of its own and keeps the trail", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /kind === "walk"/);
  assert.match(view, /walk: <WalkCard/);
});

test("a stop shows what you can do there, each with its own way in", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"));
  assert.match(card, /You can/);
  assert.match(card, /can\.map/);
  assert.match(card, /Next/);
  assert.match(card, /Finish/);
  assert.doesNotMatch(card, /Skip/);          // with only a position stored, skip and next are one act
});

test("the AI stop opens the real terminal rather than describing one", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"));
  assert.match(card, /CliPane/);
  assert.match(card, /useCliSetup/);
});

test("nothing in the walk asks a model anything", () => {
  const cards = read("assistantCards.jsx");
  const card = cards.slice(cards.indexOf("export function WalkCard"), cards.indexOf("export function WalkCard") + 4000);
  for (const banned of ["/api/concierge/say", "/api/concierge/ai", "provider"]) {
    assert.doesNotMatch(card, new RegExp(banned.replace(/\//g, "\\/")), banned);
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd website && node --test test/onboardingWalk.test.mjs
```

Expected: FAIL on all five.

- [ ] **Step 3: Build the card and wire the chip**

In `website/src/assistantCards.jsx`, add after `SetupCard` (which ends at line 750). Add `import { useCliSetup, SetupButton, CliPane, canSetup } from "./cliSetup.jsx";` to the file's imports if not present:

```jsx
/* One stop of the scripted walk. Deterministic: the text is shipped, the buttons are code, and
   nothing here asks a model anything - the chip this sits behind used to open an AI-led walk-through,
   which could not run before an AI was connected, which is when it gets pressed.

   `can` is what the APP can do here, shipped and identical on every install. `facts` is what THIS
   install has done, read off the same tables the checklist reads - so a stop can never claim
   something the checklist contradicts. */
export function WalkCard({ card, at, total, onNavigate, onNext, onFinish }) {
  const { openSetup, opening, pane, note } = useCliSetup();
  const [cli, setCli] = useState(null);
  useEffect(() => {
    if (card?.key !== "ai") return;
    api.get("/api/cli/detect").then(({ data }) => setCli((data.data || []).find((o) => canSetup(o)) || null)).catch(() => {});
  }, [card?.key]);
  const go = (goto) => {
    if (!goto) return;
    if (goto.hash) window.location.hash = goto.hash;
    onNavigate?.(goto.tab);
  };
  const last = at >= total - 1;
  return (
    <CardShell card={{ ...card, lane: "report" }} kicker={`setting up · ${at + 1} of ${total}`}
      title={card.title} sub={card.blurb}>
      {card.facts && <div className="tq-card-excerpt">{card.facts}</div>}
      <div style={{ fontSize: 12, fontWeight: 700, color: "#867f74", margin: "8px 0 4px" }}>You can</div>
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.75 }}>
        {(card.can || []).map((o, i) => (
          <li key={i}>
            {o.goto ? <span role="button" tabIndex={0} onClick={() => go(o.goto)}
              onKeyDown={(e) => { if (e.key === "Enter") go(o.goto); }}
              style={{ color: "#55697a", cursor: "pointer" }}>{o.text}</span> : o.text}
          </li>
        ))}
      </ul>
      {/* The one stop that does the work in place: what it opens is a terminal, and a terminal has
          no page of its own to visit. */}
      {card.key === "ai" && cli && (
        <div style={{ marginTop: 8 }}>
          <SetupButton cli={cli} opening={opening} onOpen={openSetup} />
          {note && <div className="tq-card-note">{note.text}</div>}
          {pane && <CliPane pane={pane} height="38vh" />}
        </div>
      )}
      <div className="tq-card-actions">
        {card.goto && <Button size="small" variant="contained" disableElevation onClick={() => go(card.goto)}
          sx={primary}>Open {card.goto.tab}</Button>}
        {!last && <Button size="small" onClick={onNext} sx={faint}>Next ›</Button>}
        <span className="sp" />
        <Button size="small" onClick={onFinish} sx={faint}>Finish</Button>
      </div>
    </CardShell>
  );
}
```

In `website/src/AssistantView.jsx`:

Import `WalkCard` alongside the other cards.

Change the `kind` line (line 384):

```jsx
  const kind = c?.kind === "setup" ? "setup" : c?.kind === "walk" ? "walk" : (m.proposal || c?.kind === "proposal") ? "proposal" : cardFor(c);
```

Add to the card map (beside `setup:` at line 400):

```jsx
    walk: <WalkCard card={m.card} at={m.card.n} total={m.card.total} onNavigate={actions.navigate}
      onNext={() => actions.walk(m.card.n + 1)} onFinish={() => actions.walk(-1)} />,
```

Extend the non-live exclusion at line 412:

```jsx
          {!live && m.card && kind && kind !== "setup" && kind !== "walk" && kind !== "brief" && (
```

Replace `setup()` (lines 979-981) with:

```jsx
  // Setting Taskuary up: the scripted walk, one stop per message so the conversation keeps the
  // trail. Nothing here reaches a model - a question typed during it is an ordinary turn, answered
  // beside the walk, and Next picks the script back up where it was.
  const pushStop = (data) => {
    const stop = (data.stops || [])[data.at];
    if (!stop) return;
    setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "assistant",
      card: { ...stop, kind: "walk", lane: "report", total: data.total }, options: [] }]);
  };
  const setup = async () => {
    try { pushStop((await api.get("/api/setup/walk")).data); }
    catch { setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt", text: "the walk could not be loaded" }]); }
  };
  // -1 is Finish: walking off the end clears the place server-side, so the next press starts over.
  const walkTo = async (at) => {
    try {
      const { data } = await api.post("/api/setup/walk", { at });
      if (at >= 0 && at < data.total) pushStop(data);
      else setMsgs((m) => [...m, { id: `w${Date.now()}`, role: "receipt",
        text: "Walk finished — “Set up Taskuary” starts it again any time." }]);
    } catch { /* the card stays where it is; nothing was lost */ }
  };
```

`walk.go` clamps anything outside the list to `0`, so Finish stores 0 and the next press starts at
the first stop. Add `walk: walkTo` to the `actions` object (line 1150).

Finally, update the chip's tooltip (line 1171):

```jsx
        <Tooltip title="A walk through every part of Taskuary — one step at a time, no AI needed">
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd website && node --test test/onboardingWalk.test.mjs && npm run lint:undef && node --test "test/**/*.test.mjs"
```

Expected: PASS. Note `browserWalkthrough.test.mjs` asserts on `SetupCard` — that card is untouched, so it must still pass.

- [ ] **Step 5: Commit**

```bash
git add website/src/assistantCards.jsx website/src/AssistantView.jsx website/test/onboardingWalk.test.mjs
git commit -m "feat: Set up Taskuary walks the app instead of asking an AI to

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: The no-model line points somewhere useful, and the whole thing ships

**Files:**
- Modify: `taskuary/concierge.py:626`
- Modify: `taskuary/web/assets/` (rebuilt bundle)
- Test: `tests/test_concierge.py` (or wherever `fallback` is covered — find it first)

**Interfaces:**
- Consumes: the `cli-agents` hash from Task 7.
- Produces: nothing.

- [ ] **Step 1: Find the existing coverage and write the failing test**

```bash
grep -rn "Connections → AI" tests/ taskuary/
```

Add to whichever test file covers `concierge.fallback`:

```python
    def test_the_no_model_line_points_at_the_page_that_fixes_it(self):
        """"No AI is connected - Connections → AI" named a tab, and the AI CLI agents page inside it
        had no door of its own. Now it has one, and this is the sentence somebody reads at the exact
        moment they need it."""
        said = concierge.fallback(None, False, pile_items=[{'key': 'k', 'kind': 'fyi', 'title': 't'}])
        self.assertIn('cli-agents', said)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_concierge.py -x -q -k no_model_line
```

Expected: FAIL — the line still says `Connections → AI`.

- [ ] **Step 3: Point it at the page**

In `taskuary/concierge.py`, line 626, change:

```python
                    '(No AI is connected, so I speak in facts rather than sentences - Connections → AI.)')
```

to:

```python
                    # the tab was as far as this went, and the page that fixes it had no door of its
                    # own until the checklist needed one. Now it does, so say it.
                    '(No AI is connected, so I speak in facts rather than sentences - '
                    'Connections → AI CLI agents: #cli-agents.)')
```

- [ ] **Step 4: Run the full suite and rebuild the bundle**

```bash
python -m pytest
```

Expected: PASS, with a real test count. **"no tests ran" is a failure**, not a pass.

Then rebuild the committed UI:

```bash
cd website && npm run build
```

Check `git status` shows the rebuilt `taskuary/web/assets/` files. A bundle that rides along while its source line does not is how the CLI installer was broken on master for two days (`ab82e00a`).

- [ ] **Step 5: Commit**

```bash
git add taskuary/concierge.py tests/ taskuary/web
git commit -m "feat: the no-AI line points at the page that fixes it, and the bundle catches up

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Manual verification

After Task 11, run the app and check the two surfaces by hand — the unit tests read source text, which cannot tell you whether a link lands.

```bash
pip install -e . --no-deps --force-reinstall
```

Restart the app, then find the running instance by its listening port (not the process list — a second instance on another port has fooled this before):

```bash
netstat -ano | grep LISTEN | grep -E "799[0-9]|800[0-9]"
```

- [ ] The top-right counter says "5 left" on a fresh home, and each row's button lands on the right page **and the right position within it** — Docs scrolled to the name field, Connections on the AI CLI agents page, Settings on Configuration → Triage & agents.
- [ ] Opening Settings → Triage & agents once makes the models row green without changing anything.
- [ ] Connecting only a tracker leaves row 4 unticked; connecting a mailbox ticks it.
- [ ] With all five done the counter is gone from the top bar entirely.
- [ ] **Set up Taskuary** on the Assistant header walks all 14 stops, each showing its "You can" list, and Next keeps the previous cards in the conversation.
- [ ] On stop 2, **Set it up** opens a real terminal pane inside the conversation and it looks like the panes on the Board.
- [ ] With no AI connected: typing a question during the walk answers in facts and does not error, and the walk card above it still advances on Next.

---

## Self-review notes

**Spec coverage.** Every section of the spec maps to a task: panel rows and counters (1), stored flag (2), `walk.py` (3), endpoints (4), demo (5), shipped skill (6), deep links (7), wizard strip (8), `AiDefaults` (9), `WalkCard` and the chip (10), `fallback` link plus the bundle (11).

**Two things the spec named that are worth re-checking during execution:**
- `walk.state()` overwrites `title` and `blurb` for the first five stops from `setup.state()`. The `STOPS` entries for those five therefore carry no `blurb` key of their own, which is deliberate — but it means `test_every_stop_says_what_you_can_do_there` must not assert on `blurb`, and it does not.
- Task 8 deletes imports of `SoulInterview.jsx`, `cliInstall.jsx` and `cliSetup.jsx` from `SetupWizard.jsx`. All three files stay: `cliSetup.jsx` is used by `ConnectorsView` and Task 10, `cliInstall.jsx` by `ConnectorsView`, `SoulInterview.jsx` by `DocsView`. Verify with grep before deleting anything.

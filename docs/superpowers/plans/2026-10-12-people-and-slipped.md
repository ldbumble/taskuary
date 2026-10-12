# People pages, the chase ladder and the slipped answers (build step 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The outcome ledger learns who answered and how fast; a page per person is compiled from it at reflection and read wherever the hub's dossier is read; a thread or a step that has gone quiet past THAT person's usual day lands in the slipped lane inside On you, counted as "3 slipped"; and the card offers the four answers - Chase, Let it go, They answered elsewhere, Later - each an outcome.

**Architecture:** `taskuary/outcomes.py` gains a person key on its rows (`who`), an answer latency at resolution, two closing kinds (`chase.let_go`, `chase.elsewhere`), and three readers (`person_facts`, `late_after`, `chase_cc`): numbers from facts, no model. New `taskuary/people_pages.py` compiles one doc per person (`person-<address>`) with the light brain at reflection, inside a marked block so the owner's own lines survive; `counsel.dossier` reads it, which reaches the reply drafter, triage context, meeting prep and the Advisor's bigger read. The rail's existing `forgotten` lane ("slipped") becomes an owner lane with two producers: a follow-up idea past the person's day, and a `person:` step past its due day plus the person's day. The four answers are three new verbs on that lane (chips → proposals → `server._run_operation`), plus Remind me, each writing the ledger.

**Tech Stack:** Python 3.12 / SQLite / FastAPI, pytest; React + Vite for the Settings → Docs rail.

**Spec:** `docs/superpowers/specs/2026-10-12-goals-outcomes-advisor-design.md`: "The outcome ledger" (facts about other people), "Surfaces: What was not followed up", build step 4.

## Global Constraints

- Public repo: stand-ins only (northwind.example, Alex Doyle, Ray Colton, Gail Moreno, Omar Keller, Payworth).
- Concise fast.ai style matching the file; no autoformatters; `website/src` stays LF.
- Never route on a word match: a person is keyed by address (`who`), never by name text; what a page SAYS is the model's, the numbers in it are the ledger's; the slipped lane is a fact (days past a person's measured day), never a word in a mail.
- A derived line never acts on its own: the slipped card offers; the owner answers. Three Let-it-gos on one person stop the Advisor RAISING that person, nothing else.
- The rail reads only task facts and ledger NUMBERS (`late_after`), never advice; `advice` stays out of the rail.
- Push only after the full pytest suite from the repo root plus `cd website && npm test && npm run build`; a `docs/site` or `settings_schema.json` edit needs `npm run build:docs`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **A person who is away** (an auto-reply on file, `assistant.ooo`): their quiet thread never slips, whatever the day count. Pinned in Task 3 (`test_someone_away_never_slips`).
2. **Three Let-it-gos on one person** silence the follow-up producer for THAT address only; a fourth thread from them is not raised, another person's is. Pinned in Task 4 (`test_three_let_gos_silence_one_person`).
3. **A chase with no thread to reply on** (a `person:` step that never had mail) is refused with a sentence naming the task page, never a 500. Pinned in Task 4 (`test_a_chase_with_no_thread_is_refused_plainly`).
4. **Fewer than three answered replies from a person**: `late_after` is the default, never a median of one. Pinned in Task 1 (`test_late_after_needs_three_answers`).
5. **The owner's own lines on a person page** outside the marked block survive a recompile; a page the owner deleted the block from gets it back at the end. Pinned in Task 2 (`test_the_owners_lines_survive_a_recompile`).

---

### Task 1: The ledger learns who, how fast, and after what

**Files:**
- Modify: `taskuary/outcomes.py` (KINDS, the `reply.sent` resolution, two closing kinds, `update_facts`, `person_facts`, `late_after`, `chase_cc`), `taskuary/verdicts.py` (the `reply.sent` facts line at `:238`), `taskuary/store.py` (`update_task`'s close door: `was` reads Assignee and DueAt too)
- Test: `tests/test_outcomes.py` (append `PersonFactsTests`)

**Interfaces:**
- Produces: `reply.sent` facts `{'cid','mid','review','verb','closed','who','cc','chase'}`; resolution adds `facts['answer_days']` (float, one decimal) when they answered; `task.closed` facts `{'from','to','who'?,'due'?,'late_days'?}` when the task's Assignee is `person:<address>`; kinds `chase.let_go` and `chase.elsewhere` (facts `{'who','where'?}`, settled at once, verdict `closed`); `outcomes.update_facts(store, row_id, **more)`; `outcomes.person_facts(store, who) -> dict` with keys `replies, answered, answer_days (list), median_days (float|None), chased, answered_after_chase, steps, steps_late, let_go, cc (dict addr -> [answered_with, total_with])`; `outcomes.late_after(store, who, default=5) -> int` (≥3 answers: `max(2, ceil(median*1.5))`, else `default`); `outcomes.chase_cc(store, who) -> str|None` (the cc address with ≥2 samples and the best answered share ≥ 0.6, else None); `outcomes.let_go_count(store, who) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_outcomes.py
class PersonFactsTests(unittest.TestCase):
    def _answered(self, s, who, days, chase=False, cc=()):
        """A reply sent to `who` `days + 1` days ago that they answered `days` days later."""
        cid = f'c{s._one("SELECT COUNT(*) AS n FROM outcome")["n"] + 1}'
        t = s.create_task({'Title': 'x'}, 'owner')
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'x', 'FromEmail': who, 'SentAt': ago(days=days + 2), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: x', 'FromEmail': who, 'SentAt': ago(days=8 - days if days < 8 else 0, hours=1), 'BodyText': 'a', 'Status': 'filed', 'TaskId': t})
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': cid, 'mid': 1, 'verb': 'approve', 'who': who, 'cc': list(cc), 'chase': chase}, at=ago(days=8))
        return i

    def test_an_answer_records_how_many_days_it_took(self):
        s = MemoryStore(); i = self._answered(s, 'ray@northwind.example', 3)
        outcomes.resolve(s)
        f = json.loads(s._one('SELECT FactsJson FROM outcome WHERE Id=?', (i,))['FactsJson'])
        self.assertAlmostEqual(f['answer_days'], 3.0, delta=0.2)

    def test_person_facts_are_counts_from_the_rows(self):
        s = MemoryStore(); who = 'ray@northwind.example'
        for d, chase, cc in ((2, False, ()), (4, True, ('omar@northwind.example',)), (3, True, ('omar@northwind.example',))): self._answered(s, who, d, chase, cc)
        outcomes.resolve(s)
        outcomes.record(s, 'chase.let_go', 'message', 9, facts={'who': who}); outcomes.resolve(s)
        f = outcomes.person_facts(s, who)
        self.assertEqual((f['replies'], f['answered'], f['chased'], f['answered_after_chase'], f['let_go']), (3, 3, 2, 2, 1))
        self.assertAlmostEqual(f['median_days'], 3.0, delta=0.2)
        self.assertEqual(f['cc']['omar@northwind.example'], [2, 2])
        self.assertEqual(outcomes.chase_cc(s, who), 'omar@northwind.example')
        self.assertEqual(outcomes.person_facts(s, 'nobody@northwind.example')['replies'], 0)

    def test_late_after_needs_three_answers(self):
        s = MemoryStore(); who = 'gail@northwind.example'
        self._answered(s, who, 1); outcomes.resolve(s)
        self.assertEqual(outcomes.late_after(s, who), 5)                                   # one answer is not a habit
        self._answered(s, who, 1); self._answered(s, who, 2); outcomes.resolve(s)
        self.assertEqual(outcomes.late_after(s, who), 2)                                   # median 1 day -> 1.5 -> at least 2
        self.assertEqual(outcomes.late_after(s, who, default=9), 2)

    def test_a_persons_step_closing_records_who_and_how_late(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Schema sign-off', 'Status': 'waiting', 'Assignee': 'person:ray@northwind.example',
                           'DueAt': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')}, 'owner')
        s.update_task(t, {'Status': 'done'}, 'owner')
        f = json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])
        self.assertEqual((f['who'], f['late_days']), ('ray@northwind.example', 3))
        self.assertEqual(outcomes.person_facts(s, 'ray@northwind.example')['steps_late'], 1)
```

- [ ] **Step 2: Run** `python -m pytest tests/test_outcomes.py -q -k PersonFacts` → FAIL (`answer_days` missing / `person_facts` missing).

- [ ] **Step 3: Implement**

`taskuary/outcomes.py`: `KINDS` gains `'chase.let_go', 'chase.elsewhere'`. Add after `settle`:
```python
def update_facts(store, row_id: int, **more):
    r = store._one('SELECT FactsJson FROM outcome WHERE Id=?', (row_id,)) or {}
    f = json.loads(r.get('FactsJson') or '{}'); f.update(more)
    store._exec('UPDATE outcome SET FactsJson=? WHERE Id=?', (json.dumps(f), row_id))
```
In `_resolve_one`'s `reply.sent` branch, before the two `settle` calls: `if later: update_facts(store, r['Id'], answer_days=round(max(0.0, ((_dt(later[0]['SentAt']) or now) - at).total_seconds() / 86400), 1), answered_by=str(later[0].get('FromEmail') or '').lower())`. Add a branch: `if kind in ('chase.let_go', 'chase.elsewhere'): return settle(store, r['Id'], 'put down' if kind == 'chase.let_go' else f"answered elsewhere: {facts.get('where') or ''}".strip(), 'closed')`.

Append the readers:
```python
def _rows_who(store, who: str, kind: str = None) -> list:
    """Every row whose facts name this address - the person key the ledger carries (`who`), never a name."""
    q, p = "SELECT * FROM outcome WHERE json_extract(FactsJson, '$.who')=?", [str(who or '').lower()]
    if kind: q += ' AND Kind=?'; p.append(kind)
    return store._rows(q + ' ORDER BY Id', p)


def person_facts(store, who: str) -> dict:
    """What the ledger counts about one person: bookkeeping, no model. The page (people_pages.py) says what it means."""
    who = str(who or '').lower(); rs = [r for r in _rows_who(store, who) if r.get('ResolvedAt')]
    f = [(r, json.loads(r.get('FactsJson') or '{}')) for r in rs]
    replies = [x for x in f if x[0]['Kind'] == 'reply.sent']
    answered = [x for x in replies if x[1].get('answer_days') is not None]
    days = sorted(x[1]['answer_days'] for x in answered)
    cc = {}
    for r, x in replies:
        for a in x.get('cc') or []:
            c = cc.setdefault(str(a).lower(), [0, 0]); c[1] += 1; c[0] += 1 if x.get('answer_days') is not None else 0
    steps = [x for x in f if x[0]['Kind'] == 'task.closed']
    return {'replies': len(replies), 'answered': len(answered), 'answer_days': days,
            'median_days': (days[len(days) // 2] if len(days) % 2 else (days[len(days) // 2 - 1] + days[len(days) // 2]) / 2) if days else None,
            'chased': sum(1 for _, x in replies if x.get('chase')), 'answered_after_chase': sum(1 for _, x in answered if x.get('chase')),
            'steps': len(steps), 'steps_late': sum(1 for _, x in steps if (x.get('late_days') or 0) > 0),
            'let_go': sum(1 for r, _ in f if r['Kind'] == 'chase.let_go'), 'cc': cc}
def let_go_count(store, who: str) -> int: return len(_rows_who(store, who, 'chase.let_go'))


def late_after(store, who: str, default: int = 5) -> int:
    """The day a silence is late for THIS person: half again their median answer, two at least - once three answers say
    what their median is. Fewer is no habit: the default day (Settings -> Advisor)."""
    import math
    f = person_facts(store, who)
    return max(2, math.ceil(f['median_days'] * 1.5)) if f['answered'] >= 3 and f['median_days'] is not None else int(default)


def chase_cc(store, who: str):
    """The copied address that moved this person, when the ledger has seen it move them: two or more replies with them on
    copy and most of those answered. None otherwise - a chase copies nobody on a guess."""
    best = [(a, n, m) for a, (n, m) in person_facts(store, who)['cc'].items() if m >= 2 and n / m >= 0.6]
    return max(best, key=lambda x: (x[1] / x[2], x[2]))[0] if best else None
```

`taskuary/verdicts.py` `:238`: the facts dict gains `'who': str((msg or {}).get('FromEmail') or '').lower(), 'cc': [str(a).lower() for a in (sent.get('cc') or [])], 'chase': str(rv.get('Reason') or '').startswith('chase')`.

`taskuary/store.py` `update_task`: `was = (self._one('SELECT Status, Assignee, DueAt FROM task WHERE TaskId=?', ...) or {})` keeps the dict; the close door reads `was.get('Status')` and, when `str(was.get('Assignee') or '').startswith('person:')`, adds `who=was['Assignee'][7:].lower()`, `due=was.get('DueAt')`, `late_days=max(0, (date.today() - due).days)` (parse `DueAt[:10]`, skip when unparsable). Keep the existing condition (`was not in (None, 'done', 'dropped')`) on `was.get('Status')`.

- [ ] **Step 4: Run** `python -m pytest tests/test_outcomes.py tests/test_advisor.py -q` → PASS.

- [ ] **Step 5: Commit** `"The ledger learns who answered, how fast, after what, and who was copied"`.

---

### Task 2: A page per person, compiled at reflection, read with the dossier

**Files:**
- Create: `taskuary/people_pages.py`
- Modify: `taskuary/counsel.py` (`dossier`, the `if frm:` branch), `taskuary/learn.py` (`reflect`'s tail, after `learn_last_reflect` is set), `taskuary/server.py` (`GET /api/people/pages` beside `GET /api/people`), `website/src/SettingsView.jsx` (`docsTree` gains a People group; it is fed by `/api/people/pages`), `website/src/DocsView.jsx` (an unknown doc name draws with its own label)
- Test: `tests/test_people_pages.py` (new), `website/test/peopleDocs.test.mjs` (new, source regexes like `test/setupWalk.test.mjs`)

**Interfaces:**
- Produces: `people_pages.doc_name(who) -> str` (`person-<address>`); `people_pages.facts_text(store, who) -> str` (the numbers as lines); `people_pages.compile(store, who, llm=None) -> str|None` (the saved doc, None when the brain said nothing or there is no brain); `people_pages.refresh(store, llm=None, limit=5, days=30) -> list[str]` (addresses compiled: those with ≥3 resolved rows in the window, most first); `people_pages.splice(doc, body) -> str` (the marked block `<!-- ledger:start -->` … `<!-- ledger:end -->` replaced or appended); `people_pages.pages(store) -> list[{who, name, updated, lines}]`; `GET /api/people/pages`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_people_pages.py
"""A page per person from the outcome ledger (spec 2026-10-12, build step 4): the numbers are the ledger's, the lines
are the model's, the owner's own lines survive."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import counsel, outcomes, people_pages
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
WHO = 'ray@northwind.example'

def brain_saying(text):
    calls = []
    def llm(system, user, max_tokens=400, images=None, want=None, **kw): calls.append(user); return text
    llm.takes_want = False; llm.calls = calls; return llm

def seed(s, n=3):
    for k in range(n):
        t = s.create_task({'Title': f'thread {k}'}, 'owner'); cid = f'c{k}'
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'thread {k}', 'FromEmail': WHO, 'FromName': 'Ray Colton', 'SentAt': ago(days=12), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': f'Re: thread {k}', 'FromEmail': WHO, 'SentAt': ago(days=6), 'BodyText': 'a', 'Status': 'filed', 'TaskId': t})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': cid, 'mid': 1, 'verb': 'approve', 'who': WHO, 'cc': [], 'chase': k > 0}, at=ago(days=9))
    outcomes.resolve(s)


class PageTests(unittest.TestCase):
    def test_the_facts_are_the_ledgers_numbers(self):
        s = MemoryStore(); seed(s)
        txt = people_pages.facts_text(s, WHO)
        self.assertIn('3 replies', txt); self.assertIn('answered 3', txt); self.assertIn('median', txt)

    def test_compile_writes_the_doc_inside_the_block_and_the_dossier_reads_it(self):
        s = MemoryStore(); seed(s)
        llm = brain_saying('- Ray answers in about 3 days and needs a second chase [ev: out2, out3]\n- Copy nobody; he answers alone')
        name = people_pages.compile(s, WHO, llm=llm)
        self.assertEqual(name, 'person-ray@northwind.example')
        doc = s.get_doc(name)
        self.assertIn('<!-- ledger:start -->', doc); self.assertIn('needs a second chase', doc); self.assertIn('3 replies', doc)
        self.assertIn('median', llm.calls[0]); self.assertIn('out2', llm.calls[0])                 # the numbers and the evidence reach the model
        self.assertIn('needs a second chase', counsel.dossier(s, {'from_email': WHO, 'subject': 'anything'}, calendar=False))

    def test_the_owners_lines_survive_a_recompile(self):
        s = MemoryStore(); seed(s)
        people_pages.compile(s, WHO, llm=brain_saying('- first'))
        s.save_doc(people_pages.doc_name(WHO), 'Ray runs the data team. Call him, do not mail.\n\n' + s.get_doc(people_pages.doc_name(WHO)), 'owner')
        people_pages.compile(s, WHO, llm=brain_saying('- second'))
        doc = s.get_doc(people_pages.doc_name(WHO))
        self.assertIn('Call him, do not mail.', doc); self.assertIn('- second', doc); self.assertNotIn('- first', doc)
        s.save_doc(people_pages.doc_name(WHO), 'Only my words now.', 'owner')                     # the owner cut the block: it comes back at the end
        people_pages.compile(s, WHO, llm=brain_saying('- third'))
        self.assertTrue(s.get_doc(people_pages.doc_name(WHO)).startswith('Only my words now.'))

    def test_refresh_takes_the_people_with_three_rows_and_silence_writes_nothing(self):
        s = MemoryStore(); seed(s)
        other = 'gail@northwind.example'; t = s.create_task({'Title': 'y'}, 'owner')
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c9', 'mid': 1, 'verb': 'approve', 'who': other, 'cc': [], 'chase': False}, at=ago(days=9)); outcomes.resolve(s)
        self.assertEqual(people_pages.refresh(s, llm=brain_saying('- a line')), [WHO])            # one row is no page
        self.assertEqual(people_pages.pages(s)[0]['who'], WHO)
        self.assertIsNone(people_pages.compile(s, other, llm=brain_saying('')))
        with mock.patch.object(people_pages, 'build_llm', return_value=None): self.assertEqual(people_pages.refresh(s), [])
```

- [ ] **Step 2: Run** → `ImportError` on `people_pages`.

- [ ] **Step 3: Implement**

```python
# taskuary/people_pages.py
"""A page per person, derived from the outcome ledger (spec 2026-10-12, build step 4; the 2026-08-28 company-brain verdict:
compiled pages per sender, quoted as data). The NUMBERS are the ledger's (outcomes.person_facts); what they mean is the
model's, written at reflection inside a marked block so the owner's own lines on the page survive. Read by counsel.dossier,
which is how the reply drafter, triage's context, meeting prep and the Advisor's bigger read all see it."""
import re
from datetime import datetime, timedelta
from loguru import logger
from . import outcomes
from .llm import build_llm

START, END = '<!-- ledger:start -->', '<!-- ledger:end -->'
SYSTEM = ("You write the one page Taskuary keeps about a person the owner deals with, from the outcome ledger's facts about them. "
          "Return 3 to 10 markdown bullet lines, each one fact about how this person works with the owner - how fast they answer, "
          "whether a chase is needed, who on copy moves them, what they deliver late - each ending with the evidence ids in "
          "brackets like [ev: out12, out15]. Only what the numbers and the lines support; never a number the facts do not carry; "
          "nothing about their character. Return nothing at all when the facts say nothing yet.")

def doc_name(who: str) -> str: return f"person-{str(who or '').lower()}"
def who_of(name: str) -> str: return name[7:] if str(name or '').startswith('person-') else ''


def facts_text(store, who: str) -> str:
    f = outcomes.person_facts(store, who)
    lines = [f"{f['replies']} replies sent to them; answered {f['answered']}" + (f", median {f['median_days']:.1f} days" if f['median_days'] is not None else ''),
             f"{f['chased']} were chases; {f['answered_after_chase']} of those got an answer",
             f"{f['steps']} steps they owed closed; {f['steps_late']} late", f"let go {f['let_go']} times"]
    lines += [f"copied {a}: answered {n} of {m}" for a, (n, m) in f['cc'].items()]
    return '\n'.join(lines)


def splice(doc: str, body: str) -> str:
    """The marked block replaced in place, or appended when the page has none - the owner's lines are never touched."""
    block = f"{START}\n{body.strip()}\n{END}"
    doc = doc or ''
    if START in doc and END in doc:
        head, rest = doc.split(START, 1); return f"{head}{block}{rest.split(END, 1)[1]}"
    return (doc.rstrip('\n') + '\n\n' if doc.strip() else '') + block + '\n'


def compile(store, who: str, llm=None):
    who = str(who or '').lower()
    brain = llm or build_llm(store)
    if not brain: return None
    facts = facts_text(store, who)
    ev = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes._rows_who(store, who) if r.get('ResolvedAt')][-20:]
    text = str(brain(SYSTEM, f"PERSON: {who}\n\nTHE NUMBERS:\n{facts}\n\nTHE LINES:\n" + '\n'.join(ev), max_tokens=400) or '').strip()
    lines = [l for l in text.splitlines() if l.strip().startswith('-')]
    if not lines: return None
    stamp = datetime.now().strftime('%Y-%m-%d')
    body = f"_From the outcome ledger, {stamp}. The numbers are counted; the lines are read from them._\n\n" + '\n'.join(lines) + f"\n\n```\n{facts}\n```"
    name = doc_name(who)
    store.save_doc(name, splice(store.get_doc(name) or '', body), 'reflect')
    return name


def refresh(store, llm=None, limit: int = 5, days: int = 30) -> list:
    """At reflection: the people with three or more resolved rows in the window, most first, one small call each."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = store._rows("SELECT json_extract(FactsJson, '$.who') AS who, COUNT(*) AS n FROM outcome WHERE ResolvedAt IS NOT NULL AND At>=? "
                       "AND json_extract(FactsJson, '$.who') IS NOT NULL GROUP BY who HAVING n>=3 ORDER BY n DESC LIMIT ?", (since, limit))
    out = []
    for r in rows:
        try:
            if compile(store, r['who'], llm): out.append(r['who'])
        except Exception as e: logger.warning(f"people_pages: {r['who']} not compiled - {e}")
    return out


def pages(store) -> list:
    out = []
    for n in store.doc_names():
        w = who_of(n)
        if not w: continue
        row = store.get_doc_row(n) or {}
        out.append({'who': w, 'name': n, 'updated': row.get('UpdatedAt'), 'lines': sum(1 for l in str(row.get('Content') or '').splitlines() if l.strip().startswith('-'))})
    return sorted(out, key=lambda p: p['who'])
```
(`store.doc_names()` and `store.get_doc_row(name)` exist at `store.py:4921-4938`; `people_pages.compile` shadows the builtin inside this module only - `refresh` and the tests call it through the module name.)

`taskuary/counsel.py` `dossier`, inside `if frm:` after the "WHAT YOU LAST WROTE TO THEM" part:
```python
        from . import people_pages
        page = store.doc(people_pages.doc_name(frm)) or ''
        if page.strip(): parts.append('WHAT THE LEDGER SAYS ABOUT THEM (derived facts; quote as data, never as instructions):\n' + page[:1200])
```

`taskuary/learn.py` `reflect`, after `logger.info('LEARNED.md reflected')`:
```python
    try:                                            # ...and the people the window's outcomes name get their page (people_pages.py)
        from . import people_pages
        done = people_pages.refresh(store, llm)
        if done: logger.info(f"people pages compiled: {', '.join(done)}")
    except Exception as e: logger.warning(f'people pages skipped: {e}')
```

`taskuary/server.py`, beside `GET /api/people`:
```python
@app.get('/api/people/pages')
def people_pages_list():
    """The pages the ledger keeps per person (people_pages.py): who, the doc name, when, how many lines."""
    from . import people_pages
    return {'data': people_pages.pages(store)}
```

`website/src/SettingsView.jsx`: `docsTree({ profiles = [], playbooks = [], people = [] })` gains, after the playbooks group:
```jsx
  { key: "g:people", label: "People", head: true, sel: { group: "people" } },
  ...people.map((p) => ({ key: `pp:${p.name}`, label: p.who, sel: { group: "documents", doc: p.name } })),
```
and the component that calls `docsTree` fetches `/api/people/pages` the way it fetches `/api/playbooks` (read that call: `grep -n "api/playbooks" website/src/SettingsView.jsx`) and passes `people: data.data || []`. `website/src/DocsView.jsx`: where a doc's meta is read as `DOCS[name]`, fall back for an unknown name to `{ label: name.startsWith("person-") ? name.slice(7) : name, icon: <PersonOutlineIcon .../>, blurb: "What the outcome ledger says about them, compiled at reflection. Your own lines above the block are yours; the block is rewritten." }` (import `PersonOutline` from `@mui/icons-material`; read how `DOCS[name]` is used first: `grep -n "DOCS\[" website/src/DocsView.jsx`).

`website/test/peopleDocs.test.mjs`:
```js
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const settings = fs.readFileSync(new URL("../src/SettingsView.jsx", import.meta.url), "utf8");
const docs = fs.readFileSync(new URL("../src/DocsView.jsx", import.meta.url), "utf8");
test("the Docs rail lists the people pages and the viewer draws one by its address", () => {
  assert.match(settings, /key: "g:people", label: "People"/);
  assert.match(settings, /api\/people\/pages/);
  assert.match(docs, /person-/);
});
```

- [ ] **Step 4: Run** `python -m pytest tests/test_people_pages.py tests/test_outcomes.py tests/test_docs_and_llm.py -q` and `cd website && npm test && npm run build` → PASS; commit the bundle with it.

- [ ] **Step 5: Commit** `"A page per person from the outcome ledger: compiled at reflection, read with the dossier, listed under Docs"`.

---

### Task 3: The slipped lane: a quiet thread or step past that person's day

**Files:**
- Modify: `taskuary/lanes.json` (the `forgotten` entry), `taskuary/funnel.py` (`MUTED_LANES`, `_BAND_FALLBACK`, `_band`'s actionable lanes, `from_forgotten`), `taskuary/assistant.py` (`followups`: the action dict), `taskuary/processing_unread.py` (`card_for`, the `theirs` spot), `taskuary/settings_schema.json` (knob `slipped_default_days`, group Advisor, number, 5)
- Test: `tests/test_slipped.py` (new)

**Interfaces:**
- Consumes: `outcomes.late_after(store, who, default)`, `assistant.ooo(store)`.
- Produces: lane `forgotten` (word "slipped") is an owner lane, band 2, actionable; cards in it carry `who_email`, `late_days` (days past the person's day) and `why` ("Ray has been quiet 5 days - late for him after 3"); a follow-up idea's action gains `who_email`, `asked_at`, `away`; the setting `slipped_default_days` (5).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_slipped.py
"""The slipped lane (spec 2026-10-12, 'What was not followed up'): a thread or a step gone quiet past THAT person's day."""
import json
from datetime import datetime, timedelta
import pytest
from taskuary import assistant, funnel, outcomes, processing_unread, terminal
from taskuary.store import MemoryStore

def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
RAY = 'ray@northwind.example'

@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()

def rail(s):
    s.reconcile_processing_membership(); funnel.invalidate()
    return processing_unread.build(s, live_state=[], include_read=True)['items']

def person_step(s, days_past_due, who=RAY):
    return s.create_task({'Title': 'Schema sign-off', 'Status': 'waiting', 'Assignee': f'person:{who}', 'DueAt': (datetime.now() - timedelta(days=days_past_due)).strftime('%Y-%m-%d')}, 'owner')

def followup_idea(s, days_ago, who=RAY, away=False):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    mid = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': who, 'FromName': 'Ray Colton', 'SentAt': ago(days=days_ago + 1), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    return s.add_idea({'Kind': 'followup', 'Text': f'No answer from Ray in {days_ago} days on "Budget" - follow up?', 'Status': 'open', 'Sig': 'x',
                       'ActionJson': json.dumps({'type': 'followup', 'mid': mid, 'tid': t, 'who_email': who, 'asked_at': ago(days=days_ago), 'away': away})})


def test_a_step_past_the_persons_day_is_slipped_and_counted(s):
    t = person_step(s, 7)
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert (card['lane'], card['who_email'], card['late_days']) == ('forgotten', RAY, 2)       # default day 5: two days late
    assert 'quiet' in card['why'] and card['actionable']
    assert funnel.LANE_COUNTED['forgotten'] == 'slipped'

def test_a_step_inside_the_persons_day_is_still_theirs(s):
    t = person_step(s, 2)
    assert next(c for c in rail(s) if c.get('tid') == t)['lane'] == 'theirs'

def test_the_persons_own_day_comes_from_the_ledger(s):
    for k in range(3):
        t = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'z{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': [], 'chase': False, 'answer_days': 1.0}, at=ago(days=9))
        outcomes.settle(s, i, 'answered', 'settled')
    t = person_step(s, 3)                                                                   # late for Ray after 2 days
    assert next(c for c in rail(s) if c.get('tid') == t)['lane'] == 'forgotten'

def test_a_quiet_thread_past_the_day_is_slipped(s):
    iid = followup_idea(s, 6)
    card = next(c for c in rail(s) if c.get('idea') == iid)
    assert card['lane'] == 'forgotten' and card['late_days'] == 1

def test_someone_away_never_slips(s):
    iid = followup_idea(s, 20, away=True)
    assert next(c for c in rail(s) if c.get('idea') == iid)['lane'] != 'forgotten'

def test_followups_carry_the_address_and_the_day_asked(s):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(days=5), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    mid = s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=4), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
    s.put_sent_verdict(mid, 'c2', True, False, None, None, 'test')
    c = next(x for x in assistant.followups(s, 24, ('followup',)) if x['kind'] == 'followup')
    assert c['action']['who_email'] == RAY and c['action']['asked_at'][:10] == ago(days=4)[:10] and c['action']['away'] is False
```

(`store.add_idea` and `store.owner_last_words`/`put_sent_verdict` exist; confirm the idea row's column names with `grep -n "def add_idea" -A4 taskuary/store.py` and adjust the dict.)

- [ ] **Step 2: Run** `python -m pytest tests/test_slipped.py -q` → FAIL (lane `theirs`, no `who_email`).

- [ ] **Step 3: Implement**

`taskuary/lanes.json`: the `forgotten` entry becomes `{"key": "forgotten", "word": "slipped", "counted": "slipped", "role": "working", "mark": "🧵", "hint": "quiet past that person's usual day: chase, let it go, or say where they answered"}` (keep whatever other fields the entry has).

`taskuary/funnel.py`: `MUTED_LANES = ('fyi', 'report')` (with a comment: slipped is the owner's move since 2026-10-12); `_BAND_FALLBACK['forgotten'] = 2`; in `_band`, add `'forgotten'` to the `actionable=lane in (...)` tuple. In `from_forgotten`, after `lane, tri = idea_lane(i), ...`:
```python
        # SLIPPED (spec 2026-10-12): a follow-up quiet past THAT person's day is the owner's move, in the slipped lane - the day
        # is the ledger's (outcomes.late_after), the default the owner's (Settings -> Advisor); someone away never slips
        late = 0
        if i.get('Kind') == 'followup' and a.get('who_email') and a.get('asked_at') and not a.get('away'):
            from . import outcomes
            day = outcomes.late_after(store, a['who_email'], int(store.get_setting('slipped_default_days', 5) or 5))
            quiet = max(0, int((datetime.now() - (_dt(a['asked_at']) or datetime.now())).total_seconds() // 86400))
            if quiet >= day: lane, late = 'forgotten', quiet - day
```
and pass `who_email=a.get('who_email') or '', late_days=late` into the `_item(...)` call. (`_dt` exists in funnel; confirm with `grep -n "^def _dt" taskuary/funnel.py`, else use `_ts`'s neighbour.)

`taskuary/assistant.py` `followups`: the followup candidate's `'action'` dict gains `'who_email': (inbound.get('FromEmail') or '').lower(), 'asked_at': _ts(r['SentAt']), 'away': bool(gone)`.

`taskuary/processing_unread.py` `card_for`, right after the line that sets `card['lane'] = 'theirs'`:
```python
    # ...and a step a PERSON owes, quiet past its day plus that person's usual day, is SLIPPED: the owner's move (spec 2026-10-12)
    who = str(task.get('Assignee') or '')
    if card['lane'] == 'theirs' and who.startswith('person:') and str(task.get('DueAt') or '')[:10]:
        from . import outcomes
        from datetime import date
        try: due = date.fromisoformat(str(task['DueAt'])[:10])
        except ValueError: due = None
        if due:
            day = outcomes.late_after(store, who[7:], int(store.get_setting('slipped_default_days', 5) or 5))
            past = (now.date() - due).days - day
            if past >= 0:
                card.update(lane='forgotten', who_email=who[7:].lower(), late_days=past,
                            why=f"{holder_name(who)} has been quiet {(now.date() - due).days} days past {due:%b %d} - late for them after {day}")
```
(`now` is the build clock already in scope in `card_for`; `holder_name` is at `:182`.) Make sure a `forgotten` card is not folded into its goal: `FOLD_LANES` does not list it (check `grep -n "FOLD_LANES" taskuary/processing_unread.py taskuary/funnel.py`).

`taskuary/settings_schema.json`, in `knobs` before `assistant_producers`:
```json
    "slipped_default_days": {"group": "Advisor", "label": "Days of silence before a thread has slipped", "type": "number",
      "desc": "A thread you wrote on, or a step somebody owes, is 'slipped' - first on your rail, with Chase, Let it go, They answered elsewhere and Remind me - once it has been quiet this many days. For a person the outcome ledger has seen answer three times, their own usual day is used instead. 5 by default.",
      "help": "Someone whose auto-reply says they are away never slips. The day is read from the ledger, never from the mail."},
```

- [ ] **Step 4: Run** `python -m pytest tests/test_slipped.py tests/test_goals_rail.py tests/processing tests/test_funnel.py tests/test_settings_schema.py -q` → PASS (the rail fixtures in `tests/fixtures/rail_levels.json` may pin `forgotten` at band 4: read the failure and move it to 2, which is the spec's word).

- [ ] **Step 5: Commit** `"The slipped lane: a quiet thread or a step somebody owes, past that person's own day, is the owner's move"`.

---

### Task 4: The four answers

**Files:**
- Modify: `taskuary/toolcatalog.py` (`DECISIONS`), `taskuary/concierge.py` (`VERBS`, `CHIP_WORDS`, `CHIP_HINTS`, `NEEDS`, `SAYS_VERB`, `PROPOSALS`, `RECEIPTS`, `chips_for`, `propose_for`), `taskuary/operations.py` (`KINDS`), `taskuary/server.py` (`_run_operation`), `taskuary/assistant.py` (`followups`: three Let-it-gos silence the person), `taskuary/advisor.py` (`habit` gains `chase`)
- Test: `tests/test_slipped.py` (append)

**Interfaces:**
- Produces: verbs `chase` ("Chase them"), `let_go` ("Let it go"), `elsewhere` ("They answered elsewhere"); on a `forgotten` card `chips_for` gives `('chase', 'let_go', 'elsewhere', 'defer', 'next')`; operation kinds `task.chase` / `task.let_go` / `task.elsewhere`, target kind `item`, params `{'key', 'text'?}`; `task.chase` opens a reply draft on the thread's last inbound with Reason `chase:<n>` and an instruction in the owner's voice naming the ledger's cc when there is one, returning `{'reviewId', 'cc'}`; `task.let_go` closes a person step as `dropped` or puts a follow-up idea down, and records `chase.let_go` with `who`; `task.elsewhere` closes the step as `done` (its box ticks) or puts the idea down, with `text` as where, and records `chase.elsewhere`; `assistant.followups` skips a person with three or more `chase.let_go` rows; `advisor.habit(store, 'chase', item)` = answered-after-chase over chases.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_slipped.py
from unittest import mock
from taskuary import concierge, operations, server
from fastapi.testclient import TestClient

def run(s, kind, key, text=None):
    """Propose and execute one operation the way the card does, through the server's one handler."""
    with mock.patch.object(server, 'store', s):
        c = TestClient(server.app)
        op = c.post('/api/operations', json={'kind': kind, 'target': key, 'params': {'key': key, **({'text': text} if text else {})}}).json()
        return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})

def test_a_slipped_card_offers_the_four_answers(s):
    t = person_step(s, 7)
    card = next(c for c in rail(s) if c.get('tid') == t)
    assert [c['verb'] for c in concierge.chips_for(s, card)] == ['chase', 'let_go', 'elsewhere', 'defer', 'next']

def test_let_it_go_drops_the_step_and_writes_the_ledger(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    r = run(s, 'task.let_go', card['key'])
    assert r.status_code == 200, r.text
    assert s.get_task(t)['Status'] == 'dropped'
    assert [x['Kind'] for x in outcomes.rows_for(s, 'task', t)][:2] == ['chase.let_go', 'task.closed']
    assert json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])['who'] == RAY

def test_answered_elsewhere_closes_the_step_with_where(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    assert run(s, 'task.elsewhere', card['key'], 'he called').status_code == 200
    assert s.get_task(t)['Status'] == 'done'
    assert any('he called' in str(c.get('Body')) for c in s.list_comments(t))
    assert json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])['where'] == 'he called'

def test_three_let_gos_silence_one_person(s):
    for k in range(3): outcomes.record(s, 'chase.let_go', 'message', k, facts={'who': RAY})
    t = s.create_task({'Title': 'Budget'}, 'owner')
    for who, cid in ((RAY, 'c5'), ('gail@northwind.example', 'c6')):
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': who, 'SentAt': ago(days=5), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        mid = s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=4), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
        s.put_sent_verdict(mid, cid, True, False, None, None, 'test')
    whos = [c['action']['who_email'] for c in assistant.followups(s, 24, ('followup',))]
    assert whos == ['gail@northwind.example']

def test_a_chase_opens_a_draft_on_the_thread_with_the_ledgers_cc(s):
    iid = followup_idea(s, 6); card = next(c for c in rail(s) if c.get('idea') == iid)
    for k in range(2):
        t = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'y{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': ['omar@northwind.example'], 'chase': True, 'answer_days': 1.0}, at=ago(days=9))
        outcomes.settle(s, i, 'answered', 'settled')
    with mock.patch('taskuary.responder.write_draft', return_value='Ray - a quick nudge on the budget.') as wd:
        r = run(s, 'task.chase', card['key'])
    assert r.status_code == 200, r.text
    body = r.json(); rv = s.get_review(body['result']['reviewId'])
    assert rv['Reason'].startswith('chase:') and body['result']['cc'] == 'omar@northwind.example'
    assert 'omar' in (wd.call_args.kwargs.get('nudge') or '')

def test_a_chase_with_no_thread_is_refused_plainly(s):
    t = person_step(s, 7); card = next(c for c in rail(s) if c.get('tid') == t)
    r = run(s, 'task.chase', card['key'])
    assert r.status_code == 422 and 'task page' in r.json()['detail']

def test_the_advisor_counts_chases_from_the_ledger(s):
    for k, ans in enumerate((1.0, None, 2.0)):
        t = s.create_task({'Title': f'x{k}'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': f'w{k}', 'mid': 1, 'verb': 'approve', 'who': RAY, 'cc': [], 'chase': True, **({'answer_days': ans} if ans else {})}, at=ago(days=9))
        outcomes.settle(s, i, 'x', 'settled')
    from taskuary import advisor
    assert advisor.habit(s, 'chase', {}) == (2, 3)
```

(`/api/operations` takes `{kind, target, params}` - confirm the body field names with `grep -n "class OperationBody" -A4 taskuary/server.py`; `execute` returns `{'result': ...}` - confirm with `grep -n "def execute_operation" -A12 taskuary/server.py`.)

- [ ] **Step 2: Run** → FAIL on chips (no `chase`) and `KINDS`.

- [ ] **Step 3: Implement**

`taskuary/toolcatalog.py` `DECISIONS` gains:
```python
    'chase':           "chase the person who has gone quiet on the item - a short nudge in the owner's voice is drafted on the thread, copying whoever the ledger says moves them; nothing is sent",
    'let_go':          'let the quiet item go - the step somebody owed is dropped, or the follow-up is put down; three on one person and the Advisor stops raising them',
    'elsewhere':       "they answered elsewhere - `text`: where (a call, a meeting); the step somebody owed closes as done, or the follow-up is put down",
```
`taskuary/concierge.py`: `VERBS` gains `'chase', 'let_go', 'elsewhere'`; `CHIP_WORDS` gains `'chase': 'Chase them', 'let_go': 'Let it go', 'elsewhere': 'They answered elsewhere'`; `CHIP_HINTS` gains `'chase': 'Drafts a short nudge on the thread, in your voice, copying whoever the ledger says gets them to answer', 'let_go': 'Puts it down: the step is dropped or the follow-up closed; three on one person and the Advisor stops raising them', 'elsewhere': 'Say where they answered - the step closes as done'`; `NEEDS` gains `'chase': 'key', 'let_go': 'key', 'elsewhere': 'key'`; `SAYS_VERB` gains `'chase': 'chase', 'let_go': 'let go', 'elsewhere': 'close as answered elsewhere'`; `PROPOSALS` gains `'chase': ('task.chase', 'Chase them', False), 'let_go': ('task.let_go', 'Let it go', True), 'elsewhere': ('task.elsewhere', 'They answered elsewhere', True)`; `RECEIPTS` gains `'chase': "I'll draft the nudge - nothing goes out until you say so.", 'let_go': 'Put down.', 'elsewhere': 'Closed - they answered elsewhere.'`. In `chips_for`, after the goal-kind line: `if item.get('lane') == 'forgotten': verbs = ['chase', 'let_go', 'elsewhere', 'defer', 'next']` (and `cannot()` must accept `key` as a NEED: read `cannot` at `:644`; `key` is on every item). In `propose_for`, mirror the `'done'`/`'later'` branch (`item.settle`, target the item's key) for the three verbs with params `{'key': item['key'], 'text': text}` - read that branch (`grep -n "'item.settle'" taskuary/concierge.py`) and copy its shape.

`taskuary/operations.py` `KINDS` gains `'task.chase': ('item', ('key',), None), 'task.let_go': ('item', ('key',), None), 'task.elsewhere': ('item', ('key',), None)`.

`taskuary/server.py` `_run_operation`, beside `item.settle`:
```python
    if kind in ('task.chase', 'task.let_go', 'task.elsewhere'):
        # THE SLIPPED ANSWERS (spec 2026-10-12): each is an outcome. The item is the rail's card (a person's step, or a
        # follow-up idea); the person is its `who_email`, the ledger's key.
        from . import advisor, assistant, concierge, funnel, outcomes
        key = str(p.get('key') or ''); item = funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)
        if not item: raise HTTPException(404, 'that one is not on the rail any more')
        who, tid_, iid, text = str(item.get('who_email') or ''), item.get('tid'), item.get('idea'), str(p.get('text') or '').strip()[:300]
        if kind == 'task.chase':
            mid = item.get('mid') or (store.last_inbound_in(store.get_task(tid_)['ConversationId']) or {}).get('MessageId') if tid_ and (store.get_task(tid_) or {}).get('ConversationId') else item.get('mid')
            if not mid: raise HTTPException(422, 'There is no thread to chase on - write to them from the task page, and the ledger will count it.')
            n = sum(1 for r in outcomes.rows_for(store, 'task', tid_) if json.loads(r.get('FactsJson') or '{}').get('chase')) + 1 if tid_ else 1
            cc = outcomes.chase_cc(store, who) if who else None
            out = open_reply(mid, OpenReplyBody(instruction=f"a short chase, in my voice: no answer yet, what I need and by when" + (f"; copy {cc}, who gets them to answer" if cc else '')))
            store._exec("UPDATE review SET Reason=? WHERE ReviewId=?", (f'chase:{n}' + (f' cc:{cc}' if cc else ''), out['reviewId']))
            return {**out, 'cc': cc}
        if iid: assistant.act(store, iid, 'dismiss', ACTOR)
        elif tid_ and kind == 'task.let_go':
            store.add_comment(tid_, ACTOR, 'human', 'Let it go - nobody is chasing this further.'); store.update_task(tid_, {'Status': 'dropped'}, ACTOR)
        elif tid_:
            store.add_comment(tid_, ACTOR, 'human', f"Answered elsewhere{': ' + text if text else ''}."); store.update_task(tid_, {'Status': 'done'}, ACTOR)
        outcomes.record(store, 'chase.let_go' if kind == 'task.let_go' else 'chase.elsewhere', 'task' if tid_ else 'message', tid_ or item.get('mid') or 0, ACTOR,
                        facts={'who': who, **({'where': text} if text else {})})
        return {'status': 'dropped' if kind == 'task.let_go' else 'done', 'who': who}
```
(`OpenReplyBody` has `instruction`; `open_reply` returns `{'reviewId', 'taskId', 'draft', 'drafting'}` - `server.py:2374-2430`. `store.last_inbound_in(conversation_id)` is at `store.py:2181`. `json` is imported in server.py; confirm.)

`taskuary/assistant.py` `followups`: when building the followup candidate, skip when `outcomes.let_go_count(store, (inbound.get('FromEmail') or '').lower()) >= 3` (import `outcomes` locally; comment: "three Let-it-gos on one person and the Advisor stops raising them - the spec's one rule about silence").

`taskuary/advisor.py` `habit`: add `'chase': ("SELECT FactsJson AS f FROM outcome WHERE Kind='reply.sent' AND ResolvedAt IS NOT NULL AND json_extract(FactsJson,'$.chase')=1", lambda r: json.loads(r['f'] or '{}').get('answer_days') is not None)`.

- [ ] **Step 4: Run** `python -m pytest tests/test_slipped.py tests/test_concierge.py tests/test_assistant_reactions.py tests/test_advisor.py tests/test_task_tools.py -q` → PASS (`test_concierge.py` pins the VERBS/DECISIONS mirror: both lists change together).

- [ ] **Step 5: Commit** `"The slipped card's four answers: Chase, Let it go, They answered elsewhere, Remind me - each an outcome"`.

---

### Task 5: The brief, the docs, the bundle

**Files:**
- Modify: `taskuary/assistant.py` (the followup candidate's `facts` names the person's day), `docs/site/advisor.md` (a "What was not followed up" section; the built list), `docs/site/how-it-works.md` (the Goals band sentence mentions slipped), `README.md` (one sentence in the memory section)
- Build: `cd website && npm run build:docs && npm run build`; full pytest suite.

- [ ] **Step 1: Failing test** - append to `tests/test_slipped.py`:
```python
def test_the_followup_line_names_the_persons_day(s):
    t = s.create_task({'Title': 'Budget'}, 'owner')
    s.add_message({'ConversationId': 'c7', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': RAY, 'FromName': 'Ray Colton', 'SentAt': ago(days=8), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
    mid = s.add_message({'ConversationId': 'c7', 'Channel': 'email', 'Subject': 'Re: Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=7), 'BodyText': 'Can you send it?', 'Status': 'context', 'TaskId': t})
    s.put_sent_verdict(mid, 'c7', True, False, None, None, 'test')
    c = next(x for x in assistant.followups(s, 24, ('followup',)) if x['kind'] == 'followup')
    assert 'late for them after 5 days' in c['facts']
```
- [ ] **Step 2: Run** → FAIL. **Step 3:** in `followups`, the followup `'facts'` string gains `f" Late for them after {day} days." ` where `day = outcomes.late_after(store, who_email, int(store.get_setting('slipped_default_days', 5) or 5))`, so the morning brief's MY OPEN LOOPS line carries the person's day (the brief reads `facts`). Docs: `advisor.md` gains, after "Seeing what it did", a section `## What was not followed up` from the spec's paragraph, written as built: the slipped lane inside On you, the count, the card as the thread with the chase drafted in your voice and the ledger's copy, the four answers and what each writes to the ledger, three Let-it-gos silencing one person, a reply arriving ending it, the morning brief carrying the same facts; and the page per person under "The outcome ledger" ("Facts about other people go to a page per person" is now built: compiled at reflection, read with the dossier, listed under Settings → Docs → People, your own lines above the block are kept). Move "per-person pages and a per-person chase ladder, with the slipped thread's four answers" from Next to Built. `README.md`'s memory section: one sentence "It also keeps a page per person it deals with, compiled from the same ledger: how fast they answer, whether a chase is needed, who on copy moves them."
- [ ] **Step 4: Run** `python -m pytest tests/test_slipped.py -q`; `cd website && npm run build:docs && npm test && npm run build`; then the full suite from the repo root.
- [ ] **Step 5: Commit** `"The brief names each person's day; the docs say the people pages and the slipped answers are built"`.

---

## Self-review

**Spec coverage:** person facts in the ledger and the page per person (T1, T2); the per-person chase ladder as the person's own late day replacing the global steps for when a silence first slips (T3; the five global steps stay for how often a quiet idea is re-said); the slipped lane inside On you with its count (T3); the card's four answers, each an outcome, the chase drafted in the owner's voice with the ledger's copy, three Let-it-gos silencing one person (T4); the morning brief carrying the same facts (T5). Left out, on purpose and said in the docs: several late at once as one batch ("Chase all three") - the fyi batch grammar is for reading, not acting, and a chase needs a draft each; the Advisor's "A reply arriving is an event: the row goes" is already true (the follow-up idea closes when a reply arrives: `from_forgotten`'s `sent_reply_for` check, and a `person:` step's lane leaves `forgotten` when its status moves).

**Placeholders:** none; four steps ask the implementer to confirm a name by grep before using it, each with the grep.

**Type consistency:** `who` is always a lowercase address; `late_after(store, who, default)` everywhere; `person_facts` keys as listed; operation params `{'key', 'text'?}`.

**Review Focus:** each line has its test (T3 ×1, T4 ×2, T1 ×1, T2 ×1).

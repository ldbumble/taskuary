# Task close slots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A task can say what closes it - N addressed email slots on its checklist - and stays open until every slot is sent or dropped, with the task page showing each slot's draft.

**Architecture:** A slot is a checklist item with `out` + `rid`. Its draft is a review row of a NEW kind, `slot`, carrying `Deliver {channel,to,subject,slot}` - the same outgoing-email row `outbox.compose` files, approved and sent by the same `verdicts.decide`. The distinct kind is what keeps every existing "the task's reply" lookup (`pending_review`, `hold_reviews`, `agent_reply`, the close-out redirect) from ever picking a slot up. Closing reuses `proposals.closed_out`'s playbook pattern.

**Tech Stack:** Python 3 / FastAPI / SQLite (`taskuary/`), pytest (`tests/`), React + MUI (`website/src/`), esbuild bundle committed.

**Spec:** `docs/superpowers/specs/2026-10-05-task-close-slots-design.md`

## Global Constraints

- A task with NO slots behaves exactly as before - every existing test passes unchanged.
- Slot kinds are a closed list in code: `('email',)`. The model only picks; code validates. No word lists.
- `out.to` is never guessed into an address: an unresolved name is kept as said.
- Nothing is sent without the owner's approve - a slot draft is a pending review like every other.
- Invented people only in tests, fixtures, comments and commits (CLAUDE.md): `*.example` / `example.com` addresses, Alex Doyle / Erin Blake / Gail Moreno / Paula Vance / Ray Colton.
- Code style: match the surrounding file (dense, one idea per line, comments say why).
- No autoformatters. Lines under ~160 chars.
- Commits go through a temp index (shared checkout - concurrent agents share `.git/index`):
  `export GIT_INDEX_FILE=$(mktemp); git read-tree HEAD; git add <files>; t=$(git write-tree); o=$(git rev-parse HEAD); c=$(git commit-tree $t -p $o -m "<msg>"); git update-ref refs/heads/master $c $o; rm $GIT_INDEX_FILE; unset GIT_INDEX_FILE; git reset -q -- <files>`
  Every message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Push only after the WHOLE suite passes from the repo root (`python -m pytest -q -x -p no:cacheprovider`); "no tests ran" is a failure.

## Review Focus

1. A slot draft on a MAIL-born task (one with inbound messages) must still send: `verdicts.context_moved` reads a review with no `MessageId` and no `ContextRevision` as moved whenever the task has inbound mail. The slot draft is pinned with `ContextRevision` at filing - Task 3 pins this.
2. Approving the task's REPLY while a close-out is pending must never send a slot draft instead: the close-out redirect's `Kind<>'action'` reply lookup - Task 2 pins this.
3. `no_reply` / `close_unsent` on a slot draft must drop THAT slot, not close the whole task (both close it today) - Task 2 pins this.
4. The owner rewording an unrelated checklist item must not strip `out`/`rid` from the slots - Task 1 pins this.
5. An agent run ending on a typed task with slots unfilled must not end `done` (which supersedes the drafts) - Task 2 pins this.

---

### Task 1: Slots on the checklist (store + `slots.py` core)

**Files:**
- Create: `taskuary/slots.py`
- Modify: `taskuary/store.py` (`REVIEW_COLS` :56, `set_task_checklist` ~:1556, `checklist_markdown` ~:1600, `pending_review` ~:4072, `sent_reply` ~:4080)
- Test: `tests/test_close_slots.py`

**Interfaces:**
- Produces: `slots.KINDS`, `slots.KIND` (`'slot'` - the review kind), `slots.clean(outputs) -> list[dict]`, `slots.add(store, tid, outputs, actor) -> list[dict]`, `slots.open_(store, tid) -> list[dict]`, `slots.of_review(rv) -> str|None`, `slots.mark(store, tid, slot_id, rid=None, done=None, actor='owner')`.
- `store.add_checklist_items(tid, items: list[dict], actor) -> list[dict]` - appends ready-made items (`{text, out}`), ids assigned like `merge_task_checklist`.

- [ ] **Step 1: Write the failing tests**

```python
"""A task says what closes it: output slots on the checklist (spec 2026-10-05-task-close-slots-design.md).

The shape: one ask, four addressed drafts, each approved on its own, the task closing when the last is sent.
"""
import json
from unittest import mock

import pytest

from taskuary import slots
from taskuary.store import MemoryStore

FOUR = [{'to': 'paula@northwind.example', 'about': 'where tab 1 stands'}, {'to': 'ray@northwind.example', 'about': 'where tab 2 stands'},
        {'to': 'Gail Moreno', 'about': 'where tab 3 stands'}, {'to': 'erin@northwind.example', 'about': 'where tab 4 stands'}]


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def typed(s, outputs=FOUR):
    tid = s.create_task({'Title': 'Check the four tabs', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    s.set_task_checklist(tid, ['Check the four tabs'], 'owner')
    slots.add(s, tid, outputs, 'owner')
    return tid


def test_clean_keeps_known_kinds_and_drops_junk():
    got = slots.clean([{'to': 'a@example.com', 'about': 'x'}, {'to': '', 'about': 'y'}, 'nope', {'about': 'z'},
                       {'to': 'b@example.com', 'about': 'w', 'kind': 'fax'}])
    assert [g['out'] for g in got] == [{'kind': 'email', 'to': 'a@example.com', 'subject': ''}]


def test_slots_ride_on_the_checklist(s):
    tid = typed(s)
    items = s.task_checklist(tid)
    assert len(items) == 5 and items[0].get('out') is None
    assert [i['out']['to'] for i in items[1:]] == [o['to'] for o in FOUR]
    assert len(slots.open_(s, tid)) == 4


def test_a_name_is_kept_as_said_never_guessed_into_an_address(s):
    tid = typed(s)
    assert slots.open_(s, tid)[2]['out']['to'] == 'Gail Moreno'


def test_rewording_another_item_keeps_the_slots(s):
    tid = typed(s); before = s.task_checklist(tid)
    slots.mark(s, tid, before[1]['id'], rid=77)
    s.set_task_checklist(tid, ['Check all four tabs'] + [i['text'] for i in before[1:]], 'owner')
    after = s.task_checklist(tid)
    assert after[1]['out'] == before[1]['out'] and after[1]['rid'] == 77


def test_the_agent_sees_its_slots_and_how_to_fill_them(s):
    tid = typed(s); sid = slots.open_(s, tid)[0]['id']
    md = s.checklist_markdown(tid)
    assert 'email to paula@northwind.example' in md and f'--slot {sid}' in md


def test_a_slot_draft_is_never_the_tasks_reply(s):
    tid = typed(s)
    s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': 'hi',
                  'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'subject': 'Tab 1', 'slot': 'x'})})
    assert s.pending_review(tid) is None and s.pending_review(tid, live_only=False) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_close_slots.py -q -p no:cacheprovider`
Expected: FAIL - `ImportError: cannot import name 'slots'`.

- [ ] **Step 3: Implement `taskuary/slots.py`**

```python
"""What closes a task: output slots on its checklist (docs/superpowers/specs/2026-10-05-task-close-slots-design.md).

A task's ending used to be implied by where it came from - one reply to its sender. An ask whose result is several
messages to several people had nowhere to live, and the first send closed the task and superseded the rest. A slot is
a checklist item that names one output; the task stays open until every slot is sent or dropped (proposals.closed_out).

Its draft is a review of kind `slot`, never `draft_reply`: every "the task's reply" lookup (pending_review, hold_reviews,
agent_reply, the close-out redirect) reads draft kinds, so a slot can never be mistaken for the reply or overwritten by it.
"""
import json

KINDS = ('email',)            # what a slot can be - a new kind is a new entry here, never a branch elsewhere
KIND = 'slot'                 # the review kind of a slot's draft


def clean(outputs) -> list:
    """Model or caller outputs -> checklist items. Unknown kinds and slots with nobody to send to are dropped."""
    out = []
    for o in outputs if isinstance(outputs, (list, tuple)) else []:
        if not isinstance(o, dict): continue
        to, about, kind = ' '.join(str(o.get('to') or '').split())[:200], ' '.join(str(o.get('about') or '').split())[:200], o.get('kind') or 'email'
        if not to or kind not in KINDS: continue
        out.append({'text': f'Email {to}' + (f' - {about}' if about else ''), 'out': {'kind': kind, 'to': to, 'subject': str(o.get('subject') or '')[:200]}})
    return out


def add(store, tid: int, outputs, actor: str) -> list:
    """Append these outputs as slots; one already open to the same person is not added twice."""
    have = {str(i['out'].get('to')).casefold() for i in open_(store, tid)}
    new = [i for i in clean(outputs) if i['out']['to'].casefold() not in have]
    return store.add_checklist_items(tid, new, actor) if new else []


def all_(store, tid: int) -> list: return [i for i in store.task_checklist(tid) if isinstance(i.get('out'), dict)]
def open_(store, tid: int) -> list: return [i for i in all_(store, tid) if not i.get('done')]


def of_review(rv) -> str | None:
    """The slot a review fills, or None for every other review."""
    if not rv or rv.get('Kind') != KIND: return None
    try: return (json.loads(rv.get('Deliver') or '{}') or {}).get('slot')
    except (TypeError, ValueError): return None


def mark(store, tid: int, slot_id: str, rid: int = None, done: bool = None, actor: str = 'owner') -> bool:
    items = store.task_checklist(tid)
    hit = next((i for i in items if i.get('id') == slot_id and isinstance(i.get('out'), dict)), None)
    if not hit: return False
    if rid is not None: hit['rid'] = int(rid)
    if done is not None: hit['done'] = bool(done)
    store._write_checklist(tid, items, actor)
    return True
```

- [ ] **Step 4: Store changes**

In `taskuary/store.py`:

`REVIEW_COLS` (:56) - add `'ContextRevision'` so a slot draft can be pinned at filing (Review Focus 1):
```python
REVIEW_COLS = ('TaskId', 'MessageId', 'RunId', 'Kind', 'DraftText', 'FinalText', 'Status', 'Reason', 'Deliver', 'ContextRevision')
```

`set_task_checklist` - the item it builds keeps a retained item's slot fields. Replace the `items.append(...)` line:
```python
            items.append({'id': item_id, 'text': text, 'done': bool(prior.get('done')),
                          **{k: prior[k] for k in ('out', 'rid') if k in prior}})     # a slot keeps what it sends and its draft
```

After `merge_task_checklist`, add:
```python
    def add_checklist_items(self, task_id, ready: list, actor: str) -> list:
        """Append ready-made items ({text, out}) - output slots (slots.add); ids as merge_task_checklist gives them."""
        items = self.task_checklist(task_id)
        have, used_ids, new = {i['text'] for i in items}, {i.get('id') for i in items}, []
        for r in ready:
            text = str(r.get('text') or '').strip()[:300]
            if not text or text in have: continue
            digest = hashlib.sha1(text.encode()).hexdigest()
            item_id = next((digest[:n] for n in range(8, len(digest) + 1) if digest[:n] not in used_ids), digest)
            new.append({'id': item_id, 'text': text, 'done': False, **({'out': r['out']} if r.get('out') else {})})
            have.add(text); used_ids.add(item_id)
        if new: self._write_checklist(task_id, items + new, actor)
        return new
```

`checklist_markdown` - a slot says where it goes and how to fill it (the seed line is byte-capped, so the command rides here):
```python
    def checklist_markdown(self, task_id) -> str:
        def line(i):
            o = i.get('out') if isinstance(i.get('out'), dict) else None
            tail = (f" -> email to {o.get('to')}, " + ('drafted' if i.get('rid') else f"fill with `taskuary --draft --slot {i['id']} \"<text>\"`")) if o else ''
            return f"- [{'x' if i.get('done') else ' '}] {i['text']}{tail}"
        return '\n'.join(line(i) for i in self.task_checklist(task_id))
```

`pending_review` - a slot draft is never the task's reply unless asked for by kind:
```python
        if kind:      q += ' AND rv.Kind=?'
        else:         q += " AND rv.Kind<>'slot'"
```

`sent_reply` - add `"rv.Kind<>'slot'"` to the `where` list beside `"rv.Kind<>'action'"`.

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest tests/test_close_slots.py tests/test_task_checklist.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit** - `taskuary/slots.py taskuary/store.py tests/test_close_slots.py`, message `A task's checklist can hold output slots`.

---

### Task 2: Closing waits for every slot

**Files:**
- Modify: `taskuary/proposals.py` (`closed_out` ~:201)
- Modify: `taskuary/verdicts.py` (`decide` ~:368-500, `_settle_task_after_sent_reply` ~:278)
- Modify: `taskuary/coder.py` (`finish` ~:307)
- Test: `tests/test_close_slots.py`

**Interfaces:**
- Consumes: `slots.open_`, `slots.of_review`, `slots.mark`, `slots.KIND`.
- Produces: `slots.settled(store, rv, sent: bool, actor) -> bool` (ticks the slot; True when the task closed).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_close_slots.py`)

```python
from taskuary import coder, operations, proposals, verdicts, outbound


def draft(s, tid, i, text='Tab is fine.'):
    sid = slots.all_(s, tid)[i]['id']
    rid = s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': text,
                        'ContextRevision': operations.message_revision(s, tid),
                        'Deliver': json.dumps({'channel': 'email', 'to': [slots.all_(s, tid)[i]['out']['to']], 'subject': 'Tab', 'slot': sid})})
    slots.mark(s, tid, sid, rid=rid)
    return rid


def approve(s, rid):
    with mock.patch('taskuary.outbound.send_out', return_value={'channel': 'email', 'to': ['x@example.com'], 'cc': []}), \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learn.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def test_four_slots_stay_open_through_three_sends_and_close_on_the_fourth(s):
    tid = typed(s); rids = [draft(s, tid, n) for n in range(4)]
    for rid in rids[:3]:
        assert approve(s, rid)['ok'] and s.get_task(tid)['Status'] != 'done'
    assert all(s.get_review(r)['Status'] == 'pending' for r in rids[3:])
    assert approve(s, rids[3])['ok'] and s.get_task(tid)['Status'] == 'done'


def test_a_rejected_slot_is_dropped_and_counts_as_settled(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    verdicts.decide(s, s.get_review(a), 'reject')
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'
    approve(s, b)
    assert s.get_task(tid)['Status'] == 'done'


@pytest.mark.parametrize('verb', ['no_reply', 'close_unsent'])
def test_not_sending_one_slot_drops_that_slot_not_the_task(s, verb):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    verdicts.decide(s, s.get_review(a), verb)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'


def test_a_reply_and_slots_close_only_when_both_are_settled(s):
    from tests.test_review_delivery_safety import make_review
    tid, mid, reply = make_review(s, task_kind='reply'); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['erin@example.com'], 'cc': []}), \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(reply), 'approve')
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(a)['Status'] == 'pending'
    approve(s, a)
    assert s.get_task(tid)['Status'] == 'done'


def test_a_task_without_slots_closes_on_its_reply_as_before(s):
    from tests.test_review_delivery_safety import make_review
    tid, mid, reply = make_review(s, task_kind='reply')
    with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'email', 'to': ['erin@example.com'], 'cc': []}), \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(reply), 'approve')
    assert s.get_task(tid)['Status'] == 'done'


def test_the_reply_lookup_never_picks_a_slot_draft(s):
    from tests.test_review_delivery_safety import make_review
    tid, mid, reply = make_review(s, task_kind='reply'); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    got = s._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action','slot') ORDER BY ReviewId DESC LIMIT 1", (tid,))
    assert got['ReviewId'] == reply


def test_a_finished_run_with_slots_open_waits_instead_of_closing(s):
    tid = typed(s, FOUR[:2]); draft(s, tid, 0)
    prev, coder.REFRESH = coder.REFRESH, None
    try: coder.finish(s, tid, {'summary': 'checked', 'outcome': 'did_work'})
    finally: coder.REFRESH = prev
    assert s.get_task(tid)['Status'] == 'waiting'
    assert [r['Status'] for r in s._rows("SELECT Status FROM review WHERE TaskId=?", (tid,))] == ['pending']
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_close_slots.py -q -p no:cacheprovider`
Expected: the closing tests FAIL (the first send closes the task; `no_reply` closes it).

- [ ] **Step 3: `slots.settled` in `taskuary/slots.py`**

```python
def settled(store, rv: dict, sent: bool, actor: str) -> bool:
    """A slot's draft was sent (or dropped): tick the slot, then close the task if nothing else of it waits.
    The same gate the reply goes through (proposals.closed_out) - whichever lands last closes it."""
    sid, tid = of_review(rv), rv.get('TaskId')
    if not (sid and tid): return False
    mark(store, tid, sid, done=True, actor=actor)
    if (store.get_task(tid) or {}).get('Status') in ('done', 'dropped'): return False
    left = len(open_(store, tid))
    reply = store._one("SELECT 1 x FROM review WHERE TaskId=? AND Status='pending' AND Kind NOT IN ('action', ?) LIMIT 1", (tid, KIND))
    said = f"{'Sent' if sent else 'Dropped'}: {rv.get('Reason') or 'one of its emails'}."
    if left or reply:
        store.add_comment(tid, actor, 'human', f"{said} {left} email{'s' if left != 1 else ''} still to go" + (' and the reply' if reply else '') + '.')
        return False
    from . import proposals
    return proposals.closed_out(store, tid, actor, said)
```

- [ ] **Step 4: `proposals.closed_out` - the slot guard beside the playbook one**

```python
def closed_out(store, tid: int, actor: str, said: str) -> bool:
    """...(docstring unchanged)..."""
    from . import slots
    left = slots.open_(store, tid)
    # ...and while its output slots wait (2026-10-05): four drafted emails, and the first send closed the task and
    # superseded the other three. The task closes when the last slot is sent or dropped (slots.settled).
    if left:
        store.audit('task', tid, 'closed_out', actor)
        store.add_comment(tid, actor, 'human', f"{said} The task closes when its {len(left)} remaining email{'s' if len(left) != 1 else ''} are sent or dropped.")
        return False
    if playbook_pending(store, tid):
        ...unchanged...
```

- [ ] **Step 5: `verdicts.decide` - four slot doors**

(a) The close-out redirect never fires for a slot, and its reply lookup never picks one. In the `# ONE CLOSE OUT, WHICHEVER CARD` block add `and rv.get('Kind') != 'slot'` to the condition, i.e. `rv.get('Kind') not in ('action', 'clarification', 'slot')`. In the `reply_text is not None` block change the query's `Kind<>'action'` to `Kind NOT IN ('action','slot')`.

(b) `close_unsent` on a slot drops the slot. At the top of the `if verb_in == 'close_unsent':` block:
```python
        if rv.get('Kind') == 'slot':
            if not store.decide_review(rid, 'closed_unsent', rv.get('DraftText'), actor, str(note or '').strip() or 'not sent'): return _delivery_busy(store, rid)
            from . import slots
            slots.settled(store, rv, False, actor)
            return {'ok': True, 'status': 'closed_unsent', 'sent': None, 'send_error': None}
```

(c) `no_reply` / `reject` on a slot drops the slot instead of closing the task. Replace
```python
    if verb == 'no_reply' and rv.get('TaskId'):
```
with
```python
    if rv.get('Kind') == 'slot' and verb in ('reject', 'no_reply'):
        from . import slots
        slots.settled(store, rv, False, actor)
    elif verb == 'no_reply' and rv.get('TaskId'):
```

(d) A sent slot ticks itself. At the top of `_settle_task_after_sent_reply`, after `if kind == 'action': return`:
```python
    if kind == 'slot':
        from . import slots
        if was_sent: slots.settled(store, rv, True, actor)
        return
```

- [ ] **Step 6: `coder.finish` - a run with open slots waits**

Change the status line (~:307):
```python
    from . import slots
    if not keep_open: store.update_task(task_id, {'Status': 'waiting' if (mid or due or slots.open_(store, task_id)) else 'done'}, actor)
```

- [ ] **Step 7: Run to verify they pass**

Run: `python -m pytest tests/test_close_slots.py tests/test_review_delivery_safety.py tests/test_verdict_paths.py tests/test_agent_reply.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 8: Commit** - `taskuary/slots.py taskuary/proposals.py taskuary/verdicts.py taskuary/coder.py tests/test_close_slots.py`, message `A task with output slots closes when the last one is sent`.

---

### Task 3: The agent fills slots (`--draft` and `[[TASKUARY-DRAFT]]`)

**Files:**
- Modify: `taskuary/slots.py` (add `draft`)
- Modify: `taskuary/server.py` (beside `/api/agent/reply` ~:3236)
- Modify: `taskuary/guard.py:112`
- Modify: `taskuary/cli.py` (~:132 args, ~:156 handler)
- Modify: `taskuary/selfclose.py` (beside `REPLY_LINE` ~:241)
- Modify: `taskuary/general.py` (~:556 system line, ~:1026 marker)
- Test: `tests/test_close_slots.py`, `tests/test_guard.py` (only if it pins the allow-list text)

**Interfaces:**
- Consumes: `slots.add`, `slots.open_`, `slots.mark`, `slots.KIND`, `operations.message_revision`.
- Produces: `slots.draft(store, tid, text, to='', subject='', slot='', agent='agent') -> dict` (`{'ok', 'review_id', 'slot', 'added'}` or `{'ok': False, 'why'}`); `selfclose.draft_markers(text) -> (cleaned, [(attrs: dict, body: str)])`; `selfclose.DRAFT_LINE`.

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient
from taskuary import selfclose


def test_the_agent_fills_a_slot_by_id(s):
    tid = typed(s, FOUR[:2]); sid = slots.open_(s, tid)[1]['id']
    out = slots.draft(s, tid, 'Tab 2 is short by one feed.', slot=sid, agent='assistant')
    rv = s.get_review(out['review_id'])
    assert (rv['Kind'], rv['Status'], rv['DraftBy'], slots.of_review(rv)) == (slots.KIND, 'pending', 'agent:assistant', sid)
    assert json.loads(rv['Deliver'])['to'] == ['ray@northwind.example'] and rv['ContextRevision']


def test_by_recipient_and_again_rewrites_the_same_draft(s):
    tid = typed(s, FOUR[:1])
    a = slots.draft(s, tid, 'first', to='PAULA@northwind.example'); b = slots.draft(s, tid, 'second', to='paula@northwind.example')
    assert a['review_id'] == b['review_id'] and s.get_review(a['review_id'])['DraftText'] == 'second'


def test_an_unmatched_recipient_adds_a_slot_and_says_so(s):
    tid = typed(s, FOUR[:1])
    out = slots.draft(s, tid, 'Tab 5 too.', to='omar@northwind.example', subject='Tab 5')
    assert out['added'] and len(slots.all_(s, tid)) == 2
    assert any('added' in c['Body'] for c in s.list_comments(tid))


def test_empty_text_or_nobody_is_refused(s):
    tid = typed(s, FOUR[:1])
    assert not slots.draft(s, tid, '  ', slot=slots.open_(s, tid)[0]['id'])['ok']
    assert not slots.draft(s, tid, 'hi')['ok']


def test_a_slot_draft_on_a_mail_task_still_sends(s):
    from tests.test_review_delivery_safety import make_review
    tid, mid, _ = make_review(s, task_kind='task'); slots.add(s, tid, FOUR[:1], 'owner')
    out = slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')
    assert verdicts.context_moved(s, s.get_review(out['review_id']))[0] is False


def test_the_chat_block_is_read_and_taken_out():
    text, found = selfclose.draft_markers('Done.\n[[TASKUARY-DRAFT to=paula@northwind.example subject="Tab 1"]]Tab 1 is fine.[[/TASKUARY-DRAFT]]')
    assert text == 'Done.' and found == [({'to': 'paula@northwind.example', 'subject': 'Tab 1'}, 'Tab 1 is fine.')]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_close_slots.py -q -p no:cacheprovider -k "draft or chat_block or recipient or refused"`
Expected: FAIL - `AttributeError: module 'taskuary.slots' has no attribute 'draft'`.

- [ ] **Step 3: `slots.draft`**

```python
def draft(store, tid: int, text: str, to: str = '', subject: str = '', slot: str = '', agent: str = 'agent') -> dict:
    """The agent that did the work writes one output itself - the slot named by id, else the open one to the same person,
    else a slot it adds (said on the task: the owner sees the list grow). Nothing is sent: the owner approves it."""
    from . import operations
    text = str(text or '').strip()
    if not text: return {'ok': False, 'why': 'no email text'}
    want = str(to or '').strip().casefold()
    hit = next((i for i in all_(store, tid) if slot and i['id'] == slot), None) or \
          next((i for i in open_(store, tid) if want and str(i['out'].get('to')).casefold() == want), None)
    added = False
    if not hit:
        if not want: return {'ok': False, 'why': 'name the slot (--slot) or who it goes to (--to)'}
        made = add(store, tid, [{'to': to, 'about': subject}], f'agent:{agent}')
        if not made: return {'ok': False, 'why': f'could not add a slot for {to}'}
        hit, added = made[0], True
        store.add_comment(tid, agent, 'agent', f'{agent} added an email to {to} to what closes this task.')
    o = hit['out']; subj = str(subject or o.get('subject') or (store.get_task(tid) or {}).get('Title') or '')[:200]
    deliver = json.dumps({'channel': 'email', 'to': [o['to']], 'cc': [], 'subject': subj, 'slot': hit['id']})
    rv = store.get_review(hit['rid']) if hit.get('rid') else None
    if rv and rv.get('Status') == 'pending':
        rid = rv['ReviewId']; store.set_review_deliver(rid, deliver)
    else:
        rid = store.add_review({'TaskId': tid, 'Kind': KIND, 'Status': 'pending', 'Deliver': deliver,
                                'ContextRevision': operations.message_revision(store, tid),
                                'Reason': f"{agent}'s email to {o['to']} - approve to send"})
        mark(store, tid, hit['id'], rid=rid, actor=f'agent:{agent}')
    store.update_review_draft(rid, text, None, by=f'agent:{agent}')
    return {'ok': True, 'review_id': rid, 'slot': hit['id'], 'added': added}
```

- [ ] **Step 4: Endpoint + guard**

`taskuary/server.py`, after `agent_reply`:
```python
class AgentDraftBody(BaseModel): task_id: int; text: str; to: str = ''; subject: str = ''; slot: str = ''; agent: str = 'agent'

@app.post('/api/agent/draft')
def agent_draft(body: AgentDraftBody, request: Request):
    """`taskuary --draft` from inside an agent's own shell: one of the emails that closes the task (slots.draft). Nothing is sent."""
    from . import slots
    _own_task_only(request, body.task_id)
    if not store.get_task(body.task_id): raise HTTPException(404, 'no such task')
    return slots.draft(store, body.task_id, body.text, body.to, body.subject, body.slot, body.agent)
```

`taskuary/guard.py:112`:
```python
    (r'POST', r'^/api/agent/(reply|done|draft)$', "`taskuary --reply/--done/--draft` on the session's OWN task (owns_task); nothing leaves"),
```

- [ ] **Step 5: CLI**

`taskuary/cli.py`, after `--reply-file`:
```python
    ap.add_argument('--draft', metavar='TEXT', help="write one of the emails that closes this task (its checklist names them) - "
                                                    "pending for the owner to approve; use with --slot or --to. Use - for stdin.")
    ap.add_argument('--draft-file', metavar='PATH', help='--draft, read from a file')
    ap.add_argument('--slot', default='', help='the checklist slot this email fills (the id after --slot in your checklist)')
    ap.add_argument('--to', default='', help='who it goes to, when no slot names them')
    ap.add_argument('--subject', default='', help='the subject line')
```

Generalise the `--reply` handler instead of copying it: change its guard to `if args.reply is not None or args.reply_file or args.draft is not None or args.draft_file:` and inside pick the door:
```python
        drafting = args.draft is not None or bool(args.draft_file)
        path, flag = (args.draft_file, args.draft) if drafting else (args.reply_file, args.reply)
        if path:
            try: text = open(path, encoding='utf-8').read()
            except (OSError, UnicodeDecodeError) as e:
                print(f'not saved: cannot read {path}: {getattr(e, "strerror", None) or e}'); return
        else: text = sys.stdin.read() if flag == '-' else flag
        ...
        url, body = ((f'{base}/api/agent/draft', {'task_id': int(tid), 'text': text, 'to': args.to, 'subject': args.subject, 'slot': args.slot,
                                                  'agent': os.environ.get('TASKUARY_AGENT') or 'agent'}) if drafting else
                     (f'{base}/api/agent/reply', {'task_id': int(tid), 'text': text, 'agent': os.environ.get('TASKUARY_AGENT') or 'agent'}))
        r = requests.post(url, timeout=60, headers=hdr, json=body)
        ...
        print(('email saved on the task, waiting on the owner to approve and send it.' if drafting else
               'reply saved on the task, waiting on the owner to approve and send it.') if out.get('ok')
              else f"not saved: {out.get('why') or out.get('detail') or r.text[:200]}")
```

- [ ] **Step 6: The general chat's block**

`taskuary/selfclose.py`, after `reply_marker`:
```python
# ...and the emails that close a task (slots.draft): one block per email, its attributes say which slot or who.
DRAFT_OPEN, DRAFT_CLOSE = '[[TASKUARY-DRAFT', '[[/TASKUARY-DRAFT]]'
_DRAFT_RE = re.compile(r'\[\[\s*TASKUARY[-_ ]?DRAFT\b([^\]]*)\]\](.*?)\[\[\s*/\s*TASKUARY[-_ ]?DRAFT\s*\]\]', re.I | re.S)
_ATTR_RE = re.compile(r'(slot|to|subject)\s*=\s*(?:"([^"]*)"|(\S+))', re.I)
DRAFT_LINE = ('EMAILS THAT CLOSE THIS TASK: the checklist lines marked "-> email to" are emails this task owes. Write each one as '
              f'{DRAFT_OPEN} slot=<id>]]<the email>{DRAFT_CLOSE} (or to=<address> subject="<subject>" for one that is not listed). '
              'Each waits for the owner\'s approval - nothing is sent until they approve it.')


def draft_markers(text: str) -> tuple:
    """(reply with every draft block taken out, [(attrs, body)]) - attrs keyed slot / to / subject."""
    found = [({k.lower(): (a or b) for k, a, b in _ATTR_RE.findall(m.group(1))}, m.group(2).strip()) for m in _DRAFT_RE.finditer(text or '')]
    return (_DRAFT_RE.sub('', text or '').strip(), [f for f in found if f[1]])
```

`taskuary/general.py` ~:556, after the `REPLY_LINE` line:
```python
    from . import slots
    if slots.all_(store, tid): system = system + '\n\n' + selfclose.DRAFT_LINE
```
and ~:1029, after the `agent_reply` block:
```python
            reply, drafts = selfclose.draft_markers(reply)
            if drafts:
                from . import slots
                for attrs, body in drafts:
                    out = slots.draft(self.store, self.task_id, body, attrs.get('to', ''), attrs.get('subject', ''), attrs.get('slot', ''), 'assistant')
                    if not out.get('ok'): logger.info(f"assistant email draft not saved on task {self.task_id}: {out.get('why')}")
```

- [ ] **Step 7: Run to verify they pass**

Run: `python -m pytest tests/test_close_slots.py tests/test_guard.py tests/test_agent_reply.py -q -p no:cacheprovider`
Expected: PASS. If `test_guard.py` pins the allow-list rows, update its expectation for the `draft` door.

- [ ] **Step 8: Commit** - message `An agent fills the emails that close a task`.

---

### Task 4: Triage and the assistant write slots when a task is made

**Files:**
- Modify: `taskuary/triage.py` (`TASK_FIELDS` :103, `verdict_schema` :127, verdict parse ~:817, `ASK_SYSTEM`/`extract_ask` ~:453-490)
- Modify: `taskuary/ingest.py` (:883 new task, :1140 attach, :1610 hand promote)
- Modify: `taskuary/concierge.py` (`handoff_task` ~:2308)
- Test: `tests/test_close_slots.py`

**Interfaces:**
- Consumes: `slots.add`.
- Produces: verdict dict key `outputs: list[{'to','about'}]` (only on `intent == 'task'`); `extract_ask(...)['outputs']`.

- [ ] **Step 1: Write the failing tests**

```python
from taskuary import triage, concierge


def test_triage_reads_outputs_only_on_a_task():
    j = {'intent': 'task', 'why': 'w', 'title': 't', 'summary': 's', 'kind': 'task', 'checklist': ['a'], 'urgent': False,
         'outputs': [{'to': 'erin@northwind.example', 'about': 'the numbers'}, {'to': '', 'about': 'x'}]}
    out = triage.parse_outputs(j)
    assert out == [{'to': 'erin@northwind.example', 'about': 'the numbers'}]
    assert triage.parse_outputs({**j, 'intent': 'fyi'}) == []


def test_the_schema_offers_outputs():
    p = triage.verdict_schema()['schema']['properties']
    assert p['outputs']['type'] == ['array', 'null'] and p['outputs']['items']['additionalProperties'] is False


def test_a_hand_made_ask_returns_its_outputs():
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': ['check'], 'outputs': [{'to': 'paula@northwind.example', 'about': 'tab 1'}]})
    assert triage.extract_ask({'body': 'Check tab 1 and email Paula'}, llm)['outputs'] == [{'to': 'paula@northwind.example', 'about': 'tab 1'}]


def test_a_chat_handoff_shows_its_slots_before_the_agent_starts(s):
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': [], 'outputs': FOUR})
    with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch('taskuary.general.start_session') as start:
        made = concierge.handoff_task(s, 'Check the four tabs and draft an email to each owner', kind='general')
    assert len(slots.open_(s, made['taskId'])) == 4 and start.called
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_close_slots.py -q -p no:cacheprovider -k "outputs or schema or handoff"`
Expected: FAIL - `AttributeError: ... 'parse_outputs'`.

- [ ] **Step 3: Triage**

`TASK_FIELDS` - append one sentence to the string:
```python
    ' For a task, also answer "outputs": [{"to": "<who>", "about": "<what to tell them>"}] - ONLY messages the sender asks the '
    'owner to send to OTHER people, the address when the message gives one, else the name as written. A reply to the sender '
    'is never an output; most tasks have none - answer null.'
```
`verdict_schema` - in `p`:
```python
         'outputs': {'type': ['array', 'null'], 'items': {'type': 'object', 'additionalProperties': False, 'required': ['to', 'about'],
                                                          'properties': {'to': {'type': 'string'}, 'about': {'type': 'string'}}}},
```
New helper beside `repo_choice_of`:
```python
def parse_outputs(j: dict) -> list:
    """The verdict's outputs - only on a task, only with somebody to send to (slots.clean validates the rest)."""
    if j.get('intent', 'task') != 'task' or not isinstance(j.get('outputs'), list): return []
    return [{'to': str(o.get('to')).strip(), 'about': str(o.get('about') or '').strip()} for o in j['outputs']
            if isinstance(o, dict) and str(o.get('to') or '').strip()][:12]
```
Verdict parse (~:817), after the checklist lines:
```python
                if out['intent'] == 'task' and parse_outputs(j): out['outputs'] = parse_outputs(j)
```
`ASK_SYSTEM` - add before the final sentence: `'Also "outputs": [{"to": "<who>", "about": "<what>"}] - only messages it asks the owner to send to OTHER people; [] when none. '` and in `extract_ask`'s success return add `'outputs': parse_outputs({'intent': 'task', **j})`, and `'outputs': []` to both fallback returns.

- [ ] **Step 4: Ingest writes them**

After `if intent.get('checklist'): store.set_task_checklist(tid, intent['checklist'], 'triage')` (:883) and after the `merge_task_checklist` at :1140:
```python
        if intent.get('outputs'):
            from . import slots
            slots.add(store, tid, intent['outputs'], 'triage')
```
At :1610 (hand promote), after its checklist line: `if ask.get('outputs'): slots.add(store, tid, ask['outputs'], 'triage')` (import `slots` the same way).

- [ ] **Step 5: The chat's hand-off**

`concierge.handoff_task`, after `made = setup_task(...)` and BEFORE the agent starts:
```python
    # what closes it, read from the owner's words: "draft an email to each" is four slots on the card before any work
    # starts, so a wrong count or recipient is fixed first (spec 2026-10-05). A brain that fails leaves the task as it was.
    try:
        from . import slots, triage
        ask = triage.extract_ask({'body': job}, brain(store, fast=True))
        if ask.get('outputs'): slots.add(store, made['taskId'], ask['outputs'], actor)
    except Exception as e: logger.info(f'could not read what closes {made["ref"]}: {e}')
```

- [ ] **Step 6: Run to verify they pass**

Run: `python -m pytest tests/test_close_slots.py tests/test_concierge.py tests/test_verdict_shape.py -q -p no:cacheprovider`
Expected: PASS. `test_verdict_shape.py` may pin the schema's property list - add `outputs` to its expectation.

- [ ] **Step 7: Triage evalset, before and after**

Run (with the owner's configured triage brain): `taskuary --evalset` on HEAD~ and on this commit; compare the intent score.
Expected: intent accuracy unchanged within noise. Report both numbers in the final summary. If the command needs live data and cannot run here, say so - do not skip silently.

- [ ] **Step 8: Commit** - message `Triage and the assistant say what closes a task`.

---

### Task 5: The assistant edits a task's list (`task.checklist`)

**Files:**
- Modify: `taskuary/operations.py` (`KINDS`)
- Modify: `taskuary/toolcatalog.py` (`PURPOSE` ~:55, group ~:249, signature ~:266)
- Modify: `taskuary/server.py` (`_run_operation`, beside `task.check` ~:807)
- Modify: `taskuary/concierge.py` (labels ~:2791, receipts ~:2836)
- Test: `tests/test_task_controls_operations.py`

**Interfaces:**
- Consumes: `store.set_task_checklist`, `slots.add`.
- Produces: operation `task.checklist` with params `items` (the full list of PLAIN item words, in order - one left out is removed; slots are untouched), `emails` (`[{to, about}]` slots to add) and `drop` (recipients whose open slot is dropped, ticked as not sent).

- [ ] **Step 1: Write the failing test** - read the top of `tests/test_task_controls_operations.py` and add a test in its style that: makes a task with two items, runs `task.checklist` through the same helper the file uses for `task.check` with `{'items': ['first, reworded'], 'emails': [{'to': 'erin@northwind.example', 'about': 'the numbers'}]}`, and asserts the list is now `['first, reworded', 'Email erin@northwind.example - the numbers']` with the second carrying `out`. Then `{'items': ['first, reworded']}` again: the email slot is still there. Then `{'drop': ['ERIN@northwind.example']}`: the slot is ticked. An empty call (`{}`) is refused with 422.

- [ ] **Step 2: Run to verify it fails** - `python -m pytest tests/test_task_controls_operations.py -q -p no:cacheprovider` - FAIL `unknown operation: task.checklist`.

- [ ] **Step 3: Implement**

`operations.KINDS`, after `'task.check'`:
```python
    'task.checklist':           ('task', (), None),          # reword / remove / add items, and add the emails that close it
```
`toolcatalog.PURPOSE`:
```python
    'task.checklist':           ('change what a task\'s checklist asks for - `items`: the full list of item words in order (one left out '
                                 'is removed, emails untouched); `emails`: [{to, about}] to add emails that must go out before it closes; `drop`: recipients whose email is no longer owed; `ref`'),
```
Add `'task.checklist'` after `'task.check'` in the `task` group tuple, and `'task.checklist': 'items?, emails?, drop?'` to the signature map.
`server._run_operation`, after the `task.check` branch:
```python
    if kind == 'task.checklist':
        from . import slots
        items, emails, drop = p.get('items'), p.get('emails'), p.get('drop')
        if not isinstance(items, list) and not emails and not drop: raise HTTPException(422, 'say the new list (items), emails to add or emails to drop')
        # plain items and slots are edited apart: a reworded list never deletes an email by leaving it out
        if isinstance(items, list): store.set_task_checklist(tid, [str(x) for x in items] + [i['text'] for i in slots.all_(store, tid)], ACTOR)
        added = slots.add(store, tid, emails, ACTOR) if emails else []
        gone = {str(x).casefold() for x in (drop or [])}
        for i in slots.open_(store, tid):
            if str(i['out'].get('to')).casefold() in gone: slots.mark(store, tid, i['id'], done=True, actor=ACTOR)
        return {'taskId': tid, 'checklist': store.task_checklist(tid), 'added': len(added)}
```
`concierge` label map: `'task.checklist': 'Change the checklist'`; receipt: `if kind == 'task.checklist': return f" The list has {len(o.get('checklist') or [])} item(s)" + (f", {o['added']} email(s) added." if o.get('added') else '.')`.

- [ ] **Step 4: Run** - `python -m pytest tests/test_task_controls_operations.py tests/test_operations.py -q -p no:cacheprovider` - PASS. If a catalogue-completeness test lists every kind, add `task.checklist` there.

- [ ] **Step 5: Commit** - message `The assistant can change a task's checklist and the emails that close it`.

---

### Task 6: The work rail shows a task's waiting emails

**Files:**
- Modify: `taskuary/funnel.py` (`from_proposals` ~:664)
- Test: `tests/test_close_slots.py`

**Interfaces:**
- Consumes: `slots.KIND`.
- Produces: one `approve`-lane row per task with pending slot drafts, key `review:<oldest pending slot rid>`.

- [ ] **Step 1: Failing test**

```python
from taskuary import funnel


def test_the_rail_shows_one_row_per_task_with_its_count(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    rows = [r for r in funnel.from_proposals(s, set()) if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['key'] == f'review:{a}' and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why']
```

- [ ] **Step 2: Run** - FAIL (no row).

- [ ] **Step 3: Implement** - in `from_proposals`, after the existing loop:
```python
    # a task's emails (slots.KIND) have no message row to ride on, so they arrive here - ONE row per task, its oldest draft
    # first: approving it puts the next one up with the count one smaller, never four rows for one ask
    from . import slots
    per = {}
    for rv in store.list_reviews('pending'):
        if rv.get('Kind') == slots.KIND and rv.get('TaskId') and rv['ReviewId'] not in used_rids: per.setdefault(rv['TaskId'], []).append(rv)
    for tid, rvs in per.items():
        first, n = min(rvs, key=lambda r: r['ReviewId']), len(rvs)
        t = store.get_task(tid) or {}
        out.append(_item(f"review:{first['ReviewId']}", 'review', 'approve', t.get('Title') or first.get('Reason') or 'emails wait for your yes',
                         tid=tid, when=first.get('CreatedAt'), rid=first['ReviewId'], draft=True,
                         why=f"{n} email{'s' if n != 1 else ''} drafted for you to send"))
```
`_item(key, kind, lane, title, *, who, when, since, why, mid, tid, rid, ...)` (funnel.py:158) takes these keywords.

- [ ] **Step 4: Run** - `python -m pytest tests/test_close_slots.py tests/test_funnel.py -q -p no:cacheprovider` - PASS.

- [ ] **Step 5: Commit** - message `A task's waiting emails reach the rail as one row`.

---

### Task 7: The task page shows each email

**Files:**
- Modify: `website/src/taskLifecycle.js` (:44-55)
- Create: `website/src/SlotList.jsx`
- Modify: `website/src/TaskPage.jsx` (checklist block ~:1070, stage 3 ~:1592/1695)
- Rebuild: the committed bundle (`cd website && npm run build`)

**Interfaces:**
- Consumes: `detail.checklist` (items with `out`, `rid`), `detail.reviews` (rows with `Kind === "slot"`), `ReviewDecision` (`review`, `onChanged`), `POST /api/reviews/{rid}/decide`.
- Produces: `slotReviews(reviews)`; `<SlotList checklist reviews onChanged />`.

- [ ] **Step 1: Keep the reply slot the reply** - in `taskLifecycle.js`, every reply finder skips slots:
```js
const isReply = (review) => review.Kind !== "action" && review.Kind !== "slot";
export const pendingReplyReview = (reviews = []) => reviews.find((review) => isReply(review) && review.Status === "pending");
```
and use `isReply(review)` in place of `review.Kind !== "action"` in `unsentReplyReview` and `sentReplyReview`. Add:
```js
// the emails that close the task (slots.py): their own block, never the reply card
export const slotReviews = (reviews = []) => (reviews || []).filter((review) => review.Kind === "slot");
```

- [ ] **Step 2: `SlotList.jsx`** - one row per slot item: recipient, a state chip, and the slot's pending draft in `ReviewDecision`; "Approve all (N)" when two or more wait.

```jsx
import { useState } from "react";
import { Box, Button, Chip, Typography } from "@mui/material";
import ReviewDecision from "./ReviewDecision.jsx";
import api from "./api";
import { slotReviews } from "./taskLifecycle.js";

// the emails that close this task (spec 2026-10-05): each slot with its own draft, approved on its own
const stateOf = (i, rv) => i.done ? (rv && ["approved", "edited", "sent"].includes(rv.Status) ? "sent" : "dropped")
  : rv?.Status === "pending" ? "waits for your yes" : "to draft";

export default function SlotList({ checklist = [], reviews = [], onChanged }) {
  const [busy, setBusy] = useState(false);
  const items = checklist.filter((i) => i.out);
  if (!items.length) return null;
  const byRid = Object.fromEntries(slotReviews(reviews).map((r) => [r.ReviewId, r]));
  const waiting = items.map((i) => byRid[i.rid]).filter((r) => r?.Status === "pending" && String(r.DraftText || "").trim());
  const approveAll = async () => {
    setBusy(true);
    try { for (const r of waiting) await api.post(`/api/reviews/${r.ReviewId}/decide`, { verb: "approve", final_text: null, note: null, cc: null }); }
    finally { setBusy(false); onChanged?.(); }
  };
  return (
    <Box sx={{ mt: 1.4 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <Typography variant="overline" sx={{ fontSize: 9, fontWeight: 750, letterSpacing: 1.25 }}>
          {`Closes when sent · ${items.filter((i) => i.done).length} of ${items.length}`}
        </Typography>
        {waiting.length > 1 && <Button size="small" disabled={busy} onClick={approveAll}>{busy ? "Sending…" : `Approve all (${waiting.length})`}</Button>}
      </Box>
      {items.map((i) => {
        const rv = byRid[i.rid];
        return (
          <Box key={i.id} sx={{ mb: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>{i.out.to}{i.out.to.includes("@") ? "" : " ?"}</Typography>
              <Chip size="small" variant="outlined" label={stateOf(i, rv)} />
            </Box>
            {rv?.Status === "pending" && <ReviewDecision review={rv} onChanged={onChanged} />}
          </Box>
        );
      })}
    </Box>
  );
}
```
`/api/reviews/{rid}/decide` with `{verb, final_text, note, cc}` is exactly what `ReviewDecision.decide` posts (ReviewDecision.jsx:125).

- [ ] **Step 3: Mount it** - in `TaskPage.jsx`: import `SlotList`; in the checklist block render plain items only (`detail.checklist.filter((i) => !i.out).map(...)`), and directly under that block:
```jsx
<SlotList checklist={detail?.checklist || []} reviews={detail?.reviews || []}
  onChanged={() => { loadDetail(selected); loadTasks(); onChanged?.(); }} />
```
Keep `checklistPct` / `progressLine` over the whole list (a slot is progress too).

- [ ] **Step 4: Gate** - `cd website && npm run lint:undef && npm run build` (Node 22 if the repo's recipe needs it: `npm exec --package=node@22 -- npm run build`). Expected: no undefined identifiers; bundle builds. Then `python -m pytest tests -q -p no:cacheprovider -k "bundle or static"` for the bundle-hash check.

- [ ] **Step 5: See it** - run the demo world (`taskuary --demo`), create a task through the assistant chat: "Check the four tabs on the finance dashboard and draft an email to Paula Vance, Ray Colton, Gail Moreno and Erin Blake about where each stands". Expected: four slots on the card; Gail's shows `?` until an address is known. Screenshot it for the summary; check the sidebar and titles hold only demo data.

- [ ] **Step 6: Commit** - `website/src/taskLifecycle.js website/src/SlotList.jsx website/src/TaskPage.jsx` + the rebuilt bundle files, message `The task page shows each email that closes it`.

---

### Task 8: Whole suite, then push

- [ ] **Step 1:** `python -m pytest -q -x -p no:cacheprovider` from the repo root. Expected: all pass. Any failure: fix, re-run whole suite. (`tests/test_terminal.py` three tests fail ALONE on this box but pass in the full suite - judge them only in the full run.)
- [ ] **Step 2:** `git log --oneline origin/master..master` - only this plan's commits plus the spec/plan docs; then `git push origin master`.
- [ ] **Step 3:** Watch CI on that sha (`gh run list --branch master --limit 3`); report the result.

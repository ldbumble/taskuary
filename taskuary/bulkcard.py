"""ONE CARD FOR A BULK JOB (the owner, 2026-11-16: "We will have to build never-ending action cards to fit all different scenarios. For a job
that is a bulk process you should be able to review a few of them and then send them all out ... On the action card we need a bulk and a
single version. On the bulk version, the send should show a progress bar in the action card since it can take a long time.").

Any act an agent raises - an email, a GitHub issue closed, an API call, a SQL row, a post - it may raise as MANY at once: one tool call
carrying `items` (agenttools.call). Each item is the ordinary card it would have been, filed by the same door, and the rows share a `Batch`:
the line of cards (cardqueue) holds them as ONE card, the chat draws them as one (the bulk form: the list, tick boxes, any one opened in its
single form), and one press runs them all here - each row by the very road its own press takes (verdicts.decide), in the background, its
progress kept and drawn as a bar in the card, cancel stopping the rest. The agent is told ONCE, at the end: how many went, which failed and
why, and how many he left out."""
import json, threading, time, uuid
from loguru import logger

KEY = 'batch:'                 # setting: batch:<key> -> the run's state
# HOW MANY IS MANY (design round 5, I4; the owner: "I have 2 emails to send, should we send this one?" - one card at a time for a few, the bulk
# card for many): fewer than this raised in one call stand one at a time in the line of cards (agenttools._many)
MANY = 5
YES = 'approve'
LEFT = 'left out by you'      # a row he unticked: closed, never done
_CLAIM = threading.Lock()      # a press claims the card's run (run)
BOOT = uuid.uuid4().hex        # this process: a run marked by another was cut short by a restart (state)


def new_key() -> str: return uuid.uuid4().hex[:12]


def rows(store, key: str) -> list:
    return store._rows("SELECT * FROM review WHERE Batch=? ORDER BY ReviewId", (str(key),))


def state(store, key: str) -> dict:
    "The run as it stands: {key, tid, total, done, failed, left, state: idle|running|cancelling|stopped|finished, rows: {rid: 'ok'|'left'|error}}."
    try: got = json.loads(store.get_setting(f'{KEY}{key}') or '{}') or {}
    except (TypeError, ValueError): got = {}
    # ...A RUN CUT SHORT BY A RESTART (its thread went with the old process) is stopped, the rest waiting for his press - never "running" for good
    # ...(one with no mark at all was written before runs carried one: by another process too)
    if got.get('state') in ('running', 'cancelling') and got.get('boot') != BOOT: got['state'] = 'stopped'
    return got or {'key': key, 'state': 'idle', 'rows': {}}


def running(store, key) -> bool: return bool(key) and state(store, key).get('state') in ('running', 'cancelling')
def at_work(store, tid) -> bool:
    """A bulk card on task `tid` whose run is under way (2026-11-17): its rows read pending until each is done, so the task read "agent waiting
    on you" over the very press doing them - the task's state reads it at work, as any act in flight (taskstate.TaskState.key)."""
    keys = store._rows("SELECT DISTINCT Batch FROM review WHERE TaskId=? AND Batch IS NOT NULL AND Status='pending'", (int(tid),))
    return any(running(store, r['Batch']) for r in keys)


def _save(store, st: dict) -> None:
    store.set_setting(f"{KEY}{st['key']}", json.dumps(st), 'system')
    if st.get('tid'): store._poke('task-changed', task_id=st['tid'])


def _went(out: dict) -> str:
    "'' when the row's press went through, else why not - in the words its own card would have said."
    if not out.get('ok'): return str(out.get('send_error') or out.get('why') or out.get('error') or 'it did not go')[:300]
    if out.get('act_failed') or out.get('delivery') in ('failed', 'unknown'): return str(out.get('send_error') or out.get('act_failed') or 'it did not go')[:300]
    return ''


def run(store, key: str, skip=(), actor: str = 'owner', wait: bool = False) -> dict:
    """His one press: every waiting row of bulk card `key` done by its own road, in order, in the background (`wait`: here, for a test);
    the rows in `skip` closed as left out. -> the run's state as it starts."""
    from . import proposals, verdicts
    # ...ONE RUN AT A TIME, however many presses (a double click, the phone and the desk): checked and marked at work as one step - two runs each
    # found the other's row in hand, counted it failed, and its agent heard the run twice, half of it "failed"
    with _CLAIM:
        todo = [r for r in rows(store, key) if r['Status'] == 'pending']
        if not todo: raise ValueError('nothing on this card waits any more')
        if running(store, key): return state(store, key)
        tid, skip = todo[0]['TaskId'], {int(x) for x in skip or ()}
        # ...A CARD THE CHAT MOVED PAST PRESSES NOTHING (verdicts._decide's rule): asked here, before the run is marked at work - a bulk card at
        # work is never written past (proposals._older), so each row's own refusal would read it as still standing
        if tid and (past := [r for r in todo if r['ReviewId'] in proposals.written_past(store, tid)]): raise ValueError(proposals.passed_why(store, past[0]))
        st = {**state(store, key), 'key': key, 'tid': tid, 'total': len(todo), 'done': 0, 'failed': 0, 'left': 0, 'state': 'running', 'rows': {}, 'at': time.time(), 'boot': BOOT}
        _save(store, st)
    def go():
        tok = verdicts.QUIET.set(True)
        try:
            for r in todo:
                if state(store, key).get('state') == 'cancelling': break
                rid = r['ReviewId']
                try:
                    if rid in skip:
                        store.decide_review(rid, 'closed_unsent' if r['Kind'] != 'action' else 'rejected', r.get('DraftText'), actor, LEFT)
                        st['rows'][str(rid)], st['left'] = 'left', st['left'] + 1
                    else:
                        why = _went(verdicts.decide(store, store.get_review(rid) or r, YES, actor=actor))
                        st['rows'][str(rid)] = why or 'ok'
                        st['done' if not why else 'failed'] += 1
                except Exception as e:
                    logger.warning(f'batch {key}: rv{rid} - {e}')
                    st['rows'][str(rid)], st['failed'] = str(e)[:300] or 'it did not go', st['failed'] + 1
                st['state'] = 'cancelling' if state(store, key).get('state') == 'cancelling' else 'running'
                _save(store, st)
        finally:
            verdicts.QUIET.reset(tok)
            st['state'] = 'stopped' if state(store, key).get('state') == 'cancelling' else 'finished'
            _save(store, st)
            try: told(store, key, st, actor)
            except Exception as e: logger.warning(f'batch {key}: its agent was not told - {e}')
    if wait: go()
    else: threading.Thread(target=go, daemon=True, name=f'batch-{key}').start()
    return st


def cancel(store, key: str) -> dict:
    "Stop the rest: the row at work finishes, nothing after it starts; what was not run still waits on the card."
    st = state(store, key)
    if st.get('state') == 'running': st['state'] = 'cancelling'; _save(store, st)
    return st


def summary(store, key: str, st: dict) -> str:
    "The run in words for its agent: what went, what failed and why, what he left out, what a cancel left waiting."
    from . import cardqueue
    rs = {str(r['ReviewId']): r for r in rows(store, key)}
    what = lambda rid: cardqueue.what(store, {'rids': [int(rid)], 'rows': [rs[rid]]}) if rid in rs else f'rv{rid}'
    bad = [(rid, why) for rid, why in st.get('rows', {}).items() if why not in ('ok', 'left')]
    # ...a send that did not go still waits on the card for his press, as a single card's does (general.NOT_GONE); an act that failed is off it
    again = [rid for rid, _ in bad if rid in rs and rs[rid]['Status'] == 'pending']
    rest = [r for r in rs.values() if r['Status'] == 'pending' and str(r['ReviewId']) not in st.get('rows', {})]
    return (f"The owner pressed the bulk card ({st.get('total', 0)} items): {st.get('done', 0)} done, {st.get('failed', 0)} failed, {st.get('left', 0)} left out by them"
            + (f", {len(rest)} not run - they stopped it" if st.get('state') == 'stopped' and rest else '') + '.'
            + (' Failed: ' + '; '.join(f'rv{rid} ({what(rid)}): {why}' for rid, why in bad[:20]) + ('…' if len(bad) > 20 else '') + '.' if bad else '')
            + (f' Did not go and still on the card for their press: {len(again)}.' if again else ''))


def told(store, key: str, st: dict, actor: str = 'owner') -> str:
    "Its agent hears the whole run once, by the one road (general.to_agent) - and nothing is said of it again with his next line."
    from . import general
    def heard(how):
        for rid in st.get('rows', {}): store.audit('review', int(rid), general.TOLD, actor, 'system', {'task': st['tid'], 'how': how, 'batch': key})
    # ...an event on the task (general.to_agent -> events.note), with each card's own state beside it (events.card)
    if not st.get('tid'): return ''
    return general.to_agent(store, st['tid'], summary(store, key, st), actor, heard=heard)

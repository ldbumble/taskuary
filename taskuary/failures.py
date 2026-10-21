"""ONE FAILURE SHAPE (general fix 1, 2026-10-18). A send, a confirmed act, an agent start and a workflow step each failed their own
way - a raw "[Errno 2] ... 'claude'" on one card, a Connect a mailbox on another, nothing on a third - so every surface read its own
story. Every failure is now said one way: `classify` turns any exception into {sentence, fix, retry, unknown}, and `record` leaves it
on the task as the agreed op row (shared with the workflow runner, taskhub-ca), which advisor.failure, concierge.recover and the
cards all read. A fix is a place from words.json under the button `fix` - never a new button, never "go to X" text."""
import json, re, smtplib, uuid
from . import outbound, redact, words

# the acts that mail someone: only for these is a lost answer "it may have gone" - a timed-out Mark done simply did not happen
SENDS = {'review.approve', 'task.handoff', 'task.clarify'}
_NOT_INSTALLED = re.compile(r"\[Errno 2\]|No such file or directory|is not recognized as an internal or external command|command not found"
                            r"|not installed|cannot find the file specified", re.I)
_NO_FOLDER = re.compile(r'working directory does not exist|needs a repository|no repository|not a git repository|repository still to choose', re.I)
_NO_TOOL = re.compile(r'pick a coding tool first', re.I)
_NO_AI = re.compile(r'no AI connector|no AI is (set up|connected)|no brain', re.I)


def _fix(label: str, pid: str) -> dict: return {'label': label, 'href': words.href(pid)}


def _said(b) -> str: return (b.decode(errors='replace') if isinstance(b, bytes) else str(b or '')).strip()
def _smtp(e) -> str:
    """A mail server's answer in words: "(535, b'5.7.8 Authentication unsuccessful')" reached the card as-is (the dead-end walk,
    2026-10-18) - the code and the bytes are the provider's bookkeeping; what it said is the sentence."""
    if isinstance(e, smtplib.SMTPAuthenticationError): return f'the mailbox refused the sign-in ({_said(e.smtp_error)})'
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return 'the mail server refused ' + '; '.join(f'{a} ({_said(m)})' for a, (_, m) in (e.recipients or {}).items())
    if isinstance(e, smtplib.SMTPResponseException): return f'the mail server said no ({_said(e.smtp_error)})'
    return ''


class Closed(ValueError):
    """An act on a closed task: "reopen it first" said so with nothing to press (the error sweep, 2026-10-18). Still a ValueError - every
    door answers it as before - carrying the way there: the task itself, where Reopen task is."""
    def __init__(self, tid, msg):
        from . import buttons
        super().__init__(msg); self.fix = {'label': f"Open it to {buttons.label('reopen').lower()}", 'href': f'#task={int(tid)}'}


def classify(e, *, act: str = None) -> dict:
    """{sentence, fix, retry, unknown} for any failure. `sentence` is plain and scrubbed - it reaches the screen and the model's
    prompt; `fix` is {label, href} or None; `retry` is whether pressing it again could work; `unknown` only for a send that may
    have gone. A string is read as the error's own words (a handler that reported its failure instead of raising)."""
    from .operations import plain
    text = str(e if isinstance(e, str) else _smtp(e) or plain(e))
    fix = None if isinstance(e, str) else outbound.fix_of(e)
    fix = fix or outbound.auth_fix(RuntimeError(text))
    sentence = text
    if isinstance(e, FileNotFoundError) or _NOT_INSTALLED.search(text):
        sentence, fix = "The coding tool isn't installed on this computer", fix or _fix('Connect a coding tool', 'ai_apps')
    elif _NO_TOOL.search(text): fix = fix or _fix('Connect a coding tool', 'ai_apps')       # terminal.NO_CODING_TOOL
    elif _NO_FOLDER.search(text): fix = fix or _fix('Choose where it works', 'coding')
    elif _NO_AI.search(text): fix = fix or _fix('Connect an AI', 'ai')
    unknown = act in SENDS and not isinstance(e, str) and outbound.delivery_uncertain(e)
    return {'sentence': redact.scrub(sentence)[:500], 'fix': fix, 'retry': not fix and not unknown, 'unknown': bool(unknown)}


def outcome(c: dict, **more) -> dict:
    """The OutcomeJson part of a classified failure - what an op row keeps."""
    return {k: v for k, v in {**more, 'fix': c.get('fix'), 'retry': c.get('retry'), **({'delivery': 'unknown'} if c.get('unknown') else {})}.items()
            if v is not None}


# WHERE A FAILURE LIVES (agreed with the workflow runner, taskhub-ca, 2026-10-18): a known area's fix is its place in words.json
AREA_PLACE = {'connection': 'connections', 'report': 'workflows', 'setting': 'settings', 'brain': 'ai'}
def area_fix(area) -> dict | None:
    pid = AREA_PLACE.get((area or {}).get('area')) if isinstance(area, dict) else None
    return {'label': f"Open {words.name(pid)}", 'href': words.href(pid)} if pid and words.href(pid) else None


def record(store, *, task_id: int = None, kind: str, error, what: str, fix: dict = None, source: str = 'app', retry: bool = None,
           step: int = None, unknown: bool = False, cause: str = 'taskuary', area: dict = None, on: tuple = None) -> str:
    """Leave a failure on the task as the agreed op row: Kind a known kind, Status error, Error the scrubbed sentence, OutcomeJson
    {what, fix, source, step, retry, delivery, cause, area}. `cause` is 'taskuary' (the app failed) or 'step' (a workflow's own step:
    fixed in the run, never a new task); `area` {area, name} names where it lives, and a known area's place is its fix. The workflow
    runner writes the same row for a step past its self-repair attempts. `on` (target kind, id) leaves it on what has no task: a
    report ('source') or a connector."""
    from .operations import KINDS
    if kind not in KINDS: raise ValueError(f'not a kind of act: {kind}')
    c = classify(error, act=kind)
    fix = fix or c['fix'] or area_fix(area); retry = (not fix and not unknown) if retry is None else retry
    oid, (tk, ti) = uuid.uuid4().hex[:12], on or ('task', task_id)
    store.add_operation({'OpId': oid, 'Kind': kind, 'TargetKind': tk, 'TargetId': int(ti), 'ParamsJson': '{}', 'Version': 1,
                         'Status': 'error', 'Error': c['sentence'],
                         'OutcomeJson': json.dumps(outcome({'fix': fix, 'retry': retry, 'unknown': unknown}, what=what, source=source, step=step,
                                                           cause=cause, area=area))})
    return oid


# A REPORT OR A CONNECTION HAS NO TASK (real-AI walk, 2026-10-18): a rerun or a test that failed was said once on its card and then
# lost - nothing the Advisor or the chat could read. It is the same row, on the report or the connector, and it stands until a run
# or a test since has gone well: a newer good run, a connection whose error has cleared.
ON = {'source': ('report', ('report.run', 'report.rerun')), 'connector': ('connection', ('connection.test',))}
def record_on(store, target_kind: str, target_id, *, kind: str, error, what: str, name: str = '') -> str:
    return record(store, on=(target_kind, int(target_id)), kind=kind, error=error, what=what, area={'area': ON[target_kind][0], 'name': name})


def _stamp(s) -> str: return str(s or '').replace('T', ' ')[:19]
def standing(store, target_kind: str, target_id) -> dict | None:
    """The newest run or test failure on a report or connector that nothing since has cleared, in advisor.failure's shape."""
    if target_kind not in ON or not target_id: return None
    kinds = ON[target_kind][1]
    r = store._one(f"SELECT * FROM operation WHERE TargetKind=? AND TargetId=? AND Kind IN ({','.join('?' * len(kinds))}) "
                   "ORDER BY CreatedAt DESC, rowid DESC LIMIT 1", (target_kind, int(target_id), *kinds))
    if not r or r.get('Status') != 'error': return None
    if target_kind == 'connector' and not (store.get_connector(int(target_id)) or {}).get('LastError'): return None
    if target_kind == 'source' and any(not x.get('failed') and _stamp(x.get('at')) > _stamp(r.get('CreatedAt')) for x in store.report_runs(int(target_id), 3)):
        return None
    try: o = json.loads(r.get('OutcomeJson') or '{}') or {}
    except (TypeError, ValueError): o = {}
    return {'what': str(o.get('what') or f"{r['Kind']} did not happen"), 'why': str(r.get('Error') or ''), 'fix': o.get('fix') or area_fix(o.get('area')),
            'unknown': False, 'kind': r['Kind'], 'source': o.get('source') or 'app', 'cause': o.get('cause') or 'taskuary', 'on': (target_kind, int(target_id))}


def target_of(item: dict) -> tuple | None:
    """What an item with no task stands for: a report's card its report, a broken connection's row its connector."""
    i, key = item or {}, str((item or {}).get('key') or '')
    if i.get('kind') == 'report' and i.get('source_id') and not i.get('tid'): return ('source', int(i['source_id']))
    return ('connector', int(key[5:])) if key.startswith('conn:') and key[5:].isdigit() else None


def chips(o: dict, *, op: dict = None) -> list:
    """The buttons a failure carries, in order: its fix first; Try again only where it could work; else Report this bug - the
    record's own words, never a guess from the sentence. `op` is the failed proposal, so Try again re-runs exactly it."""
    from . import buttons
    o = o if isinstance(o, dict) else {}
    out = [{'verb': 'go', 'href': o['fix']['href'], 'label': o['fix']['label']}] if isinstance(o.get('fix'), dict) and o['fix'].get('href') else []
    if o.get('retry') and op: out.append({'verb': 'retry', 'label': buttons.label('try_again'), 'op': op['id'], 'version': op['version'], 'kind': op.get('kind')})
    if not out: out.append({'verb': 'bug', 'label': buttons.label('report_bug')})
    return out

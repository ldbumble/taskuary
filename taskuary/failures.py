"""ONE FAILURE SHAPE (general fix 1, 2026-10-18). A send, a confirmed act, an agent start and a workflow step each failed their own
way - a raw "[Errno 2] ... 'claude'" on one card, a Connect a mailbox on another, nothing on a third - so every surface read its own
story. Every failure is now said one way: `classify` turns any exception into {sentence, fix, retry, unknown}, and `record` leaves it
on the task as the agreed op row (shared with the workflow runner, taskhub-ca), which advisor.failure, concierge.recover and the
cards all read. A fix is a place from words.json under the button `fix` - never a new button, never "go to X" text."""
import json, re, uuid
from . import outbound, redact, words

# the acts that mail someone: only for these is a lost answer "it may have gone" - a timed-out Mark done simply did not happen
SENDS = {'review.approve', 'task.handoff', 'task.clarify'}
_NOT_INSTALLED = re.compile(r"\[Errno 2\]|No such file or directory|is not recognized as an internal or external command|command not found"
                            r"|not installed|cannot find the file specified", re.I)
_NO_FOLDER = re.compile(r'working directory does not exist|needs a repository|no repository|not a git repository|repository still to choose', re.I)
_NO_AI = re.compile(r'no AI connector|no AI is (set up|connected)|no brain', re.I)


def _fix(label: str, pid: str) -> dict: return {'label': label, 'href': words.href(pid)}


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
    text = str(e if isinstance(e, str) else plain(e))
    fix = None if isinstance(e, str) else outbound.fix_of(e)
    fix = fix or outbound.auth_fix(RuntimeError(text))
    sentence = text
    if isinstance(e, FileNotFoundError) or _NOT_INSTALLED.search(text):
        sentence, fix = "The coding tool isn't installed on this computer", fix or _fix('Connect a coding tool', 'ai_apps')
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


def record(store, *, task_id: int, kind: str, error, what: str, fix: dict = None, source: str = 'app', retry: bool = None,
           step: int = None, unknown: bool = False, cause: str = 'taskuary', area: dict = None) -> str:
    """Leave a failure on the task as the agreed op row: Kind a known kind, Status error, Error the scrubbed sentence, OutcomeJson
    {what, fix, source, step, retry, delivery, cause, area}. `cause` is 'taskuary' (the app failed) or 'step' (a workflow's own step:
    fixed in the run, never a new task); `area` {area, name} names where it lives, and a known area's place is its fix. The workflow
    runner writes the same row for a step past its self-repair attempts."""
    from .operations import KINDS
    if kind not in KINDS: raise ValueError(f'not a kind of act: {kind}')
    c = classify(error, act=kind)
    fix = fix or c['fix'] or area_fix(area); retry = (not fix and not unknown) if retry is None else retry
    oid = uuid.uuid4().hex[:12]
    store.add_operation({'OpId': oid, 'Kind': kind, 'TargetKind': 'task', 'TargetId': int(task_id), 'ParamsJson': '{}', 'Version': 1,
                         'Status': 'error', 'Error': c['sentence'],
                         'OutcomeJson': json.dumps(outcome({'fix': fix, 'retry': retry, 'unknown': unknown}, what=what, source=source, step=step,
                                                           cause=cause, area=area))})
    return oid


def chips(o: dict, *, op: dict = None) -> list:
    """The buttons a failure carries, in order: its fix first; Try again only where it could work; else Report this bug - the
    record's own words, never a guess from the sentence. `op` is the failed proposal, so Try again re-runs exactly it."""
    from . import buttons
    o = o if isinstance(o, dict) else {}
    out = [{'verb': 'go', 'href': o['fix']['href'], 'label': o['fix']['label']}] if isinstance(o.get('fix'), dict) and o['fix'].get('href') else []
    if o.get('retry') and op: out.append({'verb': 'retry', 'label': buttons.label('try_again'), 'op': op['id'], 'version': op['version'], 'kind': op.get('kind')})
    if not out: out.append({'verb': 'bug', 'label': buttons.label('report_bug')})
    return out

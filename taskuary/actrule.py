"""ONE RULE FOR A STEP THAT NEEDS THE OWNER'S PRESS (the owner, 2026-11-19, over a task that held ~75 pushes in one chat: "this should be
included in whats a action no?"). Every gate asks it the same question, after its own reading of what the step is (shellgate.acts: a tool's
own grammar for a push, a publish, a delete outside the agent's folder, a web write):

  1. IS IT ALREADY ALLOWED? A trusted connection that acts on its own (the repo's GitHub card at write or full Authority - shellgate.trusted),
     or the owner already approved the same kind of step on the same target in this task (a push to the same repo and branch): it runs, and
     the task says so in one line. A decision he made once is not asked again.
  2. DID HE ALREADY SAY NO? The same step dismissed since his last line on the task: refused, and the agent is told it was his no - never a
     second card. Once he writes again it may be raised again.
  3. ELSE: one card for his press (the gate files it, by its own road into the task's one queue).

What he decided is written down where he decided it (`remember`: his Approve or Dismiss on a card, his Allow once / Reject on the buttons),
as audit rows on the task - stored facts, never a model call.
"""
import json
from loguru import logger

DECIDED = 'act_decided'
DISMISSED = 'The owner dismissed this same step'      # ...his no, said as his: never "Taskuary's own answer"


def target(a: dict, cwd: str = '') -> tuple:
    "(repo, branch) a push goes to - ('', '') for a step that is not one; '' for either part not known."
    if a.get('refs') is None: return '', ''
    # ...read from git; where git cannot answer, the push is not matched to any earlier answer - it is asked, never let through
    try: return _target(a, cwd)
    except Exception as e:
        logger.debug(f'actrule: where a push goes was not read - {e}')
        return '', ''


def _target(a: dict, cwd: str) -> tuple:
    from . import landing, shellgate
    at = shellgate.folder(cwd, a.get('to') or '')
    to = str(a.get('to') or '')
    repo = shellgate.repo_of(at) if to in ('',) or to.startswith('@') else to if to != '?' else ''
    refs = [r for r in a['refs'] if r]
    dst = refs[-1].lstrip('+').split(':')[-1] if refs else ''
    if dst in ('', 'HEAD') and at: dst = landing.head_branch(at)
    return repo, dst.removeprefix('refs/heads/')


def key(a: dict, cwd: str = '') -> str:
    "What makes two steps the same decision: what it does, and where - a push by its repo and branch."
    if a.get('refs') is not None:
        repo, br = target(a, cwd)
        return f'push|{repo.lower()}|{br}' if repo and br else ''
    return f"{a.get('what') or ''}|{str(a.get('to') or '').lower()}"


def keys(todo: list, cwd: str = '') -> list:
    "One key per step - [] when any step has none (it cannot be matched, so it is asked)."
    ks = [key(a, cwd) for a in todo]
    return ks if all(ks) else []


def words(a: dict, cwd: str = '') -> str:
    "A step in the owner's words - a push names its commits, repo and branch ('push 3 commits to northwind/ledger deploy')."
    if a.get('refs') is None: return a.get('what') or ''
    from . import landing, shellgate
    repo, br = target(a, cwd)
    if not (repo and br): return a.get('what') or ''
    at, refs = shellgate.folder(cwd, a.get('to') or ''), [r for r in a['refs'] if r]
    src = (refs[-1].lstrip('+').split(':')[0] if refs else '') or 'HEAD'
    try: n = landing._git(at, 'rev-list', '--count', f'origin/{br}..{src}') if at else ''
    except Exception: n = ''
    return f"push {n} commit{'' if n == '1' else 's'} to {repo} {br}" if n.isdigit() and n != '0' else f'push to {repo} {br}'


def _rows(store, tid: int) -> list:
    out = []
    for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId IN (?,?) AND Action=? ORDER BY Id", (int(tid), str(tid), DECIDED)):
        try: out.append(json.loads(r.get('Detail') or '{}'))
        except (TypeError, ValueError): pass
    return out


def remember(store, tid: int, ks: list, answer: str) -> None:
    "Write down his decision on these steps: 'approved' or 'dismissed'."
    if not ks or not str(tid or '').isdigit(): return
    from .shellgate import turn_of
    try: store.audit('task', int(tid), DECIDED, 'owner', 'human', {'keys': list(ks), 'answer': answer, 'turn': turn_of(store, int(tid))})
    except Exception as e: logger.warning(f'actrule: task {tid} - his {answer} was not written down - {e}')


def decide(store, tid: int, todo: list, cwd: str = '') -> tuple:
    """(how, words) for steps a gate would hold: ('trusted' | 'approved', a line for the task) runs them; ('dismissed', words for the agent)
    refuses them as his no; ('', '') - put them to him as one card."""
    from . import shellgate
    if not todo: return 'approved', ''
    if (repo := shellgate.trusted(store, cwd, todo)):
        return 'trusted', f"The agent went on to {'; '.join(dict.fromkeys(words(a, cwd) for a in todo))} on {repo} - a repo you trust to act on its own."
    ks = keys(todo, cwd)
    if not ks: return '', ''
    rows, turn = _rows(store, tid), shellgate.turn_of(store, tid)
    yes = {k for r in rows if r.get('answer') == 'approved' for k in r.get('keys') or []}
    no = {k for r in rows if r.get('answer') == 'dismissed' and int(r.get('turn') or 0) >= turn for k in r.get('keys') or []}
    what = '; '.join(dict.fromkeys(words(a, cwd) for a in todo))
    if set(ks) & no: return 'dismissed', (f"{DISMISSED} ({what}) on an earlier card since he last wrote - it was NOT run, "
                                          "and it is not put to him again. Say in one line that it waits on his word, and go on without it.")
    if set(ks) <= yes: return 'approved', f"The agent went on to {what} - you approved the same earlier in this task."
    return '', ''

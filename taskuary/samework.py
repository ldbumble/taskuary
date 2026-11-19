"""ONE JOB IS ONE TASK, AT EVERY DOOR (the owner's live app, 2026-11-18): an agent working one task broke "the bed board" out into a new
coding task the day after a chat had already made one for the same work - two open tasks, two agents, one job. Before the one start road
(concierge.handoff_task) or a break-out makes a task, the owner's open tasks go to the model with the new work, and it says whether one of
them IS that work. Meaning is the model's to read (rule 2): each open task with its ask in full and who asked (asks), never a word
match. No AI, no open task, an answer that names nothing open: a new task, as before."""
import json, re
from loguru import logger

SYSTEM = ("The owner wants a piece of work started. Below it are the owner's open tasks, each with its tid, who asked for it and its ask in "
          "full. Say whether one of them is ALREADY THIS SAME WORK - the same job or matter, a part of it or a restatement of it - judged by "
          "meaning, not wording: it is the same only when doing one would do the other. Sharing a system, a name, a person or a topic is not "
          'enough. Answer JSON only: {"same_as": <that task\'s tid, or null>}')
# ...EACH ASK IN FULL, AND WHO ASKED (design round 4, H4: a colleague's question about a sync and her sign-up list were read as his code fix in
# the same system - from one line of 140 characters a task is a name and a topic, and two jobs on one system look alike)
ASK_CHARS, ASKS = 600, 30


def asks(store, skip=()) -> list:
    "The owner's open tasks for the check: ref and tid, title, who asked, the ask in full (context._asks) - newest activity first."
    from . import context
    from .senders import channel_name
    from .store import task_ref
    out = []
    for t in store.tasks_open_brief(ASKS + len(skip)):
        if t['TaskId'] in skip: continue
        who = 'the owner himself' if context._own(t) else ' on '.join(x for x in (context._short(t.get('FromName'), 40) or 'someone',
                                                                                  channel_name(t.get('Channel') or t.get('Source'))) if x)
        out.append(f"- {task_ref(t['TaskId'])} (tid {t['TaskId']}) {context._short(t.get('Title'), 80)} | asked by {who} | the ask: "
                   f"{context._short(context._asks(t) or t.get('Summary'), ASK_CHARS)}")
        if len(out) >= ASKS: break
    return out


def same_open_task(store, words: str, skip=(), llm=None, who: str = 'the owner himself') -> int | None:
    "The tid of the open task the model reads as this same work, or None - `skip`: tasks never to name (the one asking); `who`: who asks it."
    words, skip = ' '.join(str(words or '').split()), {int(x) for x in skip if x}
    if not words: return None
    lines = asks(store, skip)
    if not lines: return None
    if llm is None:
        from .concierge import brain
        llm = brain(store, fast=True)
    if not llm: return None
    try:
        raw = llm(SYSTEM, f"THE NEW WORK (asked by {who}):\n{words[:3000]}\n\nTHE OWNER'S OPEN TASKS:\n" + '\n'.join(lines))
        same = json.loads(re.sub(r'^```(json)?|```$', '', str(raw or '').strip(), flags=re.M)).get('same_as')
        tid = int(same) if same not in (None, '', False) else None
    except Exception as e:
        logger.info(f'same-work check skipped, a new task is made: {e}'); return None
    t = store.get_task(tid) if tid and tid not in skip else None
    return tid if t and t.get('Status') not in ('done', 'dropped') else None


def tell(store, tid: int, words: str, actor: str = 'owner', files=None):
    """HIS words, heard by the agent on the task that is already that work - a line on the one road a line he types takes (general.take_line).
    An agent's ask or a break-out is Taskuary's, never his: those go by general.tell."""
    from . import general
    return general.take_line(store, int(tid), words, files, actor, wait=False)


def hand(store, tid: int, words: str, actor: str = 'owner') -> str:
    """Taskuary's words - an agent's ask, a part broken out - to the agent of the open task that is already that work: by general.tell, the one
    road Taskuary's notes take; and where no agent ever worked it (tell hands nothing), that task's agent STARTED by the dispatch door with
    the words as its opening Taskuary note - kept nowhere, they vanished (rule 4). -> 'told', 'woke', 'started', or '' when it could not."""
    from . import general, kinds
    if (how := general.tell(store, int(tid), words, actor)): return how
    from .server import _start_new_task
    k = str((store.get_task(int(tid)) or {}).get('Kind') or '').lower()
    return 'started' if _start_new_task(int(tid), k if k in kinds.AGENT else 'general', words, '')['started'] else ''

"""ONE JOB IS ONE TASK, AT EVERY DOOR (the owner's live app, 2026-11-18): an agent working one task broke "the bed board" out into a new
coding task the day after a chat had already made one for the same work - two open tasks, two agents, one job. Before the one start road
(concierge.handoff_task) or a break-out makes a task, the owner's open tasks go to the model with the new work, and it says whether one of
them IS that work. Meaning is the model's to read (rule 2): the list is the one triage reads for same_as (context.open_items), never a word
match. No AI, no open task, an answer that names nothing open: a new task, as before."""
import json, re
from loguru import logger

SYSTEM = ("The owner wants a piece of work started. Below it are the owner's open tasks, one a line, each with its tid. Say whether one of "
          "them is ALREADY THIS SAME WORK - the same job or matter, a part of it or a restatement of it - judged by meaning, not wording. "
          "Work that is only on a related topic, or a different job for the same person, is not the same. "
          'Answer JSON only: {"same_as": <that task\'s tid, or null>}')


def same_open_task(store, words: str, skip=(), llm=None) -> int | None:
    "The tid of the open task the model reads as this same work, or None - `skip`: tasks never to name (the one asking)."
    from . import context
    words, skip = ' '.join(str(words or '').split()), {int(x) for x in skip if x}
    if not words: return None
    lines = context.open_items(store, skip)
    if not lines: return None
    if llm is None:
        from .concierge import brain
        llm = brain(store, fast=True)
    if not llm: return None
    try:
        raw = llm(SYSTEM, f"THE NEW WORK:\n{words[:3000]}\n\nTHE OWNER'S OPEN TASKS:\n" + '\n'.join(lines))
        same = json.loads(re.sub(r'^```(json)?|```$', '', str(raw or '').strip(), flags=re.M)).get('same_as')
        tid = int(same) if same not in (None, '', False) else None
    except Exception as e:
        logger.info(f'same-work check skipped, a new task is made: {e}'); return None
    t = store.get_task(tid) if tid and tid not in skip else None
    return tid if t and t.get('Status') not in ('done', 'dropped') else None


def tell(store, tid: int, words: str, actor: str = 'owner', files=None):
    "The ask, heard by the agent on the task that is already that work - a line on the one road a line takes (general.take_line)."
    from . import general
    return general.take_line(store, int(tid), words, files, actor, wait=False)

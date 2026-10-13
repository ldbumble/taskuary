"""A goal's steps, written by the model (spec 2026-10-12). One planner for every door that opens a goal: the New sheet's Set a
goal and Re-plan (server.plan_goal), and triage opening one for an open-ended ask (ingest) - a goal opens with no steps and
this proposes them; the owner cuts or adds on the task page."""
import threading
from loguru import logger
from .store import task_ref

BACKGROUND = True        # the suite turns this off (tests/conftest.py): a plan runs only when a test asks for it


def plan(store, tid: int, text: str, llm=None):
    """A step already started is never reworded away: it stays, in its place, with its child (set_task_checklist keeps a box by
    its words), and the model's new words come around it (the review, 2026-10-12: a slot fallback pinned the child to whatever
    the model put in that slot)."""
    try:
        from . import concierge, triage
        ask = triage.extract_ask({'body': text}, llm or concierge.brain(store, fast=True), goal=True)
        texts = [x for x in ask.get('checklist') or [] if x]
        if not texts: return
        for k, i in enumerate(store.task_checklist(tid)):
            if i.get('tid') and i['text'] not in texts: texts.insert(min(k, len(texts)), i['text'])
        store.set_task_checklist(tid, texts, 'triage')
    except Exception as e: logger.info(f'could not plan {task_ref(tid)}: {e}')


def plan_later(store, tid: int, text: str):
    """The planner off the caller's thread: ingest and an operation answer at once, the steps arrive behind them."""
    if BACKGROUND: threading.Thread(target=plan, args=(store, tid, text), daemon=True, name=f'plan-{tid}').start()


def words(t: dict) -> str:
    """What the planner reads for a goal: its name, what done looks like, and the ask."""
    return f"{t.get('Title') or ''}\nDone when: {t.get('DoneWhen') or ''}\n{t.get('Summary') or ''}"

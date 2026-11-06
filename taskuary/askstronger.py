"""A stronger model, asked by the agent itself (the owner, 2026-11-06: "don't like cap. if it needs it, it calls it").

The general agent works on its brain's own model. When it is stuck on a hard judgement or a reasoning step, its `ask_stronger` tool
(agenttools) asks ONE question of the strong tier of that brain - the brain's strong model, else the first backup's, else its one model
at high effort (brainroute.strong_for) - and hands the answer back to the agent. No daily cap: the router's cap is for steps the APP
takes on its own, and this is the agent's call. The call is a route row like any other (rule 'agent asked'), with what it used, so the
task's "AI used" fold shows it. The strong model gets no tools: it thinks, the agent acts.
"""
from loguru import logger

RULE = 'agent asked'
SYSTEM = ("An agent working on a task for its owner is stuck on a hard judgement or reasoning step and asks you, a stronger model. Think "
          "it through carefully. Answer the question directly: your answer first, then the reasoning that decides it, briefly. You have "
          "no tools and cannot look anything up - when the context given is not enough to decide, say exactly what is missing.")


def ask(store, task_id: int, question: str, context: str = '') -> dict:
    """{'ok', 'answer', 'model', 'brain'} - or {'ok': False, 'says'} when nothing here has a stronger gear, or the call failed."""
    from . import aiusage, brainroute, llm
    q = str(question or '').strip()
    if not q: raise ValueError('ask_stronger needs a question')
    task = store.get_task(int(task_id))
    if not task: raise ValueError(f'no task {task_id}')
    pick, model = brainroute.strong_for(store, 'general', task)
    if not pick: return {'ok': False, 'says': 'no brain here has a stronger model or a higher effort to ask - decide with what you have, '
                                              'and say in your answer which judgement you were unsure of'}
    said = f"The agent asked {brainroute._said(store, pick)}'s strong gear{f', {brainroute.spell(model)}' if model else ''}, as it was stuck"
    rid = brainroute.log(store, brainroute.Route('general', 'strong', pick, model or '', 'strong', [], RULE, said), task_id)
    try:
        brain = llm._scrub(aiusage.metered(store, rid, llm._build_llm(store, pick, model or None, task_id=task_id, gear='strong', backups=[])))
        if not brain: brainroute.outcome(store, rid, 'error'); return {'ok': False, 'says': f'{brainroute._said(store, pick)} could not be started'}
        user = f"The task: {task.get('Title') or ''}\n\nThe question:\n{q}" + (f"\n\nWhat the agent knows:\n{str(context).strip()}" if str(context or '').strip() else '')
        answer = brain(SYSTEM, user)
    except Exception as e:
        brainroute.outcome(store, rid, 'error'); logger.info(f'ask_stronger on task {task_id}: {e}')
        return {'ok': False, 'says': f'the stronger model did not answer ({str(e)[:200]}) - go on with your own judgement'}
    return {'ok': True, 'answer': str(answer or '').strip(), 'brain': brainroute._said(store, pick), 'model': model or ''}

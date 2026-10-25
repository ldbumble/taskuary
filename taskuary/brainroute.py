"""Which brain does this job: one door in front of every AI call (the router, 2026-10-25).

Every job had one fixed brain, chosen by whichever of five resolvers its caller happened to ask. A
newsletter and a reply to the owner's manager were written by the same model - the triage one - and
nothing said so. `choose` is the single answer. Each call site names its JOB (what the call is for,
never a word from the mail), and `choose` says which brain, which model and which gear run it, with a
one-line reason a person can read.

Not `routing.py`: that name, and the `route` table, already mean mail-to-task matching.

FIXED mode is what a fresh install runs, and in it `choose` is exactly today's answer - it asks the
resolvers that already exist (llm.effective_pick, general.default_pick/_selected, agents.resolve_brain,
concierge.pick), so a fixed install behaves as it did before the router (tests/test_brainroute.py's
golden matrix). AUTO is a switch the owner turns on; nothing about it runs until they do.

All router state lives in the store - settings and the `brainroute` log - never in module globals: the
poller and the server are separate processes (dirty triggers are cross-process).
"""
from datetime import datetime, timedelta
from typing import NamedTuple
from loguru import logger

# What a call is FOR. Closed: a new call site picks one of these, and an AST test fails a build_llm without it.
JOBS = ('triage', 'draft', 'summary', 'advisor', 'memory', 'rank', 'assistant', 'general', 'coding', 'judge', 'report')
# the one-message jobs: read, judge, write - none of them can act, so asking again cannot do anything twice
ONE_SHOT = ('triage', 'draft', 'summary', 'advisor', 'memory', 'rank', 'judge', 'report')
# A job with no slot of its own rides the triage brain, as every unnamed build_llm always has (llm.build_llm).
SLOT_OF = {**{j: 'triage_ai' for j in ONE_SHOT}, 'general': 'assistant_ai', 'coding': 'default_brain', 'assistant': 'concierge_ai'}
JOB_WORDS = {'triage': 'triage', 'draft': 'a draft', 'summary': 'a summary', 'advisor': 'the Advisor', 'memory': 'memory',
             'rank': 'ranking', 'assistant': 'the Assistant', 'general': 'general work', 'coding': 'coding',
             'judge': 'a judgement', 'report': 'a report'}


class Route(NamedTuple):
    job: str; tier: str            # 'light'|'standard'|'strong'|'fixed'
    pick: str; model: str          # 'cli:<key>'|'connector:<id>'|''; a model id, 'model@effort', or '' for the brain's own
    gear: str                      # what make_cli_llm runs: 'light'|'main'|'strong'
    # the backups behind `pick`, in the owner's order - the ONE list a failover walks. Everything build_llm builds rides
    # triage_backup_ai, as it always has; a coding pane rides backup_brains (session_chain). Both settings keep their meaning.
    chain: list
    rule: str; why: str            # 'fixed' | 'you chose it' | a rule id; one sentence built from the inputs, never by a model
    difficulty: str = ''; data_class: str = ''
    escalate: str = ''             # the tier a retry would go up to, '' when none


KEEP_DAYS = 30           # how long a route row is kept (retention.tick trims the rest)


def log(store, r: 'Route', task_id=None, outcome: str = 'ok', pick: str = None, escalated_from=None) -> int | None:
    """One row per brain built: the job, what runs it and why - never the prompt or the answer. A log that cannot be written
    is never the reason a call fails, so a failure here is a debug line and None."""
    try:
        return store.add_brain_route({'At': datetime.now().isoformat(sep=' ', timespec='seconds'), 'Job': r.job,
                                      'TaskId': int(task_id) if str(task_id or '').isdigit() else None, 'Pick': r.pick if pick is None else pick,
                                      'Model': r.model, 'Tier': r.tier, 'Rule': r.rule, 'Why': r.why, 'Difficulty': r.difficulty or None,
                                      'DataClass': r.data_class or None, 'EscalatedFrom': escalated_from, 'Outcome': outcome})
    except Exception as e:
        logger.debug(f'brainroute: could not log a {r.job} route - {e}'); return None


def outcome(store, rid, said: str, why: str = None) -> None:
    "How the call ended when it was not as built: 'fallback:<pick>', 'refused:<why>', 'error'."
    if not rid: return
    try: store.set_brain_route(rid, Outcome=said, **({'Why': why} if why else {}))
    except Exception as e: logger.debug(f'brainroute: could not mark route {rid} {said} - {e}')


def trim(store, now: datetime = None) -> int:
    return store.trim_brain_routes(((now or datetime.now()) - timedelta(days=KEEP_DAYS)).isoformat(sep=' ', timespec='seconds'))


def why_for_task(store, task_id) -> str:
    "The reason behind the newest route on this task - the brain line's tooltip. '' when no AI call has been made for it."
    try: rows = store.brain_routes(int(task_id), limit=1)
    except Exception: return ''
    if not rows: return ''
    r = rows[0]
    said = str(r.get('Outcome') or 'ok')
    why = str(r.get('Why') or '').rstrip('.')
    return f'{why}.' + (f' {_said(store, said[9:])} answered instead, as its backup.' if said.startswith('fallback:') else '') if why else ''


def mode(store) -> str:
    "'fixed' (the cards, exactly as today) or 'auto'. Fixed on a fresh install: nothing changes until the owner turns Auto on."
    return 'auto' if str(store.get_setting('ai_route_mode') or '').strip().lower() == 'auto' else 'fixed'


def _backups(store) -> list:
    return [x.strip() for x in str(store.get_setting('triage_backup_ai') or '').split(',') if x.strip()]


def _said(store, pick: str) -> str:
    "The brain by the name the cards use - 'claude (CLI)', 'Azure OpenAI' - for the reason line."
    if not pick: return 'no AI'
    if pick == 'demo': return 'the demo'
    if pick.startswith('cli:'): return f'{pick[4:]} (CLI)'
    cid = pick[10:] if pick.startswith('connector:') else ''
    c = store.get_connector(int(cid)) if cid.isdigit() else None
    return (c.get('Name') or c.get('Type')) if c else pick


def session_chain(store, brain: str = None) -> list:
    "A coding pane's brains in order, head first: `brain`, then backup_brains (agents.brain_chain) - what terminal.start_on_task walks."
    from . import agents
    return agents.brain_chain(store, brain)


def _fixed(store, job: str, task=None, want_pick=None, want_model=None, gear=None) -> tuple:
    "(pick, model, gear, chain) - today's answer for this job, asked of the resolver that has always given it."
    from . import agents, llm
    if job in ONE_SHOT:
        # the same reading llm._build_llm makes: the named pick, else the triage brain, else what blank means
        pick = llm.effective_pick(store, want_pick if want_pick is not None else store.get_setting('triage_ai') or '')
        return pick, want_model or '', gear or 'light', _backups(store)
    if job == 'coding':
        pick = want_pick if want_pick is not None else agents.resolve_brain(store, 'coding', cli_only=True)  # a terminal or nothing
        return pick, want_model or '', gear or 'main', [f'cli:{k}' for k in session_chain(store, pick[4:] or None)] if pick else []
    # an explicit pick is taken with exactly the model it came with - '' is the brain's own, as build_llm always read it
    if want_pick is not None: return want_pick, want_model or '', gear or ('light' if job == 'assistant' else 'main'), _backups(store)
    if job == 'assistant':
        from . import concierge
        return concierge.pick(store), want_model or str(store.get_setting(concierge.MODEL_KEY) or '').strip(), gear or 'light', _backups(store)
    from . import general
    base, pick = general._selected(store), general.default_pick(store, task)
    model = want_model or (base[2] if pick == base[0] else general._selected(store, pick=pick)[2] if pick else '')
    return pick, model or '', gear or 'main', _backups(store)


def choose(store, job: str, task=None, want_pick=None, want_model=None, gear=None) -> Route:
    """The brain for one call of `job`. An explicit pick or model (`want_*`: the owner's picker, a saved session, a
    report's own brain, a workflow's model) always wins. `task` is the task dict or id the call is about, if any."""
    if job not in JOBS: raise ValueError(f'unknown AI job {job!r} - one of {", ".join(JOBS)}')
    if isinstance(task, int): task = store.get_task(task)
    pick, model, g, chain = _fixed(store, job, task, want_pick, want_model, gear)
    from . import agents
    chosen = want_pick is not None or bool(want_model)
    rule = 'you chose it' if chosen else 'fixed'
    if not pick: why = f'{agents.NO_AI}, so {JOB_WORDS[job]} waits'
    else: why = f"{JOB_WORDS[job]} on {_said(store, pick)}{f', {model}' if model else ''}, {'as picked for it' if chosen else 'as its card says'}"
    return Route(job, 'fixed', pick, model, g, [c for c in chain if c and c != pick], rule, why[0].upper() + why[1:])

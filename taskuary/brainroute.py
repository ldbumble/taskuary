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
# ...of which these may be asked again of a strong model (a report may research with tools, so it is not one of them)
ESCALATES = ('triage', 'draft', 'summary', 'judge', 'advisor', 'rank', 'memory')
# A job with no slot of its own rides the triage brain, as every unnamed build_llm always has (llm.build_llm).
SLOT_OF = {**{j: 'triage_ai' for j in ONE_SHOT}, 'draft': 'draft_ai', 'general': 'assistant_ai', 'coding': 'default_brain',
           'assistant': 'concierge_ai'}
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


def judged(store, task) -> dict:
    """{difficulty, sure, data_class, by} - triage's judgements on this task, or the owner's correction of them; '' / None where no
    verdict gave one. Standard and ordinary are what an unjudged task reads as: nothing steps up on a judgement nobody made."""
    tid = task.get('TaskId') if isinstance(task, dict) else task
    try: j = store.task_judged(int(tid)) if str(tid or '').isdigit() else {}
    except Exception: j = {}
    return {'difficulty': j.get('Difficulty') or '', 'sure': None if j.get('Sure') is None else bool(j['Sure']),
            'data_class': j.get('DataClass') or '', 'by': j.get('By') or ''}


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


def _own(store, pick: str, field: str, cfg=None) -> str:
    "A value the owner set on this brain itself - its CLI connection, or its AI card's config - or ''."
    import json
    if str(pick or '').startswith('cli:'):
        from . import agents, config
        cfg = config.load() if cfg is None else cfg
        key = agents.brain_key(store, pick, cfg)
        return str(((cfg.get('cli_connections') or {}).get(key) or {}).get(field) or '').strip()
    cid = str(pick or '')[10:] if str(pick or '').startswith('connector:') else ''
    c = store.get_connector(int(cid)) if cid.isdigit() else None
    try: return str(json.loads((c or {}).get('ConfigJson') or '{}').get(field) or '').strip()
    except ValueError: return ''


def strong_of(store, pick: str, cfg=None) -> str:
    """This brain's STRONG gear - the owner's strong_model on its CLI connection or its AI card - or '' when it has none.
    Blank is no strong tier, and nothing is inferred from a model's name (setup never assumes an AI)."""
    return _own(store, pick, 'strong_model', cfg)


# ── the data-type seam ─────────────────────────────────────────────────────────────────────────────────────────────────────────
# Triage judges whether a task carries sensitive data; each AI card has the owner's own "may read sensitive data" flag, off by
# default and never set by code (no card is pre-marked - a gateway's card included). Once the owner turns the rule on, a sensitive
# task reaches only a marked AI, its failover included, and with none it WAITS and says why: it never falls back to one the rule
# keeps out. HIPAA later is a class and a flag, not a new engine (the router, 2026-10-25).
SENSITIVE_OK = 'sensitive_ok'
NO_SENSITIVE = 'No AI here may read sensitive data; mark one on its card in Settings'


def may_read_sensitive(store, pick: str, cfg=None) -> bool:
    return _own(store, pick, SENSITIVE_OK, cfg) in ('1', 'true', 'yes')


def session_chain(store, brain: str = None) -> list:
    "A coding pane's brains in order, head first: `brain`, then backup_brains (agents.brain_chain) - what terminal.start_on_task walks."
    from . import agents
    return agents.brain_chain(store, brain)


def _fixed(store, job: str, task=None, want_pick=None, want_model=None, gear=None) -> tuple:
    "(pick, model, gear, chain) - today's answer for this job, asked of the resolver that has always given it."
    from . import agents, llm
    if job == 'draft' and want_pick is None:
        # Drafting's own card (the owner, 2026-10-25), blank = the triage brain exactly as before; its model box, blank = that brain's own
        own = '' if agents.stale(store, 'draft_ai') else str(store.get_setting('draft_ai') or '').strip()
        pick = llm.effective_pick(store, own or store.get_setting('triage_ai') or '')
        # ...and its model only once a drafting brain is chosen: blank is the triage brain on its own model, exactly (2026-10-25)
        return pick, want_model or (str(store.get_setting('draft_model') or '').strip() if own else ''), gear or 'light', _backups(store)
    if job in ONE_SHOT:
        # the same reading llm._build_llm makes: the named pick, else the triage brain, else what blank means
        pick = llm.effective_pick(store, want_pick if want_pick is not None else store.get_setting('triage_ai') or '')
        return pick, want_model or '', gear or 'light', _backups(store)
    if job == 'coding':
        pick = want_pick if want_pick is not None else agents.resolve_brain(store, 'coding', cli_only=True)  # a terminal or nothing
        return pick, want_model or '', gear or 'main', [f'cli:{k}' for k in session_chain(store, pick[4:] or None)] if pick else []
    # an explicit pick is taken with exactly the model it came with - '' is the brain's own model - and an empty pick is what
    # blank means (llm.effective_pick), the reading _build_llm makes of it anyway: the log names the brain that runs, not ''
    if want_pick is not None:
        return want_pick or llm.effective_pick(store, ''), want_model or '', gear or ('light' if job == 'assistant' else 'main'), _backups(store)
    if job == 'assistant':
        from . import concierge
        return concierge.pick(store), want_model or str(store.get_setting(concierge.MODEL_KEY) or '').strip(), gear or 'light', _backups(store)
    from . import general
    base, pick = general._selected(store), general.default_pick(store, task)
    model = want_model or (base[2] if pick == base[0] else general._selected(store, pick=pick)[2] if pick else '')
    return pick, model or '', gear or 'main', _backups(store)


# ── Auto mode: the rules ───────────────────────────────────────────────────────────────────────────────────────────────────────
# What Auto turns on, each shown as a sentence with its own switch (the owner, 2026-10-25: Auto is off on a fresh install, and in it
# each card is its job's STANDARD tier - every model still lives in one place). A rule matches judgement values and ids only, never
# words from the mail; the first rule that sets a tier wins.
TIERS = ('light', 'standard', 'strong')
GEAR_OF = {'light': 'light', 'standard': 'main', 'strong': 'strong'}
DEFAULT_RULES = [
    {'id': 'quick-jobs', 'when': {'job': ['triage', 'rank', 'memory', 'advisor', 'summary']}, 'use': {'tier': 'light'}},
    {'id': 'hard-work', 'when': {'job': ['draft', 'general', 'coding'], 'difficulty': ['hard']}, 'use': {'tier': 'strong'}},
    {'id': 'work', 'when': {'job': ['draft', 'general', 'coding']}, 'use': {'tier': 'standard'}},
    # an answer that could not be read, or one its model said it was unsure of, is asked once of a strong model - only for the jobs
    # that read and write; an agent that can act is never re-run by itself (it may have done half its work), it offers a press
    {'id': 'unsure', 'when': {'job': list(ESCALATES)}, 'use': {'escalate': True}},
    # sensitive data only to an AI whose card is marked for it - off until the owner turns it on, in either mode: a constraint, not a tier
    {'id': 'sensitive', 'when': {'data_class': ['sensitive']}, 'use': {'only': 'flagged'}, 'on': False},
]
WHEN_KEYS = ('job', 'difficulty', 'data_class', 'origin', 'person')


def rules(store) -> list:
    """The rules in the order they are tried: the owner's saved list (ai_route_rules), then any default it does not hold yet - a
    default the owner switched off stays off, and one added in a later release arrives as shipped."""
    import json
    try: saved = json.loads(str(store.get_setting('ai_route_rules') or '').strip() or '[]')
    except ValueError: saved = []
    saved = [r for r in saved if isinstance(r, dict) and r.get('id') and isinstance(r.get('when'), dict) and isinstance(r.get('use'), dict)]
    have = {r['id'] for r in saved}
    out = [*saved, *({**d, 'by': 'default'} for d in DEFAULT_RULES if d['id'] not in have)]
    return [{**r, 'on': r.get('on', True) is not False, 'by': r.get('by') or 'owner'} for r in out]


def save_rules(store, rs: list, actor: str = 'owner') -> list:
    "The owner's list, checked: known conditions and uses only - a rule nothing could ever match is refused, never stored."
    import json
    clean = []
    for r in rs or []:
        when, use = dict(r.get('when') or {}), dict(r.get('use') or {})
        if set(when) - set(WHEN_KEYS): raise ValueError(f"a rule can only match on {', '.join(WHEN_KEYS)}")
        if any(j not in JOBS for j in when.get('job') or []): raise ValueError('a rule names a job the router does not know')
        if 'tier' in use and use['tier'] not in TIERS: raise ValueError(f"a rule's tier is one of {', '.join(TIERS)}")
        if not set(use) & {'tier', 'escalate', 'only'}: raise ValueError('a rule must say what it does')
        clean.append({'id': str(r.get('id') or f'r{len(clean) + 1}')[:40], 'when': {k: [str(x) for x in v] for k, v in when.items() if v},
                      'use': use, 'on': r.get('on', True) is not False, 'by': r.get('by') or 'owner'})
    if len({r['id'] for r in clean}) < len(clean): raise ValueError('two rules share one name')
    store.set_setting('ai_route_rules', json.dumps(clean), actor)
    return rules(store)


def _people(store, task) -> set:
    """Who the task is with, as the people model keys them - the person seam: `people.keys_of_task(store, task) -> [key]`, which the
    memory redesign provides. Only the owner writes a person rule (none ships). With no people model in this build, or one that
    fails, there is nobody to match, so a person rule matches nothing rather than guessing at a name."""
    try: from . import people
    except ImportError: return set()
    f = getattr(people, 'keys_of_task', None)
    try: return set(f(store, task)) if f and task else set()
    except Exception: return set()


def facts(store, job: str, task=None) -> dict:
    "What a rule may match on: the job and the task's judgements - an unjudged task reads as standard and ordinary."
    j, o = judged(store, task) if task else {}, ''
    if task:
        from . import origin
        try: o = origin.of_task(store, task['TaskId'])[0]
        except Exception: o = ''
    return {'job': job, 'difficulty': j.get('difficulty') or 'standard', 'data_class': j.get('data_class') or 'ordinary', 'origin': o,
            'person': _people(store, task)}


def matches(rule: dict, f: dict) -> bool:
    for k, want in (rule.get('when') or {}).items():
        got = f.get(k)
        if not (set(want) & got if isinstance(got, set) else got in want): return False
    return True


def _first(store, f: dict, use: str):
    return next((r for r in rules(store) if r['on'] and use in r['use'] and matches(r, f)), None)


def choose(store, job: str, task=None, want_pick=None, want_model=None, gear=None) -> Route:
    """The brain for one call of `job`. An explicit pick or model (`want_*`: the owner's picker, a saved session, a
    report's own brain, a workflow's model) always wins. `task` is the task dict or id the call is about, if any.

    In Auto mode the rules pick the TIER - light, standard or strong - on the brain the cards (or an explicit pick) name. An
    explicit model is never overridden, the Assistant keeps its own model, and the guide chat keeps its quick gear."""
    if job not in JOBS: raise ValueError(f'unknown AI job {job!r} - one of {", ".join(JOBS)}')
    if task is not None and not isinstance(task, dict): task = store.get_task(int(task)) if str(task).isdigit() else None
    pick, model, g, chain = _fixed(store, job, task, want_pick, want_model, gear)
    j = judged(store, task) if task else {}
    from . import agents
    from .general import is_dock
    chosen = want_pick is not None or bool(want_model)
    rule, tier = ('you chose it' if chosen else 'fixed'), 'fixed'
    f = facts(store, job, task) if pick and (task or mode(store) == 'auto') else {}
    # FIRST, THE DATA (a hard constraint, failing closed - in either mode, once the owner turns its rule on): over an explicit pick too
    only, held = (_first(store, f, 'only') if task and f else None), ''
    if only:
        ok = [p for p in [pick, *chain] if p and may_read_sensitive(store, p)]
        if not ok: pick, chain, held, rule, tier = '', [], NO_SENSITIVE, only['id'], 'held'
        elif ok[0] != pick: held, model = f"; only an AI marked for sensitive data may read it (rule {only['id']})", ''
        if ok: pick, chain = ok[0], ok[1:]
    if not pick: why = f"{held or agents.NO_AI}, so {JOB_WORDS[job]} waits"
    else: why = f"{JOB_WORDS[job]} on {_said(store, pick)}{f', {model}' if model else ''}, {'as picked for it' if chosen else 'as its card says'}{held}"
    if pick and mode(store) == 'auto' and not want_model and not (job == 'general' and is_dock(task)):
        r = _first(store, f, 'tier')
        if r:
            tier, rule, said = r['use']['tier'], r['id'], ''
            if tier == 'strong':
                # the brain's own strong gear, else the first backup that has one - and for coding only ever a CLI's. A brain picked
                # explicitly is kept: without a strong model it does the work at standard
                ok = lambda p: bool(strong_of(store, p)) and (job != 'coding' or p.startswith('cli:'))
                to = pick if ok(pick) else '' if want_pick is not None else next((c for c in chain if c and ok(c)), '')
                if not to: tier, said = 'standard', f"; {'it has no' if want_pick is not None else 'no brain here has a'} strong model, so standard"
                elif to != pick: said, chain, pick = f'; {_said(store, pick)} has no strong model', [pick, *chain], to
            if tier == 'strong' and not cap_left(store): tier, said = 'standard', f"; today's {cap(store)} strong calls are spent, so standard"
            # the card's model IS the standard tier; strong runs the brain's strong gear and light its quick one
            g, model = GEAR_OF[tier], (model if tier == 'standard' else '')
            hard = f" judged {f['difficulty']}" if 'difficulty' in r['when'] else ''
            why = f"{JOB_WORDS[job]}{hard} -> {tier} on {_said(store, pick)}{f', {model}' if model else ''} (rule {rule}){said}"
    # a brain resting on its usage limit hands the call to the first backup that is not (Auto mode; the cards stand in Fixed)
    if pick and mode(store) == 'auto' and pick in (cold := cooldowns(store)):
        to = next((c for c in chain if c and c not in cold and (job != 'coding' or c.startswith('cli:'))), '')
        if to:
            why += f"; {_said(store, pick)} is limited until {cold[pick].strftime('%H:%M')}, so {_said(store, to)}"
            # ...on its own model, as a failover always is: the resting brain's model id means nothing to another provider
            chain, pick, model = [pick, *chain], to, ''
            if tier == 'strong' and not strong_of(store, pick): tier, g = 'standard', GEAR_OF['standard']
    up = ''
    if pick and mode(store) == 'auto' and tier != 'strong' and job in ESCALATES and _first(store, f, 'escalate'): up = 'strong'
    return Route(job, tier, pick, model, g, [c for c in chain if c and c != pick], rule, why[0].upper() + why[1:],
                 (j or {}).get('difficulty', ''), (j or {}).get('data_class', ''), up)


def for_session(store, task, brain: str = None) -> tuple:
    """(brain, model) a coding pane opens on. Fixed mode, or no rule asking for more: (brain, None) - exactly today's choice. In
    Auto, hard work opens on a CLI's strong gear, and the route is logged; a coding pane never lands on an API connector."""
    if mode(store) != 'auto': return brain, None
    r = choose(store, 'coding', task, want_pick=f'cli:{brain}' if brain else None)
    log(store, r, (task or {}).get('TaskId') if isinstance(task, dict) else task)
    if r.gear != 'strong' or not r.pick.startswith('cli:'): return brain, None
    return r.pick[4:], strong_of(store, r.pick) or None


def _stepped_already(store, task_id, job: str) -> bool:
    if not str(task_id or '').isdigit(): return False
    return any(x.get('EscalatedFrom') and x.get('Job') == job for x in store.brain_routes(int(task_id), limit=200))


def step_up(store, r: 'Route', rid, task_id, why: str, build):
    """The strong brain for one more try at a one-shot answer that came back `why` ('unreadable' | 'unsure'), or None. Once per
    item per job; never past the day's cap; the brain's own strong gear first, else the first backup with one. The try is logged
    with EscalatedFrom, and the first route is marked 'escalated'. `build(pick)` makes the brain on its strong gear."""
    if not r.escalate or _stepped_already(store, task_id, r.job): return None
    if not cap_left(store): return None
    to = next((p for p in [r.pick, *r.chain] if p and strong_of(store, p)), '')
    if not to: return None
    try: brain = build(to)
    except Exception as e:                            # a stranger's task its strong brain refuses stays as the first answer had it
        logger.debug(f'brainroute: no step up for {r.job} - {e}'); return None
    if brain is None: return None
    said = f"{JOB_WORDS[r.job]} came back {why} on {_said(store, r.pick)}, so it was asked once of {_said(store, to)}'s strong model"
    up = Route(r.job, 'strong', to, '', 'strong', [], 'unsure', said[0].upper() + said[1:], r.difficulty, r.data_class)
    log(store, up, task_id, escalated_from=rid); outcome(store, rid, 'escalated')
    return brain


# ── health and the day's cap (Auto mode) ─────────────────────────────────────────────────────────────────────────────────────
# A CLI refused on its usage allowance says when it comes back; until then the router hands its calls to the next brain instead
# of to one that will refuse again. Kept in a setting, not a module global: the poller and the server are separate processes.
COOL_KEY, CAP_KEY = 'ai_route_cooldown', 'ai_route_strong_cap'


def cooldowns(store, now: datetime = None) -> dict:
    "{pick: until} for every brain still resting - a reset already past is dropped."
    import json
    try: d = json.loads(str(store.get_setting(COOL_KEY) or '').strip() or '{}')
    except ValueError: d = {}
    now = now or datetime.now()
    out = {}
    for p, u in (d.items() if isinstance(d, dict) else ()):
        try: t = datetime.fromisoformat(str(u))
        except ValueError: continue
        if t > now: out[p] = t
    return out


def cool(store, pick: str, until: datetime) -> None:
    "Rest `pick` until `until` (the CLI's own reset time). Never longer than a week: a misread stamp must not shelve a brain for good."
    import json
    if not pick or not until: return
    until = min(until, datetime.now() + timedelta(days=7))
    d = {p: t.isoformat(sep=' ', timespec='minutes') for p, t in cooldowns(store).items()}
    d[pick] = until.isoformat(sep=' ', timespec='minutes')
    try: store.set_setting(COOL_KEY, json.dumps(d), 'router')
    except Exception as e: logger.debug(f'brainroute: could not rest {pick} - {e}')


def cap(store):
    "The owner's limit on strong calls a day, or None (blank, the default: no cap)."
    v = str(store.get_setting(CAP_KEY) or '').strip()
    return int(v) if v.isdigit() else None


def strong_today(store, now: datetime = None) -> int:
    return store.count_brain_routes(since=(now or datetime.now()).strftime('%Y-%m-%d'), tier='strong')


def cap_left(store) -> bool:
    "Whether a strong call is still allowed today. Blank cap (the default) is no cap."
    n = cap(store)
    return n is None or strong_today(store) < n


# ── what Settings shows: the mode line, the rules as sentences, the cap line, the recent routes ───────────────────────────────
PLURAL = {'triage': 'triage', 'draft': 'drafts', 'summary': 'summaries', 'advisor': 'the Advisor', 'memory': 'memory', 'rank': 'ranking',
          'assistant': 'the Assistant', 'general': 'general work', 'coding': 'coding', 'judge': 'judgements', 'report': 'reports'}
USE_WORDS = {'light': 'the quick model', 'standard': "the card's own model", 'strong': 'the strong model'}


def _and(xs) -> str:
    xs = [str(x) for x in xs if x]
    return '' if not xs else xs[0] if len(xs) == 1 else f"{', '.join(xs[:-1])} and {xs[-1]}"


def sentence(r: dict) -> str:
    """A rule as the owner reads it - "Hard drafts, general work and coding -> the strong model" - built from its values, so the
    sentence can never say something the rule does not do."""
    w, u = r.get('when') or {}, r.get('use') or {}
    jobs = _and(PLURAL.get(j, j) for j in w.get('job') or []) or 'every job'
    who = ' '.join(x for x in (_and(w.get('difficulty') or []), jobs) if x)
    if w.get('data_class'): who += f" carrying {_and(w['data_class'])} data"
    if w.get('origin'): who += f" written by {_and('a stranger' if o == 'stranger' else 'you' if o == 'owner' else 'people you trust' for o in w['origin'])}"
    if w.get('person'): who += f" with {_and(w['person'])}"
    if u.get('escalate'): s = f'Unreadable or unsure answers from {who} -> ask the strong model once'
    elif u.get('only'): s = f'{who} -> only an AI whose card says it may read sensitive data'
    else: s = f"{who} -> {USE_WORDS.get(u.get('tier'), u.get('tier'))}"
    return s[0].upper() + s[1:]


def panel(store) -> dict:
    "Everything the router's part of Settings draws, in one read."
    n = cap(store)
    return {'mode': mode(store), 'rules': [{**r, 'sentence': sentence(r)} for r in rules(store)], 'cap': '' if n is None else n,
            'used_today': strong_today(store), 'jobs': list(JOBS), 'tiers': list(TIERS), 'difficulties': ['quick', 'standard', 'hard'],
            'warning': coverage_warning(store)}


def set_panel(store, mode_: str = None, rs: list = None, cap_: str = None, actor: str = 'owner') -> dict:
    if mode_ is not None:
        if mode_ not in ('fixed', 'auto'): raise ValueError('the mode is fixed or auto')
        store.set_setting('ai_route_mode', mode_, actor)
    if rs is not None: save_rules(store, rs, actor)
    if cap_ is not None:
        c = str(cap_).strip()
        if c and not c.isdigit(): raise ValueError('the cap is a whole number of strong calls a day, or blank for none')
        store.set_setting(CAP_KEY, c, actor)
    return panel(store)


def recent(store, limit: int = 20) -> list:
    "The newest routes, each one line: job, task, tier -> brain and model, and why. Read-only."
    from .store import task_ref
    return [{**x, 'ref': task_ref(x['TaskId']) if x.get('TaskId') else '', 'brain': _said(store, x.get('Pick') or '')}
            for x in store.brain_routes(None, limit=limit)]


def coverage_warning(store) -> str:
    """Triage reads every message BEFORE its data is judged, so once a rule keeps sensitive data to marked AIs, the triage brain has
    to be one of them or it reads what the rule keeps from the rest of the work. Said in Settings; '' while that holds."""
    if not any(r['on'] and 'only' in r['use'] for r in rules(store)): return ''
    t = choose(store, 'triage')
    if not t.pick or may_read_sensitive(store, t.pick): return ''
    return (f"Triage reads every message before it is judged, and {_said(store, t.pick)} is not marked to read sensitive data - "
            'mark it on its card, or sensitive mail is read by an AI your rule keeps from the rest of the work.')


def session_allowed(store, task, chain: list) -> tuple:
    """(chain, why) for a coding pane: only the CLIs that may read this task's data once the owner's data rule is on - none at all
    is ([], the reason), and the pane does not open. Any other task keeps its chain exactly."""
    if not task: return chain, ''
    f = facts(store, 'coding', task)
    if not _first(store, f, 'only'): return chain, ''
    from . import agents
    ok = [c for c in chain if may_read_sensitive(store, f"cli:{c or agents.default_brain(store) or ''}")]
    return (ok, '') if ok else ([], f'{NO_SENSITIVE}, so the coding agent does not start')


def strong_for(store, job: str, task, first: str = None) -> tuple:
    """(pick, model) for "Run again on the strong model": `first` (the brain that ran it) or the job's own brain when it has a strong
    model, else the first backup with one - a coding pane only ever a CLI's. ('', '') when no brain here has one."""
    r = choose(store, job, task, want_pick=first or None)
    ok = lambda p: bool(strong_of(store, p)) and (job != 'coding' or p.startswith('cli:'))
    to = next((p for p in [r.pick, *r.chain] if p and ok(p)), '')
    return (to, strong_of(store, to)) if to else ('', '')

"""Which brain does this job: one door in front of every AI call (the router, 2026-10-25).

Every job had one fixed brain, chosen by whichever of five resolvers its caller happened to ask. A
newsletter and a reply to the owner's manager were written by the same model - the triage one - and
nothing said so. `choose` is the single answer. Each call site names its JOB (what the call is for,
never a word from the mail), and `choose` says which brain, which model and which gear run it, with a
one-line reason a person can read.

Not `routing.py`: that name, and the `route` table, already mean mail-to-task matching.

AUTO is what an install runs unless its owner chose Fixed (the owner, 2026-11-06: "it should be on auto routing by default using
triage designation"): triage's quick/standard/hard judgement picks the brain's light, card or strong model, and a brain with only
one model thinks less or harder instead where its CLI takes an effort flag (`lift`). FIXED is the cards, exactly as before the
router - in it `choose` asks the resolvers that already exist (llm.effective_pick, general.default_pick/_selected,
agents.resolve_brain, concierge.pick), so a fixed install behaves as it always did (tests/test_brainroute.py's golden matrix).

All router state lives in the store - settings and the `brainroute` log - never in module globals: the
poller and the server are separate processes (dirty triggers are cross-process).
"""
import threading, weakref
from datetime import datetime, timedelta
from typing import NamedTuple
from loguru import logger

# What a call is FOR. Closed: a new call site picks one of these, and an AST test fails a build_llm without it.
JOBS = ('triage', 'draft', 'summary', 'advisor', 'memory', 'rank', 'assistant', 'general', 'coding', 'judge', 'report', 'quick_work')
# the one-message jobs: read, judge, write - none of them can act, so asking again cannot do anything twice
ONE_SHOT = ('triage', 'draft', 'summary', 'advisor', 'memory', 'rank', 'judge', 'report')
# ...of which these may be asked again of a strong model (a report may research with tools, so it is not one of them)
ESCALATES = ('triage', 'draft', 'summary', 'judge', 'advisor', 'rank', 'memory')
# A job with no slot of its own rides the triage brain, as every unnamed build_llm always has (llm.build_llm).
SLOT_OF = {**{j: 'triage_ai' for j in ONE_SHOT}, 'general': 'assistant_ai', 'quick_work': 'assistant_ai', 'coding': 'default_brain',
           'assistant': 'concierge_ai'}
JOB_WORDS = {'triage': 'triage', 'draft': 'a redraft', 'summary': 'a summary', 'advisor': 'the Advisor', 'memory': 'memory',
             'rank': 'ranking', 'assistant': 'the Assistant', 'general': 'general work', 'coding': 'coding',
             'quick_work': 'quick general work', 'judge': 'a judgement', 'report': 'a report'}


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
    level: str = ''                # 'quick'|'normal'|'hard' when the owner's AI for that level runs it (by_level), else ''


KEEP_DAYS = 30           # how long a route's reason is kept (retention.tick trims the rest)
USAGE_DAYS = 90          # ...and the row itself, for what the call used: the AI-use dashboard reads 90 days (aiusage)


def log(store, r: 'Route', task_id=None, outcome: str = 'ok', pick: str = None, escalated_from=None) -> int | None:
    """One row per brain CALLED (Lazy) or refused: the job, what runs it and why - never the prompt or the answer. A log that cannot be
    written is never the reason a call fails, so a failure here is a debug line and None."""
    escalated_from = rid_of(escalated_from)
    from .aiusage import asked
    a = asked()            # who is asking, and about which message - the asker's own note, blank when nobody named the call
    try:
        rid = store.add_brain_route({'At': datetime.now().isoformat(sep=' ', timespec='seconds'), 'Job': r.job,
                                     'TaskId': int(task_id) if str(task_id or '').isdigit() else None, 'Pick': r.pick if pick is None else pick,
                                     'Model': r.model, 'Tier': r.tier, 'Rule': r.rule, 'Why': r.why, 'Difficulty': r.difficulty or None,
                                     'DataClass': r.data_class or None, 'EscalatedFrom': escalated_from, 'Outcome': outcome,
                                     'Caller': a.caller if a else None, 'MessageId': a.message_id if a else None})
        if a and rid: a.rids.append(rid)
        return rid
    except Exception as e:
        logger.debug(f'brainroute: could not log a {r.job} route - {e}'); return None


# A ROW PER CALL, NOT PER BUILD (the owner's live install, 2026-11-06): the row was written when a brain was BUILT, and the chat poll
# built triage's once a second and never called it - 234 rows in four minutes, every one without a task, a time or a token, counted on
# the AI-use dashboard and the task's AI-used list as calls. build_llm hands out a Lazy instead: the row is written on the brain's first
# call (aiusage.Metered), or when the build itself ends in a refusal or an error (outcome) - so the reason is kept whenever it mattered.
# ...AND A ROW PER ASKER (2026-11-11): one triage brain is built for a poll and judges every mail in it, so its one row said "3 calls"
# and one sum for three mails. Asked under another note (aiusage.asking - another mail, another function), the brain writes a new row.
class Lazy:
    """A route row written on first use: called, it is the row's id (written then, once per asker - aiusage.Asked, the calls nobody
    named sharing one of their own); a brain built and never called writes nothing. `last` is the row to MARK (outcome): the one last
    written, so a mark made once the asker has left never opens a new, empty row."""
    def __init__(self, store, r: 'Route', task_id=None, pick: str = None):
        self.store, self.r, self.task_id, self.pick, self._lock = store, r, task_id, pick, threading.Lock()
        self._ids, self._own, self._last = weakref.WeakKeyDictionary(), None, None
    def _new(self):
        self._last = log(self.store, self.r, self.task_id, pick=self.pick) or 0; return self._last
    def __call__(self) -> int | None:
        from .aiusage import asked
        a = asked()
        with self._lock:
            if a is None:
                if self._own is None: self._own = self._new()
                return self._own or None
            if a not in self._ids: self._ids[a] = self._new()
            return self._ids[a] or None
    def last(self) -> int | None:
        with self._lock:
            if self._last is None: self._own = self._new()
            return self._last or None

def rid_of(rid): return rid() if isinstance(rid, Lazy) else rid


def outcome(store, rid, said: str, why: str = None) -> None:
    "How the call ended when it was not as built: 'fallback:<pick>', 'refused:<why>', 'error'."
    rid = rid.last() if isinstance(rid, Lazy) else rid
    if not rid: return
    try: store.set_brain_route(rid, Outcome=said, **({'Why': why} if why else {}))
    except Exception as e: logger.debug(f'brainroute: could not mark route {rid} {said} - {e}')


def trim(store, now: datetime = None) -> int:
    at = lambda d: ((now or datetime.now()) - timedelta(days=d)).isoformat(sep=' ', timespec='seconds')
    return store.trim_brain_routes(at(USAGE_DAYS), at(KEEP_DAYS))


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
    """'auto' (triage's judgement picks the model) or 'fixed' (the cards, exactly as before the router). Auto unless the owner chose
    Fixed: a fresh install seeds 'auto', and an install still on the old 'fixed' seed nobody chose moves to it once (store.Store)."""
    return 'fixed' if str(store.get_setting('ai_route_mode') or '').strip().lower() == 'fixed' else 'auto'


def _backups(store) -> list:
    return [x.strip() for x in str(store.get_setting('triage_backup_ai') or '').split(',') if x.strip()]


def _said(store, pick: str) -> str:
    "The brain by the name the cards use - 'claude (CLI)', 'Azure OpenAI' - for the reason line."
    if not pick: return 'no AI'
    if pick == 'demo': return 'the demo'
    if pick.startswith('cli:'):
        # the name its card and every picker say (clis.KNOWN: 'OpenAI Codex CLI'), never a second one ('codex (CLI)') for the same thing
        from . import agents
        from .clis import KNOWN
        k = pick[4:]
        return {x['cmd']: x['label'] for x in KNOWN}.get(agents.cli_of(dict(agents.connection_brains(store)).get(k), k)) or f'{k} (CLI)'
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


# ONE MODEL, STILL THREE STEPS (the owner, 2026-11-06: "if it's api or something that only has one model use effort instead if they
# support it"). A brain with no model of its own for a tier runs its one model at this effort - the 'model@effort' pick every CLI road
# already spells in its own flag (climodels.effort_args), and make_llm sends to the API cards whose provider takes one
# (llm.EFFORT_TAKERS). Any other brain keeps its answer.
LIFT = {'light': 'low', 'strong': 'high'}
EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')


def _cli(store, pick: str, cfg=None) -> str:
    from . import agents, config
    from .aidefaults import _cli_of
    cfg = config.load() if cfg is None else cfg
    return _cli_of(cfg, agents.brain_key(store, pick, cfg))


def lift(store, pick: str, tier: str, model: str = '', cfg=None) -> str:
    """'<model>@<effort>' - `model` (else the brain's own) at the effort `tier` runs at - for a brain with no model of its own for that
    tier that takes an effort: a CLI with an effort flag, or an AI card whose provider takes one (an AI card has no quick model box, so
    its quick work is always its one model, thinking less). '' otherwise. A quick gear a CLI already ships (llm.LIGHT_DEFAULT: claude's
    haiku, codex's low effort) is its own answer, and an effort already at or past the step is no step."""
    p = str(pick or '')
    if tier not in LIFT or not p.startswith(('cli:', 'connector:')) or _own(store, p, f'{tier}_model', cfg): return ''
    from . import climodels, llm
    if p.startswith('cli:'):
        cli = _cli(store, p, cfg)
        if not climodels.effort_args(cli, 'x') or (tier == 'light' and llm.LIGHT_DEFAULT.get(cli)): return ''
    else:
        c = store.get_connector(int(p[10:])) if p[10:].isdigit() else None
        if (c or {}).get('Type') not in llm.EFFORT_TAKERS: return ''
    m, e = climodels.split_pick(model or _own(store, p, 'model', cfg))
    want = LIFT[tier]
    if e in EFFORTS and (EFFORTS.index(e) <= EFFORTS.index(want) if tier == 'light' else EFFORTS.index(e) >= EFFORTS.index(want)): return ''
    return f'{m}@{want}'


def spell(model: str) -> str:
    "'opus@high' -> 'opus, high effort'; '@high' -> 'its own model, high effort' - a pick as the reason line and Settings say it."
    m, _, e = str(model or '').partition('@')
    return f"{m or 'its own model'}, {e} effort" if e else m


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
    # NO DRAFTING BRAIN (the owner, 2026-11-11: "drafting which the agent does now no more drafting ai"): the task's agent writes every
    # reply; the one-shot 'draft' left - a reply or message the owner presses for - is a one-message job like the rest of these
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
        return concierge.pick(store), want_model or concierge.model_of(store), gear or 'light', _backups(store)
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
    {'id': 'quick-jobs', 'when': {'job': ['triage', 'rank', 'memory', 'summary']}, 'use': {'tier': 'light'}},
    {'id': 'hard-work', 'when': {'job': ['draft', 'general', 'coding'], 'difficulty': ['hard']}, 'use': {'tier': 'strong'}},
    # ...and general work triage judged QUICK runs on the brain's quick gear - a lookup or a short answer does not need the big model
    # (the owner, 2026-11-05: "haiku or sonnet instead of opus for regular agent stuff based off triage complexity"). In Auto only
    {'id': 'quick-work', 'when': {'job': ['general', 'quick_work'], 'difficulty': ['quick']}, 'use': {'tier': 'light'}},
    # ...and the Advisor, which decides every light since 2026-11-02 (the owner: no hard-coded rules) - on the standard model
    {'id': 'work', 'when': {'job': ['draft', 'general', 'coding', 'quick_work', 'advisor']}, 'use': {'tier': 'standard'}},
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


# ── an AI per level (the owner, 2026-11-06: Auto choosing between their AIs by triage's difficulty - "not by default but you can
# adjust in settings"). Off until set: each level is the card's AI. Set, quick, normal or hard work runs on the AI named for it,
# when that AI can take the call - otherwise on the card, and the reason says why. Only the agents' work: triage, drafting and the
# Assistant each have a card of their own that already IS the owner's choice of AI for that job, and coding takes only a CLI.
LEVEL_KEY = 'ai_route_brain_by_level'
LEVEL_OF = {'light': 'quick', 'standard': 'normal', 'strong': 'hard'}
LEVEL_JOBS = ('general', 'quick_work', 'coding')


def by_level(store) -> dict:
    "{level: {pick, model}} for each level the owner set an AI for - blank (the default) is none."
    import json
    try: d = json.loads(str(store.get_setting(LEVEL_KEY) or '').strip() or '{}')
    except ValueError: d = {}
    return {l: {'pick': str(v.get('pick') or '').strip(), 'model': str(v.get('model') or '').strip()}
            for l, v in (d if isinstance(d, dict) else {}).items()
            if l in LEVEL_OF.values() and isinstance(v, dict) and str(v.get('pick') or '').strip()}


def save_by_level(store, d: dict, actor: str = 'owner') -> dict:
    "The owner's choice, checked: a level is quick, normal or hard, its AI a `cli:` or `connector:` pick; a blank pick is the card's."
    import json
    clean = {}
    for l, v in (d or {}).items():
        if l not in LEVEL_OF.values(): raise ValueError('a level is quick, normal or hard')
        p = str((v or {}).get('pick') or '').strip()
        if not p: continue
        if not p.startswith(('cli:', 'connector:')): raise ValueError("a level's AI is a connected CLI or AI card")
        clean[l] = {'pick': p, 'model': str(v.get('model') or '').strip()}
    store.set_setting(LEVEL_KEY, json.dumps(clean) if clean else '', actor)
    return by_level(store)


def _not_ready(store, p: str) -> str:
    "Why a pick could not start a call here - '' when it can: connected (a CLI installed, its last test not failed; a card on, with a key)."
    from . import agents, general
    if not any(o['pick'] == p for o in general.provider_options(store)): return 'is not connected'
    if p.startswith('cli:'):
        if not agents.runs_here(dict(agents.connection_brains(store)).get(p[4:])): return 'is not installed here'
        if agents.cli_tests(store).get(p[4:]) is False: return 'failed its last test'
    return ''


def _level(store, job: str, tier: str, want_pick, want_model, hands, only) -> tuple:
    """((pick, model), '') when the owner's AI for this tier's level takes this call; (None, '; why not') when one is set and cannot;
    (None, '') when none is set or the caller named another AI or model - an explicit pick always wins."""
    s = by_level(store).get(LEVEL_OF.get(tier)) if job in LEVEL_JOBS else None
    if not s or (want_pick is not None and want_pick != s['pick']): return None, ''
    to, m = s['pick'], s['model']
    # ...a general session started on the level's AI carries that AI's own model back each turn (general._selected): still the level's
    if want_model and want_model != m:
        from . import general
        if job != 'general' or want_model != general._selected(store, pick=to)[2]: return None, ''
    cold = cooldowns(store)
    no = (_not_ready(store, to) or ('has no shell, and this work needs a CLI' if not hands(to) else '')
          or (f"is limited until {cold[to].strftime('%H:%M')}" if to in cold else '') or ('has spent its budget' if spent(store, to) else '')
          or ('is not marked to read sensitive data' if only and not may_read_sensitive(store, to) else ''))
    if no: return None, f"; {LEVEL_OF[tier]} work is set to {_said(store, to)} in AI routing, but it {no}, so its card"
    return (to, m), ''


def choose(store, job: str, task=None, want_pick=None, want_model=None, gear=None, difficulty: str = None) -> Route:
    """The brain for one call of `job`. An explicit pick or model (`want_*`: the owner's picker, a saved session, a
    report's own brain, a workflow's model) always wins. `task` is the task dict or id the call is about, if any.
    `difficulty`: the judgement to answer for where no task carries one - Settings' "right now" rows (now).

    In Auto mode the rules pick the TIER - light, standard or strong - on the brain the cards (or an explicit pick) name. An
    explicit model is never overridden, the Assistant keeps its own model, and the guide chat keeps its quick gear."""
    if job not in JOBS: raise ValueError(f'unknown AI job {job!r} - one of {", ".join(JOBS)}')
    if task is not None and not isinstance(task, dict): task = store.get_task(int(task)) if str(task).isdigit() else None
    pick, model, g, chain = _fixed(store, job, task, want_pick, want_model, gear)
    j = judged(store, task) if task else {}
    from . import agents
    from .general import is_dock, chosen_model
    # ...and an agent's model is chosen only when the owner picked it: its brain's own default, carried by a caller, is no choice
    if want_model and job in LEVEL_JOBS and not chosen_model(store, pick, want_model): want_model = None
    chosen = want_pick is not None or bool(want_model)
    rule, tier = ('you chose it' if chosen else 'fixed'), 'fixed'
    # WORK THAT NEEDS HANDS stays on a CLI: coding, and a general task with a browser - an API backup got the browser brief and no
    # shell, and the task stayed on it with the page still in the pane (the owner's computer-use walk, 2026-10-25)
    from . import browserview
    browser = job == 'general' and browserview.wanted(task)
    hands = lambda p: (job != 'coding' and not browser) or str(p or '').startswith('cli:')
    f = facts(store, job, task) if pick and (task or mode(store) == 'auto') else {}
    if f and difficulty: f['difficulty'] = difficulty
    # FIRST, THE DATA (a hard constraint, failing closed - in either mode, once the owner turns its rule on): over an explicit pick too
    only, held = (_first(store, f, 'only') if task and f else None), ''
    if only:
        ok = [p for p in [pick, *chain] if p and may_read_sensitive(store, p)]
        if not ok: pick, chain, held, rule, tier = '', [], NO_SENSITIVE, only['id'], 'held'
        elif ok[0] != pick: held, model = f"; only an AI marked for sensitive data may read it (rule {only['id']})", ''
        if ok: pick, chain = ok[0], ok[1:]
    if not pick: why = f"{held or agents.NO_AI}, so {JOB_WORDS[job]} waits"
    else: why = f"{JOB_WORDS[job]} on {_said(store, pick)}{f', {model}' if model else ''}, {'as picked for it' if chosen else 'as its card says'}{held}"
    lvl = ''
    if pick and mode(store) == 'auto' and not (job == 'general' and is_dock(task)):
        r = _first(store, f, 'tier')
        lv, miss = _level(store, job, r['use']['tier'], want_pick, want_model, hands, only) if r else (None, '')
        hard = f" judged {f['difficulty']}" if r and 'difficulty' in r['when'] else ''
        if lv:
            # THE OWNER'S AI FOR THIS LEVEL: the tier is the rules', the AI the owner's - the card's AI next behind it, then its backups
            (to, m), tier, rule, said = lv, r['use']['tier'], r['id'], ''
            if to != pick: chain, pick = [pick, *chain], to
            lvl = LEVEL_OF[tier]
            if tier == 'strong' and not cap_left(store): tier, said = 'standard', f"; today's {cap(store)} strong calls are spent, so standard"
            elif tier == 'strong' and not m and not strong_of(store, pick) and not lift(store, pick, 'strong'): tier, said = 'standard', '; it has no strong model, so standard'
            g, model = GEAR_OF[tier], m or (lift(store, pick, tier) if tier in LIFT else '')
            why = f"{JOB_WORDS[job]}{hard}: {lvl} work -> {_said(store, pick)}{f', {spell(model)}' if model else ''} as set in AI routing (rule {rule}){said}{held}"
        elif r and not want_model:
            tier, rule, said = r['use']['tier'], r['id'], ''
            if tier == 'strong':
                # a strong model first - the brain's own, else the first backup's, as before - then the brain's one model at high
                # effort, else a backup's; for coding only ever a CLI's. A brain picked explicitly is kept: with neither it does the
                # work at standard
                ok = lambda p: bool(strong_of(store, p)) and hands(p)
                up = lambda p: bool(lift(store, p, 'strong', model if p == pick else '')) and hands(p)
                to = (pick if ok(pick) or (want_pick is not None and up(pick)) else '' if want_pick is not None else
                      next((c for c in chain if c and ok(c)), '') or (pick if up(pick) else next((c for c in chain if c and up(c)), '')))
                if not to: tier, said = 'standard', f"; {'it has no' if want_pick is not None else 'no brain here has a'} strong model, so standard"
                elif to != pick: said, chain, pick, model = f'; {_said(store, pick)} has no strong model', [pick, *chain], to, ''
            if tier == 'strong' and not cap_left(store): tier, said = 'standard', f"; today's {cap(store)} strong calls are spent, so standard"
            # the card's model IS the standard tier; strong runs the brain's strong gear and light its quick one - or, on a brain with
            # one model, that model at high or low effort
            g, model = GEAR_OF[tier], (model if tier == 'standard' else lift(store, pick, tier, model))
            why = f"{JOB_WORDS[job]}{hard} -> {tier} on {_said(store, pick)}{f', {spell(model)}' if model else ''} (rule {rule}){said}{held}"
        why += miss
    # a brain resting on its usage limit hands the call to the first backup that is not (Auto mode; the cards stand in Fixed)
    if pick and mode(store) == 'auto' and pick in (cold := cooldowns(store)):
        to = next((c for c in chain if c and c not in cold and hands(c)), '')
        if to:
            why += f"; {_said(store, pick)} is limited until {cold[pick].strftime('%H:%M')}, so {_said(store, to)}"
            # ...on its own model, as a failover always is: the resting brain's model id means nothing to another provider
            chain, pick, model = [pick, *chain], to, (lift(store, to, tier) if tier in LIFT else '')
            if tier == 'strong' and not strong_of(store, pick) and not model: tier, g = 'standard', GEAR_OF['standard']
    up = ''
    if pick and mode(store) == 'auto' and tier != 'strong' and job in ESCALATES and _first(store, f, 'escalate'): up = 'strong'
    if browser and str(pick).startswith('cli:'): chain = [c for c in chain if hands(c)]      # its failover too: no brain without a shell
    return Route(job, tier, pick, model, g, [c for c in chain if c and c != pick], rule, why[0].upper() + why[1:],
                 (j or {}).get('difficulty', ''), (j or {}).get('data_class', ''), up, lvl)


def level_pick(store, job: str, task) -> tuple | None:
    "(pick, model) of the owner's AI for this task's level when it would run `job` now (choose), else None - what a new session opens on."
    r = choose(store, job, task)
    return (r.pick, r.model) if r.level else None


def for_session(store, task, brain: str = None) -> tuple:
    """(brain, model) a coding pane opens on. Fixed mode, or no rule asking for more: (brain, None) - exactly today's choice. In
    Auto, hard work opens on a CLI's strong gear, and the route is logged; a coding pane never lands on an API connector."""
    if mode(store) != 'auto': return brain, None
    r = choose(store, 'coding', task, want_pick=f'cli:{brain}' if brain else None)
    log(store, r, (task or {}).get('TaskId') if isinstance(task, dict) else task)
    # ...and on the CLI the owner set for this level in AI routing (by_level): its model, else its strong gear on hard work
    if r.level and r.pick.startswith('cli:'): return r.pick[4:], r.model or (strong_of(store, r.pick) if r.gear == 'strong' else '') or None
    if r.gear != 'strong' or not r.pick.startswith('cli:'): return brain, None
    return r.pick[4:], strong_of(store, r.pick) or r.model or None


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
    rid2 = log(store, up, task_id, escalated_from=rid); outcome(store, rid, 'escalated')
    from . import aiusage
    return aiusage.metered(store, rid2, brain)


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


SPENT_KEY = 'ai_route_spent'      # {pick: the line to say} for an AI card resting on a spent budget (llm.BudgetSpent)


def _spent_map(store) -> dict:
    import json
    try: d = json.loads(str(store.get_setting(SPENT_KEY) or '').strip() or '{}')
    except ValueError: d = {}
    return d if isinstance(d, dict) else {}


def spend(store, pick: str, line: str, until: datetime) -> None:
    "Rest `pick` on its spent budget until `until`, and keep the line it is said in."
    import json
    if not pick: return
    cool(store, pick, until)
    try: store.set_setting(SPENT_KEY, json.dumps({**_spent_map(store), pick: str(line)[:300]}), 'router')
    except Exception as e: logger.debug(f'brainroute: could not note {pick} spent - {e}')


def spent(store, pick: str) -> str:
    "The spent-budget line while `pick` still rests on it, else '' - a rest that ran out is asked again."
    line = _spent_map(store).get(pick) if pick else None
    return str(line) if line and pick in cooldowns(store) else ''


def unspend(store, pick: str) -> None:
    "It answered: whatever rest it was on is over."
    import json
    d = _spent_map(store)
    if pick not in d: return
    d.pop(pick)
    try: store.set_setting(SPENT_KEY, json.dumps(d), 'router')
    except Exception as e: logger.debug(f'brainroute: could not clear {pick} spent - {e}')


def cap(store):
    "The owner's limit on strong calls a day, or None (blank, the default: no cap)."
    v = str(store.get_setting(CAP_KEY) or '').strip()
    return int(v) if v.isdigit() else None


# A DAY'S CEILING FOR WHAT NOBODY ASKED FOR (the owner, 2026-11-10: "client claims he barely used it. are we leaking tokens?"): a leak - a
# start on every arrival, a wake that wakes again, a pass on a clock - ran a whole day unseen and spent what a month should. Past this many
# calls in a day, agents do not start or wake by themselves and the clocks' passes wait for tomorrow; the bell says why while it holds
# (problems.collect). What the owner asks for still runs. Generous by default: an ordinary busy day is a few hundred calls; 0 is no ceiling
AUTO_CAP_KEY, AUTO_CAP = 'auto_ai_daily_calls', 1500


def calls_today(store, now: datetime = None) -> int:
    r = store._one('SELECT SUM(COALESCE(Calls, 1)) n FROM brainroute WHERE At>=?', ((now or datetime.now()).strftime('%Y-%m-%d'),)) or {}
    return int(r.get('n') or 0)


def auto_held(store, now: datetime = None) -> str:
    "Why what starts by itself waits today - '' while today's AI calls are under the owner's ceiling (`auto_ai_daily_calls`)."
    v = str(store.get_setting(AUTO_CAP_KEY) or '').strip()
    n = int(v) if v.isdigit() else AUTO_CAP
    if not n or (done := calls_today(store, now)) < n: return ''
    return (f"today's AI calls reached {done:,} (the daily limit for work nobody asked for is {n:,}), so agents do not start or wake by "
            "themselves until tomorrow - what you ask for still runs, and the limit is in Settings")


def strong_today(store, now: datetime = None) -> int:
    return store.count_brain_routes(since=(now or datetime.now()).strftime('%Y-%m-%d'), tier='strong')


def cap_left(store) -> bool:
    "Whether a strong call is still allowed today. Blank cap (the default) is no cap."
    n = cap(store)
    return n is None or strong_today(store) < n


# ── what Settings shows: the mode line, the rules as sentences, the cap line, the recent routes ───────────────────────────────
PLURAL = {'triage': 'triage', 'draft': 'redrafts', 'summary': 'summaries', 'advisor': 'the Advisor', 'memory': 'memory', 'rank': 'ranking',
          'assistant': 'the Assistant', 'general': 'general work', 'coding': 'coding', 'quick_work': 'quick general work', 'judge': 'judgements', 'report': 'reports'}
USE_WORDS = {'light': 'the quick model', 'standard': "the card's own model", 'strong': 'the strong model'}


def _and(xs) -> str:
    xs = [str(x) for x in xs if x]
    return '' if not xs else xs[0] if len(xs) == 1 else f"{', '.join(xs[:-1])} and {xs[-1]}"


def sentence(r: dict) -> str:
    """A rule as the owner reads it - "Hard drafts, general work and coding -> the strong model" - built from its values, so the
    sentence can never say something the rule does not do."""
    w, u = r.get('when') or {}, r.get('use') or {}
    ds = [{'standard': 'normal'}.get(d, d) for d in w.get('difficulty') or []]
    # a job word that already names the difficulty ("quick general work") loses it under that difficulty, and a repeat goes: never
    # "Quick general work and quick general work"
    js = [PLURAL.get(j, j) for j in w.get('job') or []]
    js = [next((x[len(d) + 1:] for d in ds if x.startswith(d + ' ')), x) for x in js]
    jobs = _and(dict.fromkeys(js)) or 'every job'
    who = ' '.join(x for x in (_and(ds), jobs) if x)
    if w.get('data_class'): who += f" carrying {_and(w['data_class'])} data"
    if w.get('origin'): who += f" written by {_and('a stranger' if o == 'stranger' else 'you' if o == 'owner' else 'people you trust' for o in w['origin'])}"
    if w.get('person'): who += f" with {_and(w['person'])}"
    if u.get('escalate'): s = f'Unreadable or unsure answers from {who} -> ask the strong model once'
    elif u.get('only'): s = f'{who} -> only an AI whose card says it may read sensitive data'
    else: s = f"{who} -> {USE_WORDS.get(u.get('tier'), u.get('tier'))}"
    return s[0].upper() + s[1:]


def _card_model(store, pick: str) -> str:
    "What an AI card runs when nothing asks for more: its model box, its deployment, else the provider's default."
    from . import llm
    cid = pick[10:] if pick.startswith('connector:') else ''
    c = store.get_connector(int(cid)) if cid.isdigit() else None
    t = (c or {}).get('Type') or ''
    return (_own(store, pick, 'model') or _own(store, pick, 'deployment') or llm.PROVIDER_DEFAULT.get(t)
            or (llm.OPENAI_COMPATIBLE.get(t) or ('', ''))[1] or 'its default model')


def _base(store, p: str, cfg) -> str:
    """The model brain `p` runs when nothing asks for more, BY NAME where the app knows it (the owner, 2026-11-11: "settings are not
    clear" over "same model" and "its own model"): the model on its connection or card, else the one its CLI is set to in its own
    config (climodels), else the provider's default - 'its default model' only when nothing here names one."""
    if not p.startswith('cli:'): return _card_model(store, p)
    from . import climodels
    return (spell(_own(store, p, 'model', cfg)) or str((climodels.catalog(_cli(store, p, cfg)).get('current') or {}).get('model') or '')
            or 'its default model')


def _words(store, p: str, cfg) -> dict:
    "{quick, normal, hard} - the model each level runs on brain `p`, named: 'haiku', 'gpt-5.4, low effort'."
    from .llm import LIGHT_DEFAULT
    base = _base(store, p, cfg)
    name = base.split(', ')[0]
    at = lambda tier: f'{name}, {LIFT[tier]} effort' if lift(store, p, tier, cfg=cfg) else base
    dflt = LIGHT_DEFAULT.get(_cli(store, p, cfg), '') if p.startswith('cli:') else ''
    quick = spell(_own(store, p, 'light_model', cfg)) or (f'{name}, {dflt[7:]} effort' if dflt.startswith('effort:') else dflt) or at('light')
    return {'quick': quick, 'normal': base, 'hard': spell(strong_of(store, p, cfg)) or at('strong')}


def levels(store, cfg=None) -> list:
    """What quick, normal and hard work runs on, per brain doing a job here - [{pick, brain, quick, normal, hard}], each a model by
    name, in the words Settings shows. Read off the same gears `choose` and llm.make_cli_llm run. A level the owner gave an AI of
    its own (by_level) says that AI for the agents' work on it: all of it on a brain that only runs agents."""
    from . import config
    cfg = config.load() if cfg is None else cfg
    by = {j: _fixed(store, j)[0] for j in ('triage', 'general', 'coding')}
    picks = list(dict.fromkeys(p for p in by.values() if p and p != 'demo'))
    reads, sets = {by['triage']}, by_level(store)
    out = []
    for p in picks:
        w = _words(store, p, cfg)
        for l, v in sets.items():
            if not p.startswith('cli:') and by['general'] != p: continue      # an API card runs no coding, so only its general work moves
            to = f"{_said(store, v['pick'])}, {spell(v['model']) or _words(store, v['pick'], cfg)[l]}"
            w[l] = to if p not in reads else f'{w[l]}; agents: {to}'
        out.append({'pick': p, 'brain': _said(store, p), **w})
    return out


def brains(store, cfg=None) -> list:
    """The AIs a level may be given - the same list the cards and the general agent's picker offer (general.brain_options) - each
    with `runs`, the model it runs a level on while that level's model box is blank."""
    from . import config, general
    cfg = config.load() if cfg is None else cfg
    return [{'pick': o['pick'], 'label': o.get('label') or _said(store, o['pick']), 'cli': o['pick'].startswith('cli:'),
             'models': list(o.get('models') or ([o['model']] if o.get('model') else [])), 'runs': _words(store, o['pick'], cfg)}
            for o in general.brain_options(store)]


ASKED_AS = {'light': 'quick', 'standard': 'standard', 'strong': 'hard'}      # a tier, as the difficulty triage would have judged
GEAR_LEVEL = {'light': 'quick', 'main': 'normal', 'strong': 'hard'}


def runs(store, job: str, cfg=None, difficulty: str = None) -> dict:
    """WHAT ONE CALL OF `job` RUNS ON THIS MINUTE, in the page's words: {pick, brain, model, why, route}. It IS `choose` - the one
    answer a card's RUNS line, the "right now" rows and a task's own reason line (why_for_task) all say, so they cannot disagree."""
    from . import config
    cfg = config.load() if cfg is None else cfg
    r = choose(store, job, difficulty=difficulty)
    m = spell(r.model) if r.model and not r.model.startswith('@') else ''
    # no model named for the call: an AI card runs its own - at the router's effort where it asked for one ('@low') - and a CLI its gear's
    if not m and r.pick and r.pick != 'demo':
        card = r.pick.startswith('connector:') and (r.model or (r.gear == 'light' and not _own(store, r.pick, 'light_model')))
        m = (f"{_card_model(store, r.pick)}{spell(r.model)[len('its own model'):]}" if card
             else _words(store, r.pick, cfg)[GEAR_LEVEL.get(r.gear, 'normal')])
    return {'pick': r.pick, 'brain': _said(store, r.pick), 'model': m, 'why': r.why, 'route': r}


def now(store, cfg=None) -> list:
    """WHAT EACH LEVEL RUNS ON THIS MINUTE (the owner, 2026-11-11: "it should show light goes to this model etc etc. never change
    from what's in settings"): [{level, pick, brain, model, why}] for quick, normal and hard agent work - `runs`, asked for a
    general task of that difficulty now. `why` is said only where the work is not on the general card's AI at the level asked: an
    AI set for the level, a brain resting until HH:MM, no strong model, the day's strong calls spent, a rule switched off - or
    nothing to run on at all."""
    card, out, sets = _fixed(store, 'general')[0], [], by_level(store) if mode(store) == 'auto' else {}
    for tier in TIERS:
        x = runs(store, 'general', cfg, ASKED_AS[tier]); r = x.pop('route')
        # ...moved off the card's AI or off the level asked - or an AI set for this level that could not take it
        moved = not r.pick or r.pick != card or (r.tier in LEVEL_OF and r.tier != tier) or (LEVEL_OF[tier] in sets and not r.level)
        out.append({**x, 'level': LEVEL_OF[tier], 'why': r.why if moved else resting(store, r.pick)})
    return out


def resting(store, pick: str) -> str:
    """'Claude Code is limited until 14:05' while `pick` rests on its usage limit, else ''. What a Settings line says beside an AI the
    work is still on though it rests - nothing else was there to take it - so "right now it runs on X" is never said of a resting X
    without its time."""
    t = cooldowns(store).get(pick) if pick else None
    return f"{_said(store, pick)} is limited until {t.strftime('%H:%M')}" if t else ''


def default_level(store, cfg=None) -> dict:
    """What a level left on Default runs: {general: {pick, brain, quick, normal, hard}, coding: {...}} - the General agent and Coding
    agent cards' AIs by name with the model each level gets, so a level's picker never says "the card's AI" (the owner, 2026-11-11:
    "what is the cards ai on top?")."""
    from . import config, kinds
    cfg = config.load() if cfg is None else cfg
    one = lambda p: {'pick': p, 'brain': _said(store, p), **(_words(store, p, cfg) if p and p != 'demo' else {})}
    return {j: one(_fixed(store, j)[0]) for j in kinds.AGENT}


def panel(store) -> dict:
    "Everything the router's part of Settings draws, in one read."
    n = cap(store)
    def safe(f, empty, what):
        try: return f(store)
        except Exception as e: logger.debug(f'brainroute: could not read {what} - {e}'); return empty
    return {'mode': mode(store), 'rules': [{**r, 'sentence': sentence(r)} for r in rules(store)], 'cap': '' if n is None else n,
            'used_today': strong_today(store), 'jobs': list(JOBS), 'tiers': list(TIERS), 'difficulties': ['quick', 'standard', 'hard'],
            'warning': coverage_warning(store), 'levels': safe(levels, [], 'what each level runs on'),
            'now': safe(now, [], 'what each level runs on right now'), 'by_level': by_level(store),
            'brains': safe(brains, [], 'the AIs a level may run on'), 'default': safe(default_level, {}, 'what a level left on Default runs')}


def set_panel(store, mode_: str = None, rs: list = None, cap_: str = None, actor: str = 'owner', by_level_: dict = None) -> dict:
    if mode_ is not None:
        if mode_ not in ('fixed', 'auto'): raise ValueError('the mode is fixed or auto')
        store.set_setting('ai_route_mode', mode_, actor)
    if rs is not None: save_rules(store, rs, actor)
    if by_level_ is not None: save_by_level(store, by_level_, actor)
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


def strong_offered(task: dict, judged_: dict, ended: str, story: dict | None) -> bool:
    """Whether "Run again on the strong model" can stand on this task's ▾ (TaskPage: an open task whose agent failed, or whose reader was
    unsure) - the task page, the Assistant's row and the open's own cost all read this one rule (2026-10-26)."""
    return str((task or {}).get('Status') or '') not in ('done', 'dropped') and (
        (judged_ or {}).get('sure') is False or ended == 'failed' or (story or {}).get('kind') == 'failed')


def strong_for(store, job: str, task, first: str = None) -> tuple:
    """(pick, model) for "Run again on the strong model": `first` (the brain that ran it) or the job's own brain when it has a strong
    model, else the first backup with one - a coding pane only ever a CLI's - else a one-model CLI at high effort. ('', '') when none."""
    r = choose(store, job, task, want_pick=first or None)
    ok = lambda p: bool(strong_of(store, p) or lift(store, p, 'strong')) and (job != 'coding' or p.startswith('cli:'))
    picks = [p for p in [r.pick, *r.chain] if p]
    to = next((p for p in picks if strong_of(store, p) and ok(p)), '') or next((p for p in picks if ok(p)), '')
    return (to, strong_of(store, to) or lift(store, to, 'strong')) if to else ('', '')

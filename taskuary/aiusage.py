"""What each AI call used: the model that answered, its tokens and its time, on that call's brainroute row (the owner, 2026-11-06:
"count of tokens per agent ... time it took ... which model it used so we can build dashboard ... the token usage and per model").

The route row is written before the call (brainroute.log); what the call USED is only known after it. `Metered` wraps the brain
build_llm hands out, and every call it makes runs inside a meter (a context variable, like llm.watching): the provider's own count
is noted into it wherever an answer comes back - Anthropic's `usage`, the OpenAI-style `usage` of chat completions and the Responses
API (OpenAI, Azure, OpenRouter, the OpenAI-compatible cards, the ChatGPT plan), a Claude CLI's `result` event and a Codex CLI's
`turn.completed`, an ACP turn's PromptResponse (else its CLI's own log - acp_turn). A brain whose answer carries no count (Gemini's
and the other CLIs' one-shots) leaves the tokens blank - never a guess. An agent session in a pane is counted from its CLI's own log when it is saved (sessionrecord.save -> session).

Tokens follow sessionrecord's convention: `in` is every input token, cached ones included; `cached` is how many of them were.
"""
import contextvars, functools, time
from contextlib import contextmanager
from datetime import datetime, timedelta
from loguru import logger

_METER = contextvars.ContextVar('tq_ai_meter', default=None)
# WHO ASKED, AND ABOUT WHICH MESSAGE (2026-11-11). A row said what its brain was BUILT for (Job), and one brain serves many askers: the
# poll's triage brain judges every mail of the poll and titles a hand-made task, a report's brain triages its own run - so "triage"
# on the usage page was neither all of triage nor only triage, and no triage row could be matched to its mail. The asker pins a note
# to its own piece of work (a context variable, like the meter); the one road that writes a route row reads it (brainroute.log), and
# a brain asked under a different note writes a row of its own (brainroute.Lazy). A call nobody named is recorded blank, never guessed.
_ASKED = contextvars.ContextVar('tq_ai_asked', default=None)
# the fixed names, one per asker - a new one is added here, so the breakdown's lines are a closed list
CALLERS = ('triage.classify', 'triage.report', 'triage.idea', 'triage.title', 'triage.proof', 'triage.eval', 'triage.reread', 'triage.repomap',
           'advisor.judge', 'advisor.idea', 'advisor.think', 'advisor.propose', 'advisor.check', 'advisor.run',
           'reports.judge', 'reports.summary', 'reports.agent','sent.judge', 'draft.reply', 'summary.report', 'summary.pause', 'memory.learn', 'memory.reflect', 'rank.rerank')


class Asked:
    "One asker's note: its fixed name, the message it asks about (None until one is saved), and the route rows written under it."
    def __init__(self, caller: str, message_id=None): self.caller, self.message_id, self.rids = caller, message_id, []


@contextmanager
def asking(caller: str, message_id=None):
    "Every AI call made inside this, on this thread of work, is `caller`'s - and about `message_id` when it has one. The inner one wins."
    a = Asked(caller, int(message_id) if str(message_id or '').isdigit() else None)
    tok = _ASKED.set(a)
    try: yield a
    finally: _ASKED.reset(tok)


def named(caller: str):
    "A function whose AI calls are `caller`'s (asking, as a decorator)."
    def deco(f):
        @functools.wraps(f)
        def g(*a, **kw):
            with asking(caller): return f(*a, **kw)
        return g
    return deco


def asked(): return _ASKED.get()


def for_message(store, rids, mid) -> None:
    "The message a judged mail was SAVED as, onto the rows (an Asked's `rids`) of the calls that judged it: a new mail has no row until its verdict is in."
    for rid in (rids or ()) if mid else ():
        try: store.set_brain_route(rid, MessageId=int(mid))
        except Exception as e: logger.debug(f'aiusage: route {rid} not given its message - {e}')
TIER_WORDS = {'light': 'quick', 'standard': 'normal', 'strong': 'hard', 'fixed': 'as set', 'held': 'held'}
RUN_JOBS = ('general', 'coding', 'quick_work')       # an agent's work: one row is a run, not one message's answer


def note(model: str = '', i=None, cached=None, o=None) -> None:
    "What one answer used, into the call's meter - nothing when no meter is open (a call made outside build_llm)."
    m = _METER.get()
    if m is None: return
    if isinstance(model, str) and model: m['model'] = model
    for k, v in (('in', i), ('cached', cached), ('out', o)):
        if v is not None: m[k] = m.get(k, 0) + int(v)


def _n(o, k):
    v = o.get(k) if isinstance(o, dict) else getattr(o, k, None)
    return int(v) if isinstance(v, (int, float)) else 0


def anthropic(r) -> None:
    "An Anthropic Messages answer (the SDK's object, or the same as a dict): its input_tokens leave the cache out, so they are added in."
    u = r.get('usage') if isinstance(r, dict) else getattr(r, 'usage', None)
    if not u: return
    hit = _n(u, 'cache_read_input_tokens')
    note(r.get('model') if isinstance(r, dict) else getattr(r, 'model', ''),
         _n(u, 'input_tokens') + _n(u, 'cache_creation_input_tokens') + hit, hit, _n(u, 'output_tokens'))


def openai(j: dict) -> None:
    "An OpenAI-style answer: chat completions (prompt/completion_tokens) or the Responses API (input/output_tokens)."
    u = (j or {}).get('usage') if isinstance(j, dict) else None
    if not isinstance(u, dict): return
    chat = 'prompt_tokens' in u
    d = u.get('prompt_tokens_details' if chat else 'input_tokens_details') or {}
    # ...a gateway in front of Claude or Gemini may say its cache read the Anthropic way beside it (LiteLLM's cache_read_input_tokens)
    note(j.get('model') or '', _n(u, 'prompt_tokens' if chat else 'input_tokens'), _n(d, 'cached_tokens') or _n(u, 'cache_read_input_tokens'),
         _n(u, 'completion_tokens' if chat else 'output_tokens'))


def claude_result(j: dict) -> None:
    """A Claude CLI's closing `result` event: the turn's usage, and the model that did the most of it (modelUsage also names the
    small model Claude Code asks on the side)."""
    if not isinstance(j, dict): return
    mu = j.get('modelUsage') if isinstance(j.get('modelUsage'), dict) else {}
    model = max(mu, key=lambda k: _n(mu[k], 'outputTokens'), default='')
    if isinstance(j.get('usage'), dict): anthropic({'usage': j['usage'], 'model': model})
    elif model: note(model)


def codex_turn(u: dict) -> None:
    "A Codex CLI's `turn.completed` usage: its input_tokens already count the cached ones."
    if isinstance(u, dict): note('', _n(u, 'input_tokens'), _n(u, 'cached_input_tokens'), _n(u, 'output_tokens'))


# ── the ACP road ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# Both adapters we ship (claude-agent-acp 0.101.0, codex-acp 2.5.0) answer session/prompt with the TURN's own count - `usage`
# {inputTokens, cachedReadTokens, cachedWriteTokens, outputTokens}, its inputTokens leaving the cache out as Anthropic's do - and name
# the model in _meta.quota.model_usage. Their usage_update notifications are the context window's fill, not a count: not read here.
# A turn whose answer carries none (codex-acp when Codex reported nothing, a native ACP CLI) is read from the CLI's own log by the ACP
# session id - the CLI's own conversation id - counting only lines from the turn's start (sessionrecord.cli_usage).
def acp(r) -> dict:
    "{'model', 'in', 'cached', 'out'} from one ACP PromptResponse - only the keys it carries."
    if not isinstance(r, dict): return {}
    mu = ((r.get('_meta') or {}).get('quota') or {}).get('model_usage') if isinstance(r.get('_meta'), dict) else None
    ms = [x for x in mu if isinstance(x, dict) and x.get('model')] if isinstance(mu, list) else []
    out = {'model': max(ms, key=lambda x: _n(x.get('token_count') or {}, 'outputTokens'))['model']} if ms else {}
    u = r.get('usage')
    if not isinstance(u, dict) or not any(_n(u, k) for k in ('inputTokens', 'cachedReadTokens', 'cachedWriteTokens', 'outputTokens')): return out
    hit = _n(u, 'cachedReadTokens')
    return {**out, 'in': _n(u, 'inputTokens') + _n(u, 'cachedWriteTokens') + hit, 'cached': hit, 'out': _n(u, 'outputTokens')}


def acp_turn(cli: str, r, sid: str, since: str) -> dict:
    "What one ACP turn used: the adapter's own count, else the CLI's log for session `sid` from `since` (local 'YYYY-MM-DD HH:MM:SS')."
    got = acp(r)
    if 'in' in got or not (sid and since): return got
    from .sessionrecord import cli_usage
    use = cli_usage(cli, sid, since)
    return {**got, **{k: use[k] for k in ('in', 'cached', 'out') if k in use}}


def note_turn(use: dict) -> None: note(use.get('model') or '', use.get('in'), use.get('cached'), use.get('out'))


def record(store, rid, ms: int, use: dict) -> None:
    if not rid: return
    try: store.add_brain_usage(rid, ms, use)
    except Exception as e: logger.debug(f'aiusage: could not keep what route {rid} used - {e}')


class Metered:
    """A brain whose every call writes its time, tokens and the model that answered on its route row. It answers exactly as the brain
    it wraps, and proxies attributes (a failover sets session_id and last_pick DURING a call)."""
    def __init__(self, store, rid, brain):
        for k, v in (('_store', store), ('_rid', rid), ('_brain', brain)): object.__setattr__(self, k, v)
    def __call__(self, *a, **kw): return self._metered(object.__getattribute__(self, '_brain'), a, kw)
    def _metered(self, f, a, kw):
        from .brainroute import rid_of
        rid = rid_of(object.__getattribute__(self, '_rid'))      # the route row is written here, on the first call (brainroute.Lazy)
        m, t0, out = {}, time.monotonic(), None
        tok = _METER.set(m)
        try: out = f(*a, **kw); return out
        finally:
            _METER.reset(tok)
            ms = int((time.monotonic() - t0) * 1000)
            record(object.__getattribute__(self, '_store'), rid, ms, m)
            job = getattr(getattr(object.__getattribute__(self, '_rid'), 'r', None), 'job', '') or 'a call'
            logger.debug(f"ai {job} (route {rid}): in {m.get('in', f'~{est(*a)} (est.)')}, cached {m.get('cached', '?')}, "
                         f"out {m.get('out', f'~{est(out)} (est.)')}, {ms} ms")
    def __bool__(self): return bool(object.__getattribute__(self, '_brain'))
    def __getattr__(self, k):
        v = getattr(object.__getattribute__(self, '_brain'), k)
        # EVERY STEP OF AN AGENT'S LOOP IS A CALL (apiagent.turn's brain.chat): only the one-shot call was metered, so a turn of thirty
        # steps on an AI card read as one row with no tokens - the calls that cost the most were the ones nobody counted (2026-11-10)
        if k != 'chat' or not callable(v): return v
        def chat(*a, **kw): return self._metered(v, a, kw)
        return chat
    def __setattr__(self, k, v): setattr(object.__getattribute__(self, '_brain'), k, v)


def metered(store, rid, brain): return Metered(store, rid, brain) if brain and rid else brain


def est(*parts) -> int:
    "Tokens a call's words come to, ESTIMATED as characters / 4 - for the log where a provider gave no count, never stored as one."
    import json
    return sum(len(p if isinstance(p, str) else json.dumps(p, default=str)) for p in parts if p is not None) // 4


def today(store, day: str = None) -> dict:
    """{job: {'calls', 'in', 'cached', 'out'}} for one day (today by default), every call counted - what the Settings page's AI section
    reads to answer "what did the AI cost today, and for what" (the owner, 2026-11-10: "they spent 25 dollars in one day?")."""
    day = day or datetime.now().strftime('%Y-%m-%d')
    out = {}
    for r in store.brain_routes_since(f'{day} 00:00:00'):
        if str(r.get('At') or '')[:10] != day: continue
        g = out.setdefault(r.get('Job') or 'triage', {'calls': 0, 'in': 0, 'cached': 0, 'out': 0})
        g['calls'] += int(r.get('Calls') or 0)
        for k, c in (('in', 'TokensIn'), ('cached', 'Cached'), ('out', 'TokensOut')): g[k] += int(r.get(c) or 0)
    return out


def by_caller(store, day: str = None) -> dict:
    """{job: {caller: {'calls', 'in', 'cached', 'out'}}} for one day - `today`'s totals split by who asked. A row written before the
    column, or by a call nobody named, is under ''."""
    day = day or datetime.now().strftime('%Y-%m-%d')
    out = {}
    for r in store.brain_routes_since(f'{day} 00:00:00'):
        if str(r.get('At') or '')[:10] != day: continue
        g = out.setdefault(r.get('Job') or 'triage', {}).setdefault(r.get('Caller') or '', {'calls': 0, 'in': 0, 'cached': 0, 'out': 0})
        g['calls'] += int(r.get('Calls') or 0)
        for k, c in (('in', 'TokensIn'), ('cached', 'Cached'), ('out', 'TokensOut')): g[k] += int(r.get(c) or 0)
    return out


# ── an agent session in a pane: counted when it is saved ─────────────────────────────────────────────────────────────────────────
def session(store, tid, sid: str, cli: str, started: str, rec: dict, model: str = '') -> int | None:
    """A coding pane's run onto the route row the router logged when it opened (brainroute.for_session), else a row of its own: the
    real model, the CLI's token count and how long it worked. Saved on exit AND on close, so it is written once per session (Sid)."""
    use, took = rec.get('usage') or {}, rec.get('took')
    fields = {'Ran': model or None, 'TokensIn': use.get('in'), 'Cached': use.get('cached'), 'TokensOut': use.get('out'),
              'Ms': int(took * 1000) if isinstance(took, (int, float)) else None, 'Calls': 1, 'Sid': str(sid)}
    try:
        if (row := _session_row(store, tid, sid, started)): store.set_brain_route(row['Id'], **{k: v for k, v in fields.items() if v is not None}); return row['Id']
        return _own_row(store, tid, sid, cli, started, fields)
    except Exception as e:
        logger.debug(f'aiusage: session {sid} not counted - {e}'); return None


def _session_row(store, tid, sid: str, started: str):
    "The route row of coding session `sid`: by its Sid, else the one the router logged as the pane opened (brainroute.for_session)."
    row = store.brain_route_of_session(sid)
    if not row and tid and started:
        # the router logs the pane's route just before the pane starts: a couple of minutes' slack finds it, never an older run's
        since = (datetime.fromisoformat(str(started)[:19]) - timedelta(minutes=2)).isoformat(sep=' ', timespec='seconds')
        row = next((r for r in store.brain_routes_since(since, int(tid), limit=20) if r.get('Job') == 'coding' and not r.get('Sid')), None)
    return row


def _own_row(store, tid, sid, cli, started, fields: dict) -> int:
    return store.add_brain_route({'At': str(started or datetime.now().isoformat(sep=' ', timespec='seconds'))[:19].replace('T', ' '),
                                  'Job': 'coding', 'TaskId': int(tid) if str(tid or '').isdigit() else None, 'Pick': f'cli:{cli}' if cli else '',
                                  'Tier': 'fixed', 'Rule': 'session', 'Why': f'A session in a pane on {cli or "a CLI"}', 'Outcome': 'ok', **fields})


def coding_turn(store, tid, sid: str, cli: str, started: str, ms: int, use: dict) -> int | None:
    """One turn of a coding session over ACP (acpcoding) ADDED onto its session's route row - a session is many turns, and nothing
    files its tokens at the end the way a pane's CLI log is read on exit (session)."""
    try:
        row = _session_row(store, tid, sid, started)
        rid = row['Id'] if row else _own_row(store, tid, sid, cli, started, {'Sid': str(sid)})
        if row and not row.get('Sid'): store.set_brain_route(rid, Sid=str(sid))
        store.add_brain_usage(rid, ms, use); return rid
    except Exception as e:
        logger.debug(f'aiusage: an ACP turn of {sid} not counted - {e}'); return None


# ── what was used, as rows: the task's fold and the dashboard's dataset ───────────────────────────────────────────────────────────
def _brain(store, pick, said):
    if pick not in said:
        from .brainroute import _said
        try: said[pick] = _said(store, pick) if pick and pick != 'demo' else ('the demo' if pick == 'demo' else '')
        except Exception: said[pick] = str(pick or '')
    return said[pick]


def row(store, r: dict, said: dict = None) -> dict:
    "One route row in plain words: when, the job, the brain and model, quick/normal/hard, tokens and seconds (None where uncounted)."
    from .brainroute import JOB_WORDS
    brain, ms = _brain(store, r.get('Pick') or '', {} if said is None else said), r.get('Ms')
    i, o = r.get('TokensIn'), r.get('TokensOut')
    return {'id': r['Id'], 'at': r.get('At') or '', 'day': str(r.get('At') or '')[:10], 'task_id': r.get('TaskId'),
            'job': r.get('Job') or '', 'brain': brain,
            'what': 'a question the agent asked a stronger model' if r.get('Rule') == 'agent asked' else JOB_WORDS.get(r.get('Job'), r.get('Job') or ''),
            'model': r.get('Ran') or r.get('Model') or brain, 'tier': TIER_WORDS.get(r.get('Tier'), r.get('Tier') or ''),
            'tokens_in': i, 'cached': r.get('Cached'), 'tokens_out': o, 'tokens': None if i is None and o is None else (i or 0) + (o or 0),
            'seconds': None if ms is None else round(ms / 1000, 1), 'calls': r.get('Calls') or (1 if ms is not None else 0),
            'run': bool(r.get('Sid')) or (r.get('Job') in RUN_JOBS and r.get('Rule') != 'agent asked'), 'outcome': r.get('Outcome') or 'ok'}


def for_task(store, tid: int, limit: int = 200) -> dict:
    "Every AI call and agent run on this task, newest first, with their totals - what the task's 'AI used' fold reads."
    said = {}
    rows = [row(store, r, said) for r in store.brain_routes(int(tid), limit=limit)]
    tot = lambda k: sum(x[k] or 0 for x in rows) if any(x[k] is not None for x in rows) else None
    return {'rows': rows, 'total': {'calls': len(rows), 'tokens': tot('tokens'), 'tokens_in': tot('tokens_in'), 'tokens_out': tot('tokens_out'),
                                    'cached': tot('cached'), 'seconds': tot('seconds')}}


def dataset(store, days) -> list:
    """The `ai_usage` dataset (dashboards.DATASETS): an agent run is a row of its own; the one-message calls are rolled up per day, job,
    brain, model and tier with how many there were - so 90 days of triage fit the dashboard's rows."""
    since = (datetime.now() - timedelta(days=max(1, int(days or 90)))).strftime('%Y-%m-%d %H:%M:%S')
    out, roll, said = [], {}, {}
    for r in store.brain_routes_since(since):
        if r.get('Pick') == 'demo' and r.get('TokensIn') is None: continue          # the demo's scripted answers used nothing
        x = row(store, r, said)
        base = {k: x[k] for k in ('day', 'job', 'what', 'brain', 'model', 'tier')}
        nums = {'tokens_in': x['tokens_in'], 'tokens_out': x['tokens_out'], 'cached': x['cached'], 'tokens': x['tokens'], 'seconds': x['seconds']}
        if x['run']:
            out.append({**base, 'task_id': x['task_id'], 'kind': 'agent run', 'calls': max(1, x['calls']), **nums,
                        'minutes': None if x['seconds'] is None else round(x['seconds'] / 60, 1)}); continue
        k = tuple(base.values())
        g = roll.setdefault(k, {**base, 'task_id': None, 'kind': 'one call', 'calls': 0, **{n: None for n in nums}, 'minutes': None})
        g['calls'] += max(1, x['calls'])
        for n, v in nums.items():
            if v is not None: g[n] = round((g[n] or 0) + v, 1) if n == 'seconds' else (g[n] or 0) + v
    return sorted(out + list(roll.values()), key=lambda x: x['day'], reverse=True)

"""Say what you want; get a report configuration back.

The Reports tab is a pipeline builder, and a builder asks you to know things first: which of
twenty-odd executor types your data lives behind, what that executor's config keys are called,
and the query language of whatever is on the other end. That is a fair amount to know before
you are allowed to ask for "the vendor list from Intacct, weekly, flag anything new".

So this turns the sentence into the config. Three things keep it from being a wish machine:

1. It may only choose a type whose CONNECTION IS ACTUALLY SET UP. The catalog is built from
   this install's live connectors, so a model cannot answer "connect to Salesforce" - it can
   only say that nothing here reaches Salesforce.
2. The config keys come from the executors' own docstrings, which document them for humans
   already. One source, so a report type cannot drift from what the composer believes it takes.
3. It is allowed to say it does not know. Questions come back as questions; a guessed WHERE
   clause on a finance report is worse than a five-second ask.

There are two front doors. `compose` writes a WHOLE report from a sentence. `compose_sources`
writes only the source cards - what you need when you are already in the builder with one card
open and cannot remember whether a bill's amount is AMOUNT or TOTALENTERED, or what the
Assistant should be pointed at in the first place. Same fences, same peeking, no title and no
schedule: it fills in the part of the form that requires knowing the system.

Nothing is saved. The composer drafts, /api/reports/preview runs it for real, and the owner
looks at actual rows before anything is scheduled - which is the honest version of "the AI set
it up for you".
"""
import json, re

from loguru import logger

MAX_PEEKS = 3         # schema look-ups per compose: a table, its columns, and one lookup (a location id, say)

# what a config of this type MUST carry to run at all. A composed report with only a title is a
# form the owner has to finish - which is the thing the composer exists to spare them.
REQUIRED = {'agent': ('prompt|skill',), 'intacct': ('object',), 'intacct_fields': ('object',), 'mssql': ('query',), 'database': ('query',), 'sqlite': ('db', 'query'),
            'rest': ('url',), 'local_file': ('path',), 'winrm': ('script',), 's3_object': ('bucket',), 'cloudwatch_logs': ('log_group',),
            'metric': ('name',)}       # metric_check with no name is valid: it checks every one

# A source card is not a report: whatever the model says about scheduling, titling or summarising
# belongs to the report around the card, and is dropped rather than written into a card that
# ignores it. A blocklist, not an allowlist - a new executor key must not need editing here.
REPORT_KEYS = ('title', 'ai_prompt', 'ai_brain', 'every_minutes', 'daily_at', 'cron', 'on_startup',
               'deliver', 'alert', 'charts', 'sources', 'watch_sources', 'watch_source_ids')
MAX_SOURCES = 6      # the Assistant reads every one of them on every check; a wall of them is a slow check
NOT_A_SOURCE = ('assistant',)   # a check reading its own output is a loop, not a data source

# Sage Intacct, as the model needs it spelled out: the executor docstring says what the keys are,
# not how the system thinks. Fields are UPPERCASE ids; readByQuery filters, never SQL; nothing
# aggregates on the server, so "how many per person" is fields + an ai_prompt that counts.
INTACCT_PLAYBOOK = """SAGE INTACCT (type "intacct")
- Objects: APBILL (vendor bills), APBILLITEM (bill lines), APPYMT, ARINVOICE, VENDOR, CUSTOMER, GLENTRY / GLDETAIL (journal detail), GLACCOUNT, LOCATION (sites/entities), DEPARTMENT, GLBUDGETITEM, PROJECT.
- Field ids are UPPERCASE: RECORDNO, RECORDID, VENDORID, VENDORNAME, WHENCREATED (entered), WHENPOSTED (posted), WHENDUE, TOTALENTERED, TOTALDUE, STATE, CREATEDBY / MODIFIEDBY (the user - "who posted it"), AUUSERID, LOCATIONID, DEPARTMENTID. Custom fields exist per company: peek {"type": "intacct_fields", "object": "APBILL"} to see the real list.
- "filters" is a list of [FIELD, op, value]; ops: = != > < >= <= like notlike in notin isnull isnotnull. Dates are MM/DD/YYYY. Sites are LOCATIONs: when the owner names one, peek {"type": "intacct", "object": "LOCATION", "fields": ["LOCATIONID", "NAME"], "filters": [["NAME", "like", "<their word>%"]]} and filter the report on LOCATIONID.
- readByQuery does not group or count. "How many X per Y" = the rows with the Y field included, plus an ai_prompt that counts per Y and lists the total. "Posted yesterday/today" = a WHENPOSTED filter; a daily report should say so in explain.
- Always set "object", and set "fields" to the handful the question needs - APBILL has dozens.
- A named business number is NOT a GL query you write here. The chart of accounts is configured for this organisation, so one you write yourself is plausible and wrong. If the number has been certified it has a definition proved against figures the owner already knew: use {"type": "metric", "name": "<name>", "scope": "<what names one row>", "period": "YYYY-MM"}. If it has not, say so rather than approximating it with a GLENTRY filter - an unproved figure in a scheduled report is the one nobody re-checks."""
SCHEMA_ROWS = 300


def _keys_doc(fn) -> str:
    """The executor's own docstring, trimmed to the part that describes its config. Written for
    a person reading the code; it turns out to be exactly what a model needs too."""
    doc = ' '.join((fn.__doc__ or '').split())
    return doc[:400]


def catalog(store) -> list:
    """Every report type this install can actually run, with what it takes and whether its
    connection is ready. A type whose card is missing is still LISTED, marked not-connected, so
    the composer can answer "you would need to connect Datadog first" instead of inventing a
    config that will fail on its first scheduled run."""
    from .reports import REGISTRY, PLANNED, CONNECTION_OF, card_of
    conns = {}
    for c in store.list_connectors():
        if c['Type'] not in conns or (c.get('Active') and not conns[c['Type']].get('Active')):
            conns[c['Type']] = c
    out = []
    for t, fn in sorted(REGISTRY.items()):
        if t in PLANNED: continue
        card = card_of(t)
        c = conns.get(card)
        needs = t in CONNECTION_OF
        ready = (not needs) or bool(c and c.get('Active'))
        out.append({'type': t, 'takes': _keys_doc(fn), 'connection': card if needs else None,
                    'ready': ready,
                    'why_not': '' if ready else (f'the {card} connection is switched off'
                                                 if c else f'nothing is connected for {card}')})
    return out


# The same four rules govern both composers, so they are written once. A model that guesses a
# column name produces a report that is wrong forever and never says so.
JUDGEMENT = (
    'JUDGEMENT\n'
    '- A query you had to guess at is the thing to ask about. A wrong filter on a finance report '
    'is silently wrong forever; a question costs five seconds.\n'
    '- Never invent a table, column, object or field name. Peek, or ask.\n'
    '- The owner describes what they WANT, not what exists. "Our headcount file" is a path you do '
    'not have - ask for it.\n'
    '- confidence "low" is a real answer. Say so in explain and the owner will check it.\n')

SYSTEM = (
    'You turn a plain-English request into ONE Taskuary scheduled-report configuration.\n\n'
    'Answer with JSON only, in exactly one of three shapes:\n'
    '  {"questions": ["...", "..."]}  - you cannot build it yet and need the owner to decide '
    'something. Ask only what you genuinely cannot infer, at most three, each a short concrete '
    'question a person can answer in a few words.\n'
    '  {"peek": {"type": "<a schema type from the catalog>", ...its keys}} - you need to SEE the '
    'schema before you can write the query: which tables exist, what the columns are called. '
    'Use it rather than guessing a column name; the result comes back and you answer again.\n'
    '  {"config": {...}, "explain": "<one or two sentences: what this will do and any '
    'assumption you made>", "confidence": "high|medium|low"} - the finished report.\n\n'
    'CONFIG RULES\n'
    '- "type" MUST be one of the catalog types, and one whose ready flag is true. If what the '
    'owner asked for needs something not connected, do not substitute a different system: return '
    'questions saying what would have to be connected.\n'
    '- Use exactly the config keys the catalog lists under "takes" for that type. Do not invent keys.\n'
    '- "title" is required: short, plain, what a person would call this report on a list.\n'
    '- Schedule: "every_minutes" (a number) OR "daily_at" ("HH:MM", 24h) OR "cron". Pick the one '
    'the owner asked for; when they did not say, use daily_at 08:00 and mention it in explain.\n'
    '- "ai_prompt" is the instruction for the pass that turns rows into prose. Include it whenever '
    'the owner asked for a summary, a flag, a comparison or an interpretation - and write it as a '
    'concrete instruction ("Summarize spend by site; flag any vendor above 10k or new this '
    'month"), never "summarize the data".\n'
    '- "max_rows" only when the ask implies a size.\n'
    '- "agent" is the type for "run my <skill> every week", "have the AI research X on a schedule", or any '
    'report whose source is the AI itself doing work: set "skill" to the slash command (without the slash is fine) '
    'and/or "prompt" to the instruction; the answer is the report, so ai_prompt is usually unnecessary.\n\n' +
    JUDGEMENT +
    '- A config is not finished until it carries what its type needs to RUN: an Intacct report has an object, a SQL '
    'report has a query, a REST report has a url. A title alone is the owner\'s form handed back to them - peek or ask instead.')


# The same fence, aimed one step lower down. The report composer answers "what report do I
# want"; this one answers "what does this card have to say to reach that system", which is the
# question the Assistant's Pipeline step actually asks - and the one nobody can answer from
# memory, because it is the object names and field ids of somebody else's finance system.
SOURCE_SYSTEM = """You configure the DATA SOURCES a Taskuary check reads. Not a whole report: the owner is standing in the builder with the source cards in front of them and cannot remember what the systems here are called or what fields they carry. You write that part.

Answer with JSON only, in exactly one of three shapes:
  {"questions": ["...", "..."]} - you cannot write it yet and need the owner to decide something. At most three, each answerable in a few words.
  {"peek": {"type": "<a schema type from the catalog>", ...its keys}} - you need to SEE the schema first: which objects exist, what the fields are really called. The result comes back and you answer again.
  {"sources": [{"type": "...", "label": "...", ...its keys}], "ai_prompt": "...", "explain": "<one or two sentences: what these will read and any assumption you made>", "confidence": "high|medium|low"} - the finished cards.

SOURCE RULES
- "type" MUST be one of the catalog types, and one whose ready flag is true. If the ask needs a system nobody here has connected, do not substitute a different one: return questions saying what would have to be connected.
- Use exactly the config keys the catalog lists under "takes" for that type. Do not invent keys.
- Every source carries what its type needs to RUN: an Intacct source has an object, a SQL source has a query, a REST source has a url. A card with only a type is the owner's own empty form handed back to them - peek or ask instead.
- "label" is a short human name for the card ("AP bills due", "cash balances"). It is how the check refers to that data, so give every card one whenever there is more than one.
- "max_rows" only when the ask implies a size. Nothing else: no title, no schedule, no delivery - those belong to the report around these cards and are ignored here.
- Respect max_sources, and write ONE source per system-and-question: two questions of the same database are two cards with different queries, never one query trying to answer both.
- "ai_prompt" is one instruction over ALL these sources together - what the check should SURFACE. Concrete ("Flag any vendor over 10k or new this month; give the number and the site"), never "summarize the data". Write it when the ask says what matters; leave it out when the owner asked only for the data.
- Never choose "assistant" as a source. That is the check itself; reading its own output is a loop.
- the_card_you_are_filling_in names the type already chosen on the card. Keep it unless the ask plainly needs another system, and then say so in explain.

""" + JUDGEMENT


def _json(text):
    t = re.sub(r'^```(json)?|```$', '', (text or '').strip(), flags=re.M).strip()
    try: return json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        if not m: return None
        try: return json.loads(m.group(0))
        except ValueError: return None


def _peek(store, spec):
    """Run one schema look-up and hand back rows the model can read. Errors come back as text
    rather than raising: 'that object does not exist' is information the model should use, and
    the composer failing outright teaches it nothing."""
    from .reports import REGISTRY, resolve_cfg
    t = (spec or {}).get('type')
    if t not in REGISTRY: return f'(no such lookup type: {t})'
    try:
        head, body = REGISTRY[t](resolve_cfg(store, {**spec, 'max_rows': SCHEMA_ROWS}))
        return f'{head}\n{body[:6000]}'
    except Exception as e:
        return f'(the lookup failed: {str(e)[:300]})'

def _rounds(store, llm, system, user, rounds, finish):
    """The loop both composers share: the model may go and READ a real schema before it writes
    anything, a question comes back as a question, and `finish` reads its final answer."""
    looked = []
    for _ in range(max(1, rounds + 1)):
        out = _json(llm(system, json.dumps(user, default=str), max_tokens=2000))
        if not out: return {'error': 'the model did not answer with a configuration - try rewording the ask'}
        if out.get('questions'):
            return {'questions': [str(q)[:300] for q in out['questions']][:3], 'looked_at': looked}
        if out.get('peek') and len(looked) <= rounds:
            spec = out['peek']
            looked.append(spec)
            logger.info(f"compose: looking at {spec.get('type')} before answering")
            user.setdefault('what_you_looked_at', []).append(
                {'you_asked_for': spec, 'result': _peek(store, spec)})
            continue
        return finish(out, looked)
    return {'error': 'the model kept asking to look at schemas without answering'}


def _playbook(cat) -> str:
    """A system's own briefing rides along only where that system is actually connected - there
    is no point teaching the model Intacct's field ids on an install that cannot reach Intacct."""
    return ('\n\n' + INTACCT_PLAYBOOK) if any(c['type'] == 'intacct' and c['ready'] for c in cat) else ''


def compose(store, ask: str, llm, answers: dict = None, rounds: int = MAX_PEEKS) -> dict:
    """{'questions': [...]} or {'config': {...}, 'explain': ..., 'confidence': ..., 'looked_at': [...]}.

    `answers` are the owner's replies to a previous round's questions, so asking is a
    conversation rather than a dead end."""
    if not llm: return {'error': 'no AI connector is configured - Connections → AI'}
    if not (ask or '').strip(): return {'error': 'say what you want the report to do'}
    cat = catalog(store)
    user = {'request': ask.strip(), 'catalog': cat,
            **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        cfg = out.get('config')
        if not isinstance(cfg, dict): return {'error': 'the model answered without a config'}
        ok, why = validate(store, cfg)
        if not ok: return {'error': why, 'config': cfg}
        return {'config': cfg, 'explain': str(out.get('explain') or '')[:600],
                'confidence': out.get('confidence') or 'medium', 'looked_at': looked}
    return _rounds(store, llm, SYSTEM + _playbook(cat), user, rounds, finish)


def compose_sources(store, ask: str, llm, one_type: str = None, answers: dict = None,
                    rounds: int = MAX_PEEKS) -> dict:
    """{'sources': [...], 'ai_prompt': ...} - the source CARDS for a check and nothing else: no
    title, no schedule, no delivery. This is the composer the Assistant needs, because "point it
    at the systems it should read" is the step that requires knowing the systems.

    `one_type` is the card the owner is standing on: exactly one source comes back, of that type
    unless the ask plainly needs another system - and then `explain` says which and why."""
    if not llm: return {'error': 'no AI connector is configured - Connections → AI'}
    if not (ask or '').strip(): return {'error': 'say what it should read'}
    cat = catalog(store)
    if one_type:
        # standing on a card whose connection is off: say so now rather than after a model call
        row = next((c for c in cat if c['type'] == one_type), None)
        if row and not row['ready']: return {'error': f"{one_type} cannot run: {row['why_not']}"}
    cap = 1 if one_type else MAX_SOURCES
    user = {'request': ask.strip(), 'catalog': cat, 'max_sources': cap,
            'the_card_you_are_filling_in': one_type or
            'nothing yet - the owner is pointing a check at whatever systems the ask needs',
            **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        srcs = out.get('sources') or out.get('source')
        if isinstance(srcs, dict): srcs = [srcs]          # one card asked for, one card answered
        if not isinstance(srcs, list) or not srcs: return {'error': 'the model answered without a data source'}
        srcs = [{k: v for k, v in s.items() if k not in REPORT_KEYS} for s in srcs if isinstance(s, dict)]
        srcs = [s for s in srcs if s.get('type') not in NOT_A_SOURCE][:cap]
        if not srcs: return {'error': 'the only source it chose was the check itself - say which system it should read'}
        for s in srcs:
            ok, why = validate_source(store, s)
            if not ok: return {'error': why, 'sources': srcs}
        return {'sources': srcs, 'ai_prompt': str(out.get('ai_prompt') or '')[:2000],
                'explain': str(out.get('explain') or '')[:600],
                'confidence': out.get('confidence') or 'medium', 'looked_at': looked}
    return _rounds(store, llm, SOURCE_SYSTEM + _playbook(cat), user, rounds, finish)


def validate_source(store, src: dict, noun: str = 'source'):
    """(ok, why) for ONE source: a real type, a CONNECTED one, and the keys its executor needs to
    run at all. The model is not trusted to have got this right - it is a language model reading a
    list, and the failure it would otherwise produce arrives days later as a scheduled report
    that has never once run."""
    from .reports import REGISTRY, PLANNED
    t = (src or {}).get('type')
    if t not in REGISTRY: return False, f'unknown report type: {t}'
    if t in PLANNED: return False, f'{t} is not built yet'
    row = next((c for c in catalog(store) if c['type'] == t), None)
    if row and not row['ready']: return False, f"{t} cannot run: {row['why_not']}"
    # 'a|b' means either will do (an agent source needs a skill OR a prompt)
    missing = [k for k in REQUIRED.get(t, ()) if not any(src.get(alt) for alt in k.split('|'))]
    if missing: return False, (f"the {t} {noun} is not finished: it has no {' / '.join(missing)} - "
                               'the composer should have looked the schema up or asked')
    return True, ''


def validate(store, cfg: dict):
    """(ok, why) for a whole report: a source that can run, plus the one thing only a report
    has - a name a person will recognise on a list."""
    if not str((cfg or {}).get('title') or '').strip(): return False, 'the report has no title'
    return validate_source(store, cfg, 'report')

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
            'rest': ('url',), 'local_file': ('path',), 'winrm': ('script',), 's3_object': ('bucket',), 'cloudwatch_logs': ('log_group',)}

# Sage Intacct, as the model needs it spelled out: the executor docstring says what the keys are,
# not how the system thinks. Fields are UPPERCASE ids; readByQuery filters, never SQL; nothing
# aggregates on the server, so "how many per person" is fields + an ai_prompt that counts.
INTACCT_PLAYBOOK = """SAGE INTACCT (type "intacct")
- Objects: APBILL (vendor bills), APBILLITEM (bill lines), APPYMT, ARINVOICE, VENDOR, CUSTOMER, GLENTRY / GLDETAIL (journal detail), GLACCOUNT, LOCATION (facilities/entities), DEPARTMENT, GLBUDGETITEM, PROJECT.
- Field ids are UPPERCASE: RECORDNO, RECORDID, VENDORID, VENDORNAME, WHENCREATED (entered), WHENPOSTED (posted), WHENDUE, TOTALENTERED, TOTALDUE, STATE, CREATEDBY / MODIFIEDBY (the user - "who posted it"), AUUSERID, LOCATIONID, DEPARTMENTID. Custom fields exist per company: peek {"type": "intacct_fields", "object": "APBILL"} to see the real list.
- "filters" is a list of [FIELD, op, value]; ops: = != > < >= <= like notlike in notin isnull isnotnull. Dates are MM/DD/YYYY. Facilities are LOCATIONs: when the owner names one ("Adelphi"), peek {"type": "intacct", "object": "LOCATION", "fields": ["LOCATIONID", "NAME"], "filters": [["NAME", "like", "Adelphi%"]]} and filter the report on LOCATIONID.
- readByQuery does not group or count. "How many X per Y" = the rows with the Y field included, plus an ai_prompt that counts per Y and lists the total. "Posted yesterday/today" = a WHENPOSTED filter; a daily report should say so in explain.
- Always set "object", and set "fields" to the handful the question needs - APBILL has dozens."""
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
    conns = {c['Type']: c for c in store.list_connectors()}
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
    'concrete instruction ("Summarize spend by facility; flag any vendor above 10k or new this '
    'month"), never "summarize the data".\n'
    '- "max_rows" only when the ask implies a size.\n'
    '- "agent" is the type for "run my <skill> every week", "have the AI research X on a schedule", or any '
    'report whose source is the AI itself doing work: set "skill" to the slash command (without the slash is fine) '
    'and/or "prompt" to the instruction; the answer is the report, so ai_prompt is usually unnecessary.\n\n'
    'JUDGEMENT\n'
    '- A query you had to guess at is the thing to ask about. A wrong filter on a finance report '
    'is silently wrong forever; a question costs five seconds.\n'
    '- Never invent a table, column, object or field name. Peek, or ask.\n'
    '- The owner describes what they WANT, not what exists. "Our census file" is a path you do '
    'not have - ask for it.\n'
    '- confidence "low" is a real answer. Say so in explain and the owner will check it.\n'
    '- A config is not finished until it carries what its type needs to RUN: an Intacct report has an object, a SQL '
    'report has a query, a REST report has a url. A title alone is the owner\'s form handed back to them - peek or ask instead.')


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


def compose(store, ask: str, llm, answers: dict = None, rounds: int = MAX_PEEKS) -> dict:
    """{'questions': [...]} or {'config': {...}, 'explain': ..., 'confidence': ..., 'looked_at': [...]}.

    `answers` are the owner's replies to a previous round's questions, so asking is a
    conversation rather than a dead end."""
    if not llm: return {'error': 'no AI connector is configured - Connectors → AI'}
    if not (ask or '').strip(): return {'error': 'say what you want the report to do'}

    cat = catalog(store)
    # the Intacct playbook rides along only where Intacct is actually connected
    system = SYSTEM + ('\n\n' + INTACCT_PLAYBOOK if any(c['type'] == 'intacct' and c['ready'] for c in cat) else '')
    user = {'request': ask.strip(), 'catalog': cat,
            **({'answers_to_your_questions': answers} if answers else {})}
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
        cfg = out.get('config')
        if not isinstance(cfg, dict): return {'error': 'the model answered without a config'}
        ok, why = validate(store, cfg)
        if not ok: return {'error': why, 'config': cfg}
        return {'config': cfg, 'explain': str(out.get('explain') or '')[:600],
                'confidence': out.get('confidence') or 'medium', 'looked_at': looked}
    return {'error': 'the model kept asking to look at schemas without answering'}


def validate(store, cfg: dict):
    """(ok, why). The model is not trusted to have picked a real type or a connected one - it is
    a language model reading a list, and the failure it would otherwise produce arrives days
    later as a scheduled report that has never once run."""
    from .reports import REGISTRY, PLANNED
    t = cfg.get('type')
    if t not in REGISTRY: return False, f'unknown report type: {t}'
    if t in PLANNED: return False, f'{t} is not built yet'
    if not str(cfg.get('title') or '').strip(): return False, 'the report has no title'
    row = next((c for c in catalog(store) if c['type'] == t), None)
    if row and not row['ready']: return False, f"{t} cannot run: {row['why_not']}"
    # 'a|b' means either will do (an agent report needs a skill OR a prompt)
    missing = [k for k in REQUIRED.get(t, ()) if not any(cfg.get(alt) for alt in k.split('|'))]
    if missing: return False, f"the {t} report is not finished: it has no {' / '.join(missing)} - the composer should have looked the schema up or asked"
    return True, ''

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
from . import words

MAX_PEEKS = 3         # schema look-ups per compose: a table, its columns, and one lookup (a location id, say)

# what a config of this type MUST carry to run at all. A composed report with only a title is a
# form the owner has to finish - which is the thing the composer exists to spare them.
REQUIRED = {'agent': ('prompt|skill',), 'intacct': ('object',), 'intacct_fields': ('object',), 'mssql': ('query',), 'database': ('query',), 'sqlite': ('db', 'query'),
            'rest': ('url',), 'local_file': ('path',), 'winrm': ('script',), 's3_object': ('bucket',), 'cloudwatch_logs': ('log_group',),
            'metric': ('name',), 'amazon_report': ('report_type',), 'amazon_invoice_pdf': ('invoice',),       # metric_check with no name is valid: it checks every one
            # files (files.py). smb_read takes no required path - the card's root IS a folder, and
            # "what is in the share" is a valid report; every write needs to be told where.
            'smb_write': ('path',), 'smb_move': ('path', 'to'),
            'sftp_get': ('path',), 'sftp_put': ('path',), 'sftp_move': ('path', 'to')}

# A source card is not a report: whatever the model says about scheduling, titling or summarising
# belongs to the report around the card, and is dropped rather than written into a card that
# ignores it. A blocklist, not an allowlist - a new executor key must not need editing here.
REPORT_KEYS = ('title', 'ai_prompt', 'ai_brain', 'every_minutes', 'daily_at', 'cron', 'on_startup',
               'deliver', 'alert', 'charts', 'sources', 'watch_sources', 'watch_source_ids')
MAX_SOURCES = 6      # the Assistant reads every one of them on every check; a wall of them is a slow check
NOT_A_SOURCE = ('assistant', 'zoho_monthly_invoices', 'dashboard')  # checks may read data views, never a stateful workflow or a dashboard

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
    from .trackers import TYPES as TRACKER_WRITES
    conns = {}
    for c in store.list_connectors():
        if c['Type'] not in conns or (c.get('Active') and not conns[c['Type']].get('Active')):
            conns[c['Type']] = c
    out = []
    for t, fn in sorted(REGISTRY.items()):
        if t in PLANNED or t == 'dashboard': continue      # a dashboard is built by its own composer, never a report's source
        if t in TRACKER_WRITES: continue      # a tracker write is a proposal, never a source
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
    '- confidence "low" is a real answer. Say so in explain and the owner will check it.\n'
    '- Ask only what you can neither find out nor sensibly default. What the request already says, a repository it '
    'names, a time these rules default and an obvious search term (the product\'s own name) are not questions - '
    'use them and say so in explain; the owner sees the report before it runs.\n'
    '- A clear request is built, not questioned: never ask the owner to confirm what they already said, or to choose '
    'between readings when one is plainly meant. They check the draft before anything is saved.\n')

# A WATCH is not a report you read: it speaks only when something is wrong, and then triage judges it (the owner, 2026-10-16:
# "if it's always show up then it's just a report fyi, not a optional if this happens, then triage then fix type of thing").
WATCH_RULE = ('- "watch": ONLY when the owner wants to hear from it IF something happens ("tell me if the system shows an error", '
              '"let me know when the job fails"), the condition in their own words. Its run then shows under Reports only when '
              'that holds, and triage judges it then: triage decides whether it needs a task, and makes none for what an open '
              'task already covers. A report the owner simply wants ("send me X every morning") has NO "watch": it shows every '
              'run and triage never sees it. Never write "route" - the server writes it from "watch".\n')

# AN ANSWER HAS A SHAPE (the owner, 2026-10-29: "which repository holds the skill?" was asked as a free-text box beside a list the
# app already has). The model says what kind of answer each question takes, and the builder draws that control; no words are read.
ASK_KINDS = ('text', 'repo', 'schedule', 'choice')
ASK_SHAPE = ('- Each entry of "questions" is {"q": "<the question>", "kind": "text|repo|schedule|choice", "options": ["..."]}: "repo" when the '
             'answer is one of the owner\'s code repositories, "schedule" when it is when or how often it runs, "choice" when it is one '
             'of a few answers you can name (2-6 "options"), else "text". "options" only with "choice".\n')

REPOS_RULE = ('- "repositories" are the owner\'s own code repositories: full name and what each is for. When the request names one '
              'by its short name ("taskuary", "ledger"), it means that one - write its full owner/name, never ask which.\n')

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
    'report has a query, a REST report has a url. A title alone is the owner\'s form handed back to them - peek or ask instead.\n'
    + WATCH_RULE + REPOS_RULE + ASK_SHAPE)


# A WORKFLOW IS STEPS, and code runs every one it can (flow.py; the owner, 2026-10-18: "maybe we should do the same for
# workflows and it will end up the ai will just make judgements"): the model writes them ONCE, here, with real queries.
FLOW_RULES = (
    'FLOW RULES - an agent workflow\'s work is "flow": an ordered list of steps that code runs on every run, so only the judgement '
    'costs a model:\n'
    '  {"id": "s1", "kind": "source", "label": "<short name>", "type": "<a catalog type>", ...exactly the keys the catalog lists for it}\n'
    '  {"id": "s2", "kind": "ai", "label": "...", "prompt": "<the judgement, reading {{s1}}>", "output": "text|yes_no|fields", "fields": ["..."]}\n'
    '  {"id": "s3", "kind": "task", "label": "...", "title": "...", "summary": "...", "assignee": "<an agent name, optional>"}\n'
    '  {"id": "s4", "kind": "draft", "label": "...", "channel": "email", "to": "<address>", "about": "...", "subject": "..."}\n'
    '  {"id": "s5", "kind": "agent", "label": "...", "prompt": "<what the agent does with what the steps found>"}\n'
    '- Every read or write a catalog type can do is a "source" step with a REAL query, object or path: peek at the schema, never guess. '
    'Use only types whose ready flag is true.\n'
    '- "ai" only where a judgement, a summary or a draft is needed. When a later step depends on it, its output is yes_no or fields.\n'
    '- "task" opens a task, "draft" leaves an email for the owner to approve - that is how results land; neither needs a connection.\n'
    '- "agent" ONLY when the work needs an agent\'s hands - a web page, open-ended investigation - and it is always the last step. A job '
    'that is nothing but that is ONE agent step (or just "prompt").\n'
    '- A step reads earlier output with {{s1}} (its rows/text), {{s1.head}}, {{s1.rows}} (a count), {{s2.answer}}, {{s2.why}}, '
    '{{s2.fields.<name>}}, {{inputs.<key>}}, {{run.date}}.\n'
    '- "only_if": {"step": "s2", "is": "yes|no|rows|empty"} skips a step unless an earlier one answered so - use it instead of asking the '
    'AI whether to continue.\n'
    '- "goal": one plain sentence of what the workflow is FOR - the outcome, the people and the places it reaches, not the steps. '
    'When a step breaks later (a page moved, a column was renamed) the fix is kept by itself only while this goal still holds.\n'
    '- "repair": "propose" when the owner wants every fix to wait for them, "off" when a failure should just stop; leave it out '
    'otherwise (fixes that keep the goal are applied by themselves).\n')

WORKFLOW_SYSTEM = (
    'You turn a plain-English request into ONE Taskuary workflow configuration. Workflows do work '
    'or keep state; reports only read and summarize. This builder supports exactly two workflow types:\n'
    '- "zoho_monthly_invoices": opens a monthly customer batch, copies each customer\'s last invoice '
    'into a Zoho draft, and leaves every send on the task for owner approval.\n'
    '- "agent": a configured AI agent with write access works a saved skill and/or prompt - in the folder "cwd" names when it has '
    'one. A job that only retrieves or summarizes data is a report, not a workflow.\n\n'
    'TASKUARY IS WHERE RESULTS LAND. Each run is itself a task in Taskuary - scheduled or run by hand, its agent works it there and '
    'nothing is filed as a report or read by triage - and it may open tasks for people, write notes '
    'and leave drafts - emails, messages, invoices - for the owner to approve, with no connection at all. Never ask which '
    'connection opens a task or where a result should go. A connection is only for a system the work happens IN (Intacct '
    'to read, a portal to drive). Opening tasks or drafting IS doing work: such a job is a workflow, never "really a report".\n\n'
    'Answer JSON only in one of four shapes:\n'
    '  {"questions": ["..."]} when the request is unclear - what the job is, what it should produce, for whom - or a choice you cannot '
    'sensibly default is missing (which Zoho customers, say); at most three short questions. A clear request is built: what you chose - who runs it, the schedule, what it asks first - goes '
    'in explain, never back to the owner as a question, and nothing they already said is asked again.\n'
    '  {"peek": {"type": "<a type from the catalog>", ...its keys}} - you need to SEE a real schema (which tables, what the columns '
    'are called) before you can write a step\'s query; the result comes back and you answer again.\n'
    '  {"config": {...}, "explain": "<what it will do>", "confidence": "high|medium|low"}.\n'
    '  {"report": {<a report config: type, title, the type\'s keys, ai_prompt, schedule>}, "explain": "<why this is a report>"} - '
    'when what the owner wants is only to READ data and be told about it (pull it, summarize it, flag what stands out) and nothing '
    'is written, moved, opened or sent. That is a report, not a workflow: every workflow run is a task, and a summary is not work '
    'to close. Judge it from what they ask for, not from any one word.\n\n'
    'RULES\n'
    '- Use only connector ids, customer ids, and agent names present in WORKFLOW OPTIONS. Never invent one.\n'
    '- A Zoho workflow needs type, title, connector_id, customers, and a schedule. Customers may be '
    'a list of exact customer ids; the server replaces them with its trusted customer records. If the '
    'owner did not identify which customers, ask. Nothing ever sends automatically.\n'
    '- An agent workflow must change data or state, and needs type, title, agent, and prompt and/or skill. Use an exact configured '
    'agent name: the profile whose job it is (an accounts-payable job is ap), else the general assistant - never ask which.\n'
    '- "uses" carries every connection the request names that is in WORKFLOW OPTIONS - name Intacct and its id goes in.\n'
    '- A skill is its slash-command name without requiring the leading slash. cwd is optional and must come from the owner, never be guessed.\n'
    '- "model" and "effort" are LEFT OUT: a run works on the general agents\' brain and model, which is what the owner wants by default. '
    'Set them only when the owner\'s words ask for a harder model or harder thinking on this job ("use the best model", "think hard", '
    '"this one is tricky, give it the strongest"): "effort" from the efforts WORKFLOW OPTIONS brain lists, and "model" only to an id '
    'from its models; say so in explain.\n'
    '- Schedule with every_minutes, daily_at (HH:MM), or standard five-field cron. daily_at is EVERY day: a weekly, '
    'weekday or monthly ask is cron ("every Monday at 8" is "0 8 * * 1"), and explain must say the same schedule the '
    'config carries. If the owner gives no schedule, use daily_at "08:00" for an agent or cron "0 9 1 * *" for monthly '
    'invoices and say so - unless a mail starts it (on_mail), which needs no clock.\n'
    '- An agent workflow also says, when the request does: "uses" - the ids of the connections it works in, only from '
    'WORKFLOW OPTIONS connections; "ask_first" - what it must ask the owner before doing; "done_when" - what finished '
    'looks like, including what a run with nothing to do says; "browser": true when the work is done on a web page; '
    '"on_mail": when the job starts as a certain mail ARRIVES, that mail described in plain words (triage starts the run when one '
    'like it comes in, and its steps read it as {{mail.from}}, {{mail.subject}}, {{mail.body}}).\n'
    '- Do not add report-only keys such as sources, ai_prompt, charts, triage, route, watch, delivery, or alerts: a run is a task, '
    'so there is no condition to wait for and nothing for triage to judge.\n' + ASK_SHAPE + '\n' + FLOW_RULES)

WORKFLOW_KEYS = {
    'zoho_monthly_invoices': {'type', 'title', 'connector_id', 'customers', 'customer_ids',
                              'every_minutes', 'daily_at', 'cron', 'on_startup'},
    'agent': {'type', 'title', 'agent', 'skill', 'prompt', 'cwd', 'model', 'effort', 'access', 'uses', 'ask_first', 'done_when', 'browser',
              'flow', 'repair', 'goal', 'on_mail', 'every_minutes', 'daily_at', 'cron', 'on_startup'},
}


def with_watch(cfg: dict, watch) -> dict:
    """The card a composed config is saved with, written HERE from the model's `watch` and never from a route it wrote: a watch
    shows under Reports when its condition holds and triage judges that same run; anything else is a report to read, and its
    triage line is never (reports.LINE_DEFAULT) - so a model that forgot the key made a report, not a monitor."""
    w = str(watch or '').strip()[:500]
    line = {'how': 'ai', 'when': w}
    return {**{k: v for k, v in cfg.items() if k not in ('route', 'watch', 'triage')},
            'route': {'timeline': line, 'triage': dict(line)} if w else {'triage': {'how': 'never'}}}


def workflow_catalog(store) -> dict:
    """Trusted choices an AI workflow builder may use; credentials never enter its prompt."""
    from . import zoho
    zoho_cards = []
    for row in store.list_connectors():
        if row.get('Type') != 'zoho_invoice': continue
        item = {'connector_id': row['ConnectorId'], 'name': row.get('Name') or 'Zoho Invoice',
                'ready': bool(row.get('Active') and row.get('HasSecret')), 'customers': []}
        if item['ready']:
            try: item['customers'] = zoho.customers(zoho.connection(store, row['ConnectorId']))
            except Exception as e: item['error'] = str(e)[:300]
        zoho_cards.append(item)
    return {'zoho_monthly_invoices': zoho_cards,
            'agent': [{'name': a.get('Name')} for a in store.list_agents() if a.get('Name')],
            # what a workflow may work IN: the connections that are switched on, by id and name - never their settings
            'connections': [{'id': c['ConnectorId'], 'name': c.get('Name') or c.get('Type'), 'type': c.get('Type')}
                            for c in store.list_connectors() if c.get('Active')],
            # the brain a run works on (workflows.brain) and what it can be asked for - a harder model, more effort
            'brain': _brain(store)}


def _brain(store) -> dict:
    from . import workflows
    try: b = workflows.brain_options(store)
    except Exception as e:
        logger.debug(f'compose: the workflow brain could not be read - {e}'); return {'said': '', 'models': [], 'efforts': []}
    return {'said': b['said'], 'efforts': b['efforts'], 'models': [{'id': m['id'], 'efforts': m['efforts']} for m in b['models']]}


# what the composers answer when they cannot: what to change in the ask, or the place that lifts the block (`fix`: {label, href},
# an app link the row turns into a button - outbound.Fixable). Developer words ("unsupported workflow type: (missing)") are not it.
AGAIN = "I couldn't turn that into {}. Say it another way - what should happen, in which system, and when."
NO_AI = {'error': 'This needs an AI to build it - none is connected yet.', 'fix': {'label': 'Connect an AI', 'href': words.href('ai')}}
ZOHO = {'error': 'Invoicing runs through a connected Zoho Invoice account.', 'fix': {'label': 'Connect Zoho Invoice', 'href': '#connector=zoho_invoice'}}

REPORT_VERDICT = ('That only reads data and tells you about it, so it is a report, not a routine - a routine does something '
                  '(moves data, opens work, drafts what goes out), and every run of one is a task.')


def report_verdict(store, cfg: dict, explain, looked) -> dict:
    """{'verdict': 'report', 'report': <a report draft>, 'explain'} - what the workflow door answers when the ask is a report."""
    cfg = with_watch({k: v for k, v in cfg.items() if k not in ('access', 'flow', 'repair', 'agent', 'uses', 'ask_first', 'done_when')}, cfg.get('watch'))
    ok, why = validate(store, cfg)
    return {'verdict': 'report', 'report': cfg, 'explain': f"{REPORT_VERDICT} {str(explain or '').strip()}".strip()[:700],
            'looked_at': looked, **({} if ok else {'report_error': why})}


def compose_workflow(store, ask: str, llm, answers: dict = None) -> dict:
    """Draft a stateful invoice or AI-agent workflow from a sentence. Nothing is saved."""
    if not llm: return dict(NO_AI)
    if not (ask or '').strip(): return {'error': 'Say what you want the routine to do.'}
    options = workflow_catalog(store)
    # the systems a step may read or write, as the report composer sees them - a step is a report source card (flow.py)
    user = {'request': ask.strip(), 'workflow_options': options, 'catalog': catalog(store),
            **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        # A REPORT, NOT A WORKFLOW (the owner, 2026-10-18): only reading and reporting is the report builder's job - said plainly,
        # with the report drafted from the same reads for one press to open. The model's judgement of the ask, or steps that only read.
        if isinstance(out.get('report'), dict):
            return report_verdict(store, out['report'], out.get('explain'), looked)
        raw = out.get('config')
        from . import flow as _flow
        if isinstance(raw, dict) and raw.get('type') == 'agent' and _flow.only_reads(raw.get('flow')):
            return report_verdict(store, _flow.as_report(raw), out.get('explain'), looked)
        # THE MODEL'S MISS IS NOT THE OWNER'S: they cannot fix a missing config, only ask again - so every miss below says what
        # to change in the ASK ("the model answered without a workflow config" was the whole message, 2026-10-17)
        if not isinstance(raw, dict) or raw.get('type') not in WORKFLOW_KEYS: return {'error': AGAIN.format('a routine')}
        typ = raw['type']
        cfg = {k: v for k, v in raw.items() if k in WORKFLOW_KEYS[typ]}
        if not str(cfg.get('title') or '').strip(): return {'error': AGAIN.format('a routine')}
        schedules = [k for k in ('every_minutes', 'daily_at', 'cron', 'on_startup') if cfg.get(k)]
        if not schedules and not str(cfg.get('on_mail') or '').strip():      # a job a mail starts needs no clock
            cfg['cron' if typ == 'zoho_monthly_invoices' else 'daily_at'] = '0 9 1 * *' if typ == 'zoho_monthly_invoices' else '08:00'
        if typ == 'agent':
            names = {x['name'] for x in options['agent']}
            if cfg.get('agent') not in names:
                return ({'error': f"It picked an agent you don't have - say which one to use: {', '.join(sorted(names))}."} if names else dict(NO_AI))
            if cfg.get('flow') is not None:
                from . import flow
                ok, why = flow.validate(store, cfg['flow'], strict=True)
                if not ok: return {'error': f"{AGAIN.format('a routine')} (Its steps did not hold: {why}.)"}
                lone = len(cfg['flow']) == 1 and cfg['flow'][0].get('kind') == 'agent'
                if lone and not cfg.get('prompt'): cfg['prompt'] = cfg['flow'][0].get('prompt') or ''
                if lone: cfg.pop('flow')          # one agent step IS the prompt-only workflow (flow.steps_of)
            elif not (str(cfg.get('skill') or '').strip() or str(cfg.get('prompt') or '').strip()):
                return {'error': AGAIN.format('a routine')}
            if str(cfg.get('repair') or '') not in ('propose', 'off'): cfg.pop('repair', None)      # auto is the default (flow.repair_mode)
            if not str(cfg.get('goal') or '').strip(): cfg.pop('goal', None)
            else: cfg['goal'] = str(cfg['goal']).strip()[:400]
            if cfg.get('skill'): cfg['skill'] = str(cfg['skill']).strip().lstrip('/')
            known = {x['id'] for x in options['connections']}
            uses = [int(x) for x in (cfg.get('uses') or []) if str(x).isdigit()]
            if any(x not in known for x in uses):
                return {'error': 'It needs a connection that is not switched on - connect it, or say which connected system to use.',
                        'fix': {'label': 'Open Connections', 'href': '#connector='}}
            if uses: cfg['uses'] = list(dict.fromkeys(uses))
            else: cfg.pop('uses', None)
            for k in ('ask_first', 'done_when'):
                if not str(cfg.get(k) or '').strip(): cfg.pop(k, None)
            if not cfg.get('browser'): cfg.pop('browser', None)
            # a model the brain does not offer, or an effort it cannot take, is the model's guess - the brain's own default stands
            brain = options.get('brain') or {}
            hit = next((m for m in brain.get('models') or [] if m['id'] == str(cfg.get('model') or '').strip()), None)
            if not hit: cfg.pop('model', None)
            if str(cfg.get('effort') or '').strip().lower() not in ((hit or {}).get('efforts') if hit else brain.get('efforts') or []): cfg.pop('effort', None)
            else: cfg['effort'] = str(cfg['effort']).strip().lower()
            # The workflow door is the owner's grant to write. `type: agent` alone remains a
            # read-only report, because the executor is not the product boundary.
            cfg['access'] = 'write'
            # EVERY RUN IS A TASK (workflows.run), a checkout or not: a watch would be a line no run reads, so triage is never
            cfg = with_watch(cfg, None)
        else:
            try: cid = int(cfg.get('connector_id'))
            except (TypeError, ValueError): return dict(ZOHO)
            card = next((x for x in options['zoho_monthly_invoices'] if x['connector_id'] == cid and x['ready']), None)
            if not card: return dict(ZOHO)
            trusted = {str(x.get('customer_id')): x for x in card.get('customers') or []}
            chosen = cfg.get('customer_ids') if isinstance(cfg.get('customer_ids'), list) else cfg.get('customers')
            ids = list(dict.fromkeys(str(x.get('customer_id') if isinstance(x, dict) else x) for x in (chosen or [])))
            if not ids: return {'error': 'Say which Zoho customers it should invoice.'}
            if any(x not in trusted for x in ids): return {'error': "It named a customer your Zoho account doesn't have - say the customer as Zoho lists them."}
            cfg['connector_id'], cfg['customers'] = cid, [trusted[x] for x in ids]
            cfg.pop('customer_ids', None)
        return {'config': cfg, 'explain': str(out.get('explain') or '')[:600],
                'confidence': out.get('confidence') or 'medium', 'looked_at': looked}

    return _rounds(store, llm, WORKFLOW_SYSTEM + _playbook(user['catalog']), user, MAX_PEEKS, finish)


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
""" + REPOS_RULE + ASK_SHAPE + '\n' + JUDGEMENT


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

def ask_of(q) -> dict:
    """One question as the builder draws it: {'q', 'kind', 'options'}. A bare string (the old shape) is a text answer; a kind the
    builder has no control for is one too, and a choice with fewer than two options is asked as text."""
    if not isinstance(q, dict): return {'q': str(q or '').strip()[:300], 'kind': 'text', 'options': []}
    kind = q.get('kind') if q.get('kind') in ASK_KINDS else 'text'
    opts = [str(o).strip()[:120] for o in (q.get('options') or []) if str(o).strip()][:8] if kind == 'choice' else []
    return {'q': str(q.get('q') or q.get('question') or '').strip()[:300], 'kind': 'text' if kind == 'choice' and len(opts) < 2 else kind,
            'options': opts if len(opts) >= 2 else []}

def _rounds(store, llm, system, user, rounds, finish):
    """The loop both composers share: the model may go and READ a real schema before it writes
    anything, a question comes back as a question, and `finish` reads its final answer."""
    looked = []
    for _ in range(max(1, rounds + 1)):
        out = _json(llm(system, json.dumps(user, default=str), max_tokens=2000))
        if not out: return {'error': AGAIN.format('a report')}
        if out.get('questions'):
            asks = [a for a in map(ask_of, out['questions'] if isinstance(out['questions'], list) else [out['questions']]) if a['q']][:3]
            if asks: return {'questions': [a['q'] for a in asks], 'asks': asks, 'looked_at': looked}
        if out.get('peek') and len(looked) <= rounds:
            spec = out['peek']
            looked.append(spec)
            logger.info(f"compose: looking at {spec.get('type')} before answering")
            user.setdefault('what_you_looked_at', []).append(
                {'you_asked_for': spec, 'result': _peek(store, spec)})
            continue
        return finish(out, looked)
    return {'error': AGAIN.format('a report')}


def _repositories(store) -> dict:
    """The owner's repositories as the coding agent knows them. A report "about taskuary" asked which repository
    that was, because the composer had never been told there are any (2026-09-24 chat audit)."""
    try:
        from . import terminal
        desc = terminal.repo_map(store)
        return {r: desc.get(r, '') for r in terminal.known_repos(store)}
    except Exception as e:
        logger.debug(f'compose: no repository list - {e}'); return {}


def _playbook(cat) -> str:
    """A system's own briefing rides along only where that system is actually connected - there
    is no point teaching the model Intacct's field ids on an install that cannot reach Intacct."""
    return ('\n\n' + INTACCT_PLAYBOOK) if any(c['type'] == 'intacct' and c['ready'] for c in cat) else ''


def compose(store, ask: str, llm, answers: dict = None, rounds: int = MAX_PEEKS,
            exclude_types=None) -> dict:
    """{'questions': [...]} or {'config': {...}, 'explain': ..., 'confidence': ..., 'looked_at': [...]}.

    `answers` are the owner's replies to a previous round's questions, so asking is a
    conversation rather than a dead end."""
    if not llm: return dict(NO_AI)
    if not (ask or '').strip(): return {'error': 'Say what you want the report to do.'}
    excluded = set(exclude_types or ())
    cat = [row for row in catalog(store) if row.get('type') not in excluded]
    user = {'request': ask.strip(), 'catalog': cat, **({'repositories': repos} if (repos := _repositories(store)) else {}),
            **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        cfg = out.get('config')
        if not isinstance(cfg, dict): return {'error': AGAIN.format('a report')}
        if cfg.get('type') in excluded:
            return {'error': 'That reads as a routine, not a report.', 'fix': {'label': 'Build it as a routine', 'href': '#report=workflows'}}
        cfg = with_watch(cfg, cfg.get('watch'))
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
    if not llm: return dict(NO_AI)
    if not (ask or '').strip(): return {'error': 'Say what it should read.'}
    cat = catalog(store)
    if one_type:
        # standing on a card whose connection is off: say so now rather than after a model call
        row = next((c for c in cat if c['type'] == one_type), None)
        if row and not row['ready']: return {'error': f"{one_type} cannot run: {row['why_not']}"}
    cap = 1 if one_type else MAX_SOURCES
    user = {'request': ask.strip(), 'catalog': cat, 'max_sources': cap,
            'the_card_you_are_filling_in': one_type or
            'nothing yet - the owner is pointing a check at whatever systems the ask needs',
            **({'repositories': repos} if (repos := _repositories(store)) else {}),
            **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        srcs = out.get('sources') or out.get('source')
        if isinstance(srcs, dict): srcs = [srcs]          # one card asked for, one card answered
        if not isinstance(srcs, list) or not srcs: return {'error': "I couldn't tell which system to read. Name it - the database, mailbox or app."}
        srcs = [{k: v for k, v in s.items() if k not in REPORT_KEYS} for s in srcs if isinstance(s, dict)]
        srcs = [s for s in srcs if s.get('type') not in NOT_A_SOURCE
                and not (s.get('type') == 'agent' and s.get('access') == 'write')][:cap]
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


# ── a dashboard: sources + preset components, written once and run with no AI ─────────────────────────────
DASHBOARD_SYSTEM = (
    'You design ONE Taskuary dashboard from a plain-English request: the data sources it reads (deterministic reads from the '
    'catalog - a query, a sheet, a file, Taskuary\'s own tables) and a grid of PRESET components bound to those sources\' '
    'columns. Nothing is summarised by an AI when it runs: every run re-reads the sources and the page draws the rows.\n\n'
    'Answer JSON only, in one of three shapes:\n'
    '  {"questions": ["..."]} - at most three, only what you can neither find out nor sensibly default.\n'
    '  {"peek": {"type": "<a catalog type>", ...its keys}} - run one read to SEE the real columns before binding to them.\n'
    '  {"config": {...}, "explain": "<one or two sentences>", "confidence": "high|medium|low"}.\n\n'
    'CONFIG\n'
    '{"type": "dashboard", "title": "<short>", "daily_at": "HH:MM" | "every_minutes": N | "cron": "...",\n'
    ' "sources": [{"key": "<short id>", "label": "<what a person calls it>", "type": "<a ready catalog type>", ...that type\'s keys,\n'
    '              "date": "<the column holding each row\'s date, when it has one>"}],\n'
    '  A source\'s "key" is its own name here. An s3_object source puts its object path in "object_key", never in "key".\n'
    ' "filters": {"range": 7|30|90|0, "segment": "<a column several sources share, to slice every component by>"},\n'
    ' "components": [...]}\n'
    'COMPONENTS - only these presets, each {"kind", "title", "source": "<a source key>", ...its bindings, "w": 1-4 (of 4 columns)}:\n'
    '- "stat": one number. "agg": count|sum|avg|median|min|max, "y" for any agg but count, optional "where": {column: value}, '
    '"good": "up"|"down" (which direction is good), optional "unit" (h, min, $). Its delta and sparkline come from the source\'s date. Lead with 2-4 of them.\n'
    '- "progress": a number toward a "target" (same keys as stat, plus "target": <number>).\n'
    '- "line" / "area": a value over time. "x" = the date column, "agg", "y", optional "where". Never two measures on one chart.\n'
    '- "bar": ranked categories. "x" = the category column, "agg", "y", optional "limit" (default 8; the rest fold into Other),'
    ' optional "order": [x values] to keep stages in their order, "share": true to say each bar as a share of the first.\n'
    '- "stacked": categories split by a second column: "x", "series" (at most 6 values read well), "agg", "y".\n'
    '- "table": rows. "columns": [...], optional "sort": "<column>" or "-<column>", "limit".\n'
    '- "list": items, each one line. "label" = the column a person reads, optional "meta" column, "sort", "limit". A row with a '
    'task_id column opens that task when pressed.\n'
    'RULES\n'
    '- One screen: 4-10 components. The numbers first (stat/progress, w 1), the trends and rankings next (w 2), a table or '
    'list last (w 2-4). Every title is what a person would call the number, never a column name.\n'
    '- Bind only to columns you have SEEN - the datasets below list Taskuary\'s own, anything else you peek at first.\n'
    '- "where" values are exact matches of a column\'s values. Counts are "agg": "count" with no "y".\n'
    '- "range": false on a component that counts what is true NOW (open tasks, a balance) - the date range then never cuts it;'
    ' "range": 7 (or 30, 90) is its own fixed window (a weekly target).\n'
    '- No schedule asked for: daily_at "07:00", and say so in explain.\n')
DASHBOARD_KEYS = ('type', 'title', 'every_minutes', 'daily_at', 'cron', 'on_startup', 'sources', 'filters', 'components')


def dashboard_system() -> str:
    from .dashboards import DATASETS
    return (DASHBOARD_SYSTEM + '- Taskuary\'s own data is type "taskuary_data" with "dataset" one of: '
            + '; '.join(f'{k} ({v[1]})' for k, v in DATASETS.items()) + '.\n' + JUDGEMENT + ASK_SHAPE)


def compose_dashboard(store, ask: str, llm, answers: dict = None, rounds: int = MAX_PEEKS) -> dict:
    """{'questions': [...]} or {'config': <a dashboard spec>, 'explain', 'confidence', 'looked_at'} - the same fences as a
    report's: only connected types, only keys the executors take, a peek before a guess. The spec is checked here, and the
    page's preview runs its sources for real before anything is saved."""
    if not llm: return dict(NO_AI)
    if not (ask or '').strip(): return {'error': 'Say what the dashboard should show.'}
    from . import dashboards
    cat = [c for c in catalog(store) if c['type'] not in NOT_A_SOURCE]
    user = {'request': ask.strip(), 'catalog': cat, **({'answers_to_your_questions': answers} if answers else {})}

    def finish(out, looked):
        cfg = out.get('config')
        if not isinstance(cfg, dict): return {'error': AGAIN.format('a dashboard')}
        cfg = {k: v for k, v in cfg.items() if k in DASHBOARD_KEYS} | {'type': 'dashboard'}
        for i, s in enumerate(cfg.get('sources') or [], 1):
            if isinstance(s, dict): s.setdefault('key', f's{i}')
        ok, why = dashboards.validate(cfg, store)
        if not ok: return {'error': why, 'config': cfg}
        return {'config': cfg, 'explain': str(out.get('explain') or '')[:600],
                'confidence': out.get('confidence') or 'medium', 'looked_at': looked}
    return _rounds(store, llm, dashboard_system() + _playbook(cat), user, rounds, finish)

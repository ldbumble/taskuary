"""SOUL.md, written from a short interview.

STYLE.md and TRIAGE.md can be distilled from history: the owner's sent mail IS how they write,
and their verdicts ARE what they consider work (histgen.py). SOUL.md cannot. Who you answer for,
what you will never let an agent decide alone, which systems are yours, who outranks whom -
none of that is in the mailbox. It is in the owner's head, and the shipped template is a
stranger called John Smith until somebody replaces him.

So: seven questions, plain, none of them mandatory, most of them already half-answered from
what Taskuary can see (the connected channels, the repositories, who writes most). The owner
answers in their own words and the AI writes the document in the template's shape - the same
headings the rest of the app already reads, because a beautifully written SOUL.md with
headings nobody parses is a diary.

With no AI connector the answers are still worth having: they are laid into the template
verbatim, which is a worse document and an honest one.
"""
from datetime import datetime

QUESTIONS = [
    {'key': 'who', 'q': 'Who are you, and what is your job?',
     'why': 'Every reply is signed by you and every agent works on your behalf. A name and a role '
            'is the difference between "the owner" and somebody the agent can act for.',
     'placeholder': 'Dana Whitfield, IT director at a facilities group - I own the systems, the vendors and the data'},
    {'key': 'work', 'q': 'What kind of work actually reaches you in a day?',
     'why': 'Triage decides what becomes a task. It needs to know what your day is made of before '
            'it can tell a real request from noise.',
     'placeholder': 'system fixes and access requests, finance questions about Intacct, vendor chasing, '
                    'and a lot of mail that is only cc'},
    {'key': 'task', 'q': 'What should an agent just get on with, without asking you?',
     'why': 'This is the whole promise. Anything you name here stops arriving as a question.',
     'placeholder': 'anything read-only, pulling numbers, drafting replies, fixing an obvious bug in our own repos'},
    {'key': 'never', 'q': 'What must never happen without you?',
     'why': 'The hard line. It is quoted into every coder run and every draft, and it is the one '
            'part of the document an agent is told it cannot reason its way around.',
     'placeholder': 'anything touching payroll or resident data, spending money, promising a date, '
                    'emailing a regulator, deleting anything'},
    {'key': 'people', 'q': 'Who do you answer to, and who answers to you?',
     'why': 'It changes the answer. A question from your CFO is not the same message as the same '
            'question from a vendor.',
     'placeholder': 'the CFO and the COO outrank me; my two sysadmins and the helpdesk report to me; '
                    'vendors get a polite no by default'},
    {'key': 'systems', 'q': 'Which systems and repositories are yours?',
     'why': 'An agent that does not know which checkout is yours will guess, and a confident guess '
            'in the wrong repository is the expensive kind of mistake.',
     'placeholder': 'Sage Intacct, our Entra tenant, the SQL box behind the census app; repos: '
                    'acme/census, acme/importers'},
    {'key': 'voice', 'q': 'How do you want it to sound when it writes as you?',
     'why': 'STYLE.md learns this from your sent mail later; until then, your own description of '
            'your voice is better than the shipped default.',
     'placeholder': 'short, plain, warm but not chatty; no exclamation marks; sign "Dana"'},
]

SYSTEM = (
    'You write SOUL.md: the operator document at the top of an AI work assistant. Everything it '
    'does is stacked on this - triage reads it to decide what is work, the reply writer reads it '
    'to know who is signing, every coding agent gets it verbatim.\n\n'
    'You are given an owner\'s answers to a short interview, in their own words, and what the app '
    'can already see about their setup. Write the document.\n\n'
    'RULES:\n'
    '- Keep EXACTLY these headings, in this order: "# SOUL.md - the operator\'s document", then '
    '"## What counts as a task", "## How we respond", "## Escalate (a human decides) when", '
    '"## Systems and repositories", "## People". The app reads these sections; inventing your own '
    'is a document nothing parses.\n'
    '- Under the title, one short paragraph naming the owner and what the assistant is for.\n'
    '- Short bullets. Concrete. Their words where they gave you words - never inflate a plain '
    'sentence into corporate prose.\n'
    '- Everything they said must survive somewhere. Nothing they did NOT say may appear as fact: '
    'no invented names, systems, hours, or policies. Where they left a question blank, write the '
    'section from the safe default (escalate rather than act) and keep it to one line.\n'
    '- "Nothing sends or ships without <the owner>\'s approval." belongs in the opening paragraph.\n'
    '- Markdown only. No preamble, no closing commentary, no code fences.')


def context(store) -> dict:
    """What the app can already see, so the interview does not ask what it can read."""
    from .store import roles_of
    conns = [c for c in store.list_connectors() if c['Active']]
    repos = [s['Address'] for s in store.list_sources() if s.get('Channel') == 'github']
    who = store.get_settings().get('owner') or ''
    people = [f"{p['Name'] or p['Email']} ({p['N']} messages)" for p in store.people(8)]
    return {'owner': who, 'channels': sorted({c['Type'] for c in conns}), 'repos': repos[:12],
            'writes_most': people, 'roles': sorted({r for c in conns for r in roles_of(c)})}


def _known(ctx: dict) -> str:
    bits = [f"Owner name on file: {ctx['owner'] or '(not set)'}",
            f"Channels connected: {', '.join(ctx['channels']) or 'none yet'}",
            f"Repositories: {', '.join(ctx['repos']) or 'none'}",
            f"Writes to them most: {'; '.join(ctx['writes_most']) or 'nothing ingested yet'}"]
    return 'WHAT THE APP ALREADY SEES (facts - use them, do not contradict them):\n' + '\n'.join(bits)


def _plain(answers: dict, ctx: dict) -> str:
    """No AI connector: their answers, in the template's shape. Worse, and honest."""
    a = lambda k: str(answers.get(k) or '').strip()
    owner = a('who') or ctx.get('owner') or 'the owner'
    lines = [f"# SOUL.md - the operator's document", '',
             f"You work for **{owner}**. You are the funnel between everything inbound and their "
             f"attention. **Nothing sends or ships without {owner.split(',')[0]}'s approval.**", '',
             '## What counts as a task', f"- {a('task') or 'A concrete request to DO something.'}",
             (f"- What reaches this desk: {a('work')}" if a('work') else None), '',
             '## How we respond', f"- {a('voice') or 'Plain, brief, warm-professional.'}", '',
             '## Escalate (a human decides) when',
             f"- {a('never') or 'Money, legal, HR, credentials, permissions, or an external commitment is involved.'}", '',
             '## Systems and repositories', f"- {a('systems') or ', '.join(ctx.get('repos') or []) or '(none named)'}", '',
             '## People', f"- {a('people') or '(not stated)'}", '',
             f"<!-- written from the setup interview, {datetime.now().strftime('%Y-%m-%d')} -->"]
    return '\n'.join(l for l in lines if l is not None)      # '' is a paragraph break, not an absence


def draft(store, answers: dict, llm=None) -> str:
    """The document. The AI writes it where there is one; the answers stand in where there is not."""
    answers = {q['key']: str(answers.get(q['key']) or '').strip() for q in QUESTIONS}
    if not any(answers.values()): raise ValueError('answer at least one question first')
    ctx = context(store)
    if llm is None:
        from .llm import build_llm
        llm = build_llm(store)
    if not llm: return _plain(answers, ctx)
    said = '\n\n'.join(f"Q: {q['q']}\nA: {answers[q['key']] or '(no answer)'}" for q in QUESTIONS)
    out = str(llm(SYSTEM, f'{_known(ctx)}\n\nTHE INTERVIEW:\n\n{said}', max_tokens=1800) or '').strip()
    out = out.removeprefix('```markdown').removeprefix('```').removesuffix('```').strip()
    return out or _plain(answers, ctx)


def write(store, answers: dict, actor: str = 'owner', llm=None) -> str:
    """Draft it and save it. The owner edits it afterwards like any other document - this is a
    first draft from their own words, not a thing that happens to them."""
    body = draft(store, answers, llm)
    store.save_doc('soul', body, actor)
    store.audit('doc', 0, 'soul_interview', actor,
                detail={'answered': [k for k, v in answers.items() if str(v or '').strip()]})
    return body

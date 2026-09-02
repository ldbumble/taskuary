"""Playbooks: how THIS company does ONE kind of job, one markdown file each, accreted the first
time each kind is done (docs/beyond-code.md).

CODER.md is one playbook - the one about code - and "work only in the repository the task
names" is the wrong first rule for a bill. So a playbook is a fourth operator document with a
DIRECTORY instead of a file: ~/.taskuary/playbooks/<slug>.md, six labelled lines on top
(when / uses / steps / alone / ask first / done when) and any prose below. Two doors to the
same file: the Docs tab's Playbooks shelf edits the words, and every connector card lists the
playbooks whose `uses:` line names it.

Three consumers, none of which re-reads the mail to second-guess triage:
- triage is handed menu() - each playbook's title and `when` - and names the one a message is an
  instance of. The task is tagged playbook:<slug>; the tag routes it, like repo: does.
- the seed carries seed_block(): the playbook flattened, riding beside CODER.md and outranking its
  repository rules. context.build writes the whole text into the context file.
- on close, draft() asks one more question of the transcript: was this a kind of job that will
  recur, and does no playbook cover it? The answer is a PROPOSAL (proposals.py write_playbook) -
  approving it files the playbook, and the second such job matches it. Nothing is ever filed
  without the owner's click, for the same reason a bill is not posted without one.
"""
import json, re
from pathlib import Path
from loguru import logger

FIELDS = ('when', 'uses', 'steps', 'alone', 'ask first', 'done when')
_FIELD = re.compile(r'^(' + '|'.join(FIELDS) + r'):\s*(.*)$', re.I)
_TAG = re.compile(r'playbook:([\w-]+)')
SEED_CHARS = 2200            # the whole playbook usually fits; the seed line is the operative rules
MIN_SESSION = 600            # a session shorter than this did no job worth a playbook - no AI call for it
# connections whose presence on `uses:` makes a playbook about code: CODER.md's repository rules apply
CODE_SYSTEMS = {'github', 'gitlab', 'azdo', 'bitbucket'}
CODE_WORDS = re.compile(r'\b(repo|repository|checkout|pull request|commit|branch)\b', re.I)


def folder() -> Path:
    from .config import home
    return home() / 'playbooks'


def slugify(title: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(title or '').lower()).strip('-')[:60]
    return s or 'playbook'


def template() -> str:
    try: return (Path(__file__).parent / 'templates' / 'playbook.md').read_text(encoding='utf-8')
    except OSError: return ''


def parse(text: str) -> dict:
    """{'title', 'when', 'uses', 'steps', 'alone', 'ask first', 'done when', 'body'} - a labelled
    line runs until the next label or a blank line (the example indents its continuations)."""
    out, cur, body = {f: '' for f in FIELDS}, None, []
    out['title'] = ''
    for l in re.sub(r'<!--.*?-->', '', text or '', flags=re.S).splitlines():
        if not out['title'] and l.startswith('# '): out['title'] = l[2:].strip(); continue
        m = _FIELD.match(l.strip())
        if m: cur = m.group(1).lower(); out[cur] = m.group(2).strip(); continue
        if cur and l.strip() and l[:1].isspace(): out[cur] = (out[cur] + ' ' + l.strip()).strip(); continue
        cur = None
        if l.strip(): body.append(l.rstrip())
    out['body'] = '\n'.join(body).strip()
    return out


def uses_of(pb: dict) -> list:
    """Connector types named on `uses:` - 'quickbooks (write: bills) · teller (read)' -> ['quickbooks', 'teller']."""
    # the parentheses go first: "(write: bills, vendors)" carries the same comma the list does
    bare = re.sub(r'\([^)]*\)', '', pb.get('uses') or '')
    return [w for part in re.split(r'[·,;]', bare) for w in [part.strip().lower().replace(' ', '-')] if w]


def about_code(pb: dict) -> bool:
    return bool(CODE_SYSTEMS & set(uses_of(pb))) or bool(CODE_WORDS.search(pb.get('steps') or ''))


def read(slug: str) -> str | None:
    p = folder() / f'{slugify(slug)}.md'
    return p.read_text(encoding='utf-8') if p.is_file() else None


def write(slug: str, text: str) -> str:
    """File it and return the slug - derived from the title when none is given (the 'new' door)."""
    pb = parse(text)
    if not pb['title'] or not pb['when']: raise ValueError('a playbook needs a "# title" line and a "when:" line')
    slug = slugify(slug) if slug and slug != 'new' else slugify(pb['title'])
    d = folder(); d.mkdir(parents=True, exist_ok=True)
    (d / f'{slug}.md').write_text(str(text).rstrip() + '\n', encoding='utf-8')
    return slug


def delete(slug: str) -> bool:
    p = folder() / f'{slugify(slug)}.md'
    if not p.is_file(): return False
    p.unlink(); return True


def list_all() -> list:
    """Every playbook on disk, oldest first, each parsed - the shelf, the cards and triage all read this."""
    d = folder()
    if not d.is_dir(): return []
    out = []
    for p in sorted(d.glob('*.md'), key=lambda p: p.stat().st_mtime):
        try: text = p.read_text(encoding='utf-8')
        except OSError: continue
        pb = parse(text)
        out.append({'slug': p.stem, 'title': pb['title'] or p.stem, 'when': pb['when'], 'uses': uses_of(pb),
                    'alone': pb['alone'], 'ask_first': pb['ask first'], 'done_when': pb['done when'],
                    'about_code': about_code(pb), 'updated': p.stat().st_mtime, 'text': text})
    return out


def for_connector(ctype: str) -> list:
    return [b for b in list_all() if str(ctype or '').lower() in b['uses']]


# ── triage ──────────────────────────────────────────────────────────────────────────────
def menu(books: list = None) -> str:
    """What triage is shown: one line per playbook, slug and `when`. '' when there are none - the
    paragraph is never added for nothing."""
    books = list_all() if books is None else books
    return '\n'.join(f"- {b['slug']}: {b['title']} - when: {b['when']}" for b in books if b['when'])


def tag(slug: str) -> str: return f'playbook:{slugify(slug)}'
def of_task(task: dict) -> str | None: return (_TAG.search(str((task or {}).get('Tags') or '')) or [None, None])[1]


def for_task(task: dict) -> dict | None:
    slug = of_task(task)
    if not slug: return None
    text = read(slug)
    return {**parse(text), 'slug': slug, 'text': text} if text else None


# ── the seed and the context file ───────────────────────────────────────────────────────
def seed_block(task: dict) -> str:
    """The playbook, flattened onto the command line. It is the operative rules for this job, so it
    rides where CODER.md rides; the repository rules there yield to it, the closing-out and wall
    rules do not (an agent posting a bill still says --done)."""
    pb = for_task(task)
    if not pb: return ''
    lines = [f"{f.upper()}: {pb[f]}" for f in FIELDS if pb.get(f)] + ([pb['body']] if pb.get('body') else [])
    flat = ' '.join(' '.join(lines).split())[:SEED_CHARS]
    head = (f'PLAYBOOK "{pb["title"]}" - how this company does this kind of job; it outranks the repository rules in '
            'RULES below, and "ask first" means ask the owner here in the session and wait: ')
    tail = ('' if about_code(pb) else ' THIS IS NOT A CODE CHANGE: the systems named in USES are the ground, reached through '
                                      'Taskuary\'s tools and proposals - do not go looking for a codebase to edit.')
    return head + flat + tail


def context_section(task: dict) -> str:
    pb = for_task(task)
    return f"## The playbook for this kind of job ({pb['slug']}.md - the rules in your prompt come from here)\n{pb['text'].strip()}" if pb else ''


# ── the ending: was this a kind of job that will recur? ─────────────────────────────────
DRAFT_SYSTEM = (
    'You are reading the terminal transcript of an agent that has just finished a piece of work for a '
    'company. Decide whether it did a KIND OF JOB that will recur - posting a bill, onboarding a user, '
    'reconciling a statement, chasing a vendor - which no existing playbook covers, and which the session '
    'shows was done well enough to write down. Usually it did not: a one-off, a code change in a repository '
    '(CODER.md already covers those), or a job a listed playbook already describes is {"playbook": null}.\n'
    'When it did, draft the playbook the NEXT agent would follow, in exactly this shape - a title line and six '
    'labelled lines, then optional notes:\n'
    '# <Verb phrase naming the job>\nwhen:      <what arriving message or event is an instance of this job>\n'
    'uses:      <connection type> (read|write: what) · <connection type> (...)\n'
    'steps:     <the steps, in order, as the session actually did them, → between steps>\n'
    'alone:     <what the agent may do without asking - narrow; the owner widens it later>\n'
    'ask first: <what must be asked in the session before doing>\n'
    'done when: <the receipt: what exists, with which id, when the job is finished>\n'
    'Write only what the transcript shows; never invent a rule the owner did not state. Name systems by the '
    'connection types listed. Output ONLY JSON: {"playbook": null} or {"playbook": {"slug": "<kebab-case>", '
    '"text": "<the markdown above>", "why": "<one sentence: what in the session says this will recur>"}}.')


def draft(store, task_id: int, transcript: str, agent: str = 'coder', llm=None) -> dict | None:
    """The on-close question. Queues a write_playbook PROPOSAL for the owner and returns it, or None -
    and None is the usual, right answer. Never raises: a playbook is a bonus, the task must still close."""
    from .llm import build_llm
    from . import proposals
    try:
        if store.get_settings().get('playbooks_enabled', '1') != '1' or len(str(transcript or '').strip()) < MIN_SESSION: return None
        task = store.get_task(task_id) or {}
        if of_task(task): return None                     # the second run of a playbook is not a new kind of job
        llm = llm or build_llm(store)
        if not llm: return None
        books = list_all()
        user = (f"Playbooks already on file (a job one of these covers is not new):\n{menu(books) or '(none yet)'}\n\n"
                f"Connection types the agents can name on uses: {', '.join(sorted({c['Type'] for c in store.list_connectors() if c.get('Active')})) or '(none)'}\n\n"
                f"Task: {task.get('Title') or ''}\n\nTranscript:\n{transcript[-12000:]}")
        j = json.loads(re.sub(r'^```(json)?|```$', '', str(llm(DRAFT_SYSTEM, user, max_tokens=1200) or '').strip(), flags=re.M))
        pb = j.get('playbook')
        if not isinstance(pb, dict) or not str(pb.get('text') or '').strip(): return None
        parsed = parse(pb['text'])
        if not parsed['title'] or not parsed['when']: return None
        slug = slugify(pb.get('slug') or parsed['title'])
        if any(b['slug'] == slug for b in books): return None
        made = proposals.queue(store, task_id, {'action': 'write_playbook', 'slug': slug, 'text': pb['text'],
                                                'why': str(pb.get('why') or '')[:300]}, agent)
        if made: logger.info(f'playbooks: {agent} drafted "{parsed["title"]}" closing task {task_id} (rv{made["reviewId"]})')
        return made
    except Exception as e:
        logger.debug(f'playbooks: nothing drafted for task {task_id} - {e}')
        return None

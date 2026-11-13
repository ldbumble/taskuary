"""Playbooks: how THIS company does ONE kind of job, one markdown file each, accreted the first
time each kind is done (docs/beyond-code.md).

CODING.md is one playbook - the one about code - and "work only in the repository the task
names" is the wrong first rule for a bill. So a playbook is a fourth operator document with a
DIRECTORY instead of a file: ~/.taskuary/playbooks/<slug>.md, six labelled lines on top
(when / uses / steps / alone / ask first / done when) and any prose below. Two doors to the
same file: the Reports page's Playbooks shelf edits the words (and switches one off), and every connector card lists the
playbooks whose `uses:` line names it.

Three consumers, none of which re-reads the mail to second-guess triage:
- triage is handed menu() - each playbook's title and `when` - and names the one a message is an
  instance of. The task is tagged playbook:<slug>; the tag routes it, like repo: does.
- the seed carries seed_block(): the playbook flattened, riding beside CODING.md and outranking its
  repository rules. context.build writes the whole text into the context file.
- on close, draft() asks one more question of the transcript: was this a kind of job that will
  recur, and does no playbook cover it? The answer is a PROPOSAL (proposals.py write_playbook) -
  approving it files the playbook, and the second such job matches it. Nothing is ever filed
  without the owner's click, for the same reason a bill is not posted without one.
"""
import json, re, time
from pathlib import Path
from loguru import logger

FIELDS = ('when', 'uses', 'steps', 'alone', 'ask first', 'done when')
_FIELD = re.compile(r'^(' + '|'.join(FIELDS) + r'):\s*(.*)$', re.I)
_ITEM = re.compile(r'^(?:\d+[.)]|[-*•])\s')     # a markdown list item: "1. ", "- ", "* "
_TAG = re.compile(r'playbook:([\w-]+)')
SEED_CHARS = 2200            # the whole playbook usually fits; the seed line is the operative rules
MIN_SESSION = 600            # a session shorter than this did no job worth a playbook - no AI call for it
# connections whose presence on `uses:` makes a playbook about code: CODING.md's repository rules apply. ONLY these - the
# words of its steps decide nothing (2026-10-11, "everything should be ai"): "visit the branch office" and "commit the
# journal entry" made a bookkeeping playbook a code change, and its agent was told the repository rules outranked it.
CODE_SYSTEMS = {'github', 'gitlab', 'azdo', 'bitbucket'}


def folder() -> Path:
    from .config import home
    return home() / 'playbooks'


def slugify(title: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(title or '').lower())[:60].strip('-')     # cut, then strip: a cut can land on a '-'
    return s or 'playbook'


def template() -> str:
    try: return (Path(__file__).parent / 'templates' / 'playbook.md').read_text(encoding='utf-8')
    except OSError: return ''


def parse(text: str) -> dict:
    """{'title', 'when', 'uses', 'steps', 'alone', 'ask first', 'done when', 'body'} - a labelled
    line runs until the next label or a blank line (the example indents its continuations).
    ...and a markdown list under its label is that label's (the playbook builder, 2026-11-13): an agent wrote "steps:" with its
    numbered steps on the lines below, unindented - those fields read empty, and its whole playbook was refused as "needs all
    six fields". A label with nothing yet takes the lines below it, and list items right under a line continue it; after a blank
    line, steps written out under a label are still the body, as before."""
    out, cur, body = {f: '' for f in FIELDS}, None, []
    out['title'] = ''
    for l in re.sub(r'<!--.*?-->', '', text or '', flags=re.S).splitlines():
        if not out['title'] and l.startswith('# '): out['title'] = l[2:].strip(); continue
        s = l.strip()
        m = _FIELD.match(s)
        if m: cur = m.group(1).lower(); out[cur] = m.group(2).strip(); continue
        if cur and not s and not out[cur]: continue          # a label's value may start on a line below it
        if cur and s and (l[:1].isspace() or _ITEM.match(s) or not out[cur]): out[cur] = (out[cur] + ' ' + s).strip(); continue
        cur = None
        if s: body.append(l.rstrip())
    out['body'] = '\n'.join(body).strip()
    return out


def uses_of(pb: dict) -> list:
    """Connector types named on `uses:` - 'quickbooks (write: bills) · teller (read)' -> ['quickbooks', 'teller']."""
    # the parentheses go first: "(write: bills, vendors)" carries the same comma the list does
    bare = re.sub(r'\([^)]*\)', '', pb.get('uses') or '')
    return [w for part in re.split(r'[·,;]', bare) for w in [part.strip().lower().replace(' ', '-')] if w]


def about_code(pb: dict) -> bool:
    return bool(CODE_SYSTEMS & set(uses_of(pb)))


def read(slug: str, deleted: bool = False) -> str | None:
    """The page, or None - a deleted one too, unless `deleted` asks for it: to everything but Restore it is gone."""
    p = folder() / f'{slugify(slug)}.md'
    if not deleted and slugify(slug) in deleted_at(): return None
    return p.read_text(encoding='utf-8') if p.is_file() else None


def check(text: str) -> dict:
    "The playbook `text` parsed, or ValueError saying what it lacks - one rule for its writing and for an agent's proposal of it."
    pb = parse(text)
    if not pb['title'] or not pb['when']: raise ValueError('a playbook needs a "# title" line and a "when:" line')
    # ...AND HOW THE JOB IS DONE (the owner, 2026-11-11: "why would you create a blank playbook"): a title and a "when:" alone passed, and
    # a card stood for his approval that said nothing - refused here, to whoever wrote it, with what it lacks
    if not pb['steps'] and not pb['body']: raise ValueError('a playbook says how the job is done: it needs a "steps:" line, or the steps written out under it')
    return pb


def write(slug: str, text: str) -> str:
    """File it and return the slug - derived from the title when none is given (the 'new' door)."""
    pb = check(text)
    slug = slugify(slug) if slug and slug != 'new' else slugify(pb['title'])
    d = folder(); d.mkdir(parents=True, exist_ok=True)
    (d / f'{slug}.md').write_text(str(text).rstrip() + '\n', encoding='utf-8')
    if slug in deleted_at(): _forget(slug); set_on(slug, True)       # a new one under a deleted one's name starts fresh, and on
    return slug


# DELETE IS AT ONCE, AND RECOVERABLE (the owner, 2026-10-21: no "are you sure" on an action). The file stays where it is and a
# stamp beside it says when it was deleted: triage, the shelf and the cards stop seeing it, Recently deleted lists it, and Restore
# drops the stamp - the words, the on/off switch and the shelf order (its mtime) come back exactly. KEEP_DAYS later purge() unlinks it.
DELETED_FILE, KEEP_DAYS = '_deleted.json', 30


def deleted_at() -> dict:
    try: return {str(k): float(v) for k, v in (json.loads((folder() / DELETED_FILE).read_text(encoding='utf-8')) or {}).items()}
    except (OSError, ValueError, TypeError, AttributeError): return {}


def _save_deleted(m: dict):
    d = folder(); d.mkdir(parents=True, exist_ok=True)
    (d / DELETED_FILE).write_text(json.dumps(m, sort_keys=True), encoding='utf-8')


def _forget(slug: str):
    m = deleted_at()
    if m.pop(slugify(slug), None) is not None: _save_deleted(m)


def delete(slug: str, now: float = None) -> bool:
    s, m = slugify(slug), deleted_at()
    if s in m or not (folder() / f'{s}.md').is_file(): return False
    m[s] = time.time() if now is None else now; _save_deleted(m); return True


def restore(slug: str) -> bool:
    s = slugify(slug)
    if s not in deleted_at() or not (folder() / f'{s}.md').is_file(): return False
    _forget(s); return True


def recently_deleted(now: float = None) -> list:
    """The Recently deleted list, newest first: what Restore can still bring back, and when it goes for good."""
    now, out = time.time() if now is None else now, []
    for s, at in sorted(deleted_at().items(), key=lambda kv: -kv[1]):
        text = read(s, deleted=True)
        if text is None: continue
        pb, end = parse(text), at + KEEP_DAYS * 86400
        out.append({'slug': s, 'title': pb['title'] or s, 'when': pb['when'], 'deleted_at': at, 'purge_at': end,
                    'days_left': max(0, int((end - now) // 86400))})
    return out


def purge(now: float = None) -> list:
    """Unlink what was deleted KEEP_DAYS ago - on startup and in the daily housekeeping. The slugs it purged."""
    now, m = time.time() if now is None else now, deleted_at()
    gone = []
    for s, at in list(m.items()):
        if now - at < KEEP_DAYS * 86400: continue
        try: (folder() / f'{s}.md').unlink(missing_ok=True)
        except OSError: continue
        m.pop(s); gone.append(s)
    if gone:
        _save_deleted(m)
        for s in gone: set_on(s, True)                                  # a purged one leaves no stale switch behind
    return gone


# ONE PLAYBOOK SWITCHED OFF, KEPT FOR LATER (the owner, 2026-10-21): delete was the only way to stop one matching. Which are off
# lives beside the files, not in them - the six lines stay the owner's words, and a playbook copied elsewhere carries no switch.
OFF_FILE = '_off.json'


def off() -> set:
    try: return set(json.loads((folder() / OFF_FILE).read_text(encoding='utf-8')) or [])
    except (OSError, ValueError, TypeError): return set()


def set_on(slug: str, on: bool) -> bool:
    s, cur = slugify(slug), off()
    now = cur - {s} if on else cur | {s}
    if now != cur:
        d = folder(); d.mkdir(parents=True, exist_ok=True)
        (d / OFF_FILE).write_text(json.dumps(sorted(now)), encoding='utf-8')
    return on


def list_all() -> list:
    """Every playbook on disk and not deleted, oldest first, each parsed - the shelf, the cards and triage all read this."""
    d = folder()
    if not d.is_dir(): return []
    out, shut, gone = [], off(), deleted_at()
    for p in sorted(d.glob('*.md'), key=lambda p: p.stat().st_mtime):
        if p.stem in gone: continue
        try: text = p.read_text(encoding='utf-8')
        except OSError: continue
        pb = parse(text)
        out.append({'slug': p.stem, 'title': pb['title'] or p.stem, 'when': pb['when'], 'uses': uses_of(pb),
                    'alone': pb['alone'], 'ask_first': pb['ask first'], 'done_when': pb['done when'],
                    'about_code': about_code(pb), 'updated': p.stat().st_mtime, 'text': text,
                    'enabled': p.stem not in shut})
    return out


def for_connector(ctype: str) -> list:
    return [b for b in list_all() if str(ctype or '').lower() in b['uses']]


# ── triage ──────────────────────────────────────────────────────────────────────────────
def menu(books: list = None, store=None) -> str:
    """What triage is shown: one line per playbook, slug and `when`. '' when there are none - the
    paragraph is never added for nothing. A playbook switched off is not offered, and with the store's
    `playbooks_enabled` off none is: that switch said "follow" while triage went on matching them all."""
    if store is not None and store.get_setting('playbooks_enabled', '1') != '1': return ''
    books = list_all() if books is None else books
    return '\n'.join(f"- {b['slug']}: {b['title']} - when: {b['when']}" for b in books if b['when'] and b.get('enabled', True))


# ── the general agent's menu ─────────────────────────────────────────────────────────────
# A MENU, NOT A PICK (the owner, 2026-11-05, from Hermes' skills index: "list every playbook's when + its path ... let the agent read the full
# one itself when it decides it applies, including mid-task"): code handing one playbook to the agent decided for it what kind of job this is,
# and a job that turned into another kind halfway never saw the second. One short line each keeps the brief lean (the 2026-11-05 rule); the
# file is read whole only when the agent says it applies. Triage's match is said on its line - a reading, not a rule.
MENU_MAX, MENU_WHEN = 30, 160


def path_of(slug: str) -> Path: return folder() / f'{slugify(slug)}.md'


def agent_menu(task: dict = None, store=None) -> str:
    "Every playbook switched on, one line each - its slug, its `when` and its file. '' when there are none, or playbooks are off."
    if store is not None and store.get_setting('playbooks_enabled', '1') != '1': return ''
    books, mine = [b for b in list_all() if b['when'] and b.get('enabled', True)], of_task(task)
    if not books: return ''
    cut = lambda s: s if len(s) <= MENU_WHEN else s[:MENU_WHEN - 1] + '…'
    lines = [f"- {b['slug']}: when {cut(' '.join(b['when'].split()))} -> {path_of(b['slug'])}" + (' (triage read this task as one)' if b['slug'] == mine else '')
             for b in books[:MENU_MAX]]
    return ("PLAYBOOKS - how this company does each kind of job. When one applies - now, or as the work turns into it - read its file whole "
            "and follow it; it outranks your own way, and its `ask first` means ask the owner and wait:\n" + '\n'.join(lines))


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
    rides where CODING.md rides; the repository rules there yield to it, the closing-out and wall
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
    '(CODING.md already covers those), or a job a listed playbook already describes is {"playbook": null}.\n'
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


def draft(store, task_id: int, transcript: str, agent: str = 'agent', llm=None) -> dict | None:
    """The on-close question. Queues a write_playbook PROPOSAL for the owner and returns it, or None -
    and None is the usual, right answer. Never raises: a playbook is a bonus, the task must still close."""
    from .llm import build_llm
    from . import proposals
    try:
        if store.get_setting('playbooks_enabled', '1') != '1' or len(str(transcript or '').strip()) < MIN_SESSION: return None
        task = store.get_task(task_id) or {}
        if of_task(task): return None                     # the second run of a playbook is not a new kind of job
        # ...nor is a workflow's run (its job is written down already, as the workflow) or a playbook being written by hand
        if task.get('Source') == 'workflow' or task.get('SourceRef') == 'assistant:playbook': return None
        # ...nor asked again while this task's own proposal still waits: a chat task's agent ends its session after every turn, and each
        # ending proposed the same kind of job under another slug - three waiting on one task (the stress run, 2026-11-05)
        if proposals.playbook_pending(store, task_id): return None
        llm = llm or build_llm(store, job='memory')
        if not llm: return None
        books = list_all()
        user = (f"Playbooks already on file (a job one of these covers is not new):\n{menu(books) or '(none yet)'}\n\n"
                f"Connection types the agents can name on uses: {', '.join(sorted({c['Type'] for c in store.list_connectors() if c.get('Active')})) or '(none)'}\n\n"
                f"Task: {task.get('Title') or ''}\n\nTranscript:\n{transcript[-12000:]}")
        j = json.loads(re.sub(r'^```(json)?|```$', '', str(llm(DRAFT_SYSTEM, user, max_tokens=1200) or '').strip(), flags=re.M))
        pb = j.get('playbook')
        if not isinstance(pb, dict) or not str(pb.get('text') or '').strip(): return None
        try: parsed = check(pb['text'])                 # one rule for every road: never queue one that says nothing
        except ValueError: return None
        slug = slugify(pb.get('slug') or parsed['title'])
        if any(b['slug'] == slug for b in books): return None
        made = proposals.queue(store, task_id, {'action': 'write_playbook', 'slug': slug, 'text': pb['text'],
                                                'why': str(pb.get('why') or '')[:300]}, agent)
        if made:
            logger.info(f'playbooks: {agent} drafted "{parsed["title"]}" closing task {task_id} (rv{made["reviewId"]})')
            proposals.hold_for_playbook(store, task_id, agent)      # a task already done would hide it (proposals.HELD)
        return made
    except Exception as e:
        logger.debug(f'playbooks: nothing drafted for task {task_id} - {e}')
        return None


# ── lessons on a playbook page: an `amend_playbook` card's lessons, onto the page in a marked block, so the owner's own lines are never
# touched (proposals.py). A turn's own summary no longer leaves a lesson: it went to LEARNED.md, and the memory wrote an agent's takeaway
# as a fact about the owner (the owner, 2026-11-13) - the memory learns from what the owner did and wrote, never from what an agent concluded.
LESSONS_START, LESSONS_END, LESSONS_HEAD = '<!-- lessons:start -->', '<!-- lessons:end -->', '## Lessons from the work'
LESSONS_MAX = 40


def lessons_of(text: str) -> list:
    "The lessons already in the page's block."
    if LESSONS_START not in (text or '') or LESSONS_END not in text: return []
    body = text.split(LESSONS_START, 1)[1].split(LESSONS_END, 1)[0]
    return [l[2:].strip() for l in body.splitlines() if l.startswith('- ') and l[2:].strip()]


def with_lessons(text: str, lines: list) -> str:
    "The page with each of `lines` in its lessons block once, the newest LESSONS_MAX kept; the block goes at the foot when there is none."
    text, have = text or '', lessons_of(text)
    seen = {l.lower() for l in have}
    keep = [*have, *(l for l in dict.fromkeys(' '.join(str(x).split()) for x in lines or ()) if l and l.lower() not in seen)][-LESSONS_MAX:]
    block = f"{LESSONS_START}\n{LESSONS_HEAD}\n" + '\n'.join(f'- {l}' for l in keep) + f"\n{LESSONS_END}"
    if LESSONS_START in text and LESSONS_END in text:
        head, rest = text.split(LESSONS_START, 1)
        return head + block + rest.split(LESSONS_END, 1)[1]
    return (text.rstrip('\n') + '\n\n' if text.strip() else '') + block + '\n'

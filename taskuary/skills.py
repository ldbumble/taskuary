"""Skills: how THIS company does ONE kind of job - a folder each, in the format Claude Code and other agents already read.

    ~/.taskuary/skills/<name>/SKILL.md      frontmatter `name` + `description`, then a body in the owner's words

`description` is what triage and an agent read to decide whether the skill fits; the body is read whole only by the agent that chose
it. `metadata.uses` (optional, Taskuary's one extra) names the connections the job touches - it feeds the connection cards and the
"is this about code" check. Everything else in the frontmatter is somebody else's and is never read.

A SKILL IS CONTEXT, NEVER A PERMISSION. Nothing here, and no gate anywhere, reads a skill to allow an act: `allowed-tools`, "send
without asking", "alone: bills under $500" are words on a page. What may run is scopes.ACTIONS and his press on a card (contract 9).

One library: his own skills, the ones he imported (skillshare.py), a verified metric frozen into one (semantic.write_skill) and the one
a routine uses (workflows.definition) are all folders here, listed by list_all(). The folder of pages that came before (`playbooks/`,
six labelled lines each) is moved over once by migrate(), wording untouched, and kept where it was as a backup.

Three readers, none of which re-reads the mail to second-guess triage:
- triage is handed menu() - each skill's name and description - and names the one a message is an instance of. The task is tagged
  skill:<name>; the tag routes it, like repo: does.
- every agent's context carries brief() - the same names and descriptions - and it reads one whole through its `skills` tool (lookup).
  A stranger's task carries none, as it carries nothing else of the owner's.
- the agent that did a kind of job offers its skill itself, as one card behind the send it follows (agenttools `propose` kind skill ->
  proposals.py save_skill); his press files it. No second model reads a finished task to draft one in the agent's place, and nothing is
  ever filed without his press, for the same reason a bill is not posted without one.
"""
import json, re, shutil, time
from pathlib import Path
from loguru import logger

FILE = 'SKILL.md'
_FRONT = re.compile(r'\A\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)', re.S)
_KEY = re.compile(r'^([A-Za-z][\w-]*):[ \t]*(.*)$')
_TAG = re.compile(r'(?:skill|playbook):([\w-]+)')      # a task tagged before the move reads the same
# connections whose presence on `uses` makes a skill about code: CODING.md's repository rules apply. ONLY these - the words of its
# body decide nothing (2026-10-11, "everything should be ai"): "visit the branch office" and "commit the journal entry" made a
# bookkeeping job a code change, and its agent was told the repository rules outranked it.
CODE_SYSTEMS = {'github', 'gitlab', 'azdo', 'bitbucket'}
_moved = set()


def folder() -> Path:
    from .config import home
    h = home()
    if str(h) not in _moved: _moved.add(str(h)); migrate(h)        # once per home, by whichever process reads it first
    return h / 'skills'


def slugify(title: str) -> str:
    s = re.sub(r'[^a-z0-9]+', '-', str(title or '').lower())[:60].strip('-')     # cut, then strip: a cut can land on a '-'
    return s or 'skill'


def key(slug: str) -> str:
    "The folder a skill is kept in: one already there under exactly that name (his own, from another agent's library), else its slug."
    s = str(slug or '').strip()
    return s if re.fullmatch(r'[A-Za-z0-9][\w.-]*', s) and (folder() / s / FILE).is_file() else slugify(s)


def path_of(slug: str) -> Path: return folder() / key(slug) / FILE
def _scalar(v: str) -> str:
    v = v.strip()
    if v[:1] == '"':
        try: return str(json.loads(v))
        except ValueError: return v.strip('"')
    return v[1:-1].replace("''", "'") if len(v) > 1 and v[0] == v[-1] == "'" else v


def _front(head: str) -> dict:
    """{'name', 'description', 'uses'} of a frontmatter block - a top-level `key: value` whose value may run on indented lines (or
    under `>` / `|`), and `metadata` as an indented or an inline `{...}` mapping. Any other key is not ours and is not kept."""
    top, cur = {}, None
    for l in head.splitlines():
        m = _KEY.match(l)
        if m: cur = m.group(1).lower(); top[cur] = [m.group(2)]
        elif cur and l.strip(): top[cur].append(l.strip())
    val = lambda k: _scalar(' '.join(x for x in top.get(k, []) if x not in ('>', '|', '>-', '|-')))
    meta = top.get('metadata') or []
    inline = re.search(r'\buses:\s*("[^"]*"|\'[^\']*\'|[^,}]*)', ' '.join(meta)) if meta else None
    return {'name': val('name'), 'description': ' '.join(val('description').split()), 'uses': _scalar(inline.group(1)) if inline else ''}


def parse(text: str, slug: str = '') -> dict:
    """{'name', 'description', 'uses', 'title', 'body', 'front'} of a SKILL.md. One with no frontmatter still reads: its name is its
    folder's (`slug`) and its description its first line."""
    text = str(text or ''); m = _FRONT.match(text)
    fm, body = (_front(m.group(1)), text[m.end():]) if m else ({}, text.lstrip('\ufeff'))
    lines = [l.strip() for l in re.sub(r'<!--.*?-->', '', body, flags=re.S).splitlines() if l.strip()]
    title = next((l[2:].strip() for l in lines if l.startswith('# ')), '')
    first = lines[0].lstrip('#').strip() if lines else ''
    said = '\n'.join(lines if m else lines[1:]).strip()                # with no frontmatter the first line is the description, not the how
    return {'name': fm.get('name') or slug, 'description': fm.get('description') or first, 'uses': fm.get('uses') or '',
            'title': title or fm.get('name') or first or slug, 'body': said, 'front': bool(m)}


def uses_of(pb: dict) -> list:
    """Connector types named on `uses` - 'quickbooks (write: bills) · teller (read)' -> ['quickbooks', 'teller']."""
    # the parentheses go first: "(write: bills, vendors)" carries the same comma the list does
    bare = re.sub(r'\([^)]*\)', '', pb.get('uses') or '')
    return [w for part in re.split(r'[·,;]', bare) for w in [part.strip().lower().replace(' ', '-')] if w]


def about_code(pb: dict) -> bool:
    return bool(CODE_SYSTEMS & set(uses_of(pb)))


def front(name: str, description: str, uses: str = '') -> str:
    "The standard frontmatter - quoted, so a colon in his words is still one line to any other reader."
    q = lambda s: json.dumps(' '.join(str(s or '').split()), ensure_ascii=False)
    return f"---\nname: {slugify(name)}\ndescription: {q(description)}\n" + (f"metadata:\n  uses: {q(uses)}\n" if uses else '') + '---\n'


TEMPLATE = (front('vendor-payment-question', 'Answer a vendor asking where their payment is. Use when a vendor writes about an unpaid or '
                  'late invoice.', 'quickbooks, outlook')
            + '\n# Vendor payment question\n\n1. Find the invoice and whether it is approved, scheduled or paid.\n'
              '2. Reply with the date it was or will be paid, and how.\n3. An invoice nobody has seen is forwarded to accounts payable first.\n')


def read(slug: str, deleted: bool = False) -> str | None:
    """The SKILL.md, or None - a deleted one too, unless `deleted` asks for it: to everything but Restore it is gone."""
    p = path_of(slug)
    if not deleted and key(slug) in deleted_at(): return None
    try: return p.read_text(encoding='utf-8') if p.is_file() else None
    except (OSError, ValueError): return None


def check(text: str) -> dict:
    "The skill `text` parsed, or ValueError saying what it lacks - one rule for its writing, its import and an agent's proposal of it."
    pb = parse(text)
    if not pb['description']:
        raise ValueError('a skill needs a `description:` line in its frontmatter - what the job is and when to use it')
    # ...AND HOW THE JOB IS DONE (the owner, 2026-11-11: "why would you create a blank playbook"): a name and a description alone passed,
    # and a card stood for his approval that said nothing - refused here, to whoever wrote it, with what it lacks
    if not pb['body']: raise ValueError('a skill says how the job is done: it needs a body under its frontmatter (`name`, `description`)')
    return pb


def named(text: str, slug: str) -> str:
    "`text` as the file kept under `slug`: its frontmatter's `name` is its folder's, and one with no frontmatter is given the standard two lines."
    m = _FRONT.match(text := str(text or '').lstrip('\ufeff'))
    if not m: return adopt(text, slug)
    head = m.group(1)
    head = re.sub(r'(?m)^name:.*$', f'name: {slug}', head, count=1) if re.search(r'(?m)^name:', head) else f'name: {slug}\n{head}'
    return f'---\n{head}\n---\n' + text[m.end():].rstrip() + '\n'


def filed_as(slug: str, text: str) -> str:
    "The folder `text` is filed in under `slug` - its own name's when none is given (the 'new' door). One reading for the save and its card."
    if slug and slug != 'new': return slugify(slug)
    pb = parse(text)
    return slugify(pb['name'] or pb['title'])


def write(slug: str, text: str) -> str:
    """File it and return its name - taken from the text when none is given (the 'new' door)."""
    check(text); slug = filed_as(slug, text)
    d = folder() / slug; d.mkdir(parents=True, exist_ok=True)
    (d / FILE).write_text(named(text, slug), encoding='utf-8')
    if slug in deleted_at(): _forget(slug); set_on(slug, True)       # a new one under a deleted one's name starts fresh, and on
    return slug


def free(name: str) -> str:
    "`name` as a folder nothing holds yet - `name-2`, `name-3` when it is taken: nothing that arrives ever lands on a skill he has."
    base = s = slugify(name); n = 1
    while (folder() / s).exists(): n += 1; s = f'{base[:56]}-{n}'
    return s


# ── the pages that came before: ~/.taskuary/playbooks/<slug>.md, moved here once ─────────────────────────────────────────────────
MOVED = '_moved.json'
_OLD = lambda label, text: ' '.join((re.search(rf'(?mi)^{label}:[ \t]*(.*(?:\n[ \t]+\S.*)*)', text) or ['', ''])[1].split())


def adopt(text: str, slug: str = '') -> str:
    """A page in the old six-label shape as a SKILL.md: its title and `when` line become the description, its `uses` the metadata, and
    the page itself is the body, not a word changed. A text that already has frontmatter is returned as it is."""
    text = str(text or '')
    if _FRONT.match(text): return text
    pb, when = parse(text, slug), _OLD('when', text)
    desc = f"{pb['title'].rstrip('.')}. Use when {when}" if when else pb['description'] or pb['title']
    return front(slug or pb['title'], desc, _OLD('uses', text)) + '\n' + text.strip() + '\n' if desc else text


def migrate(home: Path) -> list:
    """Each `playbooks/<slug>.md` as `skills/<slug>/SKILL.md`, once: MOVED beside the old pages says which went, so one he deletes
    later is not brought back, and a second run moves nothing. The old folder is left exactly as it was. The names it moved."""
    old, new = Path(home) / 'playbooks', Path(home) / 'skills'
    if not old.is_dir(): return []
    def load(p, empty):
        try: return json.loads(p.read_text(encoding='utf-8')) or empty
        except (OSError, ValueError): return empty
    done, went = load(old / MOVED, {}), []
    for p in sorted(old.glob('*.md'), key=lambda p: p.stat().st_mtime):
        if p.stem in done: continue
        try:
            slug, n = slugify(p.stem), 1
            while (new / slug).exists(): n += 1; slug = f'{slugify(p.stem)[:56]}-{n}'      # never onto a skill already there
            (new / slug).mkdir(parents=True)
            (new / slug / FILE).write_text(adopt(p.read_text(encoding='utf-8'), slug), encoding='utf-8')
            shutil.copystat(p, new / slug / FILE)                                           # the shelf's order is its mtime
            done[p.stem] = slug; went.append(slug)
        except (OSError, ValueError) as e: logger.warning(f'skills: {p.name} was not moved - {e}')
    if not went: return []
    try:
        gone = {done[k]: v for k, v in load(old / DELETED_FILE, {}).items() if k in done}
        shut = [done[k] for k in load(old / OFF_FILE, []) if k in done]
        if gone: (new / DELETED_FILE).write_text(json.dumps({**load(new / DELETED_FILE, {}), **gone}, sort_keys=True), encoding='utf-8')
        if shut: (new / OFF_FILE).write_text(json.dumps(sorted({*load(new / OFF_FILE, []), *shut})), encoding='utf-8')
        (old / MOVED).write_text(json.dumps(done, sort_keys=True), encoding='utf-8')
    except OSError as e: logger.warning(f'skills: the move was not recorded - {e}')
    logger.info(f"skills: moved {len(went)} from {old} - the old folder is kept as a backup")
    return went


def move_cards(store) -> int:
    "Cards raised under the old action names, waiting or answered, read as save_skill - so nothing he had pending breaks. How many."
    rows = store._rows("SELECT ReviewId, DraftText FROM review WHERE Kind='action' AND (DraftText LIKE '%write_playbook%' OR DraftText LIKE '%amend_playbook%')")
    for r in rows:
        store._exec('UPDATE review SET DraftText=? WHERE ReviewId=?',
                    (re.sub(r'"action":\s*"(?:write|amend)_playbook"', '"action": "save_skill"', r['DraftText']), r['ReviewId']))
    return len(rows)


# ── the skills a home starts with ────────────────────────────────────────────────────────────────────────────────────────────────
# A FEW EVERYDAY JOBS, WRITTEN ONCE (the owner, 2026-11-26: "did you seed with a few skills and one that includes interview"): a website, a
# document, a spreadsheet, slides, charts, research - shipped beside the code and filed into his library like any skill of his, his to edit,
# switch off or delete. A context for the agent that picks one, as every skill is - never a permission
STARTERS, SEEDED = Path(__file__).parent / 'starter_skills', '_seeded.json'


def seed() -> list:
    """Each starter skill filed into this home's library ONCE - the names it filed. A name already offered here (SEEDED) is never offered
    again, so one he deleted stays gone and one he rewrote stays his; a folder of that name already there - his own, an imported one - is
    never touched. A home from before them gets each it has no skill named for, at its next start."""
    d, had, went = folder(), set(_json(SEEDED, [])), []
    names = sorted(p.parent.name for p in STARTERS.glob(f'*/{FILE}'))
    for s in names:
        if s in had or (d / s).exists(): continue
        (d / s).mkdir(parents=True); shutil.copyfile(STARTERS / s / FILE, d / s / FILE); went.append(s)
    if set(names) - had: _save(SEEDED, sorted(had | set(names)))
    if went: logger.info(f"skills: {len(went)} starter skill(s) filed - {', '.join(went)}")
    return went


# DELETE IS AT ONCE, AND RECOVERABLE (the owner, 2026-10-21: no "are you sure" on an action). The folder stays where it is and a
# stamp beside it says when it was deleted: triage, the shelf and the cards stop seeing it, Recently deleted lists it, and Restore
# drops the stamp - the words, the on/off switch and the shelf order (its mtime) come back exactly. KEEP_DAYS later purge() removes it.
DELETED_FILE, KEEP_DAYS = '_deleted.json', 30


def _json(name: str, empty):
    try: return json.loads((folder() / name).read_text(encoding='utf-8')) or empty
    except (OSError, ValueError, TypeError): return empty


def _save(name: str, value):
    d = folder(); d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(value, sort_keys=True), encoding='utf-8')


def deleted_at() -> dict:
    try: return {str(k): float(v) for k, v in _json(DELETED_FILE, {}).items()}
    except (ValueError, TypeError, AttributeError): return {}


def _forget(slug: str):
    m = deleted_at()
    if m.pop(key(slug), None) is not None: _save(DELETED_FILE, m)


def delete(slug: str, now: float = None) -> bool:
    s, m = key(slug), deleted_at()
    if s in m or not path_of(s).is_file(): return False
    m[s] = time.time() if now is None else now; _save(DELETED_FILE, m); return True


def restore(slug: str) -> bool:
    s = key(slug)
    if s not in deleted_at() or not path_of(s).is_file(): return False
    _forget(s); return True


def recently_deleted(now: float = None) -> list:
    """The Recently deleted list, newest first: what Restore can still bring back, and when it goes for good."""
    now, out = time.time() if now is None else now, []
    for s, at in sorted(deleted_at().items(), key=lambda kv: -kv[1]):
        text = read(s, deleted=True)
        if text is None: continue
        pb, end = parse(text, s), at + KEEP_DAYS * 86400
        out.append({'slug': s, 'title': pb['title'], 'description': pb['description'], 'deleted_at': at, 'purge_at': end,
                    'days_left': max(0, int((end - now) // 86400))})
    return out


def purge(now: float = None) -> list:
    """Remove what was deleted KEEP_DAYS ago - on startup and in the daily housekeeping. The names it purged."""
    now, m = time.time() if now is None else now, deleted_at()
    gone = []
    for s, at in list(m.items()):
        if now - at < KEEP_DAYS * 86400: continue
        try: shutil.rmtree(folder() / s) if (folder() / s).is_dir() else None
        except OSError: continue
        m.pop(s); gone.append(s)
    if gone:
        _save(DELETED_FILE, m)
        for s in gone: set_on(s, True); set_origin(s, ''); set_profile(s, '')      # a purged one leaves no stale switch behind
    return gone


# ONE SKILL SWITCHED OFF, KEPT FOR LATER (the owner, 2026-10-21): delete was the only way to stop one matching. Which are off lives
# beside the folders, not in the file - the words stay the owner's, and a skill sent to someone else carries no switch.
OFF_FILE = '_off.json'


def off() -> set:
    try: return set(_json(OFF_FILE, []))
    except TypeError: return set()


def set_on(slug: str, on: bool) -> bool:
    s, cur = key(slug), off()
    now = cur - {s} if on else cur | {s}
    if now != cur: _save(OFF_FILE, sorted(now))
    return on


# WHERE ONE CAME FROM, kept beside the folders like the switch: a skill somebody sent him is said as such wherever it is listed, so its
# words are weighed as someone else's (skillshare.py writes 'imported'; his own and an agent's approved one have none).
ORIGIN_FILE = '_origin.json'


def origins() -> dict:
    m = _json(ORIGIN_FILE, {})
    return m if isinstance(m, dict) else {}


def set_origin(slug: str, origin: str):
    s, m = key(slug), origins()
    if (m.get(s) or '') == (origin or ''): return
    m = {**m, s: origin} if origin else {k: v for k, v in m.items() if k != s}
    _save(ORIGIN_FILE, m)


def files_of(slug: str) -> list:
    "What else is in a skill's folder, as paths under it - stored, listed, and never run by Taskuary."
    d = folder() / key(slug)
    return sorted(p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file() and p.relative_to(d).as_posix() != FILE) if d.is_dir() else []


def list_all() -> list:
    """Every skill on disk and not deleted, oldest first, each parsed - the shelf, the cards, triage and the agents all read this."""
    d = folder()
    if not d.is_dir(): return []
    out, shut, gone, came, whose = [], off(), deleted_at(), origins(), profiles()
    found = [p for p in d.glob(f'*/{FILE}') if p.is_file() and p.parent.name not in gone]
    for p in sorted(found, key=lambda p: p.stat().st_mtime):
        try: text = p.read_text(encoding='utf-8')
        except (OSError, ValueError): continue
        slug = p.parent.name; pb = parse(text, slug)
        out.append({'slug': slug, 'title': pb['title'], 'description': pb['description'], 'uses': uses_of(pb),
                    'about_code': about_code(pb), 'updated': p.stat().st_mtime, 'text': text, 'enabled': slug not in shut,
                    'origin': came.get(slug) or '', 'profile': whose.get(slug) or '', 'files': files_of(slug)})
    return out


def for_connector(ctype: str) -> list:
    return [b for b in list_all() if str(ctype or '').lower() in b['uses']]


# ── who is offered them: ONE LIST, read by triage (menu), by every agent's context (brief) and by its tool (lookup) ──────────────
# A LISTING LIKE A TOOL LISTING (the owner, 2026-11-26: "it should not be more than name and short description like the way tools are
# called" - a hundred skills, general ones and one per kind of email, must not inflate triage or a brief): each skill is its name and
# its description cut to LIST_DESC characters, and nothing else. EVERY one is listed - none dropped past a count - in the order of
# their names, so the block is the same bytes on every call and a provider's cache pays for it once. The body is read whole only by
# the agent that chooses one (lookup). Triage's own pick is said on a line after the list, never inside it.
LIST_DESC = 120


# WHOSE A SKILL IS, where he keeps more than one profile (workstreams.py): one profile's, or every profile's - kept beside the folders
# like the switch. A task or a mail is offered its own profile's skills and the ones left to all, as it may use its own profile's
# accounts (workstreams.may_use).
PROFILE_FILE = '_profile.json'


def profiles() -> dict:
    m = _json(PROFILE_FILE, {})
    return {str(k): str(v) for k, v in m.items() if v} if isinstance(m, dict) else {}


def set_profile(slug: str, profile: str):
    s, m = key(slug), profiles()
    if (m.get(s) or '') == (profile or ''): return
    _save(PROFILE_FILE, {**m, s: profile} if profile else {k: v for k, v in m.items() if k != s})


def profile_of(store, task: dict = None, msg: dict = None):
    "The profile a task or an arriving mail is under ('' for none) - None where he keeps fewer than two, and nothing is told apart."
    from . import workstreams
    if store is None or len(workstreams.streams(store)) < 2: return None
    if task and task.get('TaskId'): return workstreams.of_task(store, int(task['TaskId'])) or ''
    if msg:
        up = {'SourceName': msg.get('SourceName') or msg.get('source_name'), 'Channel': msg.get('Channel') or msg.get('channel'),
              'ConversationId': msg.get('ConversationId') or msg.get('conversation_id'), 'Workstream': msg.get('Workstream'),
              'FromEmail': msg.get('FromEmail') or msg.get('from_email')}
        return workstreams.of_message(store, {**msg, **up}) or ''
    return None


def offered(store=None, books: list = None, profile: str = None) -> list:
    """The skills switched on, each with a description, by name - none when the store's `playbooks_enabled` is off: that switch said
    "use" while triage went on matching them all. `profile`: only that profile's and the ones left to every profile (None: all)."""
    if store is not None and store.get_setting('playbooks_enabled', '1') != '1': return []
    got = [b for b in (list_all() if books is None else books) if b.get('description') and b.get('enabled', True)]
    if profile is not None: got = [b for b in got if not b.get('profile') or b['profile'] == profile]
    return sorted(got, key=lambda b: b['slug'])


def line(b: dict) -> str:
    "One skill as it is listed anywhere: its name, its description cut short, and whose words they are when not his."
    d = ' '.join(b['description'].split())
    return f"- {b['slug']}: {d if len(d) <= LIST_DESC else d[:LIST_DESC - 1] + '…'}" + (' (imported, not written by the owner)' if b.get('origin') == 'imported' else '')


def menu(books: list = None, store=None, msg: dict = None) -> str:
    """What triage is shown: one line per skill offered for this mail's profile. '' when there are none - the paragraph is never added
    for nothing."""
    return '\n'.join(line(b) for b in offered(store, books, profile_of(store, msg=msg)))


BRIEF_HEAD = "THE OWNER'S SKILLS - how each kind of job is done here, by name; one read whole is the `skills` tool's answer:"
def _listing(store, task: dict) -> str:
    books = offered(store, profile=profile_of(store, task))
    mine = of_task(task)
    return '\n'.join([*(line(b) for b in books), *([f'Triage read this task as: {mine}'] if mine and any(b['slug'] == mine for b in books) else [])])


def brief(store=None, task: dict = None, sep: str = '\n') -> str:
    """What every agent's context carries of his skills: their names and short descriptions - a list of what there is, the same one
    triage is shown and the `skills` tool answers with. '' with none, or with them switched off. A body is never here: the agent reads
    one when it chooses to (lookup)."""
    got = _listing(store, task)
    return sep.join([BRIEF_HEAD, *got.split('\n')]) if got else ''


def lookup(store=None, task: dict = None, name: str = '') -> str:
    """The `skills` tool's answer (agenttools): with no `name`, every skill switched on - its name and description, triage's match said on
    its line; with one, that skill whole."""
    if store is not None and store.get_setting('playbooks_enabled', '1') != '1': return 'Skills are switched off.'
    if name:
        b = next((b for b in offered(store, profile=profile_of(store, task)) if b['slug'] == key(name)), None)
        if not b: return f"No skill is called {name!r} - ask with no name for the list."
        # ...and the routines of his that use it, by title (workflows.uses_skill): a change to this page is a change to how each does its job
        from . import workflows
        used = workflows.uses_skill(store).get(b['slug']) if store is not None else None
        return b['text'] + (f"\n\nFiles kept with it: {', '.join(b['files'])}" if b['files'] else '') + (f"\n\nUsed by his routines: {', '.join(used)}" if used else '')
    return _listing(store, task) or 'There are no skills yet.'


def tag(slug: str) -> str: return f'skill:{slugify(slug)}'
def of_task(task: dict) -> str | None: return (_TAG.search(str((task or {}).get('Tags') or '')) or [None, None])[1]


def for_task(task: dict) -> dict | None:
    slug = of_task(task)
    if not slug: return None
    text = read(slug)
    return {**parse(text, slug), 'slug': slug, 'text': text} if text else None


# ── lessons on a skill: a `save_skill` card's lessons, onto the page in a marked block, so the owner's own lines are never
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

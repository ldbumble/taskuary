"""Importing somebody else's expertise, as a profile.

A skill is HOW a job is done - eleven knowledge-work plugins of it, written by people who do those
jobs, stuck in one vendor's directory where only Claude Code can read them. Converted once it becomes
an ordinary Taskuary profile, and an ordinary profile drives a codex session.

It never becomes a PLAYBOOK. A playbook's fields are uses/alone/ask first/done when - every one about
acting on a system - and a SKILL.md states none of them, so converting to one meant inventing `uses:`,
which decides whether CODER.md's repository rules apply. A profile needs a purpose and a body, and
both are already in the file. Nothing is guessed.

This module finds and parses. It writes nothing and fetches nothing it was not pointed at.
"""
import json, re
from pathlib import Path

# Where Claude Code keeps them. Read-only, and the only thing we know about another tool's disk.
SKILL_GLOBS = ('.claude/skills/*/SKILL.md',
               '.claude/plugins/cache/*/*/*/skills/*/SKILL.md')
_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', re.S)
_KEY = re.compile(r'^(name|description)\s*:\s*(.*)$')


def _fm_fields(head: str) -> dict:
    """name/description out of the frontmatter, including YAML's folded (`>`) and literal (`|`) block
    scalars. A third-party SKILL.md may write `description: >` with the sentence on the indented lines
    below; reading only that first line turned the purpose into the literal word '>' - which becomes
    a profile's stated purpose, so garbage there is worse than a crash. Fold joins continuation lines
    with a space; literal keeps them as separate lines. The distinction barely matters for a one-line
    purpose, but it costs nothing to keep."""
    lines, out, i = head.splitlines(), {}, 0
    n = len(lines)
    while i < n:
        m = _KEY.match(lines[i])
        if not m: i += 1; continue
        key, rest = m.group(1), m.group(2).strip()
        i += 1
        if rest[:1] in ('>', '|'):
            fold, cont = rest[0] == '>', []
            while i < n and (not lines[i].strip() or lines[i][:1] in (' ', '\t')):
                cont.append(lines[i].strip()); i += 1
            while cont and cont[-1] == '': cont.pop()          # chomp trailing blank lines
            out[key] = ' '.join(c for c in cont if c) if fold else '\n'.join(cont)
        else:
            out[key] = rest.strip('"\'')
    return out


def parse(text: str) -> dict:
    """{name, description, body} from a SKILL.md. The frontmatter is metadata about the skill, not
    part of the rules a worker follows, so it does not travel into the body."""
    m = _FM.match(str(text or ''))
    head, body = (m.group(1), m.group(2)) if m else ('', str(text or ''))
    found = _fm_fields(head)
    return {'name': found.get('name', ''), 'description': found.get('description', ''),
            'body': body.strip()}


def _plugin_of(root: Path) -> tuple:
    """(name, description) from .claude-plugin/plugin.json - what a folder of skills calls itself."""
    p = root / '.claude-plugin' / 'plugin.json'
    if not p.is_file(): return '', ''
    try: j = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError): return '', ''
    return str(j.get('name') or ''), str(j.get('description') or '')


def _entry(path: Path, plugin: str = '', plugin_desc: str = '', name: str = None) -> dict:
    """`name` overrides the frontmatter for folder-based discovery: a `skills/<name>/SKILL.md` glob
    means the directory IS the skill's identity (Claude Code's own convention), so it outranks
    whatever the frontmatter claims. A bare single-file read has no such folder to trust, and falls
    back to the frontmatter (then the enclosing directory, whatever that happens to be)."""
    text = path.read_text(encoding='utf-8', errors='replace')
    got = parse(text)
    return {**got, 'name': name or got['name'] or path.parent.name, 'path': str(path),
            'plugin': plugin, 'plugin_desc': plugin_desc, 'bytes': len(text)}


def read_path(p: str, only=None) -> list:
    """One entry for a SKILL.md, or one per skill for a plugin folder. `commands/` is not read: a
    command is a thing invoked by name, which an attached playbook already is.

    A single file must actually BE named SKILL.md. Accepting any readable path made the endpoint in
    front of this an arbitrary local-file read - point it at a key, a database or a config file and
    the contents come back as a proposed worker's body.

    `only` is the owner's pick out of `list_path`, and is filtered against what the folder actually
    holds for the same reason the link door filters its own: a path that arrives from outside is a
    request to look somewhere, not permission to."""
    root = Path(p)
    if root.is_file(): return [_entry(root)] if root.name == 'SKILL.md' else []
    if not root.is_dir(): return []
    pname, pdesc = _plugin_of(root)
    files = sorted(root.glob('skills/*/SKILL.md'))
    if only is not None: files = [f for f in files if str(f) in set(only)]
    if len(files) > PICK_MAX: raise ValueError(f'{len(files)} skills - choose at most {PICK_MAX} to bring in')
    return sorted((_entry(f, pname, pdesc, f.parent.name) for f in files), key=lambda e: e['name'])


def list_path(p: str) -> list:
    """WHAT IS IN a folder, without proposing any of it: [{name, path, plugin}], no bodies and no
    model calls - the local twin of `list_url`."""
    root = Path(p)
    if root.is_file():
        return [{'name': root.parent.name, 'path': str(root), 'plugin': ''}] if root.name == 'SKILL.md' else []
    if not root.is_dir(): return []
    pname = _plugin_of(root)[0]
    return sorted(({'name': f.parent.name, 'path': str(f), 'plugin': pname} for f in root.glob('skills/*/SKILL.md')),
                  key=lambda e: e['name'])


def found(home: Path = None) -> list:
    """Every skill already installed on this machine, for the picker.

    The plugin name comes from which of SKILL_GLOBS matched, not from counting path segments back
    from the end: '.claude/skills/*/SKILL.md' is a personal skill (no plugin), and in
    '.claude/plugins/cache/*/*/*/skills/*/SKILL.md' the plugin is the second '*' - the marketplace
    cache's own layout, not an assumption about how deep `home` itself is nested."""
    home = home or Path.home()
    out = [_entry(f, name=f.parent.name) for f in sorted(home.glob(SKILL_GLOBS[0]))]
    manifests = {}  # <version-dir> -> (plugin name, plugin desc); 14 skills often share one plugin dir
    for f in sorted(home.glob(SKILL_GLOBS[1])):
        rel = f.relative_to(home).parts  # .claude/plugins/cache/<mkt>/<plugin>/<ver>/skills/<name>/SKILL.md
        plugin = rel[4] if len(rel) > 4 else ''
        root = f.parents[2]  # .../<mkt>/<plugin>/<ver>, same shape read_path's root already reads
        if root not in manifests: manifests[root] = _plugin_of(root)
        pdesc = manifests[root][1]
        out.append(_entry(f, plugin, pdesc, name=f.parent.name))
    return out


# The link door. Three shapes are understood, all read-only and all over https:
#   a raw SKILL.md            https://raw.githubusercontent.com/<owner>/<repo>/<ref>/<path>/SKILL.md
#   a GitHub page of one      https://github.com/<owner>/<repo>/blob/<ref>/<path>/SKILL.md
#   a GitHub repo or folder   https://github.com/<owner>/<repo>[/tree/<ref>[/<path>]]  -> every SKILL.md under it
# and any other https URL only if it names a SKILL.md outright. Nothing else is fetched: a link is a
# stranger's text about to become a worker's instructions, so what it can point at is narrow and the
# body arrives untouched for the owner to read before any of it is written.
GITHUB_API = 'https://api.github.com'
RAW_HOST = 'raw.githubusercontent.com'
# How many skills one import BRINGS IN. Looking is not limited: a repository of 252 is a catalogue to
# choose from, and refusing to read it refused the whole repository over a number the owner had not
# been asked about yet (the owner, 2026-09-18: "it should not limit reading it, just say max to push
# in is 10, meaning you actually choose them"). A pick costs a fetch and a model call to convert, and
# ten rules documents is already more instruction than one company has jobs for - so the CHOOSING is
# what is capped, at the point where the owner is doing the choosing.
PICK_MAX = 10
# ...and the catalogue itself is one tree read. The only ceiling left is a list nobody could scan.
LIST_MAX = 500
_FETCH_HEADERS = {'User-Agent': 'taskuary-skill-import', 'Accept': 'application/vnd.github+json'}


def _http_get(url: str) -> str:
    import requests
    r = requests.get(url, headers=_FETCH_HEADERS, timeout=20)
    if r.status_code == 404: raise ValueError(f'nothing at {url}')
    if r.status_code == 403 and 'rate limit' in r.text.lower(): raise ValueError('GitHub is rate-limiting anonymous reads - try again in a while')
    r.raise_for_status()
    return r.text


def _skill_at(url: str, text: str, name: str, plugin: str = '') -> dict:
    got = parse(text)
    return {**got, 'name': name or got['name'], 'path': url, 'plugin': plugin, 'plugin_desc': '', 'bytes': len(text)}


def fetch_url(url: str, get=None, only=None) -> list:
    """Entries for every skill a link names - see the shapes above. `get` is the text fetcher, so a
    test can hand in a fake without the network. Raises ValueError with a plain reason for anything
    this does not read, which the endpoint shows as written.

    `only` is the catalogue's own answer coming back: the raw URLs the owner ticked in `list_url`.
    Whatever it says, the tree is re-read and the picks are FILTERED against it - an arbitrary URL
    handed to this parameter fetches nothing, because a link door that takes any address is not a
    link door at all."""
    from urllib.parse import urlsplit, unquote
    get = get or _http_get
    want = set(only or ())
    u = urlsplit(str(url or '').strip())
    if u.scheme != 'https' or not u.netloc: raise ValueError('a skill link starts with https://')
    parts = [unquote(p) for p in u.path.strip('/').split('/') if p]
    host = u.netloc.lower()
    if host == RAW_HOST:
        if not parts or parts[-1] != 'SKILL.md': raise ValueError('a raw link must name a SKILL.md')
        name = parts[-2] if len(parts) >= 5 else parts[1]                  # <owner>/<repo>/<ref>/.../<folder>/SKILL.md
        return [_skill_at(url, get(url), name, plugin=parts[1] if len(parts) > 1 else '')]
    if host in ('github.com', 'www.github.com'):
        if len(parts) < 2: raise ValueError('a GitHub link needs an owner and a repository')
        owner, repo = parts[0], parts[1].removesuffix('.git')
        kind, ref, sub = (parts[2], parts[3], parts[4:]) if len(parts) >= 4 and parts[2] in ('tree', 'blob') else ('', '', [])
        if kind == 'blob':
            if not sub or sub[-1] != 'SKILL.md': raise ValueError('a GitHub file link must point at a SKILL.md')
            raw = f'https://{RAW_HOST}/{owner}/{repo}/{ref}/{"/".join(sub)}'
            return [_skill_at(raw, get(raw), sub[-2] if len(sub) > 1 else repo, plugin=repo)]
        if not ref:
            ref = str(json.loads(get(f'{GITHUB_API}/repos/{owner}/{repo}')).get('default_branch') or 'main')
        tree = json.loads(get(f'{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1'))
        prefix = '/'.join(sub) + '/' if sub else ''
        paths = sorted(t['path'] for t in tree.get('tree', [])
                       if t.get('type') == 'blob' and t['path'].startswith(prefix) and t['path'].rsplit('/', 1)[-1] == 'SKILL.md')
        if not paths: raise ValueError(f'no SKILL.md under {url}')
        picks = [(f'https://{RAW_HOST}/{owner}/{repo}/{ref}/{p}', p) for p in paths]
        if want: picks = [(raw, p) for raw, p in picks if raw in want]
        if not picks: raise ValueError('none of those skills are under that link any more')
        # counted BEFORE anything is fetched: the cap is on what an import brings in, not a tripwire
        # somebody pays eleven downloads to trip
        if len(picks) > PICK_MAX: raise ValueError(f'{len(picks)} skills - choose at most {PICK_MAX} to bring in')
        return [_skill_at(raw, get(raw), p.rsplit('/', 2)[-2] if '/' in p else repo, plugin=repo) for raw, p in picks]
    if parts and parts[-1] == 'SKILL.md':
        return [_skill_at(url, get(url), parts[-2] if len(parts) > 1 else host)]
    raise ValueError('that link is not a SKILL.md, a GitHub file, or a GitHub repository or folder')


def list_url(url: str, get=None) -> list:
    """WHAT IS THERE, without reading any of it: [{name, path, plugin}] for every skill a link names.

    One tree read for a whole repository, no bodies and no model calls - which is the difference
    between showing somebody a catalogue and importing it. The `path` of each row is the raw URL
    `fetch_url(only=...)` takes back once the owner has ticked the ones they want.
    """
    from urllib.parse import urlsplit, unquote
    get = get or _http_get
    u = urlsplit(str(url or '').strip())
    if u.scheme != 'https' or not u.netloc: raise ValueError('a skill link starts with https://')
    parts = [unquote(p) for p in u.path.strip('/').split('/') if p]
    host = u.netloc.lower()
    if host in ('github.com', 'www.github.com') and len(parts) >= 2 and not (len(parts) >= 3 and parts[2] == 'blob'):
        owner, repo = parts[0], parts[1].removesuffix('.git')
        ref, sub = (parts[3], parts[4:]) if len(parts) >= 4 and parts[2] == 'tree' else ('', [])
        if not ref:
            ref = str(json.loads(get(f'{GITHUB_API}/repos/{owner}/{repo}')).get('default_branch') or 'main')
        tree = json.loads(get(f'{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1'))
        prefix = '/'.join(sub) + '/' if sub else ''
        paths = sorted(t['path'] for t in tree.get('tree', [])
                       if t.get('type') == 'blob' and t['path'].startswith(prefix) and t['path'].rsplit('/', 1)[-1] == 'SKILL.md')
        if not paths: raise ValueError(f'no SKILL.md under {url}')
        if len(paths) > LIST_MAX: raise ValueError(f'{len(paths)} skills there - point at a folder inside it')
        return [{'name': p.rsplit('/', 2)[-2] if '/' in p else repo,
                 'path': f'https://{RAW_HOST}/{owner}/{repo}/{ref}/{p}',
                 'plugin': p.split('/')[0] if '/' in p else repo} for p in paths]
    # a single file - raw, a GitHub blob, or any https SKILL.md: there is nothing to choose between,
    # so the listing is that one row and the wizard goes straight on to reading it
    return [{'name': n, 'path': p, 'plugin': g} for n, p, g in [_single(url, parts, host)]]


def _single(url: str, parts: list, host: str) -> tuple:
    """(name, raw url, plugin) for a link that names ONE SKILL.md, by the same rules `fetch_url`
    reads it with - so what the catalogue lists and what the fetch returns cannot disagree."""
    if host == RAW_HOST:
        if not parts or parts[-1] != 'SKILL.md': raise ValueError('a raw link must name a SKILL.md')
        return (parts[-2] if len(parts) >= 5 else parts[1], url, parts[1] if len(parts) > 1 else '')
    if host in ('github.com', 'www.github.com'):
        owner, repo = parts[0], parts[1].removesuffix('.git')
        sub = parts[4:] if len(parts) >= 4 else []
        if not sub or sub[-1] != 'SKILL.md': raise ValueError('a GitHub file link must point at a SKILL.md')
        return (sub[-2] if len(sub) > 1 else repo, f'https://{RAW_HOST}/{owner}/{repo}/{parts[3]}/{"/".join(sub)}', repo)
    if parts and parts[-1] == 'SKILL.md':
        return (parts[-2] if len(parts) > 1 else host, url, '')
    raise ValueError('that link is not a SKILL.md, a GitHub file, or a GitHub repository or folder')


# A `description` is written for a harness deciding whether to load a skill; a `purpose` is written
# for a roster of workers triage picks between. Same sentence, different reader - so a model rewrites
# it. It does NOT touch the body: that is the expertise being imported, and summarising it would
# throw away the thing the import is for.
CONVERT_SYSTEM = (
    'You are turning one skill document into a WORKER PROFILE for a small company\'s assistant. '
    'The profile is chosen by a router that sees one line per worker, so the purpose must say what '
    'kind of work this worker is for, in one sentence, in the company\'s own plain words.\n\n'
    'Answer ONLY with JSON: {"name": "<kebab-case, short>", "purpose": "<one sentence>", '
    '"kind": "<research|analysis|coordination|marketing|general>"}.\n\n'
    'Never answer "coding": a coding worker is chosen a different way and works a repository. '
    'Never invent a system, a credential or a permission - the profile is knowledge, not access.')

KINDS = ('research', 'analysis', 'coordination', 'marketing', 'general')


def convert(entry: dict, llm=None) -> dict:
    """{name, purpose, body, kind} for one skill. The body is passed through UNTOUCHED.

    With no model - or one that answers nonsense - the frontmatter stands on its own: a description
    is already a usable purpose, just written for a different reader. An import that works without a
    brain is one the owner can do on a fresh install."""
    from . import compose
    out = {'name': entry.get('name') or '', 'purpose': entry.get('description') or '',
           'body': entry.get('body') or '', 'kind': 'general'}
    if not llm: return out
    try:
        said = compose._json(llm(CONVERT_SYSTEM, json.dumps(
            {'name': entry.get('name'), 'description': entry.get('description'),
             'body': (entry.get('body') or '')[:4000]}), max_tokens=300)) or {}
    except Exception:
        return out
    if str(said.get('purpose') or '').strip(): out['purpose'] = said['purpose'].strip()
    if str(said.get('name') or '').strip(): out['name'] = said['name'].strip()
    kind = str(said.get('kind') or '').strip().lower()
    if kind in KINDS: out['kind'] = kind
    return out


class ProfileCollision(Exception):
    """Raised by `save` when a name lands on a profile, or on a document, it did not create. The
    shipped roles (researcher, analyst, coordinator, marketer, trader) and any hand-written profile
    all slugify into ordinary names, and a wizard handing out arbitrary names WILL land on one
    eventually - this is the difference between updating your own import and quietly destroying
    somebody's worker.

    `doc` is set when the DOCUMENT is what was in the way. That is the worse half: soul, triage,
    agent, style, counsel, digest and learned have no agent row at all, so a name check against
    profiles waved them straight through - a skill called `triage` replaced TRIAGE.md, silently, and
    the doc table is one row per name with no history to restore from."""
    def __init__(self, name: str, kind: str, doc: str = ''):
        self.name, self.kind, self.doc = name, kind, doc or ''
        super().__init__(f"'{name}' would rewrite {doc.upper()}.md, a document this import did not write"
                         ' - not overwriting it' if doc else
                         f"'{name}' is an existing profile this import did not make - not overwriting it")


def _free_to_write(store, doc: str) -> bool:
    """Is `doc` this importer's to write? Only if it wrote it, or if there is no document and no
    shipped template of that name waiting to flow back in (profile_template reads the templates
    folder, so a name with one there IS an operator document even before it is first saved)."""
    who = store.doc_owner(doc)
    if who is not None: return who == 'import'
    return not (Path(__file__).parent / 'templates' / f'{doc}.md').is_file()


def save(store, got: dict, enabled: bool = False, replace: bool = False) -> str:
    """Write one converted skill as an ORDINARY profile - an agent row and the doc row of the same
    name, the same road Docs → Add profile takes. Nothing here is special-cased downstream, which is
    the measure of whether this was done right.

    `triage_enabled` defaults to OFF: an imported worker reaches the router when the owner says so,
    not because a file was read.

    A name that already belongs to a profile THIS FUNCTION did not write (no `imported` flag in its
    config) is refused unless `replace=True` - re-importing your own import is still one update in
    place, but a bare name collision is not consent to overwrite a hand-made worker's kind and
    rules document. The DOCUMENT is checked the same way and separately, because the operator
    documents have no agent row to collide with.

    Nothing is written before both checks pass: a refusal must not leave an agent row behind."""
    from . import agents as hub_agents
    name = re.sub(r'[^a-z0-9-]+', '-', str(got.get('name') or '').strip().lower()).strip('-')
    if not name: raise ValueError('a profile needs a name')
    kind = got.get('kind') if got.get('kind') in KINDS else 'general'
    row = store.get_agent(name)
    try: prof = json.loads((row or {}).get('Config') or '{}')
    except ValueError: prof = {}
    if row and not prof.get('imported') and not replace: raise ProfileCollision(name, row.get('Kind') or kind)
    prof.update({'kind': kind, 'purpose': str(got.get('purpose') or '').strip(),
                 'triage_enabled': bool(enabled), 'imported': True})
    doc = hub_agents.profile_document(store, name, prof)
    if not replace and not _free_to_write(store, doc): raise ProfileCollision(name, (row or {}).get('Kind') or kind, doc)
    store.upsert_agent(name, kind, (row or {}).get('Runner') or 'cli', json.dumps(prof))
    store.save_doc(doc, str(got.get('body') or '').strip() + '\n', 'import')
    return name

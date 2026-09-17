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


def read_path(p: str) -> list:
    """One entry for a SKILL.md, or one per skill for a plugin folder. `commands/` is not read: a
    command is a thing invoked by name, which an attached playbook already is."""
    root = Path(p)
    if root.is_file(): return [_entry(root)]
    if not root.is_dir(): return []
    pname, pdesc = _plugin_of(root)
    return sorted((_entry(f, pname, pdesc, f.parent.name) for f in root.glob('skills/*/SKILL.md')),
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
    """Raised by `save` when a name lands on a profile it did not create. The shipped roles
    (researcher, analyst, coordinator, marketer, trader) and any hand-written profile all slugify
    into ordinary names, and a wizard handing out arbitrary names WILL land on one eventually - this
    is the difference between updating your own import and quietly destroying somebody's worker."""
    def __init__(self, name: str, kind: str):
        self.name, self.kind = name, kind
        super().__init__(f"'{name}' is an existing profile this import did not make - not overwriting it")


def save(store, got: dict, enabled: bool = False, replace: bool = False) -> str:
    """Write one converted skill as an ORDINARY profile - an agent row and the doc row of the same
    name, the same road Docs → Add profile takes. Nothing here is special-cased downstream, which is
    the measure of whether this was done right.

    `triage_enabled` defaults to OFF: an imported worker reaches the router when the owner says so,
    not because a file was read.

    A name that already belongs to a profile THIS FUNCTION did not write (no `imported` flag in its
    config) is refused unless `replace=True` - re-importing your own import is still one update in
    place, but a bare name collision is not consent to overwrite a hand-made worker's kind and
    rules document."""
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
    store.upsert_agent(name, kind, (row or {}).get('Runner') or 'cli', json.dumps(prof))
    doc = hub_agents.profile_document(store, name, prof)
    store.save_doc(doc, str(got.get('body') or '').strip() + '\n', 'import')
    return name

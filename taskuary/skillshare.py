"""A skill out to someone else, and one in from them (the owner, 2026-11-26: "share with someone else").

OUT is the skill's folder as one zip - `<name>/SKILL.md` and whatever else it keeps - the shape Claude Code and other agents unpack
into their own skills folder as it is.

IN is a zip, a folder or a lone SKILL.md, and it is TEXT, never a permission:
- nothing in it is run, here or at any later point by Taskuary: a script in the folder is stored as a file like any other;
- no frontmatter beyond `name`, `description` and `metadata.uses` is read by anything (skills._front) - `allowed-tools` and the like
  are named back to him as ignored, and no gate reads a skill at all (scopes.ACTIONS, contract 9);
- it is shown to him whole first (read_in), and saved only by his press on exactly what was shown (`shown`, its hash);
- it never lands on a skill he has: a name already taken comes in under the next free one (skills.free);
- a path that leaves the folder, a link, a file or a pack over the limits is refused before anything is written.
What it saves is marked `imported` (skills.set_origin), so every list an agent reads says whose words they are.
"""
import hashlib, io, re, stat, zipfile
from pathlib import PurePosixPath
from . import skills

MAX_FILE, MAX_TOTAL, MAX_FILES = 1_000_000, 5_000_000, 60
# frontmatter another agent's library gives meaning to. Here it is words: named on the card so he knows it does nothing
PERMISSION_KEYS = ('allowed-tools', 'allowed_tools', 'tools', 'permissions', 'permission-mode', 'model', 'hooks', 'disable-model-invocation')


class Refused(ValueError):
    "An import that is not taken, with why in his words."


def export(slug: str) -> tuple:
    "(file name, the zip's bytes) of one skill: its folder, links left out. LookupError when there is none."
    text = skills.read(slug)
    if text is None: raise LookupError(f'no skill {slug!r}')
    name, d = skills.key(slug), skills.path_of(slug).parent
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{name}/{skills.FILE}', text)
        for rel in skills.files_of(name):
            p = d / rel
            if not p.is_symlink(): z.write(p, f'{name}/{rel}')
    return f'{name}.zip', buf.getvalue()


def _safe(name: str) -> str:
    "A file's path inside the skill, or Refused: never absolute, never up and out, never a drive or a device."
    raw = str(name or '').replace('\\', '/')
    parts = PurePosixPath(raw).parts
    if (not parts or raw.startswith('/') or re.match(r'^[A-Za-z]:', raw) or '\x00' in raw
            or any(p in ('..', '.') or p.endswith((' ', '.')) or re.search(r'[<>:"|?*]', p) or re.fullmatch(r'(?i)(con|prn|aux|nul|com\d|lpt\d)(\..*)?', p)
                   for p in parts)):
        raise Refused(f'{name!r} is a path outside the skill\'s own folder - nothing was imported')
    return '/'.join(parts)


def _unzip(data: bytes) -> dict:
    try: z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile: raise Refused('that file is not a zip Taskuary can open')
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES: raise Refused(f'that zip holds {len(infos)} files - a skill is at most {MAX_FILES}')
    out, total = {}, 0
    for i in infos:
        if stat.S_ISLNK(i.external_attr >> 16): raise Refused(f'{i.filename!r} is a link, not a file - nothing was imported')
        name = _safe(i.filename)
        # the size the zip CLAIMS is not trusted: read at most one byte past the limit, and count what really came out
        if i.file_size > MAX_FILE: raise Refused(f'{name} is over {MAX_FILE // 1000:,} KB - nothing was imported')
        with z.open(i) as f: got = f.read(MAX_FILE + 1)
        total += len(got)
        if len(got) > MAX_FILE or total > MAX_TOTAL: raise Refused(f'that zip unpacks to more than a skill may hold ({MAX_TOTAL // 1_000_000} MB) - nothing was imported')
        out[name] = got
    return out


def _gather(files: list) -> dict:
    "{path inside the skill: bytes} of what he picked - one zip unpacked, else the files as their paths name them - by every limit."
    files = [(str(n or ''), b) for n, b in files or [] if b is not None]
    if not files: raise Refused('nothing was picked to import')
    if len(files) == 1 and (files[0][0].lower().endswith('.zip') or files[0][1][:4] == b'PK\x03\x04'): got = _unzip(files[0][1])
    else:
        if len(files) > MAX_FILES: raise Refused(f'that folder holds {len(files)} files - a skill is at most {MAX_FILES}')
        if any(len(b) > MAX_FILE for _, b in files) or sum(len(b) for _, b in files) > MAX_TOTAL:
            raise Refused(f'that is more than a skill may hold ({MAX_FILE // 1000:,} KB a file, {MAX_TOTAL // 1_000_000} MB in all) - nothing was imported')
        got = {_safe(n): b for n, b in files}
    # ONE skill: the SKILL.md nearest the top, and only what sits in its folder. A lone markdown file is the skill itself.
    mds = sorted((k for k in got if PurePosixPath(k).name.lower() == skills.FILE.lower()), key=lambda k: (k.count('/'), k))
    if not mds and len(got) == 1 and next(iter(got)).lower().endswith(('.md', '.markdown', '.txt')): return {skills.FILE: next(iter(got.values()))}
    if not mds: raise Refused(f'there is no {skills.FILE} in that - a skill is a folder with one')
    root = mds[0][:-len(skills.FILE)]
    return {(skills.FILE if k == mds[0] else k[len(root):]): v for k, v in got.items() if k.startswith(root)}


def read_in(files: list, name: str = '') -> dict:
    """What an import WOULD save, for his eyes: {'slug', 'title', 'description', 'text', 'files', 'ignored', 'shown'} - or Refused.
    `files` is [(name, bytes)]: one zip, one SKILL.md, or a folder's files by their paths. Nothing is written and nothing is run."""
    got = _gather(files)
    try: text = got[skills.FILE].decode('utf-8-sig')
    except UnicodeDecodeError: raise Refused(f'its {skills.FILE} is not text')
    try: pb = skills.check(text)
    except ValueError as e: raise Refused(str(e))
    m = skills._FRONT.match(text)
    said = [k for k in PERMISSION_KEYS if m and re.search(rf'(?mi)^{re.escape(k)}\s*:', m.group(1))]
    slug = skills.free(pb['name'] or name or pb['title'])
    rest = {k: v for k, v in got.items() if k != skills.FILE}
    text = skills.named(text, slug)
    return {'slug': slug, 'title': pb['title'], 'description': pb['description'], 'text': text,
            'files': [{'name': k, 'size': len(v)} for k, v in sorted(rest.items())],
            'ignored': said, 'renamed': slug != skills.slugify(pb['name'] or name or pb['title']),
            'shown': hashlib.sha256(text.encode('utf-8') + b''.join(k.encode('utf-8') + b'\0' + v for k, v in sorted(rest.items()))).hexdigest(),
            '_rest': rest}


def save(files: list, shown: str, name: str = '') -> dict:
    """His press: what read_in showed him, saved as a new skill - and only that (`shown` is its hash: a pick that reads differently now is
    refused, never saved unseen). {'slug'}."""
    got = read_in(files, name)
    if not shown or got['shown'] != shown: raise Refused('this is not what was shown - look at it again, then save')
    slug = skills.write(got['slug'], got['text'])
    d = skills.path_of(slug).parent
    for rel, data in got['_rest'].items():
        p = d.joinpath(*PurePosixPath(rel).parts)
        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)          # stored. Never made executable, never run.
    skills.set_origin(slug, 'imported')
    return {'slug': slug}

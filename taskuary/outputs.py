"""The files an agent makes FOR the owner on a task - a spreadsheet, a PDF, a chart - and how the task page reaches them.

A chat's CLI works in Taskuary's scratch folder (llm._build_llm), and nothing told it where a finished file should go. A Codex
researcher saved a workbook under scratch/outputs/TQ-0017/ by its own habit, cited it with its own `:codex-file-citation{...}`
marker - printed raw in the chat - and, asked to send it, made up http://127.0.0.1:7787/outputs/TQ-0017/... : a route this server
never had. Session artifacts (session_artifacts.py) are only files Taskuary itself copied in under ~/.taskuary/artifacts, so a
file the agent wrote was on disk and unreachable from the page.

Now the folder is named: <home>/scratch/outputs/TQ-nnnn/ for task nnnn - the very one the agent picked - it is said in the brief
(brief), and GET /api/task-outputs/<tid>/<file> serves a file in THAT task's folder and nothing else (resolve)."""
import json, mimetypes, re, shutil
from functools import lru_cache
from datetime import datetime
from pathlib import Path

from . import config
from .store import task_ref

MAX_FILES, MAX_DEPTH = 200, 4
ROWS, COLS, CELL, SHEETS = 200, 40, 300, 30          # what a preview carries: enough to recognise the sheet, never the whole book
TYPES = {'.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsm': 'application/vnd.ms-excel.sheet.macroEnabled.12',
         '.csv': 'text/csv', '.tsv': 'text/tab-separated-values', '.md': 'text/markdown', '.txt': 'text/plain', '.json': 'application/json',
         '.log': 'text/plain', '.pdf': 'application/pdf', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
         '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.html': 'text/html', '.htm': 'text/html',
         '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
         '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
         '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
         '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4', '.ogg': 'audio/ogg'}
# how the page previews each kind; anything not here is Download only. A video or a sound PLAYS in place (Gabi, 2026-11-08: "we need to
# be able to play/interact/edit things taskuary generates right on screen" - an MP4 opened as its raw bytes)
PREVIEW = {'.xlsx': 'sheet', '.xlsm': 'sheet', '.csv': 'table', '.pdf': 'pdf', '.png': 'picture', '.jpg': 'picture', '.jpeg': 'picture',
           '.gif': 'picture', '.webp': 'picture', '.md': 'text', '.txt': 'text', '.json': 'text', '.log': 'text', '.tsv': 'text',
           '.svg': 'page', '.html': 'page', '.htm': 'page', '.docx': 'document',
           '.mp4': 'video', '.m4v': 'video', '.webm': 'video', '.mov': 'video', '.mp3': 'audio', '.wav': 'audio', '.m4a': 'audio', '.ogg': 'audio'}


def folder(tid: int) -> Path: return config.home() / 'scratch' / 'outputs' / task_ref(tid)
def content_type(name: str) -> str: return TYPES.get(Path(name).suffix.lower()) or mimetypes.guess_type(name)[0] or 'application/octet-stream'


def can_sheet() -> bool:
    "openpyxl ships in the desktop exe (deps.BUNDLE); a plain pip install may not have it - then a workbook is Download only."
    try: import openpyxl  # noqa: F401
    except ImportError: return False
    return True


def _base_ok(base: Path) -> bool:
    "The folder itself is ours too: a scratch/outputs that is a link to somewhere else serves nothing."
    return not any(q.is_symlink() for q in (base.parent, base)) and base.resolve().is_relative_to((config.home() / 'scratch').resolve())


_DRIVE = re.compile(r'^[A-Za-z]:|^[\\/]{2}')

# A FILE THE OWNER ATTACHES IN THE CHAT IS THE TASK'S (the owner, 2026-11-09): a PDF dropped in the box stayed under attachments/prompt/, and
# sign_form and the propose tools - which take a file in the task folder only - refused it, so the agent had to copy it over first
_STAMPED = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{6}-')       # the upload's own prefix (server.prompt_file), not the owner's name for it
# ...AND ONLY WHAT HE UPLOADED IS HIS FILE (the attach stress round, 2026-11-18): any other path a request names - Taskuary's own config with
# its tokens - went to the agent as "read these files", and to an API brain as a picture; one already in the task's folder is his already
def take_in(tid: int, paths) -> list:
    "`paths` as files in task `tid`'s folder: each one this server saved under attachments/ copied in under its own name; one there already kept; no other."
    root, out = (config.home() / 'attachments').resolve(), []
    for raw in paths or []:
        try:
            p = Path(str(raw)).resolve()
            if not p.is_file(): continue
            if p.parent == folder(tid).resolve(): out.append(str(p)); continue
            if not p.is_relative_to(root): continue
            d = folder(tid); d.mkdir(parents=True, exist_ok=True)
            stem, ext = Path(_STAMPED.sub('', p.name) or p.name).stem, p.suffix
            q = next(d / f'{stem}{f"-{i}" if i else ""}{ext}' for i in range(1000) if not (d / f'{stem}{f"-{i}" if i else ""}{ext}').exists()
                     or (d / f'{stem}{f"-{i}" if i else ""}{ext}').read_bytes() == p.read_bytes())
            if not q.exists(): shutil.copyfile(p, q)
            out.append(str(q))
        except (OSError, ValueError, StopIteration): continue
    return list(dict.fromkeys(out))


def take_in_text(tid: int, text: str) -> str:
    "`text` with every file this server saved under attachments/ that it names copied into task `tid`'s folder and named there (take_in)."
    if not text: return text
    root = str((config.home() / 'attachments').resolve())
    return re.sub(re.escape(root) + r'[^\r\n]*', lambda m: (take_in(tid, [m.group(0)]) or [m.group(0)])[0], str(text), flags=re.I)


def take_in_summary(store, tid: int, actor: str) -> str:
    "Task `tid`'s Summary with every file it names that this server saved taken into its folder (take_in_text) - kept, and returned."
    s = str((store.get_task(tid) or {}).get('Summary') or '')
    if (s2 := take_in_text(tid, s)) != s: store.update_task(tid, {'Summary': s2}, actor)
    return s2


def resolve(tid: int, rel: str, base: Path = None):
    """The file `rel` names inside task `tid`'s outputs folder (or `base`, a turn's kept copies - turn_folder), or None. A name only: never
    absolute, never a drive or a share, no `..` or empty step, no `:` (an NTFS stream), no link anywhere on the way - and after resolving,
    still under the folder."""
    rel = str(rel or '')
    if not rel or '\x00' in rel or _DRIVE.match(rel) or rel[0] in '/\\': return None
    parts = rel.replace('\\', '/').split('/')
    if any(p in ('', '.', '..') or ':' in p for p in parts): return None
    base = base or folder(tid)
    try:
        if not _base_ok(base): return None
        p, cur = base.joinpath(*parts), base
        for part in parts:
            cur = cur / part
            if cur.is_symlink(): return None
        p = p.resolve()
        return p if p.is_relative_to(base.resolve()) and p.is_file() else None
    except (OSError, ValueError):
        return None



def named(tid: int, raw: str):
    "A file an agent names by its name in the folder or by its full path - resolve's rules either way, so a path out of the folder is None."
    raw = str(raw or '').strip().strip('"\'')
    if raw and (Path(raw).is_absolute() or _DRIVE.match(raw)):
        try: raw = Path(raw).resolve().relative_to(folder(tid).resolve()).as_posix()
        except (OSError, ValueError): return None
    return resolve(tid, raw)

def rel(tid: int, p: Path) -> str:
    "`p`'s name in the folder. Both sides resolved: a home given by its 8.3 short form (C:/Users/ABCDEF~1) resolves to the long one."
    return Path(p).resolve().relative_to(folder(tid).resolve()).as_posix()

# WHAT IT MADE IS READ WHERE IT IS (the owner, 2026-11-15: he asked for a query to review, the agent saved it as a file, and the chat held only
# "it is ready for you to review"): a file of a kind with no viewer of its own - a query, a script, a config - that is plain text reads as text.
# By its bytes, never its name: no list of extensions decides what can be read
# A SMALL TEXT FILE GOES INTO THE MESSAGE OF AN AI THAT CANNOT OPEN IT (design round 3, 2026-11-18): a two-line .py on his line reached an AI
# card as its path alone, and its agent said "I could not open the attached totals.py from here". Whole, up to TEXT_EACH, all of them up to
# TEXT_ALL; a file that is no text (reads_as_text) or too long is left to its path, as before
TEXT_EACH, TEXT_ALL = 20_000, 60_000
def texts(paths) -> str:
    "The block of the small text files among `paths`, each whole under its name - '' where none is."
    out, room = [], TEXT_ALL
    for raw in dict.fromkeys(map(str, paths or [])):
        p = Path(raw)
        try:
            if not p.is_file() or p.stat().st_size > min(TEXT_EACH, room) or not reads_as_text(p): continue
            body = p.read_text(encoding='utf-8', errors='replace')
        except OSError: continue
        out.append(f'--- {_STAMPED.sub("", p.name) or p.name} ({p}) ---\n{body.rstrip()}'); room -= len(body)
    return ('THE TEXT OF THE FILES ABOVE, whole:\n' + '\n'.join(out)) if out else ''


# ...AND WHAT AN AI WITH NO HANDS WRITES OUT AS A FILE IS ONE (capabilities.HANDS 'none'): asked for a spreadsheet, a card that takes no tools
# answered with a CSV in its words and "no spreadsheet file anywhere". A fenced block whose first line names its file - ```csv file=quotes.csv -
# is saved to the task's folder as the file a CLI would have written there (a .xlsx, .docx, .pdf or .pptx made real, officefiles), and named in its place
_WRITTEN = re.compile(r'```[\w+.-]*[ \t]+file=([^\s`]+)[^\n]*\n(.*?)\n?```', re.S)
def keep_written(tid: int, text: str) -> tuple:
    "(`text` with each named fenced block saved to task `tid`'s folder and said as its name, the paths saved)."
    from . import officefiles
    saved = []
    def save(m):
        name = re.sub(r'[^\w .()-]', '_', Path(m.group(1)).name).strip(' .') or 'file.txt'
        d = folder(tid); d.mkdir(parents=True, exist_ok=True)
        p = d / name
        try:
            if officefiles.is_made(p): officefiles.write(p, m.group(2))
            else: p.write_text(m.group(2) + '\n', encoding='utf-8')
        except (OSError, ValueError): return m.group(0)
        saved.append(str(p)); return f'**{name}** (in this task\'s files)'
    return _WRITTEN.sub(save, str(text or '')), saved


def reads_as_text(p: Path) -> bool:
    try: st = p.stat()
    except OSError: return False
    return _reads_as_text(str(p), st.st_size, st.st_mtime_ns)

@lru_cache(maxsize=2048)
def _reads_as_text(p: str, size: int, mtime: int) -> bool:
    "...once per file as it stands (its size and stamp in the key): a list a page polls never reads the same head twice."
    try:
        with open(p, 'rb') as f: head = f.read(4096)
    except OSError: return False
    if not head or b'\0' in head: return False
    try: head.decode('utf-8')
    except UnicodeDecodeError as e: return e.start >= len(head) - 3          # a character cut by the read, not bytes that are no text
    return True


# ONE ROAD TO A PREVIEW (the owner, 2026-11-16: "it should be the same code both in the agent and on the email"): a file an agent made and a
# file that came on a mail are told how they preview here, and read for it below - `name` where the file on disk carries a stamp, not its name
def preview_of(p: Path, name: str = ''):
    "How the page previews `p` - by its kind, else plain text by its bytes; None is Download only (a workbook too, on an install with no openpyxl)."
    how = PREVIEW.get(Path(name or p.name).suffix.lower()) or ('text' if reads_as_text(p) else None)
    return None if how == 'sheet' and not can_sheet() else how


# A PICTURE DRAWS AT ITS OWN SHAPE (the owner, 2026-11-18: "images should be able to render however the agent wants it or make sense to
# show"): the page reserves its real width and height before it loads, so nothing jumps - read here off the file's header, no imaging library
def pixels(p) -> list | None:
    "[width, height] of a PNG, GIF, JPEG, WebP or BMP picture, read off its header - None for anything else or a header it cannot read."
    import struct
    try:
        with open(p, 'rb') as f: b = f.read(64 * 1024)
        if b[:8] == b'\x89PNG\r\n\x1a\n': w, h = struct.unpack('>II', b[16:24])
        elif b[:6] in (b'GIF87a', b'GIF89a'): w, h = struct.unpack('<HH', b[6:10])
        elif b[:2] == b'BM': w, h = struct.unpack('<ii', b[18:26]); h = abs(h)
        elif b[:4] == b'RIFF' and b[8:12] == b'WEBP':
            k = b[12:16]
            if k == b'VP8X': w, h = 1 + int.from_bytes(b[24:27], 'little'), 1 + int.from_bytes(b[27:30], 'little')
            elif k == b'VP8L': v = int.from_bytes(b[21:25], 'little'); w, h = 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF)
            else: w, h = (x & 0x3FFF for x in struct.unpack('<HH', b[26:30]))
        elif b[:2] == b'\xff\xd8':
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF: i += 1; continue
                m, n = b[i + 1], int.from_bytes(b[i + 2:i + 4], 'big')
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC): h, w = struct.unpack('>HH', b[i + 5:i + 9]); break
                i += 2 + n
            else: return None
        else: return None
        return [int(w), int(h)] if w > 0 and h > 0 else None
    except (OSError, struct.error, ValueError): return None


def row(tid: int, p: Path, rel: str) -> dict:
    "One file as the page draws it - the same shape as a shown page (page_row), so one list draws both."
    from urllib.parse import quote
    ext, sheet, kind = p.suffix.lower(), preview_of(p), content_type(p.name)
    st = p.stat()
    return {'id': f'output:{rel}', 'name': p.name, 'path': rel, 'kind': 'output', 'content_type': kind,
            'size': st.st_size, 'at': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S'), 'preview': sheet, 'url': f'/api/task-outputs/{int(tid)}/{quote(rel)}',
            **({'dims': d} if kind.startswith('image/') and (d := pixels(p)) else {}),
            **({'note': 'No preview on this install - Download opens it in your spreadsheet app.'} if PREVIEW.get(ext) == 'sheet' and not sheet else {})}


# EACH TURN KEEPS THE FILE AS IT MADE IT (the owner, 2026-11-07: "same file with revisions"): an agent improves one file in place (ONE_FILE),
# so a turn that named it drew the NEWEST version - turn 1's words about three tools over the four-tool table a later turn wrote. The turn that
# writes a file keeps its version: a copy when it is small, else only its name and stamp, read as "changed later" once a newer turn writes it.
# The newest turn and the file itself are the latest; the copies live beside the outputs folder, never in it (listing, deliverables)
TURN_COPY_MAX = 5_000_000
def turns_folder(tid: int) -> Path: return config.home() / 'scratch' / 'output-turns' / task_ref(tid)
def turn_folder(tid: int, turn: int) -> Path: return turns_folder(tid) / str(int(turn))


def _kept_copy(tid: int, path: str, made: list):
    "The newest copy an earlier turn kept of `path`, from turns_made's list - None where none was kept."
    turn = next((t for t, ks in reversed(made) for k in ks if k['path'] == path and k.get('kept')), None)
    return resolve(tid, path, turn_folder(tid, turn)) if turn is not None else None


def _same(a, b) -> bool:
    import filecmp
    try: return bool(a and b) and filecmp.cmp(a, b, shallow=False)
    except OSError: return False


def keep_turn(tid: int, turn: int, since: float) -> list:
    """The files turn `turn` (its answer's CommentId) wrote - changed at or after `since`, its start - kept as it left them: [{path, size, mtime,
    kept}]. A FILE WRITTEN BACK AS IT WAS IS NO CHANGE (the walk, 2026-11-18: an agent saved its posts file again each turn, word for word, and
    the chat drew the whole file under every answer): its turn stays the one that last changed what it says."""
    got, made = [], [(t, ks) for t, ks in turns_made(tid) if t != int(turn)]
    for r in listing(tid):
        p = resolve(tid, r['path'])
        if not p or (st := p.stat()).st_mtime < since or _same(_kept_copy(tid, r['path'], made), p): continue
        kept = st.st_size <= TURN_COPY_MAX
        if kept:
            (dest := turn_folder(tid, turn).joinpath(*r['path'].split('/'))).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        got.append({'path': r['path'], 'size': st.st_size, 'mtime': st.st_mtime, 'kept': kept})
    if got:
        turns_folder(tid).mkdir(parents=True, exist_ok=True)
        (turns_folder(tid) / f'{int(turn)}.json').write_text(json.dumps(got), encoding='utf-8')
    return got


# A FILE A CARD CARRIES IS DRAWN ON THAT CARD ONLY (the owner, 2026-11-10: "it should have drafted email not show me the file and the privew of
# the file. don't need preview need the email acion card"): the file the agent attached to its reply stood under its answer as a preview card
# of its own, read there as the thing it made. `show` still draws what the agent chose to show (agenttools.show_files) - never a card's file
def on_cards(store, tid: int) -> set:
    "The names of the files a draft or card of task `tid` carries (its delivery envelope's attachments)."
    out = set()
    for r in store._rows("SELECT Deliver FROM review WHERE TaskId=? AND IFNULL(Deliver,'')<>''", (int(tid),)):
        try: d = json.loads(r['Deliver']) or {}
        except (TypeError, ValueError): continue
        out |= {str(a['name']) for a in (d.get('attachments') or []) if isinstance(a, dict) and a.get('name')} if isinstance(d, dict) else set()
    return out


# ...NOR A FILE HE SENT (the attach stress round, 2026-11-18): what he attaches is copied in here (take_in), and his picture stood under the answer
# of the turn at work when he sent it, as the thing it made - until an agent writes it again, it is his
def sent(store, tid: int) -> set:
    "The files of task `tid`'s folder that a line of his sent, as he sent them: {path in the folder}. One written since is the agent's."
    from . import general
    from .conversation import ep
    base, out = folder(tid).resolve(), set()
    for c in store.list_comments(int(tid), internal=True):
        if c.get('ActorType') not in (general.WAITING_TYPE, general.USER_TYPE) or general.is_brief(c): continue
        for f in general.his_line(c)['files']:
            try:
                p = Path(f).resolve()
                if p.is_relative_to(base) and p.is_file() and p.stat().st_mtime <= ep(c['CreatedAt']) + 2: out.add(p.relative_to(base).as_posix())
            except (OSError, ValueError): continue
    return out


def turns_made(tid: int) -> list:
    "[(turn, [what keep_turn kept])], oldest turn first - [] for a task none kept."
    base, out = turns_folder(tid), []
    try: turns = sorted(int(f.stem) for f in base.glob('*.json') if f.stem.isdigit()) if base.is_dir() else []
    except OSError: return []
    for turn in turns:
        try: out.append((turn, json.loads((base / f'{turn}.json').read_text(encoding='utf-8'))))
        except (OSError, ValueError): continue
    return out


def made_by(tid: int) -> dict:
    "Each file's newest turn that wrote it: {path: 'comment-<id>'} - the turn the file as it is now belongs to."
    return {k['path']: f'comment-{turn}' for turn, made in turns_made(tid) for k in made}


def turn_versions(tid: int) -> list:
    """Each turn's own version of a file a LATER turn changed, as `row` draws it, `turn` its answer ('comment-<id>'): its copy (`url` with
    ?turn=), else - too big to copy - the file as it is now, marked `later`. A file no turn changed since is its turn's version: no row."""
    from urllib.parse import quote
    made_ = turns_made(tid)
    if not made_: return []
    now, out = {r['path']: r for r in listing(tid)}, []
    for turn, made in made_:
        for k in made:
            cur, p = now.get(k['path']), resolve(tid, k['path'])
            c = resolve(tid, k['path'], turn_folder(tid, turn)) if k.get('kept') else None
            # ...nor one written back since as it was (keep_turn): the file as it is now IS this turn's
            if cur and p and ((p.stat().st_mtime, p.stat().st_size) == (k['mtime'], k['size']) or _same(c, p)): continue
            mine = {'id': f"output:{k['path']}@{turn}", 'turn': f'comment-{turn}', 'after': f'comment-{turn}'}
            if c:
                out.append({**row(tid, c, k['path']), **mine, 'url': f"/api/task-outputs/{int(tid)}/{quote(k['path'])}?turn={turn}"})
            elif cur: out.append({**cur, **mine, 'later': True, 'note': 'Changed later - this opens its newest version.'})
    return out


def his(store, tid: int) -> set:
    """The files in task `tid`'s folder the owner attached, as he attached them: what a line of his sent (sent), and what the task's own
    words name (New's ask, general.split_files) - one written since is the agent's."""
    from . import general
    from .conversation import ep
    t, out = store.get_task(tid) or {}, sent(store, tid)
    for f in general.split_files(t.get('Summary'))['files']:
        try:
            q = folder(tid) / rel(tid, Path(f))
            if q.is_file() and q.stat().st_mtime <= ep(t.get('CreatedAt')) + 2: out.add(rel(tid, Path(f)))
        except (OSError, ValueError): continue
    return out


def made(store, tid: int) -> list:
    "listing(tid) without what the owner attached (his) - unless a turn wrote it since (made_by): the files the work made."
    mine, wrote = his(store, tid), made_by(tid)
    return [r for r in listing(tid) if r['path'] not in mine or r['path'] in wrote]


def listing(tid: int) -> list:
    "Every file in the task's outputs folder, newest first. Lock files and hidden files are not outputs; links are never followed."
    base = folder(tid)
    try:
        if not base.is_dir() or not _base_ok(base): return []
    except (OSError, ValueError): return []
    out, stack = [], [(base, 0)]
    while stack and len(out) < MAX_FILES:
        d, depth = stack.pop()
        try: kids = sorted(d.iterdir())
        except OSError: continue
        for k in kids:
            if k.name.startswith(('.', '~$')) or k.is_symlink(): continue
            if k.is_dir() and depth < MAX_DEPTH: stack.append((k, depth + 1))
            elif k.is_file():
                rel = k.relative_to(base).as_posix()
                if resolve(tid, rel): out.append((k.stat().st_mtime, row(tid, k, rel)))
    return [r for _, r in sorted(out, key=lambda x: -x[0])][:MAX_FILES]


# ONE OF EACH THING IT MADE (the owner, 2026-10-28: "it looks like it created a million attachments. Agents should not create lists of
# lists of attachments unless specifically asked"). A workbook saved as v1..v9 listed nine rows, with the helper script and its log
# between them. A FAMILY is one name with its version marks taken off (v2, _final, (1), a timestamp); only its newest is the deliverable,
# the rest are its earlier versions, kept and reachable behind it.
# ...AND NOTHING AN AGENT MADE IS HIDDEN (the owner, 2026-11-15, of a query saved as a file and folded away as the agent's own scratch: "this has
# nothing to do with sql, anything an agent creates should not be hidden of course"): no list of extensions, folder names or file names
# says what he may see - a helper script stands in the list with the workbook it built. taskOutputs.deliverables is the same rule for
# the page: keep the two alike.
_VER = re.compile(r'(?:[ _.-]+(?:v|ver|version|rev)[ _.-]?\d+|[ _.-]+(?:final|draft|copy|old|new|latest|updated|edited|revised)'
                  r'|[ _.-]*\(\d+\)|[ _.-]+\d{8}(?:[ _T-]?\d{4,6})?|[ _.-]+\d{4}-\d\d-\d\d(?:[ _T-]?\d\d[-.]?\d\d(?:[-.]?\d\d)?)?)+$', re.I)


def family(name: str) -> str:
    "A file's name without its version marks: 'Vendor pricing v9.xlsx', 'vendor pricing (2).xlsx' and 'vendor_pricing_final.xlsx' are one."
    p = Path(str(name or '').replace('\\', '/').rsplit('/', 1)[-1].lower())
    stem = _VER.sub('', p.stem).strip(' _.-') or p.stem
    return re.sub(r'[ _.-]+', ' ', stem) + p.suffix


def deliverables(rows: list) -> list:
    "Each family once - its newest row, the older ones on it as `earlier` - newest first. Every file is in it: none is left out for its kind."
    made, by = [], {}
    for r in sorted(rows or [], key=lambda r: str(r.get('at') or r.get('created_at') or ''), reverse=True):
        k = family(r.get('name') or r.get('path'))
        if k in by: by[k].setdefault('earlier', []).append(r)
        else: by[k] = dict(r); made.append(by[k])
    return made


# WHERE IS THE EXCEL THE AGENT MADE (the owner, 2026-10-28: "if I ask the chat assistant to pull up the Excel created by the agent on the
# task about X, could it find the link to it? It should be able to"). Every task's outputs folder and the pages its agents showed or
# published, matched by the task's words and the file's own name - the model passes the words and the kind; nothing reads the sentence.
_SHEET = ('.xlsx', '.xlsm', '.xls', '.csv', '.tsv')
KINDS = {'xlsx': _SHEET, 'sheet': _SHEET, 'spreadsheet': _SHEET, 'workbook': _SHEET, 'excel': _SHEET, 'csv': ('.csv', '.tsv'),
         'pdf': ('.pdf',), 'doc': ('.docx', '.doc', '.md', '.txt', '.rtf'), 'document': ('.docx', '.doc', '.md', '.txt', '.rtf', '.pdf'),
         'docx': ('.docx', '.doc'), 'word': ('.docx', '.doc'), 'deck': ('.pptx', '.ppt'), 'pptx': ('.pptx', '.ppt'), 'slides': ('.pptx', '.ppt'),
         'picture': ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'), 'chart': ('.png', '.jpg', '.jpeg', '.svg', '.html'),
         'page': ('.html', '.htm', '.md'), 'text': ('.md', '.txt')}


def exts_of(kind: str) -> tuple:
    "The extensions a `kind` means: a name in KINDS or an extension itself ('xlsx', '.pdf'); none means any file."
    k = str(kind or '').strip().lower().lstrip('.')
    return KINDS.get(k) or KINDS.get(k.rstrip('s')) or ((f'.{k}',) if re.fullmatch(r'[a-z0-9]{1,5}', k) else ())


def _tids() -> list:
    base = config.home() / 'scratch' / 'outputs'
    try: return sorted({int(m.group(1)) for d in base.iterdir() if d.is_dir() and (m := re.fullmatch(r'TQ-0*(\d+)', d.name))}, reverse=True)
    except OSError: return []


def _confined(raw):
    from .session_artifacts import confined
    return confined(raw)


def page_row(a: dict) -> dict:
    "A task's artifact as the page draws it - a page an agent showed or published among them - here, so a look-up never imports the server."
    return {'id': a['ArtifactId'], 'name': a.get('Name') or 'session artifact.md',
            'content_type': a.get('ContentType') or 'text/markdown', 'size': a.get('Size') or 0,
            **({'dims': d} if str(a.get('ContentType') or '').startswith('image/') and (f := _confined(a.get('Path'))) and (d := pixels(f)) else {}),
            'kind': a.get('Kind') or 'session', 'created_by': a.get('CreatedBy') or '', 'created_at': a.get('CreatedAt'),
            'url': f"/api/task-artifacts/{a['ArtifactId']}" if a.get('Path') else None,
            # a page a Claude session published: its claude.ai link (claude_artifacts); `url` is the local copy
            **({'external_url': a['Url'], 'version': a.get('Version') or ''} if a.get('Url') else {})}

PAGES = ('shown', 'claude_artifact')
def pages(store, tid: int) -> list:
    "The pages task `tid`'s agents showed (agenttools.show_files) or published (claude_artifacts), as rows - each chat places them by its turns."
    return [page_row(a) for a in store.list_task_artifacts(int(tid)) if a.get('Kind') in PAGES]


def find(store, query: str = '', kind: str = '', tid: int = None, limit: int = 8) -> list:
    """The files agents made, best match first: [{tid, title, name, url, at, earlier, ...}] - each family once (deliverables), whatever
    its kind. `query` is matched against the task's title and summary and the file's own name by MEANING (embeddings, textsim) -
    a count of shared word stems decided it once (the owner, 2026-10-28) - or, with no embedder, found there whole; `kind` narrows
    by what it is. Newest first when nothing is asked about."""
    from . import textsim
    want, q = exts_of(kind), ' '.join(str(query or '').split())
    ids, pages = [int(tid)] if tid else _tids(), {}
    try:
        for a in store._rows("SELECT * FROM task_artifact WHERE Kind IN ('shown','claude_artifact')" + (' AND TaskId=?' if tid else ''),
                             (int(tid),) if tid else ()):
            pages.setdefault(int(a['TaskId']), []).append(page_row(a))
    except Exception: pass
    hits = []
    for t in dict.fromkeys(ids + ([] if tid else sorted(pages, reverse=True))):
        task = store.get_task(t)
        if not task: continue
        made = deliverables(listing(t) + pages.get(t, []))
        about = f"{task.get('Title') or ''} {task.get('Summary') or ''}"
        for r in made:
            if want and Path(str(r.get('name') or '')).suffix.lower() not in want: continue
            text = f"{re.sub(r'[_.-]+', ' ', str(r.get('name') or ''))} - {about}"
            hits.append((f"file:{t}:{r.get('name')}", text, str(r.get('at') or r.get('created_at') or ''), {'tid': t, 'title': task.get('Title') or '', **r}))
    if not q: return [h[3] for h in sorted(hits, key=lambda h: h[2], reverse=True)][:limit]
    near = textsim.rank(store, q, [(k, text) for k, text, *_ in hits])
    by = {h[0]: h for h in hits}
    if near is not None: return [by[k][3] for k, _ in near][:limit]
    return [h[3] for h in sorted(hits, key=lambda h: h[2], reverse=True) if q.lower() in ' '.join(h[1].split()).lower()][:limit]


def _cell(v) -> str:
    if v is None: return ''
    s = v.isoformat(sep=' ') if hasattr(v, 'isoformat') else str(v)
    return s if len(s) <= CELL else s[:CELL - 1] + '…'


def sheet(p: Path, name: str = '') -> dict:
    """A workbook's sheet as rows the page draws: the named one (default the first), capped at ROWS x COLS, each cell at CELL
    characters; values, not formulas (data_only), read without loading the whole book (read_only)."""
    from openpyxl import load_workbook
    wb = load_workbook(p, read_only=True, data_only=True)
    try:
        names = wb.sheetnames
        ws = wb[name] if name in names else wb[names[0]]
        rows, more = [], False
        for i, r in enumerate(ws.iter_rows(values_only=True)):
            if i >= ROWS: more = True; break
            rows.append([_cell(v) for v in r[:COLS]])
        while rows and not any(rows[-1]): rows.pop()
        width = max((max((j + 1 for j, c in enumerate(r) if c), default=0) for r in rows), default=0)
        cut = (ws.max_column or 0) > COLS
        return {'sheet': ws.title, 'sheets': names[:SHEETS], 'rows': [r[:width] + [''] * (width - len(r[:width])) for r in rows],
                'more_rows': more, 'more_cols': cut, 'max_rows': ROWS, 'max_cols': COLS}
    finally: wb.close()


DOC_BLOCKS = 400                                     # a document preview: its first paragraphs and tables, never the whole book
_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def document(p: Path) -> dict:
    """A Word document as the page draws it: its paragraphs (a heading marked as one) and its tables as rows, in order, the first
    DOC_BLOCKS of them - read from the file's own XML (a .docx is a zip), so no library is needed and nothing in it runs."""
    import zipfile
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(p) as z: root = ET.fromstring(z.read('word/document.xml'))
    body = root.find(f'{_W}body')
    text = lambda el: ''.join(t.text or '' for t in el.iter(f'{_W}t'))
    blocks, more = [], False
    for el in list(body) if body is not None else []:
        if len(blocks) >= DOC_BLOCKS: more = True; break
        if el.tag == f'{_W}p':
            style = el.find(f'{_W}pPr/{_W}pStyle')
            head = style is not None and str(style.get(f'{_W}val') or '').lower().startswith(('heading', 'title'))
            if (t := text(el).strip()) or blocks: blocks.append({'text': _cell(t), **({'heading': True} if head else {})})
        elif el.tag == f'{_W}tbl':
            rows = [[_cell(text(c).strip()) for c in r.findall(f'{_W}tc')][:COLS] for r in el.findall(f'{_W}tr')][:ROWS]
            if rows: blocks.append({'rows': rows})
    while blocks and not blocks[-1].get('text', True): blocks.pop()
    return {'blocks': blocks, 'more': more, 'max_blocks': DOC_BLOCKS}


PREVIEW_VERSION = 1
def previewed(p: Path, name: str = '', sheet_name: str = '') -> dict:
    """A workbook's sheet (sheet) or a document's words (document) as the page draws them - read once per CONTENT, in the attachment-text
    cache (attachtext.cached), whichever file, route or press asks. Raises ValueError for a file of a kind with no such preview."""
    import hashlib
    from . import attachtext
    how = PREVIEW.get(Path(name or p.name).suffix.lower())
    if how not in ('sheet', 'document'): raise ValueError(how)
    def read():
        key = f'preview-{hashlib.sha256(p.read_bytes()).hexdigest()}-{how}-{sheet_name}-v{PREVIEW_VERSION}'
        return attachtext.cached(key, lambda: document(p) if how == 'document' else sheet(p, sheet_name))
    try: return read()
    except Exception:
        # ...A FILE ITS AGENT STILL WRITES (the owner's live task, 2026-11-17: a card asked the second the workbook was being saved, read half a
        # zip and said "could not be read" over a file that was whole a moment later): one that changed just now is waited on until it stops
        # changing, then read once more; one that is not changing is broken, said at once
        if not settled(p): raise
        return read()


SETTLE = 20
def settled(p: Path, wait: float = SETTLE) -> bool:
    "True once a file that changed in the last `wait` seconds has stood still for a second; False at once for one not being written."
    import time
    def stamp(): st = p.stat(); return st.st_size, st.st_mtime_ns
    if time.time() - p.stat().st_mtime > wait: return False
    end, last = time.monotonic() + wait, stamp()
    while time.monotonic() < end:
        time.sleep(0.5)
        if (now := stamp()) == last and time.time() - p.stat().st_mtime >= 1: return True
        last = now
    return False


def brief(tid: int) -> str:
    "What a chat with hands is told about the files it makes - so it saves them where the page finds them and never invents an address."
    d = folder(tid)
    try: d.mkdir(parents=True, exist_ok=True)
    except OSError: pass
    return (f'FILES YOU MAKE FOR THE OWNER: your outputs folder is {d} - each file there shows on this task with Preview and Download. '
            'Point at one by its full path. Never write a URL or a link to it (Taskuary serves the folder; an address you make up leads nowhere); '
            'asked to send it "here", it already is - name it. A file on a reply or an email rides on that card: name it there by its '
            'name, never its path.')     # ...one final file per thing: AGENT.md's Files you make (with_fence_rule)


# ...and a TERMINAL session is told the same by its environment (terminal.session_env: TASKUARY_OUTPUTS) and its standing rules
# (AGENT.md, or WHERE appended to an older copy - terminal.with_fence_rule), not its seed, which a real TUI types character by
# character under a budget: a Claude Code session on a task saved every workbook it made to the owner's Downloads and a scratchpad,
# where the task page - serving only this folder - had nothing to open or download.
ENV = 'TASKUARY_OUTPUTS'
WHERE = (f"Save each file you make for the owner in the task's outputs folder - its path is in ${ENV} (or your brief): the task page "
         'offers only that folder to open and download, so a file saved anywhere else never reaches the owner.')


def env_folder(tid) -> str:
    "The folder a session on task `tid` saves into, made now so the agent finds it there; '' with no task."
    if not str(tid or '').isdigit(): return ''
    d = folder(int(tid))
    try: d.mkdir(parents=True, exist_ok=True)
    except OSError: pass
    return str(d)


# ...and at the source (the owner, 2026-10-28): an agent that leaves every draft and every helper beside the answer is what made the list
ONE_FILE = ('Deliver one final file per thing asked: overwrite it as you improve it (or keep your drafts elsewhere), never leave every '
            'version beside it. Keep your scratch work - scripts, logs, test data, intermediate files - out of the folder the owner reads '
            'from. Make several files, or a list of files, only when the ask wants several.')

"""The files an agent makes FOR the owner on a task - a spreadsheet, a PDF, a chart - and how the task page reaches them.

A chat's CLI works in Taskuary's scratch folder (llm._build_llm), and nothing told it where a finished file should go. A Codex
researcher saved a workbook under scratch/outputs/TQ-0017/ by its own habit, cited it with its own `:codex-file-citation{...}`
marker - printed raw in the chat - and, asked to send it, made up http://127.0.0.1:7787/outputs/TQ-0017/... : a route this server
never had. Session artifacts (session_artifacts.py) are only files Taskuary itself copied in under ~/.taskuary/artifacts, so a
file the agent wrote was on disk and unreachable from the page.

Now the folder is named: <home>/scratch/outputs/TQ-nnnn/ for task nnnn - the very one the agent picked - it is said in the brief
(brief), and GET /api/task-outputs/<tid>/<file> serves a file in THAT task's folder and nothing else (resolve)."""
import mimetypes, re
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
         '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
# how the page previews each kind; anything not here is Download only
PREVIEW = {'.xlsx': 'sheet', '.xlsm': 'sheet', '.csv': 'table', '.pdf': 'pdf', '.png': 'picture', '.jpg': 'picture', '.jpeg': 'picture',
           '.gif': 'picture', '.webp': 'picture', '.md': 'text', '.txt': 'text', '.json': 'text', '.log': 'text', '.tsv': 'text',
           '.svg': 'page', '.html': 'page', '.htm': 'page'}


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

def resolve(tid: int, rel: str):
    """The file `rel` names inside task `tid`'s outputs folder, or None. A name only: never absolute, never a drive or a share, no
    `..` or empty step, no `:` (an NTFS stream), no link anywhere on the way - and after resolving, still under the folder."""
    rel = str(rel or '')
    if not rel or '\x00' in rel or _DRIVE.match(rel) or rel[0] in '/\\': return None
    parts = rel.replace('\\', '/').split('/')
    if any(p in ('', '.', '..') or ':' in p for p in parts): return None
    base = folder(tid)
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


def row(tid: int, p: Path, rel: str) -> dict:
    "One file as the page draws it - the same shape as a shown page (server._artifact_row), so one list draws both."
    from urllib.parse import quote
    ext, sheet = p.suffix.lower(), PREVIEW.get(p.suffix.lower())
    if sheet == 'sheet' and not can_sheet(): sheet = None
    return {'id': f'output:{rel}', 'name': p.name, 'path': rel, 'kind': 'output', 'content_type': content_type(p.name),
            'size': p.stat().st_size, 'preview': sheet, 'url': f'/api/task-outputs/{int(tid)}/{quote(rel)}',
            **({'note': 'No preview on this install - Download opens it in your spreadsheet app.'} if PREVIEW.get(ext) == 'sheet' and not sheet else {})}


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


def brief(tid: int) -> str:
    "What a chat with hands is told about the files it makes - so it saves them where the page finds them and never invents an address."
    d = folder(tid)
    try: d.mkdir(parents=True, exist_ok=True)
    except OSError: pass
    return (f'FILES YOU MAKE FOR THE OWNER (a spreadsheet, a document, a PDF, a chart): save each one in {d} . Every file there shows on '
            'this task with Preview and Download, so the owner opens it from the chat. To point at one, write its full path in your '
            'answer. Never write a URL or a link to it - Taskuary serves that folder itself, and an address you make up leads nowhere. '
            'Asked to send it "here", it already is: name the file.')

"""WORD AND EXCEL FILES BY AN AGENT'S OWN FILE TOOLS (apiagent's file_write / file_edit), the way a Claude Code session makes them with python.

An agent on an AI card (a HIPAA AI install: no CLI, no python - the exe has its own) could read a .docx or .xlsx but write only text: asked
to fill an invoice template and mail it (an outside user, 2026-11-15: "it says it took 25 min"), it said it had no way to, or wrote a
PowerShell script that unzipped the template and spliced its XML, step after step - each one a whole script of output from a slow model.
Now the one call does it, as plain code: text in, a real document out, and an edit made to the text the agent READ (file_read, which shows
a table's row as `a | b | c`), so a template keeps its look - and its one line-item row becomes one row per line given.
"""
import csv, html, io, re, zipfile
from copy import copy
from pathlib import Path
from xml.sax.saxutils import escape
from . import artifacts, knowledge as kn

KINDS = ('.docx', '.xlsx')
def is_office(p) -> bool: return Path(p).suffix.lower() in KINDS

_RULE = re.compile(r'^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')        # a markdown table's |---|---| line
def is_row(line: str) -> bool: return line.lstrip().startswith('|') or ' | ' in line
def cells(line: str) -> list:
    "A row's cells: a markdown row's outer bars (`| a | b |`) are its border; ` | b | c`, with no closing bar, starts with an empty cell."
    s = line.strip()
    return [c.strip() for c in (s[1:-1] if len(s) > 1 and s[0] == s[-1] == '|' else s).split('|')]
def rows_of(text: str) -> list: return [cells(l) for l in str(text or '').splitlines() if l.strip() and not _RULE.match(l)]


def value(s):
    "A number where the text is one (15, 2,930.00, $30.00) - never an id with a leading zero, a date or a code; else the text."
    t = str(s).strip().replace(',', '').removeprefix('$')
    if re.fullmatch(r'-?(0|[1-9]\d*)(\.\d+)?', t): return float(t) if '.' in t else int(t)
    return s


# ── writing one anew ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def write(p: Path, text: str) -> str:
    "`text` as the file `p` names: a sheet's rows (`a | b` or CSV lines), or a document's paragraphs and tables. What it wrote, in words."
    if p.suffix.lower() == '.xlsx':
        grid = [[value(c) for c in (cells(l) if is_row(l) else next(csv.reader([l])))] for l in str(text or '').splitlines() if l.strip() and not _RULE.match(l)]
        if not artifacts.grid_xlsx(grid, p, p.stem[:31], formulas=True): raise ValueError('no rows to write - give one line per row')
        return f'an Excel workbook, {len(grid)} rows'
    p.write_bytes(docx(text))
    return 'a Word document'


def _run(t: str, rpr: str = '') -> str:
    return f'<w:r>{f"<w:rPr>{rpr}</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{_esc(t)}</w:t></w:r>'
def _esc(t) -> str: return escape(str(t)).replace('\n', '</w:t><w:br/><w:t xml:space="preserve">')
def _p(t: str, rpr: str = '') -> str: return f'<w:p>{_run(t, rpr)}</w:p>' if t else '<w:p/>'
_EDGES = ''.join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="999999"/>' for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
def _tbl(rows: list) -> str:
    n = max(map(len, rows))
    return (f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{_EDGES}</w:tblBorders></w:tblPr><w:tblGrid>{"<w:gridCol/>" * n}</w:tblGrid>'
            + ''.join('<w:tr>' + ''.join(f'<w:tc>{_p(c, "<w:b/>" if i == 0 else "")}</w:tc>' for c in r + [''] * (n - len(r))) + '</w:tr>'
                      for i, r in enumerate(rows)) + '</w:tbl>')


def docx(text: str) -> bytes:
    "A document from text: a line a paragraph, `# ` a heading, **a line** bold, and a run of `a | b | c` lines a table (its first row bold)."
    body, rows = [], []
    for l in [*str(text or '').splitlines(), '']:
        if is_row(l):
            if not _RULE.match(l): rows.append(cells(l))
            continue
        if rows: body.append(_tbl(rows)); rows = []
        h, b = re.match(r'(#{1,3})\s+(.*)', l.strip()), re.fullmatch(r'\*\*(.+)\*\*', l.strip())
        body.append(_p(h[2], f'<w:b/><w:sz w:val="{36 - 4 * len(h[1])}"/>') if h else _p(b[1], '<w:b/>') if b else _p(l.rstrip()))
    xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{"".join(body[:-1] if body and body[-1] == "<w:p/>" else body)}<w:sectPr/></w:body></w:document>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', xml)
    return out.getvalue()


# ── editing one in place: its text as file_read shows it ─────────────────────────────────────────────────────────────────────────────
def edit(p: Path, old: str, new: str, to: Path) -> str:
    "`old` -> `new` in the document or sheet `p`, saved as `to`. Exactly one place, as the file reads (knowledge.extract); what it did, in words."
    if not old: raise ValueError('`old` is empty - give the text to replace, as file_read shows it')
    return (_edit_xlsx if p.suffix.lower() == '.xlsx' else _edit_docx)(p, old, new, to)


_P = re.compile(r'<w:p(?:\s[^>]*)?>.*?</w:p>', re.S)
_T = re.compile(r'(<w:t)(?:\s[^>]*)?>([^<]*)</w:t>')
def _text(xml: str) -> str: return ''.join(html.unescape(m[2]) for m in _T.finditer(xml))
def _once(n: int, name: str):
    if n != 1: raise ValueError(f'`old` occurs {n} times in {name} as file_read shows it - it must be exactly once (a whole table row, '
                                'or a piece of one paragraph or cell)')


def _put(p: str, old: str, new: str) -> str:
    "Paragraph `p` with `old` (in its text, across its runs) made `new`: each run keeps what it held outside `old`, the first run of it takes `new`."
    ts = list(_T.finditer(p)); a = _text(p).index(old); b, at, out = a + len(old), 0, []
    for m in ts:
        t = html.unescape(m[2]); lo = at; at += len(t)
        kept = ''.join(c for i, c in enumerate(t) if not a <= lo + i < b)
        if lo <= a < at: kept = t[:a - lo] + '\0' + kept[a - lo:]
        out.append((m, kept))
    for m, kept in reversed(out):
        p = p[:m.start()] + '<w:t xml:space="preserve">' + _esc(kept).replace('\0', _esc(new)) + '</w:t>' + p[m.end():]
    return p


_IDS = re.compile(r'\sw14:(?:paraId|textId)="[^"]*"')
def _fill(row: str, vals: list) -> str:
    "A copy of table row `row`, its cells' text `vals` in order - each cell's first run keeps its look; ids Word gives each paragraph left off."
    def cell(m, v):
        c = m.group()
        if (t := _T.search(c)): return c[:t.start()] + f'<w:t xml:space="preserve">{_esc(v)}</w:t>' + _T.sub('', c[t.end():])
        return c.replace('<w:p/>', '<w:p></w:p>', 1).replace('</w:p>', _run(v) + '</w:p>', 1) if v else c
    cs = list(kn.CELL.finditer(row)); vals = [*vals, *[''] * len(cs)]
    for m, v in reversed(list(zip(cs, vals))): row = row[:m.start()] + cell(m, v) + row[m.end():]
    return _IDS.sub('', row)


def _edit_docx(p: Path, old: str, new: str, to: Path) -> str:
    with zipfile.ZipFile(p) as z: parts = {i.filename: z.read(i.filename) for i in z.infolist()}
    s = parts['word/document.xml'].decode('utf-8')
    rows = [m for m in kn.ROW.finditer(s) if '|' in old and cells(kn.docx_row(m.group())) == cells(old)]
    paras = [m for m in _P.finditer(s) if old in _text(m.group())]
    _once(len(rows) or sum(_text(m.group()).count(old) for m in paras), p.name)
    if rows:
        m, vals = rows[0], rows_of(new)
        s, said = s[:m.start()] + ''.join(_fill(m.group(), v) for v in vals) + s[m.end():], f'that row is now {len(vals)} rows'
    else: m = paras[0]; s, said = s[:m.start()] + _put(m.group(), old, new) + s[m.end():], 'replaced'
    parts['word/document.xml'] = s.encode('utf-8')
    with zipfile.ZipFile(to, 'w', zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items(): z.writestr(k, v)
    return said


_REF = re.compile(r"(?<![A-Za-z_\d])(\$?[A-Z]{1,3}\$?)(\d+)(?::(\$?[A-Z]{1,3}\$?)(\d+))?(?![\w(])")
def _moved(f: str, at: int, n: int) -> str:
    "Formula `f` once `n` rows went in under row `at`: a reference below it moves down, a range that ends on it grows to take them."
    def go(m):
        c1, r1, c2, r2 = m[1], int(m[2]), m[3], m[4] and int(m[4])
        if not c2: return f'{c1}{r1 + n if r1 > at else r1}'
        return f'{c1}{r1 + n if r1 > at else r1}:{c2}{r2 + n if r2 >= at else r2}'
    return _REF.sub(go, f)


def _edit_xlsx(p: Path, old: str, new: str, to: Path) -> str:
    try: from openpyxl import load_workbook; from openpyxl.formula.translate import Translator
    except ImportError: raise ValueError('this computer has no Excel reader (openpyxl) - write the sheet anew with file_write') from None
    wb, shown = load_workbook(p), load_workbook(p, data_only=True)        # ...the second as file_read reads it: a total its cached value
    look = lambda ws, row: [c for c in shown[ws.title][row[0].row] if c.value not in (None, '')] if row else []
    hits = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            vis = look(ws, row)
            if '|' in old and [str(c.value).strip() for c in vis] == cells(old): hits.append((ws, row, vis)); continue
            hits += [(ws, c, None) for c in row if not str(c.value or '').startswith('=') and old in str(c.value or '') for _ in range(str(c.value).count(old))]
    _once(len(hits), p.name)
    ws, at, vis = hits[0]
    if vis is None:
        whole = str(at.value) == old
        at.value, said = value(new) if whole else str(at.value).replace(old, new), 'replaced'
    else:
        vals, r = rows_of(new), at[0].row
        if len(vals) > 1:
            ws.insert_rows(r + 1, len(vals) - 1)
            for c in ws.iter_rows():
                for x in c:
                    if isinstance(x.value, str) and x.value.startswith('=') and x.row != r: x.value = _moved(x.value, r, len(vals) - 1)
        cols = [c.column for c in vis]
        for i, v in enumerate(vals):
            for c in ws[r]:
                y = ws.cell(r + i, c.column)
                if i: y._style = copy(c._style)
                if isinstance(c.value, str) and c.value.startswith('='): y.value = Translator(c.value, origin=c.coordinate).translate_formula(y.coordinate) if i else c.value
                elif c.column in cols and cols.index(c.column) < len(v): y.value = value(v[cols.index(c.column)])
            if i and ws.row_dimensions[r].height: ws.row_dimensions[r + i].height = ws.row_dimensions[r].height
        said = f'that row is now {len(vals)} rows, its formulas carried to each and every total over it widened'
    wb.save(to)
    with zipfile.ZipFile(p) as z: pics = any(n.startswith(('xl/media/', 'xl/drawings/')) for n in z.namelist())
    return said + (' - its pictures and charts are not kept by this edit: say so, or write it anew' if pics else '')

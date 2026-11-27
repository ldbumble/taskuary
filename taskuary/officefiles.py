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
from .timewords import plural

KINDS = ('.docx', '.xlsx')                     # ...edited in place: their text as file_read shows it
MADE = (*KINDS, '.pdf', '.pptx')                # ...and written anew from text (write)
def is_office(p) -> bool: return Path(p).suffix.lower() in KINDS
def is_made(p) -> bool: return Path(p).suffix.lower() in MADE

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
    if p.suffix.lower() == '.pdf': p.write_bytes(pdf(text)); return f"a PDF, {plural(pdf.pages, 'page')}"
    if p.suffix.lower() == '.pptx': p.write_bytes(pptx(text)); return f"a PowerPoint deck, {plural(pptx.slides, 'slide')}"
    p.write_bytes(docx(text))
    return 'a Word document'


# ── A PDF AND A DECK BY THE SAME ROAD (design round 5, 2026-11-19: an agent on an AI card made the .xlsx, then said a one-page PDF with a bar
# chart and a five-slide deck "requires file generation tools ... AI CLI agents", and drew the chart in block characters in an email to a
# leader). One text grammar for every kind: `# ` a title (a slide's, in a deck), `- ` a point, `a | b | c` lines a table, `chart: <title>`
# over `label | number` lines a bar chart, `---` a new page or slide. Plain code, no library: what the HIPAA install's exe has.
def blocks(text: str) -> list:
    "[(kind, v)]: ('h', (level, text)), ('p', text), ('li', text), ('table', rows), ('chart', (title, [(label, n)])), ('break', ''), ('gap', '')."
    out, rows, chart = [], [], None
    def num(c):
        v = value(c); return float(v) if isinstance(v, (int, float)) else 0.
    def flush():
        nonlocal rows, chart
        if chart is not None: out.append(('chart', (chart, [(r[0], num(r[-1])) for r in rows if r])))
        elif rows: out.append(('table', rows))
        rows, chart = [], None
    for l in str(text or '').splitlines():
        t = l.strip()
        if is_row(l):
            if not _RULE.match(l): rows.append(cells(l))
            continue
        flush()
        if (c := re.match(r'(?i)chart:\s*(.*)', t)): chart = c[1]; continue
        h = re.match(r'(#{1,3})\s+(.*)', t)
        out.append(('h', (len(h[1]), h[2])) if h else ('break', '') if re.fullmatch(r'-{3,}', t) else ('li', t[2:]) if t[:2] in ('- ', '* ')
                   else ('p', t.strip('*') if re.fullmatch(r'\*\*.+\*\*', t) else t) if t else ('gap', ''))
    flush()
    return out


def _num(b: float) -> str: return f'{b:,.0f}' if b == int(b) else f'{b:,.2f}'
def _pstr(t) -> str:
    s = str(t).replace('•', '\x95').replace('–', '-').replace('—', '-').encode('cp1252', 'replace').decode('latin-1')
    return '(' + s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'
def _wrap(t: str, size: float, width: float) -> list:
    "Lines of `t` that fit `width` points in Helvetica at `size` (a character ~0.52 of the size)."
    n, out, cur = max(8, int(width / (size * .52))), [], ''
    for w in str(t).split():
        if cur and len(cur) + 1 + len(w) > n: out.append(cur); cur = w
        else: cur = f'{cur} {w}' if cur else w
    return out + [cur] if cur else out or ['']


def pdf(text: str) -> bytes:
    "A PDF (US Letter) from text in the grammar of `blocks`. `pdf.pages`: how many pages the last one had."
    W, H, M = 612, 792, 54
    pages, ops, y = [], [], H - M
    def page():
        nonlocal ops, y
        pages.append(ops); ops, y = [], H - M
    def room(h):
        if y - h < M and ops: page()
    def line(t, size=11, bold=False):
        nonlocal y
        room(size * 1.4); y -= size * 1.4
        ops.append(f'BT /F{2 if bold else 1} {size} Tf {M:.1f} {y:.1f} Td {_pstr(t)} Tj ET')
    for k, v in blocks(text):
        if k == 'h':
            y -= 6
            for t in _wrap(v[1], 22 - 4 * v[0], W - 2 * M): line(t, 22 - 4 * v[0], True)
            y -= 2
        elif k in ('p', 'li'):
            for i, t in enumerate(_wrap(v, 11, W - 2 * M - 14 * (k == 'li'))): line(('•  ' if not i else '    ') + t if k == 'li' else t)
        elif k == 'gap': y -= 8
        elif k == 'break': page()
        elif k == 'table':
            n = max(map(len, v)); cw = (W - 2 * M) / n
            for i, r in enumerate(v):
                room(18); y -= 18
                ops += [f'BT /F{2 if i == 0 else 1} 10 Tf {M + j * cw + 4:.1f} {y + 5:.1f} Td {_pstr(_wrap(c, 10, cw - 8)[0])} Tj ET' for j, c in enumerate(r)]
                ops.append(f'0.6 G 0.5 w {M} {y:.1f} m {W - M} {y:.1f} l S')
        elif k == 'chart':
            title, bars = v
            if title: line(title, 12, True)
            top, at = max([b for _, b in bars] + [0]) or 1, M + (W - 2 * M) * .34
            for lbl, b in bars:
                room(20); y -= 20
                bw = (W - 2 * M) * .5 * max(b, 0) / top
                ops += [f'BT /F1 10 Tf {M:.1f} {y + 5:.1f} Td {_pstr(_wrap(lbl, 10, (W - 2 * M) * .32)[0])} Tj ET',
                        f'0.25 0.42 0.55 rg {at:.1f} {y + 2:.1f} {bw:.1f} 12 re f 0 g', f'BT /F1 10 Tf {at + bw + 6:.1f} {y + 5:.1f} Td {_pstr(_num(b))} Tj ET']
            y -= 6
    page()
    pages = [p for p in pages if p] or [[]]
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', '', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>']
    kids = []
    for ops_ in pages:
        body = '\n'.join(ops_).encode('latin-1')
        objs.append(b'<< /Length %d >>\nstream\n' % len(body) + body + b'\nendstream')
        objs.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {len(objs)} 0 R >>')
        kids.append(f'{len(objs)} 0 R')
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, at = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'), []
    for i, o in enumerate(objs, 1):
        at.append(len(out)); out += f'{i} 0 obj\n'.encode() + (o if isinstance(o, bytes) else o.encode('latin-1')) + b'\nendobj\n'
    x = len(out)
    out += f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode() + b''.join(b'%010d 00000 n \n' % a for a in at)
    out += f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n'.encode()
    pdf.pages = len(pages)
    return bytes(out)


_PNS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
_REL, SW, SH, IN = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/', 12192000, 6858000, 914400      # a 16:9 slide, an inch
def _rels(*rs) -> str:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + ''.join(f'<Relationship Id="rId{i}" Type="{_REL}{t}" Target="{g}"/>' for i, (t, g) in enumerate(rs, 1)) + '</Relationships>')
def _tree(shapes: str = '') -> str:
    return '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>' + shapes + '</p:spTree></p:cSld>'
def _box(i, x, y, w, h, paras: str = '', fill: str = '') -> str:
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Shape {i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{int(x)}" y="{int(y)}"/>'
            f'<a:ext cx="{max(int(w), 1)}" cy="{int(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            + (f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>') + '</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="0" rIns="0"><a:normAutofit/></a:bodyPr><a:lstStyle/>{paras or "<a:p/>"}</p:txBody></p:sp>')
_BULLET = '<a:pPr marL="285750" indent="-285750"><a:buChar char="&#8226;"/></a:pPr>'
def _para(t, size=18, bold=False, bullet=False) -> str:
    return (f'<a:p>{_BULLET if bullet else ""}<a:r><a:rPr lang="en-US" sz="{size * 100}"{" b=" + chr(34) + "1" + chr(34) if bold else ""} dirty="0"/>'
            f'<a:t>{escape(str(t))}</a:t></a:r></a:p>')


def _slide(bs: list) -> str:
    "One slide's shapes: its title across the top, then its points, tables and charts down the rest."
    x0, w, out, body = 0.6 * IN, SW - 1.2 * IN, [], []
    n, y = 2, 1.45 * IN
    title = next((v[1] for k, v in bs if k == 'h'), '')
    if title: out.append(_box(n, x0, 0.4 * IN, w, 0.9 * IN, _para(title, 30, True))); n += 1
    def text():
        nonlocal n, y, body
        if body: h = (len(body) * .45 + .1) * IN; out.append(_box(n, x0, y, w, h, ''.join(body))); n += 1; y += h; body = []
    for k, v in bs:
        if k == 'h' and v[1] == title: continue
        if k in ('h', 'p', 'li'): body.append(_para(v[1] if k == 'h' else v, 22 if k == 'h' else 20, k == 'h', k == 'li'))
        elif k == 'table':
            text(); cols = max(map(len, v)); cw = w / cols
            for i, r in enumerate(v):
                for j, c in enumerate(r + [''] * (cols - len(r))): out.append(_box(n, x0 + j * cw, y, cw - .05 * IN, .42 * IN, _para(c, 14, i == 0), 'DCE3EA' if i == 0 else '')); n += 1
                y += .45 * IN
        elif k == 'chart':
            text()
            if v[0]: out.append(_box(n, x0, y, w, .5 * IN, _para(v[0], 18, True))); n += 1; y += .55 * IN
            top = max([b for _, b in v[1]] + [0]) or 1
            for lbl, b in v[1]:
                bw = w * .5 * max(b, 0) / top
                out += [_box(n, x0, y, w * .32, .4 * IN, _para(lbl, 14)), _box(n + 1, x0 + w * .34, y + .06 * IN, bw, .28 * IN, '', '3F6A8C'),
                        _box(n + 2, x0 + w * .34 + bw + .1 * IN, y, w * .14, .4 * IN, _para(_num(b), 14))]
                n += 3; y += .45 * IN
    text()
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld {_PNS}>{_tree("".join(out))}<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'


_THEME = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Taskuary">'
          '<a:themeElements><a:clrScheme name="Taskuary"><a:dk1><a:srgbClr val="1F2328"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
          '<a:dk2><a:srgbClr val="2F3B45"/></a:dk2><a:lt2><a:srgbClr val="EEF1F4"/></a:lt2>'
          + ''.join(f'<a:accent{i}><a:srgbClr val="{c}"/></a:accent{i}>' for i, c in enumerate(('3F6A8C', '6B8E5A', 'B07D3A', '8C4A5A', '5A6B8C', '7A7A7A'), 1))
          + '<a:hlink><a:srgbClr val="3F6A8C"/></a:hlink><a:folHlink><a:srgbClr val="5A6B8C"/></a:folHlink></a:clrScheme>'
          '<a:fontScheme name="Taskuary"><a:majorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
          '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
          '<a:fmtScheme name="Taskuary"><a:fillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:fillStyleLst>'
          '<a:lnStyleLst>' + '<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3 + '</a:lnStyleLst>'
          '<a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3 + '</a:effectStyleLst>'
          '<a:bgFillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3 + '</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>')
_CLRMAP = ('bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
           'accent6="accent6" hlink="hlink" folHlink="folHlink"')


def pptx(text: str) -> bytes:
    "A PowerPoint deck (16:9) from text in the grammar of `blocks`: each `# ` title or `---` starts a slide. `pptx.slides`: how many the last had."
    slides, cur = [], []
    for k, v in blocks(text):
        if k == 'break' or (k == 'h' and v[0] == 1 and any(x == 'h' for x, _ in cur)): slides.append(cur); cur = []
        if k != 'break': cur.append((k, v))
    slides = [s for s in [*slides, cur] if any(k != 'gap' for k, _ in s)] or [[]]
    ct, ns = 'application/vnd.openxmlformats-officedocument.presentationml', range(1, len(slides) + 1)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   f'<Override PartName="/ppt/presentation.xml" ContentType="{ct}.presentation.main+xml"/>'
                   f'<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="{ct}.slideMaster+xml"/>'
                   f'<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="{ct}.slideLayout+xml"/>'
                   '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
                   + ''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{ct}.slide+xml"/>' for i in ns) + '</Types>')
        z.writestr('_rels/.rels', _rels(('officeDocument', 'ppt/presentation.xml')))
        z.writestr('ppt/presentation.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation {_PNS}>'
                   '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>'
                   + ''.join(f'<p:sldId id="{255 + i}" r:id="rId{i + 2}"/>' for i in ns)
                   + f'</p:sldIdLst><p:sldSz cx="{SW}" cy="{SH}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', _rels(('slideMaster', 'slideMasters/slideMaster1.xml'), ('theme', 'theme/theme1.xml'),
                                                            *(('slide', f'slides/slide{i}.xml') for i in ns)))
        z.writestr('ppt/slideMasters/slideMaster1.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldMaster {_PNS}>{_tree()}'
                   f'<p:clrMap {_CLRMAP}/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst></p:sldMaster>')
        z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels', _rels(('slideLayout', '../slideLayouts/slideLayout1.xml'), ('theme', '../theme/theme1.xml')))
        z.writestr('ppt/slideLayouts/slideLayout1.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sldLayout {_PNS} type="blank">{_tree()}'
                   '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
        z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels', _rels(('slideMaster', '../slideMasters/slideMaster1.xml')))
        z.writestr('ppt/theme/theme1.xml', _THEME)
        for i, s in zip(ns, slides):
            z.writestr(f'ppt/slides/slide{i}.xml', _slide(s))
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels', _rels(('slideLayout', '../slideLayouts/slideLayout1.xml')))
    pptx.slides = len(slides)
    return out.getvalue()


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
    look = lambda ws, row: [(c, kn.shown(v.value, c.value)) for c, v in zip(row, shown[ws.title][row[0].row]) if kn.shown(v.value, c.value) not in (None, '')] if row else []
    hits = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            vis = look(ws, row)
            if '|' in old and [str(v).strip() for _, v in vis] == cells(old): hits.append((ws, row, vis)); continue
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
        cols = [c.column for c, _ in vis]
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
    return said + (' - its pictures and charts are not kept by this edit' if pics else '')

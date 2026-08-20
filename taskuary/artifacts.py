"""Report output you can actually use: the spreadsheet and the chart, not just the prose.

A report already produces ROWS - the message body is one JSON object per line - so the same
run can hand back an .xlsx to open in Excel and an .svg chart to look at in the panel. Both
are written as attachments on the report message, which means the timeline and the task page
already know how to show them (images inline, files as chips).

Both writers are hand-rolled on the standard library on purpose: xlsx is a zip of four small
XML parts, and a bar chart is a few dozen rects. Neither is worth a dependency that has to be
frozen into the one-file exe.
"""
import json, re, zipfile
from datetime import datetime
from xml.sax.saxutils import escape

MAX_SHEET_ROWS, MAX_COLS, MAX_BARS = 5000, 40, 24
_SAFE = re.compile(r'[^A-Za-z0-9._ -]+')


def attachment_dir(mid: int):
    """Where a message's files live. One folder per message, so deleting a message's bytes is
    deleting a folder."""
    from . import config
    p = config.home() / 'attachments' / str(int(mid))
    p.mkdir(parents=True, exist_ok=True)
    return p


def rows_from_body(text: str) -> list:
    """The rows back out of a report body (one JSON object per line). Anything that is not a
    JSON object is prose - a summary, an error - and is not data."""
    out = []
    for l in (text or '').splitlines():
        l = l.strip()
        if not l.startswith('{'): continue
        try:
            d = json.loads(l)
            if isinstance(d, dict): out.append(d)
        except ValueError:
            pass
    return out[:MAX_SHEET_ROWS]


def columns(rows: list) -> list:
    """Every key any row has, in the order they first appear - SQL rows are uniform, REST rows
    are not, and a missing key must not shift a column."""
    cols = []
    for r in rows:
        for k in r:
            if k not in cols: cols.append(k)
    return cols[:MAX_COLS]


def _cell(ref: str, v) -> str:
    # a missing value writes NO cell (refs are explicit, so nothing shifts): an empty inline
    # string is a value, and Excel treats "" and blank differently in counts and filters
    if v is None or v == '': return ''
    if isinstance(v, bool): v = str(v)
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"><v>{v}</v></c>'
    s = json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(s)}</t></is></c>'


def _col_name(i: int) -> str:
    s = ''
    while True:
        s, i = chr(65 + i % 26) + s, i // 26 - 1
        if i < 0: return s


def to_xlsx(rows: list, path, sheet: str = 'Report') -> bool:
    """Minimal but real xlsx: header row bold-free, inline strings, numbers as numbers so Excel
    sums them. Returns False when there is nothing tabular to write."""
    if not rows: return False
    cols = columns(rows)
    xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    xml.append('<row r="1">' + ''.join(_cell(f'{_col_name(i)}1', c) for i, c in enumerate(cols)) + '</row>')
    for n, r in enumerate(rows, start=2):
        xml.append(f'<row r="{n}">' + ''.join(_cell(f'{_col_name(i)}{n}', r.get(c)) for i, c in enumerate(cols)) + '</row>')
    xml.append('</sheetData></worksheet>')
    name = escape(_SAFE.sub('', str(sheet))[:31] or 'Report')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '</Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr('xl/workbook.xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '</Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', ''.join(xml))
    return True


def _num(v):
    if isinstance(v, bool) or v is None: return None
    if isinstance(v, (int, float)): return float(v)
    try: return float(str(v).replace(',', '').replace('$', '').strip())
    except ValueError: return None


_CHART_LINE = re.compile(r'^[ \t]*CHART:[ \t]*([^|\r\n]+?)[ \t]*(?:\|[ \t]*([^\r\n]*))?$', re.M | re.I)

def chart_directive(text: str) -> tuple:
    """(value column, label column, title) if the summary asked for a particular chart. The AI
    has just read every row, so it knows which column is the measure and which is the name -
    better than a heuristic scanning for "all numeric". Format: `CHART: amount | vendor | Spend
    by vendor`. Absent, or naming a column that is not there, falls back to the guess."""
    mt = _CHART_LINE.search(text or '')
    if not mt: return None, None, ''
    bits = [b.strip() for b in ((mt.group(1) or '') + '|' + (mt.group(2) or '')).split('|')]
    return (bits[0] or None), (bits[1] if len(bits) > 1 and bits[1] else None), (bits[2] if len(bits) > 2 else '')


def strip_directive(text: str) -> str:
    """The CHART: line is an instruction to Taskuary, not prose for the reader."""
    return _CHART_LINE.sub('', text or '').strip()


def chart_columns(rows: list) -> tuple:
    """(label column, value column) - the first column that reads as a name, and the first that
    reads as a number in every row. No numbers means no chart; a table of ids and strings is not
    a chart just because we can draw axes."""
    cols = columns(rows)
    vals = [c for c in cols if all(_num(r.get(c)) is not None for r in rows if c in r)
            and any(_num(r.get(c)) for r in rows)]
    labels = [c for c in cols if c not in vals]
    return ((labels[0] if labels else None), (vals[0] if vals else None))


# Taskuary's own indigo, and a chart that reads in both the panel and a screenshot of it.
def to_svg_chart(rows: list, path, title: str = '', want_val: str = None, want_lab: str = None) -> str:
    """Horizontal bars: label, bar, value. Horizontal because report labels are names and dates,
    which do not fit under a vertical bar without turning sideways. Returns the caption, or ''
    when the rows carry nothing to plot. `want_val`/`want_lab` are the AI's pick, honoured only
    when the column is really in the rows - a hallucinated column must not lose the chart."""
    cols = columns(rows)
    lab, val = chart_columns(rows)
    if want_val in cols and any(_num(r.get(want_val)) is not None for r in rows): val = want_val
    if want_lab in cols: lab = want_lab
    if not val: return ''
    pts = [(str(r.get(lab, ''))[:42] if lab else f'#{i + 1}', _num(r.get(val)) or 0.0)
           for i, r in enumerate(rows)][:MAX_BARS]
    if not pts: return ''
    top = max(abs(v) for _l, v in pts) or 1.0
    W, LW, RH, PAD = 760, 210, 22, 18
    H = PAD * 2 + 26 + RH * len(pts)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="{PAD}" y="{PAD + 12}" font-size="13" font-weight="700" fill="#1f2430">'
           f'{escape(title or val)}</text>',
           f'<text x="{W - PAD}" y="{PAD + 12}" font-size="10" fill="#8a94a6" text-anchor="end">'
           f'{escape(val)} by {escape(lab or "row")} · {len(pts)} of {len(rows)}</text>']
    bar_w = W - LW - PAD * 2 - 60
    for i, (l, v) in enumerate(pts):
        y = PAD + 26 + i * RH
        w = max(1, int(bar_w * abs(v) / top))
        out += [f'<text x="{LW}" y="{y + 14}" font-size="11" fill="#697386" text-anchor="end">{escape(l)}</text>',
                f'<rect x="{LW + 8}" y="{y + 4}" width="{w}" height="{RH - 9}" rx="2" fill="#4f46e5" fill-opacity="0.85"/>',
                f'<text x="{LW + 14 + w}" y="{y + 14}" font-size="10.5" fill="#1f2430">'
                f'{escape(f"{v:,.2f}".rstrip("0").rstrip("."))}</text>']
    out.append('</svg>')
    svg = ''.join(out)
    if path is not None: path.write_text(svg, encoding='utf-8')
    return svg if path is None else f'{val} by {lab or "row"}'


XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def attach_report_output(store, mid: int, title: str, body: str) -> list:
    """Turn one report's rows into files on its message: the spreadsheet, and the chart when the
    data has a measure in it. Prose-only reports (an AI summary, a failure) produce neither, and
    `report_images_enabled` = 0 turns the chart off without losing the spreadsheet."""
    rows = rows_from_body(body)
    if not rows: return []
    want_val, want_lab, want_title = chart_directive(body)
    charts_on = str(store.get_settings().get('report_images_enabled') or '1') == '1'
    stem = _SAFE.sub('', title or 'report').strip()[:60] or 'report'
    day = datetime.now().strftime('%Y-%m-%d')
    made = []
    d = attachment_dir(mid)
    x = d / f'{stem} {day}.xlsx'
    if to_xlsx(rows, x, stem[:31]):
        made.append(store.add_attachment({'MessageId': mid, 'ExternalId': f'report:{mid}:xlsx', 'Name': x.name,
                                          'ContentType': XLSX_TYPE, 'Size': x.stat().st_size, 'Path': str(x)}))
    c = d / f'{stem} {day}.svg'
    if charts_on and to_svg_chart(rows, c, want_title or stem, want_val, want_lab):
        made.append(store.add_attachment({'MessageId': mid, 'ExternalId': f'report:{mid}:chart', 'Name': c.name,
                                          'ContentType': 'image/svg+xml', 'Size': c.stat().st_size,
                                          'Inline': 1, 'Path': str(c)}))
    return made

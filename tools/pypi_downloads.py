"""The installs chart in the README, drawn from PyPI's own numbers.

Two things make a downloads number honest, and pypistats gives one of them:

* **Mirrors are not people.** Every full PyPI mirror pulls every release, so a package with
  three real users can read as hundreds. `mirrors=False` is the public API's own split and
  the series here uses it exclusively.
* **CI is not people either** - and this is the part the public API cannot do. PyPI's raw
  dataset carries an `installer` field (pip, poetry, uv, bandersnatch, "Browser") that would
  separate `pip install` in a GitHub runner from one on somebody's laptop, but it lives in
  BigQuery, not in pypistats. So the chart says "without mirrors" and does not claim to have
  removed CI: a number that overstates itself quietly is worse than one that says what it is.

No matplotlib: the SVG is written out directly, the way docs/learning-loop.svg is, so the
workflow needs one small dependency and the chart stays diffable in review.

    python tools/pypi_downloads.py --package taskuary --history docs/downloads.csv --out docs/downloads.svg
"""
import argparse, csv, json, math, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = 'https://pypistats.org/api/packages'
# pypistats.org rate-limits by user agent and answers 429 to anonymous library traffic from a
# shared address (observed 2026-08-31 from a laptop; a named agent went straight through). So the
# library is the road and a named plain request is the shoulder.
UA = 'taskuary-downloads-chart (+https://github.com/ldbumble/taskuary)'
HTTP_PARAMS = ('mirrors',)      # the rest are pypistats' own presentation options, not the API's

WIDTH, HEIGHT = 880, 260
PAD_L, PAD_R, PAD_T, PAD_B = 52, 78, 52, 30      # right padding holds the two direct labels
DAYS = 180                    # what the pypistats overall endpoint keeps
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _get(pkg: str, what: str, **params) -> dict:
    """One pypistats endpoint, as JSON. pypistats itself where it is installed and answering;
    otherwise the same URL with a user agent that says who is asking."""
    try:
        import pypistats                                # only the workflow needs it installed
        return json.loads(getattr(pypistats, what)(pkg, format='json', **params))
    except Exception as e:
        print(f'pypistats {what} did not answer ({e}); asking the API directly', file=sys.stderr)
        send = {k: str(v).lower() for k, v in params.items() if k in HTTP_PARAMS}
        q = f'?{urlencode(send)}' if send else ''
        with urlopen(Request(f'{API}/{pkg}/{what}{q}', headers={'User-Agent': UA}), timeout=30) as r:
            return json.load(r)


def series(payload: dict) -> list:
    """[(iso date, downloads)] with mirror traffic dropped, from an overall payload."""
    return [(r['date'], int(r['downloads'])) for r in (payload.get('data') or [])
            if r.get('category') in (None, 'without_mirrors') and r.get('date')]


def fetch(pkg: str) -> list:
    """The last ~180 days as the API keeps them, mirrors excluded.

    total='daily' is not decoration: pypistats defaults to 'all', which sums the whole window
    into ONE dateless row per category - and a chart of days then has no days in it at all
    ("nothing to chart yet", the first workflow run)."""
    return series(_get(pkg, 'overall', mirrors=False, total='daily'))


def merge(old: list, new: list) -> list:
    """One row per day, newest fetch winning, older days kept once they age out of the window -
    the whole point of committing a CSV rather than re-asking for a 180-day window forever."""
    by = {d: n for d, n in old}
    by.update({d: n for d, n in new})
    return sorted(by.items())


def read_history(path: Path) -> list:
    if not path.exists(): return []
    with path.open(newline='', encoding='utf-8') as f:
        return [(r['date'], int(r['downloads'])) for r in csv.DictReader(f) if r.get('date')]


def write_history(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['date', 'downloads'])
        w.writerows(rows)


def totals(rows: list, today: date = None) -> dict:
    """The three figures `pypistats recent` prints, computed from the SERIES the chart is drawn
    from - so the caption can never disagree with the line under it."""
    end = today or (datetime.fromisoformat(rows[-1][0]).date() if rows else date.today())
    by = {d: n for d, n in rows}
    span = lambda days: sum(by.get((end - timedelta(days=i)).isoformat(), 0) for i in range(days))
    return {'last_day': by.get(end.isoformat(), 0), 'last_week': span(7), 'last_month': span(30)}


def _mean7(vals: list) -> list:
    return [sum(vals[max(0, i - 6):i + 1]) / len(vals[max(0, i - 6):i + 1]) for i in range(len(vals))]


def _nice(top: int) -> int:
    """A round y-axis ceiling that stays CLOSE to the data - 500 over a peak of 210 leaves the
    line crawling along the bottom of the frame. Steps a tenth of the magnitude at a time."""
    if top <= 5: return 5
    step = 10 ** (len(str(int(top))) - 1)
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10):
        if top <= m * step: return math.ceil(m * step)
    return 10 * step


def _day(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso).date()
        return f'{MONTHS[d.month - 1]} {d.day}'
    except (TypeError, ValueError): return iso


def _ticks(rows: list, want: int = 6) -> list:
    """Indices for the dated labels: every day while there are few, evenly spaced once there
    are many. Uneven gaps read as missing data, so the spacing is computed, not sampled."""
    n = len(rows)
    if n <= 10: return list(range(n))
    step = (n - 1) / (want - 1)
    return sorted({int(i * step + 0.5) for i in range(want)})


def svg(rows: list, pkg: str, window: int = DAYS) -> str:
    """One measure, two readings of it: the daily count as a soft area, and the 7-day mean as
    the line - which is the shape a downloads chart is actually read for. One hue, because it
    is one measure; both are named at the right-hand end rather than in a legend box.

    The colours are the data-viz reference palette's slot 1, stepped for each surface, and the
    text follows the reader's theme through a media query - an <img> SVG carries its own
    rendering context, so that works on GitHub in both themes. No hover: a README renders this
    as an image, so every label it needs has to be drawn."""
    rows = rows[-window:]
    n = len(rows)
    t = totals(rows)
    plot_w, plot_h = WIDTH - PAD_L - PAD_R, HEIGHT - PAD_T - PAD_B
    vals = [v for _, v in rows]
    mean = _mean7(vals)
    top = _nice(max(vals or [0]))
    x = lambda i: PAD_L + (plot_w * (i / (n - 1)) if n > 1 else plot_w / 2)
    y = lambda v: PAD_T + plot_h - plot_h * min(v, top) / top
    base = PAD_T + plot_h
    pts = lambda ys: ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(ys))
    area = (f'<path d="M{x(0):.1f},{base} L{pts(vals).replace(" ", " L")} L{x(n - 1):.1f},{base} Z" class="area"/>'
            if n > 1 else '')
    if n == 1: area = f'<rect x="{x(0) - 3:.1f}" y="{y(vals[0]):.1f}" width="6" height="{base - y(vals[0]):.1f}" class="area"/>'
    grid = ''.join(
        f'<line x1="{PAD_L}" y1="{y(v):.1f}" x2="{WIDTH - PAD_R}" y2="{y(v):.1f}" class="grid"/>'
        f'<text x="{PAD_L - 10}" y="{y(v) + 3.5:.1f}" class="dim" text-anchor="end">{v:,}</text>'
        for v in (0, top // 2, top) if v or True)
    days = ''.join(f'<text x="{x(i):.1f}" y="{HEIGHT - 10}" class="dim" text-anchor="middle">{_day(rows[i][0])}</text>'
                   for i in _ticks(rows))
    # the two end labels, pushed apart when the day and its mean finish on top of each other
    ly, my = (y(vals[-1]), y(mean[-1])) if n else (0, 0)
    if abs(ly - my) < 13: ly, my = (ly + 6.5, my - 6.5) if ly >= my else (ly - 6.5, my + 6.5)
    tip = (f'<circle cx="{x(n - 1):.1f}" cy="{y(vals[-1]):.1f}" r="3.5" class="dot"/>'
           f'<text x="{x(n - 1) + 9:.1f}" y="{ly + 3.5:.1f}" class="key">daily</text>'
           f'<text x="{x(n - 1) + 9:.1f}" y="{my + 3.5:.1f}" class="key">7-day mean</text>') if n else ''
    caption = (f'{t["last_day"]:,} yesterday   ·   {t["last_week"]:,} in the last 7 days   ·   {t["last_month"]:,} in 30'
               if n else 'no downloads reported yet')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"
     font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
     role="img" aria-label="Daily installs of {pkg} from PyPI, mirrors excluded. {caption}">
  <style>
    text {{ font-size: 11px; }}
    .title {{ font-size: 13px; font-weight: 600; fill: #1f2328; }}
    .dim   {{ fill: #59636e; }}
    .key   {{ fill: #59636e; font-size: 10px; }}
    .grid  {{ stroke: #d1d9e0; stroke-width: 1; }}
    .line  {{ fill: none; stroke: #2a78d6; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
    .area  {{ fill: #2a78d6; fill-opacity: .14; stroke: none; }}
    .dot   {{ fill: #2a78d6; }}
    @media (prefers-color-scheme: dark) {{
      .title {{ fill: #e6edf3; }} .dim, .key {{ fill: #9198a1; }} .grid {{ stroke: #2f3742; }}
      .line, .dot {{ stroke: #3987e5; fill: #3987e5; }} .line {{ fill: none; }}
      .area {{ fill: #3987e5; fill-opacity: .18; }}
    }}
  </style>
  <text x="{PAD_L}" y="22" class="title">{pkg} · installs from PyPI</text>
  <text x="{PAD_L}" y="38" class="dim">{caption}</text>
  {grid}
  {area}
  <polyline points="{pts(mean)}" class="line"/>
  {tip}
  {days}
  <text x="{WIDTH - PAD_R}" y="22" class="dim" text-anchor="end">mirrors excluded</text>
</svg>
'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package', default='taskuary')
    ap.add_argument('--history', default='docs/downloads.csv')
    ap.add_argument('--out', default='docs/downloads.svg')
    ap.add_argument('--from-json', help='a saved pypistats overall payload, instead of the network')
    ap.add_argument('--strict', action='store_true', help='fail on a fetch error instead of leaving the chart alone')
    a = ap.parse_args(argv)
    hist = Path(a.history)
    if a.from_json:
        new = series(json.loads(Path(a.from_json).read_text(encoding='utf-8')))
    else:
        try:
            new = fetch(a.package)
        except Exception as e:
            # a package with no downloads yet, or pypistats having a bad day, is not a reason to
            # paint the repository's checks red
            print(f'could not read pypistats for {a.package}: {e}', file=sys.stderr)
            if a.strict: return 1
            # ...and the days already kept are still the chart: drawing nothing left the publish step without its file,
            # which reddened the workflow anyway (2026-10-01)
            new = []
    rows = merge(read_history(hist), new)
    if not rows:
        print('nothing to chart yet'); return 0
    write_history(hist, rows)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg(rows, a.package), encoding='utf-8')
    t = totals(rows)
    print(f'{len(rows)} days · {t["last_day"]} today · {t["last_week"]} this week · {t["last_month"]} this month')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

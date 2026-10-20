"""A reopened pane, the wrap-up and the seed check all read the session through pyte's HistoryScreen. terminal.py drives
it without the per-attribute hook HistoryScreen adds for paging - 60% of the draw - and these hold the two to the SAME
screen, history and cursor on every kind of stream a CLI paints, so the speed never changes what a pane shows."""
import random, time
import pyte
from taskuary import terminal

E = '\x1b'

def _tui(r, n):
    out = ''
    while len(out) < n:
        out += ''.join(f'{E}[{y};1H{E}[38;5;{r.randint(1, 250)}m' + ''.join(r.choice('abc def→✓') for _ in range(r.randint(5, 120)))
                       + f'{E}[0m{E}[K' for y in range(1, 33))
    return out[:n]

def _fuzz(r, n):
    toks = [lambda: ''.join(r.choice('abcxyz 012') for _ in range(r.randint(1, 30))), lambda: f'{E}[{r.randint(1, 40)};{r.randint(1, 130)}H',
            lambda: f'{E}[{r.randint(0, 9)}{r.choice("ABCDGdEF")}', lambda: f'{E}[{r.choice(["0", "1", "2", "3", ""])}J',
            lambda: f'{E}[{r.choice(["0", "1", "2", ""])}K', lambda: f'{E}[{r.randint(0, 4)};{r.randint(30, 37)}m',
            lambda: f'{E}[{r.randint(1, 10)};{r.randint(11, 40)}r', lambda: f'{E}D', lambda: f'{E}M', lambda: f'{E}[?1049{r.choice("hl")}',
            lambda: f'{E}[?7{r.choice("hl")}', lambda: '中文' * r.randint(1, 4), lambda: '\t', lambda: '\b', lambda: '\r\n', lambda: '\n',
            lambda: f'{E}[{r.randint(1, 5)}{r.choice("LMP@X")}', lambda: f'{E}[{r.randint(1, 5)}{r.choice("ST")}', lambda: f'{E}7', lambda: f'{E}8']
    out = ''
    while len(out) < n: out += r.choice(toks)()
    return out

def _scroll(r, n):
    out = ''
    while len(out) < n: out += ''.join(r.choice('abc def') for _ in range(r.randint(0, 150))) + '\r\n'
    return out[:n]

STREAMS = [_tui(random.Random(1), 30_000), _scroll(random.Random(2), 40_000)] + [_fuzz(random.Random(10 + i), 4_000) for i in range(25)]


def _plain_pyte(raw, cols, rows):
    """render_at as it was before the fast screen: pyte's own HistoryScreen, every cell read through the row map."""
    sc = pyte.HistoryScreen(cols, rows, history=terminal.HISTORY_LINES, ratio=1.0)
    pyte.Stream(sc).feed(raw)
    line = lambda r: r.rstrip() if isinstance(r, str) else ''.join(r[x].data for x in range(sc.columns)).rstrip()
    top = list(sc.history.top)
    return '\n'.join(line(r) for r in top + list(sc.display)), len(top) + sc.cursor.y, sc.cursor.x


def test_the_fast_screen_draws_what_pytes_own_draws():
    for raw in STREAMS:
        for cols, rows in ((110, 32), (80, 24), (40, 4)):
            try: want = _plain_pyte(raw, cols, rows)
            except Exception: continue                # a stream pyte itself cannot draw takes plain() either way
            assert terminal.render_at(raw, cols, rows) == want


def test_a_replay_is_the_same_seed():
    class T:
        argv = ['claude']
        def __init__(s, raw, cols, rows): s.raw, s.cols, s.rows = raw, cols, rows
        def scrollback(s): return s.raw
    for raw in STREAMS[:6]:
        t = T(raw, 110, 32)
        text, cy, cx = _plain_pyte(raw, 110, 32)
        with __import__('unittest').mock.patch.object(terminal, 'render_at', lambda *a: (text, cy, cx)):
            want = terminal.replay_text(t)
        assert terminal.replay_text(t) == want


def test_the_fast_screen_is_cheaper():
    raw = _tui(random.Random(3), 60_000)
    def best(f):
        out = []
        for _ in range(3):
            a = time.perf_counter(); f(); out.append(time.perf_counter() - a)
        return min(out)
    slow, fast = best(lambda: _plain_pyte(raw, 110, 32)), best(lambda: terminal.render_at(raw, 110, 32))
    assert fast < slow * 0.8, (slow, fast)

"""A reopened pane must show the screen the CLI left - its input box and footer included - however long ago it was drawn.

The owner's pane, 2026-10-21: a Claude session 22 minutes into one PreToolUse hook, reopened, showed the spinner line and
under it a bare cursor and a stray number - no input box, no footer. A CLI that is only animating one line rewrites that
line and nothing else (Claude's diff renderer, Codex's absolute moves, ConPTY's cell diffs), so 22 minutes of spinner is
megabytes of output in which the input box was drawn ONCE, at the start. The pty kept the last 200 KB of raw bytes, the
box fell off the front, and the replay drew a screen from bytes that began mid-stream - cursor at the top, no box, and
whatever half an escape sequence the cut began with printed as text. These hold every CLI kind's pane to the screen a
terminal that saw the whole session shows, after far more output than the scrollback keeps, cut at arbitrary points."""
import random, re
import pyte
from taskuary import terminal

E, C = '\x1b', '\r\n'
COLS, ROWS = 100, 24
SPIN = '✻✽✶✷✸✹✺·'

def _history(n=60): return ''.join(f'{E}[2m⏺{E}[0m earlier answer line {i:03d} about the import and its batch date{C}' for i in range(n))

def _spinner(i): return f'{E}[38;2;215;119;87m{SPIN[i % 8]}{E}[39m Imagining… (running PreToolUse hook · {i // 10}s · ↓ 23.1k tokens)'

BOX = ['╭' + '─' * (COLS - 2) + '╮', '│ > ' + ' ' * (COLS - 5) + '│', '╰' + '─' * (COLS - 2) + '╯',
       '  ⏵⏵ bypass permissions on (shift+tab to cycle)']

def claude():
    """Inline, no alternate screen. After the first paint only the spinner row is rewritten, by RELATIVE moves from the
    input line the cursor sits on - inside synchronized-output brackets."""
    first = _history() + _spinner(0) + C + C + C.join(BOX) + f'{E}[2A{E}[5G'
    up = 2 + 1                                    # input row -> spinner row: the box top and the blank between
    return first, lambda i: f'{E}[?2026h{E}[{up}A\r{E}[2K{_spinner(i)}{E}[{up}B{E}[5G{E}[?2026l'

def codex():
    """An inline viewport at the bottom of the screen, every row placed by an ABSOLUTE move (ConPTY's output on Windows
    looks the same for every CLI)."""
    top = ROWS - 5
    first = _history() + C * 8 + ''.join(f'{E}[{top + k};1H{E}[2K{r}' for k, r in enumerate([_spinner(0), ''] + BOX)) + f'{E}[{top + 3};5H'
    return first, lambda i: f'{E}[?2026h{E}[{top};1H{E}[2K• Working ({i // 10}s • esc to interrupt){E}[{top + 3};5H{E}[?2026l'

def ink():
    """Ink's log-update (Copilot, Gemini/Qwen inline): every frame erases the whole dynamic region line by line and
    paints it again, input box included."""
    region = lambda i: C.join([_spinner(i), ''] + BOX)
    first = _history() + region(0)
    erase = (f'{E}[2K{E}[1A' * (len(BOX) + 1)) + f'{E}[2K{E}[G'
    return first, lambda i: erase + region(i)

def alt():
    """A full-screen TUI on the alternate screen (Gemini/Qwen with the alternate buffer on): the shell's history is
    behind it, the TUI is painted by absolute rows, then only its spinner row is touched."""
    rows = [f'{E}[{y + 1};1H{E}[2K{r}' for y, r in enumerate(['gemini - a stand-in', ''] + ['answer %d' % k for k in range(8)])]
    box = [f'{E}[{ROWS - 3 + k};1H{r}' for k, r in enumerate(BOX)]
    first = _history(30) + f'{E}[?1049h{E}[H{E}[2J' + ''.join(rows + box) + f'{E}[{ROWS - 2};5H'
    return first, lambda i: f'{E}[{ROWS - 5};1H{E}[2K{_spinner(i)}{E}[{ROWS - 2};5H'

KINDS = {'claude': claude, 'codex': codex, 'ink': ink}


def _term(rows=ROWS, cols=COLS):
    """The pump's half of a Term - the buffer and its counters - with no pty behind it."""
    t = object.__new__(terminal.Term)
    t.buf, t.n, t.writes, t.wrote_at, t.rows, t.cols, t.argv = terminal.deque(), 0, 0, 0.0, rows, cols, ['claude']
    return t

def _body(kind):
    """The whole session: the first paint, then spinner frames until it is three scrollbacks long."""
    first, step = (KINDS.get(kind) or alt)()
    body, i = first, 1
    while len(body) < 3 * terminal.SCROLLBACK: body += ''.join(step(k) for k in range(i, i + 500)); i += 500
    return body

def _run(kind, seed=1, read=4096):
    """Fed the way a pty read hands it over: cut anywhere, the middle of an escape sequence included."""
    body, r, t, i = _body(kind), random.Random(seed), _term(), 0
    while i < len(body):
        k = r.randint(1, read); t._append(body[i:i + k]); i += k
    return t, body

def _show(*parts):
    sc = pyte.Screen(COLS, ROWS); st = pyte.Stream(sc)
    for p in parts: st.feed(p)
    return [r.rstrip() for r in sc.display], (sc.cursor.y, sc.cursor.x)


def test_the_scrollback_is_bounded_and_starts_from_a_whole_screen():
    for kind in KINDS:
        t, body = _run(kind)
        assert len(body) > 2 * terminal.SCROLLBACK and t.n <= terminal.SCROLLBACK + 4096, (kind, t.n)
        assert t.n == len(t.scrollback())


def test_every_cli_kind_reopens_on_the_screen_it_left():
    for kind in KINDS:
        for seed in (1, 2):
            t, body = _run(kind, seed=seed)
            pane, truth = _show(terminal.replay_text(t)), _show(body)
            assert pane == truth, (kind, seed, '\n'.join(pane[0][-8:]), '\n'.join(truth[0][-8:]), pane[1], truth[1])
            assert '╰' in pane[0][-2] and 'bypass permissions on' in pane[0][-1], kind


def test_the_next_paint_lands_where_it_would_have():
    """The pane goes on taking the CLI's live output after the seed - relative moves from the cursor for Claude - so the
    cursor must be back on the input line, not wherever the replay ended."""
    for kind in KINDS:
        t, body = _run(kind)
        nxt = KINDS[kind]()[1](10 ** 6) + 'hello'
        assert _show(terminal.replay_text(t), nxt) == _show(body, nxt), kind


def test_no_half_escape_sequence_is_printed():
    """A cut through ESC[38;2;215;119;87m left '119;87m' - or digits like it - drawn as text at the top of the replay. The
    kept scrollback, read the way the wrap-up reads it, is the tail of what the whole session reads as - no line of its
    own. Cut with small reads, so a cut lands inside a sequence many times over."""
    for kind in KINDS:
        t, body = _run(kind, seed=7, read=40)
        got, want = (terminal.render(x, COLS, ROWS).split('\n') for x in (t.scrollback(), body))
        assert not re.search(r'\d+;\d+m', '\n'.join(got)) and want[-len(got):] == got, (kind, got[:3])


def test_a_full_screen_tui_on_the_alternate_screen_reopens_on_it():
    t, body = _run('alt')
    seed = terminal.replay_text(t)
    (pane, _) = _show(seed)
    assert 'gemini - a stand-in' in pane[0] and '╰' in pane[-2] and 'bypass permissions on' in pane[-1], '\n'.join(pane)
    # ...and when it quits, the shell's screen comes back, not the TUI's paint: a real xterm keeps the two apart
    sc = pyte.Screen(COLS, ROWS)
    vt = terminal._vt_screen(pyte)(COLS, ROWS, history=100, ratio=1.0)
    pyte.Stream(vt).feed(seed + f'{E}[?1049l')
    shown = [r.rstrip() for r in vt.display]
    assert any('earlier answer line 029' in r for r in shown) and not any('gemini - a stand-in' in r for r in shown), shown


def test_the_rest_of_the_screen_survives_folding_too():
    """A scroll region and a hidden cursor set before the cut are still in force after it."""
    t = _term()
    t._append(_history() + f'{E}[?25l{E}[3;{ROWS - 2}r{E}[{ROWS};1Hfooter')
    for i in range(3 * terminal.SCROLLBACK // 60): t._append(f'{E}[3;1H{_spinner(i)}')
    t._append(f'{E}[{ROWS - 2};1H' + 'new line' + C * 3)          # scrolls inside the region: the footer stays put
    vt = terminal._vt_screen(pyte)(COLS, ROWS, history=100, ratio=1.0)
    pyte.Stream(vt).feed(t.scrollback())
    assert vt.display[ROWS - 1].rstrip() == 'footer' and (pyte.modes.DECTCEM not in vt.mode)

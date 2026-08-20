"""A stand-in for a CLI agent's TUI, so the whole session lifecycle can be tested for real
against a real pty: seeding, submitting, scrollback, harvest, wrap-up.

It behaves the way the real ones do in the ways that have actually broken things:
  * a boxed welcome banner drawn in box glyphs
  * a spinner repainted with \\r, thousands of frames, carrying the token counter and the
    "esc to interrupt" hint - the chrome that used to drown the transcript
  * it only ECHOES a prompt once a full line arrives, so a prompt typed without its Enter
    produces no work at all - which is the bug this exists to catch
Run: python fake_tui.py [--lines N]
"""
import sys, time

SPIN = '✻✽✶✷✸✹✺'


def frames(n, label='Levitating'):
    for i in range(n):
        sys.stdout.write(f'\r\x1b[2K\x1b[36m{SPIN[i % len(SPIN)]}\x1b[0m {label}… '
                         f'({i}s · esc to interrupt · {1000 + i * 431} tokens)')
        sys.stdout.flush()
        time.sleep(0.002)
    sys.stdout.write('\r\x1b[2K')


def main():
    lines = int(sys.argv[sys.argv.index('--lines') + 1]) if '--lines' in sys.argv else 0
    print('\x1b[2m╭─────────────────────────────────────────╮\x1b[0m')
    print('\x1b[2m│\x1b[0m  \x1b[1mfake-tui\x1b[0m v1 · a stand-in agent      \x1b[2m│\x1b[0m')
    print('\x1b[2m╰─────────────────────────────────────────╯\x1b[0m')
    print('\x1b[2m? for shortcuts\x1b[0m')
    for i in range(lines):                      # a long session, for testing scrollback
        print(f'line {i:04d} of prior output — the quick brown fox jumps over the lazy dog')
    sys.stdout.write('\x1b[1m❯ \x1b[0m'); sys.stdout.flush()
    frames(300)
    for raw in sys.stdin:                       # a full LINE: no Enter, no work
        ask = raw.strip()
        if not ask: continue
        if ask in ('exit', 'quit'): break
        frames(400, 'Thinking')
        print(f'\x1b[32m⏺\x1b[0m Working on: {ask[:400]}')
        print('I read the payroll import and the GLBATCH header - the adjustment rows carry the '
              'date of the FIRST line, not the payroll date, so they post to the wrong month.')
        print('Fixed in run_pto_intacct.py: the batch date now comes from the payroll date field.')
        frames(600)
        sys.stdout.write('\x1b[1m❯ \x1b[0m'); sys.stdout.flush()
    print('bye')


if __name__ == '__main__':
    main()

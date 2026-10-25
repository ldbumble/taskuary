"""No gateway address is in this repository (the owner, 2026-10-16: the HIPAA AI card is public, blank; where its gateway lives
never is). Asserted as an invariant, not as a list of addresses to avoid: a guard that spells out what it guards against has
published it. The card ships no address, and every address within reach of a mention of it is a reserved name, a local one, a
placeholder, or a public endpoint the app already names for some other connection."""
import re, subprocess
from pathlib import Path

from taskuary import llm

ROOT = Path(__file__).resolve().parents[1]
URL = re.compile(r'https?://([^/\s"\'<>`)\]\\]+)')
NEAR, REACH = re.compile(r'hipaa', re.I), 3
SKIP = ('site/demo/', 'taskuary/web/', 'site/docs/search.json')      # built copies of files scanned at their source


def _reserved(host: str) -> bool:
    h = host.split(':')[0].strip('.').lower()
    return (h in ('localhost', '127.0.0.1', '0.0.0.0') or h.rsplit('.', 1)[-1] in ('example', 'test', 'invalid', 'localhost', 'internal')
            or h in ('example.com', 'example.net', 'example.org') or '{' in h or '.' not in h)


def _files():
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True).stdout.split('\n')
    for f in out:
        if not f or f.startswith(SKIP): continue
        try: yield f, (ROOT / f).read_text(encoding='utf-8').split('\n')
        except (UnicodeDecodeError, OSError): continue


def test_the_hipaa_card_ships_no_address():
    assert llm.HIPAA_AI_URL == '' and llm.OPENAI_COMPATIBLE['hipaa_ai'][0] == ''


def test_every_address_near_the_card_is_reserved_or_one_the_app_names_elsewhere():
    near, far = {}, set()
    for f, lines in _files():
        close = {j for i, l in enumerate(lines) if NEAR.search(l) for j in range(max(0, i - REACH), min(len(lines), i + REACH + 1))}
        for j, l in enumerate(lines):
            for h in URL.findall(l):
                h = h.lower()
                if j in close: near.setdefault(h, []).append(f'{f}:{j + 1}')
                else: far.add(h)
    # ...and the endpoints the other OpenAI-compatible cards ship, listed beside it in the one table they share
    shipped = {h.lower() for k, (base, _m) in llm.OPENAI_COMPATIBLE.items() if k != 'hipaa_ai' for h in URL.findall(base or '')}
    bad = {h: at for h, at in near.items() if not _reserved(h) and h not in far | shipped}
    assert not bad, f'an address near the HIPAA card that the app names nowhere else: {bad}'

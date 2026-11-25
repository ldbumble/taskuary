"""THE CONTRACT TESTS ARE THE OWNER'S (2026-11-25: "build a few code tests that it can never change"). tests/contract/LOCK holds the sha256
of every contract test file, of CLAUDE.md's section "The basic interactions (locked)" and of the shipped AGENTS.md; this fails the moment any of them differs. An agent
that needs one changed asks him - it never rewrites the test and its hash together.

With his written OK, the new hashes are printed by `python tests/test_contract_lock.py`."""
import hashlib, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT, LOCK, SECTION = ROOT / 'tests' / 'contract', ROOT / 'tests' / 'contract' / 'LOCK', 'The basic interactions (locked)'
SAYS = "contract tests are the owner's: change only with his written OK"


def _sha(text: str) -> str: return hashlib.sha256(text.replace('\r\n', '\n').encode('utf-8')).hexdigest()      # the same on every checkout
def section() -> str:
    "CLAUDE.md's locked section: its heading through to the next heading of its level or above."
    m = re.search(rf'^### {re.escape(SECTION)}\n.*?(?=^#{{1,3}} |\Z)', (ROOT / 'CLAUDE.md').read_text(encoding='utf-8').replace('\r\n', '\n'), re.S | re.M)
    return m[0].rstrip() + '\n' if m else ''
AGENTS = 'taskuary/templates/agents.md'     # ...and what every agent is told about cards (the owner, 2026-11-25: "never change it")
def now() -> dict:
    return {**{f'tests/contract/{p.name}': _sha(p.read_text(encoding='utf-8')) for p in sorted(CONTRACT.glob('*.py'))}, f'CLAUDE.md#{SECTION}': _sha(section()),
            AGENTS: _sha((ROOT / AGENTS).read_text(encoding='utf-8'))}
def locked() -> dict:
    return dict(reversed(l.split('  ', 1)) for l in LOCK.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#'))


def test_the_contract_is_as_the_owner_locked_it():
    assert section(), f"CLAUDE.md lost its section '{SECTION}' - {SAYS}"
    have, want = now(), locked()
    assert [k for k in have if k.startswith('tests/contract/test_')], f'tests/contract holds no tests - {SAYS}'
    changed = sorted(k for k in {*have, *want} if have.get(k) != want.get(k))
    assert not changed, f"{SAYS} - differs from tests/contract/LOCK: {', '.join(changed)}"


if __name__ == '__main__':
    print("# The owner's lock on the basic interactions: sha256 of each contract file and of CLAUDE.md's locked section.\n"
          f"# {SAYS} (tests/test_contract_lock.py).")
    for k, v in now().items(): print(f'{v}  {k}')

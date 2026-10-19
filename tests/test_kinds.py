"""WHO DOES A TASK, once (taskuary/kinds.json, read by kinds.py and website/src/kinds.js): the kinds, which an agent works, which
triage may name and every kind's words come from the one file - `('coding', 'general', 'task')` was typed in ten modules and the
picker's labels twice in the page with different hints (the cleanup round, 2026-10-18)."""
import json, re
from pathlib import Path

from taskuary import categories, kinds

ROOT = Path(kinds.__file__).resolve().parents[1]
J = json.loads((ROOT / 'taskuary' / 'kinds.json').read_text(encoding='utf-8'))


def test_the_json_is_the_table():
    assert kinds.KINDS == ('task', 'general', 'coding', 'reply') == tuple(k['key'] for k in J['kinds'])
    assert set(kinds.AGENT) == {'general', 'coding'} and set(kinds.TRIAGE) == {'task', 'general', 'coding'}
    assert [kinds.label(k) for k in kinds.KINDS] == [k['label'] for k in J['kinds']] and kinds.label('setup') == 'setup'
    assert (kinds.worker('coding'), kinds.worker('general'), kinds.worker(None)) == ('the coding agent', 'the assistant', 'the assistant')
    assert categories.agent_word is kinds.worker
    assert [kinds.triage_kind(k) for k in ('coding', 'GENERAL', 'reply', 'nonsense', None)] == ['coding', 'general', 'task', 'task', 'task']


def test_a_brain_is_a_tool_and_a_profile_is_instructions():
    """No kind is named for a worker's profile (the owner, 2026-10-15) - "coder" anywhere in the table is the old naming back."""
    assert 'coder' not in json.dumps(J).lower()


# the agent kinds or the triage kinds typed out by hand - ('coding', 'general'), ('task', 'general', 'coding'); a pair picked for
# its own reason (a demo's verdicts, the two kinds a correction counts as the same) is not the table
TUPLE = re.compile(r"\(('(?:task|general|coding|reply)'(?:, ?'(?:task|general|coding|reply)')+)\)")
def typed(line: str) -> bool:
    return any({w.strip(" '") for w in m.group(1).split(',')} in ({*kinds.AGENT}, {*kinds.TRIAGE}) for m in TUPLE.finditer(line.split('#')[0]))
def test_no_module_types_the_kinds():
    assert typed("if k in ('coding', 'general'):") and typed("x in ('task', 'general', 'coding')") and not typed("('task', 'reply')")
    hits = [f'{p.relative_to(ROOT)}:{n}: {line.strip()[:100]}' for p in sorted((ROOT / 'taskuary').rglob('*.py')) if p.name != 'kinds.py'
            for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1) if typed(line)]
    assert not hits, 'read the kinds from taskuary.kinds (AGENT / TRIAGE / KINDS):\n' + '\n'.join(hits)

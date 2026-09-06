"""Keep the acceptance inventory complete as implementation sections land."""
import json
import re
from pathlib import Path


def test_every_walkthrough_checkbox_has_unique_stable_ledger_entry():
    docs = Path(__file__).resolve().parents[1] / 'docs'
    todo = (docs / 'processing-walkthrough-todos.md').read_text(encoding='utf-8')
    checkboxes = re.findall(r'^- \[[ x]\] (.+)$', todo, re.MULTILINE)
    ids = re.findall(r'^- \[[ x]\] <a id="pw-\d+"></a>\*\*(PW-\d+)\*\*', todo, re.MULTILINE)
    ledger = json.loads((docs / 'processing-acceptance-ledger.json').read_text(encoding='utf-8'))
    rows = ledger['items']
    assert len(checkboxes) == len(ids) == len(set(ids))
    assert set(ids) == {row['id'] for row in rows}
    assert len(rows) == len(ids)
    rendered = (docs / 'processing-acceptance-ledger.md').read_text(encoding='utf-8')
    for row in rows:
        assert row['phase'] and row['test'] and row['commit'] and row['status']
        assert f"[{row['id']}](processing-walkthrough-todos.md#{row['id'].lower()})" in rendered
        if row['status'] in ('implemented', 'ci-verified'):
            assert row['commit'] != 'pending'
            assert not row['test'].startswith('Required:')


def test_browser_redesign_remains_outside_approved_implementation():
    docs = Path(__file__).resolve().parents[1] / 'docs'
    rows = json.loads((docs / 'processing-acceptance-ledger.json').read_text(encoding='utf-8'))['items']
    browser = [row for row in rows if row['section'] == 'Assistant browser control and its UI: review required']
    assert len(browser) == 3
    assert all(row['phase'] == 'pending' and row['status'] == 'review-pending' for row in browser)

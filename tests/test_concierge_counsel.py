"""COUNSEL loading must preserve the complete editable instructions."""
import re
from pathlib import Path
from unittest import mock

import pytest

from taskuary import concierge
from taskuary.store import MemoryStore


def test_full_counsel_reaches_system_without_modifying_saved_content():
    store = MemoryStore()
    content = '<!-- not instructions -->\n' + 'Owner instruction. ' * 250 + '\nFINAL REQUIRED RULE'
    store.save_doc('counsel', content, 'owner')
    expected = re.sub(r'<!--.*?-->', '', content, flags=re.S).strip()
    assert len(expected) > 3200
    assert concierge._counsel(store) == expected
    assert expected in concierge._system(store)
    assert store.get_doc('counsel') == content
    assert store.doc_owner('counsel') == 'owner'


@pytest.mark.parametrize('content', [None, '', '  \n', '<!-- only a comment -->'])
def test_missing_or_blank_counsel_restores_shipped_document(content):
    store = MemoryStore()
    store.save_doc('counsel', content, 'owner')
    template = (Path(concierge.__file__).parent / 'templates' / 'counsel.md').read_text(encoding='utf-8')
    loaded = concierge._counsel(store)
    assert store.get_doc('counsel') == template
    assert store.doc_owner('counsel') == 'template'
    assert loaded == re.sub(r'<!--.*?-->', '', store.doc('counsel'), flags=re.S).strip()
    assert '{{owner_first}}' not in loaded
    with mock.patch.object(store, 'save_doc') as save:
        assert concierge._counsel(store) == loaded
        save.assert_not_called()


@pytest.mark.parametrize('failure', [OSError('unavailable'), '<!-- empty default -->'])
def test_unusable_default_fails_explicitly_without_hidden_instructions(failure):
    store = MemoryStore()
    store.save_doc('counsel', '', 'owner')
    kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
    with mock.patch.object(Path, 'read_text', **kwargs):
        with pytest.raises(RuntimeError, match='Restore COUNSEL in Docs'):
            concierge._counsel(store)
    assert store.get_doc('counsel') == ''

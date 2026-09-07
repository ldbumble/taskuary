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


BEHAVIOUR = ['coder and setup are not the same road', 'Ignore it', 'polite request is not a question',
             'take the correction', 'Never ask for a password', "the owner's own sent mail"]


def test_the_chat_prompt_is_the_document_then_the_machine_contract_and_nothing_else():
    st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Speak like a pirate.\n', 'owner')
    system = concierge._system(st)
    assert system.startswith('# Mine')
    assert 'Speak like a pirate.' in system
    assert 'DECIDE: <verb>' in system and 'OPTIONS: first choice | second choice' in system
    for phrase in BEHAVIOUR:
        assert phrase not in concierge.CONTRACT, f'behavioural prose still hardcoded: {phrase}'
        assert phrase not in system, f'behaviour reached the prompt from somewhere other than the document: {phrase}'


def test_the_shipped_document_carries_the_deciding_rules_the_code_used_to():
    from pathlib import Path
    from taskuary import counsel
    text = (Path(concierge.__file__).parent / 'templates' / 'counsel.md').read_text(encoding='utf-8')
    body = counsel.sections(text)[counsel.DECIDING_HEAD]
    for phrase in ('coder and setup are not the same road', 'just this once | this kind from now on | everything from this sender',
                   'Never ask for a password', 'Never answer a correction by moving on'):
        assert phrase in body, phrase
    assert '<!-- counsel:deciding -->' in text


def test_the_contract_still_parses_every_verb_and_refuses_the_rest():
    for verb in concierge.VERBS:
        if verb == 'none': continue
        assert verb in concierge.CONTRACT, f'{verb} is a button the model must be able to name'
        assert concierge.parse_decision(f'Fine.\nDECIDE: {verb}')[1] == {'verb': verb, 'text': ''}
    assert concierge.parse_decision('Fine.\nDECIDE: launch_missiles')[1] is None
    assert concierge.parse_decision('Fine.\nDECIDE: not_ours ON: payroll portal outage')[1] == {'verb': 'not_ours', 'text': '', 'on': 'payroll portal outage'}

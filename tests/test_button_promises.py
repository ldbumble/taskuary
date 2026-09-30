"""A button's words are a promise. These pin the ones the action-row audit (2026-09-30) found saying less than the handler does:
the assistant's `approve` was described as "send the drafted reply" though on a close-out it merges first, and three chip words
(Save and end session, Mark done, Run it again) carried no sentence on hover at all."""
from taskuary import concierge, toolcatalog


def test_approve_says_a_close_out_merges_first():
    for text in (toolcatalog.DECISIONS['approve'], toolcatalog.PURPOSE['review.approve']):
        t = text.lower()
        assert 'merge' in t and 'first' in t, text
        assert 'close-out' in t, text


def test_approve_does_not_claim_to_continue_a_session():
    assert 'agent.continue' in toolcatalog.DECISIONS['approve']


def test_every_state_changing_chip_word_says_what_it_does():
    for verb in ('stop_agent', 'close', 'rerun', 'continue', 'defer', 'mine', 'regular_agent', 'not_ours'):
        assert concierge.CHIP_HINTS.get(verb), f'the {verb!r} chip has no sentence on hover'


def test_the_end_session_sentence_is_the_handlers():
    # concierge's stop_agent wraps only when there is a transcript to write from; the sentence must not promise a write-up unconditionally
    assert 'nothing to write up' in concierge.CHIP_HINTS['stop_agent']
    assert 'task stays open' in concierge.CHIP_HINTS['stop_agent']


def test_the_generated_docs_carry_the_same_sentence():
    import pathlib
    docs = (pathlib.Path(__file__).resolve().parent.parent / 'docs' / 'site' / 'assistant-tools.md').read_text(encoding='utf-8')
    assert 'FIRST' in docs and 'Send the drafted reply as it stands.' not in docs

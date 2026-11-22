"""A button's words are a promise. These pin the ones the action-row audit (2026-09-30) found saying less than the handler does:
the assistant's `approve` was described as "send the drafted reply" though on a close-out it merges first, and three chip words
(Stop and save, Mark done, Run it again) carried no sentence on hover at all."""
from taskuary import concierge, toolcatalog


def test_approve_says_a_finish_card_merges_first():
    for text in (toolcatalog.DECISIONS['approve'], toolcatalog.PURPOSE['review.approve']):
        t = text.lower()
        assert 'merge' in t and 'first' in t, text
        assert 'finish card' in t, text


def test_approve_does_not_claim_to_continue_a_session():
    assert 'agent.continue' in toolcatalog.DECISIONS['approve']


def test_every_state_changing_chip_word_says_what_it_does():
    for verb in ('stop_agent', 'close', 'rerun', 'continue', 'defer', 'mine', 'regular_agent', 'not_ours'):
        assert concierge.CHIP_HINTS.get(verb), f'the {verb!r} chip has no sentence on hover'


def test_the_end_session_sentence_is_the_handlers():
    # concierge's stop_agent wraps only when there is a transcript to write from; the sentence must not promise a write-up unconditionally
    # the hover is buttons.json's one sentence; the chat's own receipt says it when there is nothing to write up (propose_for)
    assert 'task stays open' in concierge.CHIP_HINTS['stop_agent']


def test_from_now_on_promises_only_the_kind_of_mail_that_was_pressed():
    # the press teaches one line about THIS KIND of mail from the sender (memorylines, 7803d97b5: "never everything they send, since another
    # kind from them may be real work") - the button, its hover, the Assistant's receipt and its tool sentence said "their mail is filed"
    from taskuary import buttons
    said = [dict(buttons.choices('not_ours'))['not_ours_sender'], buttons.hint('not_ours_sender'), concierge.RECEIPTS['not_ours_sender'],
            toolcatalog.DECISIONS['not_ours_sender'], toolcatalog.PURPOSE['preference.exclude_sender']]
    for text in said:
        t = text.lower()
        assert 'like this' in t or 'this kind of mail' in t, text
        assert 'everything from' not in t and 'their mail is filed' not in t, text

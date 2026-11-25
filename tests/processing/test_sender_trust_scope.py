import json
from taskuary.store import MemoryStore


MAILBOX = 'owner@northwind.example'
OTHER_MAILBOX = 'billing@northwind.example'
SENDER = 'rita@partner.example'
DEFAULT_SOURCE = object()


def incoming(store, *, mailbox=MAILBOX, sender=SENDER, channel='email', conversation='thread-1', source=True):
    return store.add_message({
        'ExternalId': f'in:{mailbox}:{sender}:{channel}:{conversation}',
        'Channel': channel,
        'SourceName': mailbox if source else None,
        'Subject': 'A request',
        'FromEmail': sender,
        'BodyText': 'Please take a look.',
        'Status': 'routed',
        'ConversationId': conversation,
        'SentAt': '2026-09-06 09:00:00',
    })


def owner_message(store, *, mailbox=MAILBOX, source=DEFAULT_SOURCE, channel='email', conversation='thread-1', to=SENDER):
    source_name = mailbox if source is DEFAULT_SOURCE else source
    return store.add_message({
        'RecipientsJson': json.dumps({'to': [to], 'cc': []}),
        'ExternalId': f'out:{mailbox}:{source_name}:{channel}:{conversation}',
        'Channel': channel,
        'SourceName': source_name,
        'Subject': 'Re: A request',
        'FromEmail': mailbox,
        'BodyText': 'Here is my response.',
        'Status': 'context',
        'Direction': 'out',
        'ConversationId': conversation,
        'SentAt': '2026-09-06 09:05:00',
    })


def test_same_mailbox_review_is_local_sent_evidence():
    store = MemoryStore()
    reviewed = incoming(store, conversation='reviewed')
    store.add_review({'MessageId': reviewed, 'Kind': 'draft_reply', 'Status': 'approved'})

    assert store.wrote_to_locally(MAILBOX.upper(), SENDER.upper()) is True


def test_same_mailbox_owner_message_is_local_sent_evidence():
    store = MemoryStore()
    incoming(store, conversation='owner-context')
    owner_message(store, conversation='owner-context')

    assert store.wrote_to_locally(MAILBOX.upper(), SENDER.upper()) is True


def test_a_thread_the_sender_cites_is_no_evidence_he_wrote_to_them():
    "The red team, 2026-11-24 (T1a): a stranger's In-Reply-To named his thread with a colleague, and that alone made them 'written to before'."
    store = MemoryStore()
    owner_message(store, conversation='his-thread', to='erin@northwind.example')
    incoming(store, sender='attacker@evil.example', conversation='his-thread')
    assert store.wrote_to_locally(MAILBOX, 'attacker@evil.example') is False
    assert store.wrote_to_locally(MAILBOX, 'erin@northwind.example') is True


def test_a_thread_the_sender_cites_is_no_evidence_he_wrote_to_them():
    "The red team, 2026-11-24 (T1a): a stranger's In-Reply-To named his thread with a colleague, and that alone made them 'written to before'."
    store = MemoryStore()
    owner_message(store, conversation='his-thread', to='erin@northwind.example')
    incoming(store, sender='attacker@evil.example', conversation='his-thread')
    assert store.wrote_to_locally(MAILBOX, 'attacker@evil.example') is False
    assert store.wrote_to_locally(MAILBOX, 'erin@northwind.example') is True


def test_review_from_another_receiving_mailbox_cannot_authorize():
    store = MemoryStore()
    reviewed = incoming(store, mailbox=OTHER_MAILBOX)
    store.add_review({'MessageId': reviewed, 'Kind': 'draft_reply', 'Status': 'sent'})

    assert store.wrote_to_locally(MAILBOX, SENDER) is False
    assert store.wrote_to_locally(OTHER_MAILBOX, SENDER) is True


def test_missing_receiving_source_cannot_authorize_review_evidence():
    store = MemoryStore()
    reviewed = incoming(store, source=False)
    store.add_review({'MessageId': reviewed, 'Kind': 'draft_reply', 'Status': 'edited'})

    assert store.wrote_to_locally(MAILBOX, SENDER) is False


def test_cross_channel_or_other_mailbox_conversation_collision_cannot_authorize():
    store = MemoryStore()
    incoming(store, conversation='shared-channel')
    owner_message(store, channel='teams', conversation='shared-channel')
    incoming(store, conversation='shared-mailbox')
    owner_message(store, source=OTHER_MAILBOX, conversation='shared-mailbox')
    cross_channel_review = store.add_message({
        'ExternalId': 'teams-reviewed',
        'Channel': 'teams',
        'SourceName': MAILBOX,
        'FromEmail': SENDER,
        'Status': 'routed',
        'ConversationId': 'reviewed-in-teams',
    })
    store.add_review({'MessageId': cross_channel_review, 'Kind': 'draft_reply', 'Status': 'approved'})

    assert store.wrote_to_locally(MAILBOX, SENDER) is False


def test_missing_owner_message_source_cannot_authorize_conversation_evidence():
    store = MemoryStore()
    incoming(store, conversation='missing-owner-source')
    owner_message(store, source=None, conversation='missing-owner-source')

    assert store.wrote_to_locally(MAILBOX, SENDER) is False


def test_mailbox_and_sender_matches_are_exact_addresses():
    store = MemoryStore()
    reviewed = incoming(store, mailbox='owner+archive@northwind.example', sender='rita+archive@partner.example')
    store.add_review({'MessageId': reviewed, 'Kind': 'draft_reply', 'Status': 'approved'})

    assert store.wrote_to_locally(MAILBOX, 'rita@partner.example') is False
    assert store.wrote_to_locally('owner+archive@northwind.example', 'rita+archive@partner.example') is True


def test_excluded_message_cannot_supply_review_evidence():
    store = MemoryStore()
    reviewed = incoming(store)
    store.add_review({'MessageId': reviewed, 'Kind': 'draft_reply', 'Status': 'approved'})

    assert store.wrote_to_locally(MAILBOX, SENDER, exclude_mid=reviewed) is False


def test_a_quoted_local_part_stays_one_value_in_the_sent_items_search():
    "The red team, 2026-11-24 (T1b): '\" OR ALL TO \"@evil.example' reached SEARCH as more keys - OR ALL matched every sent mail."
    import shlex
    from unittest import mock
    from taskuary import imapmail, senders
    said = []
    class M:
        def select(self, box, readonly=True): return 'OK', [b'1']
        def search(self, charset, *keys): said.append(' '.join(keys)); return 'OK', [b'']
        def logout(self): pass
    evil = '" OR ALL TO "@evil.example'
    with mock.patch.object(imapmail, '_login', return_value=(M(), MAILBOX)):
        assert senders._imap_wrote_to({}, evil) is False
    assert shlex.split(said[0]) == ['TO', evil]
    assert senders.wrote_to(MemoryStore(), MAILBOX, evil) is False                 # ...and wrote_to asks neither server about it                  # IMAP quoting reads as POSIX double quotes: one key, one value
    assert imapmail._quoted('Sent Items') == '"Sent Items"' and imapmail._quoted('INBOX') == 'INBOX'

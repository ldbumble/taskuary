"""UI wake-ups (store._poke / one_poke): batched, deduplicated by content, and never a way to crash the poker."""
def test_a_nested_payload_poked_inside_a_batch_does_not_crash_the_poker():
    """The chat lane's poll ran while a settle held one_poke() on another thread. Its
    ingest-status poke carries a dict, and the held key was tuple(sorted(payload.items())) -
    a dict inside a dict key. The poll died with "unhashable type: 'dict'" and read nothing
    (whatsapp 2026-09-16, teams and telegram 2026-09-17); the traceback only appeared once the
    catch logged it. Held pokes are keyed by content, so the batch still shouts once per distinct
    wake-up, and content may nest."""
    from unittest import mock
    from taskuary.store import MemoryStore
    s = MemoryStore()
    sent = []
    with mock.patch('taskuary.live.emit', side_effect=lambda k, **p: sent.append((k, p))):
        with s.one_poke():
            s._poke('ingest-status', ingest={'state': 'running', 'what': 'syncing', 'lane': 'quick'})
            s._poke('ingest-status', ingest={'state': 'running', 'what': 'syncing', 'lane': 'quick'})   # same content: once
            s._poke('feed-changed', message_id=7)
    kinds = sorted(k for k, _ in sent)
    assert kinds == ['feed-changed', 'ingest-status'], sent
    assert next(p for k, p in sent if k == 'ingest-status')['ingest']['lane'] == 'quick'

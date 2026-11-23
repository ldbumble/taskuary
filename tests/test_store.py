

def test_a_task_search_never_holds_the_writers_lock(tmp_path):
    """His live app, 2026-11-23: triage searched tasks word by word under the writer's lock, 3-4 s each, and a press waited behind it."""
    import threading
    from taskuary.store import SQLiteStore
    s = SQLiteStore(str(tmp_path / 't.db'))
    s.create_task({'Title': 'Printer quotes for the office', 'Kind': 'general', 'Status': 'open'}, 'owner')
    took = []
    with s.lock:                      # the writer is busy for the whole search
        t = threading.Thread(target=lambda: took.append(s.list_tasks(None, q='printer', shown=True)))
        t.start(); t.join(5)
    assert took and took[0] and took[0][0]['Title'].startswith('Printer'), 'the search ran while the writer held its lock'

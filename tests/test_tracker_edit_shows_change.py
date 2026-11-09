# An edited PR or issue came in again whole, so the chat showed it twice in full (the owner, 2026-11-09): an edit shows what it added
from taskuary import ingest
from taskuary.store import MemoryStore

BASE = 'gh:northwind/portal#41'
V1 = '[pull request by erinblake - association: CONTRIBUTOR]\n## What & why\nAdds a dark theme.\n## Testing\nRan the node tests.'
V2 = V1 + '\nAlso keeps the choice after a reload.\n## Screenshots\nsee below'

def _msg(body): return {'external_id': BASE, 'channel': 'github', 'subject': 'northwind/portal#41 Dark theme', 'body': body, 'from_name': 'erinblake',
                        'from_email': 'erinblake@users.noreply.github.com', 'conversation_id': BASE, 'sent_at': '2026-11-09 12:55:00'}

def test_a_first_version_shows_whole_and_an_edit_shows_only_its_new_lines():
    s = MemoryStore()
    assert ingest.edited_words(s, BASE, V1) == ''
    ingest.ingest_tracker(s, _msg(V1), file_only=True)
    got = ingest.edited_words(s, BASE, V2)
    assert got.startswith('Edited') and 'keeps the choice after a reload' in got and 'Adds a dark theme' not in got
    ingest.ingest_tracker(s, _msg(V2), file_only=True)
    last = s.last_version(BASE)
    assert last['BodyText'] == V2 and 'Adds a dark theme' not in (last['OwnText'] or '')    # full words kept for triage; the chat shows the change

def test_an_edit_that_only_removes_lines_says_so():
    s = MemoryStore(); ingest.ingest_tracker(s, _msg(V2), file_only=True)
    assert 'nothing new' in ingest.edited_words(s, BASE, V1)

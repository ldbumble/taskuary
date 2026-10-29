"""Researching and laying out options is an agent's work; only paying or booking waits for the owner (B14, the email walk 2026-10-29).

A colleague asked the owner to book flights and a hotel and send the options. Triage judged it `task` - "only Alex can do it" - so
no agent started, although the agent the owner then started by hand came back with good options. The guide now says a booking is
two jobs: the research is general, the booking itself waits. Model guidance, no word list - and it reaches an install whose
TRIAGE.md still follows the guide (store's guide tracking), the way every guide line before it did."""
import hashlib, tempfile
from pathlib import Path

from taskuary import histgen, triage
from taskuary.store import SQLiteStore

LINE = '**Booking, buying or signing up is two jobs.**'
sha = lambda t: hashlib.sha256(t.strip().encode()).hexdigest()


def test_the_guide_says_research_is_general_and_only_the_booking_waits():
    g = ' '.join(triage.SHIPPED.split())
    assert LINE in g
    said = g.split(LINE, 1)[1].split('- **', 1)[0]
    assert 'is **general**' in said and 'Only paying or booking itself waits for the owner' in said
    # ...in the section that decides who does it, so a document that only takes the shape still reads it there
    assert g.index(LINE) > g.index('## 4. Who does it') and g.index(LINE) < g.index('## 5. Describing it')


def test_a_live_triage_doc_on_the_last_guide_takes_the_line():
    guide = (Path(triage.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
    before = '\n'.join(l for l in guide.splitlines() if LINE not in l)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = str(Path(d) / 't.db')
        s = SQLiteStore(db)
        s._exec("UPDATE doc SET Content=?, UpdatedBy='migration' WHERE Name='triage'",
                (histgen._splice(before, '_generated_\n- vendor newsletters', histgen.TITLES['triage']),))
        s._exec("UPDATE setting SET Value=? WHERE Name='triage_guide_sha'", (sha(before),)); s.close()
        s = SQLiteStore(db); doc = s.doc('triage'); s.close()
    assert LINE in doc and 'vendor newsletters' in doc

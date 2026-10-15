"""TRIAGE.md is the triage guide, and keeps following it (2026-10-09).

The guide replaced a patchwork of sentence swaps and code-written rules. A document carrying the generated "Learned
from your mail history" block differs from the template, so the plain untouched-template rule would have frozen it at
the first guide; it follows the guide while its guide part is still the one last put there, and never once edited."""
import hashlib, tempfile, unittest
from pathlib import Path

from taskuary import histgen, triage
from taskuary.store import SQLiteStore

HIST = '_generated 2026-08-30_\n\n### What history shows is ignorable\n- vendor newsletters'
sha = lambda t: hashlib.sha256(t.strip().encode()).hexdigest()


class GuideTracksTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.db = str(Path(self.dir.name) / 't.db')
        self.guide = (Path(triage.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')

    def tearDown(self): self.dir.cleanup()

    def _with(self, head, by, last=None):
        s = SQLiteStore(self.db)
        s._exec("UPDATE doc SET Content=?, UpdatedBy=? WHERE Name='triage'", (histgen._splice(head, HIST, histgen.TITLES['triage']), by))
        if last: s._exec("UPDATE setting SET Value=? WHERE Name='triage_guide_sha'", (sha(last),))
        s.close()
        s = SQLiteStore(self.db); doc = s.doc('triage'); s.close()
        return doc

    def test_a_shipped_guide_moves_on_with_the_template_and_keeps_the_history(self):
        old = 'Classify one inbound work message. (an earlier guide)'
        doc = self._with(old, 'histgen', last=old)
        self.assertIn('# How to triage what arrives', doc)
        self.assertNotIn('an earlier guide', doc)
        self.assertIn('vendor newsletters', doc)

    def test_an_edited_guide_is_left_as_it_was_edited(self):
        doc = self._with('My own way of triaging.', 'histgen', last='Classify one inbound work message. (an earlier guide)')
        self.assertIn('My own way of triaging.', doc)
        self.assertNotIn('# How to triage what arrives', doc)

    def _unprinted(self, by):
        """A guide put there before the fingerprint was kept: the 2026-10-09 migration wrote it and recorded no sha."""
        s = SQLiteStore(self.db); s._exec("DELETE FROM setting WHERE Name='triage_guide_sha'"); s.close()
        s = SQLiteStore(self.db)
        s._exec("UPDATE doc SET Content=?, UpdatedBy=? WHERE Name='triage'", (histgen._splice('A guide no fingerprint names.', HIST, histgen.TITLES['triage']), by))
        s._exec("DELETE FROM setting WHERE Name='triage_guide_sha'"); s.close()
        s = SQLiteStore(self.db); doc = s.doc('triage'); s.close()
        return doc

    def test_a_guide_the_migration_wrote_with_no_fingerprint_still_follows_the_guide(self):
        """The 10-09 migration put a guide there and kept no sha, so the install froze on it for good (2026-10-15): the
        last writer was the migration itself, so nobody has edited it since."""
        doc = self._unprinted('migration')
        self.assertIn('# How to triage what arrives', doc); self.assertNotIn('no fingerprint', doc); self.assertIn('vendor newsletters', doc)

    def test_an_unfingerprinted_guide_somebody_else_wrote_last_is_left(self):
        """histgen rewrites only the history block, so its name as the last writer can sit over an owner's edit."""
        self.assertIn('no fingerprint', self._unprinted('histgen'))

    def test_the_owners_document_is_never_touched(self):
        doc = self._with('Classify one inbound work message. (an earlier guide)', 'owner', last='Classify one inbound work message. (an earlier guide)')
        self.assertIn('an earlier guide', doc)


if __name__ == '__main__':
    unittest.main()

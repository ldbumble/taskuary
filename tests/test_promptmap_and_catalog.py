""""Map it out for me - what is the full prompt, by source?" had no answer short of reading the
code that assembles it. These cover the three things that answer it: the prompt map, the AWS
catalog behind the service/operation pickers, and the version the header reports.
"""
import re
import unittest
from pathlib import Path

import taskuary
from fastapi.testclient import TestClient
from taskuary import promptmap, server
from taskuary.store import MemoryStore

c = TestClient(server.app)


def _loaded():
    s = MemoryStore()
    s.save_doc('soul', 'You work for **Test Owner**.\nSOULMARK', 'owner')
    s.save_doc('coder', '# rules\n- CODERMARK', 'owner')
    s.save_doc('style', '### Tone\n- STYLEMARK: two sentences, answer first, never a preamble.', 'owner')
    s.add_memory({'Scope': 'global', 'ScopeKey': None, 'Note': 'NOTEMARK defer to finance',
                  'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner'})
    tid = s.create_task({'Title': 'the importer crashed', 'Kind': 'coding', 'Source': 'email'}, 'test')
    s.add_message({'TaskId': tid, 'ExternalId': 'p1', 'Channel': 'email', 'Subject': 'importer crashed',
                   'FromName': 'Dana', 'FromEmail': 'dana@vendor.com', 'SourceName': 'me@ours.com',
                   'BodyText': 'traceback (most recent call last) - please fix the export',
                   'SentAt': '2026-08-25 09:00:00', 'Status': 'routed'})
    return s, tid


class PromptMapTests(unittest.TestCase):
    def test_all_three_prompts_are_shown_and_every_block_names_its_source(self):
        s, _tid = _loaded()
        out = promptmap.render(s)
        for heading in ('1. TRIAGE', '2. THE REPLY WRITER', '3. THE CODING AGENT'):
            self.assertIn(heading, out)
        # a block with no provenance is the thing this exists to replace
        blocks = out.count('┌─ ')
        self.assertEqual(blocks, out.count('│  source: '))
        self.assertGreater(blocks, 8)
        self.assertIn('characters', out)          # the size of each block, so bloat is visible

    def test_the_real_document_text_is_in_it_attributed_to_the_right_document(self):
        s, _tid = _loaded()
        out = promptmap.render(s)
        for mark, doc in (('SOULMARK', 'SOUL.md'), ('STYLEMARK', 'STYLE.md'), ('CODERMARK', 'CODER.md')):
            self.assertIn(mark, out, f'{doc} text never appears')
        # the block header naming the doc must come BEFORE its text, or the map attributes wrongly
        self.assertLess(out.index('SOUL.md'), out.index('SOULMARK'))
        self.assertIn('NOTEMARK', out)                       # standing notes are shown too
        self.assertIn('memory table', out)

    def test_it_says_which_prompt_the_message_is_the_user_turn_of(self):
        """The system/user split is the part people get wrong when reading a prompt dump."""
        s, _tid = _loaded()
        out = promptmap.render(s)
        self.assertIn('USER turn', out)
        self.assertIn('everything above is SYSTEM', out)

    def test_an_empty_machine_says_so_instead_of_raising(self):
        out = promptmap.render(MemoryStore())
        self.assertIn('sync first', out)


def _has_botocore():
    try:
        import botocore.session          # noqa: F401 - boto3 is an optional extra ([aws])
        return True
    except ImportError:
        return False


@unittest.skipUnless(_has_botocore(), 'boto3/botocore is an optional extra - not installed here')
class AwsCatalogTests(unittest.TestCase):
    """The service and operation fields were free text with an example in the placeholder, so a
    wrong name was only discovered when a scheduled report failed."""
    def test_services_come_back_without_calling_aws(self):
        d = c.get('/api/aws/catalog').json()
        self.assertIn('s3', d['services'])
        self.assertIn('logs', d['services'])
        self.assertGreater(len(d['services']), 100)

    def test_operations_are_real_boto3_names_with_the_reads_marked(self):
        d = c.get('/api/aws/catalog', params={'service': 's3'}).json()
        self.assertIn('list_buckets', d['operations'])        # snake_case, as run_aws calls it
        self.assertIn('list_buckets', d['read'])
        self.assertIn('delete_bucket', d['operations'])       # offered, but not as a read
        self.assertNotIn('delete_bucket', d['read'])
        self.assertLess(d['operations'].index('list_buckets'),
                        d['operations'].index('delete_bucket'))   # reads sort first

    def test_the_services_this_account_actually_uses_are_flagged(self):
        """A 430-name alphabetical list is a haystack; what discovery found is the short list."""
        server.store.save_source({'Channel': 'aws', 'Address': 's3://some-bucket', 'Active': 1,
                                  'ConfigJson': '{"mode": "report", "region": "us-east-1"}'}, 'test')
        self.assertIn('s3', c.get('/api/aws/catalog').json()['seen'])

    def test_the_discovered_log_groups_and_buckets_come_back_to_be_picked(self):
        """"Don't you have to choose which log?" - yes, and typing "/aws/lambda/whatever" from
        memory is the same trap as typing an operation name: a log group that does not exist
        answers with an empty report rather than an error."""
        for addr in ('logs:///aws/lambda/ingest', 's3://reports-bucket'):
            server.store.save_source({'Channel': 'aws', 'Address': addr, 'Active': 1,
                                      'ConfigJson': '{"mode": "report", "region": "us-east-1"}'}, 'test')
        d = c.get('/api/aws/catalog').json()
        self.assertIn('/aws/lambda/ingest', d['log_groups'])       # the scheme prefix is stripped
        self.assertIn('reports-bucket', d['buckets'])

    def test_a_bad_service_name_answers_instead_of_exploding(self):
        d = c.get('/api/aws/catalog', params={'service': 'nonsense'}).json()
        self.assertEqual(d['operations'], [])
        self.assertIn('Unknown service', d.get('error', ''))


class VersionTests(unittest.TestCase):
    def test_the_reported_version_is_the_one_pyproject_declares(self):
        """It said 0.2.0 for the whole of 0.2.1 - a second hardcoded copy - and the header's own
        tooltip told the owner to restart, which reloaded the same stale string."""
        want = re.search(r'^version\s*=\s*"([^"]+)"',
                         (Path(__file__).parent.parent / 'pyproject.toml').read_text(encoding='utf-8'),
                         re.M).group(1)
        self.assertTrue(taskuary.__version__.startswith(want),
                        f'{taskuary.__version__} does not match pyproject {want}')
        self.assertEqual(c.get('/api/version').json()['version'], taskuary.__version__)


if __name__ == '__main__':
    unittest.main()

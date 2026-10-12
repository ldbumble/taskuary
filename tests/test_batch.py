"""One task per batch (batch.py): a ranked repository's head comes in as ONE task whose items an agent works top-down
(the owner, 2026-10-12: "they should all come in as one task and the agent will process them one by one picking the
most valuable one first"). Invented repositories only; no model, no pty."""
import json, unittest
from unittest import mock

from taskuary import batch, channels, ingest, rank
from taskuary.store import MemoryStore


def ranked(s, ctype='github'):
    c = s.get_connector_by_type(ctype)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')


def pr(s, repo, n, value, title=None):
    mid = s.add_message({'ExternalId': f'gh:{repo}#{n}@r1', 'ConversationId': f'gh:{repo}#{n}', 'Channel': 'github',
                         'SourceName': repo, 'Subject': f'{repo}#{n} {title or f"change {n}"}', 'FromName': 'dev',
                         'FromEmail': 'dev@users.noreply.github.com', 'SentAt': '2026-10-12 07:00:00',
                         'BodyText': f'[pull request by dev - association: CONTRIBUTOR]\nfixes {n}',
                         'SourceLink': f'https://github.com/{repo}/pull/{n}', 'Status': 'triaging'})
    s.set_message_rank(mid, value, 'floor', 'rank')
    return mid


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); ranked(self.s)
        self.judged = []
        def judge(s, m, **k): self.judged.append(m['_mid']); s.place_message(m['_mid'], None, 'filed')
        self.p = [mock.patch.object(ingest, 'ingest_message', side_effect=judge), mock.patch.object(batch, '_next')]
        for p in self.p: p.start()

    def tearDown(self):
        for p in self.p: p.stop()

    def drain(self):
        with mock.patch.object(rank, 'rank_pending', return_value=0): ingest.drain(self.s)

    def batch_of(self, repo): return self.s.open_batch(batch.source_ref('github', repo))

    def test_a_repositorys_head_comes_in_as_one_task_in_ranked_order(self):
        for n, v in enumerate((0.2, 0.9, 0.5, 0.7, 0.1, 0.6), 170): pr(self.s, 'northwind/portal', n, v)
        self.drain()
        tid = self.batch_of('northwind/portal')
        self.assertIsNotNone(tid)
        self.assertEqual(self.s.get_task(tid)['Title'], '4 pull requests on northwind/portal')
        its = batch.items(self.s, tid)
        self.assertEqual([i['ConversationId'] for i in its], [f'gh:northwind/portal#{n}' for n in (171, 173, 175, 172)])
        self.assertEqual([i['Place'] for i in its], [1, 2, 3, 4])
        self.assertEqual(its[0]['Title'], '#171 change 171', 'the repository is the task title, not every line')
        self.assertEqual(self.judged, [], 'nothing in a batch is triaged one by one')
        self.assertEqual(len(self.s.pending_triage()), 2, 'the rest wait for the next batch')

    def test_a_batch_is_one_repository(self):
        for n, v in enumerate((0.9, 0.8), 1): pr(self.s, 'northwind/portal', n, v)
        for n, v in enumerate((0.95, 0.1), 1): pr(self.s, 'northwind/ledger', n, v)
        self.drain()
        a, b = self.batch_of('northwind/portal'), self.batch_of('northwind/ledger')
        self.assertTrue(a and b and a != b)
        self.assertEqual({i['ConversationId'].split('#')[0] for i in batch.items(self.s, a)}, {'gh:northwind/portal'})

    def test_arrivals_while_a_batch_is_open_wait_for_the_next_one(self):
        for n in range(1, 5): pr(self.s, 'northwind/portal', n, 0.5)
        self.drain(); first = self.batch_of('northwind/portal')
        pr(self.s, 'northwind/portal', 9, 1.0)
        self.drain()
        self.assertEqual(len(batch.items(self.s, first)), 4, 'nothing joins an open batch')
        self.assertEqual([r['ConversationId'] for r in self.s.pending_triage()], ['gh:northwind/portal#9'])
        self.s.update_task(first, {'Status': 'done'}, 'owner')
        self.drain()
        nxt = self.batch_of('northwind/portal')
        self.assertNotEqual(nxt, first)
        self.assertEqual([i['ConversationId'] for i in batch.items(self.s, nxt)], ['gh:northwind/portal#9'])

    def test_mail_is_not_batched(self):
        ranked(self.s, 'outlook')
        for i in range(3):
            m = self.s.add_message({'ExternalId': f'e{i}', 'ConversationId': f'c{i}', 'Channel': 'email', 'Subject': f'mail {i}',
                                    'FromName': 'Erin', 'SentAt': '2026-10-12 07:00:00', 'Status': 'triaging'})
            self.s.set_message_rank(m, 0.5, 'floor', 'rank')
        self.drain()
        self.assertEqual(len(self.judged), 3, 'each mail is triaged on its own, as before')

    def test_done_on_the_batch_settles_every_line(self):
        for n in range(1, 4): pr(self.s, 'northwind/portal', n, 0.5)
        self.drain(); tid = self.batch_of('northwind/portal')
        self.s.update_task(tid, {'Status': 'done'}, 'owner')
        self.assertEqual({i['State'] for i in batch.items(self.s, tid)}, {'done'})


class ItemEndingTests(unittest.TestCase):
    """A pull request merged upstream used to close the task it was on. On a batch that would end three items nobody had
    looked at: it settles its own line, and the batch closes when no line is left."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', n, 0.5))
                                                                        for n in (1, 2)])
        self.nx = mock.patch.object(batch, '_next'); self.nx.start()

    def tearDown(self): self.nx.stop()

    def end(self, n):
        channels._gh_ended(self.s, {'number': n, 'state': 'closed', 'pull_request': {'merged_at': '2026-10-12T09:00:00Z'}},
                           f'gh:northwind/portal#{n}', 'northwind/portal')

    def test_one_merge_settles_its_line_and_the_batch_stays_open(self):
        self.end(1)
        its = {i['ConversationId']: i for i in batch.items(self.s, self.tid)}
        self.assertEqual(its['gh:northwind/portal#1']['State'], 'ended')
        self.assertIn('merged', its['gh:northwind/portal#1']['EndedWhy'])
        self.assertEqual(its['gh:northwind/portal#2']['State'], 'waiting')
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(channels.heal_upstream_ended(self.s), [], "one item's ending is not the batch's")

    def test_the_last_one_closes_the_batch(self):
        self.end(1); self.end(2)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        batch._next.assert_called_once()

    def test_a_comment_on_an_item_opens_its_line_and_makes_no_task(self):
        batch.set_item(self.s, self.tid, 'gh:northwind/portal#2', State='needs_you', Result='Looks right; ready to merge.')
        before = len(self.s.list_tasks(active_only=False))
        out = ingest.ingest_message(self.s, {'external_id': 'gh:northwind/portal#2:c7', 'channel': 'github',
                                             'conversation_id': 'gh:northwind/portal#2', 'subject': 'Re: change 2',
                                             'body': 'pushed a fix for the review note', 'from_name': 'dev',
                                             'from_email': 'dev@users.noreply.github.com', 'source_name': 'northwind/portal'})
        self.assertEqual(out['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks(active_only=False)), before)
        it = self.s.batch_item(self.tid, 'gh:northwind/portal#2')
        self.assertEqual(it['State'], 'waiting')
        self.assertIn('dev wrote on it since', it['Result'])
        self.assertIn('ready to merge', it['Result'], 'what the agent said before is kept')

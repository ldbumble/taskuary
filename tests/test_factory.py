"""The named pictures stay true: a JOIN rewrite that drops a chip fails here.

These are the regression fixtures. Each picture is one Timeline/Board state the
owner can actually see. They run on MemoryStore (the suite) and on a file
(WAL, second connection, load shape).
"""
import json, os, tempfile, unittest
from unittest import mock
from taskuary.reports import is_due
from taskuary.store import SQLiteStore
from taskuary.testing import Factory, inbound, main


def _file_fx():
    path = os.path.join(tempfile.mkdtemp(), 't.db')
    return Factory(SQLiteStore(path)), path


class InboundTests(unittest.TestCase):
    def test_unique_ids_and_overrides(self):
        a, b = inbound(), inbound(external_id='keep', body='hi')
        self.assertNotEqual(a['external_id'], b['external_id'])
        self.assertEqual((b['external_id'], b['body']), ('keep', 'hi'))
        self.assertEqual(a['body'], 'please add the new user to the system')


class PictureTests(unittest.TestCase):
    def setUp(self):
        self.fx = Factory()

    def test_pending_draft_is_on_you_with_a_review_chip(self):
        p = self.fx.pending_draft()
        row = self.fx.row(p)
        self.assertEqual((row['NeedsYou'], row['ReviewStatus'], row['Decision']), (1, 'pending', 'create'))
        self.assertEqual(self.fx.s.list_reviews('pending')[0]['ReviewId'], p.rid)

    def test_held_draft_leaves_the_queue_and_stays_held(self):
        p = self.fx.held_draft()
        self.assertEqual(self.fx.s.get_review(p.rid)['Status'], 'held')
        self.assertEqual(self.fx.s.list_reviews('pending'), [])

    def test_rejecting_the_picture_flips_the_chip_and_the_tag(self):
        p = self.fx.pending_draft()
        a = self.fx.s.feed_tag()
        self.fx.s.decide_review(p.rid, 'rejected', '', 't')
        self.assertEqual(self.fx.row(p)['ReviewStatus'], 'rejected')
        self.assertNotEqual(a, self.fx.s.feed_tag())

    def test_approved_done_is_today_on_the_board_and_not_on_you(self):
        p = self.fx.approved_done()
        self.assertEqual(self.fx.row(p)['NeedsYou'], 0)
        self.assertIn(p.tid, {t['TaskId'] for t in self.fx.s.list_tasks(active_only=True)})

    def test_old_done_and_dropped_leave_the_board(self):
        live = self.fx.open_task()
        today = self.fx.approved_done()
        old = self.fx.old_done()
        dropped = self.fx.dropped()
        ids = {t['TaskId'] for t in self.fx.s.list_tasks(active_only=True)}
        self.assertEqual(ids, {live.tid, today.tid})
        all_ids = {t['TaskId'] for t in self.fx.s.list_tasks()}
        self.assertTrue({old.tid, dropped.tid} <= all_ids)

    def test_running_agent_clears_needs_you(self):
        p = self.fx.running()
        self.assertEqual(self.fx.row(p)['NeedsYou'], 0)
        self.assertEqual(self.fx.s.list_tasks()[0]['RunStatus'], 'running')

    def test_filed_fyi_and_ignored_and_feed_never_open_a_task(self):
        fyi, ign, feed = self.fx.filed_fyi(), self.fx.ignored(), self.fx.feed_only()
        self.assertEqual((self.fx.row(fyi)['Decision'], self.fx.row(fyi)['TaskId']), ('file', None))
        self.assertEqual(self.fx.row(ign)['MsgStatus'], 'ignored')
        self.assertEqual(self.fx.row(feed)['MsgStatus'], 'feed')

    def test_report_is_a_filed_row_on_the_report_channel(self):
        p = self.fx.report_row()
        row = self.fx.row(p)
        self.assertEqual((row['Channel'], row['Decision'], row['NeedsYou']), ('report', 'file', 0))

    def test_report_source_is_not_due_after_the_picture(self):
        p = self.fx.report_row()
        src = self.fx.s.get_source(p.sid)
        self.assertTrue(src['LastPolledAt'])
        self.assertFalse(is_due(json.loads(src['ConfigJson']), src['LastPolledAt'], startup=True))

    def test_omitted_from_email_and_draft_stay_null(self):
        mid = self.fx.message()
        self.assertIsNone(self.fx.s.get_message(mid).get('FromEmail'))
        rid = self.fx.review(self.fx.task())
        self.assertIsNone(self.fx.s.get_review(rid).get('DraftText'))
        p = self.fx.pending_draft()
        self.assertEqual(self.fx.s.get_review(p.rid)['DraftText'], 'Hi - done.')

    def test_auto_reply_wears_the_auto_chip(self):
        p = self.fx.auto_replied()
        self.assertEqual(self.fx.row(p)['ReviewStatus'], 'auto')

    def test_messenger_draft_is_a_pending_reply_on_that_channel(self):
        p = self.fx.messenger('whatsapp')
        row = self.fx.row(p)
        self.assertEqual((row['Channel'], row['ReviewStatus']), ('whatsapp', 'pending'))

    def test_thread_chain_size_counts_the_follow_ups(self):
        p = self.fx.thread(n=3)
        self.assertEqual(self.fx.row(p)['ChainSize'], 3)
        self.assertEqual(len(self.fx.s.list_messages(p.tid)), 3)

    def test_attachment_and_follow_up_land_on_the_pending_row(self):
        p = self.fx.with_attachment()
        row = self.fx.row(p)
        self.assertEqual((row['Attachments'], row['ChainSize'], row['ReviewStatus']), (1, 2, 'pending'))

    def test_behind_waits_on_the_running_task(self):
        p = self.fx.behind()
        q = self.fx.s.queued_dispatches()
        self.assertEqual((q[0]['TaskId'], q[0]['BehindTaskId']), (p.tid, p.behind.tid))

    def test_waitroom_note_is_undelivered_on_the_running_task(self):
        p = self.fx.waitroom_note()
        self.assertEqual(self.fx.s.waiting_notes(p.tid)[0]['WId'], p.wid)

    def test_handover_note_beats_a_later_ordinary_comment(self):
        p = self.fx.handover()
        row = self.fx.s.list_tasks()[0]
        self.assertEqual((row['ReviewStatus'], row['RunAgent']), ('pending', 'codex'))
        self.assertIn('HANDOVER NOTE', row['HandoverNote'])

    def test_late_pending_on_a_done_task_is_gone_from_the_queue(self):
        p = self.fx.late_pending_on_done()
        self.assertEqual(self.fx.s.list_reviews('pending'), [])
        self.assertEqual(self.fx.s.pending_review(p.tid), None)
        self.assertEqual(self.fx.s.pending_review(p.tid, live_only=False)['ReviewId'], p.rid)

    def test_skipped_mail_drops_the_pending_badge(self):
        p = self.fx.skipped_pending()
        self.assertEqual(self.fx.s.list_reviews('pending'), [])
        self.fx.s.set_message_status(p.mid, 'routed')
        self.assertEqual(len(self.fx.s.list_reviews('pending')), 1)


class TimelineDeskTests(unittest.TestCase):
    """The four-row picture the JOIN tests pin. A rewrite that changes chips fails here."""

    def test_chips_match_the_latest_route_review_and_run(self):
        fx = Factory()
        d = fx.timeline()
        by = {r['MessageId']: r for r in fx.s.feed(limit=20)}
        self.assertEqual(by[d.open]['Decision'], 'create')
        self.assertEqual(by[d.open]['ReviewStatus'], 'pending')
        self.assertEqual(by[d.open]['NeedsYou'], 1)
        self.assertEqual(by[d.open]['Attachments'], 1)
        self.assertEqual(by[d.open]['ChainSize'], 2)
        self.assertEqual(by[d.done_mid]['NeedsYou'], 0)
        self.assertEqual(by[d.done_mid]['ReviewStatus'], 'approved')
        self.assertEqual(by[d.busy_mid]['NeedsYou'], 0)
        self.assertEqual(by[d.fyi_mid]['Decision'], 'file')
        self.assertEqual(by[d.fyi_mid]['ChainSize'], 0)
        pending = {r['MessageId'] for r in fx.s.feed(pending_only=True)}
        self.assertIn(d.open, pending)
        self.assertNotIn(d.done_mid, pending)
        self.assertNotIn(d.busy_mid, pending)
        self.assertNotIn(d.fyi_mid, pending)
        self.assertEqual(len(pending), 2)   # the follow-up on the open task is on you too

    def test_the_full_desk_has_every_named_picture(self):
        fx = Factory()
        d = fx.desk()
        self.assertGreaterEqual(len(d), 20)
        self.assertTrue(fx.s.feed(limit=100))

    def test_desk_stamps_every_report_source(self):
        fx, path = _file_fx()
        fx.desk()
        reports = [s for s in fx.s.list_sources() if s['Channel'] == 'report']
        self.assertGreaterEqual(len(reports), 3)  # census picture + digest + automate
        for src in reports:
            self.assertTrue(src['LastPolledAt'], src['Address'])
            self.assertFalse(is_due(json.loads(src['ConfigJson'] or '{}'), src['LastPolledAt'], startup=True))
        fx.s.cx.close()


class FileAndLoadTests(unittest.TestCase):
    def test_pictures_survive_a_file_backed_store(self):
        fx, path = _file_fx()
        p = fx.pending_draft()
        fx.s.cx.close()
        fx2 = Factory(SQLiteStore(path))
        row = next(r for r in fx2.s.feed() if r['MessageId'] == p.mid)
        self.assertEqual(row['ReviewStatus'], 'pending')
        fx2.s.cx.close()

    def test_fill_is_the_live_mix_not_one_kind_of_row(self):
        fx = Factory()
        fx.fill(16)
        rows = fx.s.feed(limit=50)
        self.assertGreaterEqual(len(rows), 16)
        self.assertGreater(len({r['MsgStatus'] for r in rows}), 1)
        self.assertTrue(any(r['NeedsYou'] for r in rows))
        self.assertTrue(any(not r['NeedsYou'] for r in rows))

    def test_cli_help_is_offline(self):
        self.assertEqual(main(['help']), 0)
        self.assertEqual(main(['nope']), 2)

    def test_cli_refuses_a_home_that_already_has_tasks(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {'TASKUARY_HOME': home}):
            self.assertEqual(main(['desk']), 0)
            self.assertEqual(main(['desk']), 1)
            self.assertEqual(main(['load', '4']), 1)
            self.assertEqual(main(['desk', '--force']), 0)
            self.assertEqual(main(['--force', 'load', '4']), 0)


def test_the_fx_fixture_is_a_factory(fx):
    p = fx.pending_draft()
    assert fx.row(p)['ReviewStatus'] == 'pending'


if __name__ == '__main__':
    unittest.main()

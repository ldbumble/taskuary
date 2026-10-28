"""The Advisor's ideas after the 2026-09-27 decision map (C5, I1-I9): one set of words on every surface, each writing the
idea's own status; a thought put down stays down; one report's ideas never silence another's; an idea never reopens
finished work; and the rail keeps the rules the old one had."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import assistant, funnel, ingest, processing_unread
from taskuary.store import MemoryStore
import tests.test_appfacts as A


def ago(**kw): return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')


def _mail(s, subject='Q3 ledger', conv='c1'):
    return s.add_message({'ExternalId': f'x:{subject}', 'ConversationId': conv, 'Channel': 'email', 'Subject': subject,
                          'FromName': 'Erin Blake', 'FromEmail': 'erin@vendor.example', 'SentAt': ago(days=2),
                          'BodyText': 'Here is the ledger.', 'Status': 'filed'})


def _say(key, text='Erin still needs the reconciled ledger.', **kw):
    return json.dumps({'say': [{'key': key, 'text': text, 'why': 'she asked twice', **kw}]})


class FindingApartTests(unittest.TestCase):
    """The finding, whose move it is and what the Advisor would do, said apart (2026-10-09). One first-person line -
    "the fact and what I would do" - read as an order: triage made a task of "I'd read it through" on a mail sent to
    another team, and the card could not show what was true apart from what was advised."""
    def test_whose_move_and_the_suggestion_ride_on_the_idea_and_reach_triage(self):
        s = MemoryStore(); mid = _mail(s)
        [line] = assistant.parse(s, _say('idea:ops-review', text='Erin asked the Ops Team to review the P&Ls line by line.', mid=mid,
                                         whose='the Ops Team', suggest='Skim it once before Monday for anything aimed at you.'), [])
        self.assertEqual((line['action']['whose'], line['action']['suggest']), ('the Ops Team', 'Skim it once before Monday for anything aimed at you.'))
        i = s.upsert_idea(line, ago(minutes=1))
        msg, _, _ = assistant._idea_message(s, i, line['action'])
        # ...beside its words, never in them: the body is what a task made from it shows as the message (2026-10-28)
        self.assertEqual(msg['idea_context']['whose'], 'the Ops Team')
        self.assertTrue(msg['idea_context']['suggest'].startswith('Skim it once'))
        self.assertNotIn('whose move', msg['body'])

    def test_a_null_suggestion_is_no_suggestion(self):
        s = MemoryStore()
        [line] = assistant.parse(s, _say('idea:quiet', whose='nobody yet', suggest='null'), [])
        self.assertNotIn('suggest', line['action'])
        self.assertEqual(line['action']['whose'], 'nobody yet')

    def test_the_contract_asks_for_them_apart_from_the_finding(self):
        self.assertIn('"whose"', assistant.CONTRACT); self.assertIn('"suggest"', assistant.CONTRACT)
        self.assertNotIn('the fact and what I would do', assistant.CONTRACT)


class KeyTests(unittest.TestCase):
    def test_a_thought_put_down_keeps_its_key_under_a_new_slug(self):
        """I2: the same-subject key was looked up among OPEN ideas only, so a dismissed thought came back reworded."""
        s = MemoryStore(); mid = _mail(s)
        old = s.upsert_idea({'key': 'idea:ledger', 'kind': 'idea', 'text': 'Chase the ledger.', 'sig': 'x', 'action': {'mid': mid}}, ago(days=3))
        s.set_idea_status(old['IdeaId'], 'dismissed', 'owner')
        out = assistant.parse(s, _say('idea:ledger-again', mid=mid), [])
        self.assertEqual(out[0]['key'], 'idea:ledger')
        self.assertFalse(assistant.fresh({i['Key']: i for i in s.list_ideas()}, out[0], datetime.now()))

    def test_a_model_line_never_takes_a_follow_ups_key(self):
        """I3: it took the key, rewrote the follow-up as a model idea, and the follow-up re-raised itself every run."""
        s = MemoryStore(); mid = _mail(s)
        s.upsert_idea({'key': 'followup:c1', 'kind': 'followup', 'text': 'No answer in 4 days.', 'sig': 'a', 'action': {'mid': mid}}, ago(days=1))
        self.assertEqual(assistant.parse(s, _say('idea:chase', mid=mid), [])[0]['key'], 'idea:chase')

    def test_another_reports_idea_does_not_silence_the_advisors(self):
        """I8: the key remap and what was already said read across every report."""
        s = MemoryStore(); mid = _mail(s)
        s.upsert_idea({'key': 'report:99:idea:ledger', 'kind': 'idea', 'text': 'Ledger check.', 'sig': 'a', 'action': {'mid': mid}}, ago(days=1))
        self.assertEqual(assistant.parse(s, _say('idea:mine', mid=mid), [])[0]['key'], 'idea:mine')
        self.assertNotIn('Ledger check', assistant._said(s))

    def test_an_idea_about_long_closed_work_stands_alone(self):
        """I6: tied to a task closed a month ago, the rail filed it under a closed row and nobody saw it."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Old close', 'Kind': 'task'}, 't'); s.update_task(tid, {'Status': 'done'}, 'owner')
        s._exec('UPDATE task SET ClosedAt=?, UpdatedAt=? WHERE TaskId=?', (ago(days=30), ago(days=30), tid))
        line = assistant.parse(s, _say('idea:again', text=f'TQ-{tid:04d} is failing the same way again.'), [])[0]
        self.assertNotIn('tid', line['action'])
        live = s.create_task({'Title': 'Open one', 'Kind': 'task'}, 't')
        # the task is the model's `about`, never a TQ-ref read out of the line's words (2026-10-11)
        self.assertNotIn('tid', assistant.parse(s, _say('idea:words', text=f'TQ-{live:04d} has not moved.'), [])[0]['action'])
        self.assertEqual(assistant.parse(s, _say('idea:live', text='The open one has not moved.', about=f'TQ-{live:04d}'), [])[0]['action']['tid'], live)


class RunTests(unittest.TestCase):
    def test_the_apps_health_counts_toward_lines_per_post(self):
        """I9: health rode on top of the cap - a post said to hold one line held every broken thing."""
        s = A.store()
        for at in ('06:00', '07:00', '08:00'):
            s.add_report_run(A.AR['sid'], {'at': f'2026-09-18 {at}:00', 'title': 'Monthly AR Report', 'failed': True, 'error': 'x'})
        # a second health line - a workflow that never ran (an erroring connection is the rail's row, not an idea)
        wf = s.save_source({'Channel': 'report', 'Address': 'wf9', 'Active': 1, 'ConfigJson': json.dumps({'title': 'Nightly sync', 'type': 'agent', 'access': 'write', 'cron': '0 1 * * *'})}, 't')
        s.set_setting(assistant.WORKFLOWS_SEEN, json.dumps({str(wf): '2026-09-01 00:00:00'}), 't')      # known for weeks, never run
        self.assertGreaterEqual(len(assistant.health_ideas(s)), 2)
        s.set_setting('assistant_max_lines', '1', 't')
        self.assertEqual(assistant.run(s, llm=None, force=True)['said'], 1)


class DoneTests(unittest.TestCase):
    def test_done_on_the_ideas_row_puts_the_idea_down(self):
        """I4: the rail's Done wrote the rail's state and nothing else."""
        s = MemoryStore()
        i = s.upsert_idea({'key': 'idea:x', 'kind': 'idea', 'text': 'Book the sign-off.', 'sig': 'x', 'action': {}}, ago(hours=1))
        funnel.settle(s, f"idea:{i['IdeaId']}", 'done')
        self.assertEqual(s.get_idea(i['IdeaId'])['Status'], 'done')
        j = s.upsert_idea({'key': 'idea:y', 'kind': 'idea', 'text': 'Another.', 'sig': 'y', 'action': {}}, ago(hours=1))
        s.set_idea_status(j['IdeaId'], 'dismissed', 'owner')
        funnel.settle(s, f"idea:{j['IdeaId']}", 'done')
        self.assertEqual(s.get_idea(j['IdeaId'])['Status'], 'dismissed')          # a verdict already given stands

    def test_an_idea_never_reopens_a_done_task_through_triage(self):
        """I7: triage's same_as joined the Advisor's idea to a task closed yesterday and set it back to waiting."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Vendor loop', 'Kind': 'task'}, 't'); s.update_task(tid, {'Status': 'done'}, 'owner')
        msg = {'external_id': 'idea:7', 'channel': 'assistant', 'from_name': 'Advisor', 'source_name': 'Advisor', 'conversation_id': 'idea:vendor',
               'subject': 'Advisor idea: the vendor loop again', 'sent_at': ago(minutes=1), 'body': 'It looks like the loop is back.',
               '_verdict': ({'intent': 'task', 'kind': 'task', 'why': 'new', 'same_as': tid, 'title': 'Vendor loop'}, {})}
        with mock.patch('taskuary.ingest._spawn'):
            out = ingest.ingest_message(s, msg, actor='assistant')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertNotEqual(out.get('task_id'), tid)


    def test_closing_a_task_puts_down_the_ideas_about_it_and_no_other(self):
        """A closed task's mail stood alone on the rail under 'asked': an Advisor idea raised on it held it there (2026-10-18)."""
        from taskuary import concierge
        s = MemoryStore(); mid = _mail(s)
        tid = s.create_task({'Title': 'Reconcile the Q3 ledger', 'Kind': 'task'}, 't'); s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mid))
        on_mail = s.upsert_idea({'key': 'idea:erin-waits', 'kind': 'idea', 'text': 'Erin still waits on the ledger.', 'sig': 'a',
                                 'action': {'mid': mid, 'triage': {'intent': 'task'}}}, ago(hours=1))
        on_task = s.upsert_idea({'key': 'idea:ledger-late', 'kind': 'idea', 'text': 'The ledger is late.', 'sig': 'b', 'action': {'tid': tid}}, ago(hours=1))
        other = s.upsert_idea({'key': 'idea:gail', 'kind': 'idea', 'text': 'Gail Moreno asked about payroll.', 'sig': 'c', 'action': {}}, ago(hours=1))
        self.assertIn(on_mail['IdeaId'], [i['idea'] for i in funnel.from_forgotten(s, set(), set())], 'the idea holds the mail before the close')
        concierge.close_task(s, tid, 'owner')
        self.assertEqual([s.get_idea(i['IdeaId'])['Status'] for i in (on_mail, on_task, other)], ['done', 'done', 'open'])
        self.assertEqual([i['idea'] for i in funnel.from_forgotten(s, set(), set())], [other['IdeaId']], 'nothing about the closed task asks')


class RailTests(unittest.TestCase):
    NOW = datetime.now()

    def _off(self, s, idea):
        return processing_unread._idea_off(s, {'ideas': [idea]}, {'open_target': {'kind': 'idea', 'id': idea['IdeaId']}}, self.NOW)

    def test_the_old_rails_idea_rules_hold_on_the_canonical_road(self):
        """I5: prep, work=no and an answered follow-up left the rail on the old road and stayed on the new one."""
        s = MemoryStore(); mid = _mail(s)
        row = lambda **kw: {'IdeaId': 1, 'Status': 'open', 'Kind': 'idea', 'ActionJson': '{}', 'LastSaid': ago(hours=2), **kw}
        self.assertFalse(self._off(s, row()))
        self.assertTrue(self._off(s, row(Kind='prep')))
        self.assertTrue(self._off(s, row(ActionJson=json.dumps({'work': False}))))
        self.assertTrue(self._off(s, row(Status='dismissed')))
        self.assertTrue(self._off(s, row(Status='snoozed', SnoozeUntil=(self.NOW + timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S'))))
        self.assertFalse(self._off(s, row(Status='snoozed', SnoozeUntil=ago(hours=1))))            # its day came: back
        rv = s.add_review({'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Sent it.'})
        s._exec("UPDATE review SET Status='approved', DecidedAt=? WHERE ReviewId=?", (ago(minutes=5), rv))
        self.assertTrue(self._off(s, row(ActionJson=json.dumps({'mid': mid}))))                     # you already replied


if __name__ == '__main__':
    unittest.main()


class PrepLineAboutAnOpenTaskTests(unittest.TestCase):
    """A meeting-prep line about a question already on an open task became a second task for the same ask - answered on the
    first, still open on the second (the owner, 2026-10-14). Its `about` is read for every line, not only an idea's."""
    def test_a_prep_line_about_an_open_task_is_tied_to_it_and_opens_nothing_new(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Send the portal SSO settings', 'Kind': 'task', 'Status': 'open'}, 'router')
        cand = {'key': 'prep:2026-10-15 10:30:Portal link review', 'kind': 'prep', 'facts': 'MEETING 2026-10-15 10:30',
                'action': {'type': 'meeting'}}
        [line] = assistant.parse(s, _say(cand['key'], text='Ray asked what the portal button should say.', about=f'TQ-{tid:04d}',
                                         suggest=f'Reply with the label - TQ-{tid:04d} has a draft waiting.'), [cand])
        self.assertEqual(line['action']['tid'], tid)
        s.cx.execute('INSERT INTO idea (Key, Kind, Text, ActionJson, Sig, Status, FirstSeen, LastSaid) VALUES (?,?,?,?,?,?,?,?)',
                     (cand['key'], 'prep', line['text'], json.dumps(line['action']), 'sig', 'open', ago(minutes=1), ago(minutes=1)))
        s.cx.commit()
        before = len(s.list_tasks())
        with mock.patch.object(ingest, 'judge', return_value=({'intent': 'task', 'kind': 'task', 'why': 'a wording decision'}, None)):
            assistant.triage_ideas(s, s.list_ideas('open'), llm=object())
        self.assertEqual(len(s.list_tasks()), before, 'tied to the open task, so no second one')
        self.assertEqual(json.loads(s.list_ideas('open')[0]['ActionJson'])['triage']['linked_task'], tid)

    def test_a_prep_line_about_closed_work_stays_untied(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Old ask', 'Kind': 'task', 'Status': 'done'}, 'router')
        cand = {'key': 'prep:2026-10-15 10:30:Portal link review', 'kind': 'prep', 'facts': 'MEETING', 'action': {'type': 'meeting'}}
        [line] = assistant.parse(s, _say(cand['key'], about=f'TQ-{tid:04d}'), [cand])
        self.assertNotIn('tid', line['action'])

"""The morning brief is the ASSISTANT's summary (TQ-0258): it reads what the assistant reads,
names what slipped (their ask, nobody answered), and speaks in COUNSEL.md's voice - not the
report summarizer's. All offline: the model is a lambda, the calendar is off."""
import unittest
from datetime import datetime, timedelta

from taskuary import assistant, digest, reports
from taskuary.store import MemoryStore

ME, DANA = 'owner@ours.com', 'dana@vendor.com'
def _ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 't'); s.set_setting('owner_email', ME, 't')
    return s


def _mail(s, frm, subject, body, days=1, conv=None, tid=None):
    return s.add_message({'TaskId': tid, 'ExternalId': f'x:{frm}:{subject}:{days}', 'ConversationId': conv, 'Channel': 'email',
                          'SourceName': ME, 'Subject': subject, 'FromName': frm.split('@')[0].title(), 'FromEmail': frm,
                          'SentAt': _ago(days), 'BodyText': body, 'Status': 'filed'})


def _mine(s, subject, body, days, conv):
    """The owner's own reply on a thread - 'context' rows ride inside the chain."""
    return s.add_message({'ExternalId': f'mine:{conv}:{days}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME,
                          'Subject': subject, 'FromName': 'You', 'FromEmail': ME, 'SentAt': _ago(days), 'BodyText': body, 'Status': 'context'})


class UnansweredTests(unittest.TestCase):
    def test_their_open_ask_slips_and_an_answered_or_askless_one_does_not(self):
        s = _store()
        _mail(s, DANA, 'Budget', 'Could you send the Q3 budget?', days=1, conv='u1')
        _mail(s, 'lee@ours.com', 'FYI', 'All handled, nothing needed from you.', days=1, conv='u2')   # no ask in it
        _mail(s, 'sam@ours.com', 'Numbers', 'Can you check the numbers?', days=2, conv='u3')
        _mine(s, 'Re: Numbers', 'Done - see attached.', days=1, conv='u3')                            # answered
        got = assistant.unanswered(s, days=3)
        self.assertEqual([c['key'] for c in got], ['asked:u1'])
        self.assertIn('Dana', got[0]['facts']); self.assertIn('no task, no draft', got[0]['facts'])
        self.assertEqual(got[0]['kind'], 'asked')

    def test_a_pending_draft_covers_the_ask_and_the_line_says_so(self):
        s = _store()
        mid = _mail(s, DANA, 'Budget', 'Could you send the Q3 budget?', days=1, conv='u1')
        tid = s.create_task({'Title': 'Budget reply', 'Kind': 'reply'}, 't')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mid))
        s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        got = assistant.unanswered(s, days=3)
        self.assertEqual(len(got), 1)
        self.assertIn('a draft waits for you in Review', got[0]['facts'])

    def test_a_fresh_ask_is_not_yet_missed(self):
        s = _store()
        _mail(s, DANA, 'Budget', 'Could you send it over?', days=0, conv='u1')      # minutes old
        self.assertEqual(assistant.unanswered(s, days=2, hours=3), [])


class BriefVoiceTests(unittest.TestCase):
    def test_the_digest_speaks_in_the_assistants_voice_not_the_report_summarizers(self):
        s = MemoryStore()
        sys_digest = reports.report_system(s, {'type': 'digest'})
        self.assertIn('MORNING BRIEF', sys_digest)
        self.assertIn('how I speak up', sys_digest)                       # COUNSEL.md is the voice
        self.assertEqual(reports.report_system(s, {'type': 'sqlite'}), reports.AI_SYSTEM)
        self.assertIn('MORNING BRIEF', reports.report_system(s, {'type': 'rest', 'sources': [{'type': 'digest'}]}))

    def test_the_scheduled_run_hands_the_digest_system_to_the_model(self):
        s = MemoryStore()
        s.create_task({'Title': 'PTO import mapping'}, 'o')
        src = next(x for x in s.list_sources() if x['Channel'] == 'report')          # the seeded Morning digest
        seen = {}
        def llm(system, user, **kw): seen['system'] = system; return '- morning.'
        reports.run_report_source(s, src, llm=llm)
        self.assertIn('MORNING BRIEF', seen['system'])
        self.assertIn('how I speak up', seen['system'])


class BriefMemoryTests(unittest.TestCase):
    def test_an_applicable_standing_verdict_governs_the_digest(self):
        s = _store()
        _mail(s, DANA, 'Resident Refund Request - Watson, Lisa',
              'The resident refund is still awaiting facility approval.', days=0, conv='refund')
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'resident refund request approved',
                      'Note': 'Resident refunds are handled by facility staff; do not raise them to Uri.',
                      'Active': 1, 'CreatedBy': 'owner'})
        text = digest.gather(s, 1)
        self.assertIn('WHAT THE OWNER HAS ALREADY DECIDED', text)
        self.assertIn('do not raise them to Uri', text)
        self.assertIn('governs every section', digest.PROMPT)

    def test_unrelated_or_switched_off_memory_stays_out_of_the_digest(self):
        s = _store()
        _mail(s, DANA, 'Resident Refund Request - Watson, Lisa',
              'The resident refund is still awaiting facility approval.', days=0, conv='refund')
        parking = s.add_memory({'Scope': 'subject', 'ScopeKey': 'parking permits',
                                'Note': 'Parking permits belong to facilities.', 'Active': 1, 'CreatedBy': 'owner'})
        retired = s.add_memory({'Scope': 'global', 'Note': 'Retired rule.', 'Active': 0, 'CreatedBy': 'owner'})
        s._exec('UPDATE memory SET CreatedAt=? WHERE MemoryId IN (?,?)', (_ago(days=3), parking, retired))
        text = digest.gather(s, 1)
        self.assertNotIn('Parking permits belong', text)
        self.assertNotIn('Retired rule', text)


def _slot_ahead() -> str:
    """A daily_at that has NOT come round yet today, so is_due's answer is about once_per_day
    and nothing else. Hard-coding '08:00' made these two tests pass only before breakfast: after
    08:00 the daily clock made the report due on its own and 'already ran today' looked broken."""
    when = datetime.now() + timedelta(hours=1)
    return '23:59' if when.day != datetime.now().day else when.strftime('%H:%M')


class OnceADayTests(unittest.TestCase):
    """A brief that lands again on every app launch is the noise that made it unreadable."""
    CFG = {'type': 'digest', 'daily_at': '08:00', 'on_startup': True, 'once_per_day': True}

    def test_the_first_launch_of_the_day_files_the_brief_and_the_next_nine_do_not(self):
        cfg = {**self.CFG, 'daily_at': _slot_ahead()}
        self.assertTrue(reports.is_due(cfg, None, startup=True))                    # never run
        self.assertTrue(reports.is_due(cfg, _ago(days=1, hours=2), startup=True))   # yesterday's
        self.assertFalse(reports.is_due(cfg, _ago(hours=1), startup=True))          # already today

    def test_without_the_flag_every_launch_still_fires(self):
        cfg = {k: v for k, v in self.CFG.items() if k != 'once_per_day'} | {'daily_at': _slot_ahead()}
        self.assertTrue(reports.is_due(cfg, _ago(hours=1), startup=True))                # the Assistant's cadence

    def test_the_daily_clock_still_fires_while_the_app_stays_open(self):
        due = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        if datetime.now() < due: self.skipTest('before 08:00 - the daily slot has not passed today')
        self.assertTrue(reports.is_due(self.CFG, (due - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')))

    def test_the_seeded_digest_ships_once_a_day(self):
        import json
        s = MemoryStore()
        cfg = next(json.loads(x['ConfigJson']) for x in s.list_sources()
                   if x['Channel'] == 'report' and json.loads(x['ConfigJson']).get('type') == 'digest')
        self.assertEqual((cfg['daily_at'], cfg['on_startup'], cfg['once_per_day']), ('08:00', True, True))


class BriefConsolidatesTheAssistantTests(unittest.TestCase):
    def test_what_the_assistant_raised_rides_in_with_its_state(self):
        s = _store()
        s.upsert_idea({'key': 'idea:demo', 'kind': 'idea', 'sig': 'x', 'text': 'Chase the Q3 budget', 'action': {}}, _ago(0, 5))
        text = digest.gather(s, 1)
        block = text.split('WHAT THE ASSISTANT ALREADY RAISED', 1)[1].split("THE ASSISTANT'S NOTES", 1)[0]
        self.assertIn('Chase the Q3 budget', block); self.assertIn('(open', block)


if __name__ == '__main__': unittest.main()

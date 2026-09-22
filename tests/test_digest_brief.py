"""The morning brief is the ASSISTANT's summary (TQ-0258): it reads what the assistant reads,
names what slipped (their ask, nobody answered), and speaks in COUNSEL.md's voice - not the
report summarizer's. All offline: the model is a lambda, the calendar is off."""
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest import mock

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
        self.assertIn('a draft waits for you on the task', got[0]['facts'])

    def test_a_fresh_ask_is_not_yet_missed(self):
        s = _store()
        _mail(s, DANA, 'Budget', 'Could you send it over?', days=0, conv='u1')      # minutes old
        self.assertEqual(assistant.unanswered(s, days=2, hours=3), [])


class BriefVoiceTests(unittest.TestCase):
    def test_the_digest_speaks_in_the_assistants_voice_not_the_report_summarizers(self):
        s = MemoryStore()
        sys_digest = reports.report_system(s, {'type': 'digest'})
        self.assertIn('MORNING BRIEF', sys_digest)
        # The approved COUNSEL edit renamed the heading; assert its voice rule,
        # not the old section title. Report/chat prompt separation is a later change.
        self.assertIn('Be plain, direct, and concise.', sys_digest)
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
        self.assertIn('Be plain, direct, and concise.', seen['system'])


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

    def test_an_ask_a_standing_verdict_covers_ranks_below_the_live_asks_and_names_its_verdict(self):
        """TQ-0654: the on-start digest led 'People want' with a resident-refund thread the owner had
        ruled not ours. The ask sat first in THEIR ASKS with 'no task, no draft' and the verdict lived
        blocks later as general context, so the model ranked the ask before it read the ruling."""
        s = _store()
        _mail(s, 'christine@ours.com', 'Re: Resident Refund Request Form Rejected - Sawyers, Donald R, Valley',
              'Can you explain why rejected? They have been calling and wanting a refund.', days=0, conv='sawyers')
        s._exec("UPDATE message SET SentAt=? WHERE ConversationId='sawyers'", (_ago(hours=5),))
        _mail(s, 'bob@ours.com', 'Target meeting', 'Can you confirm Thursday still holds?', days=1, conv='target')
        s.add_memory({'Scope': 'subject', 'ScopeKey': 'resident refund request', 'Note': 'resident refunds are not ours',
                      'Active': 1, 'CreatedBy': 'owner'})
        s._exec('UPDATE memory SET CreatedAt=?', (_ago(days=17),))
        text = digest.gather(s, 1)
        asks = text[text.index('THEIR ASKS YOU HAVE NOT ANSWERED'):text.index('ASKS YOUR STANDING VERDICTS ALREADY COVER')]
        self.assertIn('Bob asked', asks)
        self.assertNotIn('Christine asked', asks)
        ruled = text[text.index('ASKS YOUR STANDING VERDICTS ALREADY COVER'):text.index('MY OPEN LOOPS')]
        self.assertIn('Christine asked', ruled)
        self.assertIn('ruled out by your verdict "resident refunds are not ours"', ruled)
        self.assertLess(text.index('Bob asked'), text.index('Christine asked'))

    def test_a_global_verdict_covers_an_ask_only_when_it_is_about_that_topic(self):
        s = _store()
        _mail(s, 'christine@ours.com', 'Re: Resident Refund Request Form Rejected - Sawyers, Donald R, Valley',
              'Can you explain why rejected?', days=1, conv='sawyers')
        _mail(s, 'bob@ours.com', 'Target meeting', 'Can you confirm Thursday still holds?', days=1, conv='target')
        s.add_memory({'Scope': 'global', 'Note': 'Resident refunds are not ours', 'Active': 1, 'CreatedBy': 'owner'})
        s.add_memory({'Scope': 'global', 'Note': 'Never chase a vendor before noon', 'Active': 1, 'CreatedBy': 'owner'})
        s._exec('UPDATE memory SET CreatedAt=?', (_ago(days=17),))
        text = digest.gather(s, 1)
        asks = text[text.index('THEIR ASKS YOU HAVE NOT ANSWERED'):text.index('ASKS YOUR STANDING VERDICTS ALREADY COVER')]
        self.assertIn('Bob asked', asks); self.assertNotIn('Christine asked', asks)
        self.assertIn('ruled out by your verdict "Resident refunds are not ours"', text)
        self.assertNotIn('vendor before noon"', text[text.index('ASKS YOUR STANDING'):text.index('MY OPEN LOOPS')])

    def test_without_a_covering_verdict_no_ruled_out_block_is_written(self):
        s = _store()
        _mail(s, 'bob@ours.com', 'Target meeting', 'Can you confirm Thursday still holds?', days=1, conv='target')
        self.assertNotIn('ASKS YOUR STANDING VERDICTS ALREADY COVER', digest.gather(s, 1))

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


@contextmanager
def _at(h, m, day=16):
    """A frozen local clock. A scheduler test that reads the wall clock only asserts what the hour
    happens to allow - these ones ran green before breakfast and skipped after it. Every stamp below
    is a literal, so the whole morning of TQ-0589 is one readable walk."""
    class Now(datetime):
        @classmethod
        def now(cls, tz=None): return cls(2026, 9, day, h, m)
    with mock.patch.object(reports, 'datetime', Now): yield


YESTERDAY, SLOT_RUN = '2026-09-15 08:00:00', '2026-09-16 08:08:00'


class OnceADayTests(unittest.TestCase):
    """A brief that lands twice in a morning is the noise that made it unreadable. The cap belongs
    to the REPORT, not to the launch - and when both a launch and a slot could serve the day, the
    SLOT wins (the owner, 2026-09-14: "we should only have the latest one")."""
    CFG = {'type': 'digest', 'daily_at': '08:00', 'on_startup': True, 'once_per_day': True}

    def test_an_early_launch_waits_for_the_slot_instead_of_pre_empting_it(self):
        """TQ-0589: opening the app at 07:07 filed a brief at 07:10, and 08:00 filed another."""
        with _at(7, 10): self.assertFalse(reports.is_due(self.CFG, YESTERDAY, startup=True))

    def test_the_slot_files_the_day_and_nothing_else_does(self):
        with _at(8, 8):  self.assertTrue(reports.is_due(self.CFG, YESTERDAY))
        with _at(9, 0):  self.assertFalse(reports.is_due(self.CFG, SLOT_RUN))
        with _at(20, 0): self.assertFalse(reports.is_due(self.CFG, SLOT_RUN, startup=True))

    def test_a_launch_after_a_missed_slot_files_at_once(self):
        """Shut all morning: 08:00 came and went unserved, so opening at 10:00 IS the brief."""
        with _at(10, 0): self.assertTrue(reports.is_due(self.CFG, YESTERDAY, startup=True))

    def test_the_daily_clock_still_fires_while_the_app_stays_open(self):
        """Left running since yesterday, nothing has served today - 08:00 is still its moment."""
        with _at(8, 0): self.assertTrue(reports.is_due(self.CFG, YESTERDAY))

    def test_a_never_run_brief_does_not_wait_a_day_for_its_slot(self):
        with _at(7, 10): self.assertTrue(reports.is_due(self.CFG, None, startup=True))

    def test_without_the_flag_every_launch_still_fires(self):
        cfg = {k: v for k, v in self.CFG.items() if k != 'once_per_day'}
        with _at(7, 10): self.assertTrue(reports.is_due(cfg, '2026-09-16 06:00:00', startup=True))

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


class PromptOrder(unittest.TestCase):
    def test_errors_then_meetings_lead_and_the_old_stock_prompt_still_upgrades(self):
        """The current reading order is explicit and prior stock text still upgrades safely."""
        from taskuary import digest
        p = digest.PROMPT
        self.assertLess(p.index('Errors -'), p.index('Meetings today -'))
        self.assertLess(p.index('Meetings today -'), p.index('People want -'))
        self.assertLess(p.index('People want -'), p.index('In flight -'))
        self.assertIn('numbered list (1., 2., 3.', p)
        self.assertIn(digest._PROMPT_2026_09_02_MEMORY, digest.OLD_PROMPTS)
        self.assertIn(digest._PROMPT_2026_08_31_MEMORY, digest.OLD_PROMPTS)
        self.assertIn('What slipped', digest._PROMPT_2026_08_31_MEMORY)
        self.assertNotIn('What slipped', p)

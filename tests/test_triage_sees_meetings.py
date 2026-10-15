"""Triage sees today's meetings (2026-10-15). A "your meeting is about to start" reminder from a meeting tool opened an
urgent "Join the meeting" task beside the meeting's own calendar row: triage had never been shown the calendar, so it
could not know the meeting was already in front of the owner. It is given the meetings as evidence - what to make of
a mail about one is the model's call, said in the triage guide, never a keyword rule here."""
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from taskuary import context, ingest, triage
from taskuary.store import MemoryStore

def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

def day(*evs): return {'date': datetime.now().strftime('%Y-%m-%d'), 'now': '10:20', 'events': list(evs), 'tz': 'UTC', 'errors': []}

STANDUP = {'start': f"{datetime.now():%Y-%m-%d}T10:30:00", 'end': f"{datetime.now():%Y-%m-%d}T11:00:00", 'all_day': False,
           'subject': 'Northwind and Payworth: portal link review', 'who': ['Erin Blake', 'Ray Colton'], 'where': '', 'about': 'Walk through the link',
           'join': 'https://meet.example/abc'}

def reminder(sent=None):
    return {'external_id': 'm-remind', 'channel': 'email', 'from_email': 'reminder@meetings.example', 'from_name': 'Meeting reminders',
            'subject': 'Reminder: Northwind and Payworth: portal link review is about to start', 'body': 'Your meeting starts in 10 minutes. Join here.',
            'conversation_id': 'c-remind', 'sent_at': sent or ago(hours=0)}

def seen_thread(s, msg):
    got = {}
    def classify(m, **kw): got.update(kw.get('thread') or {}); return {'intent': 'fyi', 'why': 'x'}
    with mock.patch('taskuary.ingest._spawn'), mock.patch('taskuary.ingest.classify_intent', classify):
        ingest.ingest_message(s, msg, actor='test', llm=lambda *a, **k: '{}')
    return got


class TriageSeesMeetings(unittest.TestCase):
    def test_todays_meetings_are_evidence_for_a_mail_that_arrives_today(self):
        with mock.patch('taskuary.calendar.today', return_value=day(STANDUP)):
            got = seen_thread(MemoryStore(), reminder())
        m = got['meetings_today'][0]
        self.assertEqual((m['when'][:5], m['subject'], m['with']), ('10:30', STANDUP['subject'], ['Erin Blake', 'Ray Colton']))

    def test_old_mail_read_in_a_catch_up_is_not_handed_todays_calendar(self):
        with mock.patch('taskuary.calendar.today', return_value=day(STANDUP)):
            self.assertNotIn('meetings_today', seen_thread(MemoryStore(), reminder(sent=ago(hours=72))))

    def test_no_meetings_or_an_unreadable_calendar_adds_nothing(self):
        with mock.patch('taskuary.calendar.today', return_value=day()):
            self.assertNotIn('meetings_today', seen_thread(MemoryStore(), reminder()))
        with mock.patch('taskuary.calendar.today', side_effect=RuntimeError('graph down')):
            self.assertNotIn('meetings_today', seen_thread(MemoryStore(), reminder()))

    def test_the_model_is_told_what_the_field_is(self):
        """The guide names it with what to weigh; a document that does not still gets the field's plain description."""
        guide = (Path(triage.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
        self.assertIn('`meetings_today`', guide.split('## 6.')[1].split('## 7.')[0])
        def llm(system, user, **kw): llm.system, llm.user = system, user; return '{"intent": "fyi", "why": "x"}'
        triage.classify_intent(reminder(), llm=llm, system='Judge the mail.', thread={'meetings_today': context.meetings_today_of(day(STANDUP))})
        self.assertIn(triage.FIELDS['meetings_today'], llm.system); self.assertIn('portal link review', llm.user)


if __name__ == '__main__': unittest.main()

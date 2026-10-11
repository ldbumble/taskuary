"""Auto-replies are never triaged (the owner, 2026-09-25: "all auto replies should be ignored period, when it comes to
triage"). An out-of-office answering the owner's reply was triaged, filed onto the urgent task and then spoke for it."""
import email, unittest
from unittest import mock

from taskuary import assistant, autoreply, funnel, ingest
from test_funnel import ago, mail, store


def never(*a, **k): raise AssertionError('an auto-reply reached triage')


def arrive(s, subject, conv='c1', **extra):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': f'x:{subject}:{conv}', 'channel': 'email', 'from_email': 'ray@vendor.example',
                                         'from_name': 'Ray Colton', 'conversation_id': conv, 'subject': subject,
                                         'body': 'I am out of the office until Monday.', 'sent_at': ago(0), **extra}, llm=never)


class NeverTriagedTests(unittest.TestCase):
    def test_graphs_headers_mark_it(self):
        """Graph hands the headers over as internetMessageHeaders (channels.MAIL_BODY_SELECT)."""
        from taskuary.channels import _header_marks
        marks = _header_marks({'internetMessageHeaders': [{'name': 'auto-submitted', 'value': 'auto-replied'},
                                                          {'name': 'X-Auto-Response-Suppress', 'value': 'All'}]})
        self.assertTrue(marks['auto_reply'])
        s = store()
        out = arrive(s, 'Automatic reply: August financials', **marks)
        self.assertEqual((out['status'], out['task_id']), (autoreply.STATUS, None))
        self.assertEqual(s.get_message(out['message_id'])['Status'], autoreply.STATUS)
        self.assertEqual(_header_marks({'internetMessageHeaders': [{'name': 'Received', 'value': 'from mx.example'}]}), {})

    def test_a_subject_alone_is_not_the_mark(self):
        """A colleague's "Out of office coverage for Friday - can you take my calls?" is a person asking: triaged.
        The subject prefix decided it before, and the ask was stored as an auto-reply nobody saw (2026-10-11)."""
        s, seen = store(), []
        def llm(system, user, **k): seen.append(user); return '{"intent": "task", "kind": "task", "why": "asks for cover", "title": "Cover calls Friday", "summary": "Ray asks.", "sender_class": "person"}'
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(s, {'external_id': 'x:cover', 'channel': 'email', 'from_email': 'ray@vendor.example',
                                            'from_name': 'Ray Colton', 'conversation_id': 'c9', 'sent_at': ago(0),
                                            'subject': 'Out of office coverage for Friday - can you take my calls?',
                                            'body': 'I am out Friday. Can you cover my calls?'}, llm=llm)
        self.assertNotEqual(out['status'], autoreply.STATUS)
        self.assertTrue(seen, 'the model read it')
        self.assertFalse(autoreply.is_auto({'Subject': 'Automatic reply: Budget'}))

    def test_the_rfc_3834_header_where_the_connector_has_it(self):
        s = store()
        out = arrive(s, 'Re: August financials', auto_reply=True)       # imapmail sets it from the headers
        self.assertEqual(out['status'], autoreply.STATUS)
        raw = email.message_from_string('Auto-Submitted: auto-replied\nSubject: Re: hi\n\nbody')
        self.assertTrue(autoreply.from_headers(raw))
        self.assertFalse(autoreply.from_headers(email.message_from_string('Auto-Submitted: no\nSubject: hi\n\nbody')))
        self.assertTrue(autoreply.from_headers(email.message_from_string('Precedence: auto_reply\n\nx')))

    def test_it_never_joins_the_task_it_answers(self):
        s = store()
        t = s.create_task({'Title': 'Send the August financials', 'Kind': 'task', 'Status': 'open', 'Priority': 'urgent'}, 'triage')
        mail(s, 'August financials', who='Paula Vance', email='paula@vendor.example', hours=1, tid=t, conv='c1')
        out = arrive(s, 'Automatic reply: August financials', conv='c1', auto_reply=True)
        self.assertIsNone(out['task_id'])
        self.assertEqual([m['Subject'] for m in s.list_messages(t)], ['August financials'])

    def test_the_advisor_still_knows_who_is_away(self):
        s = store()
        arrive(s, 'Automatic reply: Budget', auto_reply=True)
        self.assertIn('ray@vendor.example', assistant.ooo(s))


class NeverSpeaksForACardTests(unittest.TestCase):
    def test_one_already_filed_on_a_task_does_not_speak_for_it(self):
        """The auto-reply that was already on the owner's task before this shipped."""
        from taskuary import processing_unread
        s = store()
        t = s.create_task({'Title': 'Send the August financials', 'Kind': 'task', 'Status': 'open'}, 'triage')
        ask = mail(s, 'August financials', who='Paula Vance', email='paula@vendor.example', hours=2, tid=t, conv='c1')
        s.add_route(ask, t, 'route', 1.0, 'triage: task', [], 'triage')
        ooo = mail(s, 'Automatic reply: August financials', who='Ray Colton', email='ray@vendor.example', hours=0, tid=t, conv='c1',
                   status=autoreply.STATUS)
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            card = [i for i in processing_unread.build(s, live_state=[], include_read=True)['items'] if i.get('tid') == t]
        self.assertEqual([c.get('mid') for c in card], [ask])
        self.assertNotEqual(card[0].get('mid'), ooo)


if __name__ == '__main__': unittest.main()

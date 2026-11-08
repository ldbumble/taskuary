"""Work that waits on you elsewhere (waiting.py, on the inboxes.py road): shared inboxes, phones, forms, hiring, money. HTTP faked by
URL with payloads shaped like each vendor's own API reference - no network. Each: Test learns who you are, the poll files only what
points at you, and only the vendor's own word makes an author one of the workspace (H2) - a customer, caller or respondent never is."""
import unittest
from unittest import mock

from taskuary import inboxes, net
from taskuary.store import MemoryStore
from tests.test_inboxes import SINCE, R, wired, conn, again, rows, meta, trusted


def fresh(): net._TOKENS.clear(); return MemoryStore()


class FormTests(unittest.TestCase):
    def test_typeform_new_responses_on_the_forms_picked(self):
        s = fresh(); c = conn(s, 'typeform')
        with wired({'/me': {'alias': 'Alex Doyle'}, '/forms': {'items': [{'id': 'F1', 'title': 'Intake'}]}}):
            self.assertIn('Intake (F1)', inboxes.test(s, c))                              # nothing picked yet: Test names what there is
        s.merge_connector_config(c['ConnectorId'], {'forms': 'F1'})
        r1 = {'response_id': 'r1', 'submitted_at': '2026-08-20T10:00:00Z',
              'answers': [{'field': {'id': 'q1'}, 'type': 'text', 'text': 'Need a quote'}, {'field': {'id': 'q2'}, 'type': 'email', 'email': 'pat@vendor.example'},
                          {'field': {'id': 'q3'}, 'type': 'choice', 'choice': {'label': 'Urgent'}}]}
        with wired({'/forms/F1/responses': {'items': [r1]}, '/forms/F1': {'title': 'Intake', 'fields': [{'id': 'q1', 'title': 'What do you need?'},
                    {'id': 'q2', 'title': 'Email'}, {'id': 'q3', 'title': 'How soon?'}]}}) as h:
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 1)
        self.assertTrue(h.calls[-1][2]['params']['since'].startswith('2026-0'))
        r = rows(s, 'typeform')[0]
        self.assertIn('What do you need?: Need a quote', r['BodyText']); self.assertIn('How soon?: Urgent', r['BodyText'])
        self.assertEqual(r['FromEmail'], 'pat@vendor.example'); self.assertFalse(trusted(s, r))

    def test_jotform_and_surveymonkey(self):
        s = fresh(); jf, sm = conn(s, 'jotform', {'forms': '230'}), conn(s, 'surveymonkey', {'forms': '55'})
        sub = {'id': '5001', 'created_at': '2026-08-20 10:00:00', 'answers': {'3': {'text': 'Name', 'answer': {'first': 'Pat'}, 'prettyFormat': 'Pat Buyer', 'order': '1'},
                                                                            '4': {'text': 'Message', 'answer': 'Call me', 'order': '2'}}}
        with wired({'/user/forms': {'content': []}, '/user': {'content': {'name': 'Alex Doyle'}}, '/form/230/submissions': {'content': [sub]}}) as h:
            self.assertIn('1 form', inboxes.test(s, jf)); self.assertEqual(inboxes.poll(s, jf, SINCE), 1)
        self.assertEqual(h.calls[-1][2]['params']['apiKey'], 'tok')
        self.assertIn('Name: Pat Buyer\nMessage: Call me', rows(s, 'jotform')[0]['BodyText'])
        resp = {'id': 'R9', 'date_created': '2026-08-20T10:00:00+00:00', 'analyze_url': 'https://www.surveymonkey.com/analyze/x',
                'pages': [{'questions': [{'heading': 'How did we do?', 'answers': [{'simple_text': 'Great'}]}]}]}
        with wired({'/users/me': {'username': 'alexd'}, '/surveys/55/responses/bulk': {'data': [resp]}, '/surveys': {'data': []}}):
            inboxes.test(s, sm); self.assertEqual(inboxes.poll(s, sm, SINCE), 1)
        self.assertIn('How did we do?: Great', rows(s, 'surveymonkey')[0]['BodyText'])

    def test_tally_completed_submissions_only(self):
        s = fresh(); c = conn(s, 'tally', {'forms': 'wA1'})
        sub = lambda i, done: {'id': i, 'submittedAt': '2026-08-20T10:00:00.000Z', 'isCompleted': done,
                               'responses': [{'questionId': 'q1', 'answer': 'pat@vendor.example', 'formattedAnswer': 'pat@vendor.example'}]}
        with wired({'/forms/wA1/submissions': {'questions': [{'id': 'q1', 'title': 'Email'}], 'submissions': [sub('s1', True), sub('s2', False)]}}) as h:
            self.assertIn('1 form', inboxes.test(s, c)); self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual(h.calls[-1][2]['headers']['Authorization'], 'Bearer tok')
        self.assertEqual(rows(s, 'tally')[0]['FromEmail'], 'pat@vendor.example')

    def test_google_forms_read_with_the_sheets_sign_in(self):
        s = fresh(); c = conn(s, 'google_forms', {'forms': 'GF1'})
        d = {'info': {'title': 'Event sign-up'}, 'items': [{'title': 'Your name', 'questionItem': {'question': {'questionId': 'a1'}}}]}
        resp = {'responseId': 'x1', 'lastSubmittedTime': '2026-08-20T10:00:00Z', 'respondentEmail': 'pat@vendor.example',
                'answers': {'a1': {'textAnswers': {'answers': [{'value': 'Pat'}]}}}}
        with mock.patch('taskuary.sheets.google_sheets_connection', return_value={}), mock.patch('taskuary.sheets._token', return_value='G'), \
                wired({'/forms/GF1/responses': {'responses': [resp]}, '/forms/GF1': d}) as h:
            self.assertIn('Event sign-up', inboxes.test(s, c)); self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual(h.calls[-1][2]['headers']['Authorization'], 'Bearer G')
        self.assertTrue(h.calls[-1][2]['params']['filter'].startswith('timestamp > 2026-08-0'))
        r = rows(s, 'google_forms')[0]
        self.assertEqual((r['Subject'], r['FromEmail']), ('New response to Event sign-up', 'pat@vendor.example'))


class SharedInboxTests(unittest.TestCase):
    def test_helpscout_assigned_conversations_customer_is_a_stranger(self):
        s = fresh(); c = conn(s, 'helpscout', {'app_id': 'APP'})
        v = lambda i, by: {'id': i, 'number': 100 + i, 'subject': 'Refund', 'preview': 'Where is my refund?', 'status': 'active',
                           'primaryCustomer': {'id': 77, 'first': 'Pat', 'last': 'Buyer', 'email': 'pat@vendor.example'},
                           'createdBy': {'type': by}, 'userUpdatedAt': '2026-08-20T10:00:00Z'}
        with wired({'/oauth2/token': {'access_token': 'T', 'expires_in': 172800}, '/users/me': {'id': 5, 'firstName': 'Alex', 'lastName': 'Doyle'},
                    '/conversations': {'_embedded': {'conversations': [v(1, 'customer'), v(2, 'user')]}}}) as h:
            inboxes.test(s, c); self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertEqual(h.calls[0][2]['data']['client_id'], 'APP')
        self.assertEqual(h.calls[-1][2]['params']['assigned_to'], '5')
        a, b = rows(s, 'helpscout')
        self.assertFalse(trusted(s, a)); self.assertEqual(meta(b).get('member'), True)


    def test_front_assigned_with_the_newest_message_a_contact_is_a_stranger(self):
        s = fresh(); c = conn(s, 'front', {'email': 'alex@northwind.example'})
        msg = lambda a, frm: {'_results': [{'id': 'msg_1', 'text': 'Can you resend the invoice?', 'created_at': 1787220000.0, 'author': a,
                                            'recipients': [{'handle': frm, 'role': 'from', 'name': 'Pat Buyer'}]}]}
        with wired({'/teammates/alt:email:alex@northwind.example': {'id': 'tea_1', 'first_name': 'Alex', 'last_name': 'Doyle'},
                    '/teammates/tea_1/conversations': {'_results': [{'id': 'cnv_1', 'subject': 'Invoice', 'tags': [{'name': 'billing'}]},
                                                                    {'id': 'cnv_2', 'subject': 'Handover'}]},
                    '/conversations/cnv_1/messages': msg(None, 'pat@vendor.example'),
                    '/conversations/cnv_2/messages': msg({'id': 'tea_2', 'first_name': 'Erin', 'last_name': 'Blake'}, 'erin@northwind.example')}) as h:
            inboxes.test(s, c); self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertEqual(h.calls[1][2]['params']['q[statuses][]'], 'assigned')
        a, b = rows(s, 'front')
        self.assertEqual((a['FromEmail'], a['SourceLink']), ('pat@vendor.example', 'https://app.frontapp.com/open/cnv_1'))
        self.assertFalse(trusted(s, a)); self.assertEqual((b['FromName'], meta(b).get('member')), ('Erin Blake', True))


    def test_gorgias_keeps_only_my_open_tickets_a_shopper_is_a_stranger(self):
        s = fresh(); c = conn(s, 'gorgias', {'domain': 'northwind', 'email': 'alex@northwind.example'})
        t = lambda i, who, st='open': {'id': i, 'subject': 'Where is my order?', 'status': st, 'channel': 'email', 'excerpt': 'It has been a week',
                                       'assignee_user': {'email': who}, 'customer': {'id': 5, 'name': 'Pat Buyer', 'email': 'pat@vendor.example'},
                                       'updated_datetime': '2026-08-20T10:00:00Z'}
        with wired({'/api/account': {'domain': 'northwind'}, '/api/tickets': {'data': [t(1, 'Alex@northwind.example'), t(2, 'erin@northwind.example'),
                                                                                      t(3, 'alex@northwind.example', 'closed')]}}) as h:
            inboxes.test(s, c); self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual(h.calls[0][1], 'https://northwind.gorgias.com/api/account')
        r = rows(s, 'gorgias')[0]
        self.assertEqual(r['SourceLink'], 'https://northwind.gorgias.com/app/ticket/1'); self.assertFalse(trusted(s, r))


class PhoneTests(unittest.TestCase):
    def test_dialpad_missed_and_voicemail_with_the_transcript(self):
        s = fresh(); c = conn(s, 'dialpad', {'email': 'alex@northwind.example'})
        v = lambda i, **kw: {'call_id': i, 'direction': 'inbound', 'state': 'hangup', 'date_started': 1787220000000,
                             'contact': {'name': 'Pat Buyer', 'phone': '+15550100'}, **kw}
        with wired({'/company': {'name': 'Northwind'}, '/users': {'items': [{'id': 42}]},
                    '/call': {'items': [v(1, state='missed'), v(2, voicemail_link='https://dialpad.example/vm', transcription_text='Call me back'), v(3), v(4, direction='outbound', state='missed')]}}) as h:
            inboxes.test(s, c); self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertEqual((h.calls[-1][2]['params']['target_id'], h.calls[-1][2]['params']['target_type']), ('42', 'user'))
        a, b = rows(s, 'dialpad')
        self.assertEqual(a['Subject'], 'Missed call from Pat Buyer'); self.assertIn('Call me back', b['BodyText'])

    def test_aircall_missed_and_voicemail_on_my_lines_only(self):
        s = fresh(); c = conn(s, 'aircall', {'api_id': 'ID', 'email': 'alex@northwind.example'})
        call = lambda i, **kw: {'id': i, 'direction': 'inbound', 'raw_digits': '+1 555 0100', 'started_at': 1787220000,
                                'number': {'id': 11, 'name': 'Sales line'}, 'contact': None, 'user': None, **kw}
        with wired({'/ping': {'ping': 'pong'}, '/users/3': {'user': {'numbers': [{'id': 11}]}},
                    '/users': {'users': [{'id': 3, 'name': 'Alex Doyle', 'email': 'alex@northwind.example'}]},
                    '/calls/2/transcription': {'transcription': {'content': {'utterances': [{'text': 'Hi, it is about the order.'}]}}},
                    '/calls': {'calls': [call(1, missed_call_reason='agents_did_not_answer'), call(2, voicemail='https://aircall.example/vm2'),
                                         call(3, missed_call_reason='no_available_agent', number={'id': 99}), call(4, direction='outbound', missed_call_reason='x')]}}) as h:
            self.assertIn('1 line', inboxes.test(s, c)); self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertEqual(h.calls[0][2]['auth'], ('ID', 'tok'))
        a, b = rows(s, 'aircall')
        self.assertEqual(a['Subject'], 'Missed call from +1 555 0100'); self.assertIn('about the order', b['BodyText']); self.assertFalse(trusted(s, b))

    def test_ringcentral_voicemail_text_and_missed_call(self):
        s = fresh(); c = conn(s, 'ringcentral', {'client_id': 'CID', 'client_secret': 'CS'})
        vm = {'id': 1, 'type': 'VoiceMail', 'from': {'phoneNumber': '+15550100', 'name': 'Pat Buyer'}, 'creationTime': '2026-08-20T10:00:00Z',
              'attachments': [{'type': 'AudioRecording', 'uri': 'https://platform.ringcentral.com/rec'},
                              {'type': 'AudioTranscription', 'uri': 'https://platform.ringcentral.com/restapi/v1.0/tx/1'}]}
        sms = {'id': 2, 'type': 'SMS', 'subject': 'Running late', 'from': {'phoneNumber': '+15550101'}, 'creationTime': '2026-08-20T11:00:00Z',
               'conversation': {'id': 'C9'}}
        miss = {'id': 'L1', 'startTime': '2026-08-20T12:00:00Z', 'from': {'phoneNumber': '+15550102'}, 'result': 'Missed'}
        with wired({'/restapi/oauth/token': {'access_token': 'T', 'expires_in': 3600}, '/extension/~/message-store': {'records': [vm, sms]},
                    '/account/~/extension/~/call-log': {'records': [miss, {**miss, 'id': 'L2', 'result': 'Voicemail'}, {**miss, 'id': 'L3', 'result': 'Accepted'}]}, '/tx/1': R('Please call me about the invoice'),
                    '/account/~/extension/~': {'name': 'Alex Doyle', 'extensionNumber': '101'}}) as h:
            self.assertIn('extension 101', inboxes.test(s, c)); self.assertEqual(inboxes.poll(s, c, SINCE), 3)
        self.assertEqual(h.calls[0][2]['data']['grant_type'], 'urn:ietf:params:oauth:grant-type:jwt-bearer')
        self.assertEqual(h.calls[0][2]['data']['assertion'], 'tok')
        a, b, m = rows(s, 'ringcentral')
        self.assertIn('Please call me about the invoice', a['BodyText']); self.assertEqual(b['ConversationId'], 'ringcentral:sms:C9')
        self.assertEqual(m['Subject'], 'Missed call from +15550102'); self.assertFalse(trusted(s, a))


class HiringTests(unittest.TestCase):
    def test_lever_candidates_i_own_that_changed(self):
        s = fresh(); c = conn(s, 'lever', {'email': 'alex@northwind.example'})
        o = lambda i, own, **kw: {'id': f'opp{i}', 'name': 'Pat Candidate', 'headline': 'Senior accountant', 'owner': own, 'stage': {'text': 'Phone screen'},
                                  'updatedAt': 1787220000000, 'urls': {'show': f'https://hire.lever.co/candidates/opp{i}'}, **kw}
        with wired({'/users': {'data': [{'id': 'u1', 'name': 'Alex Doyle', 'email': 'alex@northwind.example'}]},
                    '/opportunities': {'data': [o(1, 'u1'), o(2, 'u2'), o(3, {'id': 'u1'}, archived={'reason': 'hired'})]}}) as h:
            inboxes.test(s, c); self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 1)
        self.assertEqual(h.calls[0][2]['auth'], ('tok', ''))
        r = rows(s, 'lever')[0]
        self.assertIn('Phone screen', r['BodyText']); self.assertFalse(trusted(s, r))


if __name__ == '__main__': unittest.main()

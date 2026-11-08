"""The owner's own replies from their phone, in a WhatsApp group Taskuary reads (the owner, 2026-11-08: "this should show what i sent (i replied
between these messages) as well even if it does not trigger as a prompt").

The shape that pinned it: Ray writes in the ops group, the owner answers from the phone - one line spoken as a voice note, one typed - and Ray
writes again. Only typed lines of the owner's were ever kept, so the spoken answer never reached the task. Each is the owner's own line on the
task Ray's lines sit on: never triaged, never an agent turn, and the agent's next turn hears what the owner said."""
import os, tempfile, unittest
from unittest import mock

from taskuary import general, ingest, messengers, voice
from taskuary.store import MemoryStore

G = '120363000000000042@g.us'
CONV = f'whatsapp:{G}'


def room():
    s = MemoryStore()
    c = s.get_connector_by_type('whatsapp')
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
    s.save_source({'Channel': 'whatsapp', 'Address': G, 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'o')
    tid = s.create_task({'Title': 'Book the van for Friday', 'Kind': 'general', 'Status': 'open'}, 't')
    s.add_message({'TaskId': tid, 'ExternalId': f'{CONV}:IN1', 'ConversationId': CONV, 'Channel': 'whatsapp', 'FromName': 'Ray Colton',
                   'FromEmail': 'whatsapp:8000', 'SentAt': '2026-11-08 16:49:30', 'BodyText': 'is the van booked?', 'Status': 'routed'})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Asked the rental desk; waiting on their answer.')
    s._exec("UPDATE comment SET CreatedAt='2026-11-08 16:50:00' WHERE TaskId=?", (tid,))
    return s, s.get_connector_by_type('whatsapp', with_secret=True), tid


class OwnPhoneReplyTests(unittest.TestCase):
    def test_a_spoken_and_a_typed_reply_from_the_phone_are_the_owners_own_on_the_task_never_a_turn(self):
        s, c, tid = room()
        ogg = os.path.join(tempfile.mkdtemp(), 'ME1.ogg')
        with open(ogg, 'wb') as f: f.write(b'OggS' + b'\0' * 32)
        at = lambda hm: int(__import__('datetime').datetime.strptime(f'2026-11-08 {hm}', '%Y-%m-%d %H:%M').timestamp())
        feed = {'seq': 3, 'messages': [
            {'seq': 1, 'id': 'ME1', 'jid': G, 'group': True, 'fromMe': True, 'text': '', 'audio': ogg, 'mime': 'audio/ogg', 'seconds': 4,
             'voice': True, 'ts': at('17:05')},
            {'seq': 2, 'id': 'ME2', 'jid': G, 'group': True, 'fromMe': True, 'text': 'for Friday morning', 'ts': at('17:20')},
            {'seq': 3, 'id': 'OUT1', 'jid': G, 'group': True, 'fromMe': True, 'taskuary': True, 'text': 'Booked for Friday.', 'ts': at('17:21')}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed), mock.patch('taskuary.wabridge.ready', lambda *a: None), \
             mock.patch.object(voice, 'note_body', return_value=('Yes, booked it this morning.\n\n(voice note (4s) from WhatsApp)', True, '')), \
             mock.patch.object(ingest, 'ingest_message', side_effect=AssertionError('the owner\'s line is never triaged')), \
             mock.patch('taskuary.ingest._spawn') as spawn, \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
            self.assertEqual(messengers.poll_whatsapp(s, c, s.list_sources(), llm=None), 0)
        self.assertEqual(spawn.call_args_list, [])                                    # no agent turn starts on it
        own = s._rows("SELECT * FROM message WHERE ConversationId=? AND Direction='out' ORDER BY SentAt", (CONV,))
        self.assertEqual([(m['ExternalId'][-3:], m['TaskId'], m['Status'], m['FromName']) for m in own],
                         [('ME1', tid, 'context', 'You'), ('ME2', tid, 'context', 'You')])  # Taskuary's own send is not one of them
        self.assertTrue(own[0]['BodyText'].startswith('Yes, booked it this morning.'))
        self.assertEqual([a['ContentType'] for a in s.list_attachments(own[0]['MessageId'])], ['audio/ogg'])
        self.assertEqual(len(s.list_tasks()), 1)                                      # no new ask made of it
        # ...drawn among Ray's lines as the owner's, and heard on the agent's next turn
        rows = [general.mail_row(s, x) for x in s._rows(general.JOINED, (tid,))]
        self.assertEqual([(r['who'], r['own'], r['channel']) for r in rows], [('Ray Colton', False, 'whatsapp'), ('You', True, 'whatsapp'), ('You', True, 'whatsapp')])
        lb = general.latest_block(s, tid)
        self.assertIn('WHAT THE OWNER REPLIED ON THE THREAD THEMSELVES', lb)
        self.assertIn('05:05 PM on WhatsApp: "Yes, booked it this morning.', lb); self.assertIn('05:20 PM on WhatsApp: "for Friday morning"', lb)
        # ...and read again (a restarted bridge hands everything over) it is kept once, never heard twice
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed), mock.patch('taskuary.wabridge.ready', lambda *a: None), \
             mock.patch.object(voice, 'note_body', side_effect=AssertionError('heard twice')):
            messengers.poll_whatsapp(s, s.get_connector_by_type('whatsapp', with_secret=True), s.list_sources(), llm=None)
        self.assertEqual(len(s._rows("SELECT 1 FROM message WHERE Direction='out'")), 2)


if __name__ == '__main__': unittest.main()

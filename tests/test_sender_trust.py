"""Who may start a worker unattended is a visible setting, and prior incoming mail is never trust (PW-079 to PW-083).

The stranger gate had a hidden fourth door: "has written before". Two messages from an unknown
address, a historical import or a retry made the second one 'known' and started the agent the hold
existed to stop. Now the gate is three rules the owner can see and switch in Settings - the owner's
own domains, verified Sent Items evidence that THIS mailbox wrote to the exact address, and chat
channels inside a workspace the owner controls - and nothing else. A Sent Items lookup that fails is
not proof of trust: the task waits for a manual start with the failure said on it. A verified hit is
remembered per mailbox and address so the mailbox is asked once. The same contract gates both
worker kinds; a hold affects the unattended start only.
"""
import json, pathlib, unittest
from unittest import mock

from taskuary import general, ingest, senders
from taskuary.store import MemoryStore

ASK = 'Can you sit in on the board meeting Thursday and take the minutes?'


def store(**settings):
    s = MemoryStore()
    s.set_setting('owner_email', 'dana@northwind.example', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s


def msg(frm='rita@partner.example', channel='email', **kw):
    return {'external_id': 'x1', 'channel': channel, 'subject': 'board meeting', 'body': ASK, 'from_email': frm, 'from_name': 'Rita',
            'conversation_id': 'AAQk-board', 'sent_at': '2026-09-06 09:00', 'source_name': 'dana@northwind.example', **kw}


def row(s, frm, i=1):
    return s.add_message({'ExternalId': f'r{i}', 'Channel': 'email', 'Subject': 's', 'FromEmail': frm, 'SentAt': '2026-09-06 09:00', 'BodyText': ASK, 'Status': 'routed'})


class RulesTests(unittest.TestCase):
    def test_prior_incoming_mail_is_not_trust(self):
        s = store()
        mid = row(s, 'rita@partner.example')
        with mock.patch.object(s, 'known_sender', return_value=True), mock.patch.object(senders, 'wrote_to', return_value=False):
            ok, why = senders.known(s, msg(), exclude_mid=mid, deep=True)
        self.assertEqual(ok, False); self.assertIn('first message from', why); self.assertNotIn('written before', why)

    def test_verified_sent_history_allows_and_names_the_reason(self):
        s = store()
        with mock.patch.object(senders, 'wrote_to', return_value=True):
            ok, why = senders.known(s, msg(), deep=True)
        self.assertEqual((ok, why), (True, 'in your Sent Items'))

    def test_a_verified_hit_is_remembered_per_mailbox_and_address_so_the_mailbox_is_asked_once(self):
        s = store()
        with mock.patch.object(senders, 'wrote_to', return_value=True) as wrote:
            senders.known(s, msg(), deep=True); senders.known(s, msg(), deep=True)
        self.assertEqual(wrote.call_count, 1)
        with mock.patch.object(senders, 'wrote_to', return_value=True) as wrote:
            senders.known(s, msg(source_name='other@northwind.example'), deep=True)      # another mailbox: its own evidence
        self.assertEqual(wrote.call_count, 1)

    def test_a_failed_lookup_is_not_trust_and_says_so(self):
        s = store()
        with mock.patch.object(senders, 'wrote_to', side_effect=RuntimeError('IMAP timed out')):
            ok, why = senders.known(s, msg(), deep=True)
        self.assertEqual(ok, False); self.assertIn('could not check', why); self.assertIn('IMAP timed out', why)
        with mock.patch.object(senders, 'wrote_to', return_value=True):
            self.assertEqual(senders.known(s, msg(), deep=True)[0], True)                 # a failure is not remembered as 'no'

    def test_each_rule_has_a_switch(self):
        s = store(trust_sent_history='0')
        with mock.patch.object(senders, 'wrote_to', return_value=True) as wrote:
            ok, why = senders.known(s, msg(), deep=True)
        wrote.assert_not_called(); self.assertEqual(ok, False); self.assertIn('Settings', why)
        s = store(trust_own_domain='0')
        ok, why = senders.known(s, msg(frm='sam@northwind.example'))
        self.assertEqual(ok, False); self.assertIn('Settings', why)
        s = store(trust_non_email='0')
        ok, why = senders.known(s, msg(channel='teams', frm=None))
        self.assertEqual(ok, False); self.assertIn('Settings', why)
        s = store()
        self.assertEqual(senders.known(s, msg(frm='sam@northwind.example'))[1], 'your own domain')
        self.assertIn('workspace you control', senders.known(s, msg(channel='teams', frm=None))[1])

    def test_the_lookup_is_scoped_to_the_receiving_mailbox(self):
        s = store()
        with mock.patch.object(senders, 'wrote_to', return_value=False) as wrote:
            senders.known(s, msg(source_name='billing@northwind.example'), deep=True)
        self.assertEqual(wrote.call_args[0][1:], ('billing@northwind.example', 'rita@partner.example'))

    def test_prior_incoming_history_stays_available_to_the_policy_engine(self):
        """`store.known_sender` still answers the first-time-sender POLICY question; it is only out of the
        unattended-start gate."""
        s = store()
        self.assertTrue(hasattr(s, 'known_sender'))
        src = pathlib.Path(senders.__file__).read_text(encoding='utf-8')
        self.assertNotIn('known_sender(', src.split('def known(')[1].split('def wrote_to')[0])


class BothKindsTests(unittest.TestCase):
    def test_the_configured_trust_gates_coding_and_general_alike_and_a_hold_is_only_about_the_start(self):
        for kind in ('coding', 'general'):
            s = store()
            with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=False), \
                 mock.patch.object(general, 'provider_options', return_value=[{'pick': 'p'}]):
                out = ingest.ingest_message(s, msg(), llm=lambda *a, **k: json.dumps({'intent': 'task', 'kind': kind, 'why': 'w'}))
            self.assertEqual(spawn.call_args_list, [], kind)
            self.assertEqual(out['status'], 'created', kind)                        # intake, triage and the task are untouched
            self.assertTrue(s.task_has_tag(out['task_id'], ingest.HOLD_TAG), kind)
            s2 = store()
            with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
                 mock.patch.object(general, 'provider_options', return_value=[{'pick': 'p'}]):
                out2 = ingest.ingest_message(s2, msg(), llm=lambda *a, **k: json.dumps({'intent': 'task', 'kind': kind, 'why': 'w'}))
            self.assertEqual(len(spawn.call_args_list), 1, kind)
            self.assertTrue(any('in your Sent Items' in c['Body'] for c in s2.list_comments(out2['task_id'])), kind)   # the matched reason is shown

    def test_a_failed_lookup_leaves_the_task_for_a_manual_start_with_the_explanation(self):
        s = store()
        with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', side_effect=RuntimeError('Graph 503')), \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'p'}]):
            out = ingest.ingest_message(s, msg(), llm=lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'w'}))
        self.assertEqual(spawn.call_args_list, [])
        self.assertTrue(any('could not check' in c['Body'] and 'Graph 503' in c['Body'] for c in s.list_comments(out['task_id'])))
        self.assertFalse(s.task_has_tag(out['task_id'], ingest.HOLD_TAG))          # not a stranger verdict - a lookup that failed


class SettingsTests(unittest.TestCase):
    def test_defaults_and_exposure(self):
        s = MemoryStore(); cfg = s.get_settings()
        self.assertEqual((cfg.get('trust_own_domain'), cfg.get('trust_sent_history'), cfg.get('trust_non_email')), ('1', '1', '1'))
        src = pathlib.Path(__file__).resolve().parents[1].joinpath('website', 'src', 'SettingsView.jsx').read_text(encoding='utf-8')
        for k in ('trust_own_domain', 'trust_sent_history', 'trust_non_email'): self.assertIn(k, src)
        self.assertNotIn('has written before', src)


if __name__ == '__main__':
    unittest.main()

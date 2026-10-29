"""One sign-up, one road, whichever door it is started from (the owner, 2026-10-29: "if it's not hard-coded, triage knows what to do no?").

A forwarded webinar invite with "sign me up" got three outcomes from the task's box, Send to agent and the assistant chat: only the
New sheet's toggle ever wrote "needs a browser", so each door gave the agent a browser or not by its own luck. Triage reads the ask
once and says whether the work is done on a web page (needs_browser); every door that starts an agent - general.start_session (the
task's box, Send to agent, the offer, the assistant's hand-off) and the coding seed - opens Taskuary's browser for it, where the submit
waits for the owner's Approve. A stranger's task never gets one.
"""
import json, unittest
from unittest import mock

from taskuary import browserview, general, ingest, terminal, triage
from taskuary.store import MemoryStore
from tests.test_general import connect_cli

ME = 'alex@northwind.example'
FWD = ('Sign me up for this one please.\n\n---------- Forwarded message ---------\nFrom: Events <events@vendor.example>\n'
       'Subject: Live webinar: closing the books faster\nRegister here: https://vendor.example/webinar/register')


def verdict(**v):
    def llm(system, user, **k):
        return json.dumps({'intent': 'task', 'kind': 'general', 'why': 'the owner asks to be registered', 'title': 'Register Alex for the webinar',
                           'summary': 's', 'sender_class': 'person', **v})
    return llm


def arrive(s, llm, frm=ME, name='Alex Doyle'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': 'f1', 'channel': 'email', 'from_email': frm, 'from_name': name, 'to': [ME],
                                         'conversation_id': 'conv-f1', 'subject': 'Fwd: Live webinar', 'body': FWD,
                                         'sent_at': '2026-10-29 09:00:00'}, llm=llm)


def owner_store():
    s = MemoryStore(); s.set_setting('owner_email', ME, 't')
    return s


class TheVerdictSaysIt(unittest.TestCase):
    def test_needs_browser_is_asked_for_and_kept_on_a_task_only(self):
        self.assertIn('needs_browser', triage.verdict_schema()['schema']['properties'])
        self.assertIn('**needs_browser**', triage.SHIPPED)
        self.assertTrue(triage.classify_intent({'body': FWD}, llm=verdict(needs_browser=True)).get('needs_browser'))
        fyi = triage.classify_intent({'body': FWD}, llm=verdict(intent='fyi', needs_browser=True))
        self.assertNotIn('needs_browser', fyi)

    def test_an_older_document_is_still_told_what_it_means(self):
        seen = []
        def llm(system, user, **k):
            seen.append(system); return verdict()(system, user)
        triage.classify_intent({'body': FWD}, llm=llm, system='# My own triage guide\nJudge each message.')
        self.assertIn('needs_browser', seen[0])


class EveryDoorGetsTheBrowser(unittest.TestCase):
    def setUp(self):
        self.s = owner_store()
        self.tid = arrive(self.s, verdict(needs_browser=True))['task_id']
        self.assertFalse(browserview.wanted(self.s.get_task(self.tid)), 'nothing is tagged until an agent starts')

    def test_the_general_door_tags_it_once_and_opens_the_browser(self):
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        with mock.patch('taskuary.agents.runs_here', lambda p: bool((p or {}).get('cmd'))), \
             mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(general.threading, 'Thread') as thread:
            session = general.start_session(self.s, self.tid)
        self.assertTrue(browserview.wanted(self.s.get_task(self.tid)))
        self.assertTrue(session.browser_wanted)
        self.assertTrue(session.pick.startswith('cli:'), 'a browser task is a CLI\'s')
        self.assertIs(thread.call_args.kwargs['target'], browserview.start)
        notes = [c['Body'] for c in self.s.list_comments(self.tid) if "Taskuary's browser" in c['Body']]
        self.assertEqual(len(notes), 1); self.assertIn('Approve', notes[0])
        self.assertTrue(ingest.mark_browser(self.s, self.tid))
        self.assertEqual(len([c for c in self.s.list_comments(self.tid) if "Taskuary's browser" in c['Body']]), 1, 'said once')

    def test_the_coding_seed_reads_it_too(self):
        with mock.patch.object(terminal.shutil, 'which', return_value='agent-browser'):
            text = terminal.seed_text(self.s, self.tid, cli='claude')
        self.assertTrue(browserview.wanted(self.s.get_task(self.tid)))
        self.assertIn('agent-browser', text)


class WhatTheVerdictDidNotSay(unittest.TestCase):
    def test_no_needs_browser_no_tag(self):
        s = owner_store(); tid = arrive(s, verdict(needs_browser=False))['task_id']
        self.assertFalse(ingest.mark_browser(s, tid)); self.assertFalse(browserview.wanted(s.get_task(tid)))
        s2 = owner_store(); tid2 = arrive(s2, verdict())['task_id']
        self.assertFalse(ingest.mark_browser(s2, tid2))

    def test_a_strangers_task_never_gets_one(self):
        s = owner_store(); tid = arrive(s, verdict(needs_browser=True), frm='events@vendor.example', name='Events')
        tid = tid['task_id']
        with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'a first-time sender')):
            self.assertFalse(ingest.mark_browser(s, tid))
        self.assertFalse(browserview.wanted(s.get_task(tid)))

    def test_the_offer_never_says_to_press_the_submit_unasked(self):
        self.assertIn('Never press it unasked', ingest.OFFER_JOB)


if __name__ == '__main__':
    unittest.main()

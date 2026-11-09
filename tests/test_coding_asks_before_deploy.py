"""A change that only counts once it is LIVE stops at a question, not at --done.

A coding agent finished a change the requester gets only once it is deployed, committed it, saved a
reply saying "done... I'll let you know when it's live" and ran --done - and the owner had to Continue
it with "make this live". CODING.md said "do not push, deploy, publish or release unless the brief says
you may: commit locally and stop" and nothing about what that stop is when the work is not done until
it ships. Now it is a question asked in the session, and a reply never promises a later step.
"""
import tempfile, unittest
from pathlib import Path

import taskuary
from taskuary import brief, store as store_mod, terminal
from taskuary.store import MemoryStore, SQLiteStore

T = Path(taskuary.__file__).parent / 'templates'
CODING, AGENT = [(T / f'{n}.md').read_text(encoding='utf-8') for n in ('coding', 'agent')]


class ShippedWordingTests(unittest.TestCase):
    def test_coding_md_asks_before_a_deploy_and_does_not_close(self):
        sec = CODING.split('## Editing, testing, committing', 1)[1].split('##', 1)[0]
        for s in ('only once the change is LIVE', 'no `--reply`, no `--done`', 'check it is live, then finish', "the brief or John's Continue says to"):
            self.assertIn(s, sec, s)
        self.assertNotIn(store_mod._DEPLOY_WAS, CODING); self.assertNotIn(store_mod._DEPLOY_ASKED, CODING)
        self.assertIn("not waiting on John's go-ahead", CODING.split('## Closing out', 1)[1].split('##', 1)[0])

    def test_the_stop_before_a_push_is_the_owners_button_never_a_question_in_words(self):
        # the owner, 2026-11-09 (~20th time): "i thought actions should be cards/buttons??? why is this text??" - CODING.md had the agent
        # ask "ready to deploy <what> to <where> - go ahead?" in prose, and the owner typed "yes"
        sec = CODING.split('## Editing, testing, committing', 1)[1].split('##', 1)[0]
        self.assertIn("that stop is John's button, never a question in words: call\n  `propose_land` - `how` push and `deploy`", sec)
        self.assertIn('your prompt says you may push and deploy', sec, 'a trusted repo goes without stopping')
        self.assertNotIn('ask John here, "ready to', sec)
        from taskuary import agenttools
        kind, words, schema, road = agenttools.TOOLS['propose_land']
        self.assertEqual((kind, road), ('propose', ('POST', '/api/agent/propose-land')))
        self.assertIn('push', schema['properties']['how']['enum']); self.assertIn('deploy', schema['properties'])
        self.assertIn('never ask it in words', words)

    def test_an_edited_copy_that_still_asks_in_words_is_moved_to_the_button(self):
        path = Path(tempfile.mkdtemp()) / 'taskuary.db'
        s = SQLiteStore(str(path)); s.save_doc('coding', 'MY RULE.\r\n' + store_mod._DEPLOY_ASKED.replace('\n', '\r\n') + '\r\nlast.', 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='coding_proposes_push'"); s.cx.commit()
        c = SQLiteStore(str(path)).get_doc('coding')
        self.assertIn(store_mod._DEPLOY_NOW.replace('\n', '\r\n'), c); self.assertNotIn('go ahead?", and wait', c)
        self.assertTrue(c.startswith('MY RULE.') and c.endswith('last.'))

    def test_agent_md_never_promises_a_later_step(self):
        sec = AGENT.split('## Progress and completion', 1)[1]
        self.assertIn('A reply goes when what it says is true', sec)
        self.assertIn("Never promise a later step (\"I'll let you know when it's live\")", sec)
        self.assertIn('say plainly what, and who does it', sec)

    def test_the_seed_says_it_too_when_pushing_is_off(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Ship the export fix', 'Kind': 'coding', 'Status': 'open'}, 'o')
        self.assertIn("to go live, propose_land (how push, deploy <branch>) - never ask it in words", terminal.seed_text(s, tid))

    def test_the_migration_says_what_the_templates_say(self):
        self.assertIn(store_mod._DEPLOY_NOW, CODING)
        self.assertIn(store_mod._PROMISE_NOW + store_mod._PROMISE_AT, AGENT)

    def test_both_documents_reach_the_session_whole(self):
        """The budgets are measured, not trusted: AGENT.md had grown past AGENT_CHARS and lost its last sentence."""
        s = MemoryStore()
        self.assertTrue(brief.rules(s, 'agent', terminal.AGENT_CHARS).endswith(terminal.flatten_rules(s.doc('agent'))[-80:]))
        self.assertLess(len(terminal.flatten_rules(s.doc('coding'))), terminal.DOC_CHARS)
        self.assertLess(len(terminal.flatten_rules(s.doc('agent'))), terminal.AGENT_CHARS)


class EditedCopyTests(unittest.TestCase):
    """A CODING.md / AGENT.md the owner edited stops tracking the template; the two rules still go in, once."""

    def setUp(self): self.path = Path(tempfile.mkdtemp()) / 'taskuary.db'

    def _reopen(self, coding, agent, nl='\n'):
        s = SQLiteStore(str(self.path))
        s.save_doc('coding', coding.replace('\n', nl), 'owner'); s.save_doc('agent', agent.replace('\n', nl), 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='coding_asks_before_deploy'"); s.cx.commit()
        return SQLiteStore(str(self.path))

    def test_an_edited_copy_gets_the_rules_and_keeps_the_rest(self):
        s = self._reopen('MY RULE: Erin reviews every change.\n' + store_mod._DEPLOY_WAS + '\nmy last line.',
                         'MY RULE one.\n' + store_mod._PROMISE_AT + ' - say it.')
        c, a = s.get_doc('coding'), s.get_doc('agent')
        self.assertNotIn(store_mod._DEPLOY_WAS, c); self.assertIn(store_mod._DEPLOY_NOW, c)
        self.assertIn('MY RULE: Erin reviews every change.', c); self.assertIn('my last line.', c)
        self.assertIn(store_mod._PROMISE_NOW + store_mod._PROMISE_AT + ' - say it.', a); self.assertIn('MY RULE one.', a)

    def test_crlf_copies_stay_crlf(self):
        c = self._reopen('a\n' + store_mod._DEPLOY_WAS + '\nb', 'x\n' + store_mod._PROMISE_AT, nl='\r\n').get_doc('coding')
        self.assertNotIn('\n', c.replace('\r\n', ''))

    def test_it_runs_once(self):
        s = self._reopen('x\n' + store_mod._DEPLOY_WAS, 'y')
        s.save_doc('coding', 'the old way: ' + store_mod._DEPLOY_WAS, 'owner'); s.cx.commit()
        self.assertIn(store_mod._DEPLOY_WAS, SQLiteStore(str(self.path)).get_doc('coding'))

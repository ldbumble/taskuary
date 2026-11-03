"""The everyday asks (tests/assistant_queries.py), held: each one's road is right or honestly unsupported, never wrong and never a bare
"Next." - the owner's "Clear all the FYI, please." was answered "Next." (2026-10-20). No real model is ever asked: the scripted brains
answer, and the CLI and API builders raise if anything reaches for one."""
import unittest

from taskuary import concierge
from tests import assistant_queries as Q

# what no tool or desk button does today - a new tool takes its ask off this list on purpose (ASK OWNER before building one)
UNSUPPORTED = {'archive all the read mail', 'use dark mode', 'make the font bigger'}
# ...and the row buttons a phone chat cannot reach - each opens something only a screen has (the diff, a second agent's form, a file picker)
# ...and Copy, which puts an unsendable draft on the screen's own clipboard - a phone chat's draft is already text to copy
# ...and a result's Share: its link goes on the screen's clipboard and its Email it picks people in a dialog (ASK OWNER: Email it by phone)
# (Watch it left this list 2026-11-02: "watch this" typed by phone is task.watch, whose yes runs the row's task.watching - the phone audit)
PHONE_UNREACHABLE = {'review_changes', 'run_another', 'attach', 'copy', 'share_result', 'strong_again'}   # strong_again: the task page's own press (the router, 2026-10-25)


class EverydayAsks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rows = Q.run_all()

    def test_there_are_enough_of_them_in_every_category(self):
        self.assertGreaterEqual(len(self.rows), 240)
        cats = {r['q'].cat for r in self.rows}
        # ...and the powers the pop-up Assistant gained since (the owner, 2026-11-01: "we now expanded the scope of the pop up assistant
        # powers"): the page it is shown, Taskuary's own trouble, its tracker, its help, work that is an agent's, the newer row buttons
        self.assertEqual(cats, {'navigation', 'bulk', 'item', 'question', 'settings', 'agents', 'reports', 'chat', 'typos', 'short',
                                'bring-up', 'connectors', 'phone', 'memory', 'page', 'troubleshoot', 'feedback', 'help', 'agentwork',
                                'row', 'sets', 'new', 'people', 'app', 'task', 'rail', 'connections',
                                'hub-board-search', 'self-knowledge'})

    def test_a_connection_asked_after_by_its_type_is_the_owners_live_card(self):
        # the owner's Outlook card is named "Work mail"; "outlook" matched the catalogue's unused "Outlook mail" card first and the owner
        # was told their connected mail was switched off, with its Open button under the line (troubleshoot.find, 2026-11-02)
        r = next(r for r in self.rows if r['q'].text == 'is the outlook connection healthy')
        self.assertEqual(r['ideal']['got'], ['read:app.health'])
        self.assertIn('Work mail', r['ideal']['told']); self.assertNotIn('switched off', r['ideal']['told'])

    def test_every_row_action_is_reachable_on_the_desk_and_all_but_the_screens_own_on_a_phone(self):
        self.assertEqual({v for v, d, p in Q.reach() if not d}, set())
        self.assertEqual({v for v, d, p in Q.reach() if not p}, PHONE_UNREACHABLE)

    def test_every_answer_that_acts_says_what_it_did(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text): self.assertNotEqual(r['ideal']['grade'], 'silent', r['ideal']['say'][:200])

    def test_a_connector_brought_up_to_connect_lights_its_first_step(self):
        # the card opens with &step=1, and the line names the lit step once the page has lit it (website/src/connectorStep.js)
        for r in (r for r in self.rows if r['q'].cat == 'connectors' and r['q'].expect.startswith('open:')):
            with self.subTest(ask=r['q'].text):
                opened = next(g for g in r['ideal']['got'] if g.startswith('open:'))
                if 'Add another' in r['ideal']['say']: self.assertNotIn('&step=1', opened)
                else: self.assertTrue(opened.endswith('&step=1')); self.assertIn('keys go there, never in chat', r['ideal']['say'])

    def test_every_bring_up_opens_its_exact_target(self):
        for r in (r for r in self.rows if r['q'].cat == 'bring-up'):
            with self.subTest(ask=r['q'].text): self.assertIn(r['q'].expect, r['ideal']['got'])

    def test_taskuarys_road_does_what_a_good_answer_asked(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text, table=r['q'].table):
                self.assertIn(r['ideal']['grade'], ('right', 'unsupported'),
                              f"expected {r['q'].expect}, got {r['ideal']['got']}: {r['ideal']['say'][:200]!r} / told {r['ideal']['told'][:200]!r}")

    def test_the_unsupported_list_is_the_one_we_know(self):
        self.assertEqual({r['q'].text for r in self.rows if r['ideal']['grade'] == 'unsupported'}, UNSUPPORTED)

    def test_the_real_prompt_carries_a_tool_for_every_supported_ask(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text): self.assertEqual(r['ideal']['missing'], [])

    def test_the_demo_reads_no_typed_words_and_says_so_with_its_suggestions(self):
        """The owner, 2026-10-28: the demo never decides what typed words mean - every ask here gets the honest line and the suggestion
        chips, never a link, a lit button or a press guessed from its words (demo.PROMPTS answers only its own chips' words)."""
        for r in self.rows:
            with self.subTest(ask=r['q'].text):
                self.assertEqual(r['demo']['line'], 'out', r['demo']['say'][:160])
                self.assertNotEqual(r['demo']['say'].strip(), concierge.RECEIPTS['next'])

    def test_on_the_page_a_send_is_lit_for_the_owner_and_a_secret_never_set(self):
        r = next(r for r in self.rows if r['q'].cat == 'page' and r['q'].text == 'send it')
        self.assertEqual([g for g in r['ideal']['got'] if g.startswith('view:')], ['view:point:row:approve'])
        r = next(r for r in self.rows if r['q'].text.startswith('put my password in'))
        self.assertFalse([g for g in r['ideal']['got'] if g.startswith('view:')])

    def test_work_that_is_an_agents_goes_to_one_never_done_in_the_chat(self):
        # the owner, 2026-11-01: an image asked of the Assistant was "created" in the chat and never shown - it is an agent's job
        for r in (r for r in self.rows if r['q'].cat == 'agentwork' and r['q'].text.startswith(('make me', 'write'))):
            with self.subTest(ask=r['q'].text): self.assertIn('new:agent:general', r['ideal']['got'])

    def test_a_job_written_into_new_names_the_press_its_tab_draws(self):
        # the audit of New, 2026-11-02: "Wrote it into New - Build it there starts it." over a report, a dashboard and a routine, whose tab
        # has had Set up with AI since 2026-10-30 (NewSheet.jsx) - and a goal's press is Plan it while an AI can plan the steps
        from taskuary import capabilities
        drawn = {'agent:general': 'Send to agent', 'agent:terminal': 'Send to coding agent', 'send': 'Draft it', 'note': 'Note it',
                 'goal': 'Plan it' if capabilities.has_ai(Q._world()) else 'Track it',
                 **{k: 'Set up with AI' for k in ('report', 'dashboard', 'workflow', 'playbook')}}
        for r in (r for r in self.rows if r['q'].cat == 'new' and r['q'].expect.startswith('new:')):
            with self.subTest(ask=r['q'].text):
                # ...an agent's job is pressed for the owner (the owner, 2026-11-02: "why can't assistant start an agent. i'm okay with that")
                if r['q'].expect.startswith('new:agent'):
                    self.assertEqual(r['ideal']['say'], f"Wrote it into New and pressed {drawn[r['q'].expect[4:]]}.")
                    self.assertIn('press:new', r['ideal']['got'])
                else: self.assertEqual(r['ideal']['say'], f"Wrote it into New - {drawn[r['q'].expect[4:]]} there starts it.")

    def test_a_message_on_whatsapp_comes_up_on_whatsapp_to_the_group_named(self):
        # the owner, 2026-11-02: "write to the team WhatsApp group that ..." opened Send something on email with To empty
        from tests.assistant_queries import TEAM_GROUP
        r = next(r for r in self.rows if r['q'].text.startswith('write to the Northwind team WhatsApp group'))
        self.assertIn(f'to:whatsapp:{TEAM_GROUP}', r['ideal']['got']); self.assertNotIn('press:new', r['ideal']['got'])

    def test_the_assistant_starts_an_agent_and_tells_one_at_work_but_never_sends(self):
        # the owner, 2026-11-02: "it itself should not be the agent" - "start it" presses Send to agent, "tell the agent ..." reaches the
        # session as its next prompt, and a send in words still only lights (the page's Send, the row's Send)
        rows = {(r['q'].text, r['q'].table, r['q'].view is not None, r['q'].phone, r['q'].live): r['ideal']['got'] for r in self.rows}
        self.assertIn('did:dispatch.prepare', rows[('start it', 'todo', False, False, None)])
        self.assertIn('view:press:send_to_coding_agent', rows[('go ahead', None, True, False, None)])
        self.assertIn('did:agent.tell', rows[('tell the agent to use the main branch', 'todo', False, False, 1)])
        self.assertIn('did:agent.tell', rows[('tell the agent to use the main branch', 'todo', False, True, 1)])           # by phone too
        self.assertEqual(rows[('tell the agent to use the main branch', 'todo', False, False, None)], ['words'])     # nobody at work
        self.assertIn('light:approve', rows[('send it', 'review', False, False, None)])          # ...and on the page, a point (the test above)

    def test_every_address_an_ask_about_new_is_answered_with_is_one_the_prompt_names(self):
        # "I want to start something new" and "open the new dashboard builder" had no address in APP PAGES (2026-11-02)
        pages = concierge.pages_block(Q._world())
        for r in (r for r in self.rows if r['q'].cat == 'new' and r['q'].expect.startswith('link:')):
            with self.subTest(ask=r['q'].text): self.assertIn(r['q'].expect[5:], pages)

    def test_a_number_on_the_desk_is_the_action_word_it_numbers(self):
        r = next(r for r in self.rows if r['q'].text == '2')
        self.assertNotEqual(r['ideal']['heard'], '2', 'the digit reached the model as a digit')
        # ...and over a task drawn as its own view, which numbers nothing, it is the owner's digit as typed - never a hidden chip (2026-10-26)
        r = next(r for r in self.rows if r['q'].text == '3')
        self.assertEqual((r['ideal']['heard'], [g for g in r['ideal']['got'] if g.startswith(('pressed', 'light'))]), ('3', []))

    def test_the_rail_walk_starts_at_the_section_named_and_back_is_the_row_above(self):
        # the rail audit, 2026-11-02: "walk me through the reports" brought up the top of Tasks; "go back" was refused with Back on screen
        r = next(r for r in self.rows if r['q'].text == 'walk me through the reports')
        self.assertRegex(r['ideal']['say'], r'^Opened a report')
        r = next(r for r in self.rows if r['q'].text == 'go back to the one before')
        self.assertEqual(r['ideal']['say'], 'Opened TQ-0030.', 'Back from TQ-0001 is the row above it, Start here')

    def test_the_habits_row_names_each_habit_and_answers_it_in_the_owners_words(self):
        # the model was told only "Learned 1 habit · 1 to check"; a habit taken back read "Took {{owner_first}} closes..." (2026-11-02)
        r = next(r for r in self.rows if r['q'].text == 'what habits did you learn about me?')
        self.assertIn('[key: sso threads] adopted', r['ideal']['prompt']); self.assertIn('[key: fwd fyi] asking', r['ideal']['prompt'])
        for r in (r for r in self.rows if r['q'].seed is Q.habits_row and r['q'].expect.startswith('did:')):
            with self.subTest(ask=r['q'].text):
                self.assertNotIn('{{', r['ideal']['say']); self.assertIn('1 habit still on the habits row', r['ideal']['say'])

    def test_a_watched_task_is_said_watched_where_the_assistant_reads_it(self):
        # "what am I watching?" and "where did it go?" read tasks.list and task.read, and neither said so (2026-11-02)
        r = next(r for r in self.rows if r['q'].text == f'where did {Q.T2} go')
        self.assertIn('WATCHED since', r['ideal']['told'])
        s = Q._world(); Q.watched(s)
        line = next(l for l in concierge.read_op(s, 'tasks.list', {}).splitlines() if l.startswith(Q.T2))
        self.assertTrue(line.endswith('watching (Watch it)'), line)

    def test_on_the_connections_page_the_model_is_told_what_it_needs(self):
        # the Connections audit, 2026-11-02: a road that grades right can still tell the model too little to answer well
        told = {r['q'].text: r['ideal']['told'] for r in self.rows if r['q'].cat == 'connections'}
        # a system with no card: the miss names the feature request, and never asks it to name closest cards there are none of
        self.assertIn('issue.draft', told['connect Frobnitz']); self.assertNotIn('naming those', told['connect Frobnitz'])
        # a catalogue card never set up is not set up - not "switched off", as if the owner had turned it off
        self.assertIn('Gmail / Google Workspace is not set up yet', told['gmial wont conect'])
        # ...and the help it reads says a data card is a report's, and what the voice cards do
        self.assertIn('never puts work on your rail', told['will quickbooks put bills on my task list?'])
        self.assertIn('AI · voice', told['how do voice notes get transcribed?'])

    def test_the_hub_board_and_search_are_worked_where_they_stand(self):
        # the assistant audit, 2026-11-02: "put this on the hub" was refused as a tool with no button - the Hub's Write one is its press;
        # a post opened on the page opens by its number, as a click writes it; a removed Hub post is said to be on the Hub's own shelf
        r = {x['q'].text: x['ideal'] for x in self.rows if x['q'].cat in ('hub-board-search', 'app')}
        self.assertIn('open:#hub', r['put this on the hub: finance closes on the first Wednesday']['got'])
        self.assertIn('Write one', r['put this on the hub: finance closes on the first Wednesday']['say'])
        self.assertIn('open:#hub', r['save to the hub: the bank feed lags a day at month end']['got'])
        # ...and since 2026-11-02 a post the owner removed is under Recently deleted, the Hub brought up with it; the vote's is said to be on
        # the Hub's own shelf
        self.assertIn('open:#hub', r['bring back the hub post I removed']['got'])
        self.assertIn("the Hub's own removed shelf", r['bring back the post the vote took off']['told'])
        # THE DIALOGS ARE VIEWS AND THE BELL A TOOL (the owner, 2026-11-02): Write one's Post it is lit, a Search hit pressed, the bell put down
        self.assertIn('view:press:write_one', r['write one: the bank feed lags a day at month end']['got'])
        self.assertIn('view:open:search', r['search everything for pyodbc and open the first hit']['got'])
        self.assertTrue(r['clear the error on the bell']['say'].startswith('Put down “GitHub'), r['clear the error on the bell']['say'])
        self.assertIn('Work mail', r['clear the bell']['told'])
        self.assertEqual([g for g in r['comment that the driver is in the build image now']['got'] if g.startswith('view:point')], ['view:point:post'])

    def test_clear_all_the_fyi_clears_them_and_says_how_many(self):
        r = next(r for r in self.rows if r['q'].text == 'Clear all the FYI, please.')
        self.assertIn('cleared', r['ideal']['got']); self.assertRegex(r['ideal']['say'], r'^Marked (all )?\d+ (items?|FYI|reports?) read')


class WhatItKnowsOnEveryPage(unittest.TestCase):
    """The owner's documents reach the Assistant's instructions whatever page it is asked on (the owner, 2026-11-01: "it has the right
    tools, memories, and jobs/soul.md to be able to help the user on every page"). SOUL, JOB, COUNSEL and the memory's lines in use ride
    every turn, on the desk and on a phone; STYLE.md and AGENT.md are read on asking (docs.search names them) - nothing pinned this."""
    def test_soul_job_counsel_and_the_memory_reach_it_on_every_page_and_style_and_agent_on_asking(self):
        from contextlib import ExitStack
        from unittest import mock
        from taskuary import __version__, counsel as counsel_doc, memoryedit, server
        s = Q._world()
        memoryedit.remember(s, 'I put vendor renewals off to Friday', section='work')
        soul, job, counsel = (next(l for l in str(d).splitlines() if len(l.strip()) > 30).strip()
                              for d in (s.doc('soul'), s.doc('job'), counsel_doc.for_chat(s)))     # COUNSEL.md as read: its comments left out
        for name, view, phone in [('no page', None, False), ('a task', Q.TASKPAGE, False), ('a connection', Q.IMAP, False),
                                  ('settings', Q.SETTINGSPAGE, False), ('the memory', Q.LEARNEDDOC, False), ('a phone', None, True)]:
            seen = []
            with self.subTest(page=name), ExitStack() as st:
                Q._guards(st); st.enter_context(mock.patch.object(server, 'store', s))
                if phone: st.enter_context(concierge.delivering(concierge.PHONE))
                concierge.say(s, 'what matters most today?', llm=lambda sy, u, **k: (seen.append(sy), 'The month-end close.')[1], view=view)
                sy = seen[0]
                for part in (soul, job, counsel, 'I put vendor renewals off to Friday', f'TASKUARY {__version__}'): self.assertIn(part, sy)
                self.assertIn('STYLE.md (how they write', sy); self.assertIn('AGENT.md (the rules every agent works under)', sy)
                self.assertIn('"your doc style"', sy)


if __name__ == '__main__': unittest.main()

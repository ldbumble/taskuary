"""The assistant relays both ways with the agent on screen (the canvas redesign, 2026-09-29): its context for a turn
about a task holds the agent's state AND what its screen last said, so "what is it doing?" is answered from the
screen - not from a status word."""
import unittest
from unittest import mock

from taskuary import concierge
from test_funnel import store


class RelayContextTests(unittest.TestCase):
    def test_a_turn_about_a_task_carries_the_agents_last_screen_lines(self):
        s = store()
        t = s.create_task({'Title': 'Fix the ledger export', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        live = [{'taskId': t, 'sid': 's1', 'agent': 'claude', 'idle': 3, 'waiting': False}]
        screen = ['> Editing jobs/export_ledger.py', 'Running tests/test_export.py', '12 passed']
        with mock.patch.object(concierge, '_live', return_value=live), \
             mock.patch('taskuary.terminal.asking_lines', return_value=screen) as lines:
            said = concierge.task_now(s, t)
        lines.assert_called_once_with('s1', 8)
        self.assertIn('is WORKING right now', said)
        self.assertIn("THE AGENT'S SCREEN, last lines:\n  > Editing jobs/export_ledger.py\n  Running tests/test_export.py\n  12 passed", said)

    def test_no_session_means_no_screen(self):
        s = store()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        with mock.patch.object(concierge, '_live', return_value=[]):
            self.assertNotIn('SCREEN', concierge.task_now(s, t))


class OpenCardContextTests(unittest.TestCase):
    """A card browsed open in the canvas (a connector, a settings group, a report) is what "this" means in the next turn."""
    def test_the_open_card_rides_the_turn(self):
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'It reads card spend once it is connected.'
        with mock.patch.object(concierge, '_live', return_value=[]):
            out = concierge.say(s, 'what does this one do?', llm=llm, open_card='the Spendly connector card (Connections - Finance), not connected')
        self.assertIn('ON SCREEN NOW: the Spendly connector card (Connections - Finance), not connected', seen['prompt'])
        self.assertTrue(out['say'])

    def test_a_page_with_nothing_opened_is_the_context_too(self):
        """Asked over the Connections wall with no card open, the turn went out with no context at all, and "which AI agent tool
        do I need for this thing to work" was answered about the app in general (the owner, 2026-10-01)."""
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'For the agents section: an AI CLI agent.'
        page = 'the Connections page, AI - agents & models section - nothing opened on it yet'
        with mock.patch.object(concierge, '_live', return_value=[]):
            concierge.say(s, 'which ai agent tool do I need for this thing to work', llm=llm, open_card=page)
        self.assertIn(f"ON SCREEN NOW: {page} - 'this' and 'here' mean what is on screen", seen['prompt'])
        self.assertLess(seen['prompt'].index('ON SCREEN NOW'), seen['prompt'].index('The owner says:'), 'the screen first, then the words')

    def test_no_card_no_line(self):
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'Hello.'
        with mock.patch.object(concierge, '_live', return_value=[]):
            concierge.say(s, 'hi', llm=llm)
        self.assertNotIn('ON SCREEN NOW', seen['prompt'])


class WholeOpenBoxTests(unittest.TestCase):
    """Whatever is open is the turn's context, WHOLE (the owner, 2026-10-01: "if it has task open, entire task is in context, same
    with anything else, 4 fyi's"): a task opened by name or from the rail - often not in the pile at all - its description,
    checklist and notes with the agent's report; a batch of fyis, every message in it."""
    def ask(self, s, key=None, item=None):
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'Noted.'
        with mock.patch.object(concierge, '_live', return_value=[]):
            concierge.say(s, 'what is left on this?', key=key, item=item, llm=llm)
        return seen['prompt']

    def test_a_task_opened_by_name_is_the_subject_whole(self):
        s = store()
        t = s.create_task({'Title': 'Pull the ledger export', 'Kind': 'coding', 'Status': 'open',
                           'Summary': 'Extend the monthly pull to a full year, one workbook per site.'}, 'owner')
        s.set_task_checklist(t, ['Pull 2024', 'Reconcile against the ledger'], 'owner')
        s.add_comment(t, 'owner', 'owner', 'Keep it throwaway; do not push.')
        s.add_comment(t, 'coder', 'agent', 'CODER REPORT\nPulled 2024; 2023 flagged as built from bad data.')
        prompt = self.ask(s, key=f'task:{t}')
        for want in ("THE TASK'S DESCRIPTION: Extend the monthly pull to a full year", 'Pull 2024', 'Reconcile against the ledger',
                     'Keep it throwaway; do not push.', '2023 flagged as built from bad data'):
            self.assertIn(want, prompt)

    def test_a_batch_of_fyis_is_every_message_in_it(self):
        s = store()
        mids = [s.add_message({'ExternalId': f'x:f{n}', 'Channel': 'email', 'Subject': subj, 'FromName': who, 'FromEmail': f'{who.lower()}@northwind.example',
                               'SentAt': '2026-10-01 08:00:00', 'BodyText': body, 'Status': 'filed'})
                for n, (who, subj, body) in enumerate([('Erin', 'Back Tuesday', 'I am out until Tuesday.'),
                                                       ('Gail', 'Office closed Friday', 'The office closes at noon Friday.')])]
        batch = {'key': 'fyis:x', 'kind': 'fyis', 'lane': 'fyi', 'title': '2 fyi', 'who': '', 'when': '', 'why': 'people told you things',
                 'items': [{'mid': m, 'who': w, 'title': t} for m, w, t in zip(mids, ('Erin', 'Gail'), ('Back Tuesday', 'Office closed Friday'))]}
        prompt = self.ask(s, item=batch)
        self.assertIn('FYI 1 of 2: Erin - Back Tuesday', prompt); self.assertIn('I am out until Tuesday.', prompt)
        self.assertIn('FYI 2 of 2: Gail - Office closed Friday', prompt); self.assertIn('closes at noon Friday', prompt)

    def test_the_walks_own_intro_stays_small(self):
        s = store()
        t = s.create_task({'Title': 'Pull the ledger export', 'Kind': 'coding', 'Status': 'open', 'Summary': 'A long description.'}, 'owner')
        item = {'key': f'task:{t}', 'kind': 'task', 'lane': 'asked', 'title': 'Pull the ledger export', 'tid': t}
        with mock.patch.object(concierge, '_live', return_value=[]):
            self.assertNotIn("THE TASK'S DESCRIPTION", concierge.facts(s, item))
            self.assertIn("THE TASK'S DESCRIPTION", concierge.facts(s, item, whole=True))

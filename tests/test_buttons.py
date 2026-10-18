"""THE ONE LIST OF BUTTONS (taskuary/buttons.json): every word the server puts on a button is a label on that list, a removed
button is never drawn, and a sentence names only a button the item it is about actually shows (the owner, 2026-10-17: "if it's
in one code place it's easy to update it later")."""
import json, re, unittest
from pathlib import Path
from unittest import mock

from taskuary import advisor, buttons, concierge, counsel, funnel, proposals, toolcatalog
from taskuary.store import MemoryStore

LABELS = buttons.labels()
TEMPLATES = Path(counsel.__file__).parent / 'templates'
# the wordings the owner dropped - none may come back as a button's name, in a tool's sentence or in COUNSEL
DROPPED = ('Make a task', 'Take it myself', 'Snooze', 'Hand to agent', 'Regular agent', 'A non-coding agent', 'File it',
           'Silence this sender', 'Block them in Settings', 'Send back to the agent', 'Continue the agent', 'Merge & close', 'Close out',
           'Refresh the draft', 'Redraft it', 'Mark it handled', 'Test the connection', 'Run the report again',
           'Send the answer to the agent', 'Prep me', 'Archive it', 'Handled', 'Push it back', 'Skip until tomorrow', 'Draft a follow-up')
def dropped_in(text: str) -> list:
    return [w for w in DROPPED if w in text] + (['Run it'] if re.search(r'\bRun it\b(?! again)', text) else [])

# one item of every kind the walk carries, in the states whose buttons differ
ITEMS = [
    {'kind': 'review', 'key': 'review:1', 'title': 'Invoice question', 'who': 'Erin Blake', 'mid': 1, 'rid': 1, 'tid': 1, 'draft': True},
    {'kind': 'review', 'key': 'review:2', 'title': 'Invoice question', 'who': 'Erin Blake', 'mid': 2, 'rid': 2, 'tid': 2},
    {'kind': 'action', 'key': 'review:3', 'title': 'Merge the fix', 'mid': 3, 'rid': 3, 'tid': 3, 'draft': True,
     'closeout': proposals.CLOSEOUT['merge_pr'], 'why': 'the agent finished'},
    {'kind': 'action', 'key': 'review:4', 'title': 'Run the import', 'mid': 4, 'rid': 4, 'tid': 4, 'draft': True},
    {'kind': 'agent', 'key': 'task:5', 'title': 'Fix the export', 'tid': 5, 'asking': True, 'tail': ['Which branch?'], 'agent': 'The agent'},
    {'kind': 'agent', 'key': 'task:6', 'title': 'Fix the export', 'tid': 6, 'lane': 'stopped', 'tail': [], 'agent': 'The agent'},
    {'kind': 'agent', 'key': 'task:7', 'title': 'Fix the export', 'tid': 7, 'paused': True, 'why': 'its work is saved', 'tail': []},
    {'kind': 'meeting', 'key': 'meeting:1', 'title': 'Budget review', 'why': 'in an hour'},
    {'kind': 'report', 'key': 'report:1', 'title': 'Weekly spend', 'source_id': 1, 'bad': True},
    {'kind': 'report', 'key': 'report:2', 'title': 'Weekly spend', 'source_id': 2},
    {'kind': 'agentdone', 'key': 'task:8', 'title': 'Fix the export', 'tid': 8, 'mid': 8, 'summary': 'fixed it', 'who': 'Gail Moreno'},
    {'kind': 'wrapup', 'key': 'task:9', 'title': 'Fix the export', 'tid': 9},
    {'kind': 'idea', 'key': 'idea:1', 'title': 'Chase Ray about the lease', 'idea': 1, 'why': 'quiet for a week'},
    {'kind': 'task', 'key': 'task:10', 'title': 'Renew the lease', 'tid': 10},
    {'kind': 'asked', 'key': 'msg:11', 'title': 'Can you send the deck?', 'who': 'Paula Vance', 'mid': 11, 'channel': 'email'},
    {'kind': 'asked', 'key': 'task:12', 'title': 'Can you send the deck?', 'who': 'Paula Vance', 'mid': 12, 'tid': 12, 'lane': 'queued',
     'why_idle': 'Waiting for you. First message from this sender.', 'channel': 'email'},
    {'kind': 'todo', 'key': 'task:13', 'title': 'Send Omar the numbers', 'who': 'Omar Keller', 'mid': 13, 'tid': 13, 'why': 'you promised', 'channel': 'email'},
    {'kind': 'fyi', 'key': 'msg:14', 'title': 'Office closed Friday', 'who': 'Marcus Reed', 'mid': 14, 'channel': 'email'},
    {'kind': 'connection', 'key': 'conn:1', 'title': 'Mail stopped answering'},
    {'kind': 'task', 'key': 'task:15', 'title': 'Lease figures from Ray', 'tid': 15, 'lane': 'forgotten'},
]
def chips(item): return concierge.chips_for(None, item)


class Contract(unittest.TestCase):
    def test_the_json_is_the_contract(self):
        j = json.loads((Path(buttons.__file__).with_name('buttons.json')).read_text(encoding='utf-8'))
        self.assertEqual(set(buttons.VERBS), {k for k in j['verbs'] if not k.startswith('_')})
        self.assertEqual(buttons.label('approve'), j['verbs']['approve']['label'])
        self.assertEqual(buttons.label('approve', 'action'), j['verbs']['approve']['states']['action'])
        self.assertEqual(buttons.label('redraft', 'none'), j['verbs']['redraft']['states']['none'])
        self.assertEqual((buttons.canon('later'), buttons.canon('skip'), buttons.canon('archive'), buttons.canon('done'), buttons.canon('prep')),
                         ('defer', 'defer', 'not_ours', 'close', None))
        self.assertEqual(buttons.canon('reply'), 'reply')
        self.assertEqual(buttons.label('later'), buttons.label('defer'))      # an old word reads as the button it became


class EveryLabelIsOnTheList(unittest.TestCase):
    def test_chips(self):
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            for it in ITEMS:
                for c in chips(it): self.assertIn(c['label'], LABELS, (it['kind'], c))
                for c in chips(it): self.assertEqual(c['label'], buttons.label(c['verb'], 'action' if c['label'] == 'Approve' else
                                                                               'none' if c['verb'] == 'redraft' and not it.get('draft') else None), c)

    def test_state_labels_where_the_state_holds(self):
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            act = next(c for c in chips(ITEMS[2]) if c['verb'] == 'approve')
            self.assertEqual(act['label'], buttons.label('approve', 'action'))
            self.assertEqual(next(c for c in chips(ITEMS[3]) if c['verb'] == 'approve')['label'], buttons.label('approve', 'action'))
            self.assertEqual(next(c for c in chips(ITEMS[1]) if c['verb'] == 'redraft')['label'], buttons.label('redraft', 'none'))
            self.assertEqual(next(c for c in chips(ITEMS[0]) if c['verb'] == 'redraft')['label'], buttons.label('redraft'))
        self.assertEqual(concierge.closeout_label(ITEMS[2]), buttons.label('approve', 'action'))
        self.assertEqual(proposals.CLOSE_WORD, buttons.label('approve', 'action'))

    def test_proposals_and_the_cards_question(self):
        for v, (_kind, lbl, _s) in concierge.PROPOSALS.items():
            if v in buttons.VERBS: self.assertEqual(lbl, buttons.label(v), v)
        for group, pairs in list(concierge.ALTS.items()) + [('idea', concierge.IDEA_ALTS)]:
            self.assertEqual(tuple(pairs), buttons.choices(group))
            for v, _ in pairs: self.assertIn(v, buttons.VERBS)

    def test_op_labels_that_name_a_button(self):
        ops = [('task.create_from_message', {'kind': k}) for k in ('coding', 'general', 'task')] + \
              [('task.create_from_text', {'kind': k}) for k in ('coding', 'general', 'task')] + \
              [('idea.act', {'verb': v}) for v in ('task', 'agent', 'dismiss', 'dismiss_kind')] + \
              [('preference.exclude_sender', {'scope': 'sender'}), ('item.settle', {'tid': 1}), ('item.settle', {}),
               ('agent.continue', {}), ('report.rerun', {}), ('connection.test', {}), ('task.reopen', {}), ('task.split', {}),
               ('dispatch.prepare', {'kind': 'general'}), ('dispatch.prepare', {'kind': 'coding'}), ('task.complete', {}),
               ('review.approve', {}), ('agent.stop', {}), ('agent.answer', {}), ('message.file', {})]
        for kind, p in ops: self.assertIn(concierge.op_label(kind, p), LABELS, (kind, p))
        self.assertTrue(concierge.op_label('task.defer', {'until': 'monday'}).startswith(buttons.label('defer')))

    def test_advice(self):
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            for it in ITEMS:
                for v in advisor.offered(None, it): self.assertIn(v['label'], LABELS, (it['kind'], v))
        row = {'Key': 'task:1', 'Line': 'Take it on.', 'Verb': 'mine', 'Label': 'Take it myself', 'CountJson': '[0,0]', 'EvidenceJson': '[]',
               'Revision': 'r', 'Tier': 1, 'CreatedAt': ''}
        self.assertEqual(advisor._payload(row)['label'], buttons.label('mine'))           # judged under an old wording, shown as today's
        self.assertEqual(advisor._payload({**row, 'Verb': 'approve', 'Label': 'Approve'})['label'], 'Approve')   # a state's name is kept
        gone = advisor._payload({**row, 'Verb': 'prep', 'Label': 'Prep me'})
        self.assertFalse(gone['line'])                                                      # its button is gone: no line points at it

    def test_the_prompt_names_buttons_by_label(self):
        self.assertFalse(dropped_in(advisor.SYSTEM))
        for v in ('reply', 'answer_agent', 'close', 'let_go', 'continue'): self.assertIn(buttons.label(v), advisor.SYSTEM)


class NoRemovedButton(unittest.TestCase):
    def test_nowhere(self):
        for v in buttons.REMOVED:
            self.assertFalse(any(v in vs for vs in concierge.CHIPS.values()), v)
            for table in (concierge.PROPOSALS, concierge.CHIP_WORDS, toolcatalog.DECISIONS, concierge.RECEIPTS):
                self.assertNotIn(v, table, v)
            self.assertNotIn(v, concierge.VERBS)
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            for it in ITEMS:
                self.assertFalse({c['verb'] for c in chips(it)} & set(buttons.REMOVED), it['kind'])
                self.assertFalse({v['verb'] for v in advisor.offered(None, it)} & set(buttons.REMOVED), it['kind'])
                # an old word typed promotes the button it became - never itself
                self.assertFalse({c['verb'] for c in concierge.chips_for(None, it, first='later')} & set(buttons.REMOVED))
            self.assertEqual(concierge.chips_for(None, ITEMS[13], first='later')[0]['verb'], 'defer')

    def test_a_typed_removed_word_lands_on_its_button(self):
        self.assertEqual(concierge.canon_verb('done'), 'close')
        self.assertEqual(concierge.canon_verb('coder'), 'coding_agent')
        _, d = concierge.parse_decision('Done.\nCALL: {"kind": "done", "params": {}}')
        self.assertEqual(d['verb'], 'close')


class PhantomGuard(unittest.TestCase):
    """A sentence about an item names only buttons that item shows. Next is left out of the scan: the walk always carries it."""
    def names(self, text, it=None):
        """The buttons a line names. A label inside a longer one ("Send" in "Send to agent") is the longer one, and the item's own
        title ("Send Omar the numbers") names no button - both read as Send once approve's label became that word (2026-10-18)."""
        for own in ((it or {}).get('title'), (it or {}).get('ref')): text = text.replace(own, ' ') if own else text
        found = set()
        for l in sorted(LABELS - {buttons.label('next')}, key=len, reverse=True):
            pat = rf'(?<![\w]){re.escape(l)}(?![\w])'
            if re.search(pat, text): found.add(l); text = re.sub(pat, ' ', text)
        return found

    def test_every_fallback_line(self):
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            for it in ITEMS:
                shown = {c['label'] for c in chips(it)}
                for opening in (True, False):
                    line = concierge.fallback(dict(it), opening)
                    self.assertLessEqual(self.names(line, it), shown, (it['kind'], it.get('lane'), line))
                self.assertLessEqual(self.names(concierge._from_you(None, it), it), shown)

    def test_the_cannot_lines(self):
        with mock.patch.object(concierge, '_agent_running', return_value=True):
            for it in ITEMS:
                shown = {c['label'] for c in chips(it)}
                for v in ('not_ours_kind', 'approve', 'regular_agent', 'coding_agent'):
                    why = concierge.cannot(it, v)
                    self.assertLessEqual(self.names(why, it) - {buttons.label('regular_agent')}, shown, (it['kind'], v, why))

    def test_lane_hints_name_no_button_they_do_not_carry(self):
        for row in funnel._VOCAB['lanes'] + funnel._VOCAB['kinds'] + funnel._VOCAB['states']:
            allowed = {'unjudged': {buttons.label('retriage')}}.get(row['key'], set())    # the task page's own Sort it again
            self.assertLessEqual(self.names(row.get('hint') or ''), allowed, row['key'])

    def test_the_why_not_started_sentences_name_no_button(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Assignee': 'agent:coding'}, 'owner')
        st = funnel.idle_state(s, tid if isinstance(tid, int) else tid['TaskId'])
        self.assertFalse(self.names(st['line']), st['line'])


class TheAssistantIsToldTodaysButtons(unittest.TestCase):
    def test_the_block_names_exactly_the_buttons_it_offers(self):
        b = toolcatalog.block()
        line = b.split('THE BUTTONS BY NAME')[1].split('\n')[1]
        said = set(re.findall(r'"([^"]+)"', line))
        vs = [v for v in list(toolcatalog.DECISIONS) + list(toolcatalog.CHIP_TOOL) if v in buttons.VERBS]
        want = {buttons.label(v) for v in vs} | {w for v in vs for w in (buttons.VERBS[v].get('states') or {}).values()}
        self.assertEqual(said, want)
        self.assertFalse(dropped_in(b))

    def test_each_decision_quotes_only_its_own_button(self):
        for v, text in toolcatalog.DECISIONS.items():
            quoted = set(re.findall(r'"([^"]+)"', text)) & LABELS
            own = {buttons.label(v)} | set((buttons.VERBS.get(v, {}).get('states') or {}).values()) if v in buttons.VERBS else set()
            self.assertLessEqual(quoted, own, v)
            self.assertFalse(dropped_in(text), v)
        for v, text in toolcatalog.PURPOSE.items(): self.assertFalse(dropped_in(text), v)

    def test_no_coding_tool_no_coding_button(self):
        with mock.patch('taskuary.agents.coding_ready', return_value=False):
            self.assertNotIn(buttons.label('coding_agent'), toolcatalog.block(MemoryStore()))
        with mock.patch('taskuary.agents.coding_ready', return_value=True):
            self.assertIn(buttons.label('coding_agent'), toolcatalog.block(MemoryStore()))

    def test_the_contracts_name_no_dropped_word(self):
        for text in (concierge.CONTRACT, concierge.PHONE_CONTRACT, counsel.NO_CODING): self.assertFalse(dropped_in(text))


class Counsel(unittest.TestCase):
    def test_counsel_names_buttons_only_by_their_labels(self):
        text = (TEMPLATES / 'counsel.md').read_text(encoding='utf-8')
        self.assertFalse(dropped_in(text))
        self.assertNotIn('the Sync button', text)
        opts = re.search(r'OPTIONS: (.+?)\.\s*$', text, re.M).group(1).split(' | ')
        self.assertEqual(opts, [w for _, w in buttons.choices('agent')])

    def test_counsel_stays_under_its_budget(self):
        self.assertLessEqual(len((TEMPLATES / 'counsel.md').read_text(encoding='utf-8')), counsel.BUDGET)

    def test_an_install_on_the_previous_stock_text_moves_to_the_new_one(self):
        st = MemoryStore()
        st.save_doc('counsel', (TEMPLATES / 'history' / 'counsel-0.3.9.3-audit.md').read_text(encoding='utf-8'), 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertEqual(counsel._squash(st.get_doc('counsel')), counsel._squash((TEMPLATES / 'counsel.md').read_text(encoding='utf-8')))
        self.assertEqual(counsel.migrate(st), 'unchanged')


if __name__ == '__main__': unittest.main()

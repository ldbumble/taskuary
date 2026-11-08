"""A VIEW THE AGENT SHOWS IN ITS CHAT (agenttools `show`, viewspec.py): a spec outside the catalog is refused with words the model can act on,
one inside it comes back normalised after its mark for the chat to draw, and the tool reaches nothing past the chat - not even the owner's
history, so it works on a stranger's task too. Invented people and numbers.
"""
import json, unittest
from unittest import mock
from taskuary import agenttools, server, viewspec
from taskuary.store import MemoryStore
from tests.test_agent_toolbox import tool

SPEC = {'title': 'Northwind renewals', 'root': 'top', 'elements': {
    'top': {'type': 'text', 'props': {'text': 'Three renewals are due.'}, 'children': ['kpis', 't', 'c', 'todo', 'go', 'page']},
    'kpis': {'type': 'stats', 'props': {'items': [{'label': 'Due', 'value': 3}, {'label': 'Total', 'value': '$18,420', 'note': 'this quarter'}]}},
    't': {'type': 'table', 'props': {'columns': ['vendor', 'amount'], 'rows': [['Payworth', 9310], {'vendor': 'Trainly', 'amount': 5100}, ['Spendly']]}},
    'c': {'type': 'chart', 'props': {'kind': 'line', 'points': [{'label': 'Oct', 'value': 4}, {'label': 'Nov', 'value': 7.5}]}},
    'todo': {'type': 'checklist', 'props': {'items': [{'text': 'Ask Erin Blake for the quote', 'done': True}, 'Book the call']}},
    'go': {'type': 'button', 'props': {'label': 'Mark it done', 'verb': 'done'}},
    'page': {'type': 'button', 'props': {'label': 'Open settings', 'open': '#settings'}},
    'stray': {'type': 'list', 'props': {'items': ['never drawn']}}}}


def one(type_, props, **more): return {'root': 'a', 'elements': {'a': {'type': type_, 'props': props, **more}}}


class TheCheck(unittest.TestCase):
    def test_a_good_spec_comes_back_normalised_and_only_what_the_root_reaches(self):
        v = viewspec.check(SPEC)
        self.assertEqual(v['title'], 'Northwind renewals')
        self.assertEqual(v['elements']['t']['props']['rows'], [['Payworth', 9310], ['Trainly', 5100], ['Spendly', None]])
        self.assertEqual(v['elements']['todo']['props']['items'][1], {'text': 'Book the call', 'done': False})
        self.assertEqual(v['elements']['go']['props']['verb'], 'close')          # its row id names the verb
        self.assertNotIn('stray', v['elements'])

    def test_what_is_outside_the_catalog_is_refused_saying_what_to_fix(self):
        bad = lambda spec, says: self.assertRaisesRegex(ValueError, says, viewspec.check, spec)
        bad('a view', 'must be an object')
        bad(one('iframe', {'src': 'https://vendor.example'}), r"type 'iframe' is not one of table, stats")
        bad(one('text', {'text': 'hi', 'color': 'red'}), 'props has color - a text takes text')
        bad(one('text', {}), 'props needs text')
        bad(one('chart', {'kind': 'pie', 'points': [{'label': 'x', 'value': 1}]}), 'must be one of bar, line')
        bad(one('chart', {'points': [{'label': 'x', 'value': '1'}]}), r'points\[0\]\.value must be a number')
        bad(one('table', {'columns': ['a'], 'rows': [[1, 2]]}), 'at most 1 cells')
        bad(one('table', {'columns': ['a'], 'rows': [{'b': 1}]}), 'not among the columns')
        bad(one('button', {'label': 'Pay', 'verb': 'pay_now'}), r"'pay_now' is no button on the task page - one of .*close")
        bad(one('button', {'label': 'Go'}), 'one of verb')
        bad(one('button', {'label': 'Go', 'open': 'https://vendor.example'}), 'app page link')
        bad(one('button', {'label': 'Go', 'open': '#setup'}), 'app page link')
        bad(one('text', {'text': 'x'}, children=['a']), 'contains itself')
        bad(one('text', {'text': 'x'}, children=['b']), "names 'b', which is not an element")
        bad({'root': 'z', 'elements': {'a': {'type': 'text', 'props': {'text': 'x'}}}}, "root 'z' is not one of the elements")

    def test_the_caps_hold(self):
        c = viewspec.CAPS
        self.assertRaisesRegex(ValueError, 'at most 50', viewspec.check, one('list', {'items': ['x'] * (c['items'] + 1)}))
        self.assertRaisesRegex(ValueError, 'keep it to 2000', viewspec.check, one('text', {'text': 'x' * (c['long'] + 1)}))
        many = {'root': 'e0', 'elements': {f'e{i}': {'type': 'text', 'props': {'text': 'x'}} for i in range(c['elements'] + 1)}}
        self.assertRaisesRegex(ValueError, 'at most 40', viewspec.check, many)
        rows = [[f'Vendor {i}', 'a long enough cell to fill the view ' * 3] for i in range(c['items'])]
        self.assertRaisesRegex(ValueError, 'characters - keep it to 5,000', viewspec.check, one('table', {'columns': ['v', 'note'], 'rows': rows}))

    def test_the_answer_carries_the_checked_spec_after_its_mark_on_one_line(self):
        out = viewspec.shown(SPEC)
        head, spec = out.split(viewspec.MARK)
        self.assertIn("Shown in the owner's chat", head)
        self.assertNotIn('\n', out)                   # a CLI's trace joins a result's lines: one line keeps the JSON whole
        self.assertEqual(json.loads(spec), viewspec.check(SPEC))


class TheTool(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.p = mock.patch.object(server, 'store', self.s); self.p.start()
        self.tid = self.s.create_task({'Title': 'Renewals for Alex', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')

    def tearDown(self): self.p.stop()

    def test_it_is_listed_as_a_read_and_says_it_is_optional(self):
        cls, desc, schema, _ = agenttools.TOOLS['show']
        self.assertEqual(cls, 'read')
        self.assertIn('plain text is fine otherwise', desc); self.assertIn('never sends, pays or closes', desc)
        self.assertEqual(schema['required'], ['root', 'elements'])

    def test_a_call_answers_with_the_view_and_a_bad_one_with_what_to_fix(self):
        text, err = tool(self.tid, 'show', **SPEC)
        self.assertFalse(err)
        self.assertEqual(json.loads(text.split(viewspec.MARK)[1])['elements']['c']['props']['kind'], 'line')
        text, err = tool(self.tid, 'show', **one('marquee', {}))
        self.assertTrue(err); self.assertIn("type 'marquee' is not one of", text)

    def test_it_reads_nothing_of_the_owners_so_a_strangers_task_may_show_one(self):
        theirs = self.s.create_task({'Title': 'Look at this', 'Status': 'open', 'OriginBase': 'stranger'}, 'triage')
        text, err = tool(theirs, 'show', **one('text', {'text': 'What the sender asked, in three lines.'}))
        self.assertFalse(err, text)
        _, err = tool(theirs, 'search_messages', words='renewal')
        self.assertTrue(err)


if __name__ == '__main__': unittest.main()

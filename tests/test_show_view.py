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


class TheNewBlocks(unittest.TestCase):
    "grid, badge and note; a title and a description on every block; a tile's trend and format, a column's format, a highlighted point"
    NEW = {'root': 'g', 'elements': {
        'g': {'type': 'grid', 'props': {'cols': 2, 'title': 'Plans', 'description': 'For 40 people'}, 'children': ['k', 'c', 't', 'b', 'n']},
        'k': {'type': 'stats', 'props': {'items': [{'label': 'Top tier', 'value': 540, 'format': 'currency', 'trend': {'dir': 'up', 'text': '+$340 vs Basic'}}]}},
        'c': {'type': 'chart', 'props': {'kind': 'bar', 'format': 'currency', 'description': 'Per month',
                                         'points': [{'label': 'Payworth Basic', 'value': 200, 'highlight': True}, {'label': 'Payworth Pro', 'value': 540}]}},
        't': {'type': 'table', 'props': {'title': 'Costs', 'columns': ['Plan', {'label': 'Per month', 'format': 'currency'}],
                                         'rows': [{'Plan': 'Payworth Basic', 'Per month': 200}, ['Payworth Pro', 540]]}},
        'b': {'type': 'badge', 'props': {'text': 'Cheapest', 'variant': 'success'}},
        'n': {'type': 'note', 'props': {'tone': 'warning', 'title': 'Before you switch', 'text': 'Two reports are still open.'}}}}

    def test_they_pass_and_come_back_as_they_went_in(self):
        v = viewspec.check(self.NEW)
        self.assertEqual(v['elements']['g']['props'], {'cols': 2, 'title': 'Plans', 'description': 'For 40 people'})
        self.assertEqual(v['elements']['k']['props']['items'][0]['trend'], {'dir': 'up', 'text': '+$340 vs Basic'})
        self.assertEqual(v['elements']['c']['props']['points'][0], {'label': 'Payworth Basic', 'value': 200, 'highlight': True})
        self.assertNotIn('highlight', v['elements']['c']['props']['points'][1])
        self.assertEqual(v['elements']['t']['props']['columns'][1], {'label': 'Per month', 'format': 'currency'})
        self.assertEqual(v['elements']['t']['props']['rows'], [['Payworth Basic', 200], ['Payworth Pro', 540]])     # a row by its column labels
        self.assertEqual(viewspec.check(v), v)                       # the page checks the server's answer again: it must still pass
        self.assertEqual(viewspec.check(one('grid', {'cols': '3'}))['elements']['a']['props']['cols'], 3)

    def test_an_old_spec_is_still_good(self):
        self.assertEqual(viewspec.check(SPEC)['elements']['t']['props']['columns'], ['vendor', 'amount'])

    def test_what_is_wrong_with_them_is_said(self):
        bad = lambda spec, says: self.assertRaisesRegex(ValueError, says, viewspec.check, spec)
        bad(one('grid', {'cols': 5}), 'cols must be one of 1, 2, 3, 4')
        bad(one('grid', {'cols': True}), 'cols must be one of')
        bad(one('badge', {'text': 'x', 'variant': 'danger'}), 'variant must be one of default, secondary')
        bad(one('badge', {}), 'props needs text')
        bad(one('note', {'tone': 'error', 'text': 'x'}), 'tone must be one of info, success, warning')
        bad(one('note', {'text': 'x' * (viewspec.CAPS['long'] + 1)}), 'keep it to 2000')
        bad(one('text', {'text': 'x', 'title': 'y' * (viewspec.CAPS['short'] + 1)}), r'title is 201 characters')
        bad(one('stats', {'items': [{'label': 'a', 'value': 1, 'trend': {'dir': 'sideways'}}]}), r'trend\.dir must be one of up, down, neutral')
        bad(one('stats', {'items': [{'label': 'a', 'value': 1, 'trend': {'text': '+1'}}]}), 'trend needs dir')
        bad(one('stats', {'items': [{'label': 'a', 'value': 1, 'format': 'euro'}]}), 'format must be one of currency, number, percent')
        bad(one('table', {'columns': [{'label': 'a', 'format': 'money'}], 'rows': [[1]]}), r'columns\[0\]\.format must be one of')
        bad(one('table', {'columns': [{'name': 'a'}], 'rows': [[1]]}), r'columns\[0\] has name')
        bad(one('chart', {'points': [{'label': 'x', 'value': 1, 'color': 'red'}]}), 'has color')


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


def test_the_tool_says_not_to_repeat_the_view_in_words():
    from taskuary import agenttools
    assert 'never the same table or list again in text' in agenttools.TOOLS['show'][1]


def test_the_tools_one_example_is_a_good_spec_with_a_grid_tiles_a_chart_a_table_and_a_checklist():
    # ...read through the guide tool now (guides.py, 2026-11-09): the tool's description names it, and stays short
    assert '`show` topic' in agenttools.TOOLS['show'][1] and agenttools.SHOW_EXAMPLE in agenttools.call(None, 1, 'guide', {'topic': 'show'}, {})
    v = viewspec.check(json.loads(agenttools.SHOW_EXAMPLE))
    assert sorted({e['type'] for e in v['elements'].values()}) == ['chart', 'checklist', 'grid', 'stats', 'table']
    assert len(v['elements']['kpi']['props']['items']) == 3

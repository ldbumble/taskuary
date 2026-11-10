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


PNG = bytes([0x89]) + b'PNG' + bytes([13, 10, 26, 10])


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

    def test_it_is_listed_as_a_read_and_invites_use(self):     # 2026-11-09: once in 50 scenarios, with "never required" in it
        cls, desc, schema, _ = agenttools.TOOLS['show']
        self.assertEqual(cls, 'read')
        self.assertIn('Use it freely', desc); self.assertIn('never sends, pays or closes', desc)
        self.assertEqual(schema['required'], [])            # a view, or `files`, or both (2026-11-09)
        self.assertIn('files', schema['properties'])

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


    # A PICTURE THE AGENT MADE IS SHOWN IN ITS CHAT, never "opened in your image viewer" on a computer nobody watches (2026-11-09)
    def test_files_are_copied_onto_the_task_and_the_answer_carries_their_rows(self):
        import tempfile
        from pathlib import Path
        from taskuary import config, session_artifacts
        d = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))           # a CLI's own scratchpad lives in the system's temp folder
        (d / 'dark.png').write_bytes(PNG + b'fake'); (d / 'run.exe').write_bytes(b'MZ')
        text, err = tool(self.tid, 'show', files=[str(d / 'dark.png'), str(d / 'run.exe'), str(d / 'gone.png')])
        self.assertFalse(err, text)
        head, rows = text.split(agenttools.FILES_MARK)
        self.assertIn("Shown in the owner's chat under your answer: dark.png", head)
        self.assertIn('run.exe: .exe cannot be shown', head); self.assertIn('gone.png: there is no such file', head)
        (row,) = json.loads(rows)
        self.assertEqual((row['name'], row['content_type'], row['kind']), ('dark.png', 'image/png', 'shown'))
        self.assertEqual(row['url'], f"/api/task-artifacts/{row['id']}")
        art = self.s.get_task_artifact(row['id'])
        self.assertEqual((art['TaskId'], art['Kind']), (self.tid, 'shown'))
        kept = session_artifacts.confined(art['Path'])
        self.assertTrue(kept and kept.read_bytes().startswith(PNG))     # its own copy, kept after the scratch folder is cleared
        # ...and with a view in the same call, the view's mark is last, so the chat reads its spec whole (viewSpec.specIn)
        text, err = tool(self.tid, 'show', files=[str(d / 'dark.png')], **one('text', {'text': 'Two palettes.'}))
        self.assertFalse(err, text)
        self.assertLess(text.index(agenttools.FILES_MARK), text.index(viewspec.MARK))
        self.assertEqual(json.loads(text.split(viewspec.MARK)[1])['elements']['a']['type'], 'text')
        # ...and the general chat's payload places the copy under an answer, as a file it chose to show
        self.assertTrue(any(p['kind'] == 'shown' and p['name'] == 'dark.png' for p in server._assistant_payload(self.tid)['published']))

    # A DRAWN VIEW IS KEPT WITH THE TASK (2026-11-10): the CLI's log was its only copy - cleaned up, the table was gone from the chat
    def test_a_view_shown_in_a_turn_is_drawn_from_the_task_once_its_session_log_is_gone_and_never_twice(self):
        import tempfile
        from pathlib import Path
        from fastapi.testclient import TestClient
        from taskuary import sessionrecord
        text, err = tool(self.tid, 'show', **SPEC)
        self.assertFalse(err, text)
        (art,) = [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'view']
        self.assertEqual(art['ContentType'], 'application/json')
        self.s.add_transcript(self.tid, 'pty-1', 'the pane, as it ended', agent='coding', ext_id='a-log-cleaned-up', brain='claude')
        drawn = lambda ss: [x for s in ss for x in s.get('steps') or [] if viewspec.MARK in str(x.get('output') or '')]
        with mock.patch.object(sessionrecord, '_home', lambda: Path(tempfile.mkdtemp())):     # no CLI log anywhere
            chat = TestClient(server.app).get(f'/api/tasks/{self.tid}/coding-chat').json()['data']['sessions']
            rec = sessionrecord.record(self.s, self.tid)['sessions']
            for ss in (chat, rec):
                (step,) = drawn(ss)
                self.assertEqual((step['k'], step['name']), ('tool', 'show'))
                self.assertEqual(json.loads(step['output'].split(viewspec.MARK)[1])['title'], 'Northwind renewals')
            # ...and while the session's own record still carries it, that copy is the one drawn
            sessionrecord._saved_path(self.tid, 'pty-1').write_text(json.dumps({'steps': [
                {'k': 'tool', 'name': 'mcp__taskuary__show', 'text': '', 'output': text}, {'k': 'said', 'text': 'Three are due.'}]}), encoding='utf-8')
            chat = TestClient(server.app).get(f'/api/tasks/{self.tid}/coding-chat').json()['data']['sessions']
            self.assertEqual([x['name'] for x in drawn(chat)], ['mcp__taskuary__show'])
            self.assertEqual([x['name'] for x in drawn(sessionrecord.record(self.s, self.tid)['sessions'])], ['mcp__taskuary__show'])

    def test_a_file_outside_the_agents_folders_is_never_read(self):
        from pathlib import Path
        from taskuary import config
        secret = config.home().parent / 'outside-scratch.png'
        secret.write_bytes(PNG + b'not yours')
        with mock.patch.object(agenttools, '_show_roots', lambda: [(config.home() / 'scratch').resolve()]):
            text, err = tool(self.tid, 'show', files=[str(secret)])
        self.assertTrue(err); self.assertIn("only a file in your task's outputs folder", text)
        self.assertFalse([a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'shown'])
        text, err = tool(self.tid, 'show')
        self.assertTrue(err); self.assertIn('give `files`', text)


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


def test_every_worker_is_told_to_show_files_through_the_tool_and_never_claim_an_unchecked_effect():
    # 2026-11-09: a coding agent "opened" screenshots in an image viewer nobody could see and said they were on the owner's screen
    from taskuary import brief, selfclose, terminal
    rules = terminal.with_fence_rule(brief.rules(MemoryStore(), 'agent', terminal.AGENT_CHARS))      # the coding road's cut, the template's copy
    for said in ('call the `show` tool with its path in `files`', 'Never open a viewer, a browser or an app on the computer',
                 'unless the show tool returned it', 'Never claim an effect you did not verify - opened, sent, pushed, deployed, on screen'):
        assert said in rules, said
    old = terminal.with_fence_rule('Honest reporting: say what you did.')        # an owner's AGENT.md from before it hears both too
    assert agenttools.SHOW_RULE in old and agenttools.VERIFY_RULE in old
    assert rules.count('unless the show tool returned it') == 1                  # ...and the template's own copy is not said twice
    assert 'never say it is on the owner\'s screen' in selfclose.SHOW_LINE and '`show` tool\'s `files`' in selfclose.SHOW_LINE
    desc = agenttools.TOOLS['show'][1]
    assert '`files`' in desc and 'never open a viewer' in desc and 'unless this tool said it was shown' in desc

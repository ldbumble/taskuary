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
        bad(one('chart', {'kind': 'radar', 'points': [{'label': 'x', 'value': 1}]}), 'must be one of bar, line, area, pie')
        bad(one('chart', {'points': [{'label': 'x', 'value': '1'}]}), r'points\[0\]\.value must be a number')
        bad(one('table', {'columns': ['a'], 'rows': [[1, 2]]}), 'at most 1 cells')
        bad(one('table', {'columns': ['a'], 'rows': [{'b': 1}]}), 'not among the columns')
        bad(one('button', {'label': 'Pay', 'verb': 'pay_now'}), r"'pay_now' is no button on the task page - one of .*close")
        bad(one('button', {'label': 'Go'}), r'one of props.verb')
        bad(one('button', {'label': 'Go', 'open': 'https://vendor.example'}), 'app page link')
        bad(one('button', {'label': 'Go', 'open': '#setup'}), 'app page link')
        bad(one('text', {'text': 'x'}, children=['a']), 'contains itself')
        bad(one('text', {'text': 'x'}, children=['b']), "names 'b', which is not an element")
        bad({'root': 'z', 'elements': {'a': {'type': 'text', 'props': {'text': 'x'}}}}, "root 'z' is not one of the elements")

    def test_a_view_with_no_root_stands_on_its_one_top(self):
        "Walk 2, 2026-11-21: Claude left `root` out of one chart and was refused twice; with one top element there is nothing to ask."
        v = viewspec.check({'elements': {'c': {'type': 'chart', 'props': {'kind': 'bar', 'points': [{'label': 'Q1', 'value': 14}]}}}})
        self.assertEqual(v['root'], 'c')
        # ...and several tops stand in one column, in the order given (round 3, 2026-11-22: a title and a chart were refused again)
        v = viewspec.check({'elements': {'a': {'type': 'text', 'props': {'text': 'x'}}, 'b': {'type': 'text', 'props': {'text': 'y'}}}})
        self.assertEqual((v['elements'][v['root']]['type'], v['elements'][v['root']]['children']), ('grid', ['a', 'b']))

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


class WhoCanMakeWhichTimes(unittest.TestCase):
    "availability: the agent gives who and their ranges - the counts and the best slot are the page's (availability.js); a view's id names it"
    TEAM = [{'name': 'Erin Blake', 'ranges': [{'day': '2026-12-01', 'from': '14:00', 'to': '16:00'}]},
            {'name': 'Ray Colton', 'ranges': [{'day': '2026-12-02', 'from': '10:00', 'to': '12:00'}, {'day': '2026-12-01', 'from': ' 15:00', 'to': '16:00'}]},
            {'name': 'Paula Vance', 'ranges': []}, {'name': 'Omar Keller'}]

    def test_it_passes_as_given_no_reply_and_none_kept_apart(self):
        v = viewspec.check({**one('availability', {'title': 'Product ideas session', 'minutes': 60, 'people': self.TEAM}), 'id': 'times'})
        ps = v['elements']['a']['props']['people']
        self.assertEqual(ps[0], self.TEAM[0])
        self.assertEqual(ps[1]['ranges'][1], {'day': '2026-12-01', 'from': '15:00', 'to': '16:00'})
        self.assertEqual((ps[2], ps[3]), ({'name': 'Paula Vance', 'ranges': []}, {'name': 'Omar Keller'}))      # none of the times; no reply yet
        self.assertEqual(v['id'], 'times')
        self.assertIn('"id":"times"', viewspec.shown({**one('availability', {'people': self.TEAM}), 'id': 'times'}))     # ...and it rides the answer

    def test_what_it_cannot_draw_is_refused_saying_what_to_fix(self):
        bad = lambda people, says, **more: self.assertRaisesRegex(ValueError, says, viewspec.check, one('availability', {'people': people, **more}))
        at = lambda **r: [{'name': 'Erin Blake', 'ranges': [{'day': '2026-12-01', 'from': '14:00', 'to': '16:00', **r}]}]
        bad([], 'needs people')
        bad(at(to='13:00'), r'ranges\[0\]\.from must be before its to')
        bad(at(**{'from': '2pm'}), r'ranges\[0\]\.from must be a time on a 24-hour clock, like 09:30 or 14:00')
        bad(at(count=4), r'has count - it takes day, from, to')                    # a count is never the agent's to give
        bad([{'name': 'Erin Blake', 'fits': True}], 'has fits - it takes name, ranges')
        bad([{'name': 'Erin Blake'}, {'name': 'Erin Blake'}], 'listed twice')
        bad([{'name': 'Erin Blake', 'ranges': 'Tuesday afternoon'}], 'must be a list of')
        bad([{'name': f'Person {i}'} for i in range(13)], 'at most 12')
        bad([{'name': 'Erin Blake', 'ranges': [{'day': f'2026-12-0{d}', 'from': '09:00', 'to': '10:00'} for d in range(1, 9)]}], 'spans 8 days - at most 7')
        bad(self.TEAM, 'minutes .* must be 15 to 480', minutes=5)
        bad(self.TEAM, 'props has best - a availability takes people, minutes', best='Tue 3pm')        # the best slot is worked out, never taken
        self.assertRaisesRegex(ValueError, 'id must be a short name', viewspec.check, {**one('availability', {'people': self.TEAM}), 'id': 'the times!'})

    def test_a_view_he_can_answer_keeps_an_id_of_its_own(self):
        "The same choice shown twice is two questions: the agent's name for a view never stands in for the id his answer is kept under."
        ask = {**one('choice', {'label': 'Which day?', 'options': ['Tue', 'Wed']}), 'id': 'times'}
        a, b = (json.loads(viewspec.shown(ask).split(viewspec.MARK)[1])['id'] for _ in range(2))
        self.assertNotEqual(a, b); self.assertNotIn('times', (a, b))

    def test_the_tool_takes_it_and_its_guide_says_what_it_draws(self):
        from taskuary import guides
        schema = agenttools.TOOLS['show'][2]['properties']
        self.assertIn('availability', schema['elements']['additionalProperties']['properties']['type']['enum'])
        self.assertEqual(schema['elements']['additionalProperties']['properties']['props']['properties']['people']['items']['required'], ['name'])
        self.assertIn('id', schema)
        viewspec.check(json.loads(guides.AVAILABILITY))            # the guide's own example is a spec that passes
        self.assertIn('availability {people', guides.SHOW_TYPES)

    def test_the_line_every_road_lists_says_a_view_is_shown_again_under_its_id(self):
        """Walk 26, 2026-11-27: replies to "when can everyone meet?" came one by one and no agent on any road drew the view - the one line a
        session holds before it looks anything up named charts and tiles, and nothing of a view kept as one under its `id` (the lean list
        drops a parameter's words, so `id` was a bare string). The line says it, on the list a CLI and a card's harness are each given."""
        for line in (next(t['description'] for t in agenttools.listing(portable=p) if t['name'] == 'show') for p in (False, True)):
            self.assertIn('`id`', line); self.assertIn('who is free when', line)


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
        self.assertIn('never sends, pays or closes', desc)
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
        text, err = tool(theirs, 'show', **one('list', {'items': ['What the sender asked', 'By when', 'For whom']}))
        self.assertFalse(err, text)
        _, err = tool(theirs, 'search_messages', words='renewal')
        self.assertTrue(err)


    # A PICTURE THE AGENT MADE IS SHOWN IN ITS CHAT, never "opened in your image viewer" on a computer nobody watches (2026-11-09)
    def test_files_are_copied_onto_the_task_and_the_answer_carries_their_rows(self):
        import tempfile
        from pathlib import Path
        from taskuary import config, session_artifacts
        d = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))           # a CLI's own scratchpad lives in the system's temp folder
        (d / 'dark.png').write_bytes(PNG + b'fake'); (d / 'run.exe').write_bytes(b'MZ' + bytes([0x90, 0, 3, 0, 0, 0, 0xff, 0xff]))
        text, err = tool(self.tid, 'show', files=[str(d / 'dark.png'), str(d / 'run.exe'), str(d / 'gone.png')])
        self.assertFalse(err, text)
        head, rows = text.split(agenttools.FILES_MARK)
        self.assertIn("Shown in the owner's chat at this step: dark.png", head); self.assertNotIn('under your answer', head)   # ...it is drawn where the step is
        self.assertIn('run.exe: .exe cannot be shown', head); self.assertIn('gone.png: there is no such file', head)
        (row,) = json.loads(rows)
        self.assertEqual((row['name'], row['content_type'], row['kind']), ('dark.png', 'image/png', 'shown'))
        self.assertEqual(row['url'], f"/api/task-artifacts/{row['id']}")
        art = self.s.get_task_artifact(row['id'])
        self.assertEqual((art['TaskId'], art['Kind']), (self.tid, 'shown'))
        kept = session_artifacts.confined(art['Path'])
        self.assertTrue(kept and kept.read_bytes().startswith(PNG))     # its own copy, kept after the scratch folder is cleared
        # ...and with a view in the same call, the view's mark is last, so the chat reads its spec whole (viewSpec.specIn)
        text, err = tool(self.tid, 'show', files=[str(d / 'dark.png')], **one('stats', {'items': [{'label': 'Palettes', 'value': 2}]}))
        self.assertFalse(err, text)
        self.assertLess(text.index(agenttools.FILES_MARK), text.index(viewspec.MARK))
        self.assertEqual(json.loads(text.split(viewspec.MARK)[1])['elements']['a']['type'], 'stats')
        # ...and the general chat's payload places the copy under an answer, as a file it chose to show
        self.assertTrue(any(p['kind'] == 'shown' and p['name'] == 'dark.png' for p in server._assistant_payload(self.tid)['published']))

    def test_a_picture_shown_with_a_view_of_only_its_words_is_the_picture_alone(self):
        """His live app, 2026-11-25 ("really dumb visual that provides nothing"): a Codex agent showed the picture it drew together with a
        view titled for it holding nothing but its alt text. The picture stands; a view of only words is no view - nothing drawn, nothing
        kept, the agent told why - and a view refused beside files never takes the files down with it."""
        import tempfile
        from pathlib import Path
        d = Path(tempfile.mkdtemp(dir=tempfile.gettempdir())); (d / 'gate.png').write_bytes(PNG + b'fake')
        words = {'title': 'Install illustration', 'root': 'g', 'elements': {'g': {'type': 'grid', 'props': {}, 'children': ['alt', 'n']},
                 'alt': {'type': 'text', 'props': {'text': '**Alt text**\n\nA robot waits outside a locked server room.'}},
                 'n': {'type': 'note', 'props': {'text': 'For Erin Blake to look over.'}}}}
        text, err = tool(self.tid, 'show', files=[str(d / 'gate.png')], **words)
        self.assertFalse(err, text)
        self.assertNotIn(viewspec.MARK, text)
        self.assertIn('The view was not drawn - a view of only words', text)
        self.assertLess(text.index('not drawn'), text.index(agenttools.FILES_MARK))          # ...ahead of the rows the chat reads to their "]"
        self.assertEqual(json.loads(text.split(agenttools.FILES_MARK)[1])[0]['name'], 'gate.png')
        self.assertFalse([a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'view'])
        text, err = tool(self.tid, 'show', files=[str(d / 'gate.png')], **one('marquee', {}))         # a bad view: the picture still stands
        self.assertFalse(err, text); self.assertIn("type 'marquee' is not one of", text)
        self.assertEqual(json.loads(text.split(agenttools.FILES_MARK)[1])[0]['name'], 'gate.png')
        text, err = tool(self.tid, 'show', **words)                                          # ...and alone, it is refused with why
        self.assertTrue(err); self.assertIn('a view of only words shows nothing your answer does not', text)

    # A DRAWN VIEW IS KEPT WITH THE TASK (2026-11-10): the CLI's log was its only copy - cleaned up, the table was gone from the chat
    def test_a_view_shown_in_a_turn_is_drawn_from_the_task_once_its_session_log_is_gone_and_never_twice(self):
        import tempfile
        from pathlib import Path
        from taskuary import sessionrecord
        text, err = tool(self.tid, 'show', **SPEC)
        self.assertFalse(err, text)
        (art,) = [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'view']
        self.assertEqual(art['ContentType'], 'application/json')
        self.s.add_transcript(self.tid, 'pty-1', 'the pane, as it ended', agent='coding', ext_id='a-log-cleaned-up', brain='claude')
        drawn = lambda ss: [x for s in ss for x in s.get('steps') or [] if viewspec.MARK in str(x.get('output') or '')]
        with mock.patch.object(sessionrecord, '_home', lambda: Path(tempfile.mkdtemp())):     # no CLI log anywhere
            rec = sessionrecord.record(self.s, self.tid)['sessions']
            for ss in (rec,):
                (step,) = drawn(ss)
                self.assertEqual((step['k'], step['name']), ('tool', 'show'))
                self.assertEqual(json.loads(step['output'].split(viewspec.MARK)[1])['title'], 'Northwind renewals')
            # ...and while the session's own record still carries it, that copy is the one drawn
            sessionrecord._saved_path(self.tid, 'pty-1').write_text(json.dumps({'steps': [
                {'k': 'tool', 'name': 'mcp__taskuary__show', 'text': '', 'output': text}, {'k': 'said', 'text': 'Three are due.'}]}), encoding='utf-8')
            self.assertEqual([x['name'] for x in drawn(sessionrecord.record(self.s, self.tid)['sessions'])], ['mcp__taskuary__show'])

    def test_a_turn_whose_show_step_kept_only_its_title_draws_the_view_the_task_kept(self):
        """Recorded on the real CLI, 2026-11-15: Codex calls `show` from inside its own `exec` tool, and its turn's step held the call's title
        and no answer - the chat said "Your bar chart is ready" over no chart, and the step opened to `show {"title": ...}` as JSON. The
        conversation's turn draws the view the task kept, on its `show` step, as the server's answer."""
        from taskuary import conversation, sessionrecord
        text, err = tool(self.tid, 'show', **SPEC)
        self.assertFalse(err, text)
        (art,) = [a for a in self.s.list_task_artifacts(self.tid) if a.get('Kind') == 'view']
        at = conversation.ep(art['CreatedAt'])
        turn = {'kind': 'turn', 'state': 'done', 'started': at - 5, 'ended': at + 3, 'text': 'Your chart is ready.', 'cards': [],
                'steps': [{'k': 'tool', 'name': 'mcp__taskuary__show', 'text': 'Northwind renewals', 'args': {'title': 'Northwind renewals'}}]}
        later = {**turn, 'started': at + 60, 'ended': at + 90, 'steps': [{'k': 'tool', 'name': 'mcp__taskuary__show', 'args': {'title': 'x'}}]}
        sessionrecord.views_onto([turn, later], self.s.list_task_artifacts(self.tid))
        self.assertEqual(json.loads(turn['steps'][0]['output'].split(viewspec.MARK)[1])['title'], 'Northwind renewals')
        self.assertNotIn('output', later['steps'][0], 'a view goes only on the turn it was drawn in')

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


# WHAT IT MAKES FOR HIM TO LOOK AT, IT SHOWS (the owner, 2026-11-15: he asked for a query to review, the agent saved it as a file and said
# only that it was ready - the ruling: the agent decides what to show, code draws it). One sentence, the same on every road, and a file
# that is plain text can be shown whatever its name - by its bytes
def test_every_show_tool_carries_the_one_sentence_on_showing_what_it_makes():
    from taskuary import apiagent, selfclose
    assert selfclose.SHOW_WHAT in agenttools.TOOLS['show'][1], 'the tool a CLI session is handed'
    assert selfclose.SHOW_WHAT in apiagent.FULL['show'], 'the tool an API brain is handed'
    assert selfclose.SHOW_WHAT in agenttools.rpc({'id': 1, 'method': 'initialize'}, None)['result']['instructions'], 'what a CLI session is told'
    assert selfclose.SHOW_WHAT in selfclose.SHOW_LINE, 'the line a chat with no tool reads'


def test_a_query_saved_as_a_file_is_shown_as_text_by_its_bytes():
    import tempfile
    from pathlib import Path
    from taskuary import session_artifacts
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Clear three columns on three rows', 'Kind': 'general'}, 'owner')
    d = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))
    (d / 'clear_columns.sql').write_text('BEGIN;\nUPDATE facilities SET fax = NULL WHERE id IN (14, 22, 31);\nCOMMIT;\n', encoding='utf-8')
    a = session_artifacts.shown(s, tid, d / 'clear_columns.sql', 'agent')
    assert (a['Name'], a['ContentType'], a['Kind']) == ('clear_columns.sql', 'text/plain', 'shown')
    assert 'UPDATE facilities' in Path(a['Path']).read_text(encoding='utf-8')
    (d / 'blob.dat').write_bytes(bytes([0, 1, 2, 255]) * 40)
    try: session_artifacts.shown(s, tid, d / 'blob.dat', 'agent'); raise AssertionError('bytes that are no text are not shown')
    except ValueError as e: assert 'cannot be shown' in str(e)



def test_the_tools_one_example_is_a_good_spec_with_a_grid_tiles_a_chart_a_table_and_a_checklist():
    # ...read through the guide tool now (guides.py, 2026-11-09): the tool's description names it, and stays short
    assert '`show` topic' in agenttools.TOOLS['show'][1] and agenttools.SHOW_EXAMPLE in agenttools.call(None, 1, 'guide', {'topic': 'show'}, {})
    v = viewspec.check(json.loads(agenttools.SHOW_EXAMPLE))
    assert sorted({e['type'] for e in v['elements'].values()}) == ['chart', 'checklist', 'grid', 'stats', 'table']
    assert len(v['elements']['kpi']['props']['items']) == 3


def test_the_agent_is_told_what_its_tools_do_and_a_sheet_it_made_is_in_front_of_him():
    """The walks, 2026-11-21: a chart took five calls - the schema said only `elements: object`, and each refusal named one rule; `tick` was
    called with `id` ("by its id", its field is `item") from a schema Claude had deferred; a bare `show` was not found; and show answered
    ".xlsx cannot be shown" while the chat drew the sheet - so the agent told him it could not be previewed, over a Q4 column the preview drew
    blank (formulas, no cached values)."""
    import tempfile
    from pathlib import Path
    from openpyxl import Workbook
    from taskuary import outputs
    el = agenttools.TOOLS['show'][2]['properties']['elements']['additionalProperties']
    assert set(el['properties']['type']['enum']) >= {'chart', 'table', 'stats'} and 'root' in agenttools.TOOLS['show'][2]['properties']
    assert el['properties']['props']['properties']['points']['items']['required'] == ['label', 'value']
    try: viewspec.shown({'elements': {'c': {'type': 'bar', 'props': {'data': [1]}}}}); raise AssertionError('refused')
    except ValueError as e: assert 'A view that passes: ' in str(e) and viewspec.check(json.loads(str(e).split('A view that passes: ')[1]))
    assert '`item` is its id' in agenttools.TOOLS['tick'][1] and '`item`' in agenttools.SHORT['tick'] and 'tick' in agenttools.ALWAYS_LOAD
    s = MemoryStore(); tid = s.create_task({'Title': 'Q4 spend forecast', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.append(['Vendor', 'Q3', 'Q4']); ws.append(['Payworth', 1200, '=B2*1.1']); wb.save(out / 'forecast.xlsx')
    said = agenttools.show_files(s, tid, [str(out / 'forecast.xlsx')])
    assert 'already' in said and 'forecast.xlsx' in said and 'cannot be shown' not in said
    assert outputs.sheet(out / 'forecast.xlsx')['rows'][1] == ['Payworth', '1200', '1320']


def test_a_sheet_of_formulas_nothing_worked_out_previews_its_numbers():
    """Walk 2, 2026-11-21: a cash plan an agent wrote with openpyxl previewed "=$B$3", "=B8+E8" - formulas with no values. The preview works
    them out from the sheet's own cells; one it cannot (another function, a word in a sum) still reads as itself."""
    import tempfile
    from pathlib import Path
    from openpyxl import Workbook
    from taskuary import outputs
    wb = Workbook(); ws = wb.active
    ws.append(['Start', 50000]); ws.append(['Income', 6500]); ws.append(['Costs', 8000]); ws.append(['Month', 'Start', 'Net', 'End'])
    for r in range(5, 8): ws.append([f'M{r - 4}', '=$B$1' if r == 5 else f'=D{r - 1}', '=$B$2-$B$3', f'=B{r}+C{r}'])
    ws.append(['Total', '=SUM(C5:C7)', '=AVERAGE(D5:D7)/3', '=VLOOKUP(A1,A1:B3,2)']); ws.append(['', '=A1+1', '=SUM(A1:B2)'])
    p = Path(tempfile.mkdtemp()) / 'plan.xlsx'; wb.save(p)
    rows = outputs.sheet(p)['rows']
    assert rows[4:7] == [['M1', '50000', '-1500', '48500'], ['M2', '48500', '-1500', '47000'], ['M3', '47000', '-1500', '45500']]
    assert rows[7] == ['Total', '-4500', '15666.67', '=VLOOKUP(A1,A1:B3,2)'] and rows[8][1:] == ['=A1+1', '56500', '']


def test_a_sheet_previews_its_numbers_as_their_cells_format_them():
    """The walk, 2026-11-22: a budget's dollars previewed as 147210 and its variance as -0.63 - the preview read values and dropped their
    formats. Each number reads as its cell's format shows it in Excel."""
    import tempfile
    from pathlib import Path
    from openpyxl import Workbook
    from taskuary import outputs
    wb = Workbook(); ws = wb.active; ws.append(['Line', 'Budget', 'Variance'])
    ws.append(['Payroll', 147210, -0.63]); ws['B2'].number_format = '$#,##0'; ws['C2'].number_format = '0%'
    ws.append(['Travel', '=B2/10', 0.1234]); ws['B3'].number_format = '$#,##0.00'; ws['C3'].number_format = '0.0%'
    p = Path(tempfile.mkdtemp()) / 'budget.xlsx'; wb.save(p)
    assert outputs.sheet(p)['rows'][1:] == [['Payroll', '$147,210', '-63%'], ['Travel', '$14,721.00', '12.3%']]


def test_a_path_without_its_root_is_read_in_the_tasks_own_folders():
    """WALK 9 (2026-11-23): show refused "outputs/TQ-0014/sample-invoice.pdf" and a bare "crm-10-seat-pricing.pdf" as outside the outputs folder
    they were in, while the same turn's end_turn said it showed them. A relative path is the task's own: its outputs folder, then the scratch."""
    from taskuary import outputs
    from taskuary.store import task_ref
    s = MemoryStore(); tid = s.create_task({'Title': 'Sample invoice', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
    (out / 'sample-invoice.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0' * 32)
    for name in ('sample-invoice.png', f'outputs/{task_ref(tid)}/sample-invoice.png'):
        said = agenttools.show_files(s, tid, [name])
        assert 'only a file in' not in said and 'no such file' not in said, (name, said)
    try: agenttools.show_files(s, tid, ['../../../../../../etc/hosts']); raise AssertionError('a path climbing out is never read')
    except ValueError as e: assert 'only a file in' in str(e) or 'no such file' in str(e), e


def test_a_file_shown_comes_back_as_what_it_reads():
    """Walk 9 (45, 46): the agent wrote its sheet and its PDF through a shell that ate every "$558" as a variable - the files read "Starter ,400"
    while the chat said "$1,400" - and nothing read the file back. What a shown file reads is in show's answer: a broken deliverable is a fact
    the agent sees, on any brain and any shell."""
    from openpyxl import Workbook
    from taskuary import outputs
    s = MemoryStore(); tid = s.create_task({'Title': 'Three CRM tools, 10 seats', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
    wb = Workbook(); ws = wb.active; ws.append(['Plan', 'Price']); ws.append(['Starter', ',400']); wb.save(out / 'crm-pricing.xlsx')
    (out / 'notes.txt').write_text('Professional - - ,000 ,800', encoding='utf-8')
    said = agenttools.show_files(s, tid, [str(out / 'crm-pricing.xlsx'), str(out / 'notes.txt')])
    assert 'Starter' in said and ',400' in said and 'Professional - - ,000 ,800' in said, said



def deck(path, *slides):
    "A .pptx of `slides`, each one line of text - the zip of XML a deck is."
    import zipfile
    with zipfile.ZipFile(path, 'w') as z:
        for i, t in enumerate(slides, 1):
            z.writestr(f'ppt/slides/slide{i}.xml', '<p:sld xmlns:p="p" xmlns:a="a"><a:p><a:r><a:t>' + t + '</a:t></a:r></a:p></p:sld>')


def test_a_deck_that_cannot_be_drawn_is_still_read_back():
    """Walk 10, 2026-11-23: after "update everything" the deck still said "212 headcount" on slide 2, and show answered only ".pptx cannot be
    shown" - nothing read it back, and it went to the board. Every file show is handed is read back, drawn or not."""
    from taskuary import outputs
    s = MemoryStore(); tid = s.create_task({'Title': 'Q3 board pack', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid); out.mkdir(parents=True, exist_ok=True)
    deck(out / 'board-deck.pptx', 'Q3 board pack', 'Strong operating margin at 18.9% with 212 headcount')
    said = agenttools.show_files(s, tid, [str(out / 'board-deck.pptx')])
    assert agenttools.SHOWN_SAY in said and '212 headcount' in said, said


# ── WHAT-IF AND ANSWERS (the owner, 2026-11-24, after json-render's state and actions): controls move a value of the view's state on his
# screen alone, values worked out from it are checked here and evaluated on the page; his pick on a choice reaches the agent once
WHAT_IF = {'title': 'Payworth seats', 'state': {'seats': 40}, 'root': 'g', 'elements': {
    'g': {'type': 'grid', 'props': {'cols': 1}, 'children': ['s', 'k', 't', 'go']},
    's': {'type': 'slider', 'props': {'label': 'Seats', 'value': {'$bindState': '/seats'}, 'min': 5, 'max': 200, 'step': 5}},
    'k': {'type': 'stats', 'props': {'items': [{'label': 'Per month', 'format': 'currency', 'value': {'$expr': 'seats * 12'}}]}},
    't': {'type': 'table', 'props': {'rows': [{'Plan': 'Basic', 'Per seat': 12, 'Total': {'$expr': 'per_seat * seats'}}]}},
    'go': {'type': 'button', 'props': {'label': 'Go with this'}, 'on': {'press': {'action': 'answer', 'params': {'text': '{seats} seats'}}}}}}


class TheWhatIf(unittest.TestCase):
    def test_controls_and_worked_out_values_pass_and_say_what_is_wrong(self):
        v = viewspec.check(WHAT_IF)
        self.assertEqual(v['state'], {'seats': 40})
        self.assertEqual(v['elements']['s']['props']['value'], 'seats')
        self.assertEqual(v['elements']['t']['props']['columns'], ['Plan', 'Per seat', 'Total'])      # records stand as they came
        self.assertEqual(viewspec.check(v), v)
        # ...a control's value with no state behind it starts where its control does
        self.assertEqual(viewspec.check(one('toggle', {'label': 'Yearly', 'value': 'annual'}))['state'], {'annual': False})
        bad = lambda spec, says: self.assertRaisesRegex(ValueError, says, viewspec.check, spec)
        tile = lambda src: {**WHAT_IF, 'elements': {**WHAT_IF['elements'], 'k': {'type': 'stats', 'props': {'items': [{'label': 'x', 'value': {'$expr': src}}]}}}}
        bad(tile('seat * 12'), "reads seat, which the view has no value for - its state has seats")
        bad(tile('seats *'), 'it ends too soon')
        bad(tile('__import__("os")'), r"__import__\(\) is not one of min, max")
        bad({**WHAT_IF, 'elements': {**WHAT_IF['elements'], 'go': {'type': 'button', 'props': {'label': 'Pay'}, 'on': {'press': {'action': 'pay'}}}}},
            "must be answer .* or setState")
        bad(one('slider', {'label': 'x', 'value': 'n', 'min': 5, 'max': 5}), 'min must be under max')

    def test_only_a_view_he_can_answer_has_an_id_of_its_own(self):
        # ...and the spec is the answer's last thing: the chat reads it from the mark to the end, and words after it left a choice undrawn
        said = lambda spec: json.loads(viewspec.shown(spec).partition(viewspec.MARK)[2])
        self.assertIn('His pick comes to you', viewspec.shown(WHAT_IF).partition(viewspec.MARK)[0])
        self.assertNotIn('id', said(SPEC))
        a, b = said(WHAT_IF), said(WHAT_IF)
        self.assertNotEqual(a['id'], b['id'])                # ...the same choice shown twice is two questions


class TheAnswer(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        self.s = MemoryStore()
        self.p = mock.patch.object(server, 'store', self.s); self.p.start()
        self.tid = self.s.create_task({'Title': 'Renew Payworth', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        self.c = TestClient(server.app, base_url='http://127.0.0.1', headers={'X-Taskuary-Token': server.cfg['server'].get('token') or ''})

    def tearDown(self): self.p.stop()

    def test_his_pick_reaches_the_agent_once_as_his_press(self):
        from taskuary import events, general
        told = []
        with mock.patch.object(general, 'to_agent', lambda *a, **k: told.append((a, k)) or 'told'):
            r = self.c.post(f'/api/tasks/{self.tid}/view-answer', json={'view': 'v1', 'el': 'c', 'pick': 'Pro - $540/mo', 'asked': 'Which plan?'})
            self.assertEqual(r.status_code, 200, r.text); self.assertEqual(r.json()['told'], 'told')
            # ...pressed twice - a double click, a second tab - it is still one answer, and the second says the first
            again = self.c.post(f'/api/tasks/{self.tid}/view-answer', json={'view': 'v1', 'el': 'c', 'pick': 'Basic - $200/mo'})
        self.assertEqual(again.status_code, 409); self.assertIn('Pro - $540/mo', again.json()['detail'])
        self.assertEqual(len(told), 1); self.assertEqual(told[0][1]['frm'], 'taskuary')
        said, _ = events.take(self.s, self.tid)
        self.assertEqual(said.count('Pro - $540/mo'), 1, said); self.assertIn('Which plan?', said)
        self.assertEqual(self.c.get(f'/api/tasks/{self.tid}/view-answers').json(), {'v1': {'c': 'Pro - $540/mo'}})
        # ...and no chat line besides: the view he pressed shows it (general.press_lines)
        self.assertFalse([m for m in general.press_lines(self.s, self.tid) if 'Pro' in m['content'][0]['text']])


def test_files_handed_over_stand_in_the_order_they_were_handed():
    """The card gallery, 2026-11-25: "three versions - pick one" stood newest first - the third version led the group, and a board pack led
    with its clip. The files of one hand-over stand in the order the agent handed them, whatever was written last."""
    import os, shutil
    from taskuary import outputs
    s = MemoryStore(); tid = s.create_task({'Title': 'Three versions of the banner', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid)
    for d in (out, outputs.turns_folder(tid)): shutil.rmtree(d, ignore_errors=True)      # ...another test's task of the same number
    out.mkdir(parents=True, exist_ok=True)
    names = ['banner-one.md', 'banner-two.md', 'banner-three.md']
    for i, n in enumerate(names): (out / n).write_text(f'# version {i + 1}\n', encoding='utf-8'); os.utime(out / n, (1_700_000_000 + i, 1_700_000_000 + i))
    try:
        agenttools.show_files(s, tid, [str(out / n) for n in names])
        listed = [{**r, 'handed': True} for r in outputs.listing(tid)]
        assert [r['name'] for r in listed] == names[::-1], 'the folder lists newest first'
        assert [r['name'] for r in outputs.as_handed(listed, outputs.handed(tid))] == names
        agenttools.show_files(s, tid, [str(out / names[0])])                       # ...shown again, it keeps its place
        assert outputs.handed(tid) == names
    finally: shutil.rmtree(out, ignore_errors=True); shutil.rmtree(outputs.turns_folder(tid), ignore_errors=True)


def test_each_show_call_is_a_hand_over_of_its_own():
    """The card gallery, 2026-11-25: a chart and its workbook, each shown by a call of its own in one turn, stood as one artifact "2 files".
    One call is one hand-over: the files of a call share its number, the next call's have the next, and the page draws each as its own."""
    import shutil
    from taskuary import outputs
    s = MemoryStore(); tid = s.create_task({'Title': 'A chart and its numbers', 'Kind': 'general'}, 'owner')
    out = outputs.folder(tid)
    for d in (out, outputs.turns_folder(tid)): shutil.rmtree(d, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    for n in ('chart.md', 'numbers.md', 'notes.md'): (out / n).write_text(f'# {n}\n', encoding='utf-8')
    try:
        agenttools.show_files(s, tid, [str(out / 'chart.md')])
        agenttools.show_files(s, tid, [str(out / 'numbers.md'), str(out / 'notes.md')])
        assert outputs.calls(tid) == [['chart.md'], ['numbers.md', 'notes.md']]
        by = outputs.call_of(tid)
        assert by['chart.md'] != by['numbers.md'] and by['numbers.md'] == by['notes.md']
        # ...and a list kept before calls were is one hand-over, as it was drawn
        (outputs.turns_folder(tid) / 'handed.json').write_text('["chart.md", "numbers.md"]', encoding='utf-8')
        assert outputs.calls(tid) == [['chart.md', 'numbers.md']] and outputs.handed(tid) == ['chart.md', 'numbers.md']
    finally: shutil.rmtree(out, ignore_errors=True); shutil.rmtree(outputs.turns_folder(tid), ignore_errors=True)

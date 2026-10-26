"""Write-back to Jira, Monday and Linear (trackers.py, 2026-10-25): an agent's comment, move, assignment or close waits as a proposal
on its own task, and the close-out of a tracker task proposes "comment and move to done". Against FAKE upstreams - a Jira REST and two
GraphQL servers in memory - so the tests can prove nothing is written before the press, and that what the card carries is what goes.
"""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient
from taskuary import agenttools, config, guard, proposals, reports, scopes, server, trackers, verdicts, wrapup
from taskuary.store import MemoryStore


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body
        self.content = b'' if body is None else json.dumps(body).encode()
        self.text, self.reason = self.content.decode(), 'fake'
    def json(self): return self._b


class FakeJira:
    """Jira REST v3 as far as the write-back reads it: an issue's status and the workflow's transitions out of it."""
    def __init__(self, status='In Review', cat='indeterminate', done=True, users=({'accountId': 'acc-erin', 'displayName': 'Erin Blake'},)):
        self.status, self.cat, self.users, self.writes = status, cat, list(users), []
        self.tr = [{'id': '21', 'name': 'Back to work', 'to': {'name': 'In Progress', 'statusCategory': {'key': 'indeterminate'}}}]
        if done: self.tr.append({'id': '31', 'name': 'Ship it', 'to': {'name': 'Done', 'statusCategory': {'key': 'done'}}})

    def __call__(self, method, url, json=None, **kw):
        path = url.split('northwind.example', 1)[1]
        if method == 'GET' and path.startswith('/rest/api/3/issue/NW-12?'):
            return Resp(body={'key': 'NW-12', 'fields': {'summary': 'Export is empty', 'status': {'name': self.status, 'statusCategory': {'key': self.cat}}}})
        if method == 'GET' and path == '/rest/api/3/issue/NW-12/transitions': return Resp(body={'transitions': self.tr})
        if method == 'GET' and path.startswith('/rest/api/3/user/assignable/search'): return Resp(body=self.users)
        if method in ('POST', 'PUT'):
            self.writes.append((method, path, json))
            if path.endswith('/transitions'):
                hit = next(x for x in self.tr if x['id'] == json['transition']['id'])
                self.status, self.cat = hit['to']['name'], hit['to']['statusCategory']['key']
                return Resp(204)
            return Resp(201, {'id': '10001'}) if path.endswith('/comment') else Resp(204)
        return Resp(404, {'errorMessages': [f'no {path}']})


class FakeGraphQL:
    """Monday and Linear: the documents the write-back sends, answered by what they ask for; every mutation recorded with its variables."""
    def __init__(self, monday_done=(1,), linear_completed=True):
        self.md, self.lc, self.writes = list(monday_done), linear_completed, []

    def __call__(self, url, json=None, **kw):
        q, v = json['query'], json['variables']
        if q.lstrip().startswith('mutation'):
            self.writes.append((url, q, v))
            return Resp(body={'data': {k: {'success': True, 'id': '9'} for k in ('create_update', 'commentCreate', 'issueUpdate',
                                                                                 'change_simple_column_value', 'change_column_value')}})
        if 'monday' in url:
            if 'users(' in q: return Resp(body={'data': {'users': [{'id': '77', 'name': 'Gail Moreno', 'email': 'gail@northwind.example'}]}})
            labels = {'labels': {'0': 'Working on it', '1': 'Shipped', '2': 'Stuck'}, **({'done_colors': self.md} if self.md else {})}
            return Resp(body={'data': {'items': [{'id': v['ids'][0], 'name': 'Northwind kiosk refresh', 'url': 'https://northwind.example/m/4410',
                                                  'board': {'id': '88', 'columns': [
                                                      {'id': 'status', 'title': 'Stage', 'type': 'status', 'settings_str': __import__('json').dumps(labels)},
                                                      {'id': 'person', 'title': 'Owner', 'type': 'people', 'settings_str': '{}'}]},
                                                  'column_values': [{'id': 'status', 'type': 'status', 'text': 'Working on it'}]}]}})
        if 'users(' in q: return Resp(body={'data': {'users': {'nodes': [{'id': 'u-ray', 'name': 'Ray Colton'}]}}})
        states = [{'id': 's-todo', 'name': 'Todo', 'type': 'unstarted', 'position': 0}, {'id': 's-rev', 'name': 'In Review', 'type': 'started', 'position': 2},
                  *([{'id': 's-done', 'name': 'Done', 'type': 'completed', 'position': 3}] if self.lc else []),
                  {'id': 's-x', 'name': 'Canceled', 'type': 'canceled', 'position': 4}]
        return Resp(body={'data': {'issue': {'id': 'uuid-12', 'identifier': 'NW-12', 'title': 'Export is empty', 'url': 'https://linear.app/nw/NW-12',
                                             'state': {'id': 's-todo', 'name': 'Todo', 'type': 'unstarted'}, 'team': {'states': {'nodes': states}}}}})


def upstream(jira=None, gql=None):
    "The fakes in place of the wire - and anything else that tries to leave fails the test."
    def nowhere(*a, **k): raise AssertionError(f'a call left for a real upstream: {a[:2]}')
    return mock.patch.multiple(trackers.requests, request=jira or nowhere, post=gql or nowhere)


def armed(s, t, roles='trigger'):
    c = s.get_connector_by_type(t)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'Secret': 'tok-x', 'Roles': roles,
                      'ConfigJson': json.dumps({'base_url': 'https://northwind.example', 'email': 'alex@northwind.example'} if t == 'jira' else {})}, 't')
    return s.get_connector_by_type(t)['ConnectorId']


def tracker_task(s, t='jira', item='NW-12', **over):
    tid = s.create_task({'Title': 'Export is empty', 'Kind': 'general', 'Status': 'in_progress', 'Source': t, **over}, 'triage')
    s.add_message({'TaskId': tid, 'Channel': t, 'ExternalId': f'{t}:{item}@1', 'ConversationId': f'{t}:{item}', 'FromName': 'Paula Vance',
                   'Subject': f'{item} Export is empty', 'BodyText': 'The nightly export came back empty.', 'Status': 'routed'})
    return tid


def finish(s, tid):
    prev, wrapup.REFRESH = wrapup.REFRESH, None
    try:
        with mock.patch('taskuary.responder.write_draft', return_value='unused'):
            return wrapup.finish(s, tid, {'summary': 'The export reads the new view again; tonight\'s run will be full.', 'outcome': 'did_work'},
                                 None, 'general')
    finally: wrapup.REFRESH = prev


def pending(s, tid): return s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,))


class EveryActReachesPeople(unittest.TestCase):
    def test_each_tracker_act_is_a_send_and_none_runs_as_a_report(self):
        for t in trackers.TYPES:
            self.assertIn(t, reports.REGISTRY); self.assertTrue(scopes.reaches(t), t); self.assertNotIn(t, scopes.QUIET_WRITES)
            self.assertEqual(reports.card_of(t), trackers.TYPES[t][0])
            with self.assertRaises(RuntimeError): reports.gate(MemoryStore(), {'type': t})     # a schedule is nobody's press

    def test_a_proposal_names_a_real_item_and_never_its_own_connection(self):
        ok = {'action': 'run_tool', 'type': 'jira_comment', 'item': 'NW-12', 'body': 'x'}
        self.assertEqual(trackers.check(ok), '')
        for bad in ({'item': 'NW-12/../../admin'}, {'item': ''}, {'body': ''}, {'_card': {'Secret': 'mine'}}, {'base_url': 'https://elsewhere.example'}):
            self.assertTrue(trackers.check({**ok, **bad}), bad)
        self.assertTrue(trackers.check({'type': 'monday_move', 'item': 'abc', 'status': 'Done'}))
        self.assertIn('_card', reports.CONNECTION_KEYS)                                   # query_only strips it from any body


class AnAgentsActWaitsForThePress(unittest.TestCase):
    def setUp(self):
        self.s = server.store
        self.cid = armed(self.s, 'jira', roles='trigger,tool')
        self.tid = tracker_task(self.s)
        srv = config.load()['server']
        self.agent = {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, self.tid)}
        self.c = TestClient(server.app)

    def tearDown(self): self.s.save_connector({'ConnectorId': self.cid, 'Active': 0, 'Roles': 'trigger'}, 't')

    def test_a_comment_through_tools_run_is_queued_with_its_words_and_runs_only_on_the_press(self):
        jira = FakeJira()
        with upstream(jira=jira):
            r = self.c.post('/api/tools/run', headers=self.agent, json={'type': 'jira_comment', 'body': 'Fixed - the export is full again.',
                                                                        'task_id': self.tid, 'why': 'Paula asked for an update'})
            self.assertEqual(r.status_code, 202, r.text)
            self.assertEqual(jira.writes, [])                                             # nothing reached Jira
            rv = self.s.get_review(r.json()['review'])
            p = json.loads(rv['DraftText'])
            self.assertEqual((p['type'], p['item'], p['body']), ('jira_comment', 'NW-12', 'Fixed - the export is full again.'))   # the task's own item
            self.assertIn('comment on NW-12 in Jira', rv['Reason'])
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        self.assertEqual(len(jira.writes), 1)
        method, path, body = jira.writes[0]
        self.assertEqual((method, path), ('POST', '/rest/api/3/issue/NW-12/comment'))
        self.assertEqual(body['body']['content'][0]['content'][0]['text'], 'Fixed - the export is full again.')   # what the card carried, as ADF

    def test_the_propose_tool_files_a_move_and_an_agent_may_not_raise_the_close_out(self):
        jira = FakeJira()
        with upstream(jira=jira):
            out = agenttools.call(self.s, self.tid, 'propose', {'action': 'run_tool', 'type': 'jira_move', 'status': 'In Progress', 'why': 'reopened'},
                                  {'propose': lambda tid, a: server.agent_propose(server.AgentProposeBody(**{**a, 'task_id': tid}), _Req(self.agent))})
            self.assertIn('queued', out); self.assertEqual(jira.writes, [])
            with self.assertRaises(ValueError): agenttools.proposal_of({'action': 'close_item', 'tracker': 'jira', 'item': 'NW-12'})
            self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "close_item", "tracker": "jira", "item": "NW-12", "closeout": true}'), [])
            rv = next(r for r in pending(self.s, self.tid) if json.loads(r['DraftText']).get('type') == 'jira_move')
            self.assertIn('move NW-12 in Jira to In Progress', rv['Reason'])
            proposals.execute(self.s, rv)
        self.assertEqual(jira.writes, [('POST', '/rest/api/3/issue/NW-12/transitions', {'transition': {'id': '21'}})])

    def test_a_status_the_workflow_does_not_offer_is_refused_with_what_it_does(self):
        with upstream(jira=FakeJira()):
            with self.assertRaisesRegex(RuntimeError, 'offers: In Progress, Done'):
                reports.REGISTRY['jira_move']({'_card': trackers.card(self.s, 'jira'), 'type': 'jira_move', 'item': 'NW-12', 'status': 'Blocked'})

    def test_an_assignee_two_people_answer_to_is_never_guessed(self):
        jira = FakeJira(users=[{'accountId': 'a', 'displayName': 'Erin Blake'}, {'accountId': 'b', 'displayName': 'Erin Blakely'}])
        with upstream(jira=jira):
            with self.assertRaisesRegex(RuntimeError, '2 people'):
                reports.REGISTRY['jira_assign']({'_card': trackers.card(self.s, 'jira'), 'type': 'jira_assign', 'item': 'NW-12', 'assignee': 'Erin'})
        self.assertEqual(jira.writes, [])


class _Req:
    def __init__(self, h): self.headers = h


class JiraCloseOut(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); armed(self.s, 'jira'); self.tid = tracker_task(self.s)

    def test_a_finished_jira_task_proposes_comment_and_done_and_writes_only_on_the_press(self):
        jira = FakeJira()
        with upstream(jira=jira):
            self.assertEqual(finish(self.s, self.tid)['closeout'], 'close_item')
            rv = proposals.closeout_pending(self.s, self.tid)
            p = json.loads(rv['DraftText'])
            self.assertEqual((p['tracker'], p['item'], p['status'], p['from']), ('jira', 'NW-12', 'Done', 'In Review'))
            self.assertIn('the export reads the new view again', p['text'].lower())          # the comment, drafted from the result
            self.assertIn('comment on NW-12 in Jira and move it to Done', rv['Reason'])
            self.assertEqual(jira.writes, [])                                                 # proposed, nothing written
            self.assertEqual(trackers.assess(self.s, p)['ok'], True)
            self.assertTrue(verdicts.decide(self.s, rv, 'approve', final_text='Fixed - tonight\'s export will be full.')['ok'])
        self.assertEqual([w[1] for w in jira.writes], ['/rest/api/3/issue/NW-12/comment', '/rest/api/3/issue/NW-12/transitions'])
        self.assertEqual(jira.writes[0][2]['body']['content'][0]['content'][0]['text'], 'Fixed - tonight\'s export will be full.')   # the owner's edit
        self.assertEqual(jira.writes[1][2], {'transition': {'id': '31'}})
        self.assertNotEqual(self.s.get_task(self.tid)['Status'], 'done')                      # sending and closing are two steps

    def test_no_move_to_done_is_said_plainly_and_the_press_posts_the_comment_alone(self):
        jira = FakeJira(done=False)
        with upstream(jira=jira):
            finish(self.s, self.tid)
            p = json.loads(proposals.closeout_pending(self.s, self.tid)['DraftText'])
            self.assertIsNone(p['status']); self.assertIn('no move to a done status from In Review', p['no_done'])
            self.assertIn('posts the comment alone', trackers.assess(self.s, p)['note'])
            out = proposals.execute(self.s, proposals.closeout_pending(self.s, self.tid))
        self.assertEqual([w[1] for w in jira.writes], ['/rest/api/3/issue/NW-12/comment'])
        self.assertTrue(out['commented']); self.assertIn('no move to a done status', out['not_moved'])

    def test_an_item_already_done_owes_no_close_out_and_an_unreadable_one_is_no_live_approve(self):
        with upstream(jira=FakeJira(status='Done', cat='done')):
            self.assertIsNone(trackers.closeout_due(self.s, self.tid))
        def down(*a, **k): raise trackers.requests.ConnectionError('no route')
        with upstream(jira=down):
            st = trackers.assess(self.s, {'tracker': 'jira', 'item': 'NW-12'})
        self.assertEqual((st['ok'], st['state']), (False, 'unknown')); self.assertIn('could not be read', st['reason'])

    def test_the_card_reads_the_tracker_through_the_closeout_endpoint(self):
        with upstream(jira=FakeJira()):
            finish(self.s, self.tid)
            rid = proposals.closeout_pending(self.s, self.tid)['ReviewId']
            with mock.patch.object(server, 'store', self.s):
                st = TestClient(server.app).get(f'/api/reviews/{rid}/closeout').json()
        self.assertEqual((st['ok'], st['to'], st['from']), (True, 'Done', 'In Review'))

    def test_an_off_card_owes_nothing(self):
        self.s.save_connector({'ConnectorId': self.s.get_connector_by_type('jira')['ConnectorId'], 'Active': 0}, 't')
        with upstream(): self.assertIsNone(trackers.closeout_due(self.s, self.tid))


class MondayAndLinear(unittest.TestCase):
    def test_monday_done_is_the_columns_own_done_label_not_a_word(self):
        s = MemoryStore(); armed(s, 'monday'); tid = tracker_task(s, 'monday', '4410'); g = FakeGraphQL()
        with upstream(gql=g):
            finish(s, tid)
            p = json.loads(proposals.closeout_pending(s, tid)['DraftText'])
            self.assertEqual((p['item'], p['status']), ('4410', 'Shipped'))                   # done_colors names label 1, whatever it says
            self.assertEqual(g.writes, [])
            proposals.execute(s, proposals.closeout_pending(s, tid))
        (u1, q1, v1), (u2, q2, v2) = g.writes
        self.assertIn('create_update', q1); self.assertEqual(v1['i'], '4410'); self.assertIn('export reads the new view', v1['b'])
        self.assertIn('change_simple_column_value', q2); self.assertEqual((v2['b'], v2['i'], v2['c'], v2['v']), ('88', '4410', 'status', 'Shipped'))

    def test_a_monday_column_with_no_done_label_offers_the_comment_alone(self):
        s = MemoryStore(); armed(s, 'monday'); tid = tracker_task(s, 'monday', '4410')
        with upstream(gql=FakeGraphQL(monday_done=())):
            finish(s, tid)
            p = json.loads(proposals.closeout_pending(s, tid)['DraftText'])
        self.assertIn('marks no label as done', p['no_done'])

    def test_monday_assign_sets_the_people_column_to_the_one_person(self):
        s = MemoryStore(); armed(s, 'monday'); g = FakeGraphQL()
        with upstream(gql=g):
            head, _ = reports.REGISTRY['monday_assign']({'_card': trackers.card(s, 'monday'), 'type': 'monday_assign', 'item': '4410', 'assignee': 'Gail Moreno'})
        self.assertIn('Gail Moreno', head)
        self.assertEqual(json.loads(g.writes[0][2]['v']), {'personsAndTeams': [{'id': 77, 'kind': 'person'}]})

    def test_linear_closes_to_the_teams_completed_state_with_variables_not_pasted_text(self):
        s = MemoryStore(); armed(s, 'linear'); tid = tracker_task(s, 'linear'); g = FakeGraphQL()
        with upstream(gql=g):
            finish(s, tid)
            rv = proposals.closeout_pending(s, tid)
            self.assertEqual(json.loads(rv['DraftText'])['status'], 'Done')
            verdicts.decide(s, rv, 'approve', final_text='Shipped "the fix" }) { injected')
        (_, q1, v1), (_, q2, v2) = g.writes
        self.assertIn('commentCreate', q1); self.assertEqual(v1, {'i': 'uuid-12', 'b': 'Shipped "the fix" }) { injected'})
        self.assertNotIn('injected', q1)                                                      # the words ride as a variable
        self.assertEqual(v2, {'i': 'uuid-12', 's': 's-done'})

    def test_a_linear_team_with_no_completed_state_says_so(self):
        s = MemoryStore(); armed(s, 'linear'); tid = tracker_task(s, 'linear')
        with upstream(gql=FakeGraphQL(linear_completed=False)):
            self.assertIn('no completed state', trackers.closeout_due(s, tid)['no_done'])


if __name__ == '__main__': unittest.main()

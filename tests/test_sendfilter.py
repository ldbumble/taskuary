"""The owner's own MCP tools stay with the agents, minus the ones that send (the owner, 2026-10-25, revised). Which tools send comes
from the server's own annotation, then a model's verdict, then the owner's correction - never a list of words over tool names - and a
tool nobody has judged, or a server whose tools could not be read, stays out until it is (fail closed).
"""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
from taskuary import sendfilter
from taskuary.store import MemoryStore

TOOLS = {'mail': [{'name': 'list_inbox', 'description': 'List messages in the inbox', 'annotations': {'readOnlyHint': True}},
                  {'name': 'send_mail', 'description': 'Send an email to the given recipients', 'annotations': {}},
                  {'name': 'save_draft', 'description': 'Save a draft in the Drafts folder; it is not sent', 'annotations': {}},
                  # named like a send, marked read-only by its server: the annotation decides, not the word
                  {'name': 'send_history', 'description': 'Read the history of sent items', 'annotations': {'readOnlyHint': True}}]}


def brain(asked):
    def b(system, user, **kw):
        t = json.loads(user)['tool']; asked.append(t)
        return json.dumps({'sends': t == 'send_mail', 'why': 'it emails people' if t == 'send_mail' else 'a draft nobody receives'})
    return b


def lister(cfg):
    if cfg.get('command') == 'mail-server': return TOOLS['mail']
    raise RuntimeError('401 - sign in first')


class TheFilter(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        (d / '.claude.json').write_text(json.dumps({'mcpServers': {'mail': {'command': 'mail-server'}},
                                                    'projects': {'C:/work/ledger': {'mcpServers': {'chat': {'type': 'http', 'url': 'https://chat.example/mcp'}}}}}))
        (d / 'config.toml').write_text('[mcp_servers.mail]\ncommand = "mail-server"\n')
        for p in (mock.patch('taskuary.climodels.claude_home', return_value=d), mock.patch.dict('os.environ', {'CODEX_HOME': str(d)}),
                  mock.patch.object(sendfilter, '_list', side_effect=lister), mock.patch.object(sendfilter, 'refresh', return_value=False),
                  mock.patch.object(sendfilter, 'claude_ai_list', return_value={})):
            p.start(); self.addCleanup(p.stop)
        self.s, self.asked = MemoryStore(), []

    def test_before_any_scan_every_server_is_left_out_whole(self):
        self.assertEqual(sorted(sendfilter.claude_denied(self.s)), ['mcp__chat', 'mcp__mail'])
        self.assertTrue(all(v['unchecked'] for v in sendfilter.verdicts(self.s, 'claude')))     # the list says "Not checked yet"

    def test_only_the_send_is_left_out_and_the_annotation_beats_the_name(self):
        sendfilter.scan(self.s, brain(self.asked))
        self.assertEqual(sorted(sendfilter.claude_denied(self.s)), ['mcp__chat', 'mcp__mail__send_mail'])
        self.assertEqual(sorted(self.asked), ['save_draft', 'send_mail'])           # read-only tools are never asked about
        mail = next(v for v in sendfilter.verdicts(self.s, 'claude') if v['server'] == 'mail')
        self.assertEqual({t['name']: t['by'] for t in mail['tools']}['list_inbox'], 'annotation')
        chat = next(v for v in sendfilter.verdicts(self.s, 'claude') if v['server'] == 'chat')
        self.assertTrue(chat['blocked']); self.assertIn('401', chat['error'])

    def test_a_verdict_is_kept_and_not_asked_twice(self):
        sendfilter.scan(self.s, brain(self.asked)); sendfilter.scan(self.s, brain(self.asked))
        self.assertEqual(sorted(self.asked), ['save_draft', 'send_mail'])

    def test_no_brain_means_unjudged_tools_stay_out(self):
        sendfilter.scan(self.s, brain=False)
        mail = next(v for v in sendfilter.verdicts(self.s, 'claude') if v['server'] == 'mail')
        self.assertEqual({t['name'] for t in mail['tools'] if t['unchecked']}, {'send_mail', 'save_draft'})
        self.assertIn('mcp__mail__save_draft', sendfilter.claude_denied(self.s))
        self.assertNotIn('mcp__mail__list_inbox', sendfilter.claude_denied(self.s))

    def test_the_owners_correction_wins(self):
        sendfilter.scan(self.s, brain(self.asked))
        sendfilter.correct(self.s, 'mail', 'send_mail', 'keep'); sendfilter.correct(self.s, 'mail', 'save_draft', 'block')
        sendfilter.correct(self.s, 'chat', '*', 'keep')
        self.assertEqual(sendfilter.claude_denied(self.s), ['mcp__mail__save_draft'])
        with self.assertRaises(ValueError): sendfilter.correct(self.s, 'mail', 'x', 'maybe')

    def test_codex_gets_its_own_spelling_for_the_servers_it_defines(self):
        sendfilter.scan(self.s, brain(self.asked))
        self.assertEqual(sendfilter.codex_args(self.s), ['-c', 'mcp_servers.mail.disabled_tools=["send_mail"]'])


# the init event of a `claude -p --output-format stream-json` start, cut to what the lister reads (shape seen on Claude Code 2.1.310)
INIT = {'type': 'system', 'subtype': 'init',
        'mcp_servers': [{'name': 'taskuary', 'status': 'connected', 'source': 'dynamic'},
                        {'name': 'claude.ai Team Chat', 'status': 'connected', 'source': 'claudeai'},
                        {'name': 'claude.ai Files', 'status': 'needs-auth', 'source': 'claudeai'}],
        'tools': ['Bash', 'mcp__taskuary__my_task', 'mcp__claude_ai_Team_Chat__search', 'mcp__claude_ai_Team_Chat__post_message']}


class TheClaudeAiConnectors(unittest.TestCase):
    """claude.ai account connectors are in no file Taskuary reads: their names come once from a short Claude start, and they are then
    judged and filtered like the rest - one that lists no tools (not signed in) is left out whole."""
    def test_the_names_come_from_the_init_event_and_the_start_is_stopped_there(self):
        class P:
            pid, stopped = 4242, False
            stdout = iter(['not json', json.dumps(INIT), json.dumps({'type': 'assistant'})])
            def poll(self): return None
            def kill(self): P.stopped = True
            def wait(self, t=None): return 0
        argv = []
        with mock.patch('taskuary.clis.which', return_value='claude'), \
             mock.patch('taskuary.spawn.popen', side_effect=lambda a, **kw: argv.append((a, kw)) or P()), \
             mock.patch.object(sendfilter.os, 'name', 'posix'):
            got = sendfilter.claude_ai_list()
        self.assertEqual(got, {'claude.ai Team Chat': {'status': 'connected', 'tools': ['search', 'post_message']},
                               'claude.ai Files': {'status': 'needs-auth', 'tools': []}})
        a, kw = argv[0]
        self.assertIn('--setting-sources', a); self.assertEqual(a[a.index('--setting-sources') + 1], 'project,local')   # no user hooks
        self.assertFalse(any(k.startswith('TASKUARY_') for k in kw['env']))
        self.assertTrue(P.stopped)                                            # stopped at init: no turn is spent

    def test_no_claude_is_said_and_not_raised_through_a_scan(self):
        with mock.patch('taskuary.clis.which', return_value=''):
            with self.assertRaises(RuntimeError): sendfilter.claude_ai_list()

    def test_they_are_judged_by_name_read_once_and_one_not_signed_in_is_left_out_whole(self):
        d = Path(tempfile.mkdtemp()); (d / '.claude.json').write_text('{}')
        listed = {'claude.ai Team Chat': {'status': 'connected', 'tools': ['search', 'post_message']},
                  'claude.ai Files': {'status': 'needs-auth', 'tools': []}}
        s, asked = MemoryStore(), []
        def b(system, user, **kw):
            t = json.loads(user)['tool']; asked.append(t)
            return json.dumps({'sends': t == 'post_message', 'why': 'it posts in a channel' if t == 'post_message' else 'it reads'})
        with mock.patch('taskuary.climodels.claude_home', return_value=d), mock.patch.dict('os.environ', {'CODEX_HOME': str(d)}), \
             mock.patch.object(sendfilter, 'refresh', return_value=False), \
             mock.patch.object(sendfilter, 'claude_ai_list', return_value=listed) as ls:
            sendfilter.scan(s, b); sendfilter.scan(s, b)
            self.assertEqual(ls.call_count, 1)                                # once, not on every scan
            self.assertEqual(sorted(sendfilter.claude_denied(s)), ['mcp__claude_ai_Files', 'mcp__claude_ai_Team_Chat__post_message'])
            self.assertEqual(sendfilter.codex_args(s), [])                    # Codex does not load them
            sendfilter.scan(s, b, relist=True); self.assertEqual(ls.call_count, 2)    # the owner's Check again reads them anew
            sendfilter.correct(s, 'claude.ai Files', '*', 'keep')
            self.assertEqual(sendfilter.claude_denied(s), ['mcp__claude_ai_Team_Chat__post_message'])
        self.assertEqual(sorted(asked), ['post_message', 'search'])


class TheOwnersWord(unittest.TestCase):
    def test_an_agent_cannot_clear_a_send_tool_and_the_owner_can_read_the_list(self):
        from fastapi.testclient import TestClient
        from taskuary import config, server
        c, srv = TestClient(server.app), config.load()['server']
        with mock.patch.object(sendfilter, 'refresh', return_value=False):
            r = c.post('/api/sendfilter/correct', headers={'X-Taskuary-Token': srv['agent_token']},
                       json={'server': 'mail', 'tool': 'send_mail', 'verdict': 'keep'})
            self.assertEqual(r.status_code, 403)
            j = c.get('/api/sendfilter').json()
        self.assertIn('claude', j); self.assertIn('codex', j)


if __name__ == '__main__': unittest.main()

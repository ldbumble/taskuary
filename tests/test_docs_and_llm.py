"""Template docs, doc-sync automation, and the cloud-AI llm layer - all offline."""
import unittest
from unittest import mock
from taskuary.store import MemoryStore
from taskuary import docsync, learn, llm


class TemplateTests(unittest.TestCase):
    def test_docs_seeded_from_templates(self):
        s = MemoryStore()
        soul, coder = s.get_doc('soul'), s.get_doc('coder')
        # the OPEN-SOURCE docs read as a person, not token soup: John Smith is the example.
        # A real owner converts every mention at once - via retoken + the one setting.
        self.assertIn('John Smith', soul); self.assertIn('John', coder)
        self.assertEqual(s.owner()['owner'], 'the owner')       # the example is not an identity
        s.set_setting('owner_name', 'Dana Reyes', 'owner')
        s.set_setting('owner_email', 'dana@northwind.example', 'owner')
        from taskuary.store import retoken_doc
        for name in ('soul', 'coder'):                          # what _heal_owner_docs does at launch
            s.save_doc(name, retoken_doc(retoken_doc(s.get_doc(name), 'John Smith', 'john.smith@example.com'),
                                         'Dana Reyes', 'dana@northwind.example'), 'test')
        self.assertIn('Dana Reyes', s.doc('soul'))
        self.assertIn('dana@northwind.example', s.doc('soul'))
        self.assertIn('Dana is', s.doc('coder'))                # {{owner_first}}, in prose
        self.assertNotIn('John', s.doc('soul'))
        self.assertNotIn('{{owner', s.doc('soul'))              # nothing unresolved reaches the AI
        self.assertIn(docsync.CONN_START, soul)
        self.assertIn('Closing out', coder)      # no report contract: the transcript IS the report
        self.assertTrue(s.get_doc('digest'))

    def test_owner_edits_never_overwritten(self):
        s = MemoryStore()
        s.save_doc('soul', 'my own rules', 'owner')
        s2_content = s.get_doc('soul')  # re-init on same db would use INSERT OR IGNORE
        self.assertEqual(s2_content, 'my own rules')

    def test_connectors_seeded(self):
        types = {c['Type'] for c in MemoryStore().list_connectors()}
        self.assertTrue({'outlook', 'teams', 'slack', 'github', 'anthropic', 'openai', 'azure_openai'} <= types)


class LightModelTests(unittest.TestCase):
    def test_the_cli_brain_downshifts_to_the_light_model(self):
        """One brain, two gears: triage/drafts/summaries run the agent's light_model; the main
        model stays reserved for coding sessions (agent_argv, untouched here)."""
        import json
        from unittest import mock
        from taskuary.store import MemoryStore
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli',
                       json.dumps({'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}))
        seen = {}
        def fake_run_cli(prof, prompt, trace, resume=None):
            seen.update(prof); return ('{"intent":"fyi","why":"x"}', None, None)
        with mock.patch('taskuary.agents.run_cli', fake_run_cli):
            out = llm.make_cli_llm(s, 'coder')('sys', 'user')
        self.assertEqual(seen['model'], 'haiku')                  # the cheap gear reads the mail
        self.assertIn('fyi', out)
        # codex has no smaller model on a ChatGPT plan - its light gear is reasoning effort
        s.upsert_agent('codex', 'coding', 'cli',
                       json.dumps({'cmd': 'codex', 'args': ['exec'], 'model': 'gpt-5.6-sol', 'light_model': 'effort:low'}))
        with mock.patch('taskuary.agents.run_cli', fake_run_cli):
            llm.make_cli_llm(s, 'codex')('sys', 'user')
        self.assertEqual(seen['model'], 'gpt-5.6-sol')            # the model is untouched...
        self.assertIn('model_reasoning_effort=low', ' '.join(seen['args']))   # ...the effort drops
        # and the coding session still gets the big one
        from taskuary.terminal import agent_argv
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']):
            self.assertIn('opus', agent_argv(json.loads(s.get_agent('coder')['Config'])))


class DocSyncTests(unittest.TestCase):
    def test_sync_connections_fills_marker_block(self):
        s = MemoryStore()
        gh = next(c for c in s.list_connectors() if c['Type'] == 'github')
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'github', 'Address': 'you/repo', 'ConnectorId': gh['ConnectorId'], 'Active': 1}, 'o')
        s.save_source({'Channel': 'report', 'Address': 'Census', 'Active': 1,
                       'ConfigJson': '{"type": "mssql", "title": "Census", "every_minutes": 30}'}, 'o')
        docsync.sync_connections(s)
        soul = s.get_doc('soul')
        self.assertIn('GitHub: you/repo', soul)
        self.assertIn('Report "Census" (mssql, every 30m)', soul)
        # prose outside the markers untouched
        self.assertIn('John Smith', soul)

    def test_update_repo_map_preserves_notes(self):
        s = MemoryStore()
        docsync.update_repo_map(s, [{'full_name': 'o/one', 'description': 'the app', 'archived': False}])
        s.save_doc('soul', s.get_doc('soul').replace('**o/one**: the app', '**o/one**: MY NOTE'), 'owner')
        docsync.update_repo_map(s, [{'full_name': 'o/one', 'description': 'the app', 'archived': False},
                                    {'full_name': 'o/two', 'description': None, 'archived': True}])
        soul = s.get_doc('soul')
        self.assertIn('MY NOTE', soul)                       # hand edit preserved
        self.assertEqual(soul.count('o/one'), 1)             # no duplicate line
        self.assertIn('**o/two**', soul); self.assertIn('archived - do not touch', soul)

    def test_repo_map_summarizes_readme_and_heals_placeholders(self):
        from unittest import mock
        s = MemoryStore()
        # first discovery with no token: placeholder line
        docsync.update_repo_map(s, [{'full_name': 'o/app', 'description': None, 'archived': False}])
        self.assertIn('fill me in', s.get_doc('soul'))
        # re-discovery with a token + AI: README summarized, placeholder healed in place
        with mock.patch('taskuary.github.readme_text', return_value='# App\n\nPayroll importer for the ledger.'):
            docsync.update_repo_map(s, [{'full_name': 'o/app', 'description': None, 'archived': False}],
                                    tok='t', llm=lambda sys_, usr: 'Payroll importer for the ledger.')
        soul = s.get_doc('soul')
        self.assertNotIn('fill me in', soul)
        self.assertIn('**o/app**: Payroll importer for the ledger.', soul)
        self.assertEqual(soul.count('o/app'), 1)


class LocalAndOpenRouterTests(unittest.TestCase):
    class _R:
        status_code, text = 200, ''
        def json(self): return {'choices': [{'message': {'content': '{"intent":"fyi","why":"x"}'}}]}

    def test_ollama_speaks_openai_surface_without_a_key(self):
        s = MemoryStore()
        ol = next(c for c in s.list_connectors() if c['Type'] == 'ollama')
        s.save_connector({'ConnectorId': ol['ConnectorId'], 'Active': 1, 'ConfigJson': '{"model": "llama3.2"}'}, 'o')
        seen = {}
        def fake_post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, headers=headers, body=json, timeout=timeout); return self._R()
        with mock.patch('taskuary.llm.requests.post', fake_post):
            out = llm.build_llm(s)('sys', 'user')                # picked with NO key saved
        self.assertIn('fyi', out)
        self.assertEqual(seen['url'], 'http://127.0.0.1:11434/v1/chat/completions')
        self.assertNotIn('Authorization', seen['headers'])
        self.assertEqual(seen['body']['model'], 'llama3.2')
        self.assertEqual(seen['timeout'], 180)                   # room for a cold model load
        # base_url reaches any OpenAI-compatible local server - LM Studio, llama.cpp, vLLM
        s.save_connector({'ConnectorId': ol['ConnectorId'],
                          'ConfigJson': '{"model": "m", "base_url": "http://127.0.0.1:1234/"}'}, 'o')
        with mock.patch('taskuary.llm.requests.post', fake_post): llm.build_llm(s)('sys', 'u')
        self.assertEqual(seen['url'], 'http://127.0.0.1:1234/v1/chat/completions')
        # a model is required - only `ollama list` knows what is installed
        s.save_connector({'ConnectorId': ol['ConnectorId'], 'ConfigJson': '{}'}, 'o')
        with self.assertRaises(RuntimeError): llm.build_llm(s)

    def test_openrouter_is_one_key_over_the_openai_schema(self):
        s = MemoryStore()
        orc = next(c for c in s.list_connectors() if c['Type'] == 'openrouter')
        s.save_connector({'ConnectorId': orc['ConnectorId'], 'Active': 1, 'Secret': 'sk-or-x', 'ConfigJson': '{}'}, 'o')
        seen = {}
        def fake_post(url, headers=None, json=None, timeout=None):
            seen.update(url=url, headers=headers, body=json); return self._R()
        with mock.patch('taskuary.llm.requests.post', fake_post):
            llm.build_llm(s)('sys', 'user')
        self.assertEqual(seen['url'], 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(seen['headers']['Authorization'], 'Bearer sk-or-x')
        self.assertEqual(seen['body']['model'], 'openrouter/auto')       # empty model box still works
        # a catalog model rides through as-is, and `triage_ai` can name this brain explicitly
        s.save_connector({'ConnectorId': orc['ConnectorId'], 'ConfigJson': '{"model": "meta-llama/llama-3.3-70b-instruct"}'}, 'o')
        ol = next(c for c in s.list_connectors() if c['Type'] == 'ollama')
        s.save_connector({'ConnectorId': ol['ConnectorId'], 'Active': 1, 'ConfigJson': '{"model": "llama3.2"}'}, 'o')
        s.set_setting('triage_ai', 'connector:openrouter', 'o')
        with mock.patch('taskuary.llm.requests.post', fake_post): llm.build_llm(s)('sys', 'u')
        self.assertEqual(seen['url'], 'https://openrouter.ai/api/v1/chat/completions')
        self.assertEqual(seen['body']['model'], 'meta-llama/llama-3.3-70b-instruct')
        # no key = not a brain (unlike ollama, the router really needs one)
        self.assertRaises(RuntimeError, llm.make_llm, 'openrouter', {}, None)


class LearnTests(unittest.TestCase):
    def test_learned_seeded_and_injectable_strips_gated_sections(self):
        s = MemoryStore()
        doc = s.get_doc('learned')
        self.assertIn(learn.HYP_START, doc); self.assertIn(learn.PROP_START, doc)
        inj = learn.injectable(doc)
        self.assertIn('Voice & style', inj)                     # active sections travel...
        self.assertNotIn('hypotheses:start', inj)               # ...the gated ones never do
        self.assertNotIn('Proposed rules', inj)
        self.assertNotIn('still being tested', inj)

    def test_learn_from_updates_hypotheses_and_guards_garbage(self):
        s = MemoryStore()
        bullet = '- {{owner_first}} prefers replies without pleasantries. [s:2 | ev: rv7 | seen: 2026-08-21]'
        learn.learn_from(s, 'rv7: owner EDITED a draft', llm=lambda sys_, usr, **kw: bullet)
        doc = s.get_doc('learned')
        self.assertIn(bullet, doc.split(learn.HYP_START, 1)[1])  # landed inside the gated block
        self.assertNotIn(bullet, learn.injectable(doc))          # a hypothesis is never injected
        self.assertEqual(s.get_settings().get('learn_pending'), '1')
        # a broken answer (a marker inside it would corrupt the splice) never lands in the doc
        learn.learn_from(s, 'rv8: x', llm=lambda sys_, usr, **kw: f'junk {learn.HYP_END} junk')
        self.assertEqual(s.get_doc('learned'), doc)
        self.assertEqual(s.get_settings().get('learn_pending'), '2')   # the counter still ticks
        # the off switch really is off: no write, no tick
        s.set_setting('learn_enabled', '0', 't')
        learn.learn_from(s, 'rv9: x', llm=lambda sys_, usr, **kw: '- x. [s:2 | ev: rv9 | seen: y]')
        self.assertEqual(s.get_doc('learned'), doc)
        self.assertEqual(s.get_settings().get('learn_pending'), '2')

    def test_reflect_rewrites_whole_doc_and_rejects_bad_output(self):
        s = MemoryStore()
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertFalse(learn.reflect(s))                   # no brain: the old doc always stands
        good = s.get_doc('learned').replace(
            '## Voice & style', '## Voice & style\n- Short replies, no filler. [s:4 | ev: rv1,rv2,rv3 | seen: 2026-08-20]')
        self.assertTrue(learn.reflect(s, llm=lambda sys_, usr, **kw: good))
        self.assertIn('Short replies, no filler', learn.injectable(s.get_doc('learned')))   # promoted = injected
        self.assertEqual(s.get_settings().get('learn_pending'), '0')
        self.assertTrue(s.get_settings().get('learn_last_reflect'))
        # an unusable rewrite (markers lost) is refused, whole cloth
        self.assertFalse(learn.reflect(s, llm=lambda sys_, usr, **kw: '# LEARNED.md\nno markers here'))
        self.assertIn('Short replies, no filler', s.get_doc('learned'))

    def test_reflect_if_due_debounce(self):
        s = MemoryStore()
        self.assertFalse(learn.reflect_if_due(s))                # nothing pending: silence
        from datetime import datetime
        s.set_setting('learn_pending', '1', 't')
        s.set_setting('learn_last_reflect', datetime.now().isoformat(sep=' '), 't')
        self.assertFalse(learn.reflect_if_due(s))                # one lesson, already reflected today
        s.set_setting('learn_last_reflect', '2020-01-01 00:00:00', 't')
        good = s.get_doc('learned')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda sys_, usr, **kw: good):
            self.assertTrue(learn.reflect_if_due(s))             # one lesson + a stale day: due
        s.set_setting('learn_pending', str(learn.REFLECT_AT), 't')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda sys_, usr, **kw: good):
            self.assertTrue(learn.reflect_if_due(s))             # threshold: due same-day too

    def test_triage_and_ingest_read_the_learned_profile(self):
        from taskuary.triage import classify_intent
        seen = {}
        def fake(sys_, usr, **kw): seen['sys'] = sys_; return '{"intent":"fyi","why":"x"}'
        classify_intent({'subject': 's', 'body': 'b'}, llm=fake, soul='THE SOUL',
                        learned='- Vendor invoices are FYI, never tasks.')
        self.assertIn('Vendor invoices are FYI', seen['sys'])
        self.assertLess(seen['sys'].index('THE SOUL'), seen['sys'].index('Vendor'))   # soul outranks, so it leads
        # and the live path wires the doc in: a promoted line reaches the triage system prompt
        s = MemoryStore()
        s.save_doc('learned', s.get_doc('learned').replace(
            '## What becomes a task', '## What becomes a task\n- Vendor invoices are FYI, never tasks. [s:5 | ev: rv1,rv2,rv3 | seen: 2026-08-01]'), 'reflect')
        from taskuary.ingest import ingest_message
        seen.clear()
        ingest_message(s, {'external_id': 'lrn-1', 'channel': 'email', 'from_email': 'ap@vendor.example',
                           'subject': 'Invoice 42', 'body': 'Attached is the invoice, can you confirm?'}, llm=fake)
        self.assertIn('Vendor invoices are FYI', seen['sys'])
        self.assertNotIn('still being tested', seen['sys'])      # gated sections stay home


class GraphCredsTests(unittest.TestCase):
    def test_teams_borrows_outlook_creds(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        o = next(c for c in s.list_connectors() if c['Type'] == 'outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Secret': 'graph-secret',
                          'ConfigJson': '{"tenant_id": "t1", "client_id": "c1"}'}, 'o')
        t = s.get_connector_by_type('teams', with_secret=True)
        cfg, sec, borrowed = graph_creds(s, t)
        self.assertEqual((cfg['tenant_id'], cfg['client_id'], sec, borrowed), ('t1', 'c1', 'graph-secret', True))

    def test_teams_own_creds_win(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        o = next(c for c in s.list_connectors() if c['Type'] == 'outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Secret': 'osec', 'ConfigJson': '{"client_id": "oc"}'}, 'o')
        t = next(c for c in s.list_connectors() if c['Type'] == 'teams')
        s.save_connector({'ConnectorId': t['ConnectorId'], 'Secret': 'tsec', 'ConfigJson': '{"client_id": "tc", "tenant_id": "tt"}'}, 'o')
        cfg, sec, borrowed = graph_creds(s, s.get_connector_by_type('teams', with_secret=True))
        self.assertEqual((cfg['client_id'], sec, borrowed), ('tc', 'tsec', False))

    def test_outlook_never_borrows(self):
        from taskuary.channels import graph_creds
        s = MemoryStore()
        cfg, sec, borrowed = graph_creds(s, s.get_connector_by_type('outlook', with_secret=True))
        self.assertEqual((sec, borrowed), (None, False))


class OutboundMailTests(unittest.TestCase):
    def _sent(self, conv=None, i='sm1'):
        return {'id': i, 'subject': 'RE: Financial Request', 'conversationId': conv,
                'bodyPreview': 'March thru June attached.', 'sentDateTime': '2026-08-17T15:00:00Z'}

    def test_sent_mail_without_chain_is_skipped(self):
        from taskuary.channels import ingest_outbound_mail
        s = MemoryStore()
        self.assertEqual(ingest_outbound_mail(s, 'me@x.com', self._sent()), 0)
        self.assertEqual(s.feed(), []); self.assertEqual(s.list_tasks(), [])

    def test_sent_mail_attaches_to_conversation_task(self):
        from taskuary.channels import ingest_outbound_mail
        from taskuary.ingest import ingest_message
        s = MemoryStore()
        out = ingest_message(s, {'external_id': 'in1', 'channel': 'email', 'subject': 'Financial Request',
                                 'body': 'please send March thru June', 'from_email': 'client@y.com',
                                 'conversation_id': 'c9', 'sent_at': '2026-08-17 14:00', 'from_name': 'Client'},
                             llm=lambda a, b: '{"intent": "task", "why": "t"}')
        ingest_outbound_mail(s, 'me@x.com', self._sent(conv='c9', i='sm2'))
        msgs = s.list_messages(out['task_id'])
        self.assertEqual(len(msgs), 2)                       # both sides on the thread
        self.assertEqual({m['FromName'] for m in msgs}, {'Client', 'You'})
        self.assertEqual(len(s.list_tasks()), 1)             # no new task from the reply
        # the reply is IN the chain, not a separate timeline row
        self.assertEqual(len(s.feed()), 1)
        self.assertTrue(any('You replied' in c['Body'] for c in s.list_comments(out['task_id'])))
        # dedup on the next poll
        self.assertEqual(ingest_outbound_mail(s, 'me@x.com', self._sent(conv='c9', i='sm2')), 0)

    def test_full_body_beats_the_255_char_preview(self):
        from taskuary.channels import _body
        long_html = '<html><body>' + ('the actual mail body. ' * 60) + '</body></html>'
        m = {'bodyPreview': 'the actual mail body. ' * 11, 'body': {'contentType': 'html', 'content': long_html}}
        self.assertGreater(len(_body(m)), 1000)                       # not truncated to the preview
        self.assertNotIn('<', _body(m))                               # html stripped
        self.assertEqual(_body({'bodyPreview': 'only a preview'}), 'only a preview')
        self.assertEqual(_body({}), '')

    def test_ai_failure_files_instead_of_task(self):
        from taskuary.ingest import ingest_message
        def boom(a, b): raise RuntimeError('azure 400: max_tokens')
        s = MemoryStore()
        out = ingest_message(s, {'external_id': 'e1', 'channel': 'email', 'subject': 'please fix the report',
                                 'body': 'please fix the report', 'from_email': 'a@b.com', 'sent_at': '2026-08-17 14:00'},
                             llm=boom)
        self.assertEqual((out['status'], out['task_id']), ('filed', None))
        self.assertIn('AI triage failed', s.feed()[0]['RouteReason'])


class LlmTests(unittest.TestCase):
    def test_build_llm_none_without_active_key(self):
        self.assertIsNone(llm.build_llm(MemoryStore()))

    def test_build_llm_picks_first_active_with_key(self):
        s = MemoryStore()
        oa = next(c for c in s.list_connectors() if c['Type'] == 'openai')
        s.save_connector({'ConnectorId': oa['ConnectorId'], 'Active': 1, 'Secret': 'sk-x',
                          'ConfigJson': '{"model": "gpt-4o-mini"}'}, 'o')
        fn = llm.build_llm(s)
        self.assertTrue(callable(fn))
        with mock.patch('taskuary.llm.requests.post') as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {'choices': [{'message': {'content': '{"intent": "fyi"}'}}]}
            self.assertEqual(fn('sys', 'usr'), '{"intent": "fyi"}')

    def test_azure_tries_v1_then_legacy(self):
        fn = llm.make_llm('azure_openai', {'endpoint': 'https://r.openai.azure.com', 'deployment': 'gpt-5'}, 'k')
        calls = []
        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, [k for k in json if 'tokens' in k][0]))
            r = mock.Mock()
            if '/openai/v1/' in url: r.status_code, r.text = 404, 'not found'
            else: r.status_code = 200; r.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
            return r
        with mock.patch('taskuary.llm.requests.post', side_effect=fake_post):
            self.assertEqual(fn('s', 'u'), 'ok')
        self.assertIn('/openai/v1/chat/completions', calls[0][0])
        self.assertIn('/openai/deployments/gpt-5/', calls[1][0])
        self.assertIn('api-version=2024-12-01-preview', calls[1][0])
        self.assertEqual(calls[1][1], 'max_completion_tokens')

    def test_azure_token_param_fallback(self):
        fn = llm.make_llm('azure_openai', {'endpoint': 'https://r.openai.azure.com', 'deployment': 'd', 'api_version': '2024-06-01'}, 'k')
        def fake_post(url, headers=None, json=None, timeout=None):
            r = mock.Mock()
            if 'max_completion_tokens' in json:
                r.status_code, r.text = 400, "Unrecognized request argument supplied: max_completion_tokens"
            else:
                r.status_code = 200; r.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
            return r
        with mock.patch('taskuary.llm.requests.post', side_effect=fake_post):
            self.assertEqual(fn('s', 'u'), 'ok')

    def test_make_llm_validates(self):
        with self.assertRaises(RuntimeError): llm.make_llm('openai', {}, None)
        with self.assertRaises(RuntimeError): llm.make_llm('azure_openai', {}, 'k')


if __name__ == '__main__':
    unittest.main()

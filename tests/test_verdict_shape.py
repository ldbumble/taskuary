"""The verdict's SHAPE is enforced, not requested (TQ-0665, 2026-09-21).

Triage asks for a title and a summary on every verdict, and a checklist on a task. It asked in
prose, twice: once in the document and once in a block the code appends when the document forgets.
On a long forwarded mail - 8,400 characters, the ask in the first sentence and a chain under it -
the model answered the contract line at the top of the owner's own TRIAGE.md, which named
intent/kind/why and nothing else, and dropped the pair in three of eight replays. The card then
fell back to a cut of the raw body and showed the whole chain as the task.

Three things changed, from the document outwards:

- TRIAGE.md's own contract line names title, summary and checklist, in the shipped template and
  in every install whose document stopped tracking it (one surgical replacement, like the PR rule).
- The shape rides the WIRE where the provider can carry it: `want=` a JSON schema, sent as
  response_format on every OpenAI-shaped brain and as a forced tool call on Anthropic's. A brain
  that rejects it is asked again without it, down the same compat grid the token parameter walks.
- What no schema can reach - a CLI brain is a prompt and a text answer - is checked in code: a
  verdict missing the fields is asked for once more, naming exactly what it left out.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import taskuary
from taskuary import llm as llm_mod, store as store_mod, triage
from taskuary.store import SQLiteStore

TEMPLATE = (Path(taskuary.__file__).parent / 'templates' / 'triage.md').read_text(encoding='utf-8')
MSG = {'subject': 'FW: 2027 Budgets', 'from_email': 'brad@mfa.example',
       'body': 'Uri,\n\nCan you send me the link on the 2027 budgets?\n\nThanks,\n\nBrad'}


class DocumentSaysTheShapeTests(unittest.TestCase):
    """The contract line is the first thing the model reads and it read as the whole schema."""

    def setUp(self): self.path = Path(tempfile.mkdtemp()) / 'taskuary.db'

    def _reopen(self, doc=None):
        s = SQLiteStore(str(self.path))
        if doc is not None: s.save_doc('triage', doc, 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='triage_answer_shape_fixed'")
        s.cx.commit()
        return SQLiteStore(str(self.path))

    def test_the_shipped_contract_line_names_every_field_the_code_reads(self):
        line = next(l for l in TEMPLATE.splitlines() if l.startswith('Classify one inbound work message'))
        for field in ('"title"', '"summary"', '"checklist"'):
            self.assertIn(field, store_mod._SHAPE_NOW, field)
            self.assertIn(field, line, field)                             # in the contract line itself
        self.assertIn(store_mod._SHAPE_NOW, TEMPLATE)                     # the migration says what the template says
        self.assertNotIn(store_mod._SHAPE_WAS, TEMPLATE)

    def test_a_document_that_stopped_tracking_the_template_gets_the_line_back(self):
        mine = 'MY OWN RULE: anything from Dvora is urgent.\n\n' + store_mod._SHAPE_WAS + '\n\nAnd my last line.'
        after = self._reopen(mine).doc('triage')
        self.assertNotIn(store_mod._SHAPE_WAS, after)
        self.assertIn('"summary"', after)
        self.assertIn('MY OWN RULE: anything from Dvora is urgent.', after)   # nothing else touched
        self.assertIn('And my last line.', after)

    def test_it_runs_once_and_never_edits_a_document_again(self):
        s = self._reopen('plain ' + store_mod._SHAPE_WAS)
        self.assertEqual(s.get_settings().get('triage_answer_shape_fixed'), '1')
        s.save_doc('triage', 'I want it my way: ' + store_mod._SHAPE_WAS, 'owner')
        s.cx.commit()
        self.assertIn(store_mod._SHAPE_WAS, SQLiteStore(str(self.path)).doc('triage'))


class SchemaOnTheWireTests(unittest.TestCase):
    """What the provider can enforce, the provider enforces."""

    def _posts(self, status_by_body=None):
        """A fake provider that records every request and answers per the response_format sent."""
        posts = []
        def post(url, headers, body, timeout):
            posts.append(body)
            code = (status_by_body or (lambda b: 200))(body)
            r = mock.Mock(status_code=code, text='response_format.type: json_schema is not supported')
            r.json.return_value = {'choices': [{'message': {'content': '{"intent": "fyi"}'}}]}
            return r
        return posts, post

    def test_an_openai_shaped_brain_sends_the_schema_as_response_format(self):
        posts, post = self._posts()
        with mock.patch.object(llm_mod, 'post_retrying', side_effect=post):
            brain = llm_mod.make_llm('openai', {'model': 'gpt-5.4'}, 'k')
            self.assertTrue(brain.takes_want)                       # the caller can see it can carry one
            brain('sys', 'usr', want={'name': 'v', 'schema': {'type': 'object'}})
        self.assertEqual(posts[0]['response_format']['type'], 'json_schema')
        self.assertEqual(posts[0]['response_format']['json_schema']['name'], 'v')

    def test_a_brain_that_rejects_the_schema_is_asked_again_without_it(self):
        """Older models and some OpenRouter routes 400 on response_format. A verdict must not be
        lost over a wire feature - the prose contract and the recheck still stand behind it."""
        posts, post = self._posts(lambda b: 400 if 'response_format' in b else 200)
        with mock.patch.object(llm_mod, 'post_retrying', side_effect=post):
            out = llm_mod.make_llm('openai', {'model': 'old'}, 'k')('sys', 'usr', want={'name': 'v', 'schema': {}})
        self.assertEqual(out, '{"intent": "fyi"}')
        self.assertNotIn('response_format', posts[-1])
        self.assertTrue(any('response_format' in p for p in posts))       # it did try

    def test_a_cli_brain_takes_the_argument_and_ignores_it(self):
        """A CLI is a prompt in and text out; there is nothing to enforce with. It must still not
        blow up on the keyword, or triage could not pass one at all."""
        from taskuary.store import MemoryStore
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        brain = llm_mod.make_cli_llm(s, 'coder')
        self.assertIs(brain.takes_want, False)          # said out loud: it is the one worth rechecking
        with mock.patch('taskuary.agents.run_cli', return_value=('{"intent": "fyi"}', None, None)):
            self.assertEqual(brain('sys', 'usr', want={'name': 'v'}), '{"intent": "fyi"}')


class AskJsonTests(unittest.TestCase):
    """One door for "a JSON answer of this shape", so the other callers can follow later."""

    def test_a_brain_that_cannot_take_a_schema_is_never_handed_one(self):
        seen = {}
        def fake(system, user, images=None):          # a fixed signature, like every test fake
            seen['called'] = True
            return '{"intent": "fyi", "title": "t", "summary": "s"}'
        out = llm_mod.ask_json(fake, 'sys', 'usr', want={'name': 'v'}, need=('title', 'summary'))
        self.assertTrue(seen['called'])
        self.assertEqual(out.data['title'], 't')

    def test_a_missing_field_is_asked_for_once_more_naming_it(self):
        asks = []
        def brain(system, user, **kw):
            asks.append(user)
            return ('{"intent": "fyi", "why": "a newsletter"}' if len(asks) == 1
                    else '{"intent": "fyi", "why": "a newsletter", "title": "October newsletter", "summary": "Vendor news."}')
        brain.takes_want = False                      # a CLI: no wire to put a schema on
        out = llm_mod.ask_json(brain, 'sys', 'usr', need=('title', 'summary'))
        self.assertEqual(len(asks), 2)
        self.assertIn('title', asks[1]); self.assertIn('summary', asks[1])
        self.assertEqual(out.data['title'], 'October newsletter')

    def test_it_gives_up_after_one_retry_and_returns_what_it_got(self):
        """Never a loop against a model that cannot comply: the fallback downstream is what a
        missing field always meant, and a second failure is not worth a third call."""
        asks = []
        def brain(system, user, **kw):
            asks.append(user); return '{"intent": "fyi", "why": "x"}'
        brain.takes_want = False
        out = llm_mod.ask_json(brain, 'sys', 'usr', need=('title', 'summary'))
        self.assertEqual(len(asks), 2)
        self.assertEqual(out.data['intent'], 'fyi')       # the judgement it DID make is not thrown away
        self.assertNotIn('title', out.data)
        self.assertIn('"intent": "fyi"', out.raw)         # ...and what it actually said is kept for the Triage tab


class TriageUsesItTests(unittest.TestCase):
    def test_the_verdict_schema_asks_only_for_what_the_prompt_explained(self):
        """The probe answered `relationship` and `repo_reason` on a mail that was neither - a
        schema wider than the prompt invents fields nobody described."""
        plain = triage.verdict_schema()
        self.assertEqual(set(plain['schema']['required']), set(plain['schema']['properties']))   # strict mode's rule
        self.assertFalse(plain['schema']['additionalProperties'])
        for asked in ('intent', 'why', 'title', 'summary', 'kind', 'checklist'):
            self.assertIn(asked, plain['schema']['properties'], asked)
        for unasked in ('repository', 'relationship', 'playbook', 'profile'):
            self.assertNotIn(unasked, plain['schema']['properties'], unasked)
        with_repos = triage.verdict_schema(repos=[{'repo': 'a/b'}], candidates=[], playbooks='- pto: x', profiles='- analyst: x')
        for asked in ('repository', 'needs_repo_choice', 'repo_reason', 'relationship', 'related_message_ids',
                      'existing_task_id', 'playbook', 'profile'):
            self.assertIn(asked, with_repos['schema']['properties'], asked)

    def test_classify_hands_the_schema_to_a_brain_that_can_carry_one_and_asks_once(self):
        """The provider is enforcing it, so a second call would buy nothing and cost the owner."""
        seen, asks = {}, []
        def brain(system, user, **kw):
            seen['want'] = kw.get('want'); asks.append(user)
            return ('{"intent": "reply_only", "why": "Brad asks for the link", "title": "Send Brad the budgets link",'
                    ' "summary": "Brad asked for the link to the 2027 budgets."}')
        brain.takes_want = True
        out = triage.classify_intent(MSG, llm=brain, system='My own rules. Answer JSON only.')
        self.assertEqual(seen['want']['name'], 'triage_verdict')
        self.assertEqual(seen['want']['schema']['properties']['intent']['enum'], ['task', 'reply_only', 'fyi'])
        self.assertEqual(out['title'], 'Send Brad the budgets link')
        self.assertEqual(len(asks), 1)

    def test_classify_asks_a_cli_brain_again_for_the_fields_it_left_out(self):
        """No wire to put a schema on, so this is the only layer left - and the one call it costs
        is spent where we know nothing enforced the shape."""
        asks = []
        def brain(system, user, **kw):
            asks.append(user)
            self.assertNotIn('want', kw)                               # never handed one it cannot use
            return ('{"intent": "reply_only", "why": "Brad asks for the link"}' if len(asks) == 1
                    else '{"intent": "reply_only", "why": "Brad asks for the link", "title": "Send Brad the budgets link",'
                         ' "summary": "Brad asked for the link to the 2027 budgets."}')
        brain.takes_want = False
        out = triage.classify_intent(MSG, llm=brain, system='My own rules. Answer JSON only.')
        self.assertEqual(len(asks), 2)
        self.assertIn('title', asks[1]); self.assertIn('summary', asks[1])
        self.assertEqual(out['title'], 'Send Brad the budgets link')

    def test_the_wrapper_ingest_puts_round_the_brain_still_carries_a_schema(self):
        """judge() wraps the brain to catch its errors. The wrapper was a plain function, so the
        classifier could not tell that a schema would be honoured and sent none - and nothing in
        the app said so: the verdict came back fine, on the prose alone. Only the wire answered it."""
        from taskuary import ingest
        from taskuary.store import MemoryStore
        brain = mock.Mock(return_value='{"intent": "fyi", "why": "x", "title": "t", "summary": "s"}')
        brain.takes_want = True
        ingest.judge(MemoryStore(), {'channel': 'email', 'from_email': 'a@b.example', 'subject': 's',
                                     'body': 'hello', 'conversation_id': 'c'}, brain)
        self.assertEqual(brain.call_args.kwargs['want']['name'], 'triage_verdict')

    def test_a_verdict_that_still_names_nothing_is_a_verdict_not_a_failure(self):
        """The fallback is what it always was. A model that will not answer the shape must not
        cost the owner the judgement it DID make."""
        brain = mock.Mock(return_value='{"intent": "fyi", "why": "a newsletter"}')
        out = triage.classify_intent(MSG, llm=brain, system='My own rules. Answer JSON only.')
        self.assertEqual(out['intent'], 'fyi')
        self.assertFalse(out.get('degraded'))
        self.assertNotIn('title', out)


if __name__ == '__main__':
    unittest.main()

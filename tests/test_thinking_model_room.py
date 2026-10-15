"""A connected Vertex AI (Gemini 2.5 Flash) passed its Test and then sorted no mail: "Sorting 18 emails..." for good (the owner,
2026-10-15). Triage asked for 400 tokens, a thinking model spends its budget thinking, and the answer came back empty - which the
call read as "the format was refused", asked again, and then failed with no reason at all. An answer cut off at the limit is asked
again with room; an empty one says so; triage asks for room a thinking model can answer in; and setup says when the AI is failing."""
import json, unittest
from unittest import mock

from taskuary import firstrun, llm, triage
from taskuary.store import MemoryStore

CFG = {'project': 'northwind-ai', 'location': 'global', 'model': 'gemini-2.5-flash'}


def reply(content, finish='stop', status=200):
    r = mock.Mock(status_code=status, text=json.dumps({'choices': [{'message': {'content': content}, 'finish_reason': finish}]}))
    r.json.return_value = json.loads(r.text)
    return r


class RoomTests(unittest.TestCase):
    def test_an_answer_cut_off_by_the_limit_is_asked_again_with_room(self):
        sent = []
        def post(url, headers, body, timeout):
            sent.append(body.get('max_completion_tokens') or body.get('max_tokens'))
            return reply(None, 'length') if len(sent) == 1 else reply('{"intent": "fyi"}')
        with mock.patch.object(llm, 'post_retrying', side_effect=post):
            out = llm.make_llm('vertex_ai', CFG, 'key')('sys', 'user', max_tokens=400)
        self.assertEqual(out, '{"intent": "fyi"}')
        self.assertGreater(sent[1], sent[0] * 3)

    def test_an_empty_answer_fails_saying_so_never_a_blank_error(self):
        with mock.patch.object(llm, 'post_retrying', return_value=reply(None, 'length')):
            with self.assertRaises(RuntimeError) as e: llm.make_llm('vertex_ai', CFG, 'key')('sys', 'user')
        self.assertIn('ran out of room', str(e.exception))

    def test_triage_asks_for_room_a_thinking_model_can_answer_in(self):
        def brain(system, user, **kw): brain.kw = kw; return '{"intent": "fyi", "why": "x"}'
        triage.classify_intent({'from_email': 'erin@northwind.example', 'subject': 'Hi', 'body': 'x'}, llm=brain)
        self.assertGreaterEqual(brain.kw.get('max_tokens', 0), 2000)


class SetupSaysTests(unittest.TestCase):
    def test_reading_with_a_failing_ai_says_why_and_how_to_change_it(self):
        s = MemoryStore()
        with mock.patch.object(firstrun, '_sorting', return_value=18), \
             mock.patch('taskuary.setup._ai', return_value={'ready': True, 'name': 'Google Vertex AI'}), \
             mock.patch('taskuary.setup._inbound', return_value=True), mock.patch('taskuary.setup._first_items', return_value=[]):
            s.set_setting('triage_ai', 'connector:110', 'owner')
            s.set_setting('triage_last_error', 'vertex_ai error 429: quota exceeded', 'system')
            st = firstrun.state(s)
        self.assertEqual(st['step'], 'reading')
        self.assertIn('quota exceeded', st['next']); self.assertIn('Change', st['next'])
        self.assertEqual(st['ai_error'], 'vertex_ai error 429: quota exceeded')


if __name__ == '__main__': unittest.main()

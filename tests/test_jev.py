"""TypeSafe's Jev: unstructured state in, typed answers with calibrated probabilities out.

It emits no text at all, which is exactly why it can be a routing judge and can never be a brain.
This module owns the one HTTP call so reports.py never learns it.
"""
import unittest
from unittest import mock

from taskuary import jev


class TheCallTests(unittest.TestCase):
    def _reply(self, answers, status=200):
        r = mock.Mock(status_code=status)
        r.json.return_value = {'model': 'jev-latest', 'answers': answers, 'usage': {}}
        r.text = ''
        return r

    def test_one_call_carries_every_question(self):
        """N lines, one round trip - the whole reason this model suits the judge."""
        reply = self._reply({'work': {'type': 'noul', 'noul': 0.92},
                             'timeline': {'type': 'noul', 'noul': 0.10}})
        with mock.patch('taskuary.llm.post_retrying', return_value=reply) as post:
            out = jev.ask('sk-x', 'the run said 0 rows',
                          {'work': ('put it on the work rail', 'a job has not run in over two hours'),
                           'timeline': ('post it on the timeline', 'anything worth reading')})
        self.assertEqual(post.call_count, 1)
        url, headers, body, _timeout = post.call_args[0]
        self.assertEqual(url, jev.API)
        self.assertEqual(headers['Authorization'], 'Bearer sk-x')
        self.assertEqual(body['model'], 'jev-latest')
        self.assertEqual(body['state'], 'the run said 0 rows')
        self.assertEqual(body['questions']['work']['type'], 'noul')
        self.assertEqual(body['questions']['work']['instructions'], 'put it on the work rail')
        self.assertEqual(body['questions']['work']['criteria']['true'], 'a job has not run in over two hours')
        self.assertEqual(out, {'work': (True, 0.92), 'timeline': (False, 0.10)})

    def test_the_threshold_is_half_and_it_is_not_a_setting(self):
        reply = self._reply({'a': {'noul': 0.5}, 'b': {'noul': 0.49}})
        with mock.patch('taskuary.llm.post_retrying', return_value=reply):
            out = jev.ask('sk-x', 's', {'a': ('i', 'c'), 'b': ('i', 'c')})
        self.assertEqual(out['a'][0], True)
        self.assertEqual(out['b'][0], False)

    def test_a_refused_key_raises_rather_than_answering(self):
        """The caller turns a failure into 'unjudged', which reaches the owner. Swallowing it here
        would invent an answer nobody gave."""
        bad = mock.Mock(status_code=401, text='{"error":"invalid api key"}')
        with mock.patch('taskuary.llm.post_retrying', return_value=bad):
            with self.assertRaises(RuntimeError) as e:
                jev.ask('sk-bad', 's', {'a': ('i', 'c')})
        self.assertIn('401', str(e.exception))

    def test_an_endpoint_that_stayed_down_says_it_was_ridden_out(self):
        """529 is the endpoint's own problem, so the row says we tried rather than that we gave up."""
        down = mock.Mock(status_code=503, text='upstream unavailable')
        with mock.patch('taskuary.llm.post_retrying', return_value=down):
            with self.assertRaises(RuntimeError) as e:
                jev.ask('sk-x', 's', {'a': ('i', 'c')})
        self.assertIn('tries', str(e.exception))

    def test_a_missing_answer_raises_rather_than_guessing(self):
        reply = self._reply({'work': {'noul': 0.9}})
        with mock.patch('taskuary.llm.post_retrying', return_value=reply):
            with self.assertRaises(RuntimeError):
                jev.ask('sk-x', 's', {'work': ('i', 'c'), 'alert': ('i', 'c')})

    def test_no_key_is_a_failure_before_anybody_is_called(self):
        with mock.patch('taskuary.llm.post_retrying') as post:
            with self.assertRaises(RuntimeError):
                jev.ask('', 's', {'a': ('i', 'c')})
        post.assert_not_called()

    def test_no_questions_is_no_call(self):
        with mock.patch('taskuary.llm.post_retrying') as post:
            self.assertEqual(jev.ask('sk-x', 's', {}), {})
        post.assert_not_called()


class ItIsNotABrainTests(unittest.TestCase):
    """The load-bearing omission. AI_TYPES is what populates every brain picker, and a decision
    model chosen as the Assistant's brain would have nothing to say."""

    def test_typesafe_is_not_an_ai_type(self):
        from taskuary import llm
        self.assertNotIn('typesafe', llm.AI_TYPES)

    def test_the_card_exists_so_a_key_can_be_saved(self):
        from taskuary.store import MemoryStore
        self.assertTrue(MemoryStore().get_connector_by_type('typesafe'), 'no TypeSafe card to paste a key into')

    def test_it_never_reaches_the_brain_pickers(self):
        """The test that stops the assistant going mute."""
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        cid = server.store.get_connector_by_type('typesafe')['ConnectorId']
        was = server.store.get_connector(cid)
        try:
            server.store.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
            values = [str(b.get('value') or '') for b in c.get('/api/brains').json()['data']]
            self.assertFalse([v for v in values if str(cid) in v],
                             f'the decision model is offered as a brain: {values}')
        finally:
            server.store.save_connector({'ConnectorId': cid, 'Secret': '',
                                         'Active': int(was['Active'] or 0)}, 't')

    def test_its_test_button_asks_jev_a_question_instead_of_for_a_completion(self):
        """A card that tests green through the wrong road is the exact failure the wizard exists to
        prevent: llm.test_ai asks for a completion, and this model has none to give."""
        from taskuary import channels
        from taskuary.store import MemoryStore
        s = MemoryStore()
        cid = s.get_connector_by_type('typesafe')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-x', 'Active': 1}, 't')
        with mock.patch('taskuary.jev.ask', return_value={'ok': (True, 0.83)}) as ask:
            with mock.patch('taskuary.llm.test_ai', side_effect=AssertionError('no completion may be asked for')):
                out = channels.test_connector(s, cid)
        self.assertTrue(out['ok'], out)
        self.assertEqual(ask.call_args[0][0], 'sk-x')
        self.assertIn('0.83', out['detail'])


if __name__ == '__main__':
    unittest.main()

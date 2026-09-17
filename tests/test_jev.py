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


if __name__ == '__main__':
    unittest.main()

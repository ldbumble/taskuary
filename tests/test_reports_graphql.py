"""The GraphQL report executor, offline: what it posts, where it walks, and what it refuses.

No network and no credentials - like every other test here, the endpoint is a mock and the
only thing under test is the shape this executor hands back to the timeline.
"""
import unittest
from unittest import mock

from taskuary import webguard
from taskuary.reports import REGISTRY

URL = 'https://api.example.com/graphql'


def _response(payload, status_code=200, is_redirect=False):
    r = mock.Mock(status_code=status_code, is_redirect=is_redirect)
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


class GraphQLTests(unittest.TestCase):
    def _run(self, payload, cfg=None):
        r = _response(payload)
        with mock.patch.object(webguard, 'check_url') as check, \
             mock.patch('requests.post', return_value=r) as post:
            head, body = REGISTRY['graphql']({'url': URL, 'query': 'query { viewer { name } }',
                                             **(cfg or {})})
        return head, body, check, post

    def test_posts_the_query_and_walks_the_path(self):
        head, body, check, post = self._run(
            {'data': {'viewer': {'reports': [{'id': 1}, {'id': 2}]}}}, {'path': 'viewer.reports'})
        self.assertEqual(head, '2 items')
        self.assertIn('"id": 2', body)
        check.assert_called_once_with(URL)
        self.assertEqual(post.call_args.kwargs['json'], {'query': 'query { viewer { name } }'})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.kwargs['timeout'], 30)

    def test_headers_are_forwarded(self):
        _, _, _, post = self._run({'data': {'ok': True}}, {'headers': {'Authorization': 'Bearer t'}})
        self.assertEqual(post.call_args.kwargs['headers'], {'Authorization': 'Bearer t'})

    def test_a_graphql_error_fails_loudly(self):
        """GraphQL reports failures in a 200 body - 'ok' with no rows is the silent absence
        PLANNED exists to prevent."""
        with self.assertRaises(RuntimeError) as e:
            self._run({'errors': [{'message': 'field does not exist'}]})
        self.assertIn('field does not exist', str(e.exception))

    def test_a_redirect_is_not_followed(self):
        r = _response({}, status_code=302, is_redirect=True)
        with mock.patch.object(webguard, 'check_url'), mock.patch('requests.post', return_value=r):
            with self.assertRaises(RuntimeError) as e:
                REGISTRY['graphql']({'url': URL, 'query': '{ viewer { name } }'})
        self.assertIn('redirected', str(e.exception))


if __name__ == '__main__':
    unittest.main()

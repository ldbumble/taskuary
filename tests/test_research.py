"""The web as a report source.

All four are plain REST with a key on a card - no browser client, no SDK, nothing new frozen into
the single-exe build. That is the boundary as much as the design: Browserbase and Stagehand DRIVE
a browser (log in, click, fill) over CDP, which cannot be reached from REST at all. What is here
is the other ninety percent of research - search, read a page, get an answer with sources.

Every request shape below was read off the vendor's own reference, not guessed: a wrong field
name here fails at runtime with a 400 nobody sees until a scheduled report comes back empty.
"""
import json
import unittest
from unittest import mock

from taskuary import research
from taskuary.reports import REGISTRY
from taskuary.store import MemoryStore


class _Resp:
    def __init__(self, payload=None, status=200, text=''):
        self._payload, self.status_code, self.text = payload, status, text or json.dumps(payload or {})

    def json(self): return self._payload


class ExaTests(unittest.TestCase):
    HIT = {'results': [{'title': 'A post', 'url': 'https://x.com/a', 'publishedDate': '2026-08-01T00:00:00Z',
                        'text': 'the body of the page'}]}

    def test_it_asks_for_the_page_text_not_just_links(self):
        """A list of URLs is not research, and fetching each one afterwards is the thing this
        connector exists to avoid."""
        with mock.patch.object(research.requests, 'post', return_value=_Resp(self.HIT)) as post:
            head, body = research.run_exa({'api_key': 'k', 'query': 'local-first ai'})
        sent = post.call_args.kwargs['json']
        self.assertIn('text', sent['contents'])
        self.assertEqual(post.call_args.kwargs['headers']['x-api-key'], 'k')   # not Bearer
        self.assertEqual(post.call_args[0][0], 'https://api.exa.ai/search')
        self.assertIn('1 results', head)
        self.assertIn('the body of the page', body)

    def test_the_optional_narrowing_is_passed_in_the_shape_exa_expects(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp(self.HIT)) as post:
            research.run_exa({'api_key': 'k', 'query': 'q', 'num': 3,
                              'domains': 'news.ycombinator.com, lobste.rs', 'since': '2026-01-01'})
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['numResults'], 3)
        self.assertEqual(sent['includeDomains'], ['news.ycombinator.com', 'lobste.rs'])
        self.assertEqual(sent['startPublishedDate'], '2026-01-01')

    def test_no_key_says_which_card_to_go_to(self):
        with self.assertRaises(RuntimeError) as e:
            research.run_exa({'query': 'q'})
        self.assertIn('Connectors', str(e.exception))

    def test_an_http_error_carries_the_providers_own_words(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp(None, 401, 'invalid api key')):
            with self.assertRaises(RuntimeError) as e:
                research.run_exa({'api_key': 'bad', 'query': 'q'})
        self.assertIn('401', str(e.exception))
        self.assertIn('invalid api key', str(e.exception))


class TavilyTests(unittest.TestCase):
    def test_the_answer_leads_and_the_sources_sit_under_it(self):
        """So a claim can be checked rather than taken on faith."""
        payload = {'answer': 'The rule changed in June.',
                   'results': [{'title': 'Source', 'url': 'https://e.eu/1', 'content': 'text', 'score': 0.9}]}
        with mock.patch.object(research.requests, 'post', return_value=_Resp(payload)) as post:
            head, body = research.run_tavily({'api_key': 'tvly-x', 'query': 'eu ai act'})
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer tvly-x')
        self.assertIn('answered', head)
        self.assertTrue(body.startswith('ANSWER: The rule changed in June.'))
        self.assertIn('SOURCES:', body)
        self.assertIn('https://e.eu/1', body)

    def test_without_an_answer_it_is_just_results(self):
        with mock.patch.object(research.requests, 'post',
                               return_value=_Resp({'results': [{'title': 't', 'url': 'u', 'content': 'c'}]})):
            head, body = research.run_tavily({'api_key': 'k', 'query': 'q'})
        self.assertNotIn('answered', head)
        self.assertNotIn('ANSWER:', body)

    def test_max_results_is_clamped_to_what_tavily_accepts(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp({'results': []})) as post:
            research.run_tavily({'api_key': 'k', 'query': 'q', 'num': 500})
        self.assertEqual(post.call_args.kwargs['json']['max_results'], 20)


class PageReadingTests(unittest.TestCase):
    def test_firecrawl_returns_the_markdown_and_titles_the_row(self):
        payload = {'success': True, 'data': {'markdown': '# Pricing\n\n$10', 'metadata': {'title': 'Pricing'}}}
        with mock.patch.object(research.requests, 'post', return_value=_Resp(payload)) as post:
            head, body = research.run_firecrawl({'api_key': 'fc-x', 'url': 'https://e.com/pricing'})
        self.assertEqual(post.call_args[0][0], 'https://api.firecrawl.dev/v2/scrape')
        self.assertEqual(post.call_args.kwargs['json']['formats'], ['markdown'])
        self.assertTrue(post.call_args.kwargs['json']['onlyMainContent'])
        self.assertIn('Pricing', head)
        self.assertIn('$10', body)

    def test_a_page_that_yields_nothing_says_so_rather_than_filing_an_empty_report(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp({'data': {'markdown': ''}})):
            with self.assertRaises(RuntimeError) as e:
                research.run_firecrawl({'api_key': 'k', 'url': 'https://e.com'})
        self.assertIn('no markdown', str(e.exception))

    def test_the_reader_needs_no_key_at_all(self):
        """The one research source a fresh install can try immediately - a research pipeline
        should not need a paid account to read one public page."""
        with mock.patch.object(research.requests, 'get',
                               return_value=_Resp(None, 200, 'Title: Example Domain\n\ntext here')) as get:
            head, body = research.run_reader({'url': 'https://example.com'})
        self.assertEqual(get.call_args.kwargs['headers'], {})      # no Authorization at all
        self.assertIn('Example Domain', head)
        self.assertIn('text here', body)

    def test_a_reader_key_is_used_when_there_is_one(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(None, 200, 'Title: X')) as get:
            research.run_reader({'url': 'https://e.com', 'api_key': 'jina-k'})
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer jina-k')


class WiredInTests(unittest.TestCase):
    def test_all_four_are_report_types(self):
        for t in ('exa', 'tavily', 'firecrawl', 'reader'):
            self.assertIn(t, REGISTRY, f'{t} is not a report source')

    def test_reading_the_web_is_a_read(self):
        from taskuary.scopes import ACTIONS
        for t in ('exa', 'tavily', 'firecrawl', 'reader'):
            self.assertEqual(ACTIONS[t], 'read', f'{t} should not need write authority')

    def test_each_has_a_card_that_can_hold_a_key(self):
        s = MemoryStore()
        for t in ('exa', 'tavily', 'firecrawl', 'reader'):
            self.assertIsNotNone(s.get_connector_by_type(t), f'no {t} card in the catalog')

    def test_the_key_reaches_the_executor_from_the_card(self):
        """resolve_cfg is what turns a saved secret into api_key - without it every research
        report would report "no key saved" while the key sat on the card."""
        from taskuary.reports import resolve_cfg
        s = MemoryStore()
        cid = s.get_connector_by_type('exa')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'sk-exa', 'Active': 1}, 't')
        cfg = resolve_cfg(s, {'type': 'exa', 'query': 'q'})
        self.assertEqual(cfg.get('api_key'), 'sk-exa')


if __name__ == '__main__':
    unittest.main()

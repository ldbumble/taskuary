"""Five more ways to read the web, under the same rule as the first four.

Plain REST, a key on a card, nothing new frozen into the exe. They divide into two jobs: SEARCH
(Brave from its own index, SerpApi and Serper from a search engine's ranked page) and READ ONE
PAGE (ScrapingBee for a page that fights back, Apify when the crawl is one somebody already
wrote). They overlap on purpose - the bill and the terms differ far more than the results do.

Browserbase is absent for the reason research.py's header gives: it DRIVES a browser over CDP,
which no REST call reaches. Oxylabs is absent for a duller one - its realtime host did not
resolve when these five were verified against the live endpoints, and a card is not guessed at.

Every request shape below was read off the vendor's reference. A wrong field name fails at
runtime with a 400 nobody sees until a scheduled report comes back empty.
"""
import json
import unittest
from unittest import mock

from taskuary import research
from taskuary.reports import REGISTRY, CONNECTION_OF
from taskuary.store import MemoryStore

WEB = ('exa', 'tavily', 'firecrawl', 'reader', 'brave_search', 'serpapi', 'serper',
       'scrapingbee', 'apify')


class _Resp:
    def __init__(self, payload=None, status=200, text=''):
        self._payload, self.status_code, self.text = payload, status, text or json.dumps(payload or {})

    def json(self): return self._payload


class BraveTests(unittest.TestCase):
    HIT = {'web': {'results': [{'title': 'A post', 'url': 'https://x.com/a', 'age': '2 days ago',
                                'description': 'what the page says'}]}}

    def test_the_token_goes_in_braves_own_header(self):
        """X-Subscription-Token, not Bearer and not a query parameter - Brave rejects both."""
        with mock.patch.object(research.requests, 'get', return_value=_Resp(self.HIT)) as get:
            head, body = research.run_brave({'api_key': 'k', 'query': 'local-first ai'})
        self.assertEqual(get.call_args.kwargs['headers']['X-Subscription-Token'], 'k')
        self.assertEqual(get.call_args[0][0], 'https://api.search.brave.com/res/v1/web/search')
        self.assertEqual(get.call_args.kwargs['params']['q'], 'local-first ai')
        self.assertIn('1 results', head)
        self.assertIn('what the page says', body)

    def test_the_age_is_kept_so_a_summary_can_say_how_old_a_claim_is(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(self.HIT)):
            _, body = research.run_brave({'api_key': 'k', 'query': 'q'})
        self.assertIn('2 days ago', body)

    def test_the_narrowing_uses_braves_names(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(self.HIT)) as get:
            research.run_brave({'api_key': 'k', 'query': 'q', 'num': 5, 'country': 'us', 'freshness': 'pw'})
        p = get.call_args.kwargs['params']
        self.assertEqual((p['count'], p['country'], p['freshness']), (5, 'us', 'pw'))

    def test_no_key_says_which_card_to_go_to(self):
        with self.assertRaises(RuntimeError) as e: research.run_brave({'query': 'q'})
        self.assertIn('Connections', str(e.exception))


class SerpApiTests(unittest.TestCase):
    HIT = {'organic_results': [{'position': 1, 'title': 'T', 'link': 'https://a.com', 'snippet': 'S'}]}

    def test_the_ranking_is_what_comes_back(self):
        """A neural search throws the order away on purpose. This card exists for the runs where
        the order IS the finding - who comes up first for your own product name."""
        with mock.patch.object(research.requests, 'get', return_value=_Resp(self.HIT)) as get:
            head, body = research.run_serpapi({'api_key': 'k', 'query': 'taskuary'})
        self.assertEqual(get.call_args.kwargs['params']['api_key'], 'k')
        self.assertEqual(get.call_args.kwargs['params']['engine'], 'google')
        self.assertEqual(get.call_args[0][0], 'https://serpapi.com/search.json')
        self.assertIn('position', body)
        self.assertIn('https://a.com', body)
        self.assertIn('1 results', head)

    def test_another_engine_and_a_location_are_passed_through(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(self.HIT)) as get:
            research.run_serpapi({'api_key': 'k', 'query': 'q', 'engine': 'google_news',
                                  'location': 'Roanoke, Virginia'})
        p = get.call_args.kwargs['params']
        self.assertEqual((p['engine'], p['location']), ('google_news', 'Roanoke, Virginia'))

    def test_serpapis_own_error_field_is_not_swallowed(self):
        """SerpApi answers 200 with {"error": ...} for a bad key. Trusting the status code would
        turn a dead report into an empty one, which is the failure nobody notices."""
        with mock.patch.object(research.requests, 'get',
                               return_value=_Resp({'error': 'Invalid API key'})):
            with self.assertRaises(RuntimeError) as e:
                research.run_serpapi({'api_key': 'bad', 'query': 'q'})
        self.assertIn('Invalid API key', str(e.exception))


class SerperTests(unittest.TestCase):
    HIT = {'organic': [{'position': 1, 'title': 'T', 'link': 'https://a.com', 'snippet': 'S'}]}

    def test_the_key_is_a_header_and_the_query_is_a_post_body(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp(self.HIT)) as post:
            head, _ = research.run_serper({'api_key': 'k', 'query': 'q', 'num': 5, 'country': 'us'})
        self.assertEqual(post.call_args.kwargs['headers']['X-API-KEY'], 'k')
        self.assertEqual(post.call_args[0][0], 'https://google.serper.dev/search')
        self.assertEqual(post.call_args.kwargs['json'], {'q': 'q', 'num': 5, 'gl': 'us'})
        self.assertIn('1 results', head)

    def test_an_answer_box_leads_because_it_is_usually_the_whole_answer(self):
        hit = dict(self.HIT, answerBox={'answer': '42', 'link': 'https://a.com/x'})
        with mock.patch.object(research.requests, 'post', return_value=_Resp(hit)):
            head, body = research.run_serper({'api_key': 'k', 'query': 'q'})
        self.assertIn('answer box', body)
        self.assertLess(body.index('answer box'), body.index('"T"') if '"T"' in body else len(body))
        self.assertIn('2 results', head)


class ScrapingBeeTests(unittest.TestCase):
    def test_render_is_off_unless_asked_for_because_it_costs_more(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(None, 200, '<html>hi</html>')) as get:
            head, body = research.run_scrapingbee({'api_key': 'k', 'url': 'https://e.com'})
        p = get.call_args.kwargs['params']
        self.assertEqual((p['api_key'], p['url'], p['render_js']), ('k', 'https://e.com', 'false'))
        self.assertIn('https://e.com', head)
        self.assertIn('hi', body)

    def test_render_and_premium_are_opt_in(self):
        with mock.patch.object(research.requests, 'get', return_value=_Resp(None, 200, 'x')) as get:
            research.run_scrapingbee({'api_key': 'k', 'url': 'https://e.com', 'render': 'true',
                                      'premium': 1, 'country': 'gb'})
        p = get.call_args.kwargs['params']
        self.assertEqual((p['render_js'], p['premium_proxy'], p['country_code']), ('true', 'true', 'gb'))

    def test_a_missing_url_fails_before_the_call_is_paid_for(self):
        with self.assertRaises(RuntimeError) as e: research.run_scrapingbee({'api_key': 'k'})
        self.assertIn('url', str(e.exception))


class ApifyTests(unittest.TestCase):
    def test_a_slash_in_an_actor_name_becomes_a_tilde(self):
        """Actors are written apify/website-content-crawler everywhere a human reads one, and the
        API path wants apify~website-content-crawler. Making the owner know that is a bug."""
        with mock.patch.object(research.requests, 'post', return_value=_Resp([{'url': 'a', 'text': 'b'}])) as post:
            head, _ = research.run_apify({'api_key': 'k', 'actor': 'apify/website-content-crawler',
                                          'input': {'startUrls': [{'url': 'https://e.com'}]}})
        self.assertIn('apify~website-content-crawler/run-sync-get-dataset-items', post.call_args[0][0])
        self.assertEqual(post.call_args.kwargs['params']['token'], 'k')
        self.assertIn('1 items', head)

    def test_the_input_may_arrive_as_json_text(self):
        """A report field is a string. An actor input is an object. One of them has to give."""
        with mock.patch.object(research.requests, 'post', return_value=_Resp([])) as post:
            research.run_apify({'api_key': 'k', 'actor': 'apify~x', 'input': '{"maxItems": 3}'})
        self.assertEqual(post.call_args.kwargs['json'], {'maxItems': 3})

    def test_a_timeout_says_the_actor_is_the_wrong_shape_for_a_report(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp(None, 408, 'timed out')):
            with self.assertRaises(RuntimeError) as e:
                research.run_apify({'api_key': 'k', 'actor': 'apify~slow'})
        self.assertIn('sync window', str(e.exception))

    def test_one_object_back_is_still_one_row(self):
        with mock.patch.object(research.requests, 'post', return_value=_Resp({'a': 1})):
            head, _ = research.run_apify({'api_key': 'k', 'actor': 'apify~x'})
        self.assertIn('1 items', head)

    def test_a_missing_actor_names_one_so_the_error_teaches(self):
        with self.assertRaises(RuntimeError) as e: research.run_apify({'api_key': 'k'})
        self.assertIn('apify~', str(e.exception))


class WiredInTests(unittest.TestCase):
    """A card that runs but is not reachable from the page is not shipped. Each seam below has
    stranded a connector before."""

    def test_every_one_is_a_report_type(self):
        for t in WEB: self.assertIn(t, REGISTRY, f'{t} is not a report source')

    def test_reading_the_web_is_a_read(self):
        from taskuary.scopes import ACTIONS
        for t in WEB: self.assertEqual(ACTIONS[t], 'read', f'{t} should not need write authority')

    def test_every_one_has_a_card_that_can_hold_a_key(self):
        s = MemoryStore()
        for t in WEB: self.assertIsNotNone(s.get_connector_by_type(t), f'no {t} card was seeded')

    def test_the_key_reaches_the_executor_from_the_card(self):
        from taskuary.reports import resolve_cfg
        s = MemoryStore()
        for t in ('brave_search', 'serpapi', 'serper', 'scrapingbee', 'apify'):
            cid = s.get_connector_by_type(t)['ConnectorId']
            s.save_connector({'ConnectorId': cid, 'Secret': f'sk-{t}', 'Active': 1}, 't')
            self.assertEqual(resolve_cfg(s, {'type': t}).get('api_key'), f'sk-{t}',
                             f'{t} would report "no key saved" with the key sitting on its card')

    def test_the_catalogue_no_longer_calls_them_planned(self):
        """They were roadmap rows. A planned row is not offered as a report type, so leaving the
        flag up ships an executor nobody can pick."""
        from taskuary import connectorcatalog
        for t in WEB:
            self.assertFalse(connectorcatalog.by_type(t)['planned'], f'{t} still reads as planned')

    def test_each_is_a_connection_the_reports_tab_can_resolve(self):
        for t in WEB:
            if t == 'reader': continue        # keyless by design: no card required to run it
            self.assertIn(t, CONNECTION_OF, f'{t} has no connection resolver')


if __name__ == '__main__':
    unittest.main()

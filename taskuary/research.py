"""Research connectors: the web as a report source.

Every executor here is plain REST with a key on a card - no browser client, no SDK, nothing new
frozen into the single-exe build. That is deliberate and it is also the boundary: Browserbase and
Stagehand DRIVE a browser (log in, click, fill), which happens over CDP through Playwright and
cannot be reached from REST at all. What is here is the other 90% of "research" - search the web,
read a page, get an answer with sources - and it needs none of that.

Each returns (headline, body) like every other executor, so a research source drops into a report
pipeline beside a SQL query and feeds the same prompt.
"""
import json

import requests

TIMEOUT = 45


def _rows(cfg, rows, unit):
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=unit, mine=mine)


def _key(cfg, *names) -> str:
    for n in names:
        if str(cfg.get(n) or '').strip(): return str(cfg[n]).strip()
    return ''


def run_exa(cfg):
    """{"query", "num", "category", "domains", "since"} - neural search over the live web, with
    the page TEXT already extracted so the summary has something to read rather than ten links.

    contents.text is asked for on purpose: a list of URLs is not research, and fetching each one
    afterwards is the thing this connector exists to avoid.
    """
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Exa API key saved - Connections → Exa')
    body = {'query': cfg['query'], 'numResults': int(cfg.get('num') or 8),
            'contents': {'text': {'maxCharacters': int(cfg.get('chars') or 2000)}}}
    if cfg.get('category'): body['category'] = cfg['category']
    if cfg.get('since'): body['startPublishedDate'] = str(cfg['since'])
    doms = [d.strip() for d in str(cfg.get('domains') or '').split(',') if d.strip()]
    if doms: body['includeDomains'] = doms
    r = requests.post('https://api.exa.ai/search', headers={'x-api-key': key}, json=body, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'exa {r.status_code}: {r.text[:300]}')
    j = r.json()
    rows = [{'title': x.get('title'), 'url': x.get('url'), 'published': (x.get('publishedDate') or '')[:10],
             'text': (x.get('text') or x.get('summary') or '').strip()[:2000]}
            for x in j.get('results') or []]
    return _rows(cfg, rows, 'results')


def run_tavily(cfg):
    """{"query", "depth", "num", "topic", "answer", "days"} - search built for agents: it can
    hand back a written ANSWER with the sources beside it, not only a result list."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Tavily API key saved - Connections → Tavily')
    body = {'query': cfg['query'], 'search_depth': cfg.get('depth') or 'basic',
            'max_results': min(int(cfg.get('num') or 8), 20),
            'topic': cfg.get('topic') or 'general',
            'include_answer': bool(cfg.get('answer', True))}
    if cfg.get('time_range'): body['time_range'] = cfg['time_range']
    r = requests.post('https://api.tavily.com/search', headers={'Authorization': f'Bearer {key}'},
                      json=body, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'tavily {r.status_code}: {r.text[:300]}')
    j = r.json()
    rows = [{'title': x.get('title'), 'url': x.get('url'), 'score': x.get('score'),
             'text': (x.get('content') or '').strip()[:2000]} for x in j.get('results') or []]
    head, body_text = _rows(cfg, rows, 'results')
    # the answer leads, because it is what the reader wants; the sources stay under it so the
    # claim can be checked rather than taken on faith
    if j.get('answer'):
        return f'{head} · answered', f"ANSWER: {j['answer']}\n\nSOURCES:\n{body_text}"
    return head, body_text


def run_firecrawl(cfg):
    """{"url"} - one page, as clean markdown. onlyMainContent strips the nav and the cookie
    banner, which is most of what a raw fetch returns."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Firecrawl API key saved - Connections → Firecrawl')
    if not cfg.get('url'): raise RuntimeError('no url to read')
    body = {'url': cfg['url'], 'formats': ['markdown'],
            'onlyMainContent': cfg.get('main', True) is not False}
    r = requests.post('https://api.firecrawl.dev/v2/scrape', headers={'Authorization': f'Bearer {key}'},
                      json=body, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'firecrawl {r.status_code}: {r.text[:300]}')
    d = (r.json() or {}).get('data') or {}
    from .reports import BODY_CHARS
    md = (d.get('markdown') or '').strip()
    title = ((d.get('metadata') or {}).get('title') or cfg['url'])[:120]
    if not md: raise RuntimeError(f"firecrawl returned no markdown for {cfg['url']}")
    return f'{title} · {len(md)} chars', md[:BODY_CHARS]


def run_reader(cfg):
    """{"url"} - a page as markdown through Jina Reader, with NO key at all.

    Here because a research pipeline should not need a paid account to read one public page, and
    because it is the only one of these that a new install can try immediately. A key raises the
    rate limit; without one it still works, which is the point.
    """
    if not cfg.get('url'): raise RuntimeError('no url to read')
    key = _key(cfg, 'api_key', 'secret')
    hdr = {'Authorization': f'Bearer {key}'} if key else {}
    r = requests.get(f"https://r.jina.ai/{cfg['url']}", headers=hdr, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'reader {r.status_code}: {r.text[:200]}')
    from .reports import BODY_CHARS
    text = (r.text or '').strip()
    first = next((l[7:].strip() for l in text.splitlines() if l.startswith('Title: ')), cfg['url'])
    return f'{first[:120]} · {len(text)} chars', text[:BODY_CHARS]


# ── five more, same rule as the four above: plain REST, a key on a card ──────────────────────
# Browserbase is deliberately NOT here. It DRIVES a browser over CDP through Playwright, which is
# the boundary this module's header draws - it cannot be reached from REST at all, and pretending
# otherwise would ship a card that never works. Oxylabs is absent for a duller reason: its realtime
# host did not resolve when the others were verified, so it was not guessed at.

def run_brave(cfg):
    """{"query", "num", "country", "freshness"} - Brave's own index, not a reseller of someone
    else's. The free tier is real (2,000 queries a month) and needs no card."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Brave Search key saved - Connections → Brave Search')
    params = {'q': cfg['query'], 'count': int(cfg.get('num') or 10)}
    for a, b in (('country', 'country'), ('freshness', 'freshness')):
        if cfg.get(a): params[b] = str(cfg[a])
    r = requests.get('https://api.search.brave.com/res/v1/web/search', params=params, timeout=TIMEOUT,
                     headers={'X-Subscription-Token': key, 'Accept': 'application/json'})
    if r.status_code >= 400: raise RuntimeError(f'brave {r.status_code}: {r.text[:300]}')
    rows = [{'title': x.get('title'), 'url': x.get('url'), 'age': x.get('age') or '',
             'text': (x.get('description') or '').strip()[:1000]}
            for x in ((r.json().get('web') or {}).get('results') or [])]
    return _rows(cfg, rows, 'results')


def run_serpapi(cfg):
    """{"query", "num", "engine", "location"} - a real SERP as a search engine renders it, which
    is the point: ranking and the answer box, not a neural re-ranking of the web."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no SerpApi key saved - Connections → SerpApi')
    params = {'q': cfg['query'], 'api_key': key, 'engine': cfg.get('engine') or 'google',
              'num': int(cfg.get('num') or 10)}
    if cfg.get('location'): params['location'] = str(cfg['location'])
    r = requests.get('https://serpapi.com/search.json', params=params, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'serpapi {r.status_code}: {r.text[:300]}')
    j = r.json()
    if j.get('error'): raise RuntimeError(f"serpapi: {j['error']}")
    rows = [{'position': x.get('position'), 'title': x.get('title'), 'url': x.get('link'),
             'text': (x.get('snippet') or '').strip()[:1000]} for x in j.get('organic_results') or []]
    return _rows(cfg, rows, 'results')


def run_serper(cfg):
    """{"query", "num", "country"} - Google results at a fraction of SerpApi's price. Same job,
    different bill; the card exists so the choice is yours rather than ours."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Serper key saved - Connections → Serper')
    body = {'q': cfg['query'], 'num': int(cfg.get('num') or 10)}
    if cfg.get('country'): body['gl'] = str(cfg['country'])
    r = requests.post('https://google.serper.dev/search', headers={'X-API-KEY': key}, json=body, timeout=TIMEOUT)
    if r.status_code >= 400: raise RuntimeError(f'serper {r.status_code}: {r.text[:300]}')
    j = r.json()
    rows = [{'position': x.get('position'), 'title': x.get('title'), 'url': x.get('link'),
             'text': (x.get('snippet') or '').strip()[:1000]} for x in j.get('organic') or []]
    if j.get('answerBox'):
        rows.insert(0, {'position': 0, 'title': 'answer box', 'url': (j['answerBox'] or {}).get('link') or '',
                        'text': json.dumps(j['answerBox'], default=str)[:1000]})
    return _rows(cfg, rows, 'results')


def run_scrapingbee(cfg):
    """{"url", "render", "premium"} - fetch a page that fights back: rotating proxies and, with
    render on, a headless browser run on THEIR machine. Reader and Firecrawl are cheaper and
    quieter; this is the one for a page that refuses them."""
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no ScrapingBee key saved - Connections → ScrapingBee')
    if not cfg.get('url'): raise RuntimeError('scrapingbee needs a url')
    params = {'api_key': key, 'url': cfg['url'],
              'render_js': 'true' if str(cfg.get('render') or '') .lower() in ('1', 'true', 'yes') else 'false'}
    if cfg.get('premium'): params['premium_proxy'] = 'true'
    if cfg.get('country'): params['country_code'] = str(cfg['country'])
    r = requests.get('https://app.scrapingbee.com/api/v1/', params=params, timeout=max(TIMEOUT, 90))
    if r.status_code >= 400: raise RuntimeError(f'scrapingbee {r.status_code}: {r.text[:300]}')
    from .reports import BODY_CHARS
    text = (r.text or '').strip()
    return f'{len(text):,} characters from {cfg["url"]}', text[:BODY_CHARS]


def run_apify(cfg):
    """{"actor", "input", "num"} - run one Apify actor and take its dataset back in the same call.

    run-sync-get-dataset-items is used deliberately: the async road is start, poll, then fetch,
    and a report that has to poll is a report that has to hold state. An actor slower than the
    timeout is the wrong shape for this card, and the error says so rather than hanging.
    """
    key = _key(cfg, 'api_key', 'secret')
    if not key: raise RuntimeError('no Apify token saved - Connections → Apify')
    actor = str(cfg.get('actor') or '').strip()
    if not actor: raise RuntimeError('apify needs an actor, e.g. apify~website-content-crawler')
    payload = cfg.get('input') or {}
    if isinstance(payload, str): payload = json.loads(payload or '{}')
    r = requests.post(f'https://api.apify.com/v2/acts/{actor.replace("/", "~")}/run-sync-get-dataset-items',
                      params={'token': key, 'limit': int(cfg.get('num') or 50)},
                      json=payload, timeout=max(TIMEOUT, 120))
    if r.status_code == 408:
        raise RuntimeError(f'{actor} did not finish inside the sync window - this card runs actors '
                           'that answer in one call; a long crawl needs its own schedule')
    if r.status_code >= 400: raise RuntimeError(f'apify {r.status_code}: {r.text[:300]}')
    out = r.json()
    rows = out if isinstance(out, list) else [out]
    return _rows(cfg, rows, 'items')

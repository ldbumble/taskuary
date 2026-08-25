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
    if not key: raise RuntimeError('no Exa API key saved - Connectors → Exa')
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
    if not key: raise RuntimeError('no Tavily API key saved - Connectors → Tavily')
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
    if not key: raise RuntimeError('no Firecrawl API key saved - Connectors → Firecrawl')
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

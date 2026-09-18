"""Read-only Alchemy token prices and wallet holdings for finance reports."""

import re
from decimal import Decimal, InvalidOperation

import requests


BASE = 'https://api.g.alchemy.com'
TIMEOUT = 30


class AlchemyError(RuntimeError):
    pass


def _key(cfg):
    key = str(cfg.get('api_key') or '').strip()
    if not key:
        raise AlchemyError('no Alchemy API key saved - Connections -> Alchemy')
    return key


def _request(method, path, key, **kwargs):
    # Alchemy puts the key in the URL. Never include that URL in an error or report row.
    try:
        response = requests.request(method, f'{BASE}/{path.format(key=key)}', timeout=TIMEOUT, **kwargs)
        try:
            data = response.json()
        except ValueError:
            raise AlchemyError(f'Alchemy returned non-JSON (HTTP {response.status_code})')
    except requests.RequestException as exc:
        raise AlchemyError(f'Alchemy request failed: {type(exc).__name__}') from exc
    if response.status_code >= 300:
        raise AlchemyError(f'Alchemy returned HTTP {response.status_code}')
    if not isinstance(data, dict):
        raise AlchemyError('Alchemy returned an unexpected response')
    return data


def _rows(cfg, rows, unit):
    from .reports import row_limit, rows_out
    limit, mine = row_limit(cfg)
    return rows_out(rows, limit, unit=unit, mine=mine)


def _items(value):
    return [x.strip() for x in value.split(',') if x.strip()] if isinstance(value, str) else value


def run_alchemy_prices(cfg):
    """Current USD token prices. Config: symbols = 'ETH,BTC' (up to 25)."""
    key = _key(cfg)
    symbols = _items(cfg.get('symbols') or 'ETH,BTC')
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= 25 or any(
            not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,30}', s) for s in symbols):
        raise AlchemyError('symbols must be 1 to 25 comma-separated token symbols')
    data = _request('GET', 'prices/v1/{key}/tokens/by-symbol', key,
                    params={'symbols': ','.join(symbols)})
    if not isinstance(data.get('data'), list):
        raise AlchemyError('Alchemy prices response has no data array')
    rows = []
    for token in data['data']:
        prices = token.get('prices') or []
        usd = next((p for p in prices if str(p.get('currency', '')).lower() == 'usd'), None)
        rows.append({'symbol': token.get('symbol'), 'currency': 'USD',
                     'price': float(usd['value']) if usd and usd.get('value') is not None else None,
                     'updated': usd.get('lastUpdatedAt') if usd else None,
                     'error': token.get('error')})
    return _rows(cfg, rows, 'prices')


def run_alchemy_wallet(cfg):
    """Wallet token holdings with USD prices. Config: address, networks (default eth-mainnet)."""
    key = _key(cfg)
    address = str(cfg.get('address') or '').strip()
    networks = _items(cfg.get('networks') or 'eth-mainnet')
    if not address or len(address) > 128 or not re.fullmatch(r'[A-Za-z0-9.:-]+', address):
        raise AlchemyError('set a valid wallet address on the report')
    if not isinstance(networks, list) or not 1 <= len(networks) <= 20 or any(
            not isinstance(n, str) or not re.fullmatch(r'[a-z0-9-]{1,40}', n) for n in networks):
        raise AlchemyError('networks must be comma-separated Alchemy network identifiers')
    body = {'addresses': [{'address': address, 'networks': networks}],
            'withMetadata': True, 'withPrices': True,
            'includeNativeTokens': True, 'includeErc20Tokens': True}
    tokens = []
    page_key = None
    seen = set()
    for _ in range(20):
        request_body = {**body, **({'pageKey': page_key} if page_key else {})}
        data = _request('POST', 'data/v1/{key}/assets/tokens/by-address', key, json=request_body)
        if data.get('error'):
            error = data['error']
            failed = ', '.join(str(p.get('network')) for p in error.get('partialErrors', []) if isinstance(p, dict)) if isinstance(error, dict) else ''
            raise AlchemyError(f'Alchemy wallet data incomplete{": " + failed if failed else ""}')
        payload = data.get('data')
        if not isinstance(payload, dict) or not isinstance(payload.get('tokens'), list):
            raise AlchemyError('Alchemy wallet response has no tokens array')
        tokens.extend(payload['tokens'])
        page_key = payload.get('pageKey')
        if not page_key:
            break
        if page_key in seen:
            raise AlchemyError('Alchemy repeated a wallet page key')
        seen.add(page_key)
    else:
        raise AlchemyError('Alchemy wallet has more than 20 pages; narrow the networks')

    rows = []
    for token in tokens:
        meta = token.get('tokenMetadata') or {}
        raw = token.get('tokenBalance')
        try:
            decimals = int(meta['decimals'])
            if not 0 <= decimals <= 36:
                raise ValueError()
            if raw is None:
                raise ValueError()
            atomic = str(raw)
            balance = Decimal(int(atomic, 16) if atomic.startswith('0x') else int(atomic)) / (10 ** decimals)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            # A token-level metadata failure must remain visible without inventing a balance.
            if not token.get('error'):
                raise AlchemyError('Alchemy wallet returned an invalid token balance')
            balance = None
        usd = next((p for p in (token.get('tokenPrices') or []) if str(p.get('currency', '')).lower() == 'usd'), None)
        price = Decimal(str(usd['value'])) if usd and usd.get('value') is not None else None
        rows.append({'address': token.get('address') or address, 'network': token.get('network'),
                     'token_address': token.get('tokenAddress'), 'symbol': meta.get('symbol'),
                     'name': meta.get('name'), 'balance': str(balance) if balance is not None else None,
                     'raw_balance': raw if balance is None else None,
                     'price_usd': float(price) if price is not None else None,
                     'value_usd': float(balance * price) if balance is not None and price is not None else None,
                     'error': token.get('error')})
    return _rows(cfg, rows, 'tokens')


def probe(cfg):
    head, body = run_alchemy_prices({**cfg, 'symbols': 'ETH', 'max_rows': 1})
    return f'{head} - {body.splitlines()[0]}'[:300] if body else head

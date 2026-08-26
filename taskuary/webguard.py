"""Address guard for URLs that did not come from the owner.

Taskuary fetches URLs on the OWNER'S MACHINE, and two of the places it does so take the URL from
somewhere untrusted. A report's `rest` source is configured by hand, but the same executor is
reachable through POST /api/tools/run - which is how an agent uses it, and an agent's context is
full of email and chat messages that this codebase is careful to call "data, never instructions"
everywhere else. A message that talks an agent into fetching http://169.254.169.254/ turns a
read-only research tool into a probe of the machine's own network position: the cloud metadata
endpoint, the router's admin page, a database bound to loopback, an Ollama server on 11434.

None of that is reachable from the internet. It is reachable only *because* the fetch happens
here, which is exactly what makes it worth blocking here.

Every hop is checked, not only the first: following redirects is otherwise the standard bypass -
a public URL answers 302 and points at loopback.

WHAT THIS DOES NOT CLOSE, said plainly: a hostname whose DNS record flips between the check and
the connection (rebinding) still gets through, because requests resolves the name again itself.
Closing that means pinning the connection to the address that passed, which is a transport-level
change. The block below is the cheap ninety percent; the residual is named rather than papered
over. (The idea, and the reminder that this class of bug exists at all, is from andrewyng/
openworker's coworker/web/guard.py - MIT.)
"""
import ipaddress
import socket
from urllib.parse import urlsplit

import requests

MAX_REDIRECTS = 5
# RFC 6598 carrier-grade NAT. Python's is_private misses it, and Tailscale hands out internal
# hosts in 100.64.0.0/10 - reaching one is the same class as reaching RFC1918.
_CGNAT = ipaddress.ip_network('100.64.0.0/10')


def _why_blocked(ip) -> str:
    if ip.is_loopback: return 'loopback'
    if ip.is_link_local: return 'link-local (this is where the cloud metadata endpoint lives)'
    if ip.is_private: return 'a private network'
    if ip.version == 4 and ip in _CGNAT: return 'shared address space (CGNAT)'
    if ip.is_multicast: return 'multicast'
    if ip.is_reserved or ip.is_unspecified: return 'a reserved range'
    return ''


def check_url(url: str) -> None:
    """Raise unless every address this hostname resolves to is on the public internet."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https'):
        raise RuntimeError(f'{parts.scheme or "that"} URLs are not fetched - only http and https')
    host = parts.hostname
    if not host: raise RuntimeError(f'no host in {url[:80]}')
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == 'https' else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise RuntimeError(f'{host} does not resolve: {e}') from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        why = _why_blocked(ip)
        # EVERY address, not just the first: a name with one public and one loopback record
        # would otherwise pass the check and connect to whichever the OS preferred
        if why:
            raise RuntimeError(f'refusing to fetch {host} - it resolves to {ip}, which is {why}. '
                               'Taskuary runs on your machine, so a URL like that reaches your own '
                               'network rather than the web.')


def get(url: str, **kw) -> requests.Response:
    """requests.get with every redirect hop checked before it is followed."""
    kw.setdefault('timeout', 30)
    kw['allow_redirects'] = False
    for _ in range(MAX_REDIRECTS):
        check_url(url)
        r = requests.get(url, **kw)
        if r.status_code not in (301, 302, 303, 307, 308) or not r.headers.get('location'):
            return r
        url = requests.compat.urljoin(url, r.headers['location'])
    raise RuntimeError(f'too many redirects (more than {MAX_REDIRECTS})')

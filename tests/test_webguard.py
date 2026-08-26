"""A URL the owner did not type.

The `rest` and `rss` executors fetch on the OWNER'S MACHINE, and both are reachable through
POST /api/tools/run - which is how an agent uses them, and an agent's context is full of email
and chat this codebase calls data and never instructions. A message that talks an agent into
fetching http://169.254.169.254/ turns a read-only research tool into a probe of the machine's
own network: cloud metadata, the router's admin page, a database on loopback, Ollama on 11434.

None of it is reachable from the internet. It is reachable only because the fetch happens here.

(The class of bug, and the reminder to look for it, came from reading andrewyng/openworker.)
"""
import unittest
from unittest import mock

from taskuary import webguard
from taskuary.reports import REGISTRY


def _resolves_to(*ips):
    """socket.getaddrinfo's shape, for a NAME we want to pretend resolves somewhere.

    A literal IP passes straight through, exactly as real resolution does - stubbing that away
    made an earlier version of these tests answer "public" for 127.0.0.1 and quietly stop
    testing the thing they were written for."""
    import ipaddress
    import socket
    def fake(host, port, *a, **kw):
        try:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (str(ipaddress.ip_address(host)), port))]
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)) for ip in ips]
    return fake


class WhatIsRefusedTests(unittest.TestCase):
    def test_the_addresses_that_only_exist_because_we_run_on_your_machine(self):
        for url, word in (('http://127.0.0.1:11434/api/tags', 'loopback'),
                          ('http://169.254.169.254/latest/meta-data/', 'link-local'),
                          ('http://192.168.1.1/', 'private'),
                          ('http://10.0.0.5/admin', 'private'),
                          ('http://[::1]:8080/', 'loopback')):
            with self.subTest(url=url), self.assertRaises(RuntimeError) as e:
                webguard.check_url(url)
            self.assertIn(word, str(e.exception))

    def test_carrier_grade_nat_is_private_too(self):
        """Python's is_private misses 100.64.0.0/10, and Tailscale hands out internal hosts
        there - reaching one is the same class as reaching 192.168.x.x."""
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('100.64.1.2')):
            with self.assertRaises(RuntimeError) as e:
                webguard.check_url('http://tailscale-host.example/')
        self.assertIn('CGNAT', str(e.exception))

    def test_every_resolved_address_is_checked_not_just_the_first(self):
        """A name with one public and one loopback record would otherwise pass, and the OS
        would connect to whichever it preferred."""
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('93.184.216.34', '127.0.0.1')):
            with self.assertRaises(RuntimeError) as e:
                webguard.check_url('http://split-horizon.example/')
        self.assertIn('loopback', str(e.exception))

    def test_a_scheme_that_is_not_the_web_is_refused(self):
        for url in ('file:///etc/passwd', 'gopher://x/', 'ftp://host/f'):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                webguard.check_url(url)

    def test_a_public_address_passes(self):
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('93.184.216.34')):
            webguard.check_url('https://example.com/page')        # no raise


class RedirectsTests(unittest.TestCase):
    """Following redirects is the standard bypass: a public URL answers 302 and points home."""
    def test_a_redirect_into_loopback_is_caught_on_the_hop(self):
        hop = mock.Mock(status_code=302, headers={'location': 'http://127.0.0.1:8080/admin'})
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('93.184.216.34')), \
             mock.patch.object(webguard.requests, 'get', return_value=hop):
            with self.assertRaises(RuntimeError) as e:
                webguard.get('https://public.example/start')
        self.assertIn('loopback', str(e.exception))

    def test_a_redirect_loop_ends_rather_than_spinning(self):
        hop = mock.Mock(status_code=302, headers={'location': 'https://public.example/again'})
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('93.184.216.34')), \
             mock.patch.object(webguard.requests, 'get', return_value=hop):
            with self.assertRaises(RuntimeError) as e:
                webguard.get('https://public.example/start')
        self.assertIn('too many redirects', str(e.exception))

    def test_a_plain_response_comes_straight_back(self):
        ok = mock.Mock(status_code=200, headers={}, text='hello')
        with mock.patch.object(webguard.socket, 'getaddrinfo', side_effect=_resolves_to('93.184.216.34')), \
             mock.patch.object(webguard.requests, 'get', return_value=ok):
            self.assertEqual(webguard.get('https://public.example/').text, 'hello')


class TheExecutorsUseItTests(unittest.TestCase):
    def test_rest_refuses_the_metadata_endpoint(self):
        with self.assertRaises(RuntimeError) as e:
            REGISTRY['rest']({'url': 'http://169.254.169.254/latest/meta-data/'})
        self.assertIn('reaches your own', str(e.exception))

    def test_rss_is_guarded_too(self):
        """Same executor shape, same exposure - a feed url is still a url an agent can choose."""
        with self.assertRaises(RuntimeError):
            REGISTRY['rss']({'url': 'http://127.0.0.1:8000/feed.xml'})

    def test_the_refusal_explains_why_rather_than_just_saying_no(self):
        with self.assertRaises(RuntimeError) as e:
            REGISTRY['rest']({'url': 'http://192.168.0.10/'})
        msg = str(e.exception)
        self.assertIn('192.168.0.10', msg)          # which address
        self.assertIn('private network', msg)       # what is wrong with it
        self.assertIn('your own network', msg)      # why that matters here specifically


if __name__ == '__main__':
    unittest.main()

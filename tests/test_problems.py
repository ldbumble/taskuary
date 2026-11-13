"""The bell (problems.py): what is failing, each with where to fix it - and quiet once it is not."""
import unittest
from datetime import datetime, timedelta
from taskuary import problems
from taskuary.store import MemoryStore


def _on(s, typ):
    c = next(c for c in s.list_connectors() if c['Type'] == typ)
    s._exec('UPDATE connector SET Active=1 WHERE ConnectorId=?', (c['ConnectorId'],))
    return c


def _since(s, c, **ago):
    s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?',
            ((datetime.now() - timedelta(**ago)).strftime('%Y-%m-%d %H:%M:%S'), c['ConnectorId']))


class Problems(unittest.TestCase):
    def test_a_failing_connector_shows_with_its_card_and_clears_on_a_clean_poll(self):
        s = MemoryStore()
        wa = next(c for c in s.list_connectors() if c['Type'] == 'whatsapp')
        s._exec('UPDATE connector SET Active=1 WHERE ConnectorId=?', (wa['ConnectorId'],))
        s.touch_connector(wa['ConnectorId'], 'the WhatsApp bridge is not running at http://127.0.0.1:8977')
        _since(s, wa, minutes=problems.GRACE_MINUTES + 5)
        got = {p['key']: p for p in problems.collect(s)}
        key = f"connector:{wa['ConnectorId']}"
        self.assertIn(key, got)
        self.assertEqual((got[key]['where'], got[key]['connector']), ('Connections', str(wa['ConnectorId'])))
        self.assertIn('bridge is not running', got[key]['detail'])
        self.assertTrue(got[key]['restart'], 'a bridge this machine runs is restarted from the bell itself (2026-10-22)')
        s.touch_connector(wa['ConnectorId'])                         # a clean poll: off the red half...
        self.assertNotIn(key, {p['key'] for p in problems.collect(s)})
        back = {n['key']: n for n in problems.news(s)}[f'back:{key}']   # ...onto the calm one, with what it was
        self.assertEqual(back['title'], f"{wa['Name']} is working again")
        self.assertIn('bridge is not running', back['detail'])
        self.assertEqual((back['where'], back['connector']), ('Connections', str(wa['ConnectorId'])))
        problems.collect(s); self.assertIn(f'back:{key}', {n['key'] for n in problems.news(s)})   # no clock takes it down
        problems.dismiss(s, f'back:{key}')                            # Got it
        self.assertEqual(problems.news(s), [])

    def test_a_failing_card_switched_off_is_not_working_again(self):
        """Turning a failing card off stops it being read; it did not heal, so the episode closes without a word."""
        s = MemoryStore()
        wa = _on(s, 'whatsapp')
        s.touch_connector(wa['ConnectorId'], 'the WhatsApp bridge is not running')
        _since(s, wa, minutes=problems.GRACE_MINUTES + 5)
        key = f"connector:{wa['ConnectorId']}"
        self.assertIn(key, {p['key'] for p in problems.collect(s)})
        s._exec('UPDATE connector SET Active=0 WHERE ConnectorId=?', (wa['ConnectorId'],))   # the owner switches it off, error still on it
        self.assertNotIn(key, {p['key'] for p in problems.collect(s)})
        self.assertEqual(problems.news(s), [], 'a card switched off is not "working again"')

    def test_a_retry_at_work_does_not_ring(self):
        """2026-10-26: "the classic whatsapp timeout should not show up". The poll starts a dropped bridge again
        (wabridge.supervise); one that is back inside the grace never rang, so it says no "working again" either."""
        s = MemoryStore()
        wa = _on(s, 'whatsapp')
        s.touch_connector(wa['ConnectorId'], 'timed out')
        key = f"connector:{wa['ConnectorId']}"
        self.assertNotIn(key, {p['key'] for p in problems.collect(s)})
        self.assertIn(key, {p['key'] for p in problems.collect(s, all_of_them=True)}, 'the troubleshooter still sees it')
        s.touch_connector(wa['ConnectorId'])
        problems.collect(s)
        self.assertEqual(problems.news(s), [])

    def test_a_bridge_given_up_on_rings_at_once(self):
        from taskuary import wabridge
        s = MemoryStore()
        wa = _on(s, 'whatsapp')
        s.touch_connector(wa['ConnectorId'], 'the WhatsApp bridge would not stay up after 6 starts in a row')
        was = wabridge._SUP['gave_up']
        try:
            wabridge._SUP['gave_up'] = 'the WhatsApp bridge would not stay up after 6 starts in a row'
            self.assertIn(f"connector:{wa['ConnectorId']}", {p['key'] for p in problems.collect(s)})
        finally: wabridge._SUP['gave_up'] = was

    def test_an_external_bridge_or_another_connector_offers_no_restart(self):
        s = MemoryStore()
        for t in ('whatsapp', 'telegram'):
            c = next(c for c in s.list_connectors() if c['Type'] == t)
            s._exec('UPDATE connector SET Active=1 WHERE ConnectorId=?', (c['ConnectorId'],))
            s.touch_connector(c['ConnectorId'], 'not answering')
        wa = s.get_connector_by_type('whatsapp')
        s.set_connector_config(wa['ConnectorId'], {'bridge_url': 'http://wa-box.example:8977'})
        self.assertEqual([p for p in problems.collect(s) if p.get('restart')], [])

    def test_a_failure_says_when_and_stays_while_it_lasts(self):
        """No clock takes a failure down (2026-10-26): a connector whose poller stopped is still broken a day later."""
        s = MemoryStore()
        c = _on(s, 'whatsapp')
        s.touch_connector(c['ConnectorId'], 'Unsupported parameter')
        key = f"connector:{c['ConnectorId']}"
        _since(s, c, hours=26)
        got = {p['key']: p for p in problems.collect(s)}
        self.assertTrue(got[key]['since'])                           # when it FAILED, not when it last worked
        s._exec('UPDATE connector SET LastErrorAt=NULL WHERE ConnectorId=?', (c['ConnectorId'],))   # from before the stamp
        self.assertNotIn(key, {p['key'] for p in problems.collect(s, all_of_them=True)})

    def test_an_inactive_connector_with_an_old_error_does_not_nag(self):
        s = MemoryStore()
        c = next(c for c in s.list_connectors() if c['Type'] == 'slack')
        s.touch_connector(c['ConnectorId'], 'invalid_auth')
        self.assertNotIn(f"connector:{c['ConnectorId']}", {p['key'] for p in problems.collect(s)})

    def test_the_triage_brain_down_is_a_problem(self):
        s = MemoryStore()
        s.set_setting('triage_last_error', 'azure_openai: 401 Unauthorized', 'system')
        s.set_setting('triage_last_error_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'system')
        s.set_setting('triage_ai', 'connector:azure_openai', 'owner')
        got = {p['key']: p for p in problems.collect(s)}
        self.assertEqual(got['triage']['connector'], 'azure_openai')


class AnOutage(unittest.TestCase):
    """A Microsoft outage, 2026-11-12: mail answered 502/503 and chats 401 for hours while the sign-in still renewed. The bell printed
    the raw line - its URL, and the mailbox inside it - and the chats card said to paste a key it has none of. Both say the service's
    trouble now, in the same words on the card and the bell."""
    def test_a_service_down_and_a_refused_read_on_a_sign_in_card_are_said_as_the_services_trouble(self):
        import json
        s = MemoryStore()
        mail, chats = _on(s, 'outlook'), _on(s, 'teams')
        for c in (mail, chats): s._exec('UPDATE connector SET ConfigJson=? WHERE ConnectorId=?', (json.dumps({'auth': 'user'}), c['ConnectorId']))
        s.touch_connector(mail['ConnectorId'], 'inbox: 503 Server Error: Service Unavailable for url: https://graph.example/v1.0/users/alex@northwind.example/mailFolders/inbox/messages')
        s.touch_connector(chats['ConnectorId'], '401 Client Error: Unauthorized for url: https://graph.example/v1.0/users/alex@northwind.example/chats/getAllMessages/delta')
        for c in (mail, chats): _since(s, c, minutes=problems.GRACE_MINUTES + 5)
        got = {p['key']: p['detail'] for p in problems.collect(s)}
        down, refused = got[f"connector:{mail['ConnectorId']}"], got[f"connector:{chats['ConnectorId']}"]
        self.assertIn('trouble on its side (it answered 503)', down)
        self.assertIn('sign-in still works', refused); self.assertNotIn('paste', refused)
        for d in (down, refused): self.assertNotRegex(d, r'https?://|northwind')
        from taskuary.channels import card_error
        self.assertEqual(down, card_error(s.get_connector(mail['ConnectorId'])))       # one road: the card's words are the bell's

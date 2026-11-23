"""The walks' stand-in WhatsApp bridge (website/browser/fake_wa_bridge.py) against the app's REAL phone road: messengers._wa over HTTP,
poll_whatsapp, remote_assistant - only the brain is a stand-in here. If the fake drifts from what bridge.mjs serves, the live walks stress
something the owner's phone never does; this pins that it speaks the protocol the app reads. Invented people only."""
import json, sys, time, unittest
from pathlib import Path

import requests

from taskuary import config, messengers, remote_assistant as ra, wabridge
from tests.phone_transcript import GAIL, RAY, Phone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'website' / 'browser'))
import fake_wa_bridge as fwa                                                    # noqa: E402


class FakeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.srv, self.br = fwa.serve(0, config.home(), config.home() / 'fake-wa-media')
        self.addCleanup(self.srv.shutdown)
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}'
        self.said = []
        self.ph = Phone('whatsapp', brain=lambda q: self.said.append(q) or 'Two asks wait on you: badge access and visitor parking.')
        self.addCleanup(self.ph.close)
        next(p for p in self.ph._p if getattr(p, 'attribute', '') == '_wa').stop()     # the transport is the fake bridge now, over HTTP
        self.s = self.ph.s
        self.s.merge_connector_config(self.ph.cid, {'bridge_url': self.url, 'assistant_chat': fwa.ME})
        messengers._WA_FILTERED.clear()
        self.ph.f._work('Badge access for the new hire', subject='Badge access', from_name=RAY[0], from_email=RAY[1],
                        body='Alex, can you get the new clerk a badge for floors 2 and 3?', sent_at=self.ph.f.ago(hours=3))
        self.ph.f._work('Visitor parking for Friday', subject='Visitor parking', from_name=GAIL[0], from_email=GAIL[1],
                        body='Can we get a visitor parking list for Friday?', sent_at=self.ph.f.ago(hours=2))
        self.ph.ready()

    def poll(self): self.ph._poll()
    def app(self, after=0): return [b for b in self.br.bubbles[after:] if b['from'] == 'app']
    def cfg(self): return json.loads(self.s.get_connector(self.ph.cid)['ConfigJson'])

    def test_a_typed_line_is_answered_thumbed_and_its_echo_never_heard_again(self):
        self.br.owner({'text': 'what is waiting on me?'})
        self.poll()
        self.assertEqual(self.said[-1:], ['what is waiting on me?'])
        got = self.app()
        self.assertTrue(got and got[0]['text'].startswith('Taskuary:'), got)
        self.assertTrue(self.br.reacts, 'no thumb on his line')
        n = len(self.br.bubbles); self.poll()                                    # the app's own lines come back as taskuary echoes
        self.assertEqual(len(self.br.bubbles), n, 'an echo of its own answer was answered')
        self.assertEqual((self.cfg()['wa_seq'], self.cfg()['wa_boot']), (self.br.seq, self.br.boot))
        self.assertEqual(sorted(self.br.filter['jids']), [fwa.ME], 'the bridge was not told which chats to open')

    def test_a_poll_tap_picks_and_a_second_tap_on_it_is_told_spent(self):
        self.s.set_setting(ra.MORNING_KEY, '1', 't'); self.s.set_setting(ra.MORNING_AT, '', 't'); ra._talked.clear()
        ra.morning_line(self.s, force=True)
        polls = [b for b in self.app() if b['kind'] == 'poll']
        self.assertTrue(polls and ra.WALK in polls[-1]['poll'], self.app())
        n = len(self.br.bubbles)
        self.assertEqual(self.br.vote({'option': ra.WALK})[0], 200); self.poll()
        card = self.app(n)
        self.assertTrue(card, 'the tap answered nothing')
        self.assertTrue(any(w in ' '.join(b['text'] for b in card) for w in ('Badge', 'parking')), card)
        n = len(self.br.bubbles)
        self.br.vote({'option': ra.WALK, 'poll': polls[-1]['id']}); self.poll()             # the opener's poll again - an older one now
        self.assertTrue(self.app(n), 'a tap on an older poll was met with silence')

    def test_a_restarted_bridge_is_read_from_its_start(self):
        self.br.owner({'text': 'hello'}); self.poll()
        self.br.restart(); n = len(self.br.bubbles)
        self.br.owner({'text': 'what is next?'}); self.poll()
        self.assertEqual(self.said[-1], 'what is next?', 'the first line after a bridge restart was skipped')
        self.assertTrue(self.app(n))
        self.assertEqual(self.cfg()['wa_boot'], self.br.boot)

    def test_a_picture_from_the_phone_reaches_the_turn_as_a_kept_file(self):
        png = config.home() / 'shot.png'; png.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0' * 64)
        self.br.media_in({'path': str(png), 'caption': 'the words look weird on this screen'})
        self.poll()
        self.assertEqual(self.said[-1:], ['the words look weird on this screen'])
        kept = list((config.home() / 'attachments' / 'phone').rglob('*.png'))      # named by its message id, as bridge.mjs saves it
        self.assertTrue(kept, 'the picture never reached the turn')

    def test_the_token_is_the_homes_and_a_browser_is_refused(self):
        tok = wabridge.token()
        self.assertEqual(requests.get(f'{self.url}/status', headers={'X-Bridge-Token': tok}, timeout=5).status_code, 200)
        self.assertEqual(requests.get(f'{self.url}/status', headers={'X-Bridge-Token': 'wrong'}, timeout=5).status_code, 401)
        self.assertEqual(requests.get(f'{self.url}/status', headers={'X-Bridge-Token': tok, 'Origin': 'http://x.example'}, timeout=5).status_code, 403)
        self.assertEqual(messengers.wa_self_number(self.s, {**self.s.get_connector(self.ph.cid, with_secret=True), 'ConfigJson': json.dumps({'bridge_url': self.url})}),
                         fwa.ME_NUM)


if __name__ == '__main__': unittest.main()

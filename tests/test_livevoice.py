"""Live interaction (livevoice.py): the card's config and Test road, the front that may only hand on, read and press after a yes, and a
spoken ask fed through the real Pipecat pipeline - Whisper-free: the hearing and speaking services are stubs, the front and pipeline real."""
import asyncio, json, pathlib, sys, unittest, wave
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import deps, livevoice, server
from taskuary.store import MemoryStore

ROOT = pathlib.Path(__file__).resolve().parent
WAV = ROOT / 'data' / 'live_ask.wav'
ASK = 'Find the three oldest open invoices and tell me who they are from.'     # what tests/data/live_ask.wav says (Windows' own TTS)
api = TestClient(server.app)


class R:
    def __init__(self, code, body): self.status_code, self._b, self.text = code, body, json.dumps(body)
    def json(self): return self._b


def _on(s, t, secret='k1', cfg=None):
    cid = s.get_connector_by_type(t)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, **({'Secret': secret} if secret else {}), **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 'o')
    return cid


class TheCardsSetUpAndTest(unittest.TestCase):
    def test_the_three_cards_are_seeded_and_in_the_catalogue(self):
        from taskuary import connectorcatalog
        s = MemoryStore()
        for t in livevoice.TYPES:
            self.assertTrue(s.get_connector_by_type(t), t)
            self.assertEqual(connectorcatalog.by_type(t)['group'], 'AI — live interaction')

    def test_setup_says_which_card_to_open(self):
        s = MemoryStore()
        _on(s, 'live_voice', secret=None)
        with self.assertRaisesRegex(RuntimeError, 'Deepgram card has no key'): livevoice.setup(s)
        _on(s, 'deepgram')
        with self.assertRaisesRegex(RuntimeError, 'Cartesia card has no key'): livevoice.setup(s)
        _on(s, 'cartesia')
        out = livevoice.setup(s)
        self.assertEqual((out['hear']['Type'], out['speak']['Type'], out['hipaa']), ('deepgram', 'cartesia', False))

    def test_only_the_google_pair_is_for_hipaa(self):
        self.assertFalse(livevoice.hipaa_ok({}))
        self.assertFalse(livevoice.hipaa_ok({'hearing': 'google', 'speaking': 'cartesia'}))
        self.assertTrue(livevoice.hipaa_ok({'hearing': 'google', 'speaking': 'google'}))
        s = MemoryStore()
        _on(s, 'live_voice', secret=None, cfg={'hearing': 'google', 'speaking': 'google'}); _on(s, 'google_speech')
        out = livevoice.setup(s)
        self.assertEqual(out['hear']['ConnectorId'], out['speak']['ConnectorId']); self.assertTrue(out['hipaa'])

    def test_cartesia_test_asks_for_his_voice_with_his_key(self):
        cid = _on(server.store, 'cartesia', 'cart-key', {'voice_id': 'v-123'})
        with mock.patch.object(livevoice.requests, 'get', return_value=R(200, {'name': 'Reader'})) as g:
            out = api.post(f'/api/connectors/{cid}/test').json()
        self.assertTrue(out['ok'], out); self.assertIn('Reader', out['detail'])
        self.assertEqual(g.call_args[0][0], 'https://api.cartesia.ai/voices/v-123'); self.assertEqual(g.call_args[1]['headers']['X-API-Key'], 'cart-key')
        with mock.patch.object(livevoice.requests, 'get', return_value=R(401, {'error': 'Invalid API key'})):
            out = api.post(f'/api/connectors/{cid}/test').json()
        self.assertFalse(out['ok']); self.assertIn('turned the key or password down', out['detail'])      # ...said as every card says a 401 (plain_failure)

    def test_google_test_speaks_one_word_and_hears_it_with_an_api_key(self):
        cid = _on(server.store, 'google_speech', 'g-api-key')
        posts = [R(200, {'audioContent': 'UklGRg=='}), R(200, {'results': []})]
        with mock.patch.object(livevoice.requests, 'post', side_effect=posts) as p:
            out = api.post(f'/api/connectors/{cid}/test').json()
        self.assertTrue(out['ok'], out)
        urls = [c[0][0] for c in p.call_args_list]
        self.assertEqual(urls, ['https://texttospeech.googleapis.com/v1/text:synthesize', 'https://speech.googleapis.com/v1/speech:recognize'])
        self.assertEqual(p.call_args[1]['params'], {'key': 'g-api-key'}); self.assertEqual(p.call_args[1]['json']['audio']['content'], 'UklGRg==')

    def test_the_live_card_without_pipecat_offers_install(self):
        cid = server.store.get_connector_by_type('live_voice')['ConnectorId']
        with mock.patch.object(deps, 'installed', side_effect=lambda p: p != 'pipecat'):
            out = api.post(f'/api/connectors/{cid}/test').json()
        self.assertFalse(out['ok']); self.assertEqual(out['install']['package'], 'pipecat'); self.assertEqual(out['install']['name'], 'pipecat-ai')

    def test_the_live_card_tests_both_chosen_cards_and_says_it_is_not_for_hipaa(self):
        s = server.store
        cid = _on(s, 'live_voice', secret=None, cfg={'hearing': 'deepgram', 'speaking': 'cartesia'}); _on(s, 'deepgram'); _on(s, 'cartesia')
        from taskuary import voice
        with mock.patch.object(deps, 'installed', return_value=True), mock.patch.object(voice, 'test', return_value='Deepgram answered') as dg, \
                mock.patch.object(livevoice.requests, 'get', return_value=R(200, {'name': 'Reader'})):
            out = api.post(f'/api/connectors/{cid}/test').json()
        self.assertTrue(out['ok'], out); dg.assert_called_once()
        self.assertIn('Deepgram answered', out['detail']); self.assertIn('Cartesia answered', out['detail']); self.assertIn('not for HIPAA', out['detail'])

    def test_switching_the_card_on_installs_pipecat_in_the_background(self):
        cid = server.store.get_connector_by_type('live_voice')['ConnectorId']
        with mock.patch.object(livevoice, 'ensure') as e:
            api.post('/api/connectors', json={'ConnectorId': cid, 'Active': True})
        e.assert_called_once()

    def test_pipecat_is_pinned_exactly(self):
        self.assertEqual(deps.OPTIONAL['pipecat'], f'pipecat-ai[webrtc,deepgram,cartesia,google]=={livevoice.PIPECAT}')


def _facts(card=None, answer='', aid=None, working=False, steps=()):
    return {'working': working, 'steps': list(steps), 'answer': answer, 'answer_id': aid, 'card': card}


class Brain:
    "A fast model that answers whatever the test tells it to, and records what it was asked."
    def __init__(self, *answers): self.answers, self.asked = list(answers), []
    def __call__(self, system, user, **kw):
        self.asked.append((system, user))
        a = self.answers.pop(0) if self.answers else {'tool': 'hand_to_agent', 'say': ''}
        return a if isinstance(a, str) else json.dumps(a)


class TheFrontOnlyHandsOnReadsAndPresses(unittest.TestCase):
    def front(self, brain, facts=None):
        self.hand, self.press = mock.Mock(), mock.Mock(return_value=(True, ''))
        f = facts if callable(facts) else (lambda *_: facts or _facts())
        return livevoice.Front(None, 7, brain, self.hand, self.press, read=f)

    def test_a_tool_it_does_not_have_hands_his_words_on_exactly(self):
        for bad in ({'tool': 'send_email', 'say': 'Sent!'}, {'tool': 'run_shell', 'say': 'done'}, {'tool': 'close_task'}, 'not json at all'):
            fr = self.front(Brain(bad))
            self.assertEqual(fr.heard('  email   Erin the  numbers '), [livevoice.ACK])
            self.hand.assert_called_once_with('email Erin the numbers'); self.press.assert_not_called()

    def test_read_says_what_is_there_and_does_nothing(self):
        fr = self.front(Brain({'tool': 'read', 'say': 'It is reading the invoices.'}), _facts(working=True, steps=['Read invoices.csv']))
        self.assertEqual(fr.heard("what's it doing"), ['It is reading the invoices.'])
        self.hand.assert_not_called(); self.press.assert_not_called()
        self.assertIn('Read invoices.csv', fr.brain.asked[0][1])

    def test_the_front_holds_only_its_three_tools(self):
        self.assertEqual(livevoice.TOOLS, ('hand_to_agent', 'read', 'press'))
        self.assertEqual(livevoice.WANT['properties']['tool']['enum'], [*livevoice.TOOLS, 'none'])

    def test_a_yes_presses_only_after_the_readback_and_only_once(self):
        state = {'card': {'review': 41, 'readback': 'Send the reply to Gail Moreno, saying: Thursday works.'}}
        fr = self.front(Brain(*[{'tool': 'press', 'say': ''}] * 4), lambda *_: _facts(card=state['card']))
        self.assertEqual(fr.heard('send it'), ['Send the reply to Gail Moreno, saying: Thursday works. Say yes to do it.'])
        self.press.assert_not_called()
        self.assertEqual(fr.heard('yes'), ['Done.']); self.press.assert_called_once_with(41)
        state['card'] = None                                                  # ...pressed, it waits no more
        self.assertEqual(fr.heard('yes'), [livevoice.NO_CARD]); self.press.assert_called_once()
        self.hand.assert_not_called()

    def test_a_yes_to_a_card_that_changed_reads_the_new_one_back_first(self):
        state = {'card': {'review': 41, 'readback': 'Send A'}}
        fr = self.front(Brain(*[{'tool': 'press', 'say': ''}] * 3), lambda *_: _facts(card=state['card']))
        fr.heard('send it')
        state['card'] = {'review': 42, 'readback': 'Send B'}
        self.assertEqual(fr.heard('yes'), ['Send B. Say yes to do it.']); self.press.assert_not_called()
        fr.heard('yes'); self.press.assert_called_once_with(42)

    def test_no_after_a_readback_leaves_it(self):
        fr = self.front(Brain({'tool': 'press', 'say': ''}, {'tool': 'none', 'say': ''}), _facts(card={'review': 5, 'readback': 'Send A'}))
        fr.heard('send it'); self.assertEqual(fr.heard('no, wait'), [livevoice.LEFT]); self.press.assert_not_called()

    def test_news_reads_the_agents_new_words_shortened_then_its_card(self):
        state = {'f': _facts(answer='old', aid='t:1')}
        fr = self.front(Brain('Three invoices: Payworth, Trainly and Spendly.'), lambda *_: state['f'])
        self.assertEqual(fr.news(), [])                                       # ...what was there when he started is not read again
        state['f'] = _facts(answer='The three oldest are from Payworth (March), Trainly (April) and Spendly (May).', aid='t:2',
                            card={'review': 9, 'readback': 'Send the reply to Ray Colton, saying: here they are.'})
        self.assertEqual(fr.news(), ['Three invoices: Payworth, Trainly and Spendly.', 'Send the reply to Ray Colton, saying: here they are. Say yes to do it.'])
        self.assertEqual(fr.news(), [])
        self.assertEqual(fr.asked, 9)                                         # ...so his next yes is to that card


class ASpokenYesPressesThroughTheDecideHandler(unittest.TestCase):
    def test_once_through_decide_with_approve(self):
        seen = []
        def decide(rid, body, background=None): seen.append((rid, body.verb)); return {'ok': True, 'status': 'sent'}
        with mock.patch.object(server, 'decide', side_effect=decide):
            fr = livevoice.Front(None, 3, Brain(*[{'tool': 'press', 'say': ''}] * 2), mock.Mock(), server._live_press,
                                 read=lambda *_: _facts(card={'review': 12, 'readback': 'Send A'}))
            fr.heard('send it'); self.assertEqual(seen, [])
            self.assertEqual(fr.heard('yes'), ['Done.'])
        self.assertEqual(seen, [(12, 'approve')])

    def test_a_press_that_fails_says_so(self):
        with mock.patch.object(server, 'decide', return_value={'ok': False, 'send_error': 'New messages arrived after this draft. Nothing was sent.'}):
            self.assertEqual(server._live_press(12), (False, 'New messages arrived after this draft. Nothing was sent.'))


def _pipecat():
    import importlib.util
    return importlib.util.find_spec('pipecat') is not None


@unittest.skipUnless(_pipecat(), 'Pipecat is an optional package (pip install taskuary[live])')
class ASpokenAskThroughThePipeline(unittest.TestCase):
    """tests/data/live_ask.wav through the real Pipecat pipeline with the real front and VAD: the hearing service is a stub that hears
    the fixture's words once its audio has gone by (no Whisper), the agent a stub that answers, the speaking service records its text."""
    def test_the_words_reach_the_agent_and_its_answer_comes_back_to_speak(self):
        with mock.patch('nltk.download', return_value=True):       # ...its sentence splitter's data, fetched on import, is not this test's
            from pipecat.frames.frames import EndFrame, InputAudioRawFrame, TranscriptionFrame, TTSSpeakFrame, TTSTextFrame
            from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask
        from pipecat.processors.frame_processor import FrameProcessor

        class Hearing(FrameProcessor):
            "Counts the audio that reaches it; when the clip has gone by it hears what the clip says."
            def __init__(self, n): super().__init__(); self.n, self.got = n, 0
            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction)
                if isinstance(frame, InputAudioRawFrame):
                    self.got += 1
                    if self.got == self.n: await self.push_frame(TranscriptionFrame(ASK, 'owner', '2026-11-20T09:00:00Z'))
                    return
                await self.push_frame(frame, direction)

        spoken = []
        class Speaking(FrameProcessor):
            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction)
                if isinstance(frame, TTSSpeakFrame): spoken.append(frame.text); await self.push_frame(TTSTextFrame(frame.text, aggregated_by='sentence'))
                else: await self.push_frame(frame, direction)

        class Through(FrameProcessor):
            async def process_frame(self, frame, direction):
                await super().process_frame(frame, direction); await self.push_frame(frame, direction)

        agent, state = [], {'f': _facts()}
        def hand(words):                       # the task's agent: hears his words, works, answers in its turn
            agent.append(words)
            state['f'] = _facts(answer='The three oldest open invoices are from Payworth, Trainly and Spendly.', aid='t:2')
        brain = Brain({'tool': 'hand_to_agent', 'say': ''}, 'They are from Payworth, Trainly and Spendly.')
        front = livevoice.Front(None, 1, brain, hand, mock.Mock(), read=lambda *_: state['f'])

        with wave.open(str(WAV)) as w:
            rate, ch, pcm = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
        step = rate // 50 * 2 * ch                                           # 20 ms of 16-bit audio
        chunks = [pcm[i:i + step] for i in range(0, len(pcm), step)]
        hearing = Hearing(len(chunks))

        async def run():
            task = PipelineTask(livevoice.pipeline(Through(), hearing, front, Speaking(), Through(), poll=0.05))
            runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
            await asyncio.sleep(0.3)
            for c in chunks: await task.queue_frame(InputAudioRawFrame(audio=c, sample_rate=rate, num_channels=ch))
            for _ in range(200):
                if len(spoken) >= 2: break
                await asyncio.sleep(0.05)
            await task.queue_frame(EndFrame()); await asyncio.wait_for(runner, 20)
        asyncio.run(run())
        self.assertEqual(hearing.got, len(chunks))
        self.assertEqual(agent, [ASK])                                       # ...exactly as spoken, once
        self.assertEqual(spoken, [livevoice.ACK, 'They are from Payworth, Trainly and Spendly.'])


if __name__ == '__main__': unittest.main()

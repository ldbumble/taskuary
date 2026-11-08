"""Voice (voice.py): a voice note always lands - transcribed when an AI voice connector exists,
filed with the reason and the audio attached when not - and the same road serves the mic."""
import base64, json, os, sys, tempfile, types, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import messengers, server, voice, words
from taskuary.store import MemoryStore
VOICE = words.name('voice')      # the voice shelf, by its one name (words.json)

c_api = TestClient(server.app)


class R:
    def __init__(self, code, body, headers=None): self.status_code, self._b, self.text, self.headers = code, body, json.dumps(body), headers or {}
    def json(self): return self._b


def _voice_store(t='groq_stt', secret='k1'):
    s = MemoryStore()
    cid = s.get_connector_by_type(t)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1, **({'Secret': secret} if secret else {})}, 'o')
    return s


class FourAddedOn2026_11_08(unittest.TestCase):
    "AssemblyAI, Speechmatics and Gladia upload, submit and poll; Azure answers in one call - each fed the answers its docs show."
    def run_one(self, t, posts, gets, cfg=None):
        s = _voice_store(t)
        if cfg: s.save_connector({'ConnectorId': s.get_connector_by_type(t)['ConnectorId'], 'ConfigJson': json.dumps(cfg)}, 'o')
        with mock.patch.object(voice.requests, 'post', side_effect=posts) as p, mock.patch.object(voice.requests, 'get', side_effect=gets) as g,                 mock.patch.object(voice.time, 'sleep'):
            out = voice.transcribe(s, b'RIFF', 'audio/wav', 'a.wav')
        return out, p, g

    def test_assemblyai(self):
        out, p, g = self.run_one('assemblyai', [R(200, {'upload_url': 'https://cdn.assemblyai.com/upload/u1'}), R(200, {'id': 't1', 'status': 'queued'})],
                                 [R(200, {'id': 't1', 'status': 'processing'}), R(200, {'id': 't1', 'status': 'completed', 'text': 'aai text'})])
        self.assertEqual(out['text'], 'aai text')
        self.assertEqual(p.call_args_list[0][0][0], 'https://api.assemblyai.com/v2/upload'); self.assertEqual(p.call_args[1]['headers'], {'authorization': 'k1'})
        self.assertEqual(p.call_args[1]['json']['audio_url'], 'https://cdn.assemblyai.com/upload/u1')
        self.assertEqual(g.call_args[0][0], 'https://api.assemblyai.com/v2/transcript/t1')

    def test_speechmatics(self):
        txt = R(200, {}); txt.text = 'sm text'
        out, p, g = self.run_one('speechmatics', [R(201, {'id': 'j1'})], [R(200, {'job': {'id': 'j1', 'status': 'running'}}),
                                 R(200, {'job': {'id': 'j1', 'status': 'done'}}), txt], cfg={'region': 'us1'})
        self.assertEqual(out['text'], 'sm text')
        self.assertEqual(p.call_args[0][0], 'https://us1.asr.api.speechmatics.com/v2/jobs')
        self.assertEqual(json.loads(p.call_args[1]['data']['config'])['type'], 'transcription')
        self.assertEqual((g.call_args[0][0], g.call_args[1]['params']), ('https://us1.asr.api.speechmatics.com/v2/jobs/j1/transcript', {'format': 'txt'}))

    def test_gladia(self):
        out, p, g = self.run_one('gladia', [R(200, {'audio_url': 'https://api.gladia.io/file/f1'}), R(201, {'id': 'g1', 'result_url': 'x'})],
                                 [R(200, {'status': 'processing'}), R(200, {'status': 'done', 'result': {'transcription': {'full_transcript': 'gl text'}}})])
        self.assertEqual(out['text'], 'gl text'); self.assertEqual(p.call_args[1]['headers'], {'x-gladia-key': 'k1'})
        self.assertEqual(g.call_args[0][0], 'https://api.gladia.io/v2/pre-recorded/g1')

    def test_azure_one_call_and_it_needs_an_endpoint(self):
        out, p, _g = self.run_one('azure_speech', [R(200, {'durationMilliseconds': 900, 'combinedPhrases': [{'text': 'az text'}], 'phrases': []})], [],
                                  cfg={'endpoint': 'https://speech-nw.cognitiveservices.azure.com/'})
        self.assertEqual(out['text'], 'az text')
        self.assertEqual(p.call_args[0][0], 'https://speech-nw.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe')
        self.assertEqual(p.call_args[1]['headers'], {'Ocp-Apim-Subscription-Key': 'k1'})
        with self.assertRaisesRegex(RuntimeError, 'endpoint or region'): self.run_one('azure_speech', [], [])

    def test_a_failed_job_says_why(self):
        with self.assertRaisesRegex(RuntimeError, 'AssemblyAI: bad audio'):
            self.run_one('assemblyai', [R(200, {'upload_url': 'u'}), R(200, {'id': 't'})], [R(200, {'status': 'error', 'error': 'bad audio'})])


class ProviderTests(unittest.TestCase):
    def test_no_connector_is_said_the_way_the_owner_can_fix_it(self):
        s = MemoryStore()
        with mock.patch.object(voice, 'builtin', return_value=None):
            self.assertEqual(voice.ready(s), {'ready': False, 'provider': None, 'label': None, 'vocabulary': [], 'builtin': None})
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'x', 'audio/ogg', mic=True)
        self.assertIn(VOICE, str(e.exception)); self.assertIn('Groq', str(e.exception))


class BuiltinVoiceTests(unittest.TestCase):
    """The computer's own voice: Windows voice typing, found with no card. TQ-1283 (the owner, 2026-11-03: "You can't use something that
    doesn't work ... trigger the question if you want to turn that on"): the 2006 System.Speech fallback is gone; voice typing with its
    speech setting off ASKS to be turned on."""
    def test_no_mic_clip_is_heard_by_anything_but_a_card(self):
        s = MemoryStore()
        with mock.patch.object(voice, 'builtin', return_value=voice.LIVE):
            self.assertEqual(voice.ready(s)['builtin'], voice.LIVE); self.assertFalse(voice.ready(s)['ready'])
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'RIFF', 'audio/wav', 'clip.wav', mic=True)
            self.assertIn(VOICE, str(e.exception))
        self.assertFalse(hasattr(voice, '_windows') or hasattr(voice, 'BUILTIN'), 'System.Speech is gone')

    def test_a_card_still_wins(self):
        s = _voice_store('groq_stt')
        with mock.patch.object(voice, 'builtin', return_value=voice.LIVE),              mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'from groq'})):
            self.assertEqual(voice.ready(s)['builtin'], None)
            self.assertEqual(voice.transcribe(s, b'RIFF', 'audio/wav', mic=True)['provider'], 'groq_stt')

    def test_off_windows_nothing_is_found(self):
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'linux'):
            self.assertIsNone(voice.builtin())

    def test_voice_typing_with_its_setting_off_asks_and_never_falls_back(self):
        win = lambda live: (mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'win32'),
                            mock.patch.object(voice, '_live_ok', return_value=live))
        a, b, c = win(True)
        with a, b, c, mock.patch.object(voice, 'speech_on', return_value=True): self.assertEqual(voice.builtin(), voice.LIVE)
        a, b, c = win(True)
        with a, b, c, mock.patch.object(voice, 'speech_on', return_value=False):
            self.assertEqual(voice.builtin(), {**voice.LIVE, 'ask': voice.SPEECH_ASK})
            with mock.patch.object(voice, 'speech_on', return_value=True): self.assertEqual(voice.builtin(), voice.LIVE, 'on at the next press, no restart')
        a, b, c = win(False)
        with a, b, c, mock.patch.object(voice, 'speech_on', return_value=True):
            self.assertIsNone(voice.builtin(), 'no voice typing: nothing worse stands in')
        self.assertIn('Microsoft', voice.SPEECH_ASK)
        self.assertEqual(voice._why('the speech privacy policy was not accepted'), "Voice typing stopped: " + voice._LIVE_WHY['privacy'])

    def test_privacy_does_not_hide_the_enable_prompt_when_compilation_would_fail(self):
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'win32'), \
             mock.patch.object(voice, 'speech_on', return_value=False), mock.patch.object(voice, '_live_ok', return_value=False) as probe:
            self.assertEqual(voice.builtin()['ask'], voice.SPEECH_ASK)
            probe.assert_not_called()

    def test_a_failed_probe_recovers_without_restarting_after_the_cooldown(self):
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'win32'), \
             mock.patch.object(voice, 'speech_on', return_value=True), mock.patch.object(voice, '_live_ok', side_effect=[False, True]) as probe, \
             mock.patch.object(voice.time, 'monotonic', side_effect=[100, 110, 131, 131]):
            self.assertIsNone(voice.builtin())
            self.assertIsNone(voice.builtin())
            self.assertEqual(voice.builtin(), voice.LIVE)
            self.assertEqual(probe.call_count, 2)

    def test_explicit_builtin_status_is_available_even_with_a_connected_voice_card(self):
        here = TestClient(server.app, client=('127.0.0.1', 5000))
        there = TestClient(server.app, client=('192.168.1.20', 5000))
        with mock.patch.object(server, 'store', _voice_store()), mock.patch.object(voice, 'builtin', return_value=voice.LIVE):
            self.assertIsNone(here.get('/api/voice/status').json()['builtin'])
            self.assertEqual(here.get('/api/voice/status?builtin=true').json()['builtin'], voice.LIVE)
            self.assertIsNone(there.get('/api/voice/status?builtin=true').json()['builtin'])

    def test_a_manual_refresh_retries_a_recent_failed_probe(self):
        with mock.patch.dict(voice._HAS, {'live': False, 'checked': voice.time.monotonic()}, clear=True), \
             mock.patch.object(voice.sys, 'platform', 'win32'), mock.patch.object(voice, 'speech_on', return_value=True), \
             mock.patch.object(voice, '_live_ok', return_value=True) as probe:
            self.assertEqual(voice.builtin(refresh=True), voice.LIVE)
            probe.assert_called_once()

    def test_a_yes_writes_the_setting_windows_own_toggle_writes(self):
        vals = {}
        class K:
            def __enter__(s): return s
            def __exit__(s, *a): pass
        reg = types.SimpleNamespace(HKEY_CURRENT_USER='HKCU', KEY_SET_VALUE=2, REG_DWORD=4, CreateKeyEx=lambda *a: K(), OpenKey=lambda *a: K(),
                                    SetValueEx=lambda k, n, _, t, v: vals.__setitem__(n, (t, v)), QueryValueEx=lambda k, n: (vals[n][1], 4) if n in vals else (_ for _ in ()).throw(OSError()))
        with mock.patch.dict(sys.modules, {'winreg': reg}):
            self.assertFalse(voice.speech_on(), "Windows' default: never set is off")
            self.assertTrue(voice.turn_on_speech()); self.assertEqual(vals['HasAccepted'], (4, 1)); self.assertTrue(voice.speech_on())

    def test_the_yes_is_served_only_on_this_computer_and_audited(self):
        here, there = TestClient(server.app, client=('127.0.0.1', 5000)), TestClient(server.app, client=('192.168.1.20', 5000))
        st = MemoryStore()
        with mock.patch.object(server, 'store', st), mock.patch.object(voice, 'turn_on_speech', return_value=True) as on,              mock.patch.object(voice, 'builtin', return_value=voice.LIVE):
            self.assertEqual(there.post('/api/voice/speech-on').status_code, 409); on.assert_not_called()
            r = here.post('/api/voice/speech-on'); self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['builtin'], voice.LIVE)
        with mock.patch.object(server, 'store', st), mock.patch.object(voice, 'turn_on_speech', return_value=False):
            r = here.post('/api/voice/speech-on'); self.assertEqual(r.status_code, 409); self.assertIn('speech privacy', r.json()['detail'])
        from taskuary import guard
        self.assertEqual(guard.classify('POST', '/api/voice/speech-on')[0], 'owner')

    def test_the_probe_asks_a_powershell_child_for_winrt_dictation(self):
        from taskuary import spawn
        seen = {}
        def run(argv, **kw): seen.update(argv=argv, env=kw['env']); return types.SimpleNamespace(returncode=0, stdout=b'ok', stderr=b'')
        with mock.patch.object(spawn, 'run', run): self.assertTrue(voice._live_ok())
        script = base64.b64decode(seen['argv'][-1]).decode('utf-16-le')
        self.assertIn('Windows.Media.SpeechRecognition.SpeechRecognizer', script); self.assertEqual(seen['env']['TQ_PROBE'], '1')
        no = lambda argv, **kw: types.SimpleNamespace(returncode=2, stdout=b'', stderr=b'speech privacy policy was not accepted')
        with mock.patch.object(spawn, 'run', no): self.assertFalse(voice._live_ok())
        with mock.patch.object(spawn, 'run', side_effect=FileNotFoundError('powershell')): self.assertFalse(voice._live_ok())

    def test_a_listening_session_lands_each_phrase_and_stops_on_the_press(self):
        """The real child is checked by hand on Windows (the suite allows no child process): a stand-in prints what it prints."""
        from taskuary import spawn
        import io as _io, threading as _th
        class Child:
            def __init__(self, out, code=0, err=b''): self.stdout, self.stderr, self.returncode, self._go = _io.BytesIO(out), _io.BytesIO(err), code, _th.Event()
            def wait(self, timeout=None): return self.returncode
            def kill(self): pass
        made = []
        def popen(argv, **kw): made.append(kw['env']['TQ_STOP']); return Child(b'.\r\n+call Erin back\r\n+about the payroll report\r\n')
        with mock.patch.object(voice, 'builtin', return_value=voice.LIVE), mock.patch.object(spawn, 'popen', popen):
            sid = voice.listen_start()
            voice._LISTEN['cur']['reader'].join(2)
            self.assertEqual(voice.listen_poll(sid), {'said': ['call Erin back', 'about the payroll report'], 'ready': True, 'done': True, 'error': ''})
            self.assertEqual(voice.listen_poll(sid, 1)['said'], ['about the payroll report'])
            self.assertIsNone(voice.listen_poll('nope'))
            self.assertEqual(voice.listen_stop(sid, 2)['said'], [])
            self.assertIsNone(voice.listen_stop(sid), 'a stopped session is gone')
            self.assertFalse(os.path.exists(made[0]), 'the stop file does not outlive the session')
        bad = lambda argv, **kw: Child(b'', 2, b'MicrophoneUnavailable')
        with mock.patch.object(voice, 'builtin', return_value=voice.LIVE), mock.patch.object(spawn, 'popen', bad):
            sid = voice.listen_start(); voice._LISTEN['cur']['reader'].join(2)
            self.assertIn('Let desktop apps access your microphone', voice.listen_stop(sid)['error'])
        with mock.patch.object(voice, 'builtin', return_value=None), self.assertRaises(RuntimeError): voice.listen_start()
        with mock.patch.object(voice, 'builtin', return_value={**voice.LIVE, 'ask': voice.SPEECH_ASK}), self.assertRaises(RuntimeError): voice.listen_start()

    def test_voice_typing_serves_only_a_page_on_this_computer(self):
        here, there = TestClient(server.app, client=('127.0.0.1', 5000)), TestClient(server.app, client=('192.168.1.20', 5000))
        with mock.patch.object(voice, 'builtin', return_value=voice.LIVE), mock.patch.object(server, 'store', MemoryStore()):
            self.assertEqual(here.get('/api/voice/status').json()['builtin'], voice.LIVE)
            self.assertIsNone(there.get('/api/voice/status').json()['builtin'])
            with mock.patch.object(voice, 'listen_start') as start:
                self.assertEqual(there.post('/api/voice/listen').status_code, 409); start.assert_not_called()
            self.assertEqual(here.get('/api/voice/listen/abc123').status_code, 404)
        from taskuary import guard
        for path in ('/api/voice/listen', '/api/voice/listen/abc123/stop'): self.assertEqual(guard.classify('POST', path)[0], 'owner', path)

    def test_groq_and_openai_ride_the_openai_shape_with_their_own_defaults(self):
        for t, host, model in (('groq_stt', 'api.groq.com/openai/v1', 'whisper-large-v3-turbo'),
                               ('openai_stt', 'api.openai.com/v1', 'gpt-4o-mini-transcribe')):
            s = _voice_store(t)
            with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': ' hello there '})) as p:
                out = voice.transcribe(s, b'OggS...', 'audio/ogg; codecs=opus', 'note.ogg')
            self.assertEqual(out, {'text': 'hello there', 'provider': t, 'model': model})
            self.assertIn(f'{host}/audio/transcriptions', p.call_args[0][0])
            self.assertEqual(p.call_args[1]['headers'], {'Authorization': 'Bearer k1'})
            self.assertEqual(p.call_args[1]['data']['model'], model)
            self.assertEqual(p.call_args[1]['files']['file'][2], 'audio/ogg')             # the codec suffix never reaches the API

    def test_a_local_server_needs_no_key_and_a_refused_key_says_so(self):
        s = _voice_store('stt_server', secret=None)
        s.save_connector({'ConnectorId': s.get_connector_by_type('stt_server')['ConnectorId'],
                          'ConfigJson': json.dumps({'base_url': 'http://127.0.0.1:8000/v1/', 'model': 'small'})}, 'o')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'local'})) as p:
            self.assertEqual(voice.transcribe(s, b'x', 'audio/wav')['text'], 'local')
        self.assertEqual(p.call_args[0][0], 'http://127.0.0.1:8000/v1/audio/transcriptions'); self.assertEqual(p.call_args[1]['headers'], {})
        s2 = _voice_store('groq_stt')
        with mock.patch.object(voice.requests, 'post', return_value=R(401, {'error': 'bad key'})):
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s2, b'x')
        self.assertIn('key was refused', str(e.exception))

    def test_deepgram_and_elevenlabs_have_their_own_shapes(self):
        s = _voice_store('deepgram')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'results': {'channels': [{'alternatives': [{'transcript': 'dg text'}]}]}})) as p:
            out = voice.transcribe(s, b'x', 'audio/ogg')
        self.assertEqual((out['text'], out['model']), ('dg text', 'nova-3'))
        self.assertEqual(p.call_args[1]['headers']['Authorization'], 'Token k1'); self.assertEqual(p.call_args[1]['params']['model'], 'nova-3')
        s = _voice_store('elevenlabs_stt')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'el text'})) as p:
            self.assertEqual(voice.transcribe(s, b'x', 'audio/ogg')['text'], 'el text')
        self.assertEqual(p.call_args[1]['headers'], {'xi-api-key': 'k1'}); self.assertEqual(p.call_args[1]['data']['model_id'], 'scribe_v2')

    def test_one_shared_vocabulary_reaches_every_existing_provider_shape(self):
        terms = ['Taskuary', 'Payworth']
        for t in ('groq_stt', 'openai_stt', 'stt_server'):
            s = _voice_store(t, secret=None if t == 'stt_server' else 'k1'); voice.save_vocabulary(s, terms)
            with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'ok'})) as p:
                voice.transcribe(s, b'x', 'audio/wav')
            self.assertEqual(p.call_args[1]['data']['prompt'], 'Taskuary, Payworth')
        s = _voice_store('deepgram'); voice.save_vocabulary(s, terms)
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'results': {'channels': [{'alternatives': [{'transcript': 'ok'}]}]}})) as p:
            voice.transcribe(s, b'x', 'audio/wav')
        self.assertEqual(p.call_args[1]['params']['keyterm'], terms)
        s = _voice_store('elevenlabs_stt'); voice.save_vocabulary(s, terms)
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'ok'})) as p:
            voice.transcribe(s, b'x', 'audio/wav')
        self.assertEqual(p.call_args[1]['data']['keyterms'], terms)

    def test_gpt_transcribe_receives_native_keywords_and_language(self):
        s = _voice_store('openai_stt'); cid = s.get_connector_by_type('openai_stt')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'model': 'gpt-transcribe', 'language': 'en'})}, 'o')
        voice.save_vocabulary(s, ['Taskuary', 'Payworth'])
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'ok'})) as p:
            voice.transcribe(s, b'x', 'audio/wav')
        self.assertEqual(p.call_args[1]['data']['keywords[]'], ['Taskuary', 'Payworth'])
        self.assertEqual(p.call_args[1]['data']['languages[]'], ['en'])

    def test_local_whisper_receives_the_shared_vocabulary_as_its_initial_prompt(self):
        calls = []
        class FakeModel:
            def __init__(self, *a, **kw): pass
            def transcribe(self, path, **kw): calls.append(kw); return [types.SimpleNamespace(text=' local text ')], None
        s = _voice_store('local_whisper', secret=None); voice.save_vocabulary(s, ['Taskuary', 'Spendly Card']); voice._LOCAL.clear()
        with mock.patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            self.assertEqual(voice.transcribe(s, b'wav', 'audio/wav')['text'], 'local text')
        self.assertEqual(calls[0]['initial_prompt'], 'Taskuary, Spendly Card')

    def test_gemini_uploads_transcribes_with_vocabulary_and_deletes_the_clip(self):
        s = _voice_store('gemini_stt'); voice.save_vocabulary(s, ['Taskuary', 'Payworth'])
        replies = [R(200, {}, {'X-Goog-Upload-URL': 'https://upload.example/one'}),
                   R(200, {'file': {'name': 'files/one', 'uri': 'https://files.example/one', 'state': 'ACTIVE'}}),
                   R(200, {'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'queue TQ-0243'}]}]})]
        with mock.patch.object(voice.requests, 'post', side_effect=replies) as p, mock.patch.object(voice.requests, 'delete') as d:
            out = voice.transcribe(s, b'webm', 'audio/webm', 'clip.webm')
        self.assertEqual(out, {'text': 'queue TQ-0243', 'provider': 'gemini_stt', 'model': 'gemini-3.5-transcribe'})
        payload = p.call_args_list[2].kwargs['json']
        self.assertEqual(payload['generation_config']['transcription_config']['custom_vocabulary'], ['Taskuary', 'Payworth'])
        self.assertEqual(payload['input'][0]['mime_type'], 'audio/webm')
        self.assertEqual(payload['input'][0]['uri'], 'https://files.example/one')   # Gemini's own field name
        d.assert_called_once_with('https://generativelanguage.googleapis.com/v1beta/files/one', headers={'x-goog-api-key': 'k1'}, timeout=30)

    def test_vocabulary_is_normalized_validated_and_persisted_once_for_the_system(self):
        s = MemoryStore()
        self.assertEqual(voice.save_vocabulary(s, [' Taskuary ', 'taskuary', 'Payworth']), ['Taskuary', 'Payworth'])
        self.assertEqual(voice.vocabulary(s), ['Taskuary', 'Payworth'])
        with self.assertRaises(ValueError): voice.save_vocabulary(s, ['six word phrases are not accepted here'])
        with self.assertRaises(ValueError): voice.save_vocabulary(s, ['x' * 51])
        with self.assertRaises(ValueError): voice.save_vocabulary(s, [f'term {i}' for i in range(101)])

    def test_the_test_clip_is_a_second_of_silence_through_the_real_endpoint(self):
        s = _voice_store('groq_stt')
        wav = voice.silence_wav()
        self.assertEqual(wav[:4], b'RIFF'); self.assertGreater(len(wav), 30000)
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': ''})):
            self.assertIn('transcription works', voice.test(s, s.get_connector_by_type('groq_stt', with_secret=True)))

    def test_note_body_is_the_transcript_or_the_honest_placeholder(self):
        s = MemoryStore()
        body, ok, why = voice.note_body(s, b'x', 'audio/ogg', 'v.ogg', 7, 'WhatsApp')
        self.assertFalse(ok); self.assertTrue(voice.is_placeholder(body)); self.assertIn('(7s) from WhatsApp', body); self.assertIn(VOICE, body)
        s = _voice_store('groq_stt')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'please call the vendor back'})):
            body, ok, _ = voice.note_body(s, b'x', 'audio/ogg', 'v.ogg', 7, 'WhatsApp')
        self.assertTrue(ok); self.assertTrue(body.startswith('please call the vendor back')); self.assertIn('transcribed by Groq (Whisper)', body)
        self.assertFalse(voice.is_placeholder(body))


class FunnelTests(unittest.TestCase):
    def _wa(self, s):
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
        # WhatsApp has no catch-all - a paired account sees every chat its owner is in - so the
        # chat this test feeds is named, the way a real install names one (2026-09-17)
        s.save_source({'Channel': 'whatsapp', 'Address': '155@s.whatsapp.net', 'ConnectorId': cid, 'Active': 1}, 'o')
        return s.get_connector_by_type('whatsapp', with_secret=True)

    def test_a_whatsapp_voice_note_lands_even_with_nothing_to_transcribe_it(self):
        s = MemoryStore(); c = self._wa(s)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f: f.write(b'OggS voice bytes'); path = f.name
        try:
            feed = {'seq': 1, 'messages': [{'seq': 1, 'id': 'v1', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': '',
                                            'audio': path, 'mime': 'audio/ogg; codecs=opus', 'seconds': 9, 'voice': True, 'ts': 1755700000}]}
            with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
                n = messengers.poll_whatsapp(s, c, s.list_sources(), llm=lambda *a: '{"intent": "task", "why": "t"}')
        finally: os.unlink(path)
        self.assertEqual(n, 1)
        m = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]
        self.assertTrue(voice.is_placeholder(m['BodyText'])); self.assertEqual(m['Status'], 'feed')   # shown, not a task, never skipped
        self.assertIn('voice note - not transcribed', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])
        atts = s.list_attachments(m['MessageId'])
        self.assertEqual((len(atts), atts[0]['ContentType']), (1, 'audio/ogg')); self.assertTrue(atts[0]['Path'])
        # a connector arrives later: one click transcribes what was kept
        s.save_connector({'ConnectorId': s.get_connector_by_type('groq_stt')['ConnectorId'], 'Active': 1, 'Secret': 'k'}, 'o')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'the export is broken again'})):
            out = voice.transcribe_message(s, m['MessageId'])
        self.assertEqual(out['text'], 'the export is broken again')
        self.assertTrue(s.get_message(m['MessageId'])['BodyText'].startswith('the export is broken again'))

    def test_a_transcribed_voice_note_goes_through_triage_like_text(self):
        s = _voice_store('groq_stt'); c = self._wa(s)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f: f.write(b'OggS'); path = f.name
        try:
            feed = {'seq': 1, 'messages': [{'seq': 1, 'id': 'v2', 'jid': '155@s.whatsapp.net', 'name': 'Marcus', 'text': '',
                                            'audio': path, 'mime': 'audio/ogg', 'seconds': 4, 'ts': 1755700000}]}
            with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed), \
                 mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'the importer crashes on the payroll file'})):
                messengers.poll_whatsapp(s, c, s.list_sources(), llm=lambda *a: '{"intent": "task", "kind": "coding", "why": "t"}')
        finally: os.unlink(path)
        m = s._rows("SELECT * FROM message WHERE Channel='whatsapp'")[0]
        self.assertTrue(m['BodyText'].startswith('the importer crashes')); self.assertEqual(m['Status'], 'routed'); self.assertTrue(m['TaskId'])

    def test_the_mic_posts_raw_bytes_and_gets_text(self):
        with mock.patch.object(voice, 'transcribe', return_value={'text': 'queue the payroll fix', 'provider': 'groq_stt', 'model': 'w'}) as t:
            r = c_api.post('/api/voice/transcribe', content=b'webm bytes', headers={'content-type': 'audio/webm;codecs=opus'})
        self.assertEqual((r.status_code, r.json()['text']), (200, 'queue the payroll fix'))
        self.assertEqual((t.call_args[0][2], t.call_args[0][3]), ('audio/webm', 'clip.webm'))
        self.assertIs(t.call_args[1].get('mic'), True)        # the mic's clip may fall to the computer's own recogniser
        self.assertEqual(c_api.post('/api/voice/transcribe', content=b'').status_code, 422)
        with mock.patch.object(voice, 'transcribe', side_effect=RuntimeError(voice.NO_CONNECTOR)):
            r = c_api.post('/api/voice/transcribe', content=b'x', headers={'content-type': 'audio/webm'})
        self.assertEqual(r.status_code, 409); self.assertIn(VOICE, r.json()['detail'])
        self.assertIn('ready', c_api.get('/api/voice/status').json())

    def test_voice_vocabulary_api_is_shared_validated_and_audited(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s):
            r = c_api.put('/api/voice/vocabulary', json={'terms': [' Taskuary ', 'Payworth', 'taskuary']})
            self.assertEqual(r.json(), {'terms': ['Taskuary', 'Payworth'], 'limit': 100})
            self.assertEqual(c_api.get('/api/voice/vocabulary').json()['terms'], ['Taskuary', 'Payworth'])
            self.assertEqual(c_api.get('/api/voice/status').json()['vocabulary'], ['Taskuary', 'Payworth'])
            self.assertEqual(s._rows("SELECT Action FROM audit WHERE Action='voice_vocabulary'")[0]['Action'], 'voice_vocabulary')
            self.assertEqual(c_api.put('/api/voice/vocabulary', json={'terms': ['x' * 51]}).status_code, 422)


class VoiceToTheAssistantTests(unittest.TestCase):
    """The owner, 2026-09-24: "i sent whatsapp voice note to taskuary ... nothing came through to the assistant".
    A note in the Assistant's own chat had no text for the interceptors and was not an inbound source, so it was
    dropped without a trace. It is heard first now, and the words reach the Assistant as if typed."""
    ME = '15550100100@s.whatsapp.net'

    def _setup(self, s):
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'ConfigJson': json.dumps({'assistant_chat': self.ME})}, 'o')
        return s.get_connector_by_type('whatsapp', with_secret=True)

    def _feed(self, path):
        return {'seq': 1, 'messages': [{'seq': 1, 'id': 'v9', 'jid': self.ME, 'fromMe': True, 'text': '', 'audio': path,
                                        'mime': 'audio/ogg', 'seconds': 17, 'ptt': True, 'ts': 1755700000}]}

    def test_a_voice_note_in_the_assistant_chat_reaches_the_assistant_as_words(self):
        from taskuary import remote_assistant
        s = _voice_store('groq_stt'); c = self._setup(s)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f: f.write(b'OggS'); path = f.name
        heard = []
        try:
            with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: self._feed(path)), \
                 mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'walk me through my tasks'})), \
                 mock.patch.object(remote_assistant, 'intercept', lambda store, ch, jid, text, **kw: heard.append((jid, text)) or True):
                messengers.poll_whatsapp(s, c, s.list_sources())
        finally: os.unlink(path)
        self.assertEqual(heard, [(self.ME, 'walk me through my tasks')])

    def test_one_it_cannot_hear_says_so_in_the_chat(self):
        from taskuary import remote_assistant
        s = MemoryStore(); c = self._setup(s)                       # no voice connector at all
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f: f.write(b'OggS'); path = f.name
        said, heard = [], []
        try:
            with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: self._feed(path)), \
                 mock.patch.object(remote_assistant, 'send', lambda store, ch, jid, text, cid=None: said.append(text)), \
                 mock.patch.object(remote_assistant, 'intercept', lambda *a, **kw: heard.append(a) or True):
                messengers.poll_whatsapp(s, c, s.list_sources())
        finally: os.unlink(path)
        self.assertEqual(heard, [])
        self.assertEqual(len(said), 1)
        self.assertIn('could not hear that voice note', said[0])


class TelegramVoiceToTheAssistantTests(unittest.TestCase):
    """The owner, 2026-10-02: "yes fix the transcribe thing for telegram" - a Telegram voice note to the Assistant chat
    was dropped, the interceptor reading text only. It is heard first now, through the same transcriber as WhatsApp."""
    ME, TOKEN = '4242', '123:secret-bot-token'

    def _setup(self, s):
        cid = s.get_connector_by_type('telegram')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': self.TOKEN, 'ConfigJson': json.dumps({'assistant_chat': self.ME})}, 'o')
        return s.get_connector_by_type('telegram', with_secret=True)

    def _tg(self, token, method, **kw):
        if method == 'getUpdates':
            return [{'update_id': 7, 'message': {'message_id': 31, 'chat': {'id': int(self.ME), 'type': 'private'},
                                                 'from': {'id': int(self.ME), 'first_name': 'Alex'},
                                                 'voice': {'file_id': 'f1', 'duration': 4, 'mime_type': 'audio/ogg'}}}]
        if method == 'getFile': return {'file_path': 'voice/file_1.oga'}
        return {}

    def test_a_voice_note_in_the_assistant_chat_reaches_the_assistant_as_words(self):
        from taskuary import remote_assistant
        s = _voice_store('groq_stt'); c = self._setup(s)
        heard = []
        with mock.patch.object(messengers, 'tg', self._tg), \
             mock.patch.object(messengers.requests, 'get', return_value=types.SimpleNamespace(content=b'OggS')), \
             mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'walk me through my tasks'})), \
             mock.patch.object(remote_assistant, 'enabled', return_value=True), \
             mock.patch.object(remote_assistant, 'intercept', lambda store, ch, chat, text, **kw: heard.append((ch, chat, text)) or True):
            messengers.poll_telegram(s, c, s.list_sources())
        self.assertEqual(heard, [('telegram', self.ME, 'walk me through my tasks')])

    def test_one_it_cannot_hear_says_so_in_the_chat_and_never_logs_the_token(self):
        from taskuary import remote_assistant
        s = MemoryStore(); c = self._setup(s)                       # no voice connector at all
        said, heard = [], []
        with mock.patch.object(messengers, 'tg', self._tg), \
             mock.patch.object(messengers.requests, 'get', return_value=types.SimpleNamespace(content=b'OggS')), \
             mock.patch.object(remote_assistant, 'enabled', return_value=True), \
             mock.patch.object(remote_assistant, 'send', lambda store, ch, chat, text, cid=None: said.append((ch, text))), \
             mock.patch.object(remote_assistant, 'intercept', lambda *a, **kw: heard.append(a) or True):
            messengers.poll_telegram(s, c, s.list_sources())
        self.assertEqual(heard, [])
        self.assertEqual(len(said), 1)
        self.assertEqual(said[0][0], 'telegram')
        self.assertIn('could not hear that voice note', said[0][1])
        # ...and a download that fails names no token in the log
        with mock.patch.object(messengers, 'tg', self._tg), \
             mock.patch.object(messengers.requests, 'get', side_effect=RuntimeError(f'bad url https://x/file/bot{self.TOKEN}/v.oga')), \
             mock.patch.object(messengers.logger, 'warning') as warned:
            self.assertIsNone(messengers._tg_file(self.TOKEN, {'file_id': 'f1'}, 'voice.ogg'))
        self.assertNotIn(self.TOKEN, str(warned.call_args))

    def test_a_note_in_a_chat_that_is_not_the_assistants_is_never_transcribed(self):
        from taskuary import remote_assistant
        s = _voice_store('groq_stt'); c = self._setup(s)
        with mock.patch.object(messengers, 'tg', self._tg), \
             mock.patch.object(messengers.requests, 'get', return_value=types.SimpleNamespace(content=b'OggS')), \
             mock.patch.object(voice.requests, 'post') as stt, \
             mock.patch.object(remote_assistant, 'enabled', return_value=False):
            messengers.poll_telegram(s, c, s.list_sources())
        stt.assert_not_called()

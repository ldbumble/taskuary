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


class ProviderTests(unittest.TestCase):
    def test_no_connector_is_said_the_way_the_owner_can_fix_it(self):
        s = MemoryStore()
        with mock.patch.dict(voice._HAS, {'v': None}):
            self.assertEqual(voice.ready(s), {'ready': False, 'provider': None, 'label': None, 'vocabulary': [], 'builtin': None})
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'x', 'audio/ogg', mic=True)
        self.assertIn(VOICE, str(e.exception)); self.assertIn('Groq', str(e.exception))


class BuiltinVoiceTests(unittest.TestCase):
    """The owner, 2026-11-01: "local voice using microsoft edge is not working. it should be built in without having to turn it on if it
    finds it". With no card, the computer's own recogniser (Windows' System.Speech) hears the mic - found, never configured."""
    def test_found_with_no_card_it_is_reported_and_hears_the_mics_wav(self):
        s = MemoryStore()
        with mock.patch.dict(voice._HAS, {'v': voice.BUILTIN}), mock.patch.object(voice, '_windows', return_value=' call Erin back ') as w:
            self.assertEqual(voice.ready(s)['builtin'], voice.BUILTIN); self.assertFalse(voice.ready(s)['ready'])
            self.assertEqual(voice.transcribe(s, b'RIFF', 'audio/wav', 'clip.wav', mic=True),
                             {'text': 'call Erin back', 'provider': 'windows_speech', 'model': 'System.Speech dictation'})
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'webm', 'audio/webm', mic=True)
            self.assertIn('WAV', str(e.exception))
            # a voice note is no mic clip: Ogg it cannot read, so it still says how to set up a card
            with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'OggS', 'audio/ogg')
            self.assertIn(VOICE, str(e.exception))
        self.assertEqual(w.call_count, 1)

    def test_a_card_still_wins(self):
        s = _voice_store('groq_stt')
        with mock.patch.dict(voice._HAS, {'v': voice.BUILTIN}), mock.patch.object(voice, '_windows') as w, \
             mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'from groq'})):
            self.assertEqual(voice.ready(s)['builtin'], None)
            self.assertEqual(voice.transcribe(s, b'RIFF', 'audio/wav', mic=True)['provider'], 'groq_stt')
        w.assert_not_called()

    def test_off_windows_nothing_is_found(self):
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'linux'):
            self.assertIsNone(voice.builtin())

    def test_the_clip_goes_to_a_powershell_child_by_file_and_is_removed(self):
        """The real run is checked by hand on Windows (the suite allows no child process): this pins what the child is handed."""
        from taskuary import spawn
        seen = {}
        def run(argv, **kw):
            seen.update(argv=argv, path=kw['env']['TQ_WAV'], timeout=kw['timeout'])
            with open(seen['path'], 'rb') as f: seen['data'] = f.read()
            return types.SimpleNamespace(returncode=0, stdout='call Erin back'.encode(), stderr=b'')
        with mock.patch.object(spawn, 'run', run): self.assertEqual(voice._windows(b'RIFF....WAVE'), 'call Erin back')
        self.assertEqual(seen['argv'][:2], ['powershell', '-NoProfile']); self.assertEqual(seen['data'], b'RIFF....WAVE')
        script = base64.b64decode(seen['argv'][-1]).decode('utf-16-le')
        self.assertIn('DictationGrammar', script); self.assertIn('$env:TQ_WAV', script)
        self.assertFalse(os.path.exists(seen['path']), 'the clip does not outlive the call')
        bad = lambda argv, **kw: types.SimpleNamespace(returncode=2, stdout=b'', stderr=b'Wave file not valid.')
        with mock.patch.object(spawn, 'run', bad), self.assertRaises(RuntimeError) as e: voice._windows(b'x')
        self.assertIn('Wave file not valid', str(e.exception))

    def test_windows_voice_typing_comes_first_and_system_speech_says_how_to_reach_it(self):
        """The owner, 2026-11-02: "do the changes to use desktop if the machine has it" - System.Speech is only the last resort."""
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'win32'), mock.patch.object(voice, '_live_ok', return_value=True):
            self.assertEqual(voice.builtin(), voice.LIVE)
        reg = types.SimpleNamespace(HKEY_LOCAL_MACHINE=0, OpenKey=mock.MagicMock(), QueryInfoKey=lambda k: (1,))
        with mock.patch.dict(voice._HAS, clear=True), mock.patch.object(voice.sys, 'platform', 'win32'), \
             mock.patch.object(voice, '_live_ok', return_value=False), mock.patch.dict(sys.modules, {'winreg': reg}):
            self.assertEqual(voice.builtin(), {**voice.BUILTIN, 'hint': voice.SPEECH_OFF})
        self.assertIn('Online speech recognition', voice.SPEECH_OFF)

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
        with mock.patch.dict(voice._HAS, {'v': voice.LIVE}), mock.patch.object(spawn, 'popen', popen):
            sid = voice.listen_start()
            voice._LISTEN['cur']['reader'].join(2)
            self.assertEqual(voice.listen_poll(sid), {'said': ['call Erin back', 'about the payroll report'], 'ready': True, 'done': True, 'error': ''})
            self.assertEqual(voice.listen_poll(sid, 1)['said'], ['about the payroll report'])
            self.assertIsNone(voice.listen_poll('nope'))
            self.assertEqual(voice.listen_stop(sid, 2)['said'], [])
            self.assertIsNone(voice.listen_stop(sid), 'a stopped session is gone')
            self.assertFalse(os.path.exists(made[0]), 'the stop file does not outlive the session')
        bad = lambda argv, **kw: Child(b'', 2, b'MicrophoneUnavailable')
        with mock.patch.dict(voice._HAS, {'v': voice.LIVE}), mock.patch.object(spawn, 'popen', bad):
            sid = voice.listen_start(); voice._LISTEN['cur']['reader'].join(2)
            self.assertIn('Let desktop apps access your microphone', voice.listen_stop(sid)['error'])
        with mock.patch.dict(voice._HAS, {'v': voice.BUILTIN}), self.assertRaises(RuntimeError): voice.listen_start()

    def test_voice_typing_serves_only_a_page_on_this_computer(self):
        here, there = TestClient(server.app, client=('127.0.0.1', 5000)), TestClient(server.app, client=('192.168.1.20', 5000))
        with mock.patch.dict(voice._HAS, {'v': voice.LIVE}), mock.patch.object(server, 'store', MemoryStore()):
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

"""Voice (voice.py): a voice note always lands - transcribed when an AI voice connector exists,
filed with the reason and the audio attached when not - and the same road serves the mic."""
import base64, json, os, sys, tempfile, types, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import messengers, server, voice
from taskuary.store import MemoryStore

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
        self.assertEqual(voice.ready(s), {'ready': False, 'provider': None, 'label': None, 'vocabulary': []})
        with self.assertRaises(RuntimeError) as e: voice.transcribe(s, b'x', 'audio/ogg')
        self.assertIn('AI - voice', str(e.exception)); self.assertIn('Groq', str(e.exception))

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
        terms = ['Taskuary', 'PointClickCare']
        for t in ('groq_stt', 'openai_stt', 'stt_server'):
            s = _voice_store(t, secret=None if t == 'stt_server' else 'k1'); voice.save_vocabulary(s, terms)
            with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'ok'})) as p:
                voice.transcribe(s, b'x', 'audio/wav')
            self.assertEqual(p.call_args[1]['data']['prompt'], 'Taskuary, PointClickCare')
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
        voice.save_vocabulary(s, ['Taskuary', 'PointClickCare'])
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'ok'})) as p:
            voice.transcribe(s, b'x', 'audio/wav')
        self.assertEqual(p.call_args[1]['data']['keywords[]'], ['Taskuary', 'PointClickCare'])
        self.assertEqual(p.call_args[1]['data']['languages[]'], ['en'])

    def test_local_whisper_receives_the_shared_vocabulary_as_its_initial_prompt(self):
        calls = []
        class FakeModel:
            def __init__(self, *a, **kw): pass
            def transcribe(self, path, **kw): calls.append(kw); return [types.SimpleNamespace(text=' local text ')], None
        s = _voice_store('local_whisper', secret=None); voice.save_vocabulary(s, ['Taskuary', 'Pex Card']); voice._LOCAL.clear()
        with mock.patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            self.assertEqual(voice.transcribe(s, b'wav', 'audio/wav')['text'], 'local text')
        self.assertEqual(calls[0]['initial_prompt'], 'Taskuary, Pex Card')

    def test_gemini_uploads_transcribes_with_vocabulary_and_deletes_the_clip(self):
        s = _voice_store('gemini_stt'); voice.save_vocabulary(s, ['Taskuary', 'PointClickCare'])
        replies = [R(200, {}, {'X-Goog-Upload-URL': 'https://upload.example/one'}),
                   R(200, {'file': {'name': 'files/one', 'uri': 'https://files.example/one', 'state': 'ACTIVE'}}),
                   R(200, {'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': 'queue TQ-0243'}]}]})]
        with mock.patch.object(voice.requests, 'post', side_effect=replies) as p, mock.patch.object(voice.requests, 'delete') as d:
            out = voice.transcribe(s, b'webm', 'audio/webm', 'clip.webm')
        self.assertEqual(out, {'text': 'queue TQ-0243', 'provider': 'gemini_stt', 'model': 'gemini-3.5-transcribe'})
        payload = p.call_args_list[2].kwargs['json']
        self.assertEqual(payload['generation_config']['transcription_config']['custom_vocabulary'], ['Taskuary', 'PointClickCare'])
        self.assertEqual(payload['input'][0]['mime_type'], 'audio/webm')
        d.assert_called_once_with('https://generativelanguage.googleapis.com/v1beta/files/one', headers={'x-goog-api-key': 'k1'}, timeout=30)

    def test_vocabulary_is_normalized_validated_and_persisted_once_for_the_system(self):
        s = MemoryStore()
        self.assertEqual(voice.save_vocabulary(s, [' Taskuary ', 'taskuary', 'PointClickCare']), ['Taskuary', 'PointClickCare'])
        self.assertEqual(voice.vocabulary(s), ['Taskuary', 'PointClickCare'])
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
        self.assertFalse(ok); self.assertTrue(voice.is_placeholder(body)); self.assertIn('(7s) from WhatsApp', body); self.assertIn('AI - voice', body)
        s = _voice_store('groq_stt')
        with mock.patch.object(voice.requests, 'post', return_value=R(200, {'text': 'please call the vendor back'})):
            body, ok, _ = voice.note_body(s, b'x', 'audio/ogg', 'v.ogg', 7, 'WhatsApp')
        self.assertTrue(ok); self.assertTrue(body.startswith('please call the vendor back')); self.assertIn('transcribed by Groq (Whisper)', body)
        self.assertFalse(voice.is_placeholder(body))


class FunnelTests(unittest.TestCase):
    def _wa(self, s):
        cid = s.get_connector_by_type('whatsapp')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
        s.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': cid, 'Active': 1}, 'o')
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
        self.assertEqual(c_api.post('/api/voice/transcribe', content=b'').status_code, 422)
        with mock.patch.object(voice, 'transcribe', side_effect=RuntimeError(voice.NO_CONNECTOR)):
            r = c_api.post('/api/voice/transcribe', content=b'x', headers={'content-type': 'audio/webm'})
        self.assertEqual(r.status_code, 409); self.assertIn('AI - voice', r.json()['detail'])
        self.assertIn('ready', c_api.get('/api/voice/status').json())

    def test_voice_vocabulary_api_is_shared_validated_and_audited(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s):
            r = c_api.put('/api/voice/vocabulary', json={'terms': [' Taskuary ', 'PointClickCare', 'taskuary']})
            self.assertEqual(r.json(), {'terms': ['Taskuary', 'PointClickCare'], 'limit': 100})
            self.assertEqual(c_api.get('/api/voice/vocabulary').json()['terms'], ['Taskuary', 'PointClickCare'])
            self.assertEqual(c_api.get('/api/voice/status').json()['vocabulary'], ['Taskuary', 'PointClickCare'])
            self.assertEqual(s._rows("SELECT Action FROM audit WHERE Action='voice_vocabulary'")[0]['Action'], 'voice_vocabulary')
            self.assertEqual(c_api.put('/api/voice/vocabulary', json={'terms': ['x' * 51]}).status_code, 422)

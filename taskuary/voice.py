"""Voice: speech to text, for the funnel and for the prompt box.

A voice note used to vanish: the WhatsApp bridge extracted text and captions, a voice message
has neither, so the poll skipped it and nothing on the Timeline said anything had arrived. Now
every voice note LANDS - transcribed when an "AI - voice" connector is set up, and otherwise
filed with a plain line saying it was not transcribed and why, with the audio attached so one
click transcribes it later.

Providers are one small function each. The OpenAI-compatible shape covers most of the market -
OpenAI itself, Groq (Whisper on Groq is the cheapest hosted option and has a free tier), and every
local server that speaks the same endpoint (speaches / faster-whisper-server, whisper.cpp's server,
LocalAI). Deepgram and ElevenLabs Scribe have their own shapes. `local_whisper` runs faster-whisper
in-process: no key, no server, audio never leaves the box (pip install taskuary[voice]).

The same function transcribes a clip from the browser's microphone: "put voice into prompts" is
the prompt box plus a mic, and the text goes wherever the box goes.
"""
import io, json, os, re, tempfile, time, wave
import requests
from loguru import logger

VOICE_TYPES = ('gemini_stt', 'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', 'stt_server', 'local_whisper')
NEEDS_KEY = {'gemini_stt', 'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt'}
LABELS = {'groq_stt': 'Groq (Whisper)', 'openai_stt': 'OpenAI transcription', 'deepgram': 'Deepgram',
          'elevenlabs_stt': 'ElevenLabs Scribe', 'stt_server': 'Any Whisper server (OpenAI-compatible)',
          'local_whisper': 'Local Whisper (on this machine)', 'gemini_stt': 'Google Gemini transcription'}
# (base url, default model) for the OpenAI-compatible three
COMPAT = {'groq_stt': ('https://api.groq.com/openai/v1', 'whisper-large-v3-turbo'),
          'openai_stt': ('https://api.openai.com/v1', 'gpt-4o-mini-transcribe'),
          'stt_server': ('http://127.0.0.1:8000/v1', 'Systran/faster-whisper-small')}
MARK = '🎤 Voice note'
NO_CONNECTOR = ('no AI voice connector is set up - add one under Connectors > AI - voice '
                '(Groq has a free tier; Local Whisper needs no key at all)')
_EXT = {'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp4': 'm4a', 'audio/x-m4a': 'm4a', 'audio/wav': 'wav',
        'audio/x-wav': 'wav', 'audio/webm': 'webm', 'audio/flac': 'flac', 'audio/aac': 'aac', 'audio/opus': 'ogg'}
VOCAB_SETTING, VOCAB_MAX = 'voice_vocabulary', 100
_BAD_TERM = re.compile(r'[<>{}\[\]\\\r\n]')


def ext_for(mime: str) -> str: return _EXT.get((mime or '').split(';')[0].strip().lower(), 'ogg')
def _cfg(c) -> dict: return json.loads(c.get('ConfigJson') or '{}')


def normalize_vocabulary(value) -> list:
    """One safe, ordered vocabulary shared by every voice connector and browser mic."""
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: value = value.splitlines()
    if value is None: value = []
    if not isinstance(value, (list, tuple)): raise ValueError('voice vocabulary must be a list')
    out, seen = [], set()
    for raw in value:
        term = ' '.join(str(raw or '').split()).strip()
        if not term: continue
        if len(term) > 50: raise ValueError(f'voice vocabulary term is over 50 characters: {term[:30]}...')
        if len(term.split()) > 5: raise ValueError(f'voice vocabulary phrase is over 5 words: {term}')
        if _BAD_TERM.search(term): raise ValueError(f'voice vocabulary term has unsupported characters: {term}')
        key = term.casefold()
        if key not in seen: seen.add(key); out.append(term)
    if len(out) > VOCAB_MAX: raise ValueError(f'voice vocabulary supports up to {VOCAB_MAX} terms')
    return out


def vocabulary(store) -> list:
    return normalize_vocabulary(store.get_settings().get(VOCAB_SETTING) or '[]')


def save_vocabulary(store, terms, actor: str = 'owner') -> list:
    clean = normalize_vocabulary(terms)
    store.set_setting(VOCAB_SETTING, json.dumps(clean, ensure_ascii=False), actor)
    return clean


def pick(store):
    """The first active voice connector that can actually run - a key where one is needed."""
    for c in store.list_connectors():
        if c['Type'] in VOICE_TYPES and c['Active'] and (c['HasSecret'] or c['Type'] not in NEEDS_KEY):
            return store.get_connector(c['ConnectorId'], with_secret=True)
    return None


def ready(store) -> dict:
    c = pick(store)
    return {'ready': bool(c), 'provider': c['Type'] if c else None, 'label': LABELS.get(c['Type']) if c else None,
            'vocabulary': vocabulary(store)}


def transcribe(store, data: bytes, mime: str = 'audio/ogg', name: str = 'audio.ogg', c: dict = None) -> dict:
    """Bytes in, {text, provider, model} out. Raises RuntimeError with something the owner can act on."""
    c = c or pick(store)
    if not c: raise RuntimeError(NO_CONNECTOR)
    t, cfg, key, terms = c['Type'], _cfg(c), c.get('Secret') or '', vocabulary(store)
    mime = (mime or 'audio/ogg').split(';')[0].strip()
    if t in COMPAT: text, model = _openai_compat(t, cfg, key, data, mime, name, terms)
    elif t == 'gemini_stt': text, model = _gemini(cfg, key, data, mime, name, terms)
    elif t == 'deepgram': text, model = _deepgram(cfg, key, data, mime, terms)
    elif t == 'elevenlabs_stt': text, model = _elevenlabs(cfg, key, data, mime, name, terms)
    elif t == 'local_whisper': text, model = _local(cfg, data, name, terms)
    else: raise RuntimeError(f'unknown voice connector type {t!r}')
    return {'text': (text or '').strip(), 'provider': t, 'model': model}


def _fail(r, who):
    hint = (' - the key was refused' if r.status_code in (401, 403) else ' - unknown model?' if r.status_code == 404 else '')
    raise RuntimeError(f'{who} {r.status_code}{hint}: {r.text[:200]}')


def _openai_compat(t, cfg, key, data, mime, name, terms=()):
    base, dflt = COMPAT[t]
    base, model = (cfg.get('base_url') or base).rstrip('/'), cfg.get('model') or dflt
    if t in NEEDS_KEY and not key: raise RuntimeError(f'{LABELS[t]}: no API key saved')
    form = {'model': model, 'response_format': 'json'}
    if cfg.get('language'):
        if t == 'openai_stt' and model == 'gpt-transcribe': form['languages[]'] = [cfg['language']]
        else: form['language'] = cfg['language']
    if terms:
        if t == 'openai_stt' and model == 'gpt-transcribe': form['keywords[]'] = list(terms)
        form['prompt'] = ', '.join(terms)
    r = requests.post(f'{base}/audio/transcriptions', headers={'Authorization': f'Bearer {key}'} if key else {},
                      files={'file': (name, data, mime)}, data=form, timeout=180)
    if r.status_code >= 300: _fail(r, LABELS[t])
    return r.json().get('text', ''), model


def _deepgram(cfg, key, data, mime, terms=()):
    if not key: raise RuntimeError('Deepgram: no API key saved')
    model = cfg.get('model') or 'nova-3'
    params = {'model': model, 'smart_format': 'true'}
    if cfg.get('language'): params['language'] = cfg['language']
    if terms: params['keyterm' if model.startswith('nova-3') else 'keywords'] = list(terms) if model.startswith('nova-3') else [f'{x}:1' for x in terms]
    r = requests.post('https://api.deepgram.com/v1/listen', params=params, data=data, timeout=180,
                      headers={'Authorization': f'Token {key}', 'Content-Type': mime})
    if r.status_code >= 300: _fail(r, 'Deepgram')
    try: return r.json()['results']['channels'][0]['alternatives'][0]['transcript'], model
    except (KeyError, IndexError): return '', model


def _elevenlabs(cfg, key, data, mime, name, terms=()):
    if not key: raise RuntimeError('ElevenLabs: no API key saved')
    model = cfg.get('model') or 'scribe_v2'
    form = {'model_id': model}
    if cfg.get('language'): form['language_code'] = cfg['language']
    if terms and model.startswith('scribe_v2'): form['keyterms'] = list(terms)
    r = requests.post('https://api.elevenlabs.io/v1/speech-to-text', headers={'xi-api-key': key},
                      files={'file': (name, data, mime)}, data=form, timeout=180)
    if r.status_code >= 300: _fail(r, 'ElevenLabs')
    return r.json().get('text', ''), model


_LOCAL = {}
def _local(cfg, data, name, terms=()):
    """faster-whisper in-process, model cached after the first call (the first call downloads it)."""
    try: from faster_whisper import WhisperModel
    except ImportError: raise RuntimeError('Local Whisper needs faster-whisper on the server: pip install taskuary[voice]')
    size = cfg.get('model') or 'small'
    m = _LOCAL.get(size)
    if m is None: m = _LOCAL[size] = WhisperModel(size, device=cfg.get('device') or 'cpu', compute_type=cfg.get('compute') or 'int8')
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1] or '.ogg', delete=False) as f:
        f.write(data); path = f.name
    try:
        opts = {'language': cfg['language']} if cfg.get('language') else {}
        if terms: opts['initial_prompt'] = ', '.join(terms)
        segs, _info = m.transcribe(path, vad_filter=True, **opts)
        return ' '.join(s.text.strip() for s in segs), f'faster-whisper {size}'
    finally:
        try: os.unlink(path)
        except OSError: pass


def _gemini(cfg, key, data, mime, name, terms=()):
    """Gemini 3.5 Transcribe: upload the bounded clip, transcribe it, then delete it immediately."""
    if not key: raise RuntimeError('Google Gemini transcription: no API key saved')
    model = cfg.get('model') or 'gemini-3.5-transcribe'
    auth = {'x-goog-api-key': key}
    start = requests.post('https://generativelanguage.googleapis.com/upload/v1beta/files', json={'file': {'display_name': name}}, timeout=30,
                          headers={**auth, 'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
                                   'X-Goog-Upload-Header-Content-Length': str(len(data)), 'X-Goog-Upload-Header-Content-Type': mime})
    if start.status_code >= 300: _fail(start, LABELS['gemini_stt'])
    upload_url = start.headers.get('X-Goog-Upload-URL') or start.headers.get('x-goog-upload-url')
    if not upload_url: raise RuntimeError('Google Gemini transcription did not return an upload URL')
    uploaded = requests.post(upload_url, data=data, timeout=180,
                             headers={'Content-Length': str(len(data)), 'X-Goog-Upload-Offset': '0',
                                      'X-Goog-Upload-Command': 'upload, finalize'})
    if uploaded.status_code >= 300: _fail(uploaded, LABELS['gemini_stt'])
    f = uploaded.json().get('file') or uploaded.json()
    uri, file_name = f.get('uri'), f.get('name')
    if not uri: raise RuntimeError('Google Gemini transcription upload returned no file URI')
    try:
        state = str(f.get('state') or 'ACTIVE').upper()
        for _ in range(15):
            state = str(f.get('state') or 'ACTIVE').upper()
            if state == 'ACTIVE': break
            if state == 'FAILED': raise RuntimeError('Google Gemini transcription could not process the audio file')
            if not file_name: raise RuntimeError('Google Gemini transcription upload returned no file name')
            time.sleep(.2)
            check = requests.get(f'https://generativelanguage.googleapis.com/v1beta/{file_name}', headers=auth, timeout=30)
            if check.status_code >= 300: _fail(check, LABELS['gemini_stt'])
            f = check.json()
            state = str(f.get('state') or 'ACTIVE').upper()
        if state != 'ACTIVE': raise RuntimeError('Google Gemini transcription timed out while processing the audio file')
        tc = {'mode': 'smart'}
        if terms: tc['custom_vocabulary'] = list(terms)
        if cfg.get('language'): tc['language_codes'] = [cfg['language']]
        r = requests.post('https://generativelanguage.googleapis.com/v1beta/interactions', headers=auth, timeout=180,
                          json={'model': model, 'input': [{'type': 'audio', 'uri': uri, 'mime_type': mime}],
                                'generation_config': {'transcription_config': tc}})
        if r.status_code >= 300: _fail(r, LABELS['gemini_stt'])
        body = r.json()
        text = body.get('output_text') or next((part.get('text', '') for step in body.get('steps', [])
                                                for part in step.get('content', []) if part.get('type') == 'text'), '')
        return text, model
    finally:
        if file_name:
            try: requests.delete(f'https://generativelanguage.googleapis.com/v1beta/{file_name}', headers=auth, timeout=30)
            except requests.RequestException: logger.warning(f'could not delete Gemini voice upload {file_name}')


def silence_wav(seconds: float = 1.0) -> bytes:
    """One second of silence - the Test clip. It proves the key, the endpoint and the model, and
    every provider answers it with an empty or near-empty transcript."""
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b'\x00\x00' * int(16000 * seconds))
    return b.getvalue()


def test(store, c) -> str:
    out = transcribe(store, silence_wav(), 'audio/wav', 'silence.wav', c=c)
    return f"{LABELS.get(c['Type'], c['Type'])} answered ({out['model']}) - transcription works"


def note_body(store, data: bytes, mime: str, name: str, seconds: int = 0, where: str = 'chat') -> tuple:
    """The body a voice note lands with: the transcript, or the honest placeholder.
    Returns (body, transcribed, why_not)."""
    dur = f' ({int(seconds)}s)' if seconds else ''
    try:
        out = transcribe(store, data, mime, name)
        text = out['text'] or '(nothing audible)'
        return f"{text}\n\n({MARK.lower()}{dur} from {where}, transcribed by {LABELS.get(out['provider'], out['provider'])})", True, ''
    except Exception as e:
        why = str(e)[:300]
        logger.warning(f'voice note not transcribed: {why}')
        return (f"{MARK}{dur} from {where} - not transcribed: {why}. Add a connector under Connectors > AI - voice, "
                "then click Transcribe on this message."), False, why


def is_placeholder(body: str) -> bool: return str(body or '').startswith(MARK) and ' - not transcribed' in str(body or '')


def transcribe_message(store, mid: int) -> dict:
    """The one-click on a voice note that landed untranscribed: the audio is attached, so it is
    transcribed now and the body replaced. Triage is not re-run - the owner has the text and the
    panel's own buttons."""
    m = store.get_message(mid) if hasattr(store, 'get_message') else store._one('SELECT * FROM message WHERE MessageId=?', (mid,))
    if not m: raise RuntimeError('message not found')
    a = next((x for x in store.list_attachments(mid) if str(x.get('ContentType') or '').startswith('audio') and x.get('Path')), None)
    if not a: raise RuntimeError('this message has no audio attached')
    with open(a['Path'], 'rb') as f: data = f.read()
    out = transcribe(store, data, a.get('ContentType') or 'audio/ogg', a.get('Name') or 'audio.ogg')
    body = f"{out['text'] or '(nothing audible)'}\n\n({MARK.lower()} from {m.get('Channel') or 'chat'}, transcribed by {LABELS.get(out['provider'], out['provider'])})"
    store.update_message_body(mid, body)
    return {**out, 'body': body}

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
import io, json, os, tempfile, wave
import requests
from loguru import logger

VOICE_TYPES = ('groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', 'stt_server', 'local_whisper')
NEEDS_KEY = {'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt'}
LABELS = {'groq_stt': 'Groq (Whisper)', 'openai_stt': 'OpenAI transcription', 'deepgram': 'Deepgram',
          'elevenlabs_stt': 'ElevenLabs Scribe', 'stt_server': 'Any Whisper server (OpenAI-compatible)',
          'local_whisper': 'Local Whisper (on this machine)'}
# (base url, default model) for the OpenAI-compatible three
COMPAT = {'groq_stt': ('https://api.groq.com/openai/v1', 'whisper-large-v3-turbo'),
          'openai_stt': ('https://api.openai.com/v1', 'gpt-4o-mini-transcribe'),
          'stt_server': ('http://127.0.0.1:8000/v1', 'Systran/faster-whisper-small')}
MARK = '🎤 Voice note'
NO_CONNECTOR = ('no AI voice connector is set up - add one under Connectors > AI - voice '
                '(Groq has a free tier; Local Whisper needs no key at all)')
_EXT = {'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp4': 'm4a', 'audio/x-m4a': 'm4a', 'audio/wav': 'wav',
        'audio/x-wav': 'wav', 'audio/webm': 'webm', 'audio/flac': 'flac', 'audio/aac': 'aac', 'audio/opus': 'ogg'}


def ext_for(mime: str) -> str: return _EXT.get((mime or '').split(';')[0].strip().lower(), 'ogg')
def _cfg(c) -> dict: return json.loads(c.get('ConfigJson') or '{}')


def pick(store):
    """The first active voice connector that can actually run - a key where one is needed."""
    for c in store.list_connectors():
        if c['Type'] in VOICE_TYPES and c['Active'] and (c['HasSecret'] or c['Type'] not in NEEDS_KEY):
            return store.get_connector(c['ConnectorId'], with_secret=True)
    return None


def ready(store) -> dict:
    c = pick(store)
    return {'ready': bool(c), 'provider': c['Type'] if c else None, 'label': LABELS.get(c['Type']) if c else None}


def transcribe(store, data: bytes, mime: str = 'audio/ogg', name: str = 'audio.ogg', c: dict = None) -> dict:
    """Bytes in, {text, provider, model} out. Raises RuntimeError with something the owner can act on."""
    c = c or pick(store)
    if not c: raise RuntimeError(NO_CONNECTOR)
    t, cfg, key = c['Type'], _cfg(c), c.get('Secret') or ''
    mime = (mime or 'audio/ogg').split(';')[0].strip()
    if t in COMPAT: text, model = _openai_compat(t, cfg, key, data, mime, name)
    elif t == 'deepgram': text, model = _deepgram(cfg, key, data, mime)
    elif t == 'elevenlabs_stt': text, model = _elevenlabs(cfg, key, data, mime, name)
    elif t == 'local_whisper': text, model = _local(cfg, data, name)
    else: raise RuntimeError(f'unknown voice connector type {t!r}')
    return {'text': (text or '').strip(), 'provider': t, 'model': model}


def _fail(r, who):
    hint = (' - the key was refused' if r.status_code in (401, 403) else ' - unknown model?' if r.status_code == 404 else '')
    raise RuntimeError(f'{who} {r.status_code}{hint}: {r.text[:200]}')


def _openai_compat(t, cfg, key, data, mime, name):
    base, dflt = COMPAT[t]
    base, model = (cfg.get('base_url') or base).rstrip('/'), cfg.get('model') or dflt
    if t in NEEDS_KEY and not key: raise RuntimeError(f'{LABELS[t]}: no API key saved')
    form = {'model': model, 'response_format': 'json'}
    if cfg.get('language'): form['language'] = cfg['language']
    r = requests.post(f'{base}/audio/transcriptions', headers={'Authorization': f'Bearer {key}'} if key else {},
                      files={'file': (name, data, mime)}, data=form, timeout=180)
    if r.status_code >= 300: _fail(r, LABELS[t])
    return r.json().get('text', ''), model


def _deepgram(cfg, key, data, mime):
    if not key: raise RuntimeError('Deepgram: no API key saved')
    model = cfg.get('model') or 'nova-3'
    params = {'model': model, 'smart_format': 'true'}
    if cfg.get('language'): params['language'] = cfg['language']
    r = requests.post('https://api.deepgram.com/v1/listen', params=params, data=data, timeout=180,
                      headers={'Authorization': f'Token {key}', 'Content-Type': mime})
    if r.status_code >= 300: _fail(r, 'Deepgram')
    try: return r.json()['results']['channels'][0]['alternatives'][0]['transcript'], model
    except (KeyError, IndexError): return '', model


def _elevenlabs(cfg, key, data, mime, name):
    if not key: raise RuntimeError('ElevenLabs: no API key saved')
    model = cfg.get('model') or 'scribe_v1'
    form = {'model_id': model}
    if cfg.get('language'): form['language_code'] = cfg['language']
    r = requests.post('https://api.elevenlabs.io/v1/speech-to-text', headers={'xi-api-key': key},
                      files={'file': (name, data, mime)}, data=form, timeout=180)
    if r.status_code >= 300: _fail(r, 'ElevenLabs')
    return r.json().get('text', ''), model


_LOCAL = {}
def _local(cfg, data, name):
    """faster-whisper in-process, model cached after the first call (the first call downloads it)."""
    try: from faster_whisper import WhisperModel
    except ImportError: raise RuntimeError('Local Whisper needs faster-whisper on the server: pip install taskuary[voice]')
    size = cfg.get('model') or 'small'
    m = _LOCAL.get(size)
    if m is None: m = _LOCAL[size] = WhisperModel(size, device=cfg.get('device') or 'cpu', compute_type=cfg.get('compute') or 'int8')
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1] or '.ogg', delete=False) as f:
        f.write(data); path = f.name
    try:
        segs, _info = m.transcribe(path, vad_filter=True, **({'language': cfg['language']} if cfg.get('language') else {}))
        return ' '.join(s.text.strip() for s in segs), f'faster-whisper {size}'
    finally:
        try: os.unlink(path)
        except OSError: pass


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

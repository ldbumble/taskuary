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
import base64, io, json, os, re, subprocess, sys, tempfile, threading, time, uuid, wave
import requests
from loguru import logger
from . import words

# four more (the owner, 2026-11-08: "all the ones that say coming soon just add them now"), each a file in and its text out over the
# vendor's own REST call with a key - AssemblyAI, Speechmatics and Gladia upload, submit and poll; Azure's fast transcription answers at once
POLLED = ('assemblyai', 'speechmatics', 'gladia', 'azure_speech')
VOICE_TYPES = ('gemini_stt', 'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', 'stt_server', 'local_whisper', *POLLED, 'amazon_transcribe')
NEEDS_KEY = {'gemini_stt', 'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', *POLLED}
LABELS = {'groq_stt': 'Groq (Whisper)', 'openai_stt': 'OpenAI transcription', 'deepgram': 'Deepgram',
          'elevenlabs_stt': 'ElevenLabs Scribe', 'stt_server': 'Any Whisper server (OpenAI-compatible)',
          'local_whisper': 'Local Whisper (on this machine)', 'gemini_stt': 'Google Gemini transcription',
          'assemblyai': 'AssemblyAI', 'speechmatics': 'Speechmatics', 'gladia': 'Gladia', 'azure_speech': 'Azure AI Speech',
          'amazon_transcribe': 'Amazon Transcribe', 'hipaa_ai': 'HIPAA AI'}
# THE HIPAA AI CARD HEARS TOO (the owner, 2026-11-09: "the voice thing does still not work on windows????"): a client whose only AI is
# that card, on a managed machine with Windows' online speech off, had a mic that gave no words. Its gateway (LiteLLM, OpenAI-compatible)
# lists only chat models - /audio/transcriptions answered 403 there - but a Gemini model behind it takes the clip as an input_audio part
# of a chat message and writes back what was said (proven live, wav and the browser's webm/opus alike). The audio goes to that gateway
# only - the one the organisation chose for its health data - and it is used when no voice card is set up.
GATEWAY_TYPES = ('hipaa_ai',)
NO_SPEECH = '[no speech]'
HEAR = ('Transcribe the speech in this audio exactly as spoken, in its own language. Output only the words said - no notes, labels or '
        f'quotes. If no person is clearly speaking words (silence, noise, a click, breathing), output exactly: {NO_SPEECH}')
# SILENCE IS NOT INVENTED INTO WORDS: a model handed a silent clip writes a sentence anyway (Groq said "www.fema.org"; Gemini, asked
# for the sentinel above, still wrote whole made-up sentences for digital silence, 2026-11-09). A clip quieter than this - the loudest
# 20 ms window's RMS, full scale 1.0, about -44 dBFS - or shorter than MIN_SECONDS is not sent at all: it heard nothing.
QUIET, MIN_SECONDS = 0.006, 0.4
# (base url, default model) for the OpenAI-compatible three
COMPAT = {'groq_stt': ('https://api.groq.com/openai/v1', 'whisper-large-v3-turbo'),
          'openai_stt': ('https://api.openai.com/v1', 'gpt-4o-mini-transcribe'),
          'stt_server': ('http://127.0.0.1:8000/v1', 'Systran/faster-whisper-small')}
MARK = '🎤 Voice note'
NO_CONNECTOR = (f"no AI voice connector is set up - add one under {words.name('voice')} "
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
    return normalize_vocabulary(store.get_setting(VOCAB_SETTING) or '[]')


def save_vocabulary(store, terms, actor: str = 'owner') -> list:
    clean = normalize_vocabulary(terms)
    store.set_setting(VOCAB_SETTING, json.dumps(clean, ensure_ascii=False), actor)
    return clean


def pick(store):
    """The first active voice connector that can actually run - a key where one is needed - else a HIPAA AI card with its access code."""
    cs = [c for c in store.list_connectors() if c['Active']]
    c = next((c for c in cs if c['Type'] in VOICE_TYPES and (c['HasSecret'] or c['Type'] not in NEEDS_KEY)), None) \
        or next((c for c in cs if c['Type'] in GATEWAY_TYPES and c['HasSecret']), None)
    return store.get_connector(c['ConnectorId'], with_secret=True) if c else None


def ready(store) -> dict:
    c = pick(store)
    return {'ready': bool(c), 'provider': c['Type'] if c else None, 'label': LABELS.get(c['Type']) if c else None,
            'vocabulary': vocabulary(store), 'builtin': None if c else builtin()}


def transcribe(store, data: bytes, mime: str = 'audio/ogg', name: str = 'audio.ogg', c: dict = None, mic: bool = False,
               level: float = None, seconds: float = None, gate: bool = True) -> dict:
    """Bytes in, {text, provider, model} out. Raises RuntimeError with something the owner can act on.
    `mic`: a clip from the prompt box's mic, which may fall to the computer's own recogniser when no card is set up.
    `level`/`seconds`: what the browser measured while it recorded (its webm cannot be read here); a silent clip is never sent."""
    c = c or pick(store)
    if not c: raise RuntimeError(NO_CONNECTOR)
    t, cfg, key, terms = c['Type'], _cfg(c), c.get('Secret') or '', vocabulary(store)
    mime = (mime or 'audio/ogg').split(';')[0].strip()
    if gate and silent(data, mime, level, seconds): return {'text': '', 'provider': t, 'model': None, 'silent': True}
    if t in GATEWAY_TYPES: text, model = _gateway(cfg, key, data, mime, terms)
    elif t in COMPAT: text, model = _openai_compat(t, cfg, key, data, mime, name, terms)
    elif t == 'gemini_stt': text, model = _gemini(cfg, key, data, mime, name, terms)
    elif t == 'deepgram': text, model = _deepgram(cfg, key, data, mime, terms)
    elif t == 'elevenlabs_stt': text, model = _elevenlabs(cfg, key, data, mime, name, terms)
    elif t == 'local_whisper': text, model = _local(cfg, data, name, terms)
    elif t == 'amazon_transcribe': text, model = _transcribe_aws(cfg, key, data, mime, name)
    elif t in POLLED:
        if not key: raise RuntimeError(f'{LABELS[t]}: no API key saved')
        text, model = {'assemblyai': _assemblyai, 'speechmatics': _speechmatics, 'gladia': _gladia, 'azure_speech': _azure}[t](cfg, key, data, mime, name, terms)
    else: raise RuntimeError(f'unknown voice connector type {t!r}')
    return {'text': (text or '').strip(), 'provider': t, 'model': model}


def wav_level(data: bytes):
    "(loudest 20 ms window's RMS on a 0-1 scale, seconds) of a 16-bit PCM wav; None when it is not one."
    import array, math
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2: return None
            n, rate, a = w.getnchannels(), w.getframerate(), array.array('h', w.readframes(w.getnframes()))
    except (wave.Error, EOFError, ValueError): return None
    if sys.byteorder == 'big': a.byteswap()
    step = max(1, rate * n // 50)
    peak = max((math.sqrt(sum(x * x for x in a[i:i + step]) / len(a[i:i + step])) for i in range(0, len(a), step)), default=0)
    return peak / 32768, len(a) / n / rate


def silent(data: bytes, mime: str, level: float = None, seconds: float = None) -> bool:
    "Heard nothing: too short, or too quiet - measured here for a wav, else by the browser that recorded it."
    if (wl := wav_level(data) if mime in ('audio/wav', 'audio/x-wav', 'audio/wave') else None): level, seconds = wl
    return (seconds is not None and seconds < MIN_SECONDS) or (level is not None and level < QUIET)


_GW_MODEL = {}


def _gateway_model(cfg, base, key):
    "The card's voice_model, else a Gemini the gateway lists (the fast one first) - Gemini is what hears audio behind it."
    if cfg.get('voice_model'): return cfg['voice_model']
    if base not in _GW_MODEL:
        try: ids = [m.get('id') or '' for m in requests.get(f'{base}/models', headers={'Authorization': f'Bearer {key}'}, timeout=(15, 90)).json().get('data', [])]
        except (requests.RequestException, ValueError, AttributeError): ids = []
        gem = [i for i in ids if 'gemini' in i.lower()]
        _GW_MODEL[base] = next((i for i in gem if 'flash' in i.lower()), None) or (gem[0] if gem else None)
    return _GW_MODEL[base] or cfg.get('model') or 'hipaa-ai'


_FMT = {'m4a': 'mp4'}


def _gateway(cfg, key, data, mime, terms=()):
    "The HIPAA AI gateway: the clip as an input_audio part of one chat message to a Gemini model behind it."
    from .llm import gateway_base
    if not key: raise RuntimeError('HIPAA AI: no access code saved')
    try: base = gateway_base(cfg)
    except ValueError as e: raise RuntimeError(f'HIPAA AI: {e}')
    if not base: raise RuntimeError('HIPAA AI: no gateway address on its card')
    model, ext = _gateway_model(cfg, base, key), ext_for(mime)
    ask = HEAR + (f" Words that may come up: {', '.join(terms)}." if terms else '')
    body = {'model': model, 'temperature': 0, 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': ask}, {'type': 'input_audio', 'input_audio': {'data': base64.b64encode(data).decode(), 'format': _FMT.get(ext, ext)}}]}]}
    r = requests.post(f'{base}/chat/completions', headers={'Authorization': f'Bearer {key}'}, json=body, timeout=(15, 180))
    if r.status_code >= 300: _fail(r, LABELS['hipaa_ai'])
    msg = ((r.json().get('choices') or [{}])[0].get('message') or {}).get('content') or ''
    if isinstance(msg, list): msg = ' '.join(p.get('text', '') for p in msg if isinstance(p, dict))
    text = msg.strip().strip('"').strip()
    return ('' if text.lower().rstrip('.') in (NO_SPEECH, NO_SPEECH.strip('[]')) else text), model


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


POLL_EVERY, POLL_FOR = 2, 600              # a voice note is seconds of audio; an hour-long file still lands inside ten minutes


def _ok(r, who):
    if r.status_code >= 300: _fail(r, who)
    return r.json() or {}


def _until(get, done, who):
    "Ask `get()` until `done(job)` says (text, '') or raises; a job still running after POLL_FOR is a failure."
    end = time.time() + POLL_FOR
    while time.time() < end:
        if (out := done(get())) is not None: return out
        time.sleep(POLL_EVERY)
    raise RuntimeError(f'{who}: still transcribing after {POLL_FOR}s')


def _assemblyai(cfg, key, data, mime, name, terms=()):
    "assemblyai.com/docs/getting-started/transcribe-an-audio-file: upload the bytes, submit their url, poll the transcript."
    base, h = 'https://api.assemblyai.com/v2', {'authorization': key}
    up = _ok(requests.post(f'{base}/upload', headers=h, data=data, timeout=180), 'AssemblyAI')['upload_url']
    body = {'audio_url': up, **({'language_code': cfg['language']} if cfg.get('language') else {'language_detection': True}),
            **({'keyterms_prompt': list(terms)} if terms else {}), **({'speech_model': cfg['model']} if cfg.get('model') else {})}
    tid = _ok(requests.post(f'{base}/transcript', headers=h, json=body, timeout=60), 'AssemblyAI')['id']
    def done(j):
        if j.get('status') == 'error': raise RuntimeError(f"AssemblyAI: {j.get('error') or 'the transcript failed'}")
        return j.get('text') or '' if j.get('status') == 'completed' else None
    return _until(lambda: _ok(requests.get(f'{base}/transcript/{tid}', headers=h, timeout=60), 'AssemblyAI'), done, 'AssemblyAI'), cfg.get('model') or 'best'


def _speechmatics(cfg, key, data, mime, name, terms=()):
    "docs.speechmatics.com/api-ref/batch: a job with the file and its config, polled, then its transcript as plain text."
    base, h = f"https://{cfg.get('region') or 'eu1'}.asr.api.speechmatics.com/v2", {'Authorization': f'Bearer {key}'}
    tc = {'language': cfg.get('language') or 'auto', **({'additional_vocab': [{'content': x} for x in terms]} if terms else {}),
          **({'operating_point': cfg['model']} if cfg.get('model') else {})}
    jid = _ok(requests.post(f'{base}/jobs', headers=h, files={'data_file': (name, data, mime)},
                            data={'config': json.dumps({'type': 'transcription', 'transcription_config': tc})}, timeout=180), 'Speechmatics')['id']
    def done(j):
        st = (j.get('job') or {}).get('status')
        if st in ('rejected', 'deleted', 'expired'): raise RuntimeError(f'Speechmatics: the job was {st}')
        return '' if st == 'done' else None
    _until(lambda: _ok(requests.get(f'{base}/jobs/{jid}', headers=h, timeout=60), 'Speechmatics'), done, 'Speechmatics')
    r = requests.get(f'{base}/jobs/{jid}/transcript', headers=h, params={'format': 'txt'}, timeout=60)
    if r.status_code >= 300: _fail(r, 'Speechmatics')
    return r.text, cfg.get('model') or 'standard'


def _gladia(cfg, key, data, mime, name, terms=()):
    "docs.gladia.io/chapters/pre-recorded-stt/quickstart: upload, submit, poll the result."
    base, h = 'https://api.gladia.io/v2', {'x-gladia-key': key}
    url = _ok(requests.post(f'{base}/upload', headers=h, files={'audio': (name, data, mime)}, timeout=180), 'Gladia')['audio_url']
    body = {'audio_url': url, **({'language_config': {'languages': [cfg['language']]}} if cfg.get('language') else {}),
            **({'custom_vocabulary': True, 'custom_vocabulary_config': {'vocabulary': list(terms)}} if terms else {})}
    jid = _ok(requests.post(f'{base}/pre-recorded', headers=h, json=body, timeout=60), 'Gladia')['id']
    def done(j):
        if j.get('status') == 'error': raise RuntimeError(f"Gladia: {j.get('error_code') or 'the transcription failed'}")
        return (((j.get('result') or {}).get('transcription') or {}).get('full_transcript') or '') if j.get('status') == 'done' else None
    return _until(lambda: _ok(requests.get(f'{base}/pre-recorded/{jid}', headers=h, timeout=60), 'Gladia'), done, 'Gladia'), 'gladia'


AZURE_SPEECH_VERSION = '2025-10-15'
def _azure(cfg, key, data, mime, name, terms=()):
    """learn.microsoft.com/azure/ai-services/speech-service/fast-transcription-create: one POST, the text in combinedPhrases. The card
    names its resource's endpoint (https://<resource>.cognitiveservices.azure.com) or its region (eastus)."""
    ep = (cfg.get('endpoint') or '').rstrip('/') or (f"https://{cfg['region'].strip()}.api.cognitive.microsoft.com" if cfg.get('region') else '')
    if not ep: raise RuntimeError("Azure AI Speech: the card needs its resource's endpoint or region")
    d = {'locales': [cfg.get('language') or 'en-US'], **({'phraseList': {'phrases': list(terms)}} if terms else {})}
    j = _ok(requests.post(f'{ep}/speechtotext/transcriptions:transcribe', params={'api-version': AZURE_SPEECH_VERSION},
                          headers={'Ocp-Apim-Subscription-Key': key}, files={'audio': (name, data, mime), 'definition': (None, json.dumps(d))},
                          timeout=300), 'Azure AI Speech')
    return ' '.join(p.get('text') or '' for p in (j.get('combinedPhrases') or [])[:1]), 'fast transcription'


def _transcribe_aws(cfg, key, data, mime, name):
    """docs.aws.amazon.com/transcribe/latest/dg/batch-med-transcription.html: Transcribe reads audio from S3 only, so the clip goes to the
    owner's own bucket (named on the card), a job runs on it, its transcript JSON lands beside it - and both are deleted once read.
    The keys are the card's (blank: boto3's own chain); its IAM user needs s3:PutObject/GetObject/DeleteObject on the bucket and
    transcribe:StartTranscriptionJob/GetTranscriptionJob - nothing else. boto3 is the aws extra."""
    from . import aws
    b = str(cfg.get('bucket') or '').strip().removeprefix('s3://').strip('/')
    if not b: raise RuntimeError('Amazon Transcribe: the card needs the S3 bucket it may put the audio in')
    c = {**cfg, 'secret_access_key': key or cfg.get('secret_access_key')}
    s3, tr = aws.client(c, 's3'), aws.client(c, 'transcribe')
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    ext = ext if ext in ('mp3', 'mp4', 'wav', 'flac', 'ogg', 'amr', 'webm', 'm4a') else ext_for(mime)       # the formats Transcribe takes
    job, pre = f'taskuary-{uuid.uuid4().hex}', (cfg.get('prefix') or 'taskuary-transcribe').strip('/')
    k, out = f'{pre}/{job}.{ext}', f'{pre}/{job}.json'
    s3.put_object(Bucket=b, Key=k, Body=data, ContentType=mime)
    try:
        tr.start_transcription_job(TranscriptionJobName=job, Media={'MediaFileUri': f's3://{b}/{k}'}, MediaFormat=ext, OutputBucketName=b, OutputKey=out,
                                   **({'LanguageCode': cfg['language']} if cfg.get('language') else {'IdentifyLanguage': True}))
        def done(j):
            st = (j.get('TranscriptionJob') or {}).get('TranscriptionJobStatus')
            if st == 'FAILED': raise RuntimeError(f"Amazon Transcribe: {j['TranscriptionJob'].get('FailureReason') or 'the job failed'}")
            return '' if st == 'COMPLETED' else None
        _until(lambda: tr.get_transcription_job(TranscriptionJobName=job), done, 'Amazon Transcribe')
        j = json.loads(s3.get_object(Bucket=b, Key=out)['Body'].read())
        return ' '.join(x.get('transcript') or '' for x in (j.get('results') or {}).get('transcripts') or []), 'batch'
    finally:
        for x in (k, out):
            try: s3.delete_object(Bucket=b, Key=x)
            except Exception as e: logger.info(f'voice: s3://{b}/{x} was not deleted: {e}')


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


"""WINDOWS VOICE TYPING FIRST (the owner, 2026-11-02, after System.Speech wrote a dictation as "a predetermined trading land on my left
arm": "do the changes to use desktop if the machine has it"). Windows 10 and 11 ship two recognisers. System.Speech (removed, TQ-1283) is the 2006
one, untrained and offline. Windows.Media.SpeechRecognition is the one behind Win+H and Edge's tabs: Microsoft's online service, on when
Online speech recognition is on in Windows' speech privacy settings. It hears the MICROPHONE, never a file, so it is a session the
server holds: started by the mic's press, each phrase read as it settles, stopped by the next press. PowerShell 5.1 reaches it as a WinRT
type - no Python package, nothing added to the exe. A phrase still being said at the stop gets up to 3.5s to settle (an operation it has
started cannot be cancelled from PowerShell); a silence ends each listen after 3s and the next starts at once, so nothing falls between.
It hears this computer's own microphone, so it serves only a page on this computer (server: loopback). macOS has no such door for an
unbundled process - Apple's Speech framework kills a caller whose app carries no usage description - so a Mac uses its Dictation key."""
LIVE = {'engine': 'windows_voice_typing', 'label': 'Windows voice typing (on this computer)', 'live': True}
SPEECH_ASK = ("Taskuary needs Windows' online speech recognition for dictation, and it is off on this computer. Turn it on? "
              "(Windows sends what you say to Microsoft to turn it into text.)")

# NOTHING THAT DOES NOT WORK (TQ-1283, the owner, 2026-11-03: "You can't use something that doesn't work ... ask them, trigger the
# question if you want to turn that on"). The fallback under voice typing was System.Speech, the 2006 offline dictation - it wrote the
# owner's dictation as "a predetermined trading land on my left arm" and a user's as "Ojai idea or a bottle of Iraq Shore", text that
# looks real and is not. It is gone. Voice typing with its setting off is no longer a reason to fall back: the mic ASKS to turn it on.
_HAS = {}

def builtin(refresh: bool = False):
    """The computer's own recogniser: Windows voice typing (LIVE) when it is here and Online speech recognition is on; here with the
    setting off, LIVE with `ask` - the mic asks the owner to turn it on (turn_on_speech) before it listens; else None, and the mic asks
    for a voice AI. The setting is read each time, so it takes effect at the next press, no restart."""
    # Privacy can prevent compilation. Keep the enable prompt reachable and retry
    # transient failures after a cooldown rather than requiring an app restart.
    if refresh or 'live' not in _HAS or (not _HAS['live'] and time.monotonic() - _HAS.get('checked', 0) >= 30):
        _HAS['live'] = sys.platform == 'win32' and (not speech_on() or _live_ok())
        _HAS['checked'] = time.monotonic()
    if not _HAS['live']: return None
    return LIVE if speech_on() else {**LIVE, 'ask': SPEECH_ASK}

_SPEECH_KEY = r'Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy'

def speech_on() -> bool:
    """Is Online speech recognition on (Windows' speech privacy setting, which voice typing needs)? Off when never set - Windows' default."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SPEECH_KEY) as k: return int(winreg.QueryValueEx(k, 'HasAccepted')[0]) == 1
    except (OSError, ValueError, ImportError): return False

def turn_on_speech() -> bool:
    """The owner said yes at the mic: Online speech recognition on for this Windows user - the value Windows' own speech privacy
    toggle writes (HKCU, no admin). True when it reads back on."""
    try:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _SPEECH_KEY, 0, winreg.KEY_SET_VALUE) as k: winreg.SetValueEx(k, 'HasAccepted', 0, winreg.REG_DWORD, 1)
    except (OSError, ImportError) as e: logger.warning(f'voice: could not turn on Online speech recognition - {e}'); return False
    return speech_on()

# what the child's stop means to the owner, by the WinRT status it names
_LIVE_WHY = {'MicrophoneUnavailable': 'no microphone Windows will lend - turn on "Let desktop apps access your microphone" in the microphone privacy settings of Windows',
             'NetworkFailure': 'it needs the internet, and could not reach it',
             'privacy': "it needs Online speech recognition - turn it on in Windows' speech privacy settings, then press the mic again",
             'TopicLanguageNotSupported': "it does not take dictation in this computer's language"}
_WINRT = r'''$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
[Windows.Media.SpeechRecognition.SpeechRecognizer,Windows.Media.SpeechRecognition,ContentType=WindowsRuntime] | Out-Null
$r = New-Object Windows.Media.SpeechRecognition.SpeechRecognizer
$c = $asTask.MakeGenericMethod([Windows.Media.SpeechRecognition.SpeechRecognitionCompilationResult]).Invoke($null, @($r.CompileConstraintsAsync()))
$c.Wait(-1) | Out-Null; if ("$($c.Result.Status)" -ne 'Success') { throw "$($c.Result.Status)" }
if ($env:TQ_PROBE) { [Console]::Out.Write('ok'); exit 0 }
$r.Timeouts.InitialSilenceTimeout = [TimeSpan]::FromSeconds(3); $r.Timeouts.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(600)
[Console]::Out.WriteLine('.'); [Console]::Out.Flush()
$res = [Windows.Media.SpeechRecognition.SpeechRecognitionResult]
while (-not (Test-Path $env:TQ_STOP)) {
  $t = $asTask.MakeGenericMethod($res).Invoke($null, @($r.RecognizeAsync()))
  while (-not $t.Wait(200)) { if (Test-Path $env:TQ_STOP) { break } }
  if (-not $t.IsCompleted -and -not $t.Wait(3500)) { break }
  $x = $t.Result; $s = "$($x.Status)"
  if ($x.Text) { [Console]::Out.WriteLine('+' + $x.Text); [Console]::Out.Flush() }
  elseif ($s -in @('MicrophoneUnavailable', 'NetworkFailure', 'TopicLanguageNotSupported', 'GrammarCompilationFailure')) { throw $s }
  else { [Console]::Out.WriteLine('?' + $s); [Console]::Out.Flush() }
}
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 2 }'''

def _ps(script: str) -> list:
    return ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()]

def _live_ok() -> bool:
    """Will Windows voice typing take dictation here? A child compiles it and exits - a second or two, once per run."""
    from . import spawn
    try: r = spawn.run(_ps(_WINRT), capture_output=True, timeout=30, env={**os.environ, 'TQ_PROBE': '1'})
    except Exception as e: logger.debug(f'voice: no Windows voice typing - {e}'); return False      # a probe never breaks the status
    if r.returncode: logger.debug(f"voice: no Windows voice typing - {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return r.returncode == 0 and r.stdout.decode('utf-8', 'replace').strip() == 'ok'

def _why(err: str) -> str:
    k = next((k for k in _LIVE_WHY if k.lower() in err.lower()), None)
    return f"Voice typing stopped: {_LIVE_WHY[k] if k else err[:200]}"

_LISTEN, _LISTEN_LOCK = {}, threading.Lock()

def _read(s):
    p = s['proc']
    for line in iter(p.stdout.readline, b''):
        t = line.decode('utf-8', 'replace').rstrip('\r\n')
        if t == '.': s['ready'] = True
        elif t.startswith('+') and t[1:].strip(): s['said'].append(t[1:].strip())
        elif t.startswith('?'): s['last'] = t[1:].strip()
    if p.wait(): s['error'] = _why(p.stderr.read().decode('utf-8', 'replace').strip() or str(p.returncode))
    s['done'] = True

# A SESSION THAT HEARD NOTHING SAYS SO (the owner, 2026-11-09: "you start it and end it and no words show up???"). Windows answers every
# listen, and with Online speech recognition off or blocked it answers 'Unknown' with no text - the loop took that as a pause, so the
# stop came back empty and the mic said nothing at all. Now a session that ends with no words names why, by the last answer Windows gave.
_HEARD_NOTHING = {'Unknown': "Windows voice typing heard no words - Windows' speech service did not answer. Check that Online speech "
                             "recognition is on in Windows' speech privacy settings (your organisation may block it), or set up a voice AI",
                  'TimeoutExceeded': "Windows voice typing heard no speech - check the microphone Windows is using (Sound settings) "
                                     "and that it is not muted, then press the mic and talk"}
_HEARD_NOTHING['Success'] = _HEARD_NOTHING['TimeoutExceeded']     # a muted or silent mic: Windows answers 'Success' with no text

def heard_nothing(last: str = '') -> str:
    "The line a session that ended with no words shows, by Windows' last answer (`last`: a SpeechRecognitionResultStatus name, or '')."
    return _HEARD_NOTHING.get(last) or (f"Windows voice typing heard no words (Windows answered: {last})" if last else _HEARD_NOTHING['TimeoutExceeded'])

def listen_start() -> str:
    """Start the one live session (an earlier one stops first) and return its id."""
    b = builtin() or {}
    if b.get('engine') != LIVE['engine']: raise RuntimeError(f"{LIVE['label']} is not on this computer")
    if b.get('ask'): raise RuntimeError(_LIVE_WHY['privacy'])
    from . import spawn
    with _LISTEN_LOCK:
        _stop(_LISTEN.pop('cur', None))
        sid = uuid.uuid4().hex[:12]
        stop = os.path.join(tempfile.gettempdir(), f'taskuary-listen-{sid}.stop')
        p = spawn.popen(_ps(_WINRT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, 'TQ_STOP': stop})
        s = _LISTEN['cur'] = {'id': sid, 'proc': p, 'stop': stop, 'said': [], 'error': '', 'last': '', 'ready': False, 'done': False}
        s['reader'] = threading.Thread(target=_read, args=(s,), daemon=True, name='voice-listen'); s['reader'].start()
    return sid

def _view(s, since=0) -> dict: return {'said': s['said'][max(0, since):], 'ready': s['ready'], 'done': s['done'], 'error': s['error']}

def listen_poll(sid: str, since: int = 0):
    """The phrases settled since `since`; None when `sid` is not the live session."""
    s = _LISTEN.get('cur')
    return _view(s, since) if s and s['id'] == sid else None

def _stop(s):
    if not s: return
    try: open(s['stop'], 'w').close()
    except OSError: pass
    try: s['proc'].wait(timeout=6)
    except subprocess.TimeoutExpired: s['proc'].kill()
    s['reader'].join(timeout=3)
    try: os.unlink(s['stop'])
    except OSError: pass

def listen_stop(sid: str, since: int = 0):
    """Stop the session - a phrase still being said settles first - and return what came after `since`; None for an unknown id."""
    with _LISTEN_LOCK:
        s = _LISTEN.get('cur')
        if not s or s['id'] != sid: return None
        _stop(_LISTEN.pop('cur'))
    if not s['said'] and not s['error']: s['error'] = heard_nothing(s.get('last', ''))
    return {**_view(s, since), 'done': True}


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
    out = transcribe(store, silence_wav(), 'audio/wav', 'silence.wav', c=c, gate=False)
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
        return (f"{MARK}{dur} from {where} - not transcribed: {why}. Add a connector under {words.name('voice')}, "
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

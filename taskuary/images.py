"""Image models as a connector card: a prompt in, a picture out, filed on the task.

Same shape of problem as voice.py - several vendors, one thing wanted, and the owner picking
whichever they already pay for - so it is built the same way: a types tuple, labels, one table
per wire shape, and `pick()` taking the first active card that can actually run.

Eight cards on FIVE wire shapes, which is the whole design. Four of them speak OpenAI's
/v1/images/generations and share one function; Replicate reaches the long tail - FLUX, SDXL,
Ideogram, hundreds more - through a single async poll rather than eight hand-written vendors.
Adding a card that speaks one of these shapes is a row in a table, not a new code path.

The picture is fetched, never handed back as a link: a DALL-E-style answer points at a signed URL
that expires within the hour, and the owner wants the image on the task, not a dead link.
"""
import base64, json, time
import requests
from loguru import logger

IMAGE_TYPES = ('openai_image', 'azure_openai_image', 'xai_image', 'image_server',
               'gemini_image', 'stability_image', 'openrouter_image', 'replicate_image')
NEEDS_KEY = set(IMAGE_TYPES) - {'image_server'}
LABELS = {'openai_image': 'OpenAI images (gpt-image-1)', 'azure_openai_image': 'Azure OpenAI images',
          'xai_image': 'xAI Grok images', 'image_server': 'Any OpenAI-compatible image server',
          'gemini_image': 'Google Gemini images', 'stability_image': 'Stability AI',
          'openrouter_image': 'OpenRouter images', 'replicate_image': 'Replicate (FLUX, SDXL, and more)'}
# the OpenAI-compatible four: (base url, default model). azure builds its own URL from the card.
COMPAT = {'openai_image': ('https://api.openai.com/v1', 'gpt-image-1'),
          'xai_image': ('https://api.x.ai/v1', 'grok-2-image'),
          'image_server': ('http://127.0.0.1:7860/v1', 'stable-diffusion-xl'),
          'azure_openai_image': ('', 'gpt-image-1')}
SHAPES = {**{t: 'openai' for t in COMPAT}, 'gemini_image': 'gemini', 'stability_image': 'stability',
          'openrouter_image': 'openrouter', 'replicate_image': 'replicate'}
DEFAULT_MODEL = {'gemini_image': 'gemini-3-flash-image', 'stability_image': 'core',
                 'openrouter_image': 'google/gemini-3-flash-image', 'replicate_image': 'black-forest-labs/flux-schnell'}
NO_CONNECTOR = ('no image model is set up - add one under Connections > AI - images '
                '(OpenAI, Azure, Gemini, Stability, OpenRouter, Replicate, xAI, or any '
                'OpenAI-compatible server running on this machine)')
SIZES = ('1024x1024', '1024x1536', '1536x1024')
POLL_S, POLL_EVERY = 180, 2          # replicate and friends: how long to wait, how often to ask
MAX_PROMPT = 4000


def shape_of(t) -> str: return SHAPES.get(t, '')
def _cfg(c) -> dict: return json.loads(c.get('ConfigJson') or '{}')


def pick(store):
    """The first active image card that can actually run - a key where one is needed."""
    for c in store.list_connectors():
        if c['Type'] in IMAGE_TYPES and c['Active'] and (c['HasSecret'] or c['Type'] not in NEEDS_KEY):
            return store.get_connector(c['ConnectorId'], with_secret=True)
    return None


def ready(store) -> dict:
    c = pick(store)
    return {'ready': bool(c), 'provider': c['Type'] if c else None, 'label': LABELS.get(c['Type']) if c else None}


def generate(store, prompt: str, size: str = '1024x1024', c: dict = None) -> dict:
    """Prompt in, {data, mime, provider, model} out. Raises RuntimeError with something the owner
    can act on - never an empty image, which reads downstream as a picture nobody can see."""
    prompt = str(prompt or '').strip()[:MAX_PROMPT]
    if not prompt: raise RuntimeError('nothing to draw - an image needs a prompt')
    c = c or pick(store)
    if not c: raise RuntimeError(NO_CONNECTOR)
    t, cfg, key = c['Type'], _cfg(c), c.get('Secret') or ''
    if t in NEEDS_KEY and not key: raise RuntimeError(f'{LABELS.get(t, t)}: no API key saved')
    size = size if size in SIZES else '1024x1024'
    shape = shape_of(t)
    if not shape: raise RuntimeError(f'unknown image connector type {t!r}')
    data, mime, model = globals()[f'_{shape}'](t, cfg, key, prompt, size)
    if not data: raise RuntimeError(f'{LABELS.get(t, t)} returned no image')
    return {'data': data, 'mime': mime or 'image/png', 'provider': t, 'model': model, 'prompt': prompt}


def _fail(r, who):
    hint = (' - the key was refused' if r.status_code in (401, 403) else
            ' - unknown model?' if r.status_code == 404 else
            ' - the vendor is rate limiting' if r.status_code == 429 else '')
    raise RuntimeError(f'{who} {r.status_code}{hint}: {str(r.text)[:200]}')


def _bytes_from(item) -> tuple:
    """A vendor hands back base64 or a URL. Both end as bytes here."""
    if isinstance(item, str) and item.startswith('data:'):
        head, _, b64 = item.partition(',')
        return base64.b64decode(b64), head[5:].split(';')[0] or 'image/png'
    if isinstance(item, str) and item.startswith('http'):
        r = requests.get(item, timeout=120)
        if r.status_code >= 300: _fail(r, 'fetching the generated image')
        return r.content, 'image/png'
    if isinstance(item, str) and item:
        return base64.b64decode(item), 'image/png'
    return b'', ''


# ── the shapes ──────────────────────────────────────────────────────────────────────────────
def _openai(t, cfg, key, prompt, size):
    """OpenAI /v1/images/generations, and the three cards that speak it. Azure is the same BODY
    with its own URL and an api-key header instead of a bearer token."""
    model = cfg.get('model') or COMPAT[t][1]
    body = {'model': model, 'prompt': prompt, 'n': 1, 'size': size}
    if t == 'azure_openai_image':
        endpoint = str(cfg.get('endpoint') or '').rstrip('/')
        if not endpoint: raise RuntimeError('Azure OpenAI images: no endpoint saved (https://<name>.openai.azure.com)')
        deployment = cfg.get('deployment') or model
        url = f"{endpoint}/openai/deployments/{deployment}/images/generations?api-version={cfg.get('api_version') or '2025-04-01-preview'}"
        headers = {'api-key': key}
        body.pop('model', None)                      # the deployment IS the model on Azure
    else:
        base = (cfg.get('base_url') or COMPAT[t][0]).rstrip('/')
        url, headers = f'{base}/images/generations', ({'Authorization': f'Bearer {key}'} if key else {})
    r = requests.post(url, headers=headers, json=body, timeout=300)
    if r.status_code >= 300: _fail(r, LABELS.get(t, t))
    items = (r.json() or {}).get('data') or []
    if not items: return b'', '', model
    first = items[0]
    data, mime = _bytes_from(first.get('b64_json') or first.get('url') or '')
    return data, mime, model


def _gemini(t, cfg, key, prompt, size):
    model = cfg.get('model') or DEFAULT_MODEL[t]
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    r = requests.post(url, headers={'x-goog-api-key': key, 'Content-Type': 'application/json'},
                      json={'contents': [{'parts': [{'text': prompt}]}]}, timeout=300)
    if r.status_code >= 300: _fail(r, LABELS[t])
    for cand in (r.json() or {}).get('candidates') or []:
        for part in ((cand.get('content') or {}).get('parts') or []):
            inline = part.get('inlineData') or part.get('inline_data') or {}
            if inline.get('data'):
                return base64.b64decode(inline['data']), inline.get('mimeType') or 'image/png', model
    return b'', '', model


def _stability(t, cfg, key, prompt, size):
    model = cfg.get('model') or DEFAULT_MODEL[t]
    w, h = size.split('x')
    r = requests.post(f'https://api.stability.ai/v2beta/stable-image/generate/{model}',
                      headers={'Authorization': f'Bearer {key}', 'Accept': 'application/json'},
                      files={'none': ''},          # the API insists on multipart, even with no image in
                      data={'prompt': prompt, 'output_format': 'png',
                            'aspect_ratio': '1:1' if w == h else ('2:3' if int(w) < int(h) else '3:2')},
                      timeout=300)
    if r.status_code >= 300: _fail(r, LABELS[t])
    return base64.b64decode((r.json() or {}).get('image') or '' or ''), 'image/png', model


def _openrouter(t, cfg, key, prompt, size):
    """OpenRouter returns images on a CHAT answer rather than an images endpoint."""
    model = cfg.get('model') or DEFAULT_MODEL[t]
    r = requests.post('https://openrouter.ai/api/v1/chat/completions',
                      headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                      json={'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                            'modalities': ['image', 'text']}, timeout=300)
    if r.status_code >= 300: _fail(r, LABELS[t])
    for ch in (r.json() or {}).get('choices') or []:
        for img in ((ch.get('message') or {}).get('images') or []):
            url = (img.get('image_url') or {}).get('url') or ''
            if url:
                data, mime = _bytes_from(url)
                return data, mime, model
    return b'', '', model


def _replicate(t, cfg, key, prompt, size):
    """Start a prediction, then wait for it. This one path is how FLUX, SDXL, Ideogram, Recraft
    and the rest arrive without a card each."""
    model = cfg.get('model') or DEFAULT_MODEL[t]
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    w, h = size.split('x')
    r = requests.post(f'https://api.replicate.com/v1/models/{model}/predictions', headers=headers,
                      json={'input': {'prompt': prompt, 'aspect_ratio': '1:1' if w == h else ('2:3' if int(w) < int(h) else '3:2')}},
                      timeout=120)
    if r.status_code >= 300: _fail(r, LABELS[t])
    job = r.json() or {}
    poll = (job.get('urls') or {}).get('get') or f"https://api.replicate.com/v1/predictions/{job.get('id')}"
    deadline = time.time() + POLL_S
    while job.get('status') in ('starting', 'processing') and time.time() < deadline:
        time.sleep(POLL_EVERY)
        g = requests.get(poll, headers=headers, timeout=60)
        if g.status_code >= 300: _fail(g, LABELS[t])
        job = g.json() or {}
    if job.get('status') == 'failed':
        raise RuntimeError(f"{LABELS[t]}: {job.get('error') or 'the model refused the prompt'}")
    if job.get('status') != 'succeeded':
        raise RuntimeError(f'{LABELS[t]}: the image was still not ready after {POLL_S}s')
    out = job.get('output')
    first = out[0] if isinstance(out, list) and out else out
    data, mime = _bytes_from(first if isinstance(first, str) else '')
    return data, mime, model


# ── the card's Test button, and the tool agents call ────────────────────────────────────────
def test(store, c) -> str:
    """Generate the smallest thing that proves the key works, and keep nothing."""
    out = generate(store, 'a single small grey square on a white background', c=c)
    return f"{LABELS.get(out['provider'], out['provider'])} drew a {len(out['data']):,}-byte image with {out['model']}"


def run_image_generate(store, args: dict, message_id: int = None, task_id: int = None, **_) -> dict:
    """The tool. Draws the picture and FILES it as an attachment on the message, which is what
    puts it in front of the owner - the timeline already shows images inline (artifacts.py).
    Returning bytes to an agent instead would leave the owner with nothing to look at."""
    from . import artifacts
    out = generate(store, (args or {}).get('prompt'), size=(args or {}).get('size') or '1024x1024')
    mid = message_id or (args or {}).get('message_id')
    if not mid: return {'provider': out['provider'], 'model': out['model'], 'bytes': len(out['data'])}
    ext = {'image/jpeg': 'jpg', 'image/webp': 'webp'}.get(out['mime'], 'png')
    name = f"image-{int(time.time())}.{ext}"
    path = artifacts.attachment_dir(int(mid)) / name
    path.write_bytes(out['data'])
    aid = store.add_attachment({'MessageId': int(mid), 'Name': name, 'ContentType': out['mime'],
                                'Size': len(out['data']), 'Inline': 1, 'Path': str(path)})
    logger.info(f"images: {out['provider']} drew {len(out['data']):,} bytes for message {mid}")
    return {'attachment_id': aid, 'name': name, 'provider': out['provider'], 'model': out['model'],
            'bytes': len(out['data']), 'prompt': out['prompt']}

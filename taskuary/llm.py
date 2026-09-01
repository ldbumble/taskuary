"""The triage brain -> one provider-agnostic llm(system, user) -> str callable, the shape
triage.classify_intent expects. Which brain is the owner's choice (setting `triage_ai`):

    ''                  first ACTIVE AI connector with a key (anthropic/openai/azure_openai/
                        openrouter) - or keyless ollama, for a local model

    connector:<id>      that specific AI connector instance
    connector:<type>    legacy/default form - first active instance of that type
    cli:<agent>         your CODING CLI does the triage too - one headless run per message,
                        same brain that works the tasks, no second API key to buy

Cloud keys are cheap and instant per message; a CLI run is slower and heavier but keeps
everything on one model (and one bill). Configure it in Settings -> Triage & routing.
"""
import base64, json, mimetypes, requests
from pathlib import Path

AI_TYPES = ('anthropic', 'openai', 'azure_openai', 'openrouter', 'ollama')

# What a vision model will look at. "See below." is half the mail this app reads, and below was
# a screenshot - a text-only funnel filed the sentence and threw the actual ask away.
VISION_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/webp')
VISION_MAX, VISION_BYTES = 4, 5 * 1024 * 1024      # per call: how many images, and how big each


def readable_images(store, message_ids, cap: int = VISION_MAX) -> list:
    """[(media_type, base64)] for the images on these messages, or [] when the owner has vision
    switched off. SVG and PDF are skipped: no provider takes them as image input."""
    if str(store.get_settings().get('vision_enabled') or '1') != '1': return []
    out = []
    for mid in message_ids or []:
        for a in store.list_attachments(mid):
            if len(out) >= cap: return out
            ct = str(a.get('ContentType') or '').split(';')[0].lower()
            path = a.get('Path')
            if not path: continue
            if ct not in VISION_TYPES:
                ct = mimetypes.guess_type(path)[0] or ''
                if ct not in VISION_TYPES: continue
            f = Path(path)
            try:
                if not f.is_file() or f.stat().st_size > VISION_BYTES: continue
                out.append((ct, base64.b64encode(f.read_bytes()).decode()))
            except OSError:
                continue
    return out
# Triage answers with a one-line JSON object, so it needs almost nothing. A report SUMMARY
# needs room - and on a reasoning model a small budget is spent thinking and the visible
# answer comes back EMPTY, which is how reports ended up filing raw data with no summary.
MAX_TOKENS = 400


def make_cli_llm(store, agent_name: str, model: str = None, cwd: str = None, trace=None, cancel=None, resume=None):
    """A CLI agent as the classifier: prompt in on stdin, JSON out. The repo working dir
    is dropped - triage is about the message, not about any checkout.

    And the MODEL drops a tier: `light_model` on the agent profile (Connections > AI CLI
    agents) is what runs here - triage, drafts, summaries, the digest - while the profile's
    main `model` stays reserved for the coding sessions. One brain, two gears: the classifier
    reads one email; it does not need the model that rewrites your codebase."""
    row = store.get_agent(agent_name)
    if not row: return None
    prof = {k: v for k, v in json.loads(row.get('Config') or '{}').items() if k not in ('cwd', 'cwd_map')}
    light = str(prof.get('light_model') or '')
    if light.startswith('effort:'):
        # codex on a ChatGPT plan serves ONLY the plan's models - no mini/nano tier exists -
        # so its cheap gear is reasoning effort on the same model (verified: -c
        # model_reasoning_effort=low answers in a fraction of the tokens)
        prof['args'] = list(prof.get('args') or []) + ['-c', f"model_reasoning_effort={light.split(':', 1)[1].strip()}"]
    elif light:
        # 'gpt-5.4-mini@low' - a model from codex's own /model list and one of its reasoning levels
        from .climodels import split_pick
        m, eff = split_pick(light)
        prof['model'] = m
        if eff: prof['args'] = list(prof.get('args') or []) + ['-c', f'model_reasoning_effort={eff}']
    if model: prof['model'] = model     # an explicit per-job model outranks the light gear
    if cwd: prof['cwd'] = cwd           # a scheduled skill that lives in a repo runs from that repo (reports.run_agent)
    prof['timeout'] = min(int(prof.get('timeout') or 300), 300)
    def llm(system, user, max_tokens=MAX_TOKENS, images=None):
        """max_tokens is advisory here - a CLI has no such flag; the system prompt already says
        how long the answer should be. `images` is accepted and dropped: a CLI reads files off
        disk itself, and the prompt already names their paths."""
        from .agents import run_cli
        kwargs = {'cancel': cancel} if cancel is not None else {}
        out, sid, _diff = run_cli(prof, f'{system}\n\n{user}', trace or (lambda *a: None),
                                  resume=resume, **kwargs)
        # what the caller needs to CONTINUE this conversation instead of starting another one
        llm.session_id = sid or resume
        return out
    llm.session_id = resume
    return llm


def build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None):
    """The brain, or the demo's script. Everything in the app asks for its brain here, which is
    the one place a demo can be told to answer without a key, a CLI, or a request that leaves
    the machine (demo.py)."""
    from . import demo
    # the demo answers from a script: no key, no CLI, no request leaving the machine
    if demo.enabled(): return demo.brain()
    return _build_llm(store, pick, model, trace, cancel, resume)


def _build_llm(store, pick=None, model=None, trace=None, cancel=None, resume=None):
    """The brain named by `pick` ('' = first active AI connector, 'connector:<id>',
    'cli:<agent>'), defaulting to the triage_ai setting - callers like reports may name
    their OWN brain and model per job instead of riding the triage tier."""
    pick = (pick if pick is not None else store.get_settings().get('triage_ai') or '').strip()
    if pick.startswith('cli:'): return make_cli_llm(store, pick[4:], model, trace=trace, cancel=cancel, resume=resume)
    want = pick[10:] if pick.startswith('connector:') else None
    want_id = int(want) if want and want.isdigit() else None
    for c in store.list_connectors():
        # a local model server (ollama) is the one brain that needs no key to be real
        ready = c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama')
        selected = not want or (c['ConnectorId'] == want_id if want_id is not None else c['Type'] == want)
        if c['Type'] in AI_TYPES and ready and selected:
            full = store.get_connector(c['ConnectorId'], with_secret=True)
            cfg = json.loads(full.get('ConfigJson') or '{}')
            if model: cfg = {**cfg, 'model': model}
            return make_llm(full['Type'], cfg, full.get('Secret'))
    return None


def make_llm(t, cfg: dict, key: str):
    if not key and t != 'ollama': raise RuntimeError('no API key saved - paste one under Credentials')
    if t == 'anthropic':
        import anthropic
        cli = anthropic.Anthropic(api_key=key)
        model = cfg.get('model') or 'claude-opus-5'
        def llm(system, user, max_tokens=MAX_TOKENS, images=None):
            # images FIRST: every provider reads a picture better when the question follows it
            content = ([{'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}}
                        for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
            r = cli.messages.create(model=model, max_tokens=max_tokens, system=system,
                                    messages=[{'role': 'user', 'content': content}])
            if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
            return next((b.text for b in r.content if b.type == 'text'), '')
        return llm
    if t == 'openai':
        urls = ['https://api.openai.com/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or 'gpt-4o-mini'
    elif t == 'openrouter':
        # one key, the whole catalog behind the OpenAI schema - open-weights models included.
        # Model strings are OpenRouter's names ('meta-llama/llama-3.3-70b-instruct', ...);
        # 'openrouter/auto' lets their router pick, so an empty model box still works.
        urls = ['https://openrouter.ai/api/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}', 'X-Title': 'Taskuary'}, cfg.get('model') or 'openrouter/auto'
    elif t == 'ollama':
        # a LOCAL server speaking the OpenAI surface. Ollama's port out of the box, but base_url
        # reaches LM Studio (:1234), llama.cpp, vLLM - anything /v1-compatible - so open-source
        # models triage your mail without a byte leaving the machine. No key unless the server
        # demands one; the model must be named because only `ollama list` knows what's pulled.
        base = (cfg.get('base_url') or 'http://127.0.0.1:11434').rstrip('/')
        if not cfg.get('model'): raise RuntimeError('a local brain needs its model named - `ollama list` shows what is installed')
        urls, model = [f'{base}/v1/chat/completions'], cfg['model']
        headers = {'Authorization': f'Bearer {key}'} if key else {}
    elif t == 'azure_openai':
        ep = (cfg.get('endpoint') or '').rstrip('/')
        if not (ep and cfg.get('deployment')): raise RuntimeError('azure_openai needs endpoint + deployment')
        # Azure's v1 surface first (no api-version, OpenAI-compatible, all params work);
        # legacy deployments URL as fallback for resources without it. An explicit
        # api_version in the config skips straight to legacy with that version.
        legacy = f"{ep}/openai/deployments/{cfg['deployment']}/chat/completions?api-version={cfg.get('api_version') or '2024-12-01-preview'}"
        urls = [legacy] if cfg.get('api_version') else [f'{ep}/openai/v1/chat/completions', legacy]
        headers, model = {'api-key': key}, cfg['deployment']
    else:
        raise RuntimeError(f'unknown AI connector type: {t}')

    def llm(system, user, max_tokens=MAX_TOKENS, images=None):
        # two independent compat axes: newer models reject max_tokens ("use
        # max_completion_tokens"), older Azure api-versions reject max_completion_tokens,
        # and older Azure resources 404 the v1 url - walk the grid until one works
        content = ([{'type': 'image_url', 'image_url': {'url': f'data:{ct};base64,{b64}'}}
                    for ct, b64 in (images or [])] + [{'type': 'text', 'text': user}]) if images else user
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]
        last = None
        for url in urls:
            for tok_param in ('max_completion_tokens', 'max_tokens'):
                body = {'messages': msgs, tok_param: max_tokens}
                if model: body['model'] = model
                # a local model may spend its first call loading weights off disk - give it room
                r = requests.post(url, headers=headers, json=body, timeout=180 if t == 'ollama' else 60)
                if r.status_code == 200:
                    return r.json()['choices'][0]['message']['content']
                last = r
                if r.status_code == 404: break                     # wrong surface -> next url
                if not (r.status_code == 400 and 'max_completion_tokens' in r.text):
                    raise RuntimeError(f'{t} error {r.status_code} at {url.split("?")[0]}: {r.text[:300]}')
        raise RuntimeError(f'{t} error {last.status_code} at {urls[-1].split("?")[0]}: {last.text[:300]}')
    return llm


def test_ai(store, cid: int) -> str:
    """Real round trip through the configured model; returns a detail string or raises."""
    c = store.get_connector(cid, with_secret=True)
    out = make_llm(c['Type'], json.loads(c.get('ConfigJson') or '{}'), c.get('Secret'))(
        'Reply with exactly: ok', 'ping')
    return f'model responded: {(out or "").strip()[:80]} - wired into intent triage'

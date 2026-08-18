"""The triage brain -> one provider-agnostic llm(system, user) -> str callable, the shape
triage.classify_intent expects. Which brain is the owner's choice (setting `triage_ai`):

    ''                  first ACTIVE AI connector with a key (anthropic/openai/azure_openai)
    connector:<type>    that specific AI connector
    cli:<agent>         your CODING CLI does the triage too - one headless run per message,
                        same brain that works the tasks, no second API key to buy

Cloud keys are cheap and instant per message; a CLI run is slower and heavier but keeps
everything on one model (and one bill). Configure it in Settings -> Triage & routing.
"""
import json, requests

AI_TYPES = ('anthropic', 'openai', 'azure_openai')


def make_cli_llm(store, agent_name: str):
    """A CLI agent as the classifier: prompt in on stdin, JSON out. The repo working dir
    is dropped - triage is about the message, not about any checkout."""
    row = store.get_agent(agent_name)
    if not row: return None
    prof = {k: v for k, v in json.loads(row.get('Config') or '{}').items() if k not in ('cwd', 'cwd_map')}
    prof['timeout'] = min(int(prof.get('timeout') or 300), 300)
    def llm(system, user):
        from .agents import run_cli
        out, _sid, _diff = run_cli(prof, f'{system}\n\n{user}\n\nAnswer with the JSON object only.',
                                   lambda *a: None)
        return out
    return llm


def build_llm(store):
    pick = (store.get_settings().get('triage_ai') or '').strip()
    if pick.startswith('cli:'): return make_cli_llm(store, pick[4:])
    want = pick[10:] if pick.startswith('connector:') else None
    for c in store.list_connectors():
        if c['Type'] in AI_TYPES and c['Active'] and c['HasSecret'] and (not want or c['Type'] == want):
            full = store.get_connector(c['ConnectorId'], with_secret=True)
            return make_llm(full['Type'], json.loads(full.get('ConfigJson') or '{}'), full.get('Secret'))
    return None


def make_llm(t, cfg: dict, key: str):
    if not key: raise RuntimeError('no API key saved - paste one under Credentials')
    if t == 'anthropic':
        import anthropic
        cli = anthropic.Anthropic(api_key=key)
        model = cfg.get('model') or 'claude-opus-5'
        def llm(system, user):
            r = cli.messages.create(model=model, max_tokens=300, system=system,
                                    messages=[{'role': 'user', 'content': user}])
            if r.stop_reason == 'refusal': raise RuntimeError('model refused the request')
            return next((b.text for b in r.content if b.type == 'text'), '')
        return llm
    if t == 'openai':
        urls = ['https://api.openai.com/v1/chat/completions']
        headers, model = {'Authorization': f'Bearer {key}'}, cfg.get('model') or 'gpt-4o-mini'
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

    def llm(system, user):
        # two independent compat axes: newer models reject max_tokens ("use
        # max_completion_tokens"), older Azure api-versions reject max_completion_tokens,
        # and older Azure resources 404 the v1 url - walk the grid until one works
        msgs = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        last = None
        for url in urls:
            for tok_param in ('max_completion_tokens', 'max_tokens'):
                body = {'messages': msgs, tok_param: 300}
                if model: body['model'] = model
                r = requests.post(url, headers=headers, json=body, timeout=60)
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

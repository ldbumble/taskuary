"""Cloud AI connectors -> one provider-agnostic llm(system, user) -> str callable, the
shape triage.classify_intent expects. The first ACTIVE AI connector with a saved key wins
(anthropic / openai / azure_openai). Configure them on the Connectors tab; used for
intent triage today - drafting/coding agents are CLIs and bring their own models.
"""
import json, requests

AI_TYPES = ('anthropic', 'openai', 'azure_openai')


def build_llm(store):
    for c in store.list_connectors():
        if c['Type'] in AI_TYPES and c['Active'] and c['HasSecret']:
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
        url, headers, model = 'https://api.openai.com/v1/chat/completions', {'Authorization': f'Bearer {key}'}, cfg.get('model') or 'gpt-4o-mini'
    elif t == 'azure_openai':
        ep = (cfg.get('endpoint') or '').rstrip('/')
        if not (ep and cfg.get('deployment')): raise RuntimeError('azure_openai needs endpoint + deployment')
        url = f"{ep}/openai/deployments/{cfg['deployment']}/chat/completions?api-version={cfg.get('api_version') or '2024-06-01'}"
        headers, model = {'api-key': key}, None
    else:
        raise RuntimeError(f'unknown AI connector type: {t}')
    def llm(system, user):
        # newer OpenAI/Azure models reject max_tokens ("use max_completion_tokens");
        # older Azure api-versions reject max_completion_tokens - try modern, fall back
        body = {'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                'max_completion_tokens': 300}
        if model: body['model'] = model
        r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code == 400 and 'max_completion_tokens' in r.text:
            body.pop('max_completion_tokens'); body['max_tokens'] = 300
            r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code != 200: raise RuntimeError(f'{t} error {r.status_code}: {r.text[:300]}')
        return r.json()['choices'][0]['message']['content']
    return llm


def test_ai(store, cid: int) -> str:
    """Real round trip through the configured model; returns a detail string or raises."""
    c = store.get_connector(cid, with_secret=True)
    out = make_llm(c['Type'], json.loads(c.get('ConfigJson') or '{}'), c.get('Secret'))(
        'Reply with exactly: ok', 'ping')
    return f'model responded: {(out or "").strip()[:80]} - wired into intent triage'

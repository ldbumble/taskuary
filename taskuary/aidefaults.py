"""The AI defaults in one place: who triages, who codes, who assists - and on which model.

Settings named a BRAIN and stopped there. Which MODEL that brain would actually run was a
different screen every time: the connector's own card for an API key, Connections > AI CLI
agents for a CLI's light gear, and a plain text box for the assistant. Three defaults, three
places, and the Triage & routing page could not tell you what was about to happen next - the
owner asked where the "triage model" was set and the honest answer was "somewhere else, and it
depends" (2026-09-10).

So this module answers one question per slot - WHAT WILL ACTUALLY RUN, AND WHO OWNS IT - and
writes the answer back to whichever screen owns it. It stores nothing of its own: the
connector's `model`, the profile's `model` / `light_model` and the `concierge_model` setting
remain the truth. The older screens keep working and cannot disagree with this one, which is
the whole reason not to introduce a fourth place to set a model.

The split between the two gears is the part worth keeping straight. A CLI agent has a MAIN
model for coding sessions and a LIGHT model for the one-message jobs - triage, drafts,
summaries, the digest (llm.make_cli_llm). Naming the same CLI as both the coder and the triage
brain is normal and cheap; it is the light gear that keeps it cheap.
"""
import json

from . import climodels

# One row per default. `gear` says WHICH of a CLI profile's two models this slot sets, and is
# the reason a coder and a triage brain can be the same agent without fighting over one field.
SLOTS = [
    {'key': 'triage_ai', 'label': 'Triage brain', 'pick': 'brain', 'gear': 'light',
     'desc': 'Reads every inbound message and decides: a task to do, a question to answer, or FYI to file.',
     'why': 'One message in, one line of JSON out - so this wants your cheapest fast model, not your best one.'},
    {'key': 'default_agent', 'label': 'Default coding agent', 'pick': 'agent', 'gear': 'main',
     'desc': 'Works the tasks. Start session, Send to coding agent and auto-dispatch all use this one.',
     'why': 'This is the expensive, capable gear: it reads your repository and writes code.'},
    {'key': 'concierge_ai', 'label': 'Assistant', 'pick': 'brain', 'gear': 'light',
     'model_setting': 'concierge_model',
     'desc': 'Speaks on the Assistant tab and walks you through the pipe.',
     'why': 'Turn by turn and conversational, so it rides the same quick gear as triage.'},
]
SLOT = {s['key']: s for s in SLOTS}


def _prof(cfg, store, name: str) -> dict:
    """An agent's editable profile - config.toml first, the store row as the fallback, which is
    the same order put_agent writes them in."""
    p = (cfg.get('agents') or {}).get(name)
    if p: return dict(p)
    row = store.get_agent(name)
    try: return json.loads(row.get('Config') or '{}') if row else {}
    except ValueError: return {}


def _cli_of(cfg, store, name: str) -> str:
    from .clis import _base
    return _base(_prof(cfg, store, name).get('cmd') or name)


def ai_connectors(store) -> list:
    from .llm import AI_TYPES
    return [c for c in store.list_connectors() if c['Type'] in AI_TYPES]


def auto_target(store):
    """Which connector `auto` (an empty pick) actually resolves to right now - the same rule
    llm._build_llm uses. Without this the picker says "auto" and the owner still cannot tell
    which model reads their mail."""
    for c in ai_connectors(store):
        if c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama'): return c
    return None


def resolve(store, cfg, slot_key: str) -> dict:
    """What this slot is set to, what will run, and which screen owns the model."""
    s, settings = SLOT[slot_key], store.get_settings()
    value = str(settings.get(slot_key) or '')
    out = {'key': slot_key, 'label': s['label'], 'desc': s['desc'], 'why': s['why'],
           'value': value, 'model': '', 'effort': '', 'choices': [], 'efforts': [],
           # what a BLANK model box means here - shown as the field's placeholder, so an empty
           # field reads as "the provider's default" instead of as something not set up yet
           'default_hint': '', 'owner': '', 'owner_link': '', 'ready': True, 'note': ''}

    if s['pick'] == 'agent':
        name = value or ''
        prof = _prof(cfg, store, name)
        cli = _cli_of(cfg, store, name) if name else ''
        cat = climodels.catalog(cli)
        model, effort = climodels.split_pick(prof.get('model') or '')
        out.update(model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, model),
                   owner=f'the {name} profile' if name else '', owner_link='agents', cli=cli,
                   ready=bool(name))
        if not name: out['note'] = 'no coding agent configured yet'
        return out

    # a brain: auto, one AI connector, or one of your CLI agents on its light gear
    if value.startswith('cli:'):
        name = value[4:]
        prof, cli = _prof(cfg, store, name), _cli_of(cfg, store, name)
        cat = climodels.catalog(cli)
        light = str(prof.get('light_model') or '')
        model, effort = ('', light[7:]) if light.startswith('effort:') else climodels.split_pick(light)
        out.update(model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, model),
                   default_hint=f'same as the coding model ({cli})',
                   owner=f'the {name} profile (light model)', owner_link='agents', cli=cli)
        if not light: out['note'] = f'no light model set - triage runs on the {cli} coding model, which is the expensive gear'
        return out

    c = store.get_connector(int(value[10:])) if value.startswith('connector:') and value[10:].isdigit() else auto_target(store)
    if not c:
        out.update(ready=False, note='no AI connector holds a key yet')
        return out
    try: conf = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: conf = {}
    out.update(model=str(conf.get('model') or ''), choices=_conn_models(c['Type']),
               default_hint=_conn_default(c['Type']),
               owner=f"the {c['Name']} card", owner_link=f"connector:{c['ConnectorId']}",
               connector=c['ConnectorId'])
    if not value: out['note'] = f"auto — currently {c['Name']}"
    if not out['model']: out['note'] = (out['note'] + '; ' if out['note'] else '') + f"blank = {_conn_default(c['Type'])}"
    return out


def _efforts(cat: dict, model: str) -> list:
    """The reasoning levels THIS model offers, per the CLI's own catalogue. Empty for every CLI
    whose effort flag we cannot spell - climodels documents why muse is deliberately empty."""
    return next((m.get('efforts') or [] for m in cat.get('models') or [] if m.get('id') == model), [])


# What a blank model box actually means per provider, copied from llm.make_llm so the UI can
# say it rather than showing an empty field that looks unconfigured.
_CONN_DEFAULT = {'anthropic': 'claude-opus-5', 'openai': 'gpt-4o-mini', 'openrouter': 'openrouter/auto',
                 'meta': 'muse-spark-1.2', 'ollama': '(required - name the model you pulled)',
                 'azure_openai': '(the deployment name on the card)'}
_CONN_MODELS = {'anthropic': ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
                'openai': ['gpt-4o-mini', 'gpt-4o'],
                'openrouter': ['openrouter/auto', 'meta-llama/llama-3.3-70b-instruct'],
                'meta': ['muse-spark-1.2', 'muse-spark-1.3', 'muse-spark-1.2-contributor']}


def _conn_default(t: str) -> str: return _CONN_DEFAULT.get(t, '')
def _conn_models(t: str) -> list: return list(_CONN_MODELS.get(t, []))


def state(store, cfg) -> dict:
    """Every slot, plus the options each picker offers."""
    agents = [a['Name'] for a in store.list_agents()]
    return {'slots': [resolve(store, cfg, s['key']) for s in SLOTS], 'agents': agents}


def _save_profile(store, cfg, name: str, prof: dict) -> None:
    """Mirror put_agent exactly - config.toml AND the store row, or the two drift and whichever
    is read first wins."""
    from . import config
    cfg.setdefault('agents', {})[name] = prof
    config.save(cfg)
    store.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))


def apply(store, cfg, slot_key: str, value=None, model=None, effort=None, actor: str = 'owner') -> dict:
    """Point a slot at a brain/agent and set the model it runs on, writing each half to the
    screen that owns it. `model`/`effort` of None mean "leave alone"; '' means "clear"."""
    if slot_key not in SLOT: raise ValueError(f'unknown slot: {slot_key}')
    s = SLOT[slot_key]
    if value is not None:
        store.set_setting(slot_key, str(value), actor)
    if model is None and effort is None: return resolve(store, cfg, slot_key)

    cur = resolve(store, cfg, slot_key)
    model = cur['model'] if model is None else str(model).strip()
    effort = cur['effort'] if effort is None else str(effort).strip()
    now = str(store.get_settings().get(slot_key) or '')

    if s['pick'] == 'agent':
        if not now: raise ValueError('no coding agent is configured to set a model on')
        prof = _prof(cfg, store, now)
        prof['model'] = f'{model}@{effort}' if (model and effort) else model
        if not prof['model']: prof.pop('model', None)
        _save_profile(store, cfg, now, prof)
    elif now.startswith('cli:'):
        name = now[4:]
        prof = _prof(cfg, store, name)
        # codex on a ChatGPT plan has no smaller model, so its cheap gear is effort alone -
        # that is what `effort:<level>` spells, and llm.make_cli_llm turns it into the flag.
        light = f'effort:{effort}' if (effort and not model) else (f'{model}@{effort}' if (model and effort) else model)
        prof['light_model'] = light
        if not light: prof.pop('light_model', None)
        _save_profile(store, cfg, name, prof)
    else:
        setting = s.get('model_setting')
        if setting:                                     # the assistant keeps a plain override
            store.set_setting(setting, model, actor)
        else:
            cid = cur.get('connector')
            if not cid: raise ValueError('no AI connector to set a model on')
            conf = json.loads(store.get_connector(cid).get('ConfigJson') or '{}')
            conf['model'] = model
            if not model: conf.pop('model', None)
            store.set_connector_config(cid, conf)
    store.audit('setting', 0, 'save', actor, detail=f'{slot_key} model={model or "(default)"}{"@" + effort if effort else ""}')
    return resolve(store, cfg, slot_key)

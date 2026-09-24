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
    {'key': 'default_agent', 'label': 'Default coding CLI', 'pick': 'agent', 'gear': 'main',
     'desc': 'Works the tasks. Start session, Send to coding agent and auto-dispatch all use this one.',
     'why': 'This is the expensive, capable gear: it reads your repository and writes code.'},
    {'key': 'concierge_ai', 'label': 'Assistant', 'pick': 'brain', 'gear': 'light',
     'model_setting': 'concierge_model',
     'desc': 'Speaks on the Assistant tab and walks you through the pipe.',
     'why': 'Turn by turn and conversational, so it rides the same quick gear as triage.'},
    # The fourth worker had no row here, so the page that exists to say "what will actually run"
    # was silent about half the tasks on the board. `assistant_ai` was buried on the Assistant tab
    # calling itself the bubble's brain, and with it blank general._selected quietly prefers an API
    # connector over a CLI - so a general task ran on Azure gpt-5.4 while `default_brain` said
    # claude, and the owner could not see why (2026-09-16). Same picker as the others: a CLI or a
    # connector, whichever this work needs.
    {'key': 'assistant_ai', 'label': 'General agent', 'pick': 'brain', 'gear': 'light',
     'model_setting': 'assistant_model',
     'desc': 'Works every general task: research, planning, writing, a job with no repository. Also the '
             'floating bubble and the WhatsApp doorway.',
     'why': 'A CLI here can run tools, drive a browser and post to the wall; an API brain has no shell, '
            'so it can only read and write - quicker, and enough for chat.'},
    # The fifth worker, and the only one that does not have to be able to write. A report's own
    # brain writes its summary; this decides where the finished run goes - four yes/nos about text
    # somebody else produced. They were one setting while both were chat models; they are two now
    # because a decision model can do the second job and not the first.
    {'key': 'judge_ai', 'label': 'Where runs go', 'pick': 'judge', 'gear': 'light',
     'desc': 'Decides whether a finished report lands on your Timeline, your work rail, reaches you '
             'right away, or goes out - against the sentences you wrote on its card.',
     'why': 'Four yes/nos about a result somebody else wrote. It does not need to be able to talk, '
            'so a decision model belongs here and nowhere else.'},
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
    from .cli_connections import resolve
    return _base(resolve(cfg, _prof(cfg, store, name)).get('cmd') or name)


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
        model, effort = climodels.split_pick(_gears(cfg, store, name).get('model') or '')
        out.update(model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, model),
                   owner=f'the {cli} coding profile' if cli else '', owner_link='agents', cli=cli,
                   display=cli,
                   ready=bool(name))
        if not name: out['note'] = 'no coding agent configured yet'
        return out

    # the judge: blank has a second meaning here (the report's own brain, which is what this did
    # before there was a setting), and a decision model is a thing only this slot can be pointed at
    if s['pick'] == 'judge':
        # What it is actually asked, from the one place that builds it - a rule you cannot read is a
        # rule you cannot trust, and this slot's whole job is four questions somebody should be able
        # to see (the owner, 2026-09-17: "show the wording for jev ... what are the decision choices").
        from .reports import EVIDENCE_RULE, LINE_SAYS, LINES
        out['decides'] = [{'line': l, 'says': f'Decide whether to {LINE_SAYS[l]}.'} for l in LINES]
        out['evidence'] = EVIDENCE_RULE
        if not value:
            out.update(display="the report's own brain", kind='brain',
                       note="the report's own brain judges it, which is how this worked before there "
                            "was a setting")
            return out
        row = store.get_connector(int(value[10:])) if value.startswith('connector:') and value[10:].isdigit() else None
        if row is not None and row['Type'] == 'typesafe':
            out.update(display=row['Name'] or 'TypeSafe Jev', ready=bool(row['Active'] and row['HasSecret']),
                       default_hint='jev-latest', owner=f"the {row['Name']} card", kind='decision',
                       owner_link=f"connector:{row['ConnectorId']}",
                       note='' if row['Active'] and row['HasSecret'] else 'paste a key on its card first')
            return out
        out['kind'] = 'brain'
        # anything else is an ordinary brain, so it falls through to the brain branches below

    # a brain: one AI connector, or one of your CLI agents on its light gear. BLANK is the default brain - shown as the
    # brain it is, never "auto - first active AI connector" (the owner, 2026-09-24: "first connected should not matter")
    if not value:
        from .agents import default_pick
        value = default_pick(store)
        if value: out.update(value=value, default=True)
    if value.startswith('cli:'):
        from .llm import ASSISTANT_DEFAULT, LIGHT_DEFAULT
        name = value[4:]
        prof, cli = _prof(cfg, store, name), _cli_of(cfg, store, name)
        cat = climodels.catalog(cli)
        light = str(_gears(cfg, store, name).get('light_model') or '')
        if slot_key == 'concierge_ai':
            # what concierge.brain runs: its own model, else the Assistant default - never the profile's light model,
            # which is triage's (this card said "the coding model, the expensive gear" while every turn ran on haiku)
            light, dflt, owner = str(settings.get(s['model_setting']) or ''), ASSISTANT_DEFAULT.get(cli, ''), 'this page'
        else: dflt, owner = LIGHT_DEFAULT.get(cli, ''), f'the {name} profile (light model)'
        model, effort = ('', light[7:]) if light.startswith('effort:') else climodels.split_pick(light)
        said = (f"{dflt[7:]} effort" if dflt.startswith('effort:') else dflt) if dflt else f'the {cli} default'
        out.update(model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, model),
                   default_hint=f"{said} - the {'Assistant' if slot_key == 'concierge_ai' else 'light'} default",
                   owner=owner, owner_link='' if slot_key == 'concierge_ai' else 'agents', cli=cli)
        if not light and not dflt: out['note'] = f'no light model set - this runs on the {cli} coding model, which is the expensive gear'
        return out

    c = store.get_connector(int(value[10:])) if value.startswith('connector:') and value[10:].isdigit() else auto_target(store)
    if not c:
        out.update(ready=False, note='no AI connector holds a key yet')
        return out
    try: conf = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: conf = {}
    # A slot with its own model setting OWNS its model - save wrote it there (see `save` below),
    # so reading the connector's back showed the wrong box and an override you set looked lost.
    own = str(settings.get(s['model_setting']) or '') if s.get('model_setting') else ''
    out.update(model=own or str(conf.get('model') or ''), choices=_conn_models(c['Type']),
               default_hint=str(conf.get('model') or '') or _conn_default(c['Type']),
               owner=('this page' if s.get('model_setting') else f"the {c['Name']} card"),
               owner_link='' if s.get('model_setting') else f"connector:{c['ConnectorId']}",
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
    from . import agents as hub_agents
    agents = [a['Name'] for a in store.list_agents()]
    preferred = [str(store.get_settings().get('default_agent') or 'coder')]
    return {'slots': [resolve(store, cfg, s['key']) for s in SLOTS], 'agents': agents,
            'judge_options': judge_options(store),
            'agent_options': hub_agents.cli_agent_options(store, preferred=preferred, coding_only=True)}


def judge_options(store) -> list:
    """What the judge picker offers ON TOP OF the ordinary brains: blank, meaning the report's own
    brain, and the decision models - which are offered HERE AND NOWHERE ELSE, because they cannot
    answer a prompt and would leave any other slot with nothing to say.

    The brains themselves are not repeated here: the page already has /api/brains and its values
    are the ones `llm.build_llm` accepts, so a second builder is a second thing to keep in step."""
    out = [{'value': '', 'label': "the report's own brain", 'kind': 'auto', 'ready': True}]
    out += [{'value': f"connector:{c['ConnectorId']}", 'kind': 'decision', 'ready': bool(c['HasSecret']),
             'label': f"{c['Name'] or 'TypeSafe Jev'} — decisions only, no text"}
            for c in store.list_connectors() if c['Type'] == 'typesafe' and c['Active']]
    return out


def _brain_key(cfg, store, name: str) -> str:
    """The cli_connections key behind a worker - its provider, which is the brain's own name.
    Not `_cli_of`: that is the executable's basename, and cursor's connection is keyed `cursor`
    while its command is `cursor-agent`."""
    from .cli_connections import cli_key
    prof = _prof(cfg, store, name)
    provider = str(prof.get('provider') or '')
    return provider[4:] if provider.startswith('cli:') else cli_key(prof.get('cmd') or name)


def _gears(cfg, store, name: str) -> dict:
    """The brain's gears, falling back to the worker's own while an install is mid-upgrade.

    `migrate` lifts them onto the connection at boot, but a config handed in before that has run -
    or by an older API caller - still carries them on the profile, and reading nothing would look
    to the owner like their model had been forgotten. Step 3 of the spec removes the fallback with
    the field itself."""
    from .cli_connections import GEAR_FIELDS, gears
    on_brain, prof = gears(cfg, _brain_key(cfg, store, name)), _prof(cfg, store, name)
    return {f: on_brain.get(f) or str(prof.get(f) or '') for f in GEAR_FIELDS}


def _save_profile(store, cfg, name: str, prof: dict) -> None:
    """Mirror put_agent exactly - config.toml AND the store row, or the two drift and whichever
    is read first wins.

    A GEAR set here belongs to the BRAIN, not to the worker, so it is written on the connection the
    profile points at. Left on the profile it would be dropped by resolve() the moment anything
    read it back - model and light_model are command fields now (the 2026-09-16 spec)."""
    from . import config
    from .cli_connections import GEAR_FIELDS, sync
    key = _brain_key(cfg, store, name)
    for field in GEAR_FIELDS:
        # a key PRESENT and empty means "clear it" - which is why apply no longer pops it: popped,
        # a cleared gear was indistinguishable from one nobody set, and the brain kept the old model
        if key and field in prof:
            conns = cfg.setdefault('cli_connections', {})
            if prof[field]: conns.setdefault(key, {})[field] = prof[field]
            elif key in conns: conns[key].pop(field, None)
        prof.pop(field, None)
    cfg.setdefault('agents', {})[name] = prof
    config.save(cfg)
    sync(cfg, store, name)


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
    if not now and s['pick'] == 'brain':               # a blank card IS the default brain - its model goes there
        from .agents import default_pick
        now = default_pick(store)

    if s['pick'] == 'agent':
        if not now: raise ValueError('no coding agent is configured to set a model on')
        prof = _prof(cfg, store, now)
        prof['model'] = f'{model}@{effort}' if (model and effort) else model
        _save_profile(store, cfg, now, prof)
    elif now.startswith('cli:') and slot_key == 'concierge_ai':
        store.set_setting(s['model_setting'], f'effort:{effort}' if (effort and not model) else model, actor)
    elif now.startswith('cli:'):
        name = now[4:]
        prof = _prof(cfg, store, name)
        # codex on a ChatGPT plan has no smaller model, so its cheap gear is effort alone -
        # that is what `effort:<level>` spells, and llm.make_cli_llm turns it into the flag.
        light = f'effort:{effort}' if (effort and not model) else (f'{model}@{effort}' if (model and effort) else model)
        prof['light_model'] = light
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

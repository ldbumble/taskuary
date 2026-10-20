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
summaries, the digest (llm.make_cli_llm). Naming the same CLI as both the coding brain and the triage
brain is normal and cheap; it is the light gear that keeps it cheap.
"""
import json, re
from loguru import logger

from . import climodels

# One row per default. `gear` says WHICH of a CLI profile's two models this slot sets, and is
# the reason a coding brain and a triage brain can be the same agent without fighting over one field.
SLOTS = [
    {'key': 'triage_ai', 'label': 'Triage brain', 'pick': 'brain', 'gear': 'light',
     'desc': 'Reads every inbound message and decides: a task to do, a question to answer, or FYI to file. '
             'Also runs the Advisor and writes what Taskuary remembers.',
     'why': 'One message in, one line of JSON out - so this wants your cheapest fast model, not your best one.'},
    # the CLI tool itself, never a profile (the owner, 2026-10-15: "it's models or cli tools only") - it held `default_agent`,
    # a profile name, which is how a profile came to be read as a brain
    {'key': 'default_brain', 'label': 'Default coding CLI', 'pick': 'cli', 'gear': 'main',
     'desc': 'Works the tasks. Start session, Send to coding agent and auto-dispatch all use this one.',
     'why': 'This is the expensive, capable gear: it reads your repository and writes code.'},
    {'key': 'concierge_ai', 'label': 'Assistant', 'pick': 'brain', 'gear': 'light',
     'model_setting': 'concierge_model',
     'desc': 'Speaks in the chat here and on your phone (WhatsApp, Telegram), and walks you through the pipe.',
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
             'floating bubble.',
     'why': 'A CLI here can run tools, drive a browser and post to the wall; an API brain has no shell, '
            'so it can only read and write - quicker, and enough for chat.'},
    # The fifth worker, and the only one that does not have to be able to write. A report's own
    # brain writes its summary; this decides where the finished run goes - four yes/nos about text
    # somebody else produced. They were one setting while both were chat models; they are two now
    # because a decision model can do the second job and not the first.
    {'key': 'judge_ai', 'label': 'Where runs go', 'pick': 'judge', 'gear': 'light',
     'desc': 'Decides whether a finished report shows under Reports, lands on your work rail, reaches you '
             'right away, or goes out - against the sentences you wrote on its card.',
     'why': 'Four yes/nos about a result somebody else wrote. It does not need to be able to talk, '
            'so a decision model belongs here and nowhere else.'},
]
SLOT = {s['key']: s for s in SLOTS}


def _conn(cfg, key: str) -> dict:
    """The CLI connection a brain key names, with its shipped defaults - the brain itself."""
    from .cli_connections import with_defaults
    c = (cfg.get('cli_connections') or {}).get(str(key or ''))
    return with_defaults(c) if c is not None else {}


def _cli_of(cfg, key: str) -> str:
    """The executable family behind a CLI brain - its model catalogue is keyed by it (cursor's connection runs cursor-agent)."""
    from .clis import _base
    return _base(_conn(cfg, key).get('cmd') or key)


def _save_gear(store, cfg, key: str, field: str, value: str) -> None:
    """A model belongs to the BRAIN - the CLI connection - never to a profile (the 2026-09-16 spec; the owner, 2026-10-15).
    Empty clears it. The profile rows are execution snapshots of their connection, so they are refreshed after."""
    from . import config
    from .cli_connections import sync
    conns = cfg.setdefault('cli_connections', {})
    if value: conns.setdefault(key, {})[field] = value
    elif key in conns: conns[key].pop(field, None)
    config.save(cfg)
    sync(cfg, store)


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
           'default_hint': '', 'owner': '', 'owner_link': '', 'ready': True, 'note': '',
           # the settings this card stands for, so a link to one of them (#settings=..&key=assistant_model) finds the card: its rows are
           # not drawn under the panel, and a search hit for "General agent model" landed on no setting at all (verify, 2026-10-19)
           'settings': [slot_key, *([s['model_setting']] if s.get('model_setting') else [])]}

    if s['pick'] == 'cli':
        from .agents import default_brain
        key = value or default_brain(store)
        cli = _cli_of(cfg, key) if key else ''
        cat = climodels.catalog(cli)
        model, effort = climodels.split_pick(str(_conn(cfg, key).get('model') or ''))
        out.update(value=key, model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, model), resolved=_resolved(cat, model),
                   owner=f'the {key} connection' if key else '', owner_link='ai_apps', cli=cli, display=key, default=not value,
                   ready=bool(key))
        if not key: out['note'] = 'no CLI connected yet'
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
        from .agents import brain_key
        key = brain_key(store, value, cfg)
        conn, cli = _conn(cfg, key), _cli_of(cfg, key)
        cat = climodels.catalog(cli)
        light = str(conn.get('light_model') or '')
        if slot_key == 'concierge_ai':
            # what concierge.brain runs: its own model, else the Assistant default - never the brain's light model,
            # which is triage's (this card said "the coding model, the expensive gear" while every turn ran on haiku)
            light, dflt, owner = str(settings.get(s['model_setting']) or ''), ASSISTANT_DEFAULT.get(cli, ''), 'this page'
        else: dflt, owner = LIGHT_DEFAULT.get(cli, ''), f'the {key} connection (light model)'
        model, effort = ('', light[7:]) if light.startswith('effort:') else climodels.split_pick(light)
        if slot_key == 'concierge_ai' and not effort:
            from .llm import ASSISTANT_EFFORT
            effort = ASSISTANT_EFFORT.get(cli, '')          # what concierge.brain runs when the pick names no effort
        said = (f"{dflt[7:]} effort" if dflt.startswith('effort:') else dflt) if dflt else f'the {cli} default'
        # a blank box runs the gear's default model, so its efforts and version are that model's
        seen = model or ('' if dflt.startswith('effort:') else dflt)
        out.update(model=model, effort=effort, choices=cat['choices'], efforts=_efforts(cat, seen), resolved=_resolved(cat, seen),
                   default_hint=f"{said} - the {'Assistant' if slot_key == 'concierge_ai' else 'light'} default",
                   owner=owner, owner_link='' if slot_key == 'concierge_ai' else 'ai_apps', cli=cli)
        if not light and not dflt: out['note'] = f'no light model set - this runs on the {cli} coding model, which is the expensive gear'
        from .agents import runs_here
        # a brain that does not start is not "what will run": the card said claude while triage failed on it
        if not runs_here({'cmd': conn.get('cmd') or cli}): out.update(ready=False, note=f"'{cli}' is not installed on this machine")
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


def said(store, slot_key: str, cfg=None) -> str:
    """One brain in the owner's words: the CLI tool or AI connection and the model it runs - "Claude Code, claude-sonnet-5-5".
    Never the setting's raw value: a `cli:<profile>` pick named a profile, so the Assistant told the owner it ran on that profile's
    name while every turn ran Claude Code on sonnet, and a blank slot read "auto" (the owner, 2026-10-15: it is set to a specific
    model, not to a profile)."""
    from .clis import KNOWN
    try:
        if cfg is None:
            from . import config
            cfg = config.load()
        r = resolve(store, cfg, slot_key)
    except Exception as e:
        logger.debug(f'aidefaults: {slot_key} could not be said - {e}'); return ''
    if r.get('cli'):
        tool = next((k['label'] for k in KNOWN if k['name'] == r['cli']), r['cli'])
        model = r.get('model') or str(r.get('default_hint') or '').split(' - ')[0]
    elif r.get('connector'):
        c = store.get_connector(r['connector'])
        try: conf = json.loads((c or {}).get('ConfigJson') or '{}')
        except ValueError: conf = {}
        # Azure names its model by the deployment on the card; a placeholder hint ("(required ...)") is not a model
        hint = '' if str(r.get('default_hint') or '').startswith('(') else r.get('default_hint')
        tool, model = (c['Name'] or c['Type']) if c else 'an AI connection', r.get('model') or conf.get('deployment') or hint or ''
    else: return r.get('display') or r.get('note') or 'not set'
    return (f"{tool}, {model}" if model else tool) + (f", {r['effort']} effort" if r.get('effort') else '') \
        + (' (the default brain)' if r.get('default') else '') + (f" - {r['note']}" if not r.get('ready', True) and r.get('note') else '')


def _entry(cat: dict, model: str) -> dict:
    """The catalogue row a model names: the exact id, else an alias (`sonnet`) read as the NEWEST id of that family, which is
    what the CLI itself runs - so an alias pick shows its efforts and the version it lands on."""
    ms = cat.get('models') or []
    if (hit := next((m for m in ms if m.get('id') == model), None)): return hit
    fam = [m for m in ms if model and re.fullmatch(rf'claude-{re.escape(model)}-\d[\w-]*', str(m.get('id')))]
    return max(fam, key=lambda m: [int(n) for n in re.findall(r'\d+', m['id'])], default={})


def _efforts(cat: dict, model: str) -> list:
    """The reasoning levels THIS model offers, per the CLI's own catalogue. Empty for every CLI
    whose effort flag we cannot spell - climodels documents why muse is deliberately empty."""
    return _entry(cat, model).get('efforts') or []


def _resolved(cat: dict, model: str) -> str:
    """The id an alias lands on ('' when the pick already is an id, or nothing is known)."""
    i = _entry(cat, model).get('id') or ''
    return i if i != model else ''


# What a blank model box actually means per provider, copied from llm.make_llm so the UI can
# say it rather than showing an empty field that looks unconfigured.
_CONN_DEFAULT = {'anthropic': 'claude-opus-5', 'openai': 'gpt-4o-mini', 'openrouter': 'openrouter/auto',
                 'meta': 'muse-spark-1.2', 'ollama': '(required - name the model you pulled)',
                 'azure_openai': '(the deployment name on the card)', 'vertex_ai': 'google/gemini-3.8-flash','chatgpt': '(the first model your plan lists)'}
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
    return {'slots': [resolve(store, cfg, s['key']) for s in SLOTS], 'agents': agents,
            'judge_options': judge_options(store),
            'agent_options': hub_agents.cli_agent_options(store, preferred=[hub_agents.default_brain(store)])}


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
    now = str(store.get_setting(slot_key) or '')
    if not now and s['pick'] == 'brain':               # a blank card IS the default brain - its model goes there
        from .agents import default_pick
        now = default_pick(store)

    if s['pick'] == 'cli':
        from .agents import default_brain
        key = now or default_brain(store)
        if not key: raise ValueError('no CLI is connected to set a model on')
        _save_gear(store, cfg, key, 'model', f'{model}@{effort}' if (model and effort) else model)
    elif now.startswith('cli:') and slot_key == 'concierge_ai':
        store.set_setting(s['model_setting'], f'effort:{effort}' if (effort and not model) else model, actor)
    elif now.startswith('cli:'):
        from .agents import brain_key
        # codex on a ChatGPT plan has no smaller model, so its cheap gear is effort alone -
        # that is what `effort:<level>` spells, and llm.make_cli_llm turns it into the flag.
        light = f'effort:{effort}' if (effort and not model) else (f'{model}@{effort}' if (model and effort) else model)
        _save_gear(store, cfg, brain_key(store, now, cfg), 'light_model', light)
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

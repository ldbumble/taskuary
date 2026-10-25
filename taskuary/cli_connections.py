"""CLI commands belong to connections; worker profiles reference a connection and a model.

config.toml is the editable source. Agent rows remain resolved execution snapshots for existing
runners, refreshed whenever a connection or profile changes.
"""
import copy
import json
import re
from loguru import logger

COMMAND_FIELDS = ('cmd', 'args', 'resume', 'resume_args', 'timeout', 'model_arg', 'acp', 'model', 'light_model', 'strong_model')
# The GEARS, which are the half of COMMAND_FIELDS clis.KNOWN ships no preset for: what a brain
# runs, as opposed to how it is invoked. `strong_model` is the third (the router, 2026-10-25): what
# hard work steps up to, set by the owner and never guessed from a model's name - blank means this
# brain has no strong tier, and nothing steps up on it.
GEAR_FIELDS = ('model', 'light_model', 'strong_model')


def gears(cfg, key: str) -> dict:
    """A brain's gears. MAIN runs the sessions - coding and general alike; LIGHT runs the
    one-message jobs (triage, drafts, summaries, the digest). One brain, two gears, and still ONE
    brain: `claude-main` and `claude-light` are not two providers (the owner, 2026-09-16)."""
    c = cfg.get('cli_connections', {}).get(str(key or '')) or {}
    return {f: str(c.get(f) or '') for f in GEAR_FIELDS}


def cli_key(command):
    base = re.sub(r'\.(exe|cmd|bat|ps1)$', '', re.split(r'[\\/]', str(command or '').strip())[-1], flags=re.I).lower()
    return {'cursor-agent': 'cursor'}.get(base, base)


def with_defaults(connection):
    """Complete legacy command-only connections using the shipped CLI setup.

    Missing fields inherit defaults; explicitly saved fields (including empty args) win.
    """
    from .clis import KNOWN
    preset = next((c for c in KNOWN if c['name'] == cli_key(connection.get('cmd'))), {})
    return {**{k: copy.deepcopy(v) for k, v in preset.items() if k in COMMAND_FIELDS}, **connection}


def migrate(cfg):
    """Split old inline command definitions once. Existing connection settings win."""
    before = copy.deepcopy(cfg)
    connections = cfg.setdefault('cli_connections', {})
    profiles = cfg.setdefault('agents', {})
    # A CLI's original coding entry owns its command flags, ahead of copies seeded for roles.
    ordered = sorted(profiles, key=lambda n: (str(profiles[n].get('kind') or 'coding') != 'coding', n != cli_key(profiles[n].get('cmd')), n))
    for name in ordered:
        profile = profiles[name]
        if profile.get('provider') or not profile.get('cmd'): continue
        key = cli_key(profile['cmd']) or name
        if key not in connections:
            connections[key] = {k: copy.deepcopy(profile[k]) for k in COMMAND_FIELDS if k in profile}
        # ...and when the connection already exists, its GEARS still have to be filled from this
        # profile before the pop below destroys them - `ordered` puts the coding profile first, so the coding
        # profile's model is the one a shared brain keeps. Two profiles on one brain wanting two
        # different models is precisely what a brain having its own gears stops being expressible.
        for field in GEAR_FIELDS:
            if profile.get(field) and not connections[key].get(field): connections[key][field] = profile[field]
        profile['provider'] = f'cli:{key}'
        for field in COMMAND_FIELDS: profile.pop(field, None)
    # The GEARS move too, for installs already carrying a provider - which the loop above skips.
    # They were left on the profile when the commands moved (with a patch scrubbing them whenever
    # the provider changed), and `model`/`light_model` are COMMAND_FIELDS now, so resolve() would
    # drop them and the owner would silently lose the models they chose. A connection the owner has
    # already set keeps what it has: the profile is the older, weaker copy.
    for name, profile in profiles.items():
        key = str(profile.get('provider') or '')[4:]
        if not key: continue
        for field in GEAR_FIELDS:
            if profile.get(field) and not (connections.get(key) or {}).get(field):
                connections.setdefault(key, {})[field] = profile[field]
            profile.pop(field, None)
    for key, connection in connections.items():
        connections[key] = with_defaults(connection)
    return cfg != before


def resolve(cfg, profile, brain: str = ''):
    """A profile's runnable row: the profile's own fields on the BRAIN its work runs on. A profile names no brain (the owner,
    2026-10-15: "profiles ... are layered on top of any brain tool"); `brain` is the connection key the caller chose for it
    (sync: the role's override, else the default brain). A legacy `provider` is read only when no brain is given."""
    provider = f'cli:{brain}' if brain else str(profile.get('provider') or '')
    if not provider:
        # Old callers remain compatible during upgrades - but the GEARS belong to the brain now, so
        # a profile still naming only its command takes them from the connection that command points
        # at. Without this a model set on the AI defaults screen was written to the brain and the
        # store row this mirrors to never saw it, which reads to the owner as a model that did not save.
        conn = cfg.get('cli_connections', {}).get(cli_key(profile.get('cmd'))) or {}
        return {**profile, **{f: conn[f] for f in GEAR_FIELDS if conn.get(f)}}
    if not provider.startswith('cli:'): raise ValueError('Choose a configured CLI provider')
    connection = cfg.get('cli_connections', {}).get(provider[4:])
    if not connection: raise ValueError(f'CLI connection {provider[4:]!r} is not configured')
    # The connection owns commands even if an old client sends stale inline copies.
    return {**{k: v for k, v in profile.items() if k not in COMMAND_FIELDS and k != 'provider'}, **with_defaults(connection)}


def brain_of(store, cfg, worker: str, profile: dict) -> str:
    """The connection a profile's row runs on: its role's override (profile_brains), else the default brain - when either
    names a connection; else '' and the legacy provider decides (an install from before the brain layer)."""
    try: over = json.loads(store.get_setting('profile_brains') or '{}')
    except (TypeError, ValueError): over = {}
    conns = cfg.get('cli_connections') or {}
    for key in ((over.get(worker) if isinstance(over, dict) else ''), store.get_setting('default_brain')):
        if str(key or '').strip() in conns: return str(key).strip()
    return ''


def adopt_installed(cfg, store) -> list:
    """Every AI CLI ON THIS MACHINE can be started - that is the whole idea of them.

    A CLI reaches the pickers only through a WORKER: a profile naming what it is for, bound to a
    connection naming how to run it. The setup wizard writes those for whatever was installed the
    day it ran, and never again - so Devin and Copilot, installed months later and detected by
    /api/cli/detect ever since, appeared nowhere and could not be started at all (the owner,
    2026-09-14: "any ai cli agents should be possible to start no? isn't that the whole idea of it").

    So: a known CLI that is installed gets its CONNECTION from clis.KNOWN, which already carries the
    headless flags each one needs. It gets no worker - a CLI is a brain, and the picker offers
    brains directly. It used to mint a coding worker named after the CLI, carrying CODING.md and
    the same purpose line as every other, so the only thing that varied between them was which CLI
    ran it; those clones are what put `copilot` on triage's menu and sent TQ-0588's coding work to
    it. A connection the owner edited stays edited. Returns nothing it made, which is nothing."""
    # cliinstall.find, not shutil.which: a vendor's installer writes the USER path and this process
    # keeps whatever environment it was launched with, so devin's own %LOCALAPPDATA%\devin\cli\bin
    # is invisible to a plain PATH lookup - which is exactly the CLI this exists for.
    from . import clis
    from .cliinstall import find as find_cli
    connections = cfg.setdefault('cli_connections', {})
    made = []
    for spec in clis.KNOWN:
        if not find_cli(spec['name']): continue
        key = cli_key(spec['cmd']) or spec['name']
        if key not in connections:
            connections[key] = with_defaults({k: v for k, v in spec.items() if k in COMMAND_FIELDS})
    return made


def sync(cfg, store, name=None):
    for worker, profile in cfg.get('agents', {}).items():
        if name is not None and worker != name: continue
        # a profile naming a CLI that is gone is that profile's problem, never the app's: it stopped every start with
        # "CLI connection 'claude' is not configured" (2026-10-06). It keeps its last row until a CLI is picked for it.
        try: resolved = resolve(cfg, profile, brain_of(store, cfg, worker, profile))
        except ValueError as e:
            logger.warning(f'{worker}: {e} - pick a CLI for it under Settings'); continue
        old = json.loads((store.get_agent(worker) or {}).get('Config') or '{}')
        resolved['cwd_map'] = {**(old.get('cwd_map') or {}), **(resolved.get('cwd_map') or {})}
        store.upsert_agent(worker, profile.get('kind', 'coding'), 'cli', json.dumps(resolved))


def set_profile(cfg, store, name, body):
    """Keep old command-based API callers working while persisting the two-layer config. A profile is instructions and names
    no CLI (the owner, 2026-10-15: "it's models or cli tools only"): a CLI the body names - `cmd` or `provider` - becomes that
    connection and this role's brain override (profile_brains), and the model it names lands on the connection's gears."""
    current = cfg.setdefault('agents', {}).get(name) or json.loads((store.get_agent(name) or {}).get('Config') or '{}')
    profile = {**current, **body}
    picked = str(profile.pop('provider', '') or '') if 'provider' in body else ''
    if 'cmd' in body and not picked:
        key = cli_key(body['cmd'])
        cfg.setdefault('cli_connections', {}).setdefault(key, with_defaults({k: body[k] for k in COMMAND_FIELDS if k in body}))
        picked = f'cli:{key}'
    if picked:
        if not picked.startswith('cli:'): raise ValueError('Choose a configured CLI provider')
        resolve(cfg, profile, picked[4:])  # reject a dangling connection before saving
        for field in GEAR_FIELDS:
            if field in body: cfg.setdefault('cli_connections', {}).setdefault(picked[4:], {})[field] = body[field]
        try: over = json.loads(store.get_setting('profile_brains') or '{}')
        except (TypeError, ValueError): over = {}
        store.set_setting('profile_brains', json.dumps({**(over if isinstance(over, dict) else {}), name: picked[4:]}), 'owner')
    for key in (*COMMAND_FIELDS, 'provider'): profile.pop(key, None)
    cfg['agents'][name] = profile
    return profile

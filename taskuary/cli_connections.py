"""CLI commands belong to connections; worker profiles reference a connection and a model.

config.toml is the editable source. Agent rows remain resolved execution snapshots for existing
runners, refreshed whenever a connection or profile changes.
"""
import copy
import json
import re

COMMAND_FIELDS = ('cmd', 'args', 'resume', 'resume_args', 'timeout', 'model_arg', 'acp', 'model', 'light_model')
# The two GEARS, which are the half of COMMAND_FIELDS clis.KNOWN ships no preset for: what a brain
# runs, as opposed to how it is invoked.
GEAR_FIELDS = ('model', 'light_model')


def gears(cfg, key: str) -> dict:
    """A brain's two gears. MAIN runs the sessions - coding and general alike; LIGHT runs the
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
    ordered = sorted(profiles, key=lambda n: (n != 'coder', n != cli_key(profiles[n].get('cmd')), n))
    for name in ordered:
        profile = profiles[name]
        if profile.get('provider') or not profile.get('cmd'): continue
        key = cli_key(profile['cmd']) or name
        if key not in connections:
            connections[key] = {k: copy.deepcopy(profile[k]) for k in COMMAND_FIELDS if k in profile}
        # ...and when the connection already exists, its GEARS still have to be filled from this
        # profile before the pop below destroys them - `ordered` puts coder first, so the coding
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


def resolve(cfg, profile):
    provider = str(profile.get('provider') or '')
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
    return {**{k: v for k, v in profile.items() if k not in COMMAND_FIELDS}, **with_defaults(connection)}


def adopt_installed(cfg, store) -> list:
    """Every AI CLI ON THIS MACHINE can be started - that is the whole idea of them.

    A CLI reaches the pickers only through a WORKER: a profile naming what it is for, bound to a
    connection naming how to run it. The setup wizard writes those for whatever was installed the
    day it ran, and never again - so Devin and Copilot, installed months later and detected by
    /api/cli/detect ever since, appeared nowhere and could not be started at all (the owner,
    2026-09-14: "any ai cli agents should be possible to start no? isn't that the whole idea of it").

    So: a known CLI that is installed gets its connection from clis.KNOWN (which already carries the
    headless flags each one needs) and, if no worker is bound to it yet, a coding worker named after
    it - the coding profile is CODER.md, the same one `coder` and `codex` carry, so the only thing
    that varies between them is which CLI runs it. Nothing already configured is touched: a
    connection the owner edited stays edited, and a CLI they deliberately have no worker for stays
    that way once one exists. Returns the workers it made."""
    # cliinstall.find, not shutil.which: a vendor's installer writes the USER path and this process
    # keeps whatever environment it was launched with, so devin's own %LOCALAPPDATA%\devin\cliin
    # is invisible to a plain PATH lookup - which is exactly the CLI this exists for.
    from . import clis
    from .cliinstall import find as find_cli
    connections = cfg.setdefault('cli_connections', {})
    profiles = cfg.setdefault('agents', {})
    bound = {str(p.get('provider') or '')[4:] for p in profiles.values() if str(p.get('provider') or '').startswith('cli:')}
    coding = next((p for p in profiles.values() if p.get('kind') == 'coding'), {})
    made = []
    for spec in clis.KNOWN:
        if not find_cli(spec['name']): continue
        key = cli_key(spec['cmd']) or spec['name']
        if key not in connections:
            connections[key] = with_defaults({k: v for k, v in spec.items() if k in COMMAND_FIELDS})
        if key in bound or spec['name'] in profiles: continue
        profiles[spec['name']] = {
            'kind': 'coding', 'rules_doc': 'coder', 'provider': f'cli:{key}',
            'purpose': coding.get('purpose') or 'Write, review and test code in a repository.',
            # the repositories the other coding workers already know, so a new CLI lands in the same
            # checkouts rather than nowhere
            'cwd_map': dict(coding.get('cwd_map') or {})}
        made.append(spec['name'])
    if made: sync(cfg, store)
    return made


def sync(cfg, store, name=None):
    for worker, profile in cfg.get('agents', {}).items():
        if name is not None and worker != name: continue
        resolved = resolve(cfg, profile)
        old = json.loads((store.get_agent(worker) or {}).get('Config') or '{}')
        resolved['cwd_map'] = {**(old.get('cwd_map') or {}), **(resolved.get('cwd_map') or {})}
        store.upsert_agent(worker, profile.get('kind', 'coding'), 'cli', json.dumps(resolved))


def set_profile(cfg, store, name, body):
    """Keep old command-based API callers working while persisting the two-layer config."""
    current = cfg.setdefault('agents', {}).get(name) or json.loads((store.get_agent(name) or {}).get('Config') or '{}')
    profile = {**current, **body}
    provider = str(profile.get('provider') or '')
    if 'cmd' in body and 'provider' not in body:
        # A legacy editor changing its executable means choosing that CLI connection.
        key = cli_key(body['cmd'])
        provider = profile['provider'] = f'cli:{key}'
        cfg.setdefault('cli_connections', {}).setdefault(key, with_defaults({k: body[k] for k in COMMAND_FIELDS if k in body}))
    if provider:
        resolve(cfg, profile)  # reject dangling provider references before saving
        # A model named through the profile editor is a choice about the BRAIN, so it is written
        # where brains keep their gears. The scrub that used to live here is gone with the thing it
        # worked around: its comment was right - "model names belong to their provider" - and now
        # they are stored there, so a Claude model cannot follow a worker to Codex because it was
        # never on the worker to begin with.
        for field in GEAR_FIELDS:
            if field in body: cfg.setdefault('cli_connections', {}).setdefault(provider[4:], {})[field] = body[field]
        for key in COMMAND_FIELDS: profile.pop(key, None)
    cfg['agents'][name] = profile
    return profile

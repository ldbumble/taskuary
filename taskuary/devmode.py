"""DEVELOPER MODE ON AN UPGRADE (the owner, 2026-11-02: "for regular people everything should be a general agent, not coding").

The switch (agents.developer_mode) ships off, which on a home that already works with coding agents would take them away overnight.
So the first start that knows the switch decides it ONCE from what the home already holds: anything coding - a coding task, a coding
agent's run, a connected coding CLI or a picked coding brain, a code-host card or a repository map - turns it on; a home with none
stays off. The decision is written down (DECIDED: what tipped it, by 'migration') and never taken again, and a switch the owner set
themselves is never touched."""
from loguru import logger

DECIDED = 'developer_mode_decided'
CODE_HOSTS = ('github', 'gitlab', 'azdo')


def evidence(store, cfg: dict = None) -> str:
    "The first thing that says this home already codes, in a few words - '' when nothing does."
    from . import config, terminal
    cfg = config.load() if cfg is None else cfg
    has = lambda sql: store.cx.execute(sql).fetchone() is not None
    if has("SELECT 1 FROM task WHERE lower(Kind)='coding' LIMIT 1"): return 'a coding task'
    if has("SELECT 1 FROM run r JOIN agent a ON a.Name=r.AgentName WHERE lower(a.Kind) IN ('coding','cli') LIMIT 1"): return 'a coding agent run'
    if cfg.get('cli_connections'): return 'a coding CLI connected'
    if str(store.get_setting('default_brain') or '').strip(): return 'a coding brain picked'
    if any(c.get('Active') and c.get('Type') in CODE_HOSTS for c in store.list_connectors()): return 'a code-host card'
    if (cfg.get('github') or {}).get('default_repo') or terminal.repo_map(store): return 'a repository map'
    return ''


def migrate(store, cfg: dict = None) -> str | None:
    "Decide the switch once for a home that predates it. None when already decided; else what was decided, as the marker says it."
    if store.get_setting(DECIDED): return None
    from . import agents
    if store.setting_writer(agents.DEV_MODE) == 'owner': said = 'kept: the owner set it'
    else:
        why = evidence(store, cfg)
        store.set_setting(agents.DEV_MODE, '1' if why else '0', 'migration')
        said = f'on: {why}' if why else 'off: nothing coding here'
    store.set_setting(DECIDED, said, 'migration')
    store.audit('setting', 0, 'set', 'migration', detail={'key': agents.DEV_MODE, 'to': store.get_setting(agents.DEV_MODE), 'why': said})
    logger.info(f'developer mode decided once - {said}')
    return said

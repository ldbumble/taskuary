"""THE AGENT CONNECTOR: claude and codex speak ACP only through an npm adapter (clis.ADAPTERS), installed beside the CLI, never bundled.

"will the adapters get installed when you set up claude code cli tool in the card section. we need to do that. it does not have to be
built in no?" (the owner, 2026-11-06). Without it every agent start ran `npx -y <pkg>` - about 2.3 s more a start, and a download the
first time - and with no Node at all the argv road answered. So the CLI's own install takes one more step, `npm install -g` of the PINNED
package; a card whose CLI is already here says whether the connector is, in one quiet line with its own press; and a global copy of any
other version is never what runs (`runs_pinned`): a stale one left by an older release would speak a protocol this one no longer does.

WHAT IS INSTALLED is npm's own answer (`npm ls -g --depth=0 --json`), cached: a second-long spawn is no part of drawing a page. A stale
answer is served while a fresh one is read behind it, and an install through here forgets it at once.
"""
import json, os, threading, time
from pathlib import Path

from loguru import logger

from . import clis, pathcache, spawn

TTL = 600
STEP = 'Installing the agent connector…'
_LS = {'at': 0.0, 'pkgs': None, 'reading': False}
_LOCK = threading.Lock()
_BUSY = set()                     # the CLIs whose connector is installing right now, on whichever road


def row(name: str) -> dict: return clis.ADAPTERS.get(name) or {}
def split(pkg: str) -> tuple: return tuple(pkg.rsplit('@', 1))          # '@scope/x@1.2.3' -> ('@scope/x', '1.2.3')
def forget() -> None: _LS.update(at=0.0, pkgs=None)


def _ver(v: str) -> tuple:
    try: return tuple(int(x) for x in str(v).split('-')[0].split('.'))
    except ValueError: return ()


def _read(exe: str) -> dict:
    try:
        r = spawn.run([exe, 'ls', '-g', '--depth=0', '--json'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
        deps = json.loads(r.stdout or '{}').get('dependencies') or {}       # npm ls exits 1 over any extraneous package, and still answers
        return {k: str(v.get('version') or '') for k, v in deps.items() if isinstance(v, dict)}
    except Exception as e:
        logger.warning(f'npm ls -g did not answer: {e}'); return {}


def installed(refresh: bool = False) -> dict | None:
    """{package: version} npm has installed globally, or None when this machine has no npm. Cached: past TTL the old answer is
    served while a thread reads the new one; only the first look, or `refresh`, waits for npm."""
    from .cliinstall import npm
    exe = npm()
    if not exe: return None
    with _LOCK:
        have, stale = _LS['pkgs'], time.time() - _LS['at'] > TTL
        if have is not None and not refresh and not stale: return have
        if have is not None and not refresh:
            if not _LS['reading']:
                _LS['reading'] = True
                def again():
                    try: _LS.update(pkgs=_read(exe), at=time.time())
                    finally: _LS['reading'] = False
                threading.Thread(target=again, daemon=True, name='npm-ls').start()
            return have
    pkgs = _read(exe)
    _LS.update(pkgs=pkgs, at=time.time())
    return pkgs


def state(name: str, refresh: bool = False, busy: bool = True) -> dict:
    """The card's line: {pkg, want, have, status} - installed | update (an older one is here) | other (some other version) | missing |
    no_npm | installing. {} for a CLI that needs no connector."""
    ad = row(name)
    if not ad: return {}
    pkg, want = split(ad['pkg'])
    out = {'pkg': pkg, 'want': want, 'have': ''}
    if busy and name in _BUSY: return {**out, 'status': 'installing'}
    got = installed(refresh)
    if got is None: return {**out, 'status': 'no_npm'}
    have = got.get(pkg, '')
    st = 'installed' if have == want else 'missing' if not have else 'update' if _ver(have) < _ver(want) else 'other'
    return {**out, 'have': have, 'status': st}


def _beside(exe: str, pkg: str):
    """The version of the package this launcher runs, off its own package.json: npm's Windows shim sits beside node_modules, a posix
    link resolves into the package itself. None when neither is found."""
    p = Path(exe)
    dirs = [p.parent / 'node_modules' / pkg, p.parent.parent / 'lib' / 'node_modules' / pkg]
    try: dirs += list(Path(os.path.realpath(exe)).parents)[:6]
    except OSError: pass
    for d in dirs:
        try: j = json.loads((d / 'package.json').read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        if j.get('name') == pkg: return str(j.get('version') or '')
    return None


def runs_pinned(ad: dict, exe: str) -> bool:
    "Whether the adapter launcher at `exe` is the pinned version - read beside it, npm's own list when that cannot be found."
    pkg, want = split(ad['pkg'])
    v = _beside(exe, pkg)
    return (v if v is not None else (installed() or {}).get(pkg, '')) == want


def install(name: str, runner=None) -> dict:
    """`npm install -g` the pinned connector: one step of the CLI's install, or the card's own press. {..state, said}. It never fails
    the CLI's own install - with no npm, or an npm that failed, agents still start, on the command line or through npx."""
    from . import cliinstall
    ad = row(name)
    if not ad: return {}
    pkg, want = split(ad['pkg'])
    def say(t):
        if hasattr(runner, 'message'):
            try: runner.message(t)
            except RuntimeError: pass
        return t
    st = state(name, refresh=True, busy=False)
    if st['status'] == 'installed': return {**st, 'said': say(f'The agent connector ({pkg} {want}) is already installed.')}
    if st['status'] == 'no_npm':
        return {**st, 'said': say('npm is not on this machine, so the agent connector was not installed. Agents still work: '
                                  'Taskuary starts the CLI itself, a little slower.')}
    say(STEP)
    _BUSY.add(name)
    try: rc, _out = (runner or cliinstall._run)(cliinstall.npm_install(ad['pkg']), timeout=600)
    except Exception as e: rc = str(e)
    finally: _BUSY.discard(name); forget(); pathcache.forget()
    st = state(name, refresh=True, busy=False)
    if st['status'] == 'installed': return {**st, 'said': say(f'Agent connector {want} installed - agents start faster now.')}
    logger.warning(f'{name}: the agent connector did not install ({rc})')
    return {**st, 'said': say(f'The agent connector did not install (npm: {rc if isinstance(rc, str) else f"exited {rc}"}). '
                              'Agents still work without it, a little slower to start.')}


def start(name: str) -> bool:
    """Install it in the background, for the Set it up press: the CLI's own setup has the pane, and the card's line says this one."""
    if name in _BUSY or state(name).get('status') not in ('missing', 'update', 'other'): return False
    _BUSY.add(name)
    def work():
        try: install(name)
        except Exception as e: logger.warning(f'{name}: the agent connector did not install - {e}')
        finally: _BUSY.discard(name)
    threading.Thread(target=work, daemon=True, name=f'connector-{name}').start()
    return True

"""The optional packages: the ones the desktop build SHIPS, and the button that adds the rest.

Taskuary ships thin. boto3, pyodbc, sqlalchemy, openpyxl, pypdf and the rest are each wanted by
one card or one file type, and most installs want none of them - so "not installed" is a normal
thing to meet, not a broken install. What was not normal was the answer. "Run pip install boto3"
sends the owner off to find a terminal and work out WHICH Python the app is running in: the
packaged exe has none, a venv is usually not the one on PATH, and an editable checkout is a third
answer again. The app knows all of that already. So it offers a button.

Two things make that true on a double-clicked Taskuary.exe, where it was not:

  BUNDLE      the packages a desktop download arrives with. An exe cannot be asked to go and
              find a Python, so the cards that matter must simply work on it - taskuary.spec
              collects each of these into the build (owner, 2026-09-02: "you can't install
              boto3 on the desktop app since it's packaged already??").
  packages/   ...and the rest still get the button. pip is bundled too and run IN THIS PROCESS
              (a frozen exe has no interpreter to shell out to - sys.executable IS Taskuary.exe)
              installing into ~/.taskuary/packages, which is on sys.path from startup. Beside
              the owner's data, not inside the exe: one-file PyInstaller unpacks itself into a
              temp directory it deletes on exit, so anything written there lasts one run.

The list is closed on purpose. This runs pip, and pip runs arbitrary setup code: an open field
here would be "install anything on this machine" wearing a connector's clothes. That is also why
POST /api/deps/install is on guard.DENIED - it is the owner's button, never an agent's.
"""
import importlib, importlib.util, sys
from pathlib import Path

from loguru import logger

from . import spawn

# import name -> what to ask pip for. The pins follow pyproject's extras. A name that is not here
# cannot be installed from the UI, and install() says so rather than pretending.
OPTIONAL = {
    'boto3': 'boto3>=1.28',                  # the AWS card
    'pyodbc': 'pyodbc>=4',                   # SQL Server
    'sqlalchemy': 'sqlalchemy>=2',           # the 'any database' card (plus its engine driver)
    'psycopg2': 'psycopg2-binary',           # ...Postgres
    'pymysql': 'pymysql',                    # ...MySQL
    'openpyxl': 'openpyxl>=3',               # reading .xlsx attachments
    'pypdf': 'pypdf',                        # reading .pdf into the knowledge base
    'faster_whisper': 'faster-whisper>=1.0',  # local speech to text
    'winpty': 'pywinpty',                    # the interactive terminal on Windows
}

# What Taskuary.exe ships with, read by taskuary.spec at build time so the list lives in ONE
# place. faster_whisper is deliberately out: 200MB of runtime that then downloads models, wanted
# by a fraction of installs, and the button below covers it. winpty is collected by the spec
# already - it needs its binaries, not just its package.
BUNDLE = ('boto3', 'pyodbc', 'sqlalchemy', 'psycopg2', 'pymysql', 'openpyxl', 'pypdf')


class Missing(RuntimeError):
    """An optional package is not here. Carries the import name, so a card that catches this can
    offer the button instead of printing a command (channels.test_connector)."""
    def __init__(self, pkg: str, message: str = ''):
        self.package = pkg
        super().__init__(message or f'{pkg} is not installed')


def pip_name(pkg: str) -> str:
    """What the owner should see: 'pywinpty', not 'winpty>=0'."""
    return str(OPTIONAL.get(pkg) or pkg).split('>')[0].split('=')[0].split('[')[0]


def installed(pkg: str) -> bool:
    try: return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError): return False


def packages_dir() -> Path:
    from .config import home
    return home() / 'packages'


def use_packages() -> str:
    """Put the installed-here packages on the import path. Idempotent, and LAST on sys.path so a
    copy inside the build always wins over one the button added. Called at server startup,
    before anything can import an optional package."""
    p = str(packages_dir())
    if p not in sys.path:
        sys.path.append(p)
        importlib.invalidate_caches()
    return p


def frozen() -> bool: return bool(getattr(sys, 'frozen', False))


def can_install() -> tuple:
    """(may we, why not). The pip build installs into its own interpreter; the packaged build
    into ~/.taskuary/packages, with the pip it carries. Only a build without that pip has to
    say no - and then it says which install can."""
    if frozen() and not installed('pip'):
        return False, ('this packaged Taskuary.exe was built without pip inside it, so it can only '
                       'use what it already ships - the pip or source install can add the package, '
                       'or download a newer Taskuary.exe')
    return True, ''


def _pip_here(req: str) -> tuple:
    """pip, in THIS process, into the packages directory.

    A frozen exe cannot shell out to pip: `sys.executable -m pip` would start a second copy of
    the app. --only-binary because there is no compiler and no interpreter here to build a source
    distribution with, so a wheel is the only thing that could work anyway - and a package with
    no wheel for this Python says so in the output, which is a fixable answer."""
    import contextlib, io
    from pip._internal.cli.main import main as pip_main
    dst = packages_dir()
    dst.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = pip_main(['install', '--no-input', '--disable-pip-version-check', '--no-warn-script-location',
                       '--only-binary', ':all:', '--upgrade', '--target', str(dst), req])
    return int(rc or 0), buf.getvalue().strip()


def install(pkg: str, timeout: int = 900) -> dict:
    """pip install one of OPTIONAL where THIS Taskuary will import it from - which is the whole
    point of the button: the owner never has to work out which Python that is."""
    ok, why = can_install()
    if not ok: raise RuntimeError(why)
    req = OPTIONAL.get(pkg)
    if not req:
        raise ValueError(f'{pkg} is not one of the packages Taskuary installs '
                         f'({", ".join(sorted(OPTIONAL))})')
    if frozen():
        where = use_packages()
        rc, out = _pip_here(req)
    else:
        where = sys.executable
        r = spawn.run([sys.executable, '-m', 'pip', 'install', '--no-input', req],
                      capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        rc, out = r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()
    if rc != 0:
        raise RuntimeError(f'pip could not install {req}: ' + out[-400:])
    # a package installed into a RUNNING interpreter is invisible until the finders are told
    importlib.invalidate_caches()
    logger.info(f'installed {req} into {where}')
    return {'ok': True, 'package': pkg, 'name': pip_name(pkg), 'python': sys.executable, 'where': where,
            'ready': installed(pkg), 'pip': out[-400:]}

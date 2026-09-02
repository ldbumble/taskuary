"""The optional packages, and the one button that installs them.

Taskuary ships thin. boto3, pyodbc, sqlalchemy, openpyxl, pypdf and the rest are each wanted by
one card or one file type, and most installs want none of them - so "not installed" is a normal
thing to meet, not a broken install. What was not normal was the answer. "Run pip install boto3"
sends the owner off to find a terminal and work out WHICH Python the app is running in: the
packaged exe has none, a venv is usually not the one on PATH, and an editable checkout is a third
answer again. The app knows all of that already. So it offers a button.

The list is closed on purpose. This runs pip, and pip runs arbitrary setup code: an open field
here would be "install anything on this machine" wearing a connector's clothes. That is also why
POST /api/deps/install is on guard.DENIED - it is the owner's button, never an agent's.
"""
import importlib, importlib.util, sys

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


def can_install() -> tuple:
    """(may we, why not). A frozen exe has no pip and no site-packages of its own to install into,
    so a button there would only ever fail - say which install to use instead."""
    if getattr(sys, 'frozen', False):
        return False, ('this is the packaged Taskuary.exe, which has no Python to install into - '
                       'the cards that need an extra package want the pip or source install')
    return True, ''


def install(pkg: str, timeout: int = 900) -> dict:
    """pip install one of OPTIONAL into the interpreter running Taskuary - which is the whole
    point: it is the one Python whose site-packages this process will actually import from."""
    ok, why = can_install()
    if not ok: raise RuntimeError(why)
    req = OPTIONAL.get(pkg)
    if not req:
        raise ValueError(f'{pkg} is not one of the packages Taskuary installs '
                         f'({", ".join(sorted(OPTIONAL))})')
    r = spawn.run([sys.executable, '-m', 'pip', 'install', '--no-input', req],
                  capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    out = ((r.stdout or '') + (r.stderr or '')).strip()
    if r.returncode != 0:
        raise RuntimeError(f'pip could not install {req}: ' + out[-400:])
    # a package installed into a RUNNING interpreter is invisible until the finders are told
    importlib.invalidate_caches()
    logger.info(f'installed {req} into {sys.executable}')
    return {'ok': True, 'package': pkg, 'name': pip_name(pkg), 'python': sys.executable,
            'ready': installed(pkg), 'pip': out[-400:]}

"""A path into one person's machine names them - a user folder, a Windows short name, a session scratch dir. Nothing committed
may carry one (2026-10-22: two break-test scripts did). The guard states the shape it refuses, never anyone's name."""
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# a user folder followed by a name that is not a stand-in (the invented people CLAUDE.md lists, a placeholder, or a word)
STAND_INS = r'(?:owner|you|me|runner|example|username|configuration|features|alex|alexd|dana)\b'
USER_DIR = re.compile(r'(?i)(?:[A-Z]:[\\/]+Users|/Users|/home)[\\/]+(?!' + STAND_INS + r'|<|\{|\$|%|\.\.\.)[A-Za-z0-9_.~-]{2,}[\\/]')
SKIP = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.mp4', '.woff', '.woff2', '.ttf', '.pdf', '.xlsx', '.lock')


def test_no_committed_file_carries_a_path_into_someones_user_folder():
    files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for f in files:
        if f.endswith(SKIP) or f.startswith(('taskuary/web/', 'site/')): continue
        try: text = (ROOT / f).read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError): continue
        hits += [f'{f}:{n}' for n, line in enumerate(text.splitlines(), 1) if USER_DIR.search(line)]
    assert not hits, f'paths into a user folder: {hits[:10]}'


def test_the_guard_sees_the_shape_it_refuses():
    assert USER_DIR.search(r"H = r'C:\Users\SOMEONE~1\AppData\Local\Temp\x'")
    assert USER_DIR.search('/home/someone/work/x')
    assert not USER_DIR.search(r'C:\Users\owner\Documents\x') and not USER_DIR.search('/Users/alex/Projects/x')

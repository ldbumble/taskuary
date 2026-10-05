"""The stand-in names belong in prose and test data, never where an API or a shell expects its own word.

The privacy scrub (58c86189) replaced the owner's first name everywhere it appeared, and that name is also
a real word to two other programs: PowerShell's `Invoke-WebRequest -Uri` and the `uri` field of a Gemini
file upload. The Qwen installer then aborted on every Node-less Windows box and every Gemini voice clip
failed with "upload returned no file URI" - and the voice test had been scrubbed the same way, so it
agreed with the bug. These pin the two words, and catch the next scrub that lands on code.
"""
import re
from pathlib import Path

from taskuary import cliinstall

ROOT = Path(__file__).resolve().parent.parent / 'taskuary'
NAMES = ('alex', 'erin', 'gail', 'paula', 'ray', 'marcus', 'omar', 'doyle', 'blake', 'moreno', 'vance', 'colton', 'reed', 'keller')


def test_the_powershell_installer_downloads_with_the_parameter_powershell_knows():
    cmd = cliinstall.powershell_installer('https://vendor.example/install.ps1')
    assert "Invoke-WebRequest -UseBasicParsing -Uri 'https://vendor.example/install.ps1'" in cmd


def test_no_stand_in_name_is_a_string_literal_or_a_flag_in_the_app():
    """A quoted name or a `-Name` flag in code is a word some other program reads, not a person."""
    word = '|'.join(NAMES)
    quoted, flag = re.compile(rf"""['"]({word})['"]"""), re.compile(rf'\s-({word})\b', re.I)
    hits = [f'{p.relative_to(ROOT.parent)}:{i}: {l.strip()}' for p in ROOT.rglob('*.py')
            for i, l in enumerate(p.read_text(encoding='utf-8').splitlines(), 1)
            if not l.lstrip().startswith('#') and (quoted.search(l) or flag.search(l))]
    assert not hits, 'a stand-in name sits where code expects its own word:\n' + '\n'.join(hits)

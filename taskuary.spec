# PyInstaller spec: one-file Taskuary desktop exe with the web UI bundled.
# Build: pip install .[desktop,build,bundle] && pyinstaller taskuary.spec
# Output: dist/Taskuary.exe - double-click, native window, data in ~/.taskuary.
import os, sys

from PyInstaller.utils.hooks import collect_all

sys.path.insert(0, os.path.abspath(SPECPATH))   # noqa: F821 - PyInstaller injects it
from taskuary.deps import BUNDLE                # ONE list of what the desktop build ships


def _collect(*names):
    """Everything those packages need, or a loud line saying what the exe will be missing.

    A card that needs an optional package cannot be told "pip install it" on a double-clicked
    exe - there is no Python there to install into. So the download arrives complete: the
    packages in deps.BUNDLE are collected here, DATA FILES INCLUDED, which is not optional for
    boto3 (botocore is mostly JSON service models) or pyodbc. Missing from the build machine is
    a build that quietly ships without them, so say so while there is somebody reading."""
    datas, bins, hidden, gone = [], [], [], []
    for n in names:
        try:
            d, b, h = collect_all(n)
            datas += d; bins += b; hidden += h
        except Exception:
            gone.append(n)
    if gone:
        print(f'taskuary.spec: NOT in this build - {", ".join(gone)} '
              f'(pip install .[desktop,build,bundle] first, or those cards ship dead)')
    return datas, bins, hidden


# the interactive terminal needs pywinpty's binaries too (conpty.dll, winpty-agent.exe...); pyte
# renders session transcripts (terminal.render) and wcwidth, which it uses, ships data tables;
# pip rides along so the Install button works on the exe as well (deps._pip_here)
datas, bins, hidden = _collect('winpty', 'wcwidth', 'pip', *BUNDLE)

a = Analysis(['taskuary/desktop.py'],
             # templates/ too: the operator documents (SOUL.md, CODER.md, TRIAGE.md...) seed the store
             # from here, and a build without them ran every prompt with no constitution (audit 2026-09-02)
             # EVERY DATA FILE THE WHEEL SHIPS, or the exe is a different program. lanes.json is
             # read by workerstate AT IMPORT, and funnel imports workerstate - so an exe without it
             # answered 500 on the Timeline, the Assistant, /api/setup, /api/problems and every
             # report, for ever, while the wheel was fine (a second machine's log, 2026-09-22:
             # FileNotFoundError on lanes.json under the exe's own _MEI extraction directory).
             # Keep this list beside
             # [tool.setuptools.package-data] in pyproject.toml: the two must say the same thing.
             datas=[('taskuary/web', 'taskuary/web'), ('taskuary/templates', 'taskuary/templates'),
                    ('taskuary/skills', 'taskuary/skills'), ('taskuary/lanes.json', 'taskuary'),
                    ('taskuary/whatsapp', 'taskuary/whatsapp'), *datas],
             binaries=bins,
             hiddenimports=['taskuary.server', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                            'websockets', 'uvicorn.protocols.websockets.websockets_impl', 'pyte', *hidden],
             excludes=['tkinter', 'matplotlib', 'PIL'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='Taskuary', console=False, upx=False,
          icon='assets/taskuary.ico')

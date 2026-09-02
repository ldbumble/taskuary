# PyInstaller spec: one-file Taskuary desktop exe with the web UI bundled.
# Build: pip install .[desktop,build] && pyinstaller taskuary.spec
# Output: dist/Taskuary.exe - double-click, native window, data in ~/.taskuary.
from PyInstaller.utils.hooks import collect_all

# the interactive terminal needs pywinpty's binaries too (conpty.dll, winpty-agent.exe…)
try: wp_datas, wp_bins, wp_hidden = collect_all('winpty')
except Exception: wp_datas, wp_bins, wp_hidden = [], [], []

# pyte renders session transcripts (terminal.render); wcwidth, which it uses, ships data tables
try: pt_datas, pt_bins, pt_hidden = collect_all('wcwidth')
except Exception: pt_datas, pt_bins, pt_hidden = [], [], []

a = Analysis(['taskuary/desktop.py'],
             # templates/ too: the operator documents (SOUL.md, CODER.md, TRIAGE.md...) seed the store
             # from here, and a build without them ran every prompt with no constitution (audit 2026-09-02)
             datas=[('taskuary/web', 'taskuary/web'), ('taskuary/templates', 'taskuary/templates'), *wp_datas, *pt_datas],
             binaries=wp_bins + pt_bins,
             hiddenimports=['taskuary.server', 'pyodbc', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                            'websockets', 'uvicorn.protocols.websockets.websockets_impl', 'pyte',
                            *wp_hidden, *pt_hidden],
             excludes=['tkinter', 'matplotlib', 'PIL', 'sqlalchemy'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='Taskuary', console=False, upx=False,
          icon='assets/taskuary.ico')

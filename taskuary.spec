# PyInstaller spec: one-file Taskuary desktop exe with the web UI bundled.
# Build: pip install .[desktop,build] && pyinstaller taskuary.spec
# Output: dist/Taskuary.exe - double-click, native window, data in ~/.taskuary.
from PyInstaller.utils.hooks import collect_all

# the interactive terminal needs pywinpty's binaries too (conpty.dll, winpty-agent.exe…)
try: wp_datas, wp_bins, wp_hidden = collect_all('winpty')
except Exception: wp_datas, wp_bins, wp_hidden = [], [], []

a = Analysis(['taskuary/desktop.py'],
             datas=[('taskuary/web', 'taskuary/web'), *wp_datas],
             binaries=wp_bins,
             hiddenimports=['taskuary.server', 'pyodbc', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                            'websockets', 'uvicorn.protocols.websockets.websockets_impl', *wp_hidden],
             excludes=['tkinter', 'matplotlib', 'PIL', 'sqlalchemy'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='Taskuary', console=False, upx=False,
          icon='assets/taskuary.ico')

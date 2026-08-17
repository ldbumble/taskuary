# PyInstaller spec: one-file Taskuary desktop exe with the web UI bundled.
# Build: pip install .[desktop,build] && pyinstaller taskuary.spec
# Output: dist/Taskuary.exe - double-click, native window, data in ~/.taskuary.
a = Analysis(['taskuary/desktop.py'],
             datas=[('taskuary/web', 'taskuary/web')],
             hiddenimports=['taskuary.server', 'pyodbc', 'webview.platforms.edgechromium', 'webview.platforms.winforms'],
             excludes=['tkinter', 'matplotlib', 'PIL', 'sqlalchemy'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name='Taskuary', console=False, upx=False,
          icon='assets/taskuary.ico')

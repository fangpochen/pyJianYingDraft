# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('F:\\py\\pyJianYingDraft\\pyJianYingDraft\\draft_content_template.json', 'pyJianYingDraft')],
    hiddenimports=['PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'uiautomation', 'pymediainfo', 'ffmpeg', 'DrissionPage', 'logging.handlers', 'queue', 'multiprocessing', 'pkg_resources.py2_warn', 'app.core.orchestrator', 'app.config', 'app.util.logging_setup', 'app.ui.main_window'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='JianYingBatchTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project = Path(SPECPATH)
analysis = Analysis(
    [str(project / "jaka_paint_app.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[
        (str(project / "samples" / "lineart_sample.png"), "samples"),
        (str(project / "AI_DEVELOPMENT_PROMPT.md"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="JAKA_Paint",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
release = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="JAKA_Paint",
)

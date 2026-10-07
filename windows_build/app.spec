# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# Direktori spesifikasi ini (windows_build/) dan root project
SPEC_DIR = Path(SPECPATH).resolve()
ROOT_DIR = SPEC_DIR.parent

# File dan folder statis yang dimasukkan ke dalam .exe
datas = [
    (str(ROOT_DIR / "static"), "static"),
    (str(ROOT_DIR / "LJK PPTSB FINAL.json"), "."),
]

# Hidden imports yang sering dibutuhkan oleh FastAPI, Uvicorn, Pydantic, PyMuPDF, dan OpenCV
hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "fastapi",
    "starlette",
    "starlette.routing",
    "starlette.responses",
    "pydantic",
    "pydantic_core",
    "multipart",
    "python_multipart",
    "dotenv",
    "fitz",
    "pymupdf",
    "cv2",
    "numpy",
    "core",
    "core.omr",
    "core.scanner",
    "core.sesi",
    "core.template",
]

a = Analysis(
    [str(ROOT_DIR / "main.py")],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="LJK_Reader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Diset True agar terminal terlihat (mudah melihat log server & troubleshooting)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

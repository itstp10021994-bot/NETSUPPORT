# PyInstaller spec for the hub + teacher console (single-file executable).
#
# Build:  pyinstaller packaging/hub.spec
# Output: dist/classroom-hub(.exe on Windows)
#
# The teacher web console (teacher/static/*) is bundled as data so a single
# executable serves the UI with no extra files to copy.

block_cipher = None

a = Analysis(
    ["../hub/server.py"],
    pathex=[".."],
    binaries=[],
    datas=[("../teacher/static", "teacher/static")],
    hiddenimports=["aiohttp"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="classroom-hub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=True,   # keep a console so the teacher sees the server log / URL
)

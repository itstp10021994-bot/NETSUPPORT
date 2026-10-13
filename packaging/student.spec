# PyInstaller spec for the student agent (single-file executable).
#
# Build:  pyinstaller packaging/student.spec
# Output: dist/classroom-student(.exe on Windows)
#
# The student agent needs no bundled data files (it only sends thumbnails and
# shows UI), but it does need the optional screen-capture backends. hiddenimports
# make sure PyInstaller pulls them in.

block_cipher = None

a = Analysis(
    ["../student/agent.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=["mss", "PIL", "PIL.Image"],
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
    name="classroom-student",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,   # no console window on the student machine
)

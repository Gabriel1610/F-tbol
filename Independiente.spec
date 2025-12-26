# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\isrgrootx1.pem', '.'), ('c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\Escudo.ico', '.')]
binaries = []
hiddenimports = ['flet', 'argon2', 'datetime']
tmp_ret = collect_all('mysql')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mysql.connector')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\Independiente.py'],
    pathex=[],
    binaries=binaries,
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
    name='Independiente',
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
    icon=['c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\Escudo.ico'],
)

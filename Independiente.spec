# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\Independiente.py'],
    pathex=[],
    binaries=[],
    datas=[('c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\isrgrootx1.pem', '.'), ('c:\\Users\\Gabriel\\OneDrive\\Computadora\\Documents\\Programas\\Fútbol\\Escudo.ico', '.'), ('C:\\Users\\Gabriel\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\mysql\\connector\\locales', 'mysql/connector/locales')],
    hiddenimports=['flet', 'mysql.connector', 'argon2', 'datetime', 'mysql.connector.locales.eng.client_error'],
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

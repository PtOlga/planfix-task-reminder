# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['enhanced_planfix_reminder.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Добавляем файлы которые будут включены в .exe
        ('config.ini.example', '.'),
      ],
    hiddenimports=[
        # Модули которые PyInstaller может не найти автоматически
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer', 
        'idna',
        'plyer',
        'plyer.platforms.win',
        'plyer.platforms.win.notification',
        'queue',
        'threading',
        'datetime',
        'configparser',
        'json',
        'webbrowser',
        'winsound',
        'time',
        'sys',
        'os',
        'typing'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем тяжелые модули которые нам не нужны
        'matplotlib',
        'matplotlib.pyplot',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'Pillow',
        'PyQt5',
        'PyQt6', 
        'PySide2',
        'PySide6',
        'sklearn',
        'tensorflow',
        'torch',
        'cv2',
        'selenium',
        'pygame',
        'kivy'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PlanfixReminder',          # Красивое имя вместо длинного
    debug=False,                     # Отключаем отладку для релиза
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                        # Включаем сжатие UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                   # ВАЖНО: убираем консольное окно!
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='planfix.ico'             # Раскомментируйте если добавите иконку
)
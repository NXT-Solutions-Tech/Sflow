# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SFlow — macOS menu bar voice-to-text app."""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# --- Collect PyObjC frameworks ---
pyobjc_datas = []
pyobjc_binaries = []
pyobjc_hiddenimports = []

for pkg in ['AppKit', 'Foundation', 'Cocoa', 'Quartz', 'CoreFoundation',
            'objc', 'CoreText', 'ApplicationServices']:
    try:
        d, b, h = collect_all(pkg)
        pyobjc_datas += d
        pyobjc_binaries += b
        pyobjc_hiddenimports += h
    except Exception:
        pass

# --- Collect sounddevice portaudio binary ---
sounddevice_datas = collect_data_files('_sounddevice_data')

# --- Collect pynput backends ---
pynput_hidden = collect_submodules('pynput')

# --- Collect local STT stack (mlx-whisper + parakeet-mlx) ---
# Bundlea MLX (incl. los Metal .metallib), pesos-loaders y tokenizers para que
# los modelos locales corran DENTRO del .app. Si algun paquete no esta instalado
# (p.ej. build en Intel), se omite y el runtime cae a Groq.
mlx_datas, mlx_binaries, mlx_hidden = [], [], []
for pkg in ['mlx', 'mlx_whisper', 'parakeet_mlx', 'huggingface_hub', 'tiktoken', 'tiktoken_ext']:
    try:
        d, b, h = collect_all(pkg)
        mlx_datas += d
        mlx_binaries += b
        mlx_hidden += h
    except Exception:
        pass

# --- Data files ---
datas = [
    ('logo_small.png', '.'),
    ('logo.png', '.'),
    ('assets/fonts', 'assets/fonts'),   # Instrument Serif + Inter (offline)
    ('assets/icons', 'assets/icons'),   # Lucide SVGs (offline)
]
datas += sounddevice_datas
datas += pyobjc_datas
datas += mlx_datas

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=pyobjc_binaries + mlx_binaries,
    datas=datas,
    hiddenimports=[
        # PyObjC
        *pyobjc_hiddenimports,
        # pynput
        *pynput_hidden,
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        # PyQt6
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtSvg',          # Lucide SVG rendering (ui/icons.py)
        'PyQt6.QtSvgWidgets',
        # sounddevice
        '_sounddevice',
        'sounddevice',
        '_cffi_backend',
        # groq + httpx
        'groq',
        'httpx',
        'httpcore',
        'h11',
        'anyio',
        'sniffio',
        'certifi',
        'idna',
        # numpy
        'numpy',
        # dotenv
        'dotenv',
        # SFlow internals (explicit so PyInstaller picks them up)
        'core.transcriber',
        'core.transcriber_groq',
        'core.transcriber_local',
        'core.llm_cleanup',
        'core.context',
        'core.dictionary',
        'core.smart_commands',
        'core.command_mode',
        'core.hotkey',
        'core.recorder',
        'core.clipboard',
        'ui.pill_widget',
        'ui.audio_visualizer',
        'ui.red_dot_indicator',
        'core.secrets',
        'core.substitutions',
        'core.transcriber_parakeet',
        'core.permissions',
        'core.onboarding',
        'core.error_messages',
        'ui.onboarding_wizard',
        'ui.components',
        'ui.icons',
        # Local STT stack (auto-descubierto por collect_all arriba)
        *mlx_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        # NOTA: 'unittest'/'test' NO se excluyen — numba (dep de mlx-whisper y de
        # librosa/parakeet) los importa en runtime; excluirlos rompe ambos motores.
        # NOTA: el stack MLX (mlx, mlx_whisper, parakeet_mlx, librosa, numba, scipy,
        # soundfile, soxr, audioread, pooch, tiktoken, regex, llvmlite) YA NO se
        # excluye: se bundlea via collect_all (arriba) para que los modelos locales
        # corran dentro del .app. Verificado 12-jul-2026: ninguno importa torch en
        # runtime, asi que torch/torchaudio siguen fuera (ahorra ~2GB).
        'sklearn',
        'scikit-learn',
        'pandas',
        'matplotlib',
        'torch',
        'torchaudio',
        'sympy',
        'networkx',
        'moonshine',
        'moonshine_voice',
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
    [],
    exclude_binaries=True,
    name='SFlow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SFlow',
)

app = BUNDLE(
    coll,
    name='SFlow.app',
    icon='SFlow.icns',
    bundle_identifier='so.saasfactory.sflow',
    info_plist={
        'LSUIElement': True,
        'NSMicrophoneUsageDescription':
            'SFlow necesita acceso al microfono para transcribir voz.',
        'NSAppleEventsUsageDescription':
            'SFlow usa AppleScript para pegar texto en otras aplicaciones.',
        'CFBundleDisplayName': 'SFlow',
        'CFBundleName': 'SFlow',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSApplicationCategoryType': 'public.app-category.productivity',
        'NSHighResolutionCapable': True,
    },
)

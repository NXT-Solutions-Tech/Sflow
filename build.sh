#!/bin/bash
# build.sh — Build SFlow.app from source (one shot)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== SFlow Build ==="
echo ""

# --- Step 1: Generate .icns if missing ---
echo "[1/5] Icono..."
if [ ! -f "SFlow.icns" ]; then
    ICONSET="SFlow.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 64 128 256 512; do
        sips -z $size $size logo.png --out "$ICONSET/icon_${size}x${size}.png" > /dev/null 2>&1
        double=$((size * 2))
        sips -z $double $double logo.png --out "$ICONSET/icon_${size}x${size}@2x.png" > /dev/null 2>&1
    done
    iconutil -c icns "$ICONSET" -o SFlow.icns
    rm -rf "$ICONSET"
    echo "   SFlow.icns creado."
else
    echo "   SFlow.icns ya existe."
fi

# --- Step 2: Activate venv ---
echo "[2/5] Venv + PyInstaller..."
source venv/bin/activate
pip install pyinstaller --quiet 2>/dev/null

# --- Step 3: Clean ---
echo "[3/5] Limpiando builds anteriores..."
rm -rf build/ dist/

# --- Step 3b: Stage the bundled Parakeet weights (the offline guarantee) ---
# Populates models/<repo-basename> from the HF cache (or downloads once) so the
# spec's Tree can bundle it INTO the .app. The dir name MUST be the repo basename
# — that's exactly what core.models.bundle_dir() resolves under sys._MEIPASS.
echo "[3b/5] Preparando pesos de Parakeet (bundle offline)..."
python - <<'PY'
import os, sys
from huggingface_hub import snapshot_download
repo = "mlx-community/parakeet-tdt-0.6b-v3"
dest = os.path.join("models", repo.split("/")[-1])
os.makedirs("models", exist_ok=True)
try:
    path = snapshot_download(repo, local_dir=dest)
    print("   staged:", path)
except Exception as e:
    print("   ADVERTENCIA: no se pudo preparar Parakeet (%s). El .app NO tendra "
          "el motor offline garantizado; se descargara en primer uso." % e)
    sys.exit(0)  # no bloquea el build; el runtime cae a descarga/Groq
PY

# --- Step 4: Build ---
echo "[4/5] Construyendo .app (esto toma ~1-2 min)..."
pyinstaller sflow.spec --noconfirm 2>&1 | tail -5

# --- Step 5: Sign ---
echo "[5/5] Firmando..."
codesign --force --deep --sign - dist/SFlow.app 2>/dev/null
codesign --verify --deep --strict dist/SFlow.app 2>/dev/null && echo "   Firma OK." || echo "   Firma: warning (puede funcionar igual)."

echo ""
echo "=== BUILD COMPLETO ==="
echo ""
echo "  Archivo:   $(pwd)/dist/SFlow.app"
echo "  Tamano:    $(du -sh dist/SFlow.app | cut -f1)"
echo ""
echo "  Para instalar:"
echo "    ditto dist/SFlow.app /Applications/SFlow.app"
echo ""
echo "  IMPORTANTE: Usar 'ditto' (no 'cp -r') para preservar metadata del bundle."
echo ""

# Nota: NO hacemos `open dist/` — deja una ventana de Finder abierta que crea
# .DS_Store y hace fallar el `rm -rf dist/` del siguiente build (Directory not empty).

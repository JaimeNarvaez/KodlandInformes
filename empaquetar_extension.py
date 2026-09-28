# -*- coding: utf-8 -*-
"""
Genera el .zip de la extensión para repartirla (se instala con "Cargar
extensión sin empaquetar"; ver extension/INSTRUCCIONES.txt).

Antes de empaquetar comprueba que la extensión está al día con los cursos,
textos y banners (sincronizar_extension.py) y que el generador de JavaScript
sigue dando lo mismo que el de Python (pruebas/comparar_generadores.py). Si
algo falla, no genera nada.

El .zip queda en dist/Kodland Informes <versión>.zip (dist/ no se sube al repo).

Uso:  py -3 empaquetar_extension.py
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
EXT = BASE / "extension"
DIST = BASE / "dist"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    for paso in (["sincronizar_extension.py", "--comprobar"], ["pruebas/comparar_generadores.py"]):
        r = subprocess.run([sys.executable, str(BASE / paso[0]), *paso[1:]], cwd=BASE)
        if r.returncode != 0:
            print(f"\nNo se empaqueta: falló {' '.join(paso)}")
            sys.exit(1)

    version = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))["version"]
    DIST.mkdir(exist_ok=True)
    destino = DIST / f"Kodland Informes {version}.zip"
    archivos = sorted(f for f in EXT.rglob("*") if f.is_file())
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for f in archivos:
            # dentro de una carpeta: al descomprimir queda todo junto
            z.write(f, Path("Kodland Informes") / f.relative_to(EXT))
    print(f"\nListo: {destino}  ({len(archivos)} archivos, {destino.stat().st_size // 1024} KB)")
    print("Envíalo junto con las instrucciones que van dentro (INSTRUCCIONES.txt).")


if __name__ == "__main__":
    main()

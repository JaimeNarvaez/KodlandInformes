# -*- coding: utf-8 -*-
"""
Instala el puente de Native Messaging en Windows (solo para tu usuario).

  1. Escribe com.kodland.informes.json con la ruta a puente_informes.bat y el
     ID de la extensión, que es la única autorizada a usar el puente.
  2. Lo registra en HKCU para Chrome y Edge. No necesita administrador.

Uso:  py -3 instalar_puente.py [ID_EXTENSION]
"""

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import winreg
except ImportError:
    print("Este instalador es solo para Windows.")
    sys.exit(1)

NOMBRE_HOST = "com.kodland.informes"
DIR_PUENTE = Path(__file__).resolve().parent
RUTA_BAT = DIR_PUENTE / "puente_informes.bat"
RUTA_MANIFEST = DIR_PUENTE / f"{NOMBRE_HOST}.json"
CLAVES_REGISTRO = {
    "Chrome": r"Software\Google\Chrome\NativeMessagingHosts",
    "Edge": r"Software\Microsoft\Edge\NativeMessagingHosts",
}


def main():
    ext_id = (sys.argv[1] if len(sys.argv) > 1 else input("  ID de la extension: ")).strip()
    if not re.fullmatch(r"[a-p]{32}", ext_id):
        print(f"\n[X] '{ext_id}' no parece un ID de extension (32 letras de la a a la p).")
        print("    Copialo de chrome://extensions, debajo de 'Kodland Informes'.")
        sys.exit(1)

    RUTA_MANIFEST.write_text(json.dumps({
        "name": NOMBRE_HOST,
        "description": "Puente local para generar informes de Kodland",
        "path": str(RUTA_BAT),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] Manifest escrito: {RUTA_MANIFEST}")

    ok = 0
    for navegador, base in CLAVES_REGISTRO.items():
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + "\\" + NOMBRE_HOST) as clave:
                winreg.SetValueEx(clave, None, 0, winreg.REG_SZ, str(RUTA_MANIFEST))
            print(f"[OK] Registrado para {navegador}")
            ok += 1
        except Exception as e:
            print(f"[!] No se pudo registrar para {navegador}: {e}")

    if ok:
        print("\n[LISTO] Recarga la extension en chrome://extensions y la pagina del alumno.")
    else:
        print("\n[X] No se pudo registrar en ningun navegador.")
        sys.exit(1)


if __name__ == "__main__":
    main()

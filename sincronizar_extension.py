# -*- coding: utf-8 -*-
"""
Copia a la extensión lo que comparte con el generador de Python.

La extensión genera los informes por su cuenta (sin Python), pero los textos,
los estilos y el contenido de los cursos tienen una sola fuente: la de aquí.
Este script los lleva a extension/:

  generar_reporte.UI y ESTILOS  ->  extension/informe/textos.js
  reportes/curso_*.json         ->  extension/cursos/es/
  reportes/pt/curso_*.json      ->  extension/cursos/pt/
  reportes/img/banner_*.png     ->  extension/img/
  lista de cursos por idioma    ->  extension/cursos/indice.json

Hay que ejecutarlo tras cambiar cualquiera de esos archivos (y luego recargar
la extensión en chrome://extensions). Con --comprobar no copia nada: solo dice
si la extensión está al día (sale con código 1 si no).

Uso:
  py -3 sincronizar_extension.py
  py -3 sincronizar_extension.py --comprobar
"""

import json
import sys
from pathlib import Path

import generar_reporte

BASE = Path(__file__).resolve().parent
EXT = BASE / "extension"
REPORTES = BASE / "reportes"


def contenido_esperado():
    """{ruta en extension/: bytes} con todo lo que debe haber allí."""
    archivos = {}
    textos = (
        "// GENERADO por sincronizar_extension.py a partir de generar_reporte.py.\n"
        "// No editar a mano: cambiar allí y volver a sincronizar.\n\n"
        "export const UI = " + json.dumps(generar_reporte.UI, ensure_ascii=False, indent=2) + ";\n\n"
        "export const ESTILOS = " + json.dumps(generar_reporte.ESTILOS, ensure_ascii=False) + ";\n"
    )
    archivos["informe/textos.js"] = textos.encode("utf-8")

    indice = {}
    for idioma, carpeta in (("es", REPORTES), ("pt", REPORTES / "pt")):
        slugs = []
        for f in sorted(carpeta.glob("curso_*.json")):
            slug = f.stem.replace("curso_", "")
            if not slug or slug.lower() == "example":
                continue
            slugs.append(slug)
            archivos[f"cursos/{idioma}/{f.name}"] = f.read_bytes()
        indice[idioma] = slugs
    archivos["cursos/indice.json"] = (json.dumps(indice, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    for f in sorted((REPORTES / "img").glob("banner_kodland*.png")):
        archivos[f"img/{f.name}"] = f.read_bytes()
    return archivos


def igual(ruta, datos):
    """Mismo contenido, sin contar los finales de línea (Git en Windows los
    cambia a CRLF al sacar los archivos del repo)."""
    if not ruta.exists():
        return False
    actual = ruta.read_bytes()
    if ruta.suffix == ".png":
        return actual == datos
    return actual.replace(b"\r\n", b"\n") == datos.replace(b"\r\n", b"\n")


def main():
    comprobar = "--comprobar" in sys.argv
    esperado = contenido_esperado()
    distintos = [r for r, datos in esperado.items() if not igual(EXT / r, datos)]
    # cursos o banners que ya no existen en la fuente
    sobrantes = [str(f.relative_to(EXT)).replace("\\", "/")
                 for carpeta in ("cursos", "img") if (EXT / carpeta).exists()
                 for f in (EXT / carpeta).rglob("*") if f.is_file()
                 and str(f.relative_to(EXT)).replace("\\", "/") not in esperado]

    if comprobar:
        for r in distintos:
            print(f"  desactualizado: extension/{r}")
        for r in sobrantes:
            print(f"  sobra:          extension/{r}")
        if distintos or sobrantes:
            print("La extensión no está al día: ejecuta  py -3 sincronizar_extension.py")
            sys.exit(1)
        print("La extensión está al día.")
        return

    for r in distintos:
        destino = EXT / r
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(esperado[r])
        print(f"  actualizado: extension/{r}")
    for r in sobrantes:
        (EXT / r).unlink()
        print(f"  borrado:     extension/{r}")
    print("Listo." if (distintos or sobrantes) else "Nada que cambiar: ya estaba al día.")
    if distintos or sobrantes:
        print("Recarga la extensión en chrome://extensions para que tome los cambios.")


if __name__ == "__main__":
    main()

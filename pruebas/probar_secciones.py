# -*- coding: utf-8 -*-
"""
Comprueba las secciones opcionales del informe de la extensión.

Por cada combinación de casillas verifica que:
  1. la sección aparece o desaparece según lo marcado;
  2. la carátula, la portada, la firma del tutor y el pie están SIEMPRE;
  3. ninguna hoja se desborda del A4 (que la firma quepa donde se pegue).

Necesita Node.js.  Uso:  py -3 pruebas/probar_secciones.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
A4 = 1123

CODIGO = """
import { buildHtml } from '%s';
import { readFileSync } from 'node:fs';
const d = JSON.parse(readFileSync(process.argv[2], 'utf8'));
console.log(JSON.stringify(buildHtml(d.curso, d.alumno, null, '', d.secciones)));
""" % (BASE / "extension" / "informe" / "generador.js").as_uri()


def html_con(curso, alumno, secciones):
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada.json"
        entrada.write_text(json.dumps({"curso": curso, "alumno": alumno,
                                       "secciones": secciones}, ensure_ascii=False),
                           encoding="utf-8")
        script = Path(tmp) / "correr.mjs"
        script.write_text(CODIGO, encoding="utf-8")
        r = subprocess.run(["node", str(script), str(entrada)], capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace"))
        sys.exit(1)
    return json.loads(r.stdout.decode("utf-8"))


def main():
    curso = json.loads((BASE / "reportes" / "curso_unity.json").read_text(encoding="utf-8"))
    n = len(curso["modulos"])
    ses = [{"fecha": f"M{i//4+1} L{i%4+1}", "estado": "presente"} for i in range(12)]
    alumno = {
        "alumno": "Alumno Prueba", "profesor": "Tutor",
        "pct": [90, 85, 80, 75, 70, 95, 88, 60, 55, 100][:n],
        "tareas": [(4, 5)] * n, "puntos": [(45, 50)] * n,
        "asistencia": {"asistidas": 11, "total": 12, "sesiones": ses},
        "datos": {},
    }

    # (etiqueta, secciones, marcas que deben estar, marcas que NO deben estar)
    T = "CALIFICACIONES Y ASISTENCIA"
    A = "ASISTENCIA A CLASES"
    M = "DETALLE POR MÓDULO"
    C = "CONSIDERACIONES FINALES"
    todo = {"notas": True, "asistencia": True, "modulos": True, "consideraciones": True}
    casos = [
        ("completo",            dict(todo),                              [T, A, M, C], []),
        ("sin notas",           dict(todo, notas=False),                 [A, M, C],    [T]),
        ("sin asistencia",      dict(todo, asistencia=False),            [T, M, C],    [A]),
        ("sin modulos",         dict(todo, modulos=False),               [T, A, C],    [M]),
        ("sin consideraciones", dict(todo, consideraciones=False),       [T, A, M],    [C]),
        ("solo lo obligatorio", {k: False for k in todo},                [],           [T, A, M, C]),
        ("sin notas ni asist.", dict(todo, notas=False, asistencia=False), [M, C],     [T, A]),
    ]

    from playwright.sync_api import sync_playwright
    fallos = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 900, "height": 1300})
        for etq, sec, deben, no_deben in casos:
            html = html_con(curso, alumno, sec)
            malos = [m for m in deben if m not in html] + \
                    [m for m in no_deben if m in html]
            # obligatorios: carátula, portada, firma y pie
            for marca in ('class="dbasicos"', ui_titulo(html), 'class="firmas"', 'class="pie"'):
                if marca not in html:
                    malos.append("FALTA " + marca)
            pg.set_content(html, wait_until="networkidle")
            datos = pg.evaluate("""() => [...document.querySelectorAll('.pagina')]
                .map(x => Math.round(x.getBoundingClientRect().height))""")
            rotas = [h for h in datos if h > A4 + 1]
            estado = "OK " if not malos and not rotas else "MAL"
            if malos or rotas:
                fallos += 1
            print("  %s  %-20s %d hojas%s%s" % (
                estado, etq, len(datos),
                "   problemas: " + ", ".join(malos) if malos else "",
                "   HOJAS ROTAS: %s" % rotas if rotas else ""))
        b.close()
    print()
    print("fallos: %d" % fallos)
    sys.exit(1 if fallos else 0)


def ui_titulo(html):
    return "REPORTE DE DESARROLLO" if "REPORTE DE DESARROLLO" in html else "RELATÓRIO DE DESENVOLVIMENTO"


if __name__ == "__main__":
    main()

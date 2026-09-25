# -*- coding: utf-8 -*-
"""
Comprueba que la extensión y Python hacen exactamente lo mismo:

  1. extension/informe/generador.js y generar_reporte.build_html dan el mismo
     HTML, carácter a carácter.
  2. extension/informe/datos.js y generar_reportes_grupo (kodland_datos.py)
     sacan los mismos datos de las mismas respuestas de la API: curso elegido,
     porcentajes, tareas, asistencia y carátula.

Están duplicados a propósito (la extensión no puede usar Python) y esta prueba
es lo que evita que se separen: hay que pasarla tras tocar cualquiera de los
dos. Necesita Node.js (https://nodejs.org).

Uso:  py -3 pruebas/comparar_generadores.py
"""

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import generar_reporte as g  # noqa: E402
import kodland_datos as kd  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def correr_node(codigo, datos):
    """Ejecuta un módulo de Node con `datos` (JSON) y devuelve lo que imprime."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada.json"
        entrada.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        script = Path(tmp) / "correr.mjs"
        script.write_text(codigo, encoding="utf-8")
        r = subprocess.run(["node", str(script), str(entrada)], capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace"))
        sys.exit(1)
    return json.loads(r.stdout.decode("utf-8"))


# --- 1. el HTML -------------------------------------------------------------

def casos_html():
    azar = random.Random(7)
    raros = 'Ana <b>"Lú" & O\'Neil</b>'
    for idioma, carpeta in (("es", BASE / "reportes"), ("pt", BASE / "reportes" / "pt")):
        for f in sorted(carpeta.glob("curso_*.json")):
            curso = json.loads(f.read_text(encoding="utf-8"))
            n = len(curso["modulos"])
            for k in range(4):
                pct = [azar.choice([0, 0, 2.5, 3.5, 49.5, 50, 69.5, 70, 88, 100, 101, -3,
                                    azar.uniform(0, 100)]) for _ in range(n)]
                alumno = {"alumno": raros if k == 1 else "María José Pérez",
                          "profesor": "" if k == 2 else "Tutor & Cía",
                          "pct": pct if k != 3 else [0] * n}
                if k in (0, 1):
                    alumno["idioma"] = idioma
                    alumno["tareas"] = [(azar.randint(0, 8), 8) for _ in range(n)]
                    alumno["puntos"] = [(azar.randint(0, 40), 40) for _ in range(n)]
                    ses = [{"fecha": f"M{i // 4 + 1} L{i % 4 + 1}",
                            "estado": azar.choice(["presente", "ausente", "justificada", "raro<x>"])}
                           for i in range(azar.randint(0, 12))]
                    alumno["asistencia"] = {"asistidas": sum(s["estado"] == "presente" for s in ses),
                                            "total": len(ses), "sesiones": ses}
                    alumno["datos"] = {"acudiente": "Madre <x>", "email": "", "telefono": 0,
                                       "pais": "Chile", "codigo_grupo": "COL1_LU-18",
                                       "tipo_grupo": "Grupo regular", "dia_hora": "Lunes 18:00"}
                altos = None
                if k == 1:
                    altos = [azar.randint(150, 420) for _ in range(n)]
                elif k == 2:
                    altos = [300] * max(0, n - 1)   # incompletas: se estima
                yield {"nombre": f"{idioma}/{f.name}#{k}", "curso": curso, "alumno": alumno,
                       "altos": altos,
                       "banner": g.banner_uri(alumno.get("idioma") or curso.get("idioma", "es"))}


def comparar_html():
    lista = list(casos_html())
    esperados = [g.build_html(c["curso"], c["alumno"], c["altos"]) for c in lista]
    modulo = (BASE / "extension" / "informe" / "generador.js").as_uri()
    obtenidos = correr_node(
        "import { readFileSync } from 'node:fs';\n"
        f"const {{ buildHtml }} = await import({json.dumps(modulo)});\n"
        "const casos = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify(casos.map(c => buildHtml(c.curso, c.alumno, c.altos, c.banner))));\n",
        lista)

    fallos = 0
    for c, esp, obt in zip(lista, esperados, obtenidos):
        if esp != obt:
            fallos += 1
            i = next((k for k, (a, b) in enumerate(zip(esp, obt)) if a != b), min(len(esp), len(obt)))
            print(f"DISTINTO {c['nombre']} en el carácter {i}:")
            print(f"   python: {esp[max(0, i - 60):i + 60]!r}")
            print(f"   js:     {obt[max(0, i - 60):i + 60]!r}")
            if fallos >= 5:
                break
    print(f"{len(lista)} casos de HTML, {fallos} distintos")
    return fallos


# --- 2. los datos -----------------------------------------------------------

def respuestas_simuladas(azar, idioma, variante):
    """Respuestas de la API con la forma real, para un alumno en un grupo."""
    sid, gid = "700001", "800001"
    titulos = {"es": "[2060]Desarrollador de juegos Roblox lvl2[2026]", "pt": "[88]Python Pro[2026]"}
    estados = ["TASK_CHECKED", "TASK_ON_CHECK", "TASK_NOT_SUBMITTED", "TASK_NOT_GRADED", None]
    mods, lid = [], 9000
    for n in range(1, 11):
        lecciones = []
        for l in range(1, 5):
            lid += 1
            lecciones.append({"lesson_id": lid, "lesson_number": l,
                              "attendance_status": azar.choice([2, 2, 1, 0, None])})
        mods.append({"module_number": n, "module_current_grade": azar.randint(0, 40) if n < 7 else 0,
                     "module_max_grade": 40, "lessons_data": lecciones})
    azar.shuffle(mods)   # el orden de la API no está garantizado
    r = {
        f"/student_groups/{gid}/get_general_info_for_group_backoffice_page": {"status": 200, "cuerpo": {
            "course": {"title": "[1]Curso inventado[2026]" if variante == "sin_curso" else titulos[idioma]},
            "group_teacher": {"full_name": "Tutora Ñandú"},
            "passed_lessons_count": 0 if variante == "sin_empezar" else 24,
            "group_start_time": "2026-10-05 18:00:00",
            "group_kind": {"title": "[8] Grupo regular, 14 estudiantes, 90 minutos"},
            "group_is_premium": variante == "premium",
            "group_graduated": variante == "terminado",
            "group_schedule": [{"day": 2, "time": "16:00"}, {"day": 4, "time": "16:00"}],
            "group_timezone": {"offset_utc": "UTC-05:00"}}},
        f"/student_groups/{gid}/get_students_main_data": {"status": 200, "cuerpo": [
            {"main_info": {"student_id": 1, "full_name": "Otro", "status": "active"}, "progress_info": []},
            {"main_info": {"student_id": int(sid), "full_name": "Kimberly",
                           "status": "expelled" if variante == "baja" else "active",
                           "email": "k@correo.com"},
             "progress_info": mods}]},
    }
    if variante != "sin_familia":
        r[f"/students/{sid}/get_general_info_for_student_backoffice_page/"] = {"status": 200, "cuerpo": {
            "student_full_name": "Kimberly Gómez Díaz", "parent_name": "Rosa Díaz",
            "parent_phone": "+573001112233", "parent_email": "rosa@correo.com",
            "client_country": "Colombia"}}
    for m in mods:
        for l in m["lessons_data"]:
            for tipo in ("class", "homework"):
                if azar.random() < 0.9:
                    r[f"/students/{sid}/lesson/{l['lesson_id']}/get_progress_for_{tipo}_tasks/"] = {
                        "status": 200, "cuerpo": [
                            {"task_max_grade": azar.choice([0, 10, 10]),
                             "task_status_key": azar.choice(estados)}
                            for _ in range(azar.randint(0, 3))]}
    return sid, {"codigo": "COL9_MA-16", "url": f"{kd.BASE}/groups/{gid}"}, r


def datos_python(sid, grupo, resp, idioma):
    """Lo que generar_reportes_grupo le pasa a build_html (sin hacer el PDF)."""
    capturado = {}

    def capturar(curso, alumno, altos=None):
        capturado.setdefault("curso", curso.get("curso"))
        capturado.setdefault("alumno", alumno)
        raise RuntimeError("capturado")   # corta antes de hacer el PDF

    class Nada:   # navegador de mentira: aquí no se hace ningún PDF
        def __getattr__(self, _):
            return Nada()

        def __call__(self, *a, **k):
            return Nada()

    original, g.build_html = g.build_html, capturar
    registro, kd.log = kd.log, (lambda msg: None)
    try:
        kd.generar_reportes_grupo(None, None, grupo, Nada(), sid,
                                  api=lambda ruta: resp.get(ruta) or {"status": 404, "cuerpo": None},
                                  idioma=idioma)
    finally:
        g.build_html, kd.log = original, registro
    return capturado


def comparar_datos():
    azar = random.Random(11)
    lista = []
    for idioma in ("es", "pt"):
        for variante in ("normal", "baja", "sin_familia", "premium", "sin_empezar", "sin_curso",
                         "terminado"):
            sid, grupo, resp = respuestas_simuladas(azar, idioma, variante)
            py = datos_python(sid, grupo, resp, idioma)
            lista.append({"nombre": f"{idioma}/{variante}", "sid": sid, "idioma": idioma,
                          "grupo": {"gid": grupo["url"].rsplit("/", 1)[1], "codigo": grupo["codigo"]},
                          "resp": resp,
                          "python": {"curso": py.get("curso"), "alumno": py.get("alumno")}})
    # generar_reportes_grupo deja creada la carpeta de salida: se quita si quedó vacía
    salida = BASE / "reportes" / "salida" / "COL9_MA-16_desarrollo"
    if salida.exists() and not any(salida.iterdir()):
        salida.rmdir()

    modulo = (BASE / "extension" / "informe" / "datos.js").as_uri()
    cursos = (BASE / "extension" / "cursos").as_posix()
    obtenidos = correr_node(
        "import { readFileSync } from 'node:fs';\n"
        f"const {{ informeDeGrupo }} = await import({json.dumps(modulo)});\n"
        f"const dir = {json.dumps(cursos)};\n"
        "const slugs = JSON.parse(readFileSync(dir + '/indice.json', 'utf8'));\n"
        "const cargar = async (slug, idi) => JSON.parse(readFileSync(`${dir}/${idi}/curso_${slug}.json`, 'utf8'));\n"
        "const casos = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "const out = [];\n"
        "for (const c of casos) {\n"
        "  const r = await informeDeGrupo(c.resp, c.sid, c.grupo, c.idioma, slugs, cargar);\n"
        "  out.push({curso: r.curso ? r.curso.curso : null, alumno: r.alumno || null});\n"
        "}\n"
        "process.stdout.write(JSON.stringify(out));\n",
        lista)

    fallos = 0
    for c, obt in zip(lista, obtenidos):
        esp = json.loads(json.dumps(c["python"]))   # tuplas -> listas, como en JS
        if esp != obt:
            fallos += 1
            print(f"DATOS DISTINTOS {c['nombre']}:")
            ae, ao = esp.get("alumno") or {}, obt.get("alumno") or {}
            for k in sorted(set(ae) | set(ao)):
                if ae.get(k) != ao.get(k):
                    print(f"   {k}: python={json.dumps(ae.get(k), ensure_ascii=False)[:160]}")
                    print(f"   {' ' * len(k)}  js    ={json.dumps(ao.get(k), ensure_ascii=False)[:160]}")
            if esp.get("curso") != obt.get("curso"):
                print(f"   curso: python={esp.get('curso')} js={obt.get('curso')}")
    print(f"{len(lista)} escenarios de datos, {fallos} distintos")
    return fallos


def comparar_grupos():
    """Qué grupos de la ficha llevan informe: solo aquellos en que el alumno
    sigue activo (grupos_de_lista en Python, gruposDeLista en la extensión)."""
    lista = [{"group_id": 1, "group_title": "COL1_LU-18", "status": "active", "course_title": "[1]Unity[x]"},
             {"group_id": 2, "group_title": "COL2_MA-16", "status": "expelled", "course_title": "[2]Roblox"},
             {"group_id": 3, "group_title": "COL3_MI-17", "status": "ACTIVE", "course_title": ""},
             {"group_id": 4, "group_title": "", "course_title": "[4]Scratch"},
             {"group_title": "sin id", "status": "active"}, "basura"]
    registro, kd.log = kd.log, (lambda msg: None)
    try:
        py = [g["codigo"] for g in kd.grupos_de_lista(lista)]
    finally:
        kd.log = registro
    modulo = (BASE / "extension" / "informe" / "datos.js").as_uri()
    js = correr_node(
        "import { readFileSync } from 'node:fs';\n"
        f"const {{ gruposDeLista }} = await import({json.dumps(modulo)});\n"
        "const lista = JSON.parse(readFileSync(process.argv[2], 'utf8'));\n"
        "process.stdout.write(JSON.stringify(gruposDeLista(lista).filter(g => g.activo).map(g => g.codigo)));\n",
        lista)
    ok = py == js
    print(f"grupos con informe: python={py} js={js} -> {'iguales' if ok else 'DISTINTOS'}")
    return 0 if ok else 1


def main():
    fallos = comparar_html() + comparar_datos() + comparar_grupos()
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()

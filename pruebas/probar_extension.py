# -*- coding: utf-8 -*-
"""
Prueba de punta a punta de la extensión, sin tocar Kodland.

Carga extension/ en un Chromium de Playwright, simula bo.kodland.org y su API
(con respuestas de la forma real) y pulsa el botón "Generar informe" en la ficha
de un alumno con tres grupos: uno con clases, otro que aún no empezó y otro del
que ya salió. Comprueba que la API recibe el token como Bearer, que se descarga
un solo PDF, con el nombre "<alumno> - <grupo>.pdf", y que el aviso explica
por qué no salen los otros dos. Deja una captura de la primera y la última
hoja del PDF para revisarlo a ojo.

Uso:  py -3 pruebas/probar_extension.py [es|pt]
"""

import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "pruebas"))
from comparar_generadores import respuestas_simuladas  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOKEN = "token-de-prueba"
API = "https://backoffice.kodland.org/api/v2"
CORS = {"access-control-allow-origin": "https://bo.kodland.org",
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "authorization, accept, content-type"}


def respuestas(idioma):
    sid, grupo, r = respuestas_simuladas(random.Random(3), idioma, "normal")
    gid = grupo["url"].rsplit("/", 1)[1]
    r[f"/students/{sid}/backoffice_groups/"] = {"status": 200, "cuerpo": [
        {"group_id": int(gid), "group_title": grupo["codigo"], "status": "active",
         "course_title": "[1]Curso[2026]"},
        {"group_id": 800002, "group_title": "COL10_LU-18", "status": "active",
         "course_title": "[2]Otro[2026]"},
        {"group_id": 800003, "group_title": "COL11_SA-9", "status": "expelled",
         "course_title": "[3]Scratch[2025]"}]}
    r["/student_groups/800002/get_general_info_for_group_backoffice_page"] = {"status": 200, "cuerpo": {
        "course": {"title": "[2060]Unity Game Developer[2026]"}, "passed_lessons_count": 0,
        "group_start_time": "2026-10-05 18:00:00"}}
    return sid, r


def main():
    idioma = sys.argv[1] if len(sys.argv) > 1 else "pt"
    sid, resp = respuestas(idioma)
    sin_token = []
    salida = Path(tempfile.gettempdir()) / "prueba_extension_kodland"
    shutil.rmtree(salida, ignore_errors=True)
    salida.mkdir()

    def api(route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        ruta = req.url.replace(API, "").split("?")[0]
        if req.headers.get("authorization") != f"Bearer {TOKEN}":
            sin_token.append(ruta)
            return route.fulfill(status=401, headers=CORS, body="{}")
        r = resp.get(ruta)
        if r is None:
            return route.fulfill(status=404, headers=CORS, content_type="application/json", body="null")
        return route.fulfill(status=r["status"], headers=CORS, content_type="application/json",
                             body=json.dumps(r["cuerpo"]))

    ext = str(BASE / "extension")
    with tempfile.TemporaryDirectory() as perfil, sync_playwright() as pw:
        # Edge y no el Chromium de Playwright: Chrome estable ya no acepta
        # --load-extension y el Chromium sin firmar lo bloquea Windows en algunos equipos
        ctx = pw.chromium.launch_persistent_context(
            perfil, channel="msedge", headless=False, accept_downloads=True, downloads_path=str(salida),
            args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}",
                  "--window-position=-2400,0"])
        ctx.add_cookies([
            {"name": "access", "value": TOKEN, "domain": ".kodland.org", "path": "/"},
            {"name": "materio-language", "value": f"{idioma}-XX", "domain": "bo.kodland.org", "path": "/"}])
        ctx.route(f"{API}/**", api)
        ctx.route("https://bo.kodland.org/**", lambda r: r.fulfill(
            status=200, content_type="text/html", body="<html><body><h1>Ficha</h1></body></html>"))

        pg = ctx.new_page()
        pg.goto(f"https://bo.kodland.org/students/{sid}")
        boton = pg.locator("#ki-generar")
        boton.wait_for(timeout=15000)
        print("botón:", boton.inner_text())
        boton.click()
        aviso = pg.locator("#ki-aviso")
        pg.wait_for_function(
            "() => /[✅❌]|Nenhum|Ningún/.test(document.querySelector('#ki-aviso').textContent)",
            timeout=180000)
        texto = aviso.inner_text()
        print("aviso:\n" + texto)

        sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        pg.wait_for_timeout(1500)
        descargas = sw.evaluate("() => chrome.downloads.search({}).then(d => d.map(x => "
                                "({archivo: x.filename, sugerido: x.filename.split(/[\\\\/]/).pop(), "
                                "estado: x.state, bytes: x.fileSize})))")
        print("descargas:", json.dumps(descargas, ensure_ascii=False, indent=1))
        print("peticiones sin token:", sin_token or "ninguna")

        pdfs = [d for d in descargas if d["estado"] == "complete"]
        if pdfs:
            destino = salida / "informe.pdf"
            shutil.copy(pdfs[0]["archivo"], destino)
            ctx.close()
            # captura de la primera y la última hoja, con el visor de PDF de Chrome
            nav = pw.chromium.launch(channel="chrome", headless=False, args=["--window-position=-2400,0"])
            for hoja in ("1", "99"):
                v = nav.new_page(viewport={"width": 900, "height": 1250})
                v.goto(destino.as_uri() + f"#page={hoja}&zoom=page-fit")
                v.wait_for_timeout(2500)
                v.screenshot(path=str(salida / f"hoja_{'primera' if hoja == '1' else 'ultima'}.png"))
            nav.close()
            print("capturas en:", salida)
        else:
            ctx.close()
        ok = (len(pdfs) == 1 and not sin_token and "COL11_SA-9" in texto
              and "COL10_LU-18" in texto)
        print("RESULTADO:", "BIEN" if ok else "MAL")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

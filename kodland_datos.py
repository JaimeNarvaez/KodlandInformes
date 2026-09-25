# -*- coding: utf-8 -*-
"""
Capa de datos: lo necesario para sacar de Kodland lo que lleva el informe.

Cubre el inicio de sesión, la lista de grupos del profesor, las llamadas a la
API v2 del backoffice y la recolección del progreso de cada alumno.

Comparte el perfil de Chrome y la sesión con el proyecto KodlandFaster
(carpeta ~/.kodland_calificador), así que si ya iniciaste sesión allí, aquí no
te la vuelve a pedir.
"""

import datetime as dt
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Falta Playwright. Instálalo con:  py -3 -m pip install playwright")
    sys.exit(1)

BASE = "https://bo.kodland.org"
DIR_PERFIL = Path.home() / ".kodland_calificador" / "perfil_chrome"
RUTA_CONFIG = Path(__file__).resolve().parent / "config.json"
RUTA_CONFIG_EJEMPLO = Path(__file__).resolve().parent / "config.example.json"
PAGINA_PRINCIPAL = None


def _contable(t):
    """La tarea cuenta si tiene puntos posibles (excluye 'no se evalúa')."""
    return (t.get("task_max_grade") or 0) > 0 and t.get("task_status_key") != "TASK_NOT_GRADED"


def _enviada(t):
    """Enviada = el alumno la entregó (revisada o pendiente), no 'no enviada'."""
    return t.get("task_status_key") not in (None, "TASK_NOT_SUBMITTED")


def contar_tareas(*listas):
    """Cuenta (enviadas, total) sobre listas de tareas (clase y/o deberes)."""
    env = tot = 0
    for lst in listas:
        for t in (lst or []):
            if _contable(t):
                tot += 1
                if _enviada(t):
                    env += 1
    return env, tot

URL_PROFES = None  # config.json o --profesor-id; si no, se detecta al iniciar sesión

DIR_BASE = Path(__file__).resolve().parent

RUTA_SESION = Path.home() / ".kodland_calificador" / "sesion.json"

DIR_DEBUG = DIR_BASE / "depuracion"

JS_GRUPOS = r"""
() => {
  const rexL = /[MМ](\d+)\.?\s*L(\d+)/i;  // M latina o М cirílica
  const enlaces = [];
  for (const a of document.querySelectorAll("a[href*='/groups/']")) {
    const url = (a.href || '').split('?')[0];
    if (!/\/groups\/\d+$/.test(url)) continue;
    const t = (a.textContent || '').trim().replace(/\s+/g, ' ');
    if (!t) continue;
    const r = a.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    enlaces.push({ url: url, texto: t, top: r.top, bottom: r.bottom, left: r.left, el: a });
  }
  const lecciones = [];
  const estados = [];
  for (const el of document.querySelectorAll('a, span, div, td, p, button')) {
    const t = (el.textContent || '').trim();
    if (!t || t.length > 120) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const m = t.match(rexL);
    if (m) lecciones.push({ mod: +m[1], lec: +m[2], top: r.top, bottom: r.bottom, area: r.width * r.height });
    if (/^activo$/i.test(t)) estados.push({ top: r.top, bottom: r.bottom });
  }
  const solapa = (a, b) => Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 4;
  const vistos = {};
  const filas = [];
  for (const e of enlaces) {
    if (rexL.test(e.texto)) continue;  // es el enlace de la lección, no el del código
    if (vistos[e.url]) continue;
    vistos[e.url] = true;
    let mejor = null;
    for (const l of lecciones) {
      if (!solapa(e, l)) continue;
      if (!mejor || l.area < mejor.area) mejor = l;
    }
    const act = estados.some(s => solapa(e, s));
    const fila = e.el.closest('tr') || e.el.closest("[class*='row']") || e.el.parentElement;
    const texto = fila ? (fila.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 140) : '';
    filas.push({
      codigo: e.texto,
      url: e.url,
      mod: mejor ? mejor.mod : null,
      lec: mejor ? mejor.lec : null,
      activo: act,
      texto: texto,
      hay_estados: estados.length > 0
    });
  }
  return filas;
}
"""

JS_RANGO = r"""
() => {
  const rex = /^\s*(\d+)\s*[-–]\s*(\d+)\s*(?:de|of)\s*(\d+)\s*$/i;
  let mejor = null, len = 1e9, total = null;
  for (const el of document.querySelectorAll('body *')) {
    const t = (el.textContent || '').trim();
    const m = t.match(rex);
    if (m && t.length < len) { mejor = t; len = t.length; total = parseInt(m[3], 10); }
  }
  return { rango: mejor, total: total };
}
"""

JS_SIGUIENTE = r"""
() => {
  const rex = /^\s*(\d+)\s*[-–]\s*(\d+)\s*(?:de|of)\s*(\d+)\s*$/i;
  let lab = null, len = 1e9, total = null;
  for (const el of document.querySelectorAll('body *')) {
    const t = (el.textContent || '').trim();
    const m = t.match(rex);
    if (m && t.length < len) { lab = el; len = t.length; total = parseInt(m[3], 10); }
  }
  if (!lab) return { ok: false, total: null, rango: null };
  const r = lab.getBoundingClientRect();
  let cont = lab;
  for (let i = 0; i < 4 && cont.parentElement; i++) cont = cont.parentElement;

  const recoger = (sel, exigirPointer) => {
    const res = [];
    for (const el of cont.querySelectorAll(sel)) {
      const b = el.getBoundingClientRect();
      if (b.width < 14 || b.width > 80 || b.height < 14 || b.height > 80) continue;
      if (b.left <= r.right - 5) continue;                      // a la derecha del rango
      if (b.bottom < r.top - 30 || b.top > r.bottom + 30) continue;  // misma línea
      if (exigirPointer && getComputedStyle(el).cursor !== 'pointer') continue;
      res.push({ el: el, x: b.left, area: b.width * b.height });
    }
    return res;
  };
  let navs = recoger("button, a, [role='button']", false);
  if (!navs.length) navs = recoger('*', true);
  if (!navs.length) return { ok: false, total: total, rango: lab.textContent.trim() };

  navs.sort((a, b) => a.x - b.x);
  const grupos = [];
  for (const n of navs) {
    const g = grupos.find(g => Math.abs(g.x - n.x) < 8);
    if (g) { if (n.area < g.area) { g.el = n.el; g.area = n.area; } }
    else grupos.push({ x: n.x, el: n.el, area: n.area });
  }
  const idx = grupos.length >= 3 ? grupos.length - 2 : grupos.length - 1;
  const objetivo = grupos[idx].el;
  const rango = lab.textContent.trim();
  for (const tipo of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    objetivo.dispatchEvent(new MouseEvent(tipo, { bubbles: true, cancelable: true, view: window }));
  }
  return { ok: true, total: total, rango: rango, botones: grupos.length };
}
"""

def ahora():
    return dt.datetime.now().strftime("%H:%M:%S")

# que un símbolo (✓, ✗, tildes) nunca tumbe el proceso si la consola no es UTF-8
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(errors="replace")
    except Exception:
        pass

def log(msg):
    print(f"[{ahora()}] {msg}", flush=True)

def dump_debug(page, nombre):
    """Guarda captura y HTML para poder diagnosticar problemas después."""
    try:
        DIR_DEBUG.mkdir(parents=True, exist_ok=True)
        marca = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = DIR_DEBUG / f"{marca}_{re.sub(r'[^A-Za-z0-9_-]', '_', nombre)[:60]}"
        page.screenshot(path=str(base) + ".png", full_page=True)
        Path(str(base) + ".html").write_text(page.content(), encoding="utf-8")
        log(f"   (depuración guardada en {base}.png)")
    except Exception:
        pass

def restaurar_sesion(ctx):
    """Reinyecta la sesión guardada (COOKIES) para no iniciar sesión de nuevo.

    La sesión de Kodland vive en una COOKIE de sesión, que Chrome borra al cerrar
    el navegador (por eso pedía login cada vez, incluso con el perfil persistente).
    Aquí volvemos a poner esas cookies al arrancar, con caducidad, así inicias
    sesión una vez y las próximas veces entra solo. Devuelve True si restauró algo.
    """
    try:
        if not RUTA_SESION.exists():
            return False
        datos = json.loads(RUTA_SESION.read_text(encoding="utf-8"))
    except Exception:
        return False
    hecho = False

    limpias = []
    for c in (datos.get("cookies") or []):
        try:
            cc = {"name": c["name"], "value": c["value"],
                  "domain": c["domain"], "path": c.get("path", "/")}
        except Exception:
            continue
        if c.get("httpOnly"):
            cc["httpOnly"] = True
        if c.get("secure"):
            cc["secure"] = True
        if c.get("sameSite") in ("Strict", "Lax", "None"):
            cc["sameSite"] = c["sameSite"]
        exp = c.get("expires")
        cc["expires"] = exp if (isinstance(exp, (int, float)) and exp > 0) else (time.time() + 30 * 24 * 3600)
        limpias.append(cc)
    if limpias:
        try:
            ctx.add_cookies(limpias)
            hecho = True
        except Exception:
            for cc in limpias:  # si alguna falla, añadir el resto una por una
                try:
                    ctx.add_cookies([cc]); hecho = True
                except Exception:
                    pass

    # el storage no trae la sesión, pero lo restauramos por si acaso (no estorba)
    ss = json.dumps(datos.get("session") or {}, ensure_ascii=False)
    ls = json.dumps(datos.get("local") or {}, ensure_ascii=False)
    if ss != "{}" or ls != "{}":
        script = (
            "(() => { try {"
            " if (location.hostname !== 'bo.kodland.org') return;"
            " var S = " + ss + "; for (var k in S) { if (sessionStorage.getItem(k)===null) sessionStorage.setItem(k, S[k]); }"
            " var L = " + ls + "; for (var k in L) { if (localStorage.getItem(k)===null) localStorage.setItem(k, L[k]); }"
            " } catch (e) {} })();"
        )
        try:
            ctx.add_init_script(script); hecho = True
        except Exception:
            pass
    return hecho

def guardar_sesion(page):
    """Guarda las cookies (y el storage) de la sesión para reutilizarla la próxima vez."""
    try:
        if "bo.kodland.org" not in (page.url or ""):
            return
        cookies = page.context.cookies()   # incluye las httpOnly de sesión
        storage = page.evaluate(
            "() => {"
            " var s={}, l={};"
            " for (var i=0;i<sessionStorage.length;i++){var k=sessionStorage.key(i); s[k]=sessionStorage.getItem(k);}"
            " for (var i=0;i<localStorage.length;i++){var k=localStorage.key(i); l[k]=localStorage.getItem(k);}"
            " return {session:s, local:l};"
            "}"
        )
        datos = {"cookies": cookies,
                 "session": storage.get("session", {}),
                 "local": storage.get("local", {})}
        RUTA_SESION.parent.mkdir(parents=True, exist_ok=True)
        RUTA_SESION.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

JS_ENLACE_PROFESOR = """() => {
  const a = document.querySelector('a.app-logo[href^="/teachers/"]')
         || document.querySelector('aside a[href^="/teachers/"], nav a[href^="/teachers/"]');
  return a ? a.getAttribute('href') : '';
}"""

def _panel_listo(page):
    """True si se ven los grupos del panel. Sin ID de profesor configurado, lo
    saca del logo del menú lateral (enlaza a /teachers/<ID> en todas las
    páginas cuando hay sesión) y abre ese panel."""
    global URL_PROFES
    if URL_PROFES is None:
        m = re.search(r"/teachers/(\d+)", page.evaluate(JS_ENLACE_PROFESOR) or "")
        if not m:
            return False
        URL_PROFES = f"{BASE}/teachers/{m.group(1)}"
        log(f"ID de profesor detectado: {m.group(1)}")
        page.goto(URL_PROFES, wait_until="domcontentloaded")
        time.sleep(3)
    return page.locator("a[href*='/groups/']").count() > 0

def esperar_sesion(page):
    """Va al panel de profesores; si hace falta login, espera a que el usuario lo haga."""
    page.goto(URL_PROFES or BASE, wait_until="domcontentloaded")
    time.sleep(3)
    if _panel_listo(page):
        log("Sesión lista (no hizo falta iniciar sesión de nuevo).")
        guardar_sesion(page)
        return
    print()
    print("=" * 62)
    print("  No veo tus grupos todavía.")
    print("  Si aparece la página de login, inicia sesión en la ventana")
    print("  de Chrome. El script continuará solo al detectar tus grupos.")
    print("=" * 62)
    print()
    limite = time.time() + 600  # 10 minutos para loguearse
    while time.time() < limite:
        time.sleep(5)
        try:
            if _panel_listo(page):
                log("Sesión detectada, continuamos.")
                guardar_sesion(page)   # guardarla para no re-loguear la próxima vez
                time.sleep(1)
                return
            # si el login ya terminó y quedó en otra página del backoffice,
            # volvemos al panel; nunca recargamos mientras se está logueando
            u = page.url
            host = urlparse(u).netloc.lower()
            if (URL_PROFES and host == "bo.kodland.org" and "login" not in u.lower()
                    and "/teachers/" not in u):
                page.goto(URL_PROFES, wait_until="domcontentloaded")
        except Exception:
            pass
    raise RuntimeError("No se detectó la sesión tras 10 minutos. Vuelve a ejecutar el script.")

def _elegir_opcion_numerica_maxima(page):
    """En un menú desplegable abierto, pulsa la opción numérica más alta."""
    ops = page.locator("mat-option, [role='option'], .v-overlay .v-list-item")
    candidato, valor = None, -1
    for i in range(ops.count()):
        o = ops.nth(i)
        try:
            if not o.is_visible():
                continue
            t = (o.inner_text() or "").strip()
        except Exception:
            continue
        if t.isdigit() and int(t) > valor:
            candidato, valor = o, int(t)
    if candidato:
        candidato.click()
        time.sleep(2)
        return True
    return False

def ampliar_paginador(page):
    """Intenta poner 'Elementos por página' en el valor máximo (50)."""
    # La tabla es un v-data-table de Vuetify: hay que esperar a que exista el pie
    try:
        page.locator(".v-data-table-footer").first.wait_for(state="visible", timeout=12000)
    except Exception:
        pass
    try:
        rango_antes = (page.evaluate(JS_RANGO) or {}).get("rango")
    except Exception:
        rango_antes = None
    # el selector de tamaño es un .v-select cuyo campo muestra solo un número
    try:
        selectores = [
            ".v-data-table-footer__items-per-page .v-select .v-field",
            ".v-data-table-footer .v-select .v-field",
            ".v-select .v-field",
        ]
        for sel in selectores:
            campos = page.locator(sel)
            for i in range(campos.count()):
                c = campos.nth(i)
                try:
                    if not c.is_visible():
                        continue
                    texto = (c.inner_text() or "").strip()
                    if not texto.isdigit():
                        continue
                    c.click()
                    time.sleep(1.0)
                    if _elegir_opcion_numerica_maxima(page):
                        # verificar que el rango cambió (p. ej. "1-10 de 49" → "1-49 de 49")
                        for _ in range(6):
                            time.sleep(1)
                            try:
                                r = (page.evaluate(JS_RANGO) or {}).get("rango")
                            except Exception:
                                r = None
                            if r and r != rango_antes:
                                return True
                        return True
                    page.keyboard.press("Escape")
                except Exception:
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
            if campos.count():
                break  # ya probamos los campos numéricos del selector más específico
    except Exception:
        pass

    intentos = [
        "mat-paginator mat-select",
        ".mat-mdc-paginator mat-select",
        "mat-paginator select",
        ".mat-mdc-paginator select",
    ]
    # selects nativos primero
    for sel in intentos:
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        el = loc.first
        try:
            if sel.endswith("select") and not sel.endswith("mat-select"):
                opciones = el.locator("option").all_inner_texts()
                numeros = [t.strip() for t in opciones if t.strip().isdigit()]
                if numeros:
                    el.select_option(label=max(numeros, key=int))
                    time.sleep(2)
                    return True
            else:
                el.click()
                time.sleep(0.8)
                ops = page.locator("mat-option, [role='option']")
                mejor, valor = None, -1
                for i in range(ops.count()):
                    o = ops.nth(i)
                    if not o.is_visible():
                        continue
                    t = (o.inner_text() or "").strip()
                    if t.isdigit() and int(t) > valor:
                        mejor, valor = o, int(t)
                if mejor:
                    mejor.click()
                    time.sleep(2)
                    return True
                page.keyboard.press("Escape")
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
    # genérico: cualquier control cercano al texto "Elementos por página"
    try:
        et = page.get_by_text(re.compile("elementos por p|items? per page|por p[aá]gina", re.I))
        if et.count():
            caja = et.first.bounding_box()
            combos = page.locator("select, mat-select, [role='combobox'], [role='listbox']")
            mejor, dist = None, 1e9
            for i in range(combos.count()):
                c = combos.nth(i)
                try:
                    b = c.bounding_box()
                except Exception:
                    continue
                if not b or not caja:
                    continue
                d = abs(b["y"] - caja["y"]) + abs(b["x"] - (caja["x"] + caja["width"]))
                if d < dist:
                    mejor, dist = c, d
            if mejor and dist < 400:
                tag = mejor.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    opciones = mejor.locator("option").all_inner_texts()
                    numeros = [t.strip() for t in opciones if t.strip().isdigit()]
                    if numeros:
                        mejor.select_option(label=max(numeros, key=int))
                        time.sleep(2)
                        return True
                else:
                    mejor.click()
                    time.sleep(0.8)
                    ops = page.locator("mat-option, [role='option'], li")
                    candidato, valor = None, -1
                    for i in range(ops.count()):
                        o = ops.nth(i)
                        try:
                            if not o.is_visible():
                                continue
                            t = (o.inner_text() or "").strip()
                        except Exception:
                            continue
                        if t.isdigit() and int(t) > valor:
                            candidato, valor = o, int(t)
                    if candidato:
                        candidato.click()
                        time.sleep(2)
                        return True
                    page.keyboard.press("Escape")
    except Exception:
        pass
    return False

def _mejor_version(a, b):
    """Combina dos lecturas de la misma fila, prefiriendo la que tiene lección."""
    if (a["mod"] is None) != (b["mod"] is None):
        elegido = a if a["mod"] is not None else b
    else:
        elegido = a if len(a.get("texto") or "") >= len(b.get("texto") or "") else b
    elegido = dict(elegido)
    elegido["activo"] = bool(a["activo"] or b["activo"])
    return elegido

def escanear_pagina(page, acumulado, max_seg=9):
    """Escanea la página actual repetidamente hasta que los datos se estabilicen.

    Las celdas de la tabla se rellenan en diferido, así que una sola lectura
    suele llegar antes de tiempo. Devuelve True si se vio la columna de estado.
    """
    quieto = 0
    hay_estados = False
    fin = time.time() + max_seg
    while time.time() < fin:
        cambio = False
        for g in page.evaluate(JS_GRUPOS):
            hay_estados = hay_estados or g.get("hay_estados", False)
            antes = acumulado.get(g["url"])
            nuevo = g if antes is None else _mejor_version(antes, g)
            if antes != nuevo:
                acumulado[g["url"]] = nuevo
                cambio = True
        if cambio:
            quieto = 0
        else:
            quieto += 1
            if quieto >= 2:
                break
        time.sleep(1.0)
    return hay_estados

def listar_grupos(page):
    """Recorre el paginador y devuelve la lista completa de grupos."""
    if ampliar_paginador(page):
        log("Paginador ajustado al máximo de elementos por página.")
    else:
        log("No pude ajustar el paginador; recorreré las páginas con la flecha.")

    acumulado = {}
    total_esperado = None
    hay_estados = False
    for _pagina in range(40):
        time.sleep(1.2)
        hay_estados = escanear_pagina(page, acumulado) or hay_estados
        info = page.evaluate(JS_RANGO)
        if info.get("total"):
            total_esperado = info["total"]
        if total_esperado and len(acumulado) >= total_esperado:
            break
        paso = page.evaluate(JS_SIGUIENTE)
        if not paso.get("ok"):
            break
        time.sleep(2)
        despues = page.evaluate(JS_RANGO)
        if despues.get("rango") == paso.get("rango"):
            break  # el rango no cambió: era la última página

    grupos = list(acumulado.values())
    if grupos and not hay_estados:
        log("⚠ No vi la columna de estado 'Activo' en la tabla; asumiré todos activos.")
        for g in grupos:
            g["activo"] = True
    if total_esperado:
        log(f"Grupos leídos: {len(grupos)} de {total_esperado} según el paginador.")
        if len(grupos) < total_esperado:
            log("⚠ Faltaron grupos por leer; guardo depuración para ajustar el script.")
            dump_debug(page, "paginacion_incompleta")
    # si la mayoría quedó sin lección, guardamos el panel para poder analizarlo
    sin_lec = sum(1 for g in grupos if g["mod"] is None)
    if grupos and sin_lec > len(grupos) * 0.6:
        log("(guardo una copia del panel en 'depuracion' para análisis)")
        dump_debug(page, "panel_grupos")
    return grupos

API_BASE_V2 = "https://backoffice.kodland.org/api/v2"

CAPTURA_API = {"progreso": None, "tarea": None, "auth": None, "urls": []}

REX_API_PROGRESO = re.compile(r"/students/(\d+)/get_progress_by_task/(\d+)/")

REX_API_TAREA = re.compile(r"/api/v\d+/tasks/(\d+)/(?:\?|$)")

def instalar_captura(pagina):
    """Escucha las llamadas API que hace la propia página de Kodland."""
    def al_responder(resp):
        try:
            u = resp.url
            try:
                if resp.request.resource_type in ("xhr", "fetch"):
                    reg = CAPTURA_API["urls"]
                    reg.append(f"{resp.status} {resp.request.method} {u[:140]}")
                    if len(reg) > 40:
                        del reg[: len(reg) - 40]
            except Exception:
                pass
            m = REX_API_PROGRESO.search(u)
            if m and resp.status == 200:
                CAPTURA_API["progreso"] = {
                    "student": int(m.group(1)), "task": int(m.group(2)),
                    "resp": resp, "base": u.split("/students/")[0],
                }
                return
            m = REX_API_TAREA.search(u)
            if m and resp.status == 200:
                CAPTURA_API["tarea"] = {
                    "task": int(m.group(1)), "resp": resp,
                    "base": u[: u.index("/tasks/")],
                }
        except Exception:
            pass

    def al_pedir(req):
        try:
            if CAPTURA_API["auth"] is None and "/api/" in req.url:
                h = req.headers.get("authorization")
                if h:
                    CAPTURA_API["auth"] = h
        except Exception:
            pass

    try:
        pagina.on("response", al_responder)
        pagina.on("request", al_pedir)
    except Exception:
        pass

def api_llamar(pagina, base, ruta, metodo="GET", datos=None):
    """Llama a la API v2 desde el contexto de la página (misma sesión/cookies)."""
    js = """
    async (args) => {
      const cab = {'Accept': 'application/json'};
      const m = document.cookie.match(/csrftoken=([^;]+)/);
      if (m) cab['X-CSRFToken'] = m[1];
      if (args.auth) cab['Authorization'] = args.auth;
      if (args.datos) cab['Content-Type'] = 'application/json';
      try {
        const r = await fetch(args.url, {
          method: args.metodo, credentials: 'include', headers: cab,
          body: args.datos ? JSON.stringify(args.datos) : undefined,
        });
        let cuerpo = null;
        try { cuerpo = await r.json(); } catch (e) {}
        return {status: r.status, cuerpo: cuerpo};
      } catch (e) {
        return {status: -1, cuerpo: String(e)};
      }
    }
    """
    try:
        return pagina.evaluate(js, {"url": base + ruta, "metodo": metodo,
                                    "datos": datos, "auth": CAPTURA_API.get("auth")})
    except Exception as e:
        return {"status": -2, "cuerpo": str(e)}

def api_llamar_multi(paginas, ruta, metodo="GET", datos=None, bases=None):
    """Prueba la llamada desde varias páginas y bases hasta que responda.

    Devuelve (respuesta, [intentos "status base+ruta"]).
    """
    if bases is None:
        bases = []
        for cap in (CAPTURA_API.get("progreso"), CAPTURA_API.get("tarea")):
            if cap and cap.get("base") and cap["base"] not in bases:
                bases.append(cap["base"])
        if API_BASE_V2 not in bases:
            bases.append(API_BASE_V2)
    intentos = []
    for pagina in paginas:
        if pagina is None:
            continue
        for base in bases:
            r = api_llamar(pagina, base, ruta, metodo, datos)
            intentos.append(f"{r.get('status')} {base}{ruta}")
            if r.get("status") in (200, 201):
                return r, intentos
    return {"status": -3, "cuerpo": None}, intentos

def _primer_valor(dic, claves, _hondo=0):
    """Primer valor no vacío entre varias claves candidatas.

    La API no siempre usa el mismo nombre para el mismo dato (y a veces lo
    anida), así que se prueban varios nombres y se baja un par de niveles.
    """
    if not isinstance(dic, dict) or _hondo > 2:
        return ""
    for k in claves:
        v = dic.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    for v in dic.values():
        if isinstance(v, dict):
            r = _primer_valor(v, claves, _hondo + 1)
            if r:
                return r
    return ""

DIAS = {
    "es": {1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves", 5: "Viernes",
           6: "Sábado", 7: "Domingo"},
    "pt": {1: "Segunda-feira", 2: "Terça-feira", 3: "Quarta-feira", 4: "Quinta-feira",
           5: "Sexta-feira", 6: "Sábado", 7: "Domingo"},
}
IDIOMAS = tuple(DIAS)   # idiomas en que se sabe hacer el informe

def idioma_informe(valor):
    """Idioma del informe a partir del de la página ("pt-BR", "es-ES", la cookie
    materio-language del backoffice). Lo que no se sepa hacer, en español."""
    corto = str(valor or "").strip().lower()[:2]
    return corto if corto in IDIOMAS else "es"

def idioma_de_sesion(ctx):
    """Idioma elegido en el backoffice, leído de su cookie materio-language."""
    try:
        for c in ctx.cookies("https://bo.kodland.org"):
            if c.get("name") == "materio-language":
                return idioma_informe(c.get("value"))
    except Exception:
        pass
    return "es"

def _tipo_grupo(info_grupo):
    """group_kind.title viene como "[8] Grupo regular, 14 estudiantes, 90
    minutos": se deja "Grupo regular" (y "premium" si lo es)."""
    kind = info_grupo.get("group_kind")
    titulo = kind.get("title", "") if isinstance(kind, dict) else str(kind or "")
    tipo = re.sub(r"^\[\d+\]\s*", "", titulo).split(",")[0].strip()
    if tipo and info_grupo.get("group_is_premium"):
        tipo += " (premium)"
    return tipo

def _dia_hora(info_grupo, idioma="es"):
    """group_schedule es [{"day": 2, "time": "16:00", …}] con day 1 = lunes (el
    código COL…_MA-16 lo confirma), en la zona horaria del grupo."""
    horario = info_grupo.get("group_schedule")
    if not isinstance(horario, list):
        return ""
    dias = DIAS.get(idioma, DIAS["es"])
    partes = [f"{dias.get(h.get('day'), '')} {h.get('time') or ''}".strip()
              for h in horario if isinstance(h, dict)]
    texto = (" e " if idioma == "pt" else " y ").join(p for p in partes if p)
    zona = info_grupo.get("group_timezone")
    offset = zona.get("offset_utc") if isinstance(zona, dict) else ""
    return f"{texto} ({offset})" if texto and offset else texto

def datos_caratula(main, info_grupo, respaldo, nombre, codigo, info_alumno=None, idioma="es"):
    """Datos básicos del estudiante para la carátula del reporte.

    La familia (acudiente, teléfono, país) no viene en la lista de alumnos del
    grupo (`main`) sino en los datos generales del alumno (`info_alumno`, de
    get_general_info_for_student_backoffice_page); el horario y el tipo, en los
    datos del grupo. Todo se completa con reportes/datos_<codigo>.json, que
    manda sobre lo que venga de la API (ahí se corrige lo que falte o salga
    mal). Ese JSON admite una clave "_grupo" con lo común a todo el grupo y una
    clave por nombre de alumno con lo suyo.
    """
    alumno = info_alumno if isinstance(info_alumno, dict) else {}
    d = {
        "acudiente": _primer_valor(alumno, ("parent_name",)) or _primer_valor(
            main, ("parent_name", "parent_full_name", "representative_name", "parent")),
        "email": _primer_valor(alumno, ("parent_email",)) or _primer_valor(
            main, ("email", "student_email", "parent_email", "login")),
        "telefono": _primer_valor(alumno, ("parent_phone", "student_phone")) or _primer_valor(
            main, ("phone", "phone_number", "parent_phone", "telephone")),
        "pais": _primer_valor(alumno, ("client_country",)) or _primer_valor(
            main, ("country", "country_name")),
        "codigo_grupo": codigo,
        "tipo_grupo": _tipo_grupo(info_grupo),
        "dia_hora": _dia_hora(info_grupo, idioma),
    }
    manual = dict(respaldo.get("_grupo", {}) or {})
    manual.update(respaldo.get(nombre, {}) or {})
    d.update({k: v for k, v in manual.items() if str(v or "").strip()})
    return d

def _sin_tildes(t):
    """Minúsculas y sin tildes, para comparar nombres como los escribe uno."""
    t = unicodedata.normalize("NFKD", str(t or "")).lower()
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def coincide_alumno(nombre, busqueda):
    """True si cada palabra de la búsqueda aparece en el nombre (sin importar
    orden, mayúsculas ni tildes): "perez juan" encuentra a "Juan Pérez Gómez"."""
    palabras = _sin_tildes(nombre).split()
    return all(any(w.startswith(b) for w in palabras) for b in _sin_tildes(busqueda).split())


def id_de_alumno(texto):
    """ID numérico si `texto` es un ID o la URL de la ficha del alumno
    (https://bo.kodland.org/students/1346293); si es un nombre, ""."""
    t = str(texto or "").strip()
    m = re.search(r"/students/(\d+)", t) or re.fullmatch(r"(\d+)", t)
    return m.group(1) if m else ""


def _id_grupo(grupo):
    m = re.search(r"/groups/(\d+)", grupo.get("url", "") or "")
    return m.group(1) if m else ""


def grupos_desde_ficha(ctx, page, sid):
    """Grupos del alumno `sid`, según su ficha (bo.kodland.org/students/<sid>).

    No usa el panel de tutor ni un ID de profesor: sirve para cualquier cuenta
    del backoffice que pueda ver al alumno (tutor, ventas / ISM…). Abre la ficha,
    espera a que haya sesión (si hace falta, a que se inicie) y pide
    /students/<sid>/backoffice_groups/, la misma lista que carga la propia
    ficha: group_id, group_title (el código), status y course_title de cada
    grupo en que está o estuvo inscrito."""
    url = f"{BASE}/students/{sid}"
    llamadas = []

    def al_responder(resp):
        try:
            if (resp.request.resource_type in ("xhr", "fetch") and "/api/" in resp.url
                    and resp.status == 200):
                llamadas.append(resp.url)
        except Exception:
            pass

    page.on("response", al_responder)
    try:
        page.goto(url, wait_until="domcontentloaded")
        avisado = False
        limite = time.time() + 600  # 10 minutos para iniciar sesión
        while time.time() < limite:
            # page.wait_for_timeout y no time.sleep: la API síncrona de
            # Playwright solo entrega los eventos (y llena `llamadas`) mientras
            # se le habla
            page.wait_for_timeout(3000)
            u = page.url
            # en la ficha y con respuestas de la API: hay sesión
            if f"/students/{sid}" in u and "login" not in u.lower() and llamadas:
                break
            if not avisado:
                print()
                print("=" * 62)
                print("  Si aparece la página de login, inicia sesión en la ventana")
                print("  de Chrome. El script continuará solo al abrir la ficha.")
                print("=" * 62)
                print()
                avisado = True
            if (urlparse(u).netloc.lower() == "bo.kodland.org" and "login" not in u.lower()
                    and f"/students/{sid}" not in u):
                page.goto(url, wait_until="domcontentloaded")  # ya entró: volver a la ficha
        else:
            raise RuntimeError("No se abrió la ficha del alumno tras 10 minutos. "
                               "¿Tiene esta cuenta permiso para verlo?")
        guardar_sesion(page)
    finally:
        try:
            page.remove_listener("response", al_responder)
        except Exception:
            pass

    paginas = [p for p in ctx.pages] or [page]
    r, _ = api_llamar_multi(paginas, f"/students/{sid}/backoffice_groups/")
    if r.get("status") != 200 or not isinstance(r.get("cuerpo"), list):
        log(f"   no pude leer los grupos del alumno (status {r.get('status')})")
        dump_debug(page, f"ficha_alumno_{sid}")
        return []
    return grupos_de_lista(r["cuerpo"])

def grupos_de_lista(lista):
    """Convierte la respuesta de /students/<ID>/backoffice_groups/ en los
    grupos que espera generar_reportes_grupo.

    Solo los grupos en que el alumno sigue activo: `status` es el suyo en ese
    grupo, y los de cursos ya terminados o de los que salió vienen como
    "expelled" (o similar). Esos no llevan informe."""
    grupos = []
    for g in lista if isinstance(lista, list) else []:
        gid = g.get("group_id") if isinstance(g, dict) else None
        if not gid:
            continue
        codigo = str(g.get("group_title") or f"grupo_{gid}").strip()
        curso = re.sub(r"^\[\d+\]", "", g.get("course_title") or "").split("[")[0].strip()
        estado = str(g.get("status") or "").lower()
        if estado != "active":
            log(f" · {codigo}: {curso or 'curso ¿?'} → se omite (el alumno figura como «{estado or '¿?'}»)")
            continue
        log(f" · {codigo}: {curso or 'curso ¿?'}")
        grupos.append({"codigo": codigo, "url": f"{BASE}/groups/{gid}"})
    return grupos

def generar_reportes_grupo(ctx, page, grupo, pw, alumno="", api=None, idioma="es"):
    """Genera un 'Reporte de desarrollo' (PDF narrativo por módulo) por cada
    alumno inscrito del grupo, con % reales. Necesita reportes/curso_<slug>.json
    con el contenido del curso (ver curso.example.json). No califica.
    Con `alumno` solo genera el de quien coincida con ese nombre, o el de ese
    ID si es un número o la URL de su ficha.

    `api(ruta) -> {"status", "cuerpo"}` es de dónde salen los datos: por
    defecto, llamadas en vivo desde las páginas de `ctx`. Se puede pasar otra
    (respuestas ya guardadas, y entonces ctx y page sobran): así lo usa
    pruebas/comparar_generadores.py para cotejar con la extensión.

    `idioma` es el del informe ("es" o "pt"). El contenido del curso en otro
    idioma va en reportes/<idioma>/ con el mismo nombre de archivo; si falta,
    el informe sale entero en español para no mezclar idiomas."""
    sys.path.insert(0, str(DIR_BASE))
    import generar_reporte as grep
    import glob as _glob

    gid = _id_grupo(grupo)
    if not gid:
        log(f"   no pude leer el id del grupo ({grupo.get('url')})")
        return 0
    if api is None:
        paginas = [p for p in ctx.pages] or [page]
        def api(ruta):
            return api_llamar_multi(paginas, ruta)[0]

    # curso + tutor
    titulo, prof = "", ""
    r = api(f"/student_groups/{gid}/get_general_info_for_group_backoffice_page")
    info_grupo = r.get("cuerpo") if r.get("status") == 200 else None
    if not isinstance(info_grupo, dict):
        info_grupo = {}
    c = info_grupo.get("course") or {}
    titulo = c.get("title", "") or ""
    gt = info_grupo.get("group_teacher") or {}
    if isinstance(gt, dict):
        prof = gt.get("full_name") or ""

    # un grupo que aún no ha dado clase no tiene nada que informar: saldría
    # con todos los módulos al 0 % y "módulo del informe" en el último
    if info_grupo.get("passed_lessons_count") == 0:
        inicio = str(info_grupo.get("group_start_time") or "").split(" ")[0]
        log(f"   el grupo aún no ha empezado"
            f"{' (primera clase el ' + inicio + ')' if inicio else ''}: no hay informe que hacer")
        return 0
    if info_grupo.get("group_graduated") or info_grupo.get("group_is_archive"):
        log("   el grupo ya terminó: no hay informe que hacer")
        return 0

    # buscar el JSON de contenido del curso: todas las palabras del slug deben
    # aparecer en el título del curso; si varios encajan, gana el más específico
    # (más palabras). Así "roblox_2" gana a "roblox" para un grupo de Roblox 2.
    # Se separan letra-dígito ("lvl2" -> "lvl 2") para reconocer los niveles.
    def _pal(s):
        s = re.sub(r"([a-z])(\d)", r"\1 \2", s.lower())
        s = re.sub(r"(\d)([a-z])", r"\1 \2", s)
        return [w for w in re.split(r"[^a-z0-9]+", s) if w]
    palabras_txt = set(_pal(titulo))
    candidatos = []
    for rc in _glob.glob(str(DIR_BASE / "reportes" / "curso_*.json")):
        slug = Path(rc).stem.replace("curso_", "")
        if not slug or slug.lower() == "example":
            continue
        palabras_slug = _pal(slug)
        if palabras_slug and all(w in palabras_txt for w in palabras_slug):
            candidatos.append((len(palabras_slug), rc))
    ruta_curso = max(candidatos)[1] if candidatos else None
    if not ruta_curso:
        log(f"   no hay contenido para el curso «{titulo}». Crea "
            f"reportes/curso_<curso>.json (ver curso.example.json) y reintenta.")
        return 0
    if idioma != "es":
        traducido = DIR_BASE / "reportes" / idioma / Path(ruta_curso).name
        if traducido.exists():
            ruta_curso = str(traducido)
        else:
            log(f"   no hay reportes/{idioma}/{Path(ruta_curso).name}: el informe sale en español")
            idioma = "es"
    curso = json.loads(Path(ruta_curso).read_text(encoding="utf-8"))
    log(f"   curso: {curso.get('curso')} (contenido: {Path(ruta_curso).relative_to(DIR_BASE / 'reportes')}, "
        f"idioma {idioma})")

    r = api(f"/student_groups/{gid}/get_students_main_data")
    if r.get("status") != 200 or not isinstance(r.get("cuerpo"), list):
        log(f"   no pude leer los alumnos del grupo {gid} (status {r.get('status')})")
        return 0
    alumnos = r["cuerpo"]
    sid_buscado = id_de_alumno(alumno)
    if sid_buscado:
        alumnos = [s for s in alumnos
                   if str((s.get("main_info") or {}).get("student_id")) == sid_buscado]
        if not alumnos:
            log(f"   el alumno {sid_buscado} no está en este grupo")
            return 0
    elif alumno:
        alumnos = [s for s in alumnos
                   if coincide_alumno((s.get("main_info") or {}).get("full_name"), alumno)]
        if not alumnos:
            log(f"   ningún alumno del grupo coincide con «{alumno}»")
            return 0

    codigo = grupo.get("codigo") or gid
    carpeta = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{codigo}_desarrollo")
    salida = DIR_BASE / "reportes" / "salida" / carpeta
    salida.mkdir(parents=True, exist_ok=True)

    # --- datos básicos de la carátula: backoffice + respaldo manual ---
    respaldo = {}
    ruta_resp = DIR_BASE / "reportes" / f"datos_{codigo}.json"
    if ruta_resp.exists():
        try:
            respaldo = json.loads(ruta_resp.read_text(encoding="utf-8"))
            log(f"   carátula: completando con {ruta_resp.name}")
        except Exception as e:
            log(f"   no pude leer {ruta_resp.name} ({e}); sigo sin él")
    # radiografía: solo los NOMBRES de los campos (no los datos de los alumnos),
    # para saber cómo se llaman de verdad y afinar datos_caratula sin adivinar.
    try:
        DIR_DEBUG.mkdir(parents=True, exist_ok=True)
        (DIR_DEBUG / f"campos_caratula_{codigo}.json").write_text(json.dumps(
            {"main_info": sorted((alumnos[0].get("main_info") or {}).keys()) if alumnos else [],
             "info_grupo": sorted(info_grupo.keys())},
            indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    nav = None
    for canal in ("chrome", "msedge", None):
        try:
            nav = pw.chromium.launch(channel=canal, headless=True) if canal else pw.chromium.launch(headless=True)
            break
        except Exception:
            nav = None
    if nav is None:
        log("   no pude abrir un navegador headless para los PDF")
        return 0
    rpage = nav.new_page()

    ATT = {2: "presente", 1: "justificada", 0: "ausente"}
    hechos = omitidos = 0
    for s in alumnos:
        main = s.get("main_info", {}) or {}
        prog = s.get("progress_info", []) or []
        sid = main.get("student_id")
        nombre = main.get("full_name") or f"Alumno {sid}"
        # la familia y el nombre completo están en los datos generales del
        # alumno, no en la lista del grupo (que a veces trae solo el nombre)
        ri = api(f"/students/{sid}/get_general_info_for_student_backoffice_page/")
        info_alumno = ri.get("cuerpo") if ri.get("status") == 200 else None
        if isinstance(info_alumno, dict):
            completo = str(info_alumno.get("student_full_name") or "").strip()
            if len(completo.split()) > len(nombre.split()):
                nombre = completo
        # si se pidió a este alumno por su ID se hace aunque ya no esté activo
        # en el grupo (grupo terminado, cambio de horario); se avisa del estado
        if (main.get("status") or "").lower() != "active":
            if not sid_buscado:
                omitidos += 1
                continue
            log(f"   aviso: {nombre} figura como «{main.get('status')}» en este grupo")
        try:
            pct = grep.pct_por_modulo(prog)
            nrea = len(pct)
            mods_ord = sorted(prog, key=lambda mm: mm.get("module_number", 0))[:nrea]
            # puntos por módulo (ya combinados), tareas (clase+deberes) por lección,
            # y asistencia — todo para el documento combinado.
            puntos, tareas, ses = [], [], []
            for mm in mods_ord:
                puntos.append((mm.get("module_current_grade", 0) or 0, mm.get("module_max_grade", 0) or 0))
                env = tot = 0
                for l in mm.get("lessons_data", []):
                    lid = l.get("lesson_id")
                    rc = api(f"/students/{sid}/lesson/{lid}/get_progress_for_class_tasks/")
                    rh = api(f"/students/{sid}/lesson/{lid}/get_progress_for_homework_tasks/")
                    e, t = contar_tareas(rc.get("cuerpo") if rc.get("status") == 200 else None,
                                              rh.get("cuerpo") if rh.get("status") == 200 else None)
                    env += e
                    tot += t
                    st = l.get("attendance_status")
                    if st in ATT:
                        ses.append({"fecha": f"M{mm.get('module_number')} L{l.get('lesson_number')}",
                                    "estado": ATT[st]})
                tareas.append((env, tot))
            asis = {"asistidas": sum(1 for x in ses if x["estado"] == "presente"),
                    "total": len(ses), "sesiones": ses}
            alumno = {"alumno": nombre, "profesor": prof, "pct": pct, "idioma": idioma,
                      "puntos": puntos, "tareas": tareas, "asistencia": asis,
                      "datos": datos_caratula(main, info_grupo, respaldo, nombre, codigo,
                                              info_alumno, idioma)}
            html = grep.build_html(curso, alumno)
            base = "".join(ch for ch in nombre if ch.isalnum() or ch in " _-").strip() or "alumno"
            rpage.set_content(html, wait_until="networkidle")
            # ya renderizado se sabe lo que ocupa cada módulo: se rehace el
            # reparto con las medidas exactas para no dejar hojas a medias
            rpage.set_content(grep.build_html(curso, alumno, grep.altos_medidos(rpage)),
                              wait_until="networkidle")
            rpage.pdf(path=str(salida / (base + ".pdf")), format="A4",
                      print_background=True,
                      margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            hechos += 1
            log(f"   ✓ {nombre} ({nrea} módulos)")
        except Exception as e:
            log(f"   ✗ {nombre}: {e}")
    try:
        nav.close()
    except Exception:
        pass
    log(f"Reportes generados: {hechos} (omitidos por no inscritos: {omitidos}) en {salida}")
    return hechos

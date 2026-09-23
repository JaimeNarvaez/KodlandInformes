# -*- coding: utf-8 -*-
"""
Generador de informes de desarrollo de Kodland.

Abre el panel de profesores, lee el progreso real de cada alumno del grupo y
produce un PDF por alumno con el formato de Kodland: carátula con los datos
básicos, aprovechamiento por módulo, calificaciones y asistencia, detalle
módulo a módulo, y firma y sello al final.

Necesita el contenido del curso en reportes/curso_<curso>.json.

Uso:
  py -3 informes.py                       # el grupo más reciente
  py -3 informes.py --grupo COL12429      # un grupo concreto (o parte del código)
  py -3 informes.py --todos               # todos los grupos activos
  py -3 informes.py --alumno "Juan Perez" # un solo alumno (lo busca en todos los grupos)
  py -3 informes.py --alumno 1346293      # por su ID (o la URL de su ficha): un PDF
                                          # por cada grupo en que esté inscrito
  py -3 informes.py --grupo COL12429 --alumno Juan   # un alumno de un grupo concreto
  py -3 informes.py --paquete registros/paquete_1346293.json
      # datos ya reunidos por la extensión en el Chrome de quien la usa: no
      # abre navegador visible ni pide iniciar sesión (así lo usa ventas / ISM)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import kodland_datos as kd
from kodland_datos import (dump_debug, esperar_sesion, guardar_sesion, instalar_captura,
                           listar_grupos, log, restaurar_sesion, sync_playwright)


def leer_profesor_id(args):
    """ID de profesor: de --profesor-id o de config.json. Es opcional: si no
    está, se detecta en la página al iniciar sesión ("" = detectarlo)."""
    cfg = {}
    if kd.RUTA_CONFIG.exists():
        try:
            cfg = json.loads(kd.RUTA_CONFIG.read_text(encoding="utf-8"))
        except Exception as e:
            log(f"No pude leer config.json ({e}); uso --profesor-id si lo pasaste.")
    pid = str(args.profesor_id or cfg.get("profesor_id") or "").strip()
    return pid if pid.isdigit() else ""


def elegir_grupos(page, args):
    """Lista los grupos del panel y deja los que hay que procesar."""
    log("Cargando la lista de grupos…")
    grupos = listar_grupos(page)
    log(f"Grupos encontrados: {len(grupos)}")

    elegidos, ilegibles = [], 0
    for g in grupos:
        if g["mod"] is None:
            if len(g.get("texto") or "") < 25:
                ilegibles += 1
                log(f" · {g['codigo']}: no pude leer su fila → se omite")
            else:
                log(f" · {g['codigo']}: sin lección dada → se omite")
            continue
        if not g["activo"] and not args.incluir_no_activos:
            log(f" · {g['codigo']}: no está Activo → se omite")
            continue
        if args.grupo and args.grupo.upper() not in g["codigo"].upper():
            continue
        omitidos = [t.strip().upper() for t in args.omitir.split(",") if t.strip()]
        if any(t in g["codigo"].upper() for t in omitidos):
            log(f" · {g['codigo']}: excluido con --omitir")
            continue
        elegidos.append(g)

    if grupos and (ilegibles > len(grupos) / 2 or not elegidos):
        log("Casi nada quedó seleccionado; guardo depuración del panel por si hay que ajustar.")
        dump_debug(page, "panel_sin_seleccion")

    elegidos.reverse()  # primero los más recientes
    # con --alumno y sin --grupo no se sabe dónde está: se busca en todos
    if not args.todos and not args.grupo and not args.alumno:
        elegidos = elegidos[:1]
    return elegidos


class PlaywrightPerezoso:
    """Arranca Playwright solo si de verdad hay que hacer un PDF: arrancarlo y
    cerrarlo en seguida (grupos sin empezar) deja avisos de asyncio."""
    def __init__(self):
        self._pw = None

    @property
    def chromium(self):
        if self._pw is None:
            self._pw = sync_playwright().start()
        return self._pw.chromium

    def cerrar(self):
        if self._pw is not None:
            self._pw.stop()


def desde_paquete(ruta):
    """Genera los informes de un alumno con las respuestas de la API que reunió
    la extensión en la sesión de Chrome de quien la usa. Aquí no hay login ni
    navegador visible: solo un Chromium oculto para convertir a PDF.

    El paquete lleva datos de un menor: se borra al terminar."""
    ruta = Path(ruta)
    try:
        paquete = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"No pude leer el paquete {ruta}: {e}")
        sys.exit(1)
    sid = str(paquete.get("alumno") or "")
    respuestas = paquete.get("respuestas") or {}

    def api(r):
        return respuestas.get(r) or {"status": 404, "cuerpo": None}

    hechos = 0
    try:
        log(f"Alumno {sid}: datos recibidos de la extensión ({len(respuestas)} consultas).")
        lista = api(f"/students/{sid}/backoffice_groups/")
        if lista.get("status") != 200:
            log(f"No llegó la lista de grupos del alumno (status {lista.get('status')}). "
                f"¿Tiene tu cuenta permiso para ver su ficha?")
            return
        grupos = kd.grupos_de_lista(lista.get("cuerpo"))
        if not grupos:
            log("El alumno no tiene grupos.")
            return
        print()
        pw = PlaywrightPerezoso()
        try:
            for n, g in enumerate(grupos, 1):
                log(f"[{n}/{len(grupos)}] Grupo {g['codigo']}")
                try:
                    hechos += kd.generar_reportes_grupo(None, None, g, pw, sid, api=api) or 0
                except Exception as e:
                    log(f"   error en el grupo {g['codigo']}: {e}")
        finally:
            pw.cerrar()
        print()
        log(f"Listo. Informes generados: {hechos}")
    finally:
        try:
            ruta.unlink()
        except Exception:
            pass
    if hechos:
        salida = kd.DIR_BASE / "reportes" / "salida"
        log(f"Están en: {salida}")
        try:
            os.startfile(str(salida))   # abrir la carpeta para quien no la conoce
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Informes de desarrollo por alumno (Kodland)")
    ap.add_argument("--grupo", default="", help="código del grupo, o parte de él")
    ap.add_argument("--todos", action="store_true",
                    help="todos los grupos activos (por defecto sólo el más reciente)")
    ap.add_argument("--alumno", default="",
                    help="solo ese alumno: su ID, la URL de su ficha, o su nombre "
                         "(o parte, sin importar tildes)")
    ap.add_argument("--omitir", default="", help="códigos a excluir, separados por coma")
    ap.add_argument("--incluir-no-activos", action="store_true",
                    help="incluir también los grupos que no están Activos")
    ap.add_argument("--profesor-id", default="", help="tu ID de profesor (opcional: si falta, se detecta al iniciar sesión)")
    ap.add_argument("--lento", action="store_true", help="ir despacio, para ver qué hace")
    ap.add_argument("--paquete", default="",
                    help="JSON con los datos que reunió la extensión (no abre navegador)")
    args = ap.parse_args()

    if args.paquete:
        desde_paquete(args.paquete)
        return

    # por ID de alumno no se usa el panel de tutor: el ID de profesor sobra
    if not kd.id_de_alumno(args.alumno):
        pid = leer_profesor_id(args)
        if pid:
            kd.URL_PROFES = f"{kd.BASE}/teachers/{pid}"
        else:
            log("Sin ID de profesor configurado: lo detectaré al iniciar sesión.")
    kd.DIR_PERFIL.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = ultimo_error = None
        for canal in ("chrome", "msedge"):
            try:
                ctx = pw.chromium.launch_persistent_context(
                    str(kd.DIR_PERFIL),
                    channel=canal,
                    headless=False,
                    no_viewport=True,
                    args=["--start-maximized"],
                    slow_mo=250 if args.lento else 0,
                )
                log(f"Navegador iniciado ({canal}). Perfil: {kd.DIR_PERFIL}")
                break
            except Exception as e:
                ultimo_error = e
        if ctx is None:
            print(f"No pude iniciar Chrome ni Edge: {ultimo_error}")
            sys.exit(1)

        ctx.set_default_timeout(20000)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        kd.PAGINA_PRINCIPAL = page
        instalar_captura(page)
        try:
            ctx.on("page", instalar_captura)
        except Exception:
            pass

        if restaurar_sesion(ctx):
            log("Reutilizaré tu sesión anterior (si sigue válida).")

        hechos = 0
        try:
            sid = kd.id_de_alumno(args.alumno)
            if sid:
                # por ID todo sale de la ficha del alumno, nunca del panel de
                # tutor: así lo usan cuentas sin grupos propios (ventas / ISM)
                log(f"Abriendo la ficha del alumno {sid} para ver sus grupos…")
                elegidos = kd.grupos_desde_ficha(ctx, page, sid)
                if args.grupo:
                    elegidos = [g for g in elegidos
                                if args.grupo.upper() in g["codigo"].upper()]
            else:
                esperar_sesion(page)
                elegidos = elegir_grupos(page, args)
            if not elegidos:
                log("No quedó ningún grupo que procesar.")
                return
            log(f"Grupos a procesar: {len(elegidos)}")
            print()
            for n, g in enumerate(elegidos, 1):
                log(f"[{n}/{len(elegidos)}] Grupo {g['codigo']}")
                try:
                    hechos += kd.generar_reportes_grupo(ctx, page, g, pw, args.alumno) or 0
                except Exception as e:
                    log(f"   error en el grupo {g['codigo']}: {e}")
            print()
            log(f"Listo. Informes generados: {hechos}")
            log(f"Están en: {kd.DIR_BASE / 'reportes' / 'salida'}")
        finally:
            try:
                guardar_sesion(page)
            except Exception:
                pass
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()

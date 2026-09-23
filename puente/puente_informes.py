# -*- coding: utf-8 -*-
"""
Puente local (Native Messaging) entre la extensión de Chrome y los informes.

Chrome lanza este script y le habla por stdin/stdout con el protocolo de
Native Messaging (4 bytes de longitud + JSON UTF-8). La extensión manda el ID
del alumno y las respuestas de la API que ella misma reunió con la sesión del
navegador. El puente comprueba que el ID sea un número y que cada ruta sea una
de las que usa el informe, guarda el paquete en registros/ (no se sube al
repo; informes.py lo borra al terminar) y abre informe_extension.bat <ID> en una
ventana nueva. Nunca ejecuta rutas ni comandos que lleguen en el mensaje.

Todo lo que haya que contar va a puente.log: stdout es el canal con Chrome y
cualquier print lo rompería.
"""

import datetime
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

DIR_PUENTE = Path(__file__).resolve().parent
DIR_BASE = DIR_PUENTE.parent
BAT = DIR_PUENTE / "informe_extension.bat"
DIR_PAQUETES = DIR_BASE / "registros"
LOG = DIR_PUENTE / "puente.log"

# las únicas consultas que usa el informe (ver generar_reportes_grupo)
RUTAS_PERMITIDAS = re.compile(
    r"/students/\d+/(?:backoffice_groups|get_general_info_for_student_backoffice_page"
    r"|lesson/\d+/get_progress_for_(?:class|homework)_tasks)/"
    r"|/student_groups/\d+/(?:get_general_info_for_group_backoffice_page|get_students_main_data)")

CREATE_NEW_CONSOLE = 0x00000010   # ventana propia, visible, donde se ve el progreso


def log(texto):
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  {texto}\n")
    except Exception:
        pass


def leer_mensaje():
    """Un mensaje de Chrome, o None si cerró la conexión."""
    encabezado = sys.stdin.buffer.read(4)
    if len(encabezado) < 4:
        return None
    largo = struct.unpack("=I", encabezado)[0]
    cuerpo = sys.stdin.buffer.read(largo)
    if len(cuerpo) < largo:
        return None
    try:
        return json.loads(cuerpo.decode("utf-8"))
    except Exception as e:
        log(f"mensaje ilegible: {e}")
        return {}


def enviar_mensaje(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def generar_informe(alumno, respuestas):
    alumno = str(alumno or "")
    if not re.fullmatch(r"\d{1,12}", alumno):
        log(f"ID rechazado: {alumno!r}")
        return {"ok": False, "error": "ID de alumno no válido."}
    if not isinstance(respuestas, dict) or not respuestas:
        return {"ok": False, "error": "No llegaron los datos del alumno."}
    ajenas = [r for r in respuestas if not RUTAS_PERMITIDAS.fullmatch(str(r))]
    if ajenas:
        log(f"rutas rechazadas: {ajenas[:3]}")
        return {"ok": False, "error": "El paquete trae consultas que no son del informe."}
    if not BAT.is_file():
        log(f"no existe {BAT}")
        return {"ok": False, "error": f"no encuentro {BAT.name}"}
    try:
        DIR_PAQUETES.mkdir(parents=True, exist_ok=True)
        (DIR_PAQUETES / f"paquete_{alumno}.json").write_text(
            json.dumps({"alumno": alumno, "respuestas": respuestas}, ensure_ascii=False),
            encoding="utf-8")
        subprocess.Popen([str(BAT), alumno], cwd=str(DIR_BASE),
                         creationflags=CREATE_NEW_CONSOLE, close_fds=True)
        log(f"informe lanzado para el alumno {alumno} ({len(respuestas)} consultas)")
        return {"ok": True, "mensaje": f"Generando el informe del alumno {alumno}."}
    except Exception as e:
        log(f"error al lanzar el informe de {alumno}: {e}")
        return {"ok": False, "error": str(e)}


def main():
    while True:
        try:
            mensaje = leer_mensaje()
        except Exception as e:
            log(f"error leyendo: {e}")
            break
        if mensaje is None:
            break   # Chrome cerró la conexión
        mensaje = mensaje or {}
        respuesta = generar_informe(mensaje.get("alumno"), mensaje.get("respuestas"))
        try:
            enviar_mensaje(respuesta)
        except Exception as e:
            log(f"error respondiendo: {e}")
            break


if __name__ == "__main__":
    main()

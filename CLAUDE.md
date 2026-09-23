# KodlandInformes

Genera un **PDF por alumno** con su progreso en un curso de Kodland, para
entregar a las familias. Saca los datos reales del panel de profesores
(`bo.kodland.org`) y arma el documento en HTML, que convierte a PDF con
Playwright.

Salió de separar la parte de informes del proyecto **KodlandFaster** (el
calificador), que mezclaba demasiadas cosas. Aquí no se califica, no se comenta
con IA y no se toca WhatsApp: solo se leen datos y se produce el PDF.

## Ejecutar

```
py -3 informes.py                    # el grupo mas reciente
py -3 informes.py --grupo COL12429   # un grupo concreto (o parte del codigo)
py -3 informes.py --todos            # todos los grupos activos
py -3 informes.py --alumno "Juan"    # un solo alumno (sin --grupo, lo busca en todos)
py -3 informes.py --alumno 1346293   # por ID o URL de su ficha: un PDF por grupo
```

Con un ID, `--alumno` mira también los grupos no activos y genera el informe
aunque el alumno ya no figure como activo en alguno (curso terminado, cambio de
horario); con un nombre, solo grupos activos y alumnos activos.

Los `.bat` de la raíz hacen lo mismo con doble clic: `1 - Generar informes.bat`
(un grupo) y `2 - Informe de un alumno.bat` (un alumno; acepta el ID como
argumento, que es como lo llama la extensión).

Sin conectarse a la plataforma, útil para trabajar en el diseño:

```
py -3 generar_reporte.py --curso reportes/curso_unity.json --alumno "Nombre" \
   --profesor "Tutor" --pct 100,95,88,92,85,90,78,0,0,0
```

Los PDF salen en `reportes/salida/`. Única dependencia: **Playwright**
(`py -3 -m pip install playwright` + `py -3 -m playwright install chromium`).
Todo lo demás es librería estándar; conviene que siga así.

## Estructura

| Archivo | Qué hace |
|---|---|
| `informes.py` | CLI, arranque del navegador, sesión y elección de grupos |
| `kodland_datos.py` | Sesión, lista de grupos, API v2 y progreso por alumno |
| `generar_reporte.py` | Arma el HTML del informe y lo pasa a PDF |
| `reportes/curso_*.json` | Contenido de cada curso: módulos, aprendizajes, proyectos |
| `reportes/img/` | Banner de Kodland de la carátula |
| `extension/` | Extensión de Chrome: botón "Generar informe" en `/students/<ID>` |
| `puente/` | Host de Native Messaging: guarda el paquete de la extensión y abre `informe_extension.bat` |

El flujo es: `informes.py` abre Chrome con perfil persistente → `esperar_sesion`
→ `listar_grupos` → por cada grupo, `generar_reportes_grupo`, que consulta la
API v2 y llama a `generar_reporte.build_html`.

Con `--alumno <ID>` el flujo **no toca el panel de tutor ni el ID de
profesor**: `grupos_desde_ficha` abre `bo.kodland.org/students/<ID>` (sirve
también para esperar el login) y pide `/api/v2/students/<ID>/backoffice_groups/`,
la lista que carga la propia ficha: `group_id`, `group_title` (el código),
`status` y `course_title` de cada grupo. Así lo usa el equipo de ventas
(**ISM**), que no tiene cuenta de tutor. `--grupo` ahí solo filtra esos grupos.

## Sesión

El perfil de Chrome vive en `~/.kodland_calificador`, **compartido con
KodlandFaster**: la sesión iniciada en cualquiera de los dos sirve en el otro.
La primera vez hay que iniciar sesión a mano (el script espera).

El ID de profesor (`config.json` o `--profesor-id`) es **opcional**: si falta,
`_panel_listo` lo lee del logo del menú lateral, que en todas las páginas del
backoffice enlaza a `/teachers/<ID>` del usuario con sesión.

## Qué NO se sube al repo

`config.json` (ID de profesor), `reportes/datos_*.json` (nombres, correos y
teléfonos de alumnos menores), `reportes/salida/`, `depuracion/` y `registros/`.
Están en `.gitignore`; los `.example.json` sí se versionan. **Antes de commitear,
comprobar que no se cuela ninguno.**

## Trampas conocidas

- **`generar_reporte.py` está duplicado** en este repo y en KodlandFaster. Un
  arreglo del generador hay que llevarlo a los dos.
- **М cirílica (U+041C).** Los códigos de lección del panel usan М cirílica, no
  M latina (Kodland es rusa). El regex de `kodland_datos.py:67` acepta las dos:
  `/[MМ](\d+)\.?\s*L(\d+)/i`. Si algún día "no coincide un texto que se ve bien",
  sospechar siempre de homóglifos cirílicos (А В Е К М Н О Р С Т У Х).
- **El backoffice es Vuetify 3** y carga en diferido: las celdas de la tabla de
  grupos hay que re-escanear hasta que se estabilicen (`escanear_pagina`).
- **El reparto de hojas del informe va en dos pasadas.** Primero se renderiza,
  se mide con `altos_medidos()` lo que ocupa cada bloque de módulo, y se vuelve
  a armar el HTML con esas alturas para llenar cada hoja sin partir ninguna. Si
  se toca el CSS de `.mod`, hay que volver a comprobar que ninguna página se
  desborda (el A4 son 1123px de alto a 96dpi).
- Los campos de la carátula que la API no devuelve se completan con
  `reportes/datos_<grupo>.json`, que manda sobre la API. Tras la primera
  ejecución queda en `depuracion/campos_caratula_<grupo>.json` la lista de
  nombres de campo que devolvió la plataforma, para ajustarlo sin adivinar.

## Convenciones

- Todo en **español**: código, comentarios, mensajes de consola y documentación.
- Los commits van a nombre de **JaimeNarvaez <jaimeangel936@gmail.com>**, con
  mensajes en español y sin tildes, explicando el porqué del cambio. No añadir
  líneas de co-autoría ni firmas de herramientas.
- **Probar en local antes de subir nada.**

## Extensión de Chrome

Pone un botón **📄 Generar informe** abajo a la izquierda en la ficha del alumno
(abajo a la derecha está el panel de KodlandFaster). Pensada para ventas
(**ISM**): no necesita cuenta de tutor ni iniciar sesión en otro Chrome.

1. `boton-informe.js` **reúne los datos en la propia página**, con la sesión de
   quien la usa: la API pide el token de la cookie `access` como
   `Authorization: Bearer` (solo con cookies responde 401). Pide las mismas
   rutas que `generar_reportes_grupo`; si se cambian allí, hay que cambiarlas
   aquí y en `RUTAS_PERMITIDAS` del puente.
2. Las respuestas van por Native Messaging a `puente/puente_informes.py`, que
   valida el ID y cada ruta contra la lista blanca, guarda
   `registros/paquete_<ID>.json` y abre `puente/informe_extension.bat <ID>`.
3. Ese .bat corre `informes.py --paquete …`: `generar_reportes_grupo` lee de
   las respuestas (parámetro `api`) en vez de llamar en vivo, arma los PDF con
   un Chromium oculto, **borra el paquete** (datos de un menor) y abre la
   carpeta de salida.

El token nunca sale del navegador: al puente solo llegan respuestas.

Instalación, una vez por PC:
1. `chrome://extensions` → Modo de desarrollador → *Cargar extensión sin
   empaquetar* → carpeta `extension/`. Copiar su ID.
2. Doble clic en `puente/instalar_puente.bat` y pegar el ID. Registra
   `com.kodland.informes` en HKCU para Chrome y Edge.
3. Recargar la extensión y la página del alumno.

Si no conecta, mirar `puente/puente.log`. Si se carga la extensión desde otra
carpeta cambia su ID y hay que reinstalar el puente. Es un host distinto al
`com.kodland.puente` de KodlandFaster: pueden convivir.

Los grupos que aún no han dado clase (`passed_lessons_count == 0`) no generan
informe: saldrían con todos los módulos al 0 %.

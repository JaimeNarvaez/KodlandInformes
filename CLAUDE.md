# KodlandInformes

Genera un **PDF por alumno** con su progreso en un curso de Kodland, para
entregar a las familias. Saca los datos reales del panel (`bo.kodland.org`) y
arma el documento en HTML, que convierte a PDF.

Hay dos formas de usarlo, que producen el mismo informe:

- **La extensión de Chrome** (`extension/`): un botón en la ficha del alumno.
  No necesita Python ni nada instalado; es lo que usa ventas (**ISM**).
- **Los scripts de Python**: para tutores, por grupo o por alumno, desde la
  consola o los `.bat`.

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

Con un ID, `--alumno` solo hace informe de los grupos en que el alumno **sigue
activo**: los de cursos terminados o de los que salió vienen en su ficha con
otro `status` (`expelled`…) y se omiten, igual que los grupos graduados o
archivados y los que aún no empezaron. La extensión aplica la misma regla.

Los `.bat` de la raíz hacen lo mismo con doble clic: `1 - Generar informes.bat`
(un grupo) y `2 - Informe de un alumno.bat` (un alumno).

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
| `reportes/pt/curso_*.json` | El mismo contenido traducido al portugués (Brasil) |
| `reportes/img/` | Banner de la carátula (`banner_kodland.png` y `_pt.png`, el texto va en la imagen) |
| `extension/` | Extensión de Chrome que genera el informe sola (ver abajo) |
| `sincronizar_extension.py` | Copia a `extension/` textos, estilos, cursos y banners |
| `pruebas/comparar_generadores.py` | Comprueba que la extensión y Python dan el mismo HTML y datos |
| `pruebas/probar_extension.py` | Prueba de punta a punta de la extensión con Kodland simulado |

El flujo es: `informes.py` abre Chrome con perfil persistente → `esperar_sesion`
→ `listar_grupos` → por cada grupo, `generar_reportes_grupo`, que consulta la
API v2 y llama a `generar_reporte.build_html`.

Con `--alumno <ID>` el flujo **no toca el panel de tutor ni el ID de
profesor**: `grupos_desde_ficha` abre `bo.kodland.org/students/<ID>` (sirve
también para esperar el login) y pide `/api/v2/students/<ID>/backoffice_groups/`,
la lista que carga la propia ficha: `group_id`, `group_title` (el código),
`status` y `course_title` de cada grupo. Así lo usa el equipo de ventas
(**ISM**), que no tiene cuenta de tutor. `--grupo` ahí solo filtra esos grupos.

## Idioma

El informe sale en el idioma que tenga elegido la página de quien lo genera
(cookie `materio-language` del backoffice: `es-ES`, `pt-BR`…); lo que no sea
`es` ni `pt` sale en español. `--idioma es|pt` lo fuerza.

- Textos fijos: `UI` en `generar_reporte.py`. Días de la semana: `DIAS` en
  `kodland_datos.py`.
- Contenido del curso: `reportes/<idioma>/<mismo nombre>.json`. **Si se cambia
  un `curso_*.json`, hay que cambiar también su traducción.** Si falta la
  traducción, ese informe sale entero en español (no se mezclan idiomas).
- El banner lleva el texto dentro de la imagen: `banner_kodland_<idioma>.png`.
  La versión `pt` se hizo borrando el texto del original por difusión y
  escribiendo encima con Segoe UI Light.

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

- **No tocar KodlandFaster** (`Gehiner/KodlandFaster`, repo de otra persona):
  tiene su propia copia antigua de `generar_reporte.py`, pero los cambios de
  informes se quedan solo en este repo. No copiar archivos allí ni commitear.
- **El generador también está en JavaScript** (`extension/informe/`), porque la
  extensión no puede usar Python. Tras tocar `build_html`, `generar_reportes_grupo`
  o sus equivalentes JS, pasar `py -3 pruebas/comparar_generadores.py` (necesita
  Node). Tras tocar `UI`, `ESTILOS`, un `curso_*.json` o un banner, ejecutar
  `py -3 sincronizar_extension.py` y recargar la extensión.
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

Pone un botón **📄 Generar informe** (en portugués si la página lo está) abajo a
la izquierda en la ficha del alumno; abajo a la derecha está el panel de
KodlandFaster. No necesita Python, ni cuenta de tutor, ni iniciar sesión en
otro sitio: usa la sesión abierta de quien la usa.

1. `boton-informe.js` (en la página) **reúne las respuestas de la API**: la API
   pide el token de la cookie `access` como `Authorization: Bearer` (solo con
   cookies responde 401). Pide las mismas rutas que `generar_reportes_grupo`.
2. `background.js` saca los datos de cada informe (`informe/datos.js`), arma el
   HTML (`informe/generador.js`) y lo convierte a PDF con el propio Chrome:
   `chrome.debugger` + `Page.printToPDF` en una ventana minimizada, en las dos
   pasadas de siempre (render, medir `.mod`, rehacer). Mientras tanto Chrome
   muestra la barra de "está depurando este navegador": es normal.
3. Cada PDF se guarda con la ventana de **Guardar como**, que sugiere
   `<alumno> - <código del grupo>.pdf`. El aviso junto al botón dice qué
   grupos salieron y por qué no los demás (sin empezar, terminado…).

Los textos, estilos, cursos y banners **no se editan en `extension/`**: salen
de `generar_reporte.py` y `reportes/` con `sincronizar_extension.py`
(`--comprobar` dice si está al día). Los datos de familia que la API no trae
no se completan en la extensión (los `datos_<grupo>.json` son solo de Python).

Instalación, una vez por PC: `chrome://extensions` → Modo de desarrollador →
*Cargar extensión sin empaquetar* → carpeta `extension/`. Nada más.

`pruebas/probar_extension.py` la carga en **Edge** (Chrome estable ya no acepta
`--load-extension` y el Chromium de Playwright lo bloquea Windows en este
equipo) con Kodland simulado, pulsa el botón y revisa el PDF.

Los grupos que aún no han dado clase (`passed_lessons_count == 0`) no generan
informe: saldrían con todos los módulos al 0 %.

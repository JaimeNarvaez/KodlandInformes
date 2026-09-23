# Informes de desarrollo — Kodland

Genera un **PDF por alumno** con su progreso en el curso, listo para entregar a
las familias. Saca los datos reales del panel de profesores de Kodland.

## Qué lleva el informe

| Página | Contenido |
|---|---|
| 1 | Banner de Kodland, **datos básicos del estudiante**, objetivo del informe y cómo interpretarlo |
| 2 | Aprovechamiento promedio, visión general y gráfico por módulo |
| 3 | Calificaciones y asistencia |
| 4+ | Detalle módulo por módulo: aprendizajes y proyecto desarrollado |
| última | Consideraciones finales, firma del tutor y sello de Kodland |

Las hojas se reparten midiendo lo que ocupa cada módulo, para que ninguna quede
a medias.

## Instalación (una sola vez)

1. **Python 3** — https://www.python.org/downloads/ (marca *Add python.exe to PATH*).
2. La única dependencia es Playwright:

```
py -3 -m pip install --upgrade playwright
py -3 -m playwright install chromium
```

3. Copia `config.example.json` como **`config.json`** y pon tu **ID de profesor**:
   el número de `https://bo.kodland.org/teachers/<ID>`.

## Uso

Doble clic en **`1 - Generar informes.bat`**, o desde la terminal:

```
py -3 informes.py                    # el grupo más reciente
py -3 informes.py --grupo COL12429   # un grupo concreto (o parte del código)
py -3 informes.py --todos            # todos los grupos activos
```

La primera vez se abre Chrome con el login de Kodland: **inicia sesión a mano una
vez**. La sesión queda guardada en `~/.kodland_calificador` y no se vuelve a pedir.

Los PDF salen en `reportes/salida/`.

## Completar los datos básicos

Los diez campos de la primera página se piden al backoffice. Lo que la plataforma
no devuelva queda con un guion, y se rellena así:

1. Copia `reportes/datos.example.json` como **`reportes/datos_<CODIGO_DEL_GRUPO>.json`**.
2. Pon en `_grupo` lo común a todo el grupo y, con el nombre completo de cada
   alumno como clave, lo suyo.

Lo de ese archivo manda sobre lo que venga de la API. **No se sube al
repositorio**: lleva datos personales de alumnos.

## Contenido de los cursos

Cada curso tiene su plantilla en `reportes/curso_<curso>.json` con los módulos,
aprendizajes, proyectos y textos. Para añadir uno nuevo, copia
`reportes/curso.example.json`. El curso se elige solo, según el nombre que
devuelve la plataforma para el grupo.

## Generar un informe suelto, sin conectarse

Útil para probar el diseño o rehacer un informe con datos a mano:

```
py -3 generar_reporte.py --curso reportes/curso_unity.json --alumno "Nombre" ^
   --profesor "Tutor" --pct 100,95,88,92,85,90,78,0,0,0
```

## Estructura

| Archivo | Qué hace |
|---|---|
| `informes.py` | Programa principal: sesión, elección de grupos y recorrido |
| `kodland_datos.py` | Sesión, lista de grupos, API v2 y progreso de cada alumno |
| `generar_reporte.py` | Arma el HTML del informe y lo convierte a PDF |
| `reportes/` | Plantillas de curso, banner y los PDF generados |

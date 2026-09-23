@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=py -3"
%PY% -c "1" >nul 2>nul || set "PY=python"
%PY% -c "1" >nul 2>nul || (echo No se encontro Python. Instalalo desde https://python.org y vuelve a intentar. & pause & exit /b 1)
echo.
echo INFORMES DE DESARROLLO POR ALUMNO
echo Un PDF por alumno del grupo. No califica ni comenta nada.
echo Necesita el contenido del curso en:  reportes\curso_^<curso^>.json
echo Se guardan en:  reportes\salida\
echo NOTA: consulta las tareas leccion por leccion, puede tardar un poco.
echo.
set /p GRUPO="Codigo del grupo (o parte). Enter = solo el mas reciente: "
echo.
if "%GRUPO%"=="" (
  %PY% informes.py
) else (
  %PY% informes.py --grupo "%GRUPO%"
)
echo.
pause

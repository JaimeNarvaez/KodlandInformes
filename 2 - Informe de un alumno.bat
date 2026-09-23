@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=py -3"
%PY% -c "1" >nul 2>nul || set "PY=python"
%PY% -c "1" >nul 2>nul || (echo No se encontro Python. Instalalo desde https://python.org y vuelve a intentar. & pause & exit /b 1)
echo.
echo INFORME DE UN SOLO ALUMNO
echo Genera el PDF de desarrollo de un alumno concreto.
echo Se guarda en:  reportes\salida\^<grupo^>_desarrollo\
echo.
REM La extension de Chrome llama a este .bat con el ID del alumno ya puesto.
set "ALUMNO=%~1"
if not "%ALUMNO%"=="" (
  echo Alumno %ALUMNO%: se genera un PDF por cada grupo en que este inscrito.
  echo.
  %PY% informes.py --alumno "%ALUMNO%"
  goto fin
)
echo Puedes poner su ID, la URL de su ficha ^(https://bo.kodland.org/students/...^)
echo o su nombre ^(o parte; no importan mayusculas ni tildes^).
echo Con el ID se genera un PDF por cada grupo en que este inscrito.
echo.
:pedir_alumno
set /p ALUMNO="Alumno: "
if "%ALUMNO%"=="" goto pedir_alumno
set "GRUPO="
set /p GRUPO="Codigo del grupo (o parte). Enter = buscar en todos los grupos: "
echo.
if "%GRUPO%"=="" (
  %PY% informes.py --alumno "%ALUMNO%"
) else (
  %PY% informes.py --grupo "%GRUPO%" --alumno "%ALUMNO%"
)
:fin
echo.
pause

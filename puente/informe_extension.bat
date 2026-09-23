@echo off
chcp 65001 >nul
REM Lo abre el puente cuando se pulsa "Generar informe" en la extension.
REM Los datos ya los reunio la extension: aqui no se inicia sesion.
cd /d "%~dp0.."
set "PY=py -3"
%PY% -c "1" >nul 2>nul || set "PY=python"
%PY% -c "1" >nul 2>nul || (echo No se encontro Python. Instalalo desde https://python.org y vuelve a intentar. & pause & exit /b 1)
echo.
echo INFORME DE DESARROLLO DEL ALUMNO %~1
echo Se guarda en:  reportes\salida\^<grupo^>_desarrollo\
echo.
%PY% informes.py --paquete "registros\paquete_%~1.json"
echo.
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=py -3"
%PY% -c "1" >nul 2>nul || set "PY=python"
%PY% -c "1" >nul 2>nul || (echo No se encontro Python. Instalalo desde https://python.org y vuelve a intentar. & pause & exit /b 1)
echo.
echo INSTALAR PUENTE (conecta la extension "Kodland Informes" con este proyecto)
echo.
echo Necesitas el ID de la extension:
echo  1. Abre  chrome://extensions  y activa "Modo de desarrollador"
echo  2. "Cargar extension sin empaquetar" y elige la carpeta  extension
echo  3. Copia el ID ^(32 letras^) que aparece bajo "Kodland Informes"
echo.
%PY% instalar_puente.py
echo.
pause

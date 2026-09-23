@echo off
REM Lo ejecuta Chrome como host de Native Messaging. NO debe imprimir nada:
REM stdout es el canal binario con Chrome.
setlocal
set "PY=py -3"
%PY% -c "1" >nul 2>nul || set "PY=python"
%PY% "%~dp0puente_informes.py"

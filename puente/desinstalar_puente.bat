@echo off
chcp 65001 >nul
echo Quitando el puente de informes del registro de Windows...
reg delete "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.kodland.informes" /f >nul 2>nul && echo   - Chrome: quitado || echo   - Chrome: no estaba
reg delete "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.kodland.informes" /f >nul 2>nul && echo   - Edge: quitado || echo   - Edge: no estaba
echo.
pause

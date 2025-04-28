@echo off
echo Iniciando bot de Telegram...
echo Fecha y hora: %date% %time%

:start
echo Ejecutando bot...
python app.py
echo.
echo Bot cerrado o error detectado
echo Fecha y hora: %date% %time%
echo Esperando 5 segundos antes de reiniciar...
timeout /t 5
echo Reiniciando bot...
goto start 
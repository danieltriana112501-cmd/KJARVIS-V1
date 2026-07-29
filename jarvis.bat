@echo off
setlocal

set "PYTHON=C:\Users\danie\AppData\Local\Programs\Python\Python312\python.exe"
set "JARVIS_DIR=%~dp0Jarvis"

if not exist "%PYTHON%" (
    echo No se encontro Python en %PYTHON%
    echo Editar jarvis.bat y corregir la ruta.
    pause
    exit /b 1
)

cd /d "%JARVIS_DIR%"
"%PYTHON%" -m app.ui

if errorlevel 1 (
    echo.
    echo Jarvis se cerro con error. Ver arriba.
    pause
)

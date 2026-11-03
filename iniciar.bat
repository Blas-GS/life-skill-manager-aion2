@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Life Skill Manager - Aion 2

echo ==============================================
echo   Life Skill Manager - Aion 2
echo ==============================================
echo.

rem --- is it already running? ---
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    echo La app ya está en marcha. Abriendo el navegador...
    start "" http://localhost:8000
    timeout /t 3 >nul
    exit /b 0
)

rem --- virtual environment ---
if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno de Python en .venv ...
    set "PY_BASE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    call :crear_venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo ERROR: no se pudo crear el entorno. Instala Python 3.14 desde https://www.python.org/downloads/
        echo y vuelve a ejecutar este archivo.
        pause
        exit /b 1
    )
)

echo Comprobando dependencias...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo AVISO: no se pudieron instalar todas las dependencias. ¿Hay conexión a internet?
    echo Se intenta arrancar igualmente.
    echo.
)

rem --- .env to connect to YOUR Supabase project (optional) ---
if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    echo.
    echo Creado el archivo .env. Si quieres guardar el histórico en tu Supabase,
    echo rellena SUPABASE_URL y SUPABASE_KEY ^(guía: docs\supabase.md^).
    echo Mientras esté vacío se usa la base de datos local data\aion2.db.
)

rem --- recipe catalog (not in the repository: downloaded from metabot.gg) ---
if not exist "data\catalogo.json" (
    echo.
    echo Primera vez: descargando el catálogo de recetas de metabot.gg.
    echo Va despacio a propósito ^(una petición cada 2 s^); tarda unos minutos.
    ".venv\Scripts\python.exe" tools\importar_metabot.py
    if errorlevel 1 (
        echo.
        echo AVISO: no se pudo generar el catálogo. La app arrancará, pero sin recetas.
        echo Vuelve a abrir este archivo cuando tengas conexión.
    )
)

echo.
echo Arrancando en http://localhost:8000  (cierra esta ventana o pulsa Ctrl+C para salir)
echo La app solo lee la pantalla: nunca envía clics ni teclas al juego.
echo.
start "" /b cmd /c "timeout /t 3 >nul & start "" http://localhost:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
echo.
echo La app se ha detenido.
pause
exit /b 0

:crear_venv
if exist "%PY_BASE%" (
    "%PY_BASE%" -m venv .venv
    exit /b 0
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3.14 -m venv .venv
    exit /b 0
)
echo No encuentro Python 3.14 en "%PY_BASE%" ni el lanzador "py".
exit /b 1

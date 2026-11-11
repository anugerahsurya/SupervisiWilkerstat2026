@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8765/'; if ($r.Content.Contains('Ruang supervisi')) { exit 0 } } catch {}; exit 1"
if not errorlevel 1 (
    start "" "http://127.0.0.1:8765/"
    exit /b 0
)
python -c "import flask, waitress, shapely, pyproj, openpyxl, numpy, psycopg, dotenv" >nul 2>nul
if errorlevel 1 (
    python -m pip install -r requirements.txt
    if errorlevel 1 goto gagal
)
start "" "http://127.0.0.1:8765/"
python server.py
if not errorlevel 1 exit /b 0
:gagal
pause

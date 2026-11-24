@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python manage.py backup_database --if-exists
if errorlevel 1 goto failed
python manage.py migrate
if errorlevel 1 goto failed
python manage.py import_season_json --file data/season2.json --season 2
if errorlevel 1 goto failed
python manage.py import_season_json --file data/season3.json --season 3
if errorlevel 1 goto failed
echo.
echo Both seasons imported. Open Django Admin and select Players to review.
pause
exit /b 0
:failed
echo.
echo Import failed. Read the error above and share it for troubleshooting.
pause
exit /b 1

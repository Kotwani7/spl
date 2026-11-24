@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -c requirements-lock.txt
if errorlevel 1 goto failed
if not exist ".env" copy .env.example .env
python manage.py backup_database --if-exists
if errorlevel 1 goto failed
python manage.py migrate
if errorlevel 1 goto failed
echo.
echo If this is your first run, create the admin account with:
echo python manage.py createsuperuser
echo Then run: python manage.py runserver
pause
exit /b 0
:failed
echo Setup stopped. The backup or migration check failed. Read the error above.
pause
exit /b 1

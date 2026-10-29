@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo Установите Python и отметьте Add to PATH
  pause
  exit /b 1
)

python -m pip install -r requirements.txt

echo.
echo SQL Server: выполни VPNDB.sql в SSMS (F5), в db.py поправь SERVER=...
echo Без сервера сайт сам переключится на SQLite (vpn.db).
echo.
echo STEPVPN: http://127.0.0.1:5002
echo Стоп: Ctrl+C
echo.
python app.py
pause

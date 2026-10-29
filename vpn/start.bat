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
echo 1^) Открой SSMS ^(SQL Server Management Studio^)
echo 2^) Подключись к своему серверу
echo 3^) Открой VPNDB.sql и нажми Execute ^(F5^)
echo 4^) Если сайт не видит БД — в db.py поправь SERVER=...
echo.
echo STEPVPN: http://127.0.0.1:5002
echo Стоп: Ctrl+C
echo.
python app.py
pause

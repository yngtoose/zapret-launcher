@echo off
chcp 65001 > nul
:: Сборка одиночного .exe через PyInstaller.
:: Требуется Python 3.11+ (используем launcher py -3.12).

cd /d "%~dp0"

echo === Проверяю PyInstaller ===
py -3.12 -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Устанавливаю PyInstaller...
    py -3.12 -m pip install --upgrade pyinstaller
)

echo === Собираю .exe ===
py -3.12 -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --uac-admin ^
    --name "ZapretBooster" ^
    --clean ^
    zapret_launcher.py

echo.
echo Готово. Файл лежит в:  "%~dp0dist\ZapretBooster.exe"
echo (можно переименовать .exe во что угодно, например "Ускоритель.exe")
pause

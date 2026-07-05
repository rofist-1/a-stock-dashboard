@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   每日选股系统
echo ==========================================
echo.
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set NOW=%%a
echo 开始时间: %NOW%
echo.
python daily_selection_system.py --output 每日选股简报.md
echo.
for /f "tokens=*" %%b in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set END=%%b
echo 完成时间: %END%
echo.
pause

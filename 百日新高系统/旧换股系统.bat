@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   换股系统 v2.0 - 6规则筛选
echo ==========================================
echo.
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set NOW=%%a
echo 开始时间: %NOW%
echo.
python 旧系统.py --date 20260701 --output "旧换股结果.md"
echo.
for /f "tokens=*" %%b in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set END=%%b
echo 完成时间: %END%
echo.
pause

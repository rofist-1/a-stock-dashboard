@echo off
cd /d "%~dp0"
echo ==========================================
echo   百日新高 · 每日扫描
echo ==========================================
echo.
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set NOW=%%a
echo 开始时间: %NOW%
echo.
python scanner_akshare.py
echo.
for /f "tokens=*" %%b in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set END=%%b
echo 完成时间: %END%
echo.

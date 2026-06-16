@echo off
cd /d "%~dp0"
echo ==========================================
echo   百日新高 · 启动服务器
echo ==========================================
echo.
echo 请在浏览器打开: http://localhost:8080/百日新高教学看板.html
echo.
python run_server.py
pause

@echo off
chcp 65001 >nul
title 百日新高看板

echo 正在启动服务器...
start /min "" python run_server.py
timeout /t 3 /nobreak >nul

netstat -an | find "0.0.0.0:8080" >nul
if %errorlevel% equ 0 (
    echo 服务器已启动，正在打开浏览器...
    start http://localhost:8080/百日新高教学看板.html
    goto :ok
)

:: 重试一次
start /min "" python run_server.py
timeout /t 3 /nobreak >nul
netstat -an | find "0.0.0.0:8080" >nul
if %errorlevel% equ 0 (
    echo 服务器已启动，正在打开浏览器...
    start http://localhost:8080/百日新高教学看板.html
    goto :ok
)

echo [错误] 启动失败，请确认有 Python 环境。
pause
exit /b

:ok
echo.
echo 浏览器已打开，关闭此窗口不影响服务器运行。
echo 如需停止服务器，请双击 stop_server.bat
timeout /t 5 /nobreak >nul
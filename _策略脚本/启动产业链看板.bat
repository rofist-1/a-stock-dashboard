@echo off
title 产业链分析看板 - 端口 8880
echo ============================================
echo   产业链分析看板 正在启动...
echo ============================================
echo.
echo 服务器端口: 8880
echo 服务目录: %USERPROFILE%\Desktop
echo 看板地址: http://localhost:8880/产业链分析看板.html
echo.
echo 按 Ctrl+C 停止服务器
echo ============================================
python -m http.server 8880 -d "%USERPROFILE%\Desktop"
pause

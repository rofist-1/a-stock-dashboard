@echo off
chcp 65001 >nul
title 停止服务器
echo 正在停止百日新高服务器...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8080" ^| find "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
timeout /t 1 /nobreak >nul
echo 服务器已停止。
timeout /t 2 /nobreak >nul
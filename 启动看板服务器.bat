@echo off
cd /d C:\Users\Rofis\Desktop\a-stock-dashboard
start "Dashboard Server 8080" cmd /k python run_server.py
timeout /t 2 /nobreak >nul
start "" http://localhost:8080/
exit

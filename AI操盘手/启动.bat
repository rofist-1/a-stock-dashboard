@echo off
cd /d "%~dp0"
start http://127.0.0.1:8899
py -3.13 -u server.py
pause

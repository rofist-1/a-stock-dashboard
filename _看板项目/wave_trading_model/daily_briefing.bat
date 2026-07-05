@echo off
chcp 65001 >nul
cd /d "C:\Users\Rofis\Desktop"
python -X utf8 -m wave_trading_model.run_briefing
exit /b 0

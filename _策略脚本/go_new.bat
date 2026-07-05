@echo off
echo 正在关闭系统代理...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f >nul
echo 开始抓取数据...
python auto_scan.py
echo 抓取完成！
pause
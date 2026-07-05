@echo off
cd /d C:\Users\Rofis\Desktop
echo 正在启动看板服务器...
start /B python -m http.server 8080
timeout /t 2 >nul
start http://localhost:8080/A%E8%82%A1%E5%B8%82%E5%9C%BA%E6%83%85%E7%BB%AA%E7%BB%BC%E5%90%88%E7%9C%8B%E6%9D%BF17.html
echo 看板已打开 ^(http://localhost:8080^)

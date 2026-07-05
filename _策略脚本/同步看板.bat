@echo off
chcp 65001 >nul
echo =============================
echo  A股看板同步上传脚本
echo =============================

set GIT="C:\Program Files\Git\bin\git.exe"
set REPO=C:\Users\Rofis\Desktop\a-stock-dashboard
set DESKTOP=C:\Users\Rofis\Desktop

echo 正在复制最新看板文件...

for /f "delims=" %%i in ('dir /b /o-d "%DESKTOP%\a股波段看板_*.json" 2^>nul') do (
    copy /y "%DESKTOP%\%%i" "%REPO%\%%i" >nul
    copy /y "%DESKTOP%\%%i" "%REPO%\data.json" >nul
    goto next1
)
:next1

for /f "delims=" %%i in ('dir /b /o-d "%DESKTOP%\A股市场情绪综合看板*.html" 2^>nul') do (
    copy /y "%DESKTOP%\%%i" "%REPO%\index.html" >nul
    copy /y "%DESKTOP%\%%i" "%REPO%\%%i" >nul
    goto next2
)
:next2

cd /d "%REPO%"

echo 正在提交到 GitHub...
%GIT% add .
%GIT% commit -m "update %date%"
%GIT% push

echo.
echo =============================
echo  ✓ 上传完成！
echo  网页地址：
echo  https://rofist-1.github.io/a-stock-dashboard/
echo =============================
pause

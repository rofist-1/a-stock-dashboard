# 每日更新：百日新高 + 底部放量大阳线
Write-Host "=== 百日新高系统 每日更新 ===" -ForegroundColor Cyan
Write-Host ""

# 1. 运行百日新高扫描
Write-Host "[1/2] 扫描百日新高..." -ForegroundColor Yellow
& python "$PSScriptRoot\scanner_akshare.py"
if ($LASTEXITCODE -ne 0) { Write-Host "⚠ 扫描异常，继续" -ForegroundColor Red }

Write-Host ""
Write-Host "[2/2] 扫描底部放量大阳线..." -ForegroundColor Yellow
& python "$PSScriptRoot\bottom_surge_monitor.py"
if ($LASTEXITCODE -ne 0) { Write-Host "⚠ 监测异常" -ForegroundColor Red }

Write-Host ""
Write-Host "=== 完成！刷新 http://127.0.0.1:8080/A股市场情绪综合看板17.html ===" -ForegroundColor Green

# -*- coding: utf-8 -*-
# 百日新高 · 自动更新设置
# 以管理员身份运行此脚本
# 右键 → 以 PowerShell 管理员身份运行

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DailyBat = Join-Path $ScriptDir "daily_scan.bat"
$ServerPy = Join-Path $ScriptDir "run_server.py"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  百日新高 · 自动更新设置" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. 创建每日扫描任务（交易日 15:30 运行）
Write-Host "▸ 创建每日扫描任务..." -ForegroundColor Yellow

# 删除旧任务（如果存在）
schtasks /Delete /TN "BairiXinGao\DailyScan" /F 2>$null

# 创建新任务
schtasks /Create /TN "BairiXinGao\DailyScan" /TR "`"$DailyBat`"" /SC DAILY /ST 15:30 /IT /F

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ 每日扫描任务已创建" -ForegroundColor Green
    Write-Host "    运行时间: 每天 15:30" -ForegroundColor Green
    Write-Host "    仅计算机开机时生效" -ForegroundColor Gray
} else {
    Write-Host "  ✗ 创建失败，请以管理员身份运行" -ForegroundColor Red
}

# 2. 设置服务器开机自启（可选）
Write-Host ""
Write-Host "▸ 是否设置服务器开机自启？（每次开机自动启动看板服务器）" -ForegroundColor Yellow
$choice = Read-Host "  输入 y 确认，其他跳过"

if ($choice -eq 'y') {
    # 使用 Windows 计划任务实现开机自启
    schtasks /Delete /TN "BairiXinGao\Server" /F 2>$null
    schtasks /Create /TN "BairiXinGao\Server" /TR "python `"$ServerPy`"" /SC ONLOGON /DELAY 0000:30 /IT /F
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ 服务器自启已设置" -ForegroundColor Green
        Write-Host "    每次登录后 30 秒自动启动" -ForegroundColor Green
    } else {
        Write-Host "  ✗ 设置失败" -ForegroundColor Red
    }
}

# 3. 手动测试
Write-Host ""
Write-Host "▸ 是否立即运行一次扫描测试？" -ForegroundColor Yellow
$test = Read-Host "  输入 y 确认，其他跳过"

if ($test -eq 'y') {
    Write-Host "  正在运行扫描（首次约3分钟，后续约30秒）..." -ForegroundColor Gray
    python "$ScriptDir\scanner_akshare.py"
    Write-Host "  ✓ 扫描完成" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  设置完成！" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "查看任务: taskschd.msc → 任务计划程序库 → BairiXinGao"
Write-Host "手动运行: python scanner_akshare.py"
Write-Host "启动服务: python run_server.py"
Write-Host "访问看板: http://localhost:8080/百日新高教学看板.html"
Write-Host ""
pause

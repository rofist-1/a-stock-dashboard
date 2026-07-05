# 创建/更新 Windows 计划任务
# 以管理员身份运行此脚本
# 用法: powershell -ExecutionPolicy Bypass -File create_task.ps1

$taskName = "WaveTradingModel_DailyBriefing"
$batchFile = "C:\Users\Rofis\Desktop\wave_trading_model\daily_briefing.bat"
$time = "14:50"
$days = "MON,TUE,WED,THU,FRI"
$user = "$env:COMPUTERNAME\$env:USERNAME"

Write-Host "创建计划任务: $taskName"
Write-Host "  - 执行: $batchFile"
Write-Host "  - 时间: 每个交易日 $time"
Write-Host "  - 用户: $user"

# 删除已存在的同名任务
schtasks /delete /tn $taskName /f > $null 2>&1

# 创建新任务
$cmd = "schtasks /create /tn `"$taskName`" /tr `"$batchFile`" /sc WEEKLY /d $days /st $time /ru `"$user`" /it /f"
Invoke-Expression $cmd

Write-Host ""
Write-Host "验证:"
schtasks /query /tn $taskName /fo LIST

Write-Host ""
Write-Host "任务创建完成。如需删除请运行:"
Write-Host "  schtasks /delete /tn `"$taskName`" /f"

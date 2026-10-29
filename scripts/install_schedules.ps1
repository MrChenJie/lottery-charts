# Install / refresh Windows tasks for lottery sync (run as current user).
$ErrorActionPreference = "Stop"
$root = "C:\Users\PC\Projects\lottery-charts"
$ps = "powershell.exe"

function Register-LotteryTask {
  param(
    [string]$Name,
    [string]$Description,
    [string]$ScriptRel,
    [object[]]$Triggers,
    [string[]]$ScriptArgs = @()
  )
  $scriptPath = Join-Path $root $ScriptRel
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
  if ($ScriptArgs.Count -gt 0) {
    $argList += " " + ($ScriptArgs -join " ")
  }
  $action = New-ScheduledTaskAction -Execute $ps -Argument $argList
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3)
  Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Triggers `
    -Settings $settings -Description $Description -Force | Out-Null
  Write-Host "Registered $Name"
}

# Backup full refresh every 6 hours (keep existing task if present; else create daily+repeat)
$existing = Get-ScheduledTask -TaskName "LotteryChartsAutoUpdate" -ErrorAction SilentlyContinue
if (-not $existing) {
  $start = (Get-Date).Date.AddHours(((Get-Date).Hour - (Get-Date).Hour % 6 + 6) % 24)
  if ($start -le (Get-Date)) { $start = $start.AddHours(6) }
  $t6 = New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Hours 6) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
  Register-LotteryTask -Name "LotteryChartsAutoUpdate" `
    -Description "Backup: fetch lottery draws every 6 hours" `
    -ScriptRel "scripts\update_and_push.ps1" `
    -Triggers @($t6)
} else {
  Write-Host "Keep existing LotteryChartsAutoUpdate"
}

# Morning board refresh
$tMorning = New-ScheduledTaskTrigger -Daily -At 9:00am
Register-LotteryTask -Name "LotteryChartsDailyPredict" `
  -Description "Daily 09:00 refresh + next-issue board" `
  -ScriptRel "scripts\update_and_push.ps1" `
  -Triggers @($tMorning)

# 20:40 — 福彩3D / 排列3 开奖后（约 20:30）
$t2040 = New-ScheduledTaskTrigger -Daily -At "8:40pm"
Register-LotteryTask -Name "LotteryChartsPostDraw2040" `
  -Description "Post-draw poll from 20:40 (3D/PL3 first, then evening games)" `
  -ScriptRel "scripts\post_draw_update.ps1" `
  -Triggers @($t2040)

# 21:30 — 双色球 / 七乐彩 开奖后窗口
$t2130 = New-ScheduledTaskTrigger -Daily -At "9:30pm"
Register-LotteryTask -Name "LotteryChartsPostDraw2130" `
  -Description "Post-draw poll from 21:30 (SSQ/QLC/DLT as scheduled today)" `
  -ScriptRel "scripts\post_draw_update.ps1" `
  -Triggers @($t2130)

# 21:45 — 大乐透再盯一轮（约 21:25 开奖）
$t2145 = New-ScheduledTaskTrigger -Daily -At "9:45pm"
Register-LotteryTask -Name "LotteryChartsPostDraw2145" `
  -Description "Post-draw poll from 21:45 focusing DLT evening" `
  -ScriptRel "scripts\post_draw_update.ps1" `
  -Triggers @($t2145) `
  -ScriptArgs @("dlt")

Get-ScheduledTask -TaskName "LotteryCharts*" | Format-Table TaskName, State
Write-Host "Done. Logs: $env:LOCALAPPDATA\lottery-charts\update.log"

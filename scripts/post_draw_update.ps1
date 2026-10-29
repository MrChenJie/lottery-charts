# After official draw time: poll until today's results are accurate, then push Pages.
# Accuracy: multi-source cross-check for SSQ/DLT/QLC; never invent numbers.
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\PC\Projects\lottery-charts"

$env:Path = "C:\Users\PC\AppData\Local\gh-cli\bin;" + $env:Path
$logDir = Join-Path $env:LOCALAPPDATA "lottery-charts"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "update.log"

function Write-Log([string]$msg) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $log -Value $line
  Write-Output $line
}

$only = $args
$pyArgs = @("scripts/fetch_lottery.py", "--post-draw", "--poll-seconds", "180", "--max-minutes", "100")
if ($only -and $only.Count -gt 0) {
  $pyArgs += @("--only") + $only
}

try {
  Write-Log ("START post-draw " + ($only -join ","))
  & python @pyArgs
  $code = $LASTEXITCODE
  if ($code -ne 0) {
    Write-Log "WARN post-draw exit=$code"
  }

  git add data
  git diff --staged --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Log "No data changes after post-draw"
    exit 0
  }

  git commit -m "chore: post-draw refresh lottery data"
  git -c http.sslBackend=schannel -c http.sslCAInfo= push origin main
  Write-Log "PUSH ok (post-draw)"
  exit 0
}
catch {
  Write-Log ("ERROR " + $_.Exception.Message)
  exit 1
}

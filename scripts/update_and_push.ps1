# Refresh lottery JSON and push to GitHub Pages origin.
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

try {
  Write-Log "START fetch"
  python scripts/fetch_lottery.py
  if ($LASTEXITCODE -ne 0) {
    Write-Log "WARN fetch exit=$LASTEXITCODE (may still have partial data)"
  }

  git add data
  git diff --staged --quiet
  if ($LASTEXITCODE -eq 0) {
    Write-Log "No data changes"
    exit 0
  }

  git commit -m "chore: refresh lottery draw data"
  git -c http.sslBackend=schannel -c http.sslCAInfo= push origin main
  Write-Log "PUSH ok"
  exit 0
}
catch {
  Write-Log ("ERROR " + $_.Exception.Message)
  exit 1
}

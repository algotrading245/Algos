# Compiles one EA from the repo with Terminal 16's MetaEditor and prints the result line and any error or warning.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\compile.ps1 -Expert AurumNoise
#
# It compiles the repo copy in place (standard includes from Terminal 16's MQL5 folder) and never writes into the
# terminal, so it is safe while the demo runs. The .ex5 lands next to the source (never committed). Exit code 1 when
# the result is not "0 errors, 0 warnings".
param([Parameter(Mandatory = $true)][string]$Expert)
. "$PSScriptRoot\common.ps1"

$src = Join-Path $Repo "mql5\Experts\$Expert\$Expert.mq5"
if (-not (Test-Path $src)) { Write-Output "no source: mql5\Experts\$Expert\$Expert.mq5"; exit 2 }
$mql5 = Join-Path $env:APPDATA "MetaQuotes\Terminal\66FB7F5B174F9C3B2A690C49FF012FEB\MQL5"
$log = Join-Path $env:TEMP "aurum_${Expert}_compile.log"
Remove-Item $log -ErrorAction SilentlyContinue
Start-Process (Join-Path $T16 "metaeditor64.exe") -ArgumentList "/compile:`"$src`"", "/include:`"$mql5`"", "/log:`"$log`"" -Wait
$lines = Get-Content $log | Where-Object { $_ -match "error|warning|result" }
$lines | ForEach-Object { $_ -replace [regex]::Escape($Repo), "." -replace [regex]::Escape($env:APPDATA), "%APPDATA%" }
if (-not ($lines -match "\b0 errors?, 0 warnings?")) { exit 1 }

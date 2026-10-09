# Compiles AurumLadder, runs its unit tests, then a Strategy Tester job, and copies
# the report, per-ladder CSV and acceptance verdict into backtests\<date>_<run>\.
#
#   powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run baseline
#   powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run tune
#   powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run holdout
#   powershell -ExecutionPolicy Bypass -File tools\run-backtest.ps1 -Run unittest
#
# MT5 ignores /config when the same install is already open, so the target
# terminal must be closed first. Nothing here places live trades: the tester runs
# on history only and the unit-test script makes no trading calls.
param(
    [ValidateSet("unittest", "baseline", "tune", "holdout")]
    [string]$Run = "baseline",
    [string]$Terminal = "C:\Program Files\MetaTrader 5 - 14",
    [string]$DataFolder = "$env:APPDATA\MetaQuotes\Terminal\C0E230B8F9C8C2A16D1EE5E91A38A7CF"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Terminal "terminal64.exe"

$running = Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }
if ($running) {
    throw "$exe is open. Close it (File > Exit) and run again; MT5 ignores /config while it is running."
}

& (Join-Path $PSScriptRoot "link-terminal.ps1") -DataFolder $DataFolder

function Compile([string]$rel) {
    $src = Join-Path $DataFolder "MQL5\$rel"
    $log = Join-Path $env:TEMP "aurumladder_compile.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    Start-Process (Join-Path $Terminal "metaeditor64.exe") -ArgumentList "/compile:`"$src`"", "/log:`"$log`"" -Wait
    $text = Get-Content $log -Raw
    $text -split "`r?`n" | Where-Object { $_ -match "error|warning" } | ForEach-Object { Write-Host "  $_" }
    if ($text -notmatch "(?<!\d)0 errors?\b") { throw "compile failed: $rel (log: $log)" }
    Write-Host "compiled $rel"
}

function Start-Terminal([string]$ini) {
    $tmp = Join-Path $env:TEMP "aurumladder_run.ini"
    Set-Content -Path $tmp -Value $ini -Encoding Unicode
    Start-Process $exe -ArgumentList "/config:`"$tmp`"" -Wait
}

function Read-NewLogLines([string]$dir, [datetime]$since, [string]$pattern) {
    Get-ChildItem $dir -Filter *.log -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $since } |
        ForEach-Object { Get-Content $_.FullName -Encoding Unicode } |
        Where-Object { $_ -match $pattern }
}

Compile "Scripts\AurumLadder\LadderTest.mq5"
Compile "Experts\AurumLadder\AurumLadder.mq5"

if ($Run -eq "unittest") {
    $t0 = Get-Date
    Start-Terminal "[StartUp]`r`nScript=AurumLadder\LadderTest`r`nSymbol=XAUUSD.pc`r`nPeriod=M15`r`nShutdownTerminal=1`r`n"
    $lines = Read-NewLogLines (Join-Path $DataFolder "MQL5\Logs") $t0 "LadderTest|FAIL:"
    $lines | ForEach-Object { Write-Host $_ }
    if (-not ($lines -match "LadderTest: \d+ passed, 0 failed")) { throw "unit tests did not pass" }
    return
}

$cfg = Get-Content (Join-Path $repo "tester\$Run.ini") -Raw
$out = Join-Path $repo ("backtests\{0}_{1}" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $Run)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$csv = "$env:APPDATA\MetaQuotes\Terminal\Common\Files\AurumLadder_245001_tester.csv"
Remove-Item $csv -ErrorAction SilentlyContinue

Write-Host "running $Run (real ticks; this can take a long time)..."
$t0 = Get-Date
Start-Terminal $cfg

Get-ChildItem $DataFolder -Filter "AurumLadder_$Run*" | Copy-Item -Destination $out
if (Test-Path $csv) { Copy-Item $csv (Join-Path $out "ladders.csv") }
$summary = Read-NewLogLines (Join-Path $DataFolder "Tester") $t0 `
    "AurumLadder summary|net profit|win rate|worst ladder|drawdown|ACCEPTANCE|zone too small|balance needed|could not|failed"
if ($Run -ne "tune") {
    $summary | Set-Content (Join-Path $out "summary.txt")
    $summary | Select-Object -Last 7 | ForEach-Object { Write-Host $_ }
}
Copy-Item (Join-Path $repo "tester\$Run.ini") $out
Write-Host "results in $out"

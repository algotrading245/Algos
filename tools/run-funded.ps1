# Compiles AurumFunded and runs it in the Strategy Tester of an FTMO MT5 install with one of its presets, then
# copies the report and the EA's own log lines (day stops, final stop, target) into backtests\<date>_funded_<preset>\.
#
#   powershell -ExecutionPolicy Bypass -File tools\run-funded.ps1                       # phase 1, 2024-01 to now
#   powershell -ExecutionPolicy Bypass -File tools\run-funded.ps1 -Preset funded -From 2023.01.01
#   powershell -ExecutionPolicy Bypass -File tools\run-funded.ps1 -Terminal "C:\Program Files\MetaTrader 5 - 15"
#
# The phase presets stop the test at the target or the final stop (TesterStop), so a phase run ends the day the
# phase would be passed or lost; the funded preset has no target and runs the whole period, which shows the day
# stops and the drawdown.  Use an install logged in to an FTMO account (a free trial is enough) so the symbols,
# their history and the server clock are FTMO's; check that the symbol names in the EA's inputs (XAUUSD,
# US500.cash, the currency pairs) exist there.  Close that install first: MT5 ignores /config while it is open.
# Nothing here places live trades: the tester runs on history only.
param(
    [ValidateSet("phase1", "phase2", "funded")]
    [string]$Preset = "phase1",
    [string]$Terminal = "C:\Program Files\FTMO MetaTrader 5",
    [string]$DataFolder = "",
    [string]$From = "2024.01.01",
    [string]$To = (Get-Date -Format "yyyy.MM.dd"),
    [int]$Deposit = 100000,
    [int]$Leverage = 30,
    [string]$Symbol = "XAUUSD"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $Terminal "terminal64.exe"
if (-not (Test-Path $exe)) { throw "$exe not found; pass -Terminal <install folder>" }

# Each install's data folder records its install path in origin.txt.
if (-not $DataFolder) {
    $DataFolder = Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal" -Directory |
        Where-Object {
            $o = Join-Path $_.FullName "origin.txt"
            (Test-Path $o) -and ("$(Get-Content $o -Raw)".Trim().TrimEnd('\') -eq $Terminal.TrimEnd('\'))
        } | Select-Object -First 1 -ExpandProperty FullName
    if (-not $DataFolder) { throw "No data folder for $Terminal yet. Start it once, log in, then close it." }
}
Write-Host "terminal $Terminal"
Write-Host "data     $DataFolder"

$running = Get-Process terminal64 -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exe }
if ($running) { throw "$exe is open. Close it (File > Exit) and run again; MT5 ignores /config while it is running." }

& (Join-Path $PSScriptRoot "link-terminal.ps1") -DataFolder $DataFolder -Project AurumFunded

$src = Join-Path $DataFolder "MQL5\Experts\AurumFunded\AurumFunded.mq5"
$log = Join-Path $env:TEMP "aurumfunded_compile.log"
Remove-Item $log -ErrorAction SilentlyContinue
Start-Process (Join-Path $Terminal "metaeditor64.exe") -ArgumentList "/compile:`"$src`"", "/log:`"$log`"" -Wait
$text = Get-Content $log -Raw
$text -split "`r?`n" | Where-Object { $_ -match "error|warning" } | ForEach-Object { Write-Host "  $_" }
if ($text -notmatch "(?<!\d)0 errors?\b") { throw "compile failed (log: $log)" }
Write-Host "compiled AurumFunded"

# The preset's inputs, in the tester's form: name=value||start||step||stop||N (numbers), name=value (the rest).
$inputs = Get-Content (Join-Path $repo "mql5\Experts\AurumFunded\AurumFunded_FTMO_$Preset.set") |
    Where-Object { $_ -match "^\s*Inp\w+=" } |
    ForEach-Object {
        $name, $value = $_.Trim() -split "=", 2
        if ($value -match "^-?\d+(\.\d+)?$") { "$name=$value||$value||0||$value||N" } else { "$name=$value" }
    }
$report = "AurumFunded_$Preset"
$ini = @"
[Tester]
Expert=AurumFunded\AurumFunded.ex5
Symbol=$Symbol
Period=M15
Model=4
ExecutionMode=0
Deposit=$Deposit
Currency=USD
Leverage=$Leverage
ForwardMode=0
ReplaceReport=1
ShutdownTerminal=1
Visual=0
Optimization=0
FromDate=$From
ToDate=$To
Report=$report

[TesterInputs]
$($inputs -join "`r`n")
"@
$out = Join-Path $repo ("backtests\{0}_funded_{1}" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $Preset)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$tmp = Join-Path $env:TEMP "aurumfunded_run.ini"
Set-Content -Path $tmp -Value $ini -Encoding Unicode
Copy-Item $tmp (Join-Path $out "tester.ini")

Write-Host "running $Preset from $From to $To (real ticks, several symbols; this can take hours)..."
$t0 = Get-Date
Start-Process $exe -ArgumentList "/config:`"$tmp`"" -Wait

Get-ChildItem $DataFolder -Filter "$report*" | Copy-Item -Destination $out
$lines = Get-ChildItem (Join-Path $DataFolder "Tester") -Filter *.log -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -ge $t0 } |
    ForEach-Object { Get-Content $_.FullName -Encoding Unicode } |
    Where-Object { $_ -match "AurumFunded:|final balance|stopped|failed|not found|cannot" }
$lines | Set-Content (Join-Path $out "summary.txt")
$lines | Select-Object -Last 15 | ForEach-Object { Write-Host $_ }
Write-Host "results in $out"

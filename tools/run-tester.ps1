# Compiles one EA and runs it in the Strategy Tester of an MT5 install with a preset (.set) plus optional input
# overrides, then copies the report and the tester log lines into backtests\<date>_<expert>_<symbol>\.
#
#   powershell -ExecutionPolicy Bypass -File tools\run-tester.ps1 -Expert AurumBreakout -Symbol USDJPY `
#       -Preset mql5\Experts\AurumBreakout\AurumBreakout_USDJPY.set
#   powershell -ExecutionPolicy Bypass -File tools\run-tester.ps1 -Expert AurumNoise -Symbol US100.cash `
#       -Preset mql5\Experts\AurumNoise\AurumNoise_US100.set
#   powershell -ExecutionPolicy Bypass -File tools\run-tester.ps1 -Expert AurumFunded -Symbol XAUUSD `
#       -Preset mql5\Experts\AurumFunded\AurumFunded_FTMO_funded.set -Set InpBreakRiskPct=0.125,InpNoiseMult=0.275
#
# -Detach starts the terminal outside this shell's process tree (through WMI), writes job.json into the output folder
# and returns at once, so a long run survives the shell that launched it. Collect it later:
#   powershell -ExecutionPolicy Bypass -File tools\run-tester.ps1 -Collect backtests\<folder>
# which says "running" while that terminal is up, else copies the report and log lines and writes result.json.
#
# Default install: Terminal 16, logged in to an FTMO demo, so the symbols, their history and the server clock are
# FTMO's. Close that install first: MT5 ignores /config while it is open. Nothing here places live trades: the
# tester runs on history only.
param(
    [string]$Expert = "",
    [string]$Symbol = "",
    [string]$Preset = "",
    [string[]]$Set = @(),
    [string]$Terminal = "C:\Program Files\MetaTrader 5 - 16",
    [string]$DataFolder = "",
    [string]$From = "2024.01.01",
    [string]$To = (Get-Date -Format "yyyy.MM.dd"),
    [int]$Deposit = 10000,
    [int]$Leverage = 100,
    [string]$Period = "M1",
    [string]$Tag = "",
    [switch]$Detach,
    [string]$Collect = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# Copies the report and the tester log lines written since the run started, then parses the report.
function Save-Results($job, $out) {
    Get-ChildItem $job.DataFolder -Filter "$($job.Name)*" | Copy-Item -Destination $out
    $t0 = [datetime]$job.Started
    $lines = Get-ChildItem (Join-Path $job.DataFolder "Tester") -Filter *.log -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $t0 } |
        ForEach-Object { Get-Content $_.FullName -Encoding Unicode } |
        Where-Object { $_ -match "$($job.Expert):|final balance|stopped|failed|not found|cannot|error" } |
        Where-Object { $_ -notmatch "authoriz|login|account \d" }
    $lines | Set-Content (Join-Path $out "summary.txt")
    $lines | Select-Object -Last 15 | ForEach-Object { Write-Host $_ }
    & python (Join-Path $PSScriptRoot "parse_report.py") $out
    Write-Host "results in $out"
}

if ($Collect) {
    $out = if ([System.IO.Path]::IsPathRooted($Collect)) { $Collect } else { Join-Path $repo $Collect }
    $job = Get-Content (Join-Path $out "job.json") -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $job.Pid -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $job.Exe }
    if ($proc) {
        $mins = [int]((Get-Date) - [datetime]$job.Started).TotalMinutes
        Write-Host "running: $($job.Expert) on $($job.Symbol), pid $($job.Pid), $mins minutes so far"
        exit 0
    }
    Save-Results $job $out
    exit 0
}
if (-not $Expert -or -not $Symbol) { throw "pass -Expert and -Symbol (or -Collect <folder>)" }
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

& (Join-Path $PSScriptRoot "link-terminal.ps1") -DataFolder $DataFolder -Project $Expert

$src = Join-Path $DataFolder "MQL5\Experts\$Expert\$Expert.mq5"
$log = Join-Path $env:TEMP "${Expert}_compile.log"
Remove-Item $log -ErrorAction SilentlyContinue
Start-Process (Join-Path $Terminal "metaeditor64.exe") -ArgumentList "/compile:`"$src`"", "/log:`"$log`"" -Wait
$text = Get-Content $log -Raw
$text -split "`r?`n" | Where-Object { $_ -match "error|warning" } | ForEach-Object { Write-Host "  $_" }
if ($text -notmatch "(?<!\d)0 errors?\b") { throw "compile failed (log: $log)" }
Write-Host "compiled $Expert"

# Every input's default from the EA source, then the preset lines, then the overrides, in the tester's form:
# name=value||start||step||stop||N (numbers), name=value. Without the defaults, an input missing from the preset kept
# whatever value the terminal last used for it, so two runs of the same job could differ.
$values = [ordered]@{}
$skipped = @()
Get-Content (Join-Path $repo "mql5\Experts\$Expert\$Expert.mq5") | ForEach-Object {
    if ($_ -match '^\s*s?input\s+(?:const\s+)?\w+\s+(Inp\w+)\s*=\s*([^;]+);') {
        $name = $Matches[1]; $value = $Matches[2].Trim()
        if ($value -match '^"(.*)"$') { $values[$name] = $Matches[1] }
        elseif ($value -match '^(-?\d+(\.\d+)?|true|false)$') { $values[$name] = $value }
        else { $skipped += $name }    # enum names, D'...' dates, expressions: left to the preset or the terminal
    }
}
Write-Host "source defaults: $($values.Count) inputs$(if ($skipped) { "; not set from the source: $($skipped -join ', ')" })"
if ($Preset) {
    Get-Content (Join-Path $repo $Preset) | Where-Object { $_ -match "^\s*Inp\w+=" } | ForEach-Object {
        $name, $value = $_.Trim() -split "=", 2
        $values[$name] = $value
    }
}
# -File passes "-Set a=1,b=2" as one string, so split on commas here too.
foreach ($kv in ($Set -split ",")) { $name, $value = $kv -split "=", 2; $values[$name] = $value }
$inputs = foreach ($name in $values.Keys) {
    $value = $values[$name]
    if ($value -match "^-?\d+(\.\d+)?$") { "$name=$value||$value||0||$value||N" } else { "$name=$value" }
}
$name = if ($Tag) { "${Expert}_$Tag" } else { "${Expert}_$($Symbol -replace '\W', '')" }
$ini = @"
[Tester]
Expert=$Expert\$Expert.ex5
Symbol=$Symbol
Period=$Period
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
Report=$name

[TesterInputs]
$($inputs -join "`r`n")
"@
$out = Join-Path $repo ("backtests\{0}_{1}" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $name)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$tmp = Join-Path $env:TEMP "${name}_run.ini"
Set-Content -Path $tmp -Value $ini -Encoding Unicode
Copy-Item $tmp (Join-Path $out "tester.ini")

Write-Host "running $Expert on $Symbol from $From to $To (real ticks)..."
$job = [ordered]@{
    Expert = $Expert; Symbol = $Symbol; Preset = $Preset; Set = ($Set -join ","); From = $From; To = $To
    Deposit = $Deposit; Leverage = $Leverage; Period = $Period; Name = $name; Exe = $exe; DataFolder = $DataFolder
    Started = (Get-Date).ToString("o"); Pid = 0
}
if ($Detach) {
    # A process made by WMI has WmiPrvSE as its parent, so it is not killed with this shell's process tree.
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
        -Arguments @{ CommandLine = "`"$exe`" /config:`"$tmp`""; CurrentDirectory = $Terminal }
    if ($r.ReturnValue -ne 0) { throw "WMI could not start the terminal (code $($r.ReturnValue))" }
    $job.Pid = [int]$r.ProcessId
    $job | ConvertTo-Json | Set-Content (Join-Path $out "job.json")
    Write-Host "detached: pid $($job.Pid); collect with -Collect $out"
    exit 0
}
$p = Start-Process $exe -ArgumentList "/config:`"$tmp`"" -PassThru
$job.Pid = $p.Id
$job | ConvertTo-Json | Set-Content (Join-Path $out "job.json")
$p.WaitForExit()
Save-Results ([pscustomobject]$job) $out

# Runs one Strategy Tester run per calendar month (fresh deposit each month) through run-tester.ps1, one after the
# other, then python tools/months_summary.py: the share of months that reached the goal multiple. This is the test of
# the 5x EA's real question ("5x within a month?"), which one long run cannot answer: with InpGoalRepeat=false the
# 5x preset stops after its first round, and with it true each round starts from whatever the last one left.
#
#   powershell -ExecutionPolicy Bypass -File tools\run-months.ps1 -Expert AurumHydra -Symbol XAUUSD -Period M15 `
#       -Preset mql5\Experts\AurumHydra\AurumHydra_5x_month.set -Deposit 10000 -Leverage 500 -Tag 5x `
#       -FromMonth 2024.01 -ToMonth 2026.09 -Detach
#   powershell -ExecutionPolicy Bypass -File tools\run-months.ps1 -Collect backtests\<folder>
#
# -Detach starts this script again outside the caller's process tree (WMI, as run-tester.ps1 -Detach) and returns at
# once; the months run in that copy. Its folder backtests\<date>_<expert>_<tag>_months\ holds months.json (the list of
# month folders, filled as each month ends) and, at the end, months_result.json. A re-run with -Out on that folder
# skips months already done. -Collect says "running: k of n" while the copy is alive, else prints the summary.
# Close Terminal 16 first (tools\autopilot\terminal.ps1 -Hold), as for run-tester.ps1.
param(
    [string]$Expert = "",
    [string]$Symbol = "",
    [string]$Preset = "",
    [string[]]$Set = @(),
    [string]$Period = "M15",
    [int]$Deposit = 10000,
    [int]$Leverage = 100,
    [string]$Tag = "months",
    [string]$FromMonth = "2024.01",
    [string]$ToMonth = (Get-Date).AddMonths(-1).ToString("yyyy.MM"),
    [double]$Goal = 5.0,
    [switch]$Detach,
    [string]$Out = "",
    [string]$Collect = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
function Full($p) { if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $repo $p } }

if ($Collect) {
    $dir = Full $Collect
    $state = Get-Content (Join-Path $dir "months.json") -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $state.Pid -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "powershell" }
    if ($proc) {
        Write-Host "running: $(@($state.Done).Count) of $(@($state.Months).Count) months done, pid $($state.Pid)"
        exit 0
    }
    & python (Join-Path $PSScriptRoot "months_summary.py") $dir
    exit 0
}
if (-not $Expert -or -not $Symbol) { throw "pass -Expert and -Symbol (or -Collect <folder>)" }

$months = @()
$m = [datetime]::ParseExact($FromMonth, "yyyy.MM", $null)
$last = [datetime]::ParseExact($ToMonth, "yyyy.MM", $null)
while ($m -le $last) { $months += $m.ToString("yyyy.MM"); $m = $m.AddMonths(1) }
if (-not $months) { throw "no month between $FromMonth and $ToMonth" }
# The holdout (tools/holdout.py): an agent run (AURUM_AGENT=1, set by tools\autopilot\run-agent.ps1) never tests on it.
$endMonth = [regex]::Match((Get-Content (Join-Path $PSScriptRoot "holdout.py") -Raw), 'END_MONTH = "([0-9.]+)"').Groups[1].Value
if ($env:AURUM_AGENT -eq "1" -and $ToMonth -gt $endMonth) { throw "refused: -ToMonth $ToMonth reaches the holdout (after $endMonth, tools/holdout.py); agent runs end before it" }

$dir = if ($Out) { Full $Out } else { Join-Path $repo ("backtests\{0}_{1}_{2}_months" -f (Get-Date -Format "yyyy-MM-dd_HHmm"), $Expert, $Tag) }
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$stateFile = Join-Path $dir "months.json"
$state = if (Test-Path $stateFile) { Get-Content $stateFile -Raw | ConvertFrom-Json } else {
    [pscustomobject]@{ Expert = $Expert; Symbol = $Symbol; Preset = $Preset; Set = ($Set -join ","); Period = $Period
        Deposit = $Deposit; Leverage = $Leverage; Tag = $Tag; Goal = $Goal; Months = $months; Done = @(); Pid = $PID
        Started = (Get-Date).ToString("o") }
}

$common = @("-Expert", $Expert, "-Symbol", $Symbol, "-Period", $Period, "-Deposit", $Deposit, "-Leverage", $Leverage,
    "-Tag", $Tag, "-FromMonth", $FromMonth, "-ToMonth", $ToMonth, "-Goal", $Goal)
if ($Preset) { $common += @("-Preset", $Preset) }
if ($Set) { $common += @("-Set", ($Set -join ",")) }

if ($Detach) {
    $argv = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath) + $common + @("-Out", $dir)
    $cmd = ($argv | ForEach-Object { if ("$_" -match '\s') { '"' + $_ + '"' } else { "$_" } }) -join " "
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create `
        -Arguments @{ CommandLine = "powershell.exe $cmd"; CurrentDirectory = $repo }
    if ($r.ReturnValue -ne 0) { throw "WMI could not start the month runner (code $($r.ReturnValue))" }
    $state.Pid = [int]$r.ProcessId
    $state | ConvertTo-Json -Depth 4 | Set-Content $stateFile
    Write-Host "detached: $($months.Count) months, pid $($state.Pid); collect with -Collect $dir"
    exit 0
}

$state.Pid = $PID
$state | ConvertTo-Json -Depth 4 | Set-Content $stateFile
foreach ($ym in $months) {
    if (@($state.Done | Where-Object { $_.Month -eq $ym -and $_.Status -eq "done" })) { continue }
    $state.Done = @($state.Done | Where-Object { $_.Month -ne $ym })
    $first = [datetime]::ParseExact($ym, "yyyy.MM", $null)
    $to = $first.AddMonths(1).AddDays(-1)
    $monthTag = "{0}_{1}" -f $Tag, ($ym -replace '\.', '')
    $before = Get-Date
    # A hashtable: an array splatted into a script binds "-Name" strings by position, not as parameter names.
    $runArgs = @{ Expert = $Expert; Symbol = $Symbol; Period = $Period; Deposit = $Deposit; Leverage = $Leverage
        Tag = $monthTag; From = $first.ToString("yyyy.MM.dd"); To = $to.ToString("yyyy.MM.dd") }
    if ($Preset) { $runArgs.Preset = $Preset }
    if ($Set) { $runArgs.Set = @($Set -join ",") }
    $status = "done"
    try { & (Join-Path $PSScriptRoot "run-tester.ps1") @runArgs | Out-Null } catch { $status = "failed: $($_.Exception.Message)" }
    $folder = Get-ChildItem (Join-Path $repo "backtests") -Directory -Filter "*_${Expert}_$monthTag" |
        Where-Object { $_.CreationTime -ge $before.AddSeconds(-5) } | Sort-Object CreationTime | Select-Object -Last 1
    $state.Done = @($state.Done) + [pscustomobject]@{ Month = $ym; Folder = $(if ($folder) { "backtests\$($folder.Name)" } else { "" }); Status = $status }
    $state | ConvertTo-Json -Depth 4 | Set-Content $stateFile
}
& python (Join-Path $PSScriptRoot "months_summary.py") $dir

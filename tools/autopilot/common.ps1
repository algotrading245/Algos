# Shared paths and the tester window for the autopilot scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
#
# Terminal 16 (FTMO demo) runs the demo EA. The Strategy Tester runs in its own install, C:\MetaTrader 5 - Tester
# (same FTMO demo login, its own data folder), so tester jobs run at any hour and never close Terminal 16.

$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir   = Join-Path $Repo "logs\autopilot"
$HoldFile = Join-Path $LogDir "hold-terminal"
$Pause    = Join-Path $LogDir "PAUSE"
$Relay    = Join-Path $LogDir "relay.json"
$GapMinutes = 0     # relay: no gap between agents (owner 2026-10-22: one idea done, the next starts at once)
$T16      = "C:\Program Files\MetaTrader 5 - 16"
$T16Exe   = Join-Path $T16 "terminal64.exe"
$Tester   = "C:\MetaTrader 5 - Tester"
New-Item -ItemType Directory -Force $LogDir | Out-Null

function Write-Log([string]$Name, [string]$Text) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Text
    Add-Content -Path (Join-Path $LogDir "$(Get-Date -Format yyyy-MM-dd)_$Name.log") -Value $line -Encoding UTF8
}

# Weekend window, local time: Saturday 00:00 to Sunday 18:00 (FTMO reopens Sunday evening, server = local + 1h).
function Get-WindowEnd([datetime]$Now = (Get-Date)) {
    $d = $Now.Date
    switch ($Now.DayOfWeek) {
        "Saturday" { return $d.AddDays(1).AddHours(18) }
        "Sunday"   { if ($Now.Hour -lt 18) { return $d.AddHours(18) } }
    }
    return $null
}
function Test-Window { return [bool](Get-WindowEnd) }

$T16Data  = Join-Path $env:APPDATA "MetaQuotes\Terminal\66FB7F5B174F9C3B2A690C49FF012FEB"
$Attach   = Join-Path $PSScriptRoot "t16_attach.ini"

# True when a saved chart of Terminal 16 has AurumFunded attached (chart files are UTF-16, written when it closes).
function Test-DemoEA {
    foreach ($f in Get-ChildItem (Join-Path $T16Data "MQL5\Profiles\Charts") -Recurse -Filter *.chr -ErrorAction SilentlyContinue) {
        $t = [System.IO.File]::ReadAllText($f.FullName)
        if ($t -match '(?ms)<expert>.*?^name=AurumFunded\s*$') { return $true }
    }
    return $false
}

# Terminal 16's own process; the other installs (live and other firms' accounts) are never matched.
function Get-T16 {
    Get-CimInstance Win32_Process -Filter "Name='terminal64.exe'" |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -ieq $T16Exe) }
}

# A hold keeps the keeper from restarting Terminal 16. Expired or unreadable holds are removed.
function Get-Hold {
    if (-not (Test-Path $HoldFile)) { return $null }
    try { $h = Get-Content $HoldFile -Raw | ConvertFrom-Json; $until = [datetime]$h.until } catch { $until = Get-Date 0 }
    if ($until -le (Get-Date)) { Remove-Item $HoldFile -Force; return $null }
    return $h
}

# True when the tester agent has something to do. The tester is a script (tools/autopilot/tester_step.py, started by
# the keeper and the relay): it starts and collects jobs on its own and only asks for the agent when it cannot go on
# (logs/autopilot/tester-help.json). The agent deletes the file when it has fixed it.
$TesterHelp = Join-Path $LogDir "tester-help.json"
$ToJudge    = Join-Path $LogDir "to-judge.json"
function Test-TesterWork { return (Test-Path $TesterHelp) }

# Jobs the tester script collected and nobody judged yet (to-judge.json entries: {id, match, at}).
function Get-ToJudge {
    if (-not (Test-Path $ToJudge)) { return @() }
    try {
        $j = Get-Content $ToJudge -Raw | ConvertFrom-Json
        return @($j | ForEach-Object { if ($_ -is [string]) { [pscustomobject]@{ id = $_; match = $false } } else { $_ } })
    } catch { return @() }
}

# The one idea queue (owner 2026-10-22): docs/ideas/queue.jsonl, one JSON line per idea. The finder adds items
# ("new"), the builder takes one ("testing") to the gates and a tester job ("tester"), the judge ends it ("hydra",
# "funded", "both" or "rejected"). Items with source "data" are the finder's (it fetches data), all others the builder's.
$IdeaQueue = Join-Path $Repo "docs\ideas\queue.jsonl"
function Get-QueueItems {
    if (-not (Test-Path $IdeaQueue)) { return @() }
    return @(Get-Content $IdeaQueue -Encoding UTF8 | Where-Object { $_.Trim() } | ForEach-Object {
        try { $_ | ConvertFrom-Json } catch { $null } } | Where-Object { $_ })
}
# Items waiting for the builder: "testing" (one it started) or "new", data items excepted.
function Get-QueueWaiting {
    return @(Get-QueueItems | Where-Object { ($_.status -eq "testing" -or $_.status -eq "new") -and $_.source -ne "data" }).Count
}
# Data items waiting for the finder.
function Get-DataWaiting {
    return @(Get-QueueItems | Where-Object { $_.status -eq "new" -and $_.source -eq "data" }).Count
}
# Finder runs the relay gave to each data item (logs\autopilot\data-tries.json). After $DataTryCap runs that leave an
# item "new", it loses its priority, so one stuck item cannot loop the finder (2026-10-22: 68 runs on data_ftmo_specs,
# whose file already existed). The doctor reports the stuck ones.
$DataTryCap = 3
$DataTries = Join-Path $LogDir "data-tries.json"
function Get-DataTries {
    $h = @{}
    if (Test-Path $DataTries) {
        try { (Get-Content $DataTries -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $h[$_.Name] = [int]$_.Value } } catch {}
    }
    return $h
}
# True while a data item's fetch script (fetch_runner.py, owner 2026-10-24) waits to start or runs: the finder is not
# started on it until the script has ended (state done or failed in logs\autopilot\fetch\<id>.json).
function Test-FetchPending($Item) {
    if (-not ($Item.PSObject.Properties.Name -contains "fetch") -or -not $Item.fetch) { return $false }
    $f = Join-Path $LogDir "fetch\$($Item.id).json"
    if (-not (Test-Path $f)) { return $true }
    $st = try { Get-Content $f -Raw | ConvertFrom-Json } catch { $null }
    if (-not $st) { return $true }
    if ($st.script -and (($st.script -replace '\\', '/') -ne ($Item.fetch -replace '\\', '/'))) { return $true }
    return ($st.state -eq "running")
}
# Waiting data items still under the cap.
function Get-DataDue {
    $t = Get-DataTries
    return @(Get-QueueItems | Where-Object { $_.status -eq "new" -and $_.source -eq "data" -and ([int]$t["$($_.id)"]) -lt $DataTryCap -and -not (Test-FetchPending $_) })
}
# Waiting data items at the cap.
function Get-DataStuck {
    $t = Get-DataTries
    return @(Get-QueueItems | Where-Object { $_.status -eq "new" -and $_.source -eq "data" -and ([int]$t["$($_.id)"]) -ge $DataTryCap })
}
# Count one finder run against each due data item.
function Add-DataTry {
    $t = Get-DataTries
    foreach ($i in Get-DataDue) { $t["$($i.id)"] = 1 + [int]$t["$($i.id)"] }
    [pscustomobject]$t | ConvertTo-Json | Set-Content $DataTries -Encoding UTF8
}

# Agent runs of a role started today (from its log) (the relay no longer caps runs; kept for reports).
function Get-RunsToday([string]$Role) {
    $f = Join-Path $LogDir "$(Get-Date -Format yyyy-MM-dd)_agent-$Role.log"
    if (-not (Test-Path $f)) { return 0 }
    return @(Select-String -Path $f -Pattern '^\S+ \S+  start: ').Count
}

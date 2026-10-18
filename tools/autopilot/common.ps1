# Shared paths and the tester window for the autopilot scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
#
# Terminal 16 (FTMO demo) runs the demo EA. The Strategy Tester runs in its own install, C:\MetaTrader 5 - Tester
# (same FTMO demo login, its own data folder), so tester jobs run at any hour and never close Terminal 16.

$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir   = Join-Path $Repo "logs\autopilot"
$HoldFile = Join-Path $LogDir "hold-terminal"
$Pause    = Join-Path $LogDir "PAUSE"
$Relay    = Join-Path $LogDir "relay.json"
$GapMinutes = 0     # relay: no gap inside a cycle (owner 2026-10-18); the break between cycles is relay.ps1's $CycleBreakMinutes
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

# True when the tester agent has something to do. Since 2026-10-18 the tester is a script (tools/autopilot/
# tester_step.py, started by the keeper and the relay): it starts and collects jobs on its own and only asks for the
# agent when it cannot go on (logs/autopilot/tester-help.json). The agent deletes the file when it has fixed it.
$TesterHelp = Join-Path $LogDir "tester-help.json"
$ToJudge    = Join-Path $LogDir "to-judge.json"
$ScanFlag   = Join-Path $LogDir "scanner-flag.json"
function Test-TesterWork { return (Test-Path $TesterHelp) }

# Jobs the tester script collected and nobody judged yet (to-judge.json entries: {id, match, at}).
function Get-ToJudge {
    if (-not (Test-Path $ToJudge)) { return @() }
    try {
        $j = Get-Content $ToJudge -Raw | ConvertFrom-Json
        return @($j | ForEach-Object { if ($_ -is [string]) { [pscustomobject]@{ id = $_; match = $false } } else { $_ } })
    } catch { return @() }
}

# True when the scanner agent has something to do: the scanner script (scanner_step.py) flags a survivor that passed
# every gate, or a scan it could not run. The agent deletes the flag file when done.
function Test-ScannerWork {
    if (-not (Test-Path $ScanFlag)) { return $false }
    try { return [bool](Get-Content $ScanFlag -Raw | ConvertFrom-Json).work } catch { return $true }
}

# Ideas in docs/ideas/ the orchestrator has not picked up yet. An idea counts as started when
# docs/autopilot/ideas_taken.txt lists its file and heading (the orchestrator appends one line per idea it picks,
# tests or drops) or, as a fallback, when its first title words appear in a candidates.json name. The researcher is
# skipped while 3 or more wait (owner 2026-10-18: effort goes where the work is).
$IdeasTaken = Join-Path $Repo "docs\autopilot\ideas_taken.txt"
function Get-UnstartedIdeas {
    $names = @()
    try {
        $names = @((Get-Content (Join-Path $Repo "docs\candidates.json") -Raw | ConvertFrom-Json).candidates |
            ForEach-Object { "$($_.name)".ToLower() })
    } catch { }
    $taken = @()
    if (Test-Path $IdeasTaken) { $taken = @(Get-Content $IdeasTaken -Encoding UTF8 | Where-Object { $_ -and -not $_.StartsWith("#") }) }
    $n = 0
    Get-ChildItem (Join-Path $Repo "docs\ideas") -Filter *.md -ErrorAction SilentlyContinue | ForEach-Object {
        $file = $_.Name
        foreach ($line in (Get-Content $_.FullName -Encoding UTF8)) {
            if ($line -match '^##\s+(\d+\..+)$') {
                $title = $Matches[1].Trim()
                if ($taken | Where-Object { $_ -match [regex]::Escape($file) -and $_.Contains(($title -split '\s+' | Select-Object -First 3) -join ' ') }) { continue }
                $words = ((($title -replace '[:\(\)].*$','') -split '[,\s]+') | Where-Object { $_.Length -gt 3 } | Select-Object -First 4) -join ' '
                if ($words -and ($names | Where-Object { $_.Contains($words) })) { continue }
                $n++
            }
        }
    }
    return $n
}

# Agent runs of a role started today (from its log) (the relay no longer caps runs; kept for reports).
function Get-RunsToday([string]$Role) {
    $f = Join-Path $LogDir "$(Get-Date -Format yyyy-MM-dd)_agent-$Role.log"
    if (-not (Test-Path $f)) { return 0 }
    return @(Select-String -Path $f -Pattern '^\S+ \S+  start: ').Count
}

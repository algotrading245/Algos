# Shared paths and the tester window for the autopilot scripts. Dot-source it: . "$PSScriptRoot\common.ps1"
#
# Terminal 16 (FTMO demo) runs the demo EA. The Strategy Tester runs in its own install, C:\MetaTrader 5 - Tester
# (same FTMO demo login, its own data folder), so tester jobs run at any hour and never close Terminal 16.

$Repo     = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$LogDir   = Join-Path $Repo "logs\autopilot"
$HoldFile = Join-Path $LogDir "hold-terminal"
$Pause    = Join-Path $LogDir "PAUSE"
$Relay    = Join-Path $LogDir "relay.json"
$GapMinutes = 15    # relay: minutes between one agent finishing and the agent it handed over to starting
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

# True when the tester agent has something to do: a queued job, or a running job whose tester process has ended.
# With no job left it removes an old autopilot hold on Terminal 16 (from before the tester had its own install).
function Test-TesterWork {
    $q = Get-Content (Join-Path $Repo "docs\autopilot\queue.json") -Raw | ConvertFrom-Json
    $work = @($q.jobs | Where-Object { $_.status -in @("queued", "running") })
    if (-not $work) {
        $h = Get-Hold
        if ($h -and $h.by -eq "autopilot") {
            Remove-Item $HoldFile -Force
            Write-Log "keeper" "hold released: no tester job left"
        }
        return $false
    }
    # A running job whose tester process is still alive needs no Claude run yet.
    $busy = @($work | Where-Object { $_.status -eq "running" } | Where-Object {
        $f = if ($_.folder_on) { $_.folder_on } else { $_.folder }
        $jf = if ($f) { Join-Path $Repo "$f\job.json" }
        $mf = if ($f) { Join-Path $Repo "$f\months.json" }
        if ($jf -and (Test-Path $jf)) {
            $j = Get-Content $jf -Raw | ConvertFrom-Json
            Get-Process -Id $j.Pid -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $j.Exe }
        } elseif ($mf -and (Test-Path $mf)) {
            # A run-months.ps1 job: busy while its month runner (a powershell process) is alive.
            $m = Get-Content $mf -Raw | ConvertFrom-Json
            Get-Process -Id $m.Pid -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq "powershell" }
        }
    })
    return (-not $busy)
}

# Agent runs of a role started today (from its log) (the relay no longer caps runs; kept for reports).
function Get-RunsToday([string]$Role) {
    $f = Join-Path $LogDir "$(Get-Date -Format yyyy-MM-dd)_agent-$Role.log"
    if (-not (Test-Path $f)) { return 0 }
    return @(Select-String -Path $f -Pattern '^\S+ \S+  start: ').Count
}

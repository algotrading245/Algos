# Aurum relay: the agents work as a team. Each agent ends its answer with "HANDOFF: <role> <reason>"; run-agent.ps1
# writes that to logs\autopilot\relay.json, and this script starts the named agent $GapMinutes (common.ps1) later.
# Started every 5 minutes by the "Aurum Relay" task; a tick that finds an agent busy, or nothing due, exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\relay.ps1 [-DryRun]     (-DryRun: say what would start)
#
# Order on each tick:
#   1. PAUSE, another agent running, or a usage/rate-limit back-off: nothing.
#   2. A tester job to start or collect: tester (it goes first, so the tester install is never idle).
#   3. A hand-over that is due: that agent.
#   4. No agent for $IdleMinutes: the researcher if it has not run for $ResearchHours hours, else the fidelity check if
#      it has not run for a week, else the orchestrator.
# No daily caps: usage is bounded by one agent at a time, the hand-over gap and the usage/rate-limit back-off.
param([switch]$DryRun)
. "$PSScriptRoot\common.ps1"

$IdleMinutes = 15      # owner 2026-10-18: start the next piece of work 15 min after the last one (was 120)
$ResearchHours = 4     # a new research run at most every 4 hours when nothing else is handed over (was 24)

function Start-Agent([string]$Role, [string]$Why) {
    if ($DryRun) { Write-Output "would start $Role ($Why)"; return }
    Write-Log "relay" "start $Role ($Why)"
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run-agent.ps1"), "-Role", $Role)
    if ($Role -eq "tester") { $a += "-IfWork" }
    & powershell.exe @a
}

if (Test-Path $Pause) { exit 0 }
$mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
if (-not $mutex.WaitOne(0)) { exit 0 }
$mutex.ReleaseMutex()

$r = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
$now = Get-Date
if ($r -and $r.backoff_until -and [datetime]$r.backoff_until -gt $now) { exit 0 }

# 2. Tester work in the weekend window.
if (Test-TesterWork) { Start-Agent "tester" "tester job to start or collect"; exit 0 }

# 3. A due hand-over. It is cleared before the agent starts, so it runs once.
if ($r -and $r.next -and $r.next -ne "none") {
    if ([datetime]$r.due -gt $now) { if ($DryRun) { Write-Output "waiting: $($r.next) due $($r.due)" }; exit 0 }
    $next = $r.next
    if (-not $DryRun) {
        $r.next = "none"
        $r | ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    }
    if ($next -eq "tester") {
        Write-Log "relay" "hand-over to tester from $($r.from) dropped: no tester work (window closed or no job)"
        exit 0
    }
    Start-Agent $next "hand-over from $($r.from): $($r.reason)"
    exit 0
}

# 4. Idle: nobody has run for $IdleMinutes.
$last = @(Get-ChildItem $LogDir -Filter "last-*.json" | ForEach-Object {
    try { [datetime](Get-Content $_.FullName -Raw | ConvertFrom-Json).ended } catch { }
})
$lastEnd = if ($last) { $last | Sort-Object | Select-Object -Last 1 } else { Get-Date 0 }
if (($now - $lastEnd).TotalMinutes -lt $IdleMinutes) { if ($DryRun) { Write-Output "last agent ended ${lastEnd}: not idle yet" }; exit 0 }

function Get-LastEnd([string]$Role) {
    $f = Join-Path $LogDir "last-$Role.json"
    if (Test-Path $f) { try { [datetime](Get-Content $f -Raw | ConvertFrom-Json).ended } catch { Get-Date 0 } } else { Get-Date 0 }
}
$researched = Get-LastEnd "researcher"
if (($now - $researched).TotalHours -ge $ResearchHours) {
    Start-Agent "researcher" "idle, no research for $ResearchHours hours"
} elseif (($now - (Get-LastEnd "fidelity")).TotalDays -ge 7) {
    Start-Agent "fidelity" "idle, no fidelity check for a week"
} else { Start-Agent "orchestrator" "idle for $IdleMinutes min" }

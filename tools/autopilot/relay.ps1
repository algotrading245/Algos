# Aurum relay: the agents work as a team. Each agent ends its answer with "HANDOFF: <role> <reason>"; run-agent.ps1
# writes that to logs\autopilot\relay.json, and this script starts the named agent $GapMinutes (common.ps1) later.
# Started every 5 minutes by the "Aurum Relay" task; a tick that finds an agent busy, or nothing due, exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\relay.ps1 [-DryRun]     (-DryRun: say what would start)
#
# The agents run as one chain, a cycle: researcher -> scanner -> orchestrator -> tester -> fidelity, then the next cycle
# starts with the researcher again (owner 2026-10-18). Each agent starts $GapMinutes after the one before it.
# Order on each tick:
#   1. PAUSE, another agent running, or a usage/rate-limit back-off: nothing.
#   2. A tester job to start or collect: tester (it goes first, so the tester install is never idle).
#   3. The next agent once its gap is over: the one named in the last HANDOFF line, else the next in the chain.
#      The tester is skipped when there is no tester work, the fidelity check unless it has not run for a week.
# No daily caps: usage is bounded by one agent at a time, the hand-over gap and the usage/rate-limit back-off.
param([switch]$DryRun)
. "$PSScriptRoot\common.ps1"

$Chain = @("researcher", "scanner", "orchestrator", "tester", "fidelity")   # one cycle; after the last, a new cycle

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

# 3. The next agent in the cycle. A HANDOFF line names it; without one the chain decides. Nothing runs before the gap is over.
function Get-LastEnd([string]$Role) {
    $f = Join-Path $LogDir "last-$Role.json"
    if (Test-Path $f) { try { [datetime](Get-Content $f -Raw | ConvertFrom-Json).ended } catch { Get-Date 0 } } else { Get-Date 0 }
}
function Test-Runnable([string]$Role) {
    switch ($Role) {
        "tester"   { return [bool](Test-TesterWork) }
        "fidelity" { return (($now - (Get-LastEnd "fidelity")).TotalDays -ge 7) }
        default    { return $true }
    }
}
if ($r -and $r.due -and [datetime]$r.due -gt $now) { if ($DryRun) { Write-Output "waiting: next agent due $($r.due)" }; exit 0 }
$next = if ($r -and $r.next -and $r.next -ne "none") { $r.next } else { $null }
$from = if ($r -and $r.from) { $r.from } else { $null }
if ($next -and -not (Test-Runnable $next)) {
    Write-Log "relay" "hand-over to $next from $from skipped: nothing for it to do"
    $from = $next; $next = $null
}
if (-not $next) {
    # The chain: the agent after the one that ran last, skipping those with nothing to do; past the end, a new cycle.
    $i = [array]::IndexOf($Chain, $from)
    do { $i++; if ($i -ge $Chain.Count) { $i = 0 } } until (Test-Runnable $Chain[$i])
    $next = $Chain[$i]
}
if (-not $DryRun) {
    # Written before the agent starts, so an agent that fails still moves the chain on.
    [ordered]@{ from = $next; next = "none"; due = $now.ToString("s"); reason = "started by the relay" } |
        ConvertTo-Json | Set-Content $Relay -Encoding UTF8
}
Start-Agent $next $(if ($from) { "cycle: after $from" } else { "cycle start" })

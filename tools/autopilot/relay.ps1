# Aurum relay: the agents work as a team. Each agent ends its answer with "HANDOFF: <role> <reason>"; run-agent.ps1
# writes that to logs\autopilot\relay.json, and this script starts the named agent $GapMinutes (common.ps1) later.
# Started every 5 minutes by the "Aurum Relay" task; a tick that finds an agent busy, or nothing due, exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\relay.ps1 [-DryRun]     (-DryRun: say what would start)
#
# The agents run as one chain, a cycle: researcher -> scanner -> orchestrator -> tester -> fidelity, then the next cycle
# starts with the researcher again (owner 2026-10-18). Inside a cycle the next agent starts the moment the last one ends
# (this script loops, no gap); between two cycles it waits $CycleBreakMinutes.
# Order on each tick:
#   1. PAUSE, another agent running, or a usage/rate-limit back-off: nothing.
#   2. A tester job to start or collect: tester (it goes first, so the tester install is never idle).
#   3. The next agent at once: the one named in the last HANDOFF line, else the next in the chain.
#      The tester is skipped when there is no tester work, the fidelity check unless it has not run for a week.
# No daily caps: usage is bounded by one agent at a time, the hand-over gap and the usage/rate-limit back-off.
param([switch]$DryRun)
. "$PSScriptRoot\common.ps1"

$CycleBreakMinutes = 30   # owner 2026-10-18: no gap inside a cycle, a break after it before the next cycle starts
$Chain = @("researcher", "scanner", "orchestrator", "tester", "fidelity")   # one cycle; after the last, a new cycle

function Start-Agent([string]$Role, [string]$Why) {
    if ($DryRun) { Write-Output "would start $Role ($Why)"; return }
    Write-Log "relay" "start $Role ($Why)"
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run-agent.ps1"), "-Role", $Role)
    if ($Role -eq "tester") { $a += "-IfWork" }
    & powershell.exe @a
}

# 3. The next agent in the cycle. A HANDOFF line names it; without one the chain decides. The next agent starts the moment the last ends.
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
while ($true) {
    if (Test-Path $Pause) { break }
    $mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
    if (-not $mutex.WaitOne(0)) { break }
    $mutex.ReleaseMutex()

    $r = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $now = Get-Date
    if ($r -and $r.backoff_until -and [datetime]$r.backoff_until -gt $now) { break }

    # 2. Tester work in the weekend window.
    if (Test-TesterWork) {
        Start-Agent "tester" "tester job to start or collect"
        # A collected job is handed to the orchestrator: carry on at once. A job still running: wait for the next tick.
        $r2 = try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null }
        if ($r2 -and $r2.from -eq "tester" -and $r2.next -eq "orchestrator") { continue }
        break
    }

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
    if ($next -eq "researcher") {
        # A new cycle: take the break first.
        $ends = @(Get-ChildItem $LogDir -Filter "last-*.json" | ForEach-Object {
            try { [datetime](Get-Content $_.FullName -Raw | ConvertFrom-Json).ended } catch { }
        })
        $lastEnd = if ($ends) { $ends | Sort-Object | Select-Object -Last 1 } else { Get-Date 0 }
        if (($now - $lastEnd).TotalMinutes -lt $CycleBreakMinutes) {
            if ($DryRun) { Write-Output "cycle break: next cycle starts $($lastEnd.AddMinutes($CycleBreakMinutes))" }
            break
        }
    }
    if (-not $DryRun) {
        # Written before the agent starts, so an agent that fails still moves the chain on.
        [ordered]@{ from = $next; next = "none"; due = $now.ToString("s"); reason = "started by the relay" } |
            ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    }
    Start-Agent $next $(if ($from) { "cycle: after $from" } else { "cycle start" })

    if ($DryRun) { break }
}

# Aurum relay: the agents work as a team. Each agent ends its answer with "HANDOFF: <role> <reason>"; run-agent.ps1
# writes that to logs\autopilot\relay.json, and this script starts the named agent on its next tick.
# Started every 5 minutes by the "Aurum Relay" task; a tick that finds an agent busy, or nothing due, exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\relay.ps1 [-DryRun]     (-DryRun: say what would start)
#
# The mechanical work is scripts, not agents (owner 2026-10-18): tester_step.py starts and collects tester jobs,
# scanner_step.py runs the scans; the keeper starts both every minute and each has its own lock, so MetaTrader runs
# never block the agents. This script runs tester_step.py on every tick as well, so a job that ends is collected at
# once. The tester and scanner agents only run when their script asked for help or a scan passed every gate.
#
# The agents run as one chain, a cycle: researcher -> miner -> scanner -> worker -> orchestrator -> tester -> fidelity, then the next
# cycle starts with the researcher again. Inside a cycle the next agent starts the moment the last one ends (this
# script loops, no gap); between two cycles it waits $CycleBreakMinutes, but only when no work role (miner, scanner,
# worker, tester) has work waiting (owner 2026-10-22: one piece of research ends, the next starts). A work role whose run did work (2+ minutes, no failure) may run again in the same tick.
# Token budget: budget.py status, once a tick. When the week's use passes skip_above (budget.json) the researcher and
# the orchestrator's follow-ups and daily heartbeat wait until the weekly reset.
# Order on each tick:
#   1. PAUSE or another agent running: nothing.
#   2. tester_step.py (always, AI or not). Then, when no AI provider can take a run (router.py available: every
#      provider backed off after a limit, without a key or not installed), code-only mode: code_judge.py confirms
#      the collected jobs whose fixed expect check matched and releases the jobs waiting on them, the keeper's
#      tester_step/scanner_step keep the tester and the scans going, and no agent starts until a provider is back.
#      Otherwise a tester-help.json: the tester agent. A collected job: the orchestrator judges it
#      (Sonnet when the script's fixed expect check matched, Opus when it did not).
#      A new demo order or ALERT (logs\autopilot\demo-event.json, written by dispatch.py, which the keeper starts
#      every minute and which wakes this script at once): the orchestrator, at the judge tier for an ALERT.
#   3. The next agent at once: the one named in the last HANDOFF line, else the next in the chain. Skipped when it
#      has nothing to do: the tester without a help file, the scanner without its flag, the fidelity check unless it
#      has not run for a week, the researcher (data only since 2026-10-22) without an open "## Data requests" item in
#      worker_queue.md, after 8 runs that day or over budget, the miner (papers and open-source
#      strategies) the same with 15 waiting specs as its limit, the worker with an empty backlog (Get-WorkerBacklog:
#      gated candidates to build, unstarted ideas, open worker_queue.md items), the orchestrator without work
#      (Get-OrchestratorWhy: a demo event, a flag, a job, a follow-up after a run that did work, or the daily heartbeat). A hand-over from another agent to
#      the orchestrator always runs.
# No daily caps but the researcher's and the miner's: usage is bounded by one agent at a time and the cycle break. A usage/rate limit backs off only the
# provider that hit it (run-agent.ps1 -> router.py backoff); the next provider in router.json's fallback order takes
# the runs, and with none left the relay runs code-only (step 2) until one is back.
# Which CLI and model a role runs on is the router's (tools/autopilot/router.json): switch the whole system between
# Claude and Qwen with python tools/autopilot/router.py use qwen|claude. This script only names a tier (routine,
# code, judge) when a run should be cheaper than its role's default.
param([switch]$DryRun)
. "$PSScriptRoot\common.ps1"

$CycleBreakMinutes = 30   # owner 2026-10-18: no gap inside a cycle, a break after it before the next cycle starts
$Chain = @("researcher", "miner", "scanner", "worker", "orchestrator", "tester", "fidelity")   # one cycle; after the last, a new cycle

function Start-Agent([string]$Role, [string]$Why, [string]$Tier = $null) {
    if ($DryRun) { Write-Output "would start $Role ($Why)$(if ($Tier) { " at the $Tier tier" })"; return }
    Write-Log "relay" "start $Role ($Why)$(if ($Tier) { " at the $Tier tier" })"
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run-agent.ps1"), "-Role", $Role)
    if ($Tier) { $a += @("-Tier", $Tier) }
    & powershell.exe @a
}

function Test-Runnable([string]$Role) {
    switch ($Role) {
        "tester"       { return (Test-TesterWork) }
        "scanner"      { return (Test-ScannerWork) }
        "fidelity"     { return (($now - (Get-LastEnd "fidelity")).TotalDays -ge 7) }
        "researcher"   {
            # Owner 2026-10-22: idea specs are the miner's; the researcher only fetches data, and runs while an open
            # item waits under "## Data requests" in worker_queue.md, at most 8 times a day, never over the budget.
            if ($overBudget) { return $false }
            $l = Get-Last "researcher"
            $today = if ($l -and $l.runs_day -eq $now.ToString("yyyy-MM-dd")) { [int]$l.runs_today } else { 0 }
            return (((Get-QueueOpen -Only @("Data requests")) -gt 0) -and ($today -lt 8))
        }
        "miner"        {
            # Owner 2026-10-21: papers and open-source strategies as rule specs, 80-100+ tested a day. Same gates as the
            # researcher with a deeper queue: while fewer than 15 specs wait, at most 8 runs a day, the empty streak.
            $l = Get-Last "miner"
            $streak = if ($l -and $l.empty_streak) { [int]$l.empty_streak } else { 0 }
            $today = if ($l -and $l.runs_day -eq $now.ToString("yyyy-MM-dd")) { [int]$l.runs_today } else { 0 }
            return (((Get-PendingSpecs) -lt 15) -and ($today -lt 8) -and
                    (($streak -lt 3) -or ((Get-LastEnd "miner").Date -lt $now.Date)))
        }
        "orchestrator" { return [bool](Get-OrchestratorWhy) }
        # Owner 2026-10-22: the Sonnet worker takes one backlog item end to end (prototype, gates, leg, compile,
        # tester job); it runs whenever an item waits (Get-WorkerBacklog in common.ps1).
        "worker"       { return ((Get-WorkerBacklog) -gt 0) }
        default       { return $true }
    }
}
# Why the orchestrator should run (owner 2026-10-21: no idle runs), or $null. Work first: a demo event it has not
# started since, a scanner flag or a job to judge, a new ideas file with unstarted ideas; then one follow-up after a run
# that did work (a run that ended "idle" gets none), and one heartbeat run a day.
function Get-OrchestratorWhy {
    $l = Get-Last "orchestrator"
    $end = Get-LastEnd "orchestrator"
    $ev = Get-DemoEvent
    if ($ev) { return "demo $($ev.kind)" }
    if (Test-ScannerWork) { return "scanner flag" }
    if (@(Get-ToJudge).Count) { return "jobs to judge" }
    # New ideas are the worker's since 2026-10-22 (Sonnet builds, Opus only judges and reviews).
    # Over the week's budget (budget.py status: skip) the Opus runs that are nice to have, the follow-up and the
    # heartbeat, wait; the orchestrator was about 97% of the spend in October.
    if ($overBudget) { return $null }
    if ($l -and ($l.idle -eq $false) -and ($l.failed -ne $true)) { return "follow-up: $($l.reason)" }
    if ($end.Date -lt $now.Date) { return "daily heartbeat" }
    return $null
}
function Get-Last([string]$Role) {
    $f = Join-Path $LogDir "last-$Role.json"
    if (Test-Path $f) { try { Get-Content $f -Raw | ConvertFrom-Json } catch { $null } } else { $null }
}
function Get-LastEnd([string]$Role) {
    $l = Get-Last $Role
    if ($l -and $l.ended) { try { [datetime]$l.ended } catch { Get-Date 0 } } else { Get-Date 0 }
}
# The demo order/ALERT dispatch.py saw last, when the orchestrator has not started since; else $null.
function Get-DemoEvent {
    $f = Join-Path $LogDir "demo-event.json"
    if (-not (Test-Path $f)) { return $null }
    $ev = try { Get-Content $f -Raw | ConvertFrom-Json } catch { $null }
    if (-not $ev -or -not $ev.at) { return $null }
    $l = Get-Last "orchestrator"
    $start = if ($l -and $l.started) { try { [datetime]$l.started } catch { Get-Date 0 } } else { Get-Date 0 }
    if (([datetime]$ev.at) -gt $start) { return $ev }
    return $null
}
# Roles this tick already started. Without it the chain can wrap round to a role that has just run and, if that run
# ends at once (a usage limit, a configuration fault), start it again and again inside one tick.
$startedHere = @()
# The week's token budget (budget.py, owner 2026-10-22), read once a tick. Over it ("skip"): no researcher and no
# orchestrator follow-up or heartbeat, and the cycle break stays.
$bst = try { (& python.exe (Join-Path $PSScriptRoot "budget.py") status 2>$null | Select-Object -Last 1) | ConvertFrom-Json } catch { $null }
$overBudget = [bool]($bst -and $bst.skip)
if ($DryRun -and $bst) { Write-Output "budget: `$$($bst.week_usd) of `$$($bst.weekly_usd) this week ($([math]::Round(100 * $bst.fraction))%), skip=$overBudget" }
# Roles that may run again in the same tick once a run of theirs did real work (owner 2026-10-22: when one piece of
# research ends, the next starts at once). Each costs a script or Haiku/Sonnet, never Opus.
$Repeatable = @("miner", "scanner", "worker", "tester")
while ($true) {
    if (Test-Path $Pause) { break }
    $mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
    if (-not $mutex.WaitOne(0)) { break }
    $mutex.ReleaseMutex()

    $r = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $now = Get-Date
    # 2. The tester script: collect a finished job, start the next queued one (fast when idle; its own lock).
    & python.exe (Join-Path $Repo "tools\autopilot\tester_step.py") 2>&1 | Out-Null

    # No AI provider can run (all limited, keyless or missing): code-only. The scripts keep the pipeline moving and
    # the agents resume on the first tick a provider is back. The log says so once on entering and once on leaving.
    $av = & python.exe (Join-Path $PSScriptRoot "router.py") available 2>$null | Select-Object -Last 1
    $avo = try { "$av" | ConvertFrom-Json } catch { $null }
    $codeOnlyFlag = Join-Path $LogDir "code-only.flag"
    if ($avo -and -not $avo.any) {
        $why = ($avo.providers.PSObject.Properties | ForEach-Object { "$($_.Name) $($_.Value)" }) -join "; "
        if ($DryRun) { Write-Output "code-only: no AI provider available ($why); would run code_judge.py"; break }
        if (-not (Test-Path $codeOnlyFlag)) {
            Write-Log "relay" "code-only mode: no AI provider available ($why)"
            Set-Content $codeOnlyFlag (Get-Date).ToString("s") -Encoding ASCII
        }
        & python.exe (Join-Path $PSScriptRoot "code_judge.py") 2>&1 | ForEach-Object { if ("$_".Trim()) { Write-Log "relay" "code_judge: $_" } }
        break
    }
    if (Test-Path $codeOnlyFlag) {
        Remove-Item $codeOnlyFlag -Force -ErrorAction SilentlyContinue
        Write-Log "relay" "code-only mode over: $($avo.first) is available, agents resume"
    }
    if (Test-TesterWork) {
        if ($startedHere -contains "tester") { break }
        $startedHere += "tester"
        Start-Agent "tester" "tester_step.py asked for help"
        break
    }
    $judge = @(Get-ToJudge)
    if ($judge.Count) {
        if ($startedHere -contains "orchestrator") { break }
        # A collected job is judged at once. The script compared result and expect with a fixed check: a match is
        # routine (the router's code tier confirms and records); anything else is judgment (its judge tier).
        $tier = if (@($judge | Where-Object { -not $_.match }).Count) { "judge" } else { "code" }
        $startedHere += "orchestrator"
        Start-Agent "orchestrator" ("judge " + (($judge | ForEach-Object { $_.id }) -join ", ")) $tier
        $r2 = try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null }
        if ($r2 -and $r2.from -eq "orchestrator" -and $r2.next -ne "none") { continue }
        break
    }
    # A new demo order or ALERT (dispatch.py wrote it within a minute): the orchestrator at once, no cycle break;
    # an ALERT at the judge tier.
    $ev = Get-DemoEvent
    if ($ev) {
        if ($startedHere -contains "orchestrator") { break }
        $tier = if ($ev.kind -eq "ALERT") { "judge" } else { $null }
        $startedHere += "orchestrator"
        Start-Agent "orchestrator" "demo $($ev.kind) at $($ev.at): $($ev.line)" $tier
        $r2 = try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null }
        if ($r2 -and $r2.from -eq "orchestrator" -and $r2.next -ne "none") { continue }
        break
    }

    # 3. The next agent in the cycle. A HANDOFF line names it; without one the chain decides.
    $next = if ($r -and $r.next -and $r.next -ne "none") { $r.next } else { $null }
    $from = if ($r -and $r.from) { $r.from } else { $null }
    # Another agent handing work to the orchestrator is reason enough; only the orchestrator's own follow-ups and the
    # chain go through its gate.
    $handed = ($next -eq "orchestrator") -and $from -and ($from -ne "orchestrator")
    if ($next -and -not $handed -and -not (Test-Runnable $next)) {
        Write-Log "relay" "hand-over to $next from $from skipped: nothing for it to do"
        $from = $next; $next = $null
    }
    $wrapped = $false
    if (-not $next) {
        # The chain: the agent after the one that ran last, skipping those with nothing to do and those this tick
        # already started; past the end, a new cycle.
        $i = [array]::IndexOf($Chain, $from)
        $guard = 0
        do {
            $i++; if ($i -ge $Chain.Count) { $i = 0; $wrapped = $true }; $guard++
        } until (((Test-Runnable $Chain[$i]) -and ($startedHere -notcontains $Chain[$i])) -or ($guard -gt $Chain.Count))
        if ($guard -gt $Chain.Count) { break }   # nobody in the chain has anything to do (or nothing left to start)
        $next = $Chain[$i]
    }
    if ($startedHere -contains $next) { Write-Log "relay" "$next already ran in this tick: waiting for the next one"; break }
    # Work waiting for a work role: the next cycle starts at once (owner 2026-10-22). Over budget too: the budget holds
    # back the costly runs (researcher, Opus follow-ups), not the cheap work roles.
    $waitingRoles = @($Repeatable | Where-Object { Test-Runnable $_ })
    $waiting = $waitingRoles.Count -gt 0
    if ($DryRun) { Write-Output "work waiting: $(if ($waiting) { $waitingRoles -join ', ' } else { 'none' })" }
    if (($next -eq "researcher" -or $wrapped) -and -not $waiting) {
        # A new cycle with nothing waiting: take the break first. Also when the chain wrapped past its end to a later
        # role, or the orchestrator would follow itself on every tick with no break.
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
    $startedHere += $next
    $t0 = Get-Date
    Start-Agent $next $(if ($from) { "cycle: after $from" } else { "cycle start" })

    if ($DryRun) { break }
    # A work role whose run lasted 2+ minutes and did not fail may run again in this tick; one that ended at once
    # (a limit, a fault) may not, so it cannot spin.
    $lr = Get-Last $next
    if (($Repeatable -contains $next) -and $lr -and ($lr.failed -ne $true) -and (((Get-Date) - $t0).TotalMinutes -ge 2)) {
        $startedHere = @($startedHere | Where-Object { $_ -ne $next })
    }
}

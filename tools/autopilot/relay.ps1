# Aurum relay: one simple loop (owner 2026-10-22). The finder queues ideas in docs/ideas/queue.jsonl (prebuilt
# strategies, papers, ML and DRL models), the builder builds and tests one at a time and queues its Strategy Tester
# job, the tester script (tester_step.py) runs it, and the judge judges the result and reviews the EA change. When one
# idea is done the next starts at once.
# Started every 5 minutes by the "Aurum Relay" task; a tick that finds an agent busy, or nothing due, exits at once.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\relay.ps1 [-DryRun]     (-DryRun: say what would start)
#
# Order on each pass (the script loops until nothing is due, one agent at a time):
#   1. PAUSE or another agent running: nothing.
#   2. tester_step.py (always). Then, when no AI provider can take a run (router.py available), code-only mode:
#      code_judge.py confirms collected jobs whose fixed expect check matched; no agent starts until a provider is back.
#   3. tester-help.json: the tester agent.
#   4. A collected job (to-judge.json): the judge (code tier when the script's expect check matched, else judge tier).
#   5. A new demo order or ALERT (demo-event.json, from dispatch.py): the judge, at the judge tier for an ALERT.
#   6. A hand-over naming the judge, builder or tester, when that role has work.
#   7. A data item waiting: the finder writes its fetch script (ideas that need it are blocked until then). The
#      script runs detached (fetch_runner.py step, every pass); the item is skipped while it runs, then the finder
#      closes it.
#   8. An idea waiting for the builder ("new" or "testing", data items excepted): the builder.
#   9. Otherwise the finder, when fewer than 2 ideas wait, to work its lead backlog or fetch data (no budget or
#      empty-run brake). The reason it is given says MODE: scout (fewer than 10 open leads) or MODE: normal.
# The weekly budget (budget.py) is shown in -DryRun only. A usage limit backs off only the provider that hit it
# (router.py backoff); which CLI and model a role runs on is router.json's.
param([switch]$DryRun)
. "$PSScriptRoot\common.ps1"

function Start-Agent([string]$Role, [string]$Why, [string]$Tier = $null) {
    if ($DryRun) { Write-Output "would start $Role ($Why)$(if ($Tier) { " at the $Tier tier" })"; return }
    Write-Log "relay" "start $Role ($Why)$(if ($Tier) { " at the $Tier tier" })"
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run-agent.ps1"), "-Role", $Role)
    if ($Tier) { $a += @("-Tier", $Tier) }
    if ($Why) { $a += @("-Why", ($Why -replace '"', "'")) }
    & powershell.exe @a
}
function Get-Last([string]$Role) {
    $f = Join-Path $LogDir "last-$Role.json"
    if (Test-Path $f) { try { Get-Content $f -Raw | ConvertFrom-Json } catch { $null } } else { $null }
}
function Get-LastEnd([string]$Role) {
    $l = Get-Last $Role
    if ($l -and $l.ended) { try { [datetime]$l.ended } catch { Get-Date 0 } } else { Get-Date 0 }
}
# The demo order/ALERT dispatch.py saw last, when the judge has not started since; else $null.
function Get-DemoEvent {
    $f = Join-Path $LogDir "demo-event.json"
    if (-not (Test-Path $f)) { return $null }
    $ev = try { Get-Content $f -Raw | ConvertFrom-Json } catch { $null }
    if (-not $ev -or -not $ev.at) { return $null }
    $l = Get-Last "judge"
    $start = if ($l -and $l.started) { try { [datetime]$l.started } catch { Get-Date 0 } } else { Get-Date 0 }
    if (([datetime]$ev.at) -gt $start) { return $ev }
    return $null
}
# Queue items at "tester" the judge has not reviewed yet (no "review" field).
function Get-Unreviewed {
    return @(Get-QueueItems | Where-Object { $_.status -eq "tester" -and -not ($_.PSObject.Properties.Name -contains "review") }).Count
}
# Why the finder should run, or $null.
function Get-FinderWhy {
    # Queue-low trigger (owner 2026-10-24, replaces "no brake" of 2026-10-22): the finder starts only when fewer than
    # 2 ideas wait for the builder. No budget or empty-run brake: the finder prompt keeps a lead backlog
    # (docs/ideas/backlog.jsonl) so a run is empty only when it refilled that backlog. Only a usage limit
    # (router.py backoff) or PAUSE stops it.
    if (@(Get-DataDue).Count -gt 0) { return "data item waiting" }
    $stuck = @(Get-DataStuck)
    if ($stuck.Count) { Write-Log "relay" "data item(s) stuck after $DataTryCap finder runs, priority dropped: $(($stuck | ForEach-Object { $_.id }) -join ', ')" }
    $waiting = Get-QueueWaiting
    if ($waiting -ge 2) { return $null }
    $bl = Join-Path $Repo "docs\ideas\backlog.jsonl"
    $open = if (Test-Path $bl) { @(Get-Content $bl -Encoding UTF8 | Where-Object { $_ -match '"status":\s*"open"' }).Count } else { 0 }
    # One job per run (owner 2026-10-24): a scout run only adds leads, a normal run only works them, so neither
    # hits the turn cap doing both. The finder prompt reads the mode from this line.
    $mode = if ($open -lt 10) { "MODE: scout" } else { "MODE: normal" }
    return "queue low ($waiting waiting): $open open lead(s), $mode"
}

# The week's token budget (budget.py, owner 2026-10-22), read once a tick.
$bst = try { (& python.exe (Join-Path $PSScriptRoot "budget.py") status 2>$null | Select-Object -Last 1) | ConvertFrom-Json } catch { $null }
$overBudget = [bool]($bst -and $bst.skip)
if ($DryRun -and $bst) { Write-Output "budget: `$$($bst.week_usd) of `$$($bst.weekly_usd) this week ($([math]::Round(100 * $bst.fraction))%), for information only" }

# Free pre-screen before a builder (owner 2026-10-24): queue items whose "screen" proxy fails a half are rejected with
# no agent run (tools/prescreen.py). Returns the ideas still waiting.
function Invoke-Prescreen {
    $a = @(Join-Path $Repo "tools\prescreen.py")
    if ($DryRun) { $a += "--dry-run" }
    & python.exe @a 2>$null | ForEach-Object { if ("$_".Trim()) { Write-Log "relay" "prescreen: $_" } }
    return (Get-QueueWaiting)
}

# A run that ended within 2 minutes (a limit, a fault) or failed is not started again in this tick, so nothing spins.
$blocked = @()
while ($true) {
    if (Test-Path $Pause) { break }
    $mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
    if (-not $mutex.WaitOne(0)) { break }
    $mutex.ReleaseMutex()

    $r = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $now = Get-Date
    # The tester script: collect a finished job, start the next queued one (fast when idle; its own lock).
    & python.exe (Join-Path $Repo "tools\autopilot\tester_step.py") 2>&1 | Out-Null
    # Long data fetches run as detached scripts, not inside an agent session (owner 2026-10-24).
    if (-not $DryRun) {
        & python.exe (Join-Path $PSScriptRoot "fetch_runner.py") step 2>&1 | ForEach-Object { if ("$_" -match '^fetch started') { Write-Log "relay" "$_" } }
    }

    # No AI provider can run (all limited, keyless or missing): code-only until one is back.
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

    # What has work, in order.
    $role = $null; $why = $null; $tier = $null
    $judge = @(Get-ToJudge)
    $ev = Get-DemoEvent
    $want = if ($r -and $r.next -and $r.next -ne "none") { "$($r.next)" } else { $null }
    if (Test-TesterWork) { $role = "tester"; $why = "tester_step.py asked for help" }
    elseif ($judge.Count) {
        $role = "judge"; $why = "judge " + (($judge | ForEach-Object { $_.id }) -join ", ")
        $tier = if (@($judge | Where-Object { -not $_.match }).Count) { "judge" } else { "code" }
    }
    elseif ($ev) { $role = "judge"; $why = "demo $($ev.kind) at $($ev.at): $($ev.line)"; if ($ev.kind -eq "ALERT") { $tier = "judge" } }
    elseif ($want -eq "judge" -and (Get-Unreviewed) -gt 0) { $role = "judge"; $why = "review: $($r.reason)" }
    # A data item first: an idea that needs the data cannot be built until the finder fetches it (2026-10-22, the
    # builder ran 43 times on paper_fx_value_rer while data_fred_cpi_g10 waited behind it).
    # At most $DataTryCap finder runs per data item (common.ps1), then the builder goes ahead and the doctor reports it.
    elseif (@(Get-DataDue).Count -gt 0) {
        $role = "finder"; $why = "data item waiting: fetch it before the builder ($((Get-DataDue | ForEach-Object { $_.id }) -join ', '))"
        if (-not $DryRun) { Add-DataTry }
    }
    elseif ((Get-QueueWaiting) -gt 0 -and (Invoke-Prescreen) -gt 0) { $role = "builder"; $why = "$(Get-QueueWaiting) idea(s) waiting" }
    else { $why = Get-FinderWhy; if ($why) { $role = "finder" } }

    if (-not $role) { if ($DryRun) { Write-Output "nothing due" }; break }
    if ($blocked -contains $role) { Write-Log "relay" "$role ended at once or failed in this tick: waiting for the next tick"; break }
    if (-not $DryRun) {
        # Written before the agent starts, so an agent that fails cannot leave a stale hand-over behind.
        [ordered]@{ from = $role; next = "none"; due = $now.ToString("s"); reason = "started by the relay" } |
            ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    }
    $t0 = Get-Date
    Start-Agent $role $why $tier
    if ($DryRun) { break }
    $lr = Get-Last $role
    if ((-not $lr) -or ($lr.failed -eq $true) -or (((Get-Date) - $t0).TotalMinutes -lt 2)) { $blocked += $role }
}

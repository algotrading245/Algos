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
#   7b. A leg came into or left docs/book.json: the portfolio manager (also weekly, Saturday task).
#   8. An idea waiting for the builder ("new" or "testing", data items excepted): the builder.
#   9. Otherwise the finder, when fewer than 2 ideas wait, to work its lead backlog or fetch data (no budget brake).
#      The reason it is given says MODE: scout (fewer than 10 open leads, once a day; or none open) or MODE: normal. A finder run under 2
#      minutes that queued nothing and closed no lead backs the finder off 30 minutes (finder-backoff.json); 3 empty
#      runs in a row back it off 24 hours (finder-empty.json), lifted early by a new steer.md.
# A role whose last 3 runs failed (fails_in_row in last-<role>.json) is paused 2 hours after the last, then tried once.
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
$FinderBackoff = Join-Path $LogDir "finder-backoff.json"
$FinderScoutDay = Join-Path $LogDir "finder-scout-day"              # date of the day's scout run
$FinderEmpty = Join-Path $LogDir "finder-empty.json"                # empty finder runs in a row
function Get-OpenLeads {
    $bl = Join-Path $Repo "docs\ideas\backlog.jsonl"
    if (Test-Path $bl) { @(Get-Content $bl -Encoding UTF8 | Where-Object { $_ -match '"status":\s*"open"' }).Count } else { 0 }
}
function Get-QueueLines {
    $q = Join-Path $Repo "docs\ideas\queue.jsonl"
    if (Test-Path $q) { @(Get-Content $q -Encoding UTF8 | Where-Object { "$_".Trim() }).Count } else { 0 }
}
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
    # Empty-run backoff (owner 2026-10-25): a finder run under 2 minutes that queued nothing and closed no lead
    # waits 30 minutes before the next one (it re-ran every 5 minutes). A data item due is not held back.
    $fb = if (Test-Path $FinderBackoff) { try { Get-Content $FinderBackoff -Raw | ConvertFrom-Json } catch { $null } }
    if ($fb -and $fb.until -and ([datetime]$fb.until) -gt (Get-Date)) {
        # A new steer.md lifts the 24-hour backoff (it names new targets); the 30-minute one just runs out.
        $steer = Join-Path $Repo "docs\ideas\steer.md"
        $lift = $fb.long -and (Test-Path $steer) -and ((Get-Item $steer).LastWriteTime -gt (Get-Item $FinderBackoff).LastWriteTime)
        if (-not $lift) {
            Write-Log "relay" "finder backed off until $($fb.until): $($fb.why)"
            return $null
        }
        Write-Log "relay" "finder backoff lifted: steer.md is newer"
        if (-not $DryRun) { Remove-Item $FinderBackoff -Force -ErrorAction SilentlyContinue }
    }
    $open = Get-OpenLeads
    # One job per run (owner 2026-10-24): a scout run only adds leads, a normal run only works them, so neither
    # hits the turn cap doing both. The finder prompt reads the mode from this line.
    # Scout at most once a day (owner 2026-10-25): the many shallow scout runs crowded out deep reads. After the day's
    # scout, a run works the leads that are open; it scouts again only when none is open.
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $scouted = (Test-Path $FinderScoutDay) -and ((Get-Content $FinderScoutDay -Raw).Trim() -eq $today)
    # With no open lead the daily limit still holds (owner 2026-10-26): 19 empty scouts ran in one day, each after the
    # 30-minute backoff. A new steer.md (written after the day's scout) lifts it, since it names new targets.
    if ($open -eq 0 -and $scouted) {
        $steer = Join-Path $Repo "docs\ideas\steer.md"
        $newSteer = (Test-Path $steer) -and (Test-Path $FinderScoutDay) -and ((Get-Item $steer).LastWriteTime -gt (Get-Item $FinderScoutDay).LastWriteTime)
        if (-not $newSteer) { Write-Log "relay" "finder idle: 0 open leads, today's scout done, no new steer"; return $null }
    }
    $mode = if ($open -eq 0 -or ($open -lt 10 -and -not $scouted)) { "MODE: scout" } else { "MODE: normal" }
    if ($mode -eq "MODE: scout" -and -not $DryRun) { Set-Content -Path $FinderScoutDay -Value $today -Encoding ascii }
    return "queue low ($waiting waiting): $open open lead(s), $mode"
}

# A book change (owner 2026-11-01): the legs in docs/book.json (book_sim.py) differ from those the last portfolio run
# saw. Returns the change as text, or $null. The first sight of the book only records it; one run per 12 hours at most.
$BookSeen = Join-Path $LogDir "book-legs.json"
function Get-BookChange {
    $bf = Join-Path $Repo "docs\book.json"
    if (-not (Test-Path $bf)) { return $null }
    $legs = try { @((Get-Content $bf -Raw -Encoding UTF8 | ConvertFrom-Json).legs.PSObject.Properties.Name | Sort-Object) } catch { @() }
    if (-not $legs.Count) { return $null }
    $seen = if (Test-Path $BookSeen) { try { @((Get-Content $BookSeen -Raw | ConvertFrom-Json).legs) } catch { $null } } else { $null }
    # The weekly run already saw this book (it ended after book.json was written): record it, no extra run.
    if ($null -eq $seen -or (Get-LastEnd "portfolio") -gt (Get-Item $bf).LastWriteTime) {
        if (-not $DryRun) { [ordered]@{ legs = $legs; at = (Get-Date).ToString("s") } | ConvertTo-Json | Set-Content $BookSeen -Encoding UTF8 }
        return $null
    }
    $added = @($legs | Where-Object { $seen -notcontains $_ }); $gone = @($seen | Where-Object { $legs -notcontains $_ })
    if (-not ($added.Count + $gone.Count)) { return $null }
    if (((Get-Date) - (Get-LastEnd "portfolio")).TotalHours -lt 12) { return $null }
    return "book changed: $(if ($added.Count) { "+$($added -join ', +')" }) $(if ($gone.Count) { "-$($gone -join ', -')" })".Trim()
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
$blockWhy = @{}
$FailPauseMin = 120
while ($true) {
    if (Test-Path $Pause) { Write-Log "relay" "paused (logs\autopilot\PAUSE exists; the keeper log says when it was set)"; break }
    $mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
    if (-not $mutex.WaitOne(0)) { break }
    $mutex.ReleaseMutex()

    $r = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $now = Get-Date
    # Roles the owner paused from the dashboard (desk/controls.py writes logs\autopilot\PAUSE-<role>, owner 2026-11-01):
    # each is skipped and the next role with work runs; a paused tester also skips tester_step.py.
    $off = @("finder", "builder", "tester", "judge" | Where-Object { Test-Path (Join-Path $LogDir "PAUSE-$_") })
    # The tester script: collect a finished job, start the next queued one (fast when idle; its own lock).
    if ($off -notcontains "tester") { & python.exe (Join-Path $Repo "tools\autopilot\tester_step.py") 2>&1 | Out-Null }
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
    $onJ = $off -notcontains "judge"
    if ($off -notcontains "tester" -and (Test-TesterWork)) { $role = "tester"; $why = "tester_step.py asked for help" }
    elseif ($onJ -and $judge.Count) {
        $role = "judge"; $why = "judge " + (($judge | ForEach-Object { $_.id }) -join ", ")
        $tier = if (@($judge | Where-Object { -not $_.match }).Count) { "judge" } else { "code" }
    }
    elseif ($onJ -and $ev) { $role = "judge"; $why = "demo $($ev.kind) at $($ev.at): $($ev.line)"; if ($ev.kind -eq "ALERT") { $tier = "judge" } }
    elseif ($onJ -and $want -eq "judge" -and (Get-Unreviewed) -gt 0) { $role = "judge"; $why = "review: $($r.reason)" }
    # A data item first: an idea that needs the data cannot be built until the finder fetches it (2026-10-22, the
    # builder ran 43 times on paper_fx_value_rer while data_fred_cpi_g10 waited behind it).
    # At most $DataTryCap finder runs per data item (common.ps1), then the builder goes ahead and the doctor reports it.
    elseif ($off -notcontains "finder" -and @(Get-DataDue).Count -gt 0) {
        $role = "finder"; $why = "data item waiting: fetch it before the builder ($((Get-DataDue | ForEach-Object { $_.id }) -join ', '))"
        if (-not $DryRun) { Add-DataTry }
    }
    # A leg came into or left the book: the portfolio manager rewrites steer.md now, not on Saturday.
    elseif ($bc = Get-BookChange) {
        $role = "portfolio"; $why = "$bc (between the weekly reviews)"
        if (-not $DryRun) {
            $legs = @((Get-Content (Join-Path $Repo "docs\book.json") -Raw -Encoding UTF8 | ConvertFrom-Json).legs.PSObject.Properties.Name | Sort-Object)
            [ordered]@{ legs = $legs; at = (Get-Date).ToString("s") } | ConvertTo-Json | Set-Content $BookSeen -Encoding UTF8
        }
    }
    elseif ($off -notcontains "builder" -and (Get-QueueWaiting) -gt 0 -and (Invoke-Prescreen) -gt 0) { $role = "builder"; $why = "$(Get-QueueWaiting) idea(s) waiting" }
    elseif ($off -notcontains "finder") { $why = Get-FinderWhy; if ($why) { $role = "finder" } }

    if (-not $role) {
        $msg = "nothing due" + $(if ($off.Count) { " (paused from the dashboard: $($off -join ', '))" } else { "" })
        if ($DryRun) { Write-Output $msg } elseif ($off.Count) { Write-Log "relay" $msg }
        break
    }
    if ($blocked -contains $role) { Write-Log "relay" "$role $($blockWhy[$role]) in this tick: waiting for the next tick"; break }
    # 3 failed runs in a row (fails_in_row, run-agent.ps1): the role waits $FailPauseMin minutes after the last one,
    # then gets one try; a further failure pauses it again. Catches a limit message the limit pattern does not know.
    $lr0 = Get-Last $role
    if ($lr0 -and [int]$lr0.fails_in_row -ge 3 -and $lr0.ended) {
        $until = ([datetime]$lr0.ended).AddMinutes($FailPauseMin)
        if ($now -lt $until) {
            $msg = "$role paused: $($lr0.fails_in_row) failed runs in a row, next try after $($until.ToString('s'))"
            if ($DryRun) { Write-Output $msg } else { Write-Log "relay" $msg }
            break
        }
    }
    if (-not $DryRun) {
        # Written before the agent starts, so an agent that fails cannot leave a stale hand-over behind.
        [ordered]@{ from = $role; next = "none"; due = $now.ToString("s"); reason = "started by the relay" } |
            ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    }
    $t0 = Get-Date
    $leads0 = Get-OpenLeads; $queue0 = Get-QueueLines
    Start-Agent $role $why $tier
    if ($DryRun) { break }
    $lr = Get-Last $role
    $short = ((Get-Date) - $t0).TotalMinutes -lt 2
    if ((-not $lr) -or ($lr.failed -eq $true) -or $short) {
        $blocked += $role
        # The reason comes from the run's own record (exit code, time limit), not from how fast it ended.
        $blockWhy[$role] = if (-not $lr) { "left no run record" }
                           elseif ($lr.failed -eq $true) { "failed ($(if ($lr.fail_why) { $lr.fail_why } else { "exit $($lr.exit)" }))" }
                           else { "ended after $([int]((Get-Date) - $t0).TotalSeconds) s with exit $($lr.exit)" }
    }
    if ($role -eq "finder") {
        # Empty = the run changed neither the queue nor the open leads (a scout that adds leads is not empty).
        # A data-item run (it writes a fetch script) is not counted.
        $empty = ($why -like "queue low*") -and ((Get-OpenLeads) -eq $leads0) -and ((Get-QueueLines) -le $queue0)
        $st = if (Test-Path $FinderEmpty) { try { Get-Content $FinderEmpty -Raw | ConvertFrom-Json } catch { $null } }
        $n = if ($empty) { 1 + $(if ($st -and $st.streak) { [int]$st.streak } else { 0 }) } else { 0 }
        # 3 empty runs in a row (owner 2026-11-01): 24 hours off, unless a new steer.md names new targets.
        if ($n -ge 3) {
            $fbWhy = "$n empty finder runs in a row ($leads0 open leads, queue unchanged)"
            [ordered]@{ until = (Get-Date).AddHours(24).ToString("s"); why = $fbWhy; long = $true } | ConvertTo-Json | Set-Content $FinderBackoff -Encoding UTF8
            Write-Log "relay" "finder backoff 24 h: $fbWhy"
            $n = 0
        }
        elseif ($empty -and $short) {
            $fbWhy = "run of $([int]((Get-Date) - $t0).TotalSeconds) s queued nothing and closed no lead ($leads0 open)"
            [ordered]@{ until = (Get-Date).AddMinutes(30).ToString("s"); why = $fbWhy } | ConvertTo-Json | Set-Content $FinderBackoff -Encoding UTF8
            Write-Log "relay" "finder backoff 30 min: $fbWhy"
        }
        [ordered]@{ streak = $n; at = (Get-Date).ToString("s") } | ConvertTo-Json | Set-Content $FinderEmpty -Encoding UTF8
    }
}

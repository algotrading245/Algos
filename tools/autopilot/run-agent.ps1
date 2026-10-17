# Runs one unattended Claude Code session for a pipeline role, started by the relay (relay.ps1) or the monitor task.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\run-agent.ps1 -Role monitor|tester|orchestrator|researcher|scanner|fidelity [-IfWork]
#
# - Skips when logs\autopilot\PAUSE exists (create that file to pause every agent; delete it to resume).
# - One Claude run at a time on this PC (named mutex); a run that finds another one busy waits up to 20 minutes.
# - -IfWork (tester role): starts Claude only when Test-TesterWork (common.ps1) finds a job to start or collect.
# - Afterwards the agent's last "HANDOFF: <role> <reason>" line goes to logs\autopilot\relay.json, so the relay
#   starts that agent $GapMinutes later.
# - Permissions come from tools\autopilot\settings.json in dontAsk mode: anything not listed there is refused,
#   nothing waits for a prompt. Each run is killed after its time limit.
# - Output: logs\autopilot\<date>_agent-<role>.log; the last run's outcome: logs\autopilot\last-<role>.json.
param(
    [Parameter(Mandatory = $true)][ValidateSet("monitor", "tester", "orchestrator", "researcher", "scanner", "fidelity")][string]$Role,
    [switch]$IfWork
)
. "$PSScriptRoot\common.ps1"
$log = "agent-$Role"

if (Test-Path $Pause) { Write-Log $log "skipped: paused (logs\autopilot\PAUSE exists)"; exit 0 }

# Model router, by the kind of work: routine on haiku (monitor, researcher, scanner, tester: run scripts, read,
# summarise), code on sonnet (fidelity; the orchestrator's quant-coder subagent), judgment on opus (the orchestrator
# and its reviewer subagent). Agent roles carry their model in .claude/agents/*.md. All runs use the same Claude Code
# login (no API key, no switch of auth); a run that hits a usage limit backs the relay off (below).
$cfg = @{
    monitor      = @{ Args = @("--agent", "monitor");    Turns = 25; Minutes = 20 }
    researcher   = @{ Args = @("--agent", "researcher"); Turns = 40; Minutes = 60 }
    scanner      = @{ Args = @("--agent", "scanner");    Turns = 25; Minutes = 30 }
    fidelity     = @{ Args = @("--agent", "fidelity");   Turns = 30; Minutes = 40 }
    tester       = @{ Args = @("--model", "haiku");      Turns = 40; Minutes = 45 }
    orchestrator = @{ Args = @("--model", "opus");       Turns = 80; Minutes = 120 }
}[$Role]

if ($IfWork -and -not (Test-TesterWork)) { exit 0 }

$mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
if (-not $mutex.WaitOne([TimeSpan]::FromMinutes(20))) { Write-Log $log "skipped: another agent run is still busy"; exit 0 }

try {
    $exe = Join-Path $env:APPDATA "npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
    if (-not (Test-Path $exe)) { $exe = (Get-Command claude.exe -ErrorAction Stop).Source }

    $status = & "$PSScriptRoot\terminal.ps1" -Status
    $prompt = @"
Unattended autopilot run, role: $Role. Now: $(Get-Date -Format "dddd yyyy-MM-dd HH:mm") local time (W. Europe).
Shell commands: run each one exactly as written and alone, with no ";", "&&", "|", "2>&1" or "echo" added. The
permission rules match whole commands, so a compound command is refused; the exit code is reported anyway.
Terminal 16 and tester window:
$($status -join "`n")

$(Get-Content (Join-Path $PSScriptRoot "prompts\$Role.md") -Raw)
"@
    $argv = @("-p", "--settings", (Join-Path $PSScriptRoot "settings.json"), "--permission-mode", "dontAsk",
        "--permission-prompts", "none", "--max-turns", $cfg.Turns, "--output-format", "stream-json", "--verbose", "--include-partial-messages") + $cfg.Args
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = ($argv | ForEach-Object { if ("$_" -match '\s') { '"' + $_ + '"' } else { "$_" } }) -join " "
    $psi.WorkingDirectory = $Repo
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    # Marks the run as an agent's: tools\run-tester.ps1 and tools\run-months.ps1 then refuse the holdout (tools/holdout.py).
    $psi.EnvironmentVariables["AURUM_AGENT"] = "1"

    $started = Get-Date
    Write-Log $log "start: $($cfg.Args -join ' '), at most $($cfg.Turns) turns / $($cfg.Minutes) min"
    $p = [System.Diagnostics.Process]::Start($psi)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($prompt)
    $p.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $p.StandardInput.Close()
    $err = $p.StandardError.ReadToEndAsync()
    # Every stream-json event is appended to logs/autopilot/events/<stamp>_<role>.jsonl as it arrives (the live
    # dashboard, tools\live_server.py, tails it); the closing "result" event is the old json output.
    $evDir = Join-Path $LogDir "events"; New-Item -ItemType Directory -Force $evDir | Out-Null
    $evFile = Join-Path $evDir ("{0}_{1}.jsonl" -f $started.ToString("yyyyMMdd-HHmmss"), $Role)
    $sw = New-Object System.IO.StreamWriter($evFile, $true, (New-Object System.Text.UTF8Encoding($false)))
    $sw.AutoFlush = $true
    $res = $null; $raw = New-Object System.Collections.Generic.List[string]; $timedOut = $false
    $deadline = $started.AddMinutes($cfg.Minutes)
    $lineTask = $p.StandardOutput.ReadLineAsync()
    while ($true) {
        if ($lineTask.Wait(250)) {
            $line = $lineTask.Result
            if ($null -eq $line) { break }
            $sw.WriteLine($line)
            if ($line.Contains('"type":"result"') -and $line.Contains('"duration_ms"')) {
                $r = try { $line | ConvertFrom-Json } catch { $null }
                if ($r -and $r.type -eq "result") { $res = $r }
            }
            elseif (-not $line.StartsWith('{')) { $raw.Add($line) }
            $lineTask = $p.StandardOutput.ReadLineAsync()
        } elseif ((Get-Date) -gt $deadline) {
            $timedOut = $true; & taskkill.exe /PID $p.Id /T /F | Out-Null; break
        }
    }
    $p.WaitForExit(30000) | Out-Null
    $sw.Close()
    $code = if ($timedOut) { -1 } else { $p.ExitCode }

    # The result event: the answer text plus the tool calls the permission rules refused (logged so a rule can be fixed).
    $text = if ($res -and $res.result) { "$($res.result)" } else { $raw -join "`n" }
    Write-Log $log ("output:`n" + $text.Trim() + $(if ($err.Result.Trim()) { "`nstderr:`n" + $err.Result.Trim() } else { "" }))
    foreach ($d in @($res.permission_denials | Where-Object { $_ })) {
        Write-Log $log "denied: $($d.tool_name) $($d.tool_input | ConvertTo-Json -Compress -Depth 3)"
    }
    Write-Log $log "end: exit $code$(if ($timedOut) { ', killed at the time limit' }), $([int]((Get-Date) - $started).TotalMinutes) min"
    @{ role = $Role; started = $started.ToString("s"); ended = (Get-Date).ToString("s"); exit = $code; timed_out = $timedOut } |
        ConvertTo-Json | Set-Content (Join-Path $LogDir "last-$Role.json") -Encoding UTF8

    # Hand-over for the relay (relay.ps1): the agent's last "HANDOFF: <role> <reason>" line names the next agent.
    $next = "none"; $reason = "no HANDOFF line"
    $m = [regex]::Matches($text,'(?m)^\W*HANDOFF:\W*(orchestrator|researcher|tester|scanner|fidelity|none)\b[ \t:-]*(.*)$')
    if ($m.Count) { $next = $m[$m.Count - 1].Groups[1].Value; $reason = $m[$m.Count - 1].Groups[2].Value.Trim(" `t`r*_:-".ToCharArray()) }
    $old = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $state = [ordered]@{ from = $Role; next = $next; due = (Get-Date).AddMinutes($GapMinutes).ToString("s"); reason = $reason }
    # A run that hands over nothing (the nightly monitor) keeps a hand-over that has not started yet.
    if ($next -eq "none" -and $old -and $old.next -ne "none") {
        $state.from = $old.from; $state.next = $old.next; $state.due = $old.due; $state.reason = $old.reason
    }
    # A usage or rate limit: nothing starts for an hour (the relay waits, it never works around a limit).
    if ("$text`n$($err.Result)" -match '(?i)usage limit|rate limit|hit your limit|limit reached|limit will reset') {
        $state.backoff_until = (Get-Date).AddMinutes(60).ToString("s")
        Write-Log $log "usage or rate limit in the output: relay waits until $($state.backoff_until)"
    }
    $state | ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    Write-Log $log "handoff: $($state.next) at $($state.due) ($($state.reason))"
} catch {
    Write-Log $log "error: $($_.Exception.Message)"
} finally {
    $mutex.ReleaseMutex()
}

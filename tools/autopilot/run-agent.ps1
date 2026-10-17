# Runs one unattended Claude Code session for a pipeline role, started by the "Aurum ..." scheduled tasks.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\run-agent.ps1 -Role monitor|tester|orchestrator|researcher [-IfWork]
#
# - Skips when logs\autopilot\PAUSE exists (create that file to pause every agent; delete it to resume).
# - One Claude run at a time on this PC (named mutex); a run that finds another one busy waits up to 20 minutes.
# - -IfWork (tester role): starts Claude only inside the weekend window and only when docs\autopilot\queue.json
#   has a queued or running job; with no job left it releases the autopilot's hold on Terminal 16 itself.
# - Permissions come from tools\autopilot\settings.json in dontAsk mode: anything not listed there is refused,
#   nothing waits for a prompt. Each run is killed after its time limit.
# - Output: logs\autopilot\<date>_agent-<role>.log; the last run's outcome: logs\autopilot\last-<role>.json.
param(
    [Parameter(Mandatory = $true)][ValidateSet("monitor", "tester", "orchestrator", "researcher")][string]$Role,
    [switch]$IfWork
)
. "$PSScriptRoot\common.ps1"
$log = "agent-$Role"

if (Test-Path $Pause) { Write-Log $log "skipped: paused (logs\autopilot\PAUSE exists)"; exit 0 }

# Model per role: the monitor and researcher agents carry their model (haiku) in .claude/agents/*.md.
$cfg = @{
    monitor      = @{ Args = @("--agent", "monitor");    Turns = 25; Minutes = 20 }
    researcher   = @{ Args = @("--agent", "researcher"); Turns = 40; Minutes = 60 }
    tester       = @{ Args = @("--model", "sonnet");     Turns = 40; Minutes = 45 }
    orchestrator = @{ Args = @("--model", "opus");       Turns = 80; Minutes = 120 }
}[$Role]

if ($IfWork) {
    if (-not (Test-Window)) { exit 0 }
    $q = Get-Content (Join-Path $Repo "docs\autopilot\queue.json") -Raw | ConvertFrom-Json
    $work = @($q.jobs | Where-Object { $_.status -in @("queued", "running") })
    if (-not $work) {
        $h = Get-Hold
        if ($h -and $h.by -eq "autopilot") {
            Remove-Item $HoldFile -Force
            Write-Log "keeper" "hold released: no tester job left"
        }
        exit 0
    }
    # A running job whose tester process is still alive needs no Claude run yet.
    $busy = @($work | Where-Object { $_.status -eq "running" } | Where-Object {
        $f = if ($_.folder_on) { $_.folder_on } else { $_.folder }
        $jf = if ($f) { Join-Path $Repo "$f\job.json" }
        if ($jf -and (Test-Path $jf)) {
            $j = Get-Content $jf -Raw | ConvertFrom-Json
            Get-Process -Id $j.Pid -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $j.Exe }
        }
    })
    if ($busy) { exit 0 }
}

$mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
if (-not $mutex.WaitOne([TimeSpan]::FromMinutes(20))) { Write-Log $log "skipped: another agent run is still busy"; exit 0 }

try {
    $exe = Join-Path $env:APPDATA "npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
    if (-not (Test-Path $exe)) { $exe = (Get-Command claude.exe -ErrorAction Stop).Source }

    $status = & "$PSScriptRoot\terminal.ps1" -Status
    $prompt = @"
Unattended autopilot run, role: $Role. Now: $(Get-Date -Format "dddd yyyy-MM-dd HH:mm") local time (W. Europe).
Terminal 16 and tester window:
$($status -join "`n")

$(Get-Content (Join-Path $PSScriptRoot "prompts\$Role.md") -Raw)
"@
    $argv = @("-p", "--settings", (Join-Path $PSScriptRoot "settings.json"), "--permission-mode", "dontAsk",
        "--permission-prompts", "none", "--max-turns", $cfg.Turns, "--output-format", "text") + $cfg.Args
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

    $started = Get-Date
    Write-Log $log "start: $($cfg.Args -join ' '), at most $($cfg.Turns) turns / $($cfg.Minutes) min"
    $p = [System.Diagnostics.Process]::Start($psi)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($prompt)
    $p.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $p.StandardInput.Close()
    $out = $p.StandardOutput.ReadToEndAsync()
    $err = $p.StandardError.ReadToEndAsync()
    $timedOut = -not $p.WaitForExit($cfg.Minutes * 60000)
    if ($timedOut) { & taskkill.exe /PID $p.Id /T /F | Out-Null; $p.WaitForExit(30000) | Out-Null }
    $code = if ($timedOut) { -1 } else { $p.ExitCode }

    Write-Log $log ("output:`n" + $out.Result.Trim() + $(if ($err.Result.Trim()) { "`nstderr:`n" + $err.Result.Trim() } else { "" }))
    Write-Log $log "end: exit $code$(if ($timedOut) { ', killed at the time limit' }), $([int]((Get-Date) - $started).TotalMinutes) min"
    @{ role = $Role; started = $started.ToString("s"); ended = (Get-Date).ToString("s"); exit = $code; timed_out = $timedOut } |
        ConvertTo-Json | Set-Content (Join-Path $LogDir "last-$Role.json") -Encoding UTF8
} catch {
    Write-Log $log "error: $($_.Exception.Message)"
} finally {
    $mutex.ReleaseMutex()
}

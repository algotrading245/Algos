# Runs one unattended agent session for a pipeline role, started by the relay (relay.ps1) or the monitor task.
#
#   powershell -ExecutionPolicy Bypass -File tools\autopilot\run-agent.ps1 -Role monitor|tester|orchestrator|researcher|scanner|fidelity [-Tier routine|code|judge] [-Model <name>] [-IfWork]
#
# - Which CLI and which model run the role comes from the router (tools/autopilot/router.json, read through
#   router.py): one switch picks the provider for every role (claude or qwen), each role maps to a tier, and each
#   provider names a model per tier. -Tier and -Model override one run; the relay passes -Tier code for a routine
#   judge run. Switch providers with: python tools/autopilot/router.py use qwen|claude.
# - Skips when logs\autopilot\PAUSE exists (create that file to pause every agent; delete it to resume).
# - One agent run at a time on this PC (named mutex); a run that finds another one busy waits up to 20 minutes.
# - -IfWork: starts a session only when Test-TesterWork (common.ps1) finds tester-agent work (tester-help.json).
# - Afterwards the agent's last "HANDOFF: <role> <reason>" line goes to logs\autopilot\relay.json, so the relay
#   starts that agent next.
# - Permissions: Claude gets tools\autopilot\settings.json in dontAsk mode (anything not listed there is refused);
#   Qwen gets the project's .qwen\settings.json deny list with --approval-mode yolo, so nothing waits for a prompt
#   either. Each run is killed after its time limit (Qwen also has its own --max-wall-time).
# - Output: logs\autopilot\<date>_agent-<role>.log; the last run's outcome (with its provider and model):
#   logs\autopilot\last-<role>.json.
param(
    [Parameter(Mandatory = $true)][ValidateSet("monitor", "tester", "orchestrator", "researcher", "scanner", "fidelity")][string]$Role,
    [ValidateSet("routine", "code", "judge")][string]$Tier,
    [string]$Model,
    [switch]$IfWork
)
. "$PSScriptRoot\common.ps1"
$log = "agent-$Role"

if (Test-Path $Pause) { Write-Log $log "skipped: paused (logs\autopilot\PAUSE exists)"; exit 0 }

# The router decides the provider, the model and the limits for this role; nothing about models is hardcoded here.
$ra = @((Join-Path $PSScriptRoot "router.py"), "resolve", "--role", $Role)
if ($Tier) { $ra += @("--tier", $Tier) }
if ($Model) { $ra += @("--model", $Model) }
$routerOut = & python.exe @ra 2>&1
$routeLine = $routerOut | Where-Object { "$_".TrimStart().StartsWith("{") } | Select-Object -Last 1
if (-not $routeLine) { Write-Log $log "skipped: the router gave no answer for $Role ($($routerOut | Select-Object -Last 1))"; exit 1 }
try { $route = "$routeLine" | ConvertFrom-Json } catch { Write-Log $log "skipped: cannot read the router's answer: $routeLine"; exit 1 }
$Turns = [int]$route.turns
$Minutes = [int]$route.minutes

if ($IfWork -and -not (Test-TesterWork)) { exit 0 }

# The router falls back to the other provider when the one it points at cannot authenticate (a Qwen run with no API
# key), so the pipeline never idles over a missing key. Say so in the log.
if ($route.fell_back) { Write-Log $log "router fallback: $($route.fell_back); this run goes to $($route.provider) $($route.model)" }

$mutex = New-Object System.Threading.Mutex($false, "Local\AurumAgent")
if (-not $mutex.WaitOne([TimeSpan]::FromMinutes(20))) { Write-Log $log "skipped: another agent run is still busy"; exit 0 }

# A role's agent definition (.claude/agents/*.md) without its frontmatter: Claude loads it through --agent, Qwen has
# no such flag, so its body goes into the prompt instead.
function Get-AgentBody([string]$RelPath) {
    if (-not $RelPath) { return $null }
    $p = Join-Path $Repo ($RelPath -replace '/', '\')
    if (-not (Test-Path $p)) { return $null }
    $t = Get-Content $p -Raw -Encoding UTF8
    if ($t -match '(?s)^\uFEFF?---\s*\r?\n.*?\r?\n---\s*\r?\n(.*)$') { return $Matches[1].Trim() }
    return $t.Trim()
}

try {
    # What runs: Claude's own exe, or node on Qwen Code's entry script (its .cmd wrapper would swallow stdin).
    if ($route.provider -eq "qwen") {
        $exe = (Get-Command node.exe -ErrorAction Stop).Source
        $entry = Join-Path $env:APPDATA "npm\node_modules\@qwen-code\qwen-code\cli-entry.js"
        if (-not (Test-Path $entry)) { throw "Qwen Code is not installed at $entry (npm install -g @qwen-code/qwen-code)" }
    } else {
        $exe = Join-Path $env:APPDATA "npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
        if (-not (Test-Path $exe)) { $exe = (Get-Command claude.exe -ErrorAction Stop).Source }
    }

    $status = & "$PSScriptRoot\terminal.ps1" -Status
    # Shared memory (docs/memory): the mission, the lessons and the latest decisions go into every run.
    $mem = Join-Path $Repo "docs\memory"
    $memText = foreach ($f in "mission.md", "lessons.md") {
        $mp = Join-Path $mem $f
        if (Test-Path $mp) { Get-Content $mp -Raw -Encoding UTF8 }
    }
    $decFile = Join-Path $mem "decisions.jsonl"
    $recent = if (Test-Path $decFile) { (Get-Content $decFile -Encoding UTF8 | Select-Object -Last 15) -join "`n" } else { "(none yet)" }

    $agentBody = if ($route.agent_file) { Get-AgentBody $route.agent_file } else { $null }
    $agentSection = if ($agentBody) { @"

--- Your role definition ($($route.agent_file)) ---
$agentBody
--- End of the role definition ---
"@ } else { "" }

    # What differs between the two CLIs, said once. It sits after the fixed prompt parts so a repeat run still hits
    # the provider's prompt cache for everything above it.
    $providerSection = if ($route.provider -eq "qwen") { @"

--- This run's tools (Qwen Code, model $($route.model)) ---
These instructions were written for Claude Code; the same work has different tool names here. Read a file with
read_file, write one with write_file, change part of one with edit, search contents with grep_search, find files with
glob, fetch a page with web_fetch, search the web with web_search, and run every command with run_shell_command.
Where an instruction says "the Bash tool", use run_shell_command with the same single command. One command per call,
with no ";", "&&", "|" or redirect: the project's deny list (.qwen/settings.json) refuses what it lists whatever the
approval mode, and a compound command cannot be matched against it. Subagents: the quant-coder and the reviewer
definitions are mirrored into .qwen/agents/, so delegate with the agent tool (subagent_type "quant-coder" or
"reviewer") exactly where the instructions name them, and use list_agents if you need to check what is there. Never
print an API key, an account number or any credential.
"@ } else { @"

--- This run's tools (Claude Code, model $($route.model)) ---
Run every command with the Bash tool, one command per call, in exactly the form the instructions give.
"@ }

    # Prompt order (owner 2026-10-18): the fixed parts (memory, role prompt, memory instructions) come first so a
    # repeat run within 5 minutes hits the prompt cache and is billed cheaply; what changes every run (date, terminal
    # status, the latest decisions) comes last.
    $prompt = @"
Unattended autopilot run, role: $Role.
$agentSection
--- Shared memory (docs/memory; mission.md is the owner's and cannot be edited) ---
$($memText -join "`n")
--- End of memory ---

$(Get-Content (Join-Path $PSScriptRoot "prompts\$Role.md") -Raw)

Using the memory: before a decision, look at what was decided or learned before with
python tools/memory.py search <words> (add --events to search the commands earlier agents ran). Log each decision
you make (a job judged, an idea taken up or dropped, a setting kept, a plan changed) once, with
python tools/memory.py decide --role $Role --decision "<what>" --why "<why>" --evidence "<file, job or commit>".
Something the project learned that should change how we work: the same command with --kind lesson, for the
orchestrator to review. A disagreement with the mission: --kind question. Commit docs/memory/decisions.jsonl
together with your other files. Never write an account number, login or key into it.

Provisional hand-over: near the start of the run (after your first reads), write what you expect to hand over to
with python tools/autopilot/handoff.py --next <role> --reason "<what you plan to do>" --provisional, and run it
again without --provisional if your plan changes. It keeps the chain moving if this run is cut off; your final
HANDOFF line still ends the run.
$providerSection
--- Current status (this changes every run; everything above is fixed) ---
Now: $(Get-Date -Format "dddd yyyy-MM-dd HH:mm") local time (W. Europe).
Shell commands: run each one exactly as written and alone, with no ";", "&&", "|", "2>&1" or "echo" added. The
permission rules match whole commands, so a compound command is refused; the exit code is reported anyway.
Terminal 16 (demo EA; the tester has its own install):
$($status -join "`n")
Latest decisions (docs/memory/decisions.jsonl, newest last):
$recent
"@

    if ($route.provider -eq "qwen") {
        $argv = @($entry, "-m", $route.model, "-o", "stream-json", "--include-partial-messages",
            "--max-session-turns", $Turns, "--max-wall-time", "${Minutes}m", "--approval-mode", "yolo") +
            @($route.args)
    } else {
        $argv = @("-p", "--settings", (Join-Path $PSScriptRoot "settings.json"), "--permission-mode", "dontAsk",
            "--permission-prompts", "none", "--max-turns", $Turns, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages")
        if ($route.agent) { $argv += @("--agent", $route.agent) } else { $argv += @("--model", $route.model) }
    }

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
    if ($route.provider -eq "qwen") {
        # Qwen prints a sandbox warning on every yolo run; the project's deny list is the gate here, not a sandbox.
        $psi.EnvironmentVariables["QWEN_CODE_SUPPRESS_YOLO_WARNING"] = "1"
    }

    $started = Get-Date
    Write-Log $log "start: $($route.provider) $($route.model) (tier $($route.tier)), at most $Turns turns / $Minutes min"
    $p = [System.Diagnostics.Process]::Start($psi)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($prompt)
    $p.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $p.StandardInput.Close()
    $err = $p.StandardError.ReadToEndAsync()
    # Every stream-json event is appended to logs/autopilot/events/<stamp>_<role>.jsonl as it arrives (the live
    # dashboard, tools\live_server.py, tails it). Both providers write there; the shapes differ, the file does not.
    $evDir = Join-Path $LogDir "events"; New-Item -ItemType Directory -Force $evDir | Out-Null
    $evFile = Join-Path $evDir ("{0}_{1}.jsonl" -f $started.ToString("yyyyMMdd-HHmmss"), $Role)
    $sw = New-Object System.IO.StreamWriter($evFile, $true, (New-Object System.Text.UTF8Encoding($false)))
    $sw.AutoFlush = $true

    # The answer text, from either CLI's event shape: a "result" string wins (Claude's closing event); otherwise the
    # assistant's text pieces are joined, so the final HANDOFF line is still found.
    $resultText = $null
    $isError = $null
    $subtype = $null
    $assistant = New-Object System.Collections.Generic.List[string]
    $denials = New-Object System.Collections.Generic.List[string]
    $raw = New-Object System.Collections.Generic.List[string]
    $timedOut = $false
    $deadline = $started.AddMinutes($Minutes + 2)   # Qwen's own --max-wall-time fires first and exits by itself
    $lineTask = $p.StandardOutput.ReadLineAsync()
    while ($true) {
        if ($lineTask.Wait(250)) {
            $line = $lineTask.Result
            if ($null -eq $line) { break }
            $sw.WriteLine($line)
            if (-not $line.StartsWith("{")) { $raw.Add($line) }
            elseif ($line -match '"(result|text|content|permission_denials|is_error)"') {
                $o = try { $line | ConvertFrom-Json } catch { $null }
                if ($o) {
                    if ($o.PSObject.Properties["result"] -and $o.result -is [string] -and $o.result.Trim()) { $resultText = $o.result }
                    if ($o.PSObject.Properties["is_error"]) { $isError = [bool]$o.is_error; $subtype = "$($o.subtype)" }
                    foreach ($holder in @($o, $o.message)) {
                        if ($holder -and $holder.PSObject.Properties["content"]) {
                            foreach ($piece in @($holder.content)) {
                                if ($piece -and $piece.PSObject.Properties["text"] -and $piece.text -is [string]) { $assistant.Add($piece.text) }
                            }
                        }
                    }
                    if ($o.PSObject.Properties["text"] -and $o.text -is [string] -and $o.text.Trim()) { $assistant.Add($o.text) }
                    foreach ($d in @($o.permission_denials | Where-Object { $_ })) {
                        $denials.Add("$($d.tool_name) $($d.tool_input | ConvertTo-Json -Compress -Depth 3)")
                    }
                }
            }
            $lineTask = $p.StandardOutput.ReadLineAsync()
        } elseif ((Get-Date) -gt $deadline) {
            $timedOut = $true; & taskkill.exe /PID $p.Id /T /F | Out-Null; break
        }
    }
    $p.WaitForExit(30000) | Out-Null
    $sw.Close()
    # The outcome comes from the result event, not the process exit code: Qwen Code on Windows aborts with a libuv
    # assertion (0xC0000409) after writing it, because the run needs stdin closed and libuv then trips over the
    # handle. Everything we need is already in $resultText / $assistant by then.
    $rawExit = $p.ExitCode
    $code = if ($timedOut) { -1 } elseif ($null -ne $isError) { if ($isError) { 1 } else { 0 } } else { $rawExit }

    $text = if ($resultText) { $resultText } elseif ($assistant.Count) { $assistant -join "`n" } else { $raw -join "`n" }
    Write-Log $log ("output:`n" + $text.Trim() + $(if ($err.Result.Trim()) { "`nstderr:`n" + $err.Result.Trim() } else { "" }))
    foreach ($d in $denials) { Write-Log $log "denied: $d" }
    $endNote = "end: exit $code"
    if ($null -ne $isError) { $endNote += " (subtype $subtype, is_error $isError)" }
    if ($timedOut) { $endNote += ", killed at the time limit" }
    if ($rawExit -ne $code) { $endNote += ", process exit $rawExit ignored" }
    $endNote += ", $([int]((Get-Date) - $started).TotalMinutes) min"
    Write-Log $log $endNote
    @{ role = $Role; provider = $route.provider; model = $route.model; tier = $route.tier
       started = $started.ToString("s"); ended = (Get-Date).ToString("s"); exit = $code; timed_out = $timedOut } |
        ConvertTo-Json | Set-Content (Join-Path $LogDir "last-$Role.json") -Encoding UTF8

    # Hand-over for the relay (relay.ps1): the agent's last "HANDOFF: <role> <reason>" line names the next agent.
    $next = "none"; $reason = "no HANDOFF line"
    $m = [regex]::Matches($text,'(?m)^\W*HANDOFF:\W*(orchestrator|researcher|tester|scanner|fidelity|none)\b[ \t:-]*(.*)$')
    if ($m.Count) { $next = $m[$m.Count - 1].Groups[1].Value; $reason = $m[$m.Count - 1].Groups[2].Value.Trim(" `t`r*_:-".ToCharArray()) }
    $old = if (Test-Path $Relay) { try { Get-Content $Relay -Raw | ConvertFrom-Json } catch { $null } }
    $state = [ordered]@{ from = $Role; next = $next; due = (Get-Date).AddMinutes($GapMinutes).ToString("s"); reason = $reason }
    # A run without a HANDOFF line (the nightly monitor, a cut-off run) keeps a hand-over that has not started yet,
    # e.g. its own provisional one; an explicit "HANDOFF: none" ends the cycle.
    if ($m.Count -eq 0 -and $old -and $old.next -ne "none") {
        $state.from = $old.from; $state.next = $old.next; $state.due = $old.due; $state.reason = $old.reason
    }
    # A usage, session, quota or auth limit: nothing starts for an hour (the relay waits, it never works around it).
    # Both CLIs word these differently; "session limit" is Claude's weekly/session cap, the rest are Qwen's API side.
    if ("$text`n$($err.Result)" -match '(?i)usage limit|rate limit|session limit|hit your limit|limit reached|limit will reset|quota|insufficient balance|invalid api key|incorrect api key|arrearage|access denied') {
        $state.backoff_until = (Get-Date).AddMinutes(60).ToString("s")
        Write-Log $log "usage, session, quota or auth limit in the output: relay waits until $($state.backoff_until)"
    }
    $state | ConvertTo-Json | Set-Content $Relay -Encoding UTF8
    Write-Log $log "handoff: $($state.next) at $($state.due) ($($state.reason))"
} catch {
    Write-Log $log "error: $($_.Exception.Message)"
} finally {
    $mutex.ReleaseMutex()
}

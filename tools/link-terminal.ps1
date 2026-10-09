# Links this repo's MQL5 sources into an MT5 terminal's data folder with directory
# junctions, so MetaEditor compiles the files in place and nothing is copied.
# Default target: Terminal 14 (Vantage cent account). No admin rights needed.
#
#   powershell -ExecutionPolicy Bypass -File tools\link-terminal.ps1
#   powershell -ExecutionPolicy Bypass -File tools\link-terminal.ps1 -DataFolder <path>
param(
    [string]$DataFolder = "$env:APPDATA\MetaQuotes\Terminal\C0E230B8F9C8C2A16D1EE5E91A38A7CF",
    [string]$Project = "AurumLadder"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

foreach ($kind in "Experts", "Include", "Scripts") {
    $src = Join-Path $repo "mql5\$kind\$Project"
    $dst = Join-Path $DataFolder "MQL5\$kind\$Project"
    if (-not (Test-Path $src)) { continue }
    if (Test-Path $dst) {
        $item = Get-Item $dst -Force
        if ($item.LinkType -eq "Junction") { Write-Host "ok      $dst"; continue }
        throw "$dst exists and is not a junction; move it away first."
    }
    New-Item -ItemType Junction -Path $dst -Target $src | Out-Null
    Write-Host "linked  $dst -> $src"
}

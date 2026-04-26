param(
    [string]$Prompt = "Click cell 13, type hello in the message field, then press Send.",
    [switch]$KeepOpen,
    [switch]$Maximize
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$App = Join-Path $PSScriptRoot "app.py"
$ArgString = "`"$App`""
if ($KeepOpen) {
    $ArgString += " --keep-open"
}
if ($Maximize) {
    $ArgString += " --maximize"
}
$ArgString += " --prompt `"$Prompt`""

Start-Process -FilePath $Python -ArgumentList $ArgString -WorkingDirectory $RepoRoot -WindowStyle Normal

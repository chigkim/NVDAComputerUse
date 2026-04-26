param(
    [string]$Prompt,
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$App = Join-Path $PSScriptRoot "app.py"

$Args = @($App)
if ($SelfTest) {
    $Args += "--self-test"
}
if ($Prompt) {
    $Args += "--prompt"
    $Args += $Prompt
}

& $Python @Args

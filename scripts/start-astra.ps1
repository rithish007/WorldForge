[CmdletBinding()]
param(
    [switch]$Check,
    [ValidateNotNullOrEmpty()]
    [string]$Model,
    [ValidateSet('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')]
    [string]$ReasoningEffort
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$promptPath = Join-Path $repositoryRoot 'docs\ASTRA_BUILD.md'
$codexCommand = Get-Command codex -CommandType Application -ErrorAction Stop | Select-Object -First 1

foreach ($requiredFile in @('Plan.md', 'AGENTS.md', 'PROJECT.md', 'docs\ASTRA_BUILD.md', '.codex\config.toml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot $requiredFile) -PathType Leaf)) {
        throw "Missing build setup file: $requiredFile"
    }
}

$codexArguments = @('--cd', $repositoryRoot)
if ($Model) {
    $codexArguments += @('--model', $Model)
}
if ($ReasoningEffort) {
    $codexArguments += @('--config', ('model_reasoning_effort="{0}"' -f $ReasoningEffort))
}

if ($Check) {
    [pscustomobject]@{
        Model = $(if ($Model) { $Model } else { 'Inherited from Codex settings' })
        Reasoning = $(if ($ReasoningEffort) { $ReasoningEffort } else { 'Inherited from Codex settings' })
        Arguments = $codexArguments
        Repository = $repositoryRoot
        Prompt = $promptPath
        Codex = $codexCommand.Source
        BuildStarted = $false
    }
    return
}

$buildPrompt = Get-Content -LiteralPath $promptPath -Raw -Encoding UTF8
& $codexCommand.Source @codexArguments $buildPrompt
if ($LASTEXITCODE -ne 0) {
    throw "Codex exited with status $LASTEXITCODE."
}

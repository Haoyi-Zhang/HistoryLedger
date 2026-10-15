param(
    [Parameter(Mandatory=$true)][string]$ArtifactRoot,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$PythonExecutable,
    [string]$ResourceWrapper = '',
    [Parameter(Mandatory=$true)][switch]$Run
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not $Run) { throw 'Pass -Run to start the fixed measurement schedule.' }
$artifact = (Resolve-Path -LiteralPath $ArtifactRoot).ProviderPath
$python = (Get-Item -LiteralPath $PythonExecutable -ErrorAction Stop).FullName
$output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
$bundled = Join-Path $PSScriptRoot 'run-with-resources.ps1'
$wrapper = if ($ResourceWrapper) { (Resolve-Path -LiteralPath $ResourceWrapper).ProviderPath } else { $bundled }
$bundledText = [System.IO.File]::ReadAllText($bundled).Replace("`r`n", "`n").TrimEnd([char[]]"`r`n") + "`n"
$wrapperText = [System.IO.File]::ReadAllText($wrapper).Replace("`r`n", "`n").TrimEnd([char[]]"`r`n") + "`n"
if ($wrapperText -cne $bundledText) { throw 'Supplied resource wrapper differs from bundled four-slot implementation.' }
$previous = [Environment]::GetEnvironmentVariable('P022_COST_RESOURCE_ENTRY', 'Process')
try {
    # The marker restricts accidental direct entry. The wrapper itself acquires
    # four slots before starting the coordinator; the marker is not a lease.
    $env:P022_COST_RESOURCE_ENTRY = 'four-slot-wrapper-v1'
    & $wrapper -Mode measurement -Executable $python -Arguments @(
        '-I', '-B', (Join-Path $PSScriptRoot 'measure.py'), '--campaign',
        '--artifact-root', $artifact, '--output-dir', $output, '--resource-wrapper', $wrapper
    )
    $code = $LASTEXITCODE
}
finally {
    [Environment]::SetEnvironmentVariable('P022_COST_RESOURCE_ENTRY', $previous, 'Process')
}
exit $code

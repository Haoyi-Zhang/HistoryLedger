param(
    [Parameter(Mandatory=$true)][ValidateSet('compile','measurement')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$Executable,
    [string[]]$Arguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [System.IO.Path]::IsPathFullyQualified($Executable) -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw 'Executable must be an existing absolute path to a reviewed runtime.'
}
$pool = [System.Threading.Semaphore]::new(4,4,'Local\HistoryLedgerCostResourcePool')
$gate = [System.Threading.Mutex]::new($false,'Local\HistoryLedgerCostResourceGate')
$gateHeld = $false
$held = 0
$code = 1
try {
    try { $gateHeld = $gate.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $gateHeld = $true }
    if (-not $gateHeld) { $code = 75; Write-Output 'RESOURCE_BUSY'; }
    else {
        $needed = if ($Mode -eq 'measurement') { 4 } else { 1 }
        for ($i=0; $i -lt $needed; $i++) {
            if (-not $pool.WaitOne(0)) { break }
            $held++
        }
        $gate.ReleaseMutex()
        $gateHeld = $false
        if ($held -ne $needed) { $code = 75; Write-Output 'RESOURCE_BUSY' }
        else {
            $global:LASTEXITCODE = 0
            & $Executable @Arguments
            $code = $LASTEXITCODE
        }
    }
}
finally {
    if ($gateHeld) { $gate.ReleaseMutex() }
    if ($held -gt 0) { [void]$pool.Release($held) }
    $gate.Dispose()
    $pool.Dispose()
}
exit $code

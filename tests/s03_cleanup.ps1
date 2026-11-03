#requires -Version 7.4
# No inference, services, jobs or elevation used.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../scripts/Filesystem.ps1')
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('dispatcher-cleanup-' + [guid]::NewGuid().ToString('N'))
$root = Join-Path $fixture 'S03'
$session = Join-Path $root ('session-' + [guid]::NewGuid().ToString('N'))
$other = Join-Path $fixture 'other'
New-Item -ItemType Directory -Path $session, $other -Force | Out-Null
Set-Content -LiteralPath (Join-Path $session 'clients.json') -Value '{}'
Set-Content -LiteralPath (Join-Path $other 'keep.txt') -Value 'important'

try {
    $script:attempts = 0
    function Remove-Item {
        [CmdletBinding()]
        param([string]$LiteralPath, [switch]$Recurse, [switch]$Force)
        $script:attempts++
        if ($script:attempts -eq 1) { throw [IO.IOException]::new('scanner lock') }
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $LiteralPath -Recurse:$Recurse -Force:$Force -ErrorAction Stop
    }
    Assert-True (Remove-DispatcherSmokeSession -Path $session -Root $root -RetryDelaysMs @(0, 0)) 'Retry failed'
    Assert-True ($script:attempts -eq 2) 'Expected two removal attempts'
    Assert-True (Remove-DispatcherSmokeSession -Path $session -Root $root -RetryDelaysMs @(0)) 'Not idempotent'

    New-Item -ItemType Directory -Path $session -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $session 'clients.json') -Value '{}'
    function Remove-Item {
        [CmdletBinding()]
        param([string]$LiteralPath, [switch]$Recurse, [switch]$Force)
        throw [IO.IOException]::new('permanent lock')
    }
    Assert-True (-not (Remove-DispatcherSmokeSession -Path $session -Root $root -RetryDelaysMs @(0, 0))) 'Persistent lock not reported'
    Assert-True (Test-Path -LiteralPath (Join-Path $session 'clients.json')) 'Locked data removed'
    $refused = $false
    try { Remove-DispatcherSmokeSession -Path $other -Root $root -RetryDelaysMs @(0) | Out-Null }
    catch { $refused = $true }
    Assert-True $refused 'Foreign path not refused'

    Microsoft.PowerShell.Management\Remove-Item -LiteralPath Function:\Remove-Item -Force
    $nested = Join-Path $session 'linked'
    $hasLink = $false
    try {
        New-Item -ItemType Junction -Path $nested -Target $other -ErrorAction Stop | Out-Null
        $hasLink = $true
    }
    catch { Write-Host 'Junction unavailable: link fixture skipped.' }
    if ($hasLink) {
        $refused = $false
        try { Remove-DispatcherSmokeSession -Path $session -Root $root -RetryDelaysMs @(0) | Out-Null }
        catch { $refused = $true }
        Assert-True $refused 'Nested junction not refused'
        Assert-True (Test-Path -LiteralPath (Join-Path $other 'keep.txt')) 'Foreign target touched'
    }

    $stale = Join-Path $root ('session-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path (Join-Path $stale 'nested/empty') -Force | Out-Null
    (Get-Item -LiteralPath $stale).LastWriteTimeUtc = [datetime]::UtcNow.AddMinutes(-10)
    Clear-EmptyDispatcherSmokeSessions -Root $root
    Assert-True (-not (Test-Path -LiteralPath $stale)) 'Fileless old session not removed'
    Assert-True (Test-Path -LiteralPath (Join-Path $other 'keep.txt')) 'Foreign file modified'
    Write-Host 'S03 Windows cleanup tests passed.'
}
finally {
    Microsoft.PowerShell.Management\Remove-Item -LiteralPath Function:\Remove-Item -Force -ErrorAction SilentlyContinue
    Microsoft.PowerShell.Management\Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue
}

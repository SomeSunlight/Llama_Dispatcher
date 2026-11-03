#requires -Version 7.4
# Shared cleanup for tool-owned, disposable S03 smoke sessions only.
# Never use this for Strata, Caddy, installed models, or running Dispatcher data.

function Assert-DispatcherSmokeSession {
    param([Parameter(Mandatory)][string]$Path,
          [Parameter(Mandatory)][string]$Root)
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $name = [IO.Path]::GetFileName($candidate)
    $parent = [IO.Path]::GetDirectoryName($candidate)
    if (-not [string]::Equals($parent, $rootPath, [StringComparison]::OrdinalIgnoreCase) -or
        $name -cnotmatch '^session-[0-9a-f]{32}$') {
        throw [InvalidOperationException]::new("Not an owned S03 session: $candidate")
    }
    return $candidate
}

function Get-DispatcherSmokeDirectories {
    param([Parameter(Mandatory)][string]$Path)
    $stack = [Collections.Generic.Stack[string]]::new()
    $folders = [Collections.Generic.List[string]]::new()
    $stack.Push($Path)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            -not $item.PSIsContainer) {
            throw [InvalidOperationException]::new("Unsafe S03 session directory: $current")
        }
        $folders.Add($current)
        foreach ($child in Get-ChildItem -LiteralPath $current -Force -ErrorAction Stop) {
            if (($child.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw [InvalidOperationException]::new(
                    "Refusing linked/reparse S03 session entry: $($child.FullName)")
            }
            if ($child.PSIsContainer) { $stack.Push($child.FullName) }
        }
    }
    return $folders.ToArray()
}

function Remove-DispatcherSmokeSession {
    param([Parameter(Mandatory)][string]$Path,
          [Parameter(Mandatory)][string]$Root,
          [int[]]$RetryDelaysMs = @(0, 50, 150, 350))
    $candidate = Assert-DispatcherSmokeSession -Path $Path -Root $Root
    foreach ($delay in $RetryDelaysMs) {
        if ($delay -gt 0) { Start-Sleep -Milliseconds $delay }
        if (-not (Test-Path -LiteralPath $candidate)) { return $true }
        try {
            # Refuse nested junctions; retry transient enumeration locks too.
            Get-DispatcherSmokeDirectories -Path $candidate | Out-Null
            Remove-Item -LiteralPath $candidate -Recurse -Force -ErrorAction Stop
            return $true
        }
        catch {
            if ($_.Exception -is [InvalidOperationException]) { throw }
            if (-not (Test-Path -LiteralPath $candidate)) { return $true }
        }
    }
    return -not (Test-Path -LiteralPath $candidate)
}

function Clear-EmptyDispatcherSmokeSessions {
    param([Parameter(Mandatory)][string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return }
    foreach ($entry in Get-ChildItem -LiteralPath $Root -Directory -Force) {
        if ($entry.Name -cnotmatch '^session-[0-9a-f]{32}$' -or
            $entry.LastWriteTimeUtc -gt [datetime]::UtcNow.AddMinutes(-5)) {
            continue  # Never interfere with another newly started smoke run.
        }
        try {
            $folders = @(Get-DispatcherSmokeDirectories -Path $entry.FullName)
            $hasFiles = $false
            foreach ($folder in $folders) {
                if (@(Get-ChildItem -LiteralPath $folder -File -Force).Count -gt 0) {
                    $hasFiles = $true
                    break
                }
            }
            if ($hasFiles) { continue } # Only truly fileless leftovers.
            if (-not (Remove-DispatcherSmokeSession -Path $entry.FullName -Root $Root)) {
                Write-Warning "Fileless S03 session is still locked: $($entry.FullName)"
            }
        }
        catch {
            Write-Warning "S03 cleanup skipped unsafe/unreadable session $($entry.FullName): $($_.Exception.Message)"
        }
    }
}

#Requires -Version 7.4
# Select the operator-provisioned S02 digest registry for S03 attached Strata.
# The per-client tokens are never printed, rewritten or copied here.
# Standalone pure-file helper: no native services, network or processes touched.
function Select-S03ClientRegistry {
    [CmdletBinding()]
    param(
        [string]$ExternalPath,
        [Parameter(Mandatory)][string]$LegacyOutputPath,
        [Parameter(Mandatory)][string]$LegacyKey
    )
    $ErrorActionPreference = 'Stop'

    if (-not [string]::IsNullOrWhiteSpace($ExternalPath)) {
        if (-not [IO.Path]::IsPathFullyQualified($ExternalPath)) {
            throw 'S03 external client registry must be an absolute path.'
        }
        if (-not (Test-Path -LiteralPath $ExternalPath -PathType Leaf)) {
            throw 'S03 external S02 client registry missing. No fallback to shared identity.'
        }
        $item = Get-Item -LiteralPath $ExternalPath -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Refusing a linked S02 client registry.'
        }
        try {
            $doc = Get-Content -LiteralPath $ExternalPath -Raw |
                ConvertFrom-Json -AsHashtable -ErrorAction Stop
        }
        catch {
            throw 'S03 external S02 registry contains invalid JSON.'
        }
        if (-not ($doc -is [System.Collections.IDictionary]) -or
            $doc.schema_version -ne 1 -or
            $doc.Keys.Count -ne 2 -or
            -not $doc.ContainsKey('clients') -or
            -not ($doc.clients -is [array]) -or
            $doc.clients.Count -lt 1) {
            throw 'S03 external S02 registry has unexpected schema or no clients.'
        }
        $ids = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        $digests = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($client in $doc.clients) {
            if (-not ($client -is [System.Collections.IDictionary]) -or
                $client.Keys.Count -ne 3 -or
                $client.id -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$' -or
                $client.token_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
                $client.policy -cnotin @('passthrough', 'default', 'enforce') -or
                -not $ids.Add([string]$client.id) -or
                -not $digests.Add([string]$client.token_sha256)) {
                throw 'S03 external S02 registry contains invalid, duplicate or non-digest client data.'
            }
        }
        Write-Host "[S03] Using pre-provisioned S02 registry ($($doc.clients.Count) identities)."
        Write-Host '[S03] External S02 registry is left byte-for-byte unchanged.'
        return (Resolve-Path -LiteralPath $ExternalPath).Path
    }

    # Backwards-compatible migration-only behavior for older standalone
    # invocations; the new AIW configuration must provide ExternalPath.
    $digest = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($LegacyKey))
    ).ToLowerInvariant()
    $body = @{
        schema_version = 1
        clients = @(@{
            id = 'home-gateway'
            token_sha256 = $digest
            policy = 'passthrough'
        })
    } | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText(
        $LegacyOutputPath, ($body + [Environment]::NewLine),
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host '[S03] Legacy shared home-gateway identity (no per-app attribution).'
    return $LegacyOutputPath
}

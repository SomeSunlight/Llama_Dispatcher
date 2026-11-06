#Requires -Version 7.4
# Read a machine-private alias role file and attach every public alias to
# the ONE already-running model discovered through Strata /v1/models.
# No native model process is started here; no credentials or paths in the file.
function Get-S03RoleAliases {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$RoleFile,
        [Parameter(Mandatory)][string]$NativeModel
    )
    if (-not [IO.Path]::IsPathFullyQualified($RoleFile) -or
        -not (Test-Path -LiteralPath $RoleFile -PathType Leaf)) {
        throw 'An explicit absolute, existing role alias JSON path is required.'
    }
    $item = Get-Item -LiteralPath $RoleFile -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'Refusing a linked S03 role alias file.'
    }
    try {
        $doc = Get-Content -LiteralPath $RoleFile -Raw -ErrorAction Stop |
            ConvertFrom-Json -AsHashtable -ErrorAction Stop
    }
    catch {
        throw 'Unable to parse private S03 role alias JSON.'
    }
    if (-not ($doc -is [System.Collections.IDictionary]) -or
        $doc.Keys.Count -ne 2 -or
        $doc.schema_version -ne 1 -or
        -not ($doc.aliases -is [System.Collections.IDictionary]) -or
        $doc.aliases.Count -lt 1 -or $doc.aliases.Count -gt 32) {
        throw 'S03 role file requires schema_version=1 and 1..32 named aliases.'
    }
    $allowed = @(
        'temperature', 'top_p', 'top_k', 'min_p',
        'repeat_penalty', 'presence_penalty', 'frequency_penalty',
        'max_tokens', 'max_completion_tokens', 'seed',
        'reasoning_effort', 'reasoning_budget_tokens', 'chat_template_kwargs'
    )
    $aliases = @{}
    foreach ($name in $doc.aliases.Keys) {
        if ($name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$') {
            throw 'Invalid public model alias in S03 role file.'
        }
        $item = $doc.aliases[$name]
        if (-not ($item -is [System.Collections.IDictionary]) -or
            $item.Keys.Count -ne 1 -or
            -not ($item.parameters -is [System.Collections.IDictionary])) {
            throw 'Every role alias requires only a parameters object.'
        }
        foreach ($key in $item.parameters.Keys) {
            if ($key -cnotin $allowed) {
                throw 'Unsupported S03 role parameter; no attach file generated.'
            }
        }
        if ($item.parameters.ContainsKey('reasoning_effort') -and
            $item.parameters.reasoning_effort -cnotin @('none', 'low', 'medium', 'high', 'xhigh')) {
            throw 'Unrecognized role reasoning effort.'
        }
        if ($item.parameters.ContainsKey('reasoning_effort') -and
            $item.parameters.ContainsKey('chat_template_kwargs') -and
            $item.parameters.chat_template_kwargs -is [System.Collections.IDictionary] -and
            $item.parameters.chat_template_kwargs.ContainsKey('enable_thinking')) {
            throw 'Ambiguous role thinking: set only reasoning_effort or enable_thinking.'
        }
        $aliases[[string]$name] = @{
            model = $NativeModel
            parameters = $item.parameters
        }
    }
    return $aliases
}

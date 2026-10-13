# Build-owned cleanup is confined to ordinary directories beneath project/dist.
# This helper performs validation only; it never deletes or creates a directory.
function Assert-AkihaBuildDirectory {
    param([string]$ProjectRoot, [string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -match '[*?]' -or
        $Path -match '^\\\\' -or $Path -match '^[A-Za-z]:[^\\/]') {
        throw 'Build path is empty, ambiguous, a device/UNC path, or contains wildcards.'
    }
    foreach ($part in ($Path -split '[\\/]')) {
        if ($part -in @('.', '..') -or ($part -and $part -match '[ .]$')) {
            throw 'Build paths must not contain dot segments or ambiguous trailing characters.'
        }
    }
    $root = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
    $dist = [System.IO.Path]::GetFullPath((Join-Path $root 'dist')).TrimEnd('\', '/')
    $candidate = if ([System.IO.Path]::IsPathRooted($Path)) {
        [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    } else {
        [System.IO.Path]::GetFullPath((Join-Path $root $Path)).TrimEnd('\', '/')
    }
    if (-not $candidate.StartsWith($dist + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build directories must be strict descendants of project/dist.'
    }
    # Inspect every existing ancestor, including dist and the project directory.
    $ancestor = $candidate
    while ($ancestor) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force -ErrorAction Stop
            if (-not $item.PSIsContainer -or
                ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                throw 'Build directory or ancestor is a file or reparse point.'
            }
        }
        $ancestor = [System.IO.Path]::GetDirectoryName($ancestor)
    }
    return $candidate
}

function Assert-AkihaBuildPaths {
    param([string]$ProjectRoot, [string]$OutputDir, [string]$WorkDir)
    $output = Assert-AkihaBuildDirectory -ProjectRoot $ProjectRoot -Path $OutputDir
    $work = Assert-AkihaBuildDirectory -ProjectRoot $ProjectRoot -Path $WorkDir
    if ($output.Equals($work, [System.StringComparison]::OrdinalIgnoreCase) -or
        $output.StartsWith($work + '\', [System.StringComparison]::OrdinalIgnoreCase) -or
        $work.StartsWith($output + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Output and work directories must not overlap.'
    }
    return [pscustomobject]@{ OutputDir = $output; WorkDir = $work }
}

function Assert-AkihaCleanupTree {
    param([string]$ProjectRoot, [string]$Path)
    $checked = Assert-AkihaBuildDirectory -ProjectRoot $ProjectRoot -Path $Path
    if (-not (Test-Path -LiteralPath $checked)) { return }
    # Enumerate one level at a time, rejecting links before descending into them.
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($checked)
    while ($pending.Count) {
        foreach ($item in (Get-ChildItem -LiteralPath $pending.Pop() -Force -ErrorAction Stop)) {
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw 'Cleanup tree contains a reparse point; clean build refused.'
            }
            if ($item.PSIsContainer) { $pending.Push($item.FullName) }
        }
    }
}

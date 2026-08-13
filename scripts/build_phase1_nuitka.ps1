param(
    [string]$OutputDir = "dist\nuitka",
    [switch]$FastBuild,
    [switch]$CleanRelease,
    [switch]$SkipQualityChecks,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_akiha_nuitka.ps1" `
    -OutputDir $OutputDir `
    -FastBuild:$FastBuild `
    -CleanRelease:$CleanRelease `
    -SkipQualityChecks:$SkipQualityChecks `
    -SkipBuild:$SkipBuild

param(
    [string]$OutputDir = "dist\nuitka",
    [switch]$SkipQualityChecks,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

& "$PSScriptRoot\build_akiha_nuitka.ps1" `
    -OutputDir $OutputDir `
    -SkipQualityChecks:$SkipQualityChecks `
    -SkipBuild:$SkipBuild

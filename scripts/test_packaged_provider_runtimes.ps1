param(
    [string]$ExePath = "dist\nuitka-development\main.dist\Akiha.exe",
    [string]$ReportPath = "dist\nuitka-development\build-reports\provider-runtime-smoke.json",
    [switch]$SkipGeminiNetwork
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ResolvedExe = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $ExePath))
$ResolvedReport = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $ReportPath))

if (-not (Test-Path -LiteralPath $ResolvedExe -PathType Leaf)) {
    throw "Packaged executable is missing: $ResolvedExe"
}

$ReportDirectory = Split-Path -Parent $ResolvedReport
New-Item -ItemType Directory -Path $ReportDirectory -Force | Out-Null
if (Test-Path -LiteralPath $ResolvedReport) {
    Remove-Item -LiteralPath $ResolvedReport -Force
}

$Arguments = @("--provider-runtime-smoke-report=$ResolvedReport")
if ($SkipGeminiNetwork) {
    $Arguments += "--skip-gemini-network"
}

$Process = Start-Process `
    -FilePath $ResolvedExe `
    -ArgumentList $Arguments `
    -WindowStyle Hidden `
    -Wait `
    -PassThru

if (-not (Test-Path -LiteralPath $ResolvedReport -PathType Leaf)) {
    throw "Akiha did not write the provider runtime smoke report."
}

$Report = Get-Content -LiteralPath $ResolvedReport -Raw | ConvertFrom-Json
$Report.checks | Format-Table name, status, detail -AutoSize
if ($Process.ExitCode -ne 0 -or -not $Report.passed) {
    throw "Packaged provider runtime smoke failed. See $ResolvedReport"
}

Write-Host "Packaged provider runtime smoke passed: $ResolvedReport"

param(
    [string]$ExePath = "dist\nuitka-development\main.dist\Akiha.exe",
    [string]$ReportPath = "dist\nuitka-development\build-reports\provider-runtime-smoke.json",
    [int]$TimeoutSeconds = 240,
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

$StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
$StartInfo.FileName = $ResolvedExe
$StartInfo.WorkingDirectory = Split-Path -Parent $ResolvedExe
$StartInfo.UseShellExecute = $false
$StartInfo.CreateNoWindow = $true
$StartInfo.Arguments = '"--provider-runtime-smoke-report={0}"' -f $ResolvedReport
if ($SkipGeminiNetwork) {
    $StartInfo.Arguments += " --skip-gemini-network"
}

$Process = [System.Diagnostics.Process]::new()
$Process.StartInfo = $StartInfo
if (-not $Process.Start()) {
    throw "Packaged provider runtime smoke process did not start."
}
if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
    $Process.Kill($true)
    $Process.WaitForExit()
    throw "Packaged provider runtime smoke exceeded $TimeoutSeconds seconds."
}

if (-not (Test-Path -LiteralPath $ResolvedReport -PathType Leaf)) {
    throw "Akiha did not write the provider runtime smoke report."
}

$Report = Get-Content -LiteralPath $ResolvedReport -Raw | ConvertFrom-Json
$Report.checks | Format-Table name, status, detail -AutoSize
if ($Process.ExitCode -ne 0 -or -not $Report.passed) {
    throw "Packaged provider runtime smoke failed. See $ResolvedReport"
}

Write-Host "Packaged provider runtime smoke passed: $ResolvedReport"

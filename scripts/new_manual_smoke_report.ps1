param(
    [string]$OutputDir = "dist\manual-smoke-reports",
    [string]$TemplatePath = "docs\phases\phase-06-packaging\MANUAL_SMOKE_REPORT_TEMPLATE.md"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path $TemplatePath)) {
        throw "Manual smoke report template is missing: $TemplatePath"
    }

    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $ReportPath = Join-Path $OutputDir "manual-smoke-report-$Timestamp.md"
    Copy-Item -Path $TemplatePath -Destination $ReportPath
    Set-ItemProperty -Path $ReportPath -Name LastWriteTime -Value (Get-Date)

    $ResolvedReportPath = (Resolve-Path $ReportPath).Path
    Write-Host "Created manual smoke report: $ResolvedReportPath"
}
finally {
    Pop-Location
}

param(
    [string]$ExePath = "dist\nuitka\main.dist\Akiha.exe",
    [switch]$SkipSourceSmoke,
    [switch]$SkipPackagedSmoke,
    [switch]$SkipManualReport,
    [switch]$RunExistingDataPass
)

$ErrorActionPreference = "Stop"

function Invoke-Phase6Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

function Add-ReadinessResult {
    param(
        [object[]]$Results,
        [string]$Step,
        [string]$Status,
        [string]$Detail
    )

    return $Results + [pscustomobject]@{
        Step = $Step
        Status = $Status
        Detail = $Detail
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Results = @()

Push-Location $ProjectRoot
try {
    Invoke-Phase6Step "Quality gate" {
        & (Join-Path $PSScriptRoot "build_akiha_nuitka.ps1") -SkipBuild
    }
    $Results = Add-ReadinessResult $Results "Quality gate" "passed" `
        "Unit tests, Ruff, Black, compileall, and Nuitka availability passed."

    if ($SkipSourceSmoke) {
        $Results = Add-ReadinessResult $Results "Source smoke" "skipped" `
            "Skipped by -SkipSourceSmoke."
    }
    else {
        Invoke-Phase6Step "Source smoke" {
            & (Join-Path $PSScriptRoot "smoke_source_app.ps1")
        }
        $Results = Add-ReadinessResult $Results "Source smoke" "passed" `
            "Source app startup, local data, schema, and log health passed."
    }

    if ($SkipPackagedSmoke) {
        $Results = Add-ReadinessResult $Results "Packaged smoke" "skipped" `
            "Skipped by -SkipPackagedSmoke."
    }
    elseif (-not (Test-Path $ExePath)) {
        $Results = Add-ReadinessResult $Results "Packaged smoke" "skipped" `
            "Packaged executable was not found at $ExePath."
    }
    else {
        if ($RunExistingDataPass) {
            Invoke-Phase6Step "Packaged smoke" {
                & (Join-Path $PSScriptRoot "smoke_packaged_app.ps1") `
                    -ExePath $ExePath `
                    -RunExistingDataPass
            }
        }
        else {
            Invoke-Phase6Step "Packaged smoke" {
                & (Join-Path $PSScriptRoot "smoke_packaged_app.ps1") `
                    -ExePath $ExePath
            }
        }
        $Results = Add-ReadinessResult $Results "Packaged smoke" "passed" `
            "Packaged artifact, GUI subsystem, startup, schema, and log health passed."
    }

    if ($SkipManualReport) {
        $Results = Add-ReadinessResult $Results "Manual smoke report" "skipped" `
            "Skipped by -SkipManualReport."
    }
    else {
        Invoke-Phase6Step "Manual smoke report" {
            & (Join-Path $PSScriptRoot "new_manual_smoke_report.ps1")
        }
        $Results = Add-ReadinessResult $Results "Manual smoke report" "created" `
            "Manual smoke report template was copied into dist\manual-smoke-reports."
    }

    Write-Host ""
    Write-Host "== Phase 6 Release Readiness Summary =="
    $Results | Format-Table -AutoSize
}
finally {
    Pop-Location
}

param(
    [string]$ExePath = "dist\pyinstaller-development\Akiha\Akiha.exe",
    [string]$SmokeRoot = "",
    [int]$PrimaryStartupSeconds = 8,
    [int]$SecondaryExitSeconds = 5
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    $ResolvedExePath = (Resolve-Path $ExePath).Path
    $WorkingDirectory = Split-Path -Parent $ResolvedExePath
    if (-not $SmokeRoot) {
        $SmokeRoot = Join-Path `
            (Split-Path -Parent (Split-Path -Parent $ResolvedExePath)) `
            ("single-instance-localappdata-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }
    $SmokeRoot = [System.IO.Path]::GetFullPath($SmokeRoot)
    New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

    $OldLocalAppData = $env:LOCALAPPDATA
    $env:LOCALAPPDATA = $SmokeRoot
    $Primary = $null
    $Secondary = $null
    try {
        $Primary = Start-Process `
            -FilePath $ResolvedExePath `
            -WorkingDirectory $WorkingDirectory `
            -PassThru
        Start-Sleep -Seconds $PrimaryStartupSeconds
        if ($Primary.HasExited) {
            throw "Primary packaged process exited during startup."
        }

        $Secondary = Start-Process `
            -FilePath $ResolvedExePath `
            -WorkingDirectory $WorkingDirectory `
            -PassThru
        if (-not $Secondary.WaitForExit($SecondaryExitSeconds * 1000)) {
            throw "Secondary launch did not hand off activation and exit in time."
        }
        if ($Secondary.ExitCode -ne 0) {
            throw "Secondary launch exited with code $($Secondary.ExitCode)."
        }

        Start-Sleep -Milliseconds 500
        if ($Primary.HasExited) {
            throw "Primary packaged process exited after secondary activation."
        }

        [pscustomobject]@{
            ExePath = $ResolvedExePath
            SmokeLocalAppData = $SmokeRoot
            PrimaryProcessId = $Primary.Id
            PrimaryRemainedRunning = $true
            SecondaryProcessId = $Secondary.Id
            SecondaryExitCode = $Secondary.ExitCode
            ActivationHandoffPassed = $true
        } | Format-List
    }
    finally {
        foreach ($Process in @($Secondary, $Primary)) {
            if ($null -ne $Process -and -not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force
                $Process.WaitForExit()
            }
        }
        $env:LOCALAPPDATA = $OldLocalAppData
    }
}
finally {
    Pop-Location
}

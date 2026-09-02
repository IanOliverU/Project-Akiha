param(
    [string]$SmokeRoot = "",
    [string]$PythonExe = "",
    [int]$StartupSeconds = 8,
    [int]$ShutdownSeconds = 3
)

$ErrorActionPreference = "Stop"

function Test-RequiredPath {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path $Path)) {
        throw "$Label was not created: $Path"
    }
}

function Invoke-DatabaseSchemaCheck {
    param(
        [string]$DatabasePath,
        [string]$PythonExe
    )

$SchemaCheck = @'
import sqlite3
import sys

database_path = sys.argv[1]
expected_tables = {
    "external_event_receipts",
    "integration_sync_state",
    "pet_appearance_selection",
    "behavior_events",
    "conversations",
    "memories",
    "messages",
    "notification_inbox",
    "pet_reward_grants",
    "pet_state",
    "pet_state_history",
    "schema_version",
    "shop_equipment",
    "shop_inventory",
    "shop_transactions",
}

connection = sqlite3.connect(database_path)
try:
    tables = {
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type='table'"
        )
    }
finally:
    connection.close()

missing = sorted(expected_tables - tables)
if missing:
    print(f"Missing database tables: {missing}")
    raise SystemExit(1)

print(f"Database tables OK: {sorted(expected_tables)}")
'@
    $SchemaCheck | & $PythonExe - $DatabasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Database schema smoke check failed."
    }
}

function Invoke-SmokeLogCheck {
    param(
        [string]$LogPath,
        [string]$PythonExe
    )

    & $PythonExe -m project_akiha.tools.verify_smoke_log $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke log check failed."
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not $PythonExe) {
        $EnvironmentCandidates = @(
            (Join-Path $ProjectRoot ".venv313\Scripts\python.exe"),
            (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
        )
        $PythonExe = $EnvironmentCandidates |
            Where-Object { Test-Path -LiteralPath $_ } |
            Select-Object -First 1
    }
    if (-not $PythonExe) {
        $PythonExe = (& python -c "import sys; print(sys.executable)").Trim()
    }
    if (-not $PythonExe) {
        throw "Unable to resolve the current Python executable."
    }

    if (-not $SmokeRoot) {
        $SmokeRoot = Join-Path `
            $ProjectRoot `
            ("dist\source-smoke-localappdata-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }

    New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

    $OldLocalAppData = $env:LOCALAPPDATA
    $env:LOCALAPPDATA = $SmokeRoot
    try {
        $Process = Start-Process `
            -FilePath $PythonExe `
            -ArgumentList @("-m", "project_akiha.app.main") `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -PassThru

        try {
            Start-Sleep -Seconds $StartupSeconds
            if ($Process.HasExited) {
                throw "Source app exited during startup with code $($Process.ExitCode)."
            }

            $DataDir = Join-Path $SmokeRoot "Akiha"
            $LogPath = Join-Path $DataDir "logs\app.log"
            $DatabasePath = Join-Path $DataDir "akiha.sqlite3"
            $StateDir = Join-Path $DataDir "state"

            Test-RequiredPath $DataDir "Data directory"
            Test-RequiredPath $LogPath "Log file"
            Test-RequiredPath $DatabasePath "Database"
            Invoke-DatabaseSchemaCheck `
                -DatabasePath $DatabasePath `
                -PythonExe $PythonExe

            $CloseRequested = $Process.CloseMainWindow()
            Start-Sleep -Seconds $ShutdownSeconds
            $ForcedStop = $false
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force
                $Process.WaitForExit()
                $ForcedStop = $true
            }
            Invoke-SmokeLogCheck -LogPath $LogPath -PythonExe $PythonExe

            [pscustomobject]@{
                RunLabel = "source"
                PythonExe = $PythonExe
                ProcessId = $Process.Id
                SmokeLocalAppData = $SmokeRoot
                DataDirExists = Test-Path $DataDir
                LogExists = Test-Path $LogPath
                DatabaseExists = Test-Path $DatabasePath
                StateDirExists = Test-Path $StateDir
                CloseMainWindowRequested = $CloseRequested
                ForcedStop = $ForcedStop
                ExitCode = $Process.ExitCode
            } | Format-List
        }
        finally {
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force
                $Process.WaitForExit()
            }
        }
    }
    finally {
        $env:LOCALAPPDATA = $OldLocalAppData
    }
}
finally {
    Pop-Location
}

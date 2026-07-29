param(
    [string]$ExePath = "dist\nuitka-phase6-smoke\main.dist\Akiha.exe",
    [string]$SmokeRoot = "",
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

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ResolvedExePath = (Resolve-Path $ExePath).Path
    $WorkingDir = Split-Path -Parent $ResolvedExePath
    if (-not $SmokeRoot) {
        $SmokeRoot = Join-Path `
            (Split-Path -Parent (Split-Path -Parent $ResolvedExePath)) `
            ("smoke-localappdata-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }

    New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

    $OldLocalAppData = $env:LOCALAPPDATA
    $env:LOCALAPPDATA = $SmokeRoot
    try {
        $Process = Start-Process `
            -FilePath $ResolvedExePath `
            -WorkingDirectory $WorkingDir `
            -PassThru

        Start-Sleep -Seconds $StartupSeconds
        if ($Process.HasExited) {
            throw "Packaged app exited during startup with code $($Process.ExitCode)."
        }

        $DataDir = Join-Path $SmokeRoot "Akiha"
        $LogPath = Join-Path $DataDir "logs\app.log"
        $DatabasePath = Join-Path $DataDir "akiha.sqlite3"
        $StateDir = Join-Path $DataDir "state"

        Test-RequiredPath $DataDir "Data directory"
        Test-RequiredPath $LogPath "Log file"
        Test-RequiredPath $DatabasePath "Database"

        $SchemaCheck = @'
import sqlite3
import sys

database_path = sys.argv[1]
expected_tables = {
    "behavior_events",
    "conversations",
    "memories",
    "messages",
    "schema_version",
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
        $SchemaCheck | python - $DatabasePath
        if ($LASTEXITCODE -ne 0) {
            throw "Database schema smoke check failed."
        }

        $CloseRequested = $Process.CloseMainWindow()
        Start-Sleep -Seconds $ShutdownSeconds
        $ForcedStop = $false
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit()
            $ForcedStop = $true
        }

        [pscustomobject]@{
            ExePath = $ResolvedExePath
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
        $env:LOCALAPPDATA = $OldLocalAppData
    }
}
finally {
    Pop-Location
}

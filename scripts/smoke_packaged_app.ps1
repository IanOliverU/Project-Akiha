param(
    [string]$ExePath = "dist\nuitka-phase6-smoke\main.dist\Akiha.exe",
    [string]$SmokeRoot = "",
    [int]$StartupSeconds = 8,
    [int]$ShutdownSeconds = 3,
    [switch]$RunExistingDataPass
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
        [string]$PythonExe,
        [string]$DatabasePath
    )

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
    $SchemaCheck | & $PythonExe - $DatabasePath
    if ($LASTEXITCODE -ne 0) {
        throw "Database schema smoke check failed."
    }
}

function Set-Utf8NoBomContent {
    param(
        [string]$Path,
        [string]$Content
    )

    $Encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $Encoding)
}

function Write-SmokeExistingData {
    param(
        [string]$SmokeRoot
    )

    $DataDir = Join-Path $SmokeRoot "Akiha"
    $StateDir = Join-Path $DataDir "state"
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

    $UserConfigPath = Join-Path $DataDir "user_config.toml"
    Set-Utf8NoBomContent $UserConfigPath @'
[pet_window]
start_x = 96
start_y = 128

[ai]
provider = "mock"

[personality]
character_name = "Akiha"
'@

    $PetStatePath = Join-Path $StateDir "pet_window.json"
    Set-Utf8NoBomContent $PetStatePath @'
{
  "x": 96,
  "y": 128
}
'@
}

function Invoke-PackagedAppSmokeRun {
    param(
        [string]$RunLabel,
        [string]$PythonExe,
        [string]$ResolvedExePath,
        [string]$WorkingDir,
        [string]$SmokeRoot,
        [int]$StartupSeconds,
        [int]$ShutdownSeconds
    )

    $DataDir = Join-Path $SmokeRoot "Akiha"
    $LogPath = Join-Path $DataDir "logs\app.log"
    $DatabasePath = Join-Path $DataDir "akiha.sqlite3"
    $StateDir = Join-Path $DataDir "state"
    $UserConfigPath = Join-Path $DataDir "user_config.toml"

    $DataDirExistedBeforeStart = Test-Path $DataDir
    $UserConfigExistedBeforeStart = Test-Path $UserConfigPath
    $DatabaseExistedBeforeStart = Test-Path $DatabasePath
    $StateDirExistedBeforeStart = Test-Path $StateDir

    $Process = Start-Process `
        -FilePath $ResolvedExePath `
        -WorkingDirectory $WorkingDir `
        -PassThru

    try {
        Start-Sleep -Seconds $StartupSeconds
        if ($Process.HasExited) {
            throw "Packaged app exited during startup with code $($Process.ExitCode)."
        }

        Test-RequiredPath $DataDir "Data directory"
        Test-RequiredPath $LogPath "Log file"
        Test-RequiredPath $DatabasePath "Database"
        Invoke-DatabaseSchemaCheck -PythonExe $PythonExe -DatabasePath $DatabasePath

        $CloseRequested = $Process.CloseMainWindow()
        Start-Sleep -Seconds $ShutdownSeconds
        $ForcedStop = $false
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit()
            $ForcedStop = $true
        }

        [pscustomobject]@{
            RunLabel = $RunLabel
            ExePath = $ResolvedExePath
            ProcessId = $Process.Id
            SmokeLocalAppData = $SmokeRoot
            DataDirExistedBeforeStart = $DataDirExistedBeforeStart
            UserConfigExistedBeforeStart = $UserConfigExistedBeforeStart
            DatabaseExistedBeforeStart = $DatabaseExistedBeforeStart
            StateDirExistedBeforeStart = $StateDirExistedBeforeStart
            DataDirExists = Test-Path $DataDir
            LogExists = Test-Path $LogPath
            DatabaseExists = Test-Path $DatabasePath
            StateDirExists = Test-Path $StateDir
            UserConfigExists = Test-Path $UserConfigPath
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

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $ResolvedExePath = (Resolve-Path $ExePath).Path
    $WorkingDir = Split-Path -Parent $ResolvedExePath
    $PythonExe = (& python -c "import sys; print(sys.executable)").Trim()
    if (-not $PythonExe) {
        throw "Unable to resolve the current Python executable."
    }

    & $PythonExe -m project_akiha.tools.verify_windows_gui_subsystem $ResolvedExePath
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged executable is not a Windows GUI subsystem app."
    }

    if (-not $SmokeRoot) {
        $SmokeRoot = Join-Path `
            (Split-Path -Parent (Split-Path -Parent $ResolvedExePath)) `
            ("smoke-localappdata-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }

    New-Item -ItemType Directory -Force -Path $SmokeRoot | Out-Null

    $OldLocalAppData = $env:LOCALAPPDATA
    $env:LOCALAPPDATA = $SmokeRoot
    try {
        Invoke-PackagedAppSmokeRun `
            -RunLabel "fresh-data" `
            -PythonExe $PythonExe `
            -ResolvedExePath $ResolvedExePath `
            -WorkingDir $WorkingDir `
            -SmokeRoot $SmokeRoot `
            -StartupSeconds $StartupSeconds `
            -ShutdownSeconds $ShutdownSeconds

        if ($RunExistingDataPass) {
            Write-SmokeExistingData $SmokeRoot
            Invoke-PackagedAppSmokeRun `
                -RunLabel "existing-data" `
                -PythonExe $PythonExe `
                -ResolvedExePath $ResolvedExePath `
                -WorkingDir $WorkingDir `
                -SmokeRoot $SmokeRoot `
                -StartupSeconds $StartupSeconds `
                -ShutdownSeconds $ShutdownSeconds
        }
    }
    finally {
        $env:LOCALAPPDATA = $OldLocalAppData
    }
}
finally {
    Pop-Location
}

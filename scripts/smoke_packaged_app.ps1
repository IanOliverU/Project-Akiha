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

function Invoke-SmokeLogCheck {
    param(
        [string]$PythonExe,
        [string]$LogPath
    )

    & $PythonExe -m project_akiha.tools.verify_smoke_log $LogPath
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke log check failed."
    }
}

function Add-WindowInspectorType {
    if (([System.Management.Automation.PSTypeName]"AkihaWindowInspector").Type) {
        return
    }

    Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class AkihaWindowInspector
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetClassName(IntPtr hWnd, StringBuilder className, int maxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder windowText, int maxCount);
}
"@
}

function Get-VisibleProcessWindows {
    param(
        [int]$ProcessId
    )

    Add-WindowInspectorType
    $Windows = New-Object System.Collections.Generic.List[object]
    $Callback = [AkihaWindowInspector+EnumWindowsProc]{
        param(
            [IntPtr]$WindowHandle,
            [IntPtr]$Parameter
        )

        $OwnerProcessId = 0
        [AkihaWindowInspector]::GetWindowThreadProcessId(
            $WindowHandle,
            [ref]$OwnerProcessId
        ) | Out-Null

        if ($OwnerProcessId -eq $ProcessId -and [AkihaWindowInspector]::IsWindowVisible($WindowHandle)) {
            $ClassName = New-Object System.Text.StringBuilder 256
            $WindowTitle = New-Object System.Text.StringBuilder 256
            [AkihaWindowInspector]::GetClassName($WindowHandle, $ClassName, $ClassName.Capacity) | Out-Null
            [AkihaWindowInspector]::GetWindowText($WindowHandle, $WindowTitle, $WindowTitle.Capacity) | Out-Null
            $Windows.Add([pscustomobject]@{
                Handle = $WindowHandle
                ClassName = $ClassName.ToString()
                Title = $WindowTitle.ToString()
            }) | Out-Null
        }

        return $true
    }

    [AkihaWindowInspector]::EnumWindows($Callback, [IntPtr]::Zero) | Out-Null
    return $Windows
}

function Invoke-PackagedWindowCheck {
    param(
        [int]$ProcessId
    )

    $Windows = @(Get-VisibleProcessWindows -ProcessId $ProcessId)
    $ConsoleWindows = @($Windows | Where-Object { $_.ClassName -eq "ConsoleWindowClass" })
    if ($ConsoleWindows.Count -gt 0) {
        $ConsoleWindows | Format-Table -AutoSize
        throw "Packaged app opened a visible console window."
    }

    Write-Host "Window check OK: no visible console window for process $ProcessId."
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
            $Message = "Packaged app exited during startup with code $($Process.ExitCode)."
            if (-not (Test-Path $LogPath)) {
                $Message += (
                    " No app log was created, so the failure likely happened " +
                    "before Project Akiha startup logging began."
                )
            }
            throw $Message
        }

        Test-RequiredPath $DataDir "Data directory"
        Test-RequiredPath $LogPath "Log file"
        Test-RequiredPath $DatabasePath "Database"
        Invoke-DatabaseSchemaCheck -PythonExe $PythonExe -DatabasePath $DatabasePath
        Invoke-PackagedWindowCheck -ProcessId $Process.Id

        $CloseRequested = $Process.CloseMainWindow()
        Start-Sleep -Seconds $ShutdownSeconds
        $ForcedStop = $false
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force
            $Process.WaitForExit()
            $ForcedStop = $true
        }
        Invoke-SmokeLogCheck -PythonExe $PythonExe -LogPath $LogPath

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

    & $PythonExe -m project_akiha.tools.verify_packaged_artifact $WorkingDir
    if ($LASTEXITCODE -ne 0) {
        throw "Packaged artifact validation failed."
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

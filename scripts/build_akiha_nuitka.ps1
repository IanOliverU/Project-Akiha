param(
    [string]$OutputDir = "dist\nuitka",
    [switch]$SkipQualityChecks,
    [switch]$SkipBuild,
    [switch]$AllowExperimentalPython
)

$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [scriptblock]$Command,
        [string]$Name
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not $SkipQualityChecks) {
        Invoke-CheckedCommand { python -m unittest discover tests } "Unit tests"
        Invoke-CheckedCommand { python -m ruff check project_akiha tests } "Ruff"
        Invoke-CheckedCommand {
            python -m black --check project_akiha tests
        } "Black"
        Invoke-CheckedCommand {
            python -m compileall project_akiha tests
        } "Compile"
    }

    Invoke-CheckedCommand {
        python -m nuitka --version --zig --assume-yes-for-downloads
    } "Nuitka availability check"

    if ($SkipBuild) {
        Write-Host "Skipped Nuitka build after validation."
        return
    }

    $PythonVersion = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
    $PythonVersionParts = $PythonVersion.Split(".")
    $PythonMajor = [int]$PythonVersionParts[0]
    $PythonMinor = [int]$PythonVersionParts[1]
    if ($PythonMajor -eq 3 -and $PythonMinor -ge 14 -and -not $AllowExperimentalPython) {
        throw (
            "Nuitka standalone builds are blocked on Python $PythonVersion because " +
            "Python 3.14 support is experimental and produced non-runnable frozen " +
            "executables in Phase 6 smoke testing. Build with Python 3.13, or rerun " +
            "with -AllowExperimentalPython for diagnostics only."
        )
    }

    Invoke-CheckedCommand {
        python -m nuitka `
        --standalone `
        --assume-yes-for-downloads `
        --zig `
        --enable-plugin=pyside6 `
        --windows-console-mode=disable `
        --output-dir=$OutputDir `
        --output-filename=Akiha `
        --include-data-dir=assets=assets `
        --include-data-dir=project_akiha/config=project_akiha/config `
        --include-data-dir=project_akiha/database/migrations=project_akiha/database/migrations `
        project_akiha/app/main.py
    } "Nuitka build"

    $BuiltExePath = Join-Path $OutputDir "main.dist\Akiha.exe"
    Invoke-CheckedCommand {
        python -m project_akiha.tools.verify_windows_gui_subsystem $BuiltExePath
    } "Windows GUI subsystem check"

    $BuiltArtifactDir = Join-Path $OutputDir "main.dist"
    Invoke-CheckedCommand {
        python -m project_akiha.tools.verify_packaged_artifact $BuiltArtifactDir
    } "Packaged artifact check"
}
finally {
    Pop-Location
}

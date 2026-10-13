param(
    [string]$OutputDir = "dist\pyinstaller-development",
    [string]$WorkDir = "dist\pyinstaller-work",
    [string]$PythonPath = "",
    [switch]$Clean,
    [switch]$SkipQualityChecks
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'build_path_guard.ps1')

function Resolve-ProjectPath {
    param([string]$Path)

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Path))
}

function Invoke-Checked {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    $Timer = [System.Diagnostics.Stopwatch]::StartNew()
    & $Command
    $ExitCode = $LASTEXITCODE
    $Timer.Stop()
    $script:Stages.Add([pscustomobject]@{
        name = $Name
        duration_seconds = [math]::Round($Timer.Elapsed.TotalSeconds, 3)
    })
    if ($ExitCode -ne 0) {
        throw "$Name failed with exit code $ExitCode."
    }
    Write-Host "$Name passed in $($Timer.Elapsed.ToString('hh\:mm\:ss\.fff'))."
}

$BuildPaths = Assert-AkihaBuildPaths -ProjectRoot $ProjectRoot -OutputDir $OutputDir -WorkDir $WorkDir
$ResolvedOutputDir = $BuildPaths.OutputDir
$ResolvedWorkDir = $BuildPaths.WorkDir
$SpecDir = Join-Path $ResolvedWorkDir "spec"
$ReportDir = Join-Path $ResolvedOutputDir "build-reports"
$BuildStartedAt = (Get-Date).ToUniversalTime()
$BuildStamp = $BuildStartedAt.ToString("yyyyMMdd-HHmmss")
$script:Stages = [System.Collections.Generic.List[object]]::new()

if (-not $PythonPath) {
    $Candidates = @(
        (Join-Path $ProjectRoot ".venv313\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    )
    $PythonPath = $Candidates |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
}
if (-not $PythonPath) {
    throw "Python executable was not found. Use -PythonPath to select Python 3.13."
}
$PythonPath = Resolve-ProjectPath $PythonPath
$PythonVersion = (& $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($PythonVersion -ne "3.13") {
    throw "PyInstaller packaging requires Python 3.13; found $PythonVersion."
}

$OriginalBuildPath = $env:PATH
$GitDirectory = Split-Path -Parent (Get-Command git -ErrorAction Stop).Source
$PythonBase = (& $PythonPath -c "import sys; print(sys.base_prefix)").Trim()
# Exclude inherited Poppler/other tool DLL directories from Qt discovery.
$env:PATH = @((Split-Path -Parent $PythonPath), $PythonBase, $env:SystemRoot,
    (Join-Path $env:SystemRoot 'System32'),
    (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0'), $GitDirectory) -join ';'
Push-Location $ProjectRoot
try {
    Invoke-Checked "Pinned release dependencies" {
        & $PythonPath -B -m project_akiha.tools.build_identity check
    }
    Invoke-Checked "Dependency consistency" { & $PythonPath -B -m pip check }

    & $PythonPath -m PyInstaller --version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is unavailable. Install the package extra with: pip install -e .[package]"
    }

    if ($Clean) {
        # Validate BOTH final cleanup targets before removing either one.
        Assert-AkihaCleanupTree -ProjectRoot $ProjectRoot -Path $ResolvedWorkDir
        Assert-AkihaCleanupTree -ProjectRoot $ProjectRoot -Path (Join-Path $ResolvedOutputDir 'Akiha')
        if (Test-Path -LiteralPath $ResolvedWorkDir) {
            Remove-Item -LiteralPath $ResolvedWorkDir -Recurse -Force
        }
        if (Test-Path -LiteralPath (Join-Path $ResolvedOutputDir "Akiha")) {
            Remove-Item -LiteralPath (Join-Path $ResolvedOutputDir "Akiha") -Recurse -Force
        }
    }
    New-Item -ItemType Directory -Force -Path $SpecDir, $ReportDir | Out-Null

    $IdentityInputs = Join-Path $ReportDir "inputs-$BuildStamp.json"
    $IdentityReport = Join-Path $ReportDir "identity-$BuildStamp.json"
    Invoke-Checked "Build input identity" {
        & $PythonPath -B -m project_akiha.tools.build_identity capture --report $IdentityInputs
    }
    if (-not $SkipQualityChecks) {
        Invoke-Checked "Unit and integration tests" {
            & $PythonPath -m unittest discover tests
        }
        Invoke-Checked "Ruff" {
            & $PythonPath -m ruff check project_akiha tests
        }
        Invoke-Checked "Black" {
            & $PythonPath -m black --check project_akiha tests
        }
        Invoke-Checked "Compilation" {
            & $PythonPath -m compileall -q project_akiha tests
        }
    }

    $Arguments = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "Akiha",
        "--contents-directory", ".",
        "--distpath", $ResolvedOutputDir,
        "--workpath", $ResolvedWorkDir,
        "--specpath", $SpecDir,
        "--paths", $ProjectRoot,
        "--add-data", "$(Join-Path $ProjectRoot 'assets');assets",
        "--add-data", "$(Join-Path $ProjectRoot 'project_akiha/config');project_akiha/config",
        "--add-data", "$(Join-Path $ProjectRoot 'project_akiha/database/migrations');project_akiha/database/migrations",
        "--add-data", "$(Join-Path $ProjectRoot 'scripts/run_gpt_sovits_api.py');scripts",
        "--collect-all", "faster_whisper",
        "--collect-all", "google.genai",
        "--collect-all", "tzdata",
        "--copy-metadata", "google-genai",
        "--hidden-import", "av.utils",
        "--hidden-import", "websocket",
        "project_akiha/app/main.py"
    )
    if ($Clean) {
        $Arguments = @("-m", "PyInstaller", "--clean") + $Arguments[2..($Arguments.Count - 1)]
    }

    Invoke-Checked "PyInstaller one-folder build" {
        & $PythonPath @Arguments
    }

    $ArtifactDir = Join-Path $ResolvedOutputDir "Akiha"
    Invoke-Checked "Packaged artifact validation" {
        & $PythonPath -m project_akiha.tools.verify_packaged_artifact $ArtifactDir
    }
    Invoke-Checked "Windows GUI subsystem validation" {
        & $PythonPath -m project_akiha.tools.verify_windows_gui_subsystem (
            Join-Path $ArtifactDir "Akiha.exe"
        )
    }

    Invoke-Checked "Build artifact identity" {
        & $PythonPath -B -m project_akiha.tools.build_identity finalize --inputs $IdentityInputs --artifact $ArtifactDir --report $IdentityReport
    }
    $EndedAt = (Get-Date).ToUniversalTime()
    $Report = [ordered]@{
        schema_version = 2
        identity_report = $IdentityReport
        build_mode = if ($Clean) { "clean-development" } else { "cached-development" }
        outcome = "passed"
        started_at_utc = $BuildStartedAt.ToString("o")
        ended_at_utc = $EndedAt.ToString("o")
        duration_seconds = [math]::Round(($EndedAt - $BuildStartedAt).TotalSeconds, 3)
        python_executable = $PythonPath
        python_version = $PythonVersion
        output_directory = $ArtifactDir
        work_directory = $ResolvedWorkDir
        stages = @($script:Stages)
    }
    $ReportPath = Join-Path $ReportDir "pyinstaller-build-$BuildStamp.json"
    $Report | ConvertTo-Json -Depth 4 | Set-Content -Path $ReportPath -Encoding utf8

    Write-Host ""
    Write-Host "PyInstaller candidate: $ArtifactDir"
    Write-Host "Timing report: $ReportPath"
}
finally {
    $env:PATH = $OriginalBuildPath
    Pop-Location
}

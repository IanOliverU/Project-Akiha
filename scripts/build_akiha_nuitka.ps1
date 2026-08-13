param(
    [string]$OutputDir = "dist\nuitka",
    [switch]$FastBuild,
    [switch]$CleanRelease,
    [switch]$SkipQualityChecks,
    [switch]$SkipBuild,
    [switch]$AllowExperimentalPython,
    [string]$DevelopmentCacheDir = "",
    [string]$ReleaseCacheDir = ""
)

$ErrorActionPreference = "Stop"
$script:BuildTimings = [System.Collections.Generic.List[object]]::new()

function Invoke-TimedCheckedCommand {
    param(
        [scriptblock]$Command,
        [string]$Name
    )

    Write-Host ""
    Write-Host "== $Name =="
    $StartedAt = (Get-Date).ToUniversalTime()
    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $Status = "passed"
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE."
        }
    }
    catch {
        $Status = "failed"
        throw
    }
    finally {
        $Stopwatch.Stop()
        $script:BuildTimings.Add([pscustomobject]@{
            name = $Name
            status = $Status
            started_at_utc = $StartedAt.ToString("o")
            duration_seconds = [math]::Round($Stopwatch.Elapsed.TotalSeconds, 3)
        })
        Write-Host (
            "{0}: {1} in {2}" -f `
                $Name,
                $Status,
                $Stopwatch.Elapsed.ToString("hh\:mm\:ss\.fff")
        )
    }
}

function Resolve-ProjectPath {
    param(
        [string]$Path,
        [string]$ProjectRoot
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Path))
}

function Write-BuildTimingReport {
    param(
        [string]$ReportPath,
        [string]$BuildMode,
        [string]$PythonExecutable,
        [string]$CacheDirectory,
        [string]$OutputDirectory,
        [string]$CompilationReportPath,
        [datetime]$StartedAt,
        [string]$Outcome
    )

    $EndedAt = (Get-Date).ToUniversalTime()
    $Report = [ordered]@{
        schema_version = 1
        build_mode = $BuildMode
        outcome = $Outcome
        started_at_utc = $StartedAt.ToString("o")
        ended_at_utc = $EndedAt.ToString("o")
        duration_seconds = [math]::Round(($EndedAt - $StartedAt).TotalSeconds, 3)
        python_executable = $PythonExecutable
        cache_directory = $CacheDirectory
        output_directory = $OutputDirectory
        compilation_report = $CompilationReportPath
        stages = @($script:BuildTimings)
    }
    $Report | ConvertTo-Json -Depth 5 | Set-Content -Path $ReportPath -Encoding utf8

    Write-Host ""
    Write-Host "== Build timing summary =="
    $script:BuildTimings |
        Select-Object name, status, duration_seconds |
        Format-Table -AutoSize
    Write-Host "Timing report: $ReportPath"
    if ($CompilationReportPath) {
        Write-Host "Nuitka report: $CompilationReportPath"
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ResolvedOutputDir = Resolve-ProjectPath $OutputDir $ProjectRoot
$BuildStartedAt = (Get-Date).ToUniversalTime()
$BuildStamp = $BuildStartedAt.ToString("yyyyMMdd-HHmmss")
$ReportDir = Join-Path $ResolvedOutputDir "build-reports"
$TimingReportPath = Join-Path $ReportDir "build-timings-$BuildStamp.json"
$CompilationReportPath = ""
$BuildMode = "validation-only"
$CacheDirectory = ""
$BuildOutcome = "failed"
$PythonExecutable = ""
$OriginalNuitkaCacheDir = $env:NUITKA_CACHE_DIR

if ($FastBuild -and $CleanRelease) {
    throw "Choose exactly one build mode: -FastBuild or -CleanRelease."
}
if (-not $SkipBuild -and -not $FastBuild -and -not $CleanRelease) {
    throw (
        "A packaged build requires an explicit mode. Use -FastBuild for cached " +
        "development packages or -CleanRelease for a phase-closing release."
    )
}

New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

Push-Location $ProjectRoot
try {
    $PythonExecutable = (& python -c "import sys; print(sys.executable)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $PythonExecutable) {
        throw "Unable to resolve the active Python executable."
    }

    if (-not $SkipQualityChecks) {
        Invoke-TimedCheckedCommand {
            python -m unittest discover tests
        } "Unit tests"
        Invoke-TimedCheckedCommand {
            python -m ruff check project_akiha tests
        } "Ruff"
        Invoke-TimedCheckedCommand {
            python -m black --check project_akiha tests
        } "Black"
        Invoke-TimedCheckedCommand {
            python -m compileall project_akiha tests
        } "Compile"
    }

    Invoke-TimedCheckedCommand {
        python -m nuitka --version --zig --assume-yes-for-downloads
    } "Nuitka availability"

    if ($SkipBuild) {
        $BuildOutcome = "passed"
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

    if (-not $DevelopmentCacheDir) {
        $DevelopmentCacheDir = Join-Path $env:LOCALAPPDATA "Nuitka\Nuitka\Cache"
    }
    if (-not $ReleaseCacheDir) {
        $ReleaseCacheDir = Join-Path $env:LOCALAPPDATA "Akiha\BuildCache\Nuitka\release"
    }

    $NuitkaArguments = @(
        "-m",
        "nuitka"
    )
    if ($CleanRelease) {
        $BuildMode = "clean-release"
        $CacheDirectory = [System.IO.Path]::GetFullPath($ReleaseCacheDir)
        $NuitkaArguments += "--clean-cache=all"
    }
    else {
        $BuildMode = "fast-development"
        $CacheDirectory = [System.IO.Path]::GetFullPath($DevelopmentCacheDir)
    }

    New-Item -ItemType Directory -Path $CacheDirectory -Force | Out-Null
    $env:NUITKA_CACHE_DIR = $CacheDirectory
    $CompilationReportPath = Join-Path (
        Join-Path $ResolvedOutputDir "build-reports"
    ) "nuitka-compilation-report-$BuildStamp.xml"

    Write-Host "Build mode: $BuildMode"
    Write-Host "Nuitka cache: $CacheDirectory"
    Write-Host "Output directory: $ResolvedOutputDir"

    $NuitkaArguments += @(
        "--standalone",
        "--assume-yes-for-downloads",
        "--zig",
        "--enable-plugin=pyside6",
        "--include-module=av.utils",
        "--include-package-data=faster_whisper",
        "--windows-console-mode=attach",
        "--output-dir=$ResolvedOutputDir",
        "--output-filename=Akiha",
        "--include-data-dir=assets=assets",
        "--noinclude-data-files=assets/animations/akiha/Spotify.txt",
        "--include-data-dir=project_akiha/config=project_akiha/config",
        "--include-data-dir=project_akiha/database/migrations=project_akiha/database/migrations",
        "--report=$CompilationReportPath",
        "--report-user-provided=build_mode=$BuildMode",
        "project_akiha/app/main.py"
    )

    Invoke-TimedCheckedCommand {
        python @NuitkaArguments
    } "Nuitka build"

    $BuiltExePath = Join-Path $ResolvedOutputDir "main.dist\Akiha.exe"
    Invoke-TimedCheckedCommand {
        python -m project_akiha.tools.verify_windows_gui_subsystem $BuiltExePath
    } "Windows GUI subsystem check"

    $BuiltArtifactDir = Join-Path $ResolvedOutputDir "main.dist"
    Invoke-TimedCheckedCommand {
        python -m project_akiha.tools.verify_packaged_artifact $BuiltArtifactDir
    } "Packaged artifact check"
    $BuildOutcome = "passed"
}
finally {
    Pop-Location
    Write-BuildTimingReport `
        -ReportPath $TimingReportPath `
        -BuildMode $BuildMode `
        -PythonExecutable $PythonExecutable `
        -CacheDirectory $CacheDirectory `
        -OutputDirectory $ResolvedOutputDir `
        -CompilationReportPath $CompilationReportPath `
        -StartedAt $BuildStartedAt `
        -Outcome $BuildOutcome

    if ($null -eq $OriginalNuitkaCacheDir) {
        Remove-Item Env:NUITKA_CACHE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:NUITKA_CACHE_DIR = $OriginalNuitkaCacheDir
    }
}

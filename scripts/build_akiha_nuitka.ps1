param(
    [string]$OutputDir = "",
    [switch]$FastBuild,
    [switch]$CleanRelease,
    [switch]$SkipQualityChecks,
    [switch]$SkipBuild,
    [switch]$PreflightOnly,
    [switch]$AllowExperimentalPython,
    [switch]$RequireBuildReuse,
    [switch]$DisableCompilerCache,
    [ValidateRange(1, 64)]
    [int]$Jobs = 10,
    [string]$ExpectedZigVersion = "0.16.0",
    [string]$PythonPath = "",
    [string]$DevelopmentCacheDir = "",
    [string]$ReleaseCacheDir = ""
)

$ErrorActionPreference = "Stop"
$script:BuildTimings = [System.Collections.Generic.List[object]]::new()
$script:ToolchainDescription = ""
$script:CompilerExecutable = ""
$script:CompilerVersion = ""
$script:BuildObjectCountBefore = 0
$script:CompilerCacheObjectCountBefore = 0
$script:BuildObjectCountAfter = 0
$script:CompilerCacheObjectCountAfter = 0
$script:CompilerCacheSummary = @()
$script:NuitkaArgumentsForReport = @()
$script:BuildLogPath = ""
$script:MissingRequiredReuseObjects = @()

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
        build_log = $script:BuildLogPath
        toolchain = $script:ToolchainDescription
        compiler_executable = $script:CompilerExecutable
        compiler_version = $script:CompilerVersion
        parallel_jobs = if ($BuildMode -eq "fast-development") { $Jobs } else { $null }
        lto = if ($BuildMode -eq "fast-development") { "no" } else { "default" }
        bytecode_cache = if ($BuildMode -eq "fast-development") { "disabled" } else { "clean" }
        compiler_cache = if ($DisableCompilerCache) { "disabled" } else { "enabled" }
        build_object_count_before = $script:BuildObjectCountBefore
        compiler_cache_object_count_before = $script:CompilerCacheObjectCountBefore
        build_object_count_after = $script:BuildObjectCountAfter
        compiler_cache_object_count_after = $script:CompilerCacheObjectCountAfter
        compiler_cache_object_delta = (
            $script:CompilerCacheObjectCountAfter -
            $script:CompilerCacheObjectCountBefore
        )
        missing_required_reuse_objects = @($script:MissingRequiredReuseObjects)
        compiler_cache_summary = @($script:CompilerCacheSummary)
        nuitka_arguments = @($script:NuitkaArgumentsForReport)
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
if (-not $OutputDir) {
    if ($CleanRelease) {
        $OutputDir = "dist\nuitka-release"
    }
    else {
        $OutputDir = "dist\nuitka-development"
    }
}
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
$OriginalPath = $env:PATH
$OriginalZigGlobalCacheDir = $env:ZIG_GLOBAL_CACHE_DIR
$OriginalZigLocalCacheDir = $env:ZIG_LOCAL_CACHE_DIR

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
    if (-not $PythonPath) {
        $ProjectPython = Join-Path $ProjectRoot ".venv313\Scripts\python.exe"
        if (Test-Path -LiteralPath $ProjectPython) {
            $PythonPath = $ProjectPython
        }
        else {
            $PythonPath = (Get-Command python -ErrorAction Stop).Source
        }
    }
    $PythonPath = [System.IO.Path]::GetFullPath($PythonPath)
    $PythonExecutable = (& $PythonPath -c "import sys; print(sys.executable)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $PythonExecutable) {
        throw "Unable to resolve the active Python executable."
    }
    $PythonUserHome = (& $PythonExecutable -c "import os; print(os.path.expanduser('~'))").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $PythonUserHome) {
        throw "Unable to resolve the Python user home for managed tool discovery."
    }

    if (-not $SkipQualityChecks) {
        Invoke-TimedCheckedCommand {
            & $PythonExecutable -m unittest discover tests
        } "Unit tests"
        Invoke-TimedCheckedCommand {
            & $PythonExecutable -m ruff check project_akiha tests
        } "Ruff"
        Invoke-TimedCheckedCommand {
            & $PythonExecutable -m black --check project_akiha tests
        } "Black"
        Invoke-TimedCheckedCommand {
            & $PythonExecutable -m compileall project_akiha tests
        } "Compile"
    }

    Invoke-TimedCheckedCommand {
        $ToolchainOutput = (& $PythonExecutable -m nuitka --version --zig --assume-yes-for-downloads 2>&1 | Out-String).Trim()
        Write-Host $ToolchainOutput
        $script:ToolchainDescription = $ToolchainOutput

        $CompilerMatch = [regex]::Match(
            $ToolchainOutput,
            "Version C compiler:\s*(.+?zig\.exe) \(zig\.exe ([^)]+)\)\."
        )
        if (-not $CompilerMatch.Success) {
            throw "Nuitka did not resolve the required managed Zig compiler."
        }
        $script:CompilerExecutable = $CompilerMatch.Groups[1].Value
        if ($script:CompilerExecutable.StartsWith("~\")) {
            $script:CompilerExecutable = Join-Path $PythonUserHome (
                $script:CompilerExecutable.Substring(2)
            )
        }
        $script:CompilerExecutable = [System.IO.Path]::GetFullPath(
            $script:CompilerExecutable
        )
        if (-not (Test-Path -LiteralPath $script:CompilerExecutable -PathType Leaf)) {
            throw "Managed Zig executable was reported but does not exist: $($script:CompilerExecutable)"
        }
        $script:CompilerVersion = $CompilerMatch.Groups[2].Value
        if ($script:CompilerVersion -ne $ExpectedZigVersion) {
            throw (
                "Expected managed Zig $ExpectedZigVersion, but Nuitka resolved " +
                "$($script:CompilerVersion)."
            )
        }

        $CompilerDirectory = Split-Path -Parent $script:CompilerExecutable
        $env:PATH = $CompilerDirectory + ";" + $OriginalPath
    } "Nuitka availability and toolchain pin"

    if ($SkipBuild) {
        $BuildOutcome = "passed"
        Write-Host "Skipped Nuitka build after validation."
        return
    }

    $PythonVersion = (& $PythonExecutable -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
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
        $DevelopmentCacheDir = Join-Path $ProjectRoot "dist\build-cache\nuitka-dev"
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
    $ZigNativeCacheRoot = Join-Path $CacheDirectory "zig-native"
    $env:ZIG_GLOBAL_CACHE_DIR = Join-Path $ZigNativeCacheRoot "global"
    $env:ZIG_LOCAL_CACHE_DIR = Join-Path $ZigNativeCacheRoot "local"
    New-Item -ItemType Directory -Path @(
        $env:ZIG_GLOBAL_CACHE_DIR,
        $env:ZIG_LOCAL_CACHE_DIR
    ) -Force | Out-Null
    $CompilationReportPath = Join-Path (
        Join-Path $ResolvedOutputDir "build-reports"
    ) "nuitka-compilation-report-$BuildStamp.xml"

    Write-Host "Build mode: $BuildMode"
    Write-Host "Nuitka cache: $CacheDirectory"
    Write-Host "Output directory: $ResolvedOutputDir"
    Write-Host "Compiler: $($script:CompilerExecutable) (Zig $($script:CompilerVersion))"

    $BuildObjectDirectory = Join-Path $ResolvedOutputDir "main.build"
    if (Test-Path -LiteralPath $BuildObjectDirectory) {
        $script:BuildObjectCountBefore = @(
            Get-ChildItem -LiteralPath $BuildObjectDirectory -File -Filter "*.o"
        ).Count
    }
    $script:CompilerCacheObjectCountBefore = @(
        Get-ChildItem -LiteralPath $CacheDirectory -Recurse -File -Filter "*.obj" -ErrorAction SilentlyContinue
    ).Count
    $RequiredReuseObjects = @(
        "module.google.genai.types.o",
        "module.google.genai.client.o",
        "module.faster_whisper.transcribe.o",
        "module.av.o"
    )
    $script:MissingRequiredReuseObjects = @(
        $RequiredReuseObjects | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $BuildObjectDirectory $_))
        }
    )

    Write-Host "Reusable main.build objects: $($script:BuildObjectCountBefore)"
    Write-Host "Reusable compiler-cache objects: $($script:CompilerCacheObjectCountBefore)"
    if ($script:MissingRequiredReuseObjects.Count -gt 0) {
        Write-Host (
            "Missing key reusable objects: " +
            ($script:MissingRequiredReuseObjects -join ", ")
        )
    }
    if (
        $FastBuild -and
        $RequireBuildReuse -and
        (
            $script:BuildObjectCountBefore -lt 100 -or
            $script:CompilerCacheObjectCountBefore -lt 100 -or
            $script:MissingRequiredReuseObjects.Count -gt 0
        )
    ) {
        throw (
            "FastBuild reuse was required, but the persistent workspace or compiler " +
            "cache does not contain enough reusable objects. No build was started."
        )
    }

    if ($PreflightOnly) {
        $BuildOutcome = "passed"
        Write-Host "Preflight passed. No Nuitka compilation was started."
        return
    }

    $NuitkaArguments += @(
        "--standalone",
        "--assume-yes-for-downloads",
        "--zig",
        "--enable-plugin=pyside6",
        "--include-module=av.utils",
        "--include-package=google.genai",
        "--include-distribution-metadata=google-genai",
        "--include-package-data=faster_whisper",
        "--windows-console-mode=attach",
        "--output-dir=$ResolvedOutputDir",
        "--output-filename=Akiha",
        "--include-data-dir=assets=assets",
        "--noinclude-data-files=assets/animations/akiha/Spotify.txt",
        "--include-data-dir=project_akiha/config=project_akiha/config",
        "--include-data-dir=project_akiha/database/migrations=project_akiha/database/migrations",
        "--include-data-files=scripts/run_gpt_sovits_api.py=scripts/run_gpt_sovits_api.py",
        "--report=$CompilationReportPath",
        "--report-user-provided=build_mode=$BuildMode",
        "--report-user-provided=parallel_jobs=$(if ($FastBuild) { $Jobs } else { 'default' })",
        "--report-user-provided=lto=$(if ($FastBuild) { 'no' } else { 'default' })",
        "project_akiha/app/main.py"
    )
    if ($FastBuild) {
        $FastBuildArguments = @(
            $NuitkaArguments[0..1]
            "--jobs=$Jobs"
            "--lto=no"
            "--disable-cache=bytecode"
        )
        if ($DisableCompilerCache) {
            $FastBuildArguments += "--disable-cache=ccache"
        }
        $NuitkaArguments = @(
            $FastBuildArguments
            $NuitkaArguments[2..($NuitkaArguments.Count - 1)]
        )
    }
    $script:NuitkaArgumentsForReport = @($NuitkaArguments)
    $script:BuildLogPath = Join-Path $ReportDir "nuitka-build-$BuildStamp.log"

    Invoke-TimedCheckedCommand {
        $NativeErrorPreference = $ErrorActionPreference
        $NativeExitCode = 0
        try {
            # Windows PowerShell wraps native stderr status lines as error records.
            # Nuitka writes normal progress to stderr, so keep it visible and rely
            # on the native exit code instead of treating each line as terminating.
            $ErrorActionPreference = "Continue"
            & $PythonExecutable @NuitkaArguments 2>&1 |
                Tee-Object -FilePath $script:BuildLogPath
            $NativeExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $NativeErrorPreference
        }
        if ($NativeExitCode -ne 0) {
            throw "Nuitka exited with code $NativeExitCode."
        }
    } "Nuitka build"

    $script:CompilerCacheSummary = @(
        Select-String -LiteralPath $script:BuildLogPath -Pattern @(
            "cache hit",
            "cache miss",
            "cached C",
            "compiled C",
            "Nuitka-Scons"
        ) -SimpleMatch |
            Select-Object -Last 30 |
            ForEach-Object { $_.Line.Trim() }
    )

    $BuiltExePath = Join-Path $ResolvedOutputDir "main.dist\Akiha.exe"
    Invoke-TimedCheckedCommand {
        & $PythonExecutable -m project_akiha.tools.verify_windows_gui_subsystem $BuiltExePath
    } "Windows GUI subsystem check"

    $BuiltArtifactDir = Join-Path $ResolvedOutputDir "main.dist"
    Invoke-TimedCheckedCommand {
        & $PythonExecutable -m project_akiha.tools.verify_packaged_artifact $BuiltArtifactDir
    } "Packaged artifact check"
    $BuildOutcome = "passed"
}
finally {
    Pop-Location
    $FinalBuildObjectDirectory = Join-Path $ResolvedOutputDir "main.build"
    if (Test-Path -LiteralPath $FinalBuildObjectDirectory) {
        $script:BuildObjectCountAfter = @(
            Get-ChildItem -LiteralPath $FinalBuildObjectDirectory -File -Filter "*.o"
        ).Count
    }
    if ($CacheDirectory -and (Test-Path -LiteralPath $CacheDirectory)) {
        $script:CompilerCacheObjectCountAfter = @(
            Get-ChildItem -LiteralPath $CacheDirectory -Recurse -File -Filter "*.obj" -ErrorAction SilentlyContinue
        ).Count
    }
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
    if ($null -eq $OriginalZigGlobalCacheDir) {
        Remove-Item Env:ZIG_GLOBAL_CACHE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:ZIG_GLOBAL_CACHE_DIR = $OriginalZigGlobalCacheDir
    }
    if ($null -eq $OriginalZigLocalCacheDir) {
        Remove-Item Env:ZIG_LOCAL_CACHE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:ZIG_LOCAL_CACHE_DIR = $OriginalZigLocalCacheDir
    }
    $env:PATH = $OriginalPath
}

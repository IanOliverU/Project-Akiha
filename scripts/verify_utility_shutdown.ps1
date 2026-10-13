param(
    [string]$ExePath = "",
    [string]$SmokeRoot = "",
    [int]$TimeoutSeconds = 40
)
$ErrorActionPreference = "Stop"
if (-not $SmokeRoot) {
    $SmokeRoot = Join-Path $PWD ("dist/utility-shutdown-" + [guid]::NewGuid().ToString("N"))
}
if (Test-Path -LiteralPath $SmokeRoot) { throw "Smoke root must be new." }
$SmokeRoot = [IO.Path]::GetFullPath($SmokeRoot)
New-Item -ItemType Directory -Path $SmokeRoot | Out-Null
$report = Join-Path $SmokeRoot "shutdown.json"
$oldLocal = $env:LOCALAPPDATA
$oldApp = $env:APPDATA
$oldQt = $env:QT_QPA_PLATFORM
try {
    $env:LOCALAPPDATA = Join-Path $SmokeRoot "data"
    $env:APPDATA = $env:LOCALAPPDATA
    $env:QT_QPA_PLATFORM = "offscreen"
    $arguments = @("--utility-shutdown-smoke-report=`"$report`"")
    if ($ExePath) {
        $program = (Resolve-Path -LiteralPath $ExePath).Path
    } else {
        $program = (Resolve-Path .venv313/Scripts/python.exe).Path
        $arguments = @("-B", "-m", "project_akiha.app.main") + $arguments
    }
    $process = Start-Process -FilePath $program -ArgumentList $arguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $SmokeRoot "stdout.txt") `
        -RedirectStandardError (Join-Path $SmokeRoot "stderr.txt")
    $null = $process.Handle
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force
        throw "Shutdown smoke timed out; forced termination is a failed gate."
    }
    $code = $process.ExitCode
    $code | Set-Content (Join-Path $SmokeRoot "exit-code.txt")
    if ($code -ne 0 -or -not (Test-Path -LiteralPath $report)) {
        throw "Shutdown smoke failed with exit $code. See $SmokeRoot"
    }
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $result.passed) { throw "Lifecycle checks failed. See $report" }
    & .venv313/Scripts/python.exe -B -m project_akiha.tools.verify_smoke_log (Join-Path $SmokeRoot "data/Akiha/logs/app.log")
    if ($LASTEXITCODE -ne 0) { throw "Shutdown smoke log failed." }
    Write-Output "Graceful pending-clarification shutdown PASS; process exit=$code; evidence=$SmokeRoot"
} finally {
    $env:LOCALAPPDATA = $oldLocal
    $env:APPDATA = $oldApp
    $env:QT_QPA_PLATFORM = $oldQt
}

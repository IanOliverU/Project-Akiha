param(
    [string]$OutputDir = '',
    [string]$PythonExe = '',
    [switch]$SourceOnly
)

# One owner-run handoff. All application profiles are new synthetic directories.
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PreviousLocation = Get-Location
$PreviousPath = $env:PATH
$PreviousLocalAppData = $env:LOCALAPPDATA
$PreviousAppData = $env:APPDATA
$Results = [System.Collections.Generic.List[object]]::new()
try {
    Set-Location -LiteralPath $RepoRoot
    if (-not $PythonExe) { $PythonExe = Join-Path $RepoRoot '.venv313/Scripts/python.exe' }
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
    if (-not $OutputDir) {
        $OutputDir = Join-Path $RepoRoot ('dist/stabilization-owner-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6))
    }
    . (Join-Path $PSScriptRoot 'build_path_guard.ps1')
    $OutputDir = Assert-AkihaBuildDirectory -ProjectRoot $RepoRoot -Path $OutputDir
    if (Test-Path -LiteralPath $OutputDir) { throw 'OutputDir must be new.' }
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    # Isolate even diagnostic entry points that bypass normal application startup.
    # Child smoke scripts can select their own fresh subprofiles as usual.
    $env:LOCALAPPDATA = Join-Path $OutputDir 'ambient-localappdata'
    $env:APPDATA = Join-Path $OutputDir 'ambient-appdata'
    $GitDirectory = Split-Path -Parent (Get-Command git).Source
    $PythonBase = (& $PythonExe -c 'import sys; print(sys.base_prefix)').Trim()
    $env:PATH = @((Split-Path -Parent $PythonExe), $PythonBase, $env:SystemRoot,
        (Join-Path $env:SystemRoot 'System32'),
        (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0'), $GitDirectory) -join ';'

    function Invoke-Gate {
        param([string]$Name, [scriptblock]$Command)
        # Native stderr progress is captured; success requires native exit 0.
        $SavedPreference = $ErrorActionPreference
        $Code = 1
        try {
            $ErrorActionPreference = 'Continue'
            & $Command *> (Join-Path $OutputDir "$Name.log")
            $Code = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $SavedPreference }
        $Results.Add([pscustomobject]@{ gate = $Name; exit = $Code })
        Write-Host "$Name exit=$Code"
        return ($Code -eq 0)
    }

    $Source = Invoke-Gate 'source' {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_phase13c.ps1 -PythonExe $PythonExe -OutputDir (Join-Path $OutputDir 'source')
    }
    $FullLog = Join-Path $OutputDir 'source/full.log'
    if ($Source -and (Select-String -LiteralPath $FullLog -Pattern 'OK \(skipped=' -Quiet)) {
        $Results.Add([pscustomobject]@{ gate = 'source-completeness'; exit = 1 })
        Write-Host 'Source tests include skips; resolve them before package acceptance.'
        $Source = $false
    }
    $Pins = Invoke-Gate 'pins' { & $PythonExe -B -m project_akiha.tools.build_identity check }
    $Dependencies = Invoke-Gate 'pip-check' { & $PythonExe -B -m pip check }
    # Source gate includes cleanup guards, all new regressions, single-process
    # discovery, import gate, quality, ten historical Qt pairs and source smoke.
    if ($Source -and $Pins -and $Dependencies -and -not $SourceOnly) {
        $Candidate = Join-Path $OutputDir 'candidate'
        $Work = Join-Path $OutputDir 'work'
        $Build = Invoke-Gate 'build' {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_akiha_pyinstaller.ps1 -PythonPath $PythonExe -OutputDir $Candidate -WorkDir $Work -Clean -SkipQualityChecks
        }
        if ($Build) {
            $Exe = Join-Path $Candidate 'Akiha/Akiha.exe'
            $null = Invoke-Gate 'upgrade-startup-restart' {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_app.ps1 -ExePath $Exe -SmokeRoot (Join-Path $OutputDir 'package-profiles') -RunExistingDataPass -RunUpgradePass
            }
            $null = Invoke-Gate 'single-instance' {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_packaged_single_instance.ps1 -ExePath $Exe -SmokeRoot (Join-Path $OutputDir 'ipc-profile')
            }
            $null = Invoke-Gate 'graceful-shutdown' {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_utility_shutdown.ps1 -ExePath $Exe -SmokeRoot (Join-Path $OutputDir 'shutdown-profile')
            }
            $null = Invoke-Gate 'offline-provider-runtimes' {
                # This legacy verifier joins its arguments to the checkout root.
                $RelativeExe = Resolve-Path -LiteralPath $Exe -Relative
                $RelativeReport = Join-Path (Resolve-Path -LiteralPath $OutputDir -Relative) 'offline-runtimes.json'
                $OfflineRoot = Join-Path $OutputDir 'offline-profile'
                $OfflineData = Join-Path $OfflineRoot 'Akiha'
                New-Item -ItemType Directory -Path $OfflineData -ErrorAction Stop | Out-Null
                [IO.File]::WriteAllText((Join-Path $OfflineData 'user_config.toml'), "[ai]`nprovider = `"mock`"`n[voice]`nenabled = false`noutput_provider = `"disabled`"`n", [Text.UTF8Encoding]::new($false))
                $AmbientLocal = $env:LOCALAPPDATA
                $AmbientRoaming = $env:APPDATA
                try {
                    $env:LOCALAPPDATA = $OfflineRoot
                    $env:APPDATA = $OfflineRoot
                    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_packaged_provider_runtimes.ps1 -ExePath $RelativeExe -ReportPath $RelativeReport -SkipGeminiNetwork
                } finally {
                    $env:LOCALAPPDATA = $AmbientLocal
                    $env:APPDATA = $AmbientRoaming
                }
            }
        }
    }
    $Results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputDir 'results.json') -Encoding UTF8
    Write-Output "Evidence: $OutputDir"
    Write-Output 'Owner acceptance remains pending. Source/startup smoke forced cleanup is not graceful shutdown; offline runtime skips are not live-provider passes.'
    if (@($Results | Where-Object { $_.exit -ne 0 }).Count) { exit 1 }
    exit 0
}
finally {
    $env:PATH = $PreviousPath
    $env:LOCALAPPDATA = $PreviousLocalAppData
    $env:APPDATA = $PreviousAppData
    Set-Location -LiteralPath $PreviousLocation
}

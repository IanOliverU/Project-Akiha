param(
    [string]$OutputDir = "",
    [string]$PythonExe = "",
    [switch]$InventoryOnly
)

# Verification only: no packaging, cleanup, settings changes or IPC overrides.
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousLocation = Get-Location
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$gateResults = @{}
$verificationExit = 1
try {
    Set-Location -LiteralPath $repoRoot
    if (-not $PythonExe) {
        $PythonExe = Join-Path $repoRoot '.venv313\Scripts\python.exe'
    }
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Python executable not found: $PythonExe"
    }
    if (-not $OutputDir) {
        $OutputDir = Join-Path $repoRoot ('dist\phase13c-verification-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    }
    New-Item -ItemType Directory -Path $OutputDir -ErrorAction Stop | Out-Null
    $OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
    $env:TEMP = Join-Path $OutputDir 'temp'
    $env:TMP = $env:TEMP
    New-Item -ItemType Directory -Path $env:TEMP -ErrorAction Stop | Out-Null

    function Invoke-PythonGate {
        param([string]$Name, [string[]]$PythonArgs)
        & $PythonExe @PythonArgs *> (Join-Path $OutputDir "$Name.log")
        $gateCode = $LASTEXITCODE
        $gateResults[$Name] = $gateCode
        $gateCode | Set-Content -LiteralPath (Join-Path $OutputDir "$Name.exitcode.txt")
        Write-Output "$Name exit=$gateCode"
    }

    # A saved script avoids Windows PowerShell's Python -c quoting problems.
    $staticScript = Join-Path $OutputDir 'inventory_static.py'
    @'
import ast
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

output = Path(__file__).parent
suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test
ids = [test.id() for test in flatten(suite)]
assert len(ids) == len(set(ids)), 'Duplicate test IDs'
assert not any('_FailedTest' in test for test in ids), 'Discovery import failure'
output.joinpath('inventory.json').write_text(json.dumps(ids, indent=2) + '\n')
files = sorted(p for root in ('project_akiha', 'tests') for p in Path(root).rglob('*.py'))
for path in files:
    compile(path.read_bytes(), str(path), 'exec')
for path in Path('project_akiha/core').rglob('*.py'):
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
        modules = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                   [a.name for a in node.names] if isinstance(node, ast.Import) else [])
        assert not any(m.startswith(('PySide6', 'project_akiha.ui', 'project_akiha.app',
            'project_akiha.services', 'project_akiha.providers', 'project_akiha.database',
            'project_akiha.integrations')) for m in modules), str(path)
hash_files = sorted(p for root in ('project_akiha', 'tests', 'scripts', 'docs/phases/phase-13-assistant-utilities')
    for p in Path(root).rglob('*') if p.is_file() and p.suffix in ('.py', '.sql', '.ps1', '.md'))
output.joinpath('file-hashes.json').write_text(json.dumps({p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in hash_files}, indent=2) + '\n')
for name, args in [('head', ['rev-parse', 'HEAD']), ('status', ['status', '--short'])]:
    result = subprocess.run(['git', '-c', 'safe.directory=' + Path.cwd().as_posix(), *args],
        capture_output=True, text=True)
    output.joinpath(name + '.txt').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, 'Git identity capture failed'
print('Inventory:', len(ids), 'unique test IDs')
print('Compile:', len(files), 'Python files PASS')
print('Core static boundaries: PASS')
print('Timer tests:', sum('.test_phase13c_timers.' in name for name in ids))
'@ | Set-Content -LiteralPath $staticScript -Encoding UTF8
    Invoke-PythonGate -Name 'inventory-static' -PythonArgs @('-B', $staticScript)
    if (-not $InventoryOnly) {
        Invoke-PythonGate -Name 'cleanup-guard' -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.services.test_build_cleanup_guard', '-v')
        Invoke-PythonGate -Name 'timers' -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.services.test_phase13c_timers', 'tests.unit.app.test_phase13c_timers', '-v')
        Invoke-PythonGate -Name 'focused' -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.services.test_phase13c_timers', 'tests.unit.core.actions.test_models_registry', 'tests.unit.core.actions.test_validation', 'tests.unit.core.actions.test_permissions', 'tests.unit.database.test_migrator', 'tests.unit.services.test_package_artifact', 'tests.unit.services.test_command_envelope', 'tests.unit.services.test_assistant_action_bridge.AssistantActionRequestParserTest', 'tests.unit.app.test_proactive_delivery_controller', 'tests.unit.services.test_speech_identity', '-v')
        Invoke-PythonGate -Name 'security-db-shutdown' -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.database.test_sqlite_notification_repository', 'tests.unit.services.test_action_clarification', 'tests.unit.app.test_shutdown', 'tests.unit.core.utilities.test_clock', 'tests.unit.core.utilities.test_contracts', '-v')
        Invoke-PythonGate -Name 'boundaries' -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.services.test_phase13b_corrections.CorrectionOwnershipTest', 'tests.unit.services.test_phase13b_corrections.CorrectionProviderPathTest', 'tests.unit.core.actions.test_path_policy', 'tests.unit.core.actions.test_passive_files', 'tests.unit.core.actions.test_tool_schemas', 'tests.unit.core.behavior.test_notification_policy', 'tests.unit.services.test_smoke_log', '-v')
        # The required discovery gate runs all tests together in ONE process.
        Invoke-PythonGate -Name 'full' -PythonArgs @('-B', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v')
        for ($run = 1; $run -le 10; $run++) {
            Invoke-PythonGate -Name "qt-$run" -PythonArgs @('-B', '-m', 'unittest', 'tests.unit.ui.test_behavior_history_window.BehaviorHistoryWindowTest.test_clear_matching_emits_selected_filters_after_confirmation', 'tests.unit.ui.test_hosted_live_session_worker.HostedLiveSessionThreadTest.test_tool_task_failure_stops_visibly_instead_of_stranding_turn', '-v')
        }
        Invoke-PythonGate -Name 'ruff' -PythonArgs @('-B', '-m', 'ruff', 'check', 'project_akiha', 'tests')
        Invoke-PythonGate -Name 'black' -PythonArgs @('-B', '-m', 'black', '--check', 'project_akiha', 'tests')
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot 'scripts\smoke_source_app.ps1') -SmokeRoot (Join-Path $OutputDir 'smoke-data') -PythonExe $PythonExe *> (Join-Path $OutputDir 'smoke.log')
        $gateResults['smoke'] = $LASTEXITCODE
        $gateResults['smoke'] | Set-Content -LiteralPath (Join-Path $OutputDir 'smoke.exitcode.txt')
        git -c "safe.directory=$($repoRoot.Replace('\', '/'))" diff --check *> (Join-Path $OutputDir 'diff-check.log')
        $gateResults['diff-check'] = $LASTEXITCODE
        $gateResults['diff-check'] | Set-Content -LiteralPath (Join-Path $OutputDir 'diff-check.exitcode.txt')
    }
    $gateResults | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDir 'gate-results.json')
    $verificationExit = [int](@($gateResults.Values | Where-Object { $_ -ne 0 }).Count -gt 0)
    Write-Output "Return this verification folder: $OutputDir"
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    Set-Location -LiteralPath $previousLocation.Path
}
exit $verificationExit

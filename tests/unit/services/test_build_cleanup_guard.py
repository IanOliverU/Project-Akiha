"""Execute the real PowerShell guards without performing a clean build."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows PowerShell build guard")
class BuildCleanupGuardTest(unittest.TestCase):
    def setUp(self):
        self.checkout = Path(__file__).resolve().parents[3]
        parent = self.checkout / "dist" / "guard-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(parent.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.fixture = self.root / "project"
        (self.fixture / "dist").mkdir(parents=True)

    def run_probe(self, code):
        script = self.root / "probe.ps1"
        script.write_text(
            "param($Root, $Checkout)\n$ErrorActionPreference = 'Stop'\n"
            ". (Join-Path $Checkout 'scripts/build_path_guard.ps1')\n" + code,
            encoding="utf-8-sig",
        )
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Root",
                str(self.fixture),
                "-Checkout",
                str(self.checkout),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_relative_absolute_and_case_insensitive_paths(self):
        self.run_probe("""
$paths = Assert-AkihaBuildPaths $Root 'dist/candidate' 'dist/work'
if ($paths.OutputDir -ne (Join-Path $Root 'dist/candidate')) { throw 'Wrong output' }
$upperOutput = Join-Path $Root 'DIST/candidate'
Assert-AkihaBuildPaths $Root $upperOutput (Join-Path $Root 'dist/work') | Out-Null
Assert-AkihaCleanupTree $Root (Join-Path $Root 'dist/work')
""")

    def test_roots_parents_source_and_prefix_collision_fail_closed(self):
        self.run_probe("""
$bad = @($Root, (Split-Path $Root -Parent), [IO.Path]::GetPathRoot($Root),
    'dist', 'project_akiha', (Join-Path $Root 'dist-other/work'))
foreach ($path in $bad) {
    $rejected = $false
    try { Assert-AkihaBuildDirectory $Root $path | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Unsafe directory accepted' }
}
""")

    def test_ambiguous_device_traversal_and_wildcard_paths_rejected(self):
        self.run_probe("""
foreach ($path in @('', ' ', '.', '..', 'dist/../source', 'dist/./work',
    'dist/work.', 'dist/work ', 'dist/*',
    'C:relative', '\\\\server\\share', '\\\\?\\C:\\work')) {
    $rejected = $false
    try { Assert-AkihaBuildDirectory $Root $path | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Ambiguous path accepted' }
}
""")

    def test_overlapping_output_and_work_rejected_both_directions(self):
        self.run_probe("""
foreach ($pair in @(@('dist/work','dist/work'), @('dist/work','dist/work/child'),
    @('dist/work/child','dist/work'))) {
    $rejected = $false
    try { Assert-AkihaBuildPaths $Root $pair[0] $pair[1] | Out-Null }
    catch { $rejected = $true }
    if (-not $rejected) { throw 'Overlapping directories accepted' }
}
""")

    def test_file_ancestor_rejected_and_ordinary_tree_preserved(self):
        self.run_probe("""
$work = Join-Path $Root 'dist/work'
New-Item -ItemType Directory -Path $work | Out-Null
$sentinel = Join-Path $work 'keep.txt'
Set-Content -LiteralPath $sentinel 'synthetic sentinel'
Assert-AkihaCleanupTree $Root $work
if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Guard mutated tree' }
$rejected = $false
try { Assert-AkihaBuildDirectory $Root ($sentinel + '/child') | Out-Null }
    catch { $rejected = $true }
if (-not $rejected) { throw 'File ancestor accepted' }
""")

    def test_actual_builder_refuses_root_before_python_or_cleanup(self):
        self.run_probe("""
$rejected = $false
try {
    & (Join-Path $Checkout 'scripts/build_akiha_pyinstaller.ps1') `
        -WorkDir $Checkout -Clean -PythonPath 'missing-python.exe'
} catch {
    $rejected = $_.Exception.Message -like '*strict descendants*'
}
if (-not $rejected) { throw 'Actual builder did not reject root before Python' }
""")

    def test_junction_ancestor_and_nested_cleanup_link_rejected(self):
        self.run_probe("""
$outside = Join-Path $Root 'keep'
$work = Join-Path $Root 'dist/work'
New-Item -ItemType Directory -Path $outside, $work | Out-Null
$link = Join-Path $work 'link'
New-Item -ItemType Junction -Path $link -Target $outside | Out-Null
try {
    $ancestorRejected = $false
    $treeRejected = $false
    try { Assert-AkihaBuildDirectory $Root ($link + '/child') | Out-Null }
    catch { $ancestorRejected = $true }
    try { Assert-AkihaCleanupTree $Root $work } catch { $treeRejected = $true }
    if (-not $ancestorRejected -or -not $treeRejected) { throw 'Junction accepted' }
    if (-not (Test-Path -LiteralPath $outside)) { throw 'Guard mutated target' }
} finally {
    # Remove only this fixture's link, never recurse into its target.
    [IO.Directory]::Delete($link)
}
""")

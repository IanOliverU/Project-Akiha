# Phases 1–12 current-HEAD stabilization — 2026-10-13

Baseline HEAD: `88a7e6b56322759570dc0c9ee5c72b9fbf88a147`. Continuous owner
authorization covers reconciliation, S02, T02, A01, P02, documentation and final
verification. No commit/push, new feature or live application-data access.
Existing UI/Phase 13 documentation edits were present at task start and preserved.
Historical audits/acceptance records are unchanged; their old verdicts are not
current defect claims. Renewed final acceptance remains pending owner results.

## Reconciliation of all 11 original findings

| ID | Current disposition | Evidence / remaining limit |
| --- | --- | --- |
| S01 | Previously resolved; preserved | SQLite WAL/SHM/journal artifact deny checks retained; current artifact/migrator regressions pass. |
| U01 | Previously resolved; preserved | Atomic migration/receipt transaction and rollback regressions retained; no new migration or repair of live databases. |
| T01 | Previously resolved; preserved | Original behavior regressions remain enabled, including valid DDL/data followed by invalid SQL. |
| D01 | Previously resolved; preserved | Voice V0–V8 closure retained; current README/index drift separately corrected. |
| P01 | Previously resolved; preserved | Phase 13 cleanup containment/overlap/reparse guards already implemented. All seven current guard checks pass, including real junction verification. |
| T03 | Historical failure superseded | Subsequent normal Windows single-process/Qt-pair evidence addresses the historical failure. Current full discovery completes normally; skips described below are not passes. No accepted phase reopened. |
| T04 | Historical mismatch superseded | Phase 13B path/readiness corrections and later passing evidence retained; current action/permission regressions pass. |
| S02 | Resolved in source | Both synthetic unexpected-error paths fail privacy checks before fix. Fixed warning reason codes omit exception object, dynamic type/message and traceback. Gmail health recovery and Discord reconnect/backoff retained. |
| T02 | Resolved in source and package | Old `RunExistingDataPass` was restart-only. New `RunUpgradePass` independently upgrades frozen populated v14/v15 profiles, checks preservation and complete schema, then restarts. All four upgrade/restart passes succeeded. No owner data used. |
| A01 | Resolved in source | Four concrete Windows functions moved unchanged to injected adapters; core execution validation/timeouts/cancellation/results retained. Automatic AST import/platform gate is in unittest discovery and verification script. |
| P02 | Resolved for pinned workflow and attribution | Full existing packaging environment pinned without upgrades. Builders reject dependency/source drift and record source/dependency/artifact identity. Fresh candidate identity passes. Clean-environment provisioning, archive authentication, byte-identical rebuild and new Nuitka compilation are not claimed. |

## Bounded changes and review

- S02: Gmail/Discord provider handlers; new synthetic log-capture regressions.
- T02: packaged smoke, historical fixture SQL/provenance, fixture create/verify
  CLI and regressions for old schema, grant corruption and missing audit table.
  Complete schema comparison covers sqlite_master SQL (tables, indexes,
  constraints, views/triggers), ordered version/name receipts, integrity and
  foreign keys. Stable pet XP/level/currency are checked; runtime need decay is
  allowed to settle normally. Fixture creation refuses existing profiles.
- A01: core executors, composition root and new Windows adapter. Callable
  injection is required, so core never selects a concrete OS implementation.
  Adapter probes cover exact path/default handler, no-shell launch, exact-process
  WM_CLOSE and handle closure; composed wiring is checked for all four adapters.
- P02: release pins, identity CLI/regressions and both builders; guarded clean
  targets unchanged. All installed optional hook inputs are pinned, not merely
  the top-level dependency closure. Full source identity distinguishes dirty
  source from HEAD; no claim that this uncommitted candidate equals pristine HEAD.
- Documentation/handoff: README, documentation index, codebase map, release
  workflow, this register and `scripts/verify_stabilization.ps1`.

Review is an agent-run separate code/probe review, not independent human approval.
It checks moved function equivalence to HEAD, fixture historical provenance,
failure admission, downstream permission checks and identity completeness.
No safeguards, tests, IPC, GC, confirmation or permissions were weakened.

## Verification and candidate

Evidence folder: `dist/stabilization-20261013` (ignored; synthetic data only).
Initial full inventory: 2,022 unique IDs. Full discovery: **2,022 tests,
92.889 seconds, OK, exit 0, three existing symlink-privilege skips**.
The skips are directory-search, file-search and path-policy symlink checks;
Windows reports WinError 1314. They remain unverified in this run, despite the
retained later-owner evidence for historical gates. Owner handoff refuses final
source completeness if the full run still has skips.

Focused verification: S02 22 tests/0.004s; T02+migrator/artifact 25/1.823s;
A01 adapter/boundary/action/integration 24/0.947s; core actions 65/0.136s
(three symlink skips); final bounded selection 49/2.333s. All exit 0.
Cleanup: seven/1.634s, no skips, exit 0. Source-wide Ruff passes; Black checks
589 Python files unchanged. Five modified PowerShell scripts parse successfully.
Final verification/build/package results will be appended as actually run.

The first clean candidate build completed in 137.292s (PyInstaller 115.915s),
with artifact, Windows GUI and source/dependency/artifact identity checks passing.
After the usage-limit interruption the execution token changed; restricted
package startup created no application profile, IPC failed before startup and
shutdown timed out. Restricted default TEMP writes and Black's worker startup
were also blocked. Those failures are retained, not relabeled as passes.

Authorized normal Windows execution then passed fresh/restart schema checks and
exposed a synthetic fixture defect: selecting the unavailable dress appearance
caused normal startup to repair it, correctly failing preservation. The fixture
now seeds the valid seifuku selection and a regression checks its current asset
contract. No runtime/migration safeguard was changed. Build identity now scopes
Git's ownership exception to the current invocation, covering a token change
without modifying global Git configuration; a regression verifies this.
These two fixture/tooling corrections are followed by fresh final verification.

## One consolidated owner handoff

Run from normal Windows PowerShell with symlink privilege available:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/verify_stabilization.ps1
```

The script captures inventory/hashes, all source gates/full discovery, historical
Qt repetitions, cleanup guards, release pins/consistency, fresh guarded candidate,
artifact/GUI checks, genuine v14/v15 packaged upgrades/restarts, single-instance,
default-profile graceful Quit and offline provider-runtime evidence. Any failure
or skipped full-suite gate remains unresolved; dependent build work is withheld.
It never installs dependencies or uses an existing application profile.

For manual results, use the script-produced candidate with a new synthetic
LOCALAPPDATA profile beneath its evidence folder, never the live application
profile. Record confirmed passive-file/directory opening and allowlisted
launch/normal close, cancellation and denial after grant revocation, plus any
previously pending candidate/UI/configured-runtime checks. Prior accepted phases
and functional approval remain intact. No prior checklist's instruction to test
the existing profile applies to this task. Offline import/client mocks and forced
startup cleanup do not establish real configured voice/TTS/Gemini shutdown or
native DPI acceptance. Final acceptance remains owner-controlled.

## Final results and identity

Final evidence: `dist/stabilization-20261013-final`. Normal Windows source
invocation and package checks used `scripts/verify_stabilization.ps1`, with all
application profiles confined to newly created project/dist directories.

| Gate | Exact final result |
| --- | --- |
| Inventory / compilation / core boundary | 2,024 unique IDs; 589 Python files compiled; pass, exit 0. Every inventory ID occurs in full output. |
| Full discovery (`python -B -m unittest discover -s tests -t . -v`) | **2,024 tests, 94.055s, OK, zero skips, exit 0.** |
| Cleanup guard | 7 tests, 1.489s, no skips, exit 0; includes real junction assertions. |
| Timer selection | 38 tests, 6.499s, no skips, exit 0. |
| Focused selection | 142 tests, 2.399s, no skips, exit 0. |
| Security/database/shutdown selection | 63 tests, 1.259s, no skips, exit 0. |
| Boundary selection | 39 tests, 0.089s, no skips, exit 0. |
| Historical Qt pair | Ten runs of two tests each, all OK, no skips, exit 0. |
| Ruff / Black / diff | Source-wide checks pass; Black leaves 589 Python files unchanged; exit 0. |
| Source startup/schema/log smoke | Exit 0; forced cleanup (-1) is startup evidence only. |
| Release pin / `pip check` | 131 pinned installed distributions plus the source-identified editable application; no broken requirements; exit 0. |
| Fresh guarded build | 159.091s total; PyInstaller, artifact deny scan, GUI-subsystem and input/artifact identity all pass, exit 0. |
| Packaged fresh/restart smoke | Both pass schema/log/window checks, exit 0. |
| Packaged historical v14/v15 upgrade/restart | Four passes: complete 20-table target schema plus indexes/constraints, ordered migrations 1–16, integrity/FKs, prior records/grants and inbox high water; exit 0. |
| Packaged single instance | Primary remains running; secondary activation exits 0. |
| Packaged pending-clarification Quit | Process exit 0; all eight lifecycle booleans true. Default isolated profile only. |
| Independent review/probes | Four moved adapters AST-equivalent to HEAD; 15 historical migration sources/hash receipts verified; two exceptions whose `__str__` raises are never formatted; pass. |
| Actual bundled adapter binding | All four embedded Windows adapter functions/nested bytecode, constants and names match current source; pass. |
| Corrected offline gate | Actual saved handoff script block executed with new synthetic profile and verified environment restoration; exit 0. SDK import/client construction pass; Gemini network and GPT-SoVITS health are explicitly skipped. |

The original end-to-end handoff exited 1 at its last offline step: the legacy
verifier rejected an absolute path. Its correction exposed a second test-profile
assumption: the default output provider is GPT-SoVITS even with voice disabled,
and the local API was unavailable. Both failures are retained. The handoff now
passes relative arguments and creates an explicit disabled-TTS offline profile;
the actual corrected script block passes. No failed real-TTS health check was
reclassified as a pass, and the full corrected wrapper is left for owner rerun.
All earlier source/build/upgrade/IPC/shutdown results remain unchanged.

Candidate (keep the entire directory together):
`dist/stabilization-20261013-final/candidate/Akiha/Akiha.exe`.

| Identity | Value |
| --- | --- |
| Source HEAD | `88a7e6b56322759570dc0c9ee5c72b9fbf88a147` |
| HEAD Git tree | `db81c5765a0deee7ad8aa3a337fdbd0c47c431e0` |
| Captured dirty build-source tree SHA-256 | `f564ed5f158e1413fc7215e25862f8150f528e64bfcf292732a0edc6820a2e2e` |
| EXE SHA-256 | `a0e7041d3bca4de106e6bbdf082e2b3aa280bd98d116e56a48d439af08246496` |
| Artifact tree SHA-256 (1,809 files) | `4bafd4b1905bdf90c48c1e74eeb21d577e164e62060c7e7ff53d88baedbb546f` |
| Complete receipt | `dist/stabilization-20261013-final/candidate/build-reports/identity-20261013-123610.json` |

Python 3.13.14, PyInstaller 6.22.2, hooks 2026.6. The receipt inventories all
132 distributions (including the editable application), source input hashes and
every artifact hash. After building, only the handoff's offline call/profile
correction and this final documentation addendum changed; packaged runtime,
tests, dependencies, migrations and assets remain identical to the recorded
build inputs. These differences are explicitly reconciled, not presented as an
unchanged pristine-HEAD build.

No reproduced runtime finding remains open from the original register. Remaining
unverified work is owner candidate acceptance, real configured microphone/TTS/
Gemini and native interaction/DPI checks where still pending, clean-environment
dependency provisioning, archive authentication/byte-identical rebuild and a
fresh Nuitka compilation. Dependency vulnerability auditing, signing and public
distribution remain existing backlog exclusions. Historical restriction failures
and earlier acceptance are retained. No commit or push occurred.

## Exact files changed by this task

The following 27 files are the separately reviewable changes. The nine existing
UI/Phase 13 documentation modifications/additions present at task start were
preserved and are not counted as this task's edits.

```text
README.md
docs/README.md
docs/audits/STABILIZATION_CURRENT_HEAD_2026-10-13.md
docs/phases/phase-06-packaging/BUILD_RELEASE.md
docs/reference/CODEBASE_STRUCTURE.md
project_akiha/app/main.py
project_akiha/core/actions/executors.py
project_akiha/integrations/discord/gateway.py
project_akiha/integrations/gmail/provider.py
project_akiha/providers/windows_actions.py
project_akiha/tools/build_identity.py
project_akiha/tools/verify_core_boundaries.py
project_akiha/tools/verify_upgrade_fixture.py
requirements/release-win-py313.txt
scripts/build_akiha_nuitka.ps1
scripts/build_akiha_pyinstaller.ps1
scripts/smoke_packaged_app.ps1
scripts/verify_phase13c.ps1
scripts/verify_stabilization.ps1
tests/fixtures/upgrades/phase12-v14.sql
tests/fixtures/upgrades/phase13c-v15-delta.sql
tests/fixtures/upgrades/provenance.json
tests/unit/core/test_import_boundaries.py
tests/unit/integrations/test_logging_privacy.py
tests/unit/providers/test_windows_actions.py
tests/unit/services/test_build_identity.py
tests/unit/services/test_upgrade_fixture.py
```

## Owner-run complete handoff reconciled — 2026-10-13

Owner supplied `dist/stabilization-owner-20261013-205156-1f62e3`.
All eight top-level stages and every source subgate exit 0. The corrected
wrapper has now completed end to end; its earlier pending rerun is satisfied.
Full discovery: **2,024 tests, 95.828s, OK, zero skips**. All 2,024 unique
inventory IDs occur in the output. Source input hashes exactly match the current
reviewed tree before this documentation-only addendum. All 1,809 artifact file
hashes were independently rechecked against the build receipt. Both historical
upgrade profiles still pass complete-schema and preservation verification.
Shutdown exits normally with all eight lifecycle checks true.

Use this owner's newly built candidate for renewed acceptance:
`dist/stabilization-owner-20261013-205156-1f62e3/candidate/Akiha/Akiha.exe`.

- Captured dirty source tree SHA-256:
  `861f5f3b0f7b990dcb67e5635b7171092bb5d8f91975bf18d511a50dfd6dc4ef`.
- EXE SHA-256:
  `1f5e1016d319345fe3aabb16080a83207fc994da3ac9ab3ec236ec4006505786`.
- Artifact tree SHA-256:
  `866a7042383f38e59d5ad68cf6cde09e5465cc974d411d574f11436702af9c17`.
- Receipt: `candidate/build-reports/identity-20261013-125407.json` beneath
  the owner evidence folder; reconciliation: `owner-reconciliation.json`.

Offline SDK import/client construction passed. Gemini network and GPT-SoVITS
health remain explicitly skipped, not live-provider passes. The owner's message
`B` and console screenshot establish submission of automated evidence, not
explicit final acceptance. Final acceptance and remaining manual/reproduction
limits stay pending. No commit or push occurred; previous failures remain intact.

## Publication authorization — 2026-10-13

After the complete owner handoff was reconciled, the owner explicitly requested
committing and pushing all working-tree changes, including the pre-existing
Phase 13/UI documentation reconciliation. This publication authorization does
not replace the separately pending final candidate acceptance or live-provider
checks. The candidate receipts retain their original pre-commit build identity;
no package rebuild is implied by creating a Git checkpoint.

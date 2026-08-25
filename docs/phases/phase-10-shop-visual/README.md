# Phase 10: Shop, Appearance, And Autonomous Pet Expansion

**Status:** Complete - formally closed 2026-08-24

## Phase Goal

Extend the Phase 9 care loop with a lightweight trusted shop, three complete
canonical appearances, and data-driven autonomous activities that make Akiha
feel alive without turning the companion into a wardrobe manager or demanding
virtual-pet game.

Akiha remains, in priority order, an AI companion, desktop pet, and local
assistant. Shop, status, care, and activity systems support that experience.

## Approved Scope Decision

The layered-cosmetic and wardrobe design built during 10A-10E was retired
before renderer integration. Active Phase 10 code supports only these closed
appearance identities:

- `seifuku`
- `dress`
- `vermillion`

Each identity represents one complete, owner-approved animation manifest.
There are no equipment slots, layers, compositing rules, loadouts, or cosmetic
combinations. Seifuku is the default and remains available without purchase.
Dress and Vermillion stay explicitly unavailable until complete approved asset
sets exist.

## Hard Architecture Rules

1. `assets/animations/akiha/standing/000.png` remains the immutable canonical
   Seifuku source sprite.
2. Appearance selection swaps a complete trusted manifest. It never recolors,
   redraws, regenerates, interpolates, or overlays canonical pixels.
3. Shop purchases remain atomic, idempotent, non-stackable, and unable to make
   currency negative.
4. Dialogue and provider output cannot purchase products, select appearances,
   mutate pet state, or manipulate renderer frames directly.
5. Catalog and appearance definitions are closed trusted local TOML. They never
   accept provider-defined paths, URLs, scripts, or executables.
6. Pet statistics are structured state. They are not inferred by parsing
   Japanese or English dialogue.
7. Autonomous activities are selected by a deterministic pet behavior
   controller, independent of the LLM and assistant-action system.
8. Missing or unapproved assets fail closed to the selected safe appearance and
   idle behavior.
9. Builds remain deferred until 10J. Phase development uses Python 3.13 source
   verification.

## Active Architecture

### Shop and appearance

```text
Trusted ShopCatalog
    -> ShopService
        -> atomic purchase / durable ownership
            -> AppearanceService
                -> selected complete AppearanceId
                    -> trusted AnimationManifest
                        -> existing AssetAnimationProvider
                            -> SpritePetRenderer
```

`ShopService` owns catalog browsing, inspection, purchasing, and inventory.
`AppearanceService` separately owns availability, ownership checks, selection,
and trusted manifest resolution. The renderer receives a normal animation
provider and requires no wardrobe-specific code.

### Autonomous activity

```text
Pet State + Presence + Mood + Time + Current Activity
    -> ActivityBehaviorController
        -> bounded ActivityId
            -> approved ActivityManifest
                -> existing animation/controller boundaries
                    -> SpritePetRenderer
```

This pipeline belongs to 10H. The LLM may eventually propose a bounded
interaction, but it does not schedule autonomous activities or name animation
files.

Phase 10H implements that boundary through a strict local manifest at
`assets/animations/activities.toml`, a framework-free deterministic scheduler,
and a preemptible application controller. The closed activity vocabulary is:

- `quiet_idle` -> approved `idle` animation
- `wander` -> approved `walking` animation
- `rest` -> approved `sleeping` animation

There are no placeholder entries for reading, tea, play, or other missing
artwork. Those activities cannot enter the manifest until their complete
appearance assets pass the 10G gate.

Selection uses only typed user activity, companion mood, pet state, time,
current animation, fixed eligibility rules, and cooldown history. It does not
inspect conversation text, transcripts, provider output, memories, files, or
assistant-action content. The scheduler is inactive while the user is active
and fails closed to normal idle behavior when its trusted manifest is invalid.

The runtime priority order is mechanical:

```text
drag > voice > direct pet control > care reaction > autonomous activity
```

Voice listening/thinking/speaking, dragging, care, direct walk/sleep/wake,
opening Chat/Settings, and renewed user activity cancel an autonomous session.
Completion and cancellation return safely to idle unless a higher-priority
direct transition already owns the animation. Started, completed, and
cancelled lifecycle events contain only activity ID, animation state, bounded
timing, source, and cancellation reason, and are recorded in local behavior
history.

## Persistence And Compatibility

Migration `0011_shop_inventory.sql` introduced transaction, inventory, and
historical equipment tables. The transaction and inventory tables remain
active. `shop_equipment` is retained only as inert schema history so existing
databases stay compatible; no current repository, service, or UI reads or
writes it.

Migration `0012_appearance_selection.sql` adds one constrained singleton row:

- appearance ID restricted to `seifuku`, `dress`, or `vermillion`
- timezone-aware selected timestamp
- safe default of `seifuku`

An existing selection that becomes unavailable or loses required ownership is
repaired to Seifuku during service initialization. Inventory and transaction
history are never deleted by that repair.

## Trusted Data Contracts

`project_akiha/config/shop_catalog.toml` uses schema version 2. A product is a
complete non-default appearance and contains only a stable item ID, display
name, category, appearance ID, price, availability, level requirement, and
catalog version. The bundled catalog remains intentionally empty until an
appearance passes owner review.

`assets/animations/appearances.toml` is the fixed appearance registry. It must
define all three IDs, one available default, optional ownership requirements,
and normalized relative TOML manifest paths. Every available manifest must
exist inside the trusted registry root.

Every available appearance must also name a checked-in owner-approval record.
That record pins the approved manifest and every referenced PNG by SHA-256,
dimensions, and trusted relative path. Registry loading rejects a missing,
modified, incomplete, or path-escaping approved set before it can reach the
appearance service or renderer.

The minimum complete appearance contract is explicit coverage for every
runtime animation state currently consumed by the pet: `idle`, `walking`,
`dragging`, and `sleeping`. Every rendered frame must be 100 by 100 pixels,
RGBA, binary-alpha, transparent, and resolved beneath the trusted animation
root. Dress and Vermillion remain inactive until complete manifests, assets,
and separate owner-approval records satisfy the same contract.

## Whole-Set Review Workflow

`scripts/review_appearance_assets.py` validates and previews a complete set by
using the production `AssetAnimationProvider` and `SpritePetRenderer`. It does
not write to canonical assets. Contact sheets, per-frame renders, state GIFs,
and the machine-readable validation report are derived review artifacts under
`dist/appearance-review/`.

Review an active appearance:

```powershell
.venv313\Scripts\python.exe scripts\review_appearance_assets.py --appearance seifuku
```

Review a candidate without activating it:

```powershell
.venv313\Scripts\python.exe scripts\review_appearance_assets.py `
  --appearance dress `
  --manifest C:\path\to\candidate\manifest.toml
```

Candidate review proves technical validity only. Availability changes require
the owner to accept the rendered preview and add the matching approval record.
Experimental, rejected, missing, and technically invalid sets stay inactive.

Future shop categories may include food, drinks, gifts, and favorites only when
they map to an existing meaningful care or convenience behavior. Medicine is
excluded unless an approved health/sickness mechanic exists. No category is
added merely because another virtual-pet application has one.

## UI Direction

The native Qt surface is **Akiha Shop** with two compact tabs:

- **Shop** shows balance, level, trusted products, purchase requirements, and
  explicit confirmation before spending currency.
- **Appearance** shows exactly Seifuku, Dress, and Vermillion with availability,
  ownership, and current-selection state.

The old Wardrobe view, inventory equipment controls, slots, and loadout wording
have been removed. The UI can honestly show future appearances as awaiting
approved assets without offering an unsafe selection.

The read-only **Akiha Status** surface answers “How is Akiha doing?” using only
useful existing structured state: level, XP, currency, mood, care state, user
presence, current autonomous activity, appearance, and animation. It also
shows coarse local subsystem health for the trusted catalog, ownership,
activity manifest, and Phase 10 privacy boundary. Status has no purchase,
selection, care, reset, or other mutation controls; it links to the separately
owned Care and Shop surfaces when the user explicitly chooses them.

Settings diagnostics use the same typed aggregate snapshot. They report exact
local ownership and transaction counts, catalog safe-fallback state, appearance
availability, and active trusted activity without including dialogue,
credentials, asset paths, provider content, or filesystem data.

The only Phase 10 maintenance mutation remains the existing confirmed **Reset
pet progress** operation. It resets wellbeing, XP, level, currency, pet-state
history, and pet reward cooldowns. It deliberately preserves shop ownership,
purchase transactions, selected appearance, chat, memories, settings,
credentials, Spotify state, assistant permissions, action history, and other
unrelated data. No broad shop/economy reset was added.

Phase 10 is a local virtual economy only. It has no payments, real-money store,
telemetry, cloud asset upload, remote catalog, or remote marketplace.

## VPet Research Boundary

VPet was reviewed only as product research for shop discoverability, status
visibility, user interaction, and autonomous desktop activity. Project Akiha
does not copy its code, assets, UI, terminology, stat model, or mechanics.

Research references:

- VPet documentation: <https://wiki.exlb.net/en/vpet>
- VPet Menu reference: <https://vpet-simulator.fandom.com/wiki/Menu>
- VPet Status reference: <https://vpet-simulator.fandom.com/wiki/Status>
- VPet source repository: <https://github.com/LorisYounger/VPet>

Useful concepts:

- optional, discoverable care/shop interactions;
- a readable current-status surface;
- autonomous start/loop/finish activities;
- animation driven by pet behavior rather than an LLM; and
- graceful return to idle after an activity.

Explicitly rejected concepts:

- constant hunger/thirst/health micromanagement;
- death, running away, or punitive neglect loops;
- a large RPG economy;
- wardrobe pieces, layered outfits, or arbitrary customization;
- copying VPet activities without Akiha-specific character fit; and
- continuous LLM control of desktop animation.

## Subphase Checklist

### 10A: Product, Economy, And Asset Contract

- [x] Define initial trusted product, ownership, purchase, and visual contracts.
- [x] Protect the canonical sprite and preserve explicit owner approval.
- [x] Define atomic and idempotent currency behavior.
- [x] Record the original cosmetic design as superseded by the approved fixed
  appearance revision.

### 10B: Trusted Catalog Foundation

- [x] Add strict versioned local catalog loading.
- [x] Add deterministic filtering and ordering.
- [x] Fail closed for malformed or missing trusted data.
- [x] Revise schema 2 to complete appearance products only.

### 10C: Persistence And Atomic Economy

- [x] Preserve atomic transactions and durable ownership in migration `0011`.
- [x] Prevent negative currency, duplicate charges, and partial commits.
- [x] Preserve Phase 9 care, XP, level, and reward history.
- [x] Retain the old equipment table as unused migration compatibility only.

### 10D: Shop And Inventory Services

- [x] Keep typed browse, inspect, purchase, and inventory operations.
- [x] Remove equip, unequip, slot, and loadout operations.
- [x] Gate purchases on complete approved asset availability.
- [x] Keep providers and ordinary dialogue outside the mutation boundary.

### 10E: Simplified Shop And Appearance UI

- [x] Keep the compact trusted Shop view and spending confirmation.
- [x] Replace Wardrobe with a three-entry Appearance view.
- [x] Remove equipment and layer controls.
- [x] Show unavailable and awaiting-asset states clearly.

### 10F: Fixed Appearance Reconciliation And Integration

- [x] Add closed appearance IDs and strict registry loading.
- [x] Add migration `0012` and a dedicated appearance repository/service.
- [x] Select only complete, available, owned appearance sets.
- [x] Repair stale selections to Seifuku without deleting ownership.
- [x] Swap the whole animation provider after committed selection.
- [x] Remove active wardrobe/layered-cosmetic code and stale tests.
- [x] Verify migration compatibility and the full source suite.

### 10G: Whole-Set Preview And Asset Validation

- [x] Validate each appearance manifest, clip coverage, dimensions,
  transparency, paths, and canonical fingerprints.
- [x] Add preview/contact-sheet tooling that uses the production provider.
- [x] Require owner visual approval before changing availability.
- [x] Keep missing, rejected, and experimental assets inactive.
- [x] Require `idle`, `walking`, `dragging`, and `sleeping` coverage for every
  complete Dress or Vermillion set.

### 10H: Expanded Reactions And Autonomous Activities

- [x] Define closed `ActivityId`, lifecycle, cancellation, cooldown, and
  priority contracts.
- [x] Add a deterministic scheduler using typed pet state, presence, mood, and
  time rather than dialogue parsing.
- [x] Add data-driven activity manifests with safe idle fallback.
- [x] Integrate only activities supported by approved assets, beginning with
  existing idle/walk/sleep capabilities.
- [x] Preserve drag, voice, direct care, and assistant-action priority rules.
- [x] Record privacy-safe activity history.

### 10I: Status, Diagnostics, Privacy, And Reset

- [x] Add an Akiha-specific read-only Status surface.
- [x] Add catalog, ownership, appearance, activity, and transaction diagnostics.
- [x] Add only narrowly scoped confirmed reset behavior that product needs.
- [x] Preserve chat, memories, permissions, Spotify, credentials, and unrelated
  history during shop/pet maintenance.
- [x] Confirm no real-money store, telemetry, cloud asset upload, or remote
  marketplace exists.

### 10J: Final Verification And Consolidated Release Gate

- [x] Run full tests, Ruff, Black, compilation, migrations, and fresh/existing
  source-data smoke checks.
- [x] Complete owner source acceptance for shop, appearance, status, activity,
  voice, pet, actions, and graceful shutdown.
- [x] Establish PyInstaller one-folder as an optional fast development package
  only if its compatibility spike passes.
- [x] Keep Nuitka as the release candidate path unless a separately documented
  decision replaces it.
- [x] Build one consolidated standalone after Phase 10 source scope closes.
- [x] Run packaged Gemini Live, GPT-SoVITS, pet, shop, appearance, actions,
  Spotify, persistence, migration, tray, and graceful-Quit checks.
- [x] Verify credentials, private voice references, user data, rejected assets,
  and experimental files are absent.
- [x] Accept the corrected Nuitka candidate as the Phase 10 packaged checkpoint.

#### 10J Verification Record - 2026-08-23

- Python 3.13.14 source gate: 1,582 tests passed with 3 intentional skips;
  Ruff, Black, compilation, and diff checks passed.
- Fresh and existing source-data smoke passed with all Phase 10 appearance,
  shop, inventory, transaction, pet, memory, behavior, and chat tables present.
- PyInstaller 6.22.2 one-folder compatibility passed artifact, Windows GUI,
  fresh-data, existing-data, migration, and log validation. The first build took
  155.211 seconds; its unchanged cached rebuild took 12.402 seconds.
- PyInstaller produced 1,786 files totaling 626,731,753 bytes. It is retained as
  the fast development package path, not the public release artifact.
- Nuitka 4.1.3 FastBuild reused the persistent Python 3.13/Zig 0.16.0 workspace
  with 10 jobs and LTO disabled. The corrected candidate build took 418.584
  seconds and produced 828 files totaling 463,847,530 bytes.
- Nuitka artifact, Windows GUI, fresh-data, existing-data, migration, and clean
  log checks passed. Explicit `google_genai` distribution metadata inclusion was
  added after Nuitka ignored its metadata-only option.
- Both packaged candidates load the Gemini SDK. Both pass real GPT-SoVITS
  health and in-memory synthesis against the external local runtime.
- The 2026-08-24 consolidated package passed the real Gemini Live connection
  check and GPT-SoVITS health and synthesis checks.
- Recursive artifact inspection found no credentials, SQLite databases,
  Spotify export, private voice/reference audio, or user media.
- Exact candidate and owner verification steps are recorded in
  `PHASE10J_MANUAL_SMOKE_2026-08-23.md`.
- The owner accepted source mode and the corrected Nuitka candidate on
  2026-08-24. Phase 10 is formally closed.
- Adaptive short-response speech batching and GPT-SoVITS speech-only whitespace
  normalization are included in the accepted 2026-08-24 consolidated
  `dist/nuitka-development/main.dist` candidate.
- The owner completed final manual acceptance of that consolidated candidate on
  2026-08-25 and reported no blocking packaged issues.

## Explicitly Out Of Scope

- Wardrobe, cosmetic slots, equipment loadouts, or layered compositing
- Arbitrary user-generated or provider-generated appearances
- Real-money purchases, subscriptions, payments, resale, or trading
- Punitive neglect, death, or running-away mechanics
- Large RPG stat or economy systems
- LLM-controlled animation loops or arbitrary asset paths
- Copying VPet code, assets, UI, terminology, or exact mechanics
- Live2D, Spine, 3D, or mobile synchronization in this phase

## Exit Criteria

Phase 10 closes only when atomic purchases and fixed appearance selection remain
restart-safe; unavailable assets fail closed; useful status and autonomous
activity behavior are integrated without dialogue coupling; all active visuals
have owner approval; source and consolidated package gates pass; and the
companion remains lightweight in daily use.

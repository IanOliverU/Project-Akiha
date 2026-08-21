# Phase 10: Shop And Visual Pet Expansion

**Status:** In progress - Phase 10E shop and wardrobe UI complete

## Phase Goal

Turn the Phase 9 care loop into a visible, rewarding pet economy. Akiha can earn
currency through bounded care and interaction, buy trusted local catalog items,
own them durably, equip compatible cosmetics, and display approved visual layers
without changing the canonical character sprite.

Phase 10 is the visual and economic payoff for Phase 9. It is not a real-money
store, remote marketplace, generative character system, or unrestricted asset
loader.

## Hard Architecture Rules

1. `assets/animations/akiha/standing/000.png` remains the immutable character
   source of truth.
2. Cosmetics are separate approved layers. Purchasing or equipping an item never
   rewrites a canonical sprite or animation file.
3. Currency mutations occur only through one transactional economy service.
4. Balances cannot become negative, and purchases must be atomic and idempotent.
5. Dialogue and provider output cannot purchase, sell, equip, or grant items
   directly.
6. Catalog definitions are trusted local data validated before use. No arbitrary
   file path, URL, script, executable, or provider-defined item is accepted.
7. Unsupported cosmetic/state combinations use an explicit safe fallback rather
   than guessing an anchor or modifying pixels.
8. Every activated visual asset requires automated validation and owner visual
   approval.
9. Builds remain deferred until Phase 10J. Development and acceptance use the
   Python 3.13 source environment until the feature scope is complete.

## System Pipeline

```text
Trusted catalog TOML
    -> CatalogLoader / CatalogValidator
        -> ShopService
            -> EconomyTransaction
                -> PetStateService currency debit
                -> InventoryRepository ownership grant
                -> PurchaseRepository audit record

Owned InventoryItem
    -> EquipmentService
        -> validated slot and compatibility policy
            -> equipped loadout
                -> CosmeticPresentationController
                    -> existing AnimationProvider frame
                    + approved CosmeticLayer metadata
                        -> SpritePetRenderer
```

The transaction boundary must commit the currency debit, ownership grant, and
purchase record together. A crash must leave either the complete purchase or no
purchase.

## Domain Contracts

### Catalog item

A trusted catalog entry contains:

- stable `item_id` and display name
- category and equipment slot
- non-negative currency price
- availability state and optional level prerequisite
- preview asset identifier
- visual compatibility declaration
- immutable catalog version

Initial equipment slots should remain small and meaningful: `head`, `face`,
`neck`, and `accessory`. Add outfit replacement only after an approved asset set
proves that full-body layering is visually reliable.

Phase 10 begins with one product category: `cosmetic`. All initial cosmetics are
non-stackable and occupy exactly one of the four slots above. Consumable food,
care boosts, and full outfit replacement remain outside the initial catalog so
the economy does not get ahead of approved gameplay and visual assets.

### Durable inventory

Inventory records contain only stable IDs and ownership facts:

- item ID
- acquired timestamp
- acquisition source
- purchase transaction ID when applicable
- equipped state through a separate loadout record

Repeated purchase requests for a non-stackable item return the existing owned
item without charging currency again.

### Purchase behavior

The typed purchase decisions are `completed`, `already_owned`,
`insufficient_funds`, `level_required`, `item_unavailable`, and
`item_not_found`.

- A completed purchase debits exactly the catalog price and links the inventory
  grant to one UUID transaction.
- Every denied result preserves the original balance and creates no committed
  transaction or inventory record.
- Duplicate purchase requests return `already_owned` and never charge again.
- Prices may be zero for deliberate starter/promotional catalog entries, but
  balances and level/catalog versions remain strictly validated.
- Refunds, resale, trading, gifting, and item consumption are not supported in
  Phase 10. An owned item is never silently removed because a catalog entry or
  visual asset later becomes unavailable.

### Equipment loadout

Only one item may occupy a slot unless a future catalog version explicitly
defines a safe multi-layer order. Equipping is reversible and does not consume
the item. Missing or invalid visual assets preserve ownership while rendering no
layer and reporting a diagnostic state.

### Cosmetic layer

An approved layer declares:

- trusted asset path under the cosmetic asset root
- target animation clip and direction
- integer anchor offset and explicit z-order
- expected canvas dimensions, alpha behavior, and scale contract
- compatibility fallback for unsupported states

No runtime interpolation, AI-generated replacement pixels, automatic recoloring,
or subpixel positioning is allowed for canonical pixel-art presentation.

The Phase 10A code contract additionally requires normalized relative PNG paths,
the canonical 100 x 100 canvas, binary alpha, nearest-neighbor rendering, known
animation states, explicit left/right compatibility, integer offsets, and bounded
z-order. A missing or unsupported layer renders nothing while ownership and the
equipped record remain intact for diagnostics and later recovery.

## Persistence Plan

Phase 9 currently owns migrations through `0010`. Phase 10 starts at `0011`
after confirming that number remains free.

Planned tables:

- `shop_inventory` for durable ownership
- `shop_equipment` for one equipped item per slot
- `shop_transactions` for idempotent currency debits and acquisition history
- optional `shop_catalog_state` only when catalog-version migration is required

The bundled catalog remains version-controlled TOML rather than user database
content. Removing an item from the active catalog must not silently delete its
inventory or transaction history.

Migration `0011_shop_inventory.sql` owns three durable tables:

- `shop_transactions` stores completed idempotent currency debits, catalog
  version, price, before/after balances, and purchase time;
- `shop_inventory` stores one non-stackable ownership row per item with guarded
  acquisition provenance; and
- `shop_equipment` stores at most one owned item per approved slot and prevents
  one item from occupying multiple slots.

The SQLite shop repository owns the cross-table purchase transaction. Under one
`BEGIN IMMEDIATE`, it checks transaction replay, existing ownership, catalog
availability, level, and current currency before updating `pet_state`, writing
the transaction, and granting inventory. Any failed statement rolls back all
three mutations. A repeated transaction ID returns the original completed
result, while a different transaction ID for an already-owned item returns
`already_owned` without charging again.

Purchases increment the shared pet-state revision and change only currency and
the update timestamp. Phase 9 wellbeing, decay baselines, XP, level, reward
grants, and pet history remain intact. Purchase audit history belongs to
`shop_transactions`, avoiding duplicate or misleading care-history entries.

## Trusted Catalog Contract

`project_akiha/config/shop_catalog.toml` is the bundled catalog entry point. Its
schema and catalog versions are explicit positive integers. The initial file is
valid but intentionally empty until at least one cosmetic asset passes owner
visual review.

Catalog parsing is strict and fail-closed:

- root, item, and layer tables reject missing and unknown fields;
- item IDs, layer IDs, and layer asset paths must be unique;
- every item preview and cosmetic-layer ID must resolve inside the same catalog;
- prices, levels, versions, slots, availability, states, directions, canvas,
  alpha, offsets, and z-order pass the Phase 10A typed contracts;
- asset references are normalized relative PNG paths, never URLs, absolute
  locations, parent traversal, scripts, or executables; and
- a missing, unreadable, malformed, or invalid catalog returns a valid empty
  snapshot plus one bounded diagnostic reason instead of partially loading.

Catalog browsing is pure and deterministic. It supports typed category,
availability, and ownership filters plus name, category, ascending/descending
price, ownership, and availability ordering. Every ordering uses stable name and
item-ID tie breakers. Hidden items are excluded by default and appear only when
explicitly requested for trusted diagnostics or maintenance.

## Shop Service Boundary

`ShopService` is the single application-facing entry point for catalog browsing,
item inspection, purchasing, inventory inspection, loadout inspection, equipping,
and unequipping. Its methods accept typed IDs, filters, and equipment slots; it
does not accept dialogue, provider text, file paths, or arbitrary commands.

All returned views are sanitized for application and UI use. They contain stable
item metadata, ownership state, affordability, compatibility, balances, and
equipment state without exposing cosmetic asset paths or raw layer declarations.
Inventory and loadout entries remain visible by stable ID if a later catalog
revision removes the corresponding item, preserving durable ownership and making
the mismatch diagnosable.

Purchase policy remains inside the atomic SQLite repository. `ShopService`
refreshes the shared `PetStateService` snapshot after a completed purchase so
Phase 9 currency consumers cannot continue displaying a stale balance. Equip and
unequip operations require durable ownership and validate the declared slot and
baseline idle left/right visual compatibility before committing the loadout.

Only completed purchases and committed equipment changes publish events.
`shop.purchase_completed` and `shop.equipment_changed` carry bounded IDs,
decisions, slots, and balance state without prices, paths, assets, credentials,
or dialogue. Denied and no-op decisions publish no mutation event. Providers and
ordinary dialogue remain outside this service boundary; any future natural-
language shop request must pass through a separate typed proposal and explicit
confirmation path before reaching these methods.

## Shop And Wardrobe UI

`ShopWindow` is a compact two-view native Qt surface using Akiha's established
uniform palette and Fluent icon controls. It is available from the pet context
menu, tray menu, and Care window. The window contains no provider or dialogue
entry point.

The Shop view presents the current level and currency balance, typed category,
ownership/availability, and sort controls, local name filtering, a dense catalog
list, and one selected-item detail pane. Price, ownership, availability, level
requirement, affordability, and baseline visual compatibility are visible before
purchase. Currency spending always requires an explicit confirmation dialog.
Unavailable, insufficient-funds, level-locked, visually incompatible, empty,
loading, and failed-catalog states are represented directly.

The Wardrobe view presents durable owned items separately from the four-slot
loadout. Equip and unequip controls use exact item IDs and typed slots. A
completed operation returns a complete refreshed UI snapshot containing catalog,
inventory, loadout, and balance state, preventing stale mixed panels. Wardrobe
compatibility comes from each sanitized inventory view and therefore does not
depend on the active Shop filter. Missing catalog entries remain visible by
stable item ID and cannot be equipped until trusted metadata is restored.

All shop work runs outside the Qt UI thread through a closed operation enum.
Shop workers are coordinated with pet-state care, maintenance, and decay workers
and participate in graceful shutdown. The bundled catalog remains intentionally
empty until an owner-approved cosmetic passes the Phase 10G asset gate, so the
expected current source UI is an honest empty Shop rather than placeholder
merchandise.

## Subphase Blueprint

### Phase 10A: Product, Economy, And Asset Contract

- [x] Confirm the minimum item categories and equipment slots.
- [x] Define catalog, inventory, transaction, loadout, and cosmetic-layer models.
- [x] Define item pricing and level prerequisites against Phase 9 progression.
- [x] Lock duplicate-purchase, insufficient-funds, refund, and unavailable-item
  behavior.
- [x] Extend the animation architecture with cosmetic-layer acceptance rules.
- [x] Require at least one owner-approved visible starter cosmetic before visual
  Phase 10 completion can be claimed.

### Phase 10B: Trusted Catalog Foundation

- [x] Add a versioned local catalog schema and parser.
- [x] Reject duplicate IDs, invalid prices, unknown slots, unsafe paths, and
  incompatible asset declarations.
- [x] Add deterministic filtering and ordering by category, price, ownership,
  and availability.
- [x] Add a safe empty or invalid catalog fallback.

### Phase 10C: Persistence And Atomic Economy

- [x] Add migration `0011` and verify fresh and existing-data upgrades.
- [x] Implement inventory, equipment, and transaction repositories.
- [x] Implement atomic purchase with idempotency protection.
- [x] Prevent negative currency and duplicate charges.
- [x] Preserve Phase 9 pet state, XP, level, care history, and currency accrual.

### Phase 10D: Shop And Inventory Services

- [x] Add typed browse, inspect, purchase, equip, unequip, and loadout operations.
- [x] Enforce ownership, slot, level, availability, and compatibility rules.
- [x] Publish sanitized typed outcomes only after committed mutations.
- [x] Keep providers and ordinary dialogue outside the mutation boundary.

### Phase 10E: Shop And Wardrobe UI

- [x] Add a compact Shop view using the existing Akiha UI theme.
- [x] Show balance, price, ownership, availability, and compatibility clearly.
- [x] Add category filters and owned/available views without nested card clutter.
- [x] Add confirmation before spending currency.
- [x] Add Inventory/Wardrobe equipment controls and immediate durable refresh.
- [x] Provide empty, loading, insufficient-funds, and asset-unavailable states.

### Phase 10F: Layered Cosmetic Rendering

- [ ] Extend the existing renderer rather than creating a competing renderer.
- [ ] Render approved layers with integer anchors, explicit z-order, binary alpha,
  and nearest-neighbor scaling.
- [ ] Cache cosmetic pixmaps without mutating source assets.
- [ ] Handle left/right mirroring and declared animation compatibility.
- [ ] Fall back safely when a layer is missing, invalid, or unsupported.
- [ ] Prove the canonical sprite hash and palette remain unchanged.

### Phase 10G: Visual Preview And Asset Validation

- [ ] Add preview rendering that uses the same composition rules as the pet.
- [ ] Validate dimensions, palette expectations, alpha, anchors, clipping, and
  trusted paths.
- [ ] Generate contact sheets or runtime previews for owner review.
- [ ] Activate only explicitly approved cosmetic assets.
- [ ] Keep rejected and experimental assets out of active manifests.

### Phase 10H: Expanded Pet Reactions

- [ ] Add approved feeding, affection, attention, level-up, sleep, or wake assets
  only when their artwork exists.
- [ ] Trigger reactions from typed Phase 9 outcomes rather than dialogue parsing.
- [ ] Preserve voice, drag, walk, care, and idle priority rules.
- [ ] Keep canonical idle and safe-state fallbacks for missing clips.
- [ ] Record behavior events without storing private dialogue or asset contents.

### Phase 10I: Diagnostics, Privacy, And Reset

- [ ] Add read-only catalog, inventory, equipment, transaction, and visual-layer
  diagnostics.
- [ ] Add a confirmed reset boundary for equipment/inventory only if product
  behavior requires it.
- [ ] Preserve chat, memory, permissions, Spotify, credentials, and unrelated pet
  history during shop-specific maintenance.
- [ ] Confirm no real-money payment, remote storefront, telemetry, or cloud asset
  upload exists.

### Phase 10J: Final Verification And Consolidated Release Gate

- [ ] Run the complete source suite, Ruff, Black, compilation, migration, and
  fresh/existing-data smoke checks.
- [ ] Complete owner source-mode shop, inventory, equipment, animation, and
  canonical-fidelity acceptance.
- [ ] Build one corrected cached standalone containing all Phase 9 and Phase 10
  source corrections.
- [ ] Run real packaged Gemini Live and GPT-SoVITS runtime smoke.
- [ ] Run packaged pet, shop, inventory, cosmetic, provider, action, Spotify,
  tray, persistence, and graceful-Quit checks.
- [ ] Validate that credentials, private voice references, user data, rejected
  prototypes, and unapproved assets are absent from the package.
- [ ] Remove obsolete builds only after the new candidate is accepted.

## Explicitly Out Of Scope

- Real-money purchases, subscriptions, payment processing, or online commerce
- User-authored scripts or downloadable executable shop items
- Provider-controlled purchases or autonomous spending
- Selling, trading, gifting, or multiplayer inventory
- Arbitrary external asset loading
- AI-generated replacement character artwork
- A full Live2D, Spine, or 3D renderer migration
- Mobile shop synchronization

Live2D and richer model backends remain research topics. Phase 10 may document
an adapter decision, but implementation requires its own approved visual assets,
runtime licensing review, performance budget, and migration plan.

## Phase Exit Criteria

Phase 10 is complete when:

- purchases are atomic, idempotent, and cannot create negative currency;
- inventory and equipment survive restart and migrate safely;
- at least one owner-approved cosmetic is visibly equipped without modifying the
  canonical sprite;
- unsupported or missing assets fail safely without losing ownership;
- shop UI and diagnostics expose every important state without private data;
- all source and consolidated standalone gates pass; and
- owner visual and interaction approval is recorded explicitly.

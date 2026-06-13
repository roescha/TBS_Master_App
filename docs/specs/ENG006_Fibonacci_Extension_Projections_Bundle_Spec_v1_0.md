# ENG-006 Fibonacci Extension Projections + ENG-003-OBS-1 Confluence Re-Point — Bundle Specification

**Spec ID:** ENG-006 (primary) bundled with ENG-003-OBS-1
**Version:** v1.0
**Status:** SPECIFIED (S174)
**Track:** Track 1 (SIR §11.1) — single cycle, ENG-006 primary
**Author:** TBS Analyst (Project chat, S174)
**Spec format:** Markdown source-of-truth (SIR §1.3)
**Engine source audited at:** `master` HEAD commit `a1906ae385ab19c45b2fb4bcfcce8bd7d2f36452`

---

## Change Log

| Version | Date | Change |
|---|---|---|
| v1.0 | May 30, 2026 (S174) | Initial issuance. Bundles ENG-006 (Fibonacci extension projections, CONCEPT→SPECIFIED) with ENG-003-OBS-1 (confluence price-vs-entry-zone re-point, IDENTIFIED→SPECIFIED). Operator-locked DQs incorporated (S174). §11 Pre-Implementation Checklist carries the §11.6 source audit against `master@a1906ae`. |

---

## §1. Purpose and Scope

This specification covers two bundled, NON-GATE, output-layer Fibonacci changes that share the same engine surface (the rally-leg geometry block in `output.py` `_assemble_output`):

1. **ENG-006 (primary)** — adds three forward Fibonacci **extension** projection levels (127.2%, 161.8%, 261.8%) to the target hierarchy for Profile A and Profile B. Fills the structural gap between ENG-004 Measured Move (100% extension) and RWD-001 ATR projection in blue-sky scenarios.

2. **ENG-003-OBS-1** — corrects the Profile A Fibonacci **retracement** confluence so it answers the operationally useful question ("does the *entry zone* align with a Fib level?") instead of the misleading one ("is *current price* at a Fib level?"). Re-points the comparison from `last['close']` to the Daily EMA 21 entry-zone reference. **Profile A only.**

**Why bundled:** Both touch the same `output.py` Fibonacci/rally block (ENG-002 confluence ~L1788, ENG-003 confluence ~L1834, ENG-004 MM ~L1880) and both reuse the already-computed retracement rally leg. Bundling avoids two separate Phase 2 cycles over the same code region.

**Anchor outcome is deliberately split (Operator-locked):**
- ENG-003-OBS-1 confluence comparison target → **entry zone** (Daily EMA 21).
- ENG-006 extension Point C anchor → **structural floor** (`structural_floor_raw`).

These are different anchors by design: confluence asks whether the *entry* aligns with a retracement level; extensions project *exit* targets forward from the structural floor (mirroring RWD-001's ATR projection anchor for consistency).

**Out of scope:** any gate/verdict/stop change; ENG-002 (Profile B confluence) — see §9 DENY determination; Profile C extensions (exempt); ENG-004 Measured Move (unchanged — it is the 100% level, not duplicated).

---

## §2. Background and Root Cause

### §2.1 ENG-006 — gap in the target architecture

The current forward-target architecture has a structural gap between the Measured Move (100% extension, ENG-004) and the ATR projection (RWD-001, volatility-based, `floor + N × Daily ATR`). In blue-sky scenarios with no historical resistance, the Operator has only the conservative MM and the structure-blind ATR projection. The institutionally-watched higher-ratio extensions (127.2%, 161.8%, 261.8%) are absent. ENG-006 adds them as informational graduated exit context.

### §2.2 ENG-003-OBS-1 — post-AVWAP-001 confluence divergence (verified S174)

ENG-003 was designed when Profile A's structural floor was session VWAP, where price and floor converged at entry. AVWAP-001 (DQ-1) replaced the structural floor with the hourly EMA 21 (`data.py:603` — `df['ANCHOR'] = df['EMA_21']`), and the operator-facing entry-zone reference for Profile A is the **Daily** EMA 21 (the daily-context-frame EMA 21, `data.py:683–693` `daily_ema21`, surfaced as `metrics["Daily_Protective_Anchor"]`, `data.py:968`). The Daily EMA 21 can sit materially below current price.

The ENG-003 confluence (`output.py:1850` — `_current_price = last['close']`) was never updated for this. It therefore reports "price at a Fib level" when the operationally meaningful question is "does the entry zone align with a Fib level?"

**Live evidence (IE Profile A C2, S113):** price 13.43, Fib 38.2% = 13.41, Daily EMA 21 entry zone = 13.17. The engine reported `CONFLUENCE_382` (price ≈ Fib) while the actual entry zone was 0.9 ATR below at 13.17, where no confluence exists.

**Note on the register's wording:** the ENG-003-OBS-1 detail entry refers to "Daily EMA 21" as the entry anchor. Source verification (S174) clarifies the precise plumbing: the *structural floor* anchor (`ANCHOR`) is the **hourly** EMA 21 (`data.py:603`), while the **Daily** EMA 21 (the value the OBS-1 evidence and the operator-facing pullback note both reference) is a distinct daily-context value reachable as `metrics["Daily_Protective_Anchor"]`. The Operator-locked DQ ("re-point to the Daily EMA 21 entry zone") and the §11.6 audit confirm this is the correct comparison target.

---

## §3. Locked Design Decisions (Operator-Approved, S174 — DO NOT RE-OPEN)

| DQ | Decision |
|---|---|
| Bundling | ENG-006 + ENG-003-OBS-1 bundled (shared rally leg + shared `output.py` Fibonacci block), single Track 1 cycle, ENG-006 primary. |
| ENG-003-OBS-1 fix | **Option 1** — re-point confluence comparison from `last['close']` to the Daily EMA 21 entry-zone reference. **Profile A only.** |
| ENG-006 Point C (extension anchor) | **Structural floor**, per-profile (`structural_floor_raw`). Profile A + B. **Profile C exempt.** |
| ENG-006 rally leg | **Same leg as the retracement** — ENG-003 3-session hourly window (Profile A) / ENG-002 10-bar daily window (Profile B). |
| ENG-006 hierarchy model | **Separate flat levels** `FIB_EXTENSION_1272` / `_1618` / `_2618` (flat hierarchy, PA-001 DQ-9 model — not nested). |
| NON-GATE mandate | Zero gate/verdict impact. Tests must include `NotInGatesFile` + `VerdictInvariance`. |
| Anchor split | Confluence → entry zone (Daily EMA 21); extension → structural floor. Deliberate. |

ENG-003-OBS-1 Options 2 (suppress confluence outside entry zone) and 3 (dual-label) are **rejected** per the locked DQ. ENG-006 alternatives (ENG-004 leg for rally; current-price or entry-zone-lower-bound for Point C; nested hierarchy entry) are **rejected** per the locked DQs.

---

## §4. Functional Specification

### §4.1 ENG-006 — Extension Computation

**Location:** `output.py` `_assemble_output`, immediately following the ENG-004 Measured Move block (current ~L1880–1918), inside the `[INF-001]` unconditional block (runs on all verdict paths).

**3-point construction (reuses the retracement rally leg — no new data):**
- **Point A** (rally leg origin) = rally-window low. Profile A: `min(df.iloc[-(bars_per_day*3+1):-1]['low'])`; Profile B: `min(df.iloc[-11:-1]['low'])`. (Identical windows to ENG-003 / ENG-002 — recompute locally in-block per the established ENG-002/ENG-004 in-block pattern; no shared state.)
- **Point B** (rally leg peak) = rally-window high. Same windows, `['high'].max()`.
- **Point C** (extension anchor) = **`ctx.structural_floor_raw`** (per-profile structural floor: Profile A = hourly EMA 21 via `ANCHOR`; Profile B = SMA 50 via `ANCHOR`). Raw units.

**Formula (raw units):**
```
rally_range      = Point_B - Point_A            # = peak - origin
Extension_Level  = Point_C + (ratio × rally_range)
```
with `ratio ∈ {1.272, 1.618, 2.618}`.

**Per-profile scope:**
- Profile A: `p_code == "A" and not is_etf`, with the existing ENG-003 history/range guards (≥3-session lookback available; `rally_range ≥ 0.5 × state.atr_raw`).
- Profile B: `p_code == "B" and state._entry_trending and not is_etf`, with the existing ENG-002 guard (`rally_range > 0`).
- Profile C: **exempt** — no extension levels computed (SMA 200 floor, different horizon). ETFs follow profile rules (ETF short-circuits as in ENG-002/003).

**Guards (mirror ENG-002/003/004 degenerate handling):** when the profile/state scope is not met, when the rally window is unavailable, or when `rally_range` is below the per-profile minimum, all three extension flat keys are set to `None`.

**Display scaling:** extension prices are stored display-scaled (`round(raw / price_scaler, 2)`), mirroring `Fib_382_Level` / `MM_Target`.

### §4.2 ENG-006 — New Flat Keys

Written to `metrics` in the ENG-006 block (display-scaled):

| Flat key | Value |
|---|---|
| `Fib_Ext_1272_Level` | 127.2% extension price (display-scaled) or `None` |
| `Fib_Ext_1618_Level` | 161.8% extension price (display-scaled) or `None` |
| `Fib_Ext_2618_Level` | 261.8% extension price (display-scaled) or `None` |

These three keys MUST be added to the `_all_mapped_flat_keys()` registration list in `transform.py` (current ~L1113–1115, alongside `Fib_382_Level`/`MM_Target`) so `MAPPED_FLAT_KEYS` membership holds and `_audit_key_coverage` does not flag them as unmapped. **Collision audit (§11 item 6): clean** — no existing `FIB_EXTENSION` / `Fib_Ext` / `_1272` / `_1618` / `_2618` identifiers exist anywhere in `output.py`, `transform.py`, `compute.py`, `main.py` (verified S174).

The three keys are surfaced in the existing rally/fibonacci grouped sub-object (`transform.py` ~L2762–2766, alongside `Fib_A_382_Level`/`MM_Target`). The round-trip reverse map (`transform.py` ~L4526–4534) gets three additive lines mirroring `Fib_382_Level` so the `_audit_key_coverage` round-trip passes.

### §4.3 ENG-006 — Target Hierarchy Integration

Three new hierarchy rows are appended in `transform.py` `_target_entries` assembly (current ~L3078–3155), immediately after the `MEASURED_MOVE` / `ATR_PROJECTION` appends (semantic grouping with the other projections). Each row mirrors the `MEASURED_MOVE` row shape:

```
_target_entries.append({
    "price": flat_metrics.get("Fib_Ext_1618_Level"),       # (and _1272, _2618)
    "label": "FIB_EXTENSION_1618",
    "role":  {"label": "PROJECTION",
              "desc": "Fibonacci 161.8% extension -- golden-ratio forward projection from structural floor"},
    "status": "EXCEEDED" if (_current_price is not None and _current_price > price) else "ACTIVE",
    "escalation_winner": bool(_profit_target is not None and abs(price - _profit_target) < 0.01),
})
```
appended only when the corresponding `Fib_Ext_*_Level` is not `None`.

**Append position is immaterial to final ordering (verified §11 item 2):** BUGR-002 removed the pre-partition sort; both partitioned arrays are sorted ascending by price post-partition (`transform.py` ~L3266 `_targets_above.sort(key=lambda x: x["price"])`). The extension rows sort into correct ascending position automatically and are picked up by the CFL-001 confluence walk (post-sort) and the BUGR-002 ACTIVE/EXCEEDED partition with no special handling.

**No `Profit_Target_Source` / `_map_source_to_tier` change (verified §11 items 6, 8):** extensions are informational hierarchy rows that carry their own `role.desc`. They do **not** become the active `Profit_Target` / `Profit_Target_Source` and therefore require **no** entry in `_map_source_to_tier` (`transform.py` ~L1288–1335) or the source-desc rendering (~L2592–2593). Their `escalation_winner` is `False` unless an extension happens to equal `Profit_Target` exactly — consistent with the NON-GATE mandate.

### §4.4 ENG-003-OBS-1 — Confluence Re-Point (Profile A only)

**Location:** `output.py` ENG-003 block, current L1850 (`_current_price = last['close']`).

**Change:** the comparison reference for the Profile A confluence check changes from current price to the Daily EMA 21 entry-zone reference:
```
_entry_zone_ref = metrics.get("Daily_Protective_Anchor")   # raw Daily EMA 21
```
The five-branch confluence ladder (CONFLUENCE_382 / CONFLUENCE_500 / BETWEEN_FIBS / ABOVE_FIBS / BELOW_FIBS, L1854–1863) then compares `_entry_zone_ref` (instead of `last['close']`) against the raw Fib levels `_fib_a_382_raw` / `_fib_a_500_raw`. Units are consistent — both `Daily_Protective_Anchor` and the Fib levels are raw (pre-`price_scaler`).

**Mandatory null guard (verified §11 item 7):** `Daily_Protective_Anchor` defaults to `0.0` (`data.py:682`) when the daily context is absent or the daily EMA 21 / ATR is NaN. The re-pointed comparison MUST guard: if `_entry_zone_ref` is `None` or `<= 0`, set `metrics["Fib_A_Confluence"] = None` (NOT a spurious `BELOW_FIBS` from comparing against 0.0). The two Fib level fields `Fib_A_382_Level` / `Fib_A_500_Level` continue to be emitted (the *levels* are still valid geometry; only the *confluence verdict* is suppressed when the entry-zone reference is unavailable).

**Expected behavioral change (IE case):** with `_entry_zone_ref = 13.17` and Fib 38.2% = 13.41, the ladder yields `BELOW_FIBS` (entry zone below the Fib grid) — the operationally honest answer — replacing the prior misleading `CONFLUENCE_382` driven by price 13.43.

**ENG-002 (Profile B) is NOT changed** — see §9.

### §4.5 NON-GATE Mandate

Neither change is read by any gate function. ENG-006 adds only informational hierarchy rows + flat keys; ENG-003-OBS-1 changes only the value space of an existing informational diagnostic (`Fib_A_Confluence`), which no gate consumes. No verdict, stop, target-numeric (`Profit_Target` / R:R), or sizing value changes on any path. The acyclic module import graph (`types → helpers → {gates, data, compute, exit} → {trigger, output} → main`) is preserved (edits are `output.py` + `transform.py` only).

---

## §5. Output Schema Changes

1. `trade_setup.target.hierarchy[]` (and `cleared_levels[]` when EXCEEDED) gains up to three new entries with `label ∈ {FIB_EXTENSION_1272, FIB_EXTENSION_1618, FIB_EXTENSION_2618}`, `role.label = "PROJECTION"`, for Profile A and Profile B. Absent on Profile C and when the rally leg / structural floor is unavailable (self-documenting via absence).
2. Rally/fibonacci grouped sub-object gains `Fib_Ext_1272_Level` / `_1618` / `_2618` (display-scaled prices or null).
3. `Fib_A_Confluence` value space is unchanged (same five labels + null); only the *computation input* changes (Profile A). When the Daily EMA 21 reference is unavailable, `Fib_A_Confluence = null` (newly reachable null path).

No fields removed, renamed, or re-typed. Additive only.

---

## §6. Test Mandate

New test file: `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py`. Use the idempotent `sys.modules` loader guard (TEST-HRN-001 reference pattern: `if name in sys.modules: return sys.modules[name]`).

**NON-GATE assertions (required):**
- `TestENG006NotInGatesFile` — `inspect.getsource(gates)` contains none of `Fib_Ext_1272_Level`, `Fib_Ext_1618_Level`, `Fib_Ext_2618_Level`, `FIB_EXTENSION`.
- `TestENG003OBS1NotInGatesFile` — `inspect.getsource(gates)` does not newly read `Fib_A_Confluence` / `Daily_Protective_Anchor` for any gate decision (the latter may appear for the protective-stop substitution; assert no gate *verdict* branch keys off the confluence label).
- `TestENG006VerdictInvariance` — same fixtures pre/post: `gate_result.verdict` identical across a representative cohort (VALID, WAIT, INVALID paths, all profiles).
- `TestENG003OBS1VerdictInvariance` — same fixtures pre/post on Profile A: verdict identical.

**Functional assertions:**
- ENG-006 extension formula, per profile: `Extension = structural_floor + ratio × (peak − origin)` for each of 1.272 / 1.618 / 2.618; differential-verify the three values against a fixture with known rally leg + floor.
- ENG-006 Profile C exemption: all three keys `None` on Profile C.
- ENG-006 degenerate guards: `rally_range` below minimum / window unavailable → all three `None`.
- ENG-006 hierarchy: extension rows appear in `target.hierarchy` sorted into correct ascending position (assert ordering relative to MEASURED_MOVE); EXCEEDED rows route to `cleared_levels`.
- ENG-006 MAPPED_FLAT_KEYS membership + `_audit_key_coverage` round-trip passes with the three new keys.
- ENG-003-OBS-1 re-point: with entry-zone ref below the Fib grid (IE-style fixture: ref 13.17, Fib382 13.41) → `BELOW_FIBS`; with ref at a Fib level → `CONFLUENCE_382` / `CONFLUENCE_500`.
- ENG-003-OBS-1 null guard: `Daily_Protective_Anchor` = 0.0 / None → `Fib_A_Confluence = None`, `Fib_A_382_Level` / `Fib_A_500_Level` still emitted.

**Regression:** full `pytest` cohort, zero regressions vs the S173 baseline (dual-CWD per TEST-HRN-001 / BUG-CFL001-PRE-1 convention).

---

## §7. Closure Criteria

1. `output.py` + `transform.py` edits land per §4; no other engine module touched.
2. New test file added; all NON-GATE + functional assertions pass; full cohort zero-regression (dual-CWD).
3. ENG-006 extension levels verified on ≥1 live Profile A and ≥1 live Profile B ticker (Phase 3, Operator-led), present in `target.hierarchy`, NON-GATE (verdict unchanged vs pre-fix on the same ticker).
4. ENG-003-OBS-1 re-point verified on ≥1 live Profile A ticker where Daily EMA 21 diverges from price (confluence label reflects the entry zone, not price).
5. Engine-source authority on a merged branch (post-Phase-2 SHAs recorded in the Hand-Back).
6. Phase 4 6-Doc DIA cascade applied (§8); Bug Register advanced ENG-006 SPECIFIED→…→CLOSED and ENG-003-OBS-1 IDENTIFIED→…→CLOSED; bundle registered.

---

## §8. Documentation Impact Assessment (DIA)

Per ACP §5 Cross-Reference Impact Matrix, `ibkr_purity_engine.py` (now `tbs_engine/`) → Primary Doc 2; Secondary Doc 7 Step 6, Doc 8 §II Layer 2, Exec Map. Fires at Phase 4 (post-implementation), per the engine-first rule. Consumer (scanner/orchestrator) impact is informational, non-blocking.

| Document | Section(s) | Change Required | Status |
|---|---|---|---|
| Doc 2 (Core Strategy) | §IV Output Schema (target.hierarchy: add FIB_EXTENSION_* rows) + §4.2.x (ENG-006 paragraph) | Add extension-level contract + ENG-006 description | PENDING (Phase 4) |
| Doc 2 (Core Strategy) | §4.2.4 (ENG-003 confluence definition) | Update comparison target: price → Daily EMA 21 entry zone (Profile A) | PENDING (Phase 4) |
| Doc 7 (Daily Battle Card) | Step 6 | Operator reading guidance for FIB_EXTENSION_* targets | PENDING (Phase 4) |
| Doc 8 (Systemic Automation) | §II Layer 2 | Implementation-layer mirror (output.py + transform.py sites, new flat keys, NON-GATE statement) | PENDING (Phase 4) |
| EEM (Engine Execution Map) | §II | Verify-only — no gate added/renamed/reordered; module graph acyclic; confirm no §II impact | PENDING (Phase 4, verify-only) |
| README | Document Authority table + version line | Version bumps for amended docs | PENDING (Phase 4) |
| PEO | Tier 2D (ENG-006) + Tier 2G (ENG-003-OBS-1) | Mark CLOSED; register bundle | PENDING (Phase 4) |
| Bug Register | Summary + detail | ENG-006 SPECIFIED→…→CLOSED; ENG-003-OBS-1 IDENTIFIED→…→CLOSED; register bundle | PENDING |

---

## §9. Profile B (ENG-002) Confluence Analogue — Determination: DENY

The Operator's open Phase-1 check ("do NOT assume a bug"): does Profile B's ENG-002 confluence have an analogous price-vs-entry-zone issue? **Verified against source (S174): DENY.**

- ENG-002 reads `_current_price = last['close']` (`output.py:1801`) — the same *code pattern* as ENG-003.
- **But the ENG-003-OBS-1 defect is the AVWAP-001 cross-frame anchor migration**, which is **Profile-A-only**. Profile B's entry anchor (`ANCHOR = SMA_50`, `data.py:608`) was never migrated by AVWAP-001 and is in the **same (daily) frame** as the confluence price comparison. There is no slow-MA-used-cross-frame gap.
- ENG-002 confluence is scoped to `state._entry_trending`. On a TRENDING Profile B pullback entry, price sits within the pullback band (`ANCHOR ≤ close ≤ EMA_21 + 0.5 ATR`), so price ≈ entry zone; the divergence only appears on INVALID paths where `ABOVE_FIBS` already self-documents.

A *latent, bounded* same-frame looseness exists on Profile B INVALID paths (price above the ~0.5 ATR pullback band), but it is low-magnitude and not the misleading cross-frame signal ENG-003-OBS-1 documents. **Recommendation: no change to ENG-002; no new Bug Register item** (not a confirmed defect; opening one would be scope creep against the locked Profile-A-only DQ). Flagged for Operator awareness only.

---

## §11. Pre-Implementation Checklist (SIR §11.6 Source Audit)

Audited by the Project-chat Analyst at Phase 1 close against engine source at `master@a1906ae`. Per-file blob SHAs (`git hash-object`):

| File | Blob SHA |
|---|---|
| `output.py` | `ee00a7d51cb12458ca529291889482925f2d5f2a` |
| `transform.py` | `f301b2e9b48a24622834591b1e302b90822f2805` |
| `compute.py` | `1081673d02f3ae8078f2281d87795dcedb8f6dcd` |
| `main.py` | `6cd6c1b1f7473d0a00d8f021fa64b2693b9ccd03` |
| `data.py` | `d1fa56bc0f6114850da87c06553ebc0002cba8c0` |

| § | §11.6 Item | Finding | Evidence (file:line @ a1906ae) |
|---|---|---|---|
| 1 | Call-order verification | PASS. ENG-006 Point A/B computed locally in-block from `df` (no compute-layer attribute read). ENG-003-OBS-1 reads `Daily_Protective_Anchor`, written by `data.py` long before output assembly. | `output.py:1838–1841` (A/B window), `data.py:683–693` + `:968` (Daily EMA 21 write), `output.py:1850` (confluence read) |
| 2 | Sort-order check | PASS / KEY. Target hierarchy uses `.append()` in fixed source order; BUGR-002 removed the pre-partition sort; both partitioned arrays sorted ascending by price post-partition → extension append position is immaterial; no greedy-walk-on-unsorted hazard. | `transform.py:3094–3155` (append), `:3266` (`_targets_above.sort(key=lambda x: x["price"])`) |
| 3 | Shared-reference / partition-leak | PASS. Each extension row is a fresh dict literal appended to `_target_entries`. CNV-001 annotation + BUGR-002 partition operate on price/status only; no shared dict reference leaks into an unintended array. | `transform.py:3160` (`_annotate_conviction`), `:3245–3270` (partition + sort) |
| 4 | Pipeline-order feasibility | PASS. `output.py` writes extension flat keys + reads `structural_floor_raw` (Point C) + rally A/B all **before** `_transform_output` is called, which flattens metrics for the hierarchy assembly to read. | `output.py:1880–1918` (ENG-004 block = insertion site), `output.py:2679` (`return _transform_output(...)`), `transform.py:3113` (`flat_metrics.get("MM_Target")` read pattern) |
| 5 | Call-order feasibility (invocations) | PASS. ENG-006 block runs once per evaluation in `_assemble_output`; ENG-003-OBS-1 is a one-comparison change, once per Profile A evaluation. Independent, order-insensitive. | `output.py:1152` (`def _assemble_output`), single-pass block |
| 6 | Cross-spec layout audit (flat keys + desc map) | PASS. New keys `Fib_Ext_1272/1618/2618_Level` are **collision-free** (grep: zero existing hits). Register in `_all_mapped_flat_keys()` list. **No** `_map_source_to_tier` / source-desc entry needed — extensions are NON-GATE hierarchy rows, never `Profit_Target_Source`. | `transform.py:1113–1115` (registration list), `:1248` (`MAPPED_FLAT_KEYS`), `:1288–1335` (`_map_source_to_tier` — no change), `:4526–4534` (round-trip reverse map — add 3 lines) |
| 7 | Storage-mechanism feasibility | PASS with guard. `Daily_Protective_Anchor` reachable in `_assemble_output` scope (producer `data.py:968`, Profile-A-only). **Defaults to `0.0`** when daily ctx NaN/absent → §4.4 mandates `≤0 → Fib_A_Confluence=None`. `structural_floor_raw` (Point C) reachable via `ctx.structural_floor_raw` (producer `data.py:619`, wired `main.py:149/390`); not unpacked at top of `_assemble_output` — implementer uses `ctx.structural_floor_raw` directly or adds the unpack. | `data.py:619`, `:682`, `:968`; `main.py:149,390`; `output.py:1182–1203` (unpack region, lacks `structural_floor_raw`) |
| 8 | Downstream-override-path audit | PASS. `Fib_A_Confluence` / `Fib_Confluence` have a **single write site each** (`output.py` ENG-002/003 blocks); downstream uses are read-only (`output.py:2449`, `transform.py:2764`, `:4534`) — **no override** masks the re-pointed value. ENG-006 extensions write **no** `Profit_Target_Source`, so they are isolated from the FRR-001/CEG-002/BRK-001 override chain (BUGR-006-LABEL-1/2). | `output.py:1806–1877` (writers), `:2449` / `transform.py:2764` / `:4534` (read-only); `Profit_Target_Source` chain untouched |

**Defects identified by the audit:** one — the `Daily_Protective_Anchor` `0.0` default (item 7); resolved in-spec at §4.4 (null guard). No defect propagates to Phase 2 unaddressed.

---

## §12. Pre-Delivery Verification (additional Phase 2 checks)

In addition to SIR §9, at Phase 2 hand-back the implementer confirms:
- Extension levels are display-scaled in flat keys and hierarchy rows (raw only in the in-block computation).
- The ENG-003-OBS-1 null guard short-circuits before the five-branch ladder (no comparison against 0.0).
- The three new flat keys appear in `MAPPED_FLAT_KEYS` and the `_audit_key_coverage` round-trip is clean.
- `git diff --stat` shows only `output.py`, `transform.py`, and the new test file.

---

*TBS Specification | ENG-006 (primary) + ENG-003-OBS-1 bundle | v1.0 | S174 | End of Document*

# ITS-001 v1.0 Implementation Hand-Back — S165 (Phase 2)

**Spec authority:** `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md` (v1.0.1, S165, 2026-05-24)
**Brief authority:** `ITS001_Claude_Code_CLI_Implementation_Brief_v1_0.md` (v1.0, S165)
**Implementer:** Claude Code CLI, session S165
**Hand-back date:** 2026-05-26
**Track:** Track 1 multi-file scope (5 engine modules + 1 new test file per Brief §5.1) under SIR §11.6 two-layer-defense discipline
**Status request:** Bug Register advance **🟠 SPECIFIED → 🟡 IMPLEMENTED**

---

## 1. Outcome Summary

ITS-001 v1.0 (Intraday-Tactical Surface — Feature C regime-shift annotation + Feature D shelf/stop/target surface) is implemented to spec. Phase 2 deliverables complete:

- `types.py` — 18 `_intraday_*` RunContext attribute declarations (Spec §4.7)
- `compute.py` — 12 module-level constants + 4 helpers (`_detect_intraday_events`, `_detect_compression_shelf`, `_compute_intraday_tactical_levels`, `_derive_intraday_high`) + `__all__` update (Spec §4.1–§4.4)
- `output.py` — `_ITS_NULL_FLAT_KEYS` dict + `_assemble_intraday_tactical` helper + `__all__` update + sentinel-key stash call site in `_assemble_output` (Spec §4.5)
- `transform.py` — 18 flat keys registered in `_all_mapped_flat_keys()` + top-level `intraday_tactical` group emission via sentinel-key read with cleanup + per-field `lookback_stale` annotation on 3 hierarchy entries (Spec §4.6 + Item 9 resolution)
- `main.py` — 3 sequential ITS helper calls inserted between `_compute_volume_at_price` (VOL-001) and `_compute_rally_state_for_ctx` (RLY-001); compute import extended (Spec §4.8)
- `test_its001_intraday_tactical.py` (new) — 21 test classes / **75 tests** matching Spec §6.1 catalog exactly
- Full pytest cohort: **3173 passed / 4 skipped / 1 failed** (zero ITS-caused regressions)
- One **§11 Item 9 resolution decision** (DEFERRED → ANNOTATE) and one **vocabulary clarification** are documented in §6 below for Analyst review

Live validation (Phase 3) and DIA cascade (Phase 4) remain out of scope for this hand-back per Brief §3.2.

---

## 2. Files Touched (`git diff --stat`)

```
layers/tbs_engine/compute.py                       | +300 -1
layers/tbs_engine/main.py                          |  +15 -0
layers/tbs_engine/output.py                        | +206 -1
layers/tbs_engine/transform.py                     |  +58 -0
layers/tbs_engine/types.py                         |  +23 -0
layers/tests/unit/test_its001_intraday_tactical.py | +1068 (new)
                                                   ───────────────
6 files changed, 1670 insertions(+), 2 deletions(-)
```

Exactly the **5 engine files + 1 new test file** enumerated in Brief §5.1. No sixth engine file — §9.5 halt trigger did not fire.

**File SHAs (post-edit, `git hash-object`):**

| File | SHA |
|---|---|
| `layers/tbs_engine/types.py` | `b6ef462eb9a3136e4249b95ab51538d1216db732` |
| `layers/tbs_engine/compute.py` | `9d29f6fd4b98b5c55f8fbc15ea2d69cc331aab61` |
| `layers/tbs_engine/output.py` | `d698927804f00fe9bc17ea160ea0b3425c63015e` |
| `layers/tbs_engine/transform.py` | `b8c23dc0f4ad269b3947db20504d5a629cf72614` |
| `layers/tbs_engine/main.py` | `9caec7dd29d27f7da7fbf851f8fd305432c8be9e` |
| `layers/tests/unit/test_its001_intraday_tactical.py` | `f153962785e2886f48127b25598c1ad7e098bc32` |

**Branch / commit:** `master`, working-tree changes uncommitted (staged for Operator review per Brief §2 + §9 default). Suggested feature branch name per Brief §2: `feat/ITS-001-intraday-tactical-surface`.

---

## 3. What Was Built — Per Spec §4

### 3.1 `layers/tbs_engine/types.py` (Spec §4.7)

Added 18 `_intraday_*` attribute declarations to the `RunContext` dataclass immediately after the RLY-001 attribute block (mirroring the RLY-001 precedent at `types.py:246-248`). All defaulted to `None` / `False`. Profile-A-only by upstream-helper guard; on Profile B/C the attributes remain at their defaulted values (helpers no-op).

### 3.2 `layers/tbs_engine/compute.py` (Spec §4.1–§4.4)

1. **Module-level constants** (Spec §4.1) — 12 `INTRADAY_*` constants inserted immediately after the existing `RLY_*` constants block (~L27), preserving the BRK-001 / RLY-001 placement precedent. Values match spec verbatim:
   ```python
   INTRADAY_GAP_PCT_FLOOR = 0.04
   INTRADAY_GAP_ATR_MULT = 1.5
   INTRADAY_GAP_RVOL_THRESHOLD = 2.0
   INTRADAY_VOL_EXPANSION_FAST_BARS = 5
   INTRADAY_VOL_EXPANSION_SLOW_BARS = 20
   INTRADAY_VOL_EXPANSION_RATIO_THRESHOLD = 1.5
   INTRADAY_SHELF_MIN_BARS = 4
   INTRADAY_SHELF_MAX_BARS = 10
   INTRADAY_SHELF_TIGHTNESS_ATR_MULT = 0.5
   INTRADAY_STOP_FADE_ATR_MULT = 0.4
   INTRADAY_STOP_BREAKOUT_ATR_MULT = 0.3
   INTRADAY_STOP_VOL_ATR_MULT = 1.5
   ```
2. **`_detect_intraday_events(ctx)`** (Spec §4.1) — Profile-A-only global event scanner; iterates the 10-bar scan window backward, records the **most recent** GAP_UP / GAP_DOWN / VOL_EXPANSION / MULTIPLE event. Defensive null path on `p_code != "A"` or insufficient bars.
3. **`_detect_compression_shelf(ctx)`** (Spec §4.2) — sliding 4–10 bar window with `iloc[-(N+1):-1]` evaluated-bar-exclusion convention (PE-43); picks the largest-N qualifying shelf (favors stability); classifies `ABOVE` / `BELOW` / `WITHIN` against `ctx.last['close']`.
4. **`_compute_intraday_tactical_levels(ctx)`** (Spec §4.3) — reads ctx shelf state, emits `atr_volatility` stop unconditionally (when `state.atr_raw > 0`), emits `shelf_structural` stop and `near_term_target` per position. Reads `_derive_intraday_high(ctx.df)` for ABOVE-mode primary target.
5. **`_derive_intraday_high(df)`** (Spec §2.7.3 + §4.3) — module-level pure function; returns the max `df['high']` over the most-recent-session bars (INCLUDES the evaluated bar, deliberately distinct from `resistance_raw`'s `iloc[-11:-1]` exclusion convention).
6. **`__all__` update** — appended `_detect_intraday_events`, `_detect_compression_shelf`, `_compute_intraday_tactical_levels`, `_derive_intraday_high`.

### 3.3 `layers/tbs_engine/output.py` (Spec §4.5)

1. **`_ITS_NULL_FLAT_KEYS` dict** — all 18 flat keys set to `None`, inserted near the existing `_RLY_NULL_FLAT_KEYS` / `_RLC_NULL_FLAT_KEYS` siblings.
2. **`_assemble_intraday_tactical(ctx, p_code)`** — Profile-A-scope guard at top (returns `(None, dict(_ITS_NULL_FLAT_KEYS))` on B/C). Assembles shelf + lookback_status + tactical_stop + near_term_target sub-objects; serializes the 18 flat keys with `price_scaler` normalization. ISO-format event timestamp via `hasattr(ts, 'isoformat')` defensive check.
3. **Call site in `_assemble_output`** — inserted immediately after the RLC-001 `_assemble_reclaim_quality` call and immediately before the `_transform_output` return at `output.py:2301`:
   ```python
   _its_block, _its_flat = _assemble_intraday_tactical(ctx, p_code)
   metrics.update(_its_flat)
   metrics["_intraday_tactical_block"] = _its_block
   ```
4. **`__all__` update** — appended `_assemble_intraday_tactical`.

### 3.4 `layers/tbs_engine/transform.py` (Spec §4.6)

1. **Flat-key registration** — 18 keys added to `_all_mapped_flat_keys()` immediately after the existing RLC-001 `Reclaim_Quality_Pct` entry.
2. **Top-level group emission** — sentinel-key read inserted in `_transform_output` between `swing_breakout_confirmation` and the `_debug` emission:
   ```python
   _its_block = flat_metrics.get("_intraday_tactical_block")
   if _its_block is not None:
       result["intraday_tactical"] = _its_block
   flat_metrics.pop("_intraday_tactical_block", None)
   ```
   `None` on Profile B/C → group structurally absent (WKC-001 macro_frame precedent).
3. **Per-field `lookback_stale` annotation** — two mutation blocks, both gated on `flat_metrics.get("Intraday_Lookback_Stale") is True`:
   - Target side (post-CFL-001 confluence, post-partition): annotates entries with `label == "DAILY_HIGH"` in `_targets_above`
   - Floor side (post-CFL-001 confluence, post-partition): annotates entries with `label == "ESTABLISHED_LOW"` OR `label == "AVWAP_10BAR"` in `_stops_below`
   AVWAP_10BAR is the §11 Item 9 resolution (see §6 below).

### 3.5 `layers/tbs_engine/main.py` (Spec §4.8)

1. **Compute import extended** — `_detect_intraday_events`, `_detect_compression_shelf`, `_compute_intraday_tactical_levels` added to the existing `from tbs_engine.compute import (...)` block.
2. **Call site** — three sequential ITS helper calls inserted between `_compute_volume_at_price(ctx)` (VOL-001, `main.py:233`) and `_compute_rally_state_for_ctx(ctx)` (RLY-001, `main.py:239` pre-insertion; now L252). Comment block cites spec §2.4 / §2.5 / §2.7 and the pre-gate-placement rationale.

### 3.6 `layers/tests/unit/test_its001_intraday_tactical.py` (new file, 1068 lines)

**21 test classes per Spec §6.1, 75 tests total.** Counts match the spec table exactly:

| # | Class | Tests | Coverage |
|---|---|---:|---|
| 1 | `TestITS001ConstantsLocked` | 1 | All 12 INTRADAY_* constants match spec values |
| 2 | `TestITS001EventDetection` | 8 | GAP_UP / GAP_DOWN / VOL_EXPANSION / RVOL-floor / gap-floor / quiet / Profile B / insufficient-bars |
| 3 | `TestITS001ShelfDetection` | 8 | 7-bar shelf / bounds set / tightness pass / tightness reject / largest-N selection / no-shelf / Profile B / insufficient bars |
| 4 | `TestITS001ShelfPosition` | 5 | ABOVE / BELOW / WITHIN inside band / boundary at upper / boundary at lower |
| 5 | `TestITS001TacticalStopABOVE` | 4 | anchor / price formula / atr_volatility parallel / buffer_mult constant |
| 6 | `TestITS001TacticalStopBELOW` | 4 | anchor / breakout-failure price / atr_volatility parallel / buffer_mult |
| 7 | `TestITS001TacticalStopWITHIN` | 3 | dual-alternate dict price / anchor `both` / atr_volatility still emitted |
| 8 | `TestITS001NoShelfFallback` | 3 | shelf_structural None / atr_volatility emitted / atr_volatility price formula |
| 9 | `TestITS001NearTermTargetABOVE` | 4 | mode / source INTRADAY_HIGH / source SHELF_WIDTH_PROJECTION / applicable true |
| 10 | `TestITS001NearTermTargetBELOW` | 4 | mode / source SHELF_UPPER_PROJECTION / source EXTENDED_RANGE_PROJECTION / 1.5× shelf-width arithmetic |
| 11 | `TestITS001NearTermTargetWITHIN` | 2 | applicable false / mode set + primary/secondary None |
| 12 | `TestITS001IntradayHighDerivation` | 4 | session max / evaluated bar included / cross-session isolation / None on empty df |
| 13 | `TestITS001LookbackStaleAnnotation` | 5 | flat key true on event / false on no event / 3 affected_fields / empty array no event / transform-side round-trip |
| 14 | `TestITS001LookbackStatusBlock` | 4 | no-event block shape / full-payload block / ISO timestamp / 4-value event-type vocab |
| 15 | `TestITS001FlatKeyRegistration` | 1 | All 18 keys in MAPPED_FLAT_KEYS |
| 16 | `TestITS001ProfileScope` | 3 | Profile B None block + null flats / Profile C same / Profile A returns block |
| 17 | `TestITS001VerdictInvariance` | 1 | Static gates-module-source assertion (no ITS vocab anywhere in `gates.py`) — defense-in-depth for the canonical 4-ticker live-cohort Phase 3 check |
| 18 | `TestITS001VerdictPathCoverage` | 5 | Helper emits on simulated VALID / WAIT / INVALID / RECOVERY_CANDIDATE / ERROR-class ctx state |
| 19 | `TestITS001SchemaStability` | 3 | Block top-level keys / tactical_stop methodology keys / near_term_target keys |
| 20 | `TestITS001NotInGatesFile` | 1 | Negative: no `Intraday_*` / `_intraday_*` / `intraday_tactical` token in any `_gate_*` function body |
| 21 | `TestITS001RLY001CallOrderPreserved` | 2 | RLY-001 helper still importable / three ITS helpers callable on Profile B (defensive no-op) |
| **Total** | | **75** | |

**Test harness pattern:** Post-TEST-HRN-001 idempotent — mirrors `test_rly001_rally_state.py` (S158) and `test_rlc001_reclaim_quality.py` (S160). Uses `spec_from_file_location` with the `if name in sys.modules: return sys.modules[name]` guard to avoid global cache pollution. Stubs `tbs_engine.charts` to skip the plotly dependency only when not already loaded — suite-friendly.

---

## 4. Verification — Spec §11 (Pre-Implementation Checklist)

Re-executed per Brief §4 / §7.3 immediately before any code edit, using fresh `file:line` evidence anchors from the current working-tree state (anchors drifted from the spec-authoring date 2026-05-24 but structural assumptions preserved per Brief §4.1 step 4).

| # | §11.6 Item | Result | Fresh evidence anchor |
|---|---|---|---|
| 1 | **Call-order verification** — ITS insertion site between VOL-001 and RLY-001 | ✅ PASS (DRIFTED) | `main.py:233` `_compute_volume_at_price(ctx)`; `main.py:239` `_compute_rally_state_for_ctx(ctx)` pre-insertion. ITS insertion lands between these two calls (drift +23 from spec ~L210-L215; within ±50 tolerance) |
| 2 | **Sort-order check** | ✅ N/A | ITS operates on scalars; no sortable iterables |
| 3 | **Shared-reference / partition-leak audit** — ITS lives outside BUGR-002 partition | ✅ PASS by design | Partition sites at `transform.py:3152` (target side: `_targets_above` / `cleared_levels`) and `transform.py:3444` (stop side: `_stops_below` / `overhead_levels`). ITS top-level group emission lives at result-dict-construction site, structurally independent |
| 4 | **Pipeline-order feasibility** — pre-gate write, post-gate read | ✅ PASS | Compute calls at `main.py:233-239` (tier 3, pre-gate); read at tier 8 (`_assemble_output` in output.py). All early-return paths come AFTER the compute helpers complete |
| 5 | **Call-order feasibility** — three ITS helpers sequential | ✅ PASS by construction | `_compute_intraday_tactical_levels` reads `ctx._intraday_shelf_*` written by `_detect_compression_shelf`; sequential dependency enforced by spec §4.8 insertion order |
| 6 | **Cross-spec layout audit** — no existing `intraday_tactical` collision | ✅ PASS | Grep across `layers/tbs_engine/` returns **zero** matches for `intraday_tactical` or any `Intraday_*` flat key pre-edit |
| **7** | **Storage-mechanism feasibility (Brief §4.3 — highest-precedent risk class)** | ✅ **PASS — all 3 sub-checks** | (1) `transform.py:1437` `def _transform_output(action_summary: dict, flat_metrics: dict, debug: bool = False) -> dict:` — **no ctx parameter**. (2) RLY-001 sibling pattern intact at `output.py:595` (helper signature) + `output.py:2287-2288` (tuple-unpack + flat_keys merge). (3) Sentinel `_intraday_tactical_block` — zero collisions pre-edit |
| 8 | **Downstream-override-path audit** | ✅ PASS | DD-2 EXIT at `output.py:2011-2024` (mutates `action_summary` verdict→INVALID); BKOUT-001 GAP-5 at `output.py:2025-2045` (drifted from ~L1961; structurally intact). Both overrides target `action_summary` only — neither touches `metrics["_intraday_tactical_block"]` nor any `Intraday_*` flat key. Additionally, both override branches execute at L2011-L2045 which **precedes** the ITS call site (after `_assemble_reclaim_quality` at L2295, before `_transform_output` at L2301), so no override path can interfere with ITS attachment |
| 9 | **DEFERRED: AVWAP_10BAR sub-object existence** | ✅ RESOLVED → ANNOTATE | See §6.1 below. AVWAP_10BAR surfaces as a `floor_analysis`-equivalent hierarchy entry at `transform.py:3241`. Per Brief §4.2 step 2: structurally similar to ESTABLISHED_LOW → annotate alongside it |

---

## 5. Test Outcome

**New ITS-001 test file:**

```
pytest layers/tests/unit/test_its001_intraday_tactical.py -v
================================ 75 passed in 3.04s ================================
```

**Full pytest cohort (post-implementation):**

```
pytest layers/tests/unit/ --tb=line -q
1 failed, 3173 passed, 4 skipped, 2 warnings in 35.47s
```

**Pre-implementation baseline (captured at session start):**

```
1 failed, 3098 passed, 4 skipped, 2 warnings in 37.96s
```

| Metric | Baseline | Post-impl | Delta |
|---|---:|---:|---:|
| Passed | 3098 | 3173 | **+75** ✅ |
| Skipped | 4 | 4 | 0 |
| Failed | 1 | 1 | 0 |

- **Zero ITS-caused regressions.**
- The single failure (`test_eng004_measured_move::TestENG004TransformRoundTrip::test_transform_roundtrip`) is BUG-CFL001-PRE-1 — pre-existing on bare master, documented in Brief §6.4 as out-of-scope. Unchanged.
- **Baseline drift note (§9.8 — informational, not halt):** Spec §6.3 baseline was `3133/5/1` per RLC-001 S160 hand-back; current actual pre-implementation baseline is `3098/4/1`. The 3133→3098 delta (35 tests fewer) and 5→4 skipped delta occurred between RLC-001 S160 and Phase 2 entry. Root cause not investigated (out of ITS scope). Flagged in §9 for Analyst awareness.

**Worked-example sanity (Spec §8 Example B — FSLR orderly trend):**

| Field | Expected (Spec §8.2) | Test class coverage |
|---|---|---|
| `shelf.detected` (FSLR scenario) | true | `TestITS001ShelfDetection::test_seven_bar_shelf_detected` |
| `shelf.position` (ABOVE) | ABOVE | `TestITS001ShelfPosition::test_above_when_price_exceeds_upper` |
| `near_term_target.mode` | ABOVE | `TestITS001NearTermTargetABOVE::test_target_mode_above` |
| `near_term_target.primary.source` | INTRADAY_HIGH | `TestITS001NearTermTargetABOVE::test_primary_source_is_intraday_high` |
| `lookback_status.stale` (FSLR no-event) | false | `TestITS001LookbackStaleAnnotation::test_lookback_stale_flat_key_false_on_no_event` |

---

## 6. Process Deviation — For Analyst Review

Per Brief §8 / ACP §6.5, the following are surfaced for Analyst attention before Phase 3 commencement.

### 6.1 Item 9 resolution — AVWAP_10BAR annotated (not dropped)

Spec §11 item 9 was 🟡 DEFERRED to Phase 2 entry: "verify whether AVWAP-001 emits a `floor_analysis.avwap_10bar` sub-object that ITS should annotate."

**Finding:** AVWAP_10BAR exists in the engine but **as a hierarchy entry, not as a separate sub-object**:
- `transform.py:175` — `"AVWAP_10BAR": ("MA_DYNAMIC", 3)` in `_CONVICTION_TIER_MAP`
- `transform.py:3241` — emitted as a hierarchy entry with `"label": "AVWAP_10BAR"`, role SUPPORT, conviction_tier MA_DYNAMIC, alongside ESTABLISHED_LOW in the floor-side hierarchy

**Resolution path taken (Brief §4.2 step 2):** Since AVWAP_10BAR is **structurally similar** to ESTABLISHED_LOW (both 10-bar short-window fields, both hierarchy entries on the floor side, both with conviction tier MA_DYNAMIC/STRUCTURAL respectively), I annotated it alongside ESTABLISHED_LOW in two places:
1. `_assemble_intraday_tactical` `affected_fields` array (output.py) now includes `"floor_analysis.hierarchy[AVWAP_10BAR]"` when an event is within the 10-bar lookback
2. The transform.py floor-hierarchy annotation block adds `lookback_stale: True` to entries with `label == "AVWAP_10BAR"` (alongside ESTABLISHED_LOW)

**Operator-facing JSON impact:** When `Intraday_Lookback_Stale` is True, the `affected_fields` list grows from the spec §2.4.4 two-element example to three elements, and a third hierarchy entry gains the `lookback_stale: true` annotation.

**Question for the Analyst:** Bless or amend. The Brief §4.2 step-2 path was followed cleanly, but the spec's narrative at §2.1 / §3.4 / §4.5 references the AVWAP_10BAR annotation conditionally; a v1.0.2 cosmetic update could canonicalize the "annotated as a hierarchy entry alongside ESTABLISHED_LOW" wording (rather than the sub-object phrasing).

### 6.2 Path-vs-label vocabulary clarification (spec §2.1 / §3.4)

Spec §2.1 / DQ-1a references the annotation sites as:
- `floor_analysis.hierarchy[label=ESTABLISHED_LOW].lookback_stale`
- `target.hierarchy[label=DAILY_HIGH].lookback_stale`

In the engine, these label-bearing entries actually live at:
- `trade_setup.stop.hierarchy[...]` (floor-side hierarchy via BUGR-002 partition)
- `trade_setup.target.hierarchy[...]` (target-side hierarchy via BUGR-002 partition)

The `floor_analysis` top-level group exists separately (carrying `higher_frame`, `macro_frame`, `protective_anchor`, `floor_proximity_exemption`) and does NOT have a `hierarchy` key. The spec's "floor_analysis.hierarchy" / "target.hierarchy" wording is **label-equivalent rather than path-equivalent**.

**Resolution:** The implementer annotated by label-match (`if entry.get("label") == "ESTABLISHED_LOW"`), which is unambiguous regardless of the containing group's name. The annotation lands on the entries the spec intends.

**Question for the Analyst:** A v1.0.2 cosmetic update could replace "floor_analysis.hierarchy" / "target.hierarchy" with the actual engine paths `trade_setup.stop.hierarchy` / `trade_setup.target.hierarchy` to remove the read-time ambiguity. No behavior change implied.

### 6.3 Pytest baseline drift (informational, §9.8)

Spec §6.3 / Brief §2 cite `3133 passed / 5 skipped / 1 failed` as the RLC-001 S160 baseline. The actual pre-implementation baseline at Phase 2 entry was `3098 passed / 4 skipped / 1 failed` — 35 tests fewer passed, 1 fewer skipped. Pre-existing failure unchanged. Per Brief §9.8 this is informational not a halt; root cause not investigated.

**Question for the Analyst:** Note in the Bug Register or hygiene queue for visibility — the cohort baseline has drifted between RLC-001 close (S160) and ITS-001 open (S165) by a non-trivial amount.

---

## 7. Pre-Delivery Verification — Brief §7 / Spec §10

### 7.1 Brief §7.1 SIR §9 Pre-Delivery checklist

| Check | Result |
|---|---|
| Content accuracy (paths, line numbers, SHAs) | ✅ PASS |
| Internal consistency (helper formulas match §2 DQ locks; constants match §4.1 values; vocabulary matches §3) | ✅ PASS |
| Format integrity (`.md`, no trailing whitespace, mirrors RLC-001 hand-back style) | ✅ PASS |
| Scope discipline (`git diff --stat` shows exactly 5 engine files + 1 new test file) | ✅ PASS |
| Gate function verification (no gate function added; no ordering change; no new gate-input flat key) | ✅ PASS — verify-only confirmed by `TestITS001NotInGatesFile` + `TestITS001VerdictInvariance` |
| Module import graph remains acyclic (`types → helpers → {gates, data, compute, exit} → {trigger, output} → main`) | ✅ PASS — ITS adds compute → output / compute → main imports only (existing patterns) |
| Bug Register updated | NOT DONE — Analyst responsibility per Brief §3.2 |
| DIA current | NOT DONE — Phase 4 work per Brief §3.2 |

### 7.2 Spec §10 Acceptance

| Criterion | Result |
|---|---|
| All §6 tests pass (~75 tests) | ✅ PASS — **75 passed** |
| Zero regression failures on full pytest cohort | ✅ PASS — pre-existing failure unchanged, no new regressions |
| Engine runs cleanly on Profile A test ticker with `intraday_tactical` group in output JSON | ✅ PASS — Operator-run smoke on **VST** (Profile A, INVALID / CONTEXT REGIME FAILED verdict) returns full `intraday_tactical` block with `shelf.detected: true`, `position: WITHIN`, dual-alternate `tactical_stop`, and `near_term_target.applicable: false`. See §8 below |

---

## 8. Live-Sampling Confidence Notes (Operator-run smoke check)

The Operator ran the engine in `LIVE` mode against **VST** (Profile A, C2 convexity) immediately after implementation. Selected diagnostic excerpts from the rendered JSON:

```json
"intraday_tactical": {
  "shelf": {
    "detected": true,
    "upper": 157.57,
    "lower": 155.39,
    "bar_count": 4,
    "tightness_ratio": 0.322,
    "position": "WITHIN",
    "lookback_stale": false,
    "desc": "Compression shelf over 4 hourly bars; width 0.32x Daily ATR; position: WITHIN."
  },
  "lookback_status": {
    "stale": false,
    "event_type": null,
    "affected_fields": []
  },
  "tactical_stop": {
    "shelf_structural": {
      "price": {"fade_to_upper": 154.68, "breakout_above": 157.03},
      "anchor": "both",
      "atr_buffer_mult": {"fade_to_upper": 0.4, "breakout_above": 0.3},
      "atr_value_used": 1.79
    },
    "atr_volatility": {"price": 153.59, "atr_mult": 1.5, "atr_value_used": 1.79}
  },
  "near_term_target": {
    "mode": "WITHIN",
    "applicable": false
  }
}
```

Confidence observations:
- Engine ran cleanly; no exceptions; no schema gaps; no regressions in adjacent sub-objects (rally_state, swing_breakout_confirmation, trade_setup, etc.)
- `action_summary.verdict` was `INVALID` (CONTEXT REGIME FAILED). `intraday_tactical` correctly emits anyway per DQ-2 — the swing-frame and intraday-frame surfaces are independent
- Profile-A-only contract holding — group present on Profile A; not run against B/C in this smoke, but `TestITS001ProfileScope` covers the B/C absence statically
- Shelf detection produced a sensible result: 4-bar minimum window, $155.39-$157.57 band, tightness 0.32× Daily ATR (well inside the 0.5× threshold), WITHIN classification at $156.27
- WITHIN-mode `tactical_stop.shelf_structural` correctly emitted as a dict with **both** alternates (`fade_to_upper` + `breakout_above`) — Spec §2.7.2 contract
- WITHIN-mode `near_term_target` correctly null + `applicable: false` per DQ-2 semantic-neutrality lock
- ATR consistency check: `atr_value_used: 1.79` matches `trade_snapshot.atr.value: 1.79` and `floor_analysis.hourly_atr` derivation

The Operator separately asked an interpretation question (how to use the surface to identify an entry price) — that is properly Analyst-domain workflow framing (see §9.6 below) and is **not** an implementation defect.

This is a single Profile A smoke sample. The canonical Phase 3 cohort (≥5 Profile A tickers across all three shelf positions + ≥1 `lookback_stale=true` witness + ≥1 `lookback_stale=false` witness per Spec §7 #4-#7) remains for Analyst-led validation.

---

## 9. Open Items for the Analyst

1. **§11 Item 9 resolution review** (§6.1 above) — bless or amend the AVWAP_10BAR annotation decision. Annotated alongside ESTABLISHED_LOW; spec narrative could be canonicalized via v1.0.2 cosmetic update.
2. **Spec §2.1 / §3.4 path vocabulary** (§6.2 above) — consider replacing `floor_analysis.hierarchy` / `target.hierarchy` with engine-actual paths `trade_setup.stop.hierarchy` / `trade_setup.target.hierarchy` in a v1.0.2 cosmetic refinement (no behavior change).
3. **Pytest baseline drift** (§6.3 above) — 3133→3098 drift between RLC-001 S160 and Phase 2 entry. Note in Bug Register / hygiene queue for visibility.
4. **Bug Register status advance** — ITS-001 SPECIFIED → IMPLEMENTED, with file SHAs from §2 above + test-count delta `+75` + pytest cohort summary `3173/4/1`.
5. **Phase 3 cohort selection** — Spec §7 #4 calls for ≥5 Profile A tickers across ABOVE / BELOW / WITHIN positions + ≥1 `lookback_stale=true` witness (gap-and-go names — RGTI-class) + ≥1 `lookback_stale=false` witness (orderly-trend names — FSLR-class). VST is one WITHIN witness from the §8 smoke; 4 more needed across the other two positions plus the stale-witness category.
6. **Operator-workflow guidance** — the Operator asked at hand-back time how to use the `intraday_tactical` block to identify an entry price. The spec deliberately answers "no entry recommendation" per DQ-2 semantic-neutrality lock — but the Analyst may want to author an **Operator Playbook supplement** (or a Doc 3 / Doc 7 cross-link) covering the fade-to-shelf vs. breakout-from-shelf entry mechanics and the Van Tharp R-framework sizing implication. Out of Phase 2 / spec scope; flagged as a user-discoverable gap.
7. **Phase 4 DIA cascade commitment** — Doc 2 §VI / §IV substantive, Doc 7 Step 6 substantive, Doc 8 §II Layer 2 substantive mirror, EEM verify-only, README + PEO Tier closure cascade per Spec §7 #8 and Brief §3.2.
8. **3 Bug Register CONCEPT entries** to log per Spec §9: `INTRADAY-CAL-1` (compression-shelf 0.5× calibration), `INTRADAY-CAL-2` (DQ-4b stop-multiplier calibration), `INTRADAY-CFL-INTEGRATION-1` (v1.1 CFL-001 cross-surface confluence).

---

## 10. Closure-Criteria Tracker (Spec §7)

| # | Criterion | Phase | Status |
|---|---|---|---|
| 1 | Phase 2 hand-back delivered with diff-stat + file SHAs + test counts | Phase 2 close | ✅ (this document — §2, §3.6, §5) |
| 2 | All §6 tests pass; zero existing-test regressions | Phase 2 close | ✅ (75 passed; 0 ITS-caused regressions) |
| 3 | Engine runs cleanly on Profile A test ticker with `intraday_tactical` group in output JSON | Phase 2 close | ✅ (VST live smoke — §8 above) |
| 4 | Live validation cohort: ≥5 Profile A tickers across all 3 shelf positions + ≥1 `lookback_stale=true` + ≥1 `lookback_stale=false` witness | Phase 3 close | ⏳ Phase 3 — Operator-led. VST is 1 WITHIN witness; 4 more needed |
| 5 | RGTI re-run confirms `event_type=GAP_UP` + `lookback_stale=true` on ESTABLISHED_LOW + DAILY_HIGH (+ AVWAP_10BAR per §6.1) | Phase 3 | ⏳ Phase 3 |
| 6 | FSLR re-run confirms `event_type=null` + `lookback_stale=false` on all entries | Phase 3 | ⏳ Phase 3 |
| 7 | Verdict invariance confirmed across live cohort pre/post ITS-001 | Phase 3 | ⏳ Phase 3 — static defense in place via `TestITS001NotInGatesFile` + `TestITS001VerdictInvariance` |
| 8 | 6-doc DIA cascade complete: Doc 2 §VI / §IV, Doc 7 Step 6, Doc 8 §II Layer 2, EEM verify-only, README, PEO | Phase 4 close | ⏳ Phase 4 — Project-chat-Analyst-led |
| 9 | Bug Register entry advances 🔴 IDENTIFIED → 🟠 SPECIFIED → 🟡 IMPLEMENTED → 🟢 SYNCED → ✅ CLOSED | Phase 4 close | 🟡 IMPLEMENTED ready — content available in §2 / §3 above |

---

**End of Hand-Back.** Spec authority remains `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md` v1.0.1. The §6 process deviations (§6.1 Item 9 resolution; §6.2 path-vs-label vocabulary; §6.3 baseline drift) are surfaced for Analyst review but are non-blocking for Phase 3 commencement. Brief §9 halt triggers — none fired.

**Suggested next steps:**
1. Operator reviews diff, optionally commits per Brief §2 (suggested branch `feat/ITS-001-intraday-tactical-surface`)
2. Analyst consumes §6 deviations + §9 open items into the Project chat
3. Operator schedules Phase 3 live cohort (Spec §7 #4-#7)
4. Phase 4 DIA cascade after Phase 3 closes

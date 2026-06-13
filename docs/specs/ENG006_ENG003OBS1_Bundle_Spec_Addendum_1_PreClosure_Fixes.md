# ENG-006 / ENG-003-OBS-1 Bundle Spec — Addendum 1: Pre-Closure Fixes (ENG-006-OBS-1 + EZR-001 + EZR-001-OBS-1)

**Addendum to:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0 (S174).
**Status:** Phase 1 — authored + locked S176. **v1.1 amendment S176-cont** (Phase 2 hand-back fold-in: test-side count-guard enumeration — see §A2.1 v1.1 note + §A4). **v1.2 amendment S176-cont-3** (third pre-closure fold-in `EZR-001-OBS-1` — Profile A PULLBACK `reference.desc`/`reference.price` mismatch surfaced during EZR-001 Phase 3 re-validation; see §A2.3 audit + §A3.3 contract + §A4 case 7. Operator-locked Option (a), S176-cont-2).
**Authoring Analyst:** TBS Analyst (Project chat).
**Single source of truth:** ENG-006 spec v1.0 governs the bundle's existing contracts. This addendum extends v1.0 with two NON-GATE pre-closure fold-ins and **references v1.0 by section — it does not restate v1.0 contracts.**
**Track:** Track 1 (SIR §11.1) — folds into the existing Track 1 bundle; EZR-001 changes the value-meaning of an existing displayed key (`entry_zone.reference.price`), defaulting to Track 1 per SIR §11.5 regardless.
**Branch:** `eng006-eng003obs1-fib-extensions` (Phase 2 re-run uses the SAME branch; no new branch).

---

## §A1. Scope & Lineage

Two defects surfaced during the ENG-006 bundle's S175 Phase 3 live validation, both Operator-authorized as pre-closure fold-ins. The bundle remains 🟡 IMPLEMENTED (Phase 3 complete; v1.0 §7 criteria 3 + 4 MET) and does **not** advance to SYNCED/CLOSED until both fixes land.

| Item | Defect (one line) | Module | Class |
|---|---|---|---|
| **ENG-006-OBS-1** | The three `FIB_EXTENSION_*` hierarchy rows emit `conviction_tier: null / conviction_rank: null` while peer `MEASURED_MOVE` emits `PROJECTION / 4`. | `transform.py` | Map-coverage gap (CNV-001) |
| **EZR-001** | Profile A `entry_zone.reference.price` (and `entry_price_range.lower`) display the **hourly EMA 21 structural floor**, while the desc, the zone bounds, and the pullback gate are all **Daily EMA 21**–based. | `transform.py` (display) | Residual wrong-anchor, ENG-003-OBS-1 class |
| **EZR-001-OBS-1** | Profile A PULLBACK `entry_zone.reference.desc` reverts to the hourly "EMA 21 (Structural Floor)" label while `reference.price` (post-EZR-001) shows Daily EMA 21, on `Entry_Zone_Reference`-absent verdict-gate early-return paths → price/desc mismatch. | `transform.py` (display) | Fix-surfaced by §A3.2 (EZR-001 desc-side counterpart) |

All three are NON-GATE, additive/display-only, verdict-invariant.

---

## §A2. SIR §11.6 Source Audit (branch tip)

Fetched from `roescha/TBS_Master_App` branch `eng006-eng003obs1-fib-extensions` (raw content, S176). The Phase 3 outputs ran from this branch (Operator-confirmed S175-cont-4). Content-addressed git-blob SHAs (evidence anchors):

| File | git-blob SHA |
|---|---|
| `layers/tbs_engine/transform.py` | `998eb1d11da7da754e06e261c0a7fab277e7a6eb` |
| `layers/tbs_engine/output.py` | `19a66af32414ada065e25673cc2ba3ba3e1be04e` |
| `layers/tbs_engine/trigger.py` | `2493e7e556d61d6d43c51e143de8da3ac98f13fd` |

These transform.py + output.py blobs match the S175 at-source verification (the ENG-006 IMPLEMENTED hand-back); base `master@68729ba`. Source confirmed post-ENG-006 (FIB_EXTENSION rows present in transform.py; `Entry_Zone_Reference="Daily EMA 21"` lives in trigger.py, not output.py).

### A2.1 ENG-006-OBS-1 audit

- `_CONVICTION_TIER_MAP` (transform.py:165–192) — 20 entries. The PROJECTION tier (rank 4) holds only `MEASURED_MOVE` (transform.py:183). The three `FIB_EXTENSION_1272 / 1618 / 2618` labels are **absent**.
- `_annotate_conviction(entries)` (transform.py:236–250) tags each row via `_CONVICTION_TIER_MAP.get(_e.get("label"), (None, None))` (transform.py:247) — unmapped labels default to `(None, None)`.
- The three extension rows are appended to `_target_entries` (transform.py:3158–3171, `role.label = "PROJECTION"`); `_annotate_conviction(_target_entries)` runs **after** the append (transform.py:3198) → the labels fall through to `(None, None)`. Confirmed at source — matches every extension-bearing Phase 3 output (ALAB / CRWV / ALB / VTR Profile A; LLY Profile B), profile-independent.
- **Sibling-map audit (SIR §11.6 item 6).** `_CONVICTION_TIER_MAP` is the **only** conviction-tier structure in transform.py (the other module-level maps — `_HIGHER_FRAME_MAP` L101, `_MACRO_FRAME_MAP` L139, `_CFL_STRENGTH_DESC_MAP` L220 — are frame/desc maps, not conviction maps). `_annotate_conviction` is called at three sites (3198 `_target_entries`, 3480 `_floor_entries`, 3538 `_brk_floor_entries`); `FIB_EXTENSION_*` labels appear only in `_target_entries`. Therefore adding the three labels to `_CONVICTION_TIER_MAP` is the **complete** *production* fix — no other production site requires change. This closes the S174 audit-scope gap (S174 item 6 covered `MAPPED_FLAT_KEYS` / `_map_source_to_tier`, not `_CONVICTION_TIER_MAP`).

  **v1.1 note (S176-cont — Phase 2 fold-in).** The sentence above scoped *production* sites only and did not enumerate the **test-side** count-guards. Three external unit tests assert `len(_CONVICTION_TIER_MAP)` (the `== 20` literal), so the spec-mandated 20→23 change trips them: `test_cnv001_conviction_tier.py`, `test_bundle1_regression.py`, `test_ema50001_context_ema_50.py`. These are test-only count assertions — no production/behavioral impact. Each is bumped `20 → 23` with an `[ENG-006-OBS-1] … 20 -> 23` traceability comment mirroring the existing `[DSP-004-OBS-2] … 19 -> 20` idiom; method names and behavioral assertions unchanged. Logged as the audit-completeness gap `ENG-006-OBS-1-AUDIT-GAP-1` (Trivial, RESOLVED-at-logging). This was the one Operator-authorized Phase 2 scope extension; the §11.6 source audit should enumerate `len(<map>)` test-guards alongside production sibling maps on future map-extension specs.

### A2.2 EZR-001 audit + resolution of the three spec-level open items

**Root cause (confirmed at source):**

- `trigger.py:79–99` (**AVWAP-001 DQ-2**, Profile A only, `if p_code == "A"`): defines the entry zone as **Daily EMA 21 ± 0.5× daily ATR** — sets `Pullback_Zone_Lower = Daily EMA 21 − 0.5×ATR` (trigger.py:94), `Pullback_Zone_Upper = Daily EMA 21 + 0.5×ATR` (trigger.py:95), `Entry_Zone_Reference = "Daily EMA 21"` (trigger.py:96), and gates `at_pullback_zone` (trigger.py:90–93) on those Daily-EMA-21 bounds. **Label + zone + gate are correctly Daily-EMA-21-based.** Profile B/C take the `else` branch (trigger.py:100+, hourly-based, unchanged).
- `output.py:2220`: `if not _brk_active: metrics["Entry_Reference"] = metrics.get("Structural_Floor")` — a **blanket non-breakout, all-profile** assignment. For Profile A, `Structural_Floor` = hourly EMA 21. Not updated when AVWAP-001 migrated the Profile A entry anchor → the displayed reference value is the residual hourly floor.
- `transform.py` entry-zone builder (2664–2756): `_entry_ref = flat_metrics.get("Entry_Reference")` (2664) feeds **all three** of `reference.price` (2749), `entry_price_range.lower` (2751), and the inversion guard `_ez_inverted = _entry_ref > _pb_upper` (2746). The desc `_ref_desc` for PULLBACK resolves to `Entry_Zone_Reference` = "Daily EMA 21" (2689/2691) → so price (hourly floor) and desc ("Daily EMA 21") diverge.

**Open item 1 — inversion guard (`_ez_inverted`, transform.py:2746). RESOLVED: leave the guard UNCHANGED.** The fix (§A3.2) is display-only and introduces new display-local variables; it does **not** reassign `_entry_ref`. `_ez_inverted` therefore keeps comparing the structural floor against `Pullback_Zone_Upper` and retains its exact current semantics (a broken EMA structure where the hourly floor sits above the daily zone). The `[INVERTED: EMA structure broken]` desc suffix (2755) and the `entry_price_range` suppression on inversion (2754) are preserved bit-for-bit. *If the fix had instead re-sourced `Entry_Reference`/`_entry_ref` to the Daily EMA 21, the guard would compare `Daily_EMA_21 > (Daily_EMA_21 + 0.5×ATR)` — always false — silently disabling it. The display-only approach avoids this.*

**Open item 2 — re-source site (output.py metric vs transform reference). RESOLVED: transform `reference` construction, NOT the `Entry_Reference` metric.** `Entry_Reference` has a **second consumer**: `output.py:2525` (`_entry_strategy["entry_price"] = metrics.get("Entry_Reference")`), the VALID-path action_summary `entry_strategy` block (gated on `gate_result.entry_type`). Re-sourcing the `Entry_Reference` flat key at output.py:2220 would leak into `entry_strategy.entry_price` on VALID Profile A PULLBACK outputs — an out-of-scope behaviour change (SIR §11.6 item 8, downstream-override-path). A transform-display re-source is surgically scoped to the `entry_zone.reference` / `entry_price_range` rendering and touches nothing else. **Net: `output.py` is NOT in scope for this fix.**

**Open item 3 — fallback-pullback path. RESOLVED: yes, reference.price resolves to Daily EMA 21 on the fallback path too.** `reference.price` renders on both native PULLBACK (`_is_pullback`) and fallback-pullback (`_render_as_pullback_fallback`, transform.py:2685) paths, and the fallback desc already uses `Entry_Zone_Reference` = "Daily EMA 21" (2689). So the Profile A display re-source for `reference.price` is gated on `(_is_pullback OR _render_as_pullback_fallback)`. `entry_price_range` renders on **native** PULLBACK only (transform.py:2754), so its `lower` re-source is gated on `_is_pullback` only — no fallback concern.

**Key availability + null-guard.** `Daily_Protective_Anchor` (transform passthrough L1129) and `Pullback_Zone_Lower` (L1163) are present in `flat_metrics` at the builder site; transform already reads `Daily_Protective_Anchor` at 3343. All three candidate values (`Structural_Floor`, `Daily_Protective_Anchor`, `Pullback_Zone_Lower`) are display-scaled in consistent units. **Within-Profile-A fallback (trigger.py:86–89):** if daily data is unavailable, the zone falls back to the hourly ANCHOR and `Daily_Protective_Anchor` may be `0`/falsy; in that case `Pullback_Zone_Lower` already holds the hourly-ANCHOR value (so `entry_price_range.lower = Pullback_Zone_Lower` is correct in both cases), and `reference.price` must null-guard: use `Daily_Protective_Anchor` only when positive, else fall back to `_entry_ref` (structural floor).

### A2.3 EZR-001-OBS-1 source audit (branch tip — post-Phase-2-fixes re-anchor)

Re-fetched from `roescha/TBS_Master_App` branch `eng006-eng003obs1-fib-extensions` (raw content, S176-cont-3). The §A3.1 conviction-map and §A3.2 price re-source have **landed** since v1.1's audit, so `transform.py` advanced; `output.py` and `trigger.py` are byte-identical to v1.1. Content-addressed git-blob SHAs (evidence anchors), recomputed:

| File | git-blob SHA | vs v1.1 (§A2) |
|---|---|---|
| `layers/tbs_engine/transform.py` | `53ce5351ec7a6a3fbe25a7923d8e8ee37a5bd374` | **changed** — Phase 2 fixes landed (§A3.1 + §A3.2) |
| `layers/tbs_engine/output.py` | `19a66af32414ada065e25673cc2ba3ba3e1be04e` | unchanged (forbidden module untouched) |
| `layers/tbs_engine/trigger.py` | `2493e7e556d61d6d43c51e143de8da3ac98f13fd` | unchanged |

Line anchors below are at the **post-fix** `53ce5351…` blob (the §A2.2 anchors were at the pre-fix `998eb1d1…` blob; the entry-zone builder shifted with the §A3.2 insertion).

**Root cause (confirmed at source — EZR-001-OBS-1 is fix-surfaced by §A3.2):**

- The §A3.2 fix re-sources `reference.price` to `Daily_Protective_Anchor` under the boolean `_is_profile_a AND (_is_pullback OR _render_as_pullback_fallback) AND _daily_anchor > 0` (transform.py:2771–2773). `Daily_Protective_Anchor` is set in `output.py` and is **always present for Profile A**.
- The desc `_ref_desc` (transform.py:2692–2704) on the PULLBACK (2696) and fallback-pullback (2694) branches resolves `flat_metrics.get("Entry_Zone_Reference") or flat_metrics.get("Anchor_Label", "")`. `Entry_Zone_Reference = "Daily EMA 21"` is set **only** by `trigger.py:96`, inside the AVWAP-001 DQ-2 Profile A block (`if p_code == "A"`).
- On Profile A paths where a daily-context verdict gate (e.g. CONTEXT REGIME FAILED) early-returns **before** trigger.py's Profile A block runs, `Entry_Zone_Reference` is never set, so the desc falls back to `Anchor_Label = "EMA 21 (Structural Floor)"` (hourly). `Daily_Protective_Anchor` is still present, so the §A3.2 price re-source still fires → `reference.price` = Daily EMA 21 but `reference.desc` = hourly structural-floor label. **The price-source (`Daily_Protective_Anchor`) and the desc-source (`Entry_Zone_Reference`) diverge on early-return paths.**
- Phase 3 witnesses (S176-cont-2): **CMG** — `reference = {price: 31.17 (Daily EMA 21), desc: "EMA 21 (Structural Floor)"}`, hourly EMA 21 = 31.32 → mismatch. **RTX** (same fallback trigger but blocked later by MID-RANGE, *after* trigger.py ran) — `reference = {price: 179.06, desc: "Daily EMA 21"}` → consistent. The CMG↔RTX contrast isolates `Entry_Zone_Reference` presence as the trigger.

**Spec gap (v1.1):** §A3.2 gated the `reference.price` re-source on `Daily_Protective_Anchor > 0` but did not align the **desc-source** condition with the price-source condition.

**`_ref_desc` consumer + NON-GATE confirmation (SIR §11.6 item 8 — downstream-override-path audit).** `_ref_desc` is assigned only in the 2692–2704 block and consumed only at transform.py:2786 (`_entry_zone["reference"]["desc"]`, a display field). No gate function or verdict path reads it; there is no downstream re-assignment. The §A3.3 desc override is therefore the **last write before consumption** — no leak path.

**Resolution of the three open audit items (resolved at source — the hand-off's "do NOT pre-resolve" items):**

- **Open item 1 — bare literal vs reuse the trigger.py canonical string. RESOLVED: `flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"`.** The runtime `Entry_Zone_Reference` value is *precisely absent* on the defect path, so it cannot be reused there as a value; and `trigger.py:96` is a bare literal with no shared module constant, while refactoring it to one would touch `trigger.py` — **outside the transform-only fence**. The chosen form uses trigger.py's actual emitted value whenever present (set-path: no drift — the desc *is* the trigger's string) and confines the `"Daily EMA 21"` literal to the early-return fallback (the only path where trigger.py never ran, so there is no trigger value to drift against). A traceability comment mirrors `trigger.py:96` (mirrors the `[DSP-004-OBS-2]` traceability-comment idiom).
- **Open item 2 — gate the desc on the exact same boolean as the price re-source. RESOLVED: yes.** Capture a boolean (`_ref_price_is_daily_anchor`) in the branch that assigns `_ref_price = _daily_anchor` (transform.py:2771–2775) and gate the desc override on that same flag. Price and desc then move together **by construction** across all cases — including the within-Profile-A `_daily_anchor ≤ 0` fallback (§A2.2 "Key availability + null-guard"), where neither the price re-source nor the desc override fires, so both correctly stay hourly-based (`reference.price = _entry_ref`, `reference.desc = Anchor_Label`). No re-derived parallel condition that could drift.
- **Open item 3 — RECLAIM / breakout branches untouched. CONFIRMED at source.** `_ref_price_is_daily_anchor` is False on RECLAIM (`_is_reclaim` — neither `_is_pullback` nor `_render_as_pullback_fallback`) and on breakout-active paths, so the override never fires there → RECLAIM keeps "Structural floor (reclaim target)" (2702), breakout keeps "Breakout evaluation price (completed bar close)" (2700), Profile B/C keep their existing desc. (A breakout→pullback *fallback*, where `_render_as_pullback_fallback` is true, correctly *does* receive "Daily EMA 21" — matching the RTX witness; that is the intended §A3.2/§A3.3 behaviour, not a RECLAIM/breakout path.)

---

## §A3. Functional Contracts

### A3.1 ENG-006-OBS-1 — extend `_CONVICTION_TIER_MAP`

Add the three extension labels to `_CONVICTION_TIER_MAP` (transform.py PROJECTION block, after `MEASURED_MOVE`) as peers of the measured move:

```
"FIB_EXTENSION_1272": ("PROJECTION", 4),
"FIB_EXTENSION_1618": ("PROJECTION", 4),
"FIB_EXTENSION_2618": ("PROJECTION", 4),
```

- Tier/rank **`("PROJECTION", 4)`** — Operator-locked (S175-cont-4). Semantically identical projection class to `MEASURED_MOVE`; the rows already carry `role.label = "PROJECTION"`, so `conviction_tier` and `role.label` agree.
- Map size 20 → 23. No other change. `_annotate_conviction(_target_entries)` (3198) annotates the rows once they are mapped. No edit to `_annotate_conviction`, the append block, or any call site.

### A3.2 EZR-001 — Profile A PULLBACK display alignment (transform.py only)

Within the entry-zone builder (transform.py ~2664–2756), align the **displayed** Profile A PULLBACK reference to the AVWAP-001 zone the engine already gates on. The fix is display-only: it adds new display-local values and reuses existing locals; it does **not** reassign `_entry_ref` and does **not** edit the `_ez_inverted` guard.

**Contract (rendered values):**

| Surface | Profile A — native PULLBACK | Profile A — fallback-pullback | Profile A — RECLAIM | Profile A — breakout | Profile B / C (all protocols) |
|---|---|---|---|---|---|
| `entry_zone.reference.price` | **Daily EMA 21** (`Daily_Protective_Anchor`); fall back to structural floor if anchor ≤ 0 | **Daily EMA 21** (same null-guard) | Structural floor (unchanged) | bar close (unchanged) | hourly anchor / structural floor (unchanged) |
| `entry_price_range.lower` | **`Pullback_Zone_Lower`** (Daily EMA 21 − 0.5×ATR) | n/a (range not rendered on fallback) | n/a | n/a | structural floor (unchanged) |
| `entry_price_range.upper` | `Pullback_Zone_Upper` (unchanged) | n/a | n/a | n/a | unchanged |
| `reference.desc` | "Daily EMA 21" (unchanged; now matches price) | "Daily EMA 21" (unchanged) | "Structural floor (reclaim target)" (unchanged) | unchanged | unchanged |
| `_ez_inverted` guard input | structural floor vs zone upper (**unchanged**) | unchanged | unchanged | unchanged | unchanged |

- **Profile detection:** `_db` ("SWING" ⇒ Profile A), consistent with the existing `_epr_desc`/`_ez_bar_label` switches (2703/2727).
- **Protocol scope:** `reference.price` re-source gated on `_is_profile_a AND (_is_pullback OR _render_as_pullback_fallback) AND Daily_Protective_Anchor > 0`. `entry_price_range.lower` re-source gated on `_is_profile_a AND _is_pullback AND Pullback_Zone_Lower` (range renders on native PULLBACK only).
- **RECLAIM / breakout / Profile B / Profile C:** untouched — the re-source conditions exclude them, so they retain the existing `_entry_ref` value.
- **Inversion guard:** `_ez_inverted` (2746), the `[INVERTED]` desc suffix (2755), and `entry_price_range` suppression on inversion (2754) are unchanged.

*Illustrative (non-binding — implementer chooses naming):* compute `_ref_price` (default `_entry_ref`; → `Daily_Protective_Anchor` under the reference gate above) and `_range_lower` (default `_entry_ref`; → `Pullback_Zone_Lower` under the range gate above) immediately before the `_entry_zone` dict; render `"reference": {"price": _ref_price, "desc": _ref_desc} if _ref_price else None` and `"lower": _range_lower`.

### A3.3 EZR-001-OBS-1 — Profile A PULLBACK desc alignment (transform.py only)

The **desc-side counterpart to §A3.2.** When §A3.2 re-sources `reference.price` to the Daily EMA 21 protective anchor, `reference.desc` must read **"Daily EMA 21"** rather than falling back to the hourly `Anchor_Label` on `Entry_Zone_Reference`-absent (verdict-gate early-return) paths. Display-only; gated on the **same boolean** as the §A3.2 price re-source, so price and desc move together by construction. Operator-locked **Option (a)** (S176-cont-2). Option (b) — gating the §A3.2 price re-source on `Entry_Zone_Reference` presence — was **rejected** (it would surrender the semantically-correct Daily EMA 21 price on early-return paths).

**Contract (rendered `reference.desc`):**

| Profile A path | `reference.price` (§A3.2) | `reference.desc` (§A3.3) |
|---|---|---|
| native PULLBACK, `Daily_Protective_Anchor > 0` | Daily EMA 21 | **"Daily EMA 21"** |
| fallback-pullback, `Daily_Protective_Anchor > 0` | Daily EMA 21 | **"Daily EMA 21"** |
| PULLBACK / fallback, `Daily_Protective_Anchor ≤ 0` (within-Profile-A fallback) | structural floor (`_entry_ref`) | hourly `Anchor_Label` (**unchanged** — matches the floor price) |
| RECLAIM | structural floor (unchanged) | "Structural floor (reclaim target)" (unchanged) |
| breakout | bar close (unchanged) | breakout desc (unchanged) |
| Profile B / C (all protocols) | unchanged | unchanged |

- **Desc value source:** `flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"` (open item 1). Set-path → trigger.py's emitted value; early-return path → the literal fallback. Traceability comment mirrors `trigger.py:96`.
- **Gate:** the desc override fires on the **same** boolean that re-sourced `reference.price` to `Daily_Protective_Anchor` (open item 2) — i.e. `_is_profile_a AND (_is_pullback OR _render_as_pullback_fallback) AND Daily_Protective_Anchor > 0`.
- **RECLAIM / breakout / Profile B / Profile C:** untouched (open item 3) — the override condition excludes them.
- **No reassignment of `_entry_ref`; no edit to `_ez_inverted` (2756), the `[INVERTED]` desc suffix, or any render gate.** The override only conditionally re-assigns the display-local `_ref_desc` after the §A3.2 price block and before the `_entry_zone` dict (consumer at 2786).

*Illustrative (non-binding — implementer chooses naming):* in the §A3.2 branch that sets `_ref_price = _daily_anchor`, also set `_ref_price_is_daily_anchor = True` (and `False` in the `else`); then immediately before the `_entry_zone` dict add `if _ref_price_is_daily_anchor: _ref_desc = flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"`.

---

## §A4. Test Mandate

Append to the existing ENG-006 bundle test file (same Phase 2 re-run, same branch). All tests operate on transform-layer output from crafted `flat_metrics` fixtures — no IBKR/runtime dependency.

1. **ENG-006-OBS-1 — conviction non-null.** Assert `_CONVICTION_TIER_MAP` maps each of `FIB_EXTENSION_1272/1618/2618` to `("PROJECTION", 4)`; and that the three extension rows surfaced in `trade_setup.target.hierarchy` carry `conviction_tier == "PROJECTION"` and `conviction_rank == 4` (non-null).
2. **EZR-001 — Profile A PULLBACK alignment.** With a Profile A (SWING) native-PULLBACK fixture: `entry_zone.reference.price == Daily_Protective_Anchor` and `entry_zone.entry_price_range.lower == Pullback_Zone_Lower` (and `upper == Pullback_Zone_Upper`).
3. **EZR-001 — fallback-pullback.** Profile A fallback-pullback fixture (`_render_as_pullback_fallback` true): `reference.price == Daily_Protective_Anchor`; `entry_price_range is None` (not rendered on fallback).
4. **EZR-001 — null-guard.** Profile A PULLBACK fixture with `Daily_Protective_Anchor` ≤ 0: `reference.price` falls back to the structural floor (no null/zero reference emitted).
5. **Regression guards (must be unchanged).**
   - Profile A RECLAIM: `reference.price == Structural_Floor`, desc "Structural floor (reclaim target)".
   - Profile B PULLBACK and Profile C: `reference.price` == existing hourly anchor / structural floor (unchanged).
   - Inversion: fixture with structural floor > `Pullback_Zone_Upper` → `entry_price_range is None`, desc contains "[INVERTED: EMA structure broken]".
6. **NON-GATE / verdict invariance.** `TestBundleNotInGatesFile` (negative `inspect.getsource()` assertion — neither fix adds a key read by any gate function) and `TestBundleVerdictInvariance` (same fixtures, same verdict pre/post) pass.
7. **EZR-001-OBS-1 — desc/price consistency (v1.2).** Profile A (SWING) PULLBACK fixture with `Daily_Protective_Anchor > 0` and **`Entry_Zone_Reference` unset** (simulating a verdict-gate early-return before trigger.py's Profile A block — the CMG case): assert `entry_zone.reference.desc == "Daily EMA 21"` **and** `entry_zone.reference.price == Daily_Protective_Anchor` (price and desc consistent). Companion sub-assertions:
   - **Set-path no-regression:** Profile A PULLBACK fixture with `Entry_Zone_Reference == "Daily EMA 21"` present (the INSW witness) → `reference.desc == "Daily EMA 21"` (uses the runtime value; unchanged from pre-fix).
   - **Within-Profile-A fallback consistency:** Profile A PULLBACK fixture with `Daily_Protective_Anchor` ≤ 0 → `reference.price` == structural floor **and** `reference.desc` == hourly `Anchor_Label` (both hourly; neither override fires).
   - **RECLAIM desc unchanged:** `reference.desc == "Structural floor (reclaim target)"`.
   - **Profile B / C desc unchanged.**
   (Case 6 `TestBundleNotInGatesFile` already covers the new desc local — `_ref_desc` is read by no gate function; `TestBundleVerdictInvariance` covers same-fixture verdict invariance.)

**Test-file scope (v1.1, S176-cont).** Primary test target: the existing ENG-006 bundle test file (`test_eng006_eng003obs1_fib_extensions.py`) — the §A4 cases (1–6) append here. **Plus** three external count-guard test files whose `len(_CONVICTION_TIER_MAP) == 20` literals are bumped to `23` (test-only; see §A2.1 v1.1 note): `test_cnv001_conviction_tier.py`, `test_bundle1_regression.py`, `test_ema50001_context_ema_50.py`.

**Test-file scope (v1.2, S176-cont-3).** Case 7 (EZR-001-OBS-1) appends to the **same** ENG-006 bundle test file (`test_eng006_eng003obs1_fib_extensions.py`). No new external files and no further count-guard bumps — the desc fix touches no map size.

---

## §A5. NON-GATE / Verdict-Invariance Assertion

All three fixes are NON-GATE and verdict-invariant:

- **ENG-006-OBS-1** annotates informational hierarchy metadata (`conviction_tier`/`conviction_rank`) that no gate function or verdict path consumes; `transform.py`-only, additive.
- **EZR-001** corrects display values (`entry_zone.reference.price`, `entry_price_range.lower`) only. The pullback gate (`at_pullback_zone`, trigger.py:90–93) already uses the Daily-EMA-21 bounds; `Entry_Reference`/`Entry_Zone_Reference` are output-only (not read by `gates.py`/`compute.py`). Aligning the display to the zone the engine already gates on moves no verdict. The `Entry_Reference` flat key is left unchanged, so the `entry_strategy.entry_price` consumer (output.py:2525) is unaffected.
- **EZR-001-OBS-1** corrects the display `reference.desc` only, on `Entry_Zone_Reference`-absent paths, gated on the same boolean as the §A3.2 price re-source. `_ref_desc` is consumed only at transform.py:2786 (display) and read by no gate function or verdict path (`TestBundleNotInGatesFile`). Verdict-invariant.

---

## §A6. Documentation Impact Assessment (Cross-Reference Impact Matrix)

Engine-first: consumer (orchestrator/scanner) impact is informational and **non-blocking** (ORCH-002 rewrite pending; scanner trivial). DIA fires at Phase 4, folded into the ENG-006 bundle's existing pending cascade.

| Document | Baseline | Impact | Action |
|---|---|---|---|
| **Doc 2** (Core Strategy) | v8.67 | Profile A entry-zone description (§IV / §4.2.4): displayed reference is the Daily EMA 21 zone center (was structural floor); extension rows carry conviction tier. | Edit — fold into ENG-006 bundle Doc 2 entry |
| **Doc 7** (Daily Battle Card) | v8.5.57 | Step 6 entry-zone read (reference now Daily EMA 21 for Profile A PULLBACK); conviction tier visible on extension hierarchy rows. | Edit |
| **Doc 8** (Systemic Automation / Data Retrieval) | v8.7.67 | §II Layer 2 output contract: `entry_zone.reference.price` / `entry_price_range.lower` semantics for Profile A PULLBACK; `conviction_tier`/`conviction_rank` populated on `FIB_EXTENSION_*` rows. | Edit |
| **EEM** (Engine Execution Map) | v2.42 | No new functions; `_CONVICTION_TIER_MAP` + entry-zone builder already mapped. | Verify-only |
| **README** | v8.6.37 | Version line + amendment list. | Edit (version bump) |
| **PEO** | v9.29 | Tier 2D (ENG-006) + Tier 2G (ENG-003-OBS-1) closure rows; ENG-006-OBS-1 + EZR-001 closure. | Edit |
| **Bug Register** | (S-current) | ENG-006-OBS-1 + EZR-001 status advance through SPECIFIED → … → CLOSED; bundle closure. | Edit |
| Consumers (orchestrator / scanner) | — | Informational only. | Non-blocking note |

**v1.2 note (EZR-001-OBS-1).** The desc alignment is fully enclosed by the existing Doc 2 / Doc 7 / Doc 8 entry-zone-description rows above — it corrects the displayed `reference.desc` to match the already-documented Daily-EMA-21 `reference.price`, so the Profile A PULLBACK reference now reads consistently (price + desc). No new document or matrix row arises; EEM remains verify-only.

---

## §A7. Closure Criteria

- **C1 (ENG-006-OBS-1):** an extension-bearing live output shows `conviction_tier == "PROJECTION"`, `conviction_rank == 4` on the `FIB_EXTENSION_*` rows.
- **C2 (EZR-001):** a live Profile A **PULLBACK** output shows `entry_zone.reference.price == Daily EMA 21` and `entry_price_range.lower == Pullback_Zone_Lower`.
- **C2-OBS (EZR-001-OBS-1):** a live Profile A **PULLBACK** output on a verdict-gate-early-return ticker (CMG-class — `Entry_Zone_Reference` unset) shows `entry_zone.reference.desc == "Daily EMA 21"`, matching `reference.price`.
- **C3 (regression):** Profile A RECLAIM reference unchanged (structural floor, desc "Structural floor (reclaim target)"); Profile B/C reference + desc unchanged; inversion behaviour unchanged; within-Profile-A `Daily_Protective_Anchor ≤ 0` fallback keeps price and desc hourly-consistent.
- **C4 (NON-GATE):** `NotInGatesFile` + `VerdictInvariance` green.
- **C5 (DIA):** Phase 4 cascade complete across §A6 documents.
- **C6 (bundle):** ENG-006 + ENG-003-OBS-1 + ENG-006-OBS-1 + EZR-001 advance 🟡 IMPLEMENTED → 🟢 SYNCED → ✅ CLOSED; branch merged to master (Operator action). ORQ-001 (Tier 2B) returns to first position.

---

## §A8. SIR §5 Optimal-Path Self-Check

Two approaches were considered for EZR-001:

- **(A) Edit `output.py:2220`** to make `Entry_Reference` Profile-A-PULLBACK-conditional (the hand-off's anticipated "likely edit site"). **Rejected** — it leaks into the second `Entry_Reference` consumer (`entry_strategy.entry_price`, output.py:2525) on VALID Profile A PULLBACK outputs, cannot independently produce `entry_price_range.lower == Pullback_Zone_Lower` (it would set the lower bound to the zone center), and disables the `_ez_inverted` guard. Larger blast radius, two files, two layers.
- **(B) Transform-display-only re-source** (this addendum). **Selected** — single file, single layer, single output surface; preserves the inversion guard bit-for-bit; leaves the `entry_strategy.entry_price` consumer untouched; produces the exact locked contract (reference = Daily EMA 21, range.lower = `Pullback_Zone_Lower`).

This narrows the Phase 2 scope to **`transform.py` + test file only** (`output.py` is NOT touched), a deviation from the hand-off's anticipated edit sites that the hand-off explicitly left for the §11.6 audit to resolve ("do NOT pre-resolve"). The Operator-locked **fix direction** (displayed values → Daily EMA 21 / `Pullback_Zone_Lower`, protocol-scoped) is fully honored.

**v1.2 fold-in (EZR-001-OBS-1 desc alignment).** Two implementation approaches were considered:

- **(A) Restructure the desc block** (2692–2704) to compute the price-re-source boolean earlier and branch the desc there. **Rejected** — larger edit surface inside a block shared by the RECLAIM / breakout / Profile B-C branches; higher regression risk for no functional gain.
- **(B) Post-§A3.2 desc override** gated on the captured `_ref_price_is_daily_anchor` flag. **Selected** — minimal surface (one captured boolean + one conditional `_ref_desc` reassignment immediately before the `_entry_zone` dict); guarantees price and desc move together by construction; leaves the existing desc block, the RECLAIM / breakout / B-C branches, `_entry_ref`, and `_ez_inverted` untouched.

The within-fence literal resolution (open item 1) — `Entry_Zone_Reference or "Daily EMA 21"` — keeps the trigger.py coupling on the set-path and confines the literal to the early-return fallback; `trigger.py` is **not** refactored to a shared constant, which would breach the fence. Scope stays **`transform.py` (desc) + the ENG-006 bundle test file only**; `output.py` / `trigger.py` / `_entry_ref` / `_ez_inverted` / the §A3.2 price re-source all unchanged. Operator-locked Option (a) is fully honored.

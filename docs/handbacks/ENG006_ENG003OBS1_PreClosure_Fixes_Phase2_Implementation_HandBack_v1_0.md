# ENG-006-OBS-1 + EZR-001 Pre-Closure Fixes — Phase 2 Implementation Hand-Back v1.0

**Hand-Back ID:** `ENG006_ENG003OBS1_PreClosure_Fixes_Phase2_Implementation_HandBack_v1_0`
**Template:** ACP §6.5 canonical 10-section · **Phase:** 2 (Claude Code CLI), delivered in-session
**Spec authority:** ENG-006 Bundle Spec v1.0 **+ Addendum 1** (`ENG006_ENG003OBS1_Bundle_Spec_Addendum_1_PreClosure_Fixes.md`)
**Brief consumed:** `ENG006_ENG003OBS1_PreClosure_Fixes_Implementation_Brief_v1_0.md` v1.0
**Branch:** `eng006-eng003obs1-fib-extensions` (existing; base `master@68729ba`)
**Status at delivery:** Both §A3 fixes applied; +17 §A4 tests GREEN; full suite **3321 passed / 4 skipped / 0 failed** from both CWDs. One Operator-authorized scope extension (three external count-guards).

---

## §1. Mission Outcome

| Item | Action | Result |
|---|---|---|
| ENG-006-OBS-1 (§A3.1) | `_CONVICTION_TIER_MAP` += `FIB_EXTENSION_1272/1618/2618` = `("PROJECTION", 4)`; map 20→23 | ✅ Applied |
| EZR-001 (§A3.2) | Transform-display re-source: Profile A PULLBACK `reference.price`→Daily EMA 21, `entry_price_range.lower`→`Pullback_Zone_Lower`; `_entry_ref`/`_ez_inverted` untouched | ✅ Applied |
| §A4 tests | +17 cases appended to the ENG-006 bundle test file | ✅ All green |
| Scope-extension (authorized) | 3 external conviction-count guards bumped 20→23 | ✅ Applied |

## §2. Scope & Authority

- **Authority:** Addendum wins over Brief; both read in full before editing.
- **In-scope (planned):** `layers/tbs_engine/transform.py` (two edits) + `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py`.
- **Scope extension (Operator-authorized this session):** `test_cnv001_conviction_tier.py`, `test_bundle1_regression.py`, `test_ema50001_context_ema_50.py` — count-guard assertions `20→23` only (see §6).
- **Forbidden production modules:** none touched. `output.py:2220` / `Entry_Reference` / `_entry_ref` / `_ez_inverted` unchanged (verified §7).

## §3. What Was Built

Post-edit blob SHAs: `transform.py` `53ce5351…`; bundle test file `0c8bf95d…`.

- **§A3.1:** three dict lines after `MEASURED_MOVE` in the PROJECTION block; no change to `_annotate_conviction`, the append block, or call sites.
- **§A3.2:** display-locals `_is_profile_a` / `_daily_anchor` / `_pb_lower` / `_ref_price` / `_range_lower` before the `_entry_zone` dict; `reference.price`→`_ref_price`, `entry_price_range.lower`→`_range_lower`. Reference gated on `_is_profile_a AND (_is_pullback OR _render_as_pullback_fallback) AND _daily_anchor > 0`; range-lower on `_is_profile_a AND _is_pullback AND _pb_lower`. `_entry_ref`/`_ez_inverted`/`[INVERTED]` desc/range-suppression gate left bit-for-bit.

## §4. Pre-Implementation Verification (Brief §4 / Addendum §A2)

All anchors matched; all three blob SHAs matched §A2 exactly (`transform.py` `998eb1d1…`, `output.py` `19a66af3…`, `trigger.py` `2493e7e5…`). Confirmed map @165–192 (PROJECTION = MEASURED_MOVE only); `_annotate_conviction` `.get(label,(None,None))` @247 called @3198 post-append @3158–3171; entry-zone builder 2664–2756 (`_entry_ref`@2664→reference@2749/range@2751/`_ez_inverted`@2746; `_is_pullback`@2671/`_render_as_pullback_fallback`@2685; `_db` SWING @2703/2727); passthroughs @1129/@1163, precedent @3343; second consumer `output.py:2525`. No drift → no §4 halt.

## §5. Test Outcome

- **Full unit suite (both CWDs):** `3321 passed / 4 skipped / 0 failed`. Baseline 3304 → **+17** (new §A4 cases); count-guards still pass (now assert 23).
- **§A4 cases (+17):** conviction non-null ×3; alignment ×2; fallback-pullback ×1; null-guard ×2; regression guards ×4 (RECLAIM / Profile B / Profile C / inversion); NON-GATE ×1; verdict-invariance ×4.
- **Differential-verified:** with `transform.py` stashed to pre-edit, the 6 positive assertions FAIL (conviction null; `reference.price` = `124.0` residual floor vs `128.0` Daily EMA 21); regression/null-guard tests pass both sides. Post-edit: all 50 pass.

## §6. Process Deviation

**One — Operator-authorized scope extension.** Addendum §A2.1 stated the map addition was "the complete fix — no other site requires change," but did not enumerate three external count-guard tests asserting `len(_CONVICTION_TIER_MAP) == 20`. The spec-mandated 20→23 change tripped them. Halted (Brief §9: regression-guard failure + audit incompleteness); Operator authorized the minimal extension. Each guard bumped `20→23` with an `[ENG-006-OBS-1] … 20 -> 23` traceability comment matching the existing `[DSP-004-OBS-2] … 19 -> 20` idiom; method names retained; no behavioral assertion changed. **Recommend the Analyst fold this into Addendum §A2.1/§A4.**

## §7. Pre-Delivery Verification (SIR §9)

✅ Content accuracy · ✅ Internal consistency (no `output.py`/`_entry_ref`/`_ez_inverted` change; RECLAIM/B/C/breakout green) · ✅ Format integrity · ✅ Scope discipline (transform.py + 4 test files; no forbidden production module) · ✅ Gate-function verification (`NotInGatesFile` green) · ✅ Module-import (no new imports in transform.py) · ✅ VerdictInvariance + NotInGatesFile green.

## §8. Live-Sampling Smoke Check (Operator, pre-Phase-3)

Pending. **C1** — extension-bearing output shows `conviction_tier="PROJECTION"`/`conviction_rank=4`. **C2** — Profile A PULLBACK output shows `entry_zone.reference.price == Daily EMA 21` and `entry_price_range.lower == Pullback_Zone_Lower`.

## §9. Open Items for the Analyst

1. Addendum §A2.1 audit gap (§6): fold the three count-guard updates into the Addendum/Bug Register.
2. Phase 3 re-validation needs: (a) one extension-bearing output (C1); (b) one Profile A PULLBACK output (C2).
3. No outstanding code questions; §A2.2 open items 1–3 honored as resolved.

## §10. Closure-Criteria Tracker (Addendum §A7)

| | Criterion | Status |
|---|---|---|
| C1 | Extension rows non-null conviction | ⏸ Live (Operator); static tests green |
| C2 | Profile A PULLBACK reference/range aligned | ⏸ Live (Operator); static tests green |
| C3 | RECLAIM/B/C/inversion unchanged | ✅ Regression tests green |
| C4 | NotInGatesFile + VerdictInvariance | ✅ Green |
| C5 | DIA cascade (§A6) | ⏸ Phase 4 |
| C6 | Bundle → SYNCED → CLOSED; branch merge | ⏸ Operator |

---

### Sign-off
Implementer: Claude Code CLI (Opus 4.8). Branch `eng006-eng003obs1-fib-extensions`. Halt protocol: one halt (§6), resolved by Operator authorization. Ready for Phase 3 re-validation + Phase 4 DIA cascade.

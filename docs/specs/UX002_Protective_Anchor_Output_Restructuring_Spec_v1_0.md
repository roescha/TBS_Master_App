# UX-002 — Protective Anchor Output Restructuring

**Spec Version:** v1.0
**Status:** SPECIFIED (pending Operator lock)
**Bug Register ID:** UX-002 (Tier 2F)
**Type:** Enhancement (UX / Output Clarity)
**Severity:** Low — output-shape change only; zero gate / verdict / threshold / sizing impact
**Track:** Track 1 (SIR §11.1) — see §3
**Author:** TBS Analyst (Project chat)
**Governing process:** Amendment Control Process v1.3
**Engine source basis:** `roescha/TBS_Master_App@master` (audited at Phase 1; implementer re-verifies at Phase 2 entry per Brief §4)

---

## §1 Purpose / Problem Statement

`floor_analysis.protective_anchor` was introduced by PA-001 to contrast the daily protective anchor (Daily EMA 21) with the then-entry anchor (session VWAP). After **AVWAP-001** replaced the entry anchor with **Hourly EMA 21**, both anchors are "EMA 21" at different timeframes, leaving "protective anchor" semantically opaque. The section also carries data duplicated elsewhere:

1. **Naming confusion.** "Protective anchor" is no longer a meaningful contrast post-AVWAP-001.
2. **Redundant data.** The anchor `price` (Daily EMA 21) duplicates `floor_analysis.higher_frame.ema.ema_21`; the `hard_stop` duplicates the `DAILY_HARD_STOP` entry in `trade_setup.stop.hierarchy`.
3. **Orphaned datum.** Of the group's three fields, only `daily_atr` has no other home.

UX-002 relocates `daily_atr` into `higher_frame`, retires the redundant section, and leaves the daily hard stop where it already lives in the stop hierarchy.

---

## §2 Scope

- **Profile A only.** Profiles B and C never populated `protective_anchor` (guarded by `Daily_Protective_Anchor > 0`, which is Profile-A-only per `data.py:690`). B/C output is byte-identical pre/post.
- **Output-shape change only.** Zero gate, verdict, threshold, sizing, or numeric change. No gate function reads any affected flat key (asserted in §6).
- **Net effect:** remove one grouped section (`floor_analysis.protective_anchor`); add one sub-object (`higher_frame.daily_atr`); re-home three flat keys in the `_flatten()` dev-utility reverse map. No flat key is removed from the engine; no upstream consumer is touched.

---

## §3 Vocabulary & Track Classification

**Track 1.** Although the file scope (`output.py` + `transform.py`) is Track-2-admissible, the change **removes a grouped output section** (and the SIR §11.2 criterion forbids removed fields / non-additive shape changes). Track 2 is forfeited → Track 1 full Phase 0→4 lifecycle. UX-002 is the **first validation cohort for the SIR §11.6 Analyst Pre-Spec-Delivery Source Audit Checklist** (§11 below).

Phase 2 lexicon is restructuring-only: `relocate`, `remove section`, `re-home reverse map`. Out-of-scope words that signal drift: any gate/verdict/threshold vocabulary, any Profile B/C edit, any change to the `Daily_Protective_Anchor` / `Daily_Hard_Stop` flat-key writers or their internal consumers.

---

## §4 Implementation Specification

All edits are in `tbs_engine/transform.py`. `output.py` is **verify-only** (writers retained). Line anchors are master-as-audited (`~` approximate per project convention); the Phase 2 implementer re-verifies via Brief §4.

### §4.1 Change 1 — relocate `daily_atr` into `higher_frame` (Profile A)

In the `higher_frame` assembly block (`transform.py:~1769-1901`), inside the Profile-A (`DAILY` timeframe) path, add a sibling sub-object preserving the current shape (DQ-3):

```python
# [UX-002] Daily ATR relocated here from the retired protective_anchor section.
_daily_atr_val = flat_metrics.get("Daily_ATR")
if _p_code == "A" and _daily_atr_val is not None:
    higher_frame["daily_atr"] = {
        "value": _daily_atr_val,
        "unit": "price",
        "desc": "Daily ATR(14) -- swing-frame volatility unit",
    }
```

Guard: Profile A **and** `Daily_ATR` present. `Daily_ATR` is written upstream at `output.py:2603` (before the transform layer reads `flat_metrics`), so it is available at assembly time (pipeline-order confirmed, §11 ITEM 4).

### §4.2 Change 2 — `DAILY_HARD_STOP` desc (VERIFY-ONLY, per DQ-2)

**No edit.** The stop-hierarchy entry at `transform.py:3409-3417` already carries the formula in `role.desc` (`:3414`):

```
"Daily hard stop -- EMA 21 - 1.5x Daily ATR (swing-frame last resort)"
```

The S114 register proposal to interpolate live numeric values into the desc is **declined** — value-interpolation conflicts with the self-doc desc convention (RISK-001…AS-001 batch: descs are formula-text, not interpolated values) and would be the only value-interpolated desc in the schema. The implementer confirms this desc is present and unchanged.

### §4.3 Change 3 — remove the `protective_anchor` output group + re-home the reverse map

**(a)** Delete the group emission block at `transform.py:2087-2097` in its entirety (the `_daily_prot_anchor` / `_daily_hard_stop_val` / `_daily_atr_val` reads at `:2088-2090`, the `> 0` guard at `:2092`, and the `floor_analysis["protective_anchor"] = {...}` assignment at `:2092-2096`). The `daily_atr` read relocates to §4.1.

**(b)** Delete the `protective_anchor` reverse-map block in `_flatten()` at `transform.py:4435-4443`, and re-home all three flat keys to their canonical grouped homes (EMA50-001-OD-2 symmetry discipline; feasibility confirmed in §11 ITEM 7 — `_flatten(grouped)` receives the full output at `:4013` / `:4274`):

| Flat key | New reverse-map source | Notes |
|---|---|---|
| `Daily_ATR` | `higher_frame.daily_atr.value` | add in the higher_frame reverse-map block, DAILY branch (`~:4312-4323`) |
| `Daily_Protective_Anchor` | `higher_frame.ema.ema_21` | numerically equal on Profile A per DQ-4 |
| `Daily_Hard_Stop` | `trade_setup.stop.hierarchy[]` entry with `label == "DAILY_HARD_STOP"` | reachable via `grouped.get("trade_setup")`; existing stop-hierarchy reverse-map infra at `~:4817` |

### §4.4 Retained / explicitly untouched (§11 ITEM 8)

These are **not** changed — UX-002 removes output *surfacing* only, not the flat keys or their internal consumers:

- `Daily_Protective_Anchor` flat key: writer `output.py:2590`; membership set `transform.py:1127`; consumed at `transform.py:3297` (Profile A Daily EMA 21 floor-hierarchy entry) and `output.py:2873-2874` (Extension_Anchor). **All retained.**
- `Daily_Hard_Stop` flat key: writer `output.py:2598`; `DAILY_HARD_STOP` stop-hierarchy entry `transform.py:3409-3417`. **Retained** (desc verify-only per §4.2).
- ctx attributes `daily_protective_anchor` / `daily_atr` / `daily_hard_stop`: untouched.
- Profiles B/C: byte-identical pre/post.
- No new imports; module import graph stays acyclic (`types → helpers → {gates, data, compute, exit} → {trigger, output} → main`).

---

## §5 Pipeline & Call-Order

| Stage | Site | Role under UX-002 |
|---|---|---|
| compute (data.py) | `data.py:688-693` | `daily_ema21` / `daily_atr_val` / `daily_hard_stop` from `df_ctx` last bar — **unchanged** |
| output (scaler) | `output.py:2588-2603` | writes `Daily_Protective_Anchor` / `Daily_Hard_Stop` / `Daily_ATR` flat keys — **unchanged (verify-only)** |
| transform (group) | `transform.py:~1769-1901` | **Change 1**: add `higher_frame.daily_atr` |
| transform (group) | `transform.py:2087-2097` | **Change 3a**: delete `protective_anchor` emission |
| transform (hierarchy) | `transform.py:3409-3417` | `DAILY_HARD_STOP` entry — **verify-only (Change 2)** |
| transform (_flatten) | `transform.py:4435-4443` + `~4312-4323` + `~4817` | **Change 3b**: re-home reverse map |

---

## §6 Test Plan

New test file: `layers/tests/unit/test_ux002_protective_anchor_restructure.py` (post-TEST-HRN-001 idempotent module-loading guard).

| Class | Assertion |
|---|---|
| `TestUX002HigherFrameDailyAtr` | Profile A `higher_frame.daily_atr == {value, unit:"price", desc}`; `value == Daily_ATR`; absent on B/C |
| `TestUX002ProtectiveAnchorRemoved` | `floor_analysis` has no `protective_anchor` key on Profile A; B/C unchanged (never had it) |
| `TestUX002FlattenSymmetry` | round-trip: `_flatten()` recovers `Daily_ATR` (from `higher_frame.daily_atr`), `Daily_Protective_Anchor` (from `higher_frame.ema.ema_21`), `Daily_Hard_Stop` (from stop hierarchy) |
| `TestUX002ProfileBCInvariance` | Profile B/C grouped output byte-identical pre/post |
| `TestUX002VerdictInvariance` | same fixture → same verdict pre/post |
| `TestUX002NotInGatesFile` | `inspect.getsource`-based negative assertion: no gate function reads `Daily_Protective_Anchor` / `Daily_ATR` / `Daily_Hard_Stop` |

Regression: full unit cohort, zero UX-002-attributable regressions (dual-CWD if relevant).

---

## §7 Closure Criteria

1. Phase 2 Hand-Back received (ACP §6.5).
2. New tests pass; zero regressions.
3. Live validation ≥3 Profile A tickers: `higher_frame.daily_atr` present, `protective_anchor` absent, anchor price recoverable from `higher_frame.ema.ema_21`.
4. Verdict invariance verified live (Profile A) + B/C invariance confirmed.
5. IMPLEMENTED Bug Register entry logged with `file:line` + SHAs + helper/edit sites.
6. Spec verified against final source state.
7. Phase 4 DIA cascade complete (§8).

---

## §8 Documentation Impact Assessment (DIA)

Per ACP §5 Cross-Reference Impact Matrix (`ibkr_purity_engine.py` → Doc 2 SSoT; Doc 7 Step 6 / Doc 8 §II Layer 2 / Exec Map secondary):

| Document | Section(s) | Change Required | Status |
|---|---|---|---|
| Doc 2 (Core Strategy) | §IV Output Schema Reference | Remove `protective_anchor` row; add `higher_frame.daily_atr`; note `DAILY_HARD_STOP` desc verify-only | PENDING (substantive) |
| Doc 8 (Automation) | §II Layer 2 | Mirror — PA-001 bullet: `protective_anchor` → `higher_frame.daily_atr` | PENDING (substantive) |
| Doc 7 (Battle Card) | Step 6 | Scan-only | PENDING (scan) |
| Engine Execution Map | §II | Verify-only — no gate touched, cascade bitwise-invariant | PENDING (verify-only) |
| README | Document Authority + Last Updated | Housekeeping cascade | PENDING |
| PEO | §2F + ASCII map + Document History | §2F → ✅ CLOSED | PENDING |

---

## §9 Design Question Resolutions

- **DQ-1 (Operator-confirmed):** Remove the **output group** + its `_flatten` reverse-map entries; **keep** the `Daily_Protective_Anchor` flat key. Rationale: live internal consumers at `transform.py:3297` (floor entry) and `output.py:2873` (extension). The S114 register's "flat key removed" is superseded.
- **DQ-2 (Operator-confirmed):** Change 2 → **verify-only**. Formula already present at `transform.py:3414`; numeric interpolation declined (self-doc desc convention).
- **DQ-3 (Operator-confirmed):** `daily_atr` shape in `higher_frame` preserved as `{value, unit, desc}` (zero-churn vs current `transform.py:2096` emission).
- **DQ-4 (resolved from source):** `Daily_Protective_Anchor` and `Context_EMA_21` (= `higher_frame.ema.ema_21`) both reduce to `round(df_ctx['EMA_21'].iloc[-1] / price_scaler, 2)` on Profile A (`data.py:688-691` / `output.py:2590` vs `gates.py:25,49,55` / `transform.py:1688`). Equal wherever the group is emitted (the `daily_ema21` ATR-NaN edge is already group-suppressed by the `>0` guard). **Dropping the group's `price` field is lossless.**

---

## §10 Worked Example (Profile A; illustrative values — LLY-style, not live output)

Daily EMA 21 = 941.09, Daily ATR = 27.8, hard stop = 941.09 − 1.5×27.8 = 899.39.

**Before:**

```json
"floor_analysis": {
  "higher_frame": { "ema": { "ema_21": 941.09, "...": "..." }, "...": "..." },
  "protective_anchor": {
    "price":     { "value": 941.09, "unit": "price", "desc": "Daily EMA 21 -- swing-frame protective floor" },
    "hard_stop": { "value": 899.39, "unit": "price", "desc": "Daily hard stop = EMA 21 - 1.5x Daily ATR" },
    "daily_atr": { "value": 27.8,   "unit": "price", "desc": "Daily ATR(14) -- swing-frame volatility unit" }
  }
}
```

**After:**

```json
"floor_analysis": {
  "higher_frame": {
    "ema": { "ema_21": 941.09, "...": "..." },
    "...": "...",
    "daily_atr": { "value": 27.8, "unit": "price", "desc": "Daily ATR(14) -- swing-frame volatility unit" }
  }
}
```

`trade_setup.stop.hierarchy` `DAILY_HARD_STOP` entry (price 899.39, desc, conviction tier) — unchanged.

---

## §11 Pre-Implementation Checklist (SIR §11.6 Analyst Pre-Spec-Delivery Source Audit)

UX-002 is the first validation cohort. Audit executed against `master` engine source; each item annotated with finding + `file:line` evidence.

| # | §11.6 Item | Finding |
|---|---|---|
| 1 | Call-order verification | `Daily_ATR` is written at `output.py:2603` (output layer) and read by `transform.py` via `flat_metrics`; transform runs after output. **PASS.** |
| 2 | Sort-order check | No edit operates on a sorted iterable. `DAILY_HARD_STOP` entry is verify-only. **N/A.** |
| 3 | Shared-reference / partition-leak | Change 1 adds a key to the `higher_frame` dict (not a hierarchy entry → no BUGR-002 partition / CNV-001 annotation involvement). Change 2 is verify-only. **PASS — no leak surface.** |
| 4 | Pipeline-order feasibility | `Daily_ATR` populated (`output.py:2603`) before the higher_frame group assembles in `_transform_output`. **PASS.** |
| 5 | Call-order feasibility | Single transform-layer assembly; `daily_atr` read once per Profile-A run. **PASS.** |
| 6 | Cross-spec / existing-layout audit | `higher_frame` current shape (FA-001 / EMA50-001: timeframe, ema, golden_cross, sma50, ema_50, sma200, market_stage at `transform.py:1769-1901`) audited; `daily_atr` inserted as a new sibling, no key collision. Doc 2 §IV row layout audited for the removal. **PASS.** |
| 7 | Storage-mechanism feasibility | `_flatten(grouped)` receives the full output (`:4013`, `fa = grouped.get("floor_analysis")` at `:4274`); `higher_frame` + `trade_setup` both reachable; stop-hierarchy reverse-map infra exists (`~:4817`). Reverse-map re-homing of all three keys is feasible. **PASS — explicitly avoids the ANALYST-RLC-001-SPEC-1 storage-feasibility failure class.** |
| 8 | Downstream-override-path audit | `Daily_Protective_Anchor` consumed at `transform.py:3297` + `output.py:2873`; flat-key writer (`output.py:2590`) + membership set (`transform.py:1127`) retained. Removing the output group does not affect these. **PASS — headline finding; flat key retained per DQ-1.** |

---

## §12 Pre-Delivery Verification Checklist (SIR §9)

- [ ] Content accuracy — edits match audited source (`file:line` anchors verified at Phase 2 entry).
- [ ] Internal consistency — phasing/vocabulary consistent; §4 edits match §5 sites.
- [ ] Format integrity — `.md` SSoT per SIR §1.3.
- [ ] Scope discipline — Profile A only; no flat-key removal; no consumer/writer touched; no gate edit.
- [ ] Gate function verification — `TestUX002NotInGatesFile` passes; EEM §II bitwise-invariant.
- [ ] Module import verification — no new imports; acyclic graph preserved.
- [ ] Bug Register updated — status advanced; discovered findings logged.
- [ ] DIA current — §8 applied at Phase 4.

---

## §13 Change Log

| Version | Date | Change |
|---|---|---|
| v1.0 | (this session) | Initial spec. Phase 0 §11.6 source audit complete; DQ-1/2/3 Operator-confirmed; DQ-4 resolved from source. Change 2 descoped to verify-only; Change 3 scoped to output-group removal + reverse-map re-homing with flat key retained. |

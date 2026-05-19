# RLY-001 Phase 2 Standalone Implementation Prompt v1.0

**Authored by:** TBS Project Analyst (Session 158)
**Date:** 2026-05-18
**Parent spec:** `RLY001_Rally_Age_Streak_Primitive_Spec_v1_0.md` v1.0 (S158 SPECIFIED, Phase 0 DQs all locked, §5.2 convention deviation Operator-confirmed S158)
**Target venue:** Standalone chat (Sonnet 4.6 / Opus 4.7 / Claude Code) — minimal-context, non-project-linked
**Track:** Track 1 per SIR §11 (Bundle 4A — `compute.py` touch forbids Track 2 file-scope eligibility)
**Estimated effort:** 1-2 sessions for implementation + tests; live validation runs in a follow-on Operator-led session

---

## §0 — Conventions and Required Uploads

### 0.1 Line number convention

This prompt does **NOT** include line numbers for edit sites. All edits are anchored to **function names, structural cues, and parallel-pattern references** (e.g., "parallel to `_compute_extension_analysis`"). This is a deliberate choice per the BUGR-006-LABEL-PROMPT-3 lesson: line numbers drift between spec authoring and implementation (5-80 lines is normal), and anchored-by-cue references are unambiguous against the implementer's current source state.

If you (standalone Analyst) need approximate locations to start your search, scan the file for the named adjacent function or constant; the edit site is in its immediate vicinity.

### 0.2 Required uploads (minimal-context discipline)

The Operator should upload exactly these files into the standalone session:

| File | Purpose |
|---|---|
| `RLY001_Rally_Age_Streak_Primitive_Spec_v1_0.md` | **Authoritative spec — the source of truth for this implementation.** Re-read in full before writing any code (per project-level instruction (c) + §1.1 below). |
| `tbs_engine/compute.py` | Edit target — new constants + `_compute_rally_state` helper + two call sites |
| `tbs_engine/output.py` | Edit target — new `_assemble_rally_state` helper + call site + maturity-label classification |
| `tbs_engine/transform.py` | Edit target — `MAPPED_FLAT_KEYS` extension + new `_assemble_rally_state_group` helper + grouping-pass hook |
| `tbs_engine/gates.py` | Edit target — `_RLY_MATURITY_MATRIX` constant + `_gate_volatility_regime` extension |
| `tbs_engine/main.py` | **Read-only reference** — verify call-order of compute / output / gates phases per §2 verification |
| `tbs_engine/types.py` | **Read-only reference** — verify `RunContext` / `ctx` field convention if storing `_rly_primary` / `_rly_context` on ctx requires a types.py declaration |
| `IVR001_Volatility_Regime_Context_Spec_v1_0.md` | Reference for the existing IVR-001 §4.1/§4.2 matrix structure that §4.5 extends; verify your `_RLY_MATURITY_MATRIX` adheres to the same shape |
| `TBS_Engine_Execution_Map_v2_41.md` | Reference for the gate cascade ordering (G.5 → G.5.5 → G.5.6 → G.5.7); verify your call-order audit per §2.1 |
| `TBS_Analyst_Session_Integrity_Rules.md` | SIR §9 Pre-Delivery Verification Checklist (§7 of this prompt) + §11 augmentation discipline |
| Any existing test files referenced for parallel patterns (e.g., `tests/unit/test_cfl001_confluence.py`, `tests/unit/test_wkc001_macro_frame.py`) — optional, helpful for test scaffolding | Reference for negative-assertion test patterns + helper-isolation patterns |

**Do not upload anything else.** Additional context is friction; the spec + 4 engine edit targets + 2 read-only references + IVR-001 spec + EEM + SIR is sufficient.

### 0.3 Engine source baseline

The spec was authored against engine SHAs at the S157 Turn 2 baseline:
- `tbs_engine/transform.py` SHA `e206a968d359b21f2c5d8632975e269ae0ca95e04ebe6834ae6e6be624cc164c`
- `tbs_engine/output.py` SHA `d9bd127ac5eca28fcc44243d9bd67cac5348dacca67809bd9c56d8fe6b7e0cc0`
- `tbs_engine/gates.py` SHA `676fa1485d13828fab9e864c7fbbecb268f17a9a41b9eb64db566e6defdfb4ef`

If the current engine state has drifted from these SHAs (e.g., another bundle landed after S157 Turn 2), verify the call-order audit (§2.1) and shared-reference audit (§2.3) against the **current** state, not the S157 baseline. Drift is acceptable if it doesn't invalidate the spec's architectural assumptions; flag to Operator if it does.

### 0.4 Vocabulary boundaries — what words belong to what phase

Per project-level instruction (b) and SIR §3:

**This Phase 2 standalone session vocabulary:**
- `RALLY_MATURE` / `NORMAL` — the only two values of `Rally_Maturity_Label`. Verdict-invariant (advisory only).
- `DELAYED CLIMAX RISK` / `MATURE TREND` / `CLIMAX RISK` / `EXHAUSTION SIGNAL` — the four new IVR-001 §4.5 interpretation labels.
- `caution_factor` — IVR-001's existing emission surface (not new; reused).
- Existing TBS vocabulary: `PASS`, `REJECT`, `INVALID`, `HALT`, `PRE-APPROVED`, `WAIT`, `ADVISORY`, etc. unchanged by this bundle.

**Words that DO NOT belong to this phase:**
- `INVALID` from RLY-001 — RLY-001 never produces INVALID (advisory only; D7 lock)
- `Reclaim` / `Tennis Ball` — that's RLC-001's territory (Bundle 4B, separate Track 2 spec)
- `STRONG` / `MODERATE` / `WEAK` — those are RLC-001 strength bands; do NOT introduce them in RLY-001 code or tests
- `extension_analysis` modifications — RLY-001 is parallel-to extension_analysis, not modifying it. Read-only reference for structural pattern.

---

## §1 — Mission

### 1.1 What you are being asked to do

Implement RLY-001 Rally Age and Streak Primitive per the parent spec v1.0. The capability adds:

1. A 15-bar window-ratio-based rally-density classifier (`_compute_rally_state`) producing `Rally_Up_Bar_Count_*`, `Rally_Up_Bar_Ratio_*`, `Rally_Magnitude_ATR`, `Rally_Anchor_Price`, and `Rally_Maturity_Label` engine outputs
2. A new top-level `rally_state` grouped sub-object in JSON output (4 nested sub-objects: primary, context, magnitude, maturity)
3. A new §4.5 matrix branch in `_gate_volatility_regime` that produces 4 new interpretation labels and 3 new caution_factor strings when `Rally_Maturity_Label == "RALLY_MATURE"`

Net engine LOC ≈ +200-250 across 4 files. 8 new flat keys. 3 new module-level constants. ~58 new tests across 10 classes. Verdict bitwise-invariant by design.

### 1.2 What you are NOT being asked to do

- **Do NOT** modify the existing IVR-001 §4.1 / §4.2 / §4.3 / §4.4 matrices. The §4.5 branch sits BESIDE them, not modifying them. Per the spec §3.4, when `Rally_Maturity_Label != "RALLY_MATURE"`, existing matrix logic runs unchanged.
- **Do NOT** author the IVR-001 v1.1 spec amendment file. The new §4.5 matrix text lives in your `_RLY_MATURITY_MATRIX` constant in `gates.py`; the Project Analyst applies the IVR-001 v1.1 spec amendment during Phase 4 DIA cascade. You do not create or edit `IVR001_Volatility_Regime_Context_Spec_v1_1.md`.
- **Do NOT** touch RLC-001 / `Reclaim_Bar_Strength_Score` / `action_summary.reclaim_quality` — that's Bundle 4B's territory (separate spec).
- **Do NOT** touch the verdict path. Verify by running `TestRLY001VerdictInvariance` (one of the negative-assertion tests in §6.2 of the spec).
- **Do NOT** add `Rally_*` keys as gate inputs to any gate other than the §4.5 caution_factor emission in `_gate_volatility_regime`. Verified by `TestRLY001NotInGatesFile`.
- **Do NOT** implement weekly-frame Rally_Age_Weekly on Profile A. Deferred to v1.1 Track 2 retro-fit per D4 lock.
- **Do NOT** implement multi-bar tennis ball action pattern. Deferred to RLC-001-TBA-1 CONCEPT per spec §9.

### 1.3 Mandatory first step

**Re-read the spec in full before writing any code.** Specifically:
- §1 (capability summary + evidence base)
- §2 (locked design decisions D1-D8)
- §3 (architecture — helper signature + output shape + flat keys + IVR-001 integration)
- §4 (implementation detail per file)
- §5 (IVR-001 §4.5 amendment text — the source for your `_RLY_MATURITY_MATRIX` constant content)
- §6 (test plan)
- §7 (pre-implementation verification — verify these audits hold against your current source state)

The spec is the authoritative source of truth for this implementation. If you find any divergence between this prompt and the spec, **the spec wins**. Flag the divergence to the Operator in your hand-back.

---

## §2 — Pre-Implementation Verification (Mandatory)

Per SIR §11 augmentation candidacy (the unified pre-spec-delivery / pre-implementation checklist trial), execute these four audits **BEFORE writing any code**. Document findings in your hand-back §3. If any audit surfaces a blocker, **STOP and surface to Operator** per CFL-001 S157 binding precedent.

### 2.1 Call-order audit

**Question:** Does `_compute_rally_state` execute in `main.py` orchestration **before** `_gate_volatility_regime`?

**Why it matters:** The `Rally_Maturity_Label` flat key (written by `output.py:_assemble_rally_state`) is read by `_gate_volatility_regime` for §4.5 matrix lookup. If `_gate_volatility_regime` runs before `_assemble_rally_state` has written the flat key, the gate reads `None` and the §4.5 branch is unreachable — defeating the entire purpose of the bundle.

**How to verify:**
1. Open `tbs_engine/main.py` and locate the Profile-A / Profile-B / Profile-C dispatch branches
2. Trace the call order: `_compute_*` helpers → `_gate_*` functions → `_assemble_*` finalization
3. Confirm `_compute_rally_state` invocations sit alongside `_compute_extension_analysis` in the pre-gate phase
4. Confirm `_assemble_rally_state` (in `output.py`) is invoked **before** `_gate_volatility_regime` reads its result, OR that the result is propagated via `ctx` such that the gate reads from `ctx` rather than `flat_metrics`

**Acceptable resolutions:**
- (a) `_assemble_rally_state` runs in a pre-gate output-assembly pass → standard
- (b) Maturity classification moved into `compute.py` (still pure, just classifies inline) → acceptable alternative if (a) is structurally awkward
- (c) `_gate_volatility_regime` reads from `ctx._rly_context` directly (bypassing `flat_metrics`) → acceptable if `ctx` is populated pre-gate

**Blocker condition:** If none of (a)/(b)/(c) is achievable without significant restructuring of `main.py` orchestration, STOP and surface to Operator.

### 2.2 Sort-order check

**Question:** Are the `close_series` passed to `_compute_rally_state` in ascending timestamp order at the call sites?

**Why it matters:** The helper slices `close_series.iloc[-RLY_WINDOW_BARS:]` to get the last 15 bars. If the series is reverse-sorted or randomly ordered, the slice returns the wrong 15 bars and the rally-state metrics are meaningless. The defensive null path does NOT catch this (the slice will still have 15 numeric values).

**How to verify:**
1. Trace `close_series` provenance back to its origin (`data.py` typically, or via `_*_indicator_stack` helpers)
2. Confirm timestamp-index ascending order is the contract — the existing engine pattern is `pd.DataFrame.sort_index()` upstream or natural-order pandas-read
3. Optional: add an `assert close_series.index.is_monotonic_increasing` assertion at the top of `_compute_rally_state` for runtime guard

**Blocker condition:** If primary or context `close_series` is not ascending-ordered at the call site, surface to Operator.

### 2.3 Shared-reference / partition-leak check

**Question:** Does `rally_state` risk leaking into other output sub-objects via shared dict references or shallow list comprehensions?

**Why it matters:** Per CFL-001 S157 lesson — the BUGR-002 partition uses shallow list comprehensions; entries in `_targets_above` / `_stops_below` share dict references with entries in `cleared_levels` / `overhead_levels`. Annotating a shared dict propagates the annotation to all locations. RLY-001's `rally_state` is a separate top-level grouped sub-object, NOT a per-hierarchy-entry annotation, so the leak risk is structurally lower. But verify nonetheless.

**How to verify:**
1. Confirm `_assemble_rally_state_group` in `transform.py` constructs a fresh dict (not a reference to an existing structure) and assigns it to `output["rally_state"]`
2. Confirm no `rally_state` field references any object that also lives in `floor_analysis.*` or `trade_setup.target.*`
3. Confirm the 8 flat keys are written to `flat_metrics` (a fresh dict scope), not into another existing nested structure

**Blocker condition:** If `rally_state` accidentally shares references with hierarchy entries or other partitioned structures, the implementation must restructure to use fresh dicts.

### 2.4 Prompt-vs-source-truth verification

**Question:** Do all file paths and entities this prompt references exist in your current source snapshot?

**Why it matters:** Per ANALYST-PROMPT-001 S156 precedent (WKC-001 standalone prompt referenced nonexistent `tests/unit/test_flatten_stability.py`), confirm before relying on any path.

**How to verify:**
- `tbs_engine/compute.py` exists ✓ (you'll be editing it)
- `tbs_engine/output.py` exists ✓
- `tbs_engine/transform.py` exists ✓
- `tbs_engine/gates.py` exists ✓
- `tbs_engine/main.py` exists ✓ (read-only reference)
- `tbs_engine/types.py` exists ✓ (read-only reference; check if `RunContext` field declaration is needed for `_rly_primary` / `_rly_context`)
- Existing helper function names referenced (`_compute_extension_analysis`, `_gate_volatility_regime`, `_assemble_output`, `_flatten`, `_unflatten`) — verify all are still present in your current source (if any was renamed/removed in post-S157 work, surface to Operator)
- The IVR-001 §4.1 / §4.2 matrix structure in `gates.py` — verify the existing `_gate_volatility_regime` matrix-lookup pattern is still intact; your `_RLY_MATURITY_MATRIX` constant should follow the same shape

**Blocker condition:** Any referenced entity that doesn't exist → STOP and surface to Operator.

---

## §3 — Implementation Scope (4 files)

### 3.1 `tbs_engine/compute.py`

**Add three module-level constants** (top of file, after existing constants):

```python
RLY_WINDOW_BARS = 15  # Minervini tennis ball pattern window basis
RLY_MATURE_RATIO_THRESHOLD = 10.0 / 15.0  # ~0.667 RALLY_MATURE up-bar ratio gate
RLY_MATURE_MAGNITUDE_ATR_THRESHOLD = 5.0  # IBD climax-top ATR-width floor
```

**Add helper function** `_compute_rally_state` per spec §3.1 contract. Defensive returns per spec's defensive behaviour table (INSUFFICIENT_BARS / ATR_UNAVAILABLE / NAN_IN_WINDOW).

**Add two call sites in compute orchestration** for each profile (Profile A / Profile B / Profile C branches). Frame mapping per spec D5:
- Profile A: primary = hourly, context = daily
- Profile B: primary = daily, context = weekly
- Profile C: primary = weekly, context = monthly

Store results on `ctx` as `ctx._rly_primary` and `ctx._rly_context`. If `types.py` requires field declaration (check existing convention for other `_compute_*` ctx writes like `ctx._extension_analysis`), add declarations.

### 3.2 `tbs_engine/output.py`

**Add helper** `_assemble_rally_state(ctx, p_code) -> Tuple[Optional[Dict], Dict[str, Any]]`:

Returns `(rally_state_block, flat_keys_dict)`. First element is the spec §3.2 JSON shape or `None`. Second is the flat keys dict with all 8 new keys (some may be `None` on defensive paths).

**Maturity classification logic** (in `_assemble_rally_state`) per spec §4.2:

```python
context_ratio = ctx._rly_context.get('ratio')
magnitude_atr = ctx._rly_context.get('magnitude_atr')

if context_ratio is None or magnitude_atr is None:
    maturity_label = None
elif (context_ratio >= RLY_MATURE_RATIO_THRESHOLD
      and magnitude_atr >= RLY_MATURE_MAGNITUDE_ATR_THRESHOLD):
    maturity_label = "RALLY_MATURE"
else:
    maturity_label = "NORMAL"
```

(Import the constants from `compute.py` per the existing engine convention.)

**Hook into `_assemble_output`** after extension_analysis assembly and before action_summary assembly:

```python
rally_state_block, rally_flat_keys = _assemble_rally_state(ctx, p_code)
output['rally_state'] = rally_state_block  # may be None
flat_metrics.update(rally_flat_keys)
```

Verify the hook is placed **before** `_gate_volatility_regime` consumes `flat_metrics["Rally_Maturity_Label"]` per your §2.1 audit finding.

### 3.3 `tbs_engine/transform.py`

**Extend `MAPPED_FLAT_KEYS`** with 8 new entries mapping each new flat key to its grouped-output path:

```python
"Rally_Up_Bar_Count_Primary" -> "rally_state.primary.up_bar_count"
"Rally_Up_Bar_Count_Context" -> "rally_state.context.up_bar_count"
"Rally_Up_Bar_Ratio_Primary" -> "rally_state.primary.ratio"
"Rally_Up_Bar_Ratio_Context" -> "rally_state.context.ratio"
"Rally_Window_Bars"          -> (constant emission; consider how transform.py handles
                                  the parallel `Window_Bars` style — Doc 2 reference)
"Rally_Magnitude_ATR"        -> "rally_state.magnitude.atr_widths"
"Rally_Anchor_Price"         -> "rally_state.magnitude.anchor_price"
"Rally_Maturity_Label"       -> "rally_state.maturity.label"
```

**Add helper** `_assemble_rally_state_group(flat_metrics) -> Optional[Dict]` that reads the 8 flat keys and produces the spec §3.2 JSON shape. Returns `None` if `Rally_Maturity_Label` is `None` (or any required key is `None`).

Helper must populate:
- `primary` sub-object: up_bar_count, window_bars, ratio, frame, desc
- `context` sub-object: up_bar_count, window_bars, ratio, frame, desc
- `magnitude` sub-object: atr_widths, anchor_price, current_price, atr_value, desc
- `maturity` sub-object: label, trigger {context_ratio_threshold, context_ratio_actual, context_ratio_met, magnitude_atr_threshold, magnitude_atr_actual, magnitude_atr_met, both_met}, desc

**Hook into top-level grouping pass** alongside `_assemble_extension_analysis_group`, `_assemble_floor_analysis_group`, etc.

**Vocabulary-collision audit:** Run `grep -i "rally" tbs_engine/transform.py` BEFORE writing. Should return zero matches at S157 baseline. If any pre-existing `rally`-prefixed code surfaces (e.g., from PE-44 rally confluence work), surface to Operator.

### 3.4 `tbs_engine/gates.py`

**Add module-level constant** `_RLY_MATURITY_MATRIX` per spec §5.1 + §5.2 — a dict mapping regime label to `(interp_label, interp_desc, caution_factor_template)` tuples. Template strings include `[X.XX]` / `[Y.YY]` placeholders for runtime substitution with actual ratio + magnitude.

```python
_RLY_MATURITY_MATRIX = {
    "COMPLACENT": (
        "DELAYED CLIMAX RISK",
        "Options market shows no fear at mature-rally levels. ...",  # spec §5.1 full text
        "VOLATILITY REGIME: COMPLACENT -- DELAYED CLIMAX RISK at mature rally. "
        "Context up-bar ratio {ratio}/15 + magnitude {mag} ATR with options market "
        "showing no fear. Sharp mean reversion risk.",
    ),
    "ALIGNED": (
        "MATURE TREND",
        "The rally is mature but the options market is pricing the move proportionally. ...",
        None,  # ALIGNED emits no caution_factor (existing IVR convention preserved)
    ),
    "ELEVATED": (
        "CLIMAX RISK",
        "Options market pricing moderately more risk at late-stage continuation. ...",
        "VOLATILITY REGIME: ELEVATED -- CLIMAX RISK at mature rally. "
        "Context up-bar ratio {ratio}/15 + magnitude {mag} ATR with options market "
        "pricing reversal risk.",
    ),
    "EXTREME": (
        "EXHAUSTION SIGNAL",
        "Highest-risk configuration. Late-stage rally compounded with EXTREME volatility regime ...",
        "VOLATILITY REGIME: EXTREME -- EXHAUSTION SIGNAL: climax-run signature. "
        "Context up-bar ratio {ratio}/15 + magnitude {mag} ATR with options market "
        "pricing significant reversal. Consider profit-taking.",
    ),
}
```

Use spec §5.1 full description text verbatim for the `interp_desc` slot — do not paraphrase. The desc strings are operator-facing and must match the spec character-for-character.

**Extend `_gate_volatility_regime`** to read `flat_metrics.get("Rally_Maturity_Label")` and branch to the §4.5 matrix lookup when value is `"RALLY_MATURE"`. Per spec §3.4:
- When RALLY_MATURE: override `context_interpretation` label + desc per `_RLY_MATURITY_MATRIX[regime]`; emit caution_factor (formatted with actual ratio + magnitude values from flat_metrics) if non-None per §5.2 table
- When NOT RALLY_MATURE: existing §4.1 / §4.2 / §4.3 / §4.4 matrix logic unchanged
- Gate verdict: PASS unconditionally (unchanged from existing IVR-001 advisory contract)

**Convention deviation lock (§5.2):** COMPLACENT × RALLY_MATURE emits caution_factor (Operator-confirmed S158 per spec §5.2). Do NOT set the COMPLACENT caution_factor template to `None`.

---

## §4 — Test Plan

Author new test file `tests/unit/test_rly001_rally_state.py`. Ten test classes per spec §6.1. Approximate test count ~58; exact count emerges from boundary-case coverage.

### 4.1 Test class summary

| Class | Tests | What it verifies |
|---|---|---|
| `TestRLY001HelperCorrectness` | ~12 | `_compute_rally_state` numeric correctness across synthetic close series |
| `TestRLY001DefensiveBehaviour` | ~6 | INSUFFICIENT_BARS / ATR_UNAVAILABLE / NAN_IN_WINDOW returns |
| `TestRLY001MaturityClassification` | ~10 | Output-layer maturity-label thresholding (boundary cases at exactly 10/15, exactly 5.0 ATR) |
| `TestRLY001OutputShape` | ~6 | `_assemble_rally_state` matches spec §3.2 schema |
| `TestRLY001FlatKeyRoundTrip` | ~4 | All 8 new flat keys round-trip cleanly through `_flatten()` and `_unflatten()` |
| `TestRLY001IVRMatrix` | ~8 | 4 regime × 2 maturity (RALLY_MATURE / NORMAL) combinations produce correct labels + caution_factor strings |
| `TestRLY001NotInGatesFile` (negative) | 1 | RLY-001 not a gate input on any gate other than the §4.5 caution_factor write |
| `TestRLY001VocabularyHygiene` (negative) | 1 | New names don't collide with existing engine vocabulary |
| `TestRLY001VerdictInvariance` (negative) | 4 | Verdict (PASS/REJECT/INVALID/HALT) bitwise-unchanged pre/post for all 4 regime cells; only `caution_factors[]` differs (3 of 4 regimes append, ALIGNED unchanged) |
| `TestRLY001ProfileMatrix` | ~6 | Frame mapping per D5 (A/B/C primary/context combinations) + PCM-001 Profile C edge case |

### 4.2 Negative-assertion implementation hints

- **`TestRLY001NotInGatesFile`:** Use `inspect.getsource()` on each `_gate_*` function and grep for `Rally_` or `RLY_`. Expect zero matches except inside `_gate_volatility_regime` (where the §4.5 branch deliberately reads `Rally_Maturity_Label`). Pattern: same as `TestCFL001NotInGatesFile` / `TestWKC001NotInGatesFile` from CFL-001 / WKC-001.

- **`TestRLY001VocabularyHygiene`:** Programmatic check — load `MAPPED_FLAT_KEYS`, verify the 8 new keys are present + non-colliding with pre-existing names. Verify the 4 new §4.5 labels (DELAYED CLIMAX RISK / MATURE TREND / CLIMAX RISK / EXHAUSTION SIGNAL) don't appear elsewhere in `gates.py` or `transform.py` as labels for other matrices.

- **`TestRLY001VerdictInvariance`:** Use fixtures from existing test suite (e.g., a known PASS-verdict fixture + a known REJECT/INVALID/HALT fixture). Run engine pre and post — verify `output["verdict"]` is bitwise-identical. Only `output["action_summary"]["caution_factors"]` may differ (3 of 4 regimes append a new entry when RALLY_MATURE is active; ALIGNED does not append).

### 4.3 Test baseline targets

- **Pre-RLY-001 baseline (S157 Turn 2 closure):** 3010 passed / 5 skipped / 1 failed (pre-existing `BUG-CFL001-PRE-1`)
- **Expected post-RLY-001:** ~3068 passed / 5 skipped / 1 failed
- **Zero regressions** in any pre-RLY-001 test class

### 4.4 Test isolation discipline (TEST-HRN-001 carry)

Per `TEST-HRN-001` IDENTIFIED S137 (still open at S157), avoid the unsafe `sys.modules[name]` overwrite pattern when dynamically loading modules in tests. Use the idempotent guard pattern:

```python
def _load_mod(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
```

Same pattern as `tests/unit/test_bugr006_profile_b_brk_rr.py`. If you can use direct `from tbs_engine.compute import ...` imports instead of dynamic loading, prefer that — it avoids the issue entirely.

---

## §5 — Live Validation Handoff (Phase 3 — Operator-led, NOT in this standalone session)

Phase 3 live validation is an Operator-led step **after** standalone implementation hand-back. Per spec §6.2, the Operator will run ≥5 tickers across 3 profiles to verify:

1. Profile A RALLY_MATURE positive witness
2. Profile A NORMAL regression-invariance witness
3. Profile B RALLY_MATURE positive witness
4. Profile C either positive or null-emit (PCM-001 partial-tier edge)
5. RALLY_MATURE × ELEVATED end-to-end (caution_factor propagation)
6. Defensive null path (insufficient bars / null ATR)

Your hand-back §6 should propose candidate tickers from the existing live-validation roster (NVDA, OXY, EOG, LIN, CRWD, PLTR, ENPH, GEV, RDW, ADBE, MSFT, LLY, GOOGL, CTVA, REL.L per S156 / S157 cohorts), flagged by current rally-density characteristics where known. Final ticker selection is Operator's call.

---

## §6 — Hand-Back Template

Return to the Operator (and to the Project Analyst for Phase 4 DIA cascade) a hand-back document `RLY001_Phase2_Implementation_HandBack_v1_0.md` with these sections:

### §1 — Engine state at start
- Pre-RLY-001 engine SHAs (verify against §0.3 baseline)
- Pre-RLY-001 pytest baseline

### §2 — What was implemented
- 4-file engine touch summary (compute.py + output.py + transform.py + gates.py)
- Net LOC delta per file
- 3 new constants + 8 new flat keys + 1 new matrix + 2 new helpers
- Post-implementation engine SHAs

### §3 — Pre-implementation verification findings
- Call-order audit result (§2.1 of this prompt)
- Sort-order check result (§2.2)
- Shared-reference / partition-leak audit result (§2.3)
- Prompt-vs-source-truth verification result (§2.4)
- Any blockers surfaced + their resolutions

### §4 — Test results
- Pytest run output: pass/fail/skip counts vs §4.3 expected baseline
- New test class breakdown (10 classes, count per class)
- Any failures or regressions (should be zero)

### §5 — Operator decisions surfaced during implementation
- Any in-session DQs that emerged (e.g., if `types.py` field declaration needs Operator approval, log here)
- Any spec divergences flagged (per §1.3 "spec wins" rule)

### §6 — Live validation candidate cohort
- Proposed tickers for Phase 3 validation per §5 above

### §7 — SIR §9 Pre-Delivery Verification Checklist
- All 7 items green or explicit "not applicable" with rationale

### §8 — Open Questions for Operator
- Any questions emergent from implementation

### §9 — Suggested DIA cascade scope (for Project Analyst Phase 4)
- Confirm or amend the spec §8 DIA scope based on what actually shipped

---

## §7 — SIR §9 Pre-Delivery Verification Checklist (run before hand-back delivery)

| Item | Check | Pass criteria |
|---|---|---|
| Content accuracy | Does the implementation match the spec? | All spec §3 architecture details, §4 implementation details, §5 IVR-001 matrix content present in code |
| Internal consistency | Does the implementation contradict itself? | Constants in `compute.py` match thresholds used in `output.py` classification; flat key names in `MAPPED_FLAT_KEYS` match emissions in `output.py`; matrix label strings in `gates.py` match spec §5.1 text |
| Format integrity | Are files in expected formats? | `.py` for engine files; new `.md` test file path conforms; no stray `.docx` or text-as-binary |
| Scope discipline | Did the implementation only touch approved scope? | 4 files only (compute / output / transform / gates) + 1 new test file. No `main.py` / `types.py` modifications unless explicitly approved during §2.1 verification. No spec amendments. No IVR-001 v1.1 spec file. No RLC-001 work. |
| Gate function verification | Did any gate function signature or execution order change? | Zero gate function signature changes; gate cascade ordering G.5 → G.5.5 → G.5.6 → G.5.7 unchanged; only `_gate_volatility_regime` body extended with §4.5 branch (no new gate added) |
| Module import verification | Import graph still acyclic? | `grep -cE "^(import \|from )" tbs_engine/compute.py / output.py / transform.py / gates.py` matches pre-implementation baseline; zero ImportError across all 11 `tbs_engine/` modules |
| Bug Register | Any new bugs found during implementation? | If yes, log each in your hand-back §5 with IDENTIFIED status + reproduction notes for Project Analyst to add to `TBS_Bug_Register.md` at Phase 4 |

---

## §8 — Stop-and-Surface Triggers (Binding)

You **MUST STOP** and surface to Operator (do not silently work around) in any of these conditions:

1. **§2.1 call-order audit fails** — `_compute_rally_state` cannot be inserted before `_gate_volatility_regime` reads `Rally_Maturity_Label` without restructuring `main.py` orchestration
2. **§2.2 sort-order check fails** — primary or context `close_series` is not in ascending timestamp order
3. **§2.3 shared-reference audit fails** — `rally_state` accidentally shares dict references with another sub-object
4. **§2.4 prompt-vs-source-truth fails** — any referenced file or function name does not exist in current source
5. **`_RLY_MATURITY_MATRIX` text divergence** — if the spec §5.1 description text feels operator-confusing or technically incorrect to you on second read, flag rather than paraphrase
6. **Scope creep temptation** — if you find yourself wanting to touch `main.py` orchestration significantly, or modify any existing matrix in `_gate_volatility_regime`, or add a `Rally_*` flag elsewhere, STOP. Per SIR §11.2 / §11.7 risk #3, scope creep on Bundle 4A would re-class it from straightforward Track 1 to "misclassified behavior change" territory.
7. **Test failure not attributable to your change** — if existing pre-RLY-001 tests start failing post-implementation, do NOT modify the failing tests; surface the regression for Operator triage.

The Track 2 Claude Code precedent (CFL-001 S157) established that stop-and-ask discipline is what makes the Track work. Same expectation here for Track 1.

---

## §9 — Reference: Spec §2 Locked Decisions (verbatim)

For your quick reference (do not modify; the spec is the source of truth):

| ID | Decision |
|---|---|
| D1 | Counting semantics: window-ratio over 15-bar lookback (not strict-consecutive) |
| D2a | Up-bar window threshold: ≥10/15 (≈0.667) |
| D2b | Magnitude threshold: ≥5.0 ATR widths |
| D3 | IVR-001 §4.5 matrix content: per spec §5 verbatim |
| D4 | Weekly-frame rally age (Rally_Age_Weekly): deferred to v1.1 Track 2 retro-fit |
| D5 | Frame mapping: A hourly/daily, B daily/weekly, C weekly/monthly |
| D6 | Output location: new `rally_state` top-level grouped sub-object |
| D7 | Verdict impact: zero — advisory only |
| D8 | Naming convention: `Rally_Up_Bar_Count_*`, `Rally_Up_Bar_Ratio_*`, `Rally_Window_Bars`, `Rally_Magnitude_ATR`, `Rally_Anchor_Price`, `Rally_Maturity_Label`; grouped section `rally_state` |

§5.2 convention deviation (Operator-confirmed S158): COMPLACENT × RALLY_MATURE emits caution_factor (3 of 4 regimes emit; ALIGNED stays null). Do not preserve the IVR-001 §4.1/§4.2 "COMPLACENT = no caution" convention here.

---

**End of RLY-001 Phase 2 Standalone Implementation Prompt v1.0**

When ready, the Operator opens a fresh non-project-linked chat, uploads the §0.2 file list, pastes the contents of this prompt as the opening message, and the standalone Analyst executes per the prompt above.

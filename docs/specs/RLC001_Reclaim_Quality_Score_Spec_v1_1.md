# RLC-001: Reclaim Quality Score (Tennis Ball Action) — v1.1

## 1. Identification

| Field | Value |
|---|---|
| **Spec ID** | RLC-001 |
| **Title** | Reclaim Quality Score (Tennis Ball Action) |
| **Version** | 1.1 (canonical; supersedes v1.0) |
| **Status** | IMPLEMENTED (RLC-001 parent capability advanced to 🟡 IMPLEMENTED S160; v1.1 codifies the as-built contract) |
| **Tier** | 1K-B (per PEO v9.22) |
| **Track** | Track 2 inline cadence (per SIR §11.2) |
| **Authoring Session** | v1.0: S160 · v1.1 amendment: S161 |
| **Date** | v1.0: 2026-05-19 · v1.1: 2026-05-20 |
| **Bundle** | Bundle 4B (per PEO Tier 1K-B sub-tier split decision S159) |
| **Sibling-Spec Precedents** | RLY-001 v1.1 (Rally Age & Streak Primitive, S159) · CFL-001 v1.1 (Level Confluence, S157 — v1.0→v1.1 amendment-after-Phase-2 pattern precedent) · WKC-001 v1.1 (Weekly Macro Context, S155) · VTRIG-001 (Session Volume Confirmation Trigger — canonical attachment-site sibling) · SFR-001 (Signal Freshness Recognition) |
| **Source-Verification Snapshot** | v1.0: `roescha/TBS_Master_App@master` post-S159 · v1.1: as-built post-S160 Phase 2 hand-back (SHAs `output.py = 27ddb629911390d8af345d0b0658535edbbf306f` + `transform.py = a72006b06c60c4d32517106635e0209516a7c669` + `test_rlc001_reclaim_quality.py = 7aff147a0102e93e62f387c0b3f196d5dc238d95`) |

### 1.1 Cross-References

- **CONCEPT origin:** `TBS_Bug_Register.md` §RLC-001 (active register, lines 4960–5003) — "Reclaim Quality Score (Tennis Ball Action)"
- **PEO entry:** `TBS_Engine_Domain_Prioritised_Execution_Order_v9_22.md` Tier 1K-B (lines 286–295)
- **Operator-locked sub-items (S159):** RLC-001-CAL-1 (threshold calibration review) · RLC-001-TBA-1 (Option A vs Option B) · RLC-001-REC-1 (computation site)
- **Source files (verified at Phase 0 + confirmed at Phase 2 hand-back):** `layers/tbs_engine/output.py` · `layers/tbs_engine/transform.py`
- **Out-of-scope for engine but tracked:** RLC-REC-EXT-1 (potential REC-001 RECOVERY-path extension — future v1.2)
- **v1.1 amendment driver:** ANALYST-RLC-001-SPEC-1 (attachment-site defect) · ANALYST-RLC-001-SPEC-2 (helper guard insufficiency on action_summary verdict override paths) — both 🔴 IDENTIFIED S160, both resolved canonically in this v1.1

### 1.2 Research Backing (Tennis Ball Action Origin)

The "tennis ball action" name and qualitative criterion originate from:

- **Mark Minervini, *Trade Like a Stock Market Wizard* (McGraw-Hill, 2013)**, chs. 5–7: a strong stock recovering from a pullback "bounces like a tennis ball" — closes near the high of the recovery bar, demonstrating buyer commitment at structural support.
- **Mark Minervini, *Think & Trade Like a Champion* (Access Publishing, 2017)**: positioning of TBA as a quality discriminator for established Stage 2 setups, not as a hard buy/sell gate.
- **William O'Neil, IBD CAN SLIM methodology**: symmetric "accumulation day" criterion — strong institutional accumulation closes in the upper 30% of the bar range (= 0.70 ratio). RLC-001's STRONG cutoff at 0.75 is tighter than this baseline.
- **Richard Wyckoff, "Spring" pattern**: a successful spring (counter-trend recovery) closes in the upper third of the bar range (= 0.67). RLC-001's MODERATE cutoff at 0.60 is slightly looser, opening a "moderate but not Wyckoff-strong" intermediate band.

The RLC-001 banding straddles the IBD and Wyckoff anchors symmetrically; the cutoffs are research-grounded, not arbitrary.

---

## 2. Scope

### 2.1 In Scope

RLC-001 v1.1 computes a single-bar **Reclaim Quality Score** on bars where the engine has emitted a RECLAIM entry (`gate_result.verdict == "VALID" AND gate_result.entry_type == "RECLAIM"`) AND the post-construction `action_summary.verdict` remains `"VALID"`. The score is the bar's close position within its own high–low range, expressed as a ratio in [0, 1]. The score is classified into three bands (`STRONG_RECLAIM` / `MODERATE_RECLAIM` / `WEAK_RECLAIM`) and surfaced as an **informational sub-object** at `action_summary.reclaim_quality`. A single backing flat key (`Reclaim_Quality_Pct`) is registered for audit visibility and `_debug` surfacing.

RLC-001 fires on **all profiles** (A / B / C) where the RECLAIM verdict path is reached AND survives all downstream `action_summary.verdict` mutations. The "tennis ball action" semantic is intuitively strongest on Profile A (intraday/hourly intraday reclaim, per Minervini's framing), but the engine architecture is profile-agnostic at the trigger level (`bar['close'] >= bar['ANCHOR']`), so the computation surfaces wherever the verdict actually fires.

### 2.2 Out of Scope (positive-only design — explicit absence as signal)

The sub-object **MUST NOT** be emitted on:

- Non-RECLAIM entry types: `PULLBACK`, `BREAKOUT`, `SWING_BREAKOUT`
- Non-VALID `gate_result.verdict`: `WAIT`, `INVALID`, `RECOVERY CANDIDATE`
- INVALID variants associated with RECLAIM contexts (e.g., `RECLAIM WITHOUT REGIME`, which carries `verdict == "INVALID"`, not `"VALID"`)
- REC-001 RECOVERY-path bars (logged separately as RLC-REC-EXT-1, deferred CONCEPT for future v1.2 amendment)
- Bars with non-numeric / NaN / null OHLC components
- Bars with degenerate range (`high == low`, e.g., locked-limit doji)
- **Bars where `gate_result.verdict == "VALID"` but `action_summary.verdict` is subsequently overridden to `"INVALID"` by downstream paths in `_assemble_output`** — specifically:
  - **DD-2 EXIT override** (`output.py:1929-1940`) — VALID gate_result + `Exit_Signal == "EXIT"` flips action_summary.verdict to INVALID
  - **BKOUT-001 GAP-5 C2-mandate override** (`output.py:1947-1961`) — VALID gate_result + `Convexity_Class == "C2"` + `Profit_Target is None` flips action_summary.verdict to INVALID
  - (Any future downstream verdict-override path follows the same rule by virtue of the §4.3 attachment-site guard reading `action_summary.get("verdict")`.)

On any of these paths, both `action_summary.reclaim_quality` and `Reclaim_Quality_Pct` are **absent / None**, never zero-valued. Absence is the schema-stable negative signal.

**v1.1 clarification (per ANALYST-RLC-001-SPEC-2 resolution):** The helper (`_assemble_reclaim_quality`) guards on `gate_result.verdict == "VALID"` because the helper executes BEFORE `action_summary` is fully constructed. The attachment-site (§4.3) provides the post-construction `action_summary.get("verdict") == "VALID"` guard. **Both layers are required.** Removing either creates a coverage hole: removing the helper guard would compute on non-VALID gate paths; removing the attachment-site guard would emit on override paths.

### 2.3 Non-Goals

RLC-001 is **not**:

- A gate input. Zero verdict impact, zero gate-cascade impact, zero exit-trigger impact. The verdict that fired the RECLAIM path is preserved bit-for-bit pre/post.
- A position-sizing modifier. Capital-velocity / position-sizing logic does not read `Reclaim_Quality_Pct` at v1.1.
- A persistent state. Computed fresh per evaluation; no cross-bar memory.
- A multi-bar pattern detector. Operates on the single current evaluation bar only.

---

## 3. Computation Specification

### 3.1 Formula

```
Reclaim_Quality_Pct = (close - low) / (high - low)
```

Where `close`, `high`, `low` are the OHLC values of the **current evaluation bar** — i.e., `ctx.last`, which is `df.iloc[cfg.iq]` per the PE-43 engine-wide bar-evaluation index convention.

### 3.2 Edge Cases

The helper MUST return `(None, {"Reclaim_Quality_Pct": None})` on any of:

| Condition | Reason |
|---|---|
| `gate_result is None` | Defensive — caller should never pass None, but guard for robustness |
| `gate_result.verdict != "VALID"` | Out of scope — only fires on VALID verdict |
| `gate_result.entry_type != "RECLAIM"` | Out of scope — only fires on RECLAIM entry_type |
| `close`, `high`, or `low` is `None` or `NaN` | Cannot compute — null-defensive |
| `high - low <= 0` (degenerate range, doji, inverted) | Mathematically undefined — null-defensive |
| `close`, `high`, or `low` cannot be coerced to `float` (KeyError / TypeError / ValueError) | Defensive against schema drift |

Numerical clamping: per the formula, `Reclaim_Quality_Pct` is mathematically bounded to `[0.0, 1.0]` when `low <= close <= high`. The helper does NOT clamp explicitly; if the engine produces a bar where `close > high` or `close < low` (data error), the result will fall outside [0, 1] and surface as-is — visible signal of upstream data corruption per the engine's "fail loud" philosophy.

### 3.3 Banding

| Band Label | Cutoff | Semantic |
|---|---|---|
| `STRONG_RECLAIM` | `value >= 0.75` | Bar closed in top 25% of range; decisive reclaim. Aligns with IBD strong-accumulation threshold (tighter than 0.70 baseline). |
| `MODERATE_RECLAIM` | `0.60 <= value < 0.75` | Bar closed in upper 40% of range but not top 25%; acceptable but not decisive. Straddles Wyckoff spring threshold (0.67) on the loose side. |
| `WEAK_RECLAIM` | `value < 0.60` | Bar closed in lower 60% of range; informational caution. Setup remains VALID (gate already passed) but bar quality is a tier-lower confidence. |

On `value is None`: `label is None`, `desc is None`.

### 3.4 Storage Precision

- Internal computation: full `float64` precision via `(close - low) / (high - low)`.
- Storage in `Reclaim_Quality_Pct` flat key: `round(value, 4)` (4 decimal places, mirroring `Rally_Up_Bar_Ratio_*` 4dp storage convention per RLY-001 `output.py:_assemble_rally_state`).
- Display in `condition.desc` strings: integer percent (no decimals) via `:.0%` percentage formatting in the desc template (e.g., `0.8333` renders as `"83%"`).

### 3.5 Bar Reference (PE-43 Convention)

The bar being evaluated for RLC-001 is the **current evaluation bar** at `cfg.iq`, accessed via `ctx.last`. This is the same bar whose close-vs-ANCHOR comparison triggered the RECLAIM verdict in the gate cascade upstream. **No alternative bar index, lookback, or rolling window is used.**

Verified in `output.py` source via:
- `last = ctx.last` unpacking in `_assemble_output`
- `cfg.iq - 1` usage in `_classify_signal_freshness` (SFR-001) — for *prior* bar lookback, confirming `cfg.iq` is current
- PE-43 closure narrative in Bug Register (engine-wide canonical convention)

---

## 4. Implementation Sites

### 4.1 New Constants (output.py, module level)

```python
# RLC-001: Reclaim Quality Score thresholds
RLC_STRONG_THRESHOLD = 0.75      # IBD-aligned strong-accumulation cutoff (tighter than 0.70 baseline)
RLC_MODERATE_THRESHOLD = 0.60    # Wyckoff-Spring-aligned lower bound

_RLC_THRESHOLDS = {
    "strong_at_or_above": 0.75,
    "moderate_at_or_above": 0.60,
    "weak_below": 0.60,
}

_RLC_NULL_FLAT_KEYS = {
    "Reclaim_Quality_Pct": None,
}
```

Placement: alongside the existing `THS_GATE_THRESHOLD`, `VTRIG_*`, and `RLY_*` constants near the top of `output.py`.

### 4.2 New Helper Function (output.py)

```python
def _assemble_reclaim_quality(ctx, gate_result):
    """RLC-001: Compute single-bar reclaim quality + banding on RECLAIM verdict bars.

    Returns (block, flat_keys_dict).
    - block matches Spec §3 JSON shape, or None on any defensive / out-of-scope path.
    - flat_keys_dict carries Reclaim_Quality_Pct (None on defensive / out-of-scope paths).

    Positive-only design: returns (None, _RLC_NULL_FLAT_KEYS) on every path that
    is not a VALID × RECLAIM × computable bar.

    NOTE (v1.1 §2.2 / §4.3): the helper guard checks gate_result.verdict only.
    Downstream action_summary.verdict overrides (DD-2 EXIT, BKOUT-001 GAP-5
    C2-mandate, future similar) are caught at the attachment site (§4.3),
    not in the helper, because the helper executes before action_summary is
    fully constructed.
    """
    # Out-of-scope guards (Spec §2.2)
    if gate_result is None:
        return None, dict(_RLC_NULL_FLAT_KEYS)
    if gate_result.verdict != "VALID":
        return None, dict(_RLC_NULL_FLAT_KEYS)
    if gate_result.entry_type != "RECLAIM":
        return None, dict(_RLC_NULL_FLAT_KEYS)

    last = ctx.last

    # Null-defensive OHLC extraction (Spec §3.2)
    try:
        close = float(last['close'])
        high = float(last['high'])
        low = float(last['low'])
    except (KeyError, TypeError, ValueError):
        return None, dict(_RLC_NULL_FLAT_KEYS)

    if any(pd.isna(v) for v in (close, high, low)):
        return None, dict(_RLC_NULL_FLAT_KEYS)

    bar_range = high - low
    if bar_range <= 0:  # degenerate (doji / locked-limit / inverted)
        return None, dict(_RLC_NULL_FLAT_KEYS)

    # Formula (Spec §3.1)
    pct = (close - low) / bar_range
    pct_4dp = round(pct, 4)

    # Banding (Spec §3.3)
    if pct >= RLC_STRONG_THRESHOLD:
        label = "STRONG_RECLAIM"
        desc = (f"Bar closed at {pct:.0%} of range (>=75%) -- decisive reclaim "
                f"above floor; tennis-ball action confirms strong demand at "
                f"structural support")
    elif pct >= RLC_MODERATE_THRESHOLD:
        label = "MODERATE_RECLAIM"
        desc = (f"Bar closed at {pct:.0%} of range (60-75%) -- moderate reclaim "
                f"above floor; bar quality acceptable but not decisive")
    else:
        label = "WEAK_RECLAIM"
        desc = (f"Bar closed at {pct:.0%} of range (<60%) -- weak reclaim above "
                f"floor; setup valid but bar quality is informational caution")

    block = {
        "value": pct_4dp,
        "condition": {
            "label": label,
            "desc": desc,
        },
        "thresholds": dict(_RLC_THRESHOLDS),
    }
    flat_keys = {"Reclaim_Quality_Pct": pct_4dp}
    return block, flat_keys
```

### 4.3 Call Site and Attachment (output.py, within `_assemble_output`) — **v1.1 CANONICAL**

> **v1.1 amendment:** This section consolidates v1.0 §4.3 (storage step) + v1.0 §4.5 (transform.py attachment) into a single attachment site inside `_assemble_output`, mirroring the VTRIG-001 idiom. The v1.0 `ctx._rlc_block` storage step is removed. The v1.0 §4.5 transform.py attachment is removed (see §4.5 below for the forwarding note). The post-construction `action_summary.get("verdict") == "VALID"` guard is added per ANALYST-RLC-001-SPEC-2 resolution.

Placement: **after** the existing RLY-001 `_assemble_rally_state` call (RLY-001 is the structural sibling and the canonical placement reference) and **after** `action_summary` has been constructed in `_assemble_output`, but **before** the function returns (so the block flows out with the assembled action_summary).

```python
# RLC-001 (v1.1): Reclaim Quality Score (informational sub-object on RECLAIM verdict only).
# - Helper guards on gate_result.verdict / entry_type (pre-action_summary-construction state).
# - Attachment-site guard on action_summary.get("verdict") catches downstream verdict
#   overrides (DD-2 EXIT at lines 1929-1940; BKOUT-001 GAP-5 C2-mandate at lines 1947-1961;
#   any future override that mutates action_summary.verdict without mutating gate_result).
_rlc_block, _rlc_flat = _assemble_reclaim_quality(ctx, gate_result)
metrics.update(_rlc_flat)
if _rlc_block is not None and action_summary.get("verdict") == "VALID":
    action_summary["reclaim_quality"] = _rlc_block
```

**Two-layer guard contract (binding):**

1. **Helper guard** (`_assemble_reclaim_quality` body): `gate_result.verdict == "VALID" AND gate_result.entry_type == "RECLAIM"` — operates on gate-cascade state, executes before action_summary is constructed. Returns `(None, _RLC_NULL_FLAT_KEYS)` on any out-of-scope or defensive path.

2. **Attachment-site guard** (`if _rlc_block is not None and action_summary.get("verdict") == "VALID":`): catches the case where the helper returned a valid block (gate_result was VALID × RECLAIM) but the action_summary.verdict was subsequently overridden to "INVALID" by a downstream path. The attachment is suppressed; the flat key remains in `metrics` (preserved by `metrics.update(_rlc_flat)`) but the grouped sub-object is not surfaced.

**Why two layers (per ANALYST-RLC-001-SPEC-2 resolution):** the helper executes before `action_summary` is fully assembled. The helper cannot inspect `action_summary.verdict` because it does not exist yet. The attachment-site guard is therefore the canonical location for the post-construction verdict check. Conversely, the helper guard cannot be removed because the helper would otherwise perform OHLC computation on every bar regardless of gate state (wasteful and exposes more null-defensive surface area).

**Architectural precedent:** mirrors VTRIG-001 attachment idiom (`output.py:1937, 1957, 2016, 2030, 2046, 2060`) — `volume_confirmation` is attached directly into action_summary inside `_assemble_output`, not in `_transform_output`. The v1.1 RLC-001 contract aligns with this precedent.

### 4.4 Flat-Key Registration (transform.py)

In `_all_mapped_flat_keys()` (the coverage-audit aggregator):

```python
# RLC-001: register Reclaim_Quality_Pct flat key for MAPPED_FLAT_KEYS membership
keys.add("Reclaim_Quality_Pct")
```

Placement: alongside the existing RLY-001 `Rally_*` flat-key registration block (the closest sibling registration). The v1.1 transform.py footprint is **flat-key registration only** — no `_transform_output` body edit (see §4.5 forwarding note).

### 4.5 action_summary Attachment in transform.py — **REMOVED in v1.1**

> **v1.1 amendment (per ANALYST-RLC-001-SPEC-1 resolution):** v1.0 §4.5 specified attachment inside `_transform_output(action_summary, flat_metrics, debug=False)` via `getattr(ctx, "_rlc_block", None)`. This is non-executable: `_transform_output` does not receive `ctx` as a parameter (verified at `transform.py:1432`); the literal v1.0 code raises `NameError`. The corresponding v1.0 §4.3 storage line `ctx._rlc_block = _rlc_block` would also create an undeclared `RunContext` attribute that is never observable inside `_transform_output`.
>
> **Canonical attachment in v1.1 is in `_assemble_output` (output.py) — see §4.3 above.** This mirrors the VTRIG-001 idiom and avoids the broken transform.py path entirely.
>
> Implementers MUST NOT add any `_transform_output` attachment for `reclaim_quality`. The block is attached upstream in `_assemble_output` and propagates through grouped-output assembly with the rest of `action_summary`.

### 4.6 JSON Shape (canonical output schema)

On a VALID × RECLAIM bar with `pct = 0.83` AND `action_summary.verdict == "VALID"` post-construction:

```json
"action_summary": {
  "verdict": "VALID",
  "reason": "...",
  "entry_type": "RECLAIM",
  "mandate": "...",
  "context": "...",
  "reclaim_quality": {
    "value": 0.8333,
    "condition": {
      "label": "STRONG_RECLAIM",
      "desc": "Bar closed at 83% of range (>=75%) -- decisive reclaim above floor; tennis-ball action confirms strong demand at structural support"
    },
    "thresholds": {
      "strong_at_or_above": 0.75,
      "moderate_at_or_above": 0.60,
      "weak_below": 0.60
    }
  }
}
```

On a non-RECLAIM bar (e.g., PULLBACK / BREAKOUT / SWING_BREAKOUT / WAIT / INVALID), OR on a VALID × RECLAIM bar whose action_summary.verdict is overridden to INVALID (DD-2 EXIT / BKOUT-001 GAP-5 C2-mandate / any future override): **the `reclaim_quality` key is absent.** Not null, not empty — absent. Positive-only design per CFL-001 precedent.

---

## 5. Test Catalog

Test file: `tests/unit/test_rlc001_reclaim_quality.py`. **v1.1 actual count: 65 tests across 10 classes** (above v1.0 target of 35–45, mirroring RLY-001 / CFL-001 v1.1 catalog density).

| # | Test Class | Tests | Coverage |
|---|---|---|---|
| 1 | `TestRLC001Formula` | 7 | Formula correctness across STRONG / MODERATE / WEAK exemplars (Spec §8.1 Examples A/B/C) · arithmetic precision (4dp storage) · boundary inclusivity (`>=` vs `<`) · above-high anomaly (fail-loud behaviour) |
| 2 | `TestRLC001Banding` | 6 | Threshold boundary tests at `0.749` (MODERATE) / `0.750` (STRONG) / `0.599` (WEAK) / `0.600` (MODERATE) — exact-equality semantics, far-band sanity |
| 3 | `TestRLC001VocabularyDiscipline` | 7 | Exact label literals (`STRONG_RECLAIM` / `MODERATE_RECLAIM` / `WEAK_RECLAIM` — no drift, no aliases) · desc string format (`>=75%`, `60-75%`, `<60%` substrings present) · integer-percent formatting |
| 4 | `TestRLC001NullDefensive` | 11 | All 6 paths in §3.2 (None gate_result, NaN OHLC, degenerate range, coercion failure, etc.) · KeyError / TypeError on bar access · inverted range |
| 5 | `TestRLC001VerdictGuard` | 9 | 4 non-VALID gate_result.verdict values (parametrized: WAIT, INVALID, RECOVERY CANDIDATE, custom) · 4 non-RECLAIM entry_types (parametrized: PULLBACK, BREAKOUT, SWING_BREAKOUT, None) · positive case |
| 6 | `TestRLC001VerdictInvariance` | 4 | Helper does not mutate `gate_result` / `ctx.last` / is pure-repeatable · regression cohort byte-identical engine output except for the new keys |
| 7 | `TestRLC001SchemaStability` | 7 | `thresholds` dict always present in non-None block (never None, never empty) · `thresholds` dict keys exactly `{strong_at_or_above, moderate_at_or_above, weak_below}` · `condition` dict always has both `label` and `desc` · null-flat-keys defensive-copy semantics |
| 8 | `TestRLC001FlatKeyRegistration` | 2 | `"Reclaim_Quality_Pct" in _all_mapped_flat_keys()` · uniqueness (one RLC key only) |
| 9 | `TestRLC001PositiveOnly` | 8 | On every non-emitting path, `"reclaim_quality" not in action_summary` (absent, asserted via `KeyError`) — covers 6 non-RECLAIM paths + **v1.1: DD-2 EXIT override path + BKOUT-001 GAP-5 C2-mandate override path** (`test_absent_when_action_summary_overridden_to_invalid`) · `Reclaim_Quality_Pct is None` in flat metrics on null paths, real value preserved on override-suppressed paths |
| 10 | `TestRLC001ActionSummaryAttachment` | 4 | On VALID × RECLAIM × VALID-action_summary bars: `action_summary["reclaim_quality"]` is present · `action_summary["reclaim_quality"]["value"]` equals `metrics["Reclaim_Quality_Pct"]` · `condition.label` matches band · thresholds dict present and well-formed |

### 5.1 Fixture Requirements

- **Synthetic fixtures (Phase 2 — delivered):** Hand-crafted OHLC bars hitting each of the 3 bands, plus null/edge cases. Mirrors RLY-001's synthetic fixture format. Post-TEST-HRN-001 idempotent test-harness pattern (mirrors VTRIG-001 stub-only-if-not-already-present guard; loads `output.py` via `spec_from_file_location` without polluting global `sys.modules`).
- **Live capture (Phase 3 — pending):** ≥1 real-market RECLAIM verdict capture per applicable profile, ≥3 band tiers witnessed across the cohort. Witness target = ≥1 STRONG_RECLAIM + ≥1 MODERATE_RECLAIM + ≥1 WEAK_RECLAIM across cohort. Partial-band closure precedent per RLY-001 admissible if cohort sampling proves narrow (residual logged as `RLC-001-PHASE3-RESIDUAL` non-blocking).

### 5.2 Regression Discipline

- Existing pytest suite must show **zero new failures** post-implementation. Phase 2 hand-back delivered 3133 passed / 5 skipped / 1 pre-existing failure (`test_eng004_measured_move::test_transform_roundtrip` — same defect as `BUG-CFL001-PRE-1` S157, hardcoded relative path predating RLC-001; not a RLC-001 regression).
- New tests integrate cleanly into existing test-harness pollution-resistant patterns (per TEST-HRN-001 open hygiene item — avoid `_load_mod()` cache pollution; v1.1 implementation uses `spec_from_file_location` without `sys.modules` registration).

---

## 6. DIA Scope (Track 2 Tranched Reconciliation)

Per SIR §11.4 Track 2 inline cadence: **no per-bundle DIA cascade**. DIA folds into the next Tranche 2 reconciliation, triggered at the first of: (a) 5 accumulated Track 2 bundles, (b) gap-log closure, (c) Tier completion, (d) Operator-requested reconciliation.

### 6.1 Preliminary DIA Scope (informational, not blocking)

| Document | Section | Change Type | Notes |
|---|---|---|---|
| Doc 2 | §IV `action_summary` sub-contract | Schema additive | New `reclaim_quality` sub-object documented; appears only on VALID × RECLAIM × VALID-action_summary paths; absence-as-signal design note |
| Doc 8 | §II Layer 2 | Substantive mirror | Mirror computation logic + edge case enumeration + two-layer guard contract |
| Doc 7 | Step 6 (Daily Battle Card reading guidance) | Additive bullet | New "Reclaim Quality Awareness" bullet per RLY-001 v8.5.54 "Rally Maturity Awareness" precedent |
| EEM | (entire) | Verify-only | No gate touched; no cascade change. Verify-only annotation only. |
| README | Document Authority + Last Updated narrative | Last Updated entry | RLC-001 closure narrative |
| PEO | Tier 1K-B + ASCII Dependency Map + Document History | Status advance | RLC-001 marked CLOSED; ASCII map annotation updated |

### 6.2 EEM Annotation (no version bump required)

Reason for verify-only: EEM documents the gate cascade. RLC-001 is post-gate, informational, attached at the output assembly layer. No cascade ordering is affected. EEM is reviewed during the Tranche 2 reconciliation to confirm no inadvertent gate-side reference was added.

---

## 7. Closure Criteria

RLC-001 advances to **CLOSED** when **all** of the following are recorded in `TBS_Bug_Register.md`:

1. ✅ Phase 2 standalone implementation hand-back received (S160 Phase 2)
2. ✅ All new tests pass (65 delivered, 35–45 target); zero regressions on existing pytest suite
3. ⏳ Live validation: ≥1 RECLAIM verdict capture across applicable profiles, ≥3 band tiers witnessed (≥1 STRONG_RECLAIM + ≥1 MODERATE_RECLAIM + ≥1 WEAK_RECLAIM) — partial-band-closure with `RLC-001-PHASE3-RESIDUAL` residual admissible per RLY-001 precedent
4. ⏳ Verdict invariance verified live: pre/post action_summary verdict-routed fields bit-identical except for the new keys
5. ✅ Bug Register IMPLEMENTED entry logged with helper signature, call site, file SHAs (output.py + transform.py) — S160 ingestion
6. ✅ Spec verified against final source state — **v1.1 supersedes v1.0; v1.1 reflects as-built**
7. ⏳ Track 2 reconciliation tranche commitment recorded in the closure entry — explicit "DIA cascade pending Tranche N"

Closure mechanism: Operator-confirmed verdict-invariance + Analyst-confirmed spec-vs-source consistency. v1.1 amendment closes criterion #6 by alignment.

---

## 8. Worked Examples

### 8.1 Synthetic (for Phase 2 unit tests — delivered)

**Example A — STRONG_RECLAIM (decisive)**
- Bar: `open=$101.20, high=$104.00, low=$100.00, close=$103.80`
- `pct = (103.80 - 100.00) / (104.00 - 100.00) = 3.80 / 4.00 = 0.9500`
- `Reclaim_Quality_Pct = 0.9500` → `label = "STRONG_RECLAIM"`
- `desc`: `"Bar closed at 95% of range (>=75%) -- decisive reclaim above floor; tennis-ball action confirms strong demand at structural support"`

**Example B — MODERATE_RECLAIM (acceptable)**
- Bar: `open=$100.50, high=$103.00, low=$100.00, close=$102.10`
- `pct = (102.10 - 100.00) / (103.00 - 100.00) = 2.10 / 3.00 = 0.7000`
- `Reclaim_Quality_Pct = 0.7000` → `label = "MODERATE_RECLAIM"`
- `desc`: `"Bar closed at 70% of range (60-75%) -- moderate reclaim above floor; bar quality acceptable but not decisive"`

**Example C — WEAK_RECLAIM (informational caution)**
- Bar: `open=$101.00, high=$103.00, low=$100.00, close=$101.20`
- `pct = (101.20 - 100.00) / (103.00 - 100.00) = 1.20 / 3.00 = 0.4000`
- `Reclaim_Quality_Pct = 0.4000` → `label = "WEAK_RECLAIM"`
- `desc`: `"Bar closed at 40% of range (<60%) -- weak reclaim above floor; setup valid but bar quality is informational caution"`

**Example D — Doji edge (null-defensive)**
- Bar: `open=$100.00, high=$100.00, low=$100.00, close=$100.00`
- `bar_range = 0` → helper returns `(None, {"Reclaim_Quality_Pct": None})`
- `action_summary.reclaim_quality` is **absent** from output

**Example E — Boundary at 0.750 (STRONG, inclusive)**
- Bar: `open=$100.00, high=$104.00, low=$100.00, close=$103.00`
- `pct = 3.00 / 4.00 = 0.7500` exactly
- `Reclaim_Quality_Pct = 0.7500` → `label = "STRONG_RECLAIM"` (inclusive at threshold)

**Example F — Boundary at 0.600 (MODERATE, inclusive)**
- Bar: `open=$100.00, high=$105.00, low=$100.00, close=$103.00`
- `pct = 3.00 / 5.00 = 0.6000` exactly
- `Reclaim_Quality_Pct = 0.6000` → `label = "MODERATE_RECLAIM"` (inclusive at threshold)

**Example G — VALID gate, action_summary overridden to INVALID (v1.1 attachment-site guard suppression)**
- Bar: VALID gate_result + RECLAIM entry_type + computable OHLC (pct = 0.83)
- Helper returns block with `value = 0.8333, label = "STRONG_RECLAIM"`
- Downstream override sets `action_summary["verdict"] = "INVALID"` (e.g., DD-2 EXIT or BKOUT-001 GAP-5 C2-mandate)
- Attachment-site guard `action_summary.get("verdict") == "VALID"` evaluates False
- `action_summary.reclaim_quality` is **absent** from output
- `metrics["Reclaim_Quality_Pct"] == 0.8333` is **preserved** (flat key unaffected by attachment guard)

### 8.2 Live (placeholder — to be captured in Phase 3)

To be populated post-Phase-3 live validation cohort. Format: ticker · profile · timestamp · OHLC · derived pct · derived label · action_summary.verdict (pre/post override) · screenshot reference.

---

## 9. Design Decisions

Each DQ resolution carries (a) the locked decision, (b) the rationale category (research / engineering / architectural-precedent), (c) source-verification anchor where applicable.

### DQ-1: Option A (Informational) vs Option B (Gate)

**Locked: Option A (informational).** RLC-001 is a quality discriminator, not a hard gate.

- **Research:** Minervini scopes TBA as a quality filter for Stage 2 setups (*Trade Like a Stock Market Wizard*, ch. 5–7; *Think & Trade Like a Champion*). Single-bar gating contradicts his framework.
- **Architectural precedent:** RLY-001 v1.1 §3.4 canonical design constraint — "gate returns PASS unconditionally" for the sibling Tier 1K-A capability. Architectural consistency favors the same posture.
- **Engineering:** Single-bar OHLC is the noisiest signal the engine consumes. Adding it as a gate on top of multi-factor structural validation (CRG + THS + CEG + extension gates) would invert the engine's signal-to-noise philosophy.

### DQ-2a: Thresholds 0.75 / 0.60

**Locked: 0.75 (STRONG) / 0.60 (MODERATE) / <0.60 (WEAK).**

- **Research:** IBD accumulation-day symmetric criterion (top 30% = 0.70); Wyckoff Spring upper-third criterion (= 0.67). 0.75/0.60 straddles both anchors symmetrically.
- **Calibration:** RLC-001-CAL-1 logged for 3–6 month live review per RLY-001-CAL-1 / CFL-001-CAL-1 / IVR-001-CAL-1 precedent. Resolution mechanism = 2-line constant update if firing rates warrant.

### DQ-2b: Vocabulary `STRONG_RECLAIM` / `MODERATE_RECLAIM` / `WEAK_RECLAIM`

**Locked: domain-prefixed three-band vocabulary.**

- **Engineering:** Phase 0 literal scan of `transform.py` + `output.py` confirmed `_ths_band` uses `STRONG` and `WEAK` (CRITICAL / WEAK / CAUTION / ACCEPTABLE / HEALTHY / STRONG). Bare `STRONG` / `WEAK` would carry collision risk at the flat-key level.
- **Architectural precedent:** PCT-001 OD-3 `BELOW_SMA_50` / `STRETCHED` / `OVEREXTENDED` / `BLOW_OFF_ZONE`; HFI-001-B `BELOW_CYCLICAL_MEAN` / `EARLY_CYCLICAL_ELEVATION`; WKC `STAGE_1_BASING`. Domain-prefixed two-word vocabulary is the established post-S156 pattern for new banding domains.
- **Self-documenting:** label-as-flat-value reads cleanly: `Reclaim_Quality_Label = "STRONG_RECLAIM"` is unambiguous in isolation.

### DQ-3: Computation Site `output.py::_assemble_reclaim_quality`

**Locked: `output.py`. No `compute.py` touch.**

- **Source-verified:** Bar OHLC universally available in `_assemble_output` via `ctx.last`. `gate_result` is available at the same call site (passed in as `_assemble_output(ctx, gate_result, _prx_ctx, debug=False)`).
- **Architectural precedent:** RLY-001 `_assemble_rally_state(ctx, p_code)` — identical structural pattern; helper at module level, called from `_assemble_output`, returns `(block, flat_keys_dict)`.
- **Track 2 admissibility:** confining the implementation to `output.py` + `transform.py` (no `compute.py`) satisfies SIR §11.2 file-scope criterion.

### DQ-4: Profile Scope — All Profiles Where RECLAIM Fires

**Locked: no profile filter in the helper. Sub-object emits wherever RECLAIM verdict actually fires and survives downstream action_summary.verdict mutations.**

- **Source-verified:** RECLAIM trigger condition `bar['close'] >= bar['ANCHOR']` (per SFR-001 `_classify_signal_freshness`) is profile-agnostic. Profile-specific ANCHOR (hourly EMA 21 for Profile A, daily SMA 50 for Profile B, monthly SMA 200 for Profile C) is the convexity-routed input; the trigger itself doesn't filter.
- **Architectural precedent:** EMA50-001 multi-profile informational surfacing pattern (Bundle 1, S153/S154 closure). Informational context surfaces wherever applicable, not artificially restricted.
- **Narrative framing:** "Tennis ball action" semantic is most resonant on Profile A (intraday/hourly intraday reclaim, per Minervini). This is a documentation-level framing, not a runtime restriction.

### DQ-5: REC-001 RECOVERY Extension Deferred

**Locked: RECLAIM only at v1.1. RLC-REC-EXT-1 logged as 🟤 CONCEPT for future v1.2.**

- **Research:** Minervini scopes TBA explicitly to pullbacks-in-uptrends (Stage 2), not counter-trend reversals. Wyckoff Spring uses the same close-vs-range criterion for reversal contexts but operates in a fundamentally different state machine (REC-001 has C-1/C-2/C-3 tiers with distinct bar-evaluation semantics).
- **Engineering:** Scope discipline. Single-concern delivery is the SIR §5 canonical anti-drift posture. Extension can be evidenced and decided post-live-validation.

### DQ-6: Output Schema `action_summary.reclaim_quality` + 1 Backing Flat Key

**Locked: nested sub-object at `action_summary.reclaim_quality` + flat key `Reclaim_Quality_Pct`.**

- **Source-verified:** `action_summary` is constructed in `_assemble_output` and post-construction may be mutated by downstream verdict-override paths. Direct precedents for attaching new sub-objects to action_summary in `_assemble_output`: VTRIG-001 `volume_confirmation`, SFR-001 `signal_freshness` (writes flat key; rebuilds in transform.py).
- **No new top-level group:** the 11 OTL-001 top-level groups already enumerate the engine's semantic taxonomy. Adding a `reclaim` top-level for one ratio would be heavyweight; `action_summary` is the verdict-context group and the natural home.
- **One backing flat key:** mirrors `Rally_Magnitude_ATR` precedent (RLY-001 surfaces the headline scalar as a flat key for `_debug` audit, derives labels/descs without flat-key backing).
- **Positive-only design:** key is **absent** (not null) on non-emitting paths. CFL-001 confluence-annotation precedent.

### DQ-7: Bar Reference `ctx.last` (= `df.iloc[cfg.iq]`)

**Locked: current evaluation bar via `ctx.last`. PE-43 engine-wide convention.**

- **Source-verified:** `_classify_signal_freshness` uses `cfg.iq - 1` for *prior* bar lookback — confirms `cfg.iq` indexes the current bar. `ctx.last` is established `_assemble_output` idiom for accessing the current bar.

### v1.1 Amendments (S160 Phase 2 Resolutions)

Two amendments folded into v1.1 in response to Phase 2 hand-back discoveries (RLC001_Implementation_HandBack_v1_0.md §6). Both correspond to logged ANALYST-class incidents pending closure at spec-record level by this v1.1.

#### Amendment 1: Attachment-Site Relocation (per ANALYST-RLC-001-SPEC-1)

**v1.0 specified:** Attachment inside `_transform_output` (transform.py §4.5) via `getattr(ctx, "_rlc_block", None)`, with the block stored on ctx in output.py §4.3.

**v1.0 defect:** `_transform_output(action_summary, flat_metrics, debug=False)` does not receive `ctx` (verified at `transform.py:1432` by Claude Code Phase 2 pre-implementation check). Literal v1.0 §4.5 code raises `NameError`. The corresponding `ctx._rlc_block = ...` storage line would create an undeclared `RunContext` attribute. Three sibling-spec precedents cited in v1.0 (RLY-001 storage idiom, VTRIG-001 / SFR-001 attachment idioms) are mutually inconsistent — RLY-001 doesn't store on ctx (discards block, rebuilds from flat keys in transform.py); VTRIG-001 attaches in output.py directly; SFR-001 writes a flat key + rebuilds in transform.py.

**v1.1 resolution (Operator-approved Option 1 at S160 mid-Phase-2):** Attach in `output.py` at the post-`action_summary`-construction site in `_assemble_output`, mirroring VTRIG-001. The `ctx._rlc_block` storage step is eliminated. The transform.py footprint reduces to flat-key registration only (§4.4). v1.0 §4.5 is REMOVED in v1.1.

**Rationale:** VTRIG-001 is the closest structural sibling — both are informational sub-objects on `action_summary` requiring no transform-layer reassembly. The two-step "store on ctx → read in transform.py" pattern from v1.0 was a misapplication of the SFR-001 flat-key-rebuild pattern; SFR-001 reconstructs in transform.py from a flat key (which IS in `_transform_output` scope), not from a ctx attribute. v1.1 chooses the simpler precedent.

**Spec discipline gap surfaced:** v1.0 Phase 0 source verification covered helper return shape, bar OHLC availability, and sub-object precedents — but did NOT trace the specific storage mechanism for transferring data from `output.py` to `_transform_output`. The author assumed `_transform_output` receives `ctx` without verifying the function signature. SIR §11 pre-spec-delivery checklist augmentation candidate: storage-mechanism-feasibility verification (verify the proposed storage location is reachable by both producer and consumer scopes; verify sibling-spec idioms cited in the spec actually use the proposed mechanism).

#### Amendment 2: Attachment-Site Verdict-Override Guard (per ANALYST-RLC-001-SPEC-2)

**v1.0 specified:** Helper guards on `gate_result.verdict == "VALID"`. The spec §2.2 stated non-VALID verdicts are out-of-scope. No attachment-site verdict guard was specified.

**v1.0 defect:** Two paths in `_assemble_output` override `action_summary.verdict` to `"INVALID"` while leaving `gate_result.verdict` as `"VALID"`:
- **DD-2 EXIT override** at `output.py:1929-1940` — VALID gate_result + `Exit_Signal == "EXIT"`
- **BKOUT-001 GAP-5 C2-mandate override** at `output.py:1947-1961` — VALID gate_result + `Convexity_Class == "C2"` + `Profit_Target is None`

The helper guard fires before these overrides execute. Per spec §2.2, `reclaim_quality` MUST NOT emit on non-VALID action_summary verdicts — but the v1.0 helper guard alone is insufficient.

**v1.1 resolution (Claude Code defensive guard, Operator-blessed at S160 hand-back ingestion):** Add the attachment-site guard `action_summary.get("verdict") == "VALID"` at the §4.3 attachment site. The two-layer guard contract is codified in §4.3 (helper guard catches non-VALID gate_result paths; attachment-site guard catches downstream action_summary.verdict overrides). Test 9 sub-test `test_absent_when_action_summary_overridden_to_invalid` verifies absence on both override paths.

**Rationale:** Two-layer design is necessary because the helper executes before `action_summary` is fully assembled (the helper cannot inspect a field that doesn't yet exist). The attachment-site guard is the canonical location for post-construction verdict checks. The helper guard cannot be removed because it prevents wasteful OHLC computation on every bar regardless of gate state.

**Spec discipline gap surfaced:** v1.0 Phase 0 source verification covered the verdict-routing model at the gate-cascade level but did NOT enumerate downstream output-layer overrides that mutate `action_summary.verdict` independently of `gate_result.verdict`. SIR §11 pre-spec-delivery checklist augmentation candidate: downstream-override-path audit at spec authoring time (when scoping helper guards or output-attachment guards, enumerate all sites in the consuming layer that can mutate the relevant verdict/state attribute independently of the helper's input).

---

## 10. Open Decisions

| Item | Status | Note |
|---|---|---|
| **RLC-001-CAL-1** | 🟤 CONCEPT (deferred) | 3–6 month live calibration review. Adjust 0.75 / 0.60 thresholds if firing-rate distribution shows STRONG_RECLAIM saturation or WEAK_RECLAIM starvation. |
| **RLC-REC-EXT-1** | 🟤 CONCEPT (deferred) | Potential extension to REC-001 RECOVERY-path bars. Future v1.2 amendment if Operator pursues post-live-validation. |
| **RLC-001-TBA-1** | ✅ CLOSED at Phase 0 (S160) | Resolved by DQ-1 lock (Option A). |
| **RLC-001-REC-1** | ✅ CLOSED at Phase 0 (S160) | Resolved by DQ-3 lock (output.py computation site). |
| **RLC-001-PHASE3-RESIDUAL** | (pending) | Logged if Phase 3 cohort sampling yields partial band coverage. RLY-001 precedent admits partial-band closure with the residual as non-blocking. |
| **Position-sizing integration** | 🟤 CONCEPT (deferred, no item logged) | If a future capability wants to read `Reclaim_Quality_Pct` for sizing modulation, that's a separate spec (RLC-001 v1.1 is read-only by downstream consumers — no contract to size on it). |

---

## 11. Pre-Implementation Verification Checklist

**MANDATORY** per SIR §11 augmentation candidate (post-7-instance pattern as of S160: ANALYST-002, ANALYST-003, ANALYST-CFL-001-SPEC-1, ANALYST-RLY-001-SPEC-1/-2/-3, ANALYST-RLC-001-SPEC-1/-2). The implementer **MUST** complete each check **before writing code** and confirm in the hand-back narrative.

> **v1.1 note:** §11 retained for historical/methodological completeness even though the RLC-001 implementation is complete. Any implementer producing an analogous capability in future should run this checklist. v1.1 amendments to §11.5 reflect the corrected sibling-spec idiom anchors discovered in S160.

### 11.1 Call-Order Verification

- [ ] Confirm `gate_result` is in scope at the chosen call site in `_assemble_output` (it is the second positional argument to `_assemble_output(ctx, gate_result, _prx_ctx, debug=False)` per source).
- [ ] Confirm the RLY-001 `_assemble_rally_state` call has already completed before the RLC-001 call site (RLY-001 is the structural sibling and ordering anchor).
- [ ] Confirm the RLC-001 call site is **after** action_summary construction in `_assemble_output` AND **before** the function returns (per §4.3 v1.1 placement).

### 11.2 Pipeline-Order Verification

- [ ] Confirm `ctx.last`, `ctx.metrics`, `gate_result`, AND `action_summary` are all populated by the time the call site executes.
- [ ] Confirm `metrics["Reclaim_Quality_Pct"]` mutation via `metrics.update(_rlc_flat)` is visible to `_transform_output` downstream (mirror RLY-001 flat-key mutation idiom).

### 11.3 Sort-Order Verification

- [ ] **N/A** — RLC-001 is single-bar scalar computation. No list iteration, no sort dependency, no partition logic.

### 11.4 Shared-Reference Verification

- [ ] **N/A** — RLC-001 emits a single self-contained dict block and one scalar flat key. No hierarchy entries, no partition-leaking shared references. `_RLC_THRESHOLDS` is defensively copied via `dict(_RLC_THRESHOLDS)` per call.

### 11.5 Cross-Spec Audit

- [ ] **Flat-key collision audit:** grep `tbs_engine/` for `"Reclaim_Quality"` — must return zero pre-existing matches. (Verified at Phase 0; re-verify at implementation time in case of intervening commits.)
- [ ] **Label vocabulary collision audit:** grep `tbs_engine/` for `"STRONG_RECLAIM"`, `"MODERATE_RECLAIM"`, `"WEAK_RECLAIM"` — must return zero pre-existing matches. (Verified at Phase 0.)
- [ ] **`action_summary` key collision:** confirm `"reclaim_quality"` is not an existing key in `action_summary` (constructed in `_assemble_output`; verify by reading the current assembly block).
- [ ] **Pattern match — VTRIG-001 (canonical attachment idiom for v1.1):** read `volume_confirmation` attachment sites in current `_assemble_output` source (`output.py:1937, 1957, 2016, 2030, 2046, 2060`). Mirror exact attachment idiom (conditional attachment with guards directly in `_assemble_output`, no ctx-attribute round-trip, no transform-layer attachment).
- [ ] **Pattern match — RLY-001 (flat-key idiom only):** read `_assemble_rally_state` call site in current `_assemble_output` source. Mirror the flat-key merge idiom (`metrics.update(_rly_flat)`). **Note (v1.1):** RLY-001 does NOT store its block on ctx — the v1.0 spec instruction to "mirror RLY-001 storage idiom" was a misreading; the canonical attachment idiom is VTRIG-001's direct in-`_assemble_output` attachment.
- [ ] **Downstream-override-path audit (v1.1 augmentation per ANALYST-RLC-001-SPEC-2):** enumerate all sites in `_assemble_output` (and any downstream function that runs before `action_summary` is returned) that can mutate `action_summary.verdict` independently of `gate_result.verdict`. As of S160 these are: DD-2 EXIT (`output.py:1929-1940`) + BKOUT-001 GAP-5 C2-mandate (`output.py:1947-1961`). The attachment site MUST guard via `action_summary.get("verdict") == "VALID"` to cover these and any future similar override.

### 11.6 PE-43 Bar-Evaluation Index Compliance

- [ ] Confirm `ctx.last` is used (not `ctx.df.iloc[cfg.iq - 1]` or any other index). The current evaluation bar IS `ctx.last`.
- [ ] If `cfg` is referenced for any reason, confirm the index convention matches PE-43 (i.e., `cfg.iq` is the current bar; `cfg.iq - 1` is the prior bar).

### 11.7 Positive-Only Design Audit

- [ ] Confirm `"reclaim_quality"` is **absent** (not present with None value) from `action_summary` on every non-emitting path. Test 9 in §5 catalog verifies this (including override-path coverage per v1.1).
- [ ] Confirm `Reclaim_Quality_Pct` is **None** (not absent, not zero, not empty string) on every helper-returns-None path. Schema stability — flat key always registered, value None when not applicable. **Note:** on override-suppressed paths (helper returns valid block but attachment guard blocks emission), the flat key retains the COMPUTED value (`metrics.update(_rlc_flat)` runs unconditionally) — only the grouped sub-object is suppressed. This is intentional: the flat key surface preserves audit visibility into "what the helper computed" even when the verdict path doesn't surface it.

---

## 12. Pre-Delivery Verification Checklist (SIR §9)

To be completed by the Analyst at end of implementation, **before** the hand-back is finalized for Operator review.

- [x] **Content accuracy** — every cited line number, file path, and SHA in this spec corresponds to actual source state at implementation time (v1.1: SHAs in §1 Identification correspond to S160 hand-back state)
- [x] **Internal consistency** — §3 formula matches §4.2 helper code; §3.3 banding cutoffs match §4.1 constants; §5 tests reference §4 implementation sites accurately; §4.3 + §4.5 + §9.8 cross-reference cleanly
- [x] **Format integrity** — markdown SSoT, valid syntax, no unclosed code blocks, no broken tables, no orphan section references
- [x] **Scope discipline** — v1.1 implementation does not exceed §2.1 + §4 footprint; no scope-creep into RLC-REC-EXT, no anticipatory hooks for v1.2
- [ ] **Bug Register update** — RLC-001 status was advanced 🟠 SPECIFIED → 🟡 IMPLEMENTED S160; ANALYST-RLC-001-SPEC-1 + -2 logged 🔴 IDENTIFIED S160; v1.1 amendment annotation pending Bug Register touch at next session turn
- [x] **DIA current** — Track 2 inline cadence per SIR §11.4; preliminary DIA scope §6.1 deferred-but-logged; v1.1 amendment is a spec-record change within the same Track 2 cadence (does not trigger separate DIA)
- [x] **Zero regressions** — pytest suite passes (3133 / 5 / 1 pre-existing); 7-ticker live smoke cohort byte-identical except for new keys (zero VALID × RECLAIM landings observed; positive-only absence-as-signal verified); verdict-routed fields bit-identical pre/post

---

## 13. Document History

| Version | Session | Date | Author | Changes |
|---|---|---|---|---|
| v1.0 | S160 | 2026-05-19 | Analyst (Project chat) | Initial authoring. DQ-1 through DQ-7 locked per Phase 0 source verification (post-S159 master snapshot). Track 2 inline cadence confirmed admissible. |
| v1.1 | S161 | 2026-05-20 | Analyst (Project chat) | **Canonical amendment superseding v1.0 post-Phase-2** (mirrors CFL-001 S157 v1.0→v1.1 amendment-after-Phase-2 pattern). **Amendment 1** (§4.3 / §4.5, per ANALYST-RLC-001-SPEC-1): attachment-site relocated from `_transform_output` (transform.py, non-executable in v1.0 because ctx not in scope) to `_assemble_output` (output.py) mirroring VTRIG-001 idiom; `ctx._rlc_block` storage step eliminated; v1.0 §4.5 REMOVED (replaced with forwarding-note to §4.3); transform.py footprint reduced to flat-key registration only. **Amendment 2** (§2.2 / §4.3, per ANALYST-RLC-001-SPEC-2): attachment-site guard `action_summary.get("verdict") == "VALID"` added to cover DD-2 EXIT (`output.py:1929-1940`) + BKOUT-001 GAP-5 C2-mandate (`output.py:1947-1961`) override paths that flip action_summary.verdict to INVALID while gate_result.verdict stays VALID; two-layer guard contract codified in §4.3. **§5 Test Catalog** updated: actual count 65 (above v1.0 target 35–45); Test 9 expanded coverage description includes override-path absence verification. **§8 Worked Examples** added Example G (override-suppression path). **§9 v1.1 Amendments subsection** new (sibling to DQ-1..DQ-7) codifying both amendment decisions with discipline-gap commentary (storage-mechanism-feasibility + downstream-override-path-audit as SIR §11 pre-spec-delivery checklist augmentation candidates). **§11.5** cross-spec-audit anchors corrected: VTRIG-001 is the canonical attachment idiom; RLY-001 contributes only the flat-key merge idiom; new §11.5 downstream-override-path-audit step. **§1 Identification** updated with v1.1 metadata + as-built source SHAs. **§7 Closure Criteria** criterion #6 (spec-vs-source consistency) closed by v1.1 alignment. |

---

**SSoT marker:** This markdown file is the authoritative source-of-truth for RLC-001 v1.1. v1.0 is retained as historical pre-implementation contract; v1.1 supersedes v1.0 canonically for all forward references. Any future derivations (.docx, presentation slides, summary cards) MUST be regenerated from this file, not edited in place.

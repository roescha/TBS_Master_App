# RLY-001 Rally Age and Streak Primitive — Specification v1.1

**Author:** TBS Analyst (Project chat)
**Date:** 2026-05-18 (Session 158 — v1.0); 2026-05-19 (Session 159 — v1.1 amendment at Phase 4 closure)
**Status:** 🟢 SYNCED S159 (Phase 4 in-flight; advances to ✅ CLOSED at Phase 4 final batch — Tier 1K Bundle 4A parent close)
**Spec ID:** RLY-001
**Bundle:** Tier 1K Bundle 4A (Track 1 per SIR §11.2 file-scope criterion: `compute.py` touch is forbidden under Track 2)
**Sister item:** RLC-001 (Tier 1K Bundle 4B — Track 2, separate spec, locked DQs in Bug Register S158 Phase 0 close-out)
**Format SSoT:** Markdown per SIR §1.3
**Engine baseline:** SHAs at S157 Turn 2 baseline — `transform.py` `e206a968...`, `output.py` `d9bd127a...`, `gates.py` `676fa148...`, `compute.py` at parallel S157 baseline (standalone implementer verified SHAs at S158 Phase 2 session start)
**Working session assumption:** S159 for this v1.1 amendment (natural progression S157 Turn 3 → S158 [prior chat Phase 0/1/2/3] → S159 [this Phase 4 cascade]) — globally find-replaceable if Operator's numbering differs

**v1.1 amendment scope (S159 Phase 4):** Three surgical changes to v1.0 spec body — (a) §3.2 maturity.desc format formalization (only failing condition(s) emitted in NORMAL case per Phase 2 implementation reality); (b) §5.3 IVR-001 §4.x enumeration corrected to reflect existing IVR-001 §4.5 Default which renumbers to §4.6 under v1.1, with new §4.5 At Rally Maturity inserted between §4.4 At Recovery and §4.6 Default; (c) §11 Document History row appended. No engine-behaviour changes; spec body §1 / §2 / §3.1 / §3.3 / §3.4 / §4 / §5.1 / §5.2 / §5.4 / §6 / §7 / §8 / §9 / §10 unchanged at v1.1 (verified against Phase 2 Implementation Hand-Back).

---

## 0. Phase 0 Decision Lock Reference

The nine Phase 0 Design Questions for Bundle 4 (covering both RLY-001 and RLC-001) were resolved in this session preceding spec authoring. The Bug Register S158 closure changelog entry will memorialize the decisions verbatim. This spec embodies the RLY-001-relevant decisions as binding §2 Locked Design Decisions D1–D8.

Per SIR §11 augmentation candidacy strengthened by the ANALYST-002 / ANALYST-003 / ANALYST-CFL-001-SPEC-1 incident class (now 3 confirmed instances of the pre-implementation verification list executed only at standalone implementer time and not at spec-authoring time), this spec was authored after exercising the unified pre-implementation verification list at spec-authoring time. Findings documented in §7.

---

## 1. Capability Summary

### 1.1 Motivation

The TBS engine measures various aspects of trade conditions — extension distance, volatility regime, structural floor proximity, conviction tier — but has no measure of **rally maturity or climax-run risk**. An operator considering entry on a stock that has rallied for 12 of the last 15 bars at ≈6.5 ATR cumulative magnitude cannot see that signal in the engine output today; they must count manually.

RLY-001 addresses this gap by introducing a `rally_state` sub-object in the engine output that surfaces:

- Up-bar density over a 15-bar window (primary and context frames)
- Cumulative rally magnitude expressed in ATR widths
- A binary `RALLY_MATURE` classification triggered when both density and magnitude thresholds clear

The motivating canonical case is **MSTR January–February 2021** — 10 up-days out of 13 trading days, ≈+100% (≈6.5 ATR widths) — a classical Minervini climax-run signature that the current engine cannot flag.

### 1.2 Evidence base

All thresholds in this spec trace to published source authorities (per SIR §10 hallucination-prevention discipline):

| Source | Datum from source | Application in this spec |
|---|---|---|
| Minervini *Think and Trade Like a Champion* tennis ball action pattern | 12/15 up-closes + 9/15 upper-half closes as a multi-bar healthy-continuation criterion | 15-bar window basis adopted directly; up-bar threshold relaxed to 10/15 (≈ 0.667) for rally-maturity classifier to admit lumpy climax-runs that fall short of the strict 12/15 tennis-ball threshold while still excluding normal advancing trends |
| William O'Neil / Mike Webster IBD weekly precedent | "5 or more consecutive up weeks" as a climax-candidate trigger on weekly charts | Daily-frame analog: 15-bar daily window with high up-bar density catches the daily equivalent of the weekly precedent |
| Investor's Business Daily climax-top sell rule | 25%-50%+ gain in three weeks or less | ATR-width conversion: for momentum names with ATR ~2-3% of price, a 25% gain over 15 trading days ≈ 8-12 ATR widths; the 5.0-ATR lower bound aligns with the floor of this range to admit the first wave of climax-run candidates while remaining above existing EXTENSION-gate territory (~3-4 ATR) |
| MSTR Jan-Feb 2021 canonical climax (Minervini) | 10 of 13 up-days (77% ratio), ≈+100% (≈6.5 ATR widths) | Reference case both density (10/15 ≥ 0.667 at the relevant subwindow) and magnitude (6.5 ≥ 5.0) thresholds catch — operates as the regression-witness target for live validation |

### 1.3 In-scope

- New helper `_compute_rally_state(close_series, current_atr, frame_label) -> Dict[str, Any]` in `tbs_engine/compute.py`
- Two helper invocations per profile (one for primary frame, one for context frame) called from compute orchestration
- New `rally_state` top-level grouped sub-object in engine JSON output, parallel to `floor_analysis`, `extension_analysis`, `volume_at_price`
- Eight new flat keys per `MAPPED_FLAT_KEYS` registration
- IVR-001 spec v1.0 → v1.1 substantive amendment: new §4.5 "At Rally Maturity" context matrix with 4 regime cells
- IVR-001 `_gate_volatility_regime` (in `gates.py`) extended to recognize `RALLY_MATURE` trigger and emit `caution_factor` strings per §4.5 matrix (3 of 4 regimes emit caution; ALIGNED does not — convention deviation justified in §5.2)

### 1.4 Out-of-scope (v1.0)

- `Rally_Age_Weekly` on Profile A via WKC-001 weekly stack — deferred to v1.1 Track 2 retro-fit per DQ-RLY-4 Phase 0 lock
- Multi-bar tennis ball action pattern (Minervini's literal 12/15 + 9/15 multi-bar matrix) — separate CONCEPT `RLC-001-TBA-1` logged at spec landing
- Verdict impact — RLY-001 is advisory-only by design; never a REJECT, never gates VALID → INVALID
- Position sizing impact — RLY-001 does not modify any sizing logic
- Profile B `medium_term` derivation gap (PCT-001-OBS-1 logged S154) — independent investigation; no coupling to RLY-001

### 1.5 Vocabulary

| Term | Definition |
|---|---|
| Rally window | Trailing 15 bars on the relevant frame (constant `RLY_WINDOW_BARS = 15`) |
| Up-bar | A bar where `close > prior_close` (strict inequality; no inside-bar grace per DQ-RLY-1 subsumption into DQ-RLY-2) |
| Up-bar count | Integer count of up-bars in the 15-bar window |
| Up-bar ratio | Up-bar count / window size; threshold for RALLY_MATURE trigger is ≥ 10/15 ≈ 0.667 |
| Rally magnitude | `(close[-1] - close[-15]) / current_atr`; threshold for RALLY_MATURE trigger is ≥ 5.0 |
| Rally anchor | `close[-15]` — the price 15 bars prior to the iq bar; defines the rally start for magnitude calculation |
| RALLY_MATURE | Classification label triggered when context up-bar ratio ≥ threshold AND magnitude ATR ≥ threshold; **never a REJECT gate** |
| NORMAL | Classification label when RALLY_MATURE conditions are not met |

---

## 2. Locked Design Decisions

The following decisions were locked at Phase 0 close-out S158 (preceding this spec authoring). The spec embodies them verbatim. Source authorities are reproduced for traceability.

| ID | Decision | Source authority |
|---|---|---|
| D1 | **Counting semantics:** window-ratio over 15-bar lookback (not strict-consecutive) | Minervini 12/15 tennis ball pattern admits lumpy climax-runs (MSTR canonical case had 3 down days within the climax window); strict-consecutive would under-trigger |
| D2a | **Up-bar window threshold:** ≥ 10/15 (≈ 0.667) | Minervini 12/15 relaxed to 10/15 to admit climax-onset cases short of full tennis-ball-action certification |
| D2b | **Magnitude threshold:** ≥ 5.0 ATR widths | IBD climax-top floor (25% in 3 weeks ≈ 5-7 ATR for momentum names); above existing EXTENSION-gate territory (~3-4 ATR) to avoid signal overlap with extension_analysis |
| D3 | **IVR-001 §4.5 matrix content:** drafted in this spec §5; Operator reviews semantic direction at spec acceptance | New IVR-001 §4.5 substantive amendment |
| D4 | **Weekly-frame rally age (Rally_Age_Weekly):** deferred to v1.1 Track 2 retro-fit | WKC-001 weekly stack freshly closed at S156; lean v1.0 scope |
| D5 | **Frame mapping:** Profile A: hourly primary / daily context. Profile B: daily primary / weekly context. Profile C: weekly primary / monthly context | Doc 2 §III canonical frame map |
| D6 | **Output location:** new `rally_state` top-level grouped sub-object in transform.py output, parallel to `extension_analysis`, `floor_analysis`, `volume_at_price` | OTL-001 self-documentation convention |
| D7 | **Verdict impact:** zero — advisory only. New caution_factor emissions are additive on the existing `action_summary.caution_factors[]` array via IVR-001's existing emission path | Bundle 4A Track 1 classification per SIR §11.2 — verdict-invariant by design despite §4.5 matrix being a value-meaning addition |
| D8 | **Naming convention:** flat keys `Rally_Up_Bar_Count_{Primary,Context}`, `Rally_Up_Bar_Ratio_{Primary,Context}`, `Rally_Window_Bars`, `Rally_Magnitude_ATR`, `Rally_Anchor_Price`, `Rally_Maturity_Label`. Grouped section: `rally_state` | Preserves "rally" semantic continuity with the original CONCEPT entry; flat-key names accurately reflect the window-ratio semantics (vs the original "Rally_Age" name that implied strict-consecutive count) |

---

## 3. Architecture

### 3.1 Helper specification (`tbs_engine/compute.py`)

**New module-level constants** (top of file, alphabetical order after existing constants):

```python
RLY_WINDOW_BARS = 15  # Minervini tennis ball pattern window basis
RLY_MATURE_RATIO_THRESHOLD = 10.0 / 15.0  # ≈ 0.667 — RALLY_MATURE up-bar ratio gate
RLY_MATURE_MAGNITUDE_ATR_THRESHOLD = 5.0  # IBD climax-top ATR-width floor
```

**New helper function:**

```python
def _compute_rally_state(
    close_series: pd.Series,
    current_atr: float,
    frame_label: str,  # "Primary" or "Context", for downstream desc text only
) -> Dict[str, Any]:
    """
    Compute rally state metrics over the trailing RLY_WINDOW_BARS bar window.

    Args:
        close_series: Close prices, indexed by bar timestamp ascending. Must have
                      >= RLY_WINDOW_BARS + 1 bars (one extra for prior_close comparison).
        current_atr: ATR value for magnitude calculation. Caller decides which frame's ATR.
        frame_label: Either "Primary" or "Context"; used only for downstream desc text
                     assembly; does NOT change the computation.

    Returns:
        Dict with keys:
            'up_bar_count': int -- number of bars in window where close > prior_close
            'window_bars': int -- constant RLY_WINDOW_BARS
            'ratio': float -- up_bar_count / window_bars
            'magnitude_atr': float -- (close[-1] - close[-window_bars]) / current_atr
            'anchor_price': float -- close[-window_bars]
            'current_price': float -- close[-1]
            'atr_value': float -- echo of current_atr
            'frame_label': str -- echo of input
        Defensive returns (all numeric fields None + 'reason' key):
            INSUFFICIENT_BARS: close_series has < RLY_WINDOW_BARS + 1 bars
            ATR_UNAVAILABLE: current_atr is None or <= 0
            NAN_IN_WINDOW: any close in the window is NaN
    """
```

**Defensive behaviour contract:**

| Input condition | Return |
|---|---|
| `len(close_series) < RLY_WINDOW_BARS + 1` | All-null dict with `reason: "INSUFFICIENT_BARS"` |
| `current_atr is None or current_atr <= 0` | All-null dict with `reason: "ATR_UNAVAILABLE"` |
| Any `close_series.iloc[-(RLY_WINDOW_BARS+1):]` value is NaN | All-null dict with `reason: "NAN_IN_WINDOW"` |
| Valid inputs | Fully populated dict per Returns block above |

The helper is pure: no side effects, no `ctx` writes, no logging in production paths.

### 3.2 Output surface

New `rally_state` top-level grouped sub-object in transform.py output:

```json
"rally_state": {
  "primary": {
    "up_bar_count": 12,
    "window_bars": 15,
    "ratio": 0.80,
    "frame": "hourly",
    "desc": "12 of last 15 hourly bars closed above prior close (ratio 0.80)"
  },
  "context": {
    "up_bar_count": 11,
    "window_bars": 15,
    "ratio": 0.73,
    "frame": "daily",
    "desc": "11 of last 15 daily bars closed above prior close (ratio 0.73)"
  },
  "magnitude": {
    "atr_widths": 6.42,
    "anchor_price": 410.55,
    "current_price": 437.20,
    "atr_value": 4.16,
    "desc": "Rally has spanned 6.42 ATR widths from window-start anchor at $410.55"
  },
  "maturity": {
    "label": "RALLY_MATURE",
    "trigger": {
      "context_ratio_threshold": 0.667,
      "context_ratio_actual": 0.73,
      "context_ratio_met": true,
      "magnitude_atr_threshold": 5.0,
      "magnitude_atr_actual": 6.42,
      "magnitude_atr_met": true,
      "both_met": true
    },
    "desc": "RALLY_MATURE -- context up-bar ratio 0.73 >= 10/15 AND magnitude 6.42 ATR >= 5.0"
  }
}
```

**NORMAL-case example (v1.1 — formalized from Phase 2 implementation reality):**

```json
"rally_state": {
  "primary": { "...": "..." },
  "context": { "...": "..." },
  "magnitude": { "atr_widths": 3.97, "...": "..." },
  "maturity": {
    "label": "NORMAL",
    "trigger": {
      "context_ratio_threshold": 0.667,
      "context_ratio_actual": 0.73,
      "context_ratio_met": true,
      "magnitude_atr_threshold": 5.0,
      "magnitude_atr_actual": 3.97,
      "magnitude_atr_met": false,
      "both_met": false
    },
    "desc": "NORMAL -- magnitude 3.97 ATR < 5.0"
  }
}
```

**maturity.desc format convention (v1.1 formalization):**

- **RALLY_MATURE case:** desc enumerates BOTH passing conditions in `AND`-conjoined form (e.g., `"RALLY_MATURE -- context up-bar ratio 0.73 >= 10/15 AND magnitude 6.42 ATR >= 5.0"`).
- **NORMAL case:** desc enumerates ONLY the failing condition(s) — if both fail, both listed in `AND`-conjoined form; if only one fails (the common case — typically magnitude), only that one is listed. Generic phrasing like `"RALLY_MATURE conditions not met"` is **NOT** emitted; the specific failing-condition desc provides actionable operator diagnostic value (which gate to look at — density or magnitude).
- **Defensive-null case:** entire `rally_state` block is `null` per the behaviour contract table below (no desc emitted at all).

The desc-format convention is intentionally asymmetric: RALLY_MATURE highlights *what both succeeded* (the climax-run signature itself); NORMAL highlights *what specifically failed* (operator-actionable diagnostic — is the rally density-light, magnitude-light, or both?). This is a Phase 2 implementation refinement formalized into the spec at v1.1 per the Phase 2 Hand-Back §2 finding; the v1.0 vocabulary-table line 76 phrasing "Classification label when RALLY_MATURE conditions are not met" remains accurate as a *vocabulary definition* but is not itself a desc-string template.

**Behaviour contract for the grouped output:**

| Condition | `rally_state` block |
|---|---|
| Both primary and context helpers return valid dicts | Fully populated as above; maturity label is `"RALLY_MATURE"` or `"NORMAL"` per §3.3 classification |
| Either helper returns defensive null | Entire `rally_state` block is `null`; all 8 flat keys are null |
| Maturity classification: `RALLY_MATURE` | Both `context_ratio_met` AND `magnitude_atr_met` are true |
| Maturity classification: `NORMAL` | At least one of `context_ratio_met` / `magnitude_atr_met` is false; trigger object populated for transparency |

### 3.3 Flat-key registration (`MAPPED_FLAT_KEYS` extension)

Eight new flat keys:

| Flat key | Type | Description | Window source |
|---|---|---|---|
| `Rally_Up_Bar_Count_Primary` | int or null | Up-bar count in 15-bar primary-frame window | Primary helper result |
| `Rally_Up_Bar_Count_Context` | int or null | Up-bar count in 15-bar context-frame window | Context helper result |
| `Rally_Up_Bar_Ratio_Primary` | float or null | Primary up-bar ratio (informational; not a gate input) | Primary helper result |
| `Rally_Up_Bar_Ratio_Context` | float or null | Context up-bar ratio (one of two RALLY_MATURE gate inputs) | Context helper result |
| `Rally_Window_Bars` | int | Constant `RLY_WINDOW_BARS = 15` (surfaced for self-documentation) | Constant |
| `Rally_Magnitude_ATR` | float or null | Cumulative rally magnitude in ATR widths (one of two RALLY_MATURE gate inputs) | Context helper result `magnitude_atr` field |
| `Rally_Anchor_Price` | float or null | Close price 15 bars before iq bar (window start) | Context helper result `anchor_price` field |
| `Rally_Maturity_Label` | str or null | `"RALLY_MATURE"` or `"NORMAL"`; null on defensive returns | Output-layer classification per §4.2 |

**Note on `Rally_Magnitude_ATR` and `Rally_Anchor_Price` sourcing:** Both fields are sourced from the **context** helper, not primary. Rationale: the RALLY_MATURE classification gate is anchored to the context frame (the slower-moving frame is the more reliable rally-maturity indicator); the primary-frame magnitude is informational but does not currently drive a classification.

### 3.4 IVR-001 integration

IVR-001's `_gate_volatility_regime` (in `gates.py`) reads `Rally_Maturity_Label` from `flat_metrics` to drive §4.5 matrix lookup.

When `Rally_Maturity_Label == "RALLY_MATURE"`:
- Override `volatility_regime.context_interpretation.label` per §4.5 matrix (using regime as the row key)
- Override `volatility_regime.context_interpretation.desc` per §4.5 matrix
- Emit `caution_factor` string per §5.2 table (3 regimes emit; ALIGNED stays null)
- Append `caution_factor` to `action_summary.caution_factors[]` (existing IVR-001 surface)

When `Rally_Maturity_Label != "RALLY_MATURE"` (i.e., `"NORMAL"` or null):
- Existing IVR-001 §4.1 / §4.2 matrix logic unchanged

**Critical design constraint:** RLY-001 does NOT add any gate input that affects verdict (PASS/REJECT/INVALID/HALT). The `Rally_Maturity_Label` is read only by `_gate_volatility_regime` for caution_factor emission. The gate function itself continues to return PASS unconditionally (IVR-001 is pure advisory per IVR-001 v1.0 §5). Net behavior on verdict: bitwise-unchanged given the same other inputs. Verified by negative-assertion test `TestRLY001VerdictInvariance` (see §6.2).

---

## 4. Implementation Detail

### 4.1 `tbs_engine/compute.py` changes

**Constants (new):** Three module-level constants per §3.1.

**Helper (new):** `_compute_rally_state` per §3.1 contract.

**Call sites in compute orchestration:** Two invocations per profile in the Profile-A / Profile-B / Profile-C branches.

1. **Primary-frame call:** After existing extension_analysis computation. Reads primary `close_series` and primary-frame ATR. Frame label `"Primary"`. Result stored as `ctx._rly_primary`.
2. **Context-frame call:** Parallel to primary call. Reads context `close_series` and context-frame ATR. Frame label `"Context"`. Result stored as `ctx._rly_context`.

**Profile mapping (per D5 lock):**

| Profile | Primary frame | Context frame | Frame strings emitted |
|---|---|---|---|
| A | Hourly | Daily | `primary.frame = "hourly"`, `context.frame = "daily"` |
| B | Daily | Weekly | `primary.frame = "daily"`, `context.frame = "weekly"` |
| C | Weekly | Monthly | `primary.frame = "weekly"`, `context.frame = "monthly"` |

**Profile C edge case:** Where monthly context is unavailable (Profile C ticker with <15 monthly bars per PCM-001 3-tier behavior — possible on the 4-17yr partial tier), `_compute_rally_state` returns `INSUFFICIENT_BARS` defensive null, the context section of `rally_state` is null, and `Rally_Maturity_Label` flat key is null. Per PCM-001 D4, absence is the documented semantic.

### 4.2 `tbs_engine/output.py` changes

**New helper:** `_assemble_rally_state(ctx, p_code) -> Tuple[Dict, Dict]`

Returns a `(rally_state_block, flat_keys_dict)` tuple. The first element is the §3.2 JSON shape (or `None`); the second is a flat-keys dict with the 8 new keys.

**Maturity classification logic (in `_assemble_rally_state`):**

```python
context_ratio = ctx._rly_context['ratio']
magnitude_atr = ctx._rly_context['magnitude_atr']

if context_ratio is None or magnitude_atr is None:
    maturity_label = None
elif (context_ratio >= RLY_MATURE_RATIO_THRESHOLD
      and magnitude_atr >= RLY_MATURE_MAGNITUDE_ATR_THRESHOLD):
    maturity_label = "RALLY_MATURE"
else:
    maturity_label = "NORMAL"
```

**Rationale for output-layer classification (not compute-layer):** Keep `compute.py` helper pure (raw metrics only); maturity-label thresholding is an output-layer concern because it determines downstream gate routing in `_gate_volatility_regime` (which already reads classification labels, not raw metrics).

**Call site in `_assemble_output`:** After extension_analysis assembly and before action_summary assembly:

```python
rally_state_block, rally_flat_keys = _assemble_rally_state(ctx, p_code)
output['rally_state'] = rally_state_block  # may be None
flat_metrics.update(rally_flat_keys)
```

### 4.3 `tbs_engine/transform.py` changes

**Reverse-map extension:** `_MAPPED_FLAT_KEYS_RALLY_STATE` dict added to existing `MAPPED_FLAT_KEYS` registration, with all 8 new keys mapped to their grouped-output paths (`rally_state.primary.up_bar_count`, etc.).

**New helper:** `_assemble_rally_state_group(flat_metrics) -> Optional[Dict]` reads the 8 flat keys and produces the §3.2 JSON shape. Returns `None` if `Rally_Maturity_Label` is null (or any required key is null).

**Hook into top-level grouping pass:** Called alongside existing `_assemble_extension_analysis_group`, `_assemble_floor_analysis_group`, etc.

**Vocabulary-collision audit (spec-time verification):** No existing `rally_state` key, no existing `Rally_*` flat keys, no existing `RALLY_MATURE` / `NORMAL` labels in `MAPPED_FLAT_KEYS`. Verified via `grep -i "rally" tbs_engine/transform.py` returning zero matches at the S157 baseline (standalone implementer to re-verify at session start).

### 4.4 `tbs_engine/gates.py` changes

**`_gate_volatility_regime` extension:** Add §4.5 matrix lookup branch before the existing §4.1 / §4.2 / etc. matrix lookups.

```python
def _gate_volatility_regime(ctx, p_code, flat_metrics):
    # ... existing IV/HV regime computation unchanged ...

    rally_maturity = flat_metrics.get("Rally_Maturity_Label")

    if rally_maturity == "RALLY_MATURE":
        # §4.5 matrix lookup
        interp_label, interp_desc, caution_str = _RLY_MATURITY_MATRIX[regime_label]
    else:
        # Existing §4.1 / §4.2 / etc. matrix logic
        interp_label, interp_desc, caution_str = _existing_matrix_lookup(regime_label, trigger_state)

    # Existing caution_factor emission unchanged
    if caution_str is not None:
        ctx._caution_factors.append(caution_str)

    # Gate verdict: unchanged -- IVR-001 returns PASS unconditionally
    return PASS, {"context_interpretation": {"label": interp_label, "desc": interp_desc},
                  "caution_factor": caution_str}
```

**New module-level constant in `gates.py`:** `_RLY_MATURITY_MATRIX` dict per §5 IVR-001 amendment text. Includes all 4 regime cells with `(interp_label, interp_desc, caution_str)` tuples.

**Vocabulary collision audit (spec-time):** New §4.5 interpretation labels — DELAYED CLIMAX RISK, MATURE TREND, CLIMAX RISK, EXHAUSTION SIGNAL — verified non-colliding against existing §4.1 / §4.2 / §4.3 / §4.4 labels in IVR-001 spec v1.0. Standalone implementer to re-verify against any IVR-001 spec drift since v1.0.

---

## 5. IVR-001 Spec v1.0 → v1.1 Substantive Amendment

The IVR-001 spec receives a substantive §4.5 addition (analogous to BUNDLE-001 v1.0 → v1.3 / FRR-001 v1.0 → v1.1 precedent). The amendment text below is to be inserted in IVR-001 spec v1.1 immediately after §4.4 and before §5 of the existing IVR-001 v1.0 layout.

### 5.1 New §4.5 — "At Rally Maturity (RALLY_MATURE trigger, late-stage continuation)"

The RALLY_MATURE trigger fires when both of the following are simultaneously satisfied on the **context frame**:

1. Up-bar window ratio ≥ 10/15 over the trailing 15 bars (≥10 bars closed above prior close)
2. Cumulative rally magnitude ≥ 5.0 ATR widths (computed as `(close[-1] - close[-15]) / current_atr`)

When RALLY_MATURE is active, the volatility regime takes on a distinct interpretation per the following matrix:

| Regime | Interpretation Label | Description |
|---|---|---|
| COMPLACENT | DELAYED CLIMAX RISK | Options market shows no fear at mature-rally levels. The combination of context-frame up-bar density (≥10/15) and ≥5.0 ATR cumulative magnitude with a low IV/HV ratio suggests broad disregard for exhaustion risk. The longer the rally with no volatility-pricing reaction, the sharper the eventual mean reversion tends to be. Exercise caution on new continuation entries. |
| ALIGNED | MATURE TREND | The rally is mature but the options market is pricing the move proportionally. No additional signal from IVR. Defer to engine extension and structural assessment. Existing positions ride the trend; new entries acceptable provided extension and structural posture remain favourable. |
| ELEVATED | CLIMAX RISK | Options market pricing moderately more risk at late-stage continuation. Early warning: smart money may be hedging against the climax. Avoid initiating new continuation entries; consider scaling existing positions on strength. |
| EXTREME | EXHAUSTION SIGNAL | Highest-risk configuration. Late-stage rally (≥10/15 context up-bars + ≥5.0 ATR magnitude) compounded with EXTREME volatility regime constitutes a climax-run signature. Strong recommendation: avoid new entries; existing positions should consider profit-taking into strength per Minervini SEPA sell-rule guidance on climax tops. |

### 5.2 Convention Deviation — Caution Factor Emission on COMPLACENT × RALLY_MATURE

Existing IVR-001 §4.1 (At Extension) and §4.2 (At Pullback) emit caution_factor only for ELEVATED and EXTREME regimes; COMPLACENT and ALIGNED are treated as informational without caution (per IVR-001 v1.0 §5 caution_factor specification).

**§4.5 deviates from this convention:** COMPLACENT × RALLY_MATURE also emits a caution_factor.

**Rationale:** In the §4.1 / §4.2 contexts, COMPLACENT is benign-or-supportive (continuation support / calm pullback). In the §4.5 context, COMPLACENT at peak is the most insidious form of climax-run setup — operator-market complacency at a structurally late-stage move is the classical "blow-off top with no warning signs" pattern that Minervini and O'Neil both flag as the riskiest entry configuration. Treating COMPLACENT × RALLY_MATURE as benign would violate the spec's stated design intent (climax-awareness) for the sake of mechanical convention preservation.

**Caution factor string templates:**

| Regime | caution_factor string |
|---|---|
| COMPLACENT | `"VOLATILITY REGIME: COMPLACENT -- DELAYED CLIMAX RISK at mature rally. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market showing no fear. Sharp mean reversion risk."` |
| ALIGNED | `null` (no caution; trend acknowledged but proportionally priced) |
| ELEVATED | `"VOLATILITY REGIME: ELEVATED -- CLIMAX RISK at mature rally. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market pricing reversal risk."` |
| EXTREME | `"VOLATILITY REGIME: EXTREME -- EXHAUSTION SIGNAL: climax-run signature. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market pricing significant reversal. Consider profit-taking."` |

Substitution: `[X.XX]` = actual context ratio value to 2 decimals; `[Y.YY]` = actual magnitude ATR value to 2 decimals.

### 5.3 IVR-001 Spec Output Surface — No Changes

The new §4.5 inherits IVR-001's existing transparency conventions per v1.0 §5:
- `volatility_regime.context_interpretation.label` populated with the §4.5 label
- `volatility_regime.context_interpretation.desc` populated with the §4.5 description
- `volatility_regime.caution_factor` populated per §5.2 table (or null for ALIGNED)
- `caution_factors[]` array appended (existing IVR-001 surface)

No new fields on `volatility_regime` block; no schema change. Verdict bitwise-invariant.

§4 enumeration order after amendment: §4.1 At Extension → §4.2 At Pullback → §4.3 At Breakout → §4.4 At Recovery → **§4.5 At Rally Maturity (NEW)** → §4.6 Default (renumbered from existing IVR-001 v1.0 §4.5) → §5 Output Specification.

**v1.1 amendment note on enumeration correction:** RLY-001 v1.0 §5.3 originally stated "§4.5 At Rally Maturity (NEW) → §5 Output Specification" — this enumeration was authored at S158 without auditing the existing IVR-001 v1.0 §4 layout, which already contains §4.5 Default (TRENDING state, no special context) as the fallback section. The natural resolution preserves IVR-001's own semantic invariant — each numbered §4.x section is a *trigger context* (Extension / Pullback / Breakout / Recovery / Rally Maturity) except the last, which is the *fallback* — by inserting new §4.5 At Rally Maturity between §4.4 At Recovery and the (now-renumbered) §4.6 Default. The IVR-001 v1.1 spec carries this renumbering verbatim. This cross-spec audit gap is logged as `ANALYST-RLY-001-SPEC-3` Bug Register entry at S159 Phase 4 closure, strengthening SIR §11 unified pre-spec-delivery checklist augmentation candidacy to 5 confirmed instances (ANALYST-002 + ANALYST-003 + ANALYST-CFL-001-SPEC-1 + ANALYST-RLY-001-SPEC-2 + ANALYST-RLY-001-SPEC-3).

### 5.4 IVR-001 Spec Document History Entry

```markdown
| v1.1 | 2026-05-XX | Session 158 (RLY-001 closure) | Substantive: new §4.5 "At Rally Maturity" context matrix with 4 regime cells covering RALLY_MATURE × {COMPLACENT, ALIGNED, ELEVATED, EXTREME}. Convention deviation: COMPLACENT × RALLY_MATURE emits caution_factor (rationale: complacency at peak is the most insidious climax-run setup; differs from §4.1/§4.2 where COMPLACENT is benign). New caution_factor strings for 3 of 4 regime cells (ALIGNED unchanged at null). §4 enumeration order updated. No §1-§3 / §5-§7 changes. Cross-reference: RLY-001 v1.0 spec §5. |
```

---

## 6. Acceptance Criteria and Test Plan

### 6.1 Unit tests (`tests/unit/test_rly001_rally_state.py` — new file)

| Class | Test count | Coverage |
|---|---|---|
| `TestRLY001HelperCorrectness` | ~12 | `_compute_rally_state` returns correct values across synthetic close series: full-streak (15/15), half-and-half (8/15), all-down (0/15), threshold-exact (10/15), threshold-minus-one (9/15), various magnitude calculations |
| `TestRLY001DefensiveBehaviour` | ~6 | Insufficient bars / None ATR / zero ATR / NaN in window — each returns null dict with appropriate `reason` value |
| `TestRLY001MaturityClassification` | ~10 | Output-layer maturity-label computation: 10/15 + 5.0 ATR → RALLY_MATURE; 9/15 + 5.0 ATR → NORMAL; 10/15 + 4.9 ATR → NORMAL; 12/15 + 7.0 ATR → RALLY_MATURE; boundary cases at exactly the thresholds |
| `TestRLY001OutputShape` | ~6 | `_assemble_rally_state` output dict matches §3.2 schema; absent (`null`) on defensive null; trigger sub-object populated for both RALLY_MATURE and NORMAL states |
| `TestRLY001FlatKeyRoundTrip` | ~4 | All 8 new flat keys round-trip cleanly through transform.py `_flatten()` and `_unflatten()` |
| `TestRLY001IVRMatrix` | ~8 | IVR-001 §4.5 matrix lookup: each of 4 regime × 2 maturity (RALLY_MATURE / NORMAL) combinations produces correct context_interpretation label + caution_factor string |
| `TestRLY001NotInGatesFile` (negative assertion) | 1 | `inspect.getsource()` check — no `RLY_*` constant or `_compute_rally_state` referenced in `_gate_*` function bodies other than the §4.5-specific caution_factor write in `_gate_volatility_regime`; RLY-001 is not a gate input on any other gate |
| `TestRLY001VocabularyHygiene` (negative assertion) | 1 | New flat key names + interpretation labels + caution_factor strings — no collisions with existing engine vocabulary surfaced via `MAPPED_FLAT_KEYS` scan |
| `TestRLY001VerdictInvariance` (negative assertion) | 4 | Identical fixture input pre/post RLY-001 introduction produces identical verdict (PASS/REJECT/INVALID/HALT) across all 4 regime cells; only `caution_factors[]` array differs (3 of 4 regimes append a new entry; ALIGNED unchanged) |
| `TestRLY001ProfileMatrix` | ~6 | Frame-mapping correctness per D5: Profile A primary=hourly+context=daily; Profile B primary=daily+context=weekly; Profile C primary=weekly+context=monthly. Including PCM-001 Profile C edge case (insufficient monthly bars → defensive null) |

**Target:** ~58 new tests across 10 classes.

**Baseline status (S157 Turn 2 closure):** 3010 passed / 5 skipped / 1 failed (the pre-existing `BUG-CFL001-PRE-1` failure logged S157).

**Expected post-RLY-001 baseline:** ~3068 passed / 5 skipped / 1 failed (the pre-existing failure remains; new tests add cleanly with zero regressions).

### 6.2 Live validation cohort (Phase 3, Operator-led)

Minimum cohort: 5 tickers across all 3 profiles, hitting at least these dimensions:

| Coverage dimension | Witness requirement |
|---|---|
| Profile A RALLY_MATURE positive | ≥1 Profile A ticker with context (daily) ratio ≥ 10/15 AND magnitude ≥ 5.0 ATR; verifies the §4.5 matrix fires end-to-end on Profile A |
| Profile A NORMAL | ≥1 Profile A ticker with ratio < 10/15 or magnitude < 5.0 ATR (regression-invariance witness against existing IVR-001 §4.1/§4.2 paths) |
| Profile B RALLY_MATURE positive | ≥1 Profile B ticker with context (weekly) ratio ≥ 10/15 AND magnitude ≥ 5.0 ATR |
| Profile C | ≥1 Profile C ticker — either RALLY_MATURE positive or null-emit (PCM-001 partial-tier insufficient-monthly-bars edge case) |
| RALLY_MATURE × ELEVATED end-to-end | ≥1 case combining the new §4.5 matrix entry; verifies caution_factor propagates from `_gate_volatility_regime` through `action_summary.caution_factors[]` array |
| Defensive null path | ≥1 ticker on a profile where context-frame ATR is null or window has <15 bars — verify `rally_state` block is `null` and `Rally_Maturity_Label = null` (no engine crash) |

**Stretch witness target (if cohort permits):** A canonical MSTR-class case — context up-bar ratio ≥ 10/15 + magnitude ≥ 6.0 ATR + simultaneously ELEVATED or EXTREME volatility regime. Confirms the design intent fires on the type of case that motivated the capability.

### 6.3 Acceptance criteria (Phase 4 closure gates)

1. All ~58 new unit tests pass; zero regressions in any pre-RLY-001 test class
2. Negative-assertion tests `TestRLY001NotInGatesFile` + `TestRLY001VocabularyHygiene` + `TestRLY001VerdictInvariance` all pass
3. Live cohort ≥ 5 tickers covers the 6 dimensions of §6.2 (positive witnesses + regression-invariance + defensive null)
4. Zero numeric drift on any pre-RLY-001 field across live cohort (verified via fingerprint diff against pre-RLY-001 cached outputs where feasible — analogous to the CFL-001 fingerprint utility precedent)
5. Module import graph remains acyclic post-implementation; verified by `grep -cE "^(import |from )" compute.py / output.py / transform.py / gates.py` baseline match + zero ImportError across all 11 `tbs_engine/` modules
6. SIR §9 Pre-Delivery Verification Checklist all green at Phase 4 close

---

## 7. Pre-Implementation Verification (Spec-Authoring Audit — SIR §11 Augmentation Trial)

Per SIR §11 augmentation candidacy strengthened to 3 confirmed incident instances (ANALYST-002 S135 + ANALYST-003 S136 + ANALYST-CFL-001-SPEC-1 S157, all "pre-implementation verification list run only in standalone prompt, not at spec authoring time"), this spec exercises the unified pre-spec-delivery checklist at spec-authoring time. Findings documented for standalone implementer reference; standalone Analyst still re-runs the same checks at Phase 2 session start per defense-in-depth.

### 7.1 Call-order audit

**Question:** Where in `main.py` orchestration does `_compute_rally_state` need to be called? Before or after `_gate_volatility_regime`?

**Finding:** `_gate_volatility_regime` (in `gates.py`) consumes `Rally_Maturity_Label` (written by the output layer at `_assemble_rally_state`) for §4.5 matrix lookup. The chain is:

```
compute.py: _compute_rally_state (primary + context) writes ctx._rly_primary / ctx._rly_context
output.py: _assemble_rally_state reads ctx._rly_* and writes Rally_Maturity_Label to flat_metrics
gates.py: _gate_volatility_regime reads flat_metrics["Rally_Maturity_Label"]
```

Therefore `_compute_rally_state` invocations must occur in the **compute phase** (pre-gate), parallel to other compute-layer helpers like `_compute_extension_analysis`. The output-layer maturity classification must occur **before** `_gate_volatility_regime`. Per the EEM v2.41 gate cascade ordering (G.5 → G.5.5 → G.5.6 → G.5.7 with `_gate_volatility_regime` somewhere in this sequence), the compute call insertion is in the pre-gate phase.

**Standalone implementer verification step:** Confirm the actual current call-order in `main.py` against EEM v2.41. If call-order has drifted since EEM v2.41 was published, flag to Operator before proceeding. Additionally: verify that `_assemble_rally_state` runs in `output.py` before `_gate_volatility_regime` is invoked — if the output assembly is invoked post-gates in the current architecture, the maturity-label write must move earlier.

### 7.2 Sort-order check

**Question:** Does any RLY-001 logic depend on sorted upstream data?

**Finding:** No. The 15-bar window slice is taken directly from `close_series.iloc[-RLY_WINDOW_BARS:]` which preserves bar order (timestamp-indexed ascending per existing engine convention). No sort operation is required, and no upstream sort order is assumed beyond what the existing engine already provides.

**Standalone implementer verification step:** Confirm `close_series` passed to `_compute_rally_state` is in ascending timestamp order at the call site. Per existing engine convention (verified across `_compute_extension_analysis` and similar helpers at S157 baseline), this is the standard contract — verify it holds for both primary and context frames.

### 7.3 Shared-reference / partition-leak check

**Question:** Does `rally_state` risk leaking into other output sub-objects via BUGR-002-style shallow list comprehensions or shared dict references?

**Finding:** No. `rally_state` is a fresh top-level grouped sub-object assembled directly from the 8 new flat keys; it does not share refs with `floor_analysis.hierarchy`, `trade_setup.target.hierarchy`, or any partitioned list. The assembly in `transform.py` happens at the top-level grouping pass, structurally separated from any partition-based assembly (e.g., the BUGR-002 partition for cleared_levels / overhead_levels).

**Standalone implementer verification step:** Confirm the rally_state assembly site is structurally separated from any hierarchy-entry construction. Per CFL-001 S157 precedent (which surfaced a shared-reference leak at the spec-author-proposed pre-CNV-001 call site), post-partition or top-level placement is the canonical safe placement pattern.

### 7.4 Prompt-vs-source-truth verification

**Question:** Are all file paths and references in this spec actually present in the current source snapshot?

**Finding (spec authoring time, S158):**

| Reference | Status at S158 spec authoring |
|---|---|
| `tbs_engine/compute.py` | Present in project source as of S157 baseline (engine SHA `e206a968...` for transform; compute baseline at parallel snapshot per S157 Turn 2 inventory) |
| `tbs_engine/output.py` | Present (SHA `d9bd127a...`) |
| `tbs_engine/transform.py` | Present (SHA `e206a968...`) |
| `tbs_engine/gates.py` | Present (SHA `676fa148...`) |
| `tests/unit/test_rly001_rally_state.py` | **NEW file** — will be created during implementation; does not exist at spec authoring time |
| `IVR001_Volatility_Regime_Context_Spec_v1_0.md` | Verified present in project storage |
| `TBS_Engine_Execution_Map_v2_41.md` | Verified present |
| `TBS_Document_2_Core_Strategy_v8_63.md` | Verified present (post-S157 cascade) |
| `TBS_Document_7_Daily_Battle_Card_v8_5_53.md` | Verified present |
| `TBS_Document_8_Systemic_Automation_Data_Retrieval_v8_7_63.md` | Verified present |

**Standalone implementer verification step:** Re-verify all above paths at standalone session start. Per ANALYST-PROMPT-001 S156 precedent (`tests/unit/test_flatten_stability.py` referenced in WKC-001 standalone prompt did not exist at standalone session start), this check is mandatory before any implementation work begins.

---

## 8. DIA Scope (Phase 4)

| Document | Version Bump | Scope |
|---|---|---|
| Doc 2 v8.63 → v8.64 | Substantive | §IV Output Schema Reference: new `rally_state` top-level grouped sub-object documented (4 sub-objects: primary, context, magnitude, maturity). §III if profile frame mapping table needs to reference RLY-001 hourly/daily/weekly/monthly mapping (verify-only — D5 follows existing canonical map). New "Notes on special construction" entry on RLY-001 advisory-only contract + COMPLACENT × RALLY_MATURE convention deviation. |
| Doc 7 v8.5.53 → v8.5.54 | Substantive | Step 6 new body bullet "Rally Maturity Awareness (RLY-001)" inserted alongside IVR-001 / extension_analysis discussion. Operator-facing reading guidance on RALLY_MATURE × {COMPLACENT, ALIGNED, ELEVATED, EXTREME} combinations + explicit note on RLY-001 advisory-only nature. Climax-run interpretation framing. |
| Doc 8 v8.7.63 → v8.7.64 | Substantive mirror | §II Layer 2 four-file engine touch matrix (compute.py + output.py + transform.py + gates.py); helper signatures + 3 constants + 8 new flat keys + 4 §4.5 matrix cells. Body bullets retained verify-only per BUGR-002 v8.7.52 / Tranche 1 v8.7.62 precedent — substantive content lives in the v8.7.64 changelog entry. |
| EEM v2.41 → v2.42 | Substantive on indicator stack rows; verify-only on gate cascade | New §II row for `_compute_rally_state` indicator-stack step (pre-gate phase, parallel to `_compute_extension_analysis`). Gate cascade G.5 → G.5.5 → G.5.6 → G.5.7 unchanged (verify-only — IVR-001 §4.5 caution_factor emission is internal to `_gate_volatility_regime`, no gate function signature change). |
| IVR-001 spec v1.0 → v1.1 | Substantive | Per §5 above — new §4.5 matrix; §1-§3, §5-§7 unchanged; Document History v1.1 row appended; convention deviation rationale captured in §4.5. |
| README v8.6.30 → v8.6.31 | Cascade | Document Authority table rows refreshed (Doc 2 / Doc 7 / Doc 8 / EEM / IVR-001 spec / PEO); Last Updated narrative S157 CFL-001 → S158 RLY-001 replacement; Version line `+ RLY-001` appended to amendment list. |
| PEO v9.21 → v9.22 | Substantive | Tier 1K Bundle 4A (RLY-001) ✅ CLOSED annotation; Document History v9.22 row; ASCII Dependency Map annotation `1K: Bundle 4A (RLY-001) ✅ CLOSED S158`. Tier 1K Bundle 4B (RLC-001) remains open at CONCEPT pending separate Track 2 inline cadence. Active workload arithmetic update. |
| Bug Register | Status advances + new entries | RLY-001 🟤 CONCEPT → 🟠 SPECIFIED S158 (this spec) → 🟡 IMPLEMENTED S### → 🟢 SYNCED S### → ✅ CLOSED S### full lifecycle. New CONCEPT entries logged at spec landing: `RLY-001-CAL-1`, `RLC-001-CAL-1`, `RLC-001-TBA-1`, `RLC-001-REC-1`. Phase 0 close-out narrative captured in S158 changelog. |

---

## 9. Calibration Follow-Ups (CONCEPT — log at spec landing)

| ID | Title | Severity | Status | Trigger / scope |
|---|---|---|---|---|
| `RLY-001-CAL-1` | RALLY_MATURE threshold review (window ratio 10/15 + magnitude 5.0 ATR) | Low | 🟤 CONCEPT | Calibrate against 3-6 months live data; review false-trigger / under-trigger rates against operator-reviewed climax cases. Same pattern as IVR-001-CAL-1, CFL-001-CAL-1. Resolution mechanism: 2-line constant update + commentary. |
| `RLC-001-CAL-1` | Strength band cuts review (Reclaim Bar Strength Score 0.50 / 0.75) | Low | 🟤 CONCEPT | RLC-001 separate Track 2 spec; band cuts reviewed against 3-6 months live RECLAIM data |
| `RLC-001-TBA-1` | Multi-bar tennis ball action pattern (15-bar window with 12/15 up-closes + 9/15 upper-half range) | Low | 🟤 CONCEPT | Future scope extension — Minervini's literal tennis ball action criterion as a separate composite indicator. Current RLC-001 v1.0 evaluates single-bar reclaim strength only. Note: RLY-001 v1.0 already adopts the 15-bar window basis for rally-age density — synergy with RLC-001-TBA-1 future spec for shared helper. |
| `RLC-001-REC-1` | Extend Reclaim Bar Strength Score to REC-001 Recovery path | Low | 🟤 CONCEPT | Future scope extension; out of RLC-001 v1.0 scope (RECLAIM verdict only) |

---

## 10. Cross-References

- `TBS_Bug_Register.md` — RLY-001 CONCEPT entry (Session 123 origin, lines 4903-4948 at S157 baseline); Tier 1K Bundle 4 summary row (line 259); this spec advances RLY-001 to 🟠 SPECIFIED S158
- `TBS_Engine_Domain_Prioritised_Execution_Order_v9_21.md` — Tier 1K Bundle 4 specification at lines 272-281
- `IVR001_Volatility_Regime_Context_Spec_v1_0.md` v1.0 — base IVR-001 spec amended to v1.1 by this spec's §5
- `TBS_Document_2_Core_Strategy_v8_63.md` — §III canonical frame mapping basis for D5 (Profile A hourly/daily; Profile B daily/weekly; Profile C weekly/monthly)
- `TBS_Document_7_Daily_Battle_Card_v8_5_53.md` — Step 6 operator-facing reading guidance target for DIA
- `TBS_Document_8_Systemic_Automation_Data_Retrieval_v8_7_63.md` — §II Layer 2 engine touch matrix target for DIA
- `TBS_Engine_Execution_Map_v2_41.md` — gate cascade reference; indicator stack row for new `_compute_rally_state` step
- `TBS_Analyst_Session_Integrity_Rules.md` §11 Track Architecture — Bundle 4A as Track 1 (mandatory per §11.2 file-scope: `compute.py` touch fails Track 2 eligibility)
- `TBS_Amendment_Control_Process_v1_2.md` §6 Track 1 cadence (Phase 0 DQ resolution → Phase 1 spec authoring → Phase 2 standalone implementation → Phase 3 live validation → Phase 4 6-document DIA cascade)
- Companion `CFL001_Level_Confluence_Detection_Spec_v1_1.md` v1.1 (S157 first Track 2 / Claude Code process trial); RLY-001 follows the Track 1 conventional cadence, not the Track 2 lean Claude Code workflow
- Sister Bundle 4B `RLC001_Reclaim_Bar_Strength_Score_Spec_v1_0.md` (Track 2, to be authored after RLY-001 v1.0 implementation closes or in parallel per Operator preference)

---

## 11. Document History

| Version | Date | Session | Notes |
|---|---|---|---|
| v1.0 | 2026-05-18 | S158 Phase 1 | Initial spec authoring. Embodies Phase 0 DQ resolutions locked at S158 same-session preceding (9 decisions D1-D8 per §2). Pre-implementation verification list (§7) executed at spec-authoring time per SIR §11 augmentation candidacy strengthened by ANALYST-002 / ANALYST-003 / ANALYST-CFL-001-SPEC-1 incident class. New IVR-001 §4.5 substantive amendment text embedded in §5 for downstream IVR-001 v1.1 application. Convention deviation on COMPLACENT × RALLY_MATURE caution_factor emission documented and justified in §5.2. All thresholds traced to source authorities per SIR §10: O'Neil/Webby IBD weekly precedent (≥5 consecutive up weeks = climax candidate), Minervini tennis ball pattern (12/15 up-closes basis), IBD climax-top definition (25-50% in ≤3 weeks ≈ 5-7 ATR for momentum names), MSTR Jan-Feb 2021 canonical case (10/13 up-days, ≈6.5 ATR — both density and magnitude thresholds catch). Working session number S158 committed as assumption; globally find-replaceable if Operator's numbering differs. |
| v1.1 | 2026-05-19 | S159 Phase 4 (this amendment) | Three surgical amendments to v1.0 at Phase 4 closure of Tier 1K Bundle 4A. **(a) §3.2 maturity.desc format formalization** — added NORMAL-case example block alongside existing RALLY_MATURE example; documented asymmetric desc-format convention (RALLY_MATURE enumerates both passing conditions in `AND`-conjoined form; NORMAL enumerates only the failing condition(s) — operator-actionable diagnostic value); formalized from Phase 2 Implementation Hand-Back §2 finding where implementation correctly emitted `"NORMAL -- magnitude 3.97 ATR < 5.0"` rather than generic phrasing. **(b) §5.3 enumeration correction** — IVR-001 v1.0 already has `§4.5 Default (TRENDING state, no special context)` as the fallback section; v1.0 spec §5.3 enumeration "§4.3 (existing context) → §4.4 (existing context) → §4.5 At Rally Maturity (NEW) → §5" was authored without auditing IVR-001 §4 layout. Natural resolution: insert new §4.5 At Rally Maturity between §4.4 At Recovery and the renumbered §4.6 Default; preserves IVR-001's trigger-context-first / fallback-last semantic invariant. Cross-spec audit gap logged as `ANALYST-RLY-001-SPEC-3` Bug Register entry at S159 Phase 4 closure (Turn 5), strengthening SIR §11 unified pre-spec-delivery checklist augmentation candidacy from 4 → 5 confirmed instances. **(c) §11 Document History row** — this row. No engine-behaviour changes; spec body §1 / §2 / §3.1 / §3.3 / §3.4 / §4 / §5.1 / §5.2 / §5.4 / §6 / §7 / §8 / §9 / §10 unchanged at v1.1 (verified character-for-character against Phase 2 Implementation Hand-Back). Companion IVR-001 v1.0 → v1.1 spec amendment delivered same Phase 4 batch (Turn 2). |

---

**End of RLY-001 Specification v1.1**

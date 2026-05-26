# ITS-001 — Intraday-Tactical Surface (C+D Bundle) — Phase 1 Spec

**Document ID:** `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md`
**Version:** v1.0.1
**Status:** SPECIFIED (Phase 1 close — ready for Phase 2 Claude Code CLI implementation)
**Date authored:** 2026-05-24 (Session 165)
**Last refined:** 2026-05-24 (S165 — `_derive_intraday_high` pandas-API simplification, no behavior change)
**Lifecycle anchor:** Phase 0 WIP `TBS_Phase_0_WIP_Intraday_Tactical_Surface_v0_3.md` (14/14 sub-DQs locked S1–S4, 2026-05-23 to 2026-05-24)
**Authoring Analyst (Project chat):** Phase 1 spec authoring per SIR §11 Track 1.
**Spec authority:** Mission — when Brief and spec disagree, **spec wins**.

---

## 1. Purpose & Scope

### 1.1 Capability

The **Intraday-Tactical Surface** adds two related Profile-A-only features to the engine output:

- **Feature C — Regime-shift annotation.** Per-field `lookback_stale: bool` annotation on short-window fields (10-bar ESTABLISHED_LOW, 10-bar resistance, 10-bar AVWAP) PLUS a top-level summary section `intraday_tactical.lookback_status`, when the field's lookback window straddles a detected price-action discontinuity event (GAP or VOL_EXPANSION).
- **Feature D — Intraday-tactical surface.** A new top-level group `intraday_tactical` providing shelf detection (`intraday_tactical.shelf`), tactical stop (`intraday_tactical.tactical_stop`), and near-term target (`intraday_tactical.near_term_target`) — operationally tighter than the swing-frame hierarchies that currently dominate Profile A output.

Both features address the same operational gap: in macro-compressed conditions (the late-2025 / mid-2026 backdrop of Iran/oil/tariffs/US unpredictability driving frequent same-day-exit conversion of swing setups), swing-frame stops and targets are emotionally and operationally untenable as day-trade boundaries. The intraday-tactical surface provides Profile-A-aligned, hourly-granular levels parallel to the existing swing surfaces.

### 1.2 Profile Scope

**Profile A only.** Profile B (daily) and Profile C (weekly) do not naturally support intraday-tactical management. If intraday-tactical management is desired on a Profile-B/C-flagged ticker, the Operator runs Profile A on the same ticker.

The `intraday_tactical` top-level group is absent from Profile B and Profile C outputs entirely (NOT null-emitted; structurally absent — same convention as Profile-A-only `floor_analysis.macro_frame` per WKC-001).

### 1.3 v1.0 Scope Boundaries

**In scope (v1.0):**
- Feature C: `GAP` + `VOL_EXPANSION` event detection
- Feature D: compression-shelf detection (4–10 hourly bar sliding window, 0.5× Daily ATR tightness)
- Tactical stop: dual methodology (`shelf_structural` + `atr_volatility`)
- Near-term target: 3-mode by shelf `position` (`ABOVE` / `BELOW` / `WITHIN`)
- Output payload: Option α (separate `tactical_stop` + `near_term_target` sub-objects)
- Per-field `lookback_stale` annotation on three short-window fields
- Summary section `intraday_tactical.lookback_status`

**Out of scope — deferred to v1.1 (logged as design-input items + Bug Register CONCEPT entries):**
- Opening-range shelf (Raschke/Williams ORB tradition) — would add a parallel `intraday_tactical.opening_range` block
- AVWAP-pinch shelf (Shannon tradition) — already implicitly covered by AVWAP-001 + CFL-001 swing layer
- Range-break event detection (DQ-5a v1.0 minimization)
- Volume confirmation on shelf (RVOL ≤ 0.8× dry-up gate — DQ-3b v1.0 minimization)
- `NEAR_UPPER` / `NEAR_LOWER` fine-geometry labels — DQ-3d v1.0 minimization
- `avwap_anchored` / `signal_bar` / trailing-stop variants — DQ-4a v1.0 minimization
- AVWAP-intersection targets, R-multiple targets, Bollinger band targets — DQ-4c v1.0 minimization
- Cross-surface confluence with CFL-001 — DQ-6 v1.0 minimization (logged as `INTRADAY-CFL-INTEGRATION-1` CONCEPT)
- 15-minute bar-frame promotion — DQ bar-frame v1.0 minimization
- Prior-session shelves (cross-session lookback) — DQ-3c v1.0 minimization
- Explicit `relative_to_structural_floor` annotation — DQ-6c v1.0 minimization
- Profile B / Profile C extension — §1.2 scope lock

### 1.4 Non-Goals

- ITS does **NOT** participate in any swing-frame gate. No gate function (`gates.py`) reads any `Intraday_*` flat key or `ctx._intraday_*` attribute. Verdict-invariance is a closure criterion (§7).
- ITS is **NOT** an entry recommendation system. Per DQ-2 §2 (semantic neutrality lock), the surface provides levels — the Operator decides whether to act.
- ITS does **NOT** participate in the BUGR-002 partition (DQ-6 — parallel surfaces in v1.0). Cross-surface confluence with CFL-001 is a v1.1 candidate.
- ITS does **NOT** mandate Operator action when `lookback_stale: true` — the flag is operator-facing transparency, not a verdict modifier.

---

## 2. Architectural Model

This section transcribes the 14 locked sub-DQs from Phase 0 WIP v0.3 §4 with source-evidence citations for §11.6 traceability. Each DQ is the canonical decision lock; implementation MUST conform.

### 2.1 DQ-1a — Feature C location (LOCKED Session 1)

**Hybrid:**
- Per-field `lookback_stale: bool` annotation on three short-window fields:
  - `floor_analysis.hierarchy[label=ESTABLISHED_LOW].lookback_stale`
  - `target.hierarchy[label=DAILY_HIGH].lookback_stale` (the 10-bar resistance — see §3.4 for label-vocabulary clarification)
  - `floor_analysis.avwap_10bar.lookback_stale` (if AVWAP-001 surfaces an `AVWAP_10BAR` sub-object — see §11 audit item)
- Summary section `intraday_tactical.lookback_status` (shape defined in §2.4 DQ-5d)

Precedent: mirrors `volatility_regime` caution_factor convention (top-level + field-level dual surface).

### 2.2 DQ-1b — Feature D location (LOCKED Session 1)

**New top-level group `intraday_tactical`**, sibling to existing top-level groups. Follows OTL-001 concept-grouped JSON convention.

The exact set of existing top-level groups at engine-current state (verified via `transform.py` module docstring + `_transform_output` body inspection) includes: `action_summary`, `trade_snapshot`, `trade_quality`, `trade_risk`, `trend_state`, `floor_analysis`, `trade_setup`, `extension_analysis`, `psychological_levels`, `volatility_regime`, `rally_state`, `entry_proximity`, `exit_signals`, `recovery_analysis`, `swing_breakout_confirmation`, `_debug` (debug-mode only).

`intraday_tactical` slots in the reading order **after** `swing_breakout_confirmation` and **before** `_debug`. Profile-A-only by §1.2; absent on Profile B/C outputs.

### 2.3 DQ-2 — Verdict scope (LOCKED Session 1)

**Emit `intraday_tactical` group on ALL Profile A paths regardless of swing verdict.**

Operational consequences:
- The group emits on `VALID`, `WAIT`, `INVALID`, `RECOVERY CANDIDATE`, and `ERROR` (data-availability permitting on ERROR) verdicts.
- All compute helpers run pre-gate (per §5 Pipeline & Call-Order), so the data is available regardless of which `_assemble_output` early-return path the engine follows.
- Sub-decisions deferred to spec (resolved here):
  1. **Graceful degradation when no shelf detected:** `shelf.detected: false` framing, not null sub-fields. (§3.2 shelf payload.)
  2. **Semantic neutrality:** surface provides levels, does NOT imply entry recommendation. No `recommendation` / `signal` field; the Operator interprets `position` + `tactical_stop` + `near_term_target` themselves.
  3. **Cross-reference to swing verdict:** no `swing_context_note` field. The Operator reads `action_summary.verdict` directly.

### 2.4 DQ-5a/b/c/d — Regime-shift event detection (LOCKED Session 2)

#### 2.4.1 DQ-5a — Event types

Two primary event types in v1.0:
- `GAP_UP` — close-to-open or open-to-current price discontinuity above threshold, direction up
- `GAP_DOWN` — same as `GAP_UP` but direction down
- `VOL_EXPANSION` — sudden Fast-ATR / Slow-ATR ratio shift without literal gap
- `MULTIPLE` — when both a GAP and a VOL_EXPANSION fire on the same bar
- `null` — no event detected

Range-break detection is deferred to v1.1. Breakaway/runaway/exhaustion classification is excluded (would require subsequent price action to confirm).

#### 2.4.2 DQ-5b — Quantitative thresholds

```
GAP detection:
  gap_pct = abs(open - prior_close) / prior_close  (or current_price - prior_close for the in-progress bar)
  gap_atr = abs(open - prior_close) / Daily_ATR
  GAP fires when:
    gap_pct >= max(INTRADAY_GAP_PCT_FLOOR, INTRADAY_GAP_ATR_MULT * Daily_ATR / prior_close)
    AND bar_rvol >= INTRADAY_GAP_RVOL_THRESHOLD

VOL_EXPANSION detection (intraday, no gap):
  fast_atr = ATR over INTRADAY_VOL_EXPANSION_FAST_BARS hourly bars (5)
  slow_atr = ATR over INTRADAY_VOL_EXPANSION_SLOW_BARS hourly bars (20)
  expansion_ratio = fast_atr / slow_atr
  VOL_EXPANSION fires when:
    expansion_ratio >= INTRADAY_VOL_EXPANSION_RATIO_THRESHOLD (1.5)
    AND bar_rvol >= INTRADAY_GAP_RVOL_THRESHOLD (2.0)
```

Both criteria are independently sufficient — either fires the flag. When both fire on the same bar, `event_type = "MULTIPLE"`.

**Constants (compute.py module-level, per BRK-001/RLY-001 pattern):**
```python
INTRADAY_GAP_PCT_FLOOR = 0.04           # 4% — gap-and-go practitioner convention
INTRADAY_GAP_ATR_MULT = 1.5             # 1.5× Daily ATR — TradingView Unfilled Gap Detector convention
INTRADAY_GAP_RVOL_THRESHOLD = 2.0       # 2× — gap-and-go RVOL convention
INTRADAY_VOL_EXPANSION_FAST_BARS = 5    # 5 hourly bars
INTRADAY_VOL_EXPANSION_SLOW_BARS = 20   # 20 hourly bars
INTRADAY_VOL_EXPANSION_RATIO_THRESHOLD = 1.5  # TradingView Volatility Gated Supertrend convention
```

Large-cap exception (2% gap threshold for high-institutional-participation names) is **deferred to live validation**, NOT locked at v1.0. Calibration follow-up `INTRADAY-CAL-1` covers this and other multiplier reviews.

#### 2.4.3 DQ-5c — Detection architecture

**Per-field-aware global detection:**
- Event detection runs ONCE globally per Profile A invocation (in compute.py)
- Flag applied per-field based on whether the field's lookback window OVERLAPS the detected event timestamp
- Short-window fields (≤10 bars: ESTABLISHED_LOW, resistance, AVWAP_10BAR) flag readily when event within last 10 bars
- Medium-window fields (~21 bars: EMA_21) — **not annotated in v1.0** (deferred to v1.1 if Operator demand surfaces)
- Long-window fields (Daily SMA50/200, weekly anchors) — **not annotated in v1.0** (built-in regime tolerance from long lookback dwarfs single-event impact)

Algorithm: for each event detected, `event_bars_ago` (in PRIMARY-frame hourly bars) is computed. A field's lookback window is "stale" iff `event_bars_ago < field.lookback_window_bars`. The three v1.0-annotated fields all have `lookback_window_bars = 10`, so the per-field `lookback_stale` flag is identical for all three when triggered. (This is a v1.0 simplification — v1.1 may diverge per-field if Operator demand warrants.)

#### 2.4.4 DQ-5d — Event type classification surfaced (top-level `lookback_status` shape)

```json
"lookback_status": {
  "stale": true,
  "event_type": "GAP_UP|GAP_DOWN|VOL_EXPANSION|MULTIPLE|null",
  "event_timestamp": "ISO-8601 timestamp of event bar",
  "event_bars_ago": int,
  "event_magnitude_pct": float,
  "event_magnitude_atr": float,
  "rvol_at_event": float,
  "affected_fields": ["floor_analysis.hierarchy[ESTABLISHED_LOW]", "target.hierarchy[DAILY_HIGH]", ...]
}
```

When no event is detected, the block is:
```json
"lookback_status": {
  "stale": false,
  "event_type": null,
  "event_timestamp": null,
  "event_bars_ago": null,
  "event_magnitude_pct": null,
  "event_magnitude_atr": null,
  "rvol_at_event": null,
  "affected_fields": []
}
```

The block is ALWAYS emitted on Profile A (DQ-2 lock). `affected_fields` is a string-array of dotted-path field references; empty array on no-event paths.

### 2.5 DQ-3a/b/c/d — Compression-shelf detection (LOCKED Session 3)

#### 2.5.1 DQ-3a — Shelf definitional criteria

A shelf is a band on Profile A's hourly bars where:
- Over the most recent **N consecutive bars** (4 ≤ N ≤ 10),
- The total bar range is tight relative to Daily ATR: `(HH_N − LL_N) ≤ Daily_ATR × INTRADAY_SHELF_TIGHTNESS_ATR_MULT`,
- The shelf has explicit `upper` bound (HH_N) and `lower` bound (LL_N),
- The shelf is **active** until a subsequent hourly bar closes outside `[lower, upper]`.

Algorithmic template: LuxAlgo Range Intelligence Suite (TradingView canonical) + ActiveQuants Consolidation Zones (SMA-anchored variant) + Pineify Consolidation Range Detector. Bar-frame agnostic — TBS uses hourly per Profile A's existing data layer.

#### 2.5.2 DQ-3b — Quantitative thresholds + sliding detection

```
For N in [INTRADAY_SHELF_MIN_BARS .. INTRADAY_SHELF_MAX_BARS]:  # 4..10
  HH_N = max(df['high'].iloc[-(N+1):-1])  # excludes evaluated bar per existing convention
  LL_N = min(df['low'].iloc[-(N+1):-1])
  width = HH_N - LL_N
  tightness = width / Daily_ATR
  IF tightness <= INTRADAY_SHELF_TIGHTNESS_ATR_MULT:
    qualifying_shelves.append({N, HH_N, LL_N, tightness})

IF qualifying_shelves is non-empty:
  shelf = max(qualifying_shelves, key=lambda s: s['N'])  # largest N — favors stability
ELSE:
  shelf = None  # shelf.detected: false
```

**Constants:**
```python
INTRADAY_SHELF_MIN_BARS = 4             # Raschke 3-bar triangle floor + 1 validation
INTRADAY_SHELF_MAX_BARS = 10            # Matches TBS PA-001/AVWAP-001 ESTABLISHED_LOW lookback
INTRADAY_SHELF_TIGHTNESS_ATR_MULT = 0.5 # 0.5× Daily ATR — practitioner-tight (Pineify 0.3–1.5%; on Profile A's universe with Daily ATR 1.5–4% of price, 0.5× = 0.75–2% width)
```

**Volume confirmation** (RVOL ≤ 0.8× dry-up gate) is deferred to v1.1 — would add noise filtering at the cost of additional firing-rate noise.

**Bar-window convention:** `iloc[-(N+1):-1]` matches the existing Profile A convention from compute.py `_compute_early_capital_rr` L670 (`df_ctx['high'].iloc[-11:-1].max()` for the 10-bar daily ceiling). The evaluated bar is EXCLUDED from the shelf window — same convention. This is consistent with the FSLR observation source-verification finding (Phase 0 WIP §3.3 §3.4 item 5): TBS resistance uses `df_ctx['high'].iloc[-11:-1].max()` which by design excludes the current (in-progress or just-completed) bar. Shelf detection uses the same convention.

#### 2.5.3 DQ-3c — Lookback scope

- **Current Profile A hourly buffer only** (TBS pulls 21+ hourly bars per PA-001).
- Sliding window `INTRADAY_SHELF_MIN_BARS ≤ N ≤ INTRADAY_SHELF_MAX_BARS`, ending at the bar just before the evaluated bar.
- **No cross-session segmentation in v1.0** — overnight gaps are handled by Feature C `lookback_stale` flag.
- **No prior-session shelves in v1.0** — defer to v1.1.

#### 2.5.4 DQ-3d — Shelf classification surfaced (`position` field)

Field name: **`position`** — three labels:
- **`ABOVE`** — current price > shelf `upper` (shelf below current price; acts as support; fade-to-shelf entry context)
- **`BELOW`** — current price < shelf `lower` (shelf above current price; acts as resistance; breakout-from-shelf entry context)
- **`WITHIN`** — current price ∈ `[lower, upper]` (in-band; directionally neutral)

Directionally neutral by design (DQ-2 §2 lock).

**Expected `intraday_tactical.shelf` payload (v1.0):**

When shelf detected:
```json
"shelf": {
  "detected": true,
  "upper": float,
  "lower": float,
  "bar_count": int,
  "tightness_ratio": float,
  "position": "ABOVE|BELOW|WITHIN",
  "lookback_stale": bool,
  "desc": "Compression shelf detected over N hourly bars; tightness X.XX× Daily ATR; position: ABOVE/BELOW/WITHIN current price."
}
```

When no shelf:
```json
"shelf": {
  "detected": false,
  "desc": "No qualifying compression shelf detected (no 4–10 bar window with width <= 0.5× Daily ATR)."
}
```

### 2.6 DQ-6 — CFL-001 relationship (LOCKED Session 3)

**Parallel surfaces in v1.0; no CFL-001 feed.**

- `intraday_tactical` lives independently from `target.hierarchy` and `floor_analysis.hierarchy`.
- Shelf upper / lower bounds do NOT participate in the BUGR-002 partition.
- CFL-001 runs unchanged on its existing inputs.
- Cross-surface confluence noticed manually by the Operator in v1.0.
- v1.1 promotion via `INTRADAY-CFL-INTEGRATION-1` CONCEPT entry.

**v1.0 isolation rationale:**
1. Consistent with v1.0 minimization pattern (DQ-5a / DQ-3a / DQ-3b deferrals).
2. CFL-001 recently shipped (S157) — cross-surface integration would alter CFL-001 firing rates, requiring re-validation matching the SIR §11.6 ANALYST-class incident pattern (CFL-001-SPEC-1, RLY-001-SPEC-1/2/3, RLC-001-SPEC-1/2) the codification was designed to prevent.
3. Operator can still cross-reference manually in v1.0; loss of automated `confluence` label is a UX cost, not a capability gap.

### 2.7 DQ-4a/b/c/d — Tactical stop + near-term target (LOCKED Session 4)

#### 2.7.1 DQ-4a — Stop placement methodology (dual)

v1.0 emits TWO complementary stop methodologies in parallel under `tactical_stop`:

1. **`shelf_structural`** — anchored to the shelf `lower` / `upper` bound (DQ-3a/d lock); methodology native to the shelf the surface already detects. Primary candidate when `shelf.detected: true`.
2. **`atr_volatility`** — ATR-multiple distance from current price; bar-frame-agnostic; provides a fallback when `shelf.detected: false`, and a parallel alternate when shelf IS detected.

Single-methodology lock was rejected because the `shelf.detected: false` case would leave `tactical_stop` empty — degrading surface utility when shelf detection misses.

#### 2.7.2 DQ-4b — Quantitative stop thresholds

**`shelf_structural` thresholds** (anchored to shelf bounds; buffer applied outside the bound):

| Shelf `position` | Entry context (informational) | Stop derivation |
|---|---|---|
| `ABOVE` | Fade-to-shelf: long off bounce | `Stop = shelf.lower − INTRADAY_STOP_FADE_ATR_MULT × Hourly_ATR` |
| `BELOW` | Breakout-from-shelf: long on break above upper | `Stop = shelf.upper − INTRADAY_STOP_BREAKOUT_ATR_MULT × Hourly_ATR` (just INSIDE the broken bound — wholesale failure if price re-enters) |
| `WITHIN` | Directionally neutral | Emit BOTH alternates: `fade_to_upper.price` and `breakout_above.price` under `shelf_structural` |

**`atr_volatility` threshold** (bar-frame-agnostic; ATR-multiple from current price):
```
atr_volatility.price = current_price − INTRADAY_STOP_VOL_ATR_MULT × Hourly_ATR
```

**Constants:**
```python
INTRADAY_STOP_FADE_ATR_MULT = 0.4       # Nordfx fade-shelf 0.3–0.5× band midpoint
INTRADAY_STOP_BREAKOUT_ATR_MULT = 0.3   # Nordfx breakout-shelf 0.2–0.4× band midpoint
INTRADAY_STOP_VOL_ATR_MULT = 1.5        # LeBeau Chandelier shorter-term variant (1.5× for sub-daily bar-frames)
```

**Hourly_ATR sourcing:** Profile A's primary-frame ATR is `state.atr_raw` per main.py and compute.py — this IS the hourly ATR for Profile A (compute.py confirms: "Profile A: state.atr_raw is hourly ATR"). Implementation reads from `ctx.state.atr_raw`.

**Position-sizing implication (informational, not gated):** Van Tharp R-framework. Stop distance defines 1R; position size derived to keep 1R ≈ 1% of account equity (max 2%). Tactical stop being tighter than swing stop allows larger Profile-A intraday position sizes at the same account-risk-per-trade. The engine emits stop and target as raw levels; sizing is Operator / Portfolio Governor concern (Doc 3 scope).

#### 2.7.3 DQ-4c — Near-term target derivation (3-mode by shelf position)

| Shelf `position` | `primary` target | `secondary` target | Rationale |
|---|---|---|---|
| `ABOVE` (long bias; price extended above shelf) | `intraday_high` (today's session high) | `intraday_high + (shelf.upper − shelf.lower)` | Raschke prior-session H/L convention adapted to intraday. Shelf-width measured-move per Nordfx range-projection. |
| `BELOW` (long bias; breakout-from-shelf) | `shelf.upper + (shelf.upper − shelf.lower)` | `primary + 1.5 × (shelf.upper − shelf.lower)` | Nordfx range-breakout convention: first target = opposite-side projection; extended = range-multiple. |
| `WITHIN` (directionally neutral) | `null`, `applicable: false` | `null`, `applicable: false` | Per DQ-2 §2 semantic-neutrality lock — emitting directional targets would imply entry recommendation. Operator computes mid-range / boundary targets manually from `upper` / `lower`. |

**`intraday_high` derivation** (NEW — not currently in engine):

```python
def _derive_intraday_high(df):
    """Returns the max of df['high'] across hourly bars belonging to today's session.
    'Today' = the calendar date of the most recent bar in df (df.index[-1].date()).
    Includes the evaluated bar (-1) — this is the IN-PROGRESS or just-completed bar's high.
    Distinct from the existing resistance_raw convention which EXCLUDES the evaluated bar
    by design (compute.py L670 + data.py PE-43 documentation).

    Requires df.index to be a pandas DatetimeIndex (standard IBKR convention for
    hourly bars). DatetimeIndex.date returns a numpy array of datetime.date
    objects; element-wise comparison with a single datetime.date produces the
    boolean mask directly.
    """
    if df is None or len(df) == 0:
        return None
    last_date = df.index[-1].date()
    same_day_mask = df.index.date == last_date
    same_day_bars = df[same_day_mask]
    if len(same_day_bars) == 0:
        return None
    return float(same_day_bars['high'].max())
```

**Critical convention distinction:** `intraday_high` INCLUDES the evaluated bar (max over current session bars). `resistance_raw` EXCLUDES the evaluated bar (10-bar daily window over `df_ctx['high'].iloc[-11:-1]`). These are intentionally different — they answer different operational questions. The FSLR Phase 0 observation (TBS resistance $257.92 vs actual day-high $259.12) is correct behavior of `resistance_raw`, NOT a defect.

#### 2.7.4 DQ-4d — Output payload structure (Option α: separate sub-objects)

```json
"intraday_tactical": {
  "shelf": { /* DQ-3d locked shape — see §2.5.4 */ },
  "lookback_status": { /* DQ-5d locked shape — see §2.4.4 */ },
  "tactical_stop": {
    "shelf_structural": {
      "price": float | { "fade_to_upper": float, "breakout_above": float },   /* dict form on WITHIN */
      "anchor": "shelf_lower | shelf_upper | both",
      "atr_buffer_mult": 0.4 | 0.3,
      "atr_value_used": float,
      "desc": str
    } | null,                                                                  /* null when shelf.detected: false */
    "atr_volatility": {
      "price": float,
      "atr_mult": 1.5,
      "atr_value_used": float,
      "desc": str
    }
  },
  "near_term_target": {
    "mode": "ABOVE | BELOW | WITHIN",
    "primary": {
      "price": float | null,
      "source": "INTRADAY_HIGH | SHELF_UPPER_PROJECTION | NOT_APPLICABLE",
      "desc": str
    },
    "secondary": {
      "price": float | null,
      "source": "SHELF_WIDTH_PROJECTION | EXTENDED_RANGE_PROJECTION | NOT_APPLICABLE",
      "desc": str
    },
    "applicable": bool
  }
}
```

**Rationale for Option α (separate sub-objects) over Option β (combined `tactical_plan` block):**
1. Architectural consistency with TBS output schema — `target.hierarchy` and `floor_analysis.hierarchy` already live as separate concept groups per OTL-001 / BUGR-002.
2. R:R computation deferred — combined `tactical_plan.rr` would force the engine to assume a chosen entry price the surface doesn't define (semantic-neutrality lock).
3. Graceful degradation — `tactical_stop` and `near_term_target` can independently null/applicable; combined block forces both-or-nothing.
4. Cross-reference symmetry — `shelf` + `lookback_status` + `tactical_stop` + `near_term_target` = four sub-objects at the same nesting depth; flat hierarchy is more searchable than nested `tactical_plan.{stop,target}`.

### 2.8 DQ-7 — Profile scoping (LOCKED Session 1)

Profile A only. Reaffirmed in §1.2.

---

## 3. Label-Vocabulary Collision Audit

Per §11.6 item 6 (cross-spec layout audit) — applied to label tokens, since the new top-level group introduces a new label-vocabulary set.

### 3.1 New labels introduced

- `intraday_tactical` (top-level group key)
- `shelf` (sub-object key)
- `lookback_status` (sub-object key)
- `lookback_stale` (boolean field on annotated hierarchy entries)
- `tactical_stop` (sub-object key)
- `near_term_target` (sub-object key)
- `shelf_structural` (stop methodology label)
- `atr_volatility` (stop methodology label)
- `ABOVE` / `BELOW` / `WITHIN` (shelf position values)
- `GAP_UP` / `GAP_DOWN` / `VOL_EXPANSION` / `MULTIPLE` (event_type values)
- `INTRADAY_HIGH` / `SHELF_UPPER_PROJECTION` / `SHELF_WIDTH_PROJECTION` / `EXTENDED_RANGE_PROJECTION` / `NOT_APPLICABLE` (target source labels)
- `anchor` field with values `shelf_lower` / `shelf_upper` / `both`

### 3.2 Collision audit results

Comparison performed against engine canonical vocabularies (Doc 2 §IV Output Schema, Doc 8 §II Layer 2, transform.py `_CONVICTION_TIER_MAP`, gates.py vocabulary, output.py vocabulary):

- `intraday_tactical` — **No collision.** Sibling to existing 15 top-level groups.
- `shelf` — **No collision.** Standard geometric vocabulary; no TBS-existing usage.
- `lookback_stale` — **No collision.** Mirrors RWD-001's `_rwd001_*` and IVR-001's `volatility_regime.context_interpretation` precedent of per-feature stale/state flags.
- `tactical_stop` — **No collision.** `stop` exists as top-level group; `tactical_` prefix disambiguates.
- `near_term_target` — **No collision.** `target` exists as top-level group; `near_term_` prefix disambiguates.
- `shelf_structural` / `atr_volatility` — **No collision.** Distinct from existing stop-anchor labels (`DAILY_HARD_STOP`, `NEW_SUPPORT`, `TIGHT_STOP`, `CATASTROPHIC_STOP`).
- `ABOVE` / `BELOW` / `WITHIN` — **Single-shared-vocabulary scope.** Used as values on `shelf.position` AND `near_term_target.mode`. No collision with existing TBS labels (existing `position` field on `volume_at_price` uses `ABOVE_POC` / `BELOW_POC` / `AT_POC` — different value space).
- `GAP_UP` / `GAP_DOWN` / `VOL_EXPANSION` / `MULTIPLE` — **No collision.** Distinct from existing event-type vocabularies.
- `INTRADAY_HIGH` / `SHELF_UPPER_PROJECTION` / `SHELF_WIDTH_PROJECTION` / `EXTENDED_RANGE_PROJECTION` / `NOT_APPLICABLE` — **No collision with `_CONVICTION_TIER_MAP`** (verified against transform.py L213-241 conviction-tier dict). These labels are target-source labels; CNV-001 tier mapping only labels existing hierarchy entries — new target sources outside the hierarchy don't need tier mapping in v1.0 (deferred to v1.1 if shelves promote to hierarchies via `INTRADAY-CFL-INTEGRATION-1`).
- `anchor` values `shelf_lower` / `shelf_upper` / `both` — **No collision.** Distinct from existing anchor field usage in `psychological_levels.psych_floor.anchor` etc.

### 3.3 v1.1 label-pre-commit register

Provisional v1.1 labels flagged for re-audit at v1.1 spec authoring (NOT used in v1.0):
- `INTRADAY_SHELF_UPPER` / `INTRADAY_SHELF_LOWER` — hierarchy-entry labels for `INTRADAY-CFL-INTEGRATION-1` v1.1 promotion. Re-audit against `floor_analysis.hierarchy` / `target.hierarchy` label set at v1.1 spec authoring.

### 3.4 Hierarchy-label alignment for `lookback_stale` annotation

DQ-1a §2.1 references three short-window field annotations:
- `floor_analysis.hierarchy[label=ESTABLISHED_LOW].lookback_stale` — `ESTABLISHED_LOW` is a STRUCTURAL tier label per `_CONVICTION_TIER_MAP` L218.
- `target.hierarchy[label=DAILY_HIGH].lookback_stale` — `DAILY_HIGH` is a STRUCTURAL tier label per `_CONVICTION_TIER_MAP` L219. This corresponds to the 10-bar daily-frame resistance.
- `floor_analysis.avwap_10bar.lookback_stale` (if a 10-bar AVWAP sub-object exists per AVWAP-001) — verified against AVWAP-001 spec at Phase 2 entry (open §11 audit item; if no such sub-object surfaces, this annotation is dropped from v1.0).

---

## 4. Implementation Specification

### 4.1 compute.py — Event Detection Helper

**Module-level constants** (insert near existing `RLY_*` / `BRK_*` constants, ~L13–L30):

```python
# ======================================================================
# ITS-001: Intraday-Tactical Surface Constants (Profile A)
# Phase 1 spec: ITS001_Intraday_Tactical_Surface_Spec_v1_0.md §2.4–§2.7
# Calibration candidates: INTRADAY-CAL-1, INTRADAY-CAL-2 (Bug Register CONCEPT).
# ======================================================================
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

**Helper signature:**

```python
def _detect_intraday_events(ctx):
    """ITS-001: Detect GAP / VOL_EXPANSION events on Profile A hourly frame.

    Runs ONCE globally per Profile A invocation (DQ-5c lock).
    Writes ctx._intraday_event_type, ctx._intraday_event_timestamp,
    ctx._intraday_event_bars_ago, ctx._intraday_event_magnitude_pct,
    ctx._intraday_event_magnitude_atr, ctx._intraday_event_rvol.

    Defensive null path: returns early when ctx.p_code != "A" or df has
    insufficient bars (< max(INTRADAY_VOL_EXPANSION_SLOW_BARS, 2)).
    All event attributes set to None on defensive paths.

    Spec: §2.4.
    """
    # Set defaults
    ctx._intraday_event_type = None
    ctx._intraday_event_timestamp = None
    ctx._intraday_event_bars_ago = None
    ctx._intraday_event_magnitude_pct = None
    ctx._intraday_event_magnitude_atr = None
    ctx._intraday_event_rvol = None

    if ctx.p_code != "A":
        return
    if ctx.df is None or len(ctx.df) < INTRADAY_VOL_EXPANSION_SLOW_BARS:
        return

    df = ctx.df
    state = ctx.state
    daily_atr = getattr(ctx, 'daily_atr', 0.0) or 0.0

    # Scan recent bars for the most recent event within 10-bar window
    # (sufficient coverage for all v1.0-annotated short-window fields).
    scan_window = min(INTRADAY_SHELF_MAX_BARS, len(df) - 1)
    detected = []  # list of (bars_ago, event_type, magnitudes)

    for offset in range(0, scan_window):
        bar_idx = len(df) - 1 - offset
        if bar_idx <= 0:
            break
        bar = df.iloc[bar_idx]
        prior_bar = df.iloc[bar_idx - 1]
        prior_close = prior_bar['close']

        # GAP detection
        gap_abs = bar['open'] - prior_close
        gap_pct = abs(gap_abs) / prior_close if prior_close > 0 else 0.0
        gap_atr = abs(gap_abs) / daily_atr if daily_atr > 0 else 0.0
        bar_rvol_denom = bar.get('vol_sma_20', 0)
        bar_rvol = float(bar['volume']) / float(bar_rvol_denom) if bar_rvol_denom and bar_rvol_denom > 0 else 0.0

        gap_threshold_pct = max(INTRADAY_GAP_PCT_FLOOR,
                                INTRADAY_GAP_ATR_MULT * daily_atr / prior_close if prior_close > 0 else INTRADAY_GAP_PCT_FLOOR)
        is_gap = (gap_pct >= gap_threshold_pct) and (bar_rvol >= INTRADAY_GAP_RVOL_THRESHOLD)
        gap_type = ("GAP_UP" if gap_abs > 0 else "GAP_DOWN") if is_gap else None

        # VOL_EXPANSION detection
        fast_window = df.iloc[max(0, bar_idx - INTRADAY_VOL_EXPANSION_FAST_BARS):bar_idx + 1]
        slow_window = df.iloc[max(0, bar_idx - INTRADAY_VOL_EXPANSION_SLOW_BARS):bar_idx + 1]
        fast_atr = (fast_window['high'] - fast_window['low']).mean() if len(fast_window) > 0 else 0.0
        slow_atr = (slow_window['high'] - slow_window['low']).mean() if len(slow_window) > 0 else 0.0
        expansion_ratio = fast_atr / slow_atr if slow_atr > 0 else 0.0
        is_vol_expansion = (expansion_ratio >= INTRADAY_VOL_EXPANSION_RATIO_THRESHOLD
                            and bar_rvol >= INTRADAY_GAP_RVOL_THRESHOLD
                            and not is_gap)  # GAP takes precedence on same-bar

        if is_gap and is_vol_expansion:
            event_type = "MULTIPLE"
        elif is_gap:
            event_type = gap_type
        elif is_vol_expansion:
            event_type = "VOL_EXPANSION"
        else:
            continue

        detected.append({
            'bars_ago': offset,
            'event_type': event_type,
            'timestamp': bar.name if hasattr(bar, 'name') else None,
            'magnitude_pct': round(gap_pct, 4) if is_gap else None,
            'magnitude_atr': round(gap_atr, 2) if is_gap else None,
            'rvol': round(bar_rvol, 2),
        })

    if not detected:
        return

    # Take the MOST RECENT event (lowest bars_ago)
    event = min(detected, key=lambda e: e['bars_ago'])
    ctx._intraday_event_type = event['event_type']
    ctx._intraday_event_timestamp = event['timestamp']
    ctx._intraday_event_bars_ago = event['bars_ago']
    ctx._intraday_event_magnitude_pct = event['magnitude_pct']
    ctx._intraday_event_magnitude_atr = event['magnitude_atr']
    ctx._intraday_event_rvol = event['rvol']
```

### 4.2 compute.py — Shelf Detection Helper

```python
def _detect_compression_shelf(ctx):
    """ITS-001: Detect compression shelf on Profile A hourly bars per DQ-3a/b/c/d.

    Sliding window 4-10 bars; emits the largest-N qualifying shelf
    (favors stability per DQ-3b).

    Writes ctx._intraday_shelf_detected (bool),
    ctx._intraday_shelf_upper, ctx._intraday_shelf_lower,
    ctx._intraday_shelf_bar_count, ctx._intraday_shelf_tightness_ratio,
    ctx._intraday_shelf_position.

    Defensive null path: returns with shelf_detected=False when
    ctx.p_code != "A" or df has insufficient bars or Daily_ATR <= 0.

    Spec: §2.5.
    """
    ctx._intraday_shelf_detected = False
    ctx._intraday_shelf_upper = None
    ctx._intraday_shelf_lower = None
    ctx._intraday_shelf_bar_count = None
    ctx._intraday_shelf_tightness_ratio = None
    ctx._intraday_shelf_position = None

    if ctx.p_code != "A":
        return
    daily_atr = getattr(ctx, 'daily_atr', 0.0) or 0.0
    if ctx.df is None or daily_atr <= 0 or len(ctx.df) < INTRADAY_SHELF_MAX_BARS + 1:
        return

    df = ctx.df
    last = ctx.last
    qualifying = []

    for N in range(INTRADAY_SHELF_MIN_BARS, INTRADAY_SHELF_MAX_BARS + 1):
        # Match existing convention: exclude evaluated bar.
        # iloc[-(N+1):-1] gives N bars ending at the bar just before evaluated.
        window = df['high'].iloc[-(N + 1):-1]
        if len(window) < N:
            continue
        HH_N = float(df['high'].iloc[-(N + 1):-1].max())
        LL_N = float(df['low'].iloc[-(N + 1):-1].min())
        width = HH_N - LL_N
        tightness = width / daily_atr
        if tightness <= INTRADAY_SHELF_TIGHTNESS_ATR_MULT:
            qualifying.append({'N': N, 'upper': HH_N, 'lower': LL_N, 'tightness': tightness})

    if not qualifying:
        return

    # Largest N — favors stability (DQ-3b)
    shelf = max(qualifying, key=lambda s: s['N'])

    # Position relative to current price (evaluated bar close)
    current_price = float(last['close'])
    if current_price > shelf['upper']:
        position = "ABOVE"
    elif current_price < shelf['lower']:
        position = "BELOW"
    else:
        position = "WITHIN"

    ctx._intraday_shelf_detected = True
    ctx._intraday_shelf_upper = shelf['upper']
    ctx._intraday_shelf_lower = shelf['lower']
    ctx._intraday_shelf_bar_count = shelf['N']
    ctx._intraday_shelf_tightness_ratio = round(shelf['tightness'], 3)
    ctx._intraday_shelf_position = position
```

### 4.3 compute.py — Tactical Stop + Near-Term Target Helper

```python
def _compute_intraday_tactical_levels(ctx):
    """ITS-001: Compute tactical_stop + near_term_target from shelf state.

    Reads ctx._intraday_shelf_* (populated by _detect_compression_shelf).
    Writes ctx._intraday_tactical_stop_* and ctx._intraday_near_term_target_*
    attribute sets.

    Defensive null path: when shelf undetected, atr_volatility stop still
    emits (DQ-4a fallback); near_term_target defaults to applicable=False.

    Spec: §2.7.
    """
    # Defaults
    ctx._intraday_tactical_stop_shelf_structural = None
    ctx._intraday_tactical_stop_atr_volatility = None
    ctx._intraday_near_term_target_mode = None
    ctx._intraday_near_term_target_primary = None
    ctx._intraday_near_term_target_secondary = None
    ctx._intraday_near_term_target_applicable = False

    if ctx.p_code != "A":
        return
    if ctx.df is None or ctx.last is None:
        return

    state = ctx.state
    hourly_atr = state.atr_raw  # Profile A primary-frame ATR IS hourly per main.py
    current_price = float(ctx.last['close'])

    # --- atr_volatility stop (always available when hourly_atr > 0) ---
    if hourly_atr > 0:
        atr_vol_price = current_price - INTRADAY_STOP_VOL_ATR_MULT * hourly_atr
        ctx._intraday_tactical_stop_atr_volatility = {
            'price': round(atr_vol_price / ctx.price_scaler, 2),
            'atr_mult': INTRADAY_STOP_VOL_ATR_MULT,
            'atr_value_used': round(hourly_atr / ctx.price_scaler, 2),
        }

    # --- shelf_structural stop + near_term_target (shelf-detected paths only) ---
    if not ctx._intraday_shelf_detected:
        # No shelf — tactical_stop.shelf_structural stays None; near_term_target.applicable=False
        return

    shelf_upper = ctx._intraday_shelf_upper
    shelf_lower = ctx._intraday_shelf_lower
    shelf_width = shelf_upper - shelf_lower
    position = ctx._intraday_shelf_position

    if position == "ABOVE":
        # Fade-to-shelf: stop below shelf_lower
        sstop = shelf_lower - INTRADAY_STOP_FADE_ATR_MULT * hourly_atr
        ctx._intraday_tactical_stop_shelf_structural = {
            'price': round(sstop / ctx.price_scaler, 2),
            'anchor': 'shelf_lower',
            'atr_buffer_mult': INTRADAY_STOP_FADE_ATR_MULT,
            'atr_value_used': round(hourly_atr / ctx.price_scaler, 2),
        }
        # Near-term target: ABOVE mode
        intraday_high = _derive_intraday_high(ctx.df)
        if intraday_high is not None:
            primary_price = intraday_high
            secondary_price = intraday_high + shelf_width
            ctx._intraday_near_term_target_mode = "ABOVE"
            ctx._intraday_near_term_target_primary = {
                'price': round(primary_price / ctx.price_scaler, 2),
                'source': 'INTRADAY_HIGH',
            }
            ctx._intraday_near_term_target_secondary = {
                'price': round(secondary_price / ctx.price_scaler, 2),
                'source': 'SHELF_WIDTH_PROJECTION',
            }
            ctx._intraday_near_term_target_applicable = True

    elif position == "BELOW":
        # Breakout-from-shelf: stop just inside the broken upper bound
        sstop = shelf_upper - INTRADAY_STOP_BREAKOUT_ATR_MULT * hourly_atr
        ctx._intraday_tactical_stop_shelf_structural = {
            'price': round(sstop / ctx.price_scaler, 2),
            'anchor': 'shelf_upper',
            'atr_buffer_mult': INTRADAY_STOP_BREAKOUT_ATR_MULT,
            'atr_value_used': round(hourly_atr / ctx.price_scaler, 2),
        }
        # Near-term target: BELOW mode (breakout-up projection)
        primary_price = shelf_upper + shelf_width
        secondary_price = primary_price + (1.5 * shelf_width)
        ctx._intraday_near_term_target_mode = "BELOW"
        ctx._intraday_near_term_target_primary = {
            'price': round(primary_price / ctx.price_scaler, 2),
            'source': 'SHELF_UPPER_PROJECTION',
        }
        ctx._intraday_near_term_target_secondary = {
            'price': round(secondary_price / ctx.price_scaler, 2),
            'source': 'EXTENDED_RANGE_PROJECTION',
        }
        ctx._intraday_near_term_target_applicable = True

    elif position == "WITHIN":
        # Both stop alternates emitted; near_term_target inapplicable
        fade_stop = shelf_lower - INTRADAY_STOP_FADE_ATR_MULT * hourly_atr
        breakout_stop = shelf_upper - INTRADAY_STOP_BREAKOUT_ATR_MULT * hourly_atr
        ctx._intraday_tactical_stop_shelf_structural = {
            'price': {
                'fade_to_upper': round(fade_stop / ctx.price_scaler, 2),
                'breakout_above': round(breakout_stop / ctx.price_scaler, 2),
            },
            'anchor': 'both',
            'atr_buffer_mult': {'fade_to_upper': INTRADAY_STOP_FADE_ATR_MULT,
                               'breakout_above': INTRADAY_STOP_BREAKOUT_ATR_MULT},
            'atr_value_used': round(hourly_atr / ctx.price_scaler, 2),
        }
        ctx._intraday_near_term_target_mode = "WITHIN"
        # primary + secondary remain None (DQ-4c WITHIN mode lock)
        ctx._intraday_near_term_target_applicable = False


def _derive_intraday_high(df):
    """ITS-001: Today's session high from Profile A hourly buffer.

    INCLUDES the evaluated bar (distinct from resistance_raw which excludes).
    Requires df.index to be a pandas DatetimeIndex — standard IBKR hourly-bar
    convention. DatetimeIndex.date returns a numpy array of datetime.date
    objects; element-wise comparison with a single datetime.date yields the
    boolean mask directly.

    Spec: §2.7.3.
    """
    if df is None or len(df) == 0:
        return None
    try:
        last_date = df.index[-1].date()
        same_day_mask = df.index.date == last_date
        same_day_bars = df[same_day_mask]
        if len(same_day_bars) == 0:
            return None
        return float(same_day_bars['high'].max())
    except (AttributeError, TypeError):
        # Defensive: if df.index isn't a DatetimeIndex or .date attribute unavailable
        return None
```

### 4.4 compute.py — `__all__` Update

Append to existing `__all__` (compute.py L7):

```python
__all__ = [..., '_detect_intraday_events', '_detect_compression_shelf',
           '_compute_intraday_tactical_levels']
```

### 4.5 output.py — `_assemble_intraday_tactical` Helper

**Module-level constants** (NONE required — all calibration constants live in compute.py).

**Module-level null-flat-keys dict** (insert near existing `_RLY_NULL_FLAT_KEYS` at output.py ~L685):

```python
# ITS-001 null-flat-key dict for defensive paths (Profile B/C, ERROR paths)
_ITS_NULL_FLAT_KEYS = {
    "Intraday_Event_Type": None,
    "Intraday_Event_Bars_Ago": None,
    "Intraday_Event_Magnitude_Pct": None,
    "Intraday_Event_Magnitude_ATR": None,
    "Intraday_Event_RVOL": None,
    "Intraday_Shelf_Detected": None,
    "Intraday_Shelf_Upper": None,
    "Intraday_Shelf_Lower": None,
    "Intraday_Shelf_Bar_Count": None,
    "Intraday_Shelf_Tightness_Ratio": None,
    "Intraday_Shelf_Position": None,
    "Intraday_Stop_ATR_Volatility": None,
    "Intraday_Stop_Shelf_Structural": None,
    "Intraday_Target_Mode": None,
    "Intraday_Target_Primary": None,
    "Intraday_Target_Secondary": None,
    "Intraday_Target_Applicable": None,
    "Intraday_Lookback_Stale": None,
}
```

**Helper signature** (insert near existing `_assemble_rally_state` at output.py ~L705):

```python
def _assemble_intraday_tactical(ctx, p_code):
    """ITS-001: Assemble intraday_tactical top-level group + 18 flat keys.

    Returns (block, flat_keys_dict). Block is None on Profile B/C
    (group structurally absent). On Profile A:
    - block has shelf + lookback_status + tactical_stop + near_term_target sub-objects
    - flat_keys carry the same data in flattened form for transform-side reconstruction

    Reads ctx._intraday_* attributes populated by compute.py helpers
    (pre-gate call site per §5.1).

    Spec: §2 + §4.1–§4.3.
    """
    # Profile-A-scope guard — group structurally absent on Profile B/C
    if p_code != "A":
        return None, dict(_ITS_NULL_FLAT_KEYS)

    # --- Shelf sub-object ---
    shelf_detected = getattr(ctx, '_intraday_shelf_detected', False)
    if shelf_detected:
        # Per-field lookback_stale: shelf inherits from event detection
        # (shelf window <= 10 bars, so any event in last 10 bars makes shelf stale)
        event_bars_ago = getattr(ctx, '_intraday_event_bars_ago', None)
        shelf_lookback_stale = (event_bars_ago is not None
                                and event_bars_ago < ctx._intraday_shelf_bar_count)
        shelf_upper_display = round(ctx._intraday_shelf_upper / ctx.price_scaler, 2)
        shelf_lower_display = round(ctx._intraday_shelf_lower / ctx.price_scaler, 2)
        shelf_block = {
            "detected": True,
            "upper": shelf_upper_display,
            "lower": shelf_lower_display,
            "bar_count": ctx._intraday_shelf_bar_count,
            "tightness_ratio": ctx._intraday_shelf_tightness_ratio,
            "position": ctx._intraday_shelf_position,
            "lookback_stale": shelf_lookback_stale,
            "desc": (f"Compression shelf over {ctx._intraday_shelf_bar_count} hourly bars; "
                     f"width {ctx._intraday_shelf_tightness_ratio:.2f}x Daily ATR; "
                     f"position: {ctx._intraday_shelf_position}"
                     f"{' (LOOKBACK_STALE)' if shelf_lookback_stale else ''}."),
        }
    else:
        shelf_block = {
            "detected": False,
            "desc": "No qualifying compression shelf (no 4-10 bar window with width <= 0.5x Daily ATR).",
        }

    # --- lookback_status sub-object ---
    event_type = getattr(ctx, '_intraday_event_type', None)
    if event_type is not None:
        # Determine affected fields based on bars_ago + each field's lookback window
        affected_fields = []
        bars_ago = ctx._intraday_event_bars_ago
        if bars_ago is not None and bars_ago < 10:
            affected_fields.append("floor_analysis.hierarchy[ESTABLISHED_LOW]")
            affected_fields.append("target.hierarchy[DAILY_HIGH]")
            # AVWAP_10BAR conditional — only added if AVWAP-001 surfaces such a sub-object
            # (verified at Phase 2 entry per §11 audit item 3)
        lookback_status_block = {
            "stale": True,
            "event_type": event_type,
            "event_timestamp": (ctx._intraday_event_timestamp.isoformat()
                                if ctx._intraday_event_timestamp is not None
                                and hasattr(ctx._intraday_event_timestamp, 'isoformat')
                                else None),
            "event_bars_ago": ctx._intraday_event_bars_ago,
            "event_magnitude_pct": ctx._intraday_event_magnitude_pct,
            "event_magnitude_atr": ctx._intraday_event_magnitude_atr,
            "rvol_at_event": ctx._intraday_event_rvol,
            "affected_fields": affected_fields,
        }
    else:
        lookback_status_block = {
            "stale": False,
            "event_type": None,
            "event_timestamp": None,
            "event_bars_ago": None,
            "event_magnitude_pct": None,
            "event_magnitude_atr": None,
            "rvol_at_event": None,
            "affected_fields": [],
        }

    # --- tactical_stop sub-object ---
    tactical_stop_block = {
        "shelf_structural": getattr(ctx, '_intraday_tactical_stop_shelf_structural', None),
        "atr_volatility": getattr(ctx, '_intraday_tactical_stop_atr_volatility', None),
    }
    if tactical_stop_block["shelf_structural"] is not None:
        ss = tactical_stop_block["shelf_structural"]
        if isinstance(ss['price'], dict):
            ss['desc'] = (f"WITHIN-shelf stop alternates: fade_to_upper "
                          f"${ss['price']['fade_to_upper']}, breakout_above "
                          f"${ss['price']['breakout_above']}.")
        else:
            anchor_word = "below shelf lower" if ss['anchor'] == 'shelf_lower' else "inside shelf upper (breakout failure)"
            ss['desc'] = (f"Stop at ${ss['price']} ({ss['atr_buffer_mult']}x Hourly ATR "
                          f"{anchor_word}).")
    if tactical_stop_block["atr_volatility"] is not None:
        av = tactical_stop_block["atr_volatility"]
        av['desc'] = (f"Stop at ${av['price']} ({av['atr_mult']}x Hourly ATR "
                      f"from current price).")

    # --- near_term_target sub-object ---
    nt_mode = getattr(ctx, '_intraday_near_term_target_mode', None)
    nt_primary = getattr(ctx, '_intraday_near_term_target_primary', None)
    nt_secondary = getattr(ctx, '_intraday_near_term_target_secondary', None)
    nt_applicable = getattr(ctx, '_intraday_near_term_target_applicable', False)

    if nt_applicable and nt_primary is not None:
        nt_primary['desc'] = f"Primary target ${nt_primary['price']} ({nt_primary['source']})."
        nt_secondary['desc'] = f"Secondary target ${nt_secondary['price']} ({nt_secondary['source']})."
    near_term_target_block = {
        "mode": nt_mode,
        "primary": nt_primary if nt_primary is not None else {
            "price": None, "source": "NOT_APPLICABLE",
            "desc": "Directionally neutral (WITHIN shelf) — no primary target emitted."
        },
        "secondary": nt_secondary if nt_secondary is not None else {
            "price": None, "source": "NOT_APPLICABLE",
            "desc": "Directionally neutral (WITHIN shelf) — no secondary target emitted."
        },
        "applicable": nt_applicable,
    }

    # --- Assemble final block ---
    block = {
        "shelf": shelf_block,
        "lookback_status": lookback_status_block,
        "tactical_stop": tactical_stop_block,
        "near_term_target": near_term_target_block,
    }

    # --- Assemble flat keys (for transform.py registration + reconstruction) ---
    flat_keys = {
        "Intraday_Event_Type": event_type,
        "Intraday_Event_Bars_Ago": getattr(ctx, '_intraday_event_bars_ago', None),
        "Intraday_Event_Magnitude_Pct": getattr(ctx, '_intraday_event_magnitude_pct', None),
        "Intraday_Event_Magnitude_ATR": getattr(ctx, '_intraday_event_magnitude_atr', None),
        "Intraday_Event_RVOL": getattr(ctx, '_intraday_event_rvol', None),
        "Intraday_Shelf_Detected": shelf_detected,
        "Intraday_Shelf_Upper": (round(ctx._intraday_shelf_upper / ctx.price_scaler, 2)
                                  if shelf_detected else None),
        "Intraday_Shelf_Lower": (round(ctx._intraday_shelf_lower / ctx.price_scaler, 2)
                                  if shelf_detected else None),
        "Intraday_Shelf_Bar_Count": ctx._intraday_shelf_bar_count if shelf_detected else None,
        "Intraday_Shelf_Tightness_Ratio": ctx._intraday_shelf_tightness_ratio if shelf_detected else None,
        "Intraday_Shelf_Position": ctx._intraday_shelf_position if shelf_detected else None,
        "Intraday_Stop_ATR_Volatility": (tactical_stop_block['atr_volatility']['price']
                                          if tactical_stop_block['atr_volatility'] else None),
        "Intraday_Stop_Shelf_Structural": (tactical_stop_block['shelf_structural']['price']
                                            if tactical_stop_block['shelf_structural'] else None),
        "Intraday_Target_Mode": nt_mode,
        "Intraday_Target_Primary": nt_primary['price'] if nt_primary and nt_primary.get('price') is not None else None,
        "Intraday_Target_Secondary": nt_secondary['price'] if nt_secondary and nt_secondary.get('price') is not None else None,
        "Intraday_Target_Applicable": nt_applicable,
        "Intraday_Lookback_Stale": (event_type is not None),
    }

    return block, flat_keys
```

**Update `__all__` in output.py** (L33):
```python
__all__ = [..., '_assemble_intraday_tactical']
```

**Call site in `_assemble_output`** — INSERT after `_assemble_rally_state` call and BEFORE the `_transform_output` call. Reads the canonical (block, flat_keys) tuple per RLY-001 precedent:

```python
# --- ITS-001: Intraday-Tactical Surface assembly ---
_its_block, _its_flat_keys = _assemble_intraday_tactical(ctx, p_code)
metrics.update(_its_flat_keys)
# Stash block in metrics under a sentinel key for transform.py reconstruction
metrics["_intraday_tactical_block"] = _its_block
```

Implementation note: `_its_block` may be None on Profile B/C — transform.py reads the sentinel key and skips emission on None per §4.6.

### 4.6 transform.py — Flat-Key Registration + Top-Level Group Assembly

**1. Register flat keys in `_all_mapped_flat_keys()`** — add the 18 ITS flat keys to the registration function:

```python
def _all_mapped_flat_keys():
    keys = set()
    # ... existing registration ...
    # ITS-001: Intraday-Tactical Surface flat keys
    keys.update([
        "Intraday_Event_Type",
        "Intraday_Event_Bars_Ago",
        "Intraday_Event_Magnitude_Pct",
        "Intraday_Event_Magnitude_ATR",
        "Intraday_Event_RVOL",
        "Intraday_Shelf_Detected",
        "Intraday_Shelf_Upper",
        "Intraday_Shelf_Lower",
        "Intraday_Shelf_Bar_Count",
        "Intraday_Shelf_Tightness_Ratio",
        "Intraday_Shelf_Position",
        "Intraday_Stop_ATR_Volatility",
        "Intraday_Stop_Shelf_Structural",
        "Intraday_Target_Mode",
        "Intraday_Target_Primary",
        "Intraday_Target_Secondary",
        "Intraday_Target_Applicable",
        "Intraday_Lookback_Stale",
    ])
    return keys
```

**2. Top-level group emission in `_transform_output`** — read the sentinel key and emit on Profile A only:

```python
# Inside _transform_output(action_summary, flat_metrics, debug=False):
# Insert after rally_state emission, before _debug emission.

_its_block = flat_metrics.get("_intraday_tactical_block")
if _its_block is not None:  # None on Profile B/C
    output["intraday_tactical"] = _its_block
# Clean up the sentinel key — not surfaced externally
flat_metrics.pop("_intraday_tactical_block", None)
```

**3. Per-field `lookback_stale` annotation** — on Profile A, when `flat_metrics["Intraday_Lookback_Stale"] is True`, annotate the three specified hierarchy entries at the hierarchy-emission sites:

```python
# Inside the existing floor_analysis.hierarchy emission block:
if flat_metrics.get("Intraday_Lookback_Stale") is True:
    for entry in floor_hierarchy_entries:
        if entry.get("label") == "ESTABLISHED_LOW":
            entry["lookback_stale"] = True
        # Other entries: no annotation (long-window fields not annotated per DQ-5c)

# Inside the existing target.hierarchy emission block:
if flat_metrics.get("Intraday_Lookback_Stale") is True:
    for entry in target_hierarchy_entries:
        if entry.get("label") == "DAILY_HIGH":
            entry["lookback_stale"] = True
```

Implementation note: the exact entry-mutation sites in `_transform_output` are §11 audit items — the Phase 2 implementer must locate them via `file:line` evidence anchors before annotating. The mutation is benign (in-place dict update); BUGR-002 partition is post-annotation per CFL-001 precedent.

### 4.7 types.py — RunContext ctx Attribute Declarations

Add the following attribute declarations to `RunContext` dataclass (or equivalent), all defaulting to None:

```python
# ITS-001: Intraday-Tactical Surface (Profile A only; None on B/C)
_intraday_event_type: Optional[str] = None
_intraday_event_timestamp: Optional[Any] = None  # pandas Timestamp or None
_intraday_event_bars_ago: Optional[int] = None
_intraday_event_magnitude_pct: Optional[float] = None
_intraday_event_magnitude_atr: Optional[float] = None
_intraday_event_rvol: Optional[float] = None
_intraday_shelf_detected: bool = False
_intraday_shelf_upper: Optional[float] = None
_intraday_shelf_lower: Optional[float] = None
_intraday_shelf_bar_count: Optional[int] = None
_intraday_shelf_tightness_ratio: Optional[float] = None
_intraday_shelf_position: Optional[str] = None
_intraday_tactical_stop_shelf_structural: Optional[Dict] = None
_intraday_tactical_stop_atr_volatility: Optional[Dict] = None
_intraday_near_term_target_mode: Optional[str] = None
_intraday_near_term_target_primary: Optional[Dict] = None
_intraday_near_term_target_secondary: Optional[Dict] = None
_intraday_near_term_target_applicable: bool = False
```

(Existing precedent: `_rly_*` attributes in RunContext per RLY-001 spec.)

### 4.8 main.py — Call-Site Insertion

**Insertion site:** BETWEEN existing `_compute_volume_at_price(ctx)` and `_compute_rally_state_for_ctx(ctx)` calls (main.py ~L210–L215, after VOL-001 and before RLY-001).

```python
# --- [VOL-001] Volume-at-Price context computation ---
_compute_volume_at_price(ctx)

# --- [ITS-001] Intraday-Tactical Surface (Profile A only) ---
# Spec ITS001 §2.4 (DQ-5c "event detection runs once globally per Profile A invocation")
# + §2.5 (shelf detection) + §2.7 (tactical levels).
# Pre-gate placement ensures the data is available on ALL Profile A
# verdict paths (VS-06 guard early-return, recovery path early-returns,
# SBO pre-state mandatory-fail early-returns, standard cascade path).
_detect_intraday_events(ctx)
_detect_compression_shelf(ctx)
_compute_intraday_tactical_levels(ctx)

# --- [RLY-001] Rally state primitive (Spec §3.1, §4.1) ---
_compute_rally_state_for_ctx(ctx)
```

**Pre-state confirmation** (§11.6 item 4 — pipeline-order feasibility): All early-return `_assemble_output` sites in main.py (VS-06 C-3+A guard, recovery R-Gate path, SBO pre-state mandatory-fail) come AFTER L210 — so ITS data is on ctx for ALL paths. Verified at evidence-anchor `main.py:~L294-L385` (VS-06 + recovery + SBO blocks).

---

## 5. Pipeline & Call-Order Cascade

### 5.1 Tier mapping (per SIR §11.6 item 4 — pipeline-order feasibility check)

| Tier | Activity | Site (file:line approximate) | ITS Touch |
|---|---|---|---|
| 0 | Data fetch + indicator computation | data.py `_fetch_and_compute` | None |
| 1 | State classification | data.py `_classify_state` | None |
| 2 | RunContext construction | main.py `ctx = RunContext(...)` | ITS attrs default to None per §4.7 |
| 3 | Pre-gate computes | main.py L165–L215 | **ITS calls inserted at L213** |
| 4 | Profile A early branches | main.py L255–L290 (PA-001 daily protective values, etc.) | ITS already complete |
| 5 | Gate cascade | main.py L294–L380 | None (ITS does not gate-feed) |
| 6 | Trigger identification | main.py `_identify_trigger` | None |
| 7 | CQS-001 (VALID breakout paths) | main.py post-trigger | None |
| 8 | `_assemble_output` (Layer 5) | output.py | **`_assemble_intraday_tactical` called here**, flat keys merged into metrics, sentinel block stored under `_intraday_tactical_block` |
| 9 | `_transform_output` | transform.py | **Top-level `intraday_tactical` group emitted on Profile A; per-field `lookback_stale` annotated on 2 hierarchy entries** |

### 5.2 Storage-mechanism verification (§11.6 item 7)

Per RLC-001 v1.1 lesson and confirmed via transform.py module docstring inspection: `_transform_output(action_summary, flat_metrics, debug=False)` does NOT receive `ctx`. ITS uses the established RLY-001 pattern:
- compute.py writes ctx + (implicitly via `_assemble_intraday_tactical`) flat keys
- `_assemble_intraday_tactical(ctx, p_code)` in output.py returns `(block, flat_keys)` tuple
- `_assemble_output` merges `flat_keys` into `metrics` dict AND stashes `block` under sentinel key `_intraday_tactical_block` in metrics
- `_transform_output` reads the sentinel key, emits top-level group on Profile A, and cleans up the sentinel key

**No new ctx-to-transform plumbing is required.** Storage mechanism = flat_metrics dict (existing channel).

### 5.3 Downstream-override-path audit (§11.6 item 8)

`_assemble_output` contains two known verdict-override paths:
- DD-2 EXIT override at output.py ~L1929-1940 (mutates `action_summary.verdict`)
- BKOUT-001 GAP-5 C2-mandate override at output.py ~L1947-1961 (mutates `action_summary.verdict`)

**ITS impact assessment:** Both overrides mutate `action_summary.verdict` only. The `intraday_tactical` top-level group is INDEPENDENT of `action_summary.verdict` per DQ-2 (emit on all Profile A paths regardless of verdict). Neither override path touches `metrics["_intraday_tactical_block"]` or any `Intraday_*` flat key.

**No defensive guard needed at the attachment site.** Direct contrast with RLC-001 v1.1 where `reclaim_quality` sub-object on `action_summary` needed a verdict-aware guard.

---

## 6. Test Plan

Tests live at `layers/tests/unit/test_its001_intraday_tactical.py` (new file). Follow the post-TEST-HRN-001 idempotent test-harness pattern (use `spec_from_file_location` without polluting global `sys.modules`).

### 6.1 Test classes + expected coverage

| Test Class | Coverage | Target test count |
|---|---|---|
| `TestITS001ConstantsLocked` | Asserts module-level constants in compute.py exist and have spec values | 1 |
| `TestITS001EventDetection` | GAP_UP / GAP_DOWN / VOL_EXPANSION / MULTIPLE / no-event paths with synthetic df fixtures | 8 |
| `TestITS001ShelfDetection` | 4-bar / 7-bar / 10-bar qualifying shelves; tightness boundary cases; sliding-largest-N selection; no-shelf path | 8 |
| `TestITS001ShelfPosition` | ABOVE / BELOW / WITHIN classification with controlled current_price vs shelf bounds | 5 |
| `TestITS001TacticalStopABOVE` | shelf_structural ABOVE-mode stop derivation + atr_volatility parallel | 4 |
| `TestITS001TacticalStopBELOW` | shelf_structural BELOW-mode stop derivation + atr_volatility parallel | 4 |
| `TestITS001TacticalStopWITHIN` | shelf_structural WITHIN-mode dual alternates + atr_volatility | 3 |
| `TestITS001NoShelfFallback` | shelf_structural=None, atr_volatility-only emission | 3 |
| `TestITS001NearTermTargetABOVE` | INTRADAY_HIGH derivation + shelf-width projection | 4 |
| `TestITS001NearTermTargetBELOW` | SHELF_UPPER_PROJECTION + EXTENDED_RANGE_PROJECTION | 4 |
| `TestITS001NearTermTargetWITHIN` | Inapplicable mode (applicable=false) | 2 |
| `TestITS001IntradayHighDerivation` | Session-anchored high includes evaluated bar; cross-session boundary handling | 4 |
| `TestITS001LookbackStaleAnnotation` | Per-field annotation on ESTABLISHED_LOW + DAILY_HIGH; affected_fields array | 5 |
| `TestITS001LookbackStatusBlock` | Block shape on event / no-event paths; ISO timestamp format | 4 |
| `TestITS001FlatKeyRegistration` | All 18 flat keys registered in `_all_mapped_flat_keys()` | 1 |
| `TestITS001ProfileScope` | Group structurally absent on Profile B / Profile C outputs | 3 |
| `TestITS001VerdictInvariance` | Zero-difference engine verdict on identical inputs pre/post ITS-001 across 4-ticker fixture cohort | 1 |
| `TestITS001VerdictPathCoverage` | Group emitted on all Profile A paths (VALID / WAIT / INVALID / RECOVERY CANDIDATE / ERROR) | 5 |
| `TestITS001SchemaStability` | block keys match §2 spec contract; no surprise fields | 3 |
| `TestITS001NotInGatesFile` | Negative assertion: no `Intraday_*` flat key consumed by any function in gates.py | 1 |
| `TestITS001RLY001CallOrderPreserved` | Verifies `_compute_rally_state_for_ctx` still callable after ITS insertion; no shared-state collision | 2 |

**Total target test count:** ~75 tests.

### 6.2 Critical test fixtures

- **RGTI gap-and-go fixture** — synthetic df matching the WIP §3.3 RGTI Friday 2026-05-22 close state. Expected `event_type=GAP_UP`, `affected_fields=[ESTABLISHED_LOW, DAILY_HIGH]`, lookback_stale=true on both hierarchy entries.
- **FSLR orderly-trend fixture** — synthetic df matching the WIP §3.3 FSLR Friday 2026-05-22 close state. Expected `event_type=None`, lookback_stale=false on all entries.
- **Shelf-WITHIN fixture** — synthetic df with current price between shelf bounds.
- **No-shelf fixture** — synthetic df with no qualifying compression window.

### 6.3 Regression baseline

Phase 2 implementer runs full pytest cohort (currently 3133/5/1 per RLC-001 S160 baseline). ITS-001 acceptance:
- New tests: ~75 PASS
- Existing tests: 0 new failures
- Pre-existing failure `test_eng004_measured_move::test_transform_roundtrip` (BUG-CFL001-PRE-1 latent) — out of scope; remains as-is

---

## 7. Closure Criteria

| # | Criterion | Phase |
|---|---|---|
| 1 | Phase 2 hand-back delivered with diff-stat + file SHAs + test counts | Phase 2 close |
| 2 | All §6 tests pass; zero existing-test regressions | Phase 2 close |
| 3 | Engine runs cleanly on Profile A test ticker (TBS-internal smoke) with `intraday_tactical` group present in output JSON | Phase 2 close |
| 4 | Live validation cohort: ≥5 Profile A tickers across all 3 shelf positions (ABOVE / BELOW / WITHIN) + ≥1 lookback_stale=true witness + ≥1 lookback_stale=false witness | Phase 3 close |
| 5 | RGTI re-run confirms event_type=GAP_UP + lookback_stale=true on ESTABLISHED_LOW + DAILY_HIGH | Phase 3 |
| 6 | FSLR re-run confirms event_type=null + lookback_stale=false on all entries | Phase 3 |
| 7 | Verdict invariance (`TestITS001VerdictInvariance`) confirmed across live cohort pre/post ITS-001 | Phase 3 |
| 8 | 6-doc DIA cascade complete: Doc 2 §VI / §IV, Doc 7 Step 6, Doc 8 §II Layer 2, EEM verify-only, README, PEO | Phase 4 close |
| 9 | Bug Register entry advances 🔴 IDENTIFIED → 🟠 SPECIFIED (this spec) → 🟡 IMPLEMENTED (Phase 2 hand-back) → 🟢 SYNCED (Phase 4 DIA) → ✅ CLOSED | Phase 4 close |

---

## 8. Worked Examples

### 8.1 Example A — RGTI gap-and-go (Friday 2026-05-22 close)

**Input state (synthetic, mirroring WIP §3.3):**
- Profile A invocation
- df: hourly bars across recent 5 trading days; current bar = Friday afternoon
- Friday open gap: $22.05 (after Thursday close $18.39) — gap_pct = 19.9%, gap_atr = ~1.8× Daily ATR
- Daily ATR = $2.10; Hourly ATR = $0.42
- Friday session high = $27.79; current bar close = $26.42
- Shelf scan: Friday's intraday bars span ~$22.50 to $27.79 (width $5.29 = 2.5× Daily ATR) → no qualifying shelf

**Expected output `intraday_tactical`:**
```json
{
  "shelf": {
    "detected": false,
    "desc": "No qualifying compression shelf (no 4-10 bar window with width <= 0.5x Daily ATR)."
  },
  "lookback_status": {
    "stale": true,
    "event_type": "GAP_UP",
    "event_timestamp": "2026-05-22T09:30:00-04:00",
    "event_bars_ago": 6,
    "event_magnitude_pct": 0.199,
    "event_magnitude_atr": 1.83,
    "rvol_at_event": 7.42,
    "affected_fields": ["floor_analysis.hierarchy[ESTABLISHED_LOW]",
                        "target.hierarchy[DAILY_HIGH]"]
  },
  "tactical_stop": {
    "shelf_structural": null,
    "atr_volatility": {
      "price": 25.79,
      "atr_mult": 1.5,
      "atr_value_used": 0.42,
      "desc": "Stop at $25.79 (1.5x Hourly ATR from current price)."
    }
  },
  "near_term_target": {
    "mode": null,
    "primary": {"price": null, "source": "NOT_APPLICABLE",
                "desc": "Directionally neutral (WITHIN shelf) — no primary target emitted."},
    "secondary": {"price": null, "source": "NOT_APPLICABLE",
                  "desc": "Directionally neutral (WITHIN shelf) — no secondary target emitted."},
    "applicable": false
  }
}
```

Additionally, `floor_analysis.hierarchy[ESTABLISHED_LOW]` and `target.hierarchy[DAILY_HIGH]` each carry `lookback_stale: true`.

### 8.2 Example B — FSLR orderly-trend (Friday 2026-05-22 close)

**Input state:**
- Profile A; bars across last 5 trading days
- No gap on Friday open; Fast/Slow ATR ratio ~0.9
- Daily ATR = $5.20; Hourly ATR = $1.04
- Friday session mid-day shelf: hourly bars 4 through 8 = HH $254.20, LL $252.85, width $1.35 = 0.26× Daily ATR (passes 0.5× tightness)
- Current bar close $257.85 (above shelf upper)
- Friday session high = $259.12

**Expected output `intraday_tactical`:**
```json
{
  "shelf": {
    "detected": true,
    "upper": 254.20,
    "lower": 252.85,
    "bar_count": 5,
    "tightness_ratio": 0.260,
    "position": "ABOVE",
    "lookback_stale": false,
    "desc": "Compression shelf over 5 hourly bars; width 0.26x Daily ATR; position: ABOVE."
  },
  "lookback_status": {
    "stale": false,
    "event_type": null,
    "event_timestamp": null,
    "event_bars_ago": null,
    "event_magnitude_pct": null,
    "event_magnitude_atr": null,
    "rvol_at_event": null,
    "affected_fields": []
  },
  "tactical_stop": {
    "shelf_structural": {
      "price": 252.43,
      "anchor": "shelf_lower",
      "atr_buffer_mult": 0.4,
      "atr_value_used": 1.04,
      "desc": "Stop at $252.43 (0.4x Hourly ATR below shelf lower)."
    },
    "atr_volatility": {
      "price": 256.29,
      "atr_mult": 1.5,
      "atr_value_used": 1.04,
      "desc": "Stop at $256.29 (1.5x Hourly ATR from current price)."
    }
  },
  "near_term_target": {
    "mode": "ABOVE",
    "primary": {"price": 259.12, "source": "INTRADAY_HIGH",
                "desc": "Primary target $259.12 (INTRADAY_HIGH)."},
    "secondary": {"price": 260.47, "source": "SHELF_WIDTH_PROJECTION",
                  "desc": "Secondary target $260.47 (SHELF_WIDTH_PROJECTION)."},
    "applicable": true
  }
}
```

No hierarchy-entry `lookback_stale` annotations (event_type is null).

---

## 9. v1.1 Promotion Paths + Bug Register CONCEPT Entries

Three new Bug Register CONCEPT entries are logged at Phase 1 close (this spec delivery):

| ID | Title | Severity | Status |
|---|---|---|---|
| `INTRADAY-CAL-1` | 3-6 month live-data threshold review for 0.5× Daily ATR compression-shelf tightness multiplier (DQ-3b lock) | Low | 🟤 CONCEPT |
| `INTRADAY-CAL-2` | 3-6 month live-data threshold review for DQ-4b stop multipliers (0.4× fade / 0.3× breakout / 1.5× volatility) | Low | 🟤 CONCEPT |
| `INTRADAY-CFL-INTEGRATION-1` | v1.1 promotion path: promote shelf upper/lower to hierarchies for CFL-001 cross-surface confluence | Low | 🟤 CONCEPT |

Additional v1.1 promotion candidates surfaced during Phase 0 (not formal Bug Register entries — captured here as future-spec design inputs):

**From Session 3 (DQ-3 deferrals):**
- Opening-range shelf as separate `intraday_tactical.opening_range` block (Raschke/Williams ORB tradition)
- Volume profile / POC / accumulation-vs-distribution classification on shelf
- `NEAR_UPPER` / `NEAR_LOWER` fine-geometry labels (additional proximity threshold)
- 15m bar-frame promotion if hourly granularity proves insufficient
- Prior-session shelves (cross-session lookback)
- Explicit `relative_to_structural_floor` annotation field (DQ-6c follow-up)

**From Session 4 (DQ-4 deferrals):**
- `avwap_anchored` stop variant (Shannon AVWAP-anchored stop)
- `signal_bar` stop variant (Brooks signal-bar protective stop)
- Trailing-stop variant (Chandelier Exit / Parabolic SAR)
- AVWAP-intersection targets (Shannon opposing-AVWAP)
- R-multiple targets (Van Tharp 2R / 3R sizing-derived)
- Bollinger band targets
- Fibonacci extension projections (tracked separately as `ENG-006` 🟤 CONCEPT)

---

## 10. Acceptance

Phase 2 implementer accepts when:
- All §6 tests pass
- Zero regression failures on full pytest cohort (baseline 3133/5/1 per RLC-001 S160)
- Engine runs cleanly on at least 1 Profile A test ticker with `intraday_tactical` group rendering in output JSON per §8 worked examples

---

## 11. Pre-Implementation Checklist (§11.6 Mirror)

Per SIR §11.6 (codified S162 via GOV-003), this checklist is the spec-side defense layer mirroring the Phase 2 Brief §4 implementation-side defense. Each item has a `file:line` evidence anchor that the Phase 2 implementer verifies before any code edit.

| # | §11.6 Item | Status at spec delivery | Evidence anchor |
|---|---|---|---|
| 1 | **Call-order verification** — `_assemble_intraday_tactical` in output.py reads ctx._intraday_* attributes populated by compute.py helpers | ✅ VERIFIED — call site at `main.py:~L213` precedes `_assemble_output` invocation. RLY-001 precedent at `main.py:~L215` for identical pattern. | `main.py:165-294` |
| 2 | **Sort-order check** — N/A. ITS does not operate on iterables of price/level state requiring sort | ✅ N/A | — |
| 3 | **Shared-reference / partition-leak audit** — `intraday_tactical` top-level group is structurally outside BUGR-002 partition (DQ-6 lock — no participation in `target.cleared_levels` / `_targets_above` / `_stops_below`) | ✅ VERIFIED by design (DQ-6). | `transform.py` — BUGR-002 partition site in `_transform_output` body (line not directly cited; Phase 2 implementer re-verifies via in-source grep for `cleared_levels` / `overhead_levels` partition site) |
| 4 | **Pipeline-order feasibility check** — Event detection runs once globally in compute.py at tier 3 (pre-gate); read happens at tier 8 (`_assemble_output`); writes guaranteed complete | ✅ VERIFIED — main.py L165–L294 confirms all compute helpers (`_compute_morphology` through `_compute_early_capital_rr`) execute before any `_assemble_output` early-return site. | `main.py:165-294` |
| 5 | **Call-order feasibility check** — ITS calls 3 helpers (`_detect_intraday_events`, `_detect_compression_shelf`, `_compute_intraday_tactical_levels`) sequentially; `_compute_intraday_tactical_levels` depends on `_detect_compression_shelf` output (sequential dependency) | ✅ VERIFIED — spec mandates this exact ordering at §4.8. Sequential, not commutative. | `compute.py` (new — see §4.1-§4.3) |
| 6 | **Cross-spec layout audit** — No existing top-level group named `intraday_tactical`; verified against transform.py module docstring + existing groups list | ✅ VERIFIED — §3.2 collision audit complete. | `transform.py` module docstring; collision audit §3 |
| 7 | **Storage-mechanism feasibility verification** — `_transform_output(action_summary, flat_metrics, debug=False)` does NOT receive ctx; ITS uses RLY-001 (block, flat_keys) tuple pattern with sentinel-key flat_metrics stash for block | ✅ VERIFIED — RLY-001 precedent established at output.py `_assemble_rally_state` + main.py call site. Same pattern. | `output.py:~L685-L800` (RLY-001 sibling); transform.py module docstring |
| 8 | **Downstream-override-path audit** — `intraday_tactical` group is INDEPENDENT of `action_summary.verdict`; neither DD-2 EXIT nor BKOUT-001 GAP-5 verdict overrides touch the new top-level group or any `Intraday_*` flat key | ✅ VERIFIED — by design (DQ-2 emit-on-all-paths lock makes verdict irrelevant). | `output.py:~L1929-1940` (DD-2), `output.py:~L1947-1961` (BKOUT-001 GAP-5) |
| 9 (additional) | **`floor_analysis.avwap_10bar.lookback_stale` field existence** — verify whether AVWAP-001 emits an `avwap_10bar` sub-object that ITS should annotate; if absent, drop from §2.1 list | 🟡 DEFERRED to Phase 2 entry — Phase 2 implementer greps AVWAP-001 emission site; if absent, omits the third annotation site silently. Drop is acceptable per DQ-1a hybrid semantics. | output.py — search for `avwap_10bar` or `AVWAP_10BAR` |

---

## 12. Sign-off

**Spec authority:** This document is the canonical Phase 1 spec for ITS-001. Any disagreement between this spec and a downstream Brief or implementation: **spec wins**.

**Phase 0 inputs consumed:**
- `TBS_Phase_0_WIP_Intraday_Tactical_Surface_v0_3.md` (14/14 sub-DQs locked, S1–S4)

**Engine source verified at SHA `master` HEAD as of 2026-05-24:**
- `main.py` (call-order verification, pipeline-order feasibility)
- `compute.py` (RLY-001 + BRK-001 patterns; FSLR convention `_tier1_ceiling = df_ctx['high'].iloc[-11:-1].max()`)
- `output.py` (RLY-001 `_assemble_rally_state` pattern; VTRIG-001 attachment idiom)
- `transform.py` (`_transform_output` signature lacks ctx; module docstring; `_all_mapped_flat_keys()`; conviction-tier vocabulary)

**Decisions consumed at Phase 1 (not re-litigated):**
- All 14 DQ locks from Phase 0 WIP v0.3
- Vocabulary collisions audited (§3)
- §11.6 spec-side audit complete (8 items)

**Lifecycle next:** Phase 2 — author Implementation Brief (`ITS001_Claude_Code_CLI_Implementation_Brief_v1_0.md`) referencing this spec by section per ACP §6.4; deliver Brief via `present_files`; Operator copies to working-tree root before Claude Code CLI session.

---

## Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-24 (S165) | Phase 1 spec authored from WIP v0.3. 14 DQs transcribed with §11.6 evidence anchors. §3 vocabulary collision audit. §11 Pre-Implementation Checklist (8 items VERIFIED + 1 deferred). §6 test plan (~75 tests across 20 classes). §8 worked examples (RGTI + FSLR). |
| v1.0.1 | 2026-05-24 (S165) | `_derive_intraday_high` pandas-API simplification in §2.7.3 + §4.3 — removed unnecessary `.normalize()` chaining and dead defensive fallback in §4.3 implementation; canonical `df.index.date == last_date` pattern. **No behavior change** — original code was functional but unnecessarily verbose. v1.0 → v1.0.1 cosmetic refinement, no DQ re-litigation, no semantic shift. |

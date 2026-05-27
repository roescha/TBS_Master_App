# ITS-001 — Intraday-Tactical Surface (C+D Bundle) — Phase 1 Spec v1.1

**Document ID:** `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md`
**Version:** v1.1
**Status:** SPECIFIED (Phase 1 close — ready for Phase 2 v1.1 amendment via Claude Code CLI)
**Date authored:** 2026-05-26 (Session 166)
**Supersedes:** `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md` v1.0.1 (S165, retained in `docs/specs/` for historical reference per CFL-001 / RLC-001 supersession precedent)
**Lifecycle anchors:**
- v1.0 Phase 0 WIP `TBS_Phase_0_WIP_Intraday_Tactical_Surface_v0_3.md` (14/14 sub-DQs locked S1–S4)
- v1.1 Phase 0 Handoff Memo `ITS001_v1_1_Phase0_Handoff_Memo_v1_0.md` (S165 — 5 amendment items, 13 DQs)
- v1.0 Implementation Hand-Back `ITS001_Phase2_Implementation_HandBack_v1_0.md` (S165 — v1.0 committed to master)
- v1.1 Phase 0 DQ-resolution (this session — DQ-V1/V2/V3, DQ-E1/E2/E3/E4/E5/E6, DQ-D1/D2, DQ-INT-1/INT-2)

**Authoring Analyst (Project chat):** Phase 1 v1.1 spec authoring per SIR §11 Track 1.
**Spec authority:** Mission — when Brief and spec disagree, **spec wins**.

---

## 0. v1.1 Amendment Summary

v1.1 is a substantive amendment cycle layered on top of the v1.0 implementation committed at S165. v1.0 stands as the foundational reference; v1.1 amends the engine to polish the operator surface before Phase 3 live validation commences.

### 0.1 Amendment items (5 total — 3 cosmetic + 2 substantive)

| # | Item | Type | Source | DQ locks |
|---|---|---|---|---|
| 1 | AVWAP_10BAR canonicalization (annotation as hierarchy entry, not sub-object) | Cosmetic (spec narrative only) | Hand-Back §6.1 | — |
| 2 | Path-vs-label vocabulary fix (`floor_analysis.hierarchy` → `trade_setup.stop.hierarchy`) | Cosmetic (spec narrative only) | Hand-Back §6.2 | — |
| 3 | `desc` string enrichment for inline interpretive mechanics | Cosmetic (engine desc strings) | S165 UX critique | DQ-D1, DQ-D2 |
| 4 | Vocabulary rename of WITHIN-mode stop alternates (`fade_to_upper`/`breakout_above` → `range`/`breakout`) | Substantive — schema-breaking | S165 UX critique | DQ-V1, DQ-V2, DQ-V3 |
| 5 | New `entry_zone` sub-object — parallel entry-price affordance to `tactical_stop` / `near_term_target` | Substantive — schema-additive | S165 UX critique | DQ-E1, DQ-E2, DQ-E3, DQ-E4, DQ-E5, DQ-E6, DQ-INT-1, DQ-INT-2 |

### 0.2 v1.1 Phase 0 DQ locks (13 — locked this session)

| DQ | Lock | Section |
|---|---|---|
| DQ-V1 | WITHIN-mode stop alternates renamed to `range` / `breakout` (suffix `_long` dropped — see §1.4 IBKR cash account constraint) | §2.8 |
| DQ-V2 | Rename applies symmetrically to both `tactical_stop.shelf_structural.price.*` and `tactical_stop.shelf_structural.atr_buffer_mult.*` | §2.8 |
| DQ-V3 | No flat-key rename needed; `Intraday_*` keys do not carry `fade_to_upper` / `breakout_above` tokens | §2.8, §4.5 |
| DQ-E1 | `entry_zone` sub-object emits per shelf position: ABOVE→`touchback`; BELOW→`breakout`; WITHIN→dual `range`+`breakout` alternates. Mirrors `tactical_stop.shelf_structural` dual pattern | §2.9 |
| DQ-E2 | ABOVE-mode `touchback` zone: `zone_lower=shelf.upper`, `zone_upper=shelf.upper + 0.25 × hourly_atr` | §2.9 |
| DQ-E3 | BELOW + WITHIN `breakout` emits dual anchors: `trigger_structural=shelf.upper` + `trigger_confirmed=shelf.upper + 0.25 × hourly_atr`. Each anchor carries its own desc | §2.9 |
| DQ-E4 | WITHIN mode emits both `range` + `breakout` (dual alternates) | §2.9 |
| DQ-E5 | Long-only — permanent structural exclusion (IBKR cash account constraint). Short alternates NOT a deferral; out of scope permanently | §1.4 |
| DQ-E6 | No-shelf fallback: `entry_zone.applicable: false` with null sub-objects (mirrors `near_term_target` no-shelf convention) | §2.9 |
| DQ-D1 | `desc` strings ≤40 words, three-sentence template: **what** / **mechanic** / **invalidation** | §3.5 |
| DQ-D2 | Cross-reference syntax: bare-name within `intraday_tactical` block; full path for cross-block references | §3.5 |
| DQ-INT-1 | Item 4 rename + Item 5 entry_zone co-implemented in single Phase 2 pass (entry_zone descs reference renamed stop keys via `stop_ref` paths) | §4.8 |
| DQ-INT-2 | New entry_zone test classes added to existing `test_its001_intraday_tactical.py` (same file; preserves cohort cohesion) | §6.1 |

### 0.3 Bug Register policy for v1.1 cycle

Per Operator directive at memo §8: **no new ITS Bug Register entries during v1.1 cycle.** All amendment items roll into this v1.1 spec as their consolidating record. ITS-001 master row in Bug Register tracks the lifecycle:
- 🟡 IMPLEMENTED (v1.0 close, S165) → 🟠 SPECIFIED (v1.1 spec lock, this session) → 🟡 IMPLEMENTED (v1.1 Phase 2 close) → 🟢 SYNCED (v1.1 Phase 4 DIA cascade) → ✅ CLOSED (v1.1 closure).

Three pre-existing v1.0 CONCEPT items (calibration + CFL integration) remain spec-text references in §9 — no Bug Register promotion.

---

## 1. Purpose & Scope

### 1.1 Capability

The **Intraday-Tactical Surface** adds related Profile-A-only features to the engine output:

- **Feature C — Regime-shift annotation.** Per-field `lookback_stale: bool` annotation on short-window fields (10-bar ESTABLISHED_LOW, 10-bar resistance, 10-bar AVWAP) PLUS a top-level summary section `intraday_tactical.lookback_status`, when the field's lookback window straddles a detected price-action discontinuity event (GAP or VOL_EXPANSION).
- **Feature D — Intraday-tactical surface.** A new top-level group `intraday_tactical` providing shelf detection (`intraday_tactical.shelf`), tactical stop (`intraday_tactical.tactical_stop`), near-term target (`intraday_tactical.near_term_target`), and **entry zone** (`intraday_tactical.entry_zone`, new in v1.1) — operationally tighter than the swing-frame hierarchies that currently dominate Profile A output.

Both features address the same operational gap: in macro-compressed conditions (the late-2025 / mid-2026 backdrop of Iran/oil/tariffs/US unpredictability driving frequent same-day-exit conversion of swing setups), swing-frame stops and targets are emotionally and operationally untenable as day-trade boundaries. The intraday-tactical surface provides Profile-A-aligned, hourly-granular levels parallel to the existing swing surfaces.

The v1.1 amendment adds the **entry_zone** sub-object alongside the existing tactical_stop and near_term_target affordances, completing the entry/stop/target tactical triad on a single inline surface. Operator UX critique at S165 surfaced the asymmetry — first-class stop and target affordances forced manual derivation of entry levels. v1.1 closes that gap.

### 1.2 Profile Scope

**Profile A only.** Profile B (daily) and Profile C (weekly) do not naturally support intraday-tactical management. If intraday-tactical management is desired on a Profile-B/C-flagged ticker, the Operator runs Profile A on the same ticker.

The `intraday_tactical` top-level group is absent from Profile B and Profile C outputs entirely (NOT null-emitted; structurally absent — same convention as Profile-A-only `floor_analysis.macro_frame` per WKC-001).

### 1.3 Scope Boundaries

**v1.0 (already implemented, S165):**
- Feature C: `GAP` + `VOL_EXPANSION` event detection
- Feature D: compression-shelf detection (4–10 hourly bar sliding window, 0.5× Daily ATR tightness)
- Tactical stop: dual methodology (`shelf_structural` + `atr_volatility`)
- Near-term target: 3-mode by shelf `position` (`ABOVE` / `BELOW` / `WITHIN`)
- Per-field `lookback_stale` annotation on short-window fields
- Summary section `intraday_tactical.lookback_status`

**v1.1 amendments (this spec):**
- Vocabulary rename: WITHIN-mode stop alternates `fade_to_upper`/`breakout_above` → `range`/`breakout`
- New `entry_zone` sub-object with position-aware structure mirroring `tactical_stop`'s dual-alternate WITHIN pattern
- Dual-anchor `breakout` triggers (`trigger_structural` + `trigger_confirmed`) on BELOW and WITHIN modes
- `desc` string enrichment across all four sub-objects per three-sentence template
- AVWAP_10BAR annotation language canonicalized to "hierarchy entry" framing
- Path-vs-label vocabulary corrected (`trade_setup.stop.hierarchy` / `trade_setup.target.hierarchy`)

**Deferred to v1.2+ (logged as spec §9 text — no Bug Register entries per memo §8):**
- Opening-range shelf (Raschke/Williams ORB tradition) — would add a parallel `intraday_tactical.opening_range` block
- AVWAP-pinch shelf (Shannon tradition)
- Range-break event detection
- Volume confirmation on shelf (RVOL ≤ 0.8× dry-up gate)
- `NEAR_UPPER` / `NEAR_LOWER` fine-geometry labels
- `avwap_anchored` / `signal_bar` / trailing-stop variants
- AVWAP-intersection targets, R-multiple targets, Bollinger band targets
- Cross-surface confluence with CFL-001 (`INTRADAY-CFL-INTEGRATION-1` spec-text concept)
- 15-minute bar-frame promotion
- Prior-session shelves (cross-session lookback)
- Explicit `relative_to_structural_floor` annotation
- Profile B / Profile C extension (§1.2 scope lock)
- Calibration review of 0.5× Daily ATR compression-shelf tightness multiplier (`INTRADAY-CAL-1` — Phase 3 live data required)
- Calibration review of DQ-4b stop multipliers (`INTRADAY-CAL-2`)
- Calibration review of new entry-confirmation ATR multiplier (`INTRADAY-CAL-3`, new in v1.1)

### 1.4 Non-Goals

- ITS does **NOT** participate in any swing-frame gate. No gate function (`gates.py`) reads any `Intraday_*` flat key or `ctx._intraday_*` attribute. Verdict-invariance is a closure criterion (§7).
- ITS is **NOT** an entry recommendation system. Per DQ-2 §2.3 (semantic neutrality lock), the surface provides levels — the Operator decides whether to act. The v1.1 `entry_zone` addition surfaces zones and trigger levels with mechanic descriptions, but does NOT recommend "buy now" or "wait".
- ITS does **NOT** participate in the BUGR-002 partition. Cross-surface confluence with CFL-001 is a v1.x candidate.
- ITS does **NOT** mandate Operator action when `lookback_stale: true` — the flag is operator-facing transparency, not a verdict modifier.
- **ITS emits long-side affordances only.** The TBS Operator's IBKR account is a cash account, which structurally prohibits short positions. Short-side mechanics (short_range, short_breakdown, short_touchback) are **permanently out of TBS scope**, not a deferral. Spec section §9 v1.x deferrals lists do NOT include short-side items. This is a durable structural fact about the operating account, not a design preference.

---

## 2. Architectural Model

This section transcribes the locked Phase 0 DQs from v1.0 (14 sub-DQs from Phase 0 WIP v0.3) plus v1.1 amendment DQs (13 from this session's Phase 0 resolution). Each DQ is the canonical decision lock; implementation MUST conform.

### 2.1 DQ-1a — Feature C location (v1.0 LOCKED Session 1, v1.1 narrative-corrected)

**Hybrid:**
- Per-field `lookback_stale: bool` annotation on three short-window hierarchy entries (annotated by label-match, not by container-path):
  - `ESTABLISHED_LOW` (lives in `trade_setup.stop.hierarchy` per the BUGR-002 partition)
  - `DAILY_HIGH` (lives in `trade_setup.target.hierarchy` per the BUGR-002 partition — the 10-bar daily-frame resistance)
  - `AVWAP_10BAR` (lives in `trade_setup.stop.hierarchy` as a SUPPORT-role hierarchy entry; conviction tier MA_DYNAMIC per `_CONVICTION_TIER_MAP`)
- Summary section `intraday_tactical.lookback_status` (shape defined in §2.4 DQ-5d)

**v1.1 narrative correction (Item 1 + Item 2):** v1.0 §2.1 referenced these annotation sites as `floor_analysis.hierarchy[label=ESTABLISHED_LOW]`, `target.hierarchy[label=DAILY_HIGH]`, and `floor_analysis.avwap_10bar.lookback_stale` (the last conditionally, "if AVWAP-001 surfaces an `avwap_10bar` sub-object"). All three references are corrected in v1.1:
- AVWAP_10BAR is a hierarchy entry (NOT a sub-object) — annotated alongside ESTABLISHED_LOW on the floor-side hierarchy.
- The container paths are `trade_setup.stop.hierarchy[...]` and `trade_setup.target.hierarchy[...]` (not `floor_analysis.hierarchy` / `target.hierarchy`). `floor_analysis` is a separate top-level group carrying `higher_frame`, `macro_frame`, `protective_anchor`, `floor_proximity_exemption` — it does NOT have a `hierarchy` key.
- The Phase 2 v1.0 implementation correctly annotated by label-match per Brief §4.2 step 2 — this v1.1 amendment is narrative-only; engine behavior unchanged.

Precedent: mirrors `volatility_regime` caution_factor convention (top-level + field-level dual surface).

### 2.2 DQ-1b — Feature D location (v1.0 LOCKED Session 1, unchanged)

**New top-level group `intraday_tactical`**, sibling to existing top-level groups. Follows OTL-001 concept-grouped JSON convention.

The exact set of existing top-level groups at engine-current state (verified via `transform.py` module docstring + `_transform_output` body inspection) includes: `action_summary`, `trade_snapshot`, `trade_quality`, `trade_risk`, `trend_state`, `floor_analysis`, `trade_setup`, `extension_analysis`, `psychological_levels`, `volatility_regime`, `rally_state`, `entry_proximity`, `exit_signals`, `recovery_analysis`, `swing_breakout_confirmation`, `intraday_tactical` (v1.0+), `_debug` (debug-mode only).

`intraday_tactical` slots in the reading order **after** `swing_breakout_confirmation` and **before** `_debug`. Profile-A-only by §1.2; absent on Profile B/C outputs.

### 2.3 DQ-2 — Verdict scope (v1.0 LOCKED Session 1, unchanged)

**Emit `intraday_tactical` group on ALL Profile A paths regardless of swing verdict.**

Operational consequences:
- The group emits on `VALID`, `WAIT`, `INVALID`, `RECOVERY CANDIDATE`, and `ERROR` (data-availability permitting on ERROR) verdicts.
- All compute helpers run pre-gate (per §5 Pipeline & Call-Order), so the data is available regardless of which `_assemble_output` early-return path the engine follows.
- Semantic neutrality: surface provides levels, does NOT imply entry recommendation. No `recommendation` / `signal` field; the Operator interprets `position` + `tactical_stop` + `entry_zone` + `near_term_target` themselves.
- Cross-reference to swing verdict: no `swing_context_note` field. The Operator reads `action_summary.verdict` directly.
- Graceful degradation when no shelf detected: `shelf.detected: false` framing, not null sub-fields. `entry_zone.applicable: false` per DQ-E6.

### 2.4 DQ-5a/b/c/d — Regime-shift event detection (v1.0 LOCKED Session 2, unchanged)

[**Body identical to v1.0 §2.4 — event types, thresholds, scan window, summary section shape.** Per ACP §6.5.3 amendment-scope discipline, unchanged sections are referenced rather than restated. Concrete content lives in v1.0 spec; v1.1 introduces no semantic changes here. Implementer reads v1.0 §2.4 verbatim.]

#### 2.4.1 DQ-5a — Event types
Two primary event types in v1.0+: `GAP_UP`, `GAP_DOWN`, `VOL_EXPANSION`, `MULTIPLE`. Thresholds: `INTRADAY_GAP_PCT_FLOOR=0.04`, `INTRADAY_GAP_ATR_MULT=1.5`, `INTRADAY_GAP_RVOL_THRESHOLD=2.0`, `INTRADAY_VOL_EXPANSION_FAST_BARS=5`, `INTRADAY_VOL_EXPANSION_SLOW_BARS=20`, `INTRADAY_VOL_EXPANSION_RATIO_THRESHOLD=1.5`.

#### 2.4.2 DQ-5c — Scan window
10-bar lookback (matching the longest annotated short-window field's lookback).

#### 2.4.3 DQ-5b — Most-recent-event policy
Scanner records most recent event within the 10-bar window; if no event, returns silently.

#### 2.4.4 DQ-5d — `lookback_status` summary block shape
```json
"lookback_status": {
  "stale": true,
  "event_type": "GAP_UP" | "GAP_DOWN" | "VOL_EXPANSION" | "MULTIPLE",
  "event_timestamp": "<ISO 8601>" | null,
  "event_bars_ago": <int>,
  "event_magnitude_pct": <float> | null,
  "event_magnitude_atr": <float> | null,
  "rvol_at_event": <float>,
  "affected_fields": [
    "trade_setup.stop.hierarchy[ESTABLISHED_LOW]",
    "trade_setup.target.hierarchy[DAILY_HIGH]",
    "trade_setup.stop.hierarchy[AVWAP_10BAR]"
  ]
}
```

**v1.1 path correction (Item 2 + Item 1):** The `affected_fields` array uses `trade_setup.stop.hierarchy` and `trade_setup.target.hierarchy` paths (engine-actual), and includes `AVWAP_10BAR` as a hierarchy entry rather than a sub-object. The v1.0 implementation already emitted these paths correctly — this is narrative confirmation in the spec.

### 2.5 DQ-6 — BUGR-002 partition non-participation (v1.0 LOCKED Session 2, unchanged)

ITS does NOT participate in the BUGR-002 partition. `intraday_tactical` top-level group is structurally outside the `target.cleared_levels` / `_targets_above` / `_stops_below` partition system. No CFL-001 cross-surface confluence in v1.0 / v1.1 (deferred to `INTRADAY-CFL-INTEGRATION-1` spec-text concept).

### 2.6 DQ-bar-frame — Hourly only (v1.0 LOCKED Session 2, unchanged)

Profile A uses hourly bars exclusively. 15-minute frame promotion deferred to v1.x.

### 2.7 DQ-3a/b/c/d — Compression-shelf detection (v1.0 LOCKED Session 3, unchanged)

#### 2.7.1 DQ-3a — Sliding window
4–10 bar sliding window over hourly bars. Picks the largest-N qualifying shelf (favors stability over recency).

#### 2.7.2 DQ-3b — Tightness threshold
Shelf width must be ≤ `INTRADAY_SHELF_TIGHTNESS_ATR_MULT (=0.5) × Daily ATR`. Width = `max(high[window]) - min(low[window])`.

#### 2.7.3 DQ-3c — `position` classification
- `ABOVE` if `last['close'] > shelf.upper`
- `BELOW` if `last['close'] < shelf.lower`
- `WITHIN` if `shelf.lower ≤ last['close'] ≤ shelf.upper`

#### 2.7.4 DQ-3d — Geometric labels deferred
`NEAR_UPPER` / `NEAR_LOWER` fine-geometry labels deferred to v1.x.

### 2.8 DQ-V1/V2/V3 — Vocabulary rename of WITHIN-mode stop alternates (v1.1 NEW LOCK)

#### 2.8.1 DQ-V1 — Final key names

WITHIN-mode `tactical_stop.shelf_structural` dual-alternate keys are renamed:

| v1.0 (deprecated) | v1.1 (canonical) |
|---|---|
| `fade_to_upper` | `range` |
| `breakout_above` | `breakout` |

**Rationale.**
- **Concision** — 1-word keys match existing engine terse-key convention (`primary`, `secondary`, `shelf_upper`, `shelf_lower`).
- **Semantic clarity** — `range` reads as "the range-play stop"; `breakout` reads as "the breakout-play stop". The original `fade_to_upper` used "fade" in non-standard sense ("drift toward upper" rather than the trading-parlance "counter-trend"), which the S165 UX critique surfaced as a comprehension friction.
- **Cross-spec symmetry** — entry_zone (§2.9) uses identical key names for the same mechanic. `stop_ref` cross-references can use the same token (e.g., `stop_ref: "tactical_stop.shelf_structural.price.range"`).
- **Suffix discipline** — no `_long` suffix per §1.4 IBKR cash account constraint (long-side is the only side; suffix would be persistent redundancy).

#### 2.8.2 DQ-V2 — Symmetric rename across both `price.*` and `atr_buffer_mult.*`

Both dict structures in `tactical_stop.shelf_structural` use the renamed keys:

```json
"shelf_structural": {
  "price": {
    "range": <float>,        // was: fade_to_upper
    "breakout": <float>      // was: breakout_above
  },
  "anchor": "both",
  "atr_buffer_mult": {
    "range": 0.4,            // was: fade_to_upper
    "breakout": 0.3          // was: breakout_above
  },
  "atr_value_used": <float>,
  "desc": "..."
}
```

Asymmetric rename would force readers to mentally map between the two dicts — both name the same play; both use the same key.

#### 2.8.3 DQ-V3 — No flat-key rename

Audit per v1.0 spec §4.5 enumeration: the 18 `Intraday_*` flat keys use `Intraday_Stop_Shelf_Structural` (singular, dict-typed on WITHIN mode). They do NOT carry `fade_to_upper` / `breakout_above` tokens. No flat-key rename required. The dict-keyed value emitted under `Intraday_Stop_Shelf_Structural` on WITHIN mode will carry the renamed keys structurally (no schema change at the flat-key level).

### 2.9 DQ-E1/E2/E3/E4/E5/E6 — `entry_zone` sub-object (v1.1 NEW LOCK)

#### 2.9.1 DQ-E1 — Structural shape: position-aware sub-keys mirroring `tactical_stop`

`entry_zone` emits as a sub-object alongside `shelf`, `lookback_status`, `tactical_stop`, `near_term_target` in the `intraday_tactical` group. Position-aware sub-key structure:

| Shelf position | Sub-key(s) emitted | Play mechanic |
|---|---|---|
| `ABOVE` | `touchback` | Long entry on retrace to shelf upper acting as support |
| `BELOW` | `breakout` | Long entry on close above shelf upper |
| `WITHIN` | `range` + `breakout` (dual alternates) | Long entry near shelf lower (range hold) OR on close above shelf upper (range expansion) |
| No shelf | All sub-keys absent; `applicable: false`, `mode: null` | Per DQ-E6 |

Architectural parallelism with `tactical_stop.shelf_structural`'s WITHIN dual-alternate pattern preserved. `breakout` key reused across BELOW and WITHIN modes — same entry mechanic, single key name.

#### 2.9.2 DQ-E2 — ABOVE-mode `touchback` zone definition

`touchback` is a zone-occupation entry, not a trigger event. Zone band:

| Field | Value |
|---|---|
| `zone_lower` | `shelf.upper` |
| `zone_upper` | `shelf.upper + 0.25 × hourly_atr` |

The 0.25× ATR proximity buffer is consistent with existing engine convention (PoC distance threshold, AVWAP distance threshold). Operator watches for price to enter the zone and evaluates whether shelf upper holds as support.

#### 2.9.3 DQ-E3 — Dual-anchor `breakout` triggers (BELOW + WITHIN modes)

`breakout` is a trigger-event entry. Two anchors emitted, each with its own desc:

| Field | Value | Mechanic |
|---|---|---|
| `trigger_structural` | `shelf.upper` | Bare structural breakout — close above this is the textbook trigger |
| `trigger_confirmed` | `shelf.upper + 0.25 × hourly_atr` | Buffered confirmation — filters single-bar wick fakeouts |

The dual emission surfaces the execution choice (early entry vs confirmed entry) inline without forcing the Operator to consult Doc 7 reading guidance. Operator chooses which anchor to act on based on tolerance for false-breakout fills.

**New module-level constant for v1.1:**
```python
INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25
```

Calibration candidate logged as `INTRADAY-CAL-3` in §9 (no Bug Register entry per memo §8 directive).

#### 2.9.4 DQ-E4 — WITHIN dual alternates

WITHIN mode emits both `range` AND `breakout` sub-objects (not one based on directional inference). Two distinct setups exist when price is inside the consolidation; the spec surfaces both, the Operator chooses. Mirrors `tactical_stop.shelf_structural` dual-stop pattern.

#### 2.9.5 DQ-E5 — Long-only permanent scope exclusion

`entry_zone` emits long-side affordances only. Per §1.4, short-side mechanics are permanently out of TBS scope (IBKR cash account constraint). Sub-keys are unsuffixed (`touchback`, `range`, `breakout`) — no `_long` qualification needed because there is no parallel short-side namespace.

#### 2.9.6 DQ-E6 — No-shelf fallback

When `shelf.detected: false`:
```json
"entry_zone": {
  "applicable": false,
  "mode": null,
  "desc": "No qualifying compression shelf — entry_zone not emitted."
}
```

Mirrors `near_term_target.applicable: false` convention on no-shelf. Option-β (ATR-volatility-derived entry zone independent of shelf) was considered and rejected for v1.1 — introduces shelf-independent mechanics with no v1.0 precedent grounding; defer if Phase 3 surfaces demand.

### 2.10 DQ-D1/D2 — desc string enrichment + cross-reference convention (v1.1 NEW LOCK)

See §3.5 (codified as a separate cross-cutting convention applying across all four sub-objects).

---

## 3. Label-Vocabulary Collision Audit

Per §11.6 item 6 (cross-spec layout audit) — applied to label tokens.

### 3.1 New labels introduced

**v1.0 (already in production):**
- `intraday_tactical` (top-level group key)
- `shelf`, `lookback_status`, `tactical_stop`, `near_term_target` (sub-object keys)
- `lookback_stale` (boolean field on annotated hierarchy entries)
- `shelf_structural`, `atr_volatility` (stop methodology labels)
- `ABOVE` / `BELOW` / `WITHIN` (shelf position values; also `near_term_target.mode` values)
- `GAP_UP` / `GAP_DOWN` / `VOL_EXPANSION` / `MULTIPLE` (event_type values)
- `INTRADAY_HIGH` / `SHELF_UPPER_PROJECTION` / `SHELF_WIDTH_PROJECTION` / `EXTENDED_RANGE_PROJECTION` / `NOT_APPLICABLE` (target source labels)
- `anchor` field with values `shelf_lower` / `shelf_upper` / `both`

**v1.1 new labels:**
- `entry_zone` (sub-object key — sibling of `shelf` / `tactical_stop` / `near_term_target`)
- `touchback` (sub-key under entry_zone — ABOVE mode)
- `range` (sub-key under entry_zone — WITHIN mode; also renamed key under `tactical_stop.shelf_structural.price` / `.atr_buffer_mult` on WITHIN mode)
- `breakout` (sub-key under entry_zone — BELOW + WITHIN modes; also renamed key under `tactical_stop.shelf_structural.price` / `.atr_buffer_mult` on WITHIN mode)
- `trigger_structural` / `trigger_confirmed` (dual-anchor fields under `entry_zone.breakout`)
- `zone_lower` / `zone_upper` (zone-band fields under `entry_zone.touchback` and `entry_zone.range`)
- `stop_ref` / `target_ref` / `target_implied` / `trigger` / `applicable` / `mode` (entry_zone field keys)

**v1.1 deprecated labels (removed):**
- `fade_to_upper` (replaced by `range`)
- `breakout_above` (replaced by `breakout`)

### 3.2 Collision audit results

Comparison performed against engine canonical vocabularies (Doc 2 §IV Output Schema, Doc 8 §II Layer 2, transform.py `_CONVICTION_TIER_MAP`, gates.py vocabulary, output.py vocabulary).

**v1.0 labels (re-audited, no change):** All previously cleared per v1.0 §3.2.

**v1.1 new labels:**
- `entry_zone` — **No collision.** Sibling sub-object to existing intraday_tactical sub-objects; no existing key with this name at any nesting level in engine output.
- `touchback` — **No collision.** New vocabulary. Distinct from `volume_at_price` (AT_POC convention), `entry_proximity` block, and all existing entry_zone-adjacent fields.
- `range` — **No collision in this scope.** Used as sub-key under both `entry_zone.range` (top-level mode) AND `tactical_stop.shelf_structural.price.range` / `.atr_buffer_mult.range` (renamed WITHIN keys). Same-name reuse is intentional — both refer to the range-play mechanic, semantic equivalence is meaningful. Distinct from `range` as a generic English word in `desc` strings (no schema-key/desc-prose collision risk).
- `breakout` — **No collision in this scope.** Same-name reuse rationale as `range`. Distinct from `swing_breakout_confirmation` (different schema namespace — top-level group vs nested sub-key); distinct from `Is_Breakout` flag in compute layer (different layer entirely); distinct from BRK-001 `_breakout_model_active` ctx attribute (different naming convention — internal underscore-prefixed). `BREAKOUT` (uppercase) historical state-label usage in `entry_zone.trigger_historical` field appears as a value, not a key — different value space.
- `trigger_structural` / `trigger_confirmed` — **No collision.** New vocabulary. No existing field with these names.
- `zone_lower` / `zone_upper` — **No collision.** New vocabulary. Distinct from `lower` / `upper` standalone keys under `shelf` sub-object (different parent path).
- `stop_ref` / `target_ref` / `target_implied` — **No collision.** New cross-reference vocabulary. The `_ref` suffix convention is unique to entry_zone field naming.
- `applicable` / `mode` — **Single-shared-vocabulary scope.** Both fields already exist under `near_term_target` (v1.0 — `applicable: bool`, `mode: ABOVE|BELOW|WITHIN`). entry_zone reuses the same names with identical semantics — intentional, mirrors near_term_target convention. No collision; semantic alignment.
- `trigger` — **No collision in this scope.** Used as a desc-style key within entry_zone sub-objects (`trigger: "Close above shelf upper"`). Distinct from `entry_zone.trigger_historical` (value-space; uppercase event-type values) and `trigger_proximity` adjacent capabilities.

### 3.3 v1.2+ label-pre-commit register

Provisional v1.x labels flagged for re-audit at future spec authoring (NOT used in v1.1):
- `INTRADAY_SHELF_UPPER` / `INTRADAY_SHELF_LOWER` — hierarchy-entry labels for `INTRADAY-CFL-INTEGRATION-1` v1.x promotion. Re-audit against `floor_analysis.hierarchy` / `target.hierarchy` label set at the promotion-spec authoring.
- `opening_range` (sub-object key — Raschke/Williams ORB v1.x deferral)

### 3.4 Hierarchy-label alignment for `lookback_stale` annotation

DQ-1a §2.1 references three short-window field annotations, with v1.1 narrative corrections:

| Hierarchy entry label | Container path (engine-actual) | Conviction tier |
|---|---|---|
| `ESTABLISHED_LOW` | `trade_setup.stop.hierarchy[]` | STRUCTURAL per `_CONVICTION_TIER_MAP` |
| `DAILY_HIGH` | `trade_setup.target.hierarchy[]` | STRUCTURAL per `_CONVICTION_TIER_MAP` |
| `AVWAP_10BAR` | `trade_setup.stop.hierarchy[]` (annotated alongside ESTABLISHED_LOW; appears in `hierarchy[]` when price is below the AVWAP, or in `overhead_levels[]` when price is above — both are post-partition siblings) | MA_DYNAMIC per `_CONVICTION_TIER_MAP` |

**v1.0 implementation note:** The Phase 2 implementer correctly annotated by label-match (per Hand-Back §6.1 resolution), not by container-path-match. v1.1 narrative codifies the engine-actual container paths.

### 3.5 Cross-reference and `desc` string convention (v1.1 NEW)

DQ-D1 + DQ-D2 codified here as a cross-cutting convention applying to all `desc` strings across the `intraday_tactical` group.

#### 3.5.1 `desc` string template (DQ-D1)

Each `desc` string follows the **three-sentence template**:

1. **What** — the level + numeric context (price, ATR mult, anchor reference)
2. **Mechanic** — the entry/exit action this level supports (semantic-neutral phrasing; describes the play, does NOT recommend action)
3. **Invalidation** — when this level/zone becomes inactive

**Length ceiling:** ≤40 words per desc string. (Operator can read the surface inline without scrolling; long descs defeat the readability goal.)

**Worked example (COHR `tactical_stop.shelf_structural.price.range`, $367.07):**

> "Range-play long stop $367.07 — 0.4× Hourly ATR below shelf lower $370.18. Supports long entry near shelf lower expecting drift to upper $382.00. Invalidates if price closes below $370.18 (shelf range breakdown)."

(34 words; three sentences; what / mechanic / invalidation.)

#### 3.5.2 Cross-reference syntax (DQ-D2)

When a `desc` references another field within the same `intraday_tactical` group, use the **bare relative path** (no `intraday_tactical.` prefix):

> "Stop below shelf lower at `tactical_stop.shelf_structural.price.range`."

When a `desc` references a field outside the `intraday_tactical` group, use the **full JSON path**:

> "Hourly ATR sourced from `trade_snapshot.atr.value`."

Rationale: within-block references are reader-friendly with the implicit parent; cross-block references need full disambiguation. Convention codified here so all four sub-objects emit consistent cross-references.

### 3.6 ALL profile scope

Profile A only. Reaffirmed in §1.2.

---

## 4. Implementation Specification

This section specifies the engine edits for v1.1. v1.0 implementation per Hand-Back §3 SHAs is the foundational reference; v1.1 amendments are layered on top.

### 4.1 compute.py — Module-level constants (v1.1 additions)

**New constant for v1.1:**

```python
# ITS-001 v1.1 additions (Phase 0 DQ-E3 lock)
INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25
```

Inserted alongside the existing 12 INTRADAY_* constants (v1.0 Hand-Back §3.2 item 1). No existing constants modified.

### 4.2 compute.py — `_detect_intraday_events` helper (v1.0 unchanged)

[Body unchanged from v1.0 §4.1. Reference: post-S165 master at `compute.py` `_detect_intraday_events`.]

### 4.3 compute.py — `_detect_compression_shelf` helper (v1.0 unchanged)

[Body unchanged from v1.0 §4.2. Reference: post-S165 master at `compute.py` `_detect_compression_shelf`.]

### 4.4 compute.py — `_compute_intraday_tactical_levels` helper (v1.1 modified)

The v1.0 helper computes `_intraday_tactical_stop_shelf_structural` (writing to ctx) using `fade_to_upper` / `breakout_above` keys for the WITHIN-mode dict structure. **v1.1 amendment:** rename these keys to `range` / `breakout` per DQ-V1/V2.

**Affected lines (v1.0 reference):** within the WITHIN-position branch of `_compute_intraday_tactical_levels`, where the dual-alternate dict is constructed. Phase 2 implementer locates the construction site by `grep` for `fade_to_upper` in compute.py and renames per the following structural change:

```python
# v1.0 (deprecated):
ctx._intraday_tactical_stop_shelf_structural = {
    'price': {
        'fade_to_upper': <float>,
        'breakout_above': <float>,
    },
    'anchor': 'both',
    'atr_buffer_mult': {
        'fade_to_upper': INTRADAY_STOP_FADE_ATR_MULT,
        'breakout_above': INTRADAY_STOP_BREAKOUT_ATR_MULT,
    },
    'atr_value_used': state.atr_raw,
}

# v1.1 (canonical):
ctx._intraday_tactical_stop_shelf_structural = {
    'price': {
        'range': <float>,        # was: fade_to_upper
        'breakout': <float>,     # was: breakout_above
    },
    'anchor': 'both',
    'atr_buffer_mult': {
        'range': INTRADAY_STOP_FADE_ATR_MULT,        # was: fade_to_upper
        'breakout': INTRADAY_STOP_BREAKOUT_ATR_MULT, # was: breakout_above
    },
    'atr_value_used': state.atr_raw,
}
```

The numeric values are unchanged; only the dict-key names are renamed. The same constants (`INTRADAY_STOP_FADE_ATR_MULT=0.4`, `INTRADAY_STOP_BREAKOUT_ATR_MULT=0.3`) continue to drive the `range` and `breakout` multipliers respectively. The fundamental mechanics are preserved — only the operator-facing vocabulary changes.

### 4.5 compute.py — `_compute_entry_zone` helper (v1.1 NEW)

**New helper signature** — inserted in compute.py immediately after `_compute_intraday_tactical_levels` (sibling pattern):

```python
def _compute_entry_zone(ctx):
    """ITS-001 v1.1: Compute entry_zone levels per shelf position.

    Reads ctx._intraday_shelf_* state (written by _detect_compression_shelf)
    + ctx.state.atr_raw + ctx.last['close'].

    Writes:
      ctx._intraday_entry_zone_mode
      ctx._intraday_entry_zone_applicable
      ctx._intraday_entry_zone_touchback   (ABOVE mode only)
      ctx._intraday_entry_zone_range       (WITHIN mode only)
      ctx._intraday_entry_zone_breakout    (BELOW + WITHIN modes)

    Defensive null path: returns early when ctx.p_code != "A" or no shelf
    detected. All entry_zone attributes set to None on defensive paths.

    Spec: §2.9.
    """
    # Set defaults
    ctx._intraday_entry_zone_mode = None
    ctx._intraday_entry_zone_applicable = False
    ctx._intraday_entry_zone_touchback = None
    ctx._intraday_entry_zone_range = None
    ctx._intraday_entry_zone_breakout = None

    if ctx.p_code != "A":
        return
    if not getattr(ctx, '_intraday_shelf_detected', False):
        return

    shelf_upper = ctx._intraday_shelf_upper  # raw price units
    shelf_lower = ctx._intraday_shelf_lower
    position = ctx._intraday_shelf_position
    atr_raw = ctx.state.atr_raw  # hourly ATR (raw)

    if atr_raw is None or atr_raw <= 0:
        return  # defensive — entry zone undefined without ATR

    confirmation_buffer = INTRADAY_ENTRY_CONFIRMATION_ATR_MULT * atr_raw

    ctx._intraday_entry_zone_mode = position
    ctx._intraday_entry_zone_applicable = True

    if position == "ABOVE":
        # Touchback to shelf upper as support — zone-occupation entry
        ctx._intraday_entry_zone_touchback = {
            'zone_lower_raw': shelf_upper,
            'zone_upper_raw': shelf_upper + confirmation_buffer,
            'trigger': 'Touch of shelf upper as support',
            'stop_ref': 'tactical_stop.shelf_structural.price',
            'target_ref': 'near_term_target.primary',
        }
    elif position == "BELOW":
        # Breakout above shelf upper — trigger-event entry with dual anchors
        ctx._intraday_entry_zone_breakout = {
            'trigger_structural_raw': shelf_upper,
            'trigger_confirmed_raw': shelf_upper + confirmation_buffer,
            'trigger': 'Close above shelf upper',
            'stop_ref': 'tactical_stop.shelf_structural.price',
            'target_ref': 'near_term_target.primary',
        }
    elif position == "WITHIN":
        # Dual alternates — range hold + range expansion
        ctx._intraday_entry_zone_range = {
            'zone_lower_raw': shelf_lower,
            'zone_upper_raw': shelf_lower + confirmation_buffer,
            'trigger': 'Long inside shelf near lower bound, expecting drift toward upper',
            'stop_ref': 'tactical_stop.shelf_structural.price.range',
            'target_implied_raw': shelf_upper,
        }
        ctx._intraday_entry_zone_breakout = {
            'trigger_structural_raw': shelf_upper,
            'trigger_confirmed_raw': shelf_upper + confirmation_buffer,
            'trigger': 'Close above shelf upper',
            'stop_ref': 'tactical_stop.shelf_structural.price.breakout',
            'target_ref': 'near_term_target.primary',
        }
```

**Helper inserted after `_compute_intraday_tactical_levels`** in compute.py module body. Added to `__all__`.

**Raw-vs-scaled price convention:** the helper writes raw (unscaled) prices to ctx attributes using the `_raw` suffix. Output-layer `_assemble_intraday_tactical` performs the `/ price_scaler` conversion for display (consistent with v1.0 convention for all `_intraday_*_raw` ctx attributes — Hand-Back §3.3 item 2).

### 4.6 main.py — Helper call order (v1.1 addition)

The v1.0 implementation inserts three sequential ITS helpers between `_compute_volume_at_price` (VOL-001, `main.py:233`) and `_compute_rally_state_for_ctx` (RLY-001, `main.py:252` post-v1.0). v1.1 adds a fourth helper:

```python
# v1.0:
_detect_intraday_events(ctx)
_detect_compression_shelf(ctx)
_compute_intraday_tactical_levels(ctx)

# v1.1 — add fourth helper:
_compute_entry_zone(ctx)
```

`_compute_entry_zone` reads ctx state written by `_detect_compression_shelf` (sequential dependency). It does NOT depend on `_compute_intraday_tactical_levels` — the entry zone computation is independent of tactical_stop computation (both read shelf state independently). Placement after `_compute_intraday_tactical_levels` is by convention (preserve helper ordering: events → shelf detect → tactical levels → entry zone), not by dependency.

Compute import extended to include `_compute_entry_zone`.

### 4.7 output.py — `_assemble_intraday_tactical` helper (v1.1 modified)

The v1.0 helper assembles the four sub-objects (shelf, lookback_status, tactical_stop, near_term_target) and 18 flat keys. **v1.1 amendments:**

1. **Add `entry_zone` block emission** — fifth sub-object alongside the existing four.
2. **Rewrite `tactical_stop.shelf_structural.desc` for renamed keys** — emit using `range` / `breakout` instead of `fade_to_upper` / `breakout_above`.
3. **Enrich all four (now five) sub-objects' desc strings per §3.5 three-sentence template (DQ-D1) + cross-reference convention (DQ-D2).**
4. **Update `lookback_status.affected_fields` enumeration** — use `trade_setup.stop.hierarchy[ESTABLISHED_LOW]` / `trade_setup.target.hierarchy[DAILY_HIGH]` / `trade_setup.stop.hierarchy[AVWAP_10BAR]` paths.
5. **Add new flat keys for entry_zone** — listed in §4.5.4 below.

#### 4.7.1 entry_zone block emission (NEW)

Inserted in `_assemble_intraday_tactical` after the `near_term_target` block (mirrors the §4.5 sub-object sequencing):

```python
# --- entry_zone sub-object (v1.1) ---
ez_applicable = getattr(ctx, '_intraday_entry_zone_applicable', False)
ez_mode = getattr(ctx, '_intraday_entry_zone_mode', None)

if not ez_applicable:
    entry_zone_block = {
        "applicable": False,
        "mode": None,
        "desc": "No qualifying compression shelf — entry_zone not emitted."
    }
else:
    entry_zone_block = {
        "applicable": True,
        "mode": ez_mode,
    }

    # Touchback (ABOVE mode)
    tb_raw = getattr(ctx, '_intraday_entry_zone_touchback', None)
    if tb_raw is not None:
        zl = round(tb_raw['zone_lower_raw'] / ctx.price_scaler, 2)
        zu = round(tb_raw['zone_upper_raw'] / ctx.price_scaler, 2)
        target_price = nt_primary.get('price') if nt_primary else None
        target_str = f"${target_price}" if target_price is not None else "primary near-term target"
        entry_zone_block["touchback"] = {
            "zone_lower": zl,
            "zone_upper": zu,
            "trigger": tb_raw['trigger'],
            "stop_ref": tb_raw['stop_ref'],
            "target_ref": tb_raw['target_ref'],
            "desc": (
                f"Touchback long entry zone ${zl}–${zu} — buy retrace to shelf upper as support. "
                f"Stop per tactical_stop.shelf_structural.price; target {target_str}. "
                f"Invalidates if price closes below shelf upper without recovery."
            ),
        }

    # Range (WITHIN mode alternate 1)
    rg_raw = getattr(ctx, '_intraday_entry_zone_range', None)
    if rg_raw is not None:
        zl = round(rg_raw['zone_lower_raw'] / ctx.price_scaler, 2)
        zu = round(rg_raw['zone_upper_raw'] / ctx.price_scaler, 2)
        ti = round(rg_raw['target_implied_raw'] / ctx.price_scaler, 2)
        entry_zone_block["range"] = {
            "zone_lower": zl,
            "zone_upper": zu,
            "trigger": rg_raw['trigger'],
            "stop_ref": rg_raw['stop_ref'],
            "target_implied": ti,
            "desc": (
                f"Range-play entry zone ${zl}–${zu} — buy near shelf lower expecting drift toward upper ${ti}. "
                f"Stop per tactical_stop.shelf_structural.price.range. "
                f"Invalidates if price closes below shelf lower (range breakdown)."
            ),
        }

    # Breakout (BELOW + WITHIN modes; dual anchors)
    bo_raw = getattr(ctx, '_intraday_entry_zone_breakout', None)
    if bo_raw is not None:
        ts = round(bo_raw['trigger_structural_raw'] / ctx.price_scaler, 2)
        tc = round(bo_raw['trigger_confirmed_raw'] / ctx.price_scaler, 2)
        target_price = nt_primary.get('price') if nt_primary else None
        target_str = f"${target_price}" if target_price is not None else "primary near-term target"
        stop_ref_path = bo_raw['stop_ref']
        entry_zone_block["breakout"] = {
            "trigger_structural": ts,
            "trigger_confirmed": tc,
            "trigger": bo_raw['trigger'],
            "stop_ref": stop_ref_path,
            "target_ref": bo_raw['target_ref'],
            "desc_structural": (
                f"Structural breakout trigger ${ts} — bare close above shelf upper. "
                f"Use for early entry tolerating wick risk. "
                f"Invalidates if close reverses back below ${ts} within evaluation bar."
            ),
            "desc_confirmed": (
                f"Confirmed breakout trigger ${tc} — close above shelf upper plus 0.25× Hourly ATR buffer. "
                f"Filters wick fakeouts at cost of worse fill. "
                f"Invalidates if close reverses back below shelf upper after triggering."
            ),
        }
```

#### 4.7.2 tactical_stop desc enrichment (v1.1 amendment)

Existing v1.0 tactical_stop desc strings rewritten per §3.5 three-sentence template:

```python
# v1.0 (deprecated):
ss['desc'] = (f"WITHIN-shelf stop alternates: fade_to_upper "
              f"${ss['price']['fade_to_upper']}, breakout_above "
              f"${ss['price']['breakout_above']}.")

# v1.1 (canonical):
if isinstance(ss['price'], dict):
    range_price = ss['price']['range']
    breakout_price = ss['price']['breakout']
    shelf_lower = round(ctx._intraday_shelf_lower / ctx.price_scaler, 2)
    shelf_upper = round(ctx._intraday_shelf_upper / ctx.price_scaler, 2)
    ss['desc'] = (
        f"WITHIN-shelf dual stop alternates: range ${range_price} "
        f"(0.4× Hourly ATR below shelf lower ${shelf_lower}) supports range-play long; "
        f"breakout ${breakout_price} (0.3× Hourly ATR inside shelf upper ${shelf_upper}) "
        f"supports breakout-play long. Each invalidates if corresponding shelf boundary breaks."
    )
else:
    anchor_word = "below shelf lower" if ss['anchor'] == 'shelf_lower' else "inside shelf upper (breakout failure)"
    shelf_ref = ("shelf lower" if ss['anchor'] == 'shelf_lower' else "shelf upper")
    ss['desc'] = (
        f"Tactical stop ${ss['price']} — {ss['atr_buffer_mult']}× Hourly ATR {anchor_word}. "
        f"Supports the {'breakout' if 'breakout' in anchor_word else 'directional'} entry mechanic. "
        f"Invalidates if {shelf_ref} fails to hold."
    )
```

Similarly for `atr_volatility` desc:

```python
# v1.0 (deprecated):
av['desc'] = (f"Stop at ${av['price']} ({av['atr_mult']}x Hourly ATR "
              f"from current price).")

# v1.1 (canonical):
av['desc'] = (
    f"Volatility-based stop ${av['price']} — {av['atr_mult']}× Hourly ATR below current price. "
    f"Methodology-independent of shelf structure; supports stops when shelf-based stops are absent. "
    f"Invalidates as a backstop only — supersedes when shelf_structural unavailable."
)
```

#### 4.7.3 shelf, lookback_status, near_term_target desc enrichment

**shelf desc (v1.1):**

```python
# Non-stale:
shelf_block["desc"] = (
    f"Compression shelf $({shelf_lower_display}–{shelf_upper_display}) over "
    f"{bar_count} hourly bars; width {tightness_ratio:.2f}× Daily ATR; position: {position}. "
    f"Acts as intraday-tactical reference for entry, stop, and target levels."
)
# (Stale appendix preserved from v1.0 — adds " (LOOKBACK_STALE)" suffix)
```

**lookback_status desc (v1.1)** — embedded in stale-affected fields phrasing; new field added:

```python
if stale:
    lookback_status_block["desc"] = (
        f"Lookback-stale flag set — {event_type} event {event_bars_ago} bars ago "
        f"invalidates short-window references in: {', '.join(affected_fields)}. "
        f"Operator-facing transparency only; not a verdict modifier."
    )
else:
    lookback_status_block["desc"] = (
        f"No regime-shift event in 10-bar lookback. Short-window references (ESTABLISHED_LOW, "
        f"DAILY_HIGH, AVWAP_10BAR) carry no stale annotation. "
        f"Window clear for the evaluated bar."
    )
```

**near_term_target desc (v1.1)** — applied to primary + secondary desc strings inside the existing emission logic. Enrichment maintains v1.0 source-label conventions (INTRADAY_HIGH / SHELF_UPPER_PROJECTION / SHELF_WIDTH_PROJECTION / EXTENDED_RANGE_PROJECTION / NOT_APPLICABLE).

#### 4.7.4 New entry_zone flat keys

Add to the flat_keys dict in `_assemble_intraday_tactical` (Profile A only):

```python
flat_keys.update({
    "Intraday_Entry_Zone_Mode": ez_mode,
    "Intraday_Entry_Zone_Applicable": ez_applicable,
    "Intraday_Entry_Touchback_Zone_Lower": (
        round(tb_raw['zone_lower_raw'] / ctx.price_scaler, 2) if tb_raw else None
    ),
    "Intraday_Entry_Touchback_Zone_Upper": (
        round(tb_raw['zone_upper_raw'] / ctx.price_scaler, 2) if tb_raw else None
    ),
    "Intraday_Entry_Range_Zone_Lower": (
        round(rg_raw['zone_lower_raw'] / ctx.price_scaler, 2) if rg_raw else None
    ),
    "Intraday_Entry_Range_Zone_Upper": (
        round(rg_raw['zone_upper_raw'] / ctx.price_scaler, 2) if rg_raw else None
    ),
    "Intraday_Entry_Range_Target_Implied": (
        round(rg_raw['target_implied_raw'] / ctx.price_scaler, 2) if rg_raw else None
    ),
    "Intraday_Entry_Breakout_Trigger_Structural": (
        round(bo_raw['trigger_structural_raw'] / ctx.price_scaler, 2) if bo_raw else None
    ),
    "Intraday_Entry_Breakout_Trigger_Confirmed": (
        round(bo_raw['trigger_confirmed_raw'] / ctx.price_scaler, 2) if bo_raw else None
    ),
})
```

**9 new flat keys** for entry_zone. Total v1.1 flat-key count: 18 (v1.0) + 9 (v1.1) = **27 `Intraday_*` flat keys**.

#### 4.7.5 `_ITS_NULL_FLAT_KEYS` extension

The 9 new entry_zone flat keys are added to `_ITS_NULL_FLAT_KEYS` (v1.0 dict, output.py) with `None` values. Profile B/C paths continue to emit all-null flat keys.

### 4.8 transform.py — Flat-Key Registration + lookback_stale annotation paths (v1.1 amendments)

1. **Register 9 new entry_zone flat keys** in `_all_mapped_flat_keys()` — append to the existing 18-key ITS block (Hand-Back §3.4 item 1):

```python
keys.update([
    # ... existing 18 v1.0 ITS keys ...
    # v1.1 entry_zone flat keys:
    "Intraday_Entry_Zone_Mode",
    "Intraday_Entry_Zone_Applicable",
    "Intraday_Entry_Touchback_Zone_Lower",
    "Intraday_Entry_Touchback_Zone_Upper",
    "Intraday_Entry_Range_Zone_Lower",
    "Intraday_Entry_Range_Zone_Upper",
    "Intraday_Entry_Range_Target_Implied",
    "Intraday_Entry_Breakout_Trigger_Structural",
    "Intraday_Entry_Breakout_Trigger_Confirmed",
])
```

2. **Top-level group emission** — unchanged from v1.0 (`result["intraday_tactical"]` reads sentinel key from flat_metrics). The block-internal `entry_zone` sub-object emerges naturally from the v1.0 sentinel-key mechanism — no transform.py code change needed for entry_zone schema emission.

3. **Per-field `lookback_stale` annotation** — v1.0 implementation correctly annotates by label-match in floor-side + target-side hierarchy entries (Hand-Back §3.4 item 3). v1.1 amendment is **narrative-only** — no transform.py code change. The engine already annotates `ESTABLISHED_LOW` + `AVWAP_10BAR` in `trade_setup.stop.hierarchy` (and `trade_setup.stop.overhead_levels` when applicable) and `DAILY_HIGH` in `trade_setup.target.hierarchy`. v1.1 spec text canonicalizes the engine-actual paths.

### 4.9 types.py — RunContext attribute declarations (v1.1 additions)

Add the following attribute declarations to `RunContext` dataclass, all defaulting to None/False:

```python
# ITS-001 v1.1: entry_zone attributes (Profile A only)
_intraday_entry_zone_mode: Optional[str] = None
_intraday_entry_zone_applicable: bool = False
_intraday_entry_zone_touchback: Optional[Dict] = None
_intraday_entry_zone_range: Optional[Dict] = None
_intraday_entry_zone_breakout: Optional[Dict] = None
```

Inserted immediately after the existing 18 v1.0 `_intraday_*` declarations.

---

## 5. Pipeline & Call-Order

ITS pipeline at end of Phase 2 v1.1:

| Stage | Tier | Helper | Location |
|---|---|---|---|
| Compute | 3 (pre-gate) | `_detect_intraday_events(ctx)` | `compute.py` (v1.0) |
| Compute | 3 (pre-gate) | `_detect_compression_shelf(ctx)` | `compute.py` (v1.0) |
| Compute | 3 (pre-gate) | `_compute_intraday_tactical_levels(ctx)` | `compute.py` (v1.0, v1.1 internal-rename) |
| Compute | 3 (pre-gate) | `_compute_entry_zone(ctx)` | `compute.py` (v1.1 NEW) |
| Gates | 4–7 | (no ITS gate participation — verdict invariance preserved) | — |
| Output | 8 | `_assemble_intraday_tactical(ctx, p_code)` | `output.py` (v1.0, v1.1 desc + entry_zone block) |
| Output | 8 | `_assemble_output` call site (sentinel-key stash) | `output.py` (v1.0, unchanged) |
| Transform | 9 | `_transform_output` top-level group emission | `transform.py` (v1.0, unchanged) |
| Transform | 9 | per-field lookback_stale annotation (label-match) | `transform.py` (v1.0, unchanged) |

**Call-order verification (§11.6 item 5):** four ITS compute helpers run sequentially. `_compute_entry_zone` reads ctx state written by `_detect_compression_shelf`; placement after `_compute_intraday_tactical_levels` is convention, not dependency.

**Co-implementation discipline (DQ-INT-1):** Item 4 vocabulary rename and Item 5 entry_zone are co-implemented in a single Phase 2 pass. entry_zone descs reference renamed stop keys via `stop_ref` paths (e.g., `stop_ref: "tactical_stop.shelf_structural.price.range"`); sequencing the rename separately would break entry_zone reference integrity at the v1.0 → v1.1 boundary. The Phase 2 Brief must enforce single-PR (or single working-tree commit-set) discipline.

---

## 6. Test Plan

v1.1 amendments to the existing `test_its001_intraday_tactical.py` (per DQ-INT-2 — same file, preserves cohort cohesion).

### 6.1 New test classes (v1.1)

| # | Class | Tests | Coverage |
|---|---|---:|---|
| 22 | `TestITS001EntryZoneABOVE` | 4 | touchback emitted only on ABOVE / zone_lower equals shelf.upper / zone_upper equals shelf.upper + 0.25×ATR / stop_ref + target_ref strings |
| 23 | `TestITS001EntryZoneBELOW` | 4 | breakout emitted only on BELOW / trigger_structural equals shelf.upper / trigger_confirmed equals shelf.upper + 0.25×ATR / dual desc strings present |
| 24 | `TestITS001EntryZoneWITHIN` | 6 | both range + breakout emitted / range zone fields correct / range target_implied equals shelf.upper / breakout dual anchors correct / range stop_ref includes `.range` suffix / breakout stop_ref includes `.breakout` suffix |
| 25 | `TestITS001EntryZoneNoShelf` | 3 | applicable false / mode null / desc field present / no sub-keys (touchback/range/breakout) emitted |
| 26 | `TestITS001EntryZoneProfileScope` | 2 | Profile B emits no entry_zone (all flat keys null) / Profile C emits no entry_zone |
| 27 | `TestITS001EntryZoneFlatKeyRegistration` | 1 | All 9 entry_zone flat keys registered in MAPPED_FLAT_KEYS |
| 28 | `TestITS001EntryZoneVocabulary` | 3 | static assertions: no `_long` suffix in any entry_zone key / `range` + `breakout` reused across tactical_stop and entry_zone with identical semantics / no `fade_to_upper`/`breakout_above` references in v1.1 output |
| 29 | `TestITS001V11VocabularyRename` | 4 | tactical_stop WITHIN price.range emitted (not fade_to_upper) / tactical_stop WITHIN price.breakout emitted (not breakout_above) / atr_buffer_mult mirror / no flat-key rename (Intraday_Stop_Shelf_Structural unchanged) |
| 30 | `TestITS001V11DescEnrichment` | 5 | all desc strings ≤40 words / three-sentence template detected (rough heuristic: 2+ period delimiters) / cross-references use bare-name within block / cross-references use full-path for trade_snapshot.atr.value / lookback_status.affected_fields uses trade_setup.stop.hierarchy paths |

**v1.1 new tests subtotal: 32 tests across 9 new classes.**

### 6.2 Modified existing test classes (v1.1)

| # | Class | Modification |
|---|---|---|
| 7 | `TestITS001TacticalStopWITHIN` | Rename method names + assertions: `fade_to_upper` → `range`, `breakout_above` → `breakout`. Tests verify renamed dict-key emission. Count unchanged (3 tests). |
| 13 | `TestITS001LookbackStaleAnnotation` | Update affected_fields assertion: `trade_setup.stop.hierarchy[ESTABLISHED_LOW]` / `trade_setup.target.hierarchy[DAILY_HIGH]` / `trade_setup.stop.hierarchy[AVWAP_10BAR]`. Count unchanged (5 tests). |

### 6.3 v1.1 test catalog summary

| Source | Tests | Classes |
|---|---:|---:|
| v1.0 (existing, unchanged) | 67 | 19 |
| v1.0 (existing, modified for v1.1 — class names retained) | 8 | 2 |
| v1.1 (new) | 32 | 9 |
| **v1.1 total** | **107** | **30** |

Phase 2 v1.1 implementer adds 32 new tests + modifies 8 existing tests; net delta `+32` from v1.0 baseline of 75.

### 6.4 Verdict-invariance and schema-stability discipline

`TestITS001VerdictInvariance` (v1.0 #17) and `TestITS001NotInGatesFile` (v1.0 #20) continue to enforce:
- No `Intraday_*` / `_intraday_*` / `intraday_tactical` / `entry_zone` tokens in any `_gate_*` function body
- Verdict invariance across pre-/post-v1.1 fixtures (synthetic — no new gate inputs added)

`TestITS001SchemaStability` (v1.0 #19) updated to assert v1.1 schema (entry_zone sub-object presence + 9 new flat keys registered).

---

## 7. Closure Criteria

v1.1 closes when ALL of:

1. **Phase 2 v1.1 Hand-Back delivered** with diff-stat + file SHAs + test counts.
2. **All §6 tests pass** (107 total): 32 new v1.1 + 8 modified + 67 unchanged v1.0.
3. **Zero ITS-caused regressions** on full pytest cohort. Baseline at v1.1 Phase 2 entry: 3173/4/1 per Hand-Back §5 v1.0 close.
4. **Engine runs cleanly on at least 1 Profile A test ticker per shelf position** (ABOVE / BELOW / WITHIN) with `entry_zone` block rendering correctly in output JSON.
5. **Phase 3 live cohort:** ≥5 Profile A tickers across ABOVE / BELOW / WITHIN positions + ≥1 `lookback_stale=true` witness + ≥1 `lookback_stale=false` witness. v1.0 Phase 3 cohort was deferred — v1.1 absorbs the Phase 3 requirement. Operator-led IBKR validation; cohort selection at Operator discretion.
6. **Verdict invariance confirmed across live cohort pre-/post-v1.1** (static defense in place via `TestITS001NotInGatesFile` + `TestITS001VerdictInvariance` + `TestITS001EntryZoneVocabulary`).
7. **6-doc DIA cascade complete** at v1.1 Phase 4: Doc 2 §VI / §IV substantive (entry_zone schema + rename + desc convention codification), Doc 7 Step 6 substantive (operator reading guidance for entry_zone interpretation), Doc 8 §II Layer 2 mirror, EEM verify-only, README + PEO Tier closure.
8. **Bug Register ITS-001 master row advances** 🟠 SPECIFIED → 🟡 IMPLEMENTED → 🟢 SYNCED → ✅ CLOSED. No sub-entries per memo §8.

---

## 8. Worked Examples

Concrete `intraday_tactical` block output for v1.1 against the four live engine outputs provided at this session start (PLTR, IONQ, VRT, COHR — all Profile A C2). All four cohort tickers are in WITHIN-position state (or no-shelf for IONQ); no ABOVE / BELOW samples in this snapshot. Phase 3 cohort will capture ABOVE/BELOW witnesses.

### 8.1 Example A — COHR (WITHIN, $377.42 between shelf $370.18–$382.00)

Hourly ATR $7.78; Daily ATR $26.02.

```json
"intraday_tactical": {
  "shelf": {
    "detected": true,
    "upper": 382.00,
    "lower": 370.18,
    "bar_count": 5,
    "tightness_ratio": 0.45,
    "position": "WITHIN",
    "lookback_stale": false,
    "desc": "Compression shelf $(370.18–382.00) over 5 hourly bars; width 0.45× Daily ATR; position: WITHIN. Acts as intraday-tactical reference for entry, stop, and target levels."
  },
  "lookback_status": {
    "stale": false,
    "event_type": null,
    "event_timestamp": null,
    "event_bars_ago": null,
    "event_magnitude_pct": null,
    "event_magnitude_atr": null,
    "rvol_at_event": null,
    "affected_fields": [],
    "desc": "No regime-shift event in 10-bar lookback. Short-window references (ESTABLISHED_LOW, DAILY_HIGH, AVWAP_10BAR) carry no stale annotation. Window clear for the evaluated bar."
  },
  "tactical_stop": {
    "shelf_structural": {
      "price": {"range": 367.07, "breakout": 379.67},
      "anchor": "both",
      "atr_buffer_mult": {"range": 0.4, "breakout": 0.3},
      "atr_value_used": 7.78,
      "desc": "WITHIN-shelf dual stop alternates: range $367.07 (0.4× Hourly ATR below shelf lower $370.18) supports range-play long; breakout $379.67 (0.3× Hourly ATR inside shelf upper $382.00) supports breakout-play long. Each invalidates if corresponding shelf boundary breaks."
    },
    "atr_volatility": {
      "price": 365.75,
      "atr_mult": 1.5,
      "atr_value_used": 7.78,
      "desc": "Volatility-based stop $365.75 — 1.5× Hourly ATR below current price. Methodology-independent of shelf structure; supports stops when shelf-based stops are absent. Invalidates as a backstop only — supersedes when shelf_structural unavailable."
    }
  },
  "near_term_target": {
    "mode": "WITHIN",
    "primary": {"price": null, "source": "NOT_APPLICABLE",
                "desc": "Directionally neutral (WITHIN shelf) — no primary target emitted. Operator reads tactical_stop + entry_zone alternates for both directional plays."},
    "secondary": {"price": null, "source": "NOT_APPLICABLE",
                  "desc": "Directionally neutral (WITHIN shelf) — no secondary target emitted."},
    "applicable": false
  },
  "entry_zone": {
    "applicable": true,
    "mode": "WITHIN",
    "range": {
      "zone_lower": 370.18,
      "zone_upper": 372.13,
      "trigger": "Long inside shelf near lower bound, expecting drift toward upper",
      "stop_ref": "tactical_stop.shelf_structural.price.range",
      "target_implied": 382.00,
      "desc": "Range-play entry zone $370.18–$372.13 — buy near shelf lower expecting drift toward upper $382.00. Stop per tactical_stop.shelf_structural.price.range. Invalidates if price closes below shelf lower (range breakdown)."
    },
    "breakout": {
      "trigger_structural": 382.00,
      "trigger_confirmed": 383.95,
      "trigger": "Close above shelf upper",
      "stop_ref": "tactical_stop.shelf_structural.price.breakout",
      "target_ref": "near_term_target.primary",
      "desc_structural": "Structural breakout trigger $382.00 — bare close above shelf upper. Use for early entry tolerating wick risk. Invalidates if close reverses back below $382.00 within evaluation bar.",
      "desc_confirmed": "Confirmed breakout trigger $383.95 — close above shelf upper plus 0.25× Hourly ATR buffer. Filters wick fakeouts at cost of worse fill. Invalidates if close reverses back below shelf upper after triggering."
    }
  }
}
```

### 8.2 Example B — IONQ (no shelf, $63.63 at TRENDING engine state)

Hourly ATR $1.95. No qualifying compression shelf (no 4–10 bar window with width ≤ 0.5× Daily ATR).

```json
"intraday_tactical": {
  "shelf": {
    "detected": false,
    "desc": "No qualifying compression shelf (no 4-10 bar window with width <= 0.5x Daily ATR). Intraday-tactical surface degraded: tactical_stop emits atr_volatility only; near_term_target and entry_zone not applicable."
  },
  "lookback_status": {
    "stale": false,
    "event_type": null,
    "affected_fields": [],
    "desc": "No regime-shift event in 10-bar lookback. Short-window references (ESTABLISHED_LOW, DAILY_HIGH, AVWAP_10BAR) carry no stale annotation. Window clear for the evaluated bar."
  },
  "tactical_stop": {
    "shelf_structural": null,
    "atr_volatility": {
      "price": 60.71,
      "atr_mult": 1.5,
      "atr_value_used": 1.95,
      "desc": "Volatility-based stop $60.71 — 1.5× Hourly ATR below current price. Methodology-independent of shelf structure; supports stops when shelf-based stops are absent. Invalidates as a backstop only — supersedes when shelf_structural unavailable."
    }
  },
  "near_term_target": {
    "mode": null,
    "primary": {"price": null, "source": "NOT_APPLICABLE", "desc": "..."},
    "secondary": {"price": null, "source": "NOT_APPLICABLE", "desc": "..."},
    "applicable": false
  },
  "entry_zone": {
    "applicable": false,
    "mode": null,
    "desc": "No qualifying compression shelf — entry_zone not emitted."
  }
}
```

### 8.3 Example C — PLTR (WITHIN, $136.80 between shelf $135.72–$137.77)

Hourly ATR $1.46. Tight shelf.

```json
"entry_zone": {
  "applicable": true,
  "mode": "WITHIN",
  "range": {
    "zone_lower": 135.72,
    "zone_upper": 136.09,
    "trigger": "Long inside shelf near lower bound, expecting drift toward upper",
    "stop_ref": "tactical_stop.shelf_structural.price.range",
    "target_implied": 137.77,
    "desc": "Range-play entry zone $135.72–$136.09 — buy near shelf lower expecting drift toward upper $137.77. Stop per tactical_stop.shelf_structural.price.range. Invalidates if price closes below shelf lower (range breakdown)."
  },
  "breakout": {
    "trigger_structural": 137.77,
    "trigger_confirmed": 138.14,
    "trigger": "Close above shelf upper",
    "stop_ref": "tactical_stop.shelf_structural.price.breakout",
    "target_ref": "near_term_target.primary",
    "desc_structural": "Structural breakout trigger $137.77 — bare close above shelf upper. Use for early entry tolerating wick risk. Invalidates if close reverses back below $137.77 within evaluation bar.",
    "desc_confirmed": "Confirmed breakout trigger $138.14 — close above shelf upper plus 0.25× Hourly ATR buffer. Filters wick fakeouts at cost of worse fill. Invalidates if close reverses back below shelf upper after triggering."
  }
}
```

(Range zone is narrow given hourly_atr $1.46 — 0.25× ATR = $0.37 — illustrating that the entry_zone width scales naturally to ticker volatility.)

### 8.4 Example D — Hypothetical ABOVE mode

(No live cohort sample at this session; constructed for spec clarity. Real validation pending Phase 3.)

Ticker XYZ at $150.00, shelf $146.00–$148.50 (price has broken out above), Hourly ATR $0.80.

```json
"entry_zone": {
  "applicable": true,
  "mode": "ABOVE",
  "touchback": {
    "zone_lower": 148.50,
    "zone_upper": 148.70,
    "trigger": "Touch of shelf upper as support",
    "stop_ref": "tactical_stop.shelf_structural.price",
    "target_ref": "near_term_target.primary",
    "desc": "Touchback long entry zone $148.50–$148.70 — buy retrace to shelf upper as support. Stop per tactical_stop.shelf_structural.price; target $150.40. Invalidates if price closes below shelf upper without recovery."
  }
}
```

### 8.5 Example E — Hypothetical BELOW mode

Ticker XYZ at $144.00, shelf $146.00–$148.50 (price has broken down below), Hourly ATR $0.80.

```json
"entry_zone": {
  "applicable": true,
  "mode": "BELOW",
  "breakout": {
    "trigger_structural": 148.50,
    "trigger_confirmed": 148.70,
    "trigger": "Close above shelf upper",
    "stop_ref": "tactical_stop.shelf_structural.price",
    "target_ref": "near_term_target.primary",
    "desc_structural": "Structural breakout trigger $148.50 — bare close above shelf upper. Use for early entry tolerating wick risk. Invalidates if close reverses back below $148.50 within evaluation bar.",
    "desc_confirmed": "Confirmed breakout trigger $148.70 — close above shelf upper plus 0.25× Hourly ATR buffer. Filters wick fakeouts at cost of worse fill. Invalidates if close reverses back below shelf upper after triggering."
  }
}
```

---

## 9. v1.x Promotion Paths + Calibration Items (Spec-Text Concepts)

Per memo §8 directive, no new Bug Register entries during v1.1 cycle. The following items remain spec-text concepts in v1.1 — Bug Register promotion deferred or permanently declined per item.

### 9.1 Calibration items (Phase 3 live-data review pending)

| Spec-text ID | Description |
|---|---|
| `INTRADAY-CAL-1` | 3–6 month live-data threshold review for 0.5× Daily ATR compression-shelf tightness multiplier (DQ-3b lock) |
| `INTRADAY-CAL-2` | 3–6 month live-data threshold review for v1.0 stop multipliers (0.4× range / 0.3× breakout / 1.5× volatility — DQ-4b legacy lock) |
| `INTRADAY-CAL-3` | 3–6 month live-data threshold review for v1.1 entry confirmation multiplier (0.25× — DQ-E3 lock) |

### 9.2 v1.x promotion candidates (out of v1.1 scope)

| Spec-text ID | Description |
|---|---|
| `INTRADAY-CFL-INTEGRATION-1` | v1.x promotion path: promote shelf upper/lower to hierarchies for CFL-001 cross-surface confluence |
| `INTRADAY-OPENING-RANGE-1` | Opening-range shelf as separate `intraday_tactical.opening_range` block (Raschke/Williams ORB tradition) |
| `INTRADAY-VOLUME-PROFILE-1` | Volume profile / POC / accumulation-vs-distribution classification on shelf |
| `INTRADAY-FINE-GEOMETRY-1` | `NEAR_UPPER` / `NEAR_LOWER` fine-geometry labels (DQ-3d) |
| `INTRADAY-15M-FRAME-1` | 15m bar-frame promotion if hourly granularity proves insufficient |
| `INTRADAY-PRIOR-SESSION-1` | Prior-session shelves (cross-session lookback) |
| `INTRADAY-FLOOR-ANNOTATION-1` | Explicit `relative_to_structural_floor` annotation field (DQ-6c follow-up) |
| `INTRADAY-AVWAP-STOP-1` | `avwap_anchored` stop variant (Shannon AVWAP-anchored stop) |
| `INTRADAY-SIGNAL-BAR-STOP-1` | `signal_bar` stop variant (Brooks signal-bar protective stop) |
| `INTRADAY-TRAILING-STOP-1` | Trailing-stop variant (Chandelier Exit / Parabolic SAR) |
| `INTRADAY-AVWAP-TARGET-1` | AVWAP-intersection targets (Shannon opposing-AVWAP) |
| `INTRADAY-R-MULTIPLE-1` | R-multiple targets (Van Tharp 2R / 3R sizing-derived) |
| `INTRADAY-BBAND-TARGET-1` | Bollinger band targets |
| `INTRADAY-FIB-EXT-1` | Fibonacci extension projections (tracked separately as `ENG-006` 🟤 CONCEPT in Bug Register) |

### 9.3 Permanently out of scope

| Item | Reason |
|---|---|
| Short-side `entry_zone` + `tactical_stop` alternates | IBKR cash account constraint — TBS Operator cannot place short positions. Permanent structural exclusion, not a deferral. v1.1 §1.4 codifies. |
| Profile B / Profile C extension of ITS | Intraday-tactical management not natural to daily/weekly profiles. v1.0 §1.2 / v1.1 §1.2 lock. |

---

## 10. Acceptance

Phase 2 v1.1 implementer accepts when:
- All §6 tests pass (107 total)
- Zero regression failures on full pytest cohort (baseline 3173/4/1 per v1.0 Hand-Back §5)
- Engine runs cleanly on at least 1 Profile A test ticker per shelf position (ABOVE / BELOW / WITHIN + no-shelf) with `intraday_tactical` group rendering per §8 worked examples
- Co-implementation discipline (DQ-INT-1) preserved: rename + entry_zone landed in single working-tree commit set

---

## 11. Pre-Implementation Checklist (§11.6 Mirror, v1.1)

Per SIR §11.6 (codified S162 via GOV-003), this checklist is the spec-side defense layer mirroring the Phase 2 Brief §4 implementation-side defense. v1.0 v1.0.1 baseline §11 verifications carry forward; v1.1 specifically re-audits the items affected by Item 4 + Item 5 changes.

| # | §11.6 Item | Status at v1.1 spec delivery | Evidence anchor |
|---|---|---|---|
| 1 | **Call-order verification** — v1.1 adds `_compute_entry_zone(ctx)` as 4th sequential ITS helper between v1.0's `_compute_intraday_tactical_levels` and `_compute_rally_state_for_ctx` | ✅ VERIFIED — v1.0 v1.0.1 baseline at `main.py:233-252` has all three ITS helpers correctly sequenced pre-gate. v1.1 4th helper inserts in same pre-gate window. | v1.0 Hand-Back §3.5 + `main.py` master (post-S165 commit) |
| 2 | **Sort-order check** — N/A. entry_zone operates on scalars (shelf bounds, ATR, current price), not iterables | ✅ N/A | — |
| 3 | **Shared-reference / partition-leak audit** — entry_zone block lives inside `intraday_tactical` top-level group, structurally outside BUGR-002 partition (same as v1.0 — DQ-6 lock) | ✅ VERIFIED by design (DQ-6). | `transform.py` master post-S165; partition sites at `transform.py:3152` (target side) + `transform.py:3444` (stop side); entry_zone block emission is post-partition by structure |
| 4 | **Pipeline-order feasibility** — entry_zone computed at tier 3 (pre-gate) by `_compute_entry_zone`; read at tier 8 (`_assemble_output`); writes guaranteed complete | ✅ VERIFIED — v1.0 sibling helpers run pre-gate per Hand-Back §4 item 4 verification. v1.1 4th helper inherits same pipeline-order. | `main.py:165-294` (v1.0 baseline) |
| 5 | **Call-order feasibility check** — v1.1 adds 1 invocation per Profile A path; `_compute_entry_zone` reads ctx state written by `_detect_compression_shelf`; sequential dependency enforced | ✅ VERIFIED — same call-order discipline as v1.0 §4.8 sibling pattern. | compute.py master (post-v1.1 implementation site) |
| 6 | **Cross-spec layout audit** — entry_zone sub-object key + sub-key set (touchback / range / breakout / trigger_structural / trigger_confirmed / zone_lower / zone_upper / stop_ref / target_ref / target_implied / applicable / mode / trigger) audited for collisions against engine vocabulary | ✅ VERIFIED — §3.2 v1.1 collision audit complete. `range` and `breakout` intentional reuse across tactical_stop (renamed) and entry_zone (new) — semantic alignment, not collision. | transform.py module docstring; collision audit §3 (this spec) |
| 7 | **Storage-mechanism feasibility verification** — entry_zone uses same `_intraday_*` ctx attribute pattern as v1.0 (no `_transform_output` ctx-parameter dependency; sentinel-key flat_metrics stash inherited from v1.0 mechanism) | ✅ VERIFIED — RLY-001 / v1.0 ITS sibling pattern reused identically. `_transform_output` signature unchanged. | `transform.py:1437` (post-S165 baseline); v1.0 sentinel-key idiom at `_assemble_output` |
| 8 | **Downstream-override-path audit** — `intraday_tactical` group is INDEPENDENT of `action_summary.verdict`; neither DD-2 EXIT nor BKOUT-001 GAP-5 verdict overrides touch the new `entry_zone` sub-object or any `Intraday_Entry_*` flat key (per v1.0 DQ-2 emit-on-all-paths lock) | ✅ VERIFIED — by design (DQ-2 lock; v1.1 inherits). entry_zone is a sibling sub-object inside the v1.0-verified-isolated `intraday_tactical` group. | `output.py:1929-1940` (DD-2), `output.py:1947-1961` (BKOUT-001 GAP-5) — v1.0 baseline |
| 9 (v1.0 carryover) | **AVWAP_10BAR resolution** — was DEFERRED to v1.0 Phase 2; resolved as ANNOTATE per Hand-Back §6.1; v1.1 spec narrative codifies the hierarchy-entry framing | ✅ CODIFIED v1.1 (§2.1 + §3.4) | v1.0 Hand-Back §6.1; `transform.py:175` (`_CONVICTION_TIER_MAP` AVWAP_10BAR entry); `transform.py:3241` (hierarchy emission site) |

---

## 12. Sign-off

**Spec authority:** This document is the canonical Phase 1 spec for ITS-001 v1.1, superseding v1.0.1. Any disagreement between this spec and a downstream Brief or implementation: **spec wins**.

**Phase 0 inputs consumed:**
- `TBS_Phase_0_WIP_Intraday_Tactical_Surface_v0_3.md` (v1.0 14 DQs — carried forward)
- `ITS001_v1_1_Phase0_Handoff_Memo_v1_0.md` (v1.1 5 amendment items + scope handoff)
- `ITS001_Phase2_Implementation_HandBack_v1_0.md` (v1.0 §6 deviations + §9 open items + SHAs)
- v1.1 Phase 0 DQ-resolution (this session — 13 DQs locked: V1, V2, V3, E1, E2, E3, E4, E5, E6, D1, D2, INT-1, INT-2)
- 4 live engine outputs at session start (PLTR, IONQ, VRT, COHR — all Profile A C2)

**Engine source verified at SHA `master` HEAD as of 2026-05-26:**
- `compute.py` (2019 lines / 95.1 KB — post-S165 ITS-001 v1.0 commit confirmed)
- v1.0 implementation SHAs per Hand-Back §2 — types.py / compute.py / output.py / transform.py / main.py committed to master

**Decisions consumed at Phase 1 (not re-litigated):**
- All 14 DQ locks from v1.0 Phase 0 WIP v0.3
- All 13 DQ locks from v1.1 Phase 0 (this session)
- Vocabulary collisions audited (§3.2)
- §11.6 spec-side audit complete (9 items VERIFIED/CODIFIED)
- Hand-Back §6.1 (AVWAP_10BAR annotate path) blessed retroactively in §2.1
- Hand-Back §6.2 (path-vs-label vocabulary) corrected in §2.1 + §3.4

**Lifecycle next:**
- Phase 1 v1.1 Brief authoring → `ITS001_v1_1_Claude_Code_CLI_Implementation_Brief_v1_0.md` per ACP §6.4 11-section template
- Brief delivered via `present_files` → Operator copies to working-tree root before Claude Code CLI session
- Phase 2 v1.1 implementation (Claude Code CLI / IntelliJ) — engine amendments + test file updates + v1.1 Hand-Back
- Phase 3 v1.1 live cohort validation (Operator-led IBKR)
- Phase 4 v1.1 DIA cascade (fresh Project chat) + Bug Register ITS-001 master row to ✅ CLOSED

---

## Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-24 (S165) | Phase 1 spec authored from WIP v0.3. 14 DQs transcribed with §11.6 evidence anchors. §3 vocabulary collision audit. §11 Pre-Implementation Checklist (8 items VERIFIED + 1 deferred). §6 test plan (~75 tests across 20 classes). §8 worked examples (RGTI + FSLR). |
| v1.0.1 | 2026-05-24 (S165) | `_derive_intraday_high` pandas-API simplification in §2.7.3 + §4.3. Cosmetic refinement; no behavior change. |
| **v1.1** | **2026-05-26 (S166)** | **Substantive amendment cycle.** Consolidates 5 amendment items from v1.0 Hand-Back §6 deviations + S165 UX critique into single v1.1 spec (replacing planned v1.0.2 cosmetic + Phase 3 against v1.0.1 path). 13 new DQ locks (DQ-V1/V2/V3, DQ-E1/E2/E3/E4/E5/E6, DQ-D1/D2, DQ-INT-1/INT-2). Item 1: AVWAP_10BAR hierarchy-entry canonicalization (§2.1, §3.4). Item 2: path-vs-label vocabulary fix `floor_analysis.hierarchy` → `trade_setup.stop.hierarchy` (§2.1, §3.4, §2.4.4). Item 3: desc string enrichment per three-sentence template, ≤40 words (§3.5, §4.7.2, §4.7.3). Item 4: vocabulary rename `fade_to_upper`/`breakout_above` → `range`/`breakout` (§2.8, §4.4). Item 5: new `entry_zone` sub-object with position-aware structure mirroring `tactical_stop` dual-alternate WITHIN pattern (§2.9, §4.5, §4.7.1). New constant `INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25` (§4.1). 9 new flat keys (§4.7.4). 32 new tests across 9 new classes (§6.1) + 8 modified existing tests (§6.2); v1.1 total 107 tests across 30 classes. §1.4 strengthened — long-only is **permanent structural exclusion** (IBKR cash account constraint), not a v1.x deferral. Bug Register policy: no new ITS sub-entries during v1.1 cycle; spec §9 is the canonical record for 3 calibration items + 14 deferred v1.x promotion paths. Engine source verified at master post-S165; §11.6 spec-side audit complete (9 items). |

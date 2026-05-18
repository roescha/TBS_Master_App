# CFL-001 — Floor and Target Level Confluence Detection — Spec v1.1

**Status:** IMPLEMENTED (Session 157 — first Track 2 / Claude Code process trial)
**Bundle:** Bundle 3 (per PEO Tier 1J)
**Track:** Track 2 (Informational Enhancement per SIR §11.2)
**Bug Register ID:** CFL-001
**Hard prerequisite:** CNV-001 (Bundle 1 / Tier 1H) ✅ CLOSED S154 — satisfied
**Engine source authority:** `layers/tbs_engine/transform.py` per `roescha/TBS_Master_App` `master` at commit `19ba506` (2026-05-17, CFL-001 v1.1 merged) — file SHA verifiable from the hand-back §1
**Supersedes:** Spec v1.0 (S157, same session). See §13 Document History for the v1.0 → v1.1 delta. v1.0 retained as historical record of what was delivered to the standalone Claude Code session.

---

## §1. Purpose

When multiple anchor types of hierarchy entries cluster within a small ATR-scaled price band, the resulting confluence signals a structurally significant zone — what classical technical-analysis literature describes as a high-conviction support or resistance area. The "3-of-4 institutional-grade floor rule" referenced in the PEO Tier 1J scope is the most well-known formulation. CFL-001 introduces engine-level detection of this clustering and emits per-entry `confluence` annotations on the active stop and target hierarchies.

The output is **informational**. CFL-001 does not gate verdicts. It does not modify floor or target prices. It does not modify hierarchy sort order. It annotates existing hierarchy entries with additive metadata that downstream consumers (operator review, future `tbs-frontend` dashboard) can use to identify zones of structural significance at a glance.

**Industry precedent for the design:** TradingView's standard S/R confluence indicator uses ATR-scaled clustering with default multiplier 0.5× and a banded {2-level / 3-level / 4+-level} strength scale. CFL-001 adopts the same banding pattern, with a slightly tighter (0.25×) threshold on the floor side reflecting the precision requirement on stops. See §10 for full external validation.

---

## §2. Scope

### §2.1 In-Scope

- Module-level helper `_detect_level_confluence(entries, atr_value, threshold_mult, side) -> list` in `layers/tbs_engine/transform.py`.
- **Two** call sites, both **post-partition + post-sort**:
  - Target side: after the target-side BUGR-002 partition into `_targets_above` / `_cleared` and the post-partition sort of `_targets_above` (~L3045).
  - Floor side: after the floor-side BUGR-002 partition into `_stops_below` / `_overhead` and the post-partition sort of `_stops_below` (~L3335). Covers BOTH the standard and the BRK-active paths in a single call (the BRK-active branch reassigns `_floor_entries = _brk_floor_entries` upstream, so on that path `_stops_below` is the BRK-scoped four-entry list).
- Per-entry `confluence` sub-object emitted on entries that participate in a cluster.
- Three module-level constants: floor threshold multiplier, target threshold multiplier, boundary tolerance.
- One description-template map (six entries: floor/target × MODERATE/STRONG/EXCEPTIONAL).

### §2.2 Out of Scope

- **No annotation** on `target.cleared_levels` or `floor_analysis.overhead_levels`. The post-partition placement (§4) is the structural guarantee for this invariant — the helper only sees `_targets_above` / `_stops_below`, never `_cleared` / `_overhead`. Deferred to a v1.1+ candidate (`CFL-001-OBS-1`) if surfaced by live operator demand.
- **No new flat key.** The annotation lives only on hierarchy entries as a nested sub-object — never on the flat-metrics layer.
- **No gate input.** No gate function reads `confluence`. Verified by negative-assertion test class `TestCFL001NotInGatesFile`.
- **No `bias` field** as a separately structured key. Bias is implicitly conveyed by which array the entry lives in (floor → support-favored; target → resistance-favored) and explicitly in the `desc` string. A future `CFL-001-BIAS-1` may surface structured bias if the dashboard requires it.
- **No cross-boundary cluster detection.** A cluster that would naturally span the current-price boundary (one anchor cleared, one anchor active) is NOT detected by design — each side is scanned independently. Logged as `CFL-001-OBS-3` for v1.1+ consideration.

### §2.3 Files Touched

| File | Edit | LOC delta |
|---|---|---|
| `layers/tbs_engine/transform.py` | New helper + 3 module-level constants + 1 description-template map + 2 call sites | **+173** |
| `layers/tests/unit/test_cfl001_confluence.py` | New test file (8 classes, 36 tests) | **+512** |
| `layers/cfl001_fingerprint_diff.py` | New — standalone CLI utility for spec §6.2 acceptance #3/#5 automation | **+231** |
| **Total** | | **+916** |

Zero other engine modules touched. Zero gate functions modified. Zero existing flat keys altered. Zero new imports anywhere in `transform.py`. The fingerprint utility is pure stdlib (json, argparse, os, sys); not pytest-collected.

---

## §3. Algorithm

### §3.1 Module-level constants

Inserted near `_CONVICTION_TIER_MAP` (`transform.py` ~L194):

```python
# [CFL-001] ATR-scaled adjacency thresholds for confluence detection.
# DQ-1 locked S157 — 0.25x floor (industry-tighter than 0.5x default; stops are
# precision instruments) / 0.5x target (matches TradingView S/R confluence
# indicator default). Both sides are calibration candidates after 3-6 months
# live data — see CFL-001-CAL-1 (CONCEPT) for the deferred review item.
_CFL_FLOOR_THRESHOLD_ATR_MULT = 0.25
_CFL_TARGET_THRESHOLD_ATR_MULT = 0.5

# [CFL-001] Boundary tolerance for the inclusive `<=` comparison in the
# clustering walk. Live-cohort validation on CRWD-A surfaced an IEEE-754
# near-miss where 0.25 * 8.04 = 2.0100000000000016 and 560.69 - 558.68 =
# 2.0100000000001046; their absolute diff (~1.05e-13) crossed the inclusive
# boundary and prevented a cluster that visually matched at the displayed
# 2-decimal precision. The tolerance is:
#   - 7 orders of magnitude below the smallest meaningful price quantum
#     (a penny = 0.01)
#   - 4 orders of magnitude above the largest plausible single-op float
#     drift (~1e-13 observed in CRWD)
#   - directly tested: a gap of (threshold + 100 * tolerance = threshold +
#     1e-7) does NOT form a cluster (TestCFL001BoundaryTolerance).
_CFL_BOUNDARY_TOLERANCE = 1e-9

# [CFL-001] Side-aware strength-aware description templates per DQ-6.
# Format placeholders: {member_count}, {spread_atr}, {anchor_price}.
# Timing-neutral per SIR §10 (no "first test" or temporal predictions —
# CFL-001 has no knowledge of test history).
_CFL_STRENGTH_DESC_MAP = {
    ("floor", "MODERATE"):
        "MODERATE support cluster -- 2 anchors within {spread_atr} ATR of ${anchor_price}",
    ("floor", "STRONG"):
        "STRONG support cluster -- 3 anchors within {spread_atr} ATR of ${anchor_price}; institutional-grade convergence",
    ("floor", "EXCEPTIONAL"):
        "EXCEPTIONAL support cluster -- {member_count} anchors within {spread_atr} ATR of ${anchor_price}; rare multi-anchor convergence",
    ("target", "MODERATE"):
        "MODERATE resistance cluster -- 2 anchors within {spread_atr} ATR of ${anchor_price}",
    ("target", "STRONG"):
        "STRONG resistance cluster -- 3 anchors within {spread_atr} ATR of ${anchor_price}; institutional-grade convergence",
    ("target", "EXCEPTIONAL"):
        "EXCEPTIONAL resistance cluster -- {member_count} anchors within {spread_atr} ATR of ${anchor_price}; rare multi-anchor convergence",
}
```

### §3.2 Helper definition

Inserted below `_annotate_conviction` at `transform.py` ~L252:

```python
def _detect_level_confluence(entries, atr_value, threshold_mult, side):
    """CFL-001: detect adjacent-price clusters within (threshold_mult * ATR).

    In-place annotation of the entries list. Each entry that participates
    in a cluster (member_count >= 2) receives a `confluence` sub-object.
    Entries not in any cluster are left untouched — no `confluence` key
    is added. Absence of the field is silence (ordinary single-anchor
    strength), NOT a negative signal.

    Args:
        entries: hierarchy list. The greedy adjacent walk requires
            price-sorted input; the helper sorts a defensive local copy
            (ascending) so caller order is preserved on the entries list.
            Cluster identity is order-invariant.
        atr_value: current ATR(14) value from flat_metrics["ATR"].
        threshold_mult: 0.25 (floor side) or 0.5 (target side).
        side: "floor" or "target" — selects the desc template family.

    Returns:
        The same entries list reference (chained-call ergonomics, parallel
        to _annotate_conviction).

    Defensive behaviour (DQ-5):
        - empty entries -> no-op return
        - atr_value None / 0 / negative -> no-op return
        - entry with price=None -> excluded from clustering (the dict is
          left untouched)
    """
    if not entries or atr_value is None or atr_value <= 0:
        return entries

    threshold = threshold_mult * atr_value

    # Sort a local view by price (ascending). The greedy adjacent walk is
    # order-invariant on cluster identity, so ascending vs. descending does
    # not matter — but we must walk in some monotonic order. Caller's list
    # order is intentionally left untouched (BUGR-002 partition + sort
    # logic downstream depend on the caller-controlled order).
    _walk = sorted(
        (e for e in entries if e.get("price") is not None),
        key=lambda e: e["price"],
    )
    if len(_walk) < 2:
        return entries

    # `+ _CFL_BOUNDARY_TOLERANCE` makes the inclusive `<=` reliable at
    # the threshold even when float arithmetic introduces sub-penny noise.
    # See the constant's commentary above for the CRWD-A near-miss rationale.
    threshold_with_tolerance = threshold + _CFL_BOUNDARY_TOLERANCE

    clusters = []
    current_cluster = [_walk[0]]
    for entry in _walk[1:]:
        prev_price = current_cluster[-1]["price"]
        cur_price = entry["price"]
        if abs(cur_price - prev_price) <= threshold_with_tolerance:
            current_cluster.append(entry)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [entry]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    for cluster_idx, cluster in enumerate(clusters, start=1):
        member_count = len(cluster)
        if member_count == 2:
            strength = "MODERATE"
        elif member_count == 3:
            strength = "STRONG"
        else:  # >= 4
            strength = "EXCEPTIONAL"

        members = [m.get("label") for m in cluster]
        prices = [m["price"] for m in cluster]
        anchor_price = round(sum(prices) / len(prices), 2)
        spread_atr = round((max(prices) - min(prices)) / atr_value, 2)

        desc = _CFL_STRENGTH_DESC_MAP[(side, strength)].format(
            member_count=member_count,
            spread_atr=spread_atr,
            anchor_price=anchor_price,
        )

        confluence_obj = {
            "id": cluster_idx,
            "strength": strength,
            "member_count": member_count,
            "members": members,
            "desc": desc,
        }
        for m in cluster:
            m["confluence"] = confluence_obj

    return entries
```

### §3.3 Sort-determinism (DQ-4)

The helper sorts a defensive local view (`_walk`); the caller's `entries` list order is intentionally left untouched. Downstream BUGR-002 partition logic that depends on caller-controlled order is unaffected. The only mutation on `entries` is the addition of the `confluence` key on cluster member dicts (which are shared references between `entries` and `_walk`). Sort-determinism on the caller's list is preserved by construction. Verified by `TestCFL001SortDeterminism`.

### §3.4 Shared cluster object reference

Within a cluster, every member receives the **same** `confluence` dict reference (not a per-member copy). This is intentional — it guarantees consistent member-count, members list, and desc across the cluster. Downstream JSON serialisation is unaffected (json.dumps copies values, not references). Verified by `TestCFL001ClusterDetection::test_shared_object_reference`. If a future enhancement requires per-member fields within the confluence object, the implementer must switch to `copy.deepcopy` at the assignment site (~L343).

---

## §4. Call Site Integration

**Note on the v1.0 → v1.1 placement change:** Spec v1.0 specified three call sites positioned immediately after the three `_annotate_conviction(...)` invocations (target ~L2835, floor standard ~L3087, BRK-active floor ~L3145). The Track 2 / Claude Code session's pre-implementation sort-order audit caught two interlocking spec defects with those locations: (a) target and floor-standard sites were **pre-sort** (BUGR-002 had removed the pre-partition sort, leaving entries in `.append()`-order, which would have produced incorrect clusters from a greedy adjacent walk); (b) the BUGR-002 partition uses shallow list comprehensions, so cleared_levels and hierarchy share dict references — annotating at the pre-partition CNV-001 location would have mechanically leaked `confluence` into `cleared_levels` / `overhead_levels`, violating §2.2. The post-partition placement adopted in v1.1 solves both defects cleanly. See §13 Document History and the v1.0 → v1.1 delta entry for the full trail. Bug Register entry `ANALYST-CFL-001-SPEC-1` records this as a spec-authoring-time discipline lesson.

### §4.1 Target-side call site

At `transform.py` ~L3048 (locate by the `[CFL-001]` comment):

```python
    # ... BUGR-002 target partition at ~L3027-3043 produces:
    #   _targets_above  -- entries with price > current_price (the hierarchy)
    #   _cleared        -- entries with price <= current_price (intentionally excluded)
    _targets_above.sort(key=lambda x: x["price"])  # ascending
    _cleared.sort(key=lambda x: x["price"])

    # [CFL-001] Annotate target hierarchy entries with `confluence` on
    # clustered entries (within 0.5x ATR adjacency). Runs POST-partition so
    # only `_targets_above` is scanned -- `_cleared` is intentionally excluded
    # per spec §2.2 / §5.3 (cleared_levels confluence deferred to v1.1
    # candidate CFL-001-OBS-1). Runs POST-sort so the greedy adjacent walk
    # operates on sorted prices. See CFL-001 hand-back §5 for the call-site
    # deviation rationale (the spec's v1.0 §4.1 location was pre-partition/pre-sort).
    _detect_level_confluence(
        _targets_above,
        flat_metrics.get("ATR"),
        _CFL_TARGET_THRESHOLD_ATR_MULT,
        "target",
    )

    target_hierarchy = _targets_above if _targets_above else None
    target_cleared_levels = _cleared if _cleared else None
```

### §4.2 Floor-side call site (covers both standard and BRK-active paths)

At `transform.py` ~L3338 (locate by the `[CFL-001]` comment):

```python
    # ... BUGR-002 floor partition at ~L3315-3331 produces:
    #   _stops_below   -- entries with price < current_price (the hierarchy)
    #   _overhead      -- entries with price >= current_price (intentionally excluded)
    # On the BRK-active path, `_floor_entries = _brk_floor_entries` is assigned
    # UPSTREAM of the partition (~L3146), so `_stops_below` is the BRK-scoped
    # four-entry list on that path.
    _stops_below.sort(key=lambda x: x["price"], reverse=True)  # descending
    _overhead.sort(key=lambda x: x["price"])

    # [CFL-001] Annotate floor hierarchy entries with `confluence` on
    # clustered entries (within 0.25x ATR adjacency). Runs POST-partition so
    # only `_stops_below` is scanned -- `_overhead` is intentionally excluded
    # per spec §2.2 / §5.3 (overhead_levels confluence deferred to v1.1
    # candidate CFL-001-OBS-1). Runs POST-sort so the greedy adjacent walk
    # operates on sorted prices.
    #
    # Covers BOTH the standard and the BRK-active paths in a single call:
    # on the BRK path, `_floor_entries = _brk_floor_entries` is assigned
    # above (replacing the broad floor hierarchy with the BRK-scoped four-
    # entry list) BEFORE the partition runs, so `_stops_below` is the BRK
    # entry set on that path. This consolidates v1.0's §4.2 + §4.3 call sites.
    _detect_level_confluence(
        _stops_below,
        flat_metrics.get("ATR"),
        _CFL_FLOOR_THRESHOLD_ATR_MULT,
        "floor",
    )
```

---

## §5. Output Schema

### §5.1 Per-entry confluence sub-object

Added only to entries that participate in a cluster (member_count ≥ 2). Absent from entries that don't.

```json
{
  "price": 285.50,
  "label": "EMA_21",
  "role": {"label": "MA_DYNAMIC", "desc": "Daily EMA(21) -- short-term trend anchor"},
  "status": "HOLDING",
  "conviction_tier": "MA_DYNAMIC",
  "conviction_rank": 3,
  "confluence": {
    "id": 1,
    "strength": "STRONG",
    "member_count": 3,
    "members": ["DAILY_LOW", "EMA_21", "PSYCHOLOGICAL"],
    "desc": "STRONG support cluster -- 3 anchors within 0.18 ATR of $285.42; institutional-grade convergence"
  }
}
```

### §5.2 Field semantics

| Field | Type | Description |
|---|---|---|
| `id` | int ≥ 1 | Cluster identifier within the invocation. Members of the same cluster share the same `id`. Sequential, 1-based, no gaps. |
| `strength` | str enum | `MODERATE` (2 members) / `STRONG` (3) / `EXCEPTIONAL` (≥4). Positive-only — absence of the field means "no cluster," not "weak cluster" (per DQ-2 confirmed S157). |
| `member_count` | int ≥ 2 | Number of entries in this cluster. |
| `members` | list[str] | Labels of all cluster members in ascending-walk order (independent of caller display order). |
| `desc` | str | Human-readable description. Side-aware (support vs resistance), strength-aware. Includes the actual cluster spread in ATR units and the cluster anchor price (mean of member prices). Timing-neutral per SIR §10 — no "first test" or temporal predictions. |

### §5.3 Where confluence appears

| Path | Confluence emitted? |
|---|---|
| `trade_setup.target.hierarchy[*].confluence` | Yes — target-side clusters (via `_targets_above`) |
| `floor_analysis.hierarchy[*].confluence` | Yes — floor-side clusters, standard and BRK-active (via `_stops_below`) |
| `trade_setup.target.cleared_levels[*].confluence` | **No** (out of scope per §2.2; structurally guaranteed by post-partition placement) |
| `floor_analysis.overhead_levels[*].confluence` | **No** (out of scope per §2.2; structurally guaranteed by post-partition placement) |
| Any flat_metrics key | **No** — not a flat-key surface |

Live-cohort verification (hand-back §11): the cleared/overhead invariant held across all 5 IBKR runs.

---

## §6. Test Plan

### §6.1 Unit tests

Test file: `layers/tests/unit/test_cfl001_confluence.py` (note: path is under `layers/` per `pytest.ini` testpaths declaration; v1.0 spec's `tests/unit/` was incorrect and corrected at implementation time).

**8 test classes, 36 tests, all passing in 2.91s:**

| Class | Tests | Coverage |
|---|---|---|
| `TestCFL001ClusterDetection` | 10 | Core algorithm — single-entry, 2/3/4/5-member clusters, beyond-threshold, transitive, separate clusters, isolated-then-cluster, shared object reference |
| `TestCFL001ThresholdScaling` | 3 | DQ-1 — floor constant value, target constant value, side-specific threshold tightening |
| `TestCFL001DescGeneration` | 9 | DQ-6 — six side/strength combinations + spread/anchor inclusion + no-first-test-language assertion |
| `TestCFL001DefensiveBehaviour` | 6 | DQ-5 — empty/None/0/negative ATR + null-price-middle + null-price-pair |
| `TestCFL001BoundaryTolerance` | 3 | **v1.1 addition** — CRWD-A reproducer, tolerance-size contract, no-false-positives at meaningful gap |
| `TestCFL001NotInGatesFile` | 1 | SIR §11.2 negative assertion — `inspect.getsource` walk of all `_gate_*` |
| `TestCFL001NotAFlatKey` | 2 | Output contract — AST-walk for flat_metrics writes + MAPPED_FLAT_KEYS unchanged |
| `TestCFL001SortDeterminism` | 2 | DQ-4 — caller's list order preserved for target + floor |

**Regression result:** 3010 / 5 / 1 post-CFL (vs 2974 / 5 / 1 pre-CFL). +36 matches new test count exactly. **The single pre-existing failure (`test_eng004_measured_move::test_transform_roundtrip`) is NOT a CFL regression** — stale relative path `tbs_engine/transform.py` missing `layers/` prefix, predates this bundle. Logged as `BUG-CFL001-PRE-1`.

### §6.2 Live validation cohort (5 IBKR runs)

| Ticker | Profile | Verdict | Confluence emitted | Path exercised |
|---|---|---|---|---|
| OXY | A | VALID (SWING_BREAKOUT) | None | Target non-cluster + BRK-active floor non-cluster |
| LIN | A | INVALID (FLOOR WARNING) | Floor MODERATE {DAILY_EMA_21, HARD_STOP} | Non-BRK floor, 0.04 ATR spread, anchor $502.87 |
| EOG | A | VALID (SWING_BREAKOUT) | Floor MODERATE {NEW_SUPPORT, PSYCHOLOGICAL} | BRK-active floor, 0.11 ATR spread, anchor $139.94 |
| CRWD | A | INVALID (NO RECOVERY TARGET) | None (post-fix would emit) | Non-BRK floor near-miss → triggered v1.1 epsilon fix |
| OXY | B | INVALID (FLOOR FAILURE) | Target MODERATE {PSYCHOLOGICAL, DAILY_HIGH} | Target cluster — only target-side positive witness |

**Code-path coverage matrix** — all four cells hit at least once:

|   | non-BRK | BRK-active |
|---|---|---|
| **Target call site** | OXY-B (cluster), CRWD (no cluster) | OXY-A (no cluster), EOG (no cluster) |
| **Floor call site** | LIN (cluster), OXY-B (no cluster), CRWD (no cluster) | OXY-A (no cluster), EOG (cluster) |

**Acceptance criteria results:**

| # | Criterion | Result |
|---|---|---|
| 1 | ≥1 ticker emits confluence | ✓ LIN, EOG, OXY-B |
| 2 | ≥1 negative witness | ✓ OXY-A, CRWD |
| 3 | Zero numeric drift on non-confluence keys | **Tooling delivered** (`cfl001_fingerprint_diff.py`); run against cached/replay data deferred to optional follow-up |
| 4 | Zero IBKR error / pipeline crash | ✓ 5/5 exit 0 |
| 5 | Verdict bitwise-invariant on identical inputs | Same as #3 — automation delivered, run pending |

**Acceptance #3 and #5 caveat:** live-mode runs against IBKR produce different market data between captures, so a pre/post bitwise diff requires a replay/cached source. The `cfl001_fingerprint_diff.py` utility automates the comparison; running it against a controlled-data capture is an optional follow-up if the Operator wants explicit drift-zero certification beyond the engineering invariants verified by unit tests. The unit-test invariants (`TestCFL001NotAFlatKey`, `TestCFL001NotInGatesFile`, `TestCFL001SortDeterminism`) already cover the verdict-invariance pathway structurally.

---

## §7. Behavioural Invariants

| Invariant | Mechanism | Verification |
|---|---|---|
| Zero new flat keys | `confluence` is emitted only as a nested sub-object on hierarchy entries, never assigned to `flat_metrics` | `TestCFL001NotAFlatKey::test_no_new_flat_metrics_key` (AST walk) + `test_mapped_flat_keys_unchanged` |
| Zero gate function modified | `gates.py` not in the edit list | mechanical edit-list audit; `git diff --stat` on merge commit |
| Zero gate function reads `confluence` | string scan of all `_gate_*` function bodies | `TestCFL001NotInGatesFile` (inspect.getsource walk) |
| Verdict bitwise-invariant on identical inputs | no gate input added | structural — verdict path untouched; verifiable by `cfl001_fingerprint_diff.py` on replay data |
| Hierarchy sort order preserved | confluence detection sorts a local copy; caller's list untouched | `TestCFL001SortDeterminism` (target + floor) |
| Module import graph stays acyclic | edit confined to `transform.py`; zero new imports | `grep -cE "^(import \|from )" transform.py` = 0 (unchanged from pre-CFL) |
| Pre-CFL fields bitwise-identical | additive sub-object only; no existing field mutated | live cohort fingerprint comparison (#3 above) |
| No confluence leak into cleared/overhead | post-partition placement; helper only sees `_targets_above` / `_stops_below` | live-cohort verification across all 5 runs; structural by §4 placement |

---

## §8. Documentation Impact Assessment (DIA)

Per Amendment Control Process §4. Status updated post-merge.

| Document | Section | Change Required | Status |
|---|---|---|---|
| **Doc 2** (Core Strategy) | §IV Output Schema Reference | Add `confluence` sub-object to per-group structure for `floor_analysis.hierarchy[*]` and `trade_setup.target.hierarchy[*]`. New value-space note for `strength` ∈ {MODERATE, STRONG, EXCEPTIONAL}. Note that absence of the field is silence (not a weak/negative signal). Note that `cleared_levels` and `overhead_levels` never carry confluence. | PENDING |
| **Doc 8** (Systemic Automation) | §II Layer 2 | Substantive mirror of Doc 2 §IV — describe `_detect_level_confluence` helper, two call sites (post-partition), threshold constants, boundary tolerance, side-aware desc generation. | PENDING |
| **Doc 7** (Daily Battle Card) | Step 6 | Scan-only — no operator-facing process change. Version bump only. | PENDING |
| **EEM** (Engine Execution Map) | §II Indicator Stack | Verify-only. May add a row noting CFL-001 as a post-partition annotation pass (not a new gate). | PENDING |
| **README** | Document Authority + Version line | Cascade refresh: Doc 2, Doc 8, Doc 7, PEO, EEM row version bumps. | PENDING |
| **PEO** | Tier 1J + Document History | Mark Tier 1J ✅ CLOSED; append closure row to Document History. | PENDING |
| **Bug Register** | CFL-001 status advance + new entries | 🟤 CONCEPT → 🟠 SPECIFIED (S157) → 🟡 IMPLEMENTED (S157) → 🟢 SYNCED (DIA pass) → ✅ CLOSED. New entries: `BUG-CFL001-PRE-1`, `CFL-001-BIAS-1`, `CFL-001-CAL-1`, `CFL-001-OBS-1`, `CFL-001-OBS-2`, `CFL-001-OBS-3`, `ANALYST-CFL-001-SPEC-1`, `CFL-001-PROC-1`. | IN PROGRESS — this session |

---

## §9. Open Decisions Log (all resolved)

| ID | Question | Resolution | Resolved |
|---|---|---|---|
| DQ-1 | ATR threshold multipliers | 0.25× floor / 0.5× target. Industry-validated against TradingView S/R confluence indicator default 0.5×; floor side intentionally tighter for stop-placement precision. | S157 |
| DQ-2 | Strength label vocabulary | 3-band {MODERATE / STRONG / EXCEPTIONAL} for member counts {2, 3, 4+}. Positive-only design (absence = silence). | S157 |
| DQ-3 | v1.1 scope | Primary hierarchies only — `_targets_above` and `_stops_below`. Cleared/overhead deferred to v1.1+ candidate `CFL-001-OBS-1`. Structural guarantee via post-partition placement. | S157 |
| DQ-4 | Sort stability | Helper sorts a defensive local copy; caller's list untouched. Verified by `TestCFL001SortDeterminism`. | S157 |
| DQ-5 | ATR-None / 0 / negative defensive fallback | No-op early return. No `confluence` key added. | S157 |
| DQ-6 | Description and interpretation visibility | Side-aware strength-aware `desc` on confluence sub-object. Timing-neutral. Positive-only design. Bias not a separate structured field in v1.1. | S157 |
| **DQ-7 (v1.1)** | Call-site placement (re-resolved post-defect-discovery) | Post-partition placement on `_targets_above` and `_stops_below` (two call sites, consolidating v1.0's three). Resolves the v1.0 pre-sort and shared-reference-leak defects. | S157 |
| **DQ-8 (v1.1)** | Float-precision boundary handling | Inclusive `<=` with `_CFL_BOUNDARY_TOLERANCE = 1e-9`. Safe by 7 orders of magnitude against penny precision; 4 orders above observed IEEE-754 drift. | S157 |

---

## §10. SIR §11.2 Track 2 Admissibility Verification (post-implementation)

| Criterion | Status | Evidence |
|---|---|---|
| Files: transform.py ± output.py only | ✓ (+ auxiliary tooling) | transform.py only for engine edits; the `cfl001_fingerprint_diff.py` utility is auxiliary tooling per hand-back §5.7 (Operator-authorised scope extension, pure stdlib, not engine code, not pytest-collected) |
| Behavior change: additive only | ✓ | New optional sub-object on existing entries; no field renamed, removed, or value-meaning-shifted; verified by live-cohort cleared/overhead invariant hold |
| Gate impact: zero | ✓ | `TestCFL001NotInGatesFile` negative-assertion test passing |
| Verdict impact: zero | ✓ | No new gate input; verdict path untouched (structural); replay-data invariance verification available via fingerprint utility |
| Vocabulary: reuse OR audit | ✓ | MODERATE/STRONG/EXCEPTIONAL emitted on a new sub-object (`confluence`); namespace-isolated. Vocabulary collision with future RLC-001 (CONCEPT) Reclaim_Quality bands noted — flagged for Bundle 4 spec author in §12. |
| Live validation: ≥3 tickers, ≥2 profiles | ✓ | 5 IBKR runs (OXY-A, LIN-A, EOG-A, CRWD-A, OXY-B); all 4 code-path matrix cells hit; engineering acceptance #1, #2, #4 satisfied |

**Conclusion:** CFL-001 v1.1 satisfies all six SIR §11.2 Track 2 admissibility criteria as implemented.

---

## §11. Companion Artifacts

This spec is the canonical design contract for the bundle delivered in:

- **Implementation branch:** `feat/CFL-001-confluence-detection` (merged to `master` at S157 cascade)
- **Commits:**
  - `c570968` — initial implementation (helper + 2 call sites + 33 tests)
  - `19ba506` — v1.1 follow-up (boundary tolerance + 3 boundary tests + fingerprint utility)
- **Hand-back:** `CFL001_Implementation_HandBack_v1_0.md` — canonical record of implementation decisions, deviations from v1.0 spec, and live-cohort validation
- **Auxiliary utility:** `layers/cfl001_fingerprint_diff.py` — standalone CLI for spec §6.2 acceptance #3 + #5 automation against pre/post engine outputs (Operator-authorised scope extension per hand-back §5.7)
- **Spec promotion:** at CFL-001 ✅ CLOSED, this v1.1 file promotes to `docs/specs/CFL001_Level_Confluence_Detection_Spec_v1_1.md` in the repo; the v1.0 file moves alongside as historical record; the hand-back promotes to `docs/handbacks/CFL001_Implementation_HandBack_v1_0.md`; the auxiliary utility may relocate to a new `scripts/` directory at Operator's discretion (per hand-back §7 question 5).

---

## §12. Cross-references

- **Bug Register entry:** `CFL-001 | Floor and Target Level Confluence Detection | 🟤 CONCEPT (S123) → 🟠 SPECIFIED (S157) → 🟡 IMPLEMENTED (S157) → 🟢 SYNCED (S157 DIA) → ✅ CLOSED`
- **PEO:** Tier 1J (Bundle 3). Hard prerequisite CNV-001 ✅ CLOSED S154.
- **Helper precedent:** `_annotate_conviction` (CNV-001, `transform.py` module-level). CFL-001 follows a similar helper-plus-call-sites pattern but with post-partition placement rather than post-CNV.
- **Call-site model:** post-partition placement on `_targets_above` and `_stops_below` (the post-BUGR-002 sorted hierarchy slices).
- **Industry precedent:** TradingView S/R confluence indicator (ATR-based clustering, default 0.5× multiplier, {2 / 3 / 4+} banding).
- **Bundle 4 spec author note:** RLC-001 Reclaim_Quality bands (CONCEPT) reuse MODERATE/STRONG labels. Namespace-isolated (different sub-object) so no live collision; vocabulary audit required at RLC-001 spec authoring time.
- **CONF-001 distinction:** CONF-001 is the orchestrator-layer multi-floor-type confluence (cross-references engine output with external floor types). CFL-001 is engine-layer confluence on the engine's own hierarchies. Complementary, not overlapping.
- **Hand-back companion:** the implementation hand-back is the authoritative narrative for v1.0 → v1.1 evolution; spec v1.1 is the canonical design contract; the two are intentionally complementary.
- **Future v1.1+ candidates** (logged at S157 closure):
  - `CFL-001-BIAS-1` — Structured `bias` field if `tbs-frontend` dashboard requires parseable directional bias for colour-coding.
  - `CFL-001-CAL-1` — 3–6 month threshold calibration review. Validate that 0.25× / 0.5× produce healthy firing rates.
  - `CFL-001-OBS-1` — Extend confluence detection to `cleared_levels` / `overhead_levels` if operator demand surfaces.
  - `CFL-001-OBS-2` — Anchor-price design alternative (strongest-conviction member price vs cluster mean).
  - `CFL-001-OBS-3` — Cross-boundary clusters spanning current price (one anchor cleared, one active). Per hand-back §7 question 2. May fold into `CFL-001-OBS-1` v1.1 scope.
- **Process companions:**
  - `ANALYST-CFL-001-SPEC-1` — Spec-authoring-time discipline gap: pre-implementation verification list should be run during spec authoring, not only included in the standalone prompt. Companion to ANALYST-002 / ANALYST-003 SIR §11 augmentation candidates.
  - `CFL-001-PROC-1` — Process observation: standalone implementation prompts must specify `defaultMode: acceptEdits` to prevent per-edit approval friction.
- **Pre-existing test failure to log:** `BUG-CFL001-PRE-1` — `test_eng004_measured_move::test_transform_roundtrip` stale relative path, predates CFL-001.

---

## §13. Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-17 (S157) | Initial specification. DQs 1–6 resolved per Operator confirmation. Track 2 admissibility verified per SIR §11.2. First Track 2 / Claude Code process trial. Industry precedent cited (TradingView S/R indicator). |
| **v1.1** | **2026-05-17 (S157, same session, post-implementation)** | **Superseding revision. Captures two corrections discovered by the Claude Code session's pre-implementation verification + live-cohort validation:** |
|  |  | **(a) Call-site placement: three pre-CNV invocations → two post-partition invocations.** v1.0's §4.1 and §4.2 sites were pre-sort (BUGR-002 had removed pre-partition sorts; entries were in `.append()`-order, which would have produced incorrect clusters from a greedy adjacent walk). v1.0's placement would also have mechanically leaked `confluence` into `cleared_levels` / `overhead_levels` via shared dict references in the partition's shallow list comprehensions, violating v1.0 §2.2. v1.1 places CFL invocations post-partition on `_targets_above` / `_stops_below` only — structural guarantee against leak; sort-correct walking. The BRK-active branch reassigns `_floor_entries = _brk_floor_entries` upstream of the partition, so a single floor call covers both BRK and standard paths. Three sites → two. See §4 introduction and `ANALYST-CFL-001-SPEC-1`. |
|  |  | **(b) Boundary tolerance: `<= threshold` → `<= threshold + _CFL_BOUNDARY_TOLERANCE`.** Live-cohort validation on CRWD-A surfaced an IEEE-754 near-miss (0.25 × 8.04 vs 560.69 − 558.68 diverged by ~1.05e-13). v1.1 introduces `_CFL_BOUNDARY_TOLERANCE = 1e-9` (7 orders below penny precision, 4 above observed drift). New test class `TestCFL001BoundaryTolerance` (3 tests) covers reproducer + tolerance contract + no-false-positives guard. |
|  |  | **(c) Test count: 33 → 36** (3 boundary tests added in v1.1). |
|  |  | **(d) Auxiliary utility added: `layers/cfl001_fingerprint_diff.py`** (231 LOC, pure stdlib, not pytest-collected) — Operator-authorised scope extension for §6.2 acceptance #3 + #5 automation against pre/post engine outputs. Hand-back §5.7. |
|  |  | **(e) Test file path corrected: `tests/unit/` → `layers/tests/unit/`** per `pytest.ini` testpaths declaration. v1.0's path was off; in-repo location is unambiguous. |
|  |  | **(f) Misc. test mechanism upgrade:** `test_no_new_flat_metrics_key` switched from naive substring grep to AST-walk to avoid docstring contamination. Same intent, tighter mechanism. |

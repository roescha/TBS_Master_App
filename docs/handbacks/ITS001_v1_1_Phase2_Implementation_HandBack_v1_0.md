# ITS-001 v1.1 - Phase 2 Implementation Hand-Back (S166)

**Spec authority:** `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 (supersedes v1.0.1)
**Brief authority:** `ITS001_v1_1_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Implementer:** Claude Code CLI (Opus 4.7, 1M context), in IntelliJ working tree `roescha/TBS_Master_App@master`
**Hand-back date:** 2026-05-26 (delivered in-session per Brief Section 8); on-disk record finalized 2026-05-27 with post-delivery SHA/diff-stat reconciliation (see Section 6.4).
**Status request:** Bug Register advance **ORANGE SPECIFIED -> YELLOW IMPLEMENTED**

> ASCII note: this document and the engine's emitted `desc` strings use ASCII punctuation (`--`, `-`, `x`) to match the engine output convention. See Section 6.4.

---

## Section 1. Outcome Summary

ITS-001 v1.1 is implemented to spec. The substantive amendment cycle (Item 4 vocabulary rename + Item 5 `entry_zone` sub-object) plus the cosmetic Item 3 `desc` enrichment landed as a **single co-implemented working-tree commit set** per DQ-INT-1 - the rename and `entry_zone` (whose `stop_ref` paths reference renamed stop keys) were never split.

- **107 ITS tests pass** (32 new across 9 classes + 8 modified + 67 unchanged) - exactly the Brief Section 6.1 target.
- **Zero ITS-caused regressions:** full cohort 3173 -> **3205 passed** / 4 skipped / **1 failed** (repo-root CWD), delta **+32**. The 1 failure is the pre-existing CWD-sensitive `test_eng004` roundtrip (BUG-CFL001-PRE-1), unchanged.
- Exactly **5 engine files + 1 test file** modified; no 6th engine file (Section 9.5 halt did not fire); no gate function added (verdict-invariance intact).
- Section 6.4 worked-example verified against Spec Section 8 for **all four shelf positions** (WITHIN/ABOVE/BELOW/no-shelf), and confirmed end-to-end by an Operator LIVE engine run against COHR (Section 8).

Process deviations (Section 6) are near-empty as Brief Section 8.1 anticipated: no halts fired, no spec ambiguity required surfacing. The minor observations logged are non-blocking and none is an engine defect.

---

## Section 2. Files Touched

```
 layers/tbs_engine/compute.py                       |  92 ++++-
 layers/tbs_engine/main.py                          |  10 +-
 layers/tbs_engine/output.py                        | 202 ++++++++--
 layers/tbs_engine/transform.py                     |  10 +
 layers/tbs_engine/types.py                         |   9 +
 layers/tests/unit/test_its001_intraday_tactical.py | 423 ++++++++++++++++++++-
 6 files changed, 698 insertions(+), 48 deletions(-)
```

Exactly the 5 engine files + 1 test file enumerated in Brief Section 3.1. **No 6th engine file.**

**Post-edit file SHAs (`git hash-object`, final state incl. Section 6.4 ASCII pass):**

| File | SHA |
|---|---|
| `layers/tbs_engine/types.py` | `e0a2c894afd9aeecfc0f84a5109fd8f4d431c19b` |
| `layers/tbs_engine/compute.py` | `1081673d02f3ae8078f2281d87795dcedb8f6dcd` |
| `layers/tbs_engine/output.py` | `0b48f98202403779315cb823ba6674c87404dfa2` |
| `layers/tbs_engine/transform.py` | `0eb58c05c6d4171b3850ec97355e4b143d185c23` |
| `layers/tbs_engine/main.py` | `6cd6c1b1f7473d0a00d8f021fa64b2693b9ccd03` |
| `layers/tests/unit/test_its001_intraday_tactical.py` | `32a45d1e9b14e62a465bf74d0dcdf8bb58c5abbb` |

> The in-session Hand-Back (2026-05-26) listed `output.py` at `e194767db568c28dbedcbd000baccf9e58c3e4a6` with a diff-stat of `700/50` (output.py 206). The Section 6.4 ASCII conversion (cosmetic, same-line character swaps in desc strings) updated `output.py` to the SHA above and shifted the diff-stat to `698/48` (output.py 202). The other 5 SHAs are unchanged from in-session delivery.

**Branch / commit:** `master`, working-tree changes **uncommitted** (preserved for Operator review per Brief Section 2 + Section 9 default).
**Suggested PR title:** `ITS-001 v1.1 - entry_zone affordance + WITHIN-stop vocabulary rename + desc enrichment (Track 1, Phase 2)`
**Co-implementation note:** all six files form one commit set; do not split the rename from entry_zone (DQ-INT-1).

---

## Section 3. What Was Built - Per Spec

| Edit | File | Outcome |
|---|---|---|
| **1** (4.9) | types.py | 5 RunContext attrs added after the 18 v1.0 `_intraday_*` (verified count = 5): `_intraday_entry_zone_mode/_applicable/_touchback/_range/_breakout`. Bare-type annotations (`str`/`bool`/`dict`) to match the adjacent v1.0 block convention - names/defaults/semantics per spec. |
| **2** (4.1) | compute.py | `INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25` added after the 12 `INTRADAY_*` constants (L46). |
| **3** (4.4) | compute.py | Symmetric rename in `_compute_intraday_tactical_levels` WITHIN dict (L2289-2295): `price.{range,breakout}` + `atr_buffer_mult.{range,breakout}`; numeric values unchanged; deprecation comments retained. |
| **4** (4.5) | compute.py | `_compute_entry_zone(ctx)` added immediately after `_compute_intraday_tactical_levels` (body verbatim per spec); `__all__` extended. Reads `_intraday_shelf_*` + `state.atr_raw`; writes 5 attrs; defensive null on `p_code!="A"` / no shelf / `atr_raw<=0`. |
| **5** (4.6) | main.py | Import extended; `_compute_entry_zone(ctx)` call inserted as 4th ITS helper after `_compute_intraday_tactical_levels(ctx)` (comment updated "three"->"four"). |
| **6** (4.7.5) | output.py | `_ITS_NULL_FLAT_KEYS` extended with the 9 entry_zone keys (all `None`). |
| **7** (4.7) | output.py | (a) `affected_fields` -> `trade_setup.stop/target.hierarchy[...]` paths + AVWAP_10BAR; (b) lookback_status two-branch `desc`; (c) shelf desc enriched (+ no-shelf degraded desc); (d) tactical_stop desc rewrite (WITHIN dict / scalar / atr_volatility, three-sentence template, renamed keys); (e) near_term_target desc enrichment + NOT_APPLICABLE cross-refs; (f) entry_zone block emission (`tb_raw`/`rg_raw`/`bo_raw` hoisted above the if/else so flat_keys is NameError-safe on the non-applicable path); (g) `entry_zone` added to block dict; (h) 9 entry_zone flat keys added. Docstring updated (18->27 keys). |
| **8** (4.8) | transform.py | 9 entry_zone flat keys appended to `_all_mapped_flat_keys()` (verified count = 9). No other change - top-level group emission + lookback_stale annotation unchanged from v1.0. |
| **9** (Section 6) | test file | Class 7 (TacticalStopWITHIN) range/breakout assertions; class 13 (LookbackStale) trade_setup paths; class 19 (SchemaStability) +entry_zone; class 20 (NotInGatesFile) +`entry_zone` token (Section 6.4 alignment); 9 new classes (22-30, 32 tests); `_make_ctx` carries 5 entry_zone attrs; symbols + flat-key lists added. |

**Helper signature:** `def _compute_entry_zone(ctx)` - compute.py, in `__all__`. **Call-site:** main.py, between `_compute_intraday_tactical_levels(ctx)` and `_compute_rally_state_for_ctx(ctx)`. **Flat-key totals:** 18 v1.0 + 9 v1.1 = **27**.

---

## Section 4. Verification - Spec Section 11 Audit (re-executed at post-edit state)

| # | Section 11 item | Post-edit result |
|---|---|---|
| 1 | Call-order: 4th ITS helper pre-gate | PASS - main.py: `_detect_intraday_events` -> `_detect_compression_shelf` -> `_compute_intraday_tactical_levels` -> `_compute_entry_zone` -> `_compute_rally_state_for_ctx`, all pre-gate |
| 2 | Sort-order | N/A - scalars only |
| 3 | Partition-leak | PASS - entry_zone inside `intraday_tactical`, structurally outside BUGR-002 partition |
| 4 | Pipeline-order feasibility | PASS - written tier 3, read tier 8 (`_assemble_intraday_tactical`); sentinel-key stash unchanged |
| 5 | Call-order feasibility | PASS - `_compute_entry_zone` reads shelf state written by `_detect_compression_shelf` |
| 6 | Cross-spec layout audit | PASS - `range`/`breakout` intentional reuse (stop+entry); no collisions; gates.py zero ITS tokens |
| 7 | Storage-mechanism | PASS - `_transform_output(action_summary, flat_metrics, debug=False)` - no ctx param; sentinel `_intraday_tactical_block` intact (output.py L2502) |
| 8 | Downstream-override audit | PASS - DD-2 (~L2206) + BKOUT-001 GAP-5 (~L2220) touch `action_summary` only; neither references entry_zone / `Intraday_Entry_*` |
| 9 (carryover) | AVWAP_10BAR | PASS - codified as hierarchy entry alongside ESTABLISHED_LOW in `affected_fields` |

Post-edit collision audit: `fade_to_upper`/`breakout_above` appear **only** as deprecation comments (compute.py L2289/2290/2294/2295); zero `_long`/short-side tokens; gates.py zero `entry_zone`/`_intraday_`/`Intraday_`/`intraday_tactical`.

---

## Section 5. Test Outcome

**ITS-001 v1.1 file (`pytest test_its001_intraday_tactical.py`):**
```
107 passed
```
32 new (classes 22-30) + 8 modified (class 7 x3, class 13 x5) + 67 unchanged = 107. Matches Spec Section 6.3.

**Full cohort (`pytest layers/tests/unit/ -q`, repo-root CWD):**
```
1 failed, 3205 passed, 4 skipped
```

| Metric | Baseline (clean HEAD, repo-root CWD) | Post-impl | Delta |
|---|---:|---:|---:|
| Passed | 3173 | 3205 | **+32** |
| Skipped | 4 | 4 | 0 |
| Failed | 1 | 1 | 0 |

Baseline measured by stashing `layers/` changes and re-running on clean HEAD - confirmed `3173 / 4 / 1`. The single failure is `test_eng004_measured_move::TestENG004TransformRoundTrip::test_transform_roundtrip` (BUG-CFL001-PRE-1), **unchanged**. **Zero ITS-caused regressions.** (Re-confirmed after the Section 6.4 ASCII pass: 107 / 3205-4-1 hold.)

---

## Section 6. Process Deviations - For Analyst Review

Near-empty as Brief Section 8.1 anticipated. No halts; no spec ambiguity. Four minor items:

**6.1 - Spec Section 8.1 example numbers vs spec normative `round()` (RESOLVED on live data).** During the synthetic Section 6.4 sanity check, driving COHR's Example A with *exact decimal* inputs (370.18 / 7.78) produced two values 1 cent below the spec example (`zone_upper=372.12`, `trigger_confirmed=383.94`) because the raw values (372.125, 383.945) are exact float-halfway points and Python `round()` resolves them downward. **The Operator's LIVE COHR engine run (Section 8) emitted `372.13` and `383.95` - matching Spec Section 8.1 exactly** - because real full-precision shelf/ATR inputs do not land on the halfway boundary. Conclusion: the engine correctly implements the spec's normative `round(x,2)`, and live behavior matches the spec example. **No engine change; no example refresh needed** (Section 9 item 2 closed). Tests assert via `round()` replication, not hardcoded literals, so they are robust to both cases.

**6.2 - Pre-existing failure is CWD-sensitive (confirms known baseline).** `test_eng004` roundtrip loads transform via the bare relative path `'tbs_engine/transform.py'`, so it **passes** with CWD=`layers/` and **fails** (FileNotFoundError) from repo root - exactly the mechanism in the project known-baseline note. Not ITS-related; flagged for the standing ENG-004 fix-it. (Explains a transient `3206/0-failed` reading observed running from `layers/` before normalizing to the repo-root invocation `3205/1`.)

**6.3 - Minor implementation latitude (no behavior change vs spec).** (a) types.py used bare `dict`/`str`/`bool` annotations to match the adjacent v1.0 block (`Dict` not imported); names/defaults/semantics per Section 4.9. (b) entry_zone breakout locals named `ts_bo`/`tc_bo` to avoid shadowing the lookback `ts` timestamp var. (c) Test class 30's "full-path for `trade_snapshot.atr.value`" coverage item is verified as the DQ-D2 *convention* (within-block refs bare; no desc carries a redundant `intraday_tactical.` prefix) rather than asserting a literal external-path string - no spec-provided desc emits an external path. (d) `entry_zone` token added to `TestITS001NotInGatesFile`'s scan per Section 6.4 (the `_intraday_`/`Intraday_` prefixes already covered the entry_zone ctx attrs and flat keys).

**6.4 - Post-delivery ASCII conversion of ITS desc strings (Operator-requested).** The Spec Section 3.5 / Section 4.7 desc templates use typographic Unicode (em-dash U+2014, en-dash U+2013, multiply U+00D7), which the engine emitted as `\u2014`/`\u2013`/`\u00d7` escapes in the output JSON - inconsistent with every other emitted desc string in the engine, which is ASCII (`--`, `-`, `x`; e.g. "NEUTRAL -- BUILDING", "1.5x Daily ATR"). At Operator request these three characters were replaced with ASCII equivalents, scoped strictly to the emitted desc f-strings inside `_assemble_intraday_tactical` (output.py L831-1136): 13x `--`, 3x `-`, 6x `x`. The codebase's pervasive Unicode-in-comments convention (`Section`/`->` etc. in source comments and docstrings, never emitted) was left untouched. This is a cosmetic display change with zero behavioral/test impact (107 / 3205-4-1 unchanged); it updated `output.py`'s SHA and the diff-stat (Section 2). Items 1 + 2 confirmed already engine-correct in v1.0; v1.1 carries the path/AVWAP corrections in `affected_fields` + narrative only - no deviation.

---

## Section 7. Pre-Delivery Verification - Brief Section 7 / SIR Section 9

| # | Check | Result |
|---|---|---|
| 1 | Content accuracy | PASS - all Section 3.1 edits landed; Section 3.2 out-of-scope untouched; diff-stat = 5 engine + 1 test |
| 2 | Internal consistency | PASS - no `fade_to_upper`/`breakout_above`/`_long` in output (only deprecation comments); entry_zone `stop_ref`/`target_ref` resolve to real fields |
| 3 | Format integrity | PASS - all 5 engine files `ast.parse` clean; imports acyclic; emitted desc strings ASCII |
| 4 | Scope discipline | PASS - `git diff --stat` = exactly 5 engine + 1 test; no 6th engine file; no new gate function |
| 5 | Gate-function verification | PASS - `TestITS001NotInGatesFile` + `TestITS001VerdictInvariance` pass; gates.py zero ITS/entry_zone tokens |
| 6 | Module import verification | PASS - full suite imports all engine modules; `_compute_entry_zone` added to compute.py only; output/transform imports unchanged |
| 7 | Bug Register | NOT DONE - Analyst (Phase 4) per memo Section 8; flagged Section 9 |
| 8 | DIA current | NOT DONE - Phase 4; flagged Section 9/Section 10 |

---

## Section 8. Live-Sampling Confidence Notes (Operator LIVE engine run)

The Operator ran the engine in LIVE mode against **COHR** (Profile A, C2, verdict INVALID / MID-RANGE ADX<20) on 2026-05-27. The `intraday_tactical` group emitted correctly per DQ-2 (independent of the swing INVALID verdict). Rendered block (ASCII desc strings per Section 6.4):

```json
"intraday_tactical": {
  "shelf": {
    "detected": true, "upper": 382.0, "lower": 370.18, "bar_count": 5,
    "tightness_ratio": 0.454, "position": "WITHIN", "lookback_stale": false,
    "desc": "Compression shelf $(370.18-382.0) over 5 hourly bars; width 0.45x Daily ATR; position: WITHIN. Acts as intraday-tactical reference for entry, stop, and target levels."
  },
  "lookback_status": {
    "stale": false, "event_type": null, "affected_fields": [],
    "desc": "No regime-shift event in 10-bar lookback. Short-window references (ESTABLISHED_LOW, DAILY_HIGH, AVWAP_10BAR) carry no stale annotation. Window clear for the evaluated bar."
  },
  "tactical_stop": {
    "shelf_structural": {
      "price": {"range": 367.07, "breakout": 379.67},
      "anchor": "both", "atr_buffer_mult": {"range": 0.4, "breakout": 0.3},
      "atr_value_used": 7.78,
      "desc": "WITHIN-shelf dual stop alternates: range $367.07 (0.4x Hourly ATR below shelf lower $370.18) supports range-play long; breakout $379.67 (0.3x Hourly ATR inside shelf upper $382.0) supports breakout-play long. Each invalidates if corresponding shelf boundary breaks."
    },
    "atr_volatility": {
      "price": 365.75, "atr_mult": 1.5, "atr_value_used": 7.78,
      "desc": "Volatility-based stop $365.75 -- 1.5x Hourly ATR below current price. Methodology-independent of shelf structure; supports stops when shelf-based stops are absent. Invalidates as a backstop only -- supersedes when shelf_structural unavailable."
    }
  },
  "near_term_target": {
    "mode": "WITHIN",
    "primary": {"price": null, "source": "NOT_APPLICABLE",
                "desc": "Directionally neutral (WITHIN shelf) -- no primary target emitted. Operator reads tactical_stop + entry_zone alternates for both directional plays."},
    "secondary": {"price": null, "source": "NOT_APPLICABLE",
                  "desc": "Directionally neutral (WITHIN shelf) -- no secondary target emitted."},
    "applicable": false
  },
  "entry_zone": {
    "applicable": true, "mode": "WITHIN",
    "range": {
      "zone_lower": 370.18, "zone_upper": 372.13,
      "trigger": "Long inside shelf near lower bound, expecting drift toward upper",
      "stop_ref": "tactical_stop.shelf_structural.price.range",
      "target_implied": 382.0,
      "desc": "Range-play entry zone $370.18-$372.13 -- buy near shelf lower expecting drift toward upper $382.0. Stop per tactical_stop.shelf_structural.price.range. Invalidates if price closes below shelf lower (range breakdown)."
    },
    "breakout": {
      "trigger_structural": 382.0, "trigger_confirmed": 383.95,
      "trigger": "Close above shelf upper",
      "stop_ref": "tactical_stop.shelf_structural.price.breakout",
      "target_ref": "near_term_target.primary",
      "desc_structural": "Structural breakout trigger $382.0 -- bare close above shelf upper. Use for early entry tolerating wick risk. Invalidates if close reverses back below $382.0 within evaluation bar.",
      "desc_confirmed": "Confirmed breakout trigger $383.95 -- close above shelf upper plus 0.25x Hourly ATR buffer. Filters wick fakeouts at cost of worse fill. Invalidates if close reverses back below shelf upper after triggering."
    }
  }
}
```

Confidence observations:
- Engine ran cleanly; no exceptions; `intraday_tactical` emits on an INVALID swing verdict per DQ-2 (semantic-neutrality).
- WITHIN dual stop alternates emit with the **renamed** keys `range`/`breakout` (no `fade_to_upper`/`breakout_above`).
- `entry_zone` emits the WITHIN dual alternates (`range` + `breakout`); `stop_ref` paths resolve to the renamed `tactical_stop.shelf_structural.price.range` / `.breakout`.
- Live values match Spec Section 8.1 **exactly**, including `zone_upper=372.13` and `trigger_confirmed=383.95` (resolves the Section 6.1 synthetic-input rounding caveat).
- `atr_value_used: 7.78` matches `trade_snapshot.atr.value: 7.78`.

This LIVE COHR run is one WITHIN witness. Deterministic Section 6.4 checks additionally verified ABOVE (Spec Section 8.4, touchback 148.50-148.70), BELOW (Section 8.5, breakout 148.50/148.70), and no-shelf (Section 8.2) - all exact matches. The canonical Phase 3 cohort (>=5 Profile A tickers across all positions + stale/non-stale witnesses) remains Operator-led.

---

## Section 9. Open Items for the Analyst

1. **Bug Register status advance** - ITS-001 master row **ORANGE SPECIFIED -> YELLOW IMPLEMENTED**. Evidence: Section 2 SHAs, test delta **+32** (107 ITS / 3205 cohort), zero regressions. No sub-entries per memo Section 8.
2. **(CLOSED) Spec Section 8.1 example-number refresh** - originally flagged as a candidate cosmetic doc fix; the Operator LIVE run confirms the engine emits the spec's exact example values (372.13 / 383.95) on real data. No refresh needed.
3. **ENG-004 / BUG-CFL001-PRE-1** - the known CWD-sensitive roundtrip failure persists; standing fix-it (use `os.path.join(__file__, ...)`).
4. **Phase 3 live cohort (Spec Section 7 #5)** - >=5 Profile A tickers across ABOVE/BELOW/WITHIN + >=1 `lookback_stale=true` + >=1 `false` witness. COHR is one live WITHIN witness; ABOVE/BELOW + stale witnesses still needed. Operator-led IBKR.
5. **Phase 4 DIA cascade** - Doc 2 Section VI/Section IV substantive (entry_zone schema + rename + desc convention), Doc 7 Step 6 substantive (operator reading guidance for entry_zone), Doc 8 Section II Layer 2 mirror, EEM verify-only, README + PEO Tier closure.

---

## Section 10. Closure-Criteria Tracker (Spec Section 7)

| # | Criterion | Phase | Status |
|---|---|---|---|
| 1 | Phase 2 Hand-Back w/ diff-stat + SHAs + test counts | 2 | DONE (this document - Section 2, Section 3, Section 5) |
| 2 | All Section 6 tests pass (107) | 2 | DONE - 107 passed |
| 3 | Zero ITS-caused regressions (baseline 3173/4/1) | 2 | DONE - 3205/4/1 (+32; pre-existing failure unchanged) |
| 4 | Engine renders entry_zone per shelf position | 2 | DONE - WITHIN (COHR LIVE) + ABOVE/BELOW/no-shelf (deterministic) vs Spec Section 8 |
| 5 | Live cohort >=5 tickers + stale witnesses | 3 | PENDING - Operator-led IBKR (COHR is 1 WITHIN witness) |
| 6 | Verdict invariance pre/post v1.1 | 3 | PENDING - static defense in place (NotInGatesFile + VerdictInvariance + EntryZoneVocabulary) |
| 7 | 6-doc DIA cascade | 4 | PENDING - Analyst-led |
| 8 | Bug Register ORANGE->YELLOW->GREEN->CLOSED | 2->4 | YELLOW IMPLEMENTED ready (Section 9 item 1) |

---

**End of Hand-Back.** Spec authority remains `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md`. No Brief Section 9 halt triggers fired. DQ-INT-1 co-implementation preserved - rename + entry_zone in one uncommitted working-tree set, ready for the Operator to commit/push per preference (suggested branch/PR title in Section 2). Suggested next steps: (1) Operator reviews diff + commits; (2) Analyst consumes Section 6/Section 9 into Project chat + advances Bug Register; (3) Operator schedules Phase 3; (4) Phase 4 DIA cascade.

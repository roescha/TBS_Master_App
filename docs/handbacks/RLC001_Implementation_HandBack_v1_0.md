# RLC-001 v1.0 Implementation Hand-Back — S160 (Phase 2)

**Spec authority:** `RLC001_Reclaim_Quality_Score_Spec_v1_0.md` (v1.0, S160, 2026-05-19)
**Brief authority:** `RLC001_Claude_Code_CLI_Implementation_Brief_v1_0.md` (v1.0, S160)
**Implementer:** Claude Code CLI (IntelliJ plugin), session S160
**Hand-back date:** 2026-05-20
**Track:** Track 2 inline cadence (SIR §11.2 — file scope `output.py` + `transform.py` + new test file only)
**Status request:** Bug Register advance **SPECIFIED → IMPLEMENTED**

---

## 1. Outcome Summary

RLC-001 v1.0 (Reclaim Quality Score / Tennis Ball Action) is implemented to spec. Phase 2 deliverables complete:

- Constants + helper + call site in `output.py`
- Flat-key registration in `transform.py`
- New unit test file with 65 tests across 10 classes (above 35-45 target)
- Full pytest suite passes with zero RLC-001-caused regressions
- One **process deviation** from Spec §4.5 (documented in §6 below) — needs Analyst review before Phase 3

Live validation (Phase 3) and DIA cascade (Phase 4) remain Out of Scope for this hand-back per Brief §2.1.

---

## 2. Files Touched (diff --stat)

```
layers/tbs_engine/output.py                       | +95 -1
layers/tbs_engine/transform.py                    |  +5 -0
layers/tests/unit/test_rlc001_reclaim_quality.py  | +663 (new)
```

**File SHAs (post-edit, git hash-object):**

| File | SHA |
|---|---|
| `layers/tbs_engine/output.py` | `27ddb629911390d8af345d0b0658535edbbf306f` |
| `layers/tbs_engine/transform.py` | `a72006b06c60c4d32517106635e0209516a7c669` |
| `layers/tests/unit/test_rlc001_reclaim_quality.py` | `7aff147a0102e93e62f387c0b3f196d5dc238d95` |

**Branch / commit:** `master`, working-tree changes uncommitted (staged for Operator review per Brief §9 default).

---

## 3. What Was Built — Per Spec §4

### 3.1 `layers/tbs_engine/output.py`

1. **Module-level constants** (Spec §4.1) — added alongside existing `THS_*` / `VTRIG_*` / `RLY_*` constants near the top of the file:
   ```python
   RLC_STRONG_THRESHOLD = 0.75
   RLC_MODERATE_THRESHOLD = 0.60
   _RLC_THRESHOLDS = {"strong_at_or_above": 0.75, "moderate_at_or_above": 0.60, "weak_below": 0.60}
   _RLC_NULL_FLAT_KEYS = {"Reclaim_Quality_Pct": None}
   ```
2. **Helper function** `_assemble_reclaim_quality(ctx, gate_result)` — implemented verbatim from Spec §4.2. Returns `(block, flat_keys_dict)`. Module placement immediately after `_assemble_rally_state` (closest sibling). `__all__` updated to export it (mirroring RLY-001 precedent).
3. **Call site** in `_assemble_output` — placed immediately after the RLY-001 `_assemble_rally_state` call, immediately before the `_transform_output` return:
   ```python
   _rlc_block, _rlc_flat = _assemble_reclaim_quality(ctx, gate_result)
   metrics.update(_rlc_flat)
   if _rlc_block is not None and action_summary.get("verdict") == "VALID":
       action_summary["reclaim_quality"] = _rlc_block
   ```

### 3.2 `layers/tbs_engine/transform.py`

1. **Flat-key registration** — `keys.add("Reclaim_Quality_Pct")` added in `_all_mapped_flat_keys()`, placed alongside the existing RLY-001 `Rally_*` registration block.
2. **action_summary attachment** — relocated to output.py (see deviation §6 below).

### 3.3 `layers/tests/unit/test_rlc001_reclaim_quality.py` (new file, 663 lines)

10 test classes per Spec §5 catalog, 65 total tests:

| # | Class | Tests | Coverage |
|---|---|---|---|
| 1 | `TestRLC001Formula` | 7 | Spec §8.1 Examples A/B/C + 4dp storage + clamp behavior + above-high anomaly |
| 2 | `TestRLC001Banding` | 6 | Boundary inclusivity at 0.749 / 0.750 / 0.599 / 0.600 + far-band |
| 3 | `TestRLC001VocabularyDiscipline` | 7 | Exact label literals + desc substring (`>=75%`, `60-75%`, `<60%`) + integer-percent formatting |
| 4 | `TestRLC001NullDefensive` | 11 | All 6 paths in Spec §3.2 + KeyError / TypeError + inverted range |
| 5 | `TestRLC001VerdictGuard` | 9 | 4 non-VALID verdicts (parametrized) + 4 non-RECLAIM entry_types (parametrized) + positive case |
| 6 | `TestRLC001VerdictInvariance` | 4 | Helper does not mutate gate_result / ctx.last / is pure-repeatable |
| 7 | `TestRLC001SchemaStability` | 7 | Block keys exact / thresholds independent copy / null-flat-keys independent copy |
| 8 | `TestRLC001FlatKeyRegistration` | 2 | `Reclaim_Quality_Pct in MAPPED_FLAT_KEYS` + uniqueness (one RLC key only) |
| 9 | `TestRLC001PositiveOnly` | 8 | `KeyError` on `action_summary["reclaim_quality"]` access on 6 non-RECLAIM paths + override path + flat-key-None invariant |
| 10 | `TestRLC001ActionSummaryAttachment` | 4 | Positive integration: attached on VALID×RECLAIM + value matches flat key + label matches band + thresholds present |

**Test harness pattern:** Post-TEST-HRN-001 idempotent (mirrors VTRIG-001's "stub-only-if-not-already-present" guard). Loads `output.py` via `spec_from_file_location` without polluting global `sys.modules`. Stubbed sibling modules (`tbs_engine.charts`, `tbs_engine.transform`, etc.) only inserted when not already loaded — suite-friendly. Tests 8.1 + 8.2 load `transform.py` via unique synthetic module names (`_rlc001_transform_under_test*`) to avoid cache pollution.

---

## 4. Verification — Spec §11 (Pre-Implementation Checklist)

All performed on the current working tree (post-S159 master) before any code edit.

| Check | Result | Evidence |
|---|---|---|
| §11.1 Call-order: gate_result in scope at call site | PASS | `output.py:_assemble_output(ctx, gate_result, _prx_ctx, debug=False)` signature unchanged |
| §11.1 RLY-001 call completes before RLC-001 | PASS | RLC-001 call placed immediately after RLY-001 call in `_assemble_output` |
| §11.1 RLC-001 before `_transform_output` invocation | PASS | Block attached pre-return |
| §11.2 ctx.last, ctx.metrics, gate_result populated | PASS | Same pre-conditions as RLY-001 call site |
| §11.2 metrics["Reclaim_Quality_Pct"] visible downstream | PASS | `metrics.update(_rlc_flat)` mirrors RLY-001 idiom |
| §11.3 Sort-order | N/A | Single-bar scalar (no list iteration) |
| §11.4 Shared-reference | N/A | Block is fresh dict per call; thresholds dict is `dict(_RLC_THRESHOLDS)` (defensive copy) |
| §11.5a Flat-key collision audit | PASS | `git grep "Reclaim_Quality" layers/tbs_engine/` → 0 hits pre-edit |
| §11.5b Label vocabulary collision audit | PASS | 0 hits for STRONG_RECLAIM / MODERATE_RECLAIM / WEAK_RECLAIM pre-edit |
| §11.5c action_summary key collision | PASS | `"reclaim_quality"` not a pre-existing key in action_summary assembly (verified by reading lines 1918-2065 of `_assemble_output`) |
| §11.5d RLY-001 pattern match — storage idiom | DEVIATION | See §6 below — RLY-001 doesn't store its block on ctx; spec §4.3 literal `ctx._rlc_block = ...` deviates from actual RLY-001 idiom. Adapted per Operator decision (§6) |
| §11.5e VTRIG-001 / SFR-001 attachment idiom | DEVIATION | See §6 — VTRIG attaches in output.py (not transform.py); literal spec §4.5 code is broken (ctx not in `_transform_output` scope) |
| §11.6 PE-43 bar-index compliance | PASS | Helper uses `ctx.last` exclusively; no `cfg.iq` arithmetic |
| §11.7 Positive-only design audit | PASS | Test 9 (8 sub-tests) asserts `KeyError` on `action_summary["reclaim_quality"]` access across all non-RECLAIM paths including override paths |

---

## 5. Test Outcome

**New tests:**

```
pytest layers/tests/unit/test_rlc001_reclaim_quality.py -v
================================ 65 passed in 5.35s ================================
```

**Full regression suite:**

```
pytest layers/tests/ --tb=short -q
================================ 3133 passed, 5 skipped, 1 failed in 14.74s ===========
```

- **0 RLC-001-caused regressions.**
- The single failure (`test_eng004_measured_move.py::TestENG004TransformRoundTrip::test_transform_roundtrip`) is **pre-existing on bare master** (verified via `git stash` + re-run). Root cause: hardcoded relative path `'tbs_engine/transform.py'` inside the test, which assumes a working directory at `layers/` rather than the repo root. This is a candidate for the Analyst's hygiene queue but is unrelated to RLC-001 — flagging only for completeness.

**Worked-example sanity check (Spec §8 Example A live against helper):**

| Field | Expected (Spec §8.1) | Actual (test `test_strong_example_A`) |
|---|---|---|
| Input | open=$101.20, high=$104.00, low=$100.00, close=$103.80 | (same) |
| `Reclaim_Quality_Pct` | 0.9500 | 0.9500 |
| `condition.label` | STRONG_RECLAIM | STRONG_RECLAIM |
| Match | YES | YES |

---

## 6. Process Deviation — Spec §4.5 Attachment Site

**Per Brief §8.2, the following deviations are surfaced for Analyst review.**

### 6.1 The Issue

Spec §4.5 places the action_summary attachment **inside `_transform_output`** in `transform.py`, using:

```python
_rlc_block = getattr(ctx, "_rlc_block", None)
if _rlc_block is not None:
    action_summary["reclaim_quality"] = _rlc_block
```

But `_transform_output(action_summary, flat_metrics, debug=False)` does not receive `ctx` as a parameter (verified at `transform.py:1432`). The literal §4.5 code cannot execute — `ctx` is not in scope. Two consequences:

1. `getattr(ctx, ...)` raises `NameError` if executed verbatim.
2. The corresponding §4.3 storage line `ctx._rlc_block = _rlc_block` would create a ctx attribute that is undeclared in `types.py:RunContext`. RunContext is `@dataclass` without `__slots__`, so the assignment would succeed at runtime — but the attribute is never observable inside `_transform_output` because ctx isn't passed in.

Additionally, the spec instructions to "mirror RLY-001 / VTRIG-001 / SFR-001 idioms" themselves diverge from the literal §4.3 / §4.5 code:
- RLY-001 does **not** store its block on ctx — it discards `_rly_block`, merges flat keys into metrics, and reconstructs the rally_state grouped sub-object in `transform.py` from those flat keys.
- VTRIG-001 attaches `volume_confirmation` directly into the action_summary dict literals inside `_assemble_output` (`output.py:1937, 1957, 2016, 2030, 2046, 2060`) — not in `_transform_output`.
- SFR-001 writes a flat key in output.py, then rebuilds `action_summary["signal_freshness"]` from `flat_metrics.get("Signal_Freshness")` inside `_transform_output`.

### 6.2 Resolution Path Taken (Operator-approved S160)

Per Operator selection in the S160 implementation session (Option 1 of three offered), I followed the **VTRIG-001 idiom** — attach in `output.py` at the post-action_summary-construction site, with an additional verdict guard:

```python
# output.py, in _assemble_output, after RLY-001 call:
_rlc_block, _rlc_flat = _assemble_reclaim_quality(ctx, gate_result)
metrics.update(_rlc_flat)
if _rlc_block is not None and action_summary.get("verdict") == "VALID":
    action_summary["reclaim_quality"] = _rlc_block
```

Consequences vs literal spec:
- The `ctx._rlc_block` attribute is **never created** (no undeclared ctx-attribute assignment).
- `transform.py` retains only the **flat-key registration** edit (§4.4). The §4.5 transform.py attachment edit is omitted.
- The block flows from `output.py` directly into `action_summary` in the same scope where it's computed.

### 6.3 Additional Guard — action_summary.verdict

The spec helper's positive-path guards are `gate_result.verdict == "VALID"` and `gate_result.entry_type == "RECLAIM"`. But two paths in `_assemble_output` override the action_summary verdict to "INVALID" while leaving `gate_result.verdict == "VALID"`:

1. **DD-2 EXIT override** (`output.py:1929-1940`) — VALID gate_result + Exit_Signal == "EXIT" → action_summary.verdict overridden to INVALID
2. **BKOUT-001 GAP-5 C2-mandate override** (`output.py:1947-1961`) — VALID gate_result + Convexity_Class == "C2" + Profit_Target is None → action_summary.verdict overridden to INVALID

Per Spec §2.2, `reclaim_quality` MUST NOT emit on non-VALID action_summary verdicts. The added guard `action_summary.get("verdict") == "VALID"` enforces this. Test 9 `test_absent_when_action_summary_overridden_to_invalid` verifies the behavior.

### 6.4 What the Analyst Should Decide

Two questions for the spec-amendment cycle:

1. **Bless the attachment-site relocation.** Update spec §4.3 + §4.5 to reflect "attach in output.py at the post-action_summary-construction site, mirroring VTRIG-001," removing the `ctx._rlc_block` storage step entirely. This is consistent with VTRIG-001 sibling-spec precedent and avoids creating an undeclared ctx attribute.

2. **Bless the action_summary.verdict guard.** Add language to spec §2.2 or §4.3 that the sub-object attaches only when **both** `gate_result.verdict == "VALID"` AND `action_summary.get("verdict") == "VALID"` are true, to cover the DD-2 / BKOUT-001 GAP-5 override paths. (Alternative: define the helper guard against action_summary instead of gate_result — but the helper is called before action_summary exists, so this would require a signature change.)

---

## 7. Pre-Delivery Verification — Spec §12

| Check | Result |
|---|---|
| Content accuracy (paths, line numbers, SHAs) | PASS |
| Internal consistency (helper matches §3 formula, constants match §3.3 cutoffs, banding `>=` semantics) | PASS |
| Format integrity (no trailing whitespace, no unused imports, mirrors existing style) | PASS |
| Scope discipline (`git diff --stat` shows exactly 3 files — output.py, transform.py, new test file) | PASS |
| Bug Register update | NOT DONE — Analyst responsibility per Brief §7 |
| DIA current | NOT DONE — Track 2 inline cadence per SIR §11.4, folds into next Tranche reconciliation |
| Zero regressions | PASS (0 RLC-001-caused regressions; 1 pre-existing failure unrelated) |

---

## 8. Live-Sampling Confidence Notes (Operator-run smoke checks)

The Operator ran the engine in `LIVE` mode against 7 tickers as a pre-Phase-3 smoke check. **None landed on a `VALID × RECLAIM` verdict** — all were INVALID for various reasons (FLOOR FAILURE, CONTEXT REGIME FAILED, WINDOW EXPIRED). On all 7:

- `action_summary` did **not** contain a `reclaim_quality` key (absent, not null — positive-only design holding correctly)
- `Reclaim_Quality_Pct` did **not** surface anywhere in the rendered JSON (correctly — the engine's `_debug` group is a curated diagnostic subset, not a `MAPPED_FLAT_KEYS` dump; flat keys surface via grouped sub-objects only)
- Engine ran cleanly, no exceptions, no schema gaps, no regressions visible in adjacent sub-objects (rally_state, volume_confirmation, swing_breakout_confirmation, etc.)

Sample cohort: CAT (A), DHR (A), REL.L (B), SHEL.L (A), HD (A), MSFT (B), NWG.L (A). All Profile A and Profile B, no Profile C sampled.

This is reassuring negative-path evidence but does **not** substitute for the Phase 3 positive-witness cohort (≥1 STRONG_RECLAIM + ≥1 MODERATE_RECLAIM + ≥1 WEAK_RECLAIM, per Spec §5.1).

---

## 9. Open Items for the Analyst

1. **Process deviation review** (§6 above) — bless or amend the attachment-site relocation + action_summary.verdict guard. Spec §4.3 + §4.5 edits may be in scope for a v1.0.1 or v1.1 amendment.
2. **Bug Register status advance** — RLC-001 SPECIFIED → IMPLEMENTED, with file SHAs from §2 above + test-count delta `+65` and pytest cohort summary.
3. **Phase 3 cohort selection** — pre-select tickers in a current RECLAIM scenario for live witness. Suggested filter: tickers where `floor_analysis.floor_failure.reclaim_progress` shows recent progress (e.g., "1/3", "2/3") on the prior bars, and where running the next bar may yield a `VALID × RECLAIM` verdict.
4. **DIA Tranche reconciliation commitment** — log the Tranche-N target for the Doc 2 / Doc 7 / Doc 8 / EEM / README / PEO cascade per Spec §6 preliminary scope. No per-bundle DIA per SIR §11.4.
5. **Pre-existing test hygiene note** — `test_eng004_measured_move::test_transform_roundtrip` has a hardcoded relative path bug that fails on bare master. Candidate for the hygiene queue. Out of RLC-001 scope.

---

## 10. Closure-Criteria Tracker (Spec §7)

| # | Criterion | Status |
|---|---|---|
| 1 | Phase 2 standalone implementation hand-back received | ✅ (this document) |
| 2 | All new tests pass; zero regressions | ✅ (65 new pass; 0 RLC-001-caused regressions) |
| 3 | Live validation: ≥1 RECLAIM capture across applicable profiles, ≥3 band tiers witnessed | ⏳ Phase 3 — Analyst-led |
| 4 | Verdict invariance verified live | ⏳ Phase 3 |
| 5 | Bug Register IMPLEMENTED entry logged with helper signature, call site, file SHAs | ⏳ Analyst — content available in §2 + §3 above |
| 6 | Spec verified against final source state (no drift) | ⏳ Analyst — note process deviation §6 |
| 7 | Track 2 reconciliation tranche commitment recorded | ⏳ Analyst — see §9.4 above |

---

**End of Hand-Back.** Spec authority remains `RLC001_Reclaim_Quality_Score_Spec_v1_0.md`. The §6 process deviation is the principal item requiring Analyst attention before Phase 3 commencement.

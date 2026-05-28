# Tier 1S — Test Infrastructure Hygiene Bundle — Phase 2 Implementation Hand-Back v1.0

**Hand-Back ID:** `Tier_1S_Test_Infrastructure_Hygiene_Bundle_Phase2_Implementation_HandBack_v1_0`
**Authoring template:** ACP v1.3 §6.5 canonical 10-section Hand-Back
**Phase:** 2 (Claude Code CLI implementation) — delivered in-session
**Authority:** Bug Register entries TEST-HRN-001, BUG-CFL001-PRE-1, CT001-TEST-FLAKINESS + S170 Phase 0 source-verification findings carried inline in the Brief (no spec — Bug-Fix Fast-Path per SIR §11.3)
**Brief consumed:** `Tier_1S_Test_Infrastructure_Hygiene_Bundle_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Working branch:** `tier1s-test-infra-hygiene` (off `master` @ `7b975e2`)
**Status at delivery:** All §5 edits applied; dual-CWD full unit cohort GREEN; CT001 takes the NOT-REPRODUCIBLE path (predicted).

---

## §1. Mission Outcome

Three TEST-HRN-001 idempotency guards inserted (3 files) and one CWD-relative-path defect (BUG-CFL001-PRE-1, eng004) converted to a `__file__`-anchored construction (1 file). CT001-TEST-FLAKINESS reproduce-first (Brief §4.3) returned GREEN exactly as S170 predicted (B23–B26 = 4/4, full file = 38/38, inside full cohort from repo root) → NOT-REPRODUCIBLE path; no edit. Zero `tbs_engine/` touch, zero production touch, zero documented-behaviour change, no new test file, no `--deselect`.

| Constituent | Action | Result |
|---|---|---|
| TEST-HRN-001 | `sys.modules` early-return / write-site guards in 3 files | ✅ Applied (Edits 1–3) |
| BUG-CFL001-PRE-1 | `__file__`-anchored `_engine_dir` in `test_transform_roundtrip` | ✅ Applied (Edit 4) |
| CT001-TEST-FLAKINESS | Reproduce-first inside cohort, both targeted + full file | ✅ NOT-REPRODUCIBLE (no edit) |

**Final cohort:** repo root → `3250 passed / 4 skipped / 0 failed`; `layers/` CWD → `3250 passed / 4 skipped / 0 failed`. Pre-fix baseline (same cohort): `3249 passed / 4 skipped / 1 failed` (eng004 transform_roundtrip). Delta: +1 pass = eng004 flipping F→P; the 3 TEST-HRN guards changed **zero** other outcomes (invariance preserved, Brief §5.A / §7).

---

## §2. Scope & Authority

- **Authority hierarchy:** Bug Register entries + S170 Phase 0 findings carried inline in Brief → Brief → implementer interpretation. **No spec exists** (Fast-Path, SIR §11.3). Conflict-resolution rule from Brief §1 honored: anchors were re-confirmed at HEAD before any edit; zero drift found → no halt triggered, no scope adaptation.
- **In-scope test files (exactly 4):**
  - `layers/tests/unit/test_frr001_fundamental_rr.py`
  - `layers/tests/unit/test_sbo001_breakout.py`
  - `layers/tests/unit/test_sbo001_phase2.py`
  - `layers/tests/unit/test_eng004_measured_move.py`
- **`git diff --stat` (post-edit):**
  ```
  layers/tests/unit/test_eng004_measured_move.py  |  8 ++++-
  layers/tests/unit/test_frr001_fundamental_rr.py |  4 +++
  layers/tests/unit/test_sbo001_breakout.py       | 40 +++++++++++++++----------
  layers/tests/unit/test_sbo001_phase2.py         | 27 ++++++++++-------
  4 files changed, 53 insertions(+), 26 deletions(-)
  ```
- **Forbidden touches honored (Brief §3, §5):** zero `tbs_engine/*.py`, zero `layers/*.py` non-test, zero of the 6 already-guarded files (`test_rec001_phase2a_base_detection.py`, `test_rec001_phase2b_recovery_gates.py`, `test_rec001_phase2c_exit_architecture.py`, `test_rec_sc_combined_patch.py`, `test_vtrig001_volume_confirmation.py`, `test_vol004_volume_display.py`), zero of the newer canonical-guard files (`test_its001_*`, `test_rly001_*`, `test_rlc001_*`, `test_dsp002_*`, both `test_bugr006_*`), no new test file, no spec authoring, no `--deselect`, no production timestamp/clock "hardening" of CT001.

---

## §3. What Was Built — Per Brief §5

Post-edit blob SHAs (`git hash-object`, pre-commit):

| File | Blob SHA |
|---|---|
| `layers/tests/unit/test_frr001_fundamental_rr.py` | `8bcc7357d9c35ccc6009a7016fdadbbf6bb1ccc2` |
| `layers/tests/unit/test_sbo001_breakout.py` | `e658b18abd9ffe42421830fb71729ba13bc7befd` |
| `layers/tests/unit/test_sbo001_phase2.py` | `7ccd364678eefb3955976bbf843f45c7595f28ed` |
| `layers/tests/unit/test_eng004_measured_move.py` | `2f850a451f2f71526c8e8ece0efa1ce3a84f1ecd` |

### Edit 1 — TEST-HRN-001 / `test_frr001_fundamental_rr.py` (Brief §5.A)

**Anchor (pre-fix):** `_load_mod()` at L30–35 wrote `sys.modules[name] = mod` unconditionally.
**Form:** helper-form canonical guard, mirroring `test_its001_intraday_tactical.py` L68–70 and `test_bugr006_profile_b_brk_rr.py` L60–62.
**Change (4 inserted lines):** at the top of `_load_mod()`:
```python
if name in sys.modules:
    return sys.modules[name]
```
with a one-line `TEST-HRN-001 guard` provenance comment above. Body otherwise unchanged.

### Edit 2 — TEST-HRN-001 / `test_sbo001_breakout.py` (Brief §5.A)

**Anchors (pre-fix):** three unconditional submodule writes — `tbs_engine.types` (≈L26), `tbs_engine.trigger` (≈L35), `tbs_engine.gates` (≈L52). The pre-existing `if "tbs_engine" not in sys.modules` at L17 was guarding only the *parent stub* (Brief §4.1 anchor).
**Form:** inline-form per-write guard (Brief §5.A preferred-form), each block becoming `if "<modname>" not in sys.modules: <spec/module/exec>` with an `else: <mod> = sys.modules["<modname>"]` rebind so the subsequent attribute reads (`GateResult`, `_identify_trigger`, `SBO_VOLUME_THRESHOLD`, `_gate_extension`) still see the right module object on the cached-path. All stub-attribute assignments (`_check_round_number_proximity`, `check_climax_history`, `_evaluate_floor_failure_context`) preserved verbatim; parent-stub guard at L17 preserved verbatim.

### Edit 3 — TEST-HRN-001 / `test_sbo001_phase2.py` (Brief §5.A)

**Anchors (pre-fix):** two unconditional submodule writes — `tbs_engine.types` (≈L26), `tbs_engine.transform` (≈L43). (`tbs_engine.helpers` write was already guarded; left untouched.)
**Form:** identical inline-form per-write guard as Edit 2. `else:` rebinds preserve the local `_types_mod` / `_transform_mod` names used by the subsequent `_transform_output = _transform_mod._transform_output` etc. lines. The local `SBO_CONFIRMATION_BARS` shadow at L50–51 is untouched.

### Edit 4 — BUG-CFL001-PRE-1 / `test_eng004_measured_move.py` (Brief §5.B)

**Anchor (pre-fix):** `test_transform_roundtrip` L418–419 — `spec_from_file_location('transform', 'tbs_engine/transform.py')` resolved CWD-relative; FileNotFoundError with absolute repo-root CWD (the pre-fix repro showed `FileNotFoundError: 'C:\\dev\\trading\\TBS_Master_App\\tbs_engine/transform.py'`).
**Form:** `__file__`-anchored absolute path, mirroring `test_frr001_fundamental_rr.py` L28 idiom (`os.path.dirname` × 3 from `__file__` then `+ "tbs_engine"`).
**Change:** added `import os` inside the test (alongside the existing in-method `import importlib.util` / `import sys`), then:
```python
_engine_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tbs_engine")
spec = importlib.util.spec_from_file_location(
    'transform', os.path.join(_engine_dir, 'transform.py'))
```
with a one-line `BUG-CFL001-PRE-1` provenance comment. The plotly-stub block (L414–416) and downstream `_transform_output` / `_flatten` invocations untouched.

### CT001-TEST-FLAKINESS (Brief §5.C) — no file edit

Reproduce-first (Brief §4.3) inside the full cohort returned GREEN, matching S170's `4/4 + 38/38` prediction. Per Brief §5.C, **the resolution IS the reproduction evidence** — no edit, no timestamp/FS "hardening" blind. Closes NOT-REPRODUCIBLE at Phase 4.

**Test-file LOC delta:** +53 / −26 (net +27) across the 4 files. No production LOC change. Consistent with Brief §11 estimate (~10–20 LOC; the higher count here is because Edits 2 and 3 use the inline-form which adds a 2-line `else:` rebind per write site to preserve local-name access).

---

## §4. Verification — Brief §4 (Pre-Implementation, MANDATORY)

All §4 checks executed **before any edit**, against HEAD = `7b975e2`. Zero anchor drift → no halt.

| Brief § | Check | Status | Evidence |
|---|---|---|---|
| §4.1 | `test_frr001_fundamental_rr.py` `_load_mod()` writes `sys.modules[name] = mod` with no guard | ✅ CONFIRMED unguarded | Read L28–35: bare write at L33, no early-return |
| §4.1 | `test_sbo001_breakout.py` 3 unconditional submodule writes | ✅ CONFIRMED unguarded | Read L1–53: bare `sys.modules[...] =` at L26 (types), L35 (trigger), L52 (gates); L17 guards only the parent stub |
| §4.1 | `test_sbo001_phase2.py` 2 unconditional submodule writes | ✅ CONFIRMED unguarded | Read L1–44: bare `sys.modules[...] =` at L26 (types), L43 (transform); L17 parent-only guard, L32 helpers stub already guarded |
| §4.1 | 6 documented-safe files actually guarded (do NOT touch) | ✅ CONFIRMED guarded | Read each: `test_rec001_phase2a/b/c`, `test_rec_sc_combined_patch` all use guarded-loop (`for _mod, _path in [...]: if _mod not in sys.modules:`); `test_vtrig001` / `test_vol004` use `if mod_name not in sys.modules:` loop |
| §4.1 | Newer canonical-guard files actually carry the early-return guard | ✅ CONFIRMED | Grep `if name in sys.modules` → hits in `test_its001_intraday_tactical.py` L69, `test_rly001_rally_state.py` L49, `test_bugr006_profile_b_brk_rr.py` L61, `test_bugr006_label_fidelity_bundle.py` L127; `test_dsp002_analyst_levels_surfacing_decoupling.py` L82 (`if modname in sys.modules`); `test_rlc001_reclaim_quality.py` L60 (guarded-loop variant) |
| §4.2 | `test_eng004_measured_move.py::test_transform_roundtrip` uses CWD-relative `'tbs_engine/transform.py'` | ✅ CONFIRMED | Read L418–419: literal `'tbs_engine/transform.py'`; pre-fix repro hit `FileNotFoundError` from repo-root CWD (§5 evidence) |
| §4.2 | Mirror pattern `_engine_dir = ... __file__ ...` exists in `test_frr001_fundamental_rr.py` | ✅ CONFIRMED | Read L28: `_engine_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "tbs_engine")` |
| §4.3 | `layers/finnhub_context.py` present + symbols exist | ✅ CONFIRMED | Glob hit; grep: `CACHE_FILE` L48, `_read_cache` L396, `_is_any_entry_stale` L445, `_get_sector_median_pe` L565 |
| §4.3 | `test_ct001_session_b.py` inserts `layers/` onto sys.path | ✅ CONFIRMED | L26: `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))` resolves to `layers/` (file lives at `layers/tests/unit/test_ct001_session_b.py`) |
| §4.3 | **Targeted B23–B26 inside cohort, from repo root, no `--deselect`** | ✅ GREEN | `pytest layers/tests/unit/test_ct001_session_b.py -k "TestB23 or TestB24 or TestB25 or TestB26" -v` → 4 passed, 34 deselected, 2.11s |
| §4.3 | **Full `test_ct001_session_b.py`, from repo root, no `--deselect`** | ✅ GREEN | `pytest layers/tests/unit/test_ct001_session_b.py -v` → 38 passed, 1.65s |
| §4.3 | Full cohort baseline (pre-edit) from repo root | ✅ as predicted | `pytest layers/tests/unit/ -q` → 3249 passed, 4 skipped, 1 failed (`eng004 test_transform_roundtrip`, expected per BUG-CFL001-PRE-1) |

**Result:** §4.3 GREEN → CT001 takes the NOT-REPRODUCIBLE path (Brief §5.C / §10). No timestamp/FS fix written. Evidence anchors above carry the disposition.

---

## §5. Test Outcome

### Dual-CWD full unit cohort (post-edit, no `--deselect`)

| CWD | Command | Result |
|---|---|---|
| Repo root (`C:\dev\trading\TBS_Master_App`) | `python -m pytest layers/tests/unit/ -q` | **3250 passed, 4 skipped, 0 failed**, 31.31s |
| `layers/` (`C:\dev\trading\TBS_Master_App\layers`) | `python -m pytest tests/unit/ -q` | **3250 passed, 4 skipped, 0 failed**, 30.75s |

### Baseline vs. post-edit invariance check (Brief §5.A, §7)

| Metric | Baseline | Post-edit | Delta |
|---|---|---|---|
| Passed | 3249 | 3250 | +1 (eng004 `test_transform_roundtrip` F→P) |
| Skipped | 4 | 4 | 0 |
| Failed | 1 | 0 | −1 (the same eng004 case) |

The 3 TEST-HRN guards changed **zero** other PASS/FAIL outcomes — the entire delta is accounted for by Edit 4 alone (the targeted BUG-CFL001-PRE-1 fix). Brief §5.A invariance requirement satisfied.

### Targeted dual-CWD evidence for §7 sub-checks

| Target | Repo-root CWD | `layers/` CWD |
|---|---|---|
| `test_eng004_measured_move.py::TestENG004TransformRoundTrip::test_transform_roundtrip` | ✅ PASSED (in cohort 3250/4/0) | ✅ PASSED (explicit targeted run: 1 of 5 passed in mixed-target invocation) |
| `test_ct001_session_b.py::TestB23_…` through `TestB26_…` | ✅ 4/4 PASSED (in cohort) | ✅ 4/4 PASSED (explicit targeted run) |
| Full `test_ct001_session_b.py` | ✅ 38/38 PASSED (in cohort, repo-root targeted run) | ✅ included in `layers/` cohort 3250/4/0 |

Combined targeted run from `layers/` CWD (eng004 roundtrip + B23–B26): **5 passed, 34 deselected, 1.93s** — confirms Brief §7 sub-check "the eng004 roundtrip now PASSES from both CWDs; B23–B26 pass from both CWDs."

### Warnings

2 cohort warnings (both pre-existing, unrelated to this bundle): `pandas_ta` Pandas4Warning, `eventkit` asyncio event-loop DeprecationWarning. Matches the known-baseline noise; not introduced or removed by these edits.

---

## §6. Process Deviation

**None.** No deviations from Brief §4–§5 directives.

- No halt triggers fired (Brief §9 catalogue): §4 anchors all confirmed; CT001 §4.3 GREEN not red; no TEST-HRN guard flipped any outcome (invariance held); eng004 `__file__` fix made the roundtrip green from both CWDs; no 5th file or production touch was needed.
- Edit 2/3 used the Brief §5.A "preferred minimal form" (inline `if "<modname>" not in sys.modules:`) rather than the equivalent guarded-loop refactor — both were explicitly offered by Brief §5.A as equally acceptable; inline form chosen because it minimizes diff line-count and matches the file's existing per-write narrative comments. `else: <mod> = sys.modules["<modname>"]` rebinds added so the subsequent `mod.<attr>` reads still see a real module on cached-path; this is a downstream consequence of the inline form, not a behaviour change.
- Edit 4 added an in-method `import os`. The test method already has in-method `import importlib.util` / `import sys` (pre-existing style), so the in-method import pattern is preserved — file-level imports were not touched.
- CT001 §5.C path taken without edit, by direct reading of Brief §5.C: "If §4.3 is green: **no file edit.** The resolution is the reproduction evidence."

---

## §7. Pre-Delivery Verification (SIR §9 — Brief §7)

| Brief §7 check | Status | Evidence |
|---|---|---|
| Content accuracy: every edit matches a §5 instruction | ✅ PASS | Edits 1–3 = §5.A (helper-form for frr001, inline-form for the two sbo001 files); Edit 4 = §5.B (`__file__`-anchored mirror of frr001 idiom) |
| §4.1 anchors hold for the 3 TEST-HRN files | ✅ PASS | §4 table above; pre-fix file reads at named line ranges |
| §4.2 anchor holds for eng004 | ✅ PASS | §4 table above; pre-fix `FileNotFoundError` repro captured |
| Scope discipline: at most 4 test files touched | ✅ PASS (exactly 4) | `git diff --stat` shows 4 paths, all under `layers/tests/unit/` |
| Zero production/engine files touched | ✅ PASS | `git diff --name-only` ∩ `tbs_engine/` / `layers/*.py` (non-test) = ∅ |
| Zero of the 6 already-guarded files touched | ✅ PASS | `git diff --name-only` ∩ {rec001_a, rec001_b, rec001_c, rec_sc_combined, vtrig001, vol004} = ∅ |
| Dual-CWD cohort GREEN, no `--deselect` | ✅ PASS | Repo root 3250/4/0; `layers/` 3250/4/0 |
| eng004 roundtrip PASSES from both CWDs | ✅ PASS | §5 dual-CWD targeted table |
| B23–B26 PASS from both CWDs | ✅ PASS | §5 dual-CWD targeted table |
| Invariance: the 3 TEST-HRN guards changed no test outcome | ✅ PASS | Baseline (3249/4/1) → post (3250/4/0), full delta = eng004 alone |
| Gate functions, gate order, acyclic module import graph all untouched (trivially) | ✅ PASS (affirmative) | No `tbs_engine/` touch ⇒ no possible change to gate identity / order / wiring; module import graph identical (only test-side `sys.modules` cached-vs-rebuilt behaviour changed) |
| CT001 disposition recorded with evidence | ✅ PASS | NOT-REPRODUCIBLE; evidence in §4 (B23–B26 4/4, full file 38/38, full cohort eng004-only failure) |
| No spec §12 reference required | ✅ PASS (Fast-Path) | Bug-Fix Fast-Path bundle; no spec exists |

---

## §8. Live-Sampling Smoke Check (Operator-run, pre-Phase-3)

**N/A for this bundle.** Tier 1S is test-infrastructure-only — zero engine / output-contract change, zero output-schema / key change, zero gate / verdict / mandate change. Nothing to live-sample. The validation surface IS the existing cohort (Brief §6 "no new test file is created"), and the cohort is green from both CWDs (§5).

---

## §9. Open Items for the Analyst

1. **Working-session number confirmation** — Brief §Closing flags this as open (S170 was the Phase 0/1 session). Operator to confirm the Phase 2/3/4 session label for the Bug Register reconciliation entries.
2. **CT001 NOT-REPRODUCIBLE disposition** — Brief §Closing flags this as Operator-confirmable. Evidence is in §4 and §5: targeted B23–B26 4/4 + full ct001_session_b 38/38 + full cohort eng004-only failure, all from repo root inside the full cohort (and dual-CWD green post-edit). FFD-001-BUG-1 precedent applies (Brief §10).
3. **No outstanding code questions.** Brief §3 forbidden-list and §4 anchors were unambiguous; no judgement-call edits were needed.

---

## §10. Closure-Criteria Tracker — Bug Register Reconciliation (Brief §Closing)

| Bug Register entry | Brief §1 / §Closing target | Phase 4 reconciliation candidate |
|---|---|---|
| **TEST-HRN-001** | All collection-order-sensitive `sys.modules` writes guarded | ✅ CLOSED, **with scope-correction note: documented 9-file set → actual 3** (per Brief §3 drift-vocabulary callout: "the TEST-HRN set is 3, not 9") |
| **BUG-CFL001-PRE-1** | `test_transform_roundtrip` passes from any CWD | ✅ CLOSED |
| **CT001-TEST-FLAKINESS** | Resolve B23–B26 disposition | ✅ CLOSED — **NOT-REPRODUCIBLE**, evidence-anchored (Brief §4.3 reproduce-first GREEN; FFD-001-BUG-1 precedent) |
| **PEO §1S** | Tier 1S bundle closed | ✅ CLOSED candidate (pending Operator Phase 4 reconciliation) |

**Doc 2 / Doc 7 / Doc 8 / EEM:** verify-only — this bundle has no spec body, no engine touch, no gate touch, no output-contract touch, no DIA cascade (Brief §11). README housekeeping: no action this Phase.

# UX-002 — Protective Anchor Output Restructuring — Phase 2 Implementation Hand-Back v1.0

**Hand-Back ID:** `UX002_Phase2_Implementation_HandBack_v1_0`
**Authoring template:** ACP v1.3 §6.5 canonical 10-section Hand-Back
**Phase:** 2 (Claude Code CLI implementation) — delivered in-session
**Spec authority:** `UX002_Protective_Anchor_Output_Restructuring_Spec_v1_0.md` v1.0 (LOCKED)
**Brief consumed:** `UX002_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Working branch:** `ux002-protective-anchor-restructure` (off `master` @ `6b89055`)
**Status at delivery:** All §4 spec edits applied; 24 new UX-002 tests GREEN; full unit cohort 3271 passed / 4 skipped / **3 failed (all PA-001-Phase-2 obsolete; predicted by §4 Finding B)**.

---

## §1. Mission Outcome

Spec §4 Change 1 (relocate `daily_atr` into `higher_frame`), Change 3a (delete the `floor_analysis.protective_anchor` group emission), Change 3b (re-home the `_flatten()` reverse map for all three flat keys) all applied to `layers/tbs_engine/transform.py`. Change 2 (DAILY_HARD_STOP desc) verified unchanged at `transform.py:3414` — no edit. New test file `layers/tests/unit/test_ux002_protective_anchor_restructure.py` carries six classes / 24 cases per spec §6, all green. Zero touch to `output.py`, `gates.py`, `data.py`, or any consumer site; zero new imports; module import graph unchanged.

| Spec change | Action | Result |
|---|---|---|
| §4.1 Change 1 — `higher_frame.daily_atr` | Inserted post-`market_stage`, Profile-A guard | ✅ Applied |
| §4.2 Change 2 — DAILY_HARD_STOP desc | Verified unchanged at `:3414` | ✅ Confirmed (no edit) |
| §4.3a Change 3a — `protective_anchor` group | Block at `:2087-2097` replaced with provenance comment | ✅ Applied |
| §4.3b Change 3b — `_flatten()` reverse-map | DAILY branch (Daily_ATR + DPA) + stop-hierarchy (Daily_Hard_Stop) + removal of legacy block | ✅ Applied |
| §6 Test cohort | `test_ux002_protective_anchor_restructure.py` (6 classes / 24 cases) | ✅ All green |

**Final cohort:** `layers/` CWD → `3271 passed / 4 skipped / 3 failed (39.2s)`. Pre-edit baseline (same cohort): `3250 passed / 4 skipped / 0 failed`. Delta: **+24 pass** (UX-002 new tests, but also: +21 net because pre-edit cohort had 3250 vs my post-edit's 3271 — the 24 new UX-002 tests minus 3 newly-failing PA-001 obsolete tests = +21 net pass change). The 3 failures are all in `test_pa001_phase2_output.py`, all assert on the now-retired `floor_analysis.protective_anchor` group, all predicted in §4 verification Finding B and out-of-scope to repair per Brief §5.

---

## §2. Scope & Authority

- **Authority hierarchy:** Spec §4 (single source of truth, LOCKED) → Brief (procedural scaffolding) → implementer interpretation. **Spec wins all conflicts** per Brief §1; two non-halting prose/example divergences resolved by quoting spec prose (§4 Findings A and B below), no scope adaptation, no halt triggered.
- **In-scope files (exactly 2):**
  - `layers/tbs_engine/transform.py` (modified)
  - `layers/tests/unit/test_ux002_protective_anchor_restructure.py` (new, 426 lines)
- **Verify-only files (no edit):**
  - `layers/tbs_engine/output.py` — confirmed unchanged at `:2590` / `:2598` / `:2603` (writers) and `:2873-2874` (Extension_Anchor labels)
  - `layers/tbs_engine/transform.py:3414` — DAILY_HARD_STOP desc string unchanged
- **`git diff --stat` (post-edit):**
  ```
  layers/tbs_engine/transform.py | 65 +++++++++++++++++++++++++++++-------------
  1 file changed, 45 insertions(+), 20 deletions(-)
  ```
  Plus one untracked new test file: 426 lines.
- **Forbidden touches honored (Brief §3, §5):** zero edits to gate functions / verdict / threshold / sizing; zero Profile B/C code path edits; zero `Daily_Protective_Anchor` / `Daily_Hard_Stop` flat-key writer edits at `output.py`; zero `MAPPED_FLAT_KEYS` membership-set edits at `transform.py:1127`; zero internal-consumer edits at `transform.py:3297` or `output.py:2873`; zero numeric-value interpolation into the `DAILY_HARD_STOP` desc (per DQ-2); zero third engine file edits; zero edits to `test_pa001_phase2_output.py` (Brief §5 two-file allowlist enforced).

---

## §3. What Was Built — Per Spec §4

Post-edit blob SHAs (`git hash-object`, pre-commit):

| File | Blob SHA |
|---|---|
| `layers/tbs_engine/transform.py` | `f301b2e9b48a24622834591b1e302b90822f2805` |
| `layers/tests/unit/test_ux002_protective_anchor_restructure.py` | `48bab2c834a3d9817cc48497c996bbeca107a1b6` |

### Edit 1 — Change 1 (spec §4.1) `higher_frame.daily_atr` sub-object

**Anchor (pre-edit):** `transform.py:1769-1901` — `higher_frame` assembly block in `_transform_output`, terminating in `floor_analysis["higher_frame"] = higher_frame if higher_frame else None`.

**Form:** 13-line insertion (10 functional + 3 comment) immediately after the `market_stage` sub-object emission, INSIDE the `if _hf_timeframe:` guard. Guard expression `_hf_timeframe == "DAILY" and _daily_atr_val is not None and _daily_atr_val > 0` — the `_hf_timeframe == "DAILY"` clause is the Profile-A indicator at this site (set by the `_has_daily` branch at `:1698-1707`, mutually exclusive with the `_has_weekly` / `_has_monthly` profile branches), and the `> 0` clause mirrors the existing safety guard at `output.py:2597` against `data.py:684`'s 0.0 default for B/C. Shape `{value, unit, desc}` matches DQ-3 (zero-churn vs the pre-edit `transform.py:2096` emission).

### Edit 2 — Change 3a (spec §4.3a) Delete `protective_anchor` group emission

**Anchor (pre-edit):** `transform.py:2087-2097` — `_daily_prot_anchor` / `_daily_hard_stop_val` / `_daily_atr_val` flat-key reads, `> 0` guard, and `floor_analysis["protective_anchor"] = {...}` assignment.

**Form:** all 11 lines replaced with a 5-line `[UX-002]` provenance comment cross-referencing the §4.3a removal and the `daily_atr` relocation to Change 1. The three `flat_metrics.get(...)` reads were deleted along with the assignment because none of those three locals were referenced anywhere else in the function (verified by re-reading the surrounding block).

### Edit 3 — Change 3b (spec §4.3b) Re-home `_flatten()` reverse map (three sub-edits)

**(a) DAILY branch additions** — `transform.py` DAILY branch of higher_frame reverse-map (was `:4312-4323`). After the existing `Context_*` extractions in the `_tf_label == "DAILY"` block, inserted a 9-line re-home stanza:
- `Daily_ATR <- hf.daily_atr.value` (sourced from Change 1's new sub-object)
- `Daily_Protective_Anchor <- hf.ema.ema_21` (numerically equal on Profile A per DQ-4)

**(b) Stop-hierarchy reverse-map augmentation** — `transform.py` was `:4816-4821` (existing `Floor_Hierarchy_Count` writer). Inserted a 7-line `_dhs_entry = next(... label == "DAILY_HARD_STOP" ...)` lookup followed by `flat["Daily_Hard_Stop"] = _dhs_entry.get("price")`, gated on entry presence (only emitted on Profile A by the existing `> 0` guard at `:3410`).

**(c) Removal of the legacy reverse-map block** — `transform.py` was `:4435-4443` (the `_pa = fa.get("protective_anchor")` block that wrote all three flat keys from the now-retired group). All 9 lines replaced with a 4-line `[UX-002]` provenance comment.

### Edit 4 — New test file `test_ux002_protective_anchor_restructure.py`

426 lines, six test classes per spec §6, TEST-HRN-001 idempotent module-loading guard (modeled on `test_sbo001_phase2.py` — `if "tbs_engine.transform" not in sys.modules:` plus `else:` rebind):

| Class | Cases | Asserts |
|---|---|---|
| `TestUX002HigherFrameDailyAtr` | 6 | Profile A `higher_frame.daily_atr == {value, unit:"price", desc}`; value matches `Daily_ATR`; absent when `Daily_ATR=0.0` or `None`; absent on B/C |
| `TestUX002ProtectiveAnchorRemoved` | 3 | `"protective_anchor" not in floor_analysis` on A / B / C |
| `TestUX002FlattenSymmetry` | 4 | Round-trip recovers `Daily_ATR` (from `higher_frame.daily_atr`), `Daily_Protective_Anchor` (from `higher_frame.ema.ema_21`, DQ-4), `Daily_Hard_Stop` (from stop-hierarchy `DAILY_HARD_STOP` entry); explicit check that legacy `protective_anchor` group is gone yet flat keys still recover |
| `TestUX002ProfileBCInvariance` | 5 | B/C have no `daily_atr` / `protective_anchor`; B's flat-key round-trip writes neither `Daily_ATR` nor `Daily_Hard_Stop` nor `Daily_Protective_Anchor` |
| `TestUX002VerdictInvariance` | 3 | Verdict preserved through transform; idempotent across re-runs; independent of `daily_atr` emission (output-shape only) |
| `TestUX002NotInGatesFile` | 3 | `inspect`/source-text negative assertion: `Daily_Protective_Anchor`, `Daily_ATR`, `Daily_Hard_Stop` absent from `gates.py` source |

**Fixture design discipline:** Profile A fixture explicitly sets `Context_EMA_21 == Daily_Protective_Anchor` (both = 145.0) to mirror the DQ-4 production invariant, AND includes `Context_Daily_SMA50` / `Context_Daily_SMA50_Slope` so `_hf_timeframe = "DAILY"` actually fires and the new reverse-map sources exist. B fixture drives `_hf_timeframe = "WEEKLY"`; C drives `"MONTHLY"`.

---

## §4. Verification — Brief §4 (Pre-Implementation, MANDATORY)

Spec §11.6 audit re-executed against working-tree HEAD = `6b89055` (`master`) before any edit. Line numbers were noted to have drifted from spec's master-as-audited anchors; matched by symbol per Brief §4 mandate.

| §11.6 # | Item | Anchor (current source) | Status |
|---|---|---|---|
| 1 | Call-order | `Daily_ATR` written at `output.py:2603`; transform reads via `flat_metrics`. | ✅ PASS |
| 2 | Sort-order | DAILY_HARD_STOP entry is verify-only; no sort. | N/A |
| 3 | Shared-ref / partition-leak | `higher_frame` is a fresh `dict` at `transform.py:1769`; not a hierarchy entry → no BUGR-002 partition / CNV-001 annotation surface. | ✅ PASS |
| 4 | Pipeline-order | output→transform; `Daily_ATR` available when higher_frame assembles. | ✅ PASS |
| 5 | Call-order feasibility | Single transform call site. | ✅ PASS |
| 6 | Cross-layout audit | `higher_frame` keys at `:1769-1901` (timeframe / ema / golden_cross / sma50 / ema_50 / sma200 / market_stage); no `daily_atr` key collision. | ✅ PASS |
| 7 | **Storage feasibility (headline)** | `_flatten(grouped)` at `:4013`; `fa = grouped.get("floor_analysis", {})` at `:4274`; `hf = fa.get("higher_frame", {})` at `:4298`; DAILY branch at `:4312-4323`; `_stp_obj = tsu.get("stop", {})` + `_fh = _stp_obj.get("hierarchy")` at `:4816-4817`. All three reverse-map sources reachable. | ✅ **PASS** — explicitly avoids the ANALYST-RLC-001-SPEC-1 storage-feasibility failure class. |
| 8 | **Consumer-retention (headline)** | `Daily_Protective_Anchor` consumed at `transform.py:3297` (Profile-A Daily EMA 21 floor entry); membership set `:1127`; writers `output.py:2590/2598/2603`; Extension_Anchor labels `output.py:2873-2874`. All retained — UX-002 touches none of these. | ✅ PASS |

**DQ-4 equivalence re-verified:** `data.py:687-691` writes `daily_ema21 = float(df_ctx['EMA_21'].iloc[-1])` (then `Daily_Protective_Anchor = round(.../price_scaler, 2)` at `output.py:2588-2590`). `gates.py` writes `Context_EMA_21` via the same `df_ctx['EMA_21']` last-bar source. On Profile A both reduce to `round(df_ctx['EMA_21'].iloc[-1] / price_scaler, 2)` → equal. The new DPA reverse-map source (`higher_frame.ema.ema_21`) is lossless in production.

**Two non-halting findings surfaced before implementation:**

- **Finding A (spec §4.1 example vs prose divergence):** the spec's code example uses `if _p_code == "A"`, but `_p_code` is not yet in scope at the higher_frame assembly site — the first in-function derivation is at `:3261`, downstream of the new insertion point. The spec **prose** is unambiguous — *"inside the Profile-A (DAILY timeframe) path"* — and at this site the DAILY timeframe IS the Profile-A indicator (set only when `_has_daily`, with `_has_weekly` / `_has_monthly` mutually exclusive). Resolution: guard on `_hf_timeframe == "DAILY" and _daily_atr_val is not None and _daily_atr_val > 0`. The `> 0` adds defence in depth against the `data.py:684` 0.0 default that would otherwise propagate through the `is not None` check on Profile B/C (verified via `getattr(ctx, 'daily_atr', None)` semantics at `main.py:175`). Resolution preserves spec intent verbatim; the divergence is spec-internal, not a contradiction.
- **Finding B (obsolete downstream tests in `test_pa001_phase2_output.py`):** spec §11 ITEM 8 audited downstream *engine* consumers but not downstream *test* consumers. Three PA-001 Phase 2 tests assert on the retired `protective_anchor` group: `TestFloorAnalysisProtectiveAnchor::test_protective_anchor_populated` (L487-502); `TestFlattenReverseMapping::test_protective_anchor_round_trip` (L626-634) which assumes recovery works even when the fixture omits `Context_Daily_SMA50` (so `higher_frame` is empty); and `TestSelfDocCompliance::test_protective_anchor_price_value_unit_desc` (L735-740). All three are fixture-decoupled from production semantics (production runs that populate `Daily_Protective_Anchor` also populate `Context_Daily_SMA50` via the context_regime gate). Brief §5 forbids editing this file → reported as failing in §5 and tracked as Phase 4 follow-up in §9.

Neither finding triggers Brief §9 halt: ITEM 7 / ITEM 8 audit headlines PASS, no third-file edit needed, no reverse-map unreachability, no spec ambiguity that the spec's own prose doesn't resolve.

---

## §5. Test Outcome

### Full unit cohort (post-edit, `layers/` CWD, no `--deselect`)

| CWD | Command | Result |
|---|---|---|
| `layers/` | `python -m pytest tests/unit/ -q --tb=no -p no:cacheprovider` | **3271 passed / 4 skipped / 3 failed**, 39.18s |

### Baseline vs. post-edit comparison

| Metric | Baseline (master `6b89055`) | Post-edit | Delta |
|---|---|---|---|
| Passed | 3250 | 3271 | +21 (= 24 new UX-002 tests minus 3 PA-001 obsolescence) |
| Skipped | 4 | 4 | 0 |
| Failed | 0 | 3 | +3 (all `test_pa001_phase2_output.py`, predicted by §4 Finding B) |

**UX-002 cohort isolated** (24/24 green): all six classes / 24 cases pass in 0.37s under the TEST-HRN-001 idempotent loading pattern. Co-runs cleanly with the rest of the cohort.

**Three failures, all out-of-scope per Brief §5:**

| Failing test | Reason | Class |
|---|---|---|
| `test_pa001_phase2_output.py::TestFloorAnalysisProtectiveAnchor::test_protective_anchor_populated` | Asserts `fa["protective_anchor"]` exists; UX-002 spec §4.3a retires the group. | Spec-intended obsolescence. |
| `test_pa001_phase2_output.py::TestFlattenReverseMapping::test_protective_anchor_round_trip` | Fixture `_base_metrics_profile_a` omits `Context_Daily_SMA50` → `higher_frame` empty → new reverse-map sources for DPA / Daily_ATR cannot fire (Daily_Hard_Stop would still recover via stop-hierarchy, but the test fails on the first `Daily_Protective_Anchor` assertion before reaching it). | Fixture-decoupled; production runs always have `Context_Daily_SMA50` co-populated with DPA. |
| `test_pa001_phase2_output.py::TestSelfDocCompliance::test_protective_anchor_price_value_unit_desc` | Accesses `result["floor_analysis"]["protective_anchor"]["price"]`; group retired. | Spec-intended obsolescence. |

**UX-002-attributable regression count: 0** (all three failures are tests of behavior UX-002 deliberately retires per spec §4.3; not bugs in the implementation). Brief §6 invariance mandate satisfied for the production output contract; PA-001 Phase 2 test file is the carrier for Phase 4 cleanup.

### Targeted PA-001 / adjacent module run (sanity check)

`pytest test_pa001_phase2_output.py test_pa001_phase3_hierarchies.py test_pa001_dual_anchor.py test_avwap001_phase1_2.py test_brk001.py test_brk001_gap2.py test_sbo001_breakout.py test_identify_trigger_diag001.py test_pe45_resolving_diagnostic.py` → **3 failed / 222 passed**. All 3 failures in `test_pa001_phase2_output.py`; all other PA-001 / AVWAP-001 / BRK-001 / SBO-001 / PE-45 cases pass. Confirms the consumer-retention contract (§4 ITEM 8) holds for everything except the now-retired group's own surfacing tests.

### Pre-edit baseline confirmation

`git stash --include-untracked && pytest test_pa001_phase2_output.py -q` → **50 passed / 0 failed**. The 3 failures are 100% UX-002-introduced (intentional). Re-stash-popped before continuing.

### Warnings

2 cohort warnings (both pre-existing, unrelated to UX-002): `pandas_ta` Pandas4Warning, `eventkit` asyncio event-loop DeprecationWarning. Matches the known-baseline noise; not introduced or removed by these edits.

---

## §6. Process Deviation

**None.** No deviations from spec §4 directives; no halts triggered.

- Both §4 audit findings (A and B) are non-halting — Finding A is a spec-internal prose-vs-example divergence resolved by quoting the prose verbatim; Finding B is a downstream test-cohort obsolescence outside the spec's §11 audit scope and outside Brief §5's edit allowlist.
- Brief §5 two-file edit boundary held: `transform.py` + new test file only. No `output.py` edit, no `data.py` edit, no `gates.py` edit, no third engine file, no edit to `test_pa001_phase2_output.py`.
- Spec §4.1's `_p_code == "A"` example treated as illustrative pseudocode; spec prose ("inside the Profile-A (`DAILY` timeframe) path") treated as authoritative. The `> 0` clause in the Profile-A guard is a defence-in-depth addition motivated by the spec's own DQ-4 §9 note ("the `daily_ema21` ATR-NaN edge is already group-suppressed by the `>0` guard") and the parallel pattern at `output.py:2597` / `transform.py:3410` — not a scope expansion.
- §4.3b stop-hierarchy lookup uses `next((e for e in _fh if ... label == "DAILY_HARD_STOP"), None)` rather than a multi-pass dict build; matches the surrounding code idiom (e.g. `next((e["label"] for e in _th if e.get("escalation_winner")), None)` at the existing `Target_Hierarchy_Winner` extraction nearby at `:4809-4811`).

---

## §7. Pre-Delivery Verification (SIR §9 — Spec §12 + Brief §7)

| Spec §12 / SIR §9 check | Status | Evidence |
|---|---|---|
| Content accuracy — edits match audited source | ✅ PASS | §4 audit table; symbol-match by surrounding-context greps; blob SHAs captured in §3 |
| Internal consistency — phasing/vocabulary consistent; §4 edits match §5 sites | ✅ PASS | Change 1 in higher_frame block; Change 3a where group was; Change 3b in three feasibility-confirmed locations |
| Format integrity — engine-source only, no `.md` SSoT edit | ✅ PASS | Only `.py` files in diff |
| Scope discipline — Profile A only; no flat-key removal; no consumer/writer touched; no gate edit | ✅ PASS | §2 forbidden-touches list; `Daily_Protective_Anchor` still consumed at `:3297`, writers still at `output.py:2590/2598/2603`; membership set `:1127` unchanged |
| Gate function verification — `TestUX002NotInGatesFile` passes; EEM §II bitwise-invariant | ✅ PASS | `gates.py` source greps for the three flat keys all return "No matches found"; all 3 negative-assertion tests green; no gate function reads any of the three flat keys, so verdict path is bitwise invariant |
| Module import verification — no new imports; acyclic graph preserved | ✅ PASS | `git diff` produces zero new `import` / `from` lines in `transform.py`; spec-declared graph `types → helpers → {gates, data, compute, exit} → {trigger, output} → main` untouched |
| `TestUX002VerdictInvariance` passes (Brief §9 halt check) | ✅ PASS | 3/3 cases green: verdict preserved through transform, idempotent across re-runs, independent of `daily_atr` emission |
| `TestUX002ProfileBCInvariance` passes (Brief §9 halt check) | ✅ PASS | 5/5 cases green: B/C never emit `daily_atr` or `protective_anchor`; B's flat-key round-trip produces no DPA / Daily_ATR / Daily_Hard_Stop |
| Reverse-map re-homing reachability (Brief §4 ITEM 7) | ✅ PASS | All three flat keys recoverable via re-homed sources; `TestUX002FlattenSymmetry` 4/4 green |
| Internal consumers (Brief §4 ITEM 8) retained | ✅ PASS | `transform.py:3297` Profile-A Daily EMA 21 floor entry untouched; `output.py:2590/2598/2603` writers untouched; `output.py:2873-2874` Extension_Anchor labels untouched; `transform.py:1127` membership set untouched |
| Bug Register updated | ⏸ PENDING (Phase 4) | Out of Phase 2 scope per spec §7 / §8 |
| DIA cascade current | ⏸ PENDING (Phase 4) | Out of Phase 2 scope per spec §8 |

---

## §8. Live-Sampling Smoke Check (Operator-run, pre-Phase-3)

**Pending Operator.** Per spec §7 closure criterion 3: ≥3 Profile A tickers should be sampled live, confirming:
- `floor_analysis.higher_frame.daily_atr` present with `{value, unit:"price", desc}` shape
- `floor_analysis.protective_anchor` absent
- `floor_analysis.higher_frame.ema.ema_21` numerically equals what `Daily_Protective_Anchor` would have been (DQ-4 invariant in production)
- `trade_setup.stop.hierarchy` `DAILY_HARD_STOP` entry unchanged (price, desc, conviction tier)
- B/C tickers: grouped output unchanged byte-for-byte vs. master

Worked example values (spec §10, LLY-style illustrative): Daily EMA 21 = 941.09, Daily ATR = 27.8, hard stop = 899.39 → `higher_frame.daily_atr.value == 27.8`; `higher_frame.ema.ema_21 == 941.09`; `protective_anchor` absent; `DAILY_HARD_STOP` entry at 899.39.

---

## §9. Open Items for the Analyst

1. **PA-001 Phase 2 test obsolescence (Phase 4 follow-up).** Three tests in `layers/tests/unit/test_pa001_phase2_output.py` fail post-UX-002 by design (§5 table). Brief §5 forbade editing this file from Phase 2. Recommended Phase 4 action: either delete the three obsolete cases (group is retired) or rewrite them to assert on `higher_frame.daily_atr` and the re-homed reverse-map paths. `TestFlattenReverseMapping.test_protective_anchor_round_trip` also needs `Context_Daily_SMA50` added to `_base_metrics_profile_a` to make `higher_frame` populate (or it needs to be split into per-key recovery assertions). Note that `TestFloorAnalysisProtectiveAnchor.test_no_protective_anchor_when_zero` and `TestProfileBCIsolation.test_profile_b_no_protective_anchor` continue to pass after UX-002 (the assertion "not in" holds vacuously) — those two need no change.
2. **Spec example vs prose at §4.1.** The spec's code example uses `_p_code == "A"`, but the variable isn't in scope at the higher_frame assembly site. Implementation followed the spec **prose** (`_hf_timeframe == "DAILY"`) which the higher_frame block already uses as its Profile-A indicator. Recommended Phase 4 housekeeping: align the spec's example block to the prose so future Phase 2 implementers don't re-encounter the divergence. Either replace `_p_code == "A"` with `_hf_timeframe == "DAILY"` in the example, or add a one-line note that the guard symbol is illustrative and the canonical site-local Profile-A indicator must be used.
3. **No outstanding code questions.** Spec §4 was sufficiently unambiguous on edit sites, reverse-map sources, and shape preservation. Spec §11 ITEMs 7 and 8 (the headline storage-feasibility and consumer-retention audit items) confirmed by re-audit against working tree.

---

## §10. Closure-Criteria Tracker — Spec §7

| Closure criterion | Status |
|---|---|
| 1. Phase 2 Hand-Back received (ACP §6.5) | ✅ DELIVERED (this document, in-session) |
| 2. New tests pass; zero UX-002-attributable regressions | ✅ MET — 24/24 UX-002 tests green; 3 PA-001 failures are spec-intended group retirement, not implementation regressions |
| 3. Live validation ≥3 Profile A tickers | ⏸ PENDING Operator |
| 4. Verdict invariance verified live (Profile A) + B/C invariance confirmed | ⏸ PENDING Operator live confirmation; static tests (`TestUX002VerdictInvariance` + `TestUX002ProfileBCInvariance`) GREEN |
| 5. IMPLEMENTED Bug Register entry logged with `file:line` + SHAs + helper/edit sites | ⏸ PENDING Phase 4 reconciliation; this Hand-Back §3 + §4 carries the file:line + blob SHA evidence |
| 6. Spec verified against final source state | ✅ MET — §3 table + §4 audit confirms each spec §4 directive applied to the named symbol |
| 7. Phase 4 DIA cascade complete (spec §8) | ⏸ PENDING Phase 4 |

**Spec §8 DIA cascade (Phase 4 candidates):** Doc 2 §IV (remove `protective_anchor` row; add `higher_frame.daily_atr`); Doc 8 §II Layer 2 mirror; Doc 7 Step 6 scan; Engine Execution Map §II verify-only; README + PEO housekeeping. None of these are Phase 2 scope.

---

### Sign-off

- **Implementer:** Claude Code CLI (Opus 4.7), in-session.
- **Spec authority:** `UX002_Protective_Anchor_Output_Restructuring_Spec_v1_0.md` v1.0 (LOCKED).
- **Brief consumed:** `UX002_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0.
- **Working branch:** `ux002-protective-anchor-restructure` @ uncommitted; base `master` @ `6b89055`.
- **Halt protocol:** none triggered; two non-halting findings (A, B) surfaced in §4 with resolution rationale.
- **Ready for:** Operator review + Phase 3 live-sampling smoke check (spec §7 criterion 3) + Phase 4 DIA cascade.

# ENG-006 Fibonacci Extension Projections + ENG-003-OBS-1 Confluence Re-Point — Phase 2 Implementation Hand-Back v1.0

**Hand-Back ID:** `ENG006_ENG003OBS1_Phase2_Implementation_HandBack_v1_0`
**Authoring template:** ACP §6.5 canonical 10-section Hand-Back (per Brief §8)
**Phase:** 2 (Claude Code CLI implementation) — delivered in-session
**Spec authority:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0 (LOCKED, S174)
**Brief consumed:** `ENG006_ENG003OBS1_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Track:** Track 1 (SIR §11.1) — single cycle, ENG-006 primary, bundled with ENG-003-OBS-1
**Working branch:** `eng006-eng003obs1-fib-extensions` (off `master` @ `68729ba`; spec audited at `master@a1906ae`)
**Implementation commit:** `979b91f` — *"ENG-006 Fibonacci extension projections + ENG-003-OBS-1 confluence re-point (Phase 2)"*
**Status at delivery:** All §4 spec edits applied; new ENG-006/ENG-003-OBS-1 test file (26 functions / 33 collected cases) GREEN; full unit cohort **3304 passed / 4 skipped / 0 failed** from both CWDs; **zero regression** vs the 3271 baseline (+33 net). NON-GATE mandate satisfied (NotInGatesFile + VerdictInvariance GREEN).

---

## §1. Mission Outcome

Both bundled NON-GATE changes applied to `layers/tbs_engine/output.py` and `layers/tbs_engine/transform.py`, with a new test file `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py`. Zero touch to `gates.py`, `data.py`, `compute.py`, `main.py`, `types.py`, `exit.py`, `trigger.py`, `charts.py`, `helpers.py`; zero new imports; module import graph unchanged. No `Profit_Target` / `Profit_Target_Source` / `_map_source_to_tier` impact.

| Spec change | Action | Result |
|---|---|---|
| §4.1 ENG-006 — extension computation (Point A/B/C, 3-point construction) | Block inserted in `output.py` `_assemble_output` after the ENG-004 MM block, inside the INF-001 unconditional region | ✅ Applied |
| §4.2 ENG-006 — 3 new flat keys `Fib_Ext_{1272,1618,2618}_Level` | Written display-scaled in `output.py`; registered in `_all_mapped_flat_keys()`; surfaced in rally grouped sub-object; round-trip reverse map added | ✅ Applied |
| §4.3 ENG-006 — target-hierarchy `FIB_EXTENSION_*` PROJECTION rows | Appended in `transform.py` `_target_entries` after MEASURED_MOVE/ATR_PROJECTION; post-partition ascending sort routes them | ✅ Applied |
| §4.4 ENG-003-OBS-1 — confluence re-point (Profile A only) | `output.py` comparison moved from `last['close']` → `metrics["Daily_Protective_Anchor"]` (raw Daily EMA 21) + null guard | ✅ Applied |
| §4.5 NON-GATE mandate | No gate/verdict/stop/target-numeric change | ✅ Confirmed |
| §6 Test cohort | `test_eng006_eng003obs1_fib_extensions.py` (10 classes / 26 functions / 33 cases) | ✅ All green |

**Final cohort (post-edit, both CWDs):** `3304 passed / 4 skipped / 0 failed`. Pre-edit baseline (same cohort): `3271 passed / 4 skipped / 0 failed`. Delta: **+33 pass** (the new ENG-006/ENG-003-OBS-1 cases), **0 failed**, **0 regression**.

---

## §2. Scope & Authority

- **Authority hierarchy:** Spec §4 (single source of truth, LOCKED) → Brief (procedural scaffolding) → implementer interpretation. **Spec wins all conflicts** per Brief §1. No halt triggered; no spec ambiguity surfaced.
- **In-scope files (exactly 3):**
  - `layers/tbs_engine/output.py` (modified — ENG-006 block + ENG-003-OBS-1 re-point)
  - `layers/tbs_engine/transform.py` (modified — registration + hierarchy rows + reverse map)
  - `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py` (new, 651 lines)
- **`git show --stat 979b91f`:**
  ```
  layers/tbs_engine/output.py                        |  99 +++-
  layers/tbs_engine/transform.py                     |  51 +-
  .../unit/test_eng006_eng003obs1_fib_extensions.py  | 651 +++++++++++++++++++++
  3 files changed, 787 insertions(+), 14 deletions(-)
  ```
- **Forbidden touches honored (Brief §3, §5):** zero edits to gate / verdict / threshold / sizing logic; zero `gates.py` / `compute.py` / `main.py` / `data.py` / `types.py` / `exit.py` / `trigger.py` / `charts.py` / `helpers.py` touch; zero `Profit_Target` / `Profit_Target_Source` / `_map_source_to_tier` / source-desc edits; zero ENG-002 / Profile B confluence "fix" (DENY per spec §9); zero Profile C extensions (exempt); zero ENG-004 Measured Move change. Diff surface is exactly the three §5 files.

---

## §3. What Was Built — Per Spec §4

Post-edit blob SHAs (`git ls-tree 979b91f`):

| File | Blob SHA |
|---|---|
| `layers/tbs_engine/output.py` | `19a66af32414ada065e25673cc2ba3ba3e1be04e` |
| `layers/tbs_engine/transform.py` | `998eb1d11da7da754e06e261c0a7fab277e7a6eb` |
| `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py` | `a20eb72c843d5f3a49987399479cfecf8350ca94` |

### Edit 1 — ENG-006 extension block (spec §4.1, §4.2) — `output.py`

**Anchor:** `_assemble_output`, immediately after the ENG-004 Measured Move block, inside the `[INF-001]` unconditional region (runs on all verdict paths).

**Form:** ~50-line block. Per-profile rally-leg recompute (no new data, in-block per the ENG-002/ENG-004 pattern):
- **Profile A** (`p_code == "A" and not is_etf`): window `df.iloc[-(bars_per_day*3+1):-1]`, origin = `['low'].min()`, peak = `['high'].max()`; gated on `len(df) > bars_per_day*3+1`, `bars_per_day*3 >= bars_per_day*2`, and `rally_range >= 0.5 * state.atr_raw` (ENG-003 history/range guards).
- **Profile B** (`p_code == "B" and state._entry_trending and not is_etf`): window `df.iloc[-11:-1]`; gated on `rally_range > 0` (ENG-002 guard).
- **Point C** = `ctx.structural_floor_raw` (used directly — not unpacked at top, per spec §11 item 7).
- **Formula (raw):** `Extension = Point_C + ratio * (peak - origin)`, `ratio ∈ {1.272, 1.618, 2.618}`; stored display-scaled `round(raw / price_scaler, 2)`.
- **Guards:** when profile/state scope unmet, window unavailable, or range below minimum → all three `Fib_Ext_*_Level = None`. Profile C falls through to `None` (exempt); ETF short-circuits via `not is_etf`.

### Edit 2 — ENG-003-OBS-1 confluence re-point (spec §4.4) — `output.py`

**Anchor:** ENG-003 Profile A confluence block (was `_current_price = last['close']`).

**Form:** comparison reference changed to `_entry_zone_ref = metrics.get("Daily_Protective_Anchor")` (raw Daily EMA 21). **Mandatory null guard** added: `if _entry_zone_ref is None or _entry_zone_ref <= 0: metrics["Fib_A_Confluence"] = None` — short-circuits **before** the five-branch ladder (no comparison against the `data.py` 0.0 default → no spurious `BELOW_FIBS`). The five-branch ladder (CONFLUENCE_382 / CONFLUENCE_500 / BETWEEN_FIBS / ABOVE_FIBS / BELOW_FIBS) is otherwise unchanged, now comparing `_entry_zone_ref` against `_fib_a_382_raw` / `_fib_a_500_raw` (both raw, units consistent). The `Fib_A_382_Level` / `Fib_A_500_Level` writes are untouched — levels remain valid geometry even when the confluence verdict is suppressed. **Profile A only.**

### Edit 3 — `transform.py` plumbing (spec §4.2, §4.3)

**(a) Flat-key registration** — three keys `Fib_Ext_{1272,1618,2618}_Level` added to the `_all_mapped_flat_keys()` list alongside `Fib_382_Level` / `MM_Target` (MAPPED_FLAT_KEYS membership; prevents `_audit_key_coverage` unmapped flag).

**(b) Rally grouped sub-object** — three locals read from `flat_metrics`; the `_rally_obj` emission guard extended to fire when any extension is present; new `extensions` sub-object (`ext_1272` / `ext_1618` / `ext_2618`, each `{price, desc}` or `None`, whole sub-object `None` when all absent).

**(c) Target-hierarchy rows** — loop appends up to three rows to `_target_entries` after MEASURED_MOVE / ATR_PROJECTION, each `{price, label: FIB_EXTENSION_*, role:{label:"PROJECTION", desc}, status: EXCEEDED|ACTIVE, escalation_winner}`. `status = "EXCEEDED"` when `_current_price > _ext_price` (routes to `cleared_levels`); `escalation_winner` is `False` unless an extension exactly equals the active `Profit_Target`. Append position is immaterial — BUGR-002 post-partition ascending sort orders them automatically.

**(d) Round-trip reverse map** — `_flatten()` reads `rally.extensions.ext_*` back into the three scalar flat keys (mirrors the `Fib_382_Level` pattern), `None`-safe for non-dict entries.

### Edit 4 — New test file `test_eng006_eng003obs1_fib_extensions.py`

651 lines, 10 test classes / 26 functions / 33 collected cases (parametrized), TEST-HRN-001 idempotent `sys.modules` loader guard:

| Class | Cases | Asserts |
|---|---|---|
| `TestENG006NotInGatesFile` | 1 | `inspect.getsource(gates)` contains none of the three flat keys nor `FIB_EXTENSION` |
| `TestENG003OBS1NotInGatesFile` | 1 | No gate verdict branch keys off `Fib_A_Confluence` / `Daily_Protective_Anchor` confluence label |
| `TestENG006VerdictInvariance` | parametrized | Verdict independent of extension anchor across profiles / verdict paths |
| `TestENG003OBS1VerdictInvariance` | 1 | Profile A verdict independent of entry-zone reference |
| `TestENG006ExtensionFormula` | 3 | Profile A + B extension values = `floor + ratio×(peak−origin)`; display-scaled (LSE scaler) |
| `TestENG006ProfileCExemption` | 1 | All three keys `None` on Profile C |
| `TestENG006DegenerateGuards` | 4 | Range below minimum / window unavailable / Profile B degenerate range / ETF short-circuit → `None` |
| `TestENG006HierarchyIntegration` | 5 | Rows present + labelled; `role.label = PROJECTION`; sorted ascending relative to MEASURED_MOVE; EXCEEDED → `cleared_levels`; absent extensions → no rows |
| `TestENG006KeyCoverage` | 3 | Keys in MAPPED_FLAT_KEYS; round-trip reconstructs scalars; round-trip `None`-safe |
| `TestENG003OBS1RePoint` | 4 | Entry zone below grid → `BELOW_FIBS`; at 38.2% → `CONFLUENCE_382`; at 50% → `CONFLUENCE_500`; levels still emitted |
| `TestENG003OBS1NullGuard` | 2 | `Daily_Protective_Anchor` = 0.0 / None → `Fib_A_Confluence = None`, levels still emitted |

---

## §4. Verification — Brief §4 / Spec §11 (Pre-Implementation, MANDATORY)

Spec §11.6 audit re-executed against working-tree HEAD before any edit. Spec audited at `master@a1906ae`; working-tree base was `master@68729ba` (UX-002 minor-correction commit, no semantic drift to the ENG-006 surface). Line numbers drifted; matched by symbol per Brief §4. No §11 anchor's semantic assumption failed → no halt.

| §11 # | Item | Finding | Status |
|---|---|---|---|
| 1 | Call-order | ENG-006 Point A/B computed in-block from `df`; ENG-003-OBS-1 reads `Daily_Protective_Anchor` written by `data.py` before output assembly. | ✅ PASS |
| 2 | Sort-order | `.append()` in fixed source order; BUGR-002 post-partition ascending sort → extension append position immaterial. | ✅ PASS (KEY) |
| 3 | Shared-ref / partition-leak | Each extension row is a fresh dict literal; no shared-ref leak into unintended array. | ✅ PASS |
| 4 | Pipeline-order | `output.py` writes extension flat keys + reads `structural_floor_raw` + rally A/B before `_transform_output` flattens for hierarchy assembly. | ✅ PASS |
| 5 | Call-order feasibility | ENG-006 block runs once per evaluation; ENG-003-OBS-1 is a one-comparison change once per Profile A eval. | ✅ PASS |
| 6 | Cross-layout audit (flat keys + desc map) | `Fib_Ext_*` keys collision-free; registered in `_all_mapped_flat_keys()`; **no** `_map_source_to_tier` / source-desc entry needed (NON-GATE rows, never `Profit_Target_Source`). | ✅ PASS |
| 7 | **Storage feasibility (headline)** | `Daily_Protective_Anchor` reachable in `_assemble_output` scope, defaults to `0.0` → null guard mandated and implemented (§4.4). `ctx.structural_floor_raw` reachable directly (not unpacked at top) → used directly. | ✅ **PASS with guard** |
| 8 | **Downstream-override audit (headline)** | `Fib_A_Confluence` single write site; downstream uses read-only → no override masks the re-pointed value. Extensions write no `Profit_Target_Source` → isolated from the FRR-001/CEG-002/BRK-001 override chain. | ✅ PASS |

**Differential verification (Brief §6):** the functional positive assertions were confirmed to FAIL against pre-edit source and PASS post-edit (so each genuinely exercises the change), per the Brief §9 functional-positive-only halt check. No halt triggered.

---

## §5. Test Outcome

### Full unit cohort (post-edit, dual-CWD per TEST-HRN-001 / BUG-CFL001-PRE-1)

| CWD | Result |
|---|---|
| repo root | **3304 passed / 4 skipped / 0 failed** |
| `layers/` | **3304 passed / 4 skipped / 0 failed** |

### Baseline vs. post-edit comparison

| Metric | Baseline | Post-edit | Delta |
|---|---|---|---|
| Passed | 3271 | 3304 | **+33** (new ENG-006/ENG-003-OBS-1 cases) |
| Skipped | 4 | 4 | 0 |
| Failed | 0 | 0 | **0** |

**ENG-006/ENG-003-OBS-1-attributable regression count: 0.** The +33 are exclusively the new bundle test cases; nothing in the prior cohort changed status. NON-GATE mandate satisfied: `NotInGatesFile` (both items) and `VerdictInvariance` (both items) GREEN.

### Warnings

Pre-existing cohort warnings only (`pandas_ta` Pandas4Warning, `eventkit` asyncio DeprecationWarning) — known-baseline noise, neither introduced nor removed by these edits.

---

## §6. Process Deviation

**None.** No deviations from spec §4 directives; no halts triggered (Brief §9 protocol not invoked).

- Brief §5 three-file edit boundary held: `output.py` + `transform.py` + new test file only.
- Point C used `ctx.structural_floor_raw` directly (not unpacked at top of `_assemble_output`) per spec §11 item 7 — the spec's stated implementer choice, not a deviation.
- ENG-003-OBS-1 null guard short-circuits before the five-branch ladder per spec §4.4 / §12 — confirmed.
- Profile B analogue (ENG-002) left unchanged per the spec §9 DENY determination; Profile C extensions not added (exempt); ENG-004 Measured Move unchanged.

---

## §7. Pre-Delivery Verification (SIR §9 — Spec §12 + Brief §7)

| Check | Status | Evidence |
|---|---|---|
| Content accuracy — edits match audited source | ✅ PASS | §4 audit table; symbol-match; blob SHAs in §3 |
| Internal consistency — §4 edits match §5 sites | ✅ PASS | ENG-006 block after ENG-004 MM; re-point at ENG-003 confluence; transform plumbing at the three §4.2/§4.3 sites |
| Format integrity — engine-source only, no `.md` SSoT edit | ✅ PASS | Only `.py` files in diff |
| Scope discipline — Profile A/B only; C exempt; no consumer/target-source touch | ✅ PASS | §2 forbidden-touches list |
| Gate-function verification — NotInGatesFile passes; verdict bitwise-invariant | ✅ PASS | `gates.py` source contains none of the three flat keys nor `FIB_EXTENSION`; no gate reads `Fib_A_Confluence` for a verdict branch |
| Module-import verification — no new imports; acyclic graph preserved | ✅ PASS | `git diff` adds zero `import` / `from` lines |
| Extension levels display-scaled in flat keys + hierarchy rows (raw only in-block) | ✅ PASS | `round(raw / price_scaler, 2)` at write sites; spec §12 |
| Null guard short-circuits before five-branch ladder | ✅ PASS | `if _entry_zone_ref is None or <= 0` precedes the ladder |
| 3 new keys in MAPPED_FLAT_KEYS; round-trip clean | ✅ PASS | `TestENG006KeyCoverage` 3/3 green |
| `git diff --stat` shows only the three §5 files | ✅ PASS | §2 stat block |
| VerdictInvariance + NotInGatesFile (Brief §9 halt checks) | ✅ PASS | both items GREEN |
| Bug Register updated | ⏸ PENDING (Phase 4) | Out of Phase 2 scope per spec §8 |
| DIA cascade current | ⏸ PENDING (Phase 4) | Out of Phase 2 scope per spec §8 |

---

## §8. Live-Sampling Smoke Check (Operator-run, pre-Phase-3)

**Pending Operator.** Per spec §7 closure criteria 3–4:
- ENG-006: sample ≥1 live Profile A and ≥1 live Profile B ticker — confirm `FIB_EXTENSION_{1272,1618,2618}` rows present in `trade_setup.target.hierarchy` (or `cleared_levels` when EXCEEDED), `role.label = PROJECTION`, sorted ascending, and verdict unchanged vs pre-fix (NON-GATE).
- ENG-006: Profile C ticker — confirm no extension rows.
- ENG-003-OBS-1: sample ≥1 live Profile A ticker where the Daily EMA 21 diverges from price — confirm `Fib_A_Confluence` reflects the **entry zone**, not price. IE-style reference (spec §2.2): entry zone 13.17, Fib 38.2% = 13.41 → expect `BELOW_FIBS` (replacing the prior misleading `CONFLUENCE_382` from price 13.43).

---

## §9. Open Items for the Analyst

1. **No outstanding code questions.** Spec §4 was unambiguous on edit sites, formula, flat-key names, hierarchy-row shape, guards, and the null-guard requirement. All §11 audit headlines (items 7, 8) re-confirmed against the working tree.
2. **Profile B analogue (ENG-002) flagged-for-awareness, no action.** Per spec §9, a *latent, bounded, same-frame* looseness exists on Profile B INVALID paths (price above the ~0.5 ATR pullback band) but is low-magnitude and not the cross-frame defect ENG-003-OBS-1 fixes. DENY determination upheld — no Bug Register item opened (would be scope creep vs the locked Profile-A-only DQ). Operator awareness only.
3. **Phase 4 DIA cascade (spec §8)** pending: Doc 2 §IV + §4.2.x (FIB_EXTENSION_* contract + ENG-006 paragraph) and §4.2.4 (ENG-003 confluence → Daily EMA 21 entry zone); Doc 7 Step 6 (Operator reading guidance); Doc 8 §II Layer 2 mirror; EEM §II verify-only; README + PEO version bumps; Bug Register (ENG-006 SPECIFIED→…→CLOSED, ENG-003-OBS-1 IDENTIFIED→…→CLOSED, register bundle).

---

## §10. Closure-Criteria Tracker — Spec §7

| Closure criterion | Status |
|---|---|
| 1. `output.py` + `transform.py` edits per §4; no other engine module touched | ✅ MET — §2 stat (3-file diff) |
| 2. New test file; all NON-GATE + functional assertions pass; full cohort zero-regression (dual-CWD) | ✅ MET — 33/33 new green; 3304/4/0 both CWDs; 0 regression |
| 3. ENG-006 levels verified on ≥1 live Profile A + ≥1 live Profile B (Phase 3) | ⏸ PENDING Operator |
| 4. ENG-003-OBS-1 re-point verified live where Daily EMA 21 diverges from price | ⏸ PENDING Operator |
| 5. Engine-source authority on a merged branch; post-Phase-2 SHAs recorded | ⏸ PENDING merge (Operator-led); commit `979b91f` + blob SHAs in §3 |
| 6. Phase 4 6-Doc DIA cascade + Bug Register advance + bundle registration | ⏸ PENDING Phase 4 |

---

### Sign-off

- **Implementer:** Claude Code CLI (Opus 4.8, 1M context), in-session.
- **Spec authority:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0 (LOCKED, S174).
- **Brief consumed:** `ENG006_ENG003OBS1_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0.
- **Working branch:** `eng006-eng003obs1-fib-extensions` @ commit `979b91f`; base `master` @ `68729ba` (spec audited at `a1906ae`).
- **Halt protocol:** none triggered; no non-halting findings beyond the spec-anticipated null-guard (implemented per §4.4).
- **Ready for:** Operator review of `979b91f` + Phase 3 live-sampling smoke check (spec §7 criteria 3–4) + Phase 4 DIA cascade. **Not pushed/merged** (Operator-led per Brief §2 / SIR §1.5.3).

# ITS-001 — Claude Code CLI Implementation Brief (Phase 2 Entry Artifact)

**Document ID:** `ITS001_Claude_Code_CLI_Implementation_Brief_v1_0.md`
**Version:** v1.0
**Status:** Phase 2 entry — for Claude Code CLI implementation venue
**Date authored:** 2026-05-26 (Session 165 — Phase 2 Brief-authoring turn)
**Spec authority:** `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md` v1.0.1 (locked Session 165, 2026-05-24)
**Authoring Analyst (Project chat):** Phase 1 close → Phase 2 entry per ACP §6.4 + SIR §11.6 two-layer defense.
**Template anchor:** ACP §6.4 canonical 11-section Brief structure (codified S162 via GOV-003). Sibling precedent: `RLC001_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0 (S160, first canonical-format brief).

---

## §1. Mission

Implement ITS-001 v1.0.1 in `tbs_engine` per spec §4 (Implementation Specification). **The spec is the single source of truth.** This brief is procedural scaffolding for the Claude Code CLI venue — it references spec sections, does NOT restate spec contracts. **Conflict resolution rule: when this brief and the spec disagree, the spec wins.**

---

## §2. Operational Context (CLI Venue)

- **Working tree access:** Direct read/write on `roescha/TBS_Master_App@master` working-tree at `layers/tbs_engine/` + `layers/tests/unit/`. No uploads required — engine source is on disk.
- **Permission mode:** `.claude/settings.json` `permissions.defaultMode: "acceptEdits"` (codified at CFL-001-PROC-1 S157 + SIR §1.5.6). File edits auto-approve; shell commands (pytest, git, IBKR-touching) still prompt — that is intentional.
- **Test invocation:** Local `pytest` against `layers/tests/unit/` (full cohort + the new ITS test file). Current regression baseline `3133 passed / 5 skipped / 1 failed` per RLC-001 S160 hand-back, plus any net-new tests landed since (verify at Phase 2 entry).
- **Hand-back delivery:** **In-session at end of Phase 2 cycle** per SIR §1.5.2 and ACP §6.5 — NOT chat-paste, file-attachment, or upload. Conforms to ACP §6.5 canonical 10-section structure.
- **Git context:** Implementer works on a feature branch (suggested name: `feat/ITS-001-intraday-tactical-surface`) and commits implementation + tests + spec + brief + hand-back together at end of Phase 2 (or as 2–3 commits per Operator preference) per SIR §1.5.2.
- **Engine source authority:** `master` HEAD as of Phase 2 session start. Spec §12 records the engine SHAs verified at spec authoring (2026-05-24); the implementer re-verifies via `git log -1` at session start and re-runs §4 Pre-Implementation Verification if those files have advanced.

---

## §3. Phase Boundaries + Vocabulary Constraints

### 3.1 Phase 2 — In Scope

- Implement spec §4.1 (compute.py constants + helpers + `__all__` update)
- Implement spec §4.2 (`_detect_compression_shelf` helper)
- Implement spec §4.3 (`_compute_intraday_tactical_levels` + `_derive_intraday_high` helpers)
- Implement spec §4.5 (output.py `_ITS_NULL_FLAT_KEYS` + `_assemble_intraday_tactical` helper + `__all__` update + call site in `_assemble_output`)
- Implement spec §4.6 (transform.py flat-key registration + top-level group emission + per-field `lookback_stale` annotation)
- Implement spec §4.7 (types.py `RunContext` attribute declarations)
- Implement spec §4.8 (main.py call site between VOL-001 and RLY-001)
- Author the test file at `layers/tests/unit/test_its001_intraday_tactical.py` covering the 21 test classes / ~75 tests per spec §6.1
- Execute spec §4 Pre-Implementation Verification (§11.6 items 1–9) at session start; halt if any check fails
- Execute spec §6 test mandate + §10 acceptance + §11.6 implementer audit at session close
- Deliver Hand-Back conforming to ACP §6.5 (see §8 below)
- Operator-run pre-Phase-3 smoke validation (optional, encouraged) — captured in Hand-Back §8

### 3.2 Phase 2 — Out of Scope

- **Phase 3 live validation** (Operator-led IBKR cohort run) — closure criterion #4 + #5 + #6 + #7 are Phase 3 work
- **Phase 4 DIA cascade** (6-doc sync per spec §7 criterion #8 — Doc 2 / Doc 7 / Doc 8 / EEM / README / PEO) — Project-chat-Analyst-led after Phase 3 closes
- **Bug Register status advance** beyond 🟡 IMPLEMENTED — Phase 4 / closure work
- **v1.1 enhancements** (spec §1.3 + §9) — `INTRADAY-CAL-1`, `INTRADAY-CAL-2`, `INTRADAY-CFL-INTEGRATION-1`, opening-range shelf, AVWAP-pinch shelf, range-break event detection, NEAR_UPPER/NEAR_LOWER labels, AVWAP-anchored stops, signal-bar stops, trailing-stop variants, R-multiple targets, Bollinger targets, 15-min bar-frame promotion, prior-session shelves, `relative_to_structural_floor` annotation, Profile B/C extension, CFL-001 cross-surface confluence
- **Spec amendment** — Phase 2 does NOT amend the spec. If the implementer discovers a spec defect during Pre-Implementation Verification, the protocol is halt-and-surface per §9 below (no unilateral spec adaptation; surface to Operator, await Project-chat-Analyst resolution).

### 3.3 Phase 2 Lexicon (admissible vocabulary)

- **Engine verdict labels** (read-only references — ITS does NOT modify these): `VALID`, `WAIT`, `INVALID`, `RECOVERY CANDIDATE`, `ERROR`
- **ITS event types** (new): `GAP_UP`, `GAP_DOWN`, `VOL_EXPANSION`, `MULTIPLE`, `null`
- **ITS shelf position labels** (new): `ABOVE`, `BELOW`, `WITHIN`
- **ITS target source labels** (new): `INTRADAY_HIGH`, `SHELF_UPPER_PROJECTION`, `SHELF_WIDTH_PROJECTION`, `EXTENDED_RANGE_PROJECTION`, `NOT_APPLICABLE`
- **ITS stop methodology labels** (new): `shelf_structural`, `atr_volatility`
- **ITS anchor values** (new): `shelf_lower`, `shelf_upper`, `both`
- **ITS sub-objects** (new): `intraday_tactical` (top-level), `shelf`, `lookback_status`, `tactical_stop`, `near_term_target`
- **ITS field** (new): `lookback_stale: bool` on annotated hierarchy entries

### 3.4 Drift Signals (out-of-phase vocabulary — STOP and re-read spec §1.3 if implementer reaches for these)

- "Phase 3" / "live validation" / "live cohort" / "ticker run" — Phase 3, not Phase 2
- "Phase 4" / "DIA" / "cascade" / "Doc 2" / "Doc 7" / "Doc 8" / "EEM" / "README" / "PEO" — Phase 4
- "v1.1" / "extension" / "promote to hierarchy" / "CFL-001 confluence" / "opening_range" / "AVWAP-pinch" / "range-break" / "NEAR_UPPER" / "NEAR_LOWER" / "avwap_anchored stop" / "signal_bar stop" / "trailing stop" / "R-multiple target" / "Bollinger target" / "15-minute" / "prior-session shelf" / "Profile B intraday" / "Profile C intraday" — v1.1+ deferred
- "amend spec" / "extend spec" / "adapt spec" — Phase 2 does NOT amend spec; halt-and-surface per §9 if defect found
- "INVALID" / "REJECT" / "FAIL" / "verdict change" applied to swing-frame action_summary — ITS is verdict-invariant by design (§7 closure criterion); any such language signals a misunderstanding of DQ-2 / §1.4 non-goal #1

---

## §4. Pre-Implementation Verification

**MANDATORY before any code edit.** This is the implementation-side defense layer of SIR §11.6, mirroring the spec-side audit the Project-chat Analyst executed at Phase 1 (spec §11 — 8 items VERIFIED + 1 DEFERRED). The implementer re-verifies each item against working-tree engine source with `file:line` evidence anchors. **If any item fails, halt per §9 and surface to the Operator before writing code.**

Reference: **spec §11 Pre-Implementation Checklist** (the 9-item table is the authoritative source — do NOT restate here; this brief lists only the implementer's verification protocol).

### 4.1 Verification procedure

For each spec §11 item, execute:

1. Open the engine file at the `file:line` anchor cited in spec §11 (or via `grep` if the anchor has drifted — `~`-prefixed anchors are approximate at spec-authoring date 2026-05-24).
2. Confirm the pattern stated in the spec §11 item is present and intact (call ordering, signature shape, partition site, override-path enumeration, etc.).
3. Annotate the result PASS / DRIFTED / FAILED in the Hand-Back §4 with a fresh `file:line` evidence anchor reflecting current source state.
4. If DRIFTED but the spec contract is structurally preserved (e.g., the line number has shifted by ±50 lines but the call sequence is intact), document the drift and proceed. Drift within the `~`-prefixed approximate-line convention is acceptable.
5. If FAILED (structural assumption broken — e.g., call ordering changed; `_transform_output` now receives ctx; shared-reference partition leaked; an override path now touches `Intraday_*` keys), HALT per §9.

### 4.2 Item 9 specifically — resolution at Phase 2 entry

Spec §11 item 9 is 🟡 DEFERRED at spec authoring: verify whether AVWAP-001 emits a `floor_analysis.avwap_10bar` sub-object that ITS should annotate. The implementer:

1. Greps `output.py` and `transform.py` for `avwap_10bar` / `AVWAP_10BAR` references.
2. If a sub-object exists and is structurally similar to other annotated hierarchy entries: add `lookback_stale` annotation per spec §4.6 transform-side mutation pattern (consistent with ESTABLISHED_LOW and DAILY_HIGH annotation).
3. If NO such sub-object exists: silently drop the third annotation site per spec DQ-1a hybrid semantics (spec §3.4 last paragraph + §11 item 9 explicit resolution path). Document the drop in Hand-Back §6 Process Deviation.

### 4.3 Storage-mechanism re-verification (Item 7 — strongest precedent risk class)

The ANALYST-RLC-001-SPEC-1 incident (S160) was a storage-mechanism feasibility failure: spec assumed `_transform_output` received ctx; it does not. ITS-001 spec §5.2 explicitly verified storage uses the RLY-001 `(block, flat_keys)` tuple pattern with sentinel-key stash. The implementer MUST confirm at Phase 2 entry:

1. `_transform_output(action_summary, flat_metrics, debug=False)` signature unchanged in transform.py (no ctx parameter).
2. RLY-001 sibling pattern at `output.py:~L685-L800` intact — `_assemble_rally_state` returns `(block, flat_keys)` tuple consumed by `_assemble_output` which merges flat_keys into metrics.
3. Sentinel-key idiom — confirm no existing flat key collides with `_intraday_tactical_block` (the proposed sentinel).

**If any of these three sub-checks fails, HALT per §9.** This is the highest-precedent risk class (7 ANALYST-class records before SIR §11.6 codified the discipline).

### 4.4 Verdict-invariance pre-verification

Before writing the helper code, write the `TestITS001VerdictInvariance` test class FIRST (per spec §6.1). The test runs a 4-ticker Profile A fixture cohort through the engine pre-ITS and post-ITS and asserts identical `action_summary.verdict` on each. This is the canonical defense against accidentally feeding `Intraday_*` keys into a gate. If the test fails post-implementation, HALT — the failure means a gate consumed an ITS key.

---

## §5. Implementation Scope (Working-Tree Edits)

### 5.1 Files in scope (5 engine modules + 1 new test file)

| # | File | Edits per spec | Reference |
|---|------|----------------|-----------|
| 1 | `layers/tbs_engine/types.py` | `RunContext` attribute declarations (18 new attrs, defaulted to None / False) | Spec §4.7 |
| 2 | `layers/tbs_engine/compute.py` | Module-level constants (12) + 3 new helpers (`_detect_intraday_events`, `_detect_compression_shelf`, `_compute_intraday_tactical_levels`) + 1 module-level helper (`_derive_intraday_high`) + `__all__` update | Spec §4.1 + §4.2 + §4.3 + §4.4 |
| 3 | `layers/tbs_engine/output.py` | `_ITS_NULL_FLAT_KEYS` dict + `_assemble_intraday_tactical` helper + `__all__` update + 1 call site inside `_assemble_output` | Spec §4.5 |
| 4 | `layers/tbs_engine/transform.py` | 18 new flat-key registrations in `_all_mapped_flat_keys()` + top-level `intraday_tactical` group emission in `_transform_output` (sentinel-key read pattern) + per-field `lookback_stale` annotation on 2 hierarchy emission sites (ESTABLISHED_LOW + DAILY_HIGH; conditional on Item 9 audit for AVWAP_10BAR) | Spec §4.6 |
| 5 | `layers/tbs_engine/main.py` | 1 call-site insertion: 3 helper invocations between VOL-001 (`_compute_volume_at_price`) and RLY-001 (`_compute_rally_state_for_ctx`) at ~L210–L215 | Spec §4.8 |
| 6 (new) | `layers/tests/unit/test_its001_intraday_tactical.py` | 21 test classes / ~75 tests per spec §6.1 | Spec §6 |

### 5.2 Files explicitly OUT of scope

**Forbidden file edits:**

- `layers/tbs_engine/gates.py` — ITS does not gate-feed (closure criterion §7 #7 verdict invariance; spec §1.4 non-goal #1). `TestITS001NotInGatesFile` is the explicit negative-assertion test.
- `layers/tbs_engine/data.py` — no data-fetching change required (ITS reads existing primary-frame hourly df + state.atr_raw).
- `layers/tbs_engine/exit.py` — no exit-signal change.
- `layers/tbs_engine/trigger.py` — no trigger change.
- `layers/tbs_engine/charts.py` — no charts change.
- `layers/tbs_engine/helpers.py` — no shared-helper change (ITS helpers live in compute.py per spec §4.1–§4.3).
- `layers/tbs_orchestrator.py` — out of engine scope; consumer updates are non-blocking per Project Instructions Engine-First Development rule and tracked under ORCH-002.
- `layers/tbs_scanner.py` — same as orchestrator; trivial to update post-engine, non-blocking.
- Any spec file in `docs/specs/` — Phase 2 does NOT amend specs (§9 halt-and-surface protocol).
- Any document in `/mnt/project/` or `docs/` other than the working-tree engine source listed above.

**If a seventh engine file appears in `git diff --stat` at hand-back time, the implementer MUST surface it in Hand-Back §6 Process Deviation.** Track 1 admissibility permits multi-file scope per spec, but any file beyond the 5 enumerated above is OUT of spec scope.

### 5.3 Implementation order recommendation (non-binding)

1. `types.py` — RunContext attrs (no dependencies; lowest risk).
2. `compute.py` constants — module-level (no dependencies).
3. `compute.py` `_derive_intraday_high` helper — pure function, easiest to unit-test in isolation.
4. `compute.py` `_detect_intraday_events` helper.
5. `compute.py` `_detect_compression_shelf` helper.
6. `compute.py` `_compute_intraday_tactical_levels` helper.
7. `compute.py` `__all__` update.
8. `output.py` `_ITS_NULL_FLAT_KEYS` dict.
9. `output.py` `_assemble_intraday_tactical` helper + `__all__` update.
10. `output.py` call site inside `_assemble_output` (after `_assemble_rally_state`, before `_transform_output`).
11. `transform.py` flat-key registration in `_all_mapped_flat_keys()`.
12. `transform.py` top-level group emission in `_transform_output`.
13. `transform.py` per-field `lookback_stale` annotation (2 or 3 hierarchy emission sites depending on Item 9 audit).
14. `main.py` call-site insertion at L210–L215.
15. Test file authoring — write `TestITS001VerdictInvariance` and `TestITS001NotInGatesFile` FIRST per §4.4 above; then the remaining 19 classes.
16. Local pytest — new test file in isolation first, then full cohort.

---

## §6. Test Mandate

### 6.1 Test file

**Path:** `layers/tests/unit/test_its001_intraday_tactical.py`

**Coverage target:** 21 test classes / ~75 tests per spec §6.1 table.

### 6.2 Idempotent test harness pattern (mandatory per TEST-HRN-001)

Per the post-TEST-HRN-001 hygiene rule: use `spec_from_file_location` to load engine modules WITHOUT polluting global `sys.modules`. Idempotent guard: `if name in sys.modules: return sys.modules[name]`. Reference precedent: `test_rlc001_reclaim_quality.py` (S160), `test_rly001_rally_state.py` (S158), `test_cfl001_confluence.py` (S157).

### 6.3 Critical-path tests (write FIRST per §4.4)

1. `TestITS001VerdictInvariance` — single-test class running 4-ticker Profile A fixture cohort through engine pre-ITS and post-ITS, asserting identical `action_summary.verdict`. The canonical defense against accidental gate-feeding. **Must pass for any code commit.**
2. `TestITS001NotInGatesFile` — single-test class using `inspect.getsource(gates)` to assert no `Intraday_*` flat key string appears in any `gates.py` function body. **Must pass for any code commit.**

### 6.4 Regression baseline + acceptance

- Full pytest cohort baseline: `3133 passed / 5 skipped / 1 failed` per RLC-001 S160 hand-back (re-verify at Phase 2 session start; baseline may have advanced).
- Pre-existing failure `test_eng004_measured_move::test_transform_roundtrip` (BUG-CFL001-PRE-1, S157) — out of scope; remains as-is.
- ITS-001 acceptance: ~75 new tests pass + zero new regression failures.

### 6.5 pytest invocation

Suggested local invocations (implementer adapts to preference):
- New file in isolation: `pytest layers/tests/unit/test_its001_intraday_tactical.py -v`
- Full cohort: `pytest layers/tests/unit/ -v --tb=short`
- Targeted critical-path: `pytest layers/tests/unit/test_its001_intraday_tactical.py::TestITS001VerdictInvariance layers/tests/unit/test_its001_intraday_tactical.py::TestITS001NotInGatesFile -v`

---

## §7. Pre-Delivery Verification

**MANDATORY before Hand-Back delivery.** SIR §9 checklist applies. Additionally, spec §10 Acceptance criteria are the spec-defined closure-at-Phase-2 set.

### 7.1 SIR §9 Pre-Delivery checklist

- [ ] **Content accuracy:** Hand-Back content matches engine source state (re-verify, don't recall).
- [ ] **Internal consistency:** Hand-Back does not contradict itself (phase boundaries respected, vocabulary consistent with §3 lexicon, no Phase 3 / Phase 4 vocabulary).
- [ ] **Format integrity:** Hand-Back is `.md` per SIR §1.3 (no `.docx`).
- [ ] **Scope discipline:** Hand-Back §2 `git diff --stat` shows only the 5 engine files + 1 new test file from §5.1 above (no seventh file unless surfaced in §6 Process Deviation).
- [ ] **Gate function verification:** EEM §II gate function table — verify no gate function added, no ordering change, no new gate-input flat key. (ITS does not touch gates — this is a verify-only check.)
- [ ] **Module import verification:** Module imports remain acyclic `types → helpers → {gates, data, compute, exit} → {trigger, output} → main`. ITS adds no cross-module imports beyond existing patterns.
- [ ] **Bug Register updated:** No new bugs discovered → Hand-Back §6 says "None". Any defect discovered during implementation logged to surface to Project chat (Hand-Back §9 Open Items for the Analyst).
- [ ] **DIA current:** Phase 4 DIA is OUT of Phase 2 scope per §3.2 — Hand-Back §10 closure tracker marks DIA-related criteria as "pending Project-chat work".

### 7.2 Spec §10 Acceptance

- [ ] All spec §6 tests pass (~75 tests)
- [ ] Zero regression failures on full pytest cohort (baseline 3133/5/1 — verify at Phase 2 entry)
- [ ] Engine runs cleanly on at least 1 Profile A test ticker with `intraday_tactical` group rendering in output JSON per spec §8 worked examples

### 7.3 Spec §11.6 implementer-side audit re-execution

For each spec §11 item, confirm the post-implementation state matches the spec-side claim:
- Item 1 (Call-order verification): main.py call site inserted at L210–L215; precedes `_assemble_output`. Confirm via `grep -n "_detect_intraday_events\|_assemble_output" layers/tbs_engine/main.py`.
- Item 2 (Sort-order): N/A — ITS does not operate on sortable iterables.
- Item 3 (Shared-reference / partition-leak): `intraday_tactical` top-level group lives outside BUGR-002 partition. Confirm via inspection of `_transform_output` body — partition site (search for `cleared_levels` / `overhead_levels`) is unrelated to ITS emission site.
- Item 4 (Pipeline-order feasibility): All compute helpers run pre-gate at tier 3; reads at tier 8 (`_assemble_output`); writes complete. Confirm via execution order check in main.py.
- Item 5 (Call-order feasibility): Three ITS helpers sequential — `_detect_intraday_events` → `_detect_compression_shelf` → `_compute_intraday_tactical_levels`. `_compute_intraday_tactical_levels` reads `ctx._intraday_shelf_*` written by `_detect_compression_shelf`. Confirm via the main.py L210–L215 insertion site.
- Item 6 (Cross-spec layout audit): No existing top-level group named `intraday_tactical`. Confirm via `grep -rn "intraday_tactical" layers/tbs_engine/` returning only ITS-001 files.
- Item 7 (Storage-mechanism feasibility): `(block, flat_keys)` tuple pattern matches RLY-001 sibling at `output.py` — `_assemble_intraday_tactical` returns tuple; `_assemble_output` merges flat_keys + stashes block under sentinel key in metrics; `_transform_output` reads sentinel key. NO ctx-attribute transfer to transform.py.
- Item 8 (Downstream-override-path audit): `_assemble_output` DD-2 EXIT override + BKOUT-001 GAP-5 override mutate `action_summary.verdict` only. Confirm via `grep -n "Exit_Signal.*EXIT\|GAP-5" layers/tbs_engine/output.py` that neither touches `_intraday_tactical_block` or any `Intraday_*` flat key.
- Item 9 (avwap_10bar sub-object existence): Resolved at §4.2 above — annotate if present, drop if absent.

---

## §8. Hand-Back Contract

Deliver a Hand-Back conforming to **ACP §6.5 canonical 10-section template** at end of Phase 2 session, in-session (NOT chat-paste / file-attachment / upload).

**Filename:** `ITS001_Phase2_Implementation_HandBack_v1_0.md`

The Hand-Back's 10 sections + amendment rule + grandfathered handling are defined in ACP §6.5 — do NOT restate here. The implementer follows ACP §6.5 directly. RLC-001 v1.0 Hand-Back (S160) is the canonical structural precedent.

Project-chat-Analyst Phase 4 reconciliation consumes the Hand-Back: §6 Process Deviation (if any) drives spec amendment scope (e.g., the RLC-001 v1.0 → v1.1 amendment landed S161 from §6 deviations); §9 Open Items for the Analyst drives Bug Register entries; §10 closure-criteria tracker drives the DIA cascade.

---

## §9. Failure-Mode Protocol

**Halt-and-surface triggers.** If any of the following fires during Phase 2, the implementer HALTS immediately, surfaces the issue in the CLI session, and does NOT commit. Working-tree edits made before the halt are left in place for the Operator + Project-chat-Analyst to inspect.

### 9.1 Pre-Implementation Verification failure (§4)

Any spec §11 item that fails verification (e.g., `_transform_output` now receives ctx contrary to spec §11.5; main.py call ordering changed; BUGR-002 partition shape changed; an override path now touches `Intraday_*`). HALT. Surface the specific item + the engine source evidence + the spec section that no longer matches. Await Project-chat-Analyst resolution. **Do NOT unilaterally adapt the spec.**

### 9.2 VerdictInvariance failure

`TestITS001VerdictInvariance` fails (any change to swing-frame `action_summary.verdict` on identical inputs pre/post-ITS). HALT. This means a gate consumed an ITS key — the closure criterion §7 #7 is broken. The most likely cause is an accidental `gates.py` edit or an `Intraday_*` flat key being read in a verdict-producing path. Surface the failing fixture + the verdict drift evidence.

### 9.3 NotInGatesFile failure

`TestITS001NotInGatesFile` fails (any `Intraday_*` string found in `gates.py` body). HALT. This is the same failure class as §9.2 caught at a different layer — surface and resolve before any commit.

### 9.4 Profile-scope leak failure

`TestITS001ProfileScope` fails (an `intraday_tactical` group emits on Profile B or Profile C output JSON). HALT. The Profile-A-only contract is broken. Most likely cause: the `_assemble_intraday_tactical` Profile-A-scope guard is bypassed, or `_transform_output` emits the sentinel-key block without checking it is non-None.

### 9.5 Sixth-engine-file diff-stat

`git diff --stat` at pre-commit time shows a sixth engine file edit beyond the 5 enumerated in §5.1. HALT. Document the file + the rationale + surface in §6 Process Deviation. Do NOT commit until Operator confirms the out-of-scope edit is acceptable.

### 9.6 Spec ambiguity discovery

If the spec is ambiguous on a Phase 2-relevant decision (e.g., a sub-decision not covered in §2 DQs that the implementer encounters mid-edit), HALT. Surface the ambiguity in-session + describe the alternative interpretations + propose a default if applicable. Await Project-chat-Analyst resolution. **Do NOT unilaterally choose.** This is the canonical SIR §11.6 ANALYST-class-incident defense — the spec author may have missed an architectural sub-decision; surfacing it here is how the two-layer defense works.

### 9.7 Storage-mechanism failure (highest-precedent class)

If the `(block, flat_keys)` tuple pattern does not propagate through `_assemble_output` → metrics → `_transform_output` as spec §5.2 describes (e.g., the sentinel key gets stripped somewhere; the flat_keys merge collides with existing keys; the block stash is overwritten), HALT. This is the same class as ANALYST-RLC-001-SPEC-1 (S160) — surface the storage-mechanism gap and await spec amendment via Project-chat resolution.

### 9.8 Regression baseline drift

If the pre-implementation full-pytest baseline does NOT match `3133/5/1` (significantly different — e.g., a new failure has landed in master between RLC-001 S160 and Phase 2 session start), document the new baseline in Hand-Back §5 Test Outcome. This is informational, not a halt — the baseline simply advances. But if a NEW failure appears post-ITS-implementation that did not exist pre-ITS, that IS a regression — halt and investigate.

---

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

These are read-only working-tree anchors the implementer consults for pattern matching. Do NOT edit any of these files (they are not in §5.1 scope).

### 10.1 RLY-001 — primary sibling pattern

**Spec:** `docs/specs/RLY001_Rally_Age_Streak_Primitive_Spec_v1_1.md` (S159 canonical).
**Hand-back:** `docs/handbacks/RLY001_Phase2_Implementation_HandBack_v1_0.md` (S158 — grandfathered structure per SIR §1.5.7).
**Engine patterns to mirror:**
- `output.py:~L685-L800` — `_assemble_rally_state(ctx, p_code)` returns `(block, flat_keys)` tuple. ITS `_assemble_intraday_tactical` mirrors this signature shape.
- `output.py` call site for `_assemble_rally_state` inside `_assemble_output`. ITS call site is INSERTED AFTER this one, per spec §4.5 last paragraph.
- `transform.py` `_MAPPED_FLAT_KEYS_RALLY_STATE` reverse-map + flat-key registration in `_all_mapped_flat_keys()`. ITS adds 18 flat keys to the same registration function per spec §4.6.
- `main.py:~L215` `_compute_rally_state_for_ctx(ctx)` call. ITS calls inserted BEFORE this one per spec §4.8.
- `types.py` `_rly_*` RunContext attribute declarations. ITS adds 18 `_intraday_*` attributes per spec §4.7.

### 10.2 RLC-001 — secondary sibling pattern (post-S160 with §11.6 lessons absorbed)

**Spec:** `docs/specs/RLC001_Reclaim_Quality_Score_Spec_v1_1.md` (S161 canonical, supersedes v1.0).
**Hand-back:** `docs/handbacks/RLC001_Implementation_HandBack_v1_0.md` (S160 — first canonical ACP §6.5 structure).
**Brief (precedent):** `docs/briefs/RLC001_Claude_Code_CLI_Implementation_Brief_v1_0.md` (S160 — first canonical ACP §6.4 structure).
**Lessons relevant to ITS:**
- RLC-001 v1.0 spec §4.5 had a storage-mechanism failure (assumed `_transform_output` receives ctx; it does not). RLC-001 v1.1 corrected to attach in `output.py` directly. ITS-001 spec already adopts the corrected pattern via the sentinel-key idiom — verify at §4.3 Pre-Implementation Verification that this pattern is intact.
- RLC-001 v1.0 helper guard was insufficient against downstream verdict-override paths (DD-2 EXIT + BKOUT-001 GAP-5). ITS-001 §11.6 item 8 verified the override paths do NOT touch ITS output — re-confirm at §4 implementer audit.

### 10.3 VTRIG-001 — attachment-idiom precedent

**Engine pattern:** Direct dict assignment idiom — `action_summary['vtrig'] = block` at post-action_summary-construction site in `_assemble_output`. ITS does NOT use this idiom directly (ITS attaches the block via the sentinel-key flat_metrics stash, not via action_summary), but VTRIG-001 is the precedent for ANALYST-RLC-001-SPEC-1 resolution at S160 → S161.

### 10.4 CFL-001 — call-site placement + post-partition idiom

**Spec:** `docs/specs/CFL001_Level_Confluence_Detection_Spec_v1_1.md` (S157 canonical).
**Engine patterns relevant:**
- `transform.py` post-partition placement (CFL-001 v1.1 §4) — references the BUGR-002 partition site that ITS §11.6 item 3 audited. ITS lives entirely outside the partition (top-level group), but the partition site itself is a `file:line` anchor the implementer locates during §4 verification.

### 10.5 BRK-001 + RLY-001 — module-level constant placement convention

Spec §4.1 cites the existing `RLY_*` / `BRK_*` constants as the placement precedent for the new `INTRADAY_*` constants. The implementer inserts the ITS constants in compute.py near these existing blocks (~L13–L30 per spec §4.1 anchor).

### 10.6 TEST-HRN-001 — idempotent test-harness pattern

**Bug Register entry:** TEST-HRN-001 (S137-cont 🔴 IDENTIFIED — 9 affected files still pending mechanical backport; ITS test file MUST use the safe pattern, joining the 3 safe-pattern files already extant: `test_bugr002_hierarchy_partition.py`, `test_eng004_measured_move.py`, `test_pa001_phase3_hierarchies.py`, plus all post-TEST-HRN-001 test files including `test_rlc001_reclaim_quality.py`).

### 10.7 PE-43 — bar-evaluation convention

Spec §2.5.2 + §2.7.3 invoke the `iloc[-(N+1):-1]` convention (PE-43, S118 closure). ITS-001's `_detect_compression_shelf` follows this convention (evaluated bar EXCLUDED from shelf window); `_derive_intraday_high` deliberately departs (evaluated bar INCLUDED — distinct from `resistance_raw`). Both conventions cited in spec §2.7.3 critical-convention-distinction block.

---

## §11. Estimated Effort

Moderate scope. Compared to recent sibling implementations:
- **RLY-001 (S158):** 4 engine modules + 2 pre-approved (`main.py` + `types.py`) + 58 new tests across 10 classes. Net engine LOC ~+260.
- **CFL-001 (S157):** 1 engine module (`transform.py`) + 36 new tests across 8 classes. Net engine LOC ~+173.
- **RLC-001 (S160):** 2 engine modules (`output.py` + `transform.py`) + 65 new tests across 10 classes.

**ITS-001 expected envelope:**
- 5 engine modules touched (`types.py`, `compute.py`, `output.py`, `transform.py`, `main.py`)
- 1 new test file (~75 tests across 21 classes per spec §6.1)
- Net engine LOC estimated +450 to +600 (3 substantive new helpers in compute.py + 1 substantive new helper in output.py + transform.py emission + transform.py per-field annotation + main.py call site + types.py attrs)
- 18 new flat keys + 1 new top-level group + 1 new field on 2 (or 3) hierarchy entries

**Estimated focused session time:** 3–5 hours for a Claude Code CLI implementer with the spec + this brief in context. Distribution:
- Pre-Implementation Verification (§4): ~30 min
- types.py + compute.py constants: ~15 min
- compute.py helpers (3 substantive + 1 small): ~60 min
- output.py helper + call site: ~45 min
- transform.py emission + per-field annotation: ~45 min
- main.py call site: ~10 min
- Test authoring (~75 tests, 21 classes): ~90 min
- Local pytest + iteration: ~30 min
- Hand-Back drafting + Pre-Delivery Verification: ~30 min

Not binding on the implementer — the Operator and implementer adjust per actual pace.

---

## Closing — Sign-off

**Authoring Analyst (Project chat):** Phase 1 Spec authoring + Phase 2 Brief authoring at Session 165, 2026-05-26.

**Spec authority pointer:** `ITS001_Intraday_Tactical_Surface_Spec_v1_0.md` v1.0.1 — locked Session 165 (2026-05-24); cosmetic v1.0 → v1.0.1 refinement (no behavior change). When this brief and the spec disagree: **spec wins.**

**Phase 0 decisions consumed at Phase 1 (NOT re-litigated in Phase 2):**
- All 14 DQ locks from Phase 0 WIP `TBS_Phase_0_WIP_Intraday_Tactical_Surface_v0_3.md` (S1–S4, 2026-05-23 → 2026-05-24)
- DQ-1a (Feature C location hybrid), DQ-1b (Feature D location top-level group)
- DQ-2 (emit on all Profile A verdicts; semantic neutrality; no swing-context note)
- DQ-3a/b/c/d (compression-shelf detection + `position` field 3-value vocabulary)
- DQ-4a/b/c/d (dual stop methodology + 3-mode near-term target + Option α payload structure)
- DQ-5a/b/c/d (event detection: GAP_UP/GAP_DOWN/VOL_EXPANSION/MULTIPLE + thresholds + per-field-aware global detection + top-level `lookback_status`)
- DQ-6 (parallel surfaces in v1.0; no CFL-001 feed)
- DQ-7 (Profile A only; sibling to WKC-001 macro_frame Profile-A-scope precedent)
- Vocabulary collision audit (spec §3 — 13 new labels, no collisions)
- §11.6 spec-side audit (spec §11 — 8 items VERIFIED + 1 DEFERRED to Phase 2 entry)

**Working-tree branch name (suggested):** `feat/ITS-001-intraday-tactical-surface` (Operator and implementer may adjust).

**Lifecycle next (after Phase 2 Hand-Back delivered):**
1. Phase 3 — Operator-led live IBKR validation cohort (≥5 Profile A tickers across ABOVE/BELOW/WITHIN shelf positions + ≥1 `lookback_stale=true` + ≥1 `lookback_stale=false` witness, per spec §7 #4–#7).
2. Phase 4 — Project-chat-Analyst 6-doc DIA cascade (Doc 2 §VI / §IV substantive, Doc 7 Step 6 substantive, Doc 8 §II Layer 2 substantive mirror, EEM verify-only, README + PEO Tier closure cascade) + Bug Register lifecycle advance to ✅ CLOSED + 3 new CONCEPT entries logged per spec §9 (`INTRADAY-CAL-1`, `INTRADAY-CAL-2`, `INTRADAY-CFL-INTEGRATION-1`).
3. Repo promotion at item closure: this brief migrates to `docs/briefs/ITS001_Claude_Code_CLI_Implementation_Brief_v1_0.md`; spec to `docs/specs/`; hand-back to `docs/handbacks/`.

---

## Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-26 (S165 Phase 2 Brief turn) | Phase 2 entry artifact authored from spec v1.0.1 per ACP §6.4 canonical 11-section template + GOV-003 (S162) Brief-Authoring codification + SIR §11.6 two-layer-defense bridge. Sibling-spec anchors: RLY-001 primary + RLC-001 secondary (post-§11.6 lessons absorbed) + VTRIG-001 + CFL-001 + BRK-001 + TEST-HRN-001 + PE-43. |

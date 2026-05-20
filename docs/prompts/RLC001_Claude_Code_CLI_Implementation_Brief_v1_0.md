# RLC-001 v1.0 — Claude Code CLI Implementation Brief

**Spec authority:** `RLC001_Reclaim_Quality_Score_Spec_v1_0.md`
**Venue:** Claude Code CLI plugin (IntelliJ), operating on local `TBS_Master_App` working tree
**Implementer:** Claude Code
**Authoring session:** S160 (Project chat)
**Track:** Track 2 inline cadence (SIR §11.2 — file scope is `output.py` + `transform.py` only)

---

## 1. Mission

Implement RLC-001 v1.0 (Reclaim Quality Score / Tennis Ball Action) **exactly to spec**. The spec is the authoritative contract — this brief tells Claude Code how to operate during implementation; it does **not** restate spec content. Any conflict between this brief and the spec resolves in favor of the spec.

The spec file is in the project knowledge / working tree: `RLC001_Reclaim_Quality_Score_Spec_v1_0.md`. **Read it first, in full, before any code action.**

---

## 2. Operational Context (CLI Venue)

This is **not** a standalone Claude.ai chat session. The legacy "upload these files" pattern does not apply. Claude Code in IntelliJ has:

- **Direct working-tree access** — read/edit any file in `layers/tbs_engine/`, `tests/`, etc. via the file tools.
- **Local execution** — `pytest` runs against the local repo; no test results need to be paraphrased back.
- **Git context** — current branch, diff, log are inspectable natively.
- **No conversational upload step** — every artifact this brief references is already in the working tree (or will be after Claude Code's edits).

Consequences for this brief:
- File paths in this document are **working-tree paths**, e.g., `layers/tbs_engine/output.py`.
- Hand-back is an **in-session summary + commit** (or staged diff if Operator prefers pre-commit review), not a chat-paste.
- SHAs are obtainable via `git log -1 --format=%H -- <path>` after the edit cycle.

---

## 3. Phase Boundaries + Vocabulary Constraints

### 3.1 Phase 2 Scope (this implementation cycle — Claude Code's responsibility)

In scope this phase:
- Engine source edits per Spec §4 (`output.py` constants + helper + call site; `transform.py` flat-key registration + action_summary attachment)
- New unit test file `tests/unit/test_rlc001_reclaim_quality.py` per Spec §5 catalog
- Local `pytest` execution: full suite pass, zero regressions on existing tests
- Pre-implementation verification per Spec §11 (**mandatory before any code edit**)
- Pre-delivery verification per Spec §12 (**mandatory before hand-back**)

Out of scope this phase (do not perform):
- Live validation across real-market RECLAIM captures → that's **Phase 3** (Operator-led, separate cycle)
- DIA cascade across Docs 2/7/8/EEM/README/PEO → that's **Phase 4** (Project chat, tranched per SIR §11.4)
- Bug Register status advance to CLOSED → Analyst (Project chat) advances after Phase 3 + Phase 4 complete
- Any extension to REC-001 RECOVERY-path bars → out of scope per Spec DQ-5; RLC-REC-EXT-1 is a separate future CONCEPT

### 3.2 Vocabulary Constraints

**Phase 2 vocabulary** (use these words only):

- `STRONG_RECLAIM` / `MODERATE_RECLAIM` / `WEAK_RECLAIM` — the **only** label literals permitted for the `condition.label` field. No aliases, no abbreviations, no case variants.
- `Reclaim_Quality_Pct` — the **only** flat key permitted. No aliases (no `RLC_Pct`, no `Reclaim_Quality_Ratio`, no `Reclaim_Quality_Value`).
- `reclaim_quality` (lower_snake_case) — the **only** action_summary sub-object key permitted.
- `_assemble_reclaim_quality` — the **only** helper function name permitted.
- `_RLC_THRESHOLDS`, `_RLC_NULL_FLAT_KEYS`, `RLC_STRONG_THRESHOLD`, `RLC_MODERATE_THRESHOLD` — the **only** constant names permitted.

**Vocabulary that belongs to other phases (do not use in Phase 2):**

- "INVALID", "REJECT", "FAIL" — gate-decision verbs. Phase 1 (spec) explicitly locked DQ-1 to Option A (informational). RLC-001 never invalidates, rejects, or fails anything. If Claude Code finds itself reaching for these words in a comment or test name, that is a drift signal — stop and re-read Spec §2.3.
- "Phase 3", "live", "Operator validation" — these belong to the downstream cycle. Phase 2 tests are synthetic / fixture-based only.
- "v1.1", "RECOVERY", "REC-001 extension" — these belong to the future amendment cycle (RLC-REC-EXT-1 CONCEPT). Do not add anticipatory hooks.

---

## 4. Pre-Implementation Verification (MANDATORY — before any code edit)

The 5-instance spec-design failure pattern (ANALYST-002, ANALYST-003, ANALYST-CFL-001-SPEC-1, ANALYST-RLY-001-SPEC-1/2/3) all originated in implementation that skipped source-pattern verification and trusted spec text without grounding. **This step is the prevention.**

Before editing any file, complete Spec §11.1 through §11.7 against the **current working-tree state** (post-S159 master, plus any intervening Operator commits). Report each check pass/fail in the in-session summary, with a one-line evidence anchor (file:line) per check.

Key verifications to perform (these reference but do not replace Spec §11):

1. **Open `layers/tbs_engine/output.py`. Locate `_assemble_rally_state` call site in `_assemble_output`.** Verify:
   - the exact line where `_rly_block` (or equivalent) is stored on `ctx` or in `metrics`
   - the exact line where flat keys are merged into `metrics`
   - the relative position of the call vs the gate-cascade completion and vs the `_transform_output` invocation
2. **Open `layers/tbs_engine/transform.py`. Locate `_transform_output` body.** Find:
   - the action_summary custom-assembly block (where `verdict`, `reason`, `entry_type`, `mandate`, `context` are written)
   - the VTRIG-001 `volume_confirmation` attachment (the conditional `if ... is not None:` idiom)
   - the SFR-001 `signal_freshness` attachment
   - the RLY-001 `rally_state` attachment (closest structural sibling)
3. **Grep collision audit:**
   - `git grep -n "Reclaim_Quality" layers/tbs_engine/` → must return zero hits before the edit
   - `git grep -n "STRONG_RECLAIM\|MODERATE_RECLAIM\|WEAK_RECLAIM" layers/tbs_engine/` → must return zero hits before the edit
   - `git grep -n '"reclaim_quality"' layers/tbs_engine/` → must return zero hits before the edit
4. **Confirm spec-vs-source bar-index convention:** verify `cfg.iq` is the current bar (Spec DQ-7). Look at the SFR-001 `_classify_signal_freshness` use of `cfg.iq - 1` for "prior bar" — confirms `cfg.iq` is current.

**If any verification fails or yields unexpected state, stop. Report findings in the IntelliJ session and wait for Operator decision.** Do not adapt the spec on the fly. Spec-vs-source mismatch is an Analyst (Project chat) responsibility to resolve, not Claude Code's.

---

## 5. Implementation Scope (Working-Tree Edits)

All edits land in two files only. No third file is touched. If a third file edit appears necessary, **stop and report** — Track 2 admissibility forfeits with any file outside `output.py` + `transform.py`.

### 5.1 `layers/tbs_engine/output.py`

Three edits:

1. **Module-level constants** — add the four constants in Spec §4.1 (`RLC_STRONG_THRESHOLD`, `RLC_MODERATE_THRESHOLD`, `_RLC_THRESHOLDS`, `_RLC_NULL_FLAT_KEYS`). Placement: alongside the existing RLY-001 / VTRIG-001 / THS constants near the top of the file.
2. **Helper function** — add `_assemble_reclaim_quality(ctx, gate_result)` per Spec §4.2 (full implementation in the spec — copy verbatim with no logic changes; comments may be tightened for repo conventions).
3. **Call site** — add the invocation inside `_assemble_output` per Spec §4.3, **mirroring the RLY-001 storage idiom** identified in Pre-Implementation Verification step 1.

### 5.2 `layers/tbs_engine/transform.py`

Two edits:

1. **Flat-key registration** — add `keys.add("Reclaim_Quality_Pct")` in `_all_mapped_flat_keys()` per Spec §4.4.
2. **action_summary attachment** — add the conditional sub-object attachment in `_transform_output` per Spec §4.5, **mirroring the VTRIG-001 / SFR-001 idiom** identified in Pre-Implementation Verification step 2.

### 5.3 Edits NOT to make

- Do **not** edit `__all__` in `output.py` unless the helper needs explicit export. RLY-001's `_assemble_rally_state` is exported via `__all__` — verify that pattern and mirror it. If RLY-001 uses `__all__`, add `_assemble_reclaim_quality`; if not, don't.
- Do **not** add docstring autogeneration, type hints library imports, or new top-level imports beyond what's already present (`pandas as pd` is already imported in `output.py`).
- Do **not** edit any other engine file (`gates.py`, `compute.py`, `helpers.py`, `types.py`, `charts.py`). If any of these appear in the diff, the implementation has drifted from Track 2.

---

## 6. Test Mandate

### 6.1 New Test File

Create `tests/unit/test_rlc001_reclaim_quality.py` with the 10 test classes enumerated in Spec §5, targeting 35–45 individual tests.

Follow the project's existing test-style conventions (visible in the existing `tests/unit/` directory — particularly `test_rly001_*` and `test_cfl001_*` if present, as they are the closest sibling test files structurally).

Key test discipline (re-stated from Spec §5 for emphasis):

- **Test 6 (verdict invariance)** is non-negotiable. The gate cascade output must be bit-identical pre/post. Without this, Track 2's "zero verdict impact" criterion (SIR §11.2) is violated.
- **Test 9 (positive-only design)** must assert `KeyError` (not None equality). The `reclaim_quality` key is **absent** on non-RECLAIM paths, not present-with-None.
- **Test 4 (null-defensive)** must cover all 6 paths in Spec §3.2 — do not omit the degenerate-range case (high == low).

### 6.2 Regression Cohort

After new tests pass, run the full pytest suite:

```bash
pytest tests/ -x --tb=short
# or equivalent project convention
```

Expected outcome:
- All new tests pass
- Zero pre-existing tests regress
- Test count delta = +35 to +45

If any pre-existing test fails, **stop and report**. Spec-correct implementation should produce zero regressions.

### 6.3 Test Hygiene Avoidance

Be aware of open hygiene item **TEST-HRN-001** (test harness module-caching pollution via `_load_mod()`). The new test file should follow the post-TEST-HRN-001 pattern, not the legacy pattern. Specifically:
- If the project has migrated to direct `from tbs_engine import ...` imports, use those.
- If the project still uses `_load_mod("output")` style, follow that — but flag in the hand-back if the new test file participates in the pattern that TEST-HRN-001 names.

---

## 7. Pre-Delivery Verification (MANDATORY — before hand-back)

Complete Spec §12 SIR §9 checklist. Specifically:

- [ ] **Content accuracy** — every file path, line number, and SHA in the hand-back summary corresponds to the actual post-edit working-tree state
- [ ] **Internal consistency** — helper implementation matches Spec §3 formula exactly; constants match Spec §3.3 cutoffs; banding `>=` semantics match Spec §3.3 inclusivity
- [ ] **Format integrity** — code passes the project's lint / format conventions (no trailing whitespace, no unused imports, follows existing style)
- [ ] **Scope discipline** — `git diff --stat` shows exactly `output.py`, `transform.py`, `tests/unit/test_rlc001_reclaim_quality.py` touched; no other files
- [ ] **Bug Register update** — NOT done by Claude Code. The Bug Register update (RLC-001 status advance SPECIFIED → IMPLEMENTED) is done by the Analyst in the Project chat after Claude Code hands back. Claude Code's responsibility is to provide the hand-back content that lets the Analyst log it.
- [ ] **DIA current** — NOT done by Claude Code. Per Track 2 inline cadence (SIR §11.4), DIA folds into a future Tranche reconciliation in the Project chat.
- [ ] **Zero regressions** — pytest suite passes 100%, no new warnings introduced

---

## 8. Hand-Back Contract

At the end of the implementation cycle, produce an in-session summary containing:

### 8.1 Required Hand-Back Fields

```
RLC-001 v1.0 Implementation Hand-Back — S###

Branch / commit:
  <branch name> @ <SHA>

Files touched (diff --stat):
  layers/tbs_engine/output.py            | +N -M
  layers/tbs_engine/transform.py         | +N -M
  tests/unit/test_rlc001_reclaim_quality.py | +N

File SHAs (post-edit):
  output.py:    <SHA>
  transform.py: <SHA>

Test outcome:
  New tests added: NN
  Pre-existing tests: <count> passed, 0 failed, 0 regressed
  pytest command used: <command>
  Total runtime: <seconds>

Pre-Implementation Verification (Spec §11):
  §11.1 Call-order: PASS (evidence: output.py:LINE)
  §11.2 Pipeline-order: PASS (evidence: output.py:LINE)
  §11.3 Sort-order: N/A (single-bar scalar)
  §11.4 Shared-reference: N/A (no hierarchy)
  §11.5a Flat-key collision audit: PASS (git grep zero hits)
  §11.5b Label vocabulary collision audit: PASS (git grep zero hits)
  §11.5c action_summary key collision: PASS (verified existing assembly)
  §11.5d RLY-001 pattern match: PASS (mirrored at output.py:LINE)
  §11.5e VTRIG/SFR pattern match: PASS (mirrored at transform.py:LINE)
  §11.6 PE-43 bar-index compliance: PASS (uses ctx.last)
  §11.7 Positive-only design audit: PASS (Test 9 asserts KeyError)

Pre-Delivery Verification (Spec §12):
  Content accuracy: PASS
  Internal consistency: PASS
  Format integrity: PASS
  Scope discipline: PASS (3 files only)
  Zero regressions: PASS

Worked-example sanity check (one of Spec §8 A/B/C executed live against helper):
  Input: <OHLC>
  Expected: <value, label>
  Actual:   <value, label>
  Match: YES

Deviations from spec:
  <none / list any spec-vs-implementation deltas>

Open hygiene observations (NOT new spec gaps, just notes):
  <e.g., observed TEST-HRN-001 pattern in test file: yes/no; observed any
   adjacent code smell worth surfacing to Analyst for follow-up>
```

### 8.2 Deviation Reporting Discipline

If during implementation Claude Code finds **any** of the following:

1. Spec instruction that contradicts current source state
2. Spec-mandated pattern (RLY-001 storage idiom, VTRIG/SFR attachment) that has been refactored since spec authoring
3. Edge case observed in source that the spec does not address
4. Implementation choice the spec leaves ambiguous

**Stop. Do not adapt the spec unilaterally.** Report the issue in the in-session summary, document the ambiguity precisely, and wait for Operator decision. The Analyst (Project chat, S160 or later) is the spec-amendment authority, not Claude Code.

This is the canonical defense against the 5-instance pattern. The pattern was specs being interpreted-around at implementation time without surfacing the gap. The countermeasure is surface-and-pause.

---

## 9. Failure-Mode Protocol

If any of the following occurs, **halt the implementation cycle and surface to Operator in the IntelliJ session**:

- Pre-Implementation Verification step fails (e.g., RLY-001 storage idiom isn't found in current source — implies refactor since spec authoring)
- A test in Test 6 (verdict invariance) fails — implies the implementation has gate-cascade impact, violating DQ-1 lock
- A test in Test 9 (positive-only) fails — implies the attachment idiom emits the sub-object on non-RECLAIM paths
- `git diff --stat` shows a file outside `output.py`/`transform.py`/`tests/unit/test_rlc001_reclaim_quality.py` touched — Track 2 admissibility forfeits
- Pre-existing test regression after the edit
- Discovery of a spec ambiguity that DQ resolution doesn't cover

In all halt cases: do **not** commit. Leave the working tree in the halted state and provide a precise description of the issue. The Operator + Analyst will decide whether to amend the spec, adjust the implementation approach, or abort the cycle.

---

## 10. Sibling-Spec Pattern References (Read-Only Anchors)

If the working tree contains them, the closest sibling-spec implementations to pattern-match against are:

- **RLY-001 (S159):** `_assemble_rally_state` in `output.py` — closest structural sibling (output.py helper + transform.py flat-key registration, returns `(block, flat_keys_dict)`). Use as the primary reference.
- **VTRIG-001:** `_compute_volume_confirmation` in `output.py` → `action_summary.volume_confirmation` attachment in `transform.py`. Use as the primary action_summary attachment reference.
- **SFR-001:** `_classify_signal_freshness` in `output.py` → `action_summary.signal_freshness` attachment in `transform.py`. Use as the secondary attachment reference (simpler shape — single string).
- **CFL-001 (S157):** positive-only annotation pattern — use as reference for the "absence as signal" assertion style in Test 9.
- **FPC-001 / SBC-001 / HFI-001-A:** condition + thresholds + value sub-object pattern. Use as a reference for return-shape conventions on the helper.

If any of these references are missing or have been refactored, surface in Pre-Implementation Verification rather than adapting.

---

## 11. Estimated Effort

(For Operator awareness only — not a binding constraint.)

- Pre-Implementation Verification: ~10 min
- `output.py` edits: ~20 min
- `transform.py` edits: ~10 min
- Test file authoring: ~45–60 min (10 classes, 35–45 tests)
- Local pytest run + iteration: ~15 min
- Pre-Delivery Verification + hand-back authoring: ~15 min

**Total estimated cycle: ~2 hours**, contingent on zero pattern-match surprises and clean test-first iteration.

---

**End of Brief.** Spec authority remains `RLC001_Reclaim_Quality_Score_Spec_v1_0.md`. This brief is procedural scaffolding only; if any procedural instruction in this brief conflicts with a spec instruction, the spec wins.

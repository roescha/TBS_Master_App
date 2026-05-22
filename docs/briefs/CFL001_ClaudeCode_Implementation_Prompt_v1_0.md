# Claude Code Implementation Prompt — CFL-001

**Spec:** `CFL001_Level_Confluence_Detection_Spec_v1_0.md` (uploaded with this prompt — read it end-to-end before writing any code)
**Branch to create:** `feat/CFL-001-confluence-detection` (from current `master`)
**Track:** Track 2 — Informational Enhancement (per SIR §11.2)
**Hard prerequisite satisfied:** CNV-001 ✅ CLOSED S154

---

## Task

1. **Read the spec end-to-end before writing any code.** Sections §3, §4, §5, §6, §7 are all binding.
2. Check out `master`, pull latest, create the branch `feat/CFL-001-confluence-detection`.
3. Implement per **spec §3** (helper + constants + desc map) and **spec §4** (three call sites) on `layers/tbs_engine/transform.py`.
4. Implement the test file `tests/unit/test_cfl001_confluence.py` per **spec §6.1** — all 7 test classes, all listed tests, using the safe `spec_from_file_location` dynamic-module-load pattern (NOT `sys.modules[name] = mod` — see `TEST-HRN-001` in the spec §6.1 preamble).
5. Run `pytest tests/unit/test_cfl001_confluence.py -v` first to verify the new tests pass.
6. Then run the full regression `pytest tests/` and confirm the baseline does not regress.
   - **Pre-CFL pytest baseline:** 2940 passed / 4 skipped / 0 failed
   - **Expected post-CFL:** ~2975 passed / 4 skipped / 0 failed (35 new tests)
   - **Zero regressions** in any pre-CFL test class.
7. Commit on the feature branch with a clear message. **Do NOT push to `master`.** **Do NOT merge.** Operator reviews the diff before merge.

---

## Mandatory pre-implementation verification (before writing code)

These are not optional. They prevent the ANALYST-002 / ANALYST-003 incident class.

- **Re-read spec §4** and locate each call site by context cue (the `[CNV-001]` comment block above each `_annotate_conviction` invocation). The line numbers in the spec are approximate at spec-authoring date — drift of ±50 lines is expected. Locate by context, not by line number.
- **Call-order audit** — confirm `_detect_level_confluence` is invoked immediately **after** `_annotate_conviction` at each of the three call sites. CFL-001 reads `entry["price"]` and `entry["label"]` — both must be populated by the time CFL fires. They are at all three sites (entries are constructed with both fields before any annotation pass), but verify by mechanical inspection.
- **Sort-order check** — confirm CFL-001 invocation happens AFTER the existing `.sort(key=lambda x: x["price"])` (or `reverse=True` variant) call that precedes the annotation block. The spec specifies "post-sort" insertion. If the call site is pre-sort, STOP and ask.
- **Module-import-graph check** — confirm `transform.py` imports remain at the right-most position in the package graph: `types → helpers → {gates, data, compute, exit} → {trigger, output} → main`. No new imports are needed for CFL-001. If you find yourself adding an import statement, STOP and ask.
- **Negative-assertion test scope** — `TestCFL001NotInGatesFile` must use `inspect.getsource()` on each `_gate_*` function in `layers/tbs_engine/gates.py` and assert the substring `"confluence"` is absent. Pattern mirrors `TestWKC001NotInGatesFile` from S156 — search the existing test suite for that class as a template.

---

## What to STOP and ask about

- If you cannot locate one of the three call sites by context cues → STOP. Don't guess. Surface the ambiguity in the hand-back.
- If the spec's algorithm has any ambiguity at a boundary you encounter while writing it (e.g., equality at the threshold — "within threshold" reads as inclusive `≤` per the helper code in §3.2, but verify if the test boundary cases surface tension) → STOP and ask.
- If pytest fails on a test that should pass per the spec, and you can't quickly identify whether the bug is in the test or the implementation → STOP and surface in the hand-back. Don't silently adjust the test to make it pass.
- If you find yourself touching ANY file outside the spec §2.3 edit list (i.e., anything that isn't `layers/tbs_engine/transform.py` or `tests/unit/test_cfl001_confluence.py`) → STOP. This is a SIR §11.2 escape-hatch trigger. Track 2 forbids scope creep. Report to the Operator and wait for direction.

---

## End-of-session deliverables

Write **`CFL001_Implementation_HandBack_v1_0.md`** at the repository root (or wherever the Operator directs). The hand-back covers:

1. **Files touched** with exact final line numbers for the inserted code (helper, constants, desc map, three call sites)
2. **LOC delta** per file
3. **pytest output**:
   - Baseline pre-CFL: `pytest tests/ -q` summary
   - New test file alone: `pytest tests/unit/test_cfl001_confluence.py -v` full output
   - Full regression post-CFL: `pytest tests/ -q` summary — confirm no regressions
4. **SIR §9 Pre-Delivery Verification Checklist** filled out, all 8 boxes:
   - Content accuracy ✓/✗
   - Internal consistency ✓/✗
   - Format integrity ✓/✗
   - Scope discipline ✓/✗
   - Gate function verification ✓/✗ (verified by `TestCFL001NotInGatesFile`)
   - Module import verification ✓/✗
   - Bug Register updated — N/A in standalone session, will be done in Project chat at Phase 4
   - DIA current — N/A in standalone session, see spec §8
5. **Deviations from spec** — any deviation, however minor, with rationale
6. **Bugs found during implementation** (if any) — note them for the Bug Register; do NOT log them yourself (Project Analyst logs them in canonical Bug Register at Phase 4)
7. **Open questions for the Project Analyst** — anything that needs design-level input at Phase 4
8. **Branch state** — confirm branch name, commit SHA(s), confirm not pushed to master

---

## Spec re-read instruction (binding)

- Before writing the helper in §3.2 — re-read spec §3 in full.
- Before writing the call-site edits in §4 — re-read spec §4 in full.
- Before writing the tests in §6 — re-read spec §6.1 in full.
- Before declaring the session complete — re-read spec §7 (Behavioural Invariants) and confirm each row holds.

Write from the spec, not from your memory of the spec.

---

## Process trial context

This is the **first Track 2 / Claude Code process trial** for TBS. The Operator is testing whether the lean spec → Claude Code → branch → tests → Operator-confirms workflow can replace the heavier 7-hop manual standalone-chat process. Treat this session with the same discipline as a Track 1 standalone implementation chat — verification, re-reads, scope-stop-on-ambiguity. If the discipline holds, future Track 2 bundles use this same pattern. If it doesn't, the trial fails informatively and the Operator returns to the standalone-chat workflow.

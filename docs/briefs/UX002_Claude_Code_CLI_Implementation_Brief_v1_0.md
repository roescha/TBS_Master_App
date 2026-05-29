# UX-002 — Claude Code CLI Implementation Brief

**Brief Version:** v1.0
**Phase:** 2 entry artifact (Claude Code CLI venue)
**Spec authority:** `UX002_Protective_Anchor_Output_Restructuring_Spec_v1_0.md` v1.0 (LOCKED)
**Template:** ACP §6.4 (canonical 11-section)
**Author:** TBS Analyst (Project chat, Phase 1 close)

---

## §1 Mission

Implement UX-002 exactly as specified in the locked spec. **The spec is the single source of truth; this Brief is procedural scaffolding only. On any conflict, the spec wins** — surface the conflict (do not adapt unilaterally).

## §2 Operational Context (CLI Venue)

You are the Claude Code CLI implementer with direct working-tree access to `roescha/TBS_Master_App`. No uploads are needed — read engine source from the working tree. You can run local `pytest`, hold git context, and deliver the Hand-Back in-session. Work on a feature branch off current `master`.

## §3 Phase Boundaries + Vocabulary Constraints

**In scope (Phase 2):** the three changes in spec §4 — Change 1 (relocate `daily_atr` into `higher_frame`), Change 2 (**verify-only** — confirm `DAILY_HARD_STOP` desc unchanged), Change 3 (remove `protective_anchor` group + re-home `_flatten` reverse map). Plus the test file in spec §6.

**Out of scope / drift signals** — if you reach for any of these, stop and re-read spec §2/§3:
- Any edit to a flat-key **writer** (`output.py:2590/2598/2603`), the membership set (`transform.py:1127`), or the internal consumers (`transform.py:3297`, `output.py:2873`) — spec §4.4 retains all of these.
- Any **Profile B/C** code path — Profile A only.
- Any gate / verdict / threshold / sizing vocabulary — this is output-shape only.
- "remove flat key" — the flat keys are **retained**; only the output *group* and its reverse-map entries are removed.
- Numeric-value interpolation into the `DAILY_HARD_STOP` desc — declined per spec §4.2 / DQ-2.

## §4 Pre-Implementation Verification (MANDATORY before any edit)

Execute spec §11 (the §11.6 Pre-Implementation Checklist) against the **current working-tree source**, with `file:line` evidence for each, before editing. The spec audited `master` at Phase 1; confirm the anchors still hold (line drift is expected — match by symbol, not line). In particular re-confirm:

- **ITEM 7 (storage feasibility):** `_flatten(grouped)` receives the full output and `grouped["trade_setup"]` + `floor_analysis.higher_frame` are both reachable for the reverse-map re-homing (spec §4.3 table). If the stop-hierarchy reverse-map cannot reach the `DAILY_HARD_STOP` entry as the spec assumes — **halt and surface** (§9).
- **ITEM 8 (downstream consumers):** confirm `Daily_Protective_Anchor` is still read at the floor-entry site and the extension site before removing the group; the group removal must not touch them.
- **DQ-4 equivalence:** confirm `higher_frame.ema.ema_21` carries the Daily-EMA-21 value the retired `protective_anchor.price` carried (spec §9 DQ-4).

## §5 Implementation Scope (Working-Tree Edits)

- **`tbs_engine/transform.py`** — Changes 1, 3a, 3b per spec §4.1 / §4.3 / §5.
- **`tbs_engine/output.py`** — **verify-only** (Change 2, spec §4.2). No edit.
- **`layers/tests/unit/test_ux002_protective_anchor_restructure.py`** — new (spec §6).

**No third engine file.** Any edit outside `transform.py` + the test file is forbidden — if the implementation appears to need one, that forfeits scope: **halt and return** per SIR §11.2 escape hatch.

## §6 Test Mandate

Author the test file per spec §6 (six classes). Use the post-TEST-HRN-001 idempotent module-loading pattern (guard `sys.modules` — load via `spec_from_file_location` or `if name not in sys.modules`). Run the full unit cohort; report new-test count + regression baseline + any failures. Zero UX-002-attributable regressions required.

## §7 Pre-Delivery Verification (MANDATORY before Hand-Back)

Run the SIR §9 checklist and the spec §12 checklist. Confirm: `TestUX002NotInGatesFile` passes; module import graph acyclic (no new imports); Profile B/C byte-identical; verdict invariance holds.

## §8 Hand-Back Contract

Deliver an in-session Hand-Back conforming to **ACP §6.5** (canonical 10-section). Do not restate it here.

## §9 Failure-Mode Protocol

Halt-and-surface in-session (do not commit, do not adapt the spec unilaterally) on any of: a §4 Pre-Implementation Verification failure; a `TestUX002VerdictInvariance` or `TestUX002ProfileBCInvariance` failure; a reverse-map re-homing that cannot reach a source the spec §4.3 assumes (ITEM 7); a required third-file edit (§5); or any spec ambiguity. Surface with `file:line` evidence and the spec section in tension.

## §10 Sibling-Spec Pattern References (read-only anchors)

- **EMA50-001** — `_flatten()` reverse-map symmetry pattern (the OD-2 precedent this spec's §4.3 re-homing follows) and the `higher_frame.ema_50` grouped sub-object shape.
- **FA-001** — `higher_frame` sub-object structure (insertion-point reference for Change 1).
- **VTRIG-001 / TEST-HRN-001** — idempotent test-harness module-loading pattern.
- **BUGR-002 / CNV-001** — the stop-hierarchy partition + conviction annotation the `DAILY_HARD_STOP` entry passes through (relevant only to the Change 2 verify-only confirmation that the entry is unaffected).

## §11 Estimated Effort

0.5–1 session (per PEO §2F). One engine file + one verify-only file + one new test file.

---

### Sign-off

- **Authoring Analyst:** TBS Analyst (Project chat, Phase 1 close).
- **Spec authority:** `UX002_Protective_Anchor_Output_Restructuring_Spec_v1_0.md` v1.0 (locked).
- **Operator decisions consumed at Phase 1:** DQ-1 / DQ-2 / DQ-3 confirmed as recommended; DQ-4 resolved from source.
- **Expected working-tree branch:** `ux002-protective-anchor-restructure` (off current `master`).

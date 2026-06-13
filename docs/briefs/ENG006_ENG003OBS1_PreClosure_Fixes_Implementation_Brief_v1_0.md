# Claude Code CLI Implementation Brief — ENG-006-OBS-1 + EZR-001 Pre-Closure Fixes

**Spec authority:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0 **+ Addendum 1** (`ENG006_ENG003OBS1_Bundle_Spec_Addendum_1_PreClosure_Fixes.md`). This Brief references the Addendum by section; it does **not** restate contracts. **If this Brief and the Addendum disagree, the Addendum/spec wins.**
**Phase:** 2 (Claude Code CLI implementation). **Venue:** IntelliJ Claude Code CLI.
**Branch:** `eng006-eng003obs1-fib-extensions` (same branch as the S175 ENG-006 implementation — **do NOT create a new branch**).
**Authoring Analyst:** TBS Analyst (Project chat), Phase 1 close S176.

---

## §1. Mission

Land the two Operator-locked, NON-GATE pre-closure fixes for the ENG-006 bundle — ENG-006-OBS-1 (extension-row conviction tier) and EZR-001 (Profile A PULLBACK display alignment) — exactly as specified in Addendum 1 §A3, with the §A4 tests, so the bundle can advance to Phase 3 re-validation and closure. The Addendum is the authority; this Brief is procedural scaffolding.

## §2. Operational Context (CLI Venue)

You have direct working-tree access to `roescha/TBS_Master_App` on branch `eng006-eng003obs1-fib-extensions` — no uploads needed. You can run local `pytest`. You deliver the Hand-Back in-session at Phase 2 close (ACP §6.5 — not as chat paste / upload). You have git context: the ENG-006 implementation already lives on this branch (transform.py blob `998eb1d1…`); these fixes extend it.

## §3. Phase Boundaries + Vocabulary Constraints

**In scope (Phase 2):** edit `transform.py`; append tests to the existing ENG-006 bundle test file. Nothing else.

**Out of scope / drift signals — if you reach for these, stop and re-read Addendum 1 §A2.2 / §A8:**
- **`output.py`** — the EZR-001 fix is **transform-display-only**. Editing `output.py:2220` (`Entry_Reference`) is the rejected approach (Addendum §A2.2 open item 2 / §A8): it leaks into `entry_strategy.entry_price` (output.py:2525) and disables the inversion guard. Do **not** touch `output.py`.
- **`Entry_Reference` / `_entry_ref` reassignment** — the fix adds display locals; it must **not** reassign `_entry_ref` (that is what preserves `_ez_inverted`).
- **`_ez_inverted` (transform.py:2746)** — leave unchanged. Editing the guard is out of scope.
- **`gates.py` / `compute.py` / `trigger.py` / `main.py` / any third module** — out of scope. These are NON-GATE fixes; a gate-file touch forfeits the classification (SIR §11.2) — halt and surface.
- Words signalling wrong phase/scope: "new verdict", "REJECT/INVALID/FAIL" as a *produced* value (these are display/informational fixes — no verdict changes); "Phase 3" / "live cohort" (that is the Operator's next step, not yours).

## §4. Pre-Implementation Verification (MANDATORY before any edit)

Re-confirm the Addendum §A2 audit against the working tree before editing. For each, capture a `file:line` evidence anchor:

1. **`_CONVICTION_TIER_MAP`** (transform.py ~165–192) currently lacks `FIB_EXTENSION_1272/1618/2618`; PROJECTION tier holds only `MEASURED_MOVE`. Confirm `_annotate_conviction` (~236) uses `.get(label, (None, None))` and is called on `_target_entries` (~3198) after the extension append (~3158–3171).
2. **`_CONVICTION_TIER_MAP` is the only conviction map** (Addendum §A2.1). Confirm no sibling map needs the labels.
3. **Entry-zone builder** (transform.py ~2664–2756): confirm `_entry_ref = flat_metrics.get("Entry_Reference")` (2664) feeds `reference.price` (2749), `entry_price_range.lower` (2751), and `_ez_inverted` (2746); confirm `_is_pullback` / `_render_as_pullback_fallback` (2671 / 2685) and `_db` "SWING" detection (2703/2727).
4. **Key availability**: `flat_metrics.get("Daily_Protective_Anchor")` and `flat_metrics.get("Pullback_Zone_Lower")` are populated at the builder site (passthrough L1129 / L1163; read precedent L3343).
5. **Second `Entry_Reference` consumer**: confirm `output.py:2525` reads `Entry_Reference` — this is *why* the fix stays in transform (do not change the flat key).

If any anchor does not match, **halt and surface** (§9) — do not adapt the spec.

## §5. Implementation Scope (Working-Tree Edits)

**`layers/tbs_engine/transform.py` — two edits, per Addendum §A3:**

1. **§A3.1 — `_CONVICTION_TIER_MAP`:** add `FIB_EXTENSION_1272/1618/2618`, each `("PROJECTION", 4)`, in the PROJECTION block after `MEASURED_MOVE`. Map 20 → 23. No edit to `_annotate_conviction`, the append block, or call sites.
2. **§A3.2 — entry-zone display alignment:** add display locals before the `_entry_zone` dict so that, for Profile A (SWING):
   - `reference.price` → `Daily_Protective_Anchor` when `(_is_pullback or _render_as_pullback_fallback)` **and** `Daily_Protective_Anchor > 0`; else the existing `_entry_ref`.
   - `entry_price_range.lower` → `Pullback_Zone_Lower` when `_is_pullback` **and** `Pullback_Zone_Lower` is truthy; else `_entry_ref`.
   - Render `reference` only when the chosen price is truthy.
   - **Do not** reassign `_entry_ref`; **do not** change `_ez_inverted`, the `[INVERTED]` desc, the `entry_price_range` render gate (`_pb_upper and _is_pullback and not _ez_inverted`), or any non-Profile-A / non-PULLBACK path. RECLAIM, breakout, Profile B, Profile C must be byte-identical in output.

**Test file:** append the §A4 tests to the existing ENG-006 bundle test file under `layers/tests/unit/`.

**Forbidden:** `output.py`, `gates.py`, `compute.py`, `trigger.py`, `main.py`, `data.py`, `types.py`, `exit.py`, `charts.py`, `helpers.py`. A diff touching any of these = halt.

## §6. Test Mandate

Append the six §A4 test groups to the existing ENG-006 bundle test file (keep the file's existing class/naming idiom; TEST-HRN-001 idempotent pattern). Fixtures are crafted `flat_metrics` dicts driving the transform layer — no IBKR/runtime dependency. Run locally:

```
pytest layers/tests/unit/<eng006_bundle_test_file>.py -q
```

then the full unit suite for zero-regression:

```
pytest layers/tests/unit -q
```

Report the new-test count, the regression baseline (the S175 ENG-006 cohort was 3304/4/0 → +33 over 3271; your run adds the §A4 tests on top), and an explicit zero-regression assertion or itemized list.

## §7. Pre-Delivery Verification (MANDATORY before Hand-Back)

Run SIR §9 explicitly:
- [ ] Content accuracy — edits match Addendum §A3 (re-read, don't recall).
- [ ] Internal consistency — no `output.py`/guard/`_entry_ref` reassignment; RECLAIM/B/C/breakout paths unchanged.
- [ ] Format integrity — Python edits clean; test file parses.
- [ ] Scope discipline — `git diff --stat` shows **only** `transform.py` + the one test file.
- [ ] Gate-function verification — no change to gate function names/order (none touched).
- [ ] Module-import verification — no new imports; acyclic graph intact.
- [ ] Verdict invariance + NotInGatesFile — green.

## §8. Hand-Back Contract

At Phase 2 close, deliver a Hand-Back conforming to **ACP §6.5** (canonical 10-section). Map §A4 tests to §5 test outcome; map the Addendum §A7 closure criteria to §10; note in §9 that Phase 3 re-validation needs (a) one extension-bearing output for C1 and (b) one Profile A PULLBACK output for C2.

## §9. Failure-Mode Protocol

Halt-and-surface in-session; do not commit on halt; do not unilaterally adapt the spec. Specific halt triggers:
- A Pre-Implementation Verification anchor (§4) does not match the working tree.
- The diff would touch a forbidden file (§5) — including any temptation to "just fix it" in `output.py`.
- A `VerdictInvariance` or `NotInGatesFile` test fails.
- A regression-guard test (Profile A RECLAIM, Profile B/C, inversion) fails — indicates the re-source leaked outside Profile A PULLBACK.
- Spec ambiguity discovered in Addendum §A3.

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

- **CNV-001** `_CONVICTION_TIER_MAP` existing entries + **DSP-004-OBS-2** precedent (`WEEKLY_EMA_21` added at S169, transform.py:177) — the map-extension idiom.
- **ENG-006 v1.0 §4.3** — the `FIB_EXTENSION_*` row shape (read-only; not edited here).
- **ENG-003-OBS-1** (output.py confluence re-point) — the same residual-wrong-anchor class EZR-001 belongs to (conceptual anchor; do not edit).
- Entry-zone builder existing `_db` "SWING" switches (transform.py:2703 / 2727) — the Profile-A detection idiom to reuse.

## §11. Estimated Effort

Small. ENG-006-OBS-1 is three dict lines + one test. EZR-001 is a handful of display-local lines in one function + ~5 tests. Single CLI session. (Operator awareness only — not binding.)

---

## Sign-off

- **Authoring Analyst:** TBS Analyst (Project chat), Phase 1 close S176.
- **Spec authority:** ENG-006 spec v1.0 + Addendum 1 (single source of truth; this Brief references, does not restate).
- **Operator decision points consumed at Phase 1:** ENG-006-OBS-1 tier `("PROJECTION", 4)` (S175-cont-4); EZR-001 fix direction — displayed Profile A PULLBACK reference → Daily EMA 21, range lower → `Pullback_Zone_Lower`, protocol-scoped (S175-cont-4); §11.6 audit resolution: transform-only fix, `output.py` excluded (S176, Addendum §A8).
- **Expected working-tree branch:** `eng006-eng003obs1-fib-extensions`.

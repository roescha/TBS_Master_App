# Claude Code CLI Implementation Brief — EZR-001-OBS-1 Profile A PULLBACK Desc Alignment

**Spec authority:** `ENG006_ENG003OBS1_Bundle_Spec_Addendum_1_PreClosure_Fixes.md` **v1.2** — specifically **§A3.3** (contract), **§A2.3** (source audit), **§A4 case 7** (tests). This Brief references the Addendum by section; it does **not** restate contracts. **If this Brief and the Addendum disagree, the Addendum/spec wins.**
**Phase:** 2 (Claude Code CLI implementation — pre-closure fold-in re-run). **Venue:** IntelliJ Claude Code CLI.
**Branch:** `eng006-eng003obs1-fib-extensions` (same branch as the S175 ENG-006 implementation and the S176-cont §A3.1/§A3.2 fixes — **do NOT create a new branch**).
**Authoring Analyst:** TBS Analyst (Project chat), Phase 1 close S176-cont-3.
**Relationship to prior Brief:** this is a **separate, focused re-run** for the third pre-closure fold-in. The prior `ENG006_ENG003OBS1_PreClosure_Fixes_Implementation_Brief_v1_0.md` (ENG-006-OBS-1 + EZR-001) is **closed** — its edits are already landed on this branch (transform.py blob `53ce5351…`). That Brief is a read-only context anchor (§10), not amended here.

---

## §1. Mission

Land the one Operator-locked, NON-GATE desc-alignment fix — **EZR-001-OBS-1** — exactly as specified in Addendum 1 v1.2 §A3.3, with the §A4 case 7 tests, so the ENG-006 bundle can complete Phase 3 re-validation and advance to closure. EZR-001-OBS-1 is the **desc-side counterpart** to the already-landed §A3.2 price re-source: when `reference.price` is the Daily EMA 21 anchor, `reference.desc` must read "Daily EMA 21" instead of the residual hourly structural-floor label. The Addendum is the authority; this Brief is procedural scaffolding.

## §2. Operational Context (CLI Venue)

You have direct working-tree access to `roescha/TBS_Master_App` on branch `eng006-eng003obs1-fib-extensions` — no uploads needed. You can run local `pytest`. You deliver the Hand-Back in-session at Phase 2 close (ACP §6.5 — not as chat paste / upload). Git context: the §A3.1 conviction-map and §A3.2 price re-source already live on this branch (transform.py blob `53ce5351ec7a6a3fbe25a7923d8e8ee37a5bd374`; output.py `19a66af3…`, trigger.py `2493e7e5…` unchanged). This fix extends transform.py only.

## §3. Phase Boundaries + Vocabulary Constraints

**In scope (Phase 2):** **one** edit to `layers/tbs_engine/transform.py` (the desc override); append the §A4 case 7 tests to the existing ENG-006 bundle test file. Nothing else.

**Out of scope / drift signals — if you reach for these, stop and re-read Addendum §A2.3 / §A3.3 / §A8:**
- **`output.py`** — not touched (Addendum §A2.2 / §A8; the EZR-001 fix is transform-display-only and that holds here). Do **not** edit it.
- **`trigger.py`** — read-only. `trigger.py:96` (`Entry_Zone_Reference = "Daily EMA 21"`) is a reference anchor only. **Do NOT refactor it to a shared constant** — the within-fence resolution (Addendum §A2.3 open item 1) is deliberately `flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"`, with the literal as a fallback; introducing a shared constant would touch `trigger.py` and breach the fence.
- **The §A3.2 price re-source block** (transform.py ~2766–2782) — **already landed; do NOT re-touch it** except to add the one-line boolean capture (`_ref_price_is_daily_anchor`) inside the existing branch (see §5).
- **`_entry_ref` reassignment** — forbidden (that is what preserves `_ez_inverted`).
- **`_ez_inverted` (transform.py:2756)** — leave unchanged.
- **`gates.py` / `compute.py` / `main.py` / `data.py` / `types.py` / `exit.py` / `charts.py` / `helpers.py`** — out of scope. This is a NON-GATE display fix; a gate-file touch forfeits the classification (SIR §11.2) — halt and surface.
- Out-of-phase words: "new verdict", "REJECT/INVALID/FAIL" as a *produced* value (this is a display fix — no verdict change); "Phase 3" / "live cohort" (the Operator's next step, not yours).

## §4. Pre-Implementation Verification (MANDATORY before any edit)

Re-confirm the Addendum §A2.3 audit against the working tree before editing. Capture a `file:line` evidence anchor for each (anchors are at the post-fix `53ce5351…` blob):

1. **Desc resolution block** (transform.py:2692–2704): confirm the PULLBACK branch (2696) and fallback-pullback branch (2694) both resolve `flat_metrics.get("Entry_Zone_Reference") or flat_metrics.get("Anchor_Label", "")`. This is the desc whose fallback is being corrected.
2. **§A3.2 price re-source block** (transform.py:2766–2782): confirm the re-source boolean (`_is_profile_a and (_is_pullback or _render_as_pullback_fallback) and _daily_anchor is not None and _daily_anchor > 0`, ~2771–2772) and `_ref_price = _daily_anchor` (2773), `else _ref_price = _entry_ref` (2775). **This branch is where the boolean capture attaches.**
3. **`_ref_desc` consumer** (transform.py:2786 — `_entry_zone["reference"]["desc"]`): confirm it is the **only** consumer and there is no downstream re-assignment of `_ref_desc` after 2786. (SIR §11.6 item 8 — the desc override must be the last write before this read.)
4. **`_ez_inverted` (2756)** and **`_entry_ref` (2669)**: confirm present — both to be left **untouched**.
5. **`trigger.py:96`**: confirm `metrics["Entry_Zone_Reference"] = "Daily EMA 21"` (read-only reference; do not edit).

If any anchor does not match, **halt and surface** (§9) — do not adapt the spec.

## §5. Implementation Scope (Working-Tree Edits)

**`layers/tbs_engine/transform.py` — one edit, per Addendum §A3.3:**

1. In the **existing §A3.2 branch** that assigns `_ref_price = _daily_anchor` (2773), also set a boolean `_ref_price_is_daily_anchor = True`; set it `False` in the `else` (2775). (This is the only modification to the §A3.2 block — a flag capture, not a logic change.)
2. **Immediately before the `_entry_zone` dict** (before 2784), add the desc override:
   ```
   if _ref_price_is_daily_anchor:
       # [EZR-001-OBS-1] desc must match the re-sourced Daily-EMA-21 price; on
       # Entry_Zone_Reference-absent (verdict-gate early-return) paths the desc
       # would otherwise fall back to the hourly Anchor_Label. Literal mirrors
       # trigger.py:96 (Entry_Zone_Reference = "Daily EMA 21").
       _ref_desc = flat_metrics.get("Entry_Zone_Reference") or "Daily EMA 21"
   ```
   - **Gate:** fires on the same boolean as the §A3.2 price re-source (price + desc move together by construction).
   - **Do not** reassign `_entry_ref`; **do not** change `_ez_inverted`, the `[INVERTED]` desc suffix, the §A3.2 price re-source logic, the `entry_price_range` render gate, or any non-Profile-A / non-PULLBACK path. RECLAIM, breakout, Profile B, Profile C must be **byte-identical** in output.

**Test file:** append the §A4 case 7 tests (and its sub-assertions) to the existing ENG-006 bundle test file `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py`.

**Forbidden:** `output.py`, `trigger.py`, `gates.py`, `compute.py`, `main.py`, `data.py`, `types.py`, `exit.py`, `charts.py`, `helpers.py`, and any external count-guard test file (the desc fix touches no map size). A diff touching any of these = halt.

## §6. Test Mandate

Append the §A4 **case 7** group (desc/price consistency + the four sub-assertions: set-path no-regression / within-Profile-A `Daily_Protective_Anchor ≤ 0` fallback consistency / RECLAIM desc unchanged / Profile B-C desc unchanged) to the existing ENG-006 bundle test file. Keep the file's existing class/naming idiom (TEST-HRN-001 idempotent pattern). Fixtures are crafted `flat_metrics` dicts driving the transform layer — no IBKR/runtime dependency. Run locally:

```
pytest layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py -q
```

then the full unit suite for zero-regression:

```
pytest layers/tests/unit -q
```

Report the new-test count, the regression baseline (the S176-cont IMPLEMENTED state was **3321 passed / 4 skipped / 0 failed**), and an explicit zero-regression assertion or itemized list. Of particular interest: the existing case 5 regression guards (RECLAIM / Profile B-C / inversion) must remain green — a failure there indicates the desc override leaked outside Profile A PULLBACK.

## §7. Pre-Delivery Verification (MANDATORY before Hand-Back)

Run SIR §9 explicitly:
- [ ] Content accuracy — edit matches Addendum §A3.3 (re-read, don't recall).
- [ ] Internal consistency — no `output.py`/`trigger.py`/guard/`_entry_ref`/§A3.2-price-logic change; RECLAIM/B/C/breakout paths unchanged; within-Profile-A `anchor ≤ 0` fallback keeps price+desc hourly-consistent.
- [ ] Format integrity — Python edit clean; test file parses.
- [ ] Scope discipline — `git diff --stat` shows **only** `transform.py` + the one test file.
- [ ] Gate-function verification — no change to gate function names/order (none touched).
- [ ] Module-import verification — no new imports; acyclic graph intact.
- [ ] Verdict invariance + NotInGatesFile — green (the new `_ref_desc` local is not read by any gate function).

## §8. Hand-Back Contract

At Phase 2 close, deliver a Hand-Back conforming to **ACP §6.5** (canonical 10-section). Map §A4 case 7 to §5 test outcome; map the Addendum §A7 closure criteria (C2-OBS + the extended C3) to §10; note in §9 that Phase 3 re-validation needs one Profile A PULLBACK output on a verdict-gate-early-return ticker (CMG-class — `Entry_Zone_Reference` unset) confirming `entry_zone.reference.desc == "Daily EMA 21"` matching `reference.price` (C2-OBS).

## §9. Failure-Mode Protocol

Halt-and-surface in-session; do not commit on halt; do not unilaterally adapt the spec. Specific halt triggers:
- A Pre-Implementation Verification anchor (§4) does not match the working tree.
- The diff would touch a forbidden file (§5) — including any temptation to "just fix it" in `output.py` or to refactor `trigger.py:96` to a shared constant.
- A `VerdictInvariance` or `NotInGatesFile` test fails.
- A case 5 regression-guard test (Profile A RECLAIM, Profile B/C, inversion) fails — indicates the desc override leaked outside Profile A PULLBACK.
- Spec ambiguity discovered in Addendum §A3.3.

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

- **Addendum 1 v1.2 §A3.2** (the landed Profile A PULLBACK price re-source) — the desc override is its counterpart and reuses its exact re-source boolean. Read-only; do not re-touch except for the §5 flag capture.
- **`trigger.py:96`** (`Entry_Zone_Reference = "Daily EMA 21"`) — the canonical desc string the literal fallback mirrors. Read-only; do not edit.
- **DSP-004-OBS-2** traceability-comment precedent (`[DSP-004-OBS-2] … 19 -> 20`, transform.py) — the in-line traceability-comment idiom to mirror.
- **`ENG006_ENG003OBS1_PreClosure_Fixes_Implementation_Brief_v1_0.md`** (the prior ENG-006-OBS-1 + EZR-001 Phase 2 brief, closed) — read-only context for the bundle's prior re-run.
- Entry-zone builder existing `_db` "SWING" / `_is_pullback` / `_render_as_pullback_fallback` locals (transform.py:2669–2772) — the Profile-A-PULLBACK detection idiom (already computed; reuse, do not redefine).

## §11. Estimated Effort

Very small. One boolean capture in an existing branch + one conditional `_ref_desc` reassignment (4 lines incl. comment) in one function, plus one test group (case 7 with four sub-assertions). Single short CLI session. (Operator awareness only — not binding.)

---

## Sign-off

- **Authoring Analyst:** TBS Analyst (Project chat), Phase 1 close S176-cont-3.
- **Spec authority:** ENG-006 spec v1.0 + Addendum 1 **v1.2** §A3.3 (single source of truth; this Brief references, does not restate).
- **Operator decision points consumed at Phase 1:** EZR-001-OBS-1 fix direction — **Option (a)**, align `reference.desc` to "Daily EMA 21" whenever `reference.price` is sourced from `Daily_Protective_Anchor` (S176-cont-2); Option (b) rejected. §A2.3 audit resolutions (literal-fallback, same-boolean gate, RECLAIM/breakout untouched) resolved at source S176-cont-3.
- **Expected working-tree branch:** `eng006-eng003obs1-fib-extensions`.

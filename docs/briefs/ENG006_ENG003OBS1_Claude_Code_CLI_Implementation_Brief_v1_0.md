# ENG-006 + ENG-003-OBS-1 Bundle — Claude Code CLI Implementation Brief

**Brief version:** v1.0
**Authored:** S174 (Phase 1 close, after spec lock)
**Spec authority:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0
**Canonical format:** ACP §6.4 (11-section); structural anchor `RLC001_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Venue:** Claude Code CLI (within IntelliJ), working tree of `roescha/TBS_Master_App`
**Expected branch:** `eng006-eng003obs1-fib-extensions` off `master`

---

## §1. Mission

Implement the ENG-006 Fibonacci extension projections (primary) and the ENG-003-OBS-1 confluence re-point (Profile A) per the spec. **The spec is the single source of authority; this Brief is procedural scaffolding only. On any conflict between this Brief and the spec, the spec wins** — halt and surface (see §9), do not reconcile unilaterally.

This Brief references the spec by section and deliberately does **not** restate spec contracts (formulas, flat-key names, hierarchy-row shapes, guards). Read the spec.

---

## §2. Operational Context (CLI Venue)

You are the Claude Code CLI implementer with direct working-tree access:
- No uploads needed — the engine source is in the working tree (`layers/tbs_engine/`).
- You can run the local `pytest` cohort directly (dual-CWD per TEST-HRN-001 / BUG-CFL001-PRE-1 convention — from repo root and from `layers/`).
- You deliver the Hand-Back in-session at Phase 2 close (not as chat-paste / upload).
- You have git context: commit on the feature branch; do **not** push or merge (Operator-led per SIR §1.5.3).
- `.claude/settings.json` provides the pre-approval baseline (`acceptEdits` for file edits; IBKR/destructive shell still prompts).

---

## §3. Phase Boundaries + Vocabulary Constraints

**Phase 2 scope (in):** `output.py` ENG-006 extension block + ENG-003-OBS-1 confluence re-point; `transform.py` flat-key registration + hierarchy rows + round-trip reverse map; the new test file. That is the entire surface.

**Out of Phase 2 / out of scope (drift signals — if you reach for any of these, stop and re-read spec §1/§3):**
- **Any gate or verdict logic.** This bundle is NON-GATE (spec §4.5). If an edit would make a gate read `Fib_Ext_*` or `Fib_A_Confluence`, you have drifted.
- **`gates.py`, `compute.py`, `main.py`, `data.py`, `types.py`, `exit.py`, `trigger.py`, `charts.py`, `helpers.py`** — none are edited. A third-file diff-stat (beyond `output.py` + `transform.py` + the new test file) is a halt trigger (§9).
- **`Profit_Target` / `Profit_Target_Source` / `_map_source_to_tier` / the source-desc map** — extensions do **not** become the active target (spec §4.3, §11 items 6/8). Editing these is drift.
- **ENG-002 / Profile B confluence** — the Profile B analogue is a **DENY** (spec §9). Do not "fix" ENG-002.
- **Profile C extensions** — exempt (spec §3, §4.1). Do not add them.
- **ENG-004 Measured Move** — unchanged (it is the 100% level).
- **"v1.1" / scope expansion / "Phase 3" / "live validation"** — Phase 3 is Operator-led, separate. Do not attempt live runs.

**Phase 2 lexicon (use):** extension level, rally leg, Point A/B/C, structural floor, entry zone, Daily EMA 21, NON-GATE, hierarchy row, flat key, MAPPED_FLAT_KEYS, partition, ascending sort, null guard, additive.

---

## §4. Pre-Implementation Verification (MANDATORY before any edit)

Execute spec **§11 Pre-Implementation Checklist** against the working-tree source before editing. This mirrors the Analyst-side §11.6 audit (implementation-side defense layer). For each §11 item, source-pattern-match and confirm the `file:line` anchor still holds at your working-tree HEAD; record `file:line` evidence in Hand-Back §4.

Specifically re-confirm, because line numbers drift:
- `output.py` ENG-003 confluence `_current_price = last['close']` site (spec cites L1850) and the ENG-004 MM block insertion point (spec cites ~L1880–1918).
- `transform.py` `_all_mapped_flat_keys()` registration list (spec cites ~L1113–1115), the target-hierarchy append block (~L3078–3155), the post-partition `.sort(key=lambda x: x["price"])` (~L3266), and the round-trip reverse map (~L4526–4534).
- `data.py` `Daily_Protective_Anchor` producer (spec cites :968) and its `0.0` default (:682) — confirm the **null guard requirement** (spec §4.4) is necessary.
- `ctx.structural_floor_raw` reachability in `_assemble_output` (spec §11 item 7) — confirm it is **not** unpacked at the top, so use `ctx.structural_floor_raw` directly.

If any anchor has moved such that the spec's design assumption no longer holds (not just a line shift — a *semantic* change), **halt and surface** (§9). A pure line-number shift is expected; re-anchor and proceed.

---

## §5. Implementation Scope (Working-Tree Edits)

Working-tree paths only. Per-file scope per spec §4:
- `layers/tbs_engine/output.py` — ENG-006 extension block (spec §4.1, §4.2 metric writes) + ENG-003-OBS-1 re-point with null guard (spec §4.4).
- `layers/tbs_engine/transform.py` — `_all_mapped_flat_keys()` registration (spec §4.2), target-hierarchy rows (spec §4.3), round-trip reverse map (spec §4.2).
- `layers/tests/unit/test_eng006_eng003obs1_fib_extensions.py` — new (spec §6).

**No other file may be edited.** Out-of-scope file edits are forbidden; a third production-file touch forfeits scope and is a halt trigger (§9, SIR §11.2 escape-hatch discipline applies even though this is Track 1 — the principle is the same: do not silently expand the diff surface).

---

## §6. Test Mandate

Implement the full test set in spec **§6** — both NON-GATE assertions (`NotInGatesFile` + `VerdictInvariance` for both items) and the functional assertions (extension formula per profile, Profile C exemption, degenerate guards, hierarchy sort position + EXCEEDED routing, MAPPED_FLAT_KEYS + round-trip coverage, confluence re-point behavior, null guard).

- New test file location per spec §6; use the idempotent `sys.modules` loader guard (TEST-HRN-001 reference pattern).
- Run the full cohort from **both** repo-root and `layers/` CWD; assert **zero regression** vs the S173 baseline.
- Differential-verify: the new functional assertions should fail against pre-edit source and pass post-edit (record in Hand-Back §5).

---

## §7. Pre-Delivery Verification (MANDATORY before hand-back)

Run SIR §9 Pre-Delivery Verification Checklist in full. Additionally confirm the spec **§12** items:
- Extension levels display-scaled in flat keys + hierarchy rows (raw only in-block).
- ENG-003-OBS-1 null guard short-circuits before the five-branch ladder.
- Three new flat keys in `MAPPED_FLAT_KEYS`; `_audit_key_coverage` round-trip clean.
- `git diff --stat` shows only the three files in §5.

Gate-function verification (SIR §9): no gate function names/order changed — trivially true (no `gates.py`/`main.py` edit). Module-import verification: `output.py`/`transform.py` add no new cross-module imports; acyclic graph preserved.

---

## §8. Hand-Back Contract

Deliver a Hand-Back conforming to **ACP §6.5** (canonical 10-section template) in-session at Phase 2 close. (This Brief does not restate the §6.5 field list — see ACP §6.5.) Populate §4 with the spec §11 re-confirmation evidence, §5 with the dual-CWD cohort counts + differential verification, §8 with any Operator-run negative-path smoke results, §10 with the spec §7 closure-criteria tracker.

---

## §9. Failure-Mode Protocol

Halt and surface in-session (do **not** adapt the spec unilaterally; do **not** commit on halt) on any of:
- **Pre-Implementation Verification failure** — a §11 anchor's *semantic* assumption no longer holds at working-tree HEAD.
- **VerdictInvariance test failure** — any fixture's verdict changes pre/post (this bundle MUST be verdict-neutral).
- **NotInGatesFile failure** — a gate reads a new ENG-006/ENG-003-OBS-1 key.
- **Functional positive-only test failure** — a new assertion does not fail against pre-edit source (means it isn't actually exercising the change).
- **Third production-file diff-stat** — the diff touches anything beyond `output.py` + `transform.py` (+ test file).
- **Spec ambiguity discovery** — a spec instruction is under-determined against the working-tree reality.

On halt: state the trigger, the `file:line` evidence, and the decision needed. Wait for the Operator.

---

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

For pattern-matching only (do not edit):
- **ENG-002 / ENG-004** in `output.py` (the in-block rally-leg recompute + Fib/MM write pattern) — the model for the ENG-006 block shape and degenerate guards.
- **`MEASURED_MOVE` hierarchy row** in `transform.py` `_target_entries` — the model for the three `FIB_EXTENSION_*` rows (price/label/role/status/escalation_winner shape).
- **`Fib_382_Level` / `MM_Target`** in `_all_mapped_flat_keys()` + the round-trip reverse map — the model for registering + reconstructing the three new flat keys.
- **BUGR-002** target-side partition + post-partition ascending sort — confirms why extension append position is immaterial.
- **TEST-HRN-001** idempotent loader guard — the test-file `sys.modules` pattern.

---

## §11. Estimated Effort

One Phase 2 session. The rally-leg geometry and structural floor are already computed; ENG-006 is ~3 multiplication lines + flat-key/hierarchy plumbing; ENG-003-OBS-1 is a one-comparison re-point plus a null guard. The test file is the larger share (NON-GATE assertions + per-profile functional coverage). Not binding on the implementer.

---

## Sign-off

- **Authoring Analyst:** TBS Analyst (Project chat, S174).
- **Spec authority:** `ENG006_Fibonacci_Extension_Projections_Bundle_Spec_v1_0.md` v1.0 (locked S174).
- **Operator decision points consumed at Phase 1 (locked, S174):** bundling; ENG-003-OBS-1 Option 1 (Profile A only); ENG-006 Point C = structural floor (A+B; C exempt); rally leg = retracement leg; flat extension levels (PA-001 DQ-9 model); NON-GATE mandate (NotInGatesFile + VerdictInvariance); anchor split (confluence→entry zone, extension→structural floor); Profile B analogue = DENY (no ENG-002 change).
- **Expected working-tree branch:** `eng006-eng003obs1-fib-extensions` off `master@a1906ae`.

*TBS Implementation Brief | ENG-006 + ENG-003-OBS-1 bundle | v1.0 | S174 | ACP §6.4 canonical format*

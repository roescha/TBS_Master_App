# Tier 1S — Test Infrastructure Hygiene Bundle — Claude Code CLI Implementation Brief v1.0

**Phase 2 entry artifact.** Authored by the TBS Project-chat Analyst at Phase 1 close (working session S170).
**Track:** Bug-Fix Fast-Path (SIR §11.3), bundled. **Venue:** Claude Code CLI in IntelliJ on `roescha/TBS_Master_App`.
**Constituents:** TEST-HRN-001 + BUG-CFL001-PRE-1 + CT001-TEST-FLAKINESS (PEO §1S).

**Template note (read first):** This Brief follows the ACP §6.4 canonical 11-section structure. ACP §6.4 assumes a locked spec as authority and instructs the Brief to *reference spec sections without restating contracts*. **Tier 1S is a Bug-Fix Fast-Path bundle and has no spec** (SIR §11.3 — Fast-Path admits no spec authoring). Therefore this Brief's authority is the **Bug Register entries** (TEST-HRN-001, BUG-CFL001-PRE-1, CT001-TEST-FLAKINESS) **plus the locked S170 Phase 0 source-verification findings**, and the design decisions are carried **inline here** rather than by spec reference. Everywhere the template says "spec," read "Bug Register entry + Phase 0 findings in this Brief."

---

## §1 Mission

Harden three latent test-harness defects and eliminate the single pre-existing cohort failure, leaving the `pytest` suite green and CWD-independent — with **zero production-engine touch and zero documented-behaviour change**.

Authority is the Bug Register + the S170 Phase 0 findings carried in this Brief. **Conflict-resolution rule:** if the working-tree source at current `HEAD` contradicts any `file:line` anchor or scope claim below, **halt and surface** (§9) — do not adapt the fix unilaterally and do not "make the documented scope true."

---

## §2 Operational Context (CLI Venue)

The Claude Code CLI implementer has direct working-tree access to `roescha/TBS_Master_App` (no uploads needed), runs `pytest` locally, has full git context, and delivers the Hand-Back in-session (not as chat-paste/upload) per SIR §1.5.2 / ACP §6.5.

**CWD matters for this bundle.** BUG-CFL001-PRE-1 is a CWD-relative-path defect, so validation explicitly requires running the cohort from **both** the repo root **and** `layers/`. Tests are collected from `layers/tests/unit/`.

Suggested branch: `tier1s-test-infra-hygiene`.

---

## §3 Phase Boundaries + Vocabulary Constraints

**In scope (Phase 2):**
- Add the idempotent `sys.modules` guard to **3** test files (TEST-HRN-001 — corrected set, see §5.A).
- One `__file__`-anchored path fix in `test_eng004_measured_move.py` (BUG-CFL001-PRE-1 — §5.B).
- **Reproduce-first** investigation of CT001 B23–B26; edit only if it actually reproduces red (§5.C).
- Full-cohort validation from both CWDs; Hand-Back.

**Out of scope (forbidden):**
- Any edit to `tbs_engine/*.py`, `layers/*.py` production modules, or any non-test file.
- Any of the **6 already-guarded** files the stale Bug Register scope lists (see §5.A "do NOT touch").
- Any new feature, any output/gate/verdict/contract change, any spec authoring, any timestamp/clock "hardening" of CT001 written blind.

**Drift-signal vocabulary** (if you reach for these, stop and re-read scope): `engine`, `gate`, `verdict`, `output schema`, `flat key`, `DIA`, `live ticker`/`IBKR`, `spec §` (no spec exists for this bundle), and **"9 files"** (the TEST-HRN set is **3**, not 9 — §5.A).

---

## §4 Pre-Implementation Verification (MANDATORY — before any edit)

Implementation-side mirror of the Analyst's S170 source audit (SIR §11.6 discipline applied to test source). Re-confirm each anchor against current working-tree `HEAD` with `file:line` evidence; if any mismatches, **halt** (§9).

**4.1 — TEST-HRN-001 unsafe set (confirm exactly these 3, and confirm the 6 are already safe).**
- `tests/unit/test_frr001_fundamental_rr.py` — `_load_mod()` (≈L30–35) writes `sys.modules[name] = mod` with **no** early-return guard. CONFIRM unguarded.
- `tests/unit/test_sbo001_breakout.py` — inline unconditional submodule writes (≈L26 `tbs_engine.types`, L35 `tbs_engine.trigger`, L52 `tbs_engine.gates`). CONFIRM unguarded (the `if "tbs_engine" not in sys.modules` at the top guards only the *parent* stub).
- `tests/unit/test_sbo001_phase2.py` — inline unconditional submodule writes (≈L26 `tbs_engine.types`, L43 `tbs_engine.transform`). CONFIRM unguarded.
- CONFIRM already-guarded → **do NOT touch:** `test_rec001_phase2a_base_detection.py`, `test_rec001_phase2b_recovery_gates.py`, `test_rec001_phase2c_exit_architecture.py`, `test_rec_sc_combined_patch.py` (guarded `if _mod not in sys.modules:` loop), `test_vtrig001_volume_confirmation.py`, `test_vol004_volume_display.py` (guarded loop). Newer files (`its001`, `rly001`, `rlc001`, `dsp002`, both `bugr006`) already carry the canonical early-return guard — also do NOT touch.

**4.2 — BUG-CFL001-PRE-1.**
- `tests/unit/test_eng004_measured_move.py::Test...test_transform_roundtrip` (≈L418–419) calls `spec_from_file_location('transform', 'tbs_engine/transform.py')` — a **CWD-relative** path. CONFIRM it resolves only when CWD = `layers/`.
- CONFIRM the pattern to mirror exists: `test_frr001_fundamental_rr.py` computes `_engine_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tbs_engine")`. Use the same `__file__`-anchored construction.

**4.3 — CT001-TEST-FLAKINESS (reproduce-first; this is the gating check).**
- CONFIRM `layers/finnhub_context.py` is present and that `test_ct001_session_b.py` (≈L26) inserts `layers/` onto `sys.path`; CONFIRM symbols `_is_any_entry_stale`, `_get_sector_median_pe`, `_read_cache`, `CACHE_FILE` exist in `finnhub_context.py`.
- Run **`pytest tests/unit/test_ct001_session_b.py -k "TestB23 or TestB24 or TestB25 or TestB26"`** AND the full file with **no `--deselect`**, from the **repo root**, inside the full collected cohort. Capture the actual result.
  - **Green** (predicted by S170 isolated reproduction: 4/4 + 38/38, no `--deselect`) → CT001 takes the **NOT-REPRODUCIBLE** path (§5.C); no edit.
  - **Red** → capture the exact failure/traceback and **halt-and-surface** (§9). Do **not** write a timestamp/FS fix blind — the S170 evidence says timing/FS coupling is not the cause, so a red result means a new, un-traced mechanism that the Operator must scope.

---

## §5 Implementation Scope (Working-Tree Edits)

**§5.A — TEST-HRN-001 (3 files; idempotent `sys.modules` guard).**
- `test_frr001_fundamental_rr.py`: insert the early-return guard as the first two lines of `_load_mod()`:
  `if name in sys.modules: return sys.modules[name]` (mirror the canonical idiom in `test_its001_intraday_tactical.py` / `test_bugr006_profile_b_brk_rr.py`).
- `test_sbo001_breakout.py` and `test_sbo001_phase2.py`: guard each unconditional submodule write so the module is only built+registered when absent. Preferred minimal form, per write site:
  `if "<modname>" not in sys.modules: <build + spec_from_file_location + module_from_spec + sys.modules[...] = + exec_module>`; otherwise reuse the existing entry. (Equivalently, refactor the sequential writes into the guarded loop idiom used by `test_rec001_phase2a_base_detection.py`.) Preserve every existing stub-attribute assignment.
- These files are **dormant/latent** today (protected by collection order), so the cohort PASS/FAIL count is **unchanged** by this hardening. That invariance is itself a check: if guarding any of the 3 changes a test outcome, **halt** (§9).

**§5.B — BUG-CFL001-PRE-1 (1 file).**
- `test_eng004_measured_move.py::test_transform_roundtrip`: replace the CWD-relative `'tbs_engine/transform.py'` with a `__file__`-anchored absolute path (mirror `test_frr001`'s `_engine_dir`). This converts the single pre-existing cohort failure to PASS and makes it pass from **both** CWDs.

**§5.C — CT001-TEST-FLAKINESS (no edit anticipated).**
- If §4.3 is green: **no file edit.** The resolution is the reproduction evidence (close NOT-REPRODUCIBLE at Phase 4). Record the dual-context evidence in the Hand-Back.
- If §4.3 is red: **no edit** — halt (§9).

**Forbidden:** any edit outside the at-most-4 test files named above. Touching a 5th file or any production module forfeits the Fast-Path scope (SIR §11.2 escape-hatch discipline) → halt and surface.

---

## §6 Test Mandate

- **No new test file** is created — Tier 1S *fixes* test infrastructure; the validation surface **is** the existing cohort.
- Run the **full unit cohort** (`pytest layers/tests/unit/` equivalent) from **both** the repo root **and** `layers/` CWD. Both must be green with **no `--deselect`**.
- TEST-HRN-001 idempotent-pattern awareness: the canonical guard is `if name in sys.modules: return sys.modules[name]` (helper form) or `if "<mod>" not in sys.modules:` (inline form). Re-importing a guarded module must return the cached object (no `sys.modules` overwrite).
- Capture the cohort counts (passed/skipped/failed) for each CWD in the Hand-Back, plus the pre/post status of the eng004 roundtrip test and B23–B26.

---

## §7 Pre-Delivery Verification (MANDATORY — before Hand-Back)

Invoke SIR §9 explicitly. All must hold:
- **Content accuracy:** every edit matches a §5 instruction; the 3 TEST-HRN files match §4.1; eng004 matches §4.2.
- **Scope discipline:** at most 4 test files touched; zero production/engine files; zero of the 6 already-guarded files; `git diff --stat` shows only `tests/unit/` paths.
- **Dual-CWD cohort green**, no `--deselect`; the eng004 roundtrip now PASSES from both CWDs; B23–B26 pass from both CWDs.
- **Invariance:** the 3 TEST-HRN guards changed no test outcome (count delta from the guards alone = 0).
- **Gate/module checks (trivially satisfied):** no `tbs_engine/` touch ⇒ gate functions, gate order, and the acyclic module import graph are untouched — state this affirmatively.
- **CT001 disposition** recorded with evidence (NOT-REPRODUCIBLE, or red-halt).

(No spec §12 to reference — Fast-Path bundle.)

---

## §8 Hand-Back Contract

Deliver an in-session Hand-Back conforming to **ACP §6.5** (canonical 10-section structure). Do not restate the field list here. Ensure §6.5 "Process Deviation" captures any divergence from this Brief (e.g., if §4.3 reproduced red, or if a write site differed from the §4 anchors).

---

## §9 Failure-Mode Protocol

Halt-and-surface **in-session**; do **not** commit on halt; do **not** adapt scope unilaterally. Specific halt triggers:
- §4 re-confirmation mismatch (a documented-unsafe file is already guarded, or a documented-safe file is actually unsafe, or a `file:line` anchor has drifted materially).
- **CT001 B23–B26 reproduces red** (§4.3) — capture the traceback, halt; the Operator scopes the new mechanism.
- Any TEST-HRN guard changes a test PASS/FAIL outcome (§5.A invariance violated).
- The eng004 `__file__` fix fails to make the roundtrip green from **both** CWDs.
- Any need to touch a 5th file or any production/engine module (Fast-Path scope forfeit, SIR §11.2).

---

## §10 Sibling-Spec Pattern References (Read-Only Anchors)

- **Idempotent guard (helper form):** `tests/unit/test_bugr006_profile_b_brk_rr.py` (`_load_mod` with `if name in sys.modules: return sys.modules[name]`); also `test_its001_intraday_tactical.py`, `test_rly001_rally_state.py`, `test_dsp002_analyst_levels_surfacing_decoupling.py` (`_load_compute_module`, with an explicit "TEST-HRN-001 guard" comment).
- **Guarded-loop form (inline):** `tests/unit/test_rec001_phase2a_base_detection.py` (`for _mod, _path in [...]: if _mod not in sys.modules:`).
- **`__file__`-anchored engine-dir idiom:** `tests/unit/test_frr001_fundamental_rr.py` (`_engine_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tbs_engine")`).
- **NOT-REPRODUCIBLE close precedent:** Bug Register `FFD-001-BUG-1` (✅ CLOSED — NOT REPRODUCIBLE).

These are read-only anchors for pattern matching — do not edit them.

---

## §11 Estimated Effort

Small. Four test-file edits (~3 guard insertions + 1 path fix, ≈10–20 LOC total) plus one reproduce-first run for CT001. Single Phase 2 session; well under a typical bundle. No new tests, no DIA cascade.

---

## Closing — Sign-off

- **Authoring Analyst:** TBS Project-chat Analyst (working session S170).
- **Authority:** Bug Register entries TEST-HRN-001, BUG-CFL001-PRE-1, CT001-TEST-FLAKINESS + S170 Phase 0 source-verification findings (carried inline; no spec — Bug-Fix Fast-Path per SIR §11.3).
- **Operator decision points consumed at Phase 1:** DQ-1 cadence lock = Bug-Fix Fast-Path + CLI Brief; Phase 0 source-verification authorization; "proceed" to Brief authoring. (Open items deferred to the Operator: confirm working session number; confirm NOT-REPRODUCIBLE disposition for CT001 if §4.3 is green.)
- **Expected working-tree branch:** `tier1s-test-infra-hygiene`.
- **Reconciliation (Phase 4, Project chat):** Bug Register — TEST-HRN-001 ✅ CLOSED (with **scope-correction note: documented 9-file set → actual 3**), BUG-CFL001-PRE-1 ✅ CLOSED, CT001-TEST-FLAKINESS ✅ CLOSED (NOT-REPRODUCIBLE, evidence-anchored) — plus PEO §1S ✅ CLOSED + README housekeeping. Doc 2 / Doc 7 / Doc 8 / EEM verify-only. No spec body, no engine, no gate, no output-contract change.

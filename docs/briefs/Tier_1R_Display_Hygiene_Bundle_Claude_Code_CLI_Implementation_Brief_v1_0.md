# Tier 1R Display Hygiene Bundle — Claude Code CLI Implementation Brief v1.0

**Brief ID:** `Tier_1R_Display_Hygiene_Bundle_Claude_Code_CLI_Implementation_Brief_v1_0`
**Version:** v1.0
**Phase:** 2 (Claude Code CLI implementation)
**Authoring template:** ACP v1.3 §6.4 canonical 11-section Brief
**Phase 2 lifecycle position:** authored at Phase 1 close (post-spec lock); consumed at Phase 2 entry; frozen on delivery; not amended after Phase 2 begins (divergence surfaces via Hand-Back §6 Process Deviation per ACP §6.5)
**Authority hierarchy:** spec → brief → implementer interpretation; spec wins on any conflict
**Companion artifacts:**
- Authority: `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md` v1.0 (in working tree at `docs/specs/` after Operator promotion)
- Hand-Back target: `Tier_1R_Display_Hygiene_Bundle_Phase2_Implementation_HandBack_v1_0.md` per ACP §6.5

---

## §1. Mission

Implement the Tier 1R Display Hygiene Bundle per `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md` §4 (Implementation Contract), §5 (Pipeline & Call-Order Reference), and §6 (Test Plan). The **spec is the contract authority**; this brief is procedural scaffolding for the Claude Code CLI implementation venue.

**Conflict resolution rule:** If anything in this Brief appears to contradict the spec, the spec wins. Halt and surface to Operator per §9 of this Brief.

**Three constituent bugs in scope:**
- DSP-004-OBS-1 — Profile C `extension_analysis.anchor.label` + `.desc` weekly-frame correctness
- DSP-004-OBS-2 — Profile C `floor_analysis.hierarchy[EMA_21].label` weekly-frame correctness + `WEEKLY_EMA_21` vocabulary extension
- BUGR-006-LABEL-RESIDUAL-1 — Idempotence guard substring widening (`"BRK-001 fallback"` → `"BRK-001"`)

All three are display-layer cosmetic. Zero gate impact, zero verdict impact, zero arithmetic impact. Per spec §1.4.

---

## §2. Operational Context (CLI Venue)

The Phase 2 implementer operates in the Claude Code CLI venue with the following affordances and constraints per ACP v1.3 §6.2 + SIR §1.5.2:

| Affordance | Use it |
|---|---|
| Direct working-tree access at `roescha/TBS_Master_App@master` clone | Read engine source authoritatively; no `web_fetch` needed |
| No uploads / no chat-paste hops | Spec + this Brief are pre-copied to working-tree root by Operator before session entry |
| Local pytest invocation from `layers/` CWD | Run full cohort + differential tests in-session |
| Git context — branch, diff, stash, log | Create branch `tier1r-display-hygiene-bundle` off `master`; commit at session close, not before |
| Local file edit tools | Apply 4 edits per spec §4.1-§4.4 directly; iterate on tests in-session |
| Hand-Back delivered in-session per ACP §6.5 | Author Hand-Back as final deliverable before commit; do NOT push or merge — Operator handles |

**Working-tree-only constraint:** All edits land in working-tree files. Do NOT create files outside the working tree. Do NOT push to remote. Do NOT merge to master. The session ends with a clean local commit on the working branch + Hand-Back delivered in-session for Operator inspection.

**Pre-approval:** The `.claude/settings.json` project-level config grants `acceptEdits` for the standard development tools per CFL-001-PROC-1 S157 baseline. No additional permissions needed for this Bundle.

---

## §3. Phase Boundaries + Vocabulary Constraints

### 3.1 Phase 2 IN-scope

- Apply Edits 1-4 per spec §4.1-§4.4 exactly as specified
- Author `tests/unit/test_dsp004_obs_bundle_label_hygiene.py` per spec §6
- Run full pytest cohort from `layers/` CWD (target: ~3245 / 4 / 0)
- Verify 6 differential tests FAIL pre-fix → PASS post-fix per spec §6.4
- Author Hand-Back per ACP §6.5 (10-section template)

### 3.2 Phase 2 OUT-of-scope (drift signals — halt if encountered)

| Drift signal | Why it's out-of-phase |
|---|---|
| **"v1.1"**, **"extension"** (of this Bundle), **"v1.0.1"**, **"epsilon"** | Bundle scope is v1.0; any amendment to spec is Project-chat-side work, not Phase 2 |
| **"Phase 3"**, **"live cohort"**, **"6-run"**, **"REL.L"**, **"CRH-B"**, **"witness"** | Phase 3 live validation is Operator-led, runs AFTER Hand-Back |
| **"DIA"**, **"Phase 4"**, **"Doc 2 v8.66"**, **"Doc 8 v8.7.66"**, **"README v8.6.35"**, **"PEO v9.27"** | Phase 4 documentation cascade is Project-chat-side, post-Hand-Back |
| **"close BUGR-006 v2.0"** or any re-litigation of closed work | DSP-004 v1.0/v1.1, BUGR-006 v2.0, BRK-001 spec body — all out-of-scope per spec §1.3 |
| **"gate"**, **"verdict change"**, **"R:R re-derive"**, **"sizing"** | Zero gate impact per spec §1.4; if implementation surfaces any of these, halt |
| **Third file touch beyond `output.py` + `transform.py` + the new test file** | Track 1 admissibility broader than Track 2 but a third-engine-file diff is a halt signal; surface to Operator before proceeding |
| **Mid-implementation spec amendment** | Spec is frozen at Phase 1 lock; surface defects via Hand-Back §6 Process Deviation, do NOT amend spec mid-implementation |

### 3.3 Phase 2 vocabulary (lexicon)

The following terms appear in spec §4 contracts and must be used verbatim in commit messages and Hand-Back narrative:
- `Extension_Anchor_Type` (flat key name)
- `Extension_Anchor_Label` (flat key name)
- `WEEKLY_SMA_200` (Profile C extension anchor token)
- `WEEKLY_EMA_21` (Profile C EMA 21 floor token — new vocabulary)
- `DAILY_EMA_21` (Profile A/B EMA 21 floor token — preserved)
- `_ema21_label_map` (new variable per spec §4.2)
- `_LABEL_TIER_MAP` (existing module-level dict — extended per spec §4.3)
- `Profit_Target_Source` (flat key affected by guard widening per spec §4.4)
- `BRK-001 §8.1 MM-null fallback` (compute.py emission form — guard match target)
- `differential test` (FAIL pre-fix → PASS post-fix test class)
- `regression-invariance` (test class for Profile A/B + non-Profile-C paths)
- `BUGR-002 partition` (entry-preservation contract for EMA 21 floor entry per spec §3.3)

---

## §4. Pre-Implementation Verification (MANDATORY)

Execute the following before applying ANY edit. Document `file:line` evidence anchors in Hand-Back §4 per ACP §6.5. **If any check fails, halt and surface per §9 of this Brief — do NOT proceed with edits.**

This §4 mirrors **spec §11.1-§11.6** plus SIR §11.6 ITEM 1 + ITEM 3 + ITEM 6 + ITEM 8 audits as implementation-side defense.

### 4.1 Spec authority verification

- [ ] Spec file `docs/specs/Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md` is present in working tree at the path Operator copied to.
- [ ] Spec version is `v1.0`; spec §2 Design Lock DQ-1 through DQ-8 are all marked LOCKED.
- [ ] No `[TODO]`, `[TBD]`, or pending-decision markers in spec §4 (Implementation Contract) or §6 (Test Plan).

### 4.2 Engine source state verification

For each of the 4 edits, confirm the cited pre-fix code matches working-tree source exactly:

- [ ] `tbs_engine/output.py:2873-2875` — pre-fix code matches spec §4.1 "Pre-fix code" block verbatim (line drift acceptable up to ±5 lines; substring match required)
- [ ] `tbs_engine/transform.py:3309-3314` — pre-fix code matches spec §4.2 "Pre-fix code" block verbatim
- [ ] `tbs_engine/transform.py:175-180` — pre-fix code matches spec §4.3 "Pre-fix code" block verbatim (vocabulary map current state)
- [ ] `tbs_engine/output.py:2064-2066` — pre-fix code matches spec §4.4 "Pre-fix code" block verbatim

**If line numbers have drifted significantly (>10 lines from spec citation):** halt and surface — the spec needs a Files-field correction before proceeding (this is itself a §11.6 ITEM 1 audit-class incident).

### 4.3 §11.6 ITEM 3 — Shared-reference / partition-leak verification (per spec §11.1)

- [ ] Confirm `_floor_entries` list at `transform.py:~L3309` is the SAME list that flows through the BUGR-002 partition mechanism. Execute:
  ```bash
  grep -nE "_floor_entries\." layers/tbs_engine/transform.py | head -20
  ```
  Verify the partition predicate (`_current_price < _ema21_price` → `overhead_levels[]`; otherwise → `hierarchy[]`) is structurally upstream of any consumer of the entry's `label` field.
- [ ] Confirm no entry-mutation site rewrites `.label` after `_floor_entries.append(...)` — `grep` negative on `'label':\s*"DAILY_EMA_21"` outside the cited site after Edit 2 lands.

### 4.4 §11.6 ITEM 6 — Cross-spec layout audit (per spec §11.2)

- [ ] Read `docs/specs/DSP004_Profile_C_Weekly_Anchor_Label_Spec_v1_1.md` — confirm no §-numbering or scope-fingerprint collision with this Bundle's edits.
- [ ] Read `docs/specs/BUGR006_Label_Fidelity_Bundle_Spec_v1_0.md` — confirm no §-numbering or scope-fingerprint collision.
- [ ] If a CNV-001 spec is present (`docs/specs/CNV001_*.md`), confirm `_LABEL_TIER_MAP` extension via `WEEKLY_EMA_21` is admissible at MA_DYNAMIC rank 3 per CNV-001's tier-classification contract.

### 4.5 §11.6 ITEM 8 — Downstream-override-path audit (per spec §11.3)

- [ ] Execute `grep -nE 'Extension_Anchor_Type' layers/tbs_engine/*.py`. Confirm `output.py:2861-2878` is the ONLY engine-file write site. Zero other writes.
- [ ] Execute `grep -nE 'Extension_Anchor_Label' layers/tbs_engine/*.py`. Same expectation.
- [ ] Execute `grep -nE '"BRK-001 fallback"|"BRK-001 §8\.1"|"fallbacks exhausted"|"BRK-001 post-breakout"' layers/tbs_engine/*.py`. Verify the four compute.py emission forms cited in spec §4.4 plus the output.py:2064 guard. Zero other emission sites for these BRK fallback substrings.

### 4.6 Vocabulary collision verification (per spec §11.4)

- [ ] Execute `grep -nE 'WEEKLY_EMA_21' layers/tbs_engine/ layers/tests/` (recursive). Pre-edit expectation: **zero matches** in production code. After Edit 2 + Edit 3 land: matches only at the two new edit sites + new test file references.
- [ ] After Edit 3 lands, run a quick sanity import:
  ```bash
  cd layers && python -c "from tbs_engine.transform import _LABEL_TIER_MAP; print(_LABEL_TIER_MAP.get('WEEKLY_EMA_21'))"
  ```
  Expected output: `('MA_DYNAMIC', 3)`. If anything else (or KeyError), halt.

### 4.7 Gate-cascade negative assertion (per spec §11.5)

- [ ] Execute `grep -nE 'Extension_Anchor_Type|WEEKLY_EMA_21|WEEKLY_SMA_200|BRK-001 fallback|BRK-001 §8\.1' layers/tbs_engine/gates.py`. Expected: **zero matches**, both pre-edit and post-edit. If any match — halt.

### 4.8 Module-import-graph acyclicity (per spec §11.6)

- [ ] After all 4 edits land, execute:
  ```bash
  cd layers && python -c "from tbs_engine import compute, output, transform, gates, types, helpers, trigger, exit, data, main, charts; print('ok')"
  ```
  Expected: `ok`. Any ImportError — halt.
- [ ] Confirm zero new `import` statements added in any edited file. `git diff layers/tbs_engine/output.py layers/tbs_engine/transform.py | grep -E "^\+import |^\+from "` should produce zero lines.

---

## §5. Implementation Scope (Working-Tree Edits)

| Edit | File | Lines | Spec § | Touch class |
|---|---|---|---|---|
| Edit 1 (DSP-004-OBS-1) | `layers/tbs_engine/output.py` | ~2873-2875 (3 lines replaced + ~5 LOC inline commentary) | spec §4.1 | Profile C branch update + label desc weekly-frame |
| Edit 2 (DSP-004-OBS-2) | `layers/tbs_engine/transform.py` | ~3309-3314 (label_map insert + append literal change, +8 LOC) | spec §4.2 | New `_ema21_label_map` + append uses it |
| Edit 3 (vocabulary extension) | `layers/tbs_engine/transform.py` | ~175-180 (insert WEEKLY_EMA_21 row, +1 LOC) | spec §4.3 | `_LABEL_TIER_MAP` extension |
| Edit 4 (BUGR-006-LABEL-RESIDUAL-1) | `layers/tbs_engine/output.py` | ~2064-2066 (single substring + ~8 LOC commentary, +9 LOC) | spec §4.4 | Guard substring widening |
| New test file | `layers/tests/unit/test_dsp004_obs_bundle_label_hygiene.py` | NEW file (~400-500 LOC) | spec §6 | 7 classes / ~30 tests |

**Total engine LOC delta:** +23 to +25 across 2 engine files. Net engine LOC increase trivial.

**Per ACP §6.4 + SIR §11.2 third-file forbid:** ONLY the 2 engine files `output.py` + `transform.py` may be touched. Any other engine file touch is a halt signal. The new test file `test_dsp004_obs_bundle_label_hygiene.py` does not count toward the file-scope limit.

**Forbidden edits (out of scope):**

- `tbs_engine/compute.py` — DO NOT touch. compute.py:807/817/853 emit semantically-correct §8.1 fallback labels per BRK-001 v1.1; the defect is purely in the downstream output.py guard. Any compute.py edit triggers spec §1.3 out-of-scope.
- `tbs_engine/gates.py` — DO NOT touch. Bundle has zero gate impact per spec §1.4.
- `tbs_engine/types.py`, `main.py`, `helpers.py`, `data.py`, `trigger.py`, `exit.py`, `charts.py` — DO NOT touch. Not part of bundle scope.
- `tbs_orchestrator.py`, `tbs_scanner.py` — DO NOT touch per spec §9.2 (downstream consumers pass through transparently).
- Existing test files outside the new file — DO NOT touch per spec §9.3 (no pre-existing tests assert on the changed labels; pre-spec-delivery audit confirmed). If implementer's `grep` audit per §4.4 surfaces a pre-existing test that DOES assert on `"SMA_200"` or `"DAILY_EMA_21"` literal on Profile C, halt per §9 of this Brief (this would be a spec §3.2 finding inversion).

---

## §6. Test Mandate

### 6.1 New test file

- **Path:** `layers/tests/unit/test_dsp004_obs_bundle_label_hygiene.py`
- **Class structure:** per spec §6.1 — 7 classes (TestDSP004OBS1ProfileCExtensionAnchorLabel / TestDSP004OBS1ABRegressionInvariance / TestDSP004OBS2ProfileCEMA21FloorEntryLabel / TestDSP004OBS2OverheadLevelsPartition / TestDSP004OBS2VocabularyExtension / TestBUGR006LabelResidualGuardWidening / TestBUGR006LabelResidualRegressionInvariance + TestBundleVerdictInvariance + TestBundleNotInGatesFile)
- **Test count:** ~25-35 tests total
- **Differential test mode:** 6 specific tests per spec §6.4 — FAIL pre-fix, PASS post-fix. Implementer must verify the FAIL-pre-fix expectation by `git stash`-ing the engine edits, running the test file, observing the 6 failures, then `git stash pop` and re-running for the PASS-post-fix evidence. Both runs captured in Hand-Back §5.

### 6.2 TEST-HRN-001 hygiene awareness

Per the existing IDENTIFIED bug TEST-HRN-001 (logged S137-cont, still open in Bug Register):

- Use `spec_from_file_location` for any dynamic module-loading patterns
- Wrap any `sys.modules[name] = ...` registration with an idempotent guard: `if name in sys.modules: return sys.modules[name]`
- Mirror the safe-pattern precedent in existing files: `test_bugr002_hierarchy_partition.py`, `test_pa001_phase3_hierarchies.py`, `test_dsp004_profile_c_weekly_sma_label.py`

### 6.3 Local pytest invocation

```bash
cd layers
pytest tests/unit/test_dsp004_obs_bundle_label_hygiene.py -v
```

Expected: ~30 passed / 0 failed / 0 skipped (new file only).

Then full cohort regression:

```bash
cd layers
pytest -v 2>&1 | tail -50
```

Expected: ~3245 passed / 4 skipped / 0 failed. **Note:** `pytest` MUST be invoked from `layers/` CWD per S168 BUG-CFL001-PRE-1 CWD-sensitivity convention. Invocation from repository root will produce 1 spurious failure on `test_eng004` (pre-existing, unrelated to this bundle).

### 6.4 Regression baseline

| Metric | Target |
|---|---|
| Baseline pre-edit pytest (`cd layers && pytest`) | 3215 passed / 4 skipped / 0 failed (S168 baseline) |
| Post-edit pytest | ~3245 passed / 4 skipped / 0 failed |
| Net new tests | +~30 |
| Net new failures | **0** (zero Bundle-caused regressions allowed) |
| Differential test classes (FAIL pre / PASS post) | 6 specific tests per spec §6.4 |

### 6.5 Verdict-invariance + gates negative-assertion (per spec §6.1 class breakdown)

- `TestBundleVerdictInvariance` MUST pass — verdict invariance across Profile A/B/C × {VALID, INVALID} fixture matrix
- `TestBundleNotInGatesFile` MUST pass — in-test `grep`-style negative assertion on gates.py for changed identifiers

If either fails post-edit — halt per §9 of this Brief.

---

## §7. Pre-Delivery Verification (MANDATORY before Hand-Back)

Execute SIR §9 Pre-Delivery Verification Checklist before authoring Hand-Back. Each item documented with PASS / FAIL annotation in Hand-Back §7 per ACP §6.5.

| § | Item | Expected status |
|---|---|---|
| 9.1 | Content accuracy | PASS — Edit 1-4 land exactly per spec §4.1-§4.4; new test file structure matches spec §6 |
| 9.2 | Internal consistency | PASS — engine edits + test assertions match; differential tests behave per spec §6.4 |
| 9.3 | Format integrity | PASS — `.py` source files only; no `.docx-as-text` artifacts |
| 9.4 | Scope discipline | PASS — only `output.py` + `transform.py` + new test file touched; `git diff --stat` matches expectation |
| 9.5 | Gate function verification | PASS — `TestBundleNotInGatesFile` + `TestBundleVerdictInvariance` both pass; manual `grep` against gates.py returns zero matches |
| 9.6 | Module import verification | PASS — full module-import sanity import returns `ok` per §4.8 |
| 9.7 | Bug Register updated (Phase 4 work — deferred) | PENDING — not the implementer's responsibility at Phase 2 close |
| 9.8 | DIA current (Phase 4 work — deferred) | PENDING — not the implementer's responsibility at Phase 2 close |

**Additional Pre-Delivery items per spec §12:**

- [ ] Spec §11 Pre-Implementation Checklist (§11.1-§11.6) all items PASS or RESOLVED, documented in Hand-Back §4
- [ ] Live-sampling smoke check (Hand-Back §8) — Operator-run pre-Phase-3 smoke optional; if executed, capture ticker / profile / verdict
- [ ] Closure-criteria tracker (Hand-Back §10) per spec §7.1 — each criterion mapped to ✅ at Phase 2 / pending Phase 3 / pending Project-chat-side

---

## §8. Hand-Back Contract

The Hand-Back delivered at Phase 2 close follows the canonical **10-section ACP §6.5 template**. Do NOT restate the 10-section field list here — implementer references ACP §6.5 directly when authoring the Hand-Back.

**Hand-Back filename:** `Tier_1R_Display_Hygiene_Bundle_Phase2_Implementation_HandBack_v1_0.md`
**Hand-Back transit:** Authored in working-tree root; Operator promotes to `docs/handbacks/` at bundle closure per SIR §1.5.3.

**Specific spec §-anchored expectations for this Bundle's Hand-Back:**

- Hand-Back §3 ("What Was Built — Per Spec §4") — per-file breakdown of the 4 edits with `file:line` post-edit anchors + post-edit SHAs from `git rev-parse HEAD:<filepath>`
- Hand-Back §4 ("Verification — Spec §11") — each §4 item in this Brief mapped to PASS / RESOLVED / FAIL with `file:line` evidence
- Hand-Back §5 ("Test Outcome") — pytest invocation excerpt + the differential evidence (pre-fix FAIL count of 6 + post-fix PASS count of 6 on the named differential tests per spec §6.4)
- Hand-Back §6 ("Process Deviation") — if §3.2 of this Brief's drift signals were encountered + resolved in-session per §9 of this Brief, document the deviation; otherwise "None"
- Hand-Back §9 ("Open Items for the Analyst") — surface any Phase-3 / Phase-4-side items discovered during implementation (e.g., a partition-mechanism observation; a vocabulary edge case; a TEST-HRN-001 hygiene incident)
- Hand-Back §10 ("Closure-Criteria Tracker — Spec §7") — each spec §7.1 criterion marked ✅ at Phase 2 / pending Phase 3 / pending Project-chat-side

---

## §9. Failure-Mode Protocol

**Halt-and-surface in-session protocol:** If any of the conditions below trigger during implementation, halt immediately and surface to Operator with a concise summary (the issue, evidence file:line anchors, and a recommended resolution path). Do NOT commit. Do NOT amend the spec unilaterally. Do NOT proceed past the halt point.

### 9.1 Mandatory halt triggers

| # | Trigger | Detection | Resolution |
|---|---|---|---|
| 1 | Pre-Implementation Verification failure (any §4 item fails) | §4.1-§4.8 checks | Surface with `file:line` evidence anchor; spec amendment may be required Project-chat-side; do NOT proceed with edits |
| 2 | `TestBundleVerdictInvariance` FAIL post-edit | `pytest test_dsp004_obs_bundle_label_hygiene.py::TestBundleVerdictInvariance` | Verdict invariance is a Bundle hard contract; failure means an edit landed wrong OR a previously-unknown gate dependency exists. Halt; surface; Operator decides spec amendment vs edit rollback |
| 3 | `TestBundleNotInGatesFile` FAIL post-edit | `pytest test_dsp004_obs_bundle_label_hygiene.py::TestBundleNotInGatesFile` | A changed identifier surfaced in gates.py — bundle is no longer admissible as "zero gate impact". Halt; surface |
| 4 | Third engine file diff (anything beyond output.py + transform.py in `git diff --stat`) | `git diff --stat layers/tbs_engine/ \| grep -v "^output.py\|^transform.py"` | Out-of-scope per spec §1.3. Halt; surface; never silently extend scope |
| 5 | Spec ambiguity discovery in §4.1-§4.4 contracts | Implementer can't determine exact edit shape from spec contract | Halt; surface; spec amendment Project-chat-side may be needed |
| 6 | Vocabulary collision discovered for `WEEKLY_EMA_21` | §4.6 `grep` finds pre-existing matches | Vocabulary not actually new — halt; surface; spec §3.6 audit was incomplete |
| 7 | Differential test inversion | A spec §6.4 differential test PASSES pre-fix or FAILS post-fix in `git stash` reverse test | Halt; surface; one of: spec §4 contract wrong, test wrong, or pre-existing engine state differs from spec assumption |
| 8 | Pre-existing test asserts on changed label literal | §4.4 `grep` audit finds e.g. `assert anchor["label"] == "SMA_200"` on Profile C in a non-new-file test | Halt; surface; spec §9.3 consumer audit was incomplete — Operator decides scope expansion vs spec amendment |
| 9 | Pytest baseline regression (any pre-existing test FAILS post-edit) | Pre-edit `pytest` baseline differs from post-edit baseline by non-bundle regression | Halt; surface; identify which test, whether it's CWD-sensitive (BUG-CFL001-PRE-1 known issue from non-`layers/` CWD) or a genuine regression |

### 9.2 Soft halt triggers (note + continue, but document in Hand-Back §6)

| # | Trigger | Detection | Action |
|---|---|---|---|
| 10 | Line number drift ≤10 lines from spec citation (acceptable but not zero) | `file:line` lookup vs spec | Continue with substring-match validation; note drift in Hand-Back §6 Process Deviation |
| 11 | New test file is larger than ~500 LOC (above spec §6 estimate) | LOC count | Continue if tests are valuable; note size in Hand-Back §5 |
| 12 | Pytest baseline differs from S168's 3215 by ±5 (third-party test additions since spec authoring) | Pre-edit baseline check | Continue with adjusted baseline; document the actual baseline in Hand-Back §5 |

### 9.3 Forbidden self-amendments

- Do NOT amend the spec.
- Do NOT touch `compute.py`, `gates.py`, or any engine file outside `output.py` + `transform.py`.
- Do NOT extend the Bundle scope to fold in adjacent observations (e.g., if a Profile A `extension_analysis.daily.anchor.label = "EMA_21"` parallel-mismatch hygiene candidate is observed, log it for a separate Bug Register entry; do NOT fold into this Bundle).
- Do NOT push to remote.
- Do NOT merge to master.

### 9.4 Constructive in-session surfacing

If observations DO surface during implementation that warrant a future Bug Register entry but do NOT require halt (e.g., a TEST-HRN-001-class pattern observation, a partition-mechanism observation), document them in Hand-Back §9 Open Items for the Analyst. The Project-chat Analyst will log them at Phase 4 closure.

---

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

The following are read-only references for pattern matching. Do NOT modify these files. Use them for closed-pattern symmetry verification.

### 10.1 Closed-pattern templates (THIS bundle extends these)

| Path | Purpose |
|---|---|
| `docs/specs/DSP004_Profile_C_Weekly_Anchor_Label_Spec_v1_1.md` | DSP-004 v1.0/v1.1 parent — the closed Profile-C-aware label tier pattern this Bundle extends to additional sites |
| `layers/tbs_engine/transform.py:~L3335-3344` | `_sma50_label_map` closed-pattern site (DSP-004 v1.1 Edit) — template for new `_ema21_label_map` (Edit 2) |
| `layers/tbs_engine/transform.py:~L3365-3374` | `_sma200_label_map` closed-pattern site (DSP-004 v1.1 Edit) — second template for `_ema21_label_map` |
| `layers/tbs_engine/transform.py:~L175-180` | `_LABEL_TIER_MAP` vocabulary entry pattern — template for Edit 3 (`WEEKLY_EMA_21` insertion) |
| `layers/tests/unit/test_dsp004_profile_c_weekly_sma_label.py` | DSP-004 v1.0 test file — structural template for new test file |
| `layers/tests/unit/test_bugr002_hierarchy_partition.py` | BUGR-002 partition mechanism reference — for `TestDSP004OBS2OverheadLevelsPartition` test class |
| `layers/tests/unit/test_pa001_phase3_hierarchies.py` | TEST-HRN-001 safe-pattern reference |
| `docs/specs/BUGR006_Label_Fidelity_Bundle_Spec_v1_0.md` | BUGR-006 v2.0 closed parent — reference for BRK-001 §8.1 fallback semantics context (compute.py:807/817/853 emission forms) |

### 10.2 Engine-source anchors for verification

| Path | Purpose |
|---|---|
| `layers/tbs_engine/compute.py:~L765, ~L807, ~L817, ~L853` | The four compute.py BRK MM-null emission forms enumerated in spec §4.4 — implementer's reference for the guard widening substring choice |
| `layers/tbs_engine/output.py:~L2034-2080` | Full BRK-active branch context for Edit 4 — reference (not modified beyond L2064-2066) |
| `layers/tbs_engine/output.py:~L2840-2885` | Full extension_anchor write block context for Edit 1 — reference (only L2873-2875 modified) |
| `layers/tbs_engine/transform.py:~L3290-3310` | EMA 21 anchor entry context — reference for Edit 2 |

### 10.3 Governance / process references

| Path | Purpose |
|---|---|
| `TBS_Amendment_Control_Process_v1_3.md` §6.5 | Hand-Back canonical 10-section template (Phase 2 close deliverable structure) |
| `TBS_Analyst_Session_Integrity_Rules.md` §1.5 | Document Location Policy (specs / briefs / hand-backs three-way split) |
| `TBS_Analyst_Session_Integrity_Rules.md` §9 | Pre-Delivery Verification Checklist (Hand-Back §7 source) |
| `TBS_Analyst_Session_Integrity_Rules.md` §11.6 | Analyst Pre-Spec-Delivery Source Audit Checklist (mirror of this Brief's §4) |

---

## §11. Estimated Effort

**Operator awareness only — not binding on the implementer.** The implementer's actual effort governs the session.

| Phase | Estimate |
|---|---|
| §4 Pre-Implementation Verification (8 sub-checks) | ~10 min |
| 4 edits (small, all spec-prescribed shapes) | ~10-15 min |
| New test file authoring (~30 tests across 7 classes; structural template available from `test_dsp004_profile_c_weekly_sma_label.py`) | ~20-30 min |
| Full pytest run + differential FAIL-pre / PASS-post evidence capture | ~5-10 min |
| §7 Pre-Delivery Verification + Hand-Back authoring (ACP §6.5 10-section) | ~10-15 min |
| **Total session** | **~55-80 min** (well under 2 hours for an experienced Claude Code implementer) |

Per ACP §11 effort transparency convention: this is the Analyst's expectation, not a deadline. Quality and contract compliance take precedence over speed.

---

## Closing — Sign-Off

| Field | Value |
|---|---|
| Authoring Analyst | Project-chat Analyst, post-S168 Phase 1 spec-authoring session |
| Spec authority | `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md` v1.0 (canonical contract — spec wins on all conflicts) |
| Operator decisions consumed at Phase 1 | DQ-1 through DQ-8 per spec §2 Design Lock |
| Expected working-tree branch | `tier1r-display-hygiene-bundle` (off `roescha/TBS_Master_App@master`) |
| Brief authored at | Phase 1 close, post-spec lock, this Project-chat session |
| Brief consumed at | Phase 2 entry — next Claude Code CLI session |
| Brief frozen | YES — divergence from this Brief during implementation surfaces via Hand-Back §6 Process Deviation per ACP §6.5; do NOT amend the Brief mid-implementation |

---

**End of Brief.**

# ITS-001 v1.1.1 — Claude Code CLI Implementation Brief v1.0

**Authoring lifecycle stamp:** S167 close (2026-05-27). Authored by Project-chat Analyst per ACP §6.4 canonical 11-section template (anchor: `RLC001_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0 S160). Single Brief covering both v1.1.1 findings (`ITS-001-BUG-1` desc-string accuracy + `ITS-001-BUG-2` label-match annotation gap) per Operator decision Option 1 at S167 — combined engine fix in a single working-tree commit set BEFORE Phase 4 6-doc DIA cascade.

**Track:** SIR §11.3 Bug-Fix Fast-Path (per ACP §7.1 decision tree first branch — bug fix → fast-path). Phase 4 DIA cascade is independently pending for the v1.1 amendment cycle and absorbs the narrative spec amendments (§3.4 partition placement codification + §4.7.3 mode=None desc branch documentation + §11 item-3 augmentation note); v1.1.1 engine fixes ride along into the existing cascade.

**Spec authority:** `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 at master (S166-locked, Phase 2 v1.1 IMPLEMENTED). v1.1.1 is engine-code only — no spec amendment in this cycle.

---

## §1. Mission

Apply two cosmetic engine fixes to `tbs_engine/output.py::_assemble_intraday_tactical` in a single working-tree commit set:
1. **BUG-1** — branch `near_term_target.primary.desc` + `.secondary.desc` emission by `nt_mode is None` vs `nt_mode == "WITHIN"` on the `NOT_APPLICABLE` source-label path. Eliminate the incorrect `"(WITHIN shelf)"` wording on the no-shelf path.
2. **BUG-2** — extend the per-field `lookback_stale: true` label-match annotation loop to cover `trade_setup.target.cleared_levels[]` and `trade_setup.stop.overhead_levels[]`. Align the engine with Spec §2.1 explicit label-match principle + §3.4 AVWAP_10BAR partition-sibling precedent.

**Conflict resolution rule.** The spec is authority. This Brief is procedural scaffolding only. Wherever this Brief differs from `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1, the spec wins — surface the conflict via halt-and-flag (§9) rather than silently reconciling.

---

## §2. Operational Context (CLI Venue)

The Claude Code CLI implementer operates with:

- **Direct working-tree access** to `roescha/TBS_Master_App` local clone. No uploads required. No Operator paste of file contents into the chat.
- **Local pytest execution** via the project's pre-approved `.claude/settings.json` baseline (per SIR §1.5.6) — pytest invocations auto-approve under `permissions.defaultMode: "acceptEdits"`.
- **Local git context** — full commit history, blame, branch, diff available. Brief §4 Pre-Implementation Verification reads the engine source directly via `view` / `grep`, not via web_fetch.
- **In-session Hand-Back delivery** at end of Phase 2 per ACP §6.5 canonical 10-section template (not chat-paste, not file-upload — written into the working tree and surfaced inline).
- **Branch expectation** — Operator will provide branch name at session entry. Default expectation if not specified: a feature branch off `master` named `its001-v1-1-1-cosmetic-single-pass` or similar; commit set is single (combined BUG-1 + BUG-2) per Operator decision Option 1.

Implementer is NOT operating in a fresh chat without context. The spec and the prior v1.1 Hand-Back are available in the working tree (`docs/specs/`, `docs/handbacks/`). The Bug Register lives on the Project-chat Analyst side (`/mnt/project/`) and is NOT in the working tree — this Brief embeds the canonical defect mechanisms and resolution paths inline; no Bug Register read is required for the implementer's scope.

---

## §3. Phase Boundaries + Vocabulary Constraints

### Phase 2 scope (in-scope work for this CLI session)

- **Engine code edits** in `tbs_engine/output.py` only (one file).
- **Test edits** in `layers/tests/unit/test_its001_intraday_tactical.py` only (extend existing v1.1 test file per DQ-INT-2 precedent — no new test file).
- **Local pytest** of the full cohort + ITS-001 test class to verify zero regression.
- **Hand-Back authoring** per ACP §6.5 — delivered in-session before commit/push.

### Phase 2 scope (out-of-scope — DO NOT TOUCH this session)

- ❌ **Spec amendments.** No edits to `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md`. Narrative amendments fold into Phase 4 DIA cascade in a separate Project chat session — NOT this CLI session.
- ❌ **Living-document edits.** No edits to Doc 2 / Doc 7 / Doc 8 / EEM / README / PEO / SIR / ACP. All Phase 4 DIA scope.
- ❌ **Bug Register edits.** The `TBS_Bug_Register.md` row updates (advancing both sub-entries to ✅ CLOSED + master row to 🟢 SYNCED) happen at Phase 4 close in the Project-chat session that performs the DIA cascade — NOT this CLI session.
- ❌ **Other engine modules.** No edits to `compute.py` / `transform.py` / `gates.py` / `types.py` / `main.py` / `helpers.py` / `trigger.py` / `exit.py` / `data.py` / `charts.py`. Track 2 admissibility forfeits on third-file touch per SIR §11.2 — escape hatch triggers if scope creep is unavoidable (see §9 Failure-Mode Protocol).
- ❌ **Test file scope expansion.** No new test files. No edits to other test files. Single existing test file extension per v1.1 cohort-cohesion precedent.

### Phase 2 vocabulary (in-phase lexicon)

| In-phase | Meaning |
|---|---|
| `nt_mode` | Local variable holding `near_term_target.mode` value (`"WITHIN"` / `None` per the NOT_APPLICABLE source-label branch) |
| `cleared_levels` | Post-partition list of EXCEEDED target labels (sibling to active `target.hierarchy[]`) |
| `overhead_levels` | Post-partition list of stop labels above current price (sibling to active `stop.hierarchy[]`) |
| `lookback_stale` | Boolean annotation flag emitted per-field on the four partition sites |
| `label-match` | The Spec §2.1 principle — annotation attaches by label identity, not container path |
| `partition-sibling` | Post-partition placement variants of the same label across the four sites (Spec §3.4 AVWAP_10BAR convention generalized to DAILY_HIGH per BUG-2 mechanism) |
| `_assemble_intraday_tactical` | The output.py function holding the two emission sites |
| `cosmetic single-pass` | The v1.1.1 cycle classification — engine-only, no spec, no DIA, no behavior change |
| `regression test class` | TestITS001LookbackStaleAnnotation (extended) + new no-shelf-desc test class |

### Out-of-phase vocabulary (drift signals — DO NOT use)

If the implementer reaches for any of these words, STOP and re-read this §3:

| Out-of-phase | Reason |
|---|---|
| `v1.2` / `v2.0` / "next spec cycle" | This is v1.1.1 (sub-amendment within v1.1 cycle), NOT a new spec cycle |
| `INVALID` / `REJECT` / `verdict change` | v1.1.1 is cosmetic — zero verdict impact, zero gate impact |
| `Phase 3` / `live validation` / `cohort run` | Phase 3 closed at S167 with §7 #5 + #6 satisfied; v1.1.1 is post-Phase-3 engine touch |
| `Phase 4` / `DIA cascade` / "Doc 2 update" / "EEM update" | Phase 4 is the SUBSEQUENT Project-chat session, not this CLI session |
| `spec amendment` / `§3.4 amendment` / `§4.7.3 amendment` | Narrative amendments are Phase 4 scope; engine fix here does NOT require spec edit |
| `compute.py` / `transform.py` / `gates.py` / `types.py` / `main.py` | Out-of-file scope — output.py only |
| `new test file` / `new test module` | Single existing file extension per cohort-cohesion DQ-INT-2 |

---

## §4. Pre-Implementation Verification

**MANDATORY before any code edit.** This is the implementation-side defense layer mirroring SIR §11.6 Analyst Pre-Spec-Delivery Source Audit Checklist (Brief §4 vs SIR §11.6 = two-layer defense per §11.8). The §11.6 audit was conducted at Phase 1 v1.1 spec lock-in (S166); the items below are the §11.6 items applicable to the v1.1.1 fix scope, re-executed by the implementer against current engine source.

Each item below requires source-pattern-matching with **`file:line` evidence anchors** before any edit. Document the verification in Hand-Back §4 per ACP §6.5.

### Item 4.1 — Locate the `_assemble_intraday_tactical` function (both findings)

- `grep -n "def _assemble_intraday_tactical" layers/tbs_engine/output.py` to locate function start.
- Record `file:line` anchor for the function header.
- Verify the function exists at single canonical site (no duplicates).

### Item 4.2 — BUG-1: Locate the near_term_target desc emission sites

- `grep -n "near_term_target\|nt_mode\|NOT_APPLICABLE" layers/tbs_engine/output.py` to locate the primary + secondary desc emission f-strings.
- Identify the variable name holding the `near_term_target.mode` value (Brief assumes `nt_mode` per task spec; verify in-source naming).
- Record `file:line` anchor for `primary.desc` emission site.
- Record `file:line` anchor for `secondary.desc` emission site.
- Verify both currently emit the same `"(WITHIN shelf)"` parenthetical regardless of `nt_mode` value on the NOT_APPLICABLE branch (the defect mechanism).

### Item 4.3 — BUG-1: Verify §2.9.6 entry_zone no-shelf desc convention is the parallel-structure reference

- Open `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` §2.9.6 (entry_zone no-shelf convention).
- Confirm the no-shelf desc convention text used by entry_zone — this is the template to mirror in the v1.1.1 fix.
- The mode=None branch emits: `"No qualifying compression shelf -- near-term target not applicable. tactical_stop emits atr_volatility only."` (Brief §5 specifies the canonical text). Verify this text aligns with §2.9.6's parallel structure.

### Item 4.4 — BUG-2: Locate the per-field label-match annotation loop

- `grep -n "lookback_stale\|cleared_levels\|overhead_levels" layers/tbs_engine/output.py` to locate the per-field annotation site.
- Record `file:line` anchor for the existing annotation loop (currently scanning `stop.hierarchy[]` + `target.hierarchy[]` only).
- Identify the data structure carrying the labels (dict identity vs string-name comparison) — this determines whether the fix is a loop extension or a helper refactor.

### Item 4.5 — BUG-2: §11.6 ITEM 1 — Call-order verification (annotation loop runs AFTER partition)

- Verify the partition site (where labels get assigned to `hierarchy[]` / `cleared_levels[]` / `overhead_levels[]`) executes BEFORE the per-field label-match annotation loop. Annotation depends on partition completion.
- Record `file:line` for partition site + `file:line` for annotation site.
- Confirm linear ordering (partition write → annotation read).

### Item 4.6 — BUG-2: §11.6 ITEM 3 — Shared-reference / partition-leak audit

- **This is the §11.6 audit-class item from which BUG-2 surfaced.** It is the 9th confirmed instance of the SIR §11.6 ITEM 3 pattern (joins the 8-instance ANALYST-class cluster that closed retroactively at GOV-003 codification S162).
- Verify the four partition sites (`stop.hierarchy[]` / `stop.overhead_levels[]` / `target.hierarchy[]` / `target.cleared_levels[]`) carry labels that can be matched by **string-name** identity (not dict identity / shared reference).
- Confirm that extending the loop to include `cleared_levels[]` + `overhead_levels[]` will NOT cause double-annotation on the same dict (e.g., if BUGR-002 shallow list comprehensions create shared dict references across partitions — this was the precedent shared-reference surface).
- If dict-identity sharing is detected, the fix mechanism shifts from "extend loop scan" to "label-match by name across all four sites" — record this finding in Hand-Back §4 with the resolution path.

### Item 4.7 — BUG-2: §11.6 ITEM 4 — Pipeline-order feasibility check

- Per Spec §2.4.4 v1.1 path correction, `lookback_status.affected_fields` summary block enumerates paths including `target.cleared_levels[DAILY_HIGH]`. Verify the engine already computes the affected-fields summary correctly (this was confirmed in Phase 3 SIDU LIVE evidence at S167) — the defect is strictly per-field annotation, not summary computation.
- Confirm per-field annotation site runs AFTER stale detection (so `lookback_stale: true` boolean is available).

### Item 4.8 — BUG-2: §11.6 ITEM 8 — Downstream-override-path audit

- `grep -n "lookback_stale" layers/tbs_engine/*.py` across all engine modules.
- Verify no downstream consumer (transform.py / scanner.py / orchestrator.py) rewrites or clears `lookback_stale: true` after annotation site emits it.
- If override paths exist, document them — the fix may need to extend to those sites for full effectiveness, OR confirm they only operate on the active hierarchy[] (not cleared/overhead) and thus aren't affected.

### Item 4.9 — Verdict-invariance preflight (both findings)

- Both fixes are cosmetic — zero verdict impact, zero gate impact.
- Confirm no gate function reads `near_term_target.primary.desc` / `.secondary.desc` (string content).
- Confirm no gate function reads `target.cleared_levels[N].lookback_stale` (annotation flag content).
- A `grep -n "near_term_target\|cleared_levels\|overhead_levels" layers/tbs_engine/gates.py` should return zero matches. Verify.

### Verification halt rule

If ANY item above surfaces a defect that contradicts this Brief's stated mechanism (e.g., dict-identity sharing makes the BUG-2 fix non-trivial; or `gates.py` does read these fields), **STOP and surface per §9 Failure-Mode Protocol**. Do NOT silently adapt the fix. Do NOT commit on halt.

---

## §5. Implementation Scope (Working-Tree Edits)

### Files in scope (this CLI session)

| File | Edit scope |
|---|---|
| `layers/tbs_engine/output.py` | Single function `_assemble_intraday_tactical` — two edits per BUG-1 (primary + secondary desc branches) + one or more edits per BUG-2 (extend label-match loop scope) |
| `layers/tests/unit/test_its001_intraday_tactical.py` | Extend existing `TestITS001LookbackStaleAnnotation` class for BUG-2 + add new test class (or extend existing class) for BUG-1 no-shelf desc |

### Files explicitly out of scope (this CLI session — forbidden)

- All other engine modules: `compute.py` / `transform.py` / `gates.py` / `types.py` / `main.py` / `helpers.py` / `trigger.py` / `exit.py` / `data.py` / `charts.py`
- All downstream consumers: `tbs_orchestrator.py` / `tbs_scanner.py`
- All other test files
- All spec / brief / hand-back / living docs

### Third-file diff-stat halt rule

Per SIR §11.2 escape hatch, if implementation surfaces a need to touch a third file beyond `output.py` + the existing test file, **STOP and surface per §9 Failure-Mode Protocol**. Track 2/§11.3 admissibility is forfeited on third-file touch — return to Project chat for re-scoping.

### Per-file edit anchors

#### output.py edits — BUG-1 (desc branch)

Locate `_assemble_intraday_tactical` near_term_target.primary.desc + .secondary.desc emission on the `NOT_APPLICABLE` source-label path. Add an inline branch on `nt_mode`:

- If `nt_mode == "WITHIN"`: emit the existing v1.1 text (preserve "directionally neutral (WITHIN shelf)" wording — correct on the WITHIN-applicable=false path).
- If `nt_mode is None`: emit the no-shelf-appropriate text mirroring Spec §2.9.6 entry_zone no-shelf convention. **Canonical text (this Brief is authority for the new desc string):** `"No qualifying compression shelf -- near-term target not applicable. tactical_stop emits atr_volatility only."` (primary desc). Secondary desc parallel-structure: `"No qualifying compression shelf -- secondary target not applicable."` (or implementer-chosen parallel-structure variant — surface in Hand-Back §3 with rationale).

Two edits expected (primary + secondary). One if-branch per emission site.

#### output.py edits — BUG-2 (label-match annotation extension)

Locate the per-field `lookback_stale` annotation loop. Extend the partition-site scan to cover all four post-partition sites:

- `trade_setup.stop.hierarchy[]` (already covered)
- `trade_setup.stop.overhead_levels[]` (NEW — AVWAP_10BAR can land here per §3.4 precedent)
- `trade_setup.target.hierarchy[]` (already covered)
- `trade_setup.target.cleared_levels[]` (NEW — DAILY_HIGH can land here per BUG-2 mechanism)

Implementation choice (implementer discretion, surface in Hand-Back §3):
- **Option A** — extend the existing loop iteration to include the two additional partition sites.
- **Option B** — refactor to a single helper that takes a list-of-partition-sites parameter and iterates all four.
- **Option C** — label-match by name across a flattened union of all four sites.

Option B is the natural label-match implementation per Spec §2.1 principle ("annotated by label-match, not by container-path"). Implementer chooses based on existing-code idiom.

One conceptual edit (extend loop scope). LOC-count expected ≤30 net.

#### test file edits — BUG-1 (new no-shelf desc class)

Add new test class (e.g., `TestITS001NoShelfDescAccuracy`) OR extend an existing class with no-shelf desc tests. Tests verify:
- `nt_mode is None` + `source: NOT_APPLICABLE` emits the new no-shelf desc text on `primary.desc` and `secondary.desc`.
- `nt_mode == "WITHIN"` + `applicable: false` + `source: NOT_APPLICABLE` STILL emits the v1.1 "(WITHIN shelf)" text on `primary.desc` and `secondary.desc` (regression-protect the correct WITHIN-applicable=false branch).

Minimum 2 new tests (one per branch). 4-6 tests recommended for coverage including primary/secondary symmetry.

#### test file edits — BUG-2 (extend TestITS001LookbackStaleAnnotation)

Extend `TestITS001LookbackStaleAnnotation` to verify per-field annotation on all four partition sites:

- DAILY_HIGH in `target.cleared_levels[]` with stale lookback → `lookback_stale: true` annotation present (NEW test — was the defect surface).
- AVWAP_10BAR in `stop.overhead_levels[]` with stale lookback → `lookback_stale: true` annotation present (NEW test — parallel mechanism per §3.4 precedent).
- ESTABLISHED_LOW + DAILY_HIGH in active hierarchy[] → existing v1.1 tests preserved (regression-protect).
- Summary block `affected_fields` enumeration is unchanged (Spec §2.4.4 v1.1 path correction already correct per SIDU LIVE evidence).

Minimum 2 new tests (cleared_levels + overhead_levels). 4-6 tests recommended for both label sets across both partition sites.

---

## §6. Test Mandate

### Test file location

`layers/tests/unit/test_its001_intraday_tactical.py` (existing v1.1 file — extend, do NOT create new file). Cohort cohesion preserved per v1.1 DQ-INT-2 precedent.

### Regression cohort definition

- **Full cohort:** all unit tests across `layers/tests/unit/` (target: 3205 passed / 4 skipped / 1 failed pre-existing CWD-sensitive baseline per v1.1 Hand-Back §6.2).
- **ITS-001 class subset:** `test_its001_intraday_tactical.py` (107 tests post-v1.1 per Hand-Back §5).
- **Post-v1.1.1 cohort target:** 3205 + (new BUG-1 tests) + (new BUG-2 tests) passed / 4 skipped / 1 failed pre-existing. Zero NEW failures.

### Local pytest invocation

```bash
# Full cohort regression
cd layers && pytest tests/unit/ -v --tb=short

# ITS-001 class only (fast iteration during dev)
cd layers && pytest tests/unit/test_its001_intraday_tactical.py -v

# Specific new test class (after authoring)
cd layers && pytest tests/unit/test_its001_intraday_tactical.py::TestITS001NoShelfDescAccuracy -v
cd layers && pytest tests/unit/test_its001_intraday_tactical.py::TestITS001LookbackStaleAnnotation -v
```

Pre-approved per `.claude/settings.json` baseline (SIR §1.5.6) — `permissions.defaultMode: "acceptEdits"` auto-approves pytest invocations.

### TEST-HRN-001 idempotent pattern awareness

Tests must be idempotent and re-runnable. Fixture state must NOT leak across tests. If fixture reuse is appropriate (e.g., shared `nt_mode=None` setup), use the existing v1.1 fixture pattern (parametrize or class-level setup). Avoid global state mutation.

### Verdict-invariance assertion

Per Spec §6 v1.1 test plan: `TestBundleITS001VerdictInvariance` class (existing) MUST continue to pass unchanged. The cosmetic fixes do NOT alter any verdict — verify by running the verdict-invariance test class as part of the regression cohort.

```bash
cd layers && pytest tests/unit/test_its001_intraday_tactical.py -k "VerdictInvariance" -v
```

### NotInGatesFile assertion

`TestITS001NotInGatesFile` (existing) verifies no ITS-001 token appears in `gates.py` (proving zero gate impact). The v1.1 implementation added `entry_zone` to this scan per Hand-Back §6.3; v1.1.1 introduces no new tokens, so this test should pass unchanged. Verify.

---

## §7. Pre-Delivery Verification

**MANDATORY before Hand-Back delivery.** Per SIR §9 Pre-Delivery Verification Checklist:

- [ ] **Content accuracy:** Both fixes match the resolution mechanisms specified in Brief §5 (per-file edit anchors). The Brief is the canonical record for the v1.1.1 fix mechanism; the spec is authority for the underlying behavioral contracts (§2.1 label-match, §2.9.6 no-shelf parallel structure, §3.4 partition-sibling precedent, §4.7.3 emission templates). Re-read Brief §5 + the cited spec sections; do NOT rely on memory.
- [ ] **Internal consistency:** No contradictions between BUG-1 fix and BUG-2 fix in the commit set. Both touch `_assemble_intraday_tactical` but at different sites; no logical interaction.
- [ ] **Format integrity:** Hand-Back delivered as `.md` per SIR §1.3 default. No `.docx` unless Operator requests.
- [ ] **Scope discipline:** Single file (output.py) + single test file. No third-file diff-stat. No spec / living-doc / Bug Register edits in this commit set.
- [ ] **Gate function verification:** `grep -n "near_term_target\|cleared_levels\|overhead_levels" layers/tbs_engine/gates.py` returns ZERO matches. Verify.
- [ ] **Module import verification:** No new imports added to output.py. Verify import graph acyclicity per SIR §9 module-import requirement.
- [ ] **Bug Register update note:** Bug Register edits are Phase 4 scope — NOT this CLI session. Hand-Back §9 (Open Items for the Analyst) flags that both sub-entries advance to ✅ CLOSED at Phase 4 close.
- [ ] **DIA current:** N/A — DIA cascade is Phase 4 scope. v1.1.1 itself triggers no new DIA (fix RESTORES documented behavior).

### Spec §11 Pre-Implementation Checklist annotation (cross-reference to Hand-Back §4)

For each §11.6 item enumerated in Brief §4 (Items 4.1 – 4.9), Hand-Back §4 must annotate PASS / RESOLVED / FAIL with `file:line` evidence anchor. Failures discovered during Pre-Implementation Verification are documented with their resolution path.

---

## §8. Hand-Back Contract

Per ACP §6.5, Phase 2 close delivers a Hand-Back conforming to the canonical 10-section template. Reference ACP §6.5 directly for field list — this Brief does NOT restate it.

**Suggested file naming:** `docs/handbacks/ITS001_v1_1_1_Phase2_Implementation_HandBack_v1_0.md` (mirrors precedent `ITS001_v1_1_Phase2_Implementation_HandBack_v1_0.md`).

**Lifecycle stamp:** v1.1.1 cosmetic single-pass per Operator decision Option 1 at S167. Phase 2 close → Bug Register sub-entries ready for ✅ CLOSED at Phase 4. Master row ITS-001 advances 🟡 → 🟢 SYNCED at Phase 4 close.

**Operator smoke-check expectation (Hand-Back §8 Live-Sampling Confidence Notes):** Operator may opt to re-run SIDU + QUCY + FROG + AU LIVE engine traces post-commit to verify:
- SIDU: no-shelf desc text now reads correctly (BUG-1 fix witness).
- QUCY: WITHIN-applicable=false desc text still reads "(WITHIN shelf)" correctly (BUG-1 regression-protect).
- SIDU: `target.cleared_levels[DAILY_HIGH]` carries `lookback_stale: true` annotation (BUG-2 fix witness).
- AVWAP_10BAR-in-overhead_levels witness if available across cohort (BUG-2 parallel-mechanism verification).

Live smoke results are admissible at Hand-Back §8 but not blocking — Phase 3 cohort already closed at S167 with §7 #5 + #6 satisfied; v1.1.1 smoke is negative-path-only confirmation.

---

## §9. Failure-Mode Protocol

### Halt-and-surface triggers (in-session)

If ANY of the following surface during Phase 2, **STOP immediately**, surface the finding inline to the Operator, do NOT commit, do NOT push, do NOT amend the spec on your own authority:

1. **Pre-Implementation Verification (§4) FAILURE** — any item 4.1–4.9 surfaces a defect that contradicts this Brief's stated mechanism. Surface the finding + the discovered mechanism. Wait for Operator decision.
2. **Verdict-invariance test FAILURE** — `TestBundleITS001VerdictInvariance` (or other verdict-invariance test) fails. Both fixes are cosmetic; any verdict delta is a defect, not an enhancement. Surface immediately.
3. **NotInGatesFile test FAILURE** — `gates.py` scan reveals a new ITS-001 token introduced by the fix. Cosmetic fixes must not add tokens to `gates.py`. Surface immediately.
4. **Positive-only test passing on negative path** — e.g., a no-shelf desc test passes when fed a WITHIN-applicable=false fixture (or vice versa). Surface the test-fixture-mismatch, do NOT silently re-spec the test.
5. **Third-file diff-stat** — implementation surfaces a need to touch a third file beyond `output.py` + `test_its001_intraday_tactical.py`. SIR §11.2 escape hatch / §11.3 fast-path scope violated. Surface immediately for re-scoping.
6. **Spec ambiguity** — Spec §2.1 label-match principle or §3.4 partition-sibling precedent or §4.7.3 NOT_APPLICABLE branch has ambiguous interpretation in light of the fix. Surface the ambiguity, do NOT pick a side unilaterally.
7. **Shared-reference / dict-identity surface (§11.6 ITEM 3 surprise)** — if Item 4.6 surfaces that the four partition sites carry shared dict references (BUGR-002 precedent), the BUG-2 fix mechanism may shift from "extend loop" to "refactor partition site to use label-match-by-name." Surface the discovery; do NOT silently refactor outside the spec'd mechanism.

### No unilateral spec adaptation

The Brief is procedural scaffolding; the Spec is authority. If during Phase 2 the implementer believes a spec section is wrong or ambiguous, the response is to **flag and halt** — not to edit the spec, not to interpret loosely. Spec edits are Phase 4 Project-chat work.

### Do not commit on halt

A halt-and-surface event MUST NOT result in a commit. Working-tree state is preserved as evidence; uncommitted changes remain in the working tree for Operator inspection. The halt is the surface — Hand-Back is deferred until the halt is resolved (in-session if possible, or via a Project-chat round-trip if not).

---

## §10. Sibling-Spec Pattern References (Read-Only Anchors)

### Spec authority anchors

- `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` — Spec authority for v1.1.1 fix scope.
  - **§2.1** — Label-match annotation principle (BUG-2 authority).
  - **§2.4.4** — `lookback_status.affected_fields` v1.1 path correction (BUG-2 summary-block reference — already correct in engine, defect is per-field).
  - **§2.9.6** — entry_zone no-shelf desc convention (BUG-1 parallel-structure reference).
  - **§3.4** — Hierarchy-label alignment table + AVWAP_10BAR partition-sibling precedent (BUG-2 generalization authority).
  - **§4.7.3** — Output assembly normative templates including NOT_APPLICABLE source-label branch (BUG-1 emission authority).
  - **§11** — Pre-Implementation Checklist 8-item baseline (Brief §4 mirrors).

### Hand-Back precedent anchor

- `docs/handbacks/ITS001_v1_1_Phase2_Implementation_HandBack_v1_0.md` v1.0 — Phase 2 v1.1 implementation record. Reference for:
  - Cohort baseline (3205 passed / 4 skipped / 1 failed) → v1.1.1 target ≥ 3205 + new tests.
  - Test file scope (single file extension precedent per DQ-INT-2).
  - ASCII-emission convention per Hand-Back §6.4 — v1.1.1 new desc strings must use ASCII (`--` not em-dash, `-` not en-dash, `x` not multiply sign).
  - Implementation latitude conventions per Hand-Back §6.3.

### Brief precedent anchor

- `docs/briefs/ITS001_v1_1_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0 — Phase 2 v1.1 entry artifact. Format precedent for this Brief.

### Canonical record for the v1.1.1 fix mechanism

The defect mechanisms, resolution paths, and severity classifications for both findings were authored into the Project-side Bug Register at S167 by the Project-chat Analyst. The Bug Register itself lives at `/mnt/project/TBS_Bug_Register.md` (Analyst-side living document per SIR §1.5.1) and is **NOT accessible from the working tree**. For the implementer's scope, the canonical record is:

- **This Brief** — §5 specifies the per-file edit anchors and the canonical new desc text for BUG-1 (mode=None branch); §4 enumerates the §11.6 verification items for BUG-2 including the shared-reference audit specific to the partition-sibling generalization.
- **The Spec** — `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 is authority for §2.1 (label-match principle), §2.9.6 (no-shelf parallel structure), §3.4 (AVWAP_10BAR partition-sibling precedent), §4.7.3 (NOT_APPLICABLE source-label emission templates), §11 (Pre-Implementation Checklist).
- **The prior v1.1 Hand-Back** — `docs/handbacks/ITS001_v1_1_Phase2_Implementation_HandBack_v1_0.md` v1.0 for cohort baseline + ASCII emission convention + implementation-latitude precedent.

If an ambiguity surfaces during implementation that the Brief + spec + prior Hand-Back together do not resolve, halt and surface per §9 — do NOT silently interpret. The Operator will return Bug Register canonical detail to the Project chat session as needed for resolution.

**Brief-spec conflict resolution:** Wherever this Brief paraphrases the spec, the spec wins. Re-read the cited spec section at any ambiguity.

### Engine-source pre-authorized URLs (per SIR §1.5.5)

Implementer operates against the local working tree, not URL fetches. URLs are listed here only for reference if a side-by-side check against `master` is needed (e.g., to verify the implementer's branch is current with master):

- `https://github.com/roescha/TBS_Master_App/blob/master/layers/tbs_engine/output.py`
- `https://github.com/roescha/TBS_Master_App/tree/master/layers/tests/unit`

---

## §11. Estimated Effort

**For Operator awareness only — not binding on the implementer.**

### Code edits

| Edit | Site | Expected LOC delta | Difficulty |
|---|---|---|---|
| BUG-1 primary desc branch | `_assemble_intraday_tactical` near_term_target.primary.desc emission | ~5-8 LOC (one if-branch) | Trivial |
| BUG-1 secondary desc branch | `_assemble_intraday_tactical` near_term_target.secondary.desc emission | ~5-8 LOC (one if-branch) | Trivial |
| BUG-2 label-match loop extension | per-field `lookback_stale` annotation loop | ~10-30 LOC (depending on Option A/B/C choice) | Low |
| **output.py total** | | **~20-45 LOC net additive** | |

### Test edits

| Edit | Class | Expected tests | Expected LOC delta |
|---|---|---|---|
| BUG-1 no-shelf desc tests | New class `TestITS001NoShelfDescAccuracy` (or extension) | 4-6 tests | ~80-150 LOC |
| BUG-2 cleared_levels + overhead_levels annotation tests | Extend `TestITS001LookbackStaleAnnotation` | 4-6 tests | ~80-150 LOC |
| **test file total** | | **8-12 new tests** | **~160-300 LOC** |

### Time estimate

- Pre-Implementation Verification (§4): 15-30 min (9 items, `grep`-based; quick verification on a known-well-mapped file).
- BUG-1 + BUG-2 code edits: 30-60 min combined.
- Test authoring: 60-90 min (8-12 tests across two test classes).
- Local pytest cohort run + iteration: 30-45 min (multiple iterations expected on fixture wiring).
- Hand-Back authoring (ACP §6.5 canonical 10-section): 30-45 min.
- **Total estimated effort: 2.5 – 4.5 hours single-pass.**

Implementer is welcome to deviate from these estimates — surface in Hand-Back §1 if scope or time materially exceeds expectations (especially if Item 4.6 surfaces shared-reference / dict-identity surprises that shift the BUG-2 mechanism).

### Out-of-band scope flags

- If BUG-1 or BUG-2 surfaces a new defect during implementation (e.g., a third no-shelf-path emission site outside near_term_target; or a fourth partition site beyond the four enumerated), surface immediately per §9. Do NOT silently expand scope.
- If the §11.6 ITEM 3 audit (Item 4.6) reveals dict-identity sharing across partition sites, the fix may require a partition-site refactor that exceeds output.py scope. Surface immediately per §9 — this triggers SIR §11.2 escape hatch and returns to Project chat for re-scoping.

---

## Closing — Sign-off

**Authoring Analyst:** Project-chat Analyst, S167 close (2026-05-27).

**Spec authority:** `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 at master (S166 Phase 2 v1.1 IMPLEMENTED; Phase 3 §7 #5 + #6 closed S167; Phase 4 pending v1.1.1 + DIA cascade).

**Operator decision points consumed at Phase 1:**
- S167 Operator decision Option 1 — combined engine fix in a single working-tree commit set BEFORE the Phase 4 6-doc DIA cascade.
- S167 Operator policy override — Phase 0 Handoff Memo §8 directive ("no new ITS sub-entries during v1.1 cycle") scoped to v1.1 amendment items; Phase 3 net-new findings outside that scope. Both findings logged as `ITS-001-BUG-1` and `ITS-001-BUG-2` sub-entries.

**Track:** SIR §11.3 Bug-Fix Fast-Path (per ACP §7.1 decision tree first branch).

**Working-tree branch expectation:** Operator provides at session entry. Default suggestion: `its001-v1-1-1-cosmetic-single-pass` off `master`. Single combined commit set per Operator decision Option 1.

**Phase 2 close path:**
1. Implementer Phase 2 → Hand-Back authored in-session per ACP §6.5.
2. Operator commits + pushes (output.py + test file + Hand-Back per ACP §1.5.3 transit pattern).
3. Phase 3 smoke (optional, per Hand-Back §8).
4. **Fresh Project chat** for Phase 4 6-doc DIA cascade per SIR §6 context budget — Doc 2 §VI/§IV substantive (entry_zone schema + rename + desc convention + no-shelf desc + §3.4 partition placement); Doc 8 §II Layer 2 mirror; Doc 7 Step 6 substantive; EEM verify-only; README + PEO Tier closure; Bug Register: `ITS-001-BUG-1` + `ITS-001-BUG-2` ✅ CLOSED, master row 🟢 SYNCED → ✅ CLOSED.

**End of Brief.**

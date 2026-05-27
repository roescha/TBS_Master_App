# ITS-001 v1.1.1 - Phase 2 Implementation Hand-Back (S167)

**Spec authority:** `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 (S166-locked; v1.1.1 is engine-code only, no spec amendment)
**Brief authority:** `ITS001_v1_1_1_Claude_Code_CLI_Implementation_Brief_v1_0.md` v1.0
**Implementer:** Claude Code CLI (Opus 4.7, 1M context), working tree `roescha/TBS_Master_App`, branch `its001-v1-1-1-cosmetic-single-pass` off `master`@`fe63016`
**Hand-back date:** 2026-05-27 (delivered in-session per Brief §8)
**Status request:** `ITS-001-BUG-1` ready for **YELLOW IMPLEMENTED** at Phase 4 close. `ITS-001-BUG-2` **DE-SCOPED** from v1.1.1 by Operator decision (see §6.1) -- returns to Project chat for re-classification.

> ASCII note: this document and the new engine `desc` strings use ASCII punctuation (`--`, `-`, `x`) per the v1.1 Hand-Back §6.4 emission convention.

---

## Section 1. Outcome Summary

v1.1.1 entered as a **combined two-finding cosmetic single-pass** (`ITS-001-BUG-1` desc accuracy + `ITS-001-BUG-2` lookback_stale annotation gap). During the **mandatory Brief §4 Pre-Implementation Verification, before any code edit**, BUG-2 surfaced a defect contradicting the Brief's stated fix mechanism on two independent grounds (mechanism mislocation + spec contradiction). The implementer **halted and surfaced** per Brief §9 (triggers #1, #5, #6); the Operator **endorsed the halt and de-scoped BUG-2**. v1.1.1 narrowed to **BUG-1 only**.

- **BUG-1 implemented to Brief §5.** One branch on `nt_mode` in `_assemble_intraday_tactical` (output.py:987) splits the `near_term_target` `NOT_APPLICABLE` fallback `desc` between the no-shelf path (`nt_mode is None`) and the WITHIN-applicable=false path (`nt_mode == "WITHIN"`). The incorrect `"(WITHIN shelf)"` wording on the no-shelf path is eliminated.
- **9 new ITS tests pass** (class 31 `TestITS001NoShelfDescAccuracy`). ITS file 107 -> **116 passed**.
- **Zero regressions:** full cohort (from the Brief-prescribed `layers/` CWD) **3215 passed / 4 skipped / 0 failed**. Reconciliation: 3205 prior-passing + 1 previously-CWD-sensitive baseline test (passes from `layers/`) + 9 new = 3215; total collected 3219 = 3210 v1.1 baseline + 9. **Zero NEW failures.**
- Exactly **1 engine file (output.py) + 1 test file** modified. No third-file diff-stat (BUG-2's true fix site, transform.py, was never touched -- the halt held). No gate token added (verdict invariance intact).

The headline process event is the BUG-2 halt + de-scope (§6.1). The two-layer defense (Brief §4 implementation-side audit catching an Analyst-side spec-read lapse) worked as designed per SIR §11.8.

---

## Section 2. Files Touched

```
 layers/tbs_engine/output.py                        |  21 +++-
 layers/tests/unit/test_its001_intraday_tactical.py | 115 +++++++++++++++++++++
 2 files changed, 133 insertions(+), 3 deletions(-)
```

Exactly the BUG-1 in-scope file set (Brief §5). **No transform.py edit** (BUG-2 de-scoped). No spec / living-doc / Bug Register edit.

**Post-edit file SHAs (`git hash-object`):**

| File | SHA |
|---|---|
| `layers/tbs_engine/output.py` | `57216c782e2fbbe8bbc84feb61e6280c1dae593d` |
| `layers/tests/unit/test_its001_intraday_tactical.py` | `d32df17df5d5060151a0aeb081d19f9661d4ac8f` |

**Branch / commit:** `its001-v1-1-1-cosmetic-single-pass` off `master`@`fe63016`; working-tree changes **uncommitted** (preserved for Operator review per Brief §9 + Phase 2 close path step 2).
**Suggested commit / PR title:** `ITS-001 v1.1.1 -- near_term_target no-shelf desc accuracy (BUG-1; cosmetic single-pass)`
**Commit-set note:** the single-combined-commit mandate (Operator Option 1) was scoped to BUG-1 + BUG-2; with BUG-2 de-scoped, the commit set is output.py + test file + this Hand-Back.

---

## Section 3. What Was Built - Per Spec

| Edit | File | Outcome |
|---|---|---|
| **BUG-1** (Brief §5) | output.py (`_assemble_intraday_tactical`, L987-1015) | The `near_term_target` `NOT_APPLICABLE` primary/secondary fallback `desc` is reached on two compute-side paths (compute.py `_compute_intraday_tactical_levels`): `nt_mode == "WITHIN"` (shelf present, directionally neutral, `applicable=false`) and `nt_mode is None` (no shelf detected). v1.0/v1.1 emitted the `"Directionally neutral (WITHIN shelf)"` wording on **both**. The fix computes `nt_na_primary_desc` / `nt_na_secondary_desc` ahead of the block dict, branched on `nt_mode is None` -> no-shelf text; `else` (`== "WITHIN"`) -> preserved v1.1 text. |
| **BUG-1 tests** | test file (class 31 `TestITS001NoShelfDescAccuracy`, 9 tests) | No-shelf branch (mode/applicable, primary text, secondary text, omits "WITHIN shelf", ASCII-only), WITHIN regression-protect (primary + secondary preserve v1.1 wording), cross-path divergence, and applicable-path (ABOVE) guard confirming the enriched desc is untouched. |

**Canonical new desc strings (ASCII, per Brief §5):**
- primary (`nt_mode is None`): `"No qualifying compression shelf -- near-term target not applicable. tactical_stop emits atr_volatility only."`
- secondary (`nt_mode is None`): `"No qualifying compression shelf -- secondary target not applicable."`

**Secondary-desc rationale (Brief §5 invited implementer choice):** parallel structure to the primary -- same `"No qualifying compression shelf --"` opener + `"... secondary target not applicable."`, mirroring the existing shelf.desc (output.py:880) and entry_zone.desc (output.py:1012) no-shelf convention. No `tactical_stop` clause on the secondary (that operative note belongs on the primary only, matching the v1.1 WITHIN primary/secondary asymmetry).

The WITHIN-applicable=false text is preserved **verbatim** from v1.1 (Brief §5: correct on that path).

---

## Section 4. Verification - Brief §4 Pre-Implementation Audit (executed BEFORE any edit)

`file:line` anchors recorded against engine source at session entry. Items 4.4-4.8 were BUG-2 verification items; they are reported here because **Item 4.4 is the halt origin**.

| # | Item | Result |
|---|---|---|
| 4.1 | Locate `_assemble_intraday_tactical` | **PASS** -- single site, `output.py:831`; no duplicates. |
| 4.2 | BUG-1 desc emission sites | **PASS** -- primary fallback `output.py:991`, secondary fallback `output.py:996`; both emitted `"(WITHIN shelf)"` regardless of `nt_mode` (the defect). `nt_mode` = `output.py:971` (`getattr(ctx,'_intraday_near_term_target_mode',None)`). |
| 4.3 | BUG-1 no-shelf parallel-structure reference | **PASS** -- spec §2.9.6 entry_zone no-shelf convention mirrored by engine at `output.py:1012` (entry_zone) + `output.py:880-882` (shelf). Brief §5 canonical text aligns. |
| 4.4 | BUG-2 annotation-loop location | **FAIL (halt origin).** No per-field `lookback_stale` annotation loop exists in output.py. The only `lookback_stale` in output.py is `shelf_lookback_stale` (`output.py:858-875`) -- a different, shelf-level field. The actual per-field loop is in **transform.py:3244-3247** (target/`DAILY_HIGH`) and **transform.py:3551-3555** (stop/`ESTABLISHED_LOW`,`AVWAP_10BAR`). Spec §2.1 implementation map (spec line 873) confirms: *"Transform \| per-field lookback_stale annotation (label-match) \| `transform.py` (v1.0, unchanged)"*. See §6.1. |
| 4.5 | BUG-2 partition-before-annotation order | PASS (in transform.py) -- partition `transform.py:3210/3509` precedes annotation `:3244/:3551`; linear write->read. (Moot post-de-scope.) |
| 4.6 | BUG-2 shared-reference / partition-leak audit | PASS -- partitions are disjoint by price predicate (`> / <=`, `< / >=` list comprehensions over the same source list); no dict-identity sharing between hierarchy and cleared/overhead; no double-annotation risk. The §11.6 ITEM-3 surprise the Brief anticipated did **not** occur; a different surprise did (4.4). (Moot post-de-scope.) |
| 4.7 | BUG-2 affected_fields summary | **Brief misdescription.** Brief Item 4.7 claims the summary enumerates `target.cleared_levels[DAILY_HIGH]`. The engine emits **hierarchy-only** paths (`output.py:895-897`), and spec §2.4.4 (lines 187-194) specifies hierarchy-only paths, *"v1.0 implementation already emitted these paths correctly."* No `cleared_levels`/`overhead_levels` path appears. Reinforces §6.1 Ground 3. |
| 4.8 | BUG-2 downstream-override audit | Per-field `lookback_stale` is written in transform.py post-partition and not rewritten downstream; output.py does not touch it. (Moot post-de-scope.) |
| 4.9 | Verdict-invariance preflight (both findings) | **PASS** -- `grep -n "near_term_target\|cleared_levels\|overhead_levels" layers/tbs_engine/gates.py` returns **zero** matches. No gate reads the desc strings or the annotation flags. |

---

## Section 5. Test Outcome

**ITS-001 file (`pytest tests/unit/test_its001_intraday_tactical.py -q`, CWD=`layers/`):**
```
116 passed
```
107 prior (v1.0/v1.1) + 9 new (class 31) = 116.

**New class 31 `TestITS001NoShelfDescAccuracy` (9 tests), all PASS:**
`test_no_shelf_mode_is_none`, `test_no_shelf_primary_desc_text`, `test_no_shelf_secondary_desc_text`, `test_no_shelf_descs_omit_within_shelf_wording`, `test_no_shelf_descs_are_ascii_only`, `test_within_primary_desc_preserves_within_wording`, `test_within_secondary_desc_preserves_within_wording`, `test_no_shelf_and_within_descs_differ`, `test_applicable_path_uses_enriched_desc_not_fallback`.

**Full cohort (`pytest tests/unit/ -q`, CWD=`layers/`):**
```
3215 passed, 4 skipped, 0 failed (43.8s)
```

| Metric | v1.1 baseline (Hand-Back §5, repo-root CWD) | v1.1.1 (CWD=`layers/`) | Note |
|---|---:|---:|---|
| Passed | 3205 | 3215 | +9 new BUG-1 tests, +1 CWD-sensitive test passing from `layers/` |
| Skipped | 4 | 4 | unchanged |
| Failed | 1 | 0 | the 1 pre-existing failure is `test_eng004` roundtrip (BUG-CFL001-PRE-1), CWD-sensitive; it **passes** from the Brief-prescribed `cd layers` CWD (v1.1 Hand-Back §6.2). Run from repo root it would still be the same 1 pre-existing failure -- **not v1.1.1-caused**. |

Total collected 3219 = 3210 (v1.1 baseline 3205+4+1) + 9. **Zero NEW failures.** Guard classes run explicitly: `TestITS001VerdictInvariance` + `TestITS001NotInGatesFile` both **PASS** (Brief §9 triggers #2 + #3 clear).

---

## Section 6. Process Deviations - For Analyst Review

### 6.1 - HALT (Brief §9 triggers #1, #5, #6): BUG-2 de-scoped from v1.1.1

**Halt event:** 2026-05-27, during Brief §4 Pre-Implementation Verification, **before any code edit**. Surfaced inline to the Operator; **Operator endorsed the halt and directed DE-SCOPE of BUG-2 from v1.1.1.** No commit was made on halt (Brief §9). The working tree carried no BUG-2 changes (none were ever attempted).

**BUG-2 halt findings, verbatim as surfaced:**

> **Ground 1 -- The fix file is wrong (§4 Item 4.4 failure).** The Brief (§1, §4, §5) locates the per-field `lookback_stale` annotation loop in `output.py::_assemble_intraday_tactical` and instructs extending it there. That loop does not exist in output.py. The only `lookback_stale` in output.py is `shelf_lookback_stale` (`output.py:858-875`) -- a different, shelf-level field. The actual per-field annotation loop lives in **transform.py**: target side `transform.py:3244-3247` (`DAILY_HIGH` in `_targets_above`), stop side `transform.py:3551-3555` (`ESTABLISHED_LOW`/`AVWAP_10BAR` in `_stops_below`). The `cleared_levels`/`overhead_levels` partition sites are also constructed entirely in transform.py (`:3210-3250`, `:3509-3562`). output.py's `_assemble_intraday_tactical` never touches `trade_setup`. The spec itself confirms this -- §2.1 + the implementation map at spec line 873: *"Transform \| 9 \| per-field lookback_stale annotation (label-match) \| `transform.py` (v1.0, unchanged)."*

> **Ground 2 -- Implementing BUG-2 requires a forbidden third file (§9 trigger #5).** The fix must edit `transform.py`, explicitly out-of-scope/forbidden this session (Brief §3, §5). This trips the SIR §11.2 third-file escape hatch.

> **Ground 3 -- BUG-2's premise contradicts the spec (§9 trigger #6).** BUG-2 reads Spec §2.1's *"annotated by label-match, not by container-path"* as "annotate the label wherever it lands, including `cleared_levels[]`/`overhead_levels[]`." The spec says the opposite: §2.1 (line 131) scopes annotation to *"three short-window **hierarchy entries**"*, and the v1.1 narrative correction (lines 137-140) defines "label-match, not container-path" as *finding the entry by its label within the hierarchy* (vs a hardcoded positional path), explicitly *"narrative-only; engine behavior unchanged."* §2.4.4 (lines 187-194) lists **hierarchy-only** `affected_fields`. §3.4 (line 394) documents that `AVWAP_10BAR` can physically land in `overhead_levels[]` but keeps its annotation "Container path (engine-actual)" as `trade_setup.stop.hierarchy[]`. The engine comments at `transform.py:3243` / `:3550` state the cleared/overhead exclusion is **intentional**. Under the spec's plain reading the engine is already conformant; "fixing" BUG-2 would *introduce* a spec deviation.

**Operator de-scope decision (2026-05-27):** *"Halt acknowledged and endorsed. Both BUG-2 findings are correct: mechanism mislocation (transform.py is third-file forbidden) AND spec contradiction (§2.1 + §2.4.4 scope annotation to hierarchy entries only -- the §3.4 partition-sibling generalization in the Brief premise does not survive a literal §2.1/§2.4.4 read). DE-SCOPE BUG-2 from v1.1.1."* Brief §4 Items 4.4-4.8, §5 BUG-2 edit anchor, and §6 BUG-2 test mandate were removed from scope. v1.1.1 = BUG-1 only.

**BUG-2 disposition:** returns to **Project chat for re-classification as Track 1 (not Bug-Fix Fast-Path).** See §9 items 1-2.

### 6.2 - Minor BUG-1 implementation latitude (no behavior change vs Brief)

- (a) **Branch condition.** The Brief §5 frames the split as `nt_mode is None` vs `nt_mode == "WITHIN"`. The realistic value set reaching the `NOT_APPLICABLE` fallback is exactly `{None, "WITHIN"}` (compute.py: `ABOVE`/`BELOW` always populate primary/secondary dicts + `applicable=True`, so they never reach the fallback). Implemented as `if nt_mode is None:` (no-shelf) / `else:` (WITHIN), with an inline comment noting WITHIN is the only other reaching mode -- defensive against any future mode without mis-labelling.
- (b) **Locals hoisted.** `nt_na_primary_desc` / `nt_na_secondary_desc` are computed before the `near_term_target_block` dict (the dict's `if nt_primary is not None else {...}` idiom is preserved unchanged), mirroring the v1.1 `tb_raw`/`rg_raw`/`bo_raw` hoist pattern (Hand-Back §6.3b).
- (c) **No `tactical_stop` clause on the no-shelf secondary** -- kept the operative "emits atr_volatility only" note on the primary only, parallel to the v1.1 WITHIN primary/secondary asymmetry.

### 6.3 - Observation (non-blocking, pre-existing, NOT in BUG-1 scope): degenerate ABOVE+no-intraday-high edge

`nt_mode is None` is the no-shelf proxy. There is one **pre-existing** degenerate path where `nt_mode` stays `None` while a shelf *is* detected: shelf `position == "ABOVE"` but `_derive_intraday_high` returns `None` (compute.py:2249-2261 sets `mode="ABOVE"` only inside `if intraday_high is not None`). `_derive_intraday_high` returns `None` only on a non-`DatetimeIndex` df (the `except (AttributeError, TypeError)` path, compute.py:2398) -- effectively unreachable on production IBKR hourly data. On that degenerate path the new no-shelf text would be imprecise, but: (i) it is pre-existing -- v1.0/v1.1 emitted the equally-wrong `"(WITHIN shelf)"` text there; (ii) BUG-1 does not introduce it; (iii) it is production-unreachable. **Not surfaced as a halt** (mechanism works; no new defect introduced; outside cosmetic BUG-1 scope). Logged here for completeness; candidate for a future hardening pass if the Analyst wants `mode`-set-on-detect tightened in compute.py.

---

## Section 7. Pre-Delivery Verification - Brief §7 / SIR §9

| # | Check | Result |
|---|---|---|
| 1 | Content accuracy | PASS -- BUG-1 matches Brief §5 mechanism + canonical text verbatim; spec §2.9.6/§4.7.3 parallel structure honored. |
| 2 | Internal consistency | PASS -- single finding, single site; no BUG-1/BUG-2 interaction (BUG-2 de-scoped). |
| 3 | Format integrity | PASS -- Hand-Back is `.md`; new desc strings + tests are ASCII (`--`, no em/en-dash, no multiply). |
| 4 | Scope discipline | PASS -- `git diff --stat` = exactly output.py + 1 test file; **no third-file diff-stat**; no spec/living-doc/Bug Register edit. |
| 5 | Gate-function verification | PASS -- gates.py grep zero matches (Item 4.9); `TestITS001NotInGatesFile` + `TestITS001VerdictInvariance` PASS. |
| 6 | Module import verification | PASS -- **no new imports** added to output.py (`git diff` import check clean); import graph unchanged. |
| 7 | Bug Register | NOT DONE -- Phase 4 / Project-chat scope; flagged §9. |
| 8 | DIA current | N/A -- BUG-1 RESTORES documented no-shelf desc behavior; triggers no new DIA. Phase 4 DIA cascade pending independently. |

---

## Section 8. Live-Sampling Confidence Notes (negative-path; Operator-optional)

v1.1.1 is a negative-path-only confirmation per Brief §8 (Phase 3 closed at S167). No LIVE run is required to deliver. Operator smoke-check expectations if desired:

- **SIDU / any no-shelf Profile A ticker:** `near_term_target.primary.desc` now reads `"No qualifying compression shelf -- near-term target not applicable. tactical_stop emits atr_volatility only."` and `.secondary.desc` reads `"No qualifying compression shelf -- secondary target not applicable."` -- the BUG-1 fix witness.
- **QUCY / any WITHIN-shelf ticker:** `near_term_target` descs still read `"Directionally neutral (WITHIN shelf) -- ..."` -- the BUG-1 regression-protect witness. (The v1.1 COHR LIVE block in the prior Hand-Back §8 is a WITHIN witness and remains accurate -- unchanged by v1.1.1.)
- BUG-2 smoke items from the Brief (cleared_levels/overhead_levels annotation) are **N/A** -- BUG-2 de-scoped.

The deterministic class-31 tests already assert both witnesses; LIVE is confirmatory only, not blocking.

---

## Section 9. Open Items for the Analyst

1. **`ITS-001-BUG-2` returns to Project chat for re-classification.** Two outcomes possible:
   - **(a) NON-BUG** -- the engine annotation is spec-correct per §2.1/§2.4.4 hierarchy-only scope (and the engine's "intentionally excluded" comments at transform.py:3243/:3550). Close the Bug Register `ITS-001-BUG-2` sub-entry as **NOT-A-BUG**; no engine change.
   - **(b) REAL BUG requiring spec amendment + transform.py engine edit** -- if the Analyst determines cleared_levels/overhead_levels *should* carry `lookback_stale`, this needs a §2.1/§2.4.4/§3.4 spec amendment FIRST, then a transform.py edit. This is a **Track 1 cycle from Phase 0** -- NOT a Bug-Fix Fast-Path (the fast-path premise -- "extend an existing output.py loop, no spec change" -- is falsified).
2. **`ANALYST-ITS001-BUG-2-SPEC-1` needs logging at Phase 4 reconciliation.** This is the **10th instance of the SIR §11.6 ITEM 3 audit-class pattern** (joins the 8-instance ANALYST cluster + the 9th surfaced at Brief §4 Item 4.6 framing). Root cause: a spec-side defense lapse (the Brief premise read §2.1 "label-match, not container-path" as container-agnostic, against the literal §2.1/§2.4.4 hierarchy-only scope). Caught by the implementation-side defense (Brief §4 vs SIR §11.6) -- the **two-layer defense worked as designed per SIR §11.8.**
3. **`ITS-001-BUG-1` Bug Register advance** -- ready for **YELLOW IMPLEMENTED** at Phase 4 close. Evidence: §2 SHAs, +9 ITS tests (116 file / 3215 cohort), zero NEW regressions, gate-isolation intact.
4. **ENG-004 / BUG-CFL001-PRE-1** -- the known CWD-sensitive `test_eng004` roundtrip failure persists (passes from `layers/`, fails from repo root); standing fix-it, unrelated to v1.1.1.
5. **Brief §4 Item 4.7 correction** -- the Brief claimed `affected_fields` enumerates `target.cleared_levels[DAILY_HIGH]`; the engine + spec §2.4.4 use hierarchy-only paths. Fold the correction into the Phase 4 Brief/Bug-Register reconciliation alongside item 2.
6. **Phase 4 DIA cascade** (independent of v1.1.1) -- Doc 2 / Doc 7 / Doc 8 / EEM / README / PEO per the v1.1 amendment cycle; BUG-1's no-shelf desc convention folds in as a cosmetic note; BUG-2 disposition (a or b) determines whether §2.1/§2.4.4/§3.4 narrative needs touching.

---

## Section 10. Closure-Criteria Tracker

| # | Criterion | Phase | Status |
|---|---|---|---|
| 1 | Phase 2 Hand-Back w/ diff-stat + SHAs + test counts | 2 | DONE (this document) |
| 2 | BUG-1 tests pass (9 new) | 2 | DONE -- 9/9; ITS file 116 passed |
| 3 | Zero NEW regressions (v1.1 baseline 3205/4/1) | 2 | DONE -- 3215/4/0 from `layers/`; reconciled; pre-existing CWD failure not v1.1.1-caused |
| 4 | BUG-1 renders correct no-shelf desc | 2 | DONE -- deterministic class-31 (no-shelf + WITHIN witnesses); LIVE optional (§8) |
| 5 | Verdict invariance (cosmetic) | 2 | DONE -- VerdictInvariance + NotInGatesFile PASS; gates.py zero tokens |
| 6 | `ITS-001-BUG-1` Bug Register advance | 4 | YELLOW IMPLEMENTED ready (§9 item 3) |
| 7 | `ITS-001-BUG-2` disposition (NON-BUG or Track 1) | Project chat | PENDING -- de-scoped from v1.1.1 (§6.1, §9 items 1-2) |
| 8 | Phase 4 DIA cascade | 4 | PENDING -- Analyst-led (§9 item 6) |

---

**End of Hand-Back.** Spec authority remains `docs/specs/ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1. Brief §9 halt fired once (BUG-2, triggers #1/#5/#6) and was Operator-resolved by de-scope; the halt held -- transform.py was never touched. v1.1.1 = BUG-1 only, in one uncommitted working-tree set (output.py + test file + this Hand-Back), ready for the Operator to commit/push per preference. Suggested next steps: (1) Operator reviews diff + commits; (2) Analyst consumes §6.1 + §9 into Project chat -- re-classify BUG-2 (NON-BUG vs Track 1) + log `ANALYST-ITS001-BUG-2-SPEC-1`; (3) Phase 4 DIA cascade advances BUG-1 to CLOSED.

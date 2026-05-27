# ITS-001 v1.1 — Claude Code CLI Implementation Brief

**Document ID:** `ITS001_v1_1_Claude_Code_CLI_Implementation_Brief_v1_0.md`
**Version:** v1.0
**Status:** Phase 2 entry artifact — authored at Phase 1 close (S166, 2026-05-26)
**Spec authority:** `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 (locked S166, supersedes v1.0.1)
**Brief authority:** ACP §6.4 canonical 11-section template; RLC-001 v1.0 precedent (S160 first canonical-format brief)
**Implementation venue:** Claude Code CLI (within IntelliJ) on working-tree of `roescha/TBS_Master_App@master`
**Authoring Analyst:** Project chat (S166)
**Co-implementation note:** Items 4 (vocabulary rename) + 5 (entry_zone) are co-implemented in single Phase 2 pass per DQ-INT-1 lock (Spec §5).

---

## §1. Mission

Implement the ITS-001 v1.1 substantive amendment cycle against the v1.0 foundation committed at S165 (Hand-Back §2 SHAs). The v1.1 amendment consolidates 5 items (3 cosmetic + 2 substantive) per Phase 0 Handoff Memo, with 13 Phase 0 DQ locks resolved at S166.

**Conflict resolution rule:** when this Brief and the v1.1 spec disagree, **spec wins**. The Brief is procedural scaffolding for the Claude Code CLI venue; the spec is the contract.

**Five amendment items (per Spec §0.1):**

| # | Item | Type |
|---|---|---|
| 1 | AVWAP_10BAR canonicalization | Cosmetic — spec narrative; engine already correct |
| 2 | Path-vs-label vocabulary fix | Cosmetic — spec narrative; engine already correct |
| 3 | `desc` string enrichment | Cosmetic — engine desc-string edits only |
| 4 | Vocabulary rename of WITHIN stop alternates | Substantive — schema-breaking dict-key swap |
| 5 | New `entry_zone` sub-object | Substantive — schema-additive new affordance |

Items 1 + 2 introduce **zero engine code change** — the v1.0 implementer correctly annotated by label-match (Hand-Back §6.1) and the spec narrative was the only defect. v1.1 spec text codifies the engine-actual behavior; no Phase 2 implementation work required for Items 1 + 2.

Items 3, 4, 5 are the Phase 2 implementation scope.

---

## §2. Operational Context

**Venue:** Claude Code CLI session running locally in IntelliJ against the `roescha/TBS_Master_App` working tree at branch `feat/ITS-001-intraday-tactical-surface` (or `master` per Operator preference). Direct read/write access to source files; local pytest execution; no upload mechanism; in-session Hand-Back delivery (not chat-paste / file-attachment / upload).

**Working-tree state at Phase 2 entry:**
- v1.0 implementation committed per Hand-Back §2 SHAs (5 engine files + 1 test file)
- Test cohort baseline: 3173 passed / 4 skipped / 1 failed (pre-existing BUG-CFL001-PRE-1 — out of scope)
- Branch tip per memo §4: `feat/ITS-001-intraday-tactical-surface` (or master)

**Commit discipline:** v1.1 amendments land in a **single working-tree commit set** (single PR, or single commit, per Operator preference). DQ-INT-1 lock forbids splitting the rename (Item 4) and entry_zone (Item 5) into separate commits — entry_zone `desc` strings reference renamed stop keys via `stop_ref` paths; sequencing would break reference integrity at the v1.0 → v1.1 boundary.

**Permission mode:** `.claude/settings.json` at working-tree root per CFL-001-PROC-1 codification — `permissions.defaultMode: "acceptEdits"` (file edits auto-approve; shell commands prompt). If the setting is missing or differs, restore before proceeding.

**Pre-flight read order:**
1. This Brief (procedural scaffolding)
2. `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` (spec authority — sections referenced throughout this Brief)
3. `ITS001_Phase2_Implementation_HandBack_v1_0.md` (v1.0 commit reference — file SHAs in §2; deviations in §6)
4. v1.0 source files at the SHAs in Hand-Back §2 (current working-tree state)

---

## §3. Phase Boundaries + Vocabulary Constraints

### 3.1 In scope — Phase 2 v1.1 implementation

| File | Scope of edit |
|---|---|
| `layers/tbs_engine/types.py` | Add 5 new RunContext `_intraday_entry_zone_*` attribute declarations (Spec §4.9) |
| `layers/tbs_engine/compute.py` | (a) Add 1 new module-level constant `INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25` (Spec §4.1); (b) rename `fade_to_upper`/`breakout_above` → `range`/`breakout` in `_compute_intraday_tactical_levels` WITHIN-mode dict construction (Spec §4.4); (c) add new helper `_compute_entry_zone(ctx)` (Spec §4.5); (d) extend `__all__` with `_compute_entry_zone` |
| `layers/tbs_engine/output.py` | (a) Extend `_ITS_NULL_FLAT_KEYS` dict with 9 new entry_zone null flat keys (Spec §4.7.5); (b) add entry_zone block emission to `_assemble_intraday_tactical` (Spec §4.7.1); (c) rewrite tactical_stop desc strings for renamed keys + enrichment (Spec §4.7.2); (d) enrich shelf / lookback_status / near_term_target desc strings (Spec §4.7.3); (e) add 9 new entry_zone flat keys to flat_keys dict (Spec §4.7.4) |
| `layers/tbs_engine/transform.py` | Add 9 new entry_zone flat keys to `_all_mapped_flat_keys()` (Spec §4.8 item 1). **Items 2 + 3 of Spec §4.8 are no-op** — top-level group emission via sentinel-key mechanism is unchanged from v1.0; lookback_stale annotation is unchanged from v1.0 (engine already annotates by label-match correctly per Hand-Back §3.4 item 3). |
| `layers/tbs_engine/main.py` | Add 1 new compute call: `_compute_entry_zone(ctx)` inserted between `_compute_intraday_tactical_levels(ctx)` and `_compute_rally_state_for_ctx(ctx)` (Spec §4.6). Extend compute import to include `_compute_entry_zone`. |
| `layers/tests/unit/test_its001_intraday_tactical.py` | (a) Add 9 new test classes / 32 new tests (Spec §6.1); (b) modify `TestITS001TacticalStopWITHIN` method names + assertions for vocabulary rename (Spec §6.2); (c) update `TestITS001LookbackStaleAnnotation` affected_fields assertion to use `trade_setup.stop.hierarchy[...]` / `trade_setup.target.hierarchy[...]` paths (Spec §6.2); (d) `TestITS001SchemaStability` updated to assert v1.1 schema (entry_zone presence + 27 flat keys) |

**Net engine LOC delta target:** ~+200 LOC engine (entry_zone helper + sub-object emission + desc string expansions); ~+150 LOC tests (9 new classes; renamed methods).

### 3.2 Out of scope — Phase 2 v1.1 implementation

| Scope | Reason |
|---|---|
| Phase 3 live cohort validation | Operator-led IBKR work; deferred until Phase 2 close |
| Phase 4 DIA cascade (Doc 2 / Doc 7 / Doc 8 / EEM / README / PEO) | Project-chat-Analyst-led; runs after Phase 3 closes |
| Bug Register status advances or new sub-entries | Per memo §8 directive — no new ITS sub-entries during v1.1 cycle. Status advances are Analyst-side in Phase 4. |
| Items 1 + 2 (spec narrative corrections) | Already correct in v1.0 engine code per Hand-Back §6.1/§6.2; v1.1 spec narrative carries the codification. Zero Phase 2 code change. |
| Short-side mechanics | Permanently out of TBS scope per Spec §1.4 (IBKR cash account constraint). Do NOT add short-side keys or affordances even speculatively. |
| Any 6th engine file beyond the 5 listed in §3.1 | Halt trigger per §9.5 — Track 1 scope discipline. |
| New gate functions or gate-input flat keys | Verdict-invariance contract — Spec §1.4 / §7 closure criterion. |

### 3.3 Vocabulary constraints

**Phase 2 v1.1 vocabulary lexicon (use these words):**
- `range`, `breakout`, `touchback` (entry_zone sub-keys; tactical_stop renamed keys)
- `trigger_structural`, `trigger_confirmed` (dual-anchor field names)
- `zone_lower`, `zone_upper` (zone-band field names)
- `stop_ref`, `target_ref`, `target_implied`, `trigger` (cross-reference and trigger field names)
- `applicable`, `mode` (entry_zone state fields; matches v1.0 near_term_target convention)
- `INTRADAY_ENTRY_CONFIRMATION_ATR_MULT` (new constant)
- `_intraday_entry_zone_*` (5 new ctx attribute names)
- `Intraday_Entry_*` (9 new flat keys)

**Drift signals — vocabulary NOT in Phase 2 v1.1 scope (their presence indicates an error):**
- `fade_to_upper`, `breakout_above` — v1.0 deprecated keys; if found anywhere in v1.1 output (other than as deprecation comments), the rename is incomplete
- `_long`, `_short`, `long_range_play`, `long_breakout_play`, `from_lower_long`, `from_upper_long` — DQ-V1 alternatives NOT selected; do not introduce
- `short_*` — permanently out of scope per §1.4
- `INTRADAY_SHELF_UPPER`, `INTRADAY_SHELF_LOWER` (uppercase hierarchy-entry labels) — v1.x deferral; do not introduce
- `opening_range`, `avwap_anchored`, `signal_bar`, `trailing_stop` — v1.x deferrals; do not introduce
- Any new gate function name (`_gate_intraday_*` etc.) — verdict-invariance violation; halt

**Conflict-resolution vocabulary:** when in doubt about a word, the spec is the lexicon authority. If the spec uses a word and the Brief doesn't, prefer the spec.

---

## §4. Pre-Implementation Verification (§11.6 Mirror — Implementation-Side)

Per ACP §6.4 / SIR §11.6 two-layer defense bridge, the Brief §4 Pre-Implementation Verification mirrors the spec §11 audit. Execute these checks BEFORE any code edit; if any check fails, halt and surface per §9.

### 4.1 Mandatory pre-implementation reads

Use the spec §11 audit table as the master reference. Each check below cites the spec section and the file:line evidence anchor. Re-read the source at the cited anchor in the current working-tree state (post-S165 commit) before declaring the check PASS.

| # | Check | Spec §11 item | Action |
|---|---|---|---|
| 1 | **v1.0 implementation present + intact in working tree** | — | `git log --oneline` confirms post-S165 commits; `git diff HEAD~N HEAD` for ITS-001 v1.0 commit shows expected files |
| 2 | **`_compute_intraday_tactical_levels` exists in compute.py with WITHIN-mode dual-key construction** | §11 #6 (Spec §4.4 reference) | `grep -n 'fade_to_upper' layers/tbs_engine/compute.py` returns at least one hit inside the WITHIN-position branch |
| 3 | **`_assemble_intraday_tactical` exists in output.py with current desc strings** | §11 #7 (RLY-001 sibling pattern) | `grep -n '_assemble_intraday_tactical' layers/tbs_engine/output.py` returns helper definition and call site |
| 4 | **`_all_mapped_flat_keys` registration block contains 18 ITS flat keys** | §11 #6 | `grep -A 25 'ITS-001' layers/tbs_engine/transform.py` shows the existing 18-key block |
| 5 | **`_intraday_*` ctx attribute declarations exist in types.py (18 attrs)** | §11 #7 | `grep -n '_intraday_' layers/tbs_engine/types.py` returns ≥18 declarations |
| 6 | **No existing `_intraday_entry_zone_*` attributes** | §11 #6 collision audit | `grep -n '_intraday_entry_zone' layers/tbs_engine/types.py` returns zero hits |
| 7 | **No existing `Intraday_Entry_*` flat keys** | §11 #6 collision audit | `grep -n 'Intraday_Entry' layers/tbs_engine/` returns zero hits |
| 8 | **No existing `entry_zone` key in `_assemble_intraday_tactical` output** | §11 #6 collision audit | `grep -n 'entry_zone' layers/tbs_engine/output.py` returns zero hits in ITS scope (zero hits ideal; if found elsewhere outside ITS, audit relevance) |
| 9 | **DD-2 EXIT override and BKOUT-001 GAP-5 override sites located** | §11 #8 | `grep -n 'DD-2\\|BKOUT-001' layers/tbs_engine/output.py` returns the override sites; verify neither touches entry_zone or Intraday_Entry_* keys (will be zero before edit, by construction) |
| 10 | **`main.py` ITS call sequence intact: VOL-001 → 3 ITS helpers → RLY-001** | §11 #1, #4 | `grep -B 2 -A 2 '_compute_intraday_tactical_levels' layers/tbs_engine/main.py` shows the call site between `_compute_volume_at_price` and `_compute_rally_state_for_ctx` |

### 4.2 Defect-discovery protocol

If any check returns unexpected results (e.g., check 2 returns zero hits — meaning the v1.0 implementation didn't land the `fade_to_upper` key — that contradicts Hand-Back §3.2 item 4 and the engine's actual live output COHR/PLTR/VRT verified at S166):

1. **Halt** — do not proceed to any code edit.
2. **Surface** — quote the unexpected check output and the contradicting evidence.
3. **Request guidance** — pause for Operator input. Do NOT silently re-interpret the spec.

This protocol mirrors RLC-001 Phase 2's spec-defect surfacing pattern (Hand-Back §6.1 / §6.2 in v1.0 — the precedent for catching spec issues at Phase 2 entry).

### 4.3 Storage-mechanism feasibility re-verification

The v1.0 implementation established the `_transform_output(action_summary, flat_metrics, debug=False)` signature has no ctx parameter (Hand-Back §4 item 7), and that the sentinel-key flat_metrics stash idiom is intact. v1.1 inherits this — entry_zone block emerges from the same sentinel-key mechanism via the modified `_assemble_intraday_tactical` block.

**Re-verify at Phase 2 entry:**
- `transform.py` `_transform_output` signature unchanged (still no ctx parameter)
- `output.py` `_assemble_output` continues to populate `metrics["_intraday_tactical_block"]` sentinel from `_assemble_intraday_tactical` return tuple
- No new ctx-dependent code paths needed in transform.py

If the signature has changed since S165 (e.g., a different bundle added a ctx parameter — would be surprising but worth checking), surface per §4.2 protocol.

---

## §5. Implementation Scope

### 5.1 File-by-file edit plan

Follow the order below. The order is non-binding for correctness (any topological-sort-respecting order works), but minimizes mental context-switching by keeping related edits together.

#### Edit 1: `layers/tbs_engine/types.py` (Spec §4.9)

Add 5 RunContext attribute declarations after the existing 18 v1.0 `_intraday_*` declarations. Default values: 4 × `None`, 1 × `False` (per spec exact declarations):

```python
_intraday_entry_zone_mode: Optional[str] = None
_intraday_entry_zone_applicable: bool = False
_intraday_entry_zone_touchback: Optional[Dict] = None
_intraday_entry_zone_range: Optional[Dict] = None
_intraday_entry_zone_breakout: Optional[Dict] = None
```

#### Edit 2: `layers/tbs_engine/compute.py` — constant (Spec §4.1)

Add new module-level constant alongside the existing 12 `INTRADAY_*` constants (insert at end of the block):

```python
INTRADAY_ENTRY_CONFIRMATION_ATR_MULT = 0.25
```

#### Edit 3: `layers/tbs_engine/compute.py` — vocabulary rename (Spec §4.4)

Locate WITHIN-mode dual-alternate dict construction in `_compute_intraday_tactical_levels` (Hand-Back §3.2 item 4 places the helper in compute.py; `grep` for `fade_to_upper` to find exact line).

Rename dict keys per Spec §4.4 structural change:
- `'price': {'fade_to_upper': ..., 'breakout_above': ...}` → `'price': {'range': ..., 'breakout': ...}`
- `'atr_buffer_mult': {'fade_to_upper': ..., 'breakout_above': ...}` → `'atr_buffer_mult': {'range': ..., 'breakout': ...}`

**Numeric values unchanged.** Only dict keys renamed.

#### Edit 4: `layers/tbs_engine/compute.py` — new helper (Spec §4.5)

Add `_compute_entry_zone(ctx)` helper immediately after `_compute_intraday_tactical_levels`. Body per Spec §4.5 verbatim (helper reads `ctx._intraday_shelf_*` state + `ctx.state.atr_raw` + `ctx.p_code`; writes 5 ctx attributes; defensive null path on `p_code != "A"` or `not _intraday_shelf_detected` or `atr_raw <= 0`).

Extend `__all__` with `'_compute_entry_zone'`.

#### Edit 5: `layers/tbs_engine/main.py` (Spec §4.6)

(a) Extend compute import:
```python
from tbs_engine.compute import (
    # ... existing imports ...
    _compute_entry_zone,
)
```

(b) Add call after `_compute_intraday_tactical_levels(ctx)`:
```python
_compute_intraday_tactical_levels(ctx)
_compute_entry_zone(ctx)  # ITS-001 v1.1
```

#### Edit 6: `layers/tbs_engine/output.py` — `_ITS_NULL_FLAT_KEYS` extension (Spec §4.7.5)

Add 9 new entry_zone flat keys to the existing `_ITS_NULL_FLAT_KEYS` dict (all `None` values). Keys: `Intraday_Entry_Zone_Mode`, `Intraday_Entry_Zone_Applicable`, `Intraday_Entry_Touchback_Zone_Lower`, `Intraday_Entry_Touchback_Zone_Upper`, `Intraday_Entry_Range_Zone_Lower`, `Intraday_Entry_Range_Zone_Upper`, `Intraday_Entry_Range_Target_Implied`, `Intraday_Entry_Breakout_Trigger_Structural`, `Intraday_Entry_Breakout_Trigger_Confirmed`.

#### Edit 7: `layers/tbs_engine/output.py` — `_assemble_intraday_tactical` body (Spec §4.7)

Within the helper body:

**(a) Update lookback_status `affected_fields` paths** (Spec §2.4.4):
```python
if bars_ago is not None and bars_ago < 10:
    affected_fields.append("trade_setup.stop.hierarchy[ESTABLISHED_LOW]")
    affected_fields.append("trade_setup.target.hierarchy[DAILY_HIGH]")
    affected_fields.append("trade_setup.stop.hierarchy[AVWAP_10BAR]")
```

Note: v1.0 affected_fields used `floor_analysis.hierarchy[ESTABLISHED_LOW]` and `target.hierarchy[DAILY_HIGH]`. v1.1 corrects to engine-actual paths. AVWAP_10BAR added unconditionally (Spec §3.4 codifies it as a hierarchy entry alongside ESTABLISHED_LOW per v1.0 Hand-Back §6.1 resolution).

**(b) Rewrite shelf desc** (Spec §4.7.3): enrich per three-sentence template.

**(c) Rewrite lookback_status desc** (Spec §4.7.3): two branches (stale + non-stale) with new desc strings.

**(d) Rewrite tactical_stop desc strings** (Spec §4.7.2):
- WITHIN-mode dict-typed price: new desc using `range` / `breakout` keys + shelf bounds + invalidation
- Scalar-typed price (ABOVE/BELOW): new three-sentence desc
- atr_volatility desc: new three-sentence desc

**(e) Rewrite near_term_target desc strings** (Spec §4.7.3) — primary + secondary `desc` enriched per template; NOT_APPLICABLE paths get cross-reference language pointing to tactical_stop + entry_zone.

**(f) Add entry_zone block emission** (Spec §4.7.1) immediately after the near_term_target block:
- `applicable: false` short-circuit with desc
- `applicable: true` branch reading ctx state, building sub-objects per mode
- ABOVE → touchback sub-object with zone band + desc
- BELOW → breakout sub-object with dual anchors + dual desc strings
- WITHIN → range + breakout sub-objects (dual alternates)
- All prices rounded `/ ctx.price_scaler` for display

**(g) Extend final block dict to include `entry_zone`:**
```python
block = {
    "shelf": shelf_block,
    "lookback_status": lookback_status_block,
    "tactical_stop": tactical_stop_block,
    "near_term_target": near_term_target_block,
    "entry_zone": entry_zone_block,  # v1.1 NEW
}
```

**(h) Extend flat_keys dict with 9 new entry_zone keys** (Spec §4.7.4) reading ctx state.

#### Edit 8: `layers/tbs_engine/transform.py` (Spec §4.8)

Add 9 new entry_zone flat keys to `_all_mapped_flat_keys()` `keys.update([...])` block. Append after the existing 18 v1.0 ITS keys.

**No other transform.py changes.** Top-level group emission and lookback_stale annotation paths are unchanged from v1.0 (engine already annotates by label-match correctly).

#### Edit 9: `layers/tests/unit/test_its001_intraday_tactical.py` (Spec §6)

**(a) Rename methods in `TestITS001TacticalStopWITHIN`** (existing class, 3 tests):
- Update test method names referencing `fade_to_upper` / `breakout_above` to use `range` / `breakout`
- Update assertions to check renamed dict keys

**(b) Update `TestITS001LookbackStaleAnnotation`** affected_fields assertion to use `trade_setup.stop.hierarchy[ESTABLISHED_LOW]` / `trade_setup.target.hierarchy[DAILY_HIGH]` / `trade_setup.stop.hierarchy[AVWAP_10BAR]` paths.

**(c) Add 9 new test classes** per Spec §6.1 catalog:
- `TestITS001EntryZoneABOVE` (4 tests)
- `TestITS001EntryZoneBELOW` (4 tests)
- `TestITS001EntryZoneWITHIN` (6 tests)
- `TestITS001EntryZoneNoShelf` (3 tests)
- `TestITS001EntryZoneProfileScope` (2 tests)
- `TestITS001EntryZoneFlatKeyRegistration` (1 test)
- `TestITS001EntryZoneVocabulary` (3 tests)
- `TestITS001V11VocabularyRename` (4 tests)
- `TestITS001V11DescEnrichment` (5 tests)

**(d) Update `TestITS001SchemaStability`** (existing class, 3 tests) — extend assertion set:
- Block top-level keys now include `entry_zone` (5 keys total)
- Flat-key count is 27 (v1.0 18 + v1.1 9)
- No `fade_to_upper` / `breakout_above` tokens in v1.1 output

**Test harness pattern:** preserve post-TEST-HRN-001 idempotent pattern from v1.0 file. New classes use same `spec_from_file_location` + `if name in sys.modules: return sys.modules[name]` guard. Stubs `tbs_engine.charts` only when not already loaded (per v1.0 convention).

### 5.2 Co-implementation discipline (DQ-INT-1)

All edits land in a **single working-tree commit set** — a single PR-ready state, or a single commit, or 2–3 commits per Operator preference grouped into one push. Specifically:

- Edits 3 (rename) and 4 + 7f (entry_zone) MUST land together. Entry_zone `desc` strings include `stop_ref: "tactical_stop.shelf_structural.price.range"` references; if the rename hasn't landed, those references break the engine.
- Edits 9a + 9b (test modifications) MUST land with edits 3 + 4 + 7 (engine changes). Running pytest after only the engine-side rename would fail `TestITS001TacticalStopWITHIN` until test names are updated.

**Sequence inside the single commit:**

1. types.py (Edit 1) — additive, safe in isolation
2. compute.py (Edits 2 + 3 + 4) — constant, then rename, then new helper
3. main.py (Edit 5) — wire new helper into pipeline
4. output.py (Edits 6 + 7) — null-keys extension, then all desc + entry_zone body changes
5. transform.py (Edit 8) — flat-key registration
6. test file (Edit 9) — rename existing methods + add new test classes
7. Run full test suite — verify zero regressions

---

## §6. Test Mandate

### 6.1 New tests + regression cohort

| Cohort | Expected outcome |
|---|---|
| 32 new tests across 9 new classes (Spec §6.1 catalog) | All 32 pass |
| 8 modified tests in 2 classes (TestITS001TacticalStopWITHIN 3 tests; TestITS001LookbackStaleAnnotation 5 tests) | All 8 pass with v1.1 assertions |
| 67 unchanged v1.0 tests in 19 classes | All 67 pass |
| **v1.1 ITS test total** | **107 passed** |
| Full pytest cohort (post-implementation) | 3173 passed → 3205 passed (delta +32). 4 skipped unchanged. 1 failed (BUG-CFL001-PRE-1, pre-existing, out of scope, unchanged). |

### 6.2 Pytest invocation

```bash
# New ITS-001 v1.1 file only
pytest layers/tests/unit/test_its001_intraday_tactical.py -v

# Full cohort regression
pytest layers/tests/unit/ --tb=line -q
```

### 6.3 Test harness hygiene

- Preserve TEST-HRN-001 idempotent pattern (mirrors RLY-001 / RLC-001 / v1.0 ITS-001 sibling files)
- `spec_from_file_location` for output.py + compute.py + transform.py loads — DO NOT pollute global `sys.modules`
- `tbs_engine.charts` stub only when not already loaded — `if 'tbs_engine.charts' not in sys.modules:` guard
- All new test classes use the same harness pattern; do not introduce a new harness convention

### 6.4 Worked-example sanity check (mandatory before Hand-Back)

Run the engine against COHR (or any WITHIN-position Profile A C2 ticker available) and verify the output JSON matches Spec §8.1 Example A:
- `intraday_tactical.entry_zone.applicable: true`
- `intraday_tactical.entry_zone.mode: "WITHIN"`
- `entry_zone.range` sub-object present with `zone_lower` = shelf.lower and `zone_upper` = shelf.lower + 0.25 × hourly_atr (rounded to 2dp)
- `entry_zone.breakout` sub-object present with `trigger_structural` = shelf.upper and `trigger_confirmed` = shelf.upper + 0.25 × hourly_atr (rounded to 2dp)
- `tactical_stop.shelf_structural.price.range` (NOT `fade_to_upper`) emitted
- `tactical_stop.shelf_structural.price.breakout` (NOT `breakout_above`) emitted
- All desc strings match Spec §8.1 template (or close — minor wording acceptable; structure must match)

If COHR is unavailable at Phase 2 entry time, run VST (v1.0 smoke witness per Hand-Back §8) or any other WITHIN-position ticker. Capture the JSON in the Hand-Back §8 live-sampling section.

---

## §7. Pre-Delivery Verification (SIR §9 Mirror)

Before producing the Hand-Back, run the SIR §9 checklist explicitly:

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Content accuracy** | All §3.1 file edits landed; all §3.2 out-of-scope items left untouched. Diff-stat shows exactly 5 engine files + 1 test file modified. |
| 2 | **Internal consistency** | No `fade_to_upper` / `breakout_above` / `_long` suffix anywhere in v1.1 output (other than deprecation comments). entry_zone `desc` cross-references resolve. |
| 3 | **Format integrity** | All edits land as Python source — syntax-valid; module imports acyclic; no broken docstrings. |
| 4 | **Scope discipline** | `git diff --stat` shows exactly 5 engine files + 1 test file. No 6th engine file. No new gate function. |
| 5 | **Gate function verification** | `TestITS001NotInGatesFile` passes — zero `Intraday_*` / `_intraday_*` / `entry_zone` tokens in any `_gate_*` function body. |
| 6 | **Module import verification** | Engine package import graph remains acyclic: `types → helpers → {gates, data, compute, exit} → {trigger, output} → main`. `_compute_entry_zone` added to compute.py only; output.py + transform.py imports unchanged. |
| 7 | **Bug Register updated** | **NOT DONE BY IMPLEMENTER** — per memo §8 directive, no new ITS Bug Register entries during v1.1 cycle. Status advance (🟠 → 🟡) is Project-chat Analyst's responsibility in Phase 4. Implementer flags "ready for status advance" in Hand-Back §9. |
| 8 | **DIA current** | **NOT DONE BY IMPLEMENTER** — Phase 4 work. Implementer flags Phase 4 scope (Doc 2 §VI / §IV substantive, Doc 7 Step 6 substantive, Doc 8 §II Layer 2 mirror, EEM verify-only, README + PEO Tier closure) in Hand-Back §9 / §10. |

---

## §8. Hand-Back Contract

Per ACP §6.5 canonical 10-section template. Hand-Back delivered **in-session** at end of Phase 2 (NOT chat-paste, NOT file-attachment, NOT upload). Required fields:

| Section | Content |
|---|---|
| §1 Outcome Summary | One-paragraph status; advancement request 🟠 SPECIFIED → 🟡 IMPLEMENTED |
| §2 Files Touched | `git diff --stat` output; file SHAs post-edit (`git hash-object` for each); branch + commit info; suggested PR title |
| §3 What Was Built — Per Spec | Per-file recap (Edit 1 through Edit 9 outcomes); flat-key counts; helper signatures; call-site evidence anchors |
| §4 Verification — Spec §11 | Re-execute the §11 audit table at post-edit state; cite `file:line` evidence anchors at the new state |
| §5 Test Outcome | New ITS test run results (107 expected); full cohort run results; baseline + delta table; pre-existing failure unchanged |
| §6 Process Deviations — For Analyst Review | Any spec defects discovered + resolution path taken; any halt-and-surface incidents; AVWAP_10BAR / path-vs-label items confirmed already-correct from v1.0 (no deviation expected) |
| §7 Pre-Delivery Verification — Brief §7 / SIR §9 | Per-check status with evidence |
| §8 Live-Sampling Confidence Notes | Operator-run smoke check JSON excerpt for the worked-example ticker (Spec §8.1 / §8.2 / §8.3 reference) |
| §9 Open Items for the Analyst | Bug Register status advance flag; Phase 3 cohort selection guidance; Phase 4 DIA cascade scope |
| §10 Closure-Criteria Tracker (Spec §7) | Per-criterion status table (#1-#8) |

### 8.1 Hand-Back §6 expected emptiness

For v1.1, the §6 Process Deviations section should be **empty or close-to-empty**. Items 1 + 2 are pre-corrected; Items 3, 4, 5 are well-specified at Phase 0 lock. The spec was authored with the v1.0 implementation evidence already in hand (engine + Hand-Back § 6 findings), so spec-defect discovery at Phase 2 should be rare.

If §6 is non-empty, the deviations must be **flagged loudly** at the top of §1 Outcome Summary. The deviation pattern would be unusual for an amendment cycle.

### 8.2 Hand-Back §8 worked-example mandatory

The §8 live-sampling section MUST include the rendered JSON for at least one ticker showing the v1.1 entry_zone block. WITHIN-mode is the minimum (Spec §8.1 / §8.3 PLTR template). If ABOVE or BELOW mode samples are available, capture those too (Spec §8.4 / §8.5 templates — currently hypothetical, would become live witnesses).

---

## §9. Failure-Mode Protocol

### 9.1 Pre-Implementation Verification fails (§4)

Halt no code edits + surface in session. Quote the failing check + the evidence anchor + the unexpected output. Do NOT silently re-interpret the spec.

### 9.2 Verdict-invariance test fails

If `TestITS001VerdictInvariance` or `TestITS001NotInGatesFile` fails after any edit, the v1.1 amendment has accidentally introduced a gate input. Halt + revert the last edit + surface. The §1.4 non-goal contract is broken — Phase 2 cannot complete.

### 9.3 entry_zone-attachment test fails

If `TestITS001EntryZoneABOVE`/`BELOW`/`WITHIN`/`NoShelf` fails after entry_zone block emission, the attachment idiom or block construction is defective. Halt + diff against Spec §4.7.1 expected emission + surface.

### 9.4 vocabulary-rename test fails

If `TestITS001V11VocabularyRename` fails, the rename in compute.py `_compute_intraday_tactical_levels` is incomplete (e.g., only `price.*` renamed but `atr_buffer_mult.*` left as `fade_to_upper` / `breakout_above`). DQ-V2 lock requires symmetric rename. Halt + re-audit compute.py rename site + surface.

### 9.5 Diff-stat shows 6th engine file touched

If `git diff --stat` shows any engine file beyond the 5 listed in §3.1, Track 1 scope is exceeded. Halt + revert the unexpected file's changes + surface. Determine whether the additional file is genuinely necessary (e.g., a helper site found in helpers.py that requires modification) — if yes, this is a spec defect to surface to the Analyst; if no, the change was speculative and must be reverted.

### 9.6 Spec ambiguity discovered

Halt + surface no unilateral spec adaptation. Quote the spec text that's ambiguous + the implementation question + the candidate resolution paths. Wait for Operator/Analyst guidance.

### 9.7 General halt protocol

For all halt cases:
- Do NOT commit
- Leave working tree in halted state (uncommitted changes preserved for inspection)
- Provide precise issue description in chat session

---

## §10. Sibling-Spec Pattern References

Read-only working-tree anchors for pattern matching. Use these as references when implementing v1.1 — they exemplify the established idioms.

| Pattern | Sibling reference | Use case |
|---|---|---|
| Helper signature + ctx attribute storage + sentinel-key flat_metrics stash | `output.py` `_assemble_rally_state` (RLY-001) + `output.py` `_assemble_intraday_tactical` (v1.0 ITS) | New `_compute_entry_zone` helper structure + new entry_zone block emission |
| Module-level constant block | `compute.py` `INTRADAY_*` constants block (v1.0) | New `INTRADAY_ENTRY_CONFIRMATION_ATR_MULT` placement |
| RunContext attribute declarations | `types.py` v1.0 `_intraday_*` declarations | New `_intraday_entry_zone_*` placement |
| Flat-key registration | `transform.py` `_all_mapped_flat_keys()` v1.0 ITS 18-key `keys.update([...])` block | New 9 entry_zone flat keys append |
| Pipeline call insertion | `main.py` v1.0 3-call ITS sequence | New `_compute_entry_zone` 4th call insertion |
| Test class structure + test harness | `layers/tests/unit/test_its001_intraday_tactical.py` v1.0 21 classes / 75 tests | New 9 v1.1 classes follow same harness pattern |
| Position-aware sub-object emission | `_assemble_intraday_tactical` `near_term_target` block (v1.0) | entry_zone position-aware emission |
| Desc-string template enrichment precedent | None (v1.1 introduces the template) | Apply §3.5 three-sentence template + §3.5 cross-reference convention |

---

## §11. Estimated Effort

**Indicative only — not binding.** Operator awareness.

| Phase | Effort estimate |
|---|---|
| §4 Pre-Implementation Verification | 15–30 minutes (10 grep / view checks against current working-tree) |
| §5 Edits 1–8 (engine code) | 1.5–2 hours (mostly Spec §4.5 + §4.7 — the entry_zone helper and output block emission; rename is mechanical) |
| §5 Edit 9 (test file modifications + new classes) | 1–1.5 hours (32 new tests + 8 modified; harness pattern is established, content is the work) |
| §6 Pytest run + §6.4 worked-example sanity | 15–30 minutes (full cohort ~35 sec per Hand-Back §5; smoke ticker capture + JSON verification) |
| §7 Pre-Delivery Verification | 15 minutes (run §9 checklist explicitly) |
| §8 Hand-Back authoring | 30–45 minutes (per ACP §6.5 10-section template) |
| **Total** | **3.5–5 hours focused CLI time** |

Confidence intervals reflect the amendment scope (well-specified at Phase 0 lock; no unknown unknowns expected) and the v1.0 commit's clean state (no test debt; no architectural ambiguity).

---

## Sign-off

**Brief authority:** This document is the Phase 2 entry artifact for ITS-001 v1.1, referencing `ITS001_Intraday_Tactical_Surface_Spec_v1_1.md` v1.1 as authority. The Brief provides procedural scaffolding for the Claude Code CLI venue; the spec carries the contracts.

**Implementation venue:** Claude Code CLI session within IntelliJ, working-tree `roescha/TBS_Master_App@master` (or branch `feat/ITS-001-intraday-tactical-surface` per Operator preference).

**Co-implementation lock:** Items 4 + 5 in single commit set per DQ-INT-1 (Spec §5).

**Authoring Analyst:** Project chat (S166, 2026-05-26).

**Spec lock-in confirmation:** Spec v1.1 locked at S166; 13 Phase 0 DQs resolved (V1, V2, V3, E1, E2, E3, E4, E5, E6, D1, D2, INT-1, INT-2).

**Lifecycle next (post-Hand-Back):**
- Operator commits / pushes per preference
- Operator schedules Phase 3 live IBKR cohort (Spec §7 #5)
- Project-chat Analyst executes Phase 4 DIA cascade (6 documents) + Bug Register ITS-001 master row to ✅ CLOSED

---

## Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | 2026-05-26 (S166) | Initial Brief authored at v1.1 spec Phase 1 close. References v1.1 spec by section per ACP §6.4.2 (does NOT restate spec contracts). Enforces DQ-INT-1 single-commit-set co-implementation of Item 4 vocabulary rename + Item 5 entry_zone. §4 Pre-Implementation Verification: 10 checks against current working-tree state. §5 Implementation Scope: 9 edits across 5 engine files + 1 test file. §6 Test Mandate: 107 v1.1 ITS tests + zero regressions. §9 Failure-Mode Protocol: 7 halt cases enumerated. §11 Estimated Effort: 3.5–5 hours focused CLI time. |

# Tier 1R — Display Hygiene Bundle Spec v1.0

**Spec ID:** `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0`
**Version:** v1.0
**Status:** SPECIFIED (Phase 1 lock — Project chat)
**Authored:** Session post-S168, in response to PEO v9.26 Tier 1R framing (S163 hygiene-pass scheduling)
**Track:** Track 1 (per ACP §7.1 — fails SIR §11.2 "no value-meaning changes on existing keys" criterion; same class as DSP-004 v1.0 parent precedent S150-S152)
**Bundle constituents:**
- DSP-004-OBS-1 (Low) — Profile C `extension_analysis.anchor.label` parallel hygiene
- DSP-004-OBS-2 (Low) — Profile C `floor_analysis.hierarchy[EMA_21].label` parallel mismatch
- BUGR-006-LABEL-RESIDUAL-1 (Trivial) — Duplicate parenthetical suffix on BRK §8.1 MM-null fallback display label

---

## 1. Purpose & Scope

### 1.1 Bundle rationale

Tier 1R Display Hygiene Bundle consolidates three previously-floating cosmetic display/label defects into a single Track 1 implementation cycle. All three share **display-layer label hygiene** as the defect class — none touches gate logic, verdict computation, or risk arithmetic. Two of three (DSP-004-OBS-1 + DSP-004-OBS-2) are the natural Profile-C-label-hygiene successors to DSP-004 v1.0 parent closure (S150-S152), extending the same profile-aware label-tier pattern to additional emission sites. The third (BUGR-006-LABEL-RESIDUAL-1) was surfaced during DSP-001 S142-cont live validation and shares the **operator-facing display correctness** thematic with the DSP-004 OBS items.

### 1.2 In-scope

| Constituent | Defect | Fix site (verified S### Project chat against `roescha/TBS_Master_App@master`) |
|---|---|---|
| DSP-004-OBS-1 | `extension_analysis.anchor.label` emits `"SMA_200"` on Profile C (should be `"WEEKLY_SMA_200"`); `extension_analysis.anchor.desc` reads `"...(~10 months on daily bars)"` on Profile C (description references daily bars but Profile C SMA_200 is computed over weekly bars) | `tbs_engine/output.py:2873-2875` (Profile C branch of the `Extension_Anchor_Type` / `Extension_Anchor_Label` write block; single Profile-C-reachable branch in this dispatch — see §3.2 SIR §11.6 ITEM 8 finding) |
| DSP-004-OBS-2 | `floor_analysis.hierarchy[EMA_21].label` emits `"DAILY_EMA_21"` on Profile C (should be `"WEEKLY_EMA_21"`); surfaces in both `target.cleared_levels` / `stop.overhead_levels` partitions per BUGR-002 partition mechanism (REL.L `overhead_levels @ 31.17` S151 live witness) | `tbs_engine/transform.py:3309-3314` (the EMA 21 anchor entry `_floor_entries.append(...)` block; profile-aware `_ema21_label_map` to be added mirroring the closed `_sma50_label_map` / `_sma200_label_map` pattern at L3337 / L3367) |
| BUGR-006-LABEL-RESIDUAL-1 | Profile B BRK MM-null fallback emits double parenthetical suffix `"WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback) (BRK-001 fallback -- measured move unavailable)"` due to downstream idempotence guard substring miss | `tbs_engine/output.py:2064-2066` (the BRK-active branch's MM-null fallback annotation; idempotence guard substring `"BRK-001 fallback"` doesn't match compute.py:807's emission `"WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"` because `§8.1` between `BRK-001` and `fallback` defeats the substring containment check) |

### 1.3 Out-of-scope (explicitly)

- DSP-004 v1.0 / v1.1 parent already-closed work (S152) — out of bundle re-litigation.
- BUGR-006 v2.0 / Label Fidelity Bundle / LABEL-1 / LABEL-2 / OUT-002 already-closed work (S137-S140-cont) — out of bundle re-litigation.
- DSP-001 / DSP-002 / DSP-003 / DSP-004 already-closed work — out of bundle re-litigation.
- BRK-001 spec body amendment — none required (compute.py:807's emission is spec-correct per BRK-001 §8.1; the defect is purely in the downstream guard at output.py:2064-2066).
- Profile-C-SMA_50 / Profile-C-EMA_21 Extension_Anchor branches — see §3.2 (SIR §11.6 ITEM 8 finding: not Profile-C-reachable; DSP-004-OBS-1 scope NARROWS from original 2-site expectation to single-site Profile C SMA_200 branch).
- Files-field provenance corrections — folded into bundle as `*-CORR-N` register entries per S147 DSP-002-CORR-1 precedent.
- ANALYST-class incident records — folded as new entries closing retroactively via SIR §11.6 pattern resolution per S162/S168 precedent.

### 1.4 Severity confirmation

All three constituents are **display-layer cosmetic** with zero impact on:
- Gate function execution or ordering
- Verdict computation (`gate_result.verdict` or `action_summary.verdict`)
- R:R numerator/denominator arithmetic
- Position sizing arithmetic
- Floor-failure detection
- Any downstream consumer (orchestrator / scanner) decision logic

Display-layer-only severity is the basis for Track 1 admissibility WITHOUT a Bug-Fix Fast-Path classification — the bundle pattern is **value-space extension** (DSP-004-OBS-1/-2) and **guard-substring widening** (BUGR-006-LABEL-RESIDUAL-1), not regression-restoration.

---

## 2. Design Lock (Phase 0 DQ resolutions)

| DQ | Question | Locked option |
|---|---|---|
| **DQ-1** | DSP-004-OBS-1 fix shape | **Option A** — extend the `output.py:2873-2875` Profile C branch with a profile-aware label dict pattern, symmetric with DSP-004 v1.1 closed pattern at `transform.py:3337` (`_sma50_label_map`) / `transform.py:3367` (`_sma200_label_map`). No helper extraction — branch-local label dict mirrors precedent. |
| **DQ-2** | DSP-004-OBS-2 fix shape | **Option A** — add `_ema21_label_map = {"A": "DAILY_EMA_21", "B": "DAILY_EMA_21", "C": "WEEKLY_EMA_21"}` at `transform.py:3309-3314`, mirror of SMA_50/SMA_200 closed pattern. Existing `_ema21_desc_map[C] = "Higher-frame EMA 21 -- trend support reference"` already encodes the Profile C frame asymmetry, so the label parallel is structurally required for end-to-end Profile-C label↔desc consistency. |
| **DQ-3** | `WEEKLY_EMA_21` vocabulary addition | **Option A** — direct mirror in `_LABEL_TIER_MAP` (transform.py:175-180) as `("MA_DYNAMIC", 3)` matching `DAILY_EMA_21`. Vocabulary collision audit clean (§3.3). |
| **DQ-4** | BUGR-006-LABEL-RESIDUAL-1 fix shape | **Option α** — widen the idempotence guard substring at `output.py:2065` from `"BRK-001 fallback"` to `"BRK-001"`. Single-token delta. Matches all three compute.py emission forms cleanly (see §4.3.2). Minimal-diff fix-class same as DSP-001 v1.1 prose-only S143 amendment + SIR-ACP-REF-1 S162 stale-reference correction. |
| **DQ-5** | Bundle structure | **Single spec** (this document). All three are display-layer label hygiene. Single test file. Single Phase 4 DIA cascade. Matches PEO Tier 1R framing. |
| **DQ-6** | Live-validation cohort scope | **6-run cohort** — see §7 below. |
| **DQ-7** | Files-field correction sub-issues | **Yes — inline** — log as 2 new `*-CORR-N` register entries CLOSED-at-spec-authoring per S147 DSP-002-CORR-1 precedent. |
| **DQ-8** | ANALYST-class incident records for stale Files fields | **Yes — log as 2 new ANALYST-class records CLOSED-at-logging** via SIR §11.6 pattern resolution per S168 ITS-001 precedent (12th + 13th instances of §11.6 ITEM 1 audit-class). |

---

## 3. Source Verification Findings (SIR §11.6 Pre-Spec-Delivery Audit)

### 3.1 Engine source authority

Audit performed at Phase 1 against `github.com/roescha/TBS_Master_App@master` via `web_fetch` per SIR §1.5.5 + §0 Step 5. Engine files audited:
- `tbs_engine/compute.py` (BRK MM-null fallback emission site)
- `tbs_engine/output.py` (Extension_Anchor write block + BRK MM-null guard)
- `tbs_engine/transform.py` (extension_analysis assembly + floor_entries.append + _LABEL_TIER_MAP)
- `tbs_engine/gates.py` (verified zero gate consumes the changed label strings — `grep` negative on `Extension_Anchor_Type` / `DAILY_EMA_21` / new label literals)

### 3.2 SIR §11.6 ITEM 8 finding (downstream-override-path audit) — IMPORTANT SCOPE NARROWING

**Finding:** DSP-004-OBS-1's original Bug Register entry (S152 logging) expected fixes at **two sites** in `transform.py`: `~L1646` (EMA_21 site) + `~L1691` (SMA_50 site). Audit against current master confirms:

1. The `extension_analysis.anchor.label` value originates from the `Extension_Anchor_Type` flat key at `transform.py:2860` (`_anchor_canonical = flat_metrics.get("Extension_Anchor_Type", _atr_anchor)`).
2. `Extension_Anchor_Type` is **written exclusively** at `tbs_engine/output.py:2861-2878` (`_populate_base_metrics`). No other engine module writes this key.
3. The output.py:2861-2878 dispatch chain has six branches; **only one** is Profile-C-reachable:

| Branch | Condition | Profile-C-reachable? |
|---|---|---|
| L2861 | `p_code == "A"` | No |
| L2864 | `p_code == "B" and state.is_trending and not is_etf` | No |
| L2867 | `p_code == "B" and state.is_resolving and not state.is_trending and not is_etf` | No |
| L2870 | `is_etf and p_code == "B"` | No |
| **L2873** | **`p_code == "C" or (is_etf and p_code == "C")`** | **YES** (exclusive) |
| L2876 | `else` (defensive fallback) | Effectively no — Profile C always satisfies L2873 |

**Conclusion:** DSP-004-OBS-1's fix scope is **single-site** (output.py:2873-2875) — Profile C's `Extension_Anchor_Type` is always `"SMA_200"` (never `"EMA_21"` or `"SMA_50"`). The original Bug Register entry's two-site expectation was based on a stale code view (transform.py line numbers from a different code state OR misclassification of the actual write site). Same Files-field-correction class as DSP-001 S127 → S142 / DSP-002-CORR-1 S147.

**Bonus finding:** The Profile C SMA_200 branch's `Extension_Anchor_Label` (L2874) reads `"Long-term secular trend floor (~10 months on daily bars)"` — **doubly wrong** on Profile C, since 200 weekly bars ≈ 4 years, not "10 months on daily bars". Fix scope expands to include the Label desc string parallel to the Type.

### 3.3 SIR §11.6 ITEM 3 finding (shared-reference / partition-leak audit)

**EMA 21 floor entry partition behavior under BUGR-002:**
- The EMA 21 anchor entry written at `transform.py:3309-3314` flows through the BUGR-002 stop-hierarchy partition mechanism.
- When `_current_price > _ema21_price`: entry lands in `floor_analysis.hierarchy[]` with status `HOLDING`.
- When `_current_price < _ema21_price`: entry lands in `stop.overhead_levels[]` (post-partition; per BUGR-002 partition predicate).
- BOTH partition sites must reflect the new `WEEKLY_EMA_21` label on Profile C (label-match — entry retains its label across partition).

**Confirmed safe:** transform.py:3309-3314 writes the label ONCE on entry construction; the partition mechanism at the post-sort site preserves the entry dict structure including the label field. No partition-leak risk; new label propagates consistently across both partition placements.

**Comparison to ITS-001-BUG-2 (S168 NOT-A-BUG)**: This bundle's per-partition propagation is OPPOSITE direction from ITS-001-BUG-2 — there the spec EXCLUDED cleared/overhead partition annotation deliberately (`lookback_stale` annotation hierarchy-scoped only); here the label IS part of the entry construction and SHOULD propagate to whichever partition the entry lands in. No spec contradiction; mechanism is correct.

### 3.4 SIR §11.6 ITEM 6 finding (cross-spec layout audit)

DSP-004 v1.1 spec (`DSP004_Profile_C_Weekly_Anchor_Label_Spec_v1_1.md`) introduces the profile-aware label tier pattern at §5 (Edit blocks). This Bundle spec is an **extension** of that pattern, not a re-litigation. No re-numbering or layout conflict with DSP-004 v1.1. New extensions land as additive sites:
- `output.py:2873-2875` (DSP-004-OBS-1 — new Profile C label branch parallel to existing DSP-004 v1.1 transform.py sites)
- `transform.py:3309-3314` (DSP-004-OBS-2 — new `_ema21_label_map` parallel to existing `_sma50_label_map` / `_sma200_label_map`)

### 3.5 Verification audit summary

| §11.6 Item | Applicability | Status |
|---|---|---|
| ITEM 1 (call-order) | N/A | — |
| ITEM 2 (sort-order) | N/A | — |
| **ITEM 3 (shared-reference / partition-leak)** | **Applicable** — EMA 21 floor entry partition behavior | ✅ PASS (entry-level label propagates consistently across BUGR-002 partition sites) |
| ITEM 4 (pipeline-order) | N/A | — |
| ITEM 5 (call-order feasibility) | N/A | — |
| **ITEM 6 (cross-spec layout audit)** | **Applicable** — DSP-004 v1.1 layout vs Bundle extension | ✅ PASS (additive sites, no renumbering conflict) |
| ITEM 7 (storage-mechanism feasibility) | N/A | — |
| **ITEM 8 (downstream-override-path audit)** | **Applicable** — Extension_Anchor_Type / EMA 21 label write paths | ✅ PASS (scope-narrowing finding folded into §3.2; no additional override paths) |

### 3.6 Vocabulary collision audit (`WEEKLY_EMA_21` new token)

| Domain | Existing tokens | Collision with `WEEKLY_EMA_21`? |
|---|---|---|
| `_LABEL_TIER_MAP` (transform.py:175-180) | `DAILY_EMA_21`, `DAILY_SMA_50`, `WEEKLY_SMA_50`, `DAILY_SMA_200`, `WEEKLY_SMA_200`, others | No — `WEEKLY_EMA_21` is the natural symmetric completion (currently absent) |
| `_LABEL_VOCAB_MAP` (transform.py:~199) | EMA 21 vocabulary domain | No — additive; mirror of DAILY_EMA_21 |
| `extension_analysis.condition.label` | `OVEREXTENDED`, `ELEVATED`, `NORMAL`, `AT_FLOOR`, `BELOW_FLOOR` | No — different surface entirely |
| `volume.rvol.label` / other banding domains | QUIET, BELOW AVERAGE, NORMAL, ELEVATED, HIGH, EXTREME | No — different surface |
| Gate input flat keys | Verified zero gates consume label literal | No — display-only |

**Audit clean.** New token `WEEKLY_EMA_21` admitted at MA_DYNAMIC rank 3 (matching DAILY_EMA_21).

---

## 4. Implementation Contract

### 4.1 DSP-004-OBS-1 — Profile C `extension_analysis.anchor.label` + `.anchor.desc` (output.py:2861-2878)

**Pre-fix code (CURRENT MASTER — lines 2873-2875):**

```python
elif p_code == "C" or (is_etf and p_code == "C"):
    metrics["Extension_Anchor_Type"] = "SMA_200"
    metrics["Extension_Anchor_Label"] = "Long-term secular trend floor (~10 months on daily bars)"
```

**Post-fix code (Edit 1 — replace lines 2873-2875):**

```python
elif p_code == "C" or (is_etf and p_code == "C"):
    # [DSP-004-OBS-1] Profile C primary frame is weekly per PA-001 — extension
    # anchor on Profile C IS the weekly SMA 200. Label + Label desc reflect the
    # weekly-frame identity (parallel to DSP-004 v1.1 _sma50_label_map /
    # _sma200_label_map closed pattern at transform.py:3337 / 3367 for floor
    # entries; this is the corresponding extension_analysis surface).
    metrics["Extension_Anchor_Type"] = "WEEKLY_SMA_200"
    metrics["Extension_Anchor_Label"] = "Long-term secular trend floor (~4 years on weekly bars)"
```

**Diff stat estimate:** +5 LOC (~3 LOC inline `[DSP-004-OBS-1]` provenance commentary).

**Behavior change:**
- Profile C `flat_metrics.get("Extension_Anchor_Type")` now returns `"WEEKLY_SMA_200"` (was `"SMA_200"`).
- Profile C `flat_metrics.get("Extension_Anchor_Label")` now returns `"Long-term secular trend floor (~4 years on weekly bars)"` (was `"Long-term secular trend floor (~10 months on daily bars)"`).
- Profile C `extension_analysis.anchor.label` JSON surface now emits `"WEEKLY_SMA_200"` (was `"SMA_200"`).
- Profile C `extension_analysis.anchor.desc` JSON surface now emits the weekly-frame description.
- **Profile A / Profile B label space unchanged** — bitwise-invariant on those profiles.

### 4.2 DSP-004-OBS-2 — Profile C `floor_analysis.hierarchy[EMA_21].label` (transform.py:3309-3314)

**Pre-fix code (CURRENT MASTER):**

```python
if _ema21_price is not None:
    _floor_entries.append({
        "price": _ema21_price,
        "label": "DAILY_EMA_21",
        "role": {"label": _ema21_role_map.get(_p_code, "SUPPORT"), "desc": _ema21_desc_map.get(_p_code, "")},
        "status": "BREACHED" if (_current_price is not None and _current_price < _ema21_price) else "HOLDING",
    })
```

**Post-fix code (Edit 2 — insert label map immediately before append, then update append literal):**

```python
# [DSP-004-OBS-2] Profile-aware label map mirroring _sma50_label_map (L3337) /
# _sma200_label_map (L3367) closed pattern. Profile C primary frame is weekly
# per PA-001, so the EMA 21 anchor on Profile C is the higher-frame EMA 21
# (matches _ema21_desc_map[C] = "Higher-frame EMA 21 -- trend support reference"
# already encoded above). Profile A/B retain DAILY_EMA_21. Default
# "DAILY_EMA_21" matches the _p_code defensive fallback convention.
_ema21_label_map = {"A": "DAILY_EMA_21", "B": "DAILY_EMA_21", "C": "WEEKLY_EMA_21"}
if _ema21_price is not None:
    _floor_entries.append({
        "price": _ema21_price,
        "label": _ema21_label_map.get(_p_code, "DAILY_EMA_21"),
        "role": {"label": _ema21_role_map.get(_p_code, "SUPPORT"), "desc": _ema21_desc_map.get(_p_code, "")},
        "status": "BREACHED" if (_current_price is not None and _current_price < _ema21_price) else "HOLDING",
    })
```

**Diff stat estimate:** +8 LOC (~6 LOC inline `[DSP-004-OBS-2]` provenance commentary + 1 LOC label_map + 1 LOC append literal change).

**Behavior change:**
- Profile C `floor_analysis.hierarchy[]` (and parallel partition sites `target.cleared_levels[]` / `stop.overhead_levels[]` per BUGR-002 partition) — EMA 21 anchor entry's `label` field emits `"WEEKLY_EMA_21"` (was `"DAILY_EMA_21"`).
- Conviction-tier classification (CNV-001) — `WEEKLY_EMA_21` resolves to `(MA_DYNAMIC, 3)` per Edit 3 below, so `conviction_tier` field on the entry stays `MA_DYNAMIC` (unchanged from pre-fix Profile C `DAILY_EMA_21` resolution).
- **Profile A / Profile B label space unchanged** — bitwise-invariant on those profiles.

### 4.3 DSP-004-OBS-2 — `WEEKLY_EMA_21` vocabulary extension (transform.py:175-180)

**Pre-fix code (CURRENT MASTER, transform.py:175-180):**

```python
    # MA_DYNAMIC (rank 3) — moving-average reference (daily + weekly per DSP-004 v1.1)
    "DAILY_EMA_21":    ("MA_DYNAMIC", 3),
    "DAILY_SMA_50":    ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_50":   ("MA_DYNAMIC", 3),
    "DAILY_SMA_200":   ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_200":  ("MA_DYNAMIC", 3),
```

**Post-fix code (Edit 3 — insert `WEEKLY_EMA_21` row immediately after `DAILY_EMA_21`):**

```python
    # MA_DYNAMIC (rank 3) — moving-average reference (daily + weekly per DSP-004 v1.1; weekly EMA 21 per DSP-004-OBS-2)
    "DAILY_EMA_21":    ("MA_DYNAMIC", 3),
    "WEEKLY_EMA_21":   ("MA_DYNAMIC", 3),
    "DAILY_SMA_50":    ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_50":   ("MA_DYNAMIC", 3),
    "DAILY_SMA_200":   ("MA_DYNAMIC", 3),
    "WEEKLY_SMA_200":  ("MA_DYNAMIC", 3),
```

**Diff stat estimate:** +1 LOC (single map entry) + comment refresh (+/- 0 LOC).

**Behavior:** `_LABEL_TIER_MAP.get("WEEKLY_EMA_21")` returns `("MA_DYNAMIC", 3)` instead of the prior null (which would have produced `(None, None)` per CNV-001 unknown-label safety branch — visible vocabulary-drift signal). Post-fix, CNV-001's `conviction_tier` field resolves cleanly to `MA_DYNAMIC` on Profile C EMA 21 entries.

### 4.4 BUGR-006-LABEL-RESIDUAL-1 — Idempotence guard widening (output.py:2064-2066)

**Pre-fix code (CURRENT MASTER):**

```python
        else:
            _existing_src = metrics.get("Profit_Target_Source", "")
            if "BRK-001 fallback" not in str(_existing_src):
                metrics["Profit_Target_Source"] = str(_existing_src) + " (BRK-001 fallback -- measured move unavailable)"
```

**Post-fix code (Edit 4 — single-token substring widening):**

```python
        else:
            _existing_src = metrics.get("Profit_Target_Source", "")
            # [BUGR-006-LABEL-RESIDUAL-1] Widened guard substring from "BRK-001 fallback"
            # to "BRK-001" to match all three compute.py emission forms:
            #   - "MEASURED_MOVE (BRK-001 post-breakout target)" (compute.py:765)
            #   - "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)" (compute.py:807)
            #   - "ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)" (compute.py:817)
            #   - "BRK-001 post-breakout (fallbacks exhausted)" (compute.py:853)
            # Original substring missed the §8.1 fallback forms (§8.1 between
            # "BRK-001" and "fallback" defeated containment check), causing
            # duplicate parenthetical suffix on Profile B BRK MM-null +
            # weekly-fallback path. Single-character substring delta (" fallback"
            # → "") matches all forms cleanly.
            if "BRK-001" not in str(_existing_src):
                metrics["Profit_Target_Source"] = str(_existing_src) + " (BRK-001 fallback -- measured move unavailable)"
```

**Diff stat estimate:** +9 LOC (single-string literal change + 8 LOC inline `[BUGR-006-LABEL-RESIDUAL-1]` provenance commentary).

**Behavior change:**
- Profile B BRK-active + MM-null + weekly-fallback path: `Profit_Target_Source` emits the clean compute.py:807 string `"WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"` without the double-append. **THE BUG IS FIXED.**
- Profile B BRK-active + MM-null + ATR-fallback path: `Profit_Target_Source` emits the clean compute.py:817 string `"ATR_PROJECTION (BRK-001 §8.1 MM-null fallback)"`. (Implicit regression-invariance — was previously also affected by double-append.)
- Profile B BRK-active + MM-null + fallbacks-exhausted path: `Profit_Target_Source` emits the clean compute.py:853 string `"BRK-001 post-breakout (fallbacks exhausted)"`. (Implicit regression-invariance.)
- Profile A BRK-active + MM-null path: compute.py:774's local-mutation-only write path is unaffected (compute.py only writes `Profit_Target_Source` on Profile A at L777). On Profile A, the output.py:2065 guard now checks for `"BRK-001"` — Profile A flows through compute.py:774's prior path where `_profit_target_source = "DAILY_CTX (BRK-001 fallback -- measured move unavailable)"` is written for `p_code == "A"`. The guard then correctly skips the output.py append (substring `"BRK-001"` is present), preserving the Profile A clean single-suffix label.
- Profile A / Profile B / Profile C non-BRK paths: completely unaffected — the entire `else` branch only runs when `_mm_raw is None` AND BRK-active.

**Net effect:** Single-token guard widening eliminates the double-append on all four BRK MM-null fallback paths (Profile B weekly / Profile B ATR / Profile B exhausted / Profile A). The output.py:2066 append text is preserved verbatim (`" (BRK-001 fallback -- measured move unavailable)"`) for the legacy Profile A non-BUGR-006-v2.0 path (which still writes via this site when `_profit_target_source = ""` or unset).

---

## 5. Pipeline & Call-Order Reference

| Edit | File | Engine layer (per EEM v2.42) | Layer position | Reads | Writes |
|---|---|---|---|---|---|
| Edit 1 (DSP-004-OBS-1) | output.py:2873-2875 | `_populate_base_metrics` (PHASE 1 base metric population) | Pre-cascade | `p_code`, `is_etf` (ctx unpack) | `Extension_Anchor_Type`, `Extension_Anchor_Label` (flat keys) |
| Edit 2 (DSP-004-OBS-2) | transform.py:3309-3314 | `_transform_output` (Layer 5 grouping) | Post-engine | `_p_code`, `_ema21_price`, `_current_price`, `_ema21_role_map`, `_ema21_desc_map` (local scope) | `_floor_entries[]` (local list of dicts) |
| Edit 3 (vocabulary extension) | transform.py:175-180 | Module-level constant | Module load | (none — module-level) | `_LABEL_TIER_MAP` (module-level dict) |
| Edit 4 (BUGR-006-LABEL-RESIDUAL-1) | output.py:2064-2066 | `_assemble_output` (Layer 5 output assembly) | Post-cascade | `metrics["Profit_Target_Source"]` (read), `_brk_active`, `_mm_raw` (local) | `metrics["Profit_Target_Source"]` (write) |

**Gate cascade impact:** ZERO. No gate function consumes any of the changed values. Verified by `grep -nE "Extension_Anchor_Type|DAILY_EMA_21|WEEKLY_EMA_21|WEEKLY_SMA_200|BRK-001 fallback" tbs_engine/gates.py` returning zero matches in the engine's gate-cascade module.

**Module import graph:** Zero new imports. Acyclic graph preserved (`types → helpers → {gates, data, compute, exit} → {trigger, output} → main`).

---

## 6. Test Plan

**New test file:** `tests/unit/test_dsp004_obs_bundle_label_hygiene.py`

**Test count target:** ~25-35 tests across 7 classes. Mirrors DSP-004 v1.0 test cohort structure (`tests/unit/test_dsp004_profile_c_weekly_sma_label.py`).

### 6.1 Test class breakdown

| Class | Tests | Purpose |
|---|---|---|
| `TestDSP004OBS1ProfileCExtensionAnchorLabel` | ~5 | Profile C `extension_analysis.anchor.label = "WEEKLY_SMA_200"` + `.desc` weekly-frame text; Profile C `Extension_Anchor_Type` flat key value-space extension |
| `TestDSP004OBS1ABRegressionInvariance` | ~4 | Profile A / Profile B label space bitwise-invariant for the 5 non-Profile-C branches of the extension_anchor write block (TRENDING / RESOLVING / ETF / etc.) |
| `TestDSP004OBS2ProfileCEMA21FloorEntryLabel` | ~5 | Profile C `floor_analysis.hierarchy[EMA_21].label = "WEEKLY_EMA_21"` + `_ema21_label_map.get(...)` resolution per profile |
| `TestDSP004OBS2OverheadLevelsPartition` | ~3 | REL.L-pattern reproduction — Profile C with price below EMA_21 anchor — entry lands in `stop.overhead_levels[]` partition with `WEEKLY_EMA_21` label preserved (BUGR-002 partition propagation) |
| `TestDSP004OBS2VocabularyExtension` | ~3 | `_LABEL_TIER_MAP.get("WEEKLY_EMA_21") == ("MA_DYNAMIC", 3)`; `_LABEL_TIER_MAP.get("DAILY_EMA_21") == ("MA_DYNAMIC", 3)` (regression-invariance); CNV-001 conviction_tier resolution on Profile C EMA 21 entries |
| `TestBUGR006LabelResidualGuardWidening` | ~6 | Profile B BRK-active + MM-null + weekly-fallback path emits single suffix (the killer test); Profile B BRK-active + MM-null + ATR-fallback path single-suffix; Profile B BRK-active + MM-null + exhausted path single-suffix; Profile A BRK-active + MM-null path single-suffix; verdict-invariance pre/post on the four BRK MM-null sub-paths |
| `TestBUGR006LabelResidualRegressionInvariance` | ~4 | Profile B BRK-active + MM-present (non-fallback) path unchanged; non-BRK paths completely unaffected; the entire `else` (MM-null) branch's other side-effects (Cons_High etc.) unchanged |
| `TestBundleVerdictInvariance` | ~3 | `gate_result.verdict` unchanged pre/post across Profile A/B/C × {VALID, INVALID} matrix; `action_summary.verdict` unchanged pre/post |
| `TestBundleNotInGatesFile` | ~2 | Negative-assertion: `grep` test against `gates.py` — zero matches for `Extension_Anchor_Type`, `DAILY_EMA_21`, `WEEKLY_EMA_21`, `WEEKLY_SMA_200`, `BRK-001 fallback` substrings; per SIR §11.2 Track 2 admissibility test class precedent (carried into Track 1 for verdict-invariance evidence) |

### 6.2 Test harness convention

Per TEST-HRN-001 hygiene awareness (logged S137-cont, still IDENTIFIED): the new test file MUST use the idempotent module-loading guard pattern (`if name in sys.modules: return sys.modules[name]`) on any `sys.modules[...]` registrations. Fixture mocks use `spec_from_file_location` without polluting global `sys.modules` per TEST-HRN-001 safe-pattern (e.g., test_bugr002_hierarchy_partition.py / test_pa001_phase3_hierarchies.py precedent).

### 6.3 Regression baseline

Phase 2 pytest target: **3215 → ~3245 passed / 4 skipped / 0 failed** (baseline 3215 from S168 + ~30 new tests). Zero Bundle-caused regressions. Pre-existing BUG-CFL001-PRE-1 CWD-sensitive `test_eng004` may still produce 1 failure from non-`layers/` CWD — invocation MUST be `cd layers && pytest tests/unit/test_dsp004_obs_bundle_label_hygiene.py` per S168 convention.

### 6.4 Differential test mode (FAIL pre-fix → PASS post-fix)

The following tests are expected to **FAIL** when run against pre-fix engine source (baseline regression evidence) and **PASS** post-fix:

| Test | Pre-fix expected | Post-fix expected |
|---|---|---|
| `TestDSP004OBS1ProfileCExtensionAnchorLabel::test_label_is_weekly_sma_200` | FAIL (`"SMA_200"`) | PASS (`"WEEKLY_SMA_200"`) |
| `TestDSP004OBS1ProfileCExtensionAnchorLabel::test_desc_references_weekly_bars` | FAIL (`"...10 months on daily bars"`) | PASS (`"...4 years on weekly bars"`) |
| `TestDSP004OBS2ProfileCEMA21FloorEntryLabel::test_label_is_weekly_ema_21` | FAIL (`"DAILY_EMA_21"`) | PASS (`"WEEKLY_EMA_21"`) |
| `TestDSP004OBS2OverheadLevelsPartition::test_overhead_partition_preserves_weekly_ema_21` | FAIL (`"DAILY_EMA_21"` in overhead partition) | PASS (`"WEEKLY_EMA_21"` in overhead partition) |
| `TestBUGR006LabelResidualGuardWidening::test_profile_b_brk_mm_null_weekly_fallback_single_suffix` | FAIL (double suffix) | PASS (clean single suffix) |
| `TestBUGR006LabelResidualGuardWidening::test_profile_b_brk_mm_null_atr_fallback_single_suffix` | FAIL (double suffix) | PASS (clean single suffix) |

Each differential test serves as regression-protection evidence per spec §7.

---

## 7. Closure Criteria

### 7.1 Closure path

| Criterion | Required |
|---|---|
| #1 | Phase 2 Hand-Back delivered per ACP §6.5 canonical 10-section template; branch `tier1r-display-hygiene-bundle` on `roescha/TBS_Master_App` |
| #2 | Tests pass: 3215 baseline + ~30 new = ~3245 passed / 4 skipped / 0 failed; zero Bundle-caused regressions; all 6 differential tests FAIL pre-fix → PASS post-fix |
| #3 | Live validation cohort §7.2 complete with positive Profile C witnesses + Profile A/B regression witnesses |
| #4 | `TestBundleVerdictInvariance` + `TestBundleNotInGatesFile` PASS post-fix |
| #5 | Bug Register Bundle entry (this spec) advanced to ✅ CLOSED + 2 CORR sub-entries CLOSED-at-spec-authoring + 2 ANALYST-class records CLOSED-at-logging per §11.6 pattern resolution |
| #6 | Phase 4 6-doc DIA cascade complete (Doc 2 + Doc 8 substantive; Doc 7 scan-only; EEM verify-only; README + PEO substantive) |
| #7 | Spec verified against final engine state (this spec's contracts match post-implementation Hand-Back evidence) |

### 7.2 Live validation cohort (6-run minimum)

| Run | Profile | Ticker class | Purpose |
|---|---|---|---|
| 1 | C | **REL.L** (S151 witness from DSP-004-OBS-2 surfacing) | DSP-004-OBS-2 `WEEKLY_EMA_21` label witness on `stop.overhead_levels` partition (price below EMA 21 reproducer) |
| 2 | C | **LIN** OR **CRWD** (existing Profile C ticker) | DSP-004-OBS-1 `WEEKLY_SMA_200` `extension_analysis.anchor.label` witness + `WEEKLY_EMA_21` `floor_analysis.hierarchy` witness (if EMA 21 entry present); validates both edits cohabit cleanly on a Profile C run |
| 3 | A | Any Profile A ticker | DSP-004-OBS-1/-2 Profile A regression-invariance (label space unchanged — `DAILY_EMA_21`, `DAILY_SMA_200` etc. preserved verbatim) |
| 4 | B | Any Profile B ticker | DSP-004-OBS-1/-2 Profile B regression-invariance (label space unchanged) |
| 5 | B | **BRK-active + MM-null + weekly-fallback path ticker** (CRH-B per S142-cont evidence OR similar Profile B BRK-active candidate where MM unavailable AND weekly 10-bar high > current close) | BUGR-006-LABEL-RESIDUAL-1 single-suffix witness — the killer test reproducing the original double-append observation |
| 6 | B | **BRK-active + MM-present path ticker** (PWR / SNDK / TSLA per S140-cont LABEL-2 cohort) | BUGR-006-LABEL-RESIDUAL-1 regression-invariance — non-fallback path emits MEASURED_MOVE label without any suffix mutation |

### 7.3 Validation evidence required (per run)

- JSON output sample showing the changed label field(s) with expected post-fix value
- Verdict (`gate_result.verdict` + `action_summary.verdict`) — must match pre-fix run on equivalent fixture
- For BRK-active runs (Runs 5 + 6): full `trade_setup.target.source.label` value documented byte-for-byte
- For Profile C runs (Runs 1 + 2): both `extension_analysis.anchor.label` AND `floor_analysis.hierarchy[*].label` enumerated for EMA 21 / SMA 200 entries

---

## 8. Worked Examples

### 8.1 Profile C extension_analysis.anchor.label witness (Run 2 expected output)

**Ticker:** Any Profile C (LIN / CRWD / similar) where SMA_200 is the structural floor.

**Engine output JSON excerpt (`extension_analysis` group, daily sub-block):**

```json
"extension_analysis": {
  "distance": {"value": 1.23, "unit": "ATR", "desc": "Distance from structural anchor (positive = above)"},
  "anchor": {
    "label": "WEEKLY_SMA_200",                                                                
    "desc": "Long-term secular trend floor (~4 years on weekly bars)"                          
  },
  "limit": {...},
  ...
}
```

Pre-fix `anchor` block emitted `"label": "SMA_200"` + `"desc": "...10 months on daily bars"`.

### 8.2 Profile C floor_analysis.hierarchy[EMA_21] witness — overhead partition (Run 1 expected output)

**Ticker:** REL.L Profile C (current_price below EMA 21 anchor; BUGR-002 partition routes the entry to `stop.overhead_levels[]`).

**Engine output JSON excerpt (`stop.overhead_levels[]`):**

```json
"stop": {
  "hierarchy": [...],
  "overhead_levels": [
    {
      "price": 31.17,
      "label": "WEEKLY_EMA_21",                                                                  
      "role": {"label": "SUPPORT", "desc": "Higher-frame EMA 21 -- trend support reference"},
      "status": "BREACHED",
      "conviction_tier": "MA_DYNAMIC",                                                           
      "conviction_rank": 3                                                                       
    },
    ...
  ]
}
```

Pre-fix entry emitted `"label": "DAILY_EMA_21"` (the label↔desc mismatch the OBS-2 entry was logged for); conviction resolution was also `("MA_DYNAMIC", 3)` via the `DAILY_EMA_21` key, so conviction unchanged — only the label string is corrected.

### 8.3 Profile B BRK MM-null weekly-fallback single suffix (Run 5 expected output)

**Ticker:** Profile B BRK-active candidate, MM-target unavailable, weekly 10-bar high > current close.

**Engine output JSON excerpt (`trade_setup.target.source`):**

```json
"trade_setup": {
  "target": {
    "price": <weekly 10-bar high>,
    "source": {
      "label": "WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)",                              
      ...
    },
    ...
  },
  ...
}
```

Pre-fix `source.label` emitted `"WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback) (BRK-001 fallback -- measured move unavailable)"` — the duplicate parenthetical.

### 8.4 Profile A regression-invariance (Run 3 expected output)

**Ticker:** Any Profile A.

**Engine output JSON excerpt (`extension_analysis.daily.anchor`):**

```json
"daily": {
  "distance": {...},
  "anchor": {"label": "EMA_21", "desc": "Daily 21-period exponential moving average (protective anchor)"},
  ...
}
```

Note: Profile A's extension_analysis primary sub-block is `intraday_retired` (per AVWAP-001 DQ-4 — see transform.py:2894-2900). The daily overlay at L2911-2949 emits the EMA_21 anchor with hardcoded `"label": "EMA_21"` — **unchanged by this bundle** (out of bundle scope; would be a separate concern if needed).

---

## 9. Consumer Audit (SIR §11 "Two-Pass Discipline" per S152 DSP-004-AUDIT-GAP-1 augmentation)

### 9.1 Engine package consumers

| File | Touch | Verification |
|---|---|---|
| `tbs_engine/types.py` | None | No type signature affected |
| `tbs_engine/data.py` | None | No data fetch affected |
| `tbs_engine/compute.py` | None | Read-side unaffected (compute.py:807/817 already emits BRK §8.1 fallback labels — clean strings) |
| `tbs_engine/gates.py` | None | `grep` negative on all changed identifiers — zero gate consumes |
| `tbs_engine/trigger.py` | None | No trigger pattern affected |
| `tbs_engine/exit.py` | None | No exit signal affected |
| `tbs_engine/output.py` | **EDITED** (Edit 1 + Edit 4) | See §4.1 + §4.4 |
| `tbs_engine/transform.py` | **EDITED** (Edit 2 + Edit 3) | See §4.2 + §4.3 |
| `tbs_engine/main.py` | None | Orchestration unaffected |
| `tbs_engine/helpers.py` | None | No helper signature affected |
| `tbs_engine/charts.py` | None | Chart rendering unaffected |

### 9.2 Downstream layer consumers

| File | Touch | Verification |
|---|---|---|
| `tbs_orchestrator.py` | None | Reads engine output transparently; new label values pass through |
| `tbs_scanner.py` | None | Reads engine output transparently |
| `ai_*_retriever.py` | None | Out of bundle scope |
| `*_context.py` | None | Out of bundle scope |

### 9.3 Test suite touchpoints

| Test file | Action |
|---|---|
| `tests/unit/test_dsp004_obs_bundle_label_hygiene.py` | **NEW** — bundle test file per §6 |
| Other tests | Verify-only — no expected updates required. Per the SIR §11 "Two-Pass Consumer Audit Discipline" augmentation (S152), the implementer MUST read test file bodies (not file names) to confirm no other tests assert on the changed label strings. Pre-spec-delivery audit identified no Profile C `"SMA_200"` / `"DAILY_EMA_21"` literal assertions in other test files; Phase 2 implementer re-verifies with `grep` before declaring zero regression scope. |

---

## 10. DIA Scope (Phase 4 — 6-doc + Bug Register)

| Document | Current version | Target version | Touch class | Reason |
|---|---|---|---|---|
| Doc 2 | v8.65 | v8.66 | **Substantive** | §IV value-space extensions: (a) `extension_analysis.anchor.label` admits `"WEEKLY_SMA_200"` on Profile C; (b) `floor_analysis.hierarchy[].label` admits `"WEEKLY_EMA_21"` on Profile C; (c) `trade_setup.target.source.label` BRK MM-null fallback single-suffix convention (forbid double-append on guard fix); (d) `extension_analysis.anchor.desc` Profile C frame description |
| Doc 8 | v8.7.65 | v8.7.66 | **Substantive mirror** | §II Layer 2 — three edit sites + Files-field-correction provenance |
| Doc 7 | v8.5.55 | v8.5.56 | **Scan-only** | Step 6 prose unchanged — label hygiene is invisible at operator-reading level |
| EEM | v2.42 | v2.42 (verify-only — no version bump) | **Verify-only** | Zero gate touched, gate cascade bitwise-invariant, no flat-key added; non-gate-cascade-affecting cosmetic change per S147 DSP-002 / S148 RALLY-TRIG-001 / S152 DSP-004 / S157 CFL-001 verify-only precedent class |
| README | v8.6.34 | v8.6.35 | **Cascade** | Document Authority cascade (Doc 2 + Doc 8 + PEO) + Last Updated narrative + Version line `+ Tier 1R` append |
| PEO | v9.26 | v9.27 | **Substantive** | Tier 1R ✅ CLOSED + Document History v9.27 row + ASCII Dependency Map annotation (1R closure) |
| Bug Register | n/a | n/a | **Substantive** | 3 master-row status advances (DSP-004-OBS-1 ✅ CLOSED + DSP-004-OBS-2 ✅ CLOSED + BUGR-006-LABEL-RESIDUAL-1 ✅ CLOSED) + 2 new CORR entries (DSP-004-OBS-1-CORR-1 + BUGR-006-LABEL-RESIDUAL-1-CORR-1) + 2 new ANALYST-class entries (ANALYST-Tier1R-FILES-1 + ANALYST-Tier1R-FILES-2 — 12th/13th instances of SIR §11.6 ITEM 1 audit-class, closing retroactively via §11.6 pattern resolution) + S### changelog entry |

**DSP-004 spec v1.1 amendment status:** None required. DSP-004 v1.0 / v1.1 parent closure is complete (S152); this Bundle is a successor work item, not a re-litigation. DSP-004 v1.1 spec file remains canonical for its own scope; this Bundle spec is the authority for its own scope.

**BRK-001 spec v1.1 amendment status:** None required. compute.py:807 emission `"WEEKLY_RESISTANCE (BRK-001 §8.1 MM-null fallback)"` is spec-correct per BRK-001 v1.1 §8.1; the defect is purely in the downstream output.py guard. Spec body unchanged.

**Detail-entry archive migration:** Defer per S143/S144/S145/S147/S149/S152/S154/S156/S157/S159/S161/S162/S163/S168 precedent — closure entries are flagged for next archive sweep session; not folded into this Phase 4 DIA scope.

---

## 11. Pre-Implementation Checklist (Brief §4 — implementation-side defense)

The Phase 2 Claude Code CLI implementer MUST execute the following verifications BEFORE any code edit and report `file:line` evidence anchors in Hand-Back §4 per ACP §6.5 canonical template.

### 11.1 §11.6 ITEM 3 — Shared-reference / partition-leak verification

- [ ] `_floor_entries` list at `transform.py:~L3309+` is the same list passed through BUGR-002 partition mechanism at `transform.py:~L3210-3250` (`_targets_above`) + `transform.py:~L3509-3562` (`_stops_below`).
- [ ] New EMA 21 entry (with `WEEKLY_EMA_21` label on Profile C) propagates consistently to whichever partition site receives it — verified by partition predicate (`_current_price < _ema21_price` → `overhead_levels[]`; `_current_price >= _ema21_price` → `hierarchy[]`).
- [ ] No partition site mutates the entry's `label` field after partition — verified by `grep` on entry-mutation sites within transform.py.

### 11.2 §11.6 ITEM 6 — Cross-spec layout audit

- [ ] DSP-004 v1.1 spec layout (`docs/specs/DSP004_Profile_C_Weekly_Anchor_Label_Spec_v1_1.md`) confirmed via `web_fetch` to have no §-numbering collision with this Bundle's new sites.
- [ ] BUGR-006 Label Fidelity Bundle spec (`BUGR006_Label_Fidelity_Bundle_Spec_v1_0.md`) confirmed via `web_fetch` to have no §-numbering collision with this Bundle's new sites.
- [ ] CNV-001 spec — verify `_LABEL_TIER_MAP` extension via `WEEKLY_EMA_21` doesn't conflict with CNV-001's tier-classification audit (CNV-001 reads `_LABEL_TIER_MAP` via `_annotate_conviction()` at the per-hierarchy-entry level; new vocabulary entry resolves cleanly to MA_DYNAMIC rank 3).

### 11.3 §11.6 ITEM 8 — Downstream-override-path audit

- [ ] `Extension_Anchor_Type` flat key — confirm via `grep -nE 'Extension_Anchor_Type' tbs_engine/*.py` that ONLY `output.py:2861-2878` writes this key; no override paths elsewhere.
- [ ] `Extension_Anchor_Label` flat key — same `grep` audit.
- [ ] `Profit_Target_Source` flat key — confirm the BRK-active branch at `output.py:2034+` is the only output.py write path that interacts with the BRK MM-null fallback semantics; compute.py:807/817/853 are upstream writers; no other engine module modifies this key on BRK MM-null fallback paths.

### 11.4 Vocabulary collision verification

- [ ] `grep -nE 'WEEKLY_EMA_21' tbs_engine/` returns ONLY the new entry in `_LABEL_TIER_MAP` + the new entry in `_ema21_label_map` after edits land — zero pre-existing occurrences (confirms the token is genuinely new vocabulary).
- [ ] CNV-001 `_annotate_conviction` resolution test — `_LABEL_TIER_MAP.get("WEEKLY_EMA_21") == ("MA_DYNAMIC", 3)` after Edit 3 lands.

### 11.5 Gate-cascade negative assertion

- [ ] `grep -nE 'Extension_Anchor_Type|WEEKLY_EMA_21|WEEKLY_SMA_200|BRK-001 fallback' tbs_engine/gates.py` returns zero matches post-edit.
- [ ] `TestBundleVerdictInvariance` passes on full pytest cohort.
- [ ] `TestBundleNotInGatesFile` passes (in-test `grep`-style negative assertion).

### 11.6 Module-import-graph acyclicity

- [ ] All 11 `tbs_engine/` modules import cleanly after edits (`python -c "from tbs_engine import compute, output, transform, ..."`); zero ImportError.
- [ ] No new imports added to output.py or transform.py.

---

## 12. Pre-Delivery Verification Checklist (SIR §9 — spec-side)

| Item | Status |
|---|---|
| **Content accuracy** | ✅ — All `file:line` anchors verified against `roescha/TBS_Master_App@master` current state via `web_fetch` at Phase 1 spec authoring (S###); all DQ-1 through DQ-8 outcomes captured in §2 Design Lock |
| **Internal consistency** | ✅ — §4 contracts match §6 test expectations; §3.2 scope-narrowing finding consistently reflected in §4.1 single-edit-site scope; §3.6 vocabulary audit consistent with §4.3 vocabulary extension |
| **Format integrity** | ✅ — Markdown SSoT per SIR §1.3 default for new spec deliverables; file destined for `/mnt/user-data/outputs/` then Operator-copy to working-tree root per SIR §1.5.2 transit policy |
| **Scope discipline** | ✅ — Three constituents only (DSP-004-OBS-1/-2 + BUGR-006-LABEL-RESIDUAL-1); explicit out-of-scope §1.3 enumeration; no scope creep into DSP-004 v1.x re-litigation, BUGR-006 v2.0 re-litigation, BRK-001 spec re-litigation, or DSP-001/-002/-003/-004 re-litigation |
| **Gate function verification** | ✅ — Zero gate touched per §5 + §9.1; verified by `grep` against gates.py |
| **Module import verification** | ✅ — Zero new imports per §5; acyclic graph preserved |
| **Bug Register updated (to be done at Bundle close)** | Pending — Phase 4 DIA cascade Step T2 |
| **DIA current** | ✅ — DIA scope enumerated §10 |

---

## 13. Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | S### Project chat post-S168 | Initial spec authored at Phase 1 lock per Operator DQ approval. Bundles DSP-004-OBS-1 + DSP-004-OBS-2 + BUGR-006-LABEL-RESIDUAL-1 per PEO Tier 1R framing. Track 1 cadence per ACP §7.1 (fails SIR §11.2 "no value-meaning changes on existing keys"). SIR §11.6 audit clean (items 3 / 6 / 8 applicable, all PASS); §11.6 ITEM 8 surfaced important scope-narrowing finding for DSP-004-OBS-1 (Profile C reaches only one branch in output.py extension_anchor dispatch, not two sites as original Bug Register entry suggested). Files-field correction sub-issues + ANALYST-class incident records to land at Phase 4 closure cycle per S147 / S168 precedent. |

---

**End of spec.**

**Companion artifacts to be authored at Phase 1 close:**

- `Tier_1R_Display_Hygiene_Bundle_Claude_Code_CLI_Implementation_Brief_v1_0.md` (per ACP §6.4 canonical 11-section template) — to be authored as the next deliverable after this spec is approved.

**Closing sign-off:**
- Spec authority: this document, v1.0.
- Authoring Analyst: Project-chat Analyst (post-S168 session).
- Operator decisions consumed at Phase 1: DQ-1 through DQ-8 per §2.
- Expected working-tree branch: `tier1r-display-hygiene-bundle` (off `roescha/TBS_Master_App@master`).

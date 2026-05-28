# Tier 1R — Display Hygiene Bundle Spec v1.0.1 (Corrigendum)

**Spec ID:** `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0_1`
**Version:** v1.0.1 (corrigendum supersession of v1.0)
**Status:** CLOSED corrigendum — supersedes `Tier_1R_Display_Hygiene_Bundle_Spec_v1_0.md` v1.0 for the enumerated sections; v1.0 retained as historical.
**Authored:** Session 169 (Tier 1R Phase 4 closure cascade, T3)
**Authority:** v1.0 body remains the canonical contract; this corrigendum amends only the transcription/identifier/line-reference defects enumerated in §1. **Zero contract change** — no DQ outcome, no engine edit, no test contract, no closure criterion is altered.
**Driver:** `Tier_1R_Display_Hygiene_Bundle_Phase2_Implementation_HandBack_v1_0.md` v1.0 — §6 DEV-1/-2/-3/-6 + §9 OI-1/OI-3/OI-4.

---

## 0. Nature of this corrigendum (SIR §5 form decision)

This document is issued as a **corrigendum schedule**, not a full re-issue of the 601-line v1.0 spec. Rationale:

- All amendments are **transcription / identifier / line-reference / code-block-presentation** fixes with **zero contract change**. No implementer-facing instruction changes meaning; the Phase 2 implementation (Hand-Back v1.0) already landed correctly *because* the implementer's Brief §4 audit caught these before any edit.
- Reconstructing the entire v1.0 body from the web-rendered source to re-issue it would risk introducing **new** transcription drift — precisely the failure class (`Tier1R-SPEC-CORR-1/-2`) being corrected here.
- Therefore: **v1.0.1 = v1.0 body verbatim, EXCEPT the deltas in §1 below.** A reader applies §1 against v1.0 to obtain the canonical v1.0.1 text.

This matches the SIR §1.3 spec-amendment convention (specs accumulate addenda/version bumps) and the corrigendum precedent class (DSP-002-CORR-1 S147; SIR-ACP-REF-1 S162).

---

## 1. Corrigendum Schedule

Each amendment is anchored to the v1.0 section where the defect actually occurs (verified against the v1.0 text), with the register entry it closes.

### Tier1R-SPEC-CORR-1 — `DAILY_EMA_21` transcription drift in the gate-cascade-negative-assertion set (Hand-Back DEV-1 / OI-1)

`DAILY_EMA_21` is a **pre-existing Profile-A/B token present in `gates.py:1138, 1153`** (REC-001 recovery-target construction — untouched by this bundle). It must therefore be **excluded** from the bundle's gate-cascade-negative-assertion ("zero match in `gates.py`") identifier set. v1.0 §11.5 + §12 + Brief §4.7 already exclude it correctly; the following three sites erroneously included it and are corrected:

| § (v1.0) | Original (v1.0) | Corrected (v1.0.1) |
|---|---|---|
| **§3.1** (engine source authority — `gates.py` bullet) | "…`grep` negative on `Extension_Anchor_Type` / `DAILY_EMA_21` / new label literals" | "…`grep` negative on `Extension_Anchor_Type` / `WEEKLY_EMA_21` / `WEEKLY_SMA_200` / `BRK-001 fallback` (the bundle's new/changed tokens). **Note:** `DAILY_EMA_21` is a *pre-existing* Profile-A/B token present at `gates.py:1138, 1153` (REC-001 recovery-target) and is deliberately **excluded** from the negative-assertion set — it is preserved, not introduced, by this bundle." |
| **§5** (Gate cascade impact paragraph — verifying `grep`) | "Verified by `grep -nE "Extension_Anchor_Type\|DAILY_EMA_21\|WEEKLY_EMA_21\|WEEKLY_SMA_200\|BRK-001 fallback" tbs_engine/gates.py` returning zero matches…" | "Verified by `grep -nE "Extension_Anchor_Type\|WEEKLY_EMA_21\|WEEKLY_SMA_200\|BRK-001 fallback" tbs_engine/gates.py` returning zero matches… (`DAILY_EMA_21` excluded — pre-existing REC-001 token at `gates.py:1138, 1153`, not a bundle-introduced identifier)" |
| **§6.1** (`TestBundleNotInGatesFile` identifier list) | "…zero matches for `Extension_Anchor_Type`, `DAILY_EMA_21`, `WEEKLY_EMA_21`, `WEEKLY_SMA_200`, `BRK-001 fallback` substrings" | "…zero matches for `Extension_Anchor_Type`, `WEEKLY_EMA_21`, `WEEKLY_SMA_200`, `BRK-001 fallback` substrings (`DAILY_EMA_21` deliberately excluded — pre-existing REC-001 token at `gates.py:1138, 1153`; a witness test documents its pre-existing presence)" |

> **Cross-check:** v1.0 §11.5 already reads the corrected (excluding) form and requires **no change**. This confirms the defect was a §3.1/§5/§6.1 narrative transcription slip, not a contract error — the authoritative checklist (§11.5) and the Brief (§4.7) were always correct.

### Tier1R-SPEC-CORR-2 — `_LABEL_TIER_MAP` → `_CONVICTION_TIER_MAP` rename + §4.3 elided VWAP rows + `compute.py` line-ref (Hand-Back DEV-2 / DEV-3 / DEV-6 / OI-4)

**(a) Identifier rename (DEV-2).** The actual engine dict is `_CONVICTION_TIER_MAP` (`transform.py:165`, consumed by `_annotate_conviction()` @ `transform.py:247`). v1.0 names it `_LABEL_TIER_MAP`; the spec's `from tbs_engine.transform import _LABEL_TIER_MAP` sanity command raises `ImportError`. Rename **every** occurrence of `_LABEL_TIER_MAP` → `_CONVICTION_TIER_MAP`:

| § (v1.0) — true occurrence | Context |
|---|---|
| **§2 DQ-3** | "direct mirror in `_LABEL_TIER_MAP` (transform.py:175-180)" → `_CONVICTION_TIER_MAP` |
| **§3.6** (vocabulary collision table, row 1) | "`_LABEL_TIER_MAP` (transform.py:175-180)" → `_CONVICTION_TIER_MAP`. *(The separate `_LABEL_VOCAB_MAP` row is a different dict and is NOT renamed — no defect.)* |
| **§4.3** (title + behavior text) | "`_LABEL_TIER_MAP.get("WEEKLY_EMA_21")`" → `_CONVICTION_TIER_MAP.get(...)` |
| **§5** (pipeline table, Edit 3 "Writes" cell) | "`_LABEL_TIER_MAP` (module-level dict)" → `_CONVICTION_TIER_MAP` |
| **§6.1** (`TestDSP004OBS2VocabularyExtension`) | "`_LABEL_TIER_MAP.get("WEEKLY_EMA_21") == ("MA_DYNAMIC", 3)`; `_LABEL_TIER_MAP.get("DAILY_EMA_21")…`" → `_CONVICTION_TIER_MAP.get(...)` |
| **§11.4** (vocabulary collision verification) | "`_LABEL_TIER_MAP.get("WEEKLY_EMA_21") == ("MA_DYNAMIC", 3)`" → `_CONVICTION_TIER_MAP.get(...)` |

**Section-citation correction (vs Hand-Back OI-4):** OI-4 cited "§3.3 / §11.1.2" for the rename. Those are imprecise — v1.0 §3.3 is the *ITEM-3 partition-leak finding* (no dict reference) and there is **no §11.1.2**. The true occurrences are the six rows above (§2 DQ-3, §3.6, §4.3, §5, §6.1, §11.4). v1.0.1 renames at the true sites; the OI-4 citation drift is itself logged as part of this corrigendum.

**(b) §4.3 elided live rows + block-replace → surgical insert (DEV-3).** v1.0 §4.3 pre/post code blocks show the `MA_DYNAMIC` comment immediately followed by `DAILY_EMA_21`, omitting the two live rows `SESSION_VWAP` (`transform.py:174`) and `AVWAP_10BAR` (`transform.py:175`) that sit between them on master. A literal block-replace of the v1.0 block would **delete** those two rows. §4.3 is corrected to a **surgical single-row insert** directive:

> *Corrected §4.3 edit directive:* Insert the single line `"WEEKLY_EMA_21":   ("MA_DYNAMIC", 3),` immediately **after** the existing `"DAILY_EMA_21": ("MA_DYNAMIC", 3),` row, and refresh the `MA_DYNAMIC` comment. **Do NOT block-replace** — the `MA_DYNAMIC` group on master also contains `SESSION_VWAP` (L174) and `AVWAP_10BAR` (L175) between the comment and `DAILY_EMA_21`; these must be preserved verbatim. Net `_CONVICTION_TIER_MAP` size **19 → 20**.

*(This is exactly the surgical approach the Phase 2 implementer used per Hand-Back §3 Edit 3 / DEV-3; v1.0.1 brings the spec directive into line with what was correctly implemented. Exact tier tuples for `SESSION_VWAP`/`AVWAP_10BAR` are intentionally not restated — the directive mandates their preservation rather than reproducing values not needed for the insert.)*

**(c) `compute.py` MEASURED_MOVE line-ref (DEV-6).** v1.0 §4.4's post-fix comment block cites `compute.py:765` for the MEASURED_MOVE emission form; the actual write is `compute.py:766` (off-by-one). Correct the single comment line:

| § (v1.0) | Original | Corrected |
|---|---|---|
| **§4.4** (output.py comment block, MEASURED_MOVE line) | `#   - "MEASURED_MOVE (BRK-001 post-breakout target)" (compute.py:765)` | `#   - "MEASURED_MOVE (BRK-001 post-breakout target)" (compute.py:766)` |

> The other three forms (`compute.py:807`, `:817`, `:853`) are correct in v1.0 and unchanged. This is a cosmetic comment line-ref only — the engine guard behaviour is unaffected. (Note: the off-by-one was reproduced verbatim into the post-edit `output.py:2064-2066` comment per the verbatim-edit directive; that source-side comment is a known cosmetic carry — not re-touched here, no behaviour impact.)

### §9.3 Consumer-Audit enumeration correction (Hand-Back DEV-5 / OI-3 — closes the spec side of `ANALYST-Tier1R-AUDITGAP-2`)

v1.0 §9.3 ("Test suite touchpoints" → "Other tests") states: *"Pre-spec-delivery audit identified no Profile C `"SMA_200"` / `"DAILY_EMA_21"` literal assertions in other test files."* This was **incomplete** — the Phase 2 full-cohort surfaced **5 pre-existing assertions across 4 files** broken by the bundle's intended changes (HALT H2). §9.3 "Other tests" row is corrected to **enumerate** them:

> *Corrected §9.3 "Other tests" entry:* Four pre-existing test files carried assertions on the bundle's changed surface and were updated under in-session Operator authorization (Hand-Back §6 DEV-5 / §9 OI-5):
> 1. `tests/unit/test_pa001_phase3_hierarchies.py:486` + `:684` — Profile C `e["label"] == "DAILY_EMA_21"` → `"WEEKLY_EMA_21"` (Edit 2 relabel; mirrors the already-updated `WEEKLY_SMA_50` row at `pa001:479`).
> 2. `tests/unit/test_cnv001_conviction_tier.py:253` — `len(_CONVICTION_TIER_MAP) == 19` → `20` (Edit 3 vocab-add tripwire).
> 3. `tests/unit/test_bundle1_regression.py:527` — `len(_CONVICTION_TIER_MAP) == 19` → `20`.
> 4. `tests/unit/test_ema50001_context_ema_50.py:824` — `len(_CONVICTION_TIER_MAP) == 19` → `20`.
>
> The "Two-Pass Consumer Audit Discipline" (S152 `DSP-004-AUDIT-GAP-1`) requires enumerating consumer test files by *actual assertion content* (read bodies), not by file-name heuristic; the v1.0 pre-spec audit did not, which is logged as `ANALYST-Tier1R-AUDITGAP-2` (consumer-audit-enumeration variant, §11.6 audit-class). Legacy method names retaining the historical count (`test_total_entry_count_is_19`, `test_conviction_tier_map_exactly_19_entries`, `test_conviction_map_still_19_entries`) now assert `== 20`; rename deferred per OI-5 (out of this corrigendum's scope).

---

## 2. §11.6 re-audit (corrigendum-side)

The corrigendum amendments touch **narrative / identifier / test-enumeration** surfaces only — no engine contract, no new gate input, no verdict surface. The v1.0 §11.6 audit (items 3 / 6 / 8 applicable, all PASS) stands; this corrigendum adds two findings that feed the **§11.6 v-next refinement candidate** (carried to PEO + SIR §11.6 v-next at Phase 4 T5):

1. **Enumerative-section-token discipline** (`ANALYST-Tier1R-AUDITGAP-1`, §11.6 12th instance): a gate-cascade-negative grep run only against new/changed identifiers will miss a *pre-existing* token wrongly enumerated in a narrative/test-list section (here `DAILY_EMA_21` in §3.1/§5/§6.1). Candidate new §11.6 item: *"when a spec section enumerates a gate-negative identifier set, audit each listed token against current `gates.py` — exclude any pre-existing token and annotate it as preserved-not-introduced."*
2. **Consumer-audit-enumeration discipline** (`ANALYST-Tier1R-AUDITGAP-2`, §11.6 13th instance; `DSP-004-AUDIT-GAP-1` lineage): the §9.3 consumer audit must enumerate test files by actual assertion content (`grep` the changed literals + any count tripwires), not by file-name heuristic.

Neither is among the current 8 §11.6 items — hence neither ITEM 1 (as v1.0 DQ-8 supposed) nor ITEM 8 (as Hand-Back OI-2 supposed); both are **new sub-disciplines**.

---

## 3. Carry-forward statement

All v1.0 content not listed in §1 is carried forward **verbatim** as the canonical v1.0.1 text, including: §1 Purpose/Scope, §1.2 In-scope table, §1.3 Out-of-scope, §1.4 Severity, §2 Design Lock (DQ-1/-2/-4/-5/-6/-7/-8 unchanged; DQ-3 identifier-renamed only), §3.2 ITEM-8 scope-narrowing finding, §3.3 ITEM-3 finding, §3.4/§3.5 audit summaries, §3.6 collision audit (identifier-renamed only), §4.1/§4.2/§4.4 (DEV-6 comment line excepted), §5 (gate-grep + Writes-cell excepted), §6 test plan (§6.1 excepted), §7 closure criteria, §8 worked examples, §9.1/§9.2 (§9.3 excepted), §10 DIA scope, §11.1–§11.6 (§11.4 identifier-renamed only), §12 pre-delivery checklist.

**Closure-criteria impact:** none. v1.0 §7 criteria #1–#7 are unchanged; this corrigendum is the §5/§7 "spec verified against final engine state" deliverable.

---

## 4. Document History

| Version | Date | Change |
|---|---|---|
| v1.0 | S### (post-S168) Project chat | Initial Phase 1 spec. Three constituents (DSP-004-OBS-1/-2 + BUGR-006-LABEL-RESIDUAL-1). Track 1 per ACP §7.1. §11.6 audit (items 3/6/8 PASS); §3.2 ITEM-8 scope-narrowing for DSP-004-OBS-1. |
| **v1.0.1** | **2026-05-28 (S169)** | **Corrigendum (this document).** Tier1R-SPEC-CORR-1 — remove `DAILY_EMA_21` from the gate-negative-assertion set at §3.1 / §5 / §6.1 (pre-existing REC-001 token at `gates.py:1138,1153`; §11.5 already correct). Tier1R-SPEC-CORR-2 — (a) rename `_LABEL_TIER_MAP` → `_CONVICTION_TIER_MAP` at §2 DQ-3 / §3.6 / §4.3 / §5 / §6.1 / §11.4 (true occurrences; OI-4's "§3.3/§11.1.2" citations corrected); (b) §4.3 block-replace → surgical single-row insert preserving `SESSION_VWAP`(L174)/`AVWAP_10BAR`(L175), size 19→20; (c) §4.4 comment `compute.py:765`→`766`. §9.3 consumer-audit enumerated to the 4 updated test files (closes spec side of ANALYST-Tier1R-AUDITGAP-2). Zero contract change. §11.6 v-next refinement candidate (enumerative-section-token + consumer-audit-enumeration) surfaced. Issued as corrigendum-schedule supersession per §0. |

---

**End of corrigendum.**

**Promotion (Operator executes — Analyst flags + cannot push):** `docs/specs/Tier_1R_Display_Hygiene_Bundle_Spec_v1_0_1.md` (v1.0 retained as historical alongside). Companion Phase 4 cascade: Bug Register S169 (T2, delivered) + Doc 2 v8.66 / Doc 8 v8.7.66 / Doc 7 v8.5.56 / EEM v2.42 verify-only / README v8.6.35 / PEO v9.27 (T4-T5, pending).

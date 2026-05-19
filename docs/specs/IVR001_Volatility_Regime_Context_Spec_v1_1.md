# IVR-001 — IV/HV Volatility Regime Context — Spec v1.1

> **POST-CLOSED AMENDMENT POINTER HEADER (authored S144, May 5, 2026; updated S159, May 19, 2026 for v1.1 substantive amendment)**
>
> **This spec was CLOSED at body version v1.0 (April 13, 2026); the spec body now stands at v1.1 (May 19, 2026, S159) following a substantive amendment authored under the RLY-001 v1.0 § 5 directive at Tier 1K Bundle 4A Phase 4 closure.** Pre-v1.1, all body content was preserved verbatim as authored at v1.0; post-CLOSED amendments to engine behaviour were recorded in the Amendment Ledger below this header. **v1.1 changes:** new §4.5 At Rally Maturity context-interpretation matrix inserted between §4.4 At Recovery and the renumbered §4.6 Default (formerly §4.5 Default at v1.0); §5.2 / §6.1 / §6.2 caution_factor body language updated to acknowledge the new §4.5 deviation (COMPLACENT × RALLY_MATURE emits caution_factor — a documented deviation from the §4.1/§4.2 "ELEVATED or EXTREME only" convention, justified in new §4.5.2). Readers should consult the **Amendment Ledger** below this header for pre-v1.1 post-CLOSED corrections AND the new §4.5 / §4.5.2 substantive content for the RLY-001 v1.1 integration. Pre-v1.1 directives still apply: when the spec body and the canonical engine source diverge, the canonical source wins (the IBKR-API-pattern corrections at S116/S119/S121 remain authoritative over body §3.1 / §7.1 language at the data-fetch level).
>
> **Format note:** This file was originally produced as a `.docx` artifact at S114 (April 13, 2026) and stored as text-as-`.docx` in project storage. At S144 (May 5, 2026), the file was opportunistically converted to `.md` per Session Integrity Rules §1.2 ("Opportunistic Migration") as part of the IVR-001-BUG-4-SUB-1 / IVR-001-BUG-4 / BUG-IVR-2 Tier 2A closure DIA pass. The conversion preserves the spec body content character-for-character. The `.md` file replaces the `.docx` as the canonical spec artifact going forward; the original `.docx` is retained as legacy (not deleted, just superseded). At S159 (May 19, 2026), v1.1 is published as a new file `IVR001_Volatility_Regime_Context_Spec_v1_1.md` superseding the v1.0 `.md` per SIR §1.3 (new spec versions are standalone files; v1.0 retained as historical record).
>
> **Recursive precedent observation (logged for SIR §11 augmentation candidacy at S144; strengthened at S159):** This pointer header convention was originally specified at S119 via IVR-001-BUG-4 DQ-1 Option C resolution, but the file edit never landed (the pointer header was DIA-pending alongside the `.docx → .md` conversion bundle which carried 24 sessions S120 → S121 → ... → S143 → S144 before being applied together at S144). SBO-001-BUG-1 detail entry (S134) and BUGR-006-FORMAT-1 detail entry (S140-cont) both cited "IVR-001 precedent pattern" as originating template — but in practice the IVR-001 pointer header was not landed until S144. SBO-001 spec S134 Turn 4 was the first such artifact actually landed in the project. S144 retroactively closes the recursive citation loop by authoring this header for the first time. See bug `IVR-001-FORMAT-1` (✅ CLOSED S144 same-session) for full discovery context and the SIR §11 augmentation candidacy proposal. **S159 strengthening:** ANALYST-RLY-001-SPEC-3 logged at S159 Phase 4 closure (cross-spec audit gap — RLY-001 v1.0 §5.3 did not audit existing IVR-001 §4.5 Default before drafting "new §4.5 At Rally Maturity" enumeration; resolved at IVR-001 v1.1 via renumbering existing §4.5 → §4.6). 5th confirmed instance of the SIR §11 unified pre-spec-delivery checklist augmentation candidate class.

## Amendment Ledger

| Session | Date | Capability / Bug | Lifecycle | Implementation Pattern | Spec Body Affected | Validation |
|---|---|---|---|---|---|---|
| S116 | April 14, 2026 | BUG-IVR-2 | 🔴 IDENTIFIED S116 → ✅ CLOSED S116 (premature — see S120) → 🔴 REOPENED S120 → ✅ CLOSED S144 lockstep | Original fix at S116: separate `reqMktData(contract, '106', True, False)` snapshot+generic-ticks call for Profile B/C IV after the existing price data call. **LATER INVALIDATED** — IBKR rejects this combination with Error 321 ("Snapshot market data subscription is not applicable to generic ticks"). The S116 fix never functioned on the live IBKR gateway; "live validation" on SNDK/MRVL/STM did not actually exercise the IV path. Corrected at S121 via IVR-001-BUG-4-SUB-1 helper. | §3.1 ("Zero new API connections" — accurate per S116 design intent; IBKR-rejected pattern still uses existing connection); §7.1 (data.py changes — original 10-line estimate accurate; superseded by SUB-1 streaming helper). | S116 SNDK/MRVL/STM "live validation" was retrospectively invalidated at S120; S144 lockstep close validates corrected fix end-to-end via SUB-1 RTH 4-run sweep. |
| S119 | April 17, 2026 | IVR-001-BUG-4 | 🔴 IDENTIFIED S119 → 🟠 SPECIFIED S119 → 🟢 IMPLEMENTED S120 → 🟠 PARTIALLY IMPLEMENTED S120 (rolled back when SUB-1 surfaced) → ✅ CLOSED S144 lockstep | DQ-1 resolution Option C: this post-CLOSED pointer header convention specified at S119 (header authored fresh at S144 — bundle was DIA Pending across 24 sessions; see IVR-001-FORMAT-1). DQ-2 resolution Option A: drop generic tick `'106'` from primary Profile A `reqMktData` (becomes `''` for price/volume only); IV fetch moved to a separate snapshot-mode call after primary cancel — matches Profile B/C pattern and BUG-IVR-2 precedent. (B) gates.py: `_IVR_REGIME_DESC["UNAVAILABLE"]` description extended to include "IBKR tick 106 not populated (can occur after hours on otherwise-liquid options chains)" as a possible cause — working live since S120. (A) data.py Profile A IV fetch corrected at S121 via IVR-001-BUG-4-SUB-1 streaming helper. | §3.1 ("Zero new API connections" — body text inaccurate post-fix because Profile A originally had IV on the primary streaming call and was moved to a separate snapshot call; superseded again at S121 by streaming helper); §7.1 (Profile A IV fetch implementation — superseded). | S120 ON Semiconductor live validation surfaced Error 321 on the (A) half despite (B) half rendering correctly; S121 corrected fix; S144 RTH 4-run sweep on AAPL/VRT × A/B confirms (A) functional alongside (B) end-to-end. |
| S120/S121 | April 17, 2026 | IVR-001-BUG-4-SUB-1 | 🔴 IDENTIFIED S120 → 🟠 SPECIFIED S120/S121 (DQ-1 + DQ-3 resolved S120, DQ-2 resolved S121 Option C) → 🟢 IMPLEMENTED S121 → 🟢 SYNCED S144 → ✅ CLOSED S144 (single-session SYNCED → CLOSED cascade via RTH validation) | Streaming-mode helper `_fetch_iv_streaming()` extracted in `tbs_engine/data.py` (~30 LOC): streaming `reqMktData(contract, '106', False, False)` + Option C poll-loop budget (2s initial sleep + up to 4×1s polls, 6s max wall-time, exit early when `impliedVolatility` populates non-NaN). Both Profile A IV block (~L758-770) and Profile B/C IV block (~L788-799) replaced with single-line helper calls — single point of maintenance. Variable name `_iv_raw_from_mktdata` preserved for zero downstream interface change. **NOT** the original §3.1 pattern (snapshot+generic-ticks combination — IBKR-rejected with Error 321). | §3.1 (data layer integration — superseded; IV fetch is now streaming + poll-loop, not snapshot+generic-ticks); §7.1 (Profile A + Profile B/C IV fetch — superseded by shared helper). | (a) AH 6-run sweep S121 across ON Profile A (61.53% ALIGNED — original failure case resolved), SNDK Profile B (111.47% COMPLACENT), TLT Profile C (10.22% COMPLACENT), ON Profile C (61.53%), TLT Profile A (10.22% ALIGNED), TLT Profile B (10.22% COMPLACENT) — all returned real IV where previously null; cross-profile IV consistency for same underlying confirms helper functional. (b) RTH 4-run sweep S144 across AAPL Profile B (23.06 ALIGNED at 10:14:50 ET), AAPL Profile A (23.05 ALIGNED at 10:15:27), VRT Profile A (64.21 ALIGNED at 10:16:03), VRT Profile B (64.21 ELEVATED at 10:17:04) — all stderr-clean (no Error 321); cross-profile IV stability per underlying + cross-underlying variability + sub-3s wall-time cadence (4 runs spanned 2m 14s; if Option C maxed at 6s × 4 = 24s of IV-fetch the cadence would show it — actual cadence consistent with <3s = poll-loop never iterated, IV populated within 2s initial sleep). RTH happy-path early-exit contract met. VRT/B regime=ELEVATED also exercised IVR-001 caution-factor propagation end-to-end (`volatility_regime.caution_factor` → `action_summary.caution_factors[]`). |
| S122 | April 18, 2026 | BUG-IVR-3 | 🔴 IDENTIFIED S121 → ✅ CLOSED S122 | Profile-conditional HV annualization factor: A→252 (daily), B→52 (weekly), C→12 (monthly). Pre-fix: `math.sqrt(252)` unconditional, inflating HV ~2.2× on Profile B and ~4.6× on Profile C. Two lines added (dict lookup), one line changed (sqrt call). Two-line fix to `tbs_engine/data.py::_hv_30d` only. | §3.1 ("HV Lookback") and §3.2 (Computation): `HV_LOOKBACK_DAYS = 30` accurate, but the annualization-factor implementation was Profile-A-only correct in the original spec; Profile B/C now corrected. | TLT cross-profile live sweep S122: corrected HV on B (~8.4% vs pre-fix 18.43%) and C (~13.4% vs pre-fix 61.43%) yielding correct regime labels. Profile A regression safe. 6 unit tests added. |
| S144 | May 5, 2026 | IVR-001-FORMAT-1 (this pointer header + opportunistic `.docx → .md` conversion) | 🔴 IDENTIFIED S144 → 🟠 SPECIFIED + 🟢 IMPLEMENTED + 🟢 SYNCED + ✅ CLOSED S144 same-session | Format integrity + Doc Inconsistency: on-disk `IVR001_Volatility_Regime_Context_Spec_v1_0.docx` was text-as-`.docx` (`file` reports `Unicode text, UTF-8 text, with very long lines (790)`, NOT `Microsoft Word 2007+`) AND lacked the S119 DQ-1 Option C post-CLOSED pointer header that was specified-but-never-landed (bundle had been carrying 24 sessions). Per Operator approval at S144 kick-off: opportunistic `.docx → .md` conversion bundled into S144 Tier 2A closure DIA per SIR §1.2 (this DIA pass's first textual touch of IVR-001 spec for amendment qualifies); pointer header authored at conversion time, modeled on SBO-001 spec S134 Turn 4 pattern + content sourced from IVR-001-BUG-4 detail entry's S119 DQ-1 Option C resolution narrative + §3.1 "Zero new API connections" body inaccuracy that originally triggered the S119 amendment requirement. Original `.docx` retained as legacy artifact per SBO-001 / BUGR-006-FORMAT-1 precedent. Spec body content preserved verbatim character-for-character per handoff §4.5. | Meta-layer only — pointer header + this Amendment Ledger added to top of file; spec body §1 through §11 untouched. | Spec body byte-equivalence verified between converted `.md` and original text-as-`.docx` source — zero textual differences in spec body content; only file extension, added pointer-header block, and Amendment Ledger differ. |
| S159 | May 19, 2026 | RLY-001 v1.0 §5 substantive amendment (Tier 1K Bundle 4A Phase 4 closure) — v1.0 body → v1.1 body | 🟠 SPECIFIED S158 (RLY-001 v1.0 §5 directive) → 🟢 SYNCED S159 (this v1.1 amendment authored Project chat Turn 2) → ✅ CLOSED at S159 Phase 4 final batch (Turn 5, lockstep with RLY-001 parent closure) | **Substantive body amendment** (first since v1.0 publication): new §4.5 At Rally Maturity context-interpretation matrix inserted between §4.4 At Recovery and the renumbered §4.6 Default. Matrix content: 4 regime cells covering RALLY_MATURE × {COMPLACENT, ALIGNED, ELEVATED, EXTREME} with interpretation labels DELAYED CLIMAX RISK / MATURE TREND / CLIMAX RISK / EXHAUSTION SIGNAL. Convention deviation in new §4.5.2: COMPLACENT × RALLY_MATURE emits caution_factor (differs from §4.1/§4.2 where COMPLACENT is benign — rationale: complacency at peak is the most insidious climax-run setup, classical "blow-off top with no warning signs" pattern per Minervini/O'Neil). Caution_factor string templates for 3 of 4 cells (ALIGNED unchanged at null). Existing §4.5 Default (TRENDING state, no special context) renumbered to §4.6 with verbatim content. §5.2 / §6.1 / §6.2 caution_factor body language updated to acknowledge the new §4.5 deviation (minor wording: "ELEVATED or EXTREME (plus COMPLACENT × RALLY_MATURE per §4.5)" replaces "ELEVATED or EXTREME" at the three caution_factor reference sites). READ-PATH NEUTRAL wording for §4.5 trigger: "When the RALLY_MATURE classification is active" / "consumes the RALLY_MATURE signal" rather than flat_metrics-specific "_gate_volatility_regime reads Rally_Maturity_Label from flat_metrics" (the implementation-path detail lives in RLY-001 spec §3.4 / §4.4, not in IVR-001 §4.5 spec content). | §4 (Context Interpretation Matrix) — substantive: new §4.5 + renumber §4.5 Default → §4.6; §5.2 (Advisory-Only at Launch) — surgical wording update for caution_factor scope; §6.1 (Grouped Output transform.py) — caution_factor table row wording update; §6.2 (Action Summary) — caution_factor scope wording update. **Unchanged at v1.1:** §1 / §2 / §3.1 / §3.2 / §3.3 / §3.4 / §4.1-§4.4 / §4.6 (content from former §4.5 Default) / §5.1 / §5.3 / §5.4 / §6.3 / §7 / §8 / §9 / §10 / §11. | Implementation already shipped via RLY-001 Phase 2 standalone session (S158, prior chat) with verdict-invariance test class `TestRLY001VerdictInvariance` passing — IVR-001 caution_factor emission scope extension is bitwise-additive on the existing `action_summary.caution_factors[]` array. Phase 3 live validation per RLY-001 §6.2 cohort: CRWD Profile A RALLY_MATURE positive witness verified end-to-end (§4.5 ALIGNED × RALLY_MATURE → MATURE TREND propagation confirmed); 7 NORMAL witnesses + 2 defensive nulls covered. Outstanding: Profile C edge + RALLY_MATURE × {COMPLACENT/ELEVATED/EXTREME} caution_factor cells (PHASE3-RESIDUAL, non-blocking). Cross-spec audit gap discovered at this v1.1 amendment authoring: RLY-001 v1.0 §5.3 enumeration "§4.3 (existing context) → §4.4 (existing context) → §4.5 At Rally Maturity (NEW)" did not audit existing IVR-001 v1.0 §4.5 Default — logged as `ANALYST-RLY-001-SPEC-3` at S159 Phase 4 closure, strengthening SIR §11 unified pre-spec-delivery checklist augmentation candidacy from 4 → 5 confirmed instances. |

## Reading Guidance

When consulting this spec, read in this order:
1. **This pointer header + Amendment Ledger first** — establishes which post-CLOSED corrections supersede spec body claims.
2. **Spec body §1 (Purpose), §2 (Research Basis), §4 (Context Interpretation Matrix), §5 (Gate Behaviour) §5.1–§5.4, §6 (Output Schema), §10 (Vocabulary Constraints), §11 (Related Items)** — accurate as authored; not affected by post-CLOSED amendments.
3. **Spec body §3 (Signal Design)** — read with caution: §3.1 (Inputs) "Zero new API connections" claim is post-CLOSED amended (see ledger S116/S119/S121); §3.2 (Computation) HV annualization pattern is post-CLOSED amended for Profile B/C (see ledger S122); §3.3 (Regime Classification) and §3.4 (Tuneable Constants) accurate as authored.
4. **Spec body §7 (Implementation Scope)** — read with caution: §7.1 (Files Modified) data.py 10-line estimate accurate at original scope; the IV fetch pattern itself superseded by SUB-1 streaming helper (see ledger S121). §7.2 (Zero-Change Confirmation) and §7.3 (Consumer Impact) accurate as authored.
5. **Spec body §8 (Test Cases) and §9 (Documentation Impact Assessment)** — accurate as authored.

For canonical engine behaviour, the source-of-truth is `tbs_engine/data.py` + `tbs_engine/gates.py` + the most recent Doc 2 §IV / Doc 8 §II Layer 2 entries (currently Doc 2 v8.57, Doc 8 v8.7.57 as of S144). When the spec body and the canonical source diverge, the canonical source wins.

---

IVR-001  |  IV/HV Volatility Regime Context  |  Spec v1.0

**IVR-001**

Implied Volatility / Historical Volatility Regime Context

TBS Specification Document  |  Version 1.0  |  April 13, 2026

| **Status** | SPECIFIED |
| --- | --- |
| **Type** | Enhancement (Engine-Native Advisory Gate) |
| **Severity** | Low -- informational advisory. No hard gate at launch. |
| **Profile Scope** | All profiles (A, B, C, ETF). Interpretation adapts by engine state and trigger. |
| **Origin** | Session 114 (April 13, 2026). Evolved from EXT-003 concept (Options-Informed Extension Confluence). Operator-driven generalisation: IV/HV ratio provides universal trade context beyond extension. |
| **Prerequisites** | PA-001 (CLOSED). Asset Gates HV computation (existing). IBKR reqMktData infrastructure (PE-42, existing). |
| **Estimated Effort** | 1-2 sessions (implementation) + 0.5 session (DIA sync) |
| **Companion Item** | IVR-001-CAL-1: Threshold calibration review after 3-6 months live data. |

# 1. Purpose

IVR-001 introduces an engine-native Implied Volatility / Historical Volatility (IV/HV) ratio as a universal trade context signal. The ratio answers one question for every evaluation: does the options market agree with the current price regime?

Unlike OI-derived metrics (put wall, call wall, max pain) which lag price action on fast-moving tickers, IV is computed from live option prices and responds to current market conditions. Combined with historical volatility (which the engine computes from daily close data), the ratio produces an instantaneous read on whether the options market is pricing more, less, or the same amount of risk as the stock has been delivering.

The signal is generalised across all engine states and triggers. The same ratio value carries different implications depending on whether the stock is at extension, pullback, breakout, or recovery. The engine produces a state-aware interpretation label alongside the raw ratio, giving the Operator a single human-readable assessment.

# 2. Research Basis

The design is grounded in the following established findings from quantitative volatility research:

- **Volatility Risk Premium (VRP): **IV exceeds realised volatility approximately 85% of the time across a range of market environments (S&P 500, 1990-present). The average magnitude of overstatement is 2-4 percentage points. This persistent gap is the insurance premium options buyers pay. Implication: IV being slightly above HV is normal. Only significant divergence is actionable. [CAIA / Parametric Research, 2024; Carr & Wu, Review of Financial Studies, 2009]

- **Predictive Power: **Bollerslev, Tauchen, and Zhou (Review of Financial Studies, 2009) demonstrated that the VRP is a statistically significant predictor of future equity returns. High VRP environments historically favour equity exposure because the market prices more pessimism than typically materialises. Implication: elevated IV/HV at a pullback is contrarian-supportive, not cautionary.

- **Mean Reversion: **The IV-HV spread is mean-reverting. Extreme readings normalise within days. This aligns with Profile A swing trade horizons (2-5 day holds). An EXTREME reading at entry is likely to compress by exit. [Volatility Box Research, 2026; MenthorQ VRP Guide]

- **Lookback Matching: **Comparing 30-day HV to 30-day IV produces an apples-to-apples baseline. Mismatched lookback periods (e.g., 10-day HV to 30-day IV) produce misleading signals. The TBS engine computes HV from ~30 days of daily closes, matching the forward period of IBKR model-implied IV. [Volatility Box Research; Schwab/Thinkorswim methodology]

- **Magnitude Not Direction: **IV does not predict price direction, only magnitude. It measures expected movement size, not whether the stock will go up or down. Implication: the signal is advisory context, not a directional filter. This supports the pure advisory architecture (no hard gate at launch). [Schwab Options Education; Volatility Box Research]

# 3. Signal Design

## 3.1 Inputs

| **Input** | **Source** | **Mechanism** | **Notes** |
| --- | --- | --- | --- |
| Current IV | IBKR tick 106 | Added to existing reqMktData call in data.py (PE-42 infrastructure). Returns model-implied IV for the underlying as a single float. | Zero new API connections. One additional generic tick on an existing request. Annualised percentage. |
| 30-Day HV | Engine-computed from df_ctx | Standard deviation of daily log returns over 30 trading days, annualised. ~3 lines of code in data.py. | Self-contained. No cross-layer dependency on Asset Gates. CLI works without orchestrator. Values will closely match Asset Gates HV. |

## 3.2 Computation

The ratio is computed as: IV / HV. The result is a dimensionless number centered around 1.0. Values above 1.0 mean the options market expects more future movement than the stock has recently delivered. Values below 1.0 mean the options market is pricing less movement than realised.

## 3.3 Regime Classification

The ratio is classified into four bands. Thresholds are implemented as tuneable constants in gates.py.

| **Label** | **Ratio Range** | **Description (surfaced in output desc field)** |
| --- | --- | --- |
| **COMPLACENT** | < 0.8 | Options market pricing LESS risk than the stock has been delivering. Rare condition (~15% of observations historically). The market is underestimating actual price movement. At breakout: dealers are not positioned for this move -- mechanical follow-through is likely as hedging demand creates buying pressure (high-quality breakout confirmation). At extension: supports continuation -- the options market does not see reversal risk. At pullback: calm conditions with no capitulation signal -- standard pullback, not fear-driven. |
| **ALIGNED** | 0.8 - 1.2 | Options market and recent price action agree on volatility magnitude. IV exceeds HV by a normal insurance premium (2-4 percentage points is typical -- IV exceeds HV approximately 85% of the time historically). The current price regime is orderly. No additional volatility risk signal. Defer to structural assessment from the engine gates. |
| **ELEVATED** | 1.2 - 1.5 | Options market pricing moderately more risk than recent price action justifies. At pullback near structural floor: contrarian-supportive signal -- elevated fear at structural support often marks capitulation, which historically precedes positive equity returns (VRP research). At extension: early warning that the options market sees reversal risk the chart does not yet show. At breakout: the move may already be priced into options -- follow-through could be limited as options traders have already positioned. At recovery: higher risk but higher asymmetry if the base holds. |
| **EXTREME** | > 1.5 | Options market pricing significantly more risk than the stock has been delivering. Strong signal in all contexts. At pullback: extreme fear -- highest asymmetry if the structural floor holds, as the market is pricing a collapse that may not materialise. At extension: danger -- smart money may be hedging a reversal that is not yet visible in price action. At breakout: move is heavily priced in -- dealers already positioned, limited mechanical follow-through expected. At recovery: maximum asymmetry -- the market is uncertain about the base, but if it holds, the VRP compression alone generates positive return as IV normalises. Historically mean-reverting -- extreme readings normalise within days, aligning with Profile A swing trade horizons (2-5 day holds). |

## 3.4 Tuneable Constants

| **Constant** | **Value** | **Location** | **Rationale** |
| --- | --- | --- | --- |
| IVR_COMPLACENT_THRESHOLD | 0.8 | gates.py | Below this: options market underpricing risk. Occurs ~15% of the time historically. |
| IVR_ELEVATED_THRESHOLD | 1.2 | gates.py | Above this: options market pricing moderately more risk. Accounts for normal 2-4 point VRP on most stocks. |
| IVR_EXTREME_THRESHOLD | 1.5 | gates.py | Above this: significant divergence. Strong signal regardless of context. |
| HV_LOOKBACK_DAYS | 30 | data.py | Matches 30-day forward period of IBKR model-implied IV. Research mandates matching lookback periods. |

# 4. Context Interpretation Matrix

The regime label alone is insufficient. The same IV/HV ratio carries different implications depending on the engine state and trigger. IVR-001 produces a context_interpretation label by combining the regime with the current engine state.

The following matrix defines the interpretation labels and their desc strings:

## 4.1 At Extension (CAUTION or EXHAUSTION)

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | CONTINUATION SUPPORT | Options market pricing less risk than realised despite elevated price distance from anchor. The move is not generating fear in the options market. Supports continuation of the trend -- the extension may be sustainable, especially if driven by a structural catalyst (index inclusion, sector rotation, earnings beat). |
| ALIGNED | ORDERLY EXTENSION | Options market and price action agree on volatility magnitude at the extended level. The extension is acknowledged but not feared. Normal insurance premium. Defer to the engine extension gate assessment. |
| ELEVATED | REVERSAL RISK AT EXTENSION | Options market pricing moderately more risk than realised at an already-extended level. Early warning: the options market may be seeing reversal risk that the chart does not yet show. Smart money may be accumulating protective positions. Exercise additional caution on new entries. |
| EXTREME | DANGER AT EXTENSION | Options market pricing significantly more risk than realised at an extended level. Strong warning: smart money is likely hedging against a reversal. The combination of structural overextension (engine) and fear-level volatility premium (options) is the highest-risk configuration. Avoid new entries. If already holding, consider tightening stops. |

## 4.2 At Pullback (PULLBACK trigger, near structural floor)

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | CALM PULLBACK | Options market pricing less risk than realised near the structural floor. The pullback is orderly with no panic. No capitulation signal. Standard mean-reversion entry conditions -- the setup relies on structural floor integrity, not on contrarian fear. |
| ALIGNED | NORMAL CONDITIONS | Options market and price action agree on volatility magnitude at the pullback level. Normal conditions. No additional signal from the options market. Defer to structural assessment (floor integrity, THS, R:R). |
| ELEVATED | CAPITULATION SUPPORT | Options market pricing moderately more risk than realised near the structural floor. Contrarian-supportive: elevated fear at structural support often marks capitulation. Research shows high VRP environments historically favour equity exposure because the market prices more pessimism than typically materialises. Higher-quality pullback entry than ALIGNED. |
| EXTREME | STRONG CAPITULATION | Options market pricing significantly more risk than realised near the structural floor. Extreme fear at support -- highest-asymmetry entry if the floor holds. The market is pricing a structural breakdown that may not materialise. VRP compression alone generates positive return as IV normalises over the swing hold period. Strongest contrarian signal available from the options market. |

## 4.3 At Breakout (BREAKOUT / SWING_BREAKOUT trigger)

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | HIGH QUALITY BREAKOUT | Options market pricing less risk than realised at the breakout level. Dealers are not positioned for this move. As the breakout progresses, dealers must hedge by buying the underlying, creating mechanical follow-through buying pressure. This is the highest-quality breakout confirmation from the options market -- the move is catching participants off guard. |
| ALIGNED | ORDERLY BREAKOUT | Options market and price action agree on volatility magnitude at the breakout. The move is not surprising the options market. Neutral signal -- defer to volume confirmation and structural assessment. |
| ELEVATED | PARTIALLY PRICED IN | Options market pricing moderately more risk than realised. The breakout may already be anticipated by options traders. Follow-through could be limited as hedging demand was front-loaded. Not disqualifying but the entry has less mechanical tailwind than ALIGNED or COMPLACENT. |
| EXTREME | HEAVILY PRICED IN | Options market pricing significantly more risk than realised at the breakout. The move is heavily anticipated -- options traders are already positioned for large movement. Mechanical follow-through from dealer hedging is likely exhausted. Caution: the breakout event itself may be the catalyst that triggers IV normalisation (the classic post-event volatility crush), which removes the tailwind. |

## 4.4 At Recovery (REC-001 base formation)

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | ORDERLY BASE | Options market pricing less risk than realised during base formation. The market views the basing action as orderly, not distressed. Low-uncertainty recovery -- standard base quality assessment applies. |
| ALIGNED | STANDARD REGIME | Options market and price action agree on volatility magnitude during recovery. Normal conditions for base formation. Defer to recovery gate assessment (base bar count, ATR contraction, recovery R:R). |
| ELEVATED | ELEVATED ASYMMETRY | Options market pricing moderately more risk than realised during base formation. Higher risk but higher asymmetry -- if the base holds and the recovery triggers, the VRP compression contributes to positive return as IV normalises. The elevated uncertainty makes the base test more meaningful. |
| EXTREME | MAXIMUM ASYMMETRY | Options market pricing significantly more risk than realised during base formation. Maximum-asymmetry recovery if the base holds. The market is uncertain about the bottom -- fear is extreme. If the base proves valid, the VRP normalisation alone generates meaningful return over the recovery hold period. Highest-conviction recovery signal from the options market, contingent on structural base integrity. |

## 4.5 At Rally Maturity (RALLY_MATURE trigger, late-stage continuation)

> **§4.5 introduced at v1.1 (S159, May 19, 2026)** per RLY-001 v1.0 §5 directive at Tier 1K Bundle 4A Phase 4 closure. Implementation already shipped via RLY-001 Phase 2 standalone session (S158, prior chat). This section documents the IVR-001 context-interpretation matrix when the RALLY_MATURE classification (sourced from RLY-001's `rally_state.maturity.label`) is active.

The RALLY_MATURE classification is active when both of the following are simultaneously satisfied on the **context frame** (per RLY-001 v1.1 §3.1 / §3.3):

1. Up-bar window ratio ≥ 10/15 over the trailing 15 bars (≥10 bars closed above prior close)
2. Cumulative rally magnitude ≥ 5.0 ATR widths (computed as `(close[-1] - close[-15]) / current_atr` on the context frame)

When the RALLY_MATURE classification is active, IVR-001 consumes the RALLY_MATURE signal and emits the following context_interpretation per the regime cell:

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | DELAYED CLIMAX RISK | Options market shows no fear at mature-rally levels. The combination of context-frame up-bar density (≥10/15) and ≥5.0 ATR cumulative magnitude with a low IV/HV ratio suggests broad disregard for exhaustion risk. The longer the rally with no volatility-pricing reaction, the sharper the eventual mean reversion tends to be. Exercise caution on new continuation entries. |
| ALIGNED | MATURE TREND | The rally is mature but the options market is pricing the move proportionally. No additional signal from IVR. Defer to engine extension and structural assessment. Existing positions ride the trend; new entries acceptable provided extension and structural posture remain favourable. |
| ELEVATED | CLIMAX RISK | Options market pricing moderately more risk at late-stage continuation. Early warning: smart money may be hedging against the climax. Avoid initiating new continuation entries; consider scaling existing positions on strength. |
| EXTREME | EXHAUSTION SIGNAL | Highest-risk configuration. Late-stage rally (≥10/15 context up-bars + ≥5.0 ATR magnitude) compounded with EXTREME volatility regime constitutes a climax-run signature. Strong recommendation: avoid new entries; existing positions should consider profit-taking into strength per Minervini SEPA sell-rule guidance on climax tops. |

### 4.5.1 Trigger semantics — Read-path neutrality

The §4.5 matrix is keyed by the RALLY_MATURE classification (active / not-active), not by any specific data-access pattern. IVR-001's gate function (`_gate_volatility_regime` in `tbs_engine/gates.py`) consumes the RALLY_MATURE signal via whatever read path the engine architecture provides (current implementation: pre-gate compute-orchestrator-populated `ctx._rly_maturity_label` attribute per RLY-001 v1.1 §3.4; alternative read paths — flat_metrics key lookup, ctx attribute, helper return — would all satisfy this spec's contract). The contract is: **when the RALLY_MATURE classification is active, the §4.5 matrix is selected over the §4.6 Default matrix for context_interpretation emission**. The read-path implementation detail is governed by RLY-001 spec §3.4 / §4.4, not by this section.

### 4.5.2 Convention Deviation — Caution Factor Emission on COMPLACENT × RALLY_MATURE

Existing §4.1 (At Extension), §4.2 (At Pullback), §4.3 (At Breakout), §4.4 (At Recovery), and §4.6 (Default) all follow the IVR-001 v1.0 caution_factor convention per §5.2 / §6.1 / §6.2: caution_factor is emitted only for **ELEVATED** and **EXTREME** regimes; COMPLACENT and ALIGNED are treated as informational without caution.

**§4.5 deviates from this convention:** COMPLACENT × RALLY_MATURE also emits a caution_factor.

**Rationale:** In the §4.1 / §4.2 / §4.3 / §4.4 contexts, COMPLACENT is benign-or-supportive (continuation support / calm pullback / high-quality breakout / orderly base). In the §4.5 context, COMPLACENT at peak is the most insidious form of climax-run setup — operator-market complacency at a structurally late-stage move is the classical "blow-off top with no warning signs" pattern that Minervini and O'Neil both flag as the riskiest entry configuration. Treating COMPLACENT × RALLY_MATURE as benign would violate the spec's stated design intent (climax-awareness) for the sake of mechanical convention preservation.

**Caution factor string templates (§4.5 cells):**

| **Regime** | **caution_factor string** |
| --- | --- |
| COMPLACENT | `"VOLATILITY REGIME: COMPLACENT -- DELAYED CLIMAX RISK at mature rally. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market showing no fear. Sharp mean reversion risk."` |
| ALIGNED | `null` (no caution; trend acknowledged but proportionally priced) |
| ELEVATED | `"VOLATILITY REGIME: ELEVATED -- CLIMAX RISK at mature rally. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market pricing reversal risk."` |
| EXTREME | `"VOLATILITY REGIME: EXTREME -- EXHAUSTION SIGNAL: climax-run signature. Context up-bar ratio [X.XX]/15 + magnitude [Y.YY] ATR with options market pricing significant reversal. Consider profit-taking."` |

Substitution: `[X.XX]` = actual context ratio value to 2 decimals; `[Y.YY]` = actual magnitude ATR value to 2 decimals.

### 4.5.3 Output Surface — No Schema Change

The new §4.5 inherits IVR-001's existing transparency conventions per §6:
- `volatility_regime.context_interpretation.label` populated with the §4.5 label (DELAYED CLIMAX RISK / MATURE TREND / CLIMAX RISK / EXHAUSTION SIGNAL)
- `volatility_regime.context_interpretation.desc` populated with the §4.5 description
- `volatility_regime.caution_factor` populated per §4.5.2 table (or null for ALIGNED)
- `caution_factors[]` array appended per the existing IVR-001 surface (§6.2)

No new fields on the `volatility_regime` block; no schema change. Verdict bitwise-invariant — §4.5 caution_factor emission is additive on the existing `action_summary.caution_factors[]` array; the gate function continues to return PASS unconditionally per §5.2.

## 4.6 Default (TRENDING state, no special context)

> **§4.6 note (v1.1):** Renumbered from §4.5 at v1.1 amendment. Content unchanged from v1.0. Insertion of new §4.5 At Rally Maturity above this section preserves IVR-001's semantic invariant — each numbered §4.x section is a trigger context (Extension / Pullback / Breakout / Recovery / Rally Maturity), except this final section which is the fallback.

| **Regime** | **Interpretation Label** | **Description** |
| --- | --- | --- |
| COMPLACENT | LOW VOLATILITY PREMIUM | Options market pricing less risk than realised in a trending environment. The trend is not generating hedging demand. Suggests orderly, well-accepted trend with potential for surprise moves if conditions change. |
| ALIGNED | STANDARD REGIME | Options market and price action agree on volatility magnitude. Normal trending conditions. No additional options market signal. Defer entirely to structural engine assessment. |
| ELEVATED | ELEVATED UNCERTAINTY | Options market pricing moderately more risk than the trend has been delivering. The options market sees potential disruption that is not yet visible in price action. Advisory awareness -- monitor for catalysts (earnings, macro events, sector rotation). |
| EXTREME | EXTREME UNCERTAINTY | Options market pricing significantly more risk than the trend has been delivering. Strong divergence between orderly price trend and fearful options positioning. Potential regime change ahead. Exercise caution on new entries and consider tightening stops on existing positions. |

# 5. Gate Behaviour

## 5.1 Execution Model

IVR-001 executes as a gate function in gates.py under the Tier 3 parallel execution model (PA-001 precedent). It runs unconditionally on both VALID and INVALID paths, writes its metrics regardless of earlier gate failures, and does not contribute to the verdict. The verdict is determined by existing gates; IVR-001 adds context.

## 5.2 Advisory-Only at Launch

IVR-001 is pure advisory. No regime label produces a REJECT or INVALID verdict. The gate function writes metrics and returns PASS unconditionally. When the regime is ELEVATED or EXTREME (plus COMPLACENT when the RALLY_MATURE classification is active per §4.5.2 deviation), a caution_factor note is written to the action_summary caution_factors array.

The gate infrastructure (function signature, execution order position, metric writing pattern) is identical to an enforcement gate. If live observation (IVR-001-CAL-1) demonstrates that EXTREME at extension consistently precedes failed entries, promotion to a state-dependent hard gate requires changing one return statement, not the architecture.

> **§5.2 v1.1 note:** The parenthetical "(plus COMPLACENT when the RALLY_MATURE classification is active per §4.5.2 deviation)" was added at v1.1 to acknowledge the new §4.5 cell convention deviation. Pre-v1.1 wording was "ELEVATED or EXTREME" only. The §4.5.2 rationale documents why COMPLACENT × RALLY_MATURE warrants caution emission despite the §4.1-§4.4/§4.6 convention.

## 5.3 Execution Order

IVR-001 runs after G.5 Extension (PA-001 daily extension gate) and before G.5.5 Floor Proximity. Rationale: the volatility regime contextualises the extension assessment. Placing it immediately after extension means the extension verdict is already determined when IVR-001 reads the engine state for its context interpretation. The gate reads extension_condition from metrics (written by the extension gate in the same Tier 3 pass).

## 5.4 Graceful Degradation

When IBKR tick 106 does not return IV (non-optionable stocks, newly listed tickers, illiquid options chains), the gate writes all volatility_regime metrics as null and the regime label as UNAVAILABLE. No caution factor is generated. The action_summary omits the volatility_regime sub-object. The grouped output volatility_regime section appears with label UNAVAILABLE and a desc explaining the reason. This is consistent with MOD-K and MSX-001 degradation patterns -- silent skip, no alarm.

# 6. Output Schema

## 6.1 Grouped Output (transform.py)

A new top-level section volatility_regime is added to the grouped output, following self-documentation conventions established in the Batch 1/Batch 2 self-doc sprint.

Structure:

| **Field** | **Type / Shape** | **Description** |
| --- | --- | --- |
| volatility_regime |  | Top-level section |
| iv | {value, unit, desc} | Current implied volatility. Unit: percent_annualised. Desc explains source (IBKR model-implied, 30-day forward). |
| hv | {value, unit, desc} | 30-day historical volatility. Unit: percent_annualised. Desc explains computation (daily log returns, annualised). |
| ratio | {value, desc} | IV / HV ratio. Desc explains interpretation (above 1.0 = options expect more movement; below 1.0 = options expect less). |
| regime | {label, desc} | COMPLACENT / ALIGNED / ELEVATED / EXTREME / UNAVAILABLE. Desc is the full regime description from Section 3.3. |
| thresholds | {complacent, elevated, extreme} | Each threshold: {value, desc}. Desc explains what the boundary means and cites the research basis. |
| context_interpretation | {engine_state, trigger, interpretation} | interpretation: {label, desc}. Label from the matrix (Section 4). Desc is the full context-aware explanation. |
| caution_factor │ null | string | Non-null when ELEVATED or EXTREME (plus COMPLACENT × RALLY_MATURE per §4.5.2 deviation introduced at v1.1). Text for action_summary caution_factors array. |

## 6.2 Action Summary

The action_summary gains a volatility_regime sub-object with two fields:

| **Field** | **Description** |
| --- | --- |
| label | Regime label: COMPLACENT / ALIGNED / ELEVATED / EXTREME / UNAVAILABLE. What the options market is doing. |
| interpretation | Context interpretation label from Section 4 matrix. What it means for this specific trade. Examples: ORDERLY BREAKOUT, DANGER AT EXTENSION, CAPITULATION SUPPORT, HIGH QUALITY BREAKOUT. |

When ELEVATED or EXTREME (plus COMPLACENT × RALLY_MATURE per §4.5.2 deviation introduced at v1.1), a caution_factor string is also appended to the existing caution_factors array. Format: "VOLATILITY REGIME: [LABEL] -- [INTERPRETATION LABEL]. [One-sentence summary from desc]." (For §4.5 RALLY_MATURE cells, see the specific caution_factor string templates in §4.5.2 — those templates inline the actual context up-bar ratio and magnitude ATR values for operator-actionable diagnostic.)

## 6.3 Flat Keys (_flatten())

The following flat keys are registered in MAPPED_FLAT_KEYS for scanner and orchestrator consumption:

| **Flat Key** | **Type** | **Source** |
| --- | --- | --- |
| IV_Current | float │ null | volatility_regime.iv.value |
| HV_30D | float │ null | volatility_regime.hv.value |
| IV_HV_Ratio | float │ null | volatility_regime.ratio.value |
| Volatility_Regime | str │ null | volatility_regime.regime.label |
| Volatility_Interpretation | str │ null | volatility_regime.context_interpretation.interpretation.label |

# 7. Implementation Scope

## 7.1 Files Modified

| **File** | **Changes** |
| --- | --- |
| data.py | Add generic tick 106 (model IV) to existing reqMktData call. Compute 30-day HV from df_ctx: log returns of daily closes, standard deviation, annualise (* sqrt(252)). Store IV and HV on metrics dict. ~10 lines. |
| gates.py | New function _gate_volatility_regime(ctx). Reads IV and HV from metrics. Computes ratio. Classifies into regime band using tuneable constants. Reads engine state and trigger from ctx for context interpretation. Writes all metrics. Returns PASS unconditionally. 4 constants + ~40 lines. |
| output.py | Surface IV, HV, ratio, regime label, context interpretation label + desc, caution_factor note. Write to metrics dict for transform.py consumption. ~25 lines. |
| transform.py | New volatility_regime top-level section with full self-doc (iv, hv, ratio, regime, thresholds, context_interpretation, caution_factor). Action_summary volatility_regime sub-object (label + interpretation). Caution factor in caution_factors array. _flatten() reverse mapping. MAPPED_FLAT_KEYS registration (5 keys). ~80 lines. |
| types.py | Add iv and hv fields to RunContext if needed for gate function access. ~2 lines. |
| main.py | Add _gate_volatility_regime to Tier 3 parallel gate execution block, after _gate_extension. ~3 lines. |

## 7.2 Zero-Change Confirmation

- Profile B: No change to existing gates, anchors, or thresholds. IVR-001 runs on the same parallel path.

- Profile C: No change. IVR-001 runs and produces context, relevance is lower for long-duration holds (noted in desc).

- Recovery Protocol (REC-001): Not affected. Recovery uses its own gate cascade. IVR-001 metrics are available on recovery paths via Tier 3 parallel execution.

- SBO-001: Not affected. Breakout path unmodified.

- All existing gates: Zero modification. IVR-001 is additive.

## 7.3 Consumer Impact

- tbs_scanner.py: New flat keys need _flatten() mapping. Informational -- Engine-First Development principle applies.

- tbs_orchestrator.py: Dashboard may display Volatility_Regime and Volatility_Interpretation. Informational.

- tbs_engine_cli.py: Works without modification (engine self-contained). New fields appear in JSON output.

# 8. Test Cases

| **ID** | **Scenario** | **Input** | **Expected** |
| --- | --- | --- | --- |
| T01 | COMPLACENT regime | IV=18%, HV=25%, ratio=0.72 | Label: COMPLACENT. No caution factor. |
| T02 | ALIGNED regime (normal VRP) | IV=33%, HV=30%, ratio=1.10 | Label: ALIGNED. No caution factor. |
| T03 | ELEVATED regime | IV=42%, HV=30%, ratio=1.40 | Label: ELEVATED. Caution factor in action_summary. |
| T04 | EXTREME regime | IV=55%, HV=30%, ratio=1.83 | Label: EXTREME. Caution factor in action_summary. |
| T05 | IV unavailable (non-optionable) | IV=null, HV=25% | Label: UNAVAILABLE. All fields null. No caution factor. No action_summary entry. |
| T06 | HV zero (insufficient data) | IV=30%, HV=0% | Label: UNAVAILABLE. Division by zero guarded. Desc: insufficient daily bar history. |
| T07 | COMPLACENT at BREAKOUT | IV=18%, HV=25%, trigger=BREAKOUT | Interpretation: HIGH QUALITY BREAKOUT. |
| T08 | EXTREME at Extension CAUTION | IV=55%, HV=30%, ext=CAUTION | Interpretation: DANGER AT EXTENSION. Caution factor. |
| T09 | ELEVATED at Pullback | IV=42%, HV=30%, trigger=PULLBACK | Interpretation: CAPITULATION SUPPORT. |
| T10 | EXTREME at Recovery | IV=55%, HV=30%, recovery=active | Interpretation: MAXIMUM ASYMMETRY. |
| T11 | High-HV stock (SNDK-like) | IV=118%, HV=109%, ratio=1.08 | Label: ALIGNED. Correctly identifies orderly move despite high absolute volatility. |
| T12 | Low-HV stock (JNJ-like) | IV=22%, HV=15%, ratio=1.47 | Label: ELEVATED. Correctly identifies that 7-point spread is significant relative to low HV baseline. |
| T13 | Boundary: ratio exactly 0.8 | IV=20%, HV=25%, ratio=0.80 | Label: ALIGNED (0.8 is inclusive lower bound of ALIGNED). |
| T14 | Boundary: ratio exactly 1.2 | IV=30%, HV=25%, ratio=1.20 | Label: ELEVATED (1.2 is inclusive lower bound of ELEVATED). |
| T15 | Boundary: ratio exactly 1.5 | IV=37.5%, HV=25%, ratio=1.50 | Label: EXTREME (1.5 is inclusive lower bound of EXTREME). |
| T16 | VALID path with ALIGNED | VALID verdict, ratio=1.05 | volatility_regime populated. action_summary contains label + interpretation. No caution factor. |
| T17 | INVALID path with EXTREME | INVALID (DAILY EXTENSION), ratio=1.8 | volatility_regime populated. Caution factor present. Tier 3 parallel confirmed. |
| T18 | ETF evaluation | SPY, IV=15%, HV=12% | Label: ELEVATED. Profile-independent computation confirmed. |
| T19 | LSE stock (price scaler) | RR.L, IV/HV in percentage | IV and HV are percentages (not prices). No price scaler impact. Verify display. |
| T20 | Regression: existing gates | Full regression suite | All existing tests pass. Zero change to existing gate verdicts, thresholds, or metrics. |

# 9. Documentation Impact Assessment

| **Document** | **Section** | **Required Update** |
| --- | --- | --- |
| Doc 2 (Core Strategy) | Section VIII (Extension Rule) | Add volatility regime context paragraph. Reference IVR-001 as advisory overlay on extension assessment. |
| Doc 2 (Core Strategy) | Section IV (Output Schema Reference) | Add volatility_regime top-level section. Document all fields and types. |
| Doc 7 (Battle Card) | Step 6 (Technical Engine) | Add VOLATILITY REGIME reading guidance. Document regime labels, interpretation labels, and what they mean for execution decisions. |
| Doc 8 (Automation) | Section II Layer 2 | Add IVR-001 bullet to engine gate description. Note Tier 3 parallel execution and IBKR tick 106 source. |
| Engine Execution Map | Section II (Gate Function Table) | Add _gate_volatility_regime row. Position after G.5 Extension, before G.5.5 Floor Proximity. |
| Module G (THS) | No change | IVR-001 does not affect THS scoring. Confirmed zero interaction. |
| README | Engine line | Version bump. |

# 10. Vocabulary Constraints

**Permitted vocabulary: **COMPLACENT, ALIGNED, ELEVATED, EXTREME, UNAVAILABLE, advisory, context, regime, informational, caution factor. All interpretation labels from Section 4 matrix.

**Forbidden vocabulary: **REJECT, INVALID, HALT, BLOCK, GATE FAILURE, or any verdict-producing language. IVR-001 is advisory at launch. The gate function returns PASS unconditionally. No output string may imply that IVR-001 has rejected or blocked an entry.

# 11. Related Items

| **Item** | **Relationship** | **Notes** |
| --- | --- | --- |
| EXT-003 | Sibling (reduced scope) | Post-engine PCR + Max Pain extension confluence. Split from original EXT-003 concept. IVR-001 handles the generalised IV/HV signal; EXT-003 handles OI-derived options context with a data quality gate for thin chains. |
| PA-001 | Prerequisite (CLOSED) | Daily extension gate provides the extension context that IVR-001 interprets. Tier 3 parallel execution model is the architectural precedent. |
| MOD-K | Related (SYNCED) | Options chain data source. IVR-001 uses IBKR tick 106 (model IV) which is independent of MOD-K. EXT-003 consumes MOD-K output (PCR, Max Pain). |
| MSX-001 | Not consumed | IVR-001 is engine-native. MSX-001 is post-engine. No interaction. EXT-003 may add an MSX component (Component 10) in the future. |
| IVR-001-CAL-1 | Companion observation | Threshold calibration review after 3-6 months live data. Assess: false ELEVATED rate on low-HV stocks, EXTREME predictive power at extension, potential promotion to state-dependent hard gate. |

TBS Specification Document  |  IVR-001  |  End of Document

Page
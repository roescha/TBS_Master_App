"""DSP-002 — Analyst Levels Surfacing Decoupling (from R:R-Validity Gate).

Spec: DSP002_Analyst_Levels_Surfacing_Decoupling_Spec_v1_0.md (S146, v1.0)
Joint scope: DSP-002 (parent) + DSP-002-CORR-1 (Files-field correction;
lockstep closure with parent at Phase 4 DIA sync).

Implements the four test classes enumerated in spec §5.1:

    1. TestAnalystLevelsSurfacingEdgeCase   — QXO-class edge case
                                              (new flag True, existing False)
    2. TestExitPathAnalystLevelsRetention   — EXIT-active analyst-level retention
                                              (sub-cases (i) regular + (ii) edge)
    3. TestEnforcementScopePreservation     — gates.py:919-970 reads existing flag
                                              only (slices A/B/C)
    4. TestBitwiseInvariance                — Profile A + Profile C + Profile B
                                              current-True regression batteries
                                              (with explicit `_atm ≤ close`
                                              boundary-narrowing test per
                                              Phase 3 prompt §12 Option B)

Differential-evidence contract (spec §5.3):
    - Class 1 (all tests) and Class 2 sub-case (ii) MUST FAIL on pre-fix code
      and PASS on post-fix code. FAIL→PASS evidence captured by reverting the
      compute.py + output.py edits, running the tests, then restoring.
    - Class 3 + Class 4 are REGRESSION/INVARIANCE tests — they pass on both
      pre-fix and post-fix engines by design. Differential evidence not
      required per spec §5.3.

Architecture (spec §4):
    - compute.py: two-block restructure introducing _has_analyst_levels_data
      ctx flag (NEW, gates analyst-level metric writes); _has_fundamental_data
      ctx flag (existing, gates R:R metric writes).
    - output.py: EXIT-clear split — R:R metrics cleared on EXIT; analyst-level
      metrics retained on EXIT.

Boundary-case discipline (spec §4.5 + §10.1; Phase 3 prompt §12):
    The `_atl < _atm ≤ close` boundary case is reachable: existing flag True,
    new flag False. Pre-fix wrote analyst-level metrics; post-fix suppresses
    them ("designed surfacing narrowing" per DQ-2 rationale). Per Phase 3
    prompt §12 Option B (recommended), this boundary is included as an
    explicit test method in TestBitwiseInvariance with a clear behaviour
    contract — passes post-fix, fails pre-fix (additional differential test).

Import strategy
===============
Pure spec_from_file_location pattern with non-package module names and no
sys.modules write — strictly equivalent to test_dsp001_source_label_
escalation_coupling.py and test_bugr002_hierarchy_partition.py. Avoids the
TEST-HRN-001 overwrite anti-pattern by construction.

The compute.py module imports from tbs_engine.types and tbs_engine.helpers;
those are loaded as standalone non-package modules and pre-registered in
sys.modules under the names compute.py expects, scoped by a guard so we
do not overwrite if already loaded by a sibling test in the same session.
"""

import os
import sys
import importlib.util as _ilu
from types import SimpleNamespace

import pytest


# ===========================================================================
# Module loader — safe pattern, idempotent guard against TEST-HRN-001
# ===========================================================================

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_ENGINE_DIR = os.path.join(_REPO_ROOT, "tbs_engine")


def _load_safe(modname, path):
    """Load a module via spec_from_file_location.

    If `modname` is already in sys.modules (e.g., another DSP-002 test in
    the same pytest session loaded it), return the existing entry — we do
    not overwrite (TEST-HRN-001 guard).
    """
    if modname in sys.modules:
        return sys.modules[modname]
    spec = _ilu.spec_from_file_location(modname, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-register a stub for tbs_engine package so submodules can `from
# tbs_engine.types import ...` without triggering the package __init__ chain
# (charts.py → plotly, main.py → ib_insync, etc.).
if "tbs_engine" not in sys.modules:
    import types as _types_mod
    sys.modules["tbs_engine"] = _types_mod.ModuleType("tbs_engine")

# compute.py imports from tbs_engine.types, tbs_engine.helpers, and
# tbs_engine.exit. Load them in dependency order.
_types_mod = _load_safe(
    "tbs_engine.types",
    os.path.join(_ENGINE_DIR, "types.py"),
)
_helpers_mod = _load_safe(
    "tbs_engine.helpers",
    os.path.join(_ENGINE_DIR, "helpers.py"),
)
_exit_mod = _load_safe(
    "tbs_engine.exit",
    os.path.join(_ENGINE_DIR, "exit.py"),
)
_compute_mod = _load_safe(
    "tbs_engine.compute",
    os.path.join(_ENGINE_DIR, "compute.py"),
)
_gates_mod = _load_safe(
    "tbs_engine.gates",
    os.path.join(_ENGINE_DIR, "gates.py"),
)

_compute_early_capital_rr = _compute_mod._compute_early_capital_rr
_gate_capital_expectancy = _gates_mod._gate_capital_expectancy


# ===========================================================================
# Fixture builders
# ===========================================================================

def _make_state(**overrides):
    """Minimal `state` SimpleNamespace for _compute_early_capital_rr.

    Defaults exercise no floor failure / violation / breakout state — the
    suppression guards downstream of FRR-001 stay quiet so the FRR-001
    block runs unencumbered.
    """
    defaults = dict(
        is_floor_failure=False,
        is_violated=False,
        is_resolving=False,
        is_trending=False,
        atr_raw=2.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ctx(p_code="B",
              close=18.89,
              atm=31.0,
              atl=26.0,
              ath=50.0,
              acnt=13,
              breakout_active=False,
              is_c3=True,
              resistance_raw=24.4,
              hard_stop_raw=15.0,
              **state_overrides):
    """Build a synthetic RunContext-shaped SimpleNamespace.

    Default values reproduce the QXO-class edge case observed at S146:
    - close = 18.89
    - analyst median = 31.0  (above price ⇒ new flag True)
    - analyst low    = 26.0  (above price ⇒ existing flag False)
    - analyst high   = 50.0
    - analyst count  = 13

    `_compute_early_capital_rr` ctx attributes referenced (verified by
    grep against compute.py):
        ctx.p_code, ctx.last, ctx.metrics, ctx.state, ctx.price_scaler,
        ctx.resistance_raw, ctx.hard_stop_raw, ctx.df, ctx.cfg,
        ctx._df_ctx, ctx._is_c3, ctx.daily_atr, ctx.daily_hard_stop,
        ctx.cons_high_raw (set inside fn), ctx.mm_target_raw,
        ctx._brk_mm_target_raw, ctx._brk_tight_stop_raw,
        ctx._breakout_model_active (getattr default False),
        ctx._analyst_target_median, ctx._analyst_target_low,
        ctx._analyst_target_high, ctx._analyst_count.
    """
    last = {
        "close": close,
        "open": close - 0.5,
        "ANCHOR": hard_stop_raw,
        "SMA_200": close * 0.8,
    }
    metrics = {}
    state = _make_state(**state_overrides)
    ctx = SimpleNamespace(
        p_code=p_code,
        last=last,
        metrics=metrics,
        state=state,
        price_scaler=1.0,
        resistance_raw=resistance_raw,
        hard_stop_raw=hard_stop_raw,
        df=None,
        cfg=None,
        _df_ctx=None,
        _is_c3=is_c3,
        daily_atr=2.0,
        daily_hard_stop=hard_stop_raw,
        cons_high_raw=None,
        mm_target_raw=None,
        _brk_mm_target_raw=None,
        _brk_tight_stop_raw=None,
        _breakout_model_active=breakout_active,
        _analyst_target_median=atm,
        _analyst_target_low=atl,
        _analyst_target_high=ath,
        _analyst_count=acnt,
    )
    return ctx


# ===========================================================================
# Class 1: TestAnalystLevelsSurfacingEdgeCase
# ===========================================================================

class TestAnalystLevelsSurfacingEdgeCase:
    """[DSP-002 §5.1 Class 1] QXO-class edge case path:
    `_atm > close` AND `_atl >= close` (new flag True, existing flag False).

    Path-class scope: Profile B + C-3 paths in non-EXIT engine state.
    Canonical reproducer: QXO at S146 (_atm=31, _atl=26, close=18.89).

    Differential evidence (spec §5.3): all tests in this class MUST FAIL
    on pre-fix code (no _has_analyst_levels_data flag; the four metric
    writes are gated on _has_fundamental_data which is False on this path)
    and PASS on post-fix code (Block A fires under the new flag).
    """

    def test_qxo_fundamental_target_written(self):
        """QXO scenario: Fundamental_Target = analyst median = 31.0."""
        ctx = _make_ctx()  # defaults to QXO shape
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get("Fundamental_Target") == 31.0

    def test_qxo_fundamental_floor_written(self):
        """QXO scenario: Fundamental_Floor = analyst low = 26.0."""
        ctx = _make_ctx()
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get("Fundamental_Floor") == 26.0

    def test_qxo_target_high_and_count_written(self):
        """QXO scenario: Fundamental_Target_High=50.0; Fundamental_Analyst_Count=13."""
        ctx = _make_ctx()
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx.metrics.get("Fundamental_Target_High") == 50.0
        assert ctx.metrics.get("Fundamental_Analyst_Count") == 13

    def test_qxo_rr_remains_suppressed(self):
        """QXO scenario: Fundamental_RR is None (existing flag False ⇒
        Block B does not fire ⇒ R:R denominator suppression preserved per
        FRR-001 §5.4.1 Guard). Both flags persist on ctx for downstream."""
        ctx = _make_ctx()
        _compute_early_capital_rr(ctx, exit_signal=False)
        # R:R metrics not written on this path (Block B gated on existing flag)
        assert ctx.metrics.get("Fundamental_RR") is None
        assert ctx.metrics.get("Fundamental_RR_Label") is None
        # ctx flags persisted: new True, existing False
        assert ctx._has_analyst_levels_data is True
        assert ctx._has_fundamental_data is False


# ===========================================================================
# Class 2: TestExitPathAnalystLevelsRetention
# ===========================================================================
#
# The EXIT-clear lives at output.py:~L2295-2308 inside _assemble_output.
# Rather than constructing a full _assemble_output ctx (heavy), we extract
# the EXIT-clear block from the live output.py source at test time and
# exec() it against a synthetic metrics dict. This gives true differential
# evidence: pre-fix source has the 7-key clear; post-fix source has the
# 3-key clear with retention comment. The test reads real source — not a
# re-implementation.
# ===========================================================================

def _exec_exit_clear_block_from_source(metrics):
    """Read output.py and exec the EXIT-clear block against `metrics`.

    Locates the block by anchoring on `metrics.get("Exit_Signal") == "EXIT"`
    inside the Profile B fundamental fields region (~L2295-2308 post-edit;
    ~L2295-2303 pre-edit). Slices conservatively: from the immediately
    preceding comment ("EXIT suppression" or "[DSP-002] EXIT suppression")
    down to the next blank line followed by a `#`-comment header that is
    NOT inside our block.

    The exec'd snippet must operate at indent-level 4 (inside a function);
    we dedent before exec.
    """
    output_path = os.path.join(_ENGINE_DIR, "output.py")
    with open(output_path, "r", encoding="utf-8") as f:
        src_lines = f.readlines()

    # Find the EXIT-clear region. Anchor on the line containing
    # `if metrics.get("Exit_Signal") == "EXIT":` AND inside the Fundamental
    # fields block (after the setdefault for Fundamental_RR_Note).
    start_idx = None
    end_idx = None
    seen_setdefault_for_rr_note = False
    for i, line in enumerate(src_lines):
        if 'metrics.setdefault("Fundamental_RR_Note", None)' in line:
            seen_setdefault_for_rr_note = True
            continue
        if (
            seen_setdefault_for_rr_note
            and 'if metrics.get("Exit_Signal") == "EXIT":' in line
        ):
            # Walk backward to find the start of the comment block immediately
            # above (a contiguous run of `# ...` lines).
            j = i - 1
            while j >= 0 and src_lines[j].lstrip().startswith("#"):
                j -= 1
            start_idx = j + 1
            # Walk forward to find the end: include the if-block body, plus
            # any contiguous trailing `#` comments inside that block, then
            # stop at the first line that is at-or-shallower-indent than the
            # `if` and is not a comment continuing the EXIT block.
            if_line = src_lines[i]
            if_indent = len(if_line) - len(if_line.lstrip())
            k = i + 1
            while k < len(src_lines):
                ln = src_lines[k]
                stripped = ln.strip()
                if stripped == "":
                    end_idx = k  # end is exclusive — stop at blank line
                    break
                cur_indent = len(ln) - len(ln.lstrip())
                if cur_indent > if_indent:
                    # Inside the if-block body (assignments) — keep going
                    k += 1
                    continue
                if cur_indent == if_indent and stripped.startswith("#"):
                    # Trailing comment at same indent as `if` — could be
                    # the "Fundamental_Target / ... NOT cleared" block in
                    # the post-edit form. Include if comment text relates
                    # to DSP-002 retention; otherwise stop.
                    if (
                        "DSP-002" in stripped
                        or "NOT cleared" in stripped
                        or "Block A" in stripped
                        or "_has_analyst_levels_data" in stripped
                        or "analyst_levels JSON" in stripped
                        or "ANALYST_CONSENSUS" in stripped
                        or "hierarchy row" in stripped
                    ):
                        k += 1
                        continue
                    end_idx = k
                    break
                # Indent ≤ if_indent and not a comment — block done
                end_idx = k
                break
            if end_idx is None:
                end_idx = len(src_lines)
            break

    assert start_idx is not None and end_idx is not None, (
        "Could not locate EXIT-clear block in output.py — test harness "
        "anchor strings did not match source. This is a test-harness bug, "
        "not a fix-correctness bug."
    )

    snippet_lines = src_lines[start_idx:end_idx]
    # Compute minimum indent of non-blank lines, dedent.
    min_indent = min(
        (len(ln) - len(ln.lstrip()))
        for ln in snippet_lines
        if ln.strip()
    )
    dedented = "".join(ln[min_indent:] if ln.strip() else ln for ln in snippet_lines)

    # Exec against a local namespace exposing `metrics`.
    local_ns = {"metrics": metrics}
    exec(compile(dedented, "<exit_clear_block>", "exec"), {}, local_ns)
    return metrics


class TestExitPathAnalystLevelsRetention:
    """[DSP-002 §5.1 Class 2] EXIT-active paths where analyst data is
    available. Two sub-cases per spec §5.1:

        (i)  both flags True (dominant case)
        (ii) new flag True, existing flag False (edge case + EXIT
             conjunction — QXO at S146 satisfies this)

    Differential evidence (spec §5.3): sub-case (ii) MUST FAIL on pre-fix
    (all 7 keys nulled by old EXIT-clear) and PASS on post-fix (only 3
    R:R keys nulled, 4 analyst-level keys retained).
    """

    def test_subcase_i_both_flags_true_dominant_path(self):
        """Sub-case (i): both flags True — full analyst data plus EXIT firing.

        Pre-EXIT-clear metrics simulate compute.py post-edit output where
        BOTH Block A and Block B fired (all 7 Fundamental_* keys non-None).
        Post-edit EXIT-clear retains 4 analyst-level keys, clears 3 R:R keys.
        """
        metrics = {
            "Exit_Signal": "EXIT",
            # Block A writes (analyst-level, retained)
            "Fundamental_Target": 31.0,
            "Fundamental_Floor": 26.0,
            "Fundamental_Target_High": 50.0,
            "Fundamental_Analyst_Count": 13,
            # Block B writes (R:R, cleared)
            "Fundamental_RR": 1.5,
            "Fundamental_RR_Label": "INSUFFICIENT",
            "Fundamental_RR_Note": "some advisory text",
        }
        _exec_exit_clear_block_from_source(metrics)

        # Analyst-level retained (DSP-002 §4.3)
        assert metrics["Fundamental_Target"] == 31.0
        assert metrics["Fundamental_Floor"] == 26.0
        assert metrics["Fundamental_Target_High"] == 50.0
        assert metrics["Fundamental_Analyst_Count"] == 13
        # R:R cleared
        assert metrics["Fundamental_RR"] is None
        assert metrics["Fundamental_RR_Label"] is None
        assert metrics["Fundamental_RR_Note"] is None

    def test_subcase_ii_edge_case_exit_conjunction_qxo(self):
        """Sub-case (ii): new True, existing False — QXO + EXIT conjunction.

        Pre-EXIT-clear metrics simulate compute.py post-edit on edge-case
        path: Block A fired (4 analyst-level keys non-None); Block B did
        NOT fire (3 R:R keys remain at None from setdefault). EXIT clears
        the 3 R:R keys (already None — no-op) and retains the 4 analyst-
        level keys.
        """
        metrics = {
            "Exit_Signal": "EXIT",
            # Block A wrote (new flag True)
            "Fundamental_Target": 31.0,
            "Fundamental_Floor": 26.0,
            "Fundamental_Target_High": 50.0,
            "Fundamental_Analyst_Count": 13,
            # Block B did not fire (existing flag False); setdefault then
            # populated with None at output.py:~L2287-2293
            "Fundamental_RR": None,
            "Fundamental_RR_Label": None,
            "Fundamental_RR_Note": None,
        }
        _exec_exit_clear_block_from_source(metrics)

        # Analyst-level RETAINED — this is the QXO+EXIT differential
        assert metrics["Fundamental_Target"] == 31.0
        assert metrics["Fundamental_Floor"] == 26.0
        assert metrics["Fundamental_Target_High"] == 50.0
        assert metrics["Fundamental_Analyst_Count"] == 13
        # R:R remains None (clear is no-op since already None)
        assert metrics["Fundamental_RR"] is None
        assert metrics["Fundamental_RR_Label"] is None
        assert metrics["Fundamental_RR_Note"] is None

    def test_non_exit_path_no_clear_fires(self):
        """Regression: EXIT-clear is gated on Exit_Signal == "EXIT".
        On non-EXIT paths, all 7 Fundamental_* keys preserved verbatim."""
        metrics = {
            "Exit_Signal": "VALID",  # not "EXIT"
            "Fundamental_Target": 31.0,
            "Fundamental_Floor": 26.0,
            "Fundamental_Target_High": 50.0,
            "Fundamental_Analyst_Count": 13,
            "Fundamental_RR": 1.5,
            "Fundamental_RR_Label": "INSUFFICIENT",
            "Fundamental_RR_Note": "some advisory",
        }
        _exec_exit_clear_block_from_source(metrics)

        # All seven preserved (clause guard False)
        assert metrics["Fundamental_Target"] == 31.0
        assert metrics["Fundamental_RR"] == 1.5
        assert metrics["Fundamental_RR_Label"] == "INSUFFICIENT"
        assert metrics["Fundamental_RR_Note"] == "some advisory"


# ===========================================================================
# Class 3: TestEnforcementScopePreservation
# ===========================================================================

class TestEnforcementScopePreservation:
    """[DSP-002 §5.1 Class 3] gates.py:919-970 reads `_has_fundamental_data`
    only — never the new `_has_analyst_levels_data` flag.

    Three regression slices per spec §5.1:
        Slice A: current-True path (existing flag True, R:R numeric)
        Slice B: current-False, no analyst data (skip path)
        Slice C: edge-case path (new True, existing False) — gate
                 evaluates on existing flag, skips R:R-bound REJECT

    Verifies: gate signature unchanged, gate execution-order unchanged,
    no new flag enters enforcement (per spec §3.4 + §4.4).
    """

    def _make_gate_ctx(self, has_fund=False, has_analyst=False, is_c3=False):
        """Build a minimal ctx for _gate_capital_expectancy."""
        # Match the precedent test_frr001_fundamental_rr.py shape.
        return SimpleNamespace(
            _has_fundamental_data=has_fund,
            _has_analyst_levels_data=has_analyst,
            _is_c3=is_c3,
            _df_ctx=None,
        )

    def test_slice_a_current_true_insufficient_rejects(self):
        """Slice A: existing flag True, R:R < 2.0, C-1/C-2 ⇒ REJECT fires."""
        ctx = self._make_gate_ctx(has_fund=True, has_analyst=True, is_c3=False)
        metrics = {
            "Exit_Signal": "VALID",  # not EXIT
            "Fundamental_RR": 1.0,
            "Fundamental_Target": 31.0,
            "Fundamental_Floor": 26.0,
        }
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=0.0,
            cons_high_raw=None,
            last_close=27.0,
            hard_stop_raw=24.0,
            resistance_raw=30.0,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
            ctx=ctx,
        )
        # Gate evaluates on existing flag and R:R < 2.0 ⇒ INVALID
        assert result is not None
        assert result.verdict == "INVALID"
        assert "FUNDAMENTAL EXPECTANCY FAILED" in result.reason

    def test_slice_b_current_false_no_analyst_data_skip(self):
        """Slice B: both flags False — gate skips FRR-001 enforcement."""
        ctx = self._make_gate_ctx(has_fund=False, has_analyst=False, is_c3=False)
        metrics = {
            "Exit_Signal": "VALID",
            "Fundamental_RR": None,
        }
        # On this path FRR-001 enforcement skips; falls through to CEG-003
        # technical fallback. The verdict depends on Capital R:R; we only
        # need to assert that the gate did NOT REJECT for FUNDAMENTAL
        # EXPECTANCY.
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=0.0,
            cons_high_raw=None,
            last_close=27.0,
            hard_stop_raw=24.0,
            resistance_raw=30.0,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
            ctx=ctx,
        )
        # Either result is None (gate fell through cleanly) OR result is
        # not a FUNDAMENTAL EXPECTANCY rejection. The key invariant is that
        # the existing-flag-False path does NOT trip the FRR-001 branch.
        if result is not None:
            assert "FUNDAMENTAL EXPECTANCY" not in result.reason

    def test_slice_c_edge_case_new_true_existing_false_no_frr_reject(self):
        """Slice C: edge case — new flag True, existing flag False.

        Gate evaluates on `_has_fundamental_data` (existing) per spec §3.4
        and §4.4. Because `Fundamental_RR is None` on this path (Block B
        did not fire post-fix), the gate's `_has_fund and _fund_rr is not
        None and not _is_c3` clause evaluates False → falls through to
        CEG-003 technical fallback. The new flag does NOT enter the gate.
        """
        ctx = self._make_gate_ctx(has_fund=False, has_analyst=True, is_c3=False)
        metrics = {
            "Exit_Signal": "VALID",
            "Fundamental_RR": None,             # Block B did not fire
            "Fundamental_Target": 31.0,         # Block A did fire (Class 1)
            "Fundamental_Floor": 26.0,
        }
        result = _gate_capital_expectancy(
            p_code="B",
            risk_a=0.0,
            cons_high_raw=None,
            last_close=18.89,
            hard_stop_raw=15.0,
            resistance_raw=24.4,
            atr_raw=2.0,
            price_scaler=1.0,
            metrics=metrics,
            ctx=ctx,
        )
        # The FUNDAMENTAL EXPECTANCY REJECT branch must NOT fire on this
        # path — the existing flag is False so the FRR-001 clause skips.
        if result is not None:
            assert "FUNDAMENTAL EXPECTANCY" not in result.reason


# ===========================================================================
# Class 4: TestBitwiseInvariance
# ===========================================================================

class TestBitwiseInvariance:
    """[DSP-002 §5.1 Class 4] Differential pre-fix vs post-fix output
    equality on every non-edge-case path.

    Three regression batteries per spec §5.1:
        - Profile A battery: compute.py:846 Profile B guard ⇒ neither
          flag is computed on Profile A; no metric writes flow.
        - Profile C battery: same Profile B guard scopes both flags.
        - Profile B current-True battery: dominant case (`_atl < close`,
          `_atm > close`) — both flags True; metric writes fire identically
          to pre-fix; output bitwise-equal.

    Boundary-case discipline (Phase 3 prompt §12 — Option B selected):
        The `_atm ≤ close` boundary sub-case (existing True, new False) is
        included as an explicit test method asserting the post-fix
        designed surfacing narrowing per spec §4.5 + §10.1. This test
        passes on post-fix engine and would FAIL on pre-fix engine —
        making it an additional differential-evidence test alongside
        Class 1 + Class 2 sub-case (ii).
    """

    def test_profile_a_no_flag_writes(self):
        """Profile A: `if p_code == "B":` guard at compute.py:846 prevents
        either flag from being computed. Both ctx flags retain default
        False; no Fundamental_* metric writes occur.

        Profile A path requires a minimal df_ctx (the function reads
        `df_ctx['high'].iloc[-11:-1].max()` for cons_high_raw); we provide
        a 12-row DataFrame so the path executes cleanly through to the
        FRR-001 block (where the Profile B guard then bypasses both flag
        computations).
        """
        import pandas as pd
        df_ctx = pd.DataFrame({"high": [25.0 + i * 0.1 for i in range(12)]})
        ctx = _make_ctx(p_code="A", close=24.0,
                        resistance_raw=26.5, hard_stop_raw=22.0)
        ctx._df_ctx = df_ctx
        _compute_early_capital_rr(ctx, exit_signal=False)
        # Both flags persisted as default False (Profile A bypasses the
        # `if p_code == "B":` guard entirely). Use getattr for the new
        # flag so this invariance test passes on both pre-fix and post-fix
        # engines per spec §5.3 contract for TestBitwiseInvariance.
        assert ctx._has_fundamental_data is False
        assert getattr(ctx, "_has_analyst_levels_data", False) is False
        # No Fundamental_* writes on Profile A from this function
        assert ctx.metrics.get("Fundamental_Target") is None
        assert ctx.metrics.get("Fundamental_Floor") is None
        assert ctx.metrics.get("Fundamental_RR") is None

    def test_profile_c_no_flag_writes(self):
        """Profile C: same Profile B guard — both flags False, no writes.
        Invariance assertion uses getattr for the new flag so this test
        passes on both pre-fix and post-fix engines per spec §5.3."""
        ctx = _make_ctx(p_code="C")
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx._has_fundamental_data is False
        assert getattr(ctx, "_has_analyst_levels_data", False) is False
        assert ctx.metrics.get("Fundamental_Target") is None
        assert ctx.metrics.get("Fundamental_RR") is None

    def test_profile_b_current_true_dominant_path_writes_both_blocks(self):
        """Profile B dominant case: `_atl < close < _atm` ⇒ both flags True.

        Both Block A (analyst-level writes) and Block B (R:R writes + Profit
        Target demotion) fire, identically to pre-fix behaviour. Engine
        output JSON bitwise-equal to pre-fix on this path (spec §4.5).
        """
        # _atl=20, close=25, _atm=40 ⇒ existing True (20 < 25), new True (40 > 25)
        ctx = _make_ctx(close=25.0, atm=40.0, atl=20.0, ath=60.0, acnt=8,
                        resistance_raw=28.0, hard_stop_raw=22.0)
        _compute_early_capital_rr(ctx, exit_signal=False)

        # Existing flag True on dominant path (passes pre-fix and post-fix).
        # Per spec §5.3 + §4.5 dominant-case invariance contract:
        # "output bitwise-unchanged" — the four analyst-level metric writes
        # and the three R:R metric writes are identical pre-fix vs post-fix.
        # We do NOT assert on the new flag's value here; that assertion
        # would make this test post-fix-only (it belongs in Class 1's edge
        # case differential evidence, not in TestBitwiseInvariance).
        assert ctx._has_fundamental_data is True
        # Block A writes (both engines write these on the dominant path)
        assert ctx.metrics["Fundamental_Target"] == 40.0
        assert ctx.metrics["Fundamental_Floor"] == 20.0
        assert ctx.metrics["Fundamental_Target_High"] == 60.0
        assert ctx.metrics["Fundamental_Analyst_Count"] == 8
        # Block B writes (reward=15, risk=5 ⇒ R:R=3.0 ⇒ STRONG)
        assert ctx.metrics["Fundamental_RR"] == 3.0
        assert ctx.metrics["Fundamental_RR_Label"] == "STRONG"
        # Profit target demotion (BRK guard False ⇒ source written)
        assert ctx.metrics.get("Profit_Target_Source") == "ANALYST_CONSENSUS"
        assert ctx.metrics.get("Profit_Target_Role") == "INFORMATIONAL"

    def test_profile_b_no_analyst_data_both_flags_false(self):
        """Profile B without analyst data: both flags False; neither block
        fires; no Fundamental_* writes from this function. Invariance
        assertion uses getattr for the new flag (passes both engines)."""
        ctx = _make_ctx(atm=None, atl=None, ath=None, acnt=None,
                        resistance_raw=28.0, hard_stop_raw=22.0, close=25.0)
        _compute_early_capital_rr(ctx, exit_signal=False)
        assert ctx._has_fundamental_data is False
        assert getattr(ctx, "_has_analyst_levels_data", False) is False
        assert ctx.metrics.get("Fundamental_Target") is None
        assert ctx.metrics.get("Fundamental_RR") is None

    def test_boundary_atm_le_close_designed_surfacing_narrowing(self):
        """Boundary sub-case (Phase 3 prompt §12 Option B; spec §4.5 + §10.1):

        `_atl < _atm ≤ close` — existing flag True, new flag False.
        Concrete shape: _atl=10, _atm=15, close=20.

        Post-fix behaviour (designed surfacing narrowing per DQ-2 rationale
        "median ≤ price is operationally meaningless as a forward target
        reference"):
            - Block A does NOT fire (new flag False)
            - Block B DOES fire (existing flag True)
            - Result: R:R metrics written; analyst-level metrics suppressed
            - This is symmetrical to QXO-class edge case (where Block A
              fires but Block B does not)

        Pre-fix behaviour on the same path: Block A and Block B both fired
        (single welded gate on existing flag) ⇒ all four analyst-level
        metrics were written. This test would therefore FAIL on pre-fix
        code (Fundamental_Target would be 15.0, not None) — making it an
        additional differential-evidence test.
        """
        # _atl=10, _atm=15, close=20 ⇒ existing True (10 < 20), new False (15 ≤ 20)
        ctx = _make_ctx(close=20.0, atm=15.0, atl=10.0, ath=25.0, acnt=5,
                        resistance_raw=22.0, hard_stop_raw=8.0)
        _compute_early_capital_rr(ctx, exit_signal=False)

        # Flag asymmetry confirmed
        assert ctx._has_fundamental_data is True
        assert ctx._has_analyst_levels_data is False

        # Block A did NOT write (new flag False) — designed narrowing
        assert ctx.metrics.get("Fundamental_Target") is None
        assert ctx.metrics.get("Fundamental_Floor") is None
        assert ctx.metrics.get("Fundamental_Target_High") is None
        assert ctx.metrics.get("Fundamental_Analyst_Count") is None

        # Block B DID write (existing flag True) — R:R math fires.
        # reward = _atm - close = 15 - 20 = -5 ⇒ negative reward.
        # risk = close - _atl = 20 - 10 = 10 ⇒ positive risk.
        # _fund_rr = round(-5/10, 2) = -0.5 ⇒ < 2.0 ⇒ "INSUFFICIENT".
        assert ctx.metrics.get("Fundamental_RR") == -0.5
        assert ctx.metrics.get("Fundamental_RR_Label") == "INSUFFICIENT"

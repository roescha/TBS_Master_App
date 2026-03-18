"""
Tests for OTL-002 + OTL-003: Diagnostic exit-signal annotation.

OTL-003: Corrects misleading floor counter note when exit already active.
OTL-002: Appends exit visibility suffix on HALT + active exit.

Tests call _annotate_exit_signal() directly — no full RunContext needed.

Import note: _annotate_exit_signal is a pure-logic helper with zero
in-package dependencies, so we load output.py directly to avoid pulling
the full tbs_engine.__init__ dependency chain (ib_insync, plotly, etc.)
which is unnecessary for this unit test.
"""
import pytest
import sys
import os
import importlib.util

_output_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "tbs_engine", "output.py"
)
_spec = importlib.util.spec_from_file_location("_output_isolated", _output_path)
_mod = importlib.util.module_from_spec(_spec)

# Stub out output.py's own imports so the module loads in isolation.
# _annotate_exit_signal uses only builtins — these stubs are never called.
import types as _t
for _stub_name in ("tbs_engine.types", "tbs_engine.helpers", "tbs_engine.charts",
                    "tbs_engine.transform", "pandas", "plotly", "plotly.graph_objects"):
    sys.modules.setdefault(_stub_name, _t.ModuleType(_stub_name))

# Provide the specific names output.py imports from its dependencies
_helpers_stub = sys.modules["tbs_engine.helpers"]
if not hasattr(_helpers_stub, "_clamp"):
    _helpers_stub._clamp = None
    _helpers_stub.check_climax_history = None
_charts_stub = sys.modules["tbs_engine.charts"]
if not hasattr(_charts_stub, "_build_focus_chart"):
    _charts_stub._build_focus_chart = None
_types_stub = sys.modules["tbs_engine.types"]
if not hasattr(_types_stub, "GRACE_BUFFER_ATR_PCT"):
    _types_stub.GRACE_BUFFER_ATR_PCT = 0.0
    _types_stub.MetricsResult = None
_transform_stub = sys.modules["tbs_engine.transform"]
if not hasattr(_transform_stub, "_transform_output"):
    _transform_stub._transform_output = None
    _transform_stub._flatten = None
    _transform_stub._audit_key_coverage = None
    _transform_stub._error_output = None

_spec.loader.exec_module(_mod)
_annotate_exit_signal = _mod._annotate_exit_signal


# ---------------------------------------------------------------------------
# Shared diagnostic fragments
# ---------------------------------------------------------------------------
FLOOR_WARNING_TEMPLATE = (
    "FLOOR WARNING (2/4 bars below floor). "
    "Note: Exit_Signal activates after 3 consecutive closes below floor ({frac} bars)."
)


def _make_floor_diag(frac="2/3"):
    return FLOOR_WARNING_TEMPLATE.format(frac=frac)


# ---------------------------------------------------------------------------
# Test 1: FLOOR WARNING + SMA breach EXIT
# ---------------------------------------------------------------------------
def test_01_floor_warning_sma_breach_exit():
    diag = _make_floor_diag("2/3")
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # OTL-003: forward-looking note replaced
    assert "Exit_Signal activates after" not in result
    assert "Exit_Signal ACTIVE" in result
    assert "EXIT via Close below 50-SMA" in result
    assert "(independent of floor counter at 2/3)" in result

    # OTL-002: suffix appended
    assert result.endswith("[ACTIVE EXIT: Close below 50-SMA]")


# ---------------------------------------------------------------------------
# Test 2: FLOOR WARNING + no other exit (Exit_Signal=False)
# ---------------------------------------------------------------------------
def test_02_floor_warning_no_exit():
    diag = _make_floor_diag("1/3")
    metrics = {"Exit_Signal": False, "Exit_Reason": "None"}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # Neither OTL-003 nor OTL-002 fires
    assert result == diag


# ---------------------------------------------------------------------------
# Test 3: FLOOR WARNING + VWAP EXIT at threshold (3/3)
# ---------------------------------------------------------------------------
def test_03_floor_warning_vwap_exit_threshold():
    diag = _make_floor_diag("3/3")
    exit_reason = "VWAP Violation (3 consecutive bar(s) below floor -- strict Sec X counter)"
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": exit_reason}
    result = _annotate_exit_signal("HALT", diag, metrics)

    assert "Exit_Signal activates after" not in result
    assert "Exit_Signal ACTIVE" in result
    assert f"EXIT via {exit_reason}" in result
    assert "(independent of floor counter at 3/3)" in result
    assert result.endswith(f"[ACTIVE EXIT: {exit_reason}]")


# ---------------------------------------------------------------------------
# Test 4: FLOOR WARNING + EMA WARNING
# ---------------------------------------------------------------------------
def test_04_floor_warning_ema_warning():
    diag = _make_floor_diag("1/3")
    exit_reason = "Close below EMA 8 (Convexity active)"
    metrics = {"Exit_Signal": "WARNING", "Exit_Reason": exit_reason}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # OTL-003: note corrected with WARNING
    assert "Exit_Signal activates after" not in result
    assert "WARNING via Close below EMA 8 (Convexity active)" in result
    assert "(independent of floor counter at 1/3)" in result

    # OTL-002: WARNING suffix
    assert result.endswith(f"[EXIT WARNING: {exit_reason}]")


# ---------------------------------------------------------------------------
# Test 5: Non-floor HALT + EXIT
# ---------------------------------------------------------------------------
def test_05_non_floor_halt_exit():
    diag = "WAIT (reason: AMBIGUOUS STATE). Volume below threshold."
    exit_reason = "Close below EMA 8 (2 consecutive) -- C-3 thesis invalidation"
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": exit_reason}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # OTL-003 does NOT fire (no floor note marker)
    assert "WAIT (reason: AMBIGUOUS STATE). Volume below threshold." in result

    # OTL-002: suffix appended
    assert result.endswith(f"[ACTIVE EXIT: {exit_reason}]")


# ---------------------------------------------------------------------------
# Test 6: Non-floor HALT + WARNING
# ---------------------------------------------------------------------------
def test_06_non_floor_halt_warning():
    diag = "WAIT (reason: MID-RANGE). Consolidation zone."
    exit_reason = "Close below EMA 8 (Convexity active)"
    metrics = {"Exit_Signal": "WARNING", "Exit_Reason": exit_reason}
    result = _annotate_exit_signal("HALT", diag, metrics)

    assert "WAIT (reason: MID-RANGE). Consolidation zone." in result
    assert result.endswith(f"[EXIT WARNING: {exit_reason}]")


# ---------------------------------------------------------------------------
# Test 7: Non-floor HALT + no exit
# ---------------------------------------------------------------------------
def test_07_non_floor_halt_no_exit():
    diag = "WAIT (reason: AMBIGUOUS STATE). Volume below threshold."
    metrics = {"Exit_Signal": False, "Exit_Reason": "None"}
    result = _annotate_exit_signal("HALT", diag, metrics)
    assert result == diag


# ---------------------------------------------------------------------------
# Test 8: PASS + EXIT — PASS diagnostics excluded
# ---------------------------------------------------------------------------
def test_08_pass_exit_excluded():
    diag = "PRE-APPROVED: All gates cleared."
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("PASS", diag, metrics)
    assert result == diag


# ---------------------------------------------------------------------------
# Test 9: REJECT + EXIT (FLOOR FAILURE) — suffix only
# ---------------------------------------------------------------------------
def test_09_reject_exit_floor_failure():
    diag = "REJECT (reason: FLOOR FAILURE). Price below structural floor."
    exit_reason = "FLOOR FAILURE OVERRIDE: structural break"
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": exit_reason}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # No floor counter marker in REJECT diagnostics
    assert "Exit_Signal ACTIVE" not in result

    # Suffix appended
    assert result.endswith(f"[ACTIVE EXIT: {exit_reason}]")


# ---------------------------------------------------------------------------
# Test 10: ERROR + EXIT — ERROR excluded
# ---------------------------------------------------------------------------
def test_10_error_exit_excluded():
    diag = "ERROR: insufficient data for evaluation."
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("ERROR", diag, metrics)
    assert result == diag


# ---------------------------------------------------------------------------
# Test 11: Exit_Signal missing from metrics entirely
# ---------------------------------------------------------------------------
def test_11_exit_signal_missing():
    diag = "WAIT (reason: AMBIGUOUS STATE). Volume below threshold."
    metrics = {}  # no Exit_Signal key at all
    result = _annotate_exit_signal("HALT", diag, metrics)
    assert result == diag


# ---------------------------------------------------------------------------
# Test 12: Exit_Reason is "None" string — still annotates
# ---------------------------------------------------------------------------
def test_12_exit_reason_none_string():
    diag = _make_floor_diag("2/3")
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "None"}
    result = _annotate_exit_signal("HALT", diag, metrics)

    # OTL-003 fires with "None" reason
    assert "EXIT via None" in result
    assert "(independent of floor counter at 2/3)" in result

    # OTL-002 fires with "None" reason
    assert result.endswith("[ACTIVE EXIT: None]")


# ===========================================================================
# GAP-CLOSING TESTS — Coverage holes identified during review
# ===========================================================================

# ---------------------------------------------------------------------------
# Realistic diagnostic from gates.py _gate_floor_violation_active (BHP-style)
# ---------------------------------------------------------------------------
BHP_STYLE_DIAG = (
    "WAIT (reason: FLOOR WARNING ACTIVE). "
    "FLOOR WARNING ACTIVE: 2/4 consecutive bars below Floor (71.23). "
    "Current bar has NOT reclaimed (Close 70.62 < Floor). "
    "Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
    "Note: Exit_Signal activates after 3 consecutive closes below floor (2/3 bars)."
)


def test_13_realistic_bhp_diagnostic_otl003_fires():
    """Full-length production diagnostic from gates.py — multiple parenthesized
    segments before the note. Confirms rfind('(') targets the correct '(' in
    the note tail, not earlier floor-price or reclaim-check parens."""
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("HALT", BHP_STYLE_DIAG, metrics)

    # OTL-003: forward-looking note replaced
    assert "Exit_Signal activates after" not in result
    # Fraction extracted correctly despite earlier parens
    assert "(independent of floor counter at 2/3)" in result

    # OTL-002: suffix appended
    assert result.endswith("[ACTIVE EXIT: Close below 50-SMA]")


def test_14_realistic_diagnostic_prefix_preserved():
    """Everything before the Note: marker must survive intact."""
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("HALT", BHP_STYLE_DIAG, metrics)

    expected_prefix = (
        "WAIT (reason: FLOOR WARNING ACTIVE). "
        "FLOOR WARNING ACTIVE: 2/4 consecutive bars below Floor (71.23). "
        "Current bar has NOT reclaimed (Close 70.62 < Floor). "
        "Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
    )
    assert result.startswith(expected_prefix)


def test_15_exact_corrected_note_format():
    """Assert the full corrected note string including the -- delimiter,
    not just substring fragments."""
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("HALT", BHP_STYLE_DIAG, metrics)

    expected_note = (
        "Note: Exit_Signal ACTIVE -- EXIT via Close below 50-SMA "
        "(independent of floor counter at 2/3)."
    )
    assert expected_note in result


def test_16_compute_py_precheck_diagnostic():
    """Diagnostic from compute.py _evaluate_precheck (line 611-614).
    Same note pattern, slightly different surrounding text (no floor_price in
    reclaim parenthetical). Confirms both source sites are handled."""
    precheck_diag = (
        "WAIT (reason: FLOOR WARNING ACTIVE). "
        "FLOOR WARNING ACTIVE: 1/4 consecutive bars below Floor (88.48). "
        "Current bar has NOT reclaimed (Close 87.20 < Floor). "
        "Mandate: HARD WAIT. Entry only valid on confirmed reclaim close above floor. "
        "Note: Exit_Signal activates after 3 consecutive closes below floor (1/3 bars)."
    )
    metrics = {"Exit_Signal": "WARNING", "Exit_Reason": "Close below established Hourly Low"}
    result = _annotate_exit_signal("HALT", precheck_diag, metrics)

    assert "Exit_Signal activates after" not in result
    assert "(independent of floor counter at 1/3)" in result
    assert "WARNING via Close below established Hourly Low" in result
    assert result.endswith("[EXIT WARNING: Close below established Hourly Low]")


def test_17_trailing_text_after_note():
    """Hypothetical: text exists after the floor note sentence.
    OTL-003 should replace only the note sentence, leaving trailing text intact."""
    diag = (
        "FLOOR WARNING. "
        "Note: Exit_Signal activates after 3 consecutive closes below floor (2/3 bars). "
        "Additional trailing context here."
    )
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("HALT", diag, metrics)

    assert "Exit_Signal activates after" not in result
    assert "Additional trailing context here." in result
    assert "(independent of floor counter at 2/3)." in result


def test_18_pass_with_floor_marker_and_exit():
    """PASS + floor marker + EXIT: OTL-003 SHOULD fire (marker + exit present),
    OTL-002 should NOT fire (PASS excluded from suffix).
    Edge case — unlikely in production since PASS means gates cleared."""
    diag = _make_floor_diag("1/3")
    metrics = {"Exit_Signal": "EXIT", "Exit_Reason": "Close below 50-SMA"}
    result = _annotate_exit_signal("PASS", diag, metrics)

    # OTL-003 fires — corrects the misleading note
    assert "Exit_Signal activates after" not in result
    assert "Exit_Signal ACTIVE -- EXIT via Close below 50-SMA" in result
    assert "(independent of floor counter at 1/3)" in result

    # OTL-002 does NOT fire — PASS excluded
    assert "[ACTIVE EXIT:" not in result


def test_19_exit_reason_key_missing():
    """Exit_Signal present but Exit_Reason key entirely absent from metrics.
    .get("Exit_Reason", "None") should default gracefully."""
    diag = "WAIT (reason: DIRECTIONAL BLOCK). -DI > +DI."
    metrics = {"Exit_Signal": "EXIT"}  # no Exit_Reason key
    result = _annotate_exit_signal("HALT", diag, metrics)

    assert result.endswith("[ACTIVE EXIT: None]")


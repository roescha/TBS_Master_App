"""VOL-004: Volume Display Enhancement — unit tests.

Tests C1 (Session Volume), C2 (Bar Volume), C3 (K/M Formatting),
C4 (VTRIG-001 Pace Label), and regression guards.
"""
import sys, os, types, importlib.util, math, pytest

# ---------------------------------------------------------------------------
# Isolate output.py + transform.py from heavy transitive deps
# ---------------------------------------------------------------------------
_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

if "tbs_engine" not in sys.modules:
    _pkg = types.ModuleType("tbs_engine")
    _pkg.__path__ = [os.path.join(_root, "tbs_engine")]
    sys.modules["tbs_engine"] = _pkg

for mod_name in [
    "tbs_engine.types", "tbs_engine.helpers",
    "tbs_engine.charts", "tbs_engine.transform",
]:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        m.GRACE_BUFFER_ATR_PCT = 0.0
        m.MetricsResult = type("MetricsResult", (), {})
        m.GateResult = type("GateResult", (), {})
        m._clamp = lambda *a, **k: None
        m.check_climax_history = lambda *a, **k: None
        m._build_focus_chart = lambda *a, **k: None
        m._transform_output = lambda *a, **k: None
        m._flatten = lambda *a, **k: None
        m._audit_key_coverage = lambda *a, **k: None
        m._error_output = lambda *a, **k: None
        sys.modules[mod_name] = m

# Load output.py (for _compute_volume_confirmation)
if "tbs_engine.output" in sys.modules:
    _output_mod = sys.modules["tbs_engine.output"]
else:
    spec = importlib.util.spec_from_file_location(
        "tbs_engine.output", os.path.join(_root, "tbs_engine", "output.py"))
    _output_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_output_mod)

_compute_volume_confirmation = _output_mod._compute_volume_confirmation

# Load transform.py (for _format_volume, _format_dollar_volume, _flatten, _transform_output)
# Need real transform for formatting + flatten tests
_transform_path = os.path.join(_root, "tbs_engine", "transform.py")
_tspec = importlib.util.spec_from_file_location("tbs_engine.transform_real", _transform_path)
_transform_mod = importlib.util.module_from_spec(_tspec)
_tspec.loader.exec_module(_transform_mod)

_format_volume = _transform_mod._format_volume
_format_dollar_volume = _transform_mod._format_dollar_volume
_flatten = _transform_mod._flatten
_transform_output = _transform_mod._transform_output
_all_mapped_flat_keys = _transform_mod._all_mapped_flat_keys
MAPPED_FLAT_KEYS = _transform_mod.MAPPED_FLAT_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metrics(adv_20, session_volume=None, bar_volume=None):
    m = {"ADV_20": adv_20}
    if session_volume is not None:
        m["Session_Volume"] = session_volume
    if bar_volume is not None:
        m["Bar_Volume"] = bar_volume
    return m


# ===========================================================================
# C1 — Session Volume
# ===========================================================================

class TestC1SessionVolumeProfileA:
    """Session_Volume populated for Profile A."""

    def test_session_volume_int(self):
        """Profile A with valid session volume → int in metrics."""
        m = _make_metrics(4_200_000, session_volume=850_000)
        r = _compute_volume_confirmation(m)
        assert r["session_volume"] == 850_000

    def test_session_volume_formatted(self):
        """Profile A → session_volume_formatted is present."""
        m = _make_metrics(4_200_000, session_volume=850_000)
        r = _compute_volume_confirmation(m)
        assert r["session_volume_formatted"] == "850K"

    def test_session_volume_nan_becomes_none(self):
        """Session_Volume = None → fields are None."""
        m = _make_metrics(4_200_000)  # no Session_Volume key
        r = _compute_volume_confirmation(m)
        assert r["session_volume"] is None
        assert r["session_volume_formatted"] is None
        assert r["pace"] is None


class TestC1SessionVolumeProfileBC:
    """Session_Volume is None for Profile B/C."""

    def test_profile_b_none(self):
        m = {"ADV_20": 4_200_000, "Session_Volume": None}
        r = _compute_volume_confirmation(m)
        assert r["session_volume"] is None
        assert r["pace"] is None

    def test_profile_c_none(self):
        m = {"ADV_20": 4_200_000}  # Session_Volume absent
        r = _compute_volume_confirmation(m)
        assert r["session_volume"] is None
        assert r["pace"] is None


# ===========================================================================
# C2 — Bar Volume (tested via transform grouped output)
# ===========================================================================

class TestC2BarVolume:
    """Bar_Volume appears in grouped output under trade_quality.volume.bar_volume."""

    def test_bar_volume_value(self):
        flat = {"Bar_Volume": 285000.0, "ADV_20": 5_000_000}
        # Build minimal action_summary
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        bv = vol.get("bar_volume", {})
        assert bv["value"] == 285000.0

    def test_bar_volume_zero(self):
        flat = {"Bar_Volume": 0.0, "ADV_20": 5_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        bv = vol.get("bar_volume", {})
        assert bv["value"] == 0.0

    def test_bar_volume_formatted(self):
        flat = {"Bar_Volume": 285000.0}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        bv = vol.get("bar_volume", {})
        assert bv["formatted"] == "285K"


# ===========================================================================
# C3 — K/M Formatting
# ===========================================================================

class TestC3FormatVolume:
    """_format_volume unit tests."""

    def test_sub_thousand(self):
        assert _format_volume(952) == "952"

    def test_zero(self):
        assert _format_volume(0) == "0"

    def test_low_k(self):
        assert _format_volume(1500) == "1.5K"

    def test_mid_k(self):
        # 641,000 → 641.0K  (k=641, >= 100 → int format)
        assert _format_volume(641000) == "641K"

    def test_millions(self):
        assert _format_volume(4275938) == "4.28M"

    def test_none(self):
        assert _format_volume(None) is None

    def test_negative(self):
        assert _format_volume(-100) is None

    def test_large_m(self):
        assert _format_volume(125_000_000) == "125M"

    def test_exact_thousand(self):
        assert _format_volume(1000) == "1.0K"

    def test_exact_million(self):
        assert _format_volume(1_000_000) == "1.00M"

    def test_string_input(self):
        assert _format_volume("285000") == "285K"

    def test_invalid_string(self):
        assert _format_volume("abc") is None


class TestC3FormatDollarVolume:
    """_format_dollar_volume unit tests."""

    def test_dollar_prefix(self):
        assert _format_dollar_volume(4_275_938) == "$4.28M"

    def test_dollar_k(self):
        assert _format_dollar_volume(641_000) == "$641K"

    def test_dollar_none(self):
        assert _format_dollar_volume(None) is None


class TestC3FormattedSubFields:
    """Formatted sub-fields appear in grouped output."""

    def test_avg_daily_volume_formatted(self):
        flat = {"ADV_20": 4_200_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        ts = grouped.get("trade_snapshot", {})
        adv = ts.get("avg_daily_volume", {})
        assert adv["formatted"] == "4.20M"

    def test_avg_daily_dollar_volume_formatted(self):
        flat = {"ADV_20_Dollar": 630_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        addv = vol.get("avg_daily_dollar_volume", {})
        assert addv["formatted"] == "$630M"

    def test_bar_volume_formatted_present(self):
        flat = {"Bar_Volume": 1_234_567}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        bv = vol.get("bar_volume", {})
        assert bv["formatted"] == "1.23M"

    def test_session_volume_formatted_present(self):
        flat = {"Session_Volume": 2_500_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        sv = vol.get("session_volume", {})
        assert sv is not None
        assert sv["formatted"] == "2.50M"

    def test_session_volume_none_suppressed(self):
        flat = {}  # no Session_Volume
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        assert vol.get("session_volume") is None

    def test_checkpoint_min_shares_formatted(self):
        m = _make_metrics(4_200_000)
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["min_shares_formatted"] == "630K"
        assert r["checkpoints"]["30m"]["min_shares_formatted"] == "1.26M"
        assert r["checkpoints"]["60m"]["min_shares_formatted"] == "1.89M"


# ===========================================================================
# C4 — Pace Label
# ===========================================================================

class TestC4PaceLabel:
    """VTRIG-001 pace label: BELOW / TRACKING / CONFIRMED."""

    def test_below(self):
        """session_vol = 400K, 15m threshold = 630K → BELOW."""
        m = _make_metrics(4_200_000, session_volume=400_000)
        r = _compute_volume_confirmation(m)
        assert r["pace"] == "BELOW"

    def test_tracking(self):
        """session_vol = 800K, 15m = 630K, 60m = 1.89M → TRACKING."""
        m = _make_metrics(4_200_000, session_volume=800_000)
        r = _compute_volume_confirmation(m)
        assert r["pace"] == "TRACKING"

    def test_confirmed(self):
        """session_vol = 2.1M, 60m = 1.89M → CONFIRMED."""
        m = _make_metrics(4_200_000, session_volume=2_100_000)
        r = _compute_volume_confirmation(m)
        assert r["pace"] == "CONFIRMED"

    def test_none_when_no_session_vol(self):
        """Profile B → session_vol None → pace None."""
        m = _make_metrics(4_200_000)  # no Session_Volume
        r = _compute_volume_confirmation(m)
        assert r["pace"] is None

    def test_none_explicit_none(self):
        """Explicitly None session volume → pace None."""
        m = {"ADV_20": 4_200_000, "Session_Volume": None}
        r = _compute_volume_confirmation(m)
        assert r["pace"] is None

    def test_boundary_exact_15m(self):
        """session_vol exactly = 15m threshold → TRACKING."""
        m = _make_metrics(4_200_000, session_volume=630_000)
        r = _compute_volume_confirmation(m)
        assert r["pace"] == "TRACKING"

    def test_boundary_exact_60m(self):
        """session_vol exactly = 60m threshold → CONFIRMED."""
        m = _make_metrics(4_200_000, session_volume=1_890_000)
        r = _compute_volume_confirmation(m)
        assert r["pace"] == "CONFIRMED"

    def test_volume_confirmation_fields_present(self):
        """volume_confirmation dict has session_volume, session_volume_formatted, pace."""
        m = _make_metrics(4_200_000, session_volume=1_000_000)
        r = _compute_volume_confirmation(m)
        assert "session_volume" in r
        assert "session_volume_formatted" in r
        assert "pace" in r
        assert r["session_volume"] == 1_000_000
        assert r["session_volume_formatted"] == "1.00M"
        assert r["pace"] == "TRACKING"


# ===========================================================================
# Regression guards
# ===========================================================================

class TestRegressionRVOL:
    """Existing RVOL computation unchanged."""

    def test_rvol_not_formatted(self):
        """RVOL is a ratio — no K/M formatting applied."""
        flat = {"RVOL_Value": 1.19, "RVOL_Label": "NORMAL"}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        rvol = vol.get("rvol", {})
        assert rvol["value"] == 1.19
        assert rvol["label"] == "NORMAL"
        assert "formatted" not in rvol


class TestRegressionADV:
    """Existing ADV_20 and ADV_20_Dollar values unchanged."""

    def test_adv_20_value_preserved(self):
        flat = {"ADV_20": 5_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        ts = grouped.get("trade_snapshot", {})
        adv = ts.get("avg_daily_volume", {})
        assert adv["value"] == 5_000_000

    def test_adv_20_dollar_value_preserved(self):
        flat = {"ADV_20_Dollar": 750_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat)
        tq = grouped.get("trade_quality", {})
        vol = tq.get("volume", {})
        addv = vol.get("avg_daily_dollar_volume", {})
        assert addv["value"] == 750_000_000


class TestRegressionVTRIG:
    """Existing VTRIG-001 checkpoint min_shares values unchanged."""

    def test_standard_tier_checkpoints(self):
        m = _make_metrics(4_200_000)
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["min_shares"] == 630_000
        assert r["checkpoints"]["30m"]["min_shares"] == 1_260_000
        assert r["checkpoints"]["60m"]["min_shares"] == 1_890_000

    def test_thick_tier_checkpoints(self):
        m = _make_metrics(35_000_000)
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["min_shares"] == 4_200_000

    def test_thin_tier_checkpoints(self):
        m = _make_metrics(800_000)
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["min_shares"] == 200_000


class TestRegressionFlatKeys:
    """Bar_Volume and Session_Volume registered in MAPPED_FLAT_KEYS."""

    def test_bar_volume_registered(self):
        assert "Bar_Volume" in MAPPED_FLAT_KEYS

    def test_session_volume_registered(self):
        assert "Session_Volume" in MAPPED_FLAT_KEYS


class TestRegressionFlattenRoundTrip:
    """Grouped → flat → grouped produces identical values for VOL-004 fields."""

    def test_bar_volume_roundtrip(self):
        flat_in = {"Bar_Volume": 285000.0, "ADV_20": 5_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat_in)
        flat_out_tuple = _flatten(grouped)
        flat_out = flat_out_tuple[2] if isinstance(flat_out_tuple, tuple) else flat_out_tuple
        assert flat_out.get("Bar_Volume") == 285000.0

    def test_session_volume_roundtrip(self):
        flat_in = {"Session_Volume": 2_500_000, "ADV_20": 5_000_000}
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat_in)
        flat_out_tuple = _flatten(grouped)
        flat_out = flat_out_tuple[2] if isinstance(flat_out_tuple, tuple) else flat_out_tuple
        assert flat_out.get("Session_Volume") == 2_500_000

    def test_session_volume_none_roundtrip(self):
        flat_in = {"ADV_20": 5_000_000}  # no Session_Volume
        action_summary = {"status": "VALID", "diagnostic": "test"}
        grouped = _transform_output(action_summary, flat_in)
        flat_out_tuple = _flatten(grouped)
        flat_out = flat_out_tuple[2] if isinstance(flat_out_tuple, tuple) else flat_out_tuple
        # session_volume is None in grouped → no extraction
        assert flat_out.get("Session_Volume") is None


# ===========================================================================
# Checkpoint time localization (VTRIG-001 bug fix)
# ===========================================================================

class TestCheckpointTimeLocalization:
    """Checkpoint times reflect local exchange timezone, not hardcoded ET."""

    def test_us_default_et(self):
        """No _tz_label → defaults to ET times."""
        m = {"ADV_20": 5_000_000}
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["time"] == "09:45 ET"
        assert r["checkpoints"]["30m"]["time"] == "10:00 ET"
        assert r["checkpoints"]["60m"]["time"] == "10:30 ET"

    def test_explicit_et(self):
        """_tz_label = ET → US times."""
        m = {"ADV_20": 5_000_000, "_tz_label": "ET"}
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["time"] == "09:45 ET"
        assert r["checkpoints"]["30m"]["time"] == "10:00 ET"
        assert r["checkpoints"]["60m"]["time"] == "10:30 ET"

    def test_london_times(self):
        """_tz_label = London → LSE times (open 08:00)."""
        m = {"ADV_20": 5_000_000, "_tz_label": "London"}
        r = _compute_volume_confirmation(m)
        assert r["checkpoints"]["15m"]["time"] == "08:15 London"
        assert r["checkpoints"]["30m"]["time"] == "08:30 London"
        assert r["checkpoints"]["60m"]["time"] == "09:00 London"

    def test_unknown_tz_falls_back_to_et(self):
        """Unknown _tz_label → falls back to US open times."""
        m = {"ADV_20": 5_000_000, "_tz_label": "CET"}
        r = _compute_volume_confirmation(m)
        # Falls back to 9:30 open, but uses the provided label
        assert r["checkpoints"]["15m"]["time"] == "09:45 CET"
        assert r["checkpoints"]["30m"]["time"] == "10:00 CET"
        assert r["checkpoints"]["60m"]["time"] == "10:30 CET"

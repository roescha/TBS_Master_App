"""VTRIG-001: Session Volume Confirmation Trigger — Phase 1 unit tests.

Tests the _compute_volume_confirmation() pure function directly.
"""
import sys, os, types, importlib.util, pytest

# ---------------------------------------------------------------------------
# Isolate output.py from heavy transitive deps (ib_insync, etc.)
# We only need the pure _compute_volume_confirmation function + constants.
# ---------------------------------------------------------------------------
_root = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _root)

# Stub out all tbs_engine sub-modules that output.py imports
# Only stub modules that aren't already loaded (avoids poisoning
# sys.modules when running in the full test suite with real deps).
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

if "tbs_engine.output" in sys.modules:
    _compute_volume_confirmation = sys.modules["tbs_engine.output"]._compute_volume_confirmation
else:
    spec = importlib.util.spec_from_file_location(
        "tbs_engine.output", os.path.join(_root, "tbs_engine", "output.py"))
    _output = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_output)
    _compute_volume_confirmation = _output._compute_volume_confirmation


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_metrics(adv_20):
    return {"ADV_20": adv_20}


# ---------------------------------------------------------------------------
# TC-01: THICK tier (AVGO-like)
# ---------------------------------------------------------------------------

class TestTC01ThickTier:
    def test_tier_label(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["liquidity_tier"] == "THICK"

    def test_multiplier(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["multiplier"] == 1.2

    def test_15m(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["checkpoints"]["15m"]["min_shares"] == 4_200_000

    def test_30m(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["checkpoints"]["30m"]["min_shares"] == 8_400_000

    def test_60m(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["checkpoints"]["60m"]["min_shares"] == 12_600_000

    def test_adv_20_shares(self):
        r = _compute_volume_confirmation(_make_metrics(35_000_000))
        assert r["adv_20_shares"] == 35_000_000


# ---------------------------------------------------------------------------
# TC-02: STANDARD tier (CTVA-like)
# ---------------------------------------------------------------------------

class TestTC02StandardTier:
    def test_tier_label(self):
        r = _compute_volume_confirmation(_make_metrics(4_200_000))
        assert r["liquidity_tier"] == "STANDARD"

    def test_multiplier(self):
        r = _compute_volume_confirmation(_make_metrics(4_200_000))
        assert r["multiplier"] == 1.5

    def test_15m(self):
        r = _compute_volume_confirmation(_make_metrics(4_200_000))
        assert r["checkpoints"]["15m"]["min_shares"] == 630_000

    def test_30m(self):
        r = _compute_volume_confirmation(_make_metrics(4_200_000))
        assert r["checkpoints"]["30m"]["min_shares"] == 1_260_000

    def test_60m(self):
        r = _compute_volume_confirmation(_make_metrics(4_200_000))
        assert r["checkpoints"]["60m"]["min_shares"] == 1_890_000


# ---------------------------------------------------------------------------
# TC-03: THIN tier
# ---------------------------------------------------------------------------

class TestTC03ThinTier:
    def test_tier_label(self):
        r = _compute_volume_confirmation(_make_metrics(800_000))
        assert r["liquidity_tier"] == "THIN"

    def test_multiplier(self):
        r = _compute_volume_confirmation(_make_metrics(800_000))
        assert r["multiplier"] == 2.5

    def test_15m(self):
        r = _compute_volume_confirmation(_make_metrics(800_000))
        assert r["checkpoints"]["15m"]["min_shares"] == 200_000

    def test_30m(self):
        r = _compute_volume_confirmation(_make_metrics(800_000))
        assert r["checkpoints"]["30m"]["min_shares"] == 400_000

    def test_60m(self):
        r = _compute_volume_confirmation(_make_metrics(800_000))
        assert r["checkpoints"]["60m"]["min_shares"] == 600_000


# ---------------------------------------------------------------------------
# TC-04: ERROR path — ADV_20 = None
# ---------------------------------------------------------------------------

class TestTC04ErrorPath:
    def test_none_adv(self):
        assert _compute_volume_confirmation({"ADV_20": None}) is None

    def test_missing_adv(self):
        assert _compute_volume_confirmation({}) is None

    def test_zero_adv(self):
        assert _compute_volume_confirmation({"ADV_20": 0}) is None

    def test_negative_adv(self):
        assert _compute_volume_confirmation({"ADV_20": -1}) is None


# ---------------------------------------------------------------------------
# TC-05: INVALID path with ADV_20 populated
# ---------------------------------------------------------------------------

class TestTC05InvalidPathPopulated:
    """ADV_20 = 5,000,000 → STANDARD tier, thresholds populated."""

    def test_populated(self):
        r = _compute_volume_confirmation(_make_metrics(5_000_000))
        assert r is not None
        assert r["liquidity_tier"] == "STANDARD"
        assert r["checkpoints"]["15m"]["min_shares"] == 750_000
        assert r["checkpoints"]["30m"]["min_shares"] == 1_500_000
        assert r["checkpoints"]["60m"]["min_shares"] == 2_250_000


# ---------------------------------------------------------------------------
# TC-06: Profile uniformity
# ---------------------------------------------------------------------------

class TestTC06ProfileUniformity:
    """Same ADV_20 across profiles A, B, C → identical volume_confirmation."""

    def test_uniform(self):
        adv = 6_000_000
        results = [_compute_volume_confirmation(_make_metrics(adv)) for _ in range(3)]
        assert results[0] == results[1] == results[2]


# ---------------------------------------------------------------------------
# TC-07: Boundary cases
# ---------------------------------------------------------------------------

class TestTC07Boundaries:
    def test_2m_is_standard(self):
        """ADV_20 = 2,000,000 → STANDARD (inclusive lower bound)."""
        r = _compute_volume_confirmation(_make_metrics(2_000_000))
        assert r["liquidity_tier"] == "STANDARD"

    def test_10m_is_standard(self):
        """ADV_20 = 10,000,000 → STANDARD (inclusive upper bound)."""
        r = _compute_volume_confirmation(_make_metrics(10_000_000))
        assert r["liquidity_tier"] == "STANDARD"

    def test_1999999_is_thin(self):
        """ADV_20 = 1,999,999 → THIN."""
        r = _compute_volume_confirmation(_make_metrics(1_999_999))
        assert r["liquidity_tier"] == "THIN"

    def test_10000001_is_thick(self):
        """ADV_20 = 10,000,001 → THICK."""
        r = _compute_volume_confirmation(_make_metrics(10_000_001))
        assert r["liquidity_tier"] == "THICK"

    def test_checkpoint_times(self):
        """All checkpoints carry correct ET times."""
        r = _compute_volume_confirmation(_make_metrics(5_000_000))
        assert r["checkpoints"]["15m"]["time"] == "09:45 ET"
        assert r["checkpoints"]["30m"]["time"] == "10:00 ET"
        assert r["checkpoints"]["60m"]["time"] == "10:30 ET"

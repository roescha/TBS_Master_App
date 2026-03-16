"""PE-40: Crypto Asset Interim Mitigation Guard — Unit Tests.

Verification matrix (from PE-40 prompt):
  V1: BTC  → HALT/REJECT with UNSUPPORTED ASSET CLASS, no IBKR connection
  V2: ETH  → same rejection
  V3: Normal equity (AAPL, MSFT) → guard does NOT fire
  V4: Crypto-adjacent equity (MSTR, COIN) → guard does NOT fire
  V5: Return structure matches existing early-return error paths
  V6: CRYPTO_TICKERS defined at module level, not inside a function
  V7: (Verified by diff — purely additive, no test needed)
  V8: CRYPTO_TICKERS is importable
"""

import sys
import ast
import inspect
import pytest
from unittest.mock import MagicMock, patch, call

# Stub heavy dependencies before importing engine modules
for _mod in ("ib_insync", "pandas_ta", "plotly", "plotly.graph_objects", "plotly.subplots"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from tbs_engine.data import _fetch_and_compute, CRYPTO_TICKERS, _build_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Standard arguments for _fetch_and_compute (profile B, equity defaults)
_BASE_KWARGS = dict(
    p_code="B",
    cfg=_build_config("B"),
    profile="TREND",
    is_etf_arg=False,
    mode="INFO",
    exchange="SMART",
    currency="USD",
    convexity_class="C1",
)


def _call_engine(ticker, **overrides):
    """Call _fetch_and_compute with standard defaults + optional overrides."""
    kwargs = {**_BASE_KWARGS, **overrides}
    return _fetch_and_compute(ticker, **kwargs)


# ---------------------------------------------------------------------------
# V8: CRYPTO_TICKERS is importable and correct
# ---------------------------------------------------------------------------

class TestCryptoTickersConstant:
    """V6 + V8: The set exists at module level and is importable."""

    def test_importable(self):
        """V8: from tbs_engine.data import CRYPTO_TICKERS succeeds."""
        assert CRYPTO_TICKERS is not None
        assert isinstance(CRYPTO_TICKERS, set)

    def test_contains_expected_tickers(self):
        """All 10 specified tickers are present."""
        expected = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "MATIC"}
        assert CRYPTO_TICKERS == expected

    def test_module_level_definition(self):
        """V6: CRYPTO_TICKERS is defined at module scope, not inside a function."""
        source_path = inspect.getfile(sys.modules["tbs_engine.data"])
        tree = ast.parse(open(source_path).read())
        # Module-level assignments are direct children of the Module node
        module_level_names = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module_level_names.append(target.id)
        assert "CRYPTO_TICKERS" in module_level_names, \
            "CRYPTO_TICKERS must be a module-level assignment, not nested in a function"

    def test_exported_in_all(self):
        """CRYPTO_TICKERS is listed in __all__ for public API visibility."""
        import tbs_engine.data as mod
        assert "CRYPTO_TICKERS" in mod.__all__


# ---------------------------------------------------------------------------
# V1 + V2: Crypto tickers → HALT / REJECT (UNSUPPORTED ASSET CLASS)
# ---------------------------------------------------------------------------

class TestCryptoGuardRejects:
    """The guard must return HALT + REJECT before any IBKR call."""

    @pytest.mark.parametrize("ticker", ["BTC", "ETH", "SOL", "XRP", "ADA",
                                         "DOGE", "AVAX", "DOT", "LINK", "MATIC"])
    def test_all_crypto_tickers_rejected(self, ticker):
        """Every ticker in CRYPTO_TICKERS produces HALT/REJECT."""
        df, raw = _call_engine(ticker)
        assert df is None, f"{ticker} should return None DataFrame"
        assert "_early_return" in raw, f"{ticker} should set _early_return"
        status, diag, metrics = raw["_early_return"]
        assert status == "HALT"
        assert "REJECT" in diag
        assert "UNSUPPORTED ASSET CLASS" in diag

    def test_btc_diagnostic_content(self):
        """V1: BTC diagnostic contains required context strings."""
        _, raw = _call_engine("BTC")
        diag = raw["_early_return"][1]
        assert "BTC" in diag
        assert "cryptocurrency" in diag
        assert "ETF proxy" in diag
        assert "CRYPTO-001" in diag
        assert "Stock()" in diag

    def test_eth_diagnostic_content(self):
        """V2: ETH diagnostic contains required context strings."""
        _, raw = _call_engine("ETH")
        diag = raw["_early_return"][1]
        assert "ETH" in diag
        assert "UNSUPPORTED ASSET CLASS" in diag

    def test_lowercase_ticker_rejected(self):
        """Guard normalises via ticker.upper() — lowercase 'btc' must also reject."""
        _, raw = _call_engine("btc")
        assert "_early_return" in raw
        assert raw["_early_return"][0] == "HALT"
        assert "UNSUPPORTED ASSET CLASS" in raw["_early_return"][1]

    def test_mixed_case_ticker_rejected(self):
        """Mixed case 'Eth' normalises to 'ETH' and rejects."""
        _, raw = _call_engine("Eth")
        assert "_early_return" in raw
        assert raw["_early_return"][0] == "HALT"


# ---------------------------------------------------------------------------
# V3 + V4: Equity tickers are NOT affected by the guard
# ---------------------------------------------------------------------------

class TestEquityUnaffected:
    """Normal equities and crypto-adjacent equities must NOT trigger the guard.

    Since we can't connect to IBKR in tests, we verify the guard does NOT
    fire by checking that _early_return is NOT set with UNSUPPORTED ASSET CLASS.
    The function will fail later (connection error), which is expected and
    proves the guard was bypassed.
    """

    @pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"])
    def test_normal_equities_bypass_guard(self, ticker):
        """V3: Standard equity tickers do not trigger UNSUPPORTED ASSET CLASS."""
        _, raw = _call_engine(ticker)
        if "_early_return" in raw:
            # It may fail for connection reasons, but NOT for crypto guard
            diag = raw["_early_return"][1]
            assert "UNSUPPORTED ASSET CLASS" not in diag, \
                f"{ticker} incorrectly rejected as crypto: {diag}"

    @pytest.mark.parametrize("ticker", ["MSTR", "COIN", "MARA", "RIOT", "GBTC"])
    def test_crypto_adjacent_equities_bypass_guard(self, ticker):
        """V4: Crypto-adjacent equities (MSTR, COIN, etc.) are not in CRYPTO_TICKERS."""
        assert ticker not in CRYPTO_TICKERS, \
            f"{ticker} should NOT be in CRYPTO_TICKERS"
        _, raw = _call_engine(ticker)
        if "_early_return" in raw:
            diag = raw["_early_return"][1]
            assert "UNSUPPORTED ASSET CLASS" not in diag, \
                f"{ticker} incorrectly rejected as crypto: {diag}"


# ---------------------------------------------------------------------------
# V5: Return structure matches existing early-return error paths
# ---------------------------------------------------------------------------

class TestReturnStructure:
    """The guard's return must match the (status, diagnostic, metrics) tuple
    pattern used by all other _early_return paths in _fetch_and_compute."""

    def test_return_is_none_and_dict(self):
        """Return value is (None, dict) — same as all error paths."""
        result = _call_engine("BTC")
        assert isinstance(result, tuple) and len(result) == 2
        df, raw = result
        assert df is None
        assert isinstance(raw, dict)

    def test_early_return_is_three_tuple(self):
        """_early_return value is a 3-tuple: (status, diagnostic, metrics)."""
        _, raw = _call_engine("BTC")
        early = raw["_early_return"]
        assert isinstance(early, tuple), f"Expected tuple, got {type(early)}"
        assert len(early) == 3, f"Expected 3-element tuple, got {len(early)}"

    def test_status_is_string(self):
        """First element (status) is a string."""
        _, raw = _call_engine("BTC")
        status = raw["_early_return"][0]
        assert isinstance(status, str)

    def test_diagnostic_is_string(self):
        """Second element (diagnostic) is a string."""
        _, raw = _call_engine("BTC")
        diag = raw["_early_return"][1]
        assert isinstance(diag, str)

    def test_metrics_is_dict(self):
        """Third element (metrics) is a dict — same as other HALT paths."""
        _, raw = _call_engine("BTC")
        metrics = raw["_early_return"][2]
        assert isinstance(metrics, dict)

    def test_metrics_contains_proximity_fields(self):
        """metrics dict contains EPX-001 Proximity_Signal fields
        (initialised before the guard fires)."""
        _, raw = _call_engine("BTC")
        metrics = raw["_early_return"][2]
        for field in ["Proximity_Signal", "Proximity_Blocking_Gate",
                      "Proximity_Distance", "Proximity_Target", "Proximity_Note"]:
            assert field in metrics, f"metrics missing {field}"

    def test_status_is_halt_not_error(self):
        """Status is HALT (structural rejection), not ERROR (exception)."""
        _, raw = _call_engine("BTC")
        assert raw["_early_return"][0] == "HALT"

    def test_diagnostic_uses_reject_not_wait(self):
        """Verdict prefix is REJECT (permanent), not WAIT (temporal)."""
        _, raw = _call_engine("BTC")
        diag = raw["_early_return"][1]
        assert diag.startswith("REJECT")
        assert "WAIT" not in diag


# ---------------------------------------------------------------------------
# Guard placement: fires BEFORE any IBKR interaction
# ---------------------------------------------------------------------------

class TestGuardPlacement:
    """The guard must prevent ib.connect(), Stock(), reqContractDetails,
    and reqHistoricalData from being called for crypto tickers."""

    def test_no_ib_connect_for_crypto(self):
        """ib.connect() must never be called for a crypto ticker."""
        with patch("tbs_engine.data.IB") as MockIB:
            mock_ib = MockIB.return_value
            _call_engine("BTC")
            mock_ib.connect.assert_not_called()

    def test_no_stock_constructor_for_crypto(self):
        """Stock() must never be called for a crypto ticker."""
        with patch("tbs_engine.data.Stock") as MockStock:
            _call_engine("SOL")
            MockStock.assert_not_called()

    def test_ib_connect_attempted_for_equity(self):
        """For normal equity, ib.connect() IS attempted (proving guard didn't fire)."""
        with patch("tbs_engine.data.IB") as MockIB:
            mock_ib = MockIB.return_value
            mock_ib.connect.side_effect = ConnectionRefusedError("No IBKR")
            _call_engine("AAPL")
            mock_ib.connect.assert_called_once()

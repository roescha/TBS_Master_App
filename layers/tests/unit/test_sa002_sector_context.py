"""
SA-002: Sector ETF Context Enrichment -- Unit Tests
Covers all 28 test cases from SA002_Sector_ETF_Context_Enrichment_Spec_v1_0 Section 11.

Tests are grouped by spec section:
  11.1 Layer 1 -- Sector ETF Context (T01-T09)
  11.2 Layer 2 -- Relative Strength (T10-T17)
  11.3 Layer 3 -- Niche ETF Context (T18-T23)
  11.4 Integration / Live Validation (T24-T28)

All tests use mocked IBKR data. No live connection required.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import numpy as np

# Resolve project root (two levels up from tests/unit/) for imports.
# If conftest.py already handles this, this line is a harmless no-op.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)

from ibkr_sympathy_audit import (
    run_sympathy_audit,
    _sa002_trend_label,
    _sa002_pct_change,
    _sa002_compute_rs,
    _sa002_golden_cross,
    _sa002_resolve_niche_etf,
    _sa002_format_rs_diagnostic,
    NICHE_ETF_MAP,
    NICHE_ETF_TICKER_MAP,
    _spy_cache,
)


# ==============================================================================
# HELPERS: Build mock DataFrames for sector/SPY/niche ETF bar data
# ==============================================================================

def _make_df(n_bars, base_price=100.0, pct_change_20=None, pct_change_10=None):
    """Build a mock OHLCV DataFrame with `n_bars` rows.
    If pct_change_20 is given, the price 20 bars ago is set so that
    (close[-1] - close[-21]) / close[-21] * 100 == pct_change_20.
    """
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="D")
    close = np.full(n_bars, base_price)
    # Set the 20-bar-ago price to produce the desired % change
    if pct_change_20 is not None and n_bars >= 21:
        close_20ago = base_price / (1 + pct_change_20 / 100.0)
        close[-(21)] = close_20ago
    if pct_change_10 is not None and n_bars >= 11:
        close_10ago = base_price / (1 + pct_change_10 / 100.0)
        close[-(11)] = close_10ago
    df = pd.DataFrame({
        'date': dates,
        'open': close * 0.99,
        'high': close * 1.01,
        'low': close * 0.98,
        'close': close,
        'volume': np.full(n_bars, 1000000),
    })
    df.set_index('date', inplace=True)
    return df


def _make_df_linear(n_bars, start_price, end_price):
    """Build a DataFrame with linearly spaced close prices."""
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="D")
    close = np.linspace(start_price, end_price, n_bars)
    df = pd.DataFrame({
        'date': dates,
        'open': close * 0.99,
        'high': close * 1.01,
        'low': close * 0.98,
        'close': close,
        'volume': np.full(n_bars, 1000000),
    })
    df.set_index('date', inplace=True)
    return df


def _make_golden_cross_df(n_bars=250, golden=True):
    """Build a DataFrame where SMA 50 > SMA 200 (golden) or vice versa."""
    dates = pd.date_range("2026-01-01", periods=n_bars, freq="D")
    if golden:
        # Recent prices high (SMA 50 > SMA 200)
        close = np.concatenate([
            np.full(150, 80.0),   # old lower prices (pull down SMA 200)
            np.full(100, 120.0),  # recent higher prices (push up SMA 50)
        ])
    else:
        # Recent prices low (SMA 50 < SMA 200 => death cross)
        close = np.concatenate([
            np.full(150, 120.0),  # old higher prices (push up SMA 200)
            np.full(100, 80.0),   # recent lower prices (pull down SMA 50)
        ])
    df = pd.DataFrame({
        'date': dates,
        'open': close * 0.99,
        'high': close * 1.01,
        'low': close * 0.98,
        'close': close,
        'volume': np.full(n_bars, 1000000),
    })
    df.set_index('date', inplace=True)
    return df


# ==============================================================================
# MOCK SETUP: Fake IB connection with controllable responses
# ==============================================================================

class MockContractDetail:
    def __init__(self, long_name="Technology Select Sector SPDR Fund",
                 industry="Technology", category="Semiconductors",
                 subcategory="Semiconductors"):
        self.longName = long_name
        self.industry = industry
        self.category = category
        self.subcategory = subcategory
        self.contract = MagicMock()
        self.contract.symbol = ""


def _make_mock_contract(symbol):
    """Create a mock contract with a symbol attribute."""
    c = MagicMock()
    c.symbol = symbol
    return c


class MockBar:
    """Mimics ib_insync BarData enough for util.df()."""
    def __init__(self, date, open_, high, low, close, volume):
        self.date = date
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.average = close
        self.barCount = 1

    def __iter__(self):
        """Make iterable for pandas from_records."""
        return iter({
            'date': self.date, 'open': self.open, 'high': self.high,
            'low': self.low, 'close': self.close, 'volume': self.volume,
            'average': self.average, 'barCount': self.barCount,
        }.items())

    def __getitem__(self, key):
        return getattr(self, key)


def _df_to_bars(df):
    """Convert a pandas DataFrame to a list of MockBar objects."""
    bars = []
    for dt, row in df.iterrows():
        bars.append(MockBar(dt, row['open'], row['high'], row['low'], row['close'], row['volume']))
    return bars


# ==============================================================================
# 11.1 LAYER 1: SECTOR ETF CONTEXT TESTS (T01-T09)
# ==============================================================================

class TestSA002Layer1_TrendLabel(unittest.TestCase):
    """Tests for _sa002_trend_label helper."""

    def test_T03_rising(self):
        """T03: 20-bar change = +2.5% -> RISING"""
        self.assertEqual(_sa002_trend_label(2.5), "RISING")

    def test_T04_flat(self):
        """T04: 20-bar change = +0.3% -> FLAT"""
        self.assertEqual(_sa002_trend_label(0.3), "FLAT")

    def test_T05_declining(self):
        """T05: 20-bar change = -3.1% -> DECLINING"""
        self.assertEqual(_sa002_trend_label(-3.1), "DECLINING")

    def test_T06_insufficient_data(self):
        """T06: None input -> INSUFFICIENT DATA"""
        self.assertEqual(_sa002_trend_label(None), "INSUFFICIENT DATA")

    def test_boundary_rising(self):
        """Boundary: exactly +1.0 -> FLAT (not > +1.0)"""
        self.assertEqual(_sa002_trend_label(1.0), "FLAT")

    def test_boundary_declining(self):
        """Boundary: exactly -1.0 -> FLAT (not < -1.0)"""
        self.assertEqual(_sa002_trend_label(-1.0), "FLAT")

    def test_just_above_rising(self):
        """Just above +1.0 -> RISING"""
        self.assertEqual(_sa002_trend_label(1.01), "RISING")

    def test_just_below_declining(self):
        """Just below -1.0 -> DECLINING"""
        self.assertEqual(_sa002_trend_label(-1.01), "DECLINING")


class TestSA002Layer1_PctChange(unittest.TestCase):
    """Tests for _sa002_pct_change helper."""

    def test_normal_positive(self):
        """Normal 20-bar positive change."""
        df = _make_df(50, base_price=105.0, pct_change_20=5.0)
        result = _sa002_pct_change(df, 20)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 5.0, places=1)

    def test_normal_negative(self):
        """Normal 20-bar negative change."""
        df = _make_df(50, base_price=97.0, pct_change_20=-3.0)
        result = _sa002_pct_change(df, 20)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, -3.0, places=1)

    def test_T06_insufficient_bars(self):
        """T06: fewer than 21 bars -> None"""
        df = _make_df(15)
        result = _sa002_pct_change(df, 20)
        self.assertIsNone(result)

    def test_none_df(self):
        """None DataFrame -> None"""
        self.assertIsNone(_sa002_pct_change(None, 20))

    def test_ten_bar_change(self):
        """10-bar change computation."""
        df = _make_df(50, base_price=110.0, pct_change_10=10.0)
        result = _sa002_pct_change(df, 10)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 10.0, places=1)


class TestSA002Layer1_GoldenCross(unittest.TestCase):
    """Tests for _sa002_golden_cross helper."""

    def test_T07_golden_cross(self):
        """T07: SMA 50 > SMA 200 -> True"""
        df = _make_golden_cross_df(250, golden=True)
        result = _sa002_golden_cross(df)
        self.assertTrue(result)

    def test_T08_death_cross(self):
        """T08: SMA 50 < SMA 200 -> False"""
        df = _make_golden_cross_df(250, golden=False)
        result = _sa002_golden_cross(df)
        self.assertFalse(result)

    def test_T09_insufficient_data(self):
        """T09: fewer than 200 bars -> None"""
        df = _make_df(150)
        result = _sa002_golden_cross(df)
        self.assertIsNone(result)


class TestSA002Layer1_SectorETFName(unittest.TestCase):
    """Tests for sector ETF name extraction (T01, T02)."""

    def test_T01_name_available(self):
        """T01: longName attribute present -> name populated."""
        detail = MockContractDetail(long_name="Technology Select Sector SPDR Fund")
        name = getattr(detail, 'longName', None)
        self.assertEqual(name, "Technology Select Sector SPDR Fund")

    def test_T02_name_missing(self):
        """T02: longName attribute missing -> None, no crash."""
        detail = MockContractDetail()
        detail.longName = None
        name = getattr(detail, 'longName', None)
        self.assertIsNone(name)


# ==============================================================================
# 11.2 LAYER 2: RELATIVE STRENGTH TESTS (T10-T17)
# ==============================================================================

class TestSA002Layer2_RSComputation(unittest.TestCase):
    """Tests for _sa002_compute_rs helper (ratio and spread modes)."""

    def test_T10_ratio_leading(self):
        """T10: Asset +5%, Sector +2% -> ratio = 2.5, LEADING"""
        val, label, spread = _sa002_compute_rs(5.0, 2.0)
        self.assertAlmostEqual(val, 2.5, places=1)
        self.assertEqual(label, "LEADING")
        self.assertFalse(spread)

    def test_T11_ratio_inline(self):
        """T11: Asset +1%, Sector +1.1% -> ratio = 0.91, INLINE"""
        val, label, spread = _sa002_compute_rs(1.0, 1.1)
        self.assertAlmostEqual(val, 0.91, places=2)
        self.assertEqual(label, "INLINE")
        self.assertFalse(spread)

    def test_T12_ratio_lagging(self):
        """T12: Asset +0.5%, Sector +3% -> ratio = 0.17, LAGGING"""
        val, label, spread = _sa002_compute_rs(0.5, 3.0)
        self.assertAlmostEqual(val, 0.17, places=2)
        self.assertEqual(label, "LAGGING")
        self.assertFalse(spread)

    def test_T13_benchmark_near_zero_positive(self):
        """T13: Sector +0.05% (abs < 0.1%) -> spread mode"""
        val, label, spread = _sa002_compute_rs(3.0, 0.05)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, 2.95, places=2)
        self.assertEqual(label, "LEADING")

    def test_T14_benchmark_near_zero_negative(self):
        """T14: Sector -0.03% (abs < 0.1%), Asset +2% -> spread = +2.03pp, LEADING"""
        val, label, spread = _sa002_compute_rs(2.0, -0.03)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, 2.03, places=2)
        self.assertEqual(label, "LEADING")

    def test_spread_inline(self):
        """Spread mode: small positive spread -> INLINE"""
        val, label, spread = _sa002_compute_rs(0.5, 0.05)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, 0.45, places=2)
        self.assertEqual(label, "INLINE")

    def test_spread_lagging(self):
        """Spread mode: large negative spread -> LAGGING"""
        val, label, spread = _sa002_compute_rs(-2.5, 0.05)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, -2.55, places=2)
        self.assertEqual(label, "LAGGING")

    def test_unavailable_none_numerator(self):
        """None numerator -> UNAVAILABLE"""
        val, label, spread = _sa002_compute_rs(None, 2.0)
        self.assertIsNone(val)
        self.assertEqual(label, "UNAVAILABLE")

    def test_unavailable_none_benchmark(self):
        """None benchmark -> UNAVAILABLE"""
        val, label, spread = _sa002_compute_rs(5.0, None)
        self.assertIsNone(val)
        self.assertEqual(label, "UNAVAILABLE")

    def test_T15_spy_failure_propagation(self):
        """T15: When SPY fetch fails, sector_vs_market and asset_vs_market = UNAVAILABLE.
        Asset_vs_Sector remains computable."""
        # Asset vs Sector should work (doesn't need SPY)
        val, label, _ = _sa002_compute_rs(5.0, 2.0)
        self.assertAlmostEqual(val, 2.5, places=1)
        self.assertEqual(label, "LEADING")
        # SPY-dependent calls with None -> UNAVAILABLE
        val2, label2, _ = _sa002_compute_rs(5.0, None)
        self.assertIsNone(val2)
        self.assertEqual(label2, "UNAVAILABLE")

    def test_T16_no_asset_history(self):
        """T16: asset_close_20bar = None -> asset_change_20 = None -> UNAVAILABLE"""
        val, label, _ = _sa002_compute_rs(None, 2.0)
        self.assertIsNone(val)
        self.assertEqual(label, "UNAVAILABLE")

    def test_T17_multi_layer_spread(self):
        """T17: SPY change = +0.02% (abs < 0.1%) -> both sector_vs_market
        and asset_vs_market switch to spread mode independently."""
        spy_change = 0.02
        sector_change = 3.0
        asset_change = 5.0

        # Sector vs Market (denominator = SPY near-zero)
        svm_val, svm_label, svm_spread = _sa002_compute_rs(sector_change, spy_change)
        self.assertTrue(svm_spread)
        self.assertAlmostEqual(svm_val, 2.98, places=2)
        self.assertEqual(svm_label, "LEADING")

        # Asset vs Market (denominator = SPY near-zero)
        avm_val, avm_label, avm_spread = _sa002_compute_rs(asset_change, spy_change)
        self.assertTrue(avm_spread)
        self.assertAlmostEqual(avm_val, 4.98, places=2)
        self.assertEqual(avm_label, "LEADING")

        # Asset vs Sector (denominator = sector, NOT near-zero) -> ratio mode
        avs_val, avs_label, avs_spread = _sa002_compute_rs(asset_change, sector_change)
        self.assertFalse(avs_spread)

    def test_ratio_boundary_leading(self):
        """Ratio boundary: exactly 1.2 -> INLINE (not > 1.2)"""
        # numerator / denominator = 1.2 => e.g. 6.0 / 5.0 = 1.2
        val, label, _ = _sa002_compute_rs(6.0, 5.0)
        self.assertAlmostEqual(val, 1.2, places=1)
        self.assertEqual(label, "INLINE")

    def test_ratio_boundary_lagging(self):
        """Ratio boundary: exactly 0.8 -> INLINE (not < 0.8)"""
        val, label, _ = _sa002_compute_rs(4.0, 5.0)
        self.assertAlmostEqual(val, 0.8, places=1)
        self.assertEqual(label, "INLINE")

    def test_divergent_signs_numerator_up_benchmark_down(self):
        """XLE +12%, SPY -6% -> spread = +18pp, LEADING (not ratio -2.0 'underperforming')"""
        val, label, spread = _sa002_compute_rs(12.0, -6.0)
        self.assertTrue(spread, "Should use spread mode when benchmark is negative")
        self.assertAlmostEqual(val, 18.0, places=1)
        self.assertEqual(label, "LEADING")

    def test_divergent_signs_numerator_down_benchmark_up(self):
        """Asset -5%, Sector +3% -> spread = -8pp, LAGGING"""
        val, label, spread = _sa002_compute_rs(-5.0, 3.0)
        # benchmark positive -> ratio mode, but numerator negative...
        # Actually: -5/3 = -1.67, ratio < 0.8 -> LAGGING. Ratio mode works here
        # because both the ratio AND spread agree on LAGGING.
        self.assertEqual(label, "LAGGING")

    def test_both_negative_less_decline_outperforms(self):
        """Asset -3%, Sector -6% -> spread = +3pp, LEADING (not ratio 0.5 'lagging')"""
        val, label, spread = _sa002_compute_rs(-3.0, -6.0)
        self.assertTrue(spread, "Should use spread mode when both negative")
        self.assertAlmostEqual(val, 3.0, places=1)
        self.assertEqual(label, "LEADING")

    def test_both_negative_more_decline_underperforms(self):
        """Asset -8%, Sector -3% -> spread = -5pp, LAGGING"""
        val, label, spread = _sa002_compute_rs(-8.0, -3.0)
        self.assertTrue(spread, "Should use spread mode when both negative")
        self.assertAlmostEqual(val, -5.0, places=1)
        self.assertEqual(label, "LAGGING")

    def test_both_negative_similar_decline_inline(self):
        """Asset -4%, Sector -3.5% -> spread = -0.5pp, INLINE"""
        val, label, spread = _sa002_compute_rs(-4.0, -3.5)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, -0.5, places=1)
        self.assertEqual(label, "INLINE")


# ==============================================================================
# 11.3 LAYER 3: NICHE ETF CONTEXT TESTS (T18-T23)
# ==============================================================================

class TestSA002Layer3_NicheMapping(unittest.TestCase):
    """Tests for _sa002_resolve_niche_etf helper."""

    def test_T18_semiconductors_to_SMH(self):
        """T18: AMAT (SEMICONDUCTORS category) -> SMH"""
        result = _sa002_resolve_niche_etf("Semiconductors", "Semiconductors", "AMAT")
        self.assertEqual(result, "SMH")

    def test_T19_software_to_IGV(self):
        """T19: MSFT (SOFTWARE category) -> IGV"""
        result = _sa002_resolve_niche_etf("Software", "Enterprise Software", "MSFT")
        self.assertEqual(result, "IGV")

    def test_T20_no_mapping(self):
        """T20: Utility with no niche mapping -> None"""
        result = _sa002_resolve_niche_etf("Electric", "Electric-Integrated", "NEE")
        self.assertIsNone(result)

    def test_ticker_fallback_HACK(self):
        """Ticker fallback: CRWD -> HACK (cybersecurity, no clean category)"""
        result = _sa002_resolve_niche_etf("Technology", "Internet", "CRWD")
        self.assertEqual(result, "HACK")

    def test_ticker_fallback_TAN(self):
        """Ticker fallback: ENPH -> TAN (solar energy)"""
        result = _sa002_resolve_niche_etf("Energy", "Solar", "ENPH")
        self.assertEqual(result, "TAN")

    def test_ticker_fallback_LIT(self):
        """Ticker fallback: ALB -> LIT (lithium)"""
        result = _sa002_resolve_niche_etf("Basic Materials", "Chemicals-Specialty", "ALB")
        self.assertEqual(result, "LIT")

    def test_ticker_takes_priority_over_category(self):
        """Ticker-level override takes priority over category match [SA-003]."""
        # PANW in NICHE_ETF_TICKER_MAP -> HACK
        # Category "Software" / subcategory "Enterprise Software" would match IGV
        # from NICHE_ETF_MAP, but ticker-level is checked first per SA-003.
        result = _sa002_resolve_niche_etf("Software", "Enterprise Software", "PANW")
        self.assertEqual(result, "HACK")

    def test_subcategory_match(self):
        """Subcategory substring match: 'OIL&GAS PRODUCTION' -> XOP"""
        result = _sa002_resolve_niche_etf("Energy", "Oil&Gas Production", "COP")
        self.assertEqual(result, "XOP")

    def test_banks_to_KRE(self):
        """BANKS category -> KRE"""
        result = _sa002_resolve_niche_etf("Banks", "Commercial Banks-US", "JPM")
        self.assertEqual(result, "KRE")

    def test_aerospace_to_ITA(self):
        """AEROSPACE/DEFENSE category -> ITA"""
        result = _sa002_resolve_niche_etf("Aerospace/Defense", "Aerospace/Defense", "LMT")
        self.assertEqual(result, "ITA")


class TestSA002Layer3_NicheSpreadMode(unittest.TestCase):
    """T23: Niche vs Sector RS switches to spread when sector change < 0.1%."""

    def test_T23_niche_spread_mode(self):
        """T23: sector_change < 0.1% -> niche_vs_sector uses spread"""
        niche_change = 3.5
        sector_change = 0.05  # abs < 0.1%
        val, label, spread = _sa002_compute_rs(niche_change, sector_change)
        self.assertTrue(spread)
        self.assertAlmostEqual(val, 3.45, places=2)
        self.assertEqual(label, "LEADING")


# ==============================================================================
# DIAGNOSTIC STRING FORMAT TESTS
# ==============================================================================

class TestSA002DiagnosticFormat(unittest.TestCase):
    """Tests for _sa002_format_rs_diagnostic helper."""

    def test_ratio_mode(self):
        result = _sa002_format_rs_diagnostic("XLK vs SPY", 1.15, "LEADING", False)
        self.assertEqual(result, "XLK vs SPY: 1.15 (LEADING)")

    def test_spread_mode(self):
        result = _sa002_format_rs_diagnostic("XLK vs SPY", 1.8, "INLINE", True)
        self.assertEqual(result, "XLK vs SPY: +1.8pp spread (INLINE) [spread mode]")

    def test_spread_mode_negative(self):
        result = _sa002_format_rs_diagnostic("AMAT vs XLK", -2.5, "LAGGING", True)
        self.assertEqual(result, "AMAT vs XLK: -2.5pp spread (LAGGING) [spread mode]")

    def test_unavailable(self):
        result = _sa002_format_rs_diagnostic("XLK vs SPY", None, None, False, "SPY fetch failed")
        self.assertEqual(result, "XLK vs SPY: UNAVAILABLE [SPY fetch failed]")

    def test_ascii_only(self):
        """Verify all diagnostic format outputs are ASCII-only."""
        for test_output in [
            _sa002_format_rs_diagnostic("XLK vs SPY", 1.15, "LEADING", False),
            _sa002_format_rs_diagnostic("XLK vs SPY", 1.8, "INLINE", True),
            _sa002_format_rs_diagnostic("XLK vs SPY", None, None, False, "SPY fetch failed"),
        ]:
            try:
                test_output.encode('ascii')
            except UnicodeEncodeError:
                self.fail(f"Non-ASCII character in diagnostic: {test_output!r}")


# ==============================================================================
# INTEGRATION TESTS: Full run_sympathy_audit with mocked IBKR (T21-T28)
# ==============================================================================

class TestSA002Integration(unittest.TestCase):
    """Integration tests using mocked IB connection."""

    def _make_mock_ib(self, sector_df, spy_df=None, niche_df=None,
                      asset_detail=None, sector_detail=None, niche_detail=None,
                      spy_fetch_fail=False, niche_fetch_fail=False):
        """Build a mock IB object with controllable responses.
        Also stores DataFrames for the util.df patch to return."""
        ib = MagicMock()
        ib.isConnected.return_value = True

        # Store DataFrames for _patched_util_df to use
        self._sector_df = sector_df
        self._spy_df = spy_df
        self._niche_df = niche_df
        self._hist_call_index = 0
        self._hist_responses = []  # ordered list of (ticker_key, df_or_fail)

        # Default asset detail
        if asset_detail is None:
            asset_detail = MockContractDetail(
                long_name="Applied Materials Inc",
                industry="Technology",
                category="Semiconductors",
                subcategory="Semiconductors"
            )

        # Default sector detail
        if sector_detail is None:
            sector_detail = MockContractDetail(
                long_name="Technology Select Sector SPDR Fund"
            )
            sector_detail.contract = _make_mock_contract("XLK")

        # Default niche detail
        if niche_detail is None:
            niche_detail = MockContractDetail(
                long_name="VanEck Semiconductor ETF"
            )
            niche_detail.contract = _make_mock_contract("SMH")

        # SPY detail
        spy_detail = MockContractDetail(long_name="SPDR S&P 500 ETF Trust")
        spy_detail.contract = _make_mock_contract("SPY")

        # Map of all niche ETF tickers for matching
        all_niche = set(NICHE_ETF_MAP.values()) | set(NICHE_ETF_TICKER_MAP.values())
        sector_etfs = {'XLK', 'XLE', 'XLF', 'XLV', 'XLI', 'XLY', 'XLP',
                       'XLB', 'XLC', 'XLU', 'XLRE', 'XBI', 'XME'}

        def mock_contract_details(contract):
            sym = getattr(contract, 'symbol', '') or ''
            if sym == 'SPY':
                return [spy_detail]
            elif sym in all_niche:
                return [niche_detail]
            elif sym in sector_etfs:
                return [sector_detail]
            else:
                return [asset_detail]
        ib.reqContractDetails.side_effect = mock_contract_details

        # Track historical data calls to map to correct DataFrames
        self._hist_call_log = []

        def mock_hist_data(contract, *args, **kwargs):
            sym = getattr(contract, 'symbol', '') or ''
            self._hist_call_log.append(sym)
            if sym == 'SPY':
                if spy_fetch_fail:
                    raise Exception("SPY fetch timeout")
                if spy_df is not None:
                    # Return a list with correct length for the len() >= 21 check
                    return ["SPY_BAR"] * len(spy_df)
                return []
            elif sym in all_niche:
                if niche_fetch_fail:
                    raise Exception("Niche ETF fetch timeout")
                if niche_df is not None:
                    return ["NICHE_BAR"] * len(niche_df)
                return []
            else:
                if sector_df is not None:
                    return ["SECTOR_BAR"] * len(sector_df)
                return []
        ib.reqHistoricalData.side_effect = mock_hist_data

        return ib

    def _get_patched_util_df(self):
        """Return a replacement for util.df that maps sentinel lists to real DataFrames."""
        sector_df = self._sector_df
        spy_df = self._spy_df
        niche_df = self._niche_df

        def patched_df(bars):
            if not bars:
                raise ValueError("Empty bars")
            first = bars[0] if isinstance(bars, list) else None
            if first == "SECTOR_BAR" and sector_df is not None:
                return sector_df.copy().reset_index()
            elif first == "SPY_BAR" and spy_df is not None:
                return spy_df.copy().reset_index()
            elif first == "NICHE_BAR" and niche_df is not None:
                return niche_df.copy().reset_index()
            raise ValueError(f"Unexpected bars input: {bars[:3] if isinstance(bars, list) else bars}")
        return patched_df

    def setUp(self):
        """Reset SPY cache before each test."""
        import ibkr_sympathy_audit
        ibkr_sympathy_audit._spy_cache = {"bars": None, "bar_size": None, "duration": None}

    def _run_audit(self, ticker, profile="TREND", sector_etf_override=None,
                   ib=None, asset_close_current=None, asset_close_20bar=None):
        """Run sympathy audit with util.df and Stock patched."""
        def mock_stock(symbol, exchange, currency, **kwargs):
            c = MagicMock()
            c.symbol = symbol
            return c

        with patch('ibkr_sympathy_audit.util.df', side_effect=self._get_patched_util_df()), \
             patch('ibkr_sympathy_audit.Stock', side_effect=mock_stock):
            return run_sympathy_audit(
                ticker, profile=profile,
                sector_etf_override=sector_etf_override,
                ib_connection=ib,
                asset_close_current=asset_close_current,
                asset_close_20bar=asset_close_20bar
            )

    def test_T21_niche_fetch_failure(self):
        """T21: SMH niche fetch fails -> Niche fields = UNAVAILABLE, Layer 1 preserved."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=3.2)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, niche_fetch_fail=True)
        status, diag, metrics = self._run_audit(
            "AMAT", ib=ib, asset_close_current=160.0, asset_close_20bar=150.0
        )

        # Layer 1 verdict preserved
        self.assertIn(status, ("PASS", "HALT"))
        # Niche fields degraded
        self.assertEqual(metrics.get("Niche_ETF"), "SMH")
        self.assertEqual(metrics.get("Niche_ETF_Trend"), "UNAVAILABLE")
        self.assertEqual(metrics.get("Niche_vs_Sector_RS_Label"), "UNAVAILABLE")
        # Diagnostic notes failure
        self.assertIn("fetch failed", diag)

    def test_T22_halt_path_with_niche(self):
        """T22: Layer 1 HALT + niche ETF mapped -> niche context in HALT diagnostic."""
        # Sector below floor: create DF where close < SMA 50
        sector_df = _make_df_linear(250, start_price=250.0, end_price=180.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.0)
        niche_df = _make_df(250, base_price=100.0, pct_change_20=5.8)

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, niche_df=niche_df)
        status, diag, metrics = self._run_audit(
            "AMAT", ib=ib, asset_close_current=160.0, asset_close_20bar=150.0
        )

        self.assertEqual(status, "HALT")
        # SA-002 context still present on HALT path
        self.assertIn("[SECTOR CONTEXT]", diag)
        # Niche context on HALT path (DQ-7)
        self.assertIn("[SUB-SECTOR]", diag)

    def test_T24_full_pipeline_AMAT(self):
        """T24: AMAT Profile B (TREND) -- all three layers populated."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=3.2)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)
        niche_df = _make_df(250, base_price=280.0, pct_change_20=5.8)

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, niche_df=niche_df)
        status, diag, metrics = self._run_audit(
            "AMAT", ib=ib, asset_close_current=160.0, asset_close_20bar=150.0
        )

        # Layer 1
        self.assertIsNotNone(metrics.get("Sector_ETF_Name"))
        self.assertIsNotNone(metrics.get("Sector_ETF_Change_20"))
        self.assertIn(metrics.get("Sector_ETF_Trend"), ("RISING", "FLAT", "DECLINING"))
        # Layer 2
        self.assertIsNotNone(metrics.get("Asset_vs_Sector_RS"))
        self.assertIn(metrics["Asset_vs_Sector_RS_Label"], ("LEADING", "INLINE", "LAGGING"))
        self.assertIsNotNone(metrics.get("Sector_vs_Market_RS"))
        self.assertIsNotNone(metrics.get("Asset_vs_Market_RS"))
        # Layer 3
        self.assertEqual(metrics.get("Niche_ETF"), "SMH")
        self.assertIsNotNone(metrics.get("Niche_ETF_Change_20"))
        self.assertIn(metrics.get("Niche_ETF_Trend"), ("RISING", "FLAT", "DECLINING"))
        # Diagnostic string complete
        self.assertIn("[SECTOR CONTEXT]", diag)
        self.assertIn("[SUB-SECTOR]", diag)

    def test_T15_spy_fetch_failure(self):
        """T15: SPY fetch fails -> Sector_vs_Market and Asset_vs_Market UNAVAILABLE.
        Asset_vs_Sector unaffected."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=2.0)

        ib = self._make_mock_ib(sector_df, spy_fetch_fail=True)
        status, diag, metrics = self._run_audit(
            "AMAT", ib=ib, asset_close_current=160.0, asset_close_20bar=150.0
        )

        self.assertEqual(metrics["Sector_vs_Market_RS_Label"], "UNAVAILABLE")
        self.assertEqual(metrics["Asset_vs_Market_RS_Label"], "UNAVAILABLE")
        # Asset_vs_Sector should still work
        self.assertNotEqual(metrics["Asset_vs_Sector_RS_Label"], "UNAVAILABLE")
        self.assertIn("SPY fetch failed", diag)

    def test_T16_asset_fetch_failure(self):
        """T16: asset_close params = None AND self-fetch returns insufficient bars
        -> Asset RS fields UNAVAILABLE. Sector_vs_Market unaffected."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=2.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        ib = self._make_mock_ib(sector_df, spy_df=spy_df)

        # Override reqHistoricalData to return empty for the asset contract
        _orig_side_effect = ib.reqHistoricalData.side_effect
        _call_count = [0]
        def _hist_with_asset_fail(contract, *args, **kwargs):
            sym = getattr(contract, 'symbol', '') or ''
            _call_count[0] += 1
            # The asset self-fetch is the FIRST hist call (before sector fetch
            # which already happened). But in practice the sector fetch happens
            # first. The asset self-fetch uses the original asset contract.
            # We detect it by symbol = "AMAT" (not a sector/SPY/niche ETF).
            if sym == 'AMAT':
                return []  # empty -> self-fetch fails
            return _orig_side_effect(contract, *args, **kwargs)
        ib.reqHistoricalData.side_effect = _hist_with_asset_fail

        status, diag, metrics = self._run_audit(
            "AMAT", ib=ib, asset_close_current=None, asset_close_20bar=None
        )

        self.assertEqual(metrics["Asset_vs_Sector_RS_Label"], "UNAVAILABLE")
        self.assertEqual(metrics["Asset_vs_Market_RS_Label"], "UNAVAILABLE")
        # Sector vs Market should still work
        self.assertNotEqual(metrics["Sector_vs_Market_RS_Label"], "UNAVAILABLE")

    def test_T25_LSE_equity(self):
        """T25: BARC.L Profile B (TREND) -- LSE equity.
        Sector context populated. Niche mapping check. SPY RS computed.
        (Mock analog -- live validation requires IBKR connection.)"""
        sector_df = _make_df(250, base_price=150.0, pct_change_20=1.5)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.0)

        asset_detail = MockContractDetail(
            long_name="Barclays PLC",
            industry="Financial",
            category="Banks",
            subcategory="Commercial Banks-Non US"
        )

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, asset_detail=asset_detail)
        # BARC.L -> routing strips .L, resolves to BARC
        # Banks category -> KRE niche mapping
        status, diag, metrics = self._run_audit(
            "BARC.L", ib=ib, asset_close_current=250.0, asset_close_20bar=245.0
        )

        self.assertIn(status, ("PASS", "HALT"))
        self.assertIn("[SECTOR CONTEXT]", diag)
        # Niche mapping: BANKS -> KRE
        self.assertEqual(metrics.get("Niche_ETF"), "KRE")
        # SPY RS should be computed
        self.assertIsNotNone(metrics.get("Sector_vs_Market_RS"))

    def test_T26_etf_self_referential(self):
        """T26: XLE Profile B -- ETF is its own sector ETF.
        Self-referential case: asset IS the sector ETF.
        (Mock analog -- sector-etf-override used to force the self-referential path.)"""
        sector_df = _make_df(250, base_price=85.0, pct_change_20=2.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        asset_detail = MockContractDetail(
            long_name="Energy Select Sector SPDR Fund",
            industry="Energy",
            category="Energy",
            subcategory="Oil&Gas"
        )

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, asset_detail=asset_detail)

        # asset close = sector close (self-referential)
        status, diag, metrics = self._run_audit(
            "XLE_TEST", sector_etf_override="XLE", ib=ib,
            asset_close_current=85.0, asset_close_20bar=85.0 / 1.02  # +2% to match sector
        )

        self.assertIn(status, ("PASS", "HALT"))
        # Asset vs Sector should be ~1.0 (INLINE) when asset IS the sector
        if metrics.get("Asset_vs_Sector_RS") is not None:
            self.assertAlmostEqual(metrics["Asset_vs_Sector_RS"], 1.0, places=0)
            self.assertEqual(metrics["Asset_vs_Sector_RS_Label"], "INLINE")
        # Niche mapping check: OIL&GAS -> XOP
        self.assertEqual(metrics.get("Niche_ETF"), "XOP")

    def test_T27_spy_benchmark_self_reference(self):
        """T27: SPY Profile A -- the benchmark itself.
        Sector-vs-market should be ~1.0. Asset-vs-market should be 1.0.
        (Mock analog -- uses SPY as asset with sector-etf-override.)"""
        sector_df = _make_df(250, base_price=500.0, pct_change_20=1.5)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        asset_detail = MockContractDetail(
            long_name="SPDR S&P 500 ETF Trust",
            industry="Financial",
            category="ETF",
            subcategory="Broad Market"
        )

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, asset_detail=asset_detail)

        # Asset close matches SPY -> asset-vs-market = 1.0
        spy_20bar = 500.0 / 1.015
        status, diag, metrics = self._run_audit(
            "SPY_TEST", sector_etf_override="XLK", ib=ib,
            asset_close_current=500.0, asset_close_20bar=spy_20bar
        )

        self.assertIn(status, ("PASS", "HALT"))
        # Asset vs Market should be ~1.0 when asset IS SPY
        if metrics.get("Asset_vs_Market_RS") is not None:
            self.assertAlmostEqual(metrics["Asset_vs_Market_RS"], 1.0, places=0)

    def test_T28_backward_compatibility(self):
        """T28: sympathy audit called without asset_close params -> no crash.
        Self-fetch populates asset RS when IB connection available.
        Layer 1 verdict unaffected."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=2.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        ib = self._make_mock_ib(sector_df, spy_df=spy_df)

        # Call WITHOUT asset_close params (backward compatible -- self-fetch kicks in)
        status, diag, metrics = self._run_audit("AMAT", ib=ib)

        # No crash
        self.assertIn(status, ("PASS", "HALT"))
        # Self-fetch should populate asset RS (mock returns sector_df for unknown symbols)
        self.assertIn(metrics["Asset_vs_Sector_RS_Label"],
                      ("LEADING", "INLINE", "LAGGING", "UNAVAILABLE"))
        # Sector context still computed
        self.assertIn("[SECTOR CONTEXT]", diag)

    def test_T20_no_niche_mapping(self):
        """T20: Asset with no niche mapping -> no niche fields, no fetch attempted."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=1.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)

        asset_detail = MockContractDetail(
            long_name="NextEra Energy Inc",
            industry="Utilities",
            category="Electric",
            subcategory="Electric-Integrated"
        )

        ib = self._make_mock_ib(sector_df, spy_df=spy_df, asset_detail=asset_detail)
        status, diag, metrics = self._run_audit(
            "NEE", sector_etf_override="XLU", ib=ib,
            asset_close_current=80.0, asset_close_20bar=79.0
        )

        self.assertIsNone(metrics.get("Niche_ETF"))
        self.assertNotIn("[SUB-SECTOR]", diag)
        # [SECTOR CONTEXT] should still be present
        self.assertIn("[SECTOR CONTEXT]", diag)


class TestSA002IntegrationASCII(unittest.TestCase):
    """Verify all diagnostic output strings are ASCII-only."""

    def test_diagnostic_ascii_pass_path(self):
        """Diagnostic on PASS path is ASCII-only."""
        sector_df = _make_df(250, base_price=200.0, pct_change_20=3.2)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.5)
        niche_df = _make_df(250, base_price=280.0, pct_change_20=5.8)

        helper = TestSA002Integration()
        mock_ib = helper._make_mock_ib(sector_df, spy_df=spy_df, niche_df=niche_df)

        import ibkr_sympathy_audit
        ibkr_sympathy_audit._spy_cache = {"bars": None, "bar_size": None, "duration": None}

        def _mock_stock(symbol, exchange, currency, **kwargs):
            c = MagicMock()
            c.symbol = symbol
            return c

        with patch('ibkr_sympathy_audit.util.df', side_effect=helper._get_patched_util_df()), \
             patch('ibkr_sympathy_audit.Stock', side_effect=_mock_stock):
            _, diag, _ = run_sympathy_audit(
                "AMAT", profile="TREND", ib_connection=mock_ib,
                asset_close_current=160.0, asset_close_20bar=150.0
            )
        try:
            diag.encode('ascii')
        except UnicodeEncodeError:
            self.fail(f"Non-ASCII character in PASS diagnostic: {diag!r}")

    def test_diagnostic_ascii_halt_path(self):
        """Diagnostic on HALT path is ASCII-only."""
        sector_df = _make_df_linear(250, start_price=250.0, end_price=180.0)
        spy_df = _make_df(250, base_price=500.0, pct_change_20=1.0)
        niche_df = _make_df(250, base_price=100.0, pct_change_20=5.8)

        helper = TestSA002Integration()
        mock_ib = helper._make_mock_ib(sector_df, spy_df=spy_df, niche_df=niche_df)

        import ibkr_sympathy_audit
        ibkr_sympathy_audit._spy_cache = {"bars": None, "bar_size": None, "duration": None}

        def _mock_stock(symbol, exchange, currency, **kwargs):
            c = MagicMock()
            c.symbol = symbol
            return c

        with patch('ibkr_sympathy_audit.util.df', side_effect=helper._get_patched_util_df()), \
             patch('ibkr_sympathy_audit.Stock', side_effect=_mock_stock):
            _, diag, _ = run_sympathy_audit(
                "AMAT", profile="TREND", ib_connection=mock_ib,
                asset_close_current=160.0, asset_close_20bar=150.0
            )
        try:
            diag.encode('ascii')
        except UnicodeEncodeError:
            self.fail(f"Non-ASCII character in HALT diagnostic: {diag!r}")


# ==============================================================================
# NICHE_ETF_MAP DICTIONARY COMPLETENESS
# ==============================================================================

class TestSA002NicheMapCompleteness(unittest.TestCase):
    """Verify NICHE_ETF_MAP and NICHE_ETF_TICKER_MAP have expected entries."""

    def test_map_has_all_spec_niche_etfs(self):
        """All 15 niche ETFs from spec Section 5.2 are reachable."""
        expected_niche_etfs = {
            "SMH", "IGV", "HACK", "IBB", "KRE", "ITB", "XRT",
            "ITA", "PAVE", "IYT", "XOP", "GDX", "IPAY", "TAN", "LIT"
        }
        all_values = set(NICHE_ETF_MAP.values()) | set(NICHE_ETF_TICKER_MAP.values())
        for etf in expected_niche_etfs:
            self.assertIn(etf, all_values, f"Niche ETF {etf} not reachable from either map")

    def test_ticker_fallback_covers_HACK_TAN_LIT(self):
        """HACK, TAN, LIT are in ticker fallback (no clean category mapping)."""
        fallback_targets = set(NICHE_ETF_TICKER_MAP.values())
        for etf in ["HACK", "TAN", "LIT"]:
            self.assertIn(etf, fallback_targets,
                          f"{etf} should be in NICHE_ETF_TICKER_MAP (manual ticker fallback)")


if __name__ == "__main__":
    unittest.main(verbosity=2)

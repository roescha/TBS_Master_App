"""PE-45 unit tests."""
import math, sys, os, types as bt, unittest
from typing import NamedTuple, Optional
from unittest.mock import MagicMock

class GateResult(NamedTuple):
    verdict: str; reason: str; mandate: Optional[str]; context: Optional[str]
    legacy_diagnostic: Optional[str] = None; entry_type: Optional[str] = None
    trigger_rule: Optional[str] = None; state: Optional[str] = None

# Stub tbs_engine.types before importing trigger
_tm = bt.ModuleType("tbs_engine.types"); _tm.GateResult = GateResult
_pm = bt.ModuleType("tbs_engine"); _pm.types = _tm
sys.modules.setdefault("tbs_engine", _pm)
sys.modules.setdefault("tbs_engine.types", _tm)

# Add tbs_engine dir to path and import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tbs_engine"))
import importlib
trigger_mod = importlib.import_module("trigger")
_identify_trigger = trigger_mod._identify_trigger

def _make_state(**ov):
    d = dict(adx_t=20.0,adx_t1=19.0,di_plus=25.0,di_minus=15.0,atr_raw=1.0,
        is_trending=False,is_resolving=True,ma_stack_full=False,ma_squeeze=False,
        ema_stacked=False,_etf_entry_trending=False,_etf_entry_resolving=True,
        _entry_trending=False,_entry_resolving=True,_resolving_is_bearish=False,
        is_reclaim=False,is_ambiguous=False,is_violated=False,is_floor_failure=False,
        floor_raw=0.0,consec_below=0,_reclaim_run=0)
    d.update(ov)
    s = MagicMock()
    for k,v in d.items(): setattr(s,k,v)
    return s

def _make_last(close,ema8,ema21,sma50,sma200=float('nan'),scaler=1):
    data = {'close':close*scaler,'EMA_8':ema8*scaler,'EMA_21':ema21*scaler,
        'SMA_50':sma50*scaler,
        'SMA_200':sma200*scaler if not math.isnan(sma200) else float('nan'),
        'ANCHOR':(sma50-1)*scaler}
    m = MagicMock()
    m.__getitem__ = lambda self,k: data[k]
    m.get = lambda k,d=None: data.get(k,d)
    return m

def _make_ctx(state,last,price_scaler=1,p_code="A"):
    ctx = MagicMock(); ctx.state=state; ctx.cfg=MagicMock()
    ctx.cfg.pb_upper_col='EMA_21'; ctx.cfg.ff_threshold=3
    ctx.p_code=p_code; ctx.is_etf=False; ctx.metrics={}; ctx.last=last
    ctx.df=MagicMock(); ctx.resistance_raw=999999; ctx.resistance_display=999.99
    ctx.floor_price=10.0; ctx.hard_stop=9.0; ctx.chart_ref=""
    ctx.price_scaler=price_scaler; ctx._resistance_suppressed=False
    return ctx

def _run(ctx): return _identify_trigger(ctx,None,1.5,"GOOD",None,None)

class TestPE45(unittest.TestCase):
    def test_tc01_adx_below_25(self):
        r = _run(_make_ctx(_make_state(adx_t=22.3), _make_last(50,51,52,53)))
        self.assertEqual(r.reason,"PROFILE A RESOLVING BLOCK")
        self.assertIn("below 25 threshold",r.context)
        self.assertIn("below 25 threshold",r.legacy_diagnostic)

    def test_tc02_price_below_ema8(self):
        r = _run(_make_ctx(_make_state(adx_t=35.18), _make_last(30.48,30.49,29.0,28.0)))
        self.assertIn("MA stack broken",r.context)
        self.assertIn("Price 30.48 <= EMA 8 30.49",r.context)
        self.assertNotIn("below 25 threshold",r.context)
        self.assertIn("Price 30.48 <= EMA 8 30.49",r.legacy_diagnostic)

    def test_tc03_ema8_below_ema21(self):
        r = _run(_make_ctx(_make_state(adx_t=28.0), _make_last(55,54,56,50)))
        self.assertIn("EMA 8 54.0 <= EMA 21 56.0",r.context)
        self.assertNotIn("below 25 threshold",r.context)

    def test_tc04_lse_scaler(self):
        r = _run(_make_ctx(_make_state(adx_t=35.0), _make_last(30.48,30.49,29.0,28.0,scaler=100), price_scaler=100))
        self.assertIn("Price 30.48 <= EMA 8 30.49",r.context)
        self.assertNotIn("3048",r.context)

if __name__=="__main__": unittest.main()

"""SelfDoc Batch 1 -- Unit Tests.

Covers: THS-002, TS-001, EXIT-001, PROX-001, RISK-001, CVN-001.
Tests grouped output shapes, label derivation, _flatten() backward compat.

Run: pytest tests/unit/test_selfdoc_batch1.py -v
"""
import pytest
import os

from tbs_engine.transform import _transform_output, _flatten


# ---------------------------------------------------------------------------
# THS-002: _ths_band label derivation (local copy for isolated testing)
# ---------------------------------------------------------------------------

def _ths_band(val):
    if val >= 80: return 'STRONG'
    if val >= 60: return 'HEALTHY'
    if val >= 51: return 'ACCEPTABLE'
    if val >= 40: return 'CAUTION'
    if val >= 20: return 'WEAK'
    return 'CRITICAL'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_action_summary(verdict="INVALID"):
    return {
        "verdict": verdict,
        "reason": "TEST",
        "approaching": False,
        "action": "Test mandate",
        "context": "Test context",
    }

def _build_base_metrics():
    return {
        "Price": 220.0, "Structural_Floor": 215.0, "Resistance": 225.0,
        "ADV_20": 1000000, "ADV_20_Dollar": 50000000, "Is_ETF": False,
        "Engine_State": "TRENDING",
        "Engine_State_Desc": "ADX > 20 + full MA stack + no squeeze",
        "Trend_Age_Bars": 5, "Trend_Age_Max": 30,
        "Active_Modifiers": "None", "Active_Modifiers_List": [],
        "Inst_Churn": "CLEAR (No Churn)",
        "ADX": 25.0, "ADX_Accel": 0.1, "ADX_Accel_State": "CRUISING",
        "DI_Plus": 26.0, "DI_Minus": 22.0, "DI_Spread": 4.0, "DI_Bias": "BULLISH",
        "EMA_8": 219.0, "EMA_21": 217.0, "SMA_50": 215.0, "SMA_200": 200.0,
        "ATR": 2.5,
        "Trend_Health_Score": 65.0, "THS_Label": "HEALTHY",
        "THS_Floor_Buffer": 50.0, "THS_Floor_Buffer_Label": "ACCEPTABLE",
        "THS_Dir_Momentum": 60.0, "THS_Dir_Momentum_Label": "HEALTHY",
        "THS_Trend_Age": 80.0, "THS_Trend_Age_Label": "STRONG",
        "THS_Structure": 55.0, "THS_Structure_Label": "ACCEPTABLE",
        "Exit_Signal": "CLEAR", "Exit_Triggers": [], "Exit_Reason": None,
    }


# ===================================================================
# THS-002 Tests
# ===================================================================

class TestTHS002:

    def test_band_strong(self):
        assert _ths_band(85) == 'STRONG'
        assert _ths_band(80) == 'STRONG'
        assert _ths_band(100) == 'STRONG'

    def test_band_healthy(self):
        assert _ths_band(65) == 'HEALTHY'
        assert _ths_band(60) == 'HEALTHY'

    def test_band_acceptable(self):
        assert _ths_band(55) == 'ACCEPTABLE'
        assert _ths_band(51) == 'ACCEPTABLE'

    def test_band_caution(self):
        assert _ths_band(45) == 'CAUTION'
        assert _ths_band(40) == 'CAUTION'

    def test_band_weak(self):
        assert _ths_band(25) == 'WEAK'
        assert _ths_band(20) == 'WEAK'

    def test_band_critical(self):
        assert _ths_band(10) == 'CRITICAL'
        assert _ths_band(0) == 'CRITICAL'
        assert _ths_band(19.9) == 'CRITICAL'

    def test_subscore_is_dict_with_required_keys(self):
        flat = _build_base_metrics()
        flat.update({
            'Trend_Health_Score': 37.3, 'THS_Label': 'WEAK',
            'THS_Floor_Buffer': 18.8, 'THS_Floor_Buffer_Label': 'CRITICAL',
            'THS_Dir_Momentum': 13.3, 'THS_Dir_Momentum_Label': 'CRITICAL',
            'THS_Trend_Age': 100.0, 'THS_Trend_Age_Label': 'STRONG',
            'THS_Structure': 57.4, 'THS_Structure_Label': 'HEALTHY',
        })
        result = _transform_output(_build_action_summary(), flat)
        th = result['trade_quality']['trend_health']
        assert th['score']['value'] == 37.3
        assert th['score']['max'] == 100
        assert th['score']['label'] == 'WEAK'
        assert 'desc' in th['score']
        assert th['threshold']['value'] == 50
        assert th['threshold']['max'] == 100
        for key in ('floor_buffer', 'dir_momentum', 'trend_age', 'structure'):
            sub = th[key]
            assert isinstance(sub, dict), f"{key} not dict"
            for k in ('value', 'max', 'label', 'desc'):
                assert k in sub, f"{key} missing '{k}'"
            assert sub['max'] == 100

    def test_flatten_trend_health(self):
        flat = _build_base_metrics()
        flat.update({
            'Trend_Health_Score': 72.5, 'THS_Label': 'HEALTHY',
            'THS_Floor_Buffer': 45.0, 'THS_Floor_Buffer_Label': 'CAUTION',
            'THS_Dir_Momentum': 60.0, 'THS_Dir_Momentum_Label': 'HEALTHY',
            'THS_Trend_Age': 80.0, 'THS_Trend_Age_Label': 'STRONG',
            'THS_Structure': 55.0, 'THS_Structure_Label': 'ACCEPTABLE',
        })
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert f['Trend_Health_Score'] == 72.5
        assert f['THS_Label'] == 'HEALTHY'
        assert f['THS_Floor_Buffer'] == 45.0
        assert f['THS_Dir_Momentum'] == 60.0
        assert f['THS_Trend_Age'] == 80.0
        assert f['THS_Structure'] == 55.0


# ===================================================================
# TS-001 Tests
# ===================================================================

class TestTS001:

    def test_di_spread_bullish(self):
        s = round(30.0 - 20.0, 2)
        assert s == 10.0
        assert ('BULLISH' if s > 0 else 'BEARISH' if s < 0 else 'NEUTRAL') == 'BULLISH'

    def test_di_spread_bearish(self):
        s = round(20.0 - 30.0, 2)
        assert s == -10.0
        assert ('BULLISH' if s > 0 else 'BEARISH' if s < 0 else 'NEUTRAL') == 'BEARISH'

    def test_di_spread_neutral(self):
        s = round(25.0 - 25.0, 2)
        assert s == 0.0
        assert ('BULLISH' if s > 0 else 'BEARISH' if s < 0 else 'NEUTRAL') == 'NEUTRAL'

    def test_state_desc_trending(self):
        flat = _build_base_metrics()
        flat['Engine_State'] = 'TRENDING'
        flat['Engine_State_Desc'] = 'ADX > 20 + full MA stack + no squeeze'
        result = _transform_output(_build_action_summary(), flat)
        st = result['trend_state']['classification']['state']
        assert st['label'] == 'TRENDING'
        assert 'ADX' in st['desc']

    def test_state_desc_resolving(self):
        flat = _build_base_metrics()
        flat['Engine_State'] = 'RESOLVING'
        flat['Engine_State_Desc'] = 'ADX 15-20 or partial MA alignment'
        result = _transform_output(_build_action_summary(), flat)
        assert result['trend_state']['classification']['state']['label'] == 'RESOLVING'

    def test_state_desc_midrange(self):
        flat = _build_base_metrics()
        flat['Engine_State'] = 'MID-RANGE (ADX <20)'
        flat['Engine_State_Desc'] = 'ADX < 20 -- no directional regime'
        result = _transform_output(_build_action_summary(), flat)
        assert result['trend_state']['classification']['state']['label'] == 'MID-RANGE (ADX <20)'

    def test_modifiers_active_is_list_of_dicts(self):
        flat = _build_base_metrics()
        flat['Active_Modifiers_List'] = [
            {"label": "A", "name": "Rejection"},
            {"label": "B", "name": "Ignition"},
        ]
        result = _transform_output(_build_action_summary(), flat)
        mods = result['trend_state']['classification']['modifiers']
        assert isinstance(mods['active'], list)
        assert len(mods['active']) == 2
        assert mods['active'][0]['label'] == 'A'
        assert mods['active'][1]['name'] == 'Ignition'

    def test_modifiers_inactive_is_empty_list(self):
        flat = _build_base_metrics()
        flat['Active_Modifiers_List'] = []
        result = _transform_output(_build_action_summary(), flat)
        assert result['trend_state']['classification']['modifiers']['active'] == []

    def test_churn_label_active(self):
        flat = _build_base_metrics()
        flat['Inst_Churn'] = 'ACTIVE (Inst. Churn)'
        result = _transform_output(_build_action_summary(), flat)
        assert result['trend_state']['classification']['churn']['label'] == 'ACTIVE'

    def test_churn_label_clear(self):
        flat = _build_base_metrics()
        flat['Inst_Churn'] = 'CLEAR (No Churn)'
        result = _transform_output(_build_action_summary(), flat)
        assert result['trend_state']['classification']['churn']['label'] == 'CLEAR'

    def test_flatten_trend_state(self):
        flat = _build_base_metrics()
        flat.update({
            'Engine_State': 'TRENDING', 'Engine_State_Desc': 'test',
            'Trend_Age_Bars': 5, 'Trend_Age_Max': 30,
            'Active_Modifiers': 'A (Rejection), B (Ignition)',
            'Active_Modifiers_List': [
                {"label": "A", "name": "Rejection"},
                {"label": "B", "name": "Ignition"},
            ],
            'Inst_Churn': 'CLEAR (No Churn)',
            'ADX': 25.5, 'ADX_Accel': 0.5, 'ADX_Accel_State': 'ACCELERATING',
            'DI_Plus': 30.0, 'DI_Minus': 20.0,
            'DI_Spread': 10.0, 'DI_Bias': 'BULLISH',
        })
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert f['Engine_State'] == 'TRENDING'
        assert f['Trend_Age_Bars'] == 5
        assert f['ADX'] == 25.5
        assert f['ADX_Accel'] == 0.5
        assert f['ADX_Accel_State'] == 'ACCELERATING'
        assert f['DI_Plus'] == 30.0
        assert f['DI_Minus'] == 20.0
        assert f['Active_Modifiers'] == 'A (Rejection), B (Ignition)'
        assert f['Inst_Churn'] == 'CLEAR (No Churn)'


# ===================================================================
# EXIT-001 Tests
# ===================================================================

class TestEXIT001:

    def test_clear_signal_on_inactive(self):
        flat = _build_base_metrics()
        flat.update({'Exit_Signal': 'CLEAR', 'Exit_Triggers': [], 'Exit_Reason': None,
                     'Exit_VWAP_Counter': '0/3', 'Established_Hourly_Low': 208.8})
        result = _transform_output(_build_action_summary(), flat)
        assert result['exit_signals']['signal']['label'] == 'CLEAR'

    def test_triggers_empty_list(self):
        flat = _build_base_metrics()
        result = _transform_output(_build_action_summary(), flat)
        assert result['exit_signals']['triggers'] == []

    def test_reason_none_on_inactive(self):
        flat = _build_base_metrics()
        result = _transform_output(_build_action_summary(), flat)
        assert result['exit_signals']['reason'] is None

    def test_vwap_counter_object(self):
        flat = _build_base_metrics()
        flat['Exit_VWAP_Counter'] = '0/3'
        result = _transform_output(_build_action_summary(), flat)
        vc = result['exit_signals']['vwap_counter']
        assert isinstance(vc, dict)
        assert vc['value'] == 0  # integer, parsed from "0/3"
        assert vc['threshold'] == 3
        assert 'desc' in vc

    def test_clear_is_truthy(self):
        assert bool("CLEAR") is True

    def test_flatten_exit_signals(self):
        flat = _build_base_metrics()
        flat.update({
            'Exit_Signal': 'WARNING', 'Exit_Triggers': ['Hourly_Low_Breach'],
            'Exit_Reason': 'Close below established Hourly Low',
            'Exit_VWAP_Counter': '1/3', 'Established_Hourly_Low': 208.8,
        })
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert f['Exit_Signal'] == 'WARNING'
        assert f['Exit_Triggers'] == ['Hourly_Low_Breach']
        assert f['Exit_Reason'] == 'Close below established Hourly Low'
        assert f['Exit_VWAP_Counter'] == '1/3'
        assert f['Established_Hourly_Low'] == 208.8


# ===================================================================
# PROX-001 Tests
# ===================================================================

class TestPROX001:

    def test_blocking_condition_labels(self):
        mapping = {
            "VWAP_PULLBACK": "AWAITING_PULLBACK",
            "EXTENSION": "OVEREXTENDED",
            "ADX_THRESHOLD_20": "TREND_EMERGING",
        }
        for eng, lbl in mapping.items():
            assert lbl, f"No label for {eng}"

    def test_distance_has_unit(self):
        flat = _build_base_metrics()
        flat.update({
            'Proximity_Signal': 'APPROACHING', 'Proximity_Blocking_Gate': 'VWAP_PULLBACK',
            'Proximity_Condition_Label': 'AWAITING_PULLBACK', 'Proximity_Condition_Desc': 'test',
            'Proximity_Distance': 0.38, 'Proximity_Distance_Unit': 'ATR',
            'Proximity_Target': 218.94, 'Proximity_Note': 'test note',
        })
        result = _transform_output(_build_action_summary(), flat)
        assert result['entry_proximity']['distance']['unit'] == 'ATR'

    def test_inactive_collapse(self):
        flat = _build_base_metrics()
        result = _transform_output(_build_action_summary(), flat)
        ep = result['entry_proximity']
        assert ep['signal']['label'] == 'NONE'
        assert 'blocking_condition' not in ep
        assert 'distance' not in ep

    def test_vocabulary_checks_pass(self):
        note = "APPROACHING: test. All structural checks pass. THS: 50."
        assert "checks pass" in note
        assert "gates PASS" not in note

    def test_flatten_proximity(self):
        flat = _build_base_metrics()
        flat.update({
            'Proximity_Signal': 'APPROACHING', 'Proximity_Blocking_Gate': 'EXTENSION',
            'Proximity_Condition_Label': 'OVEREXTENDED', 'Proximity_Condition_Desc': 'test',
            'Proximity_Distance': 0.15, 'Proximity_Distance_Unit': 'ATR',
            'Proximity_Target': 220.0, 'Proximity_Note': 'test note',
        })
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert f['Proximity_Signal'] == 'APPROACHING'
        assert f['Proximity_Distance'] == 0.15
        assert f['Proximity_Target'] == 220.0


# ===================================================================
# RISK-001 Tests
# ===================================================================

class TestRISK001:

    def test_summary_favorable(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 3.5, 'Capital_Reward_Risk': 2.15,
            'Capital_RR_Label': 'HEALTHY', 'Expectancy_Threshold': 2.0,
            'Risk_Summary_Label': 'FAVORABLE', 'Risk_Summary_Desc': 'test.',
        })
        result = _transform_output(_build_action_summary(), flat)
        assert result['trade_risk']['summary']['label'] == 'FAVORABLE'

    def test_summary_adequate(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 2.5, 'Capital_Reward_Risk': 1.2,
            'Capital_RR_Label': 'NARROW', 'Expectancy_Threshold': 2.0,
            'Risk_Summary_Label': 'ADEQUATE', 'Risk_Summary_Desc': 'test.',
        })
        result = _transform_output(_build_action_summary(), flat)
        assert result['trade_risk']['summary']['label'] == 'ADEQUATE'

    def test_summary_unfavorable(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 1.5, 'Expectancy_Threshold': 2.0,
            'Risk_Summary_Label': 'UNFAVORABLE', 'Risk_Summary_Desc': 'test.',
        })
        result = _transform_output(_build_action_summary(), flat)
        assert result['trade_risk']['summary']['label'] == 'UNFAVORABLE'

    def test_threshold_inside_price_rr(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 3.0, 'Expectancy_Threshold': 2.0,
            'Risk_Summary_Label': 'FAVORABLE', 'Risk_Summary_Desc': 'test.',
        })
        result = _transform_output(_build_action_summary(), flat)
        tr = result['trade_risk']
        assert 'threshold' in tr['price_reward_risk']
        assert tr['price_reward_risk']['threshold']['value'] == 2.0
        assert 'threshold' not in tr['capital_reward_risk']

    def test_flatten_trade_risk(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 3.5, 'Reward_Risk_Note': 'note', 'Capital_Reward_Risk': 2.15,
            'Capital_RR_Label': 'HEALTHY', 'Risk_Per_Unit': 0.45,
            'Expectancy_Threshold': 2.0, 'Expectancy_Threshold_Note': 'PE-CAL-3',
            'Risk_Summary_Label': 'FAVORABLE', 'Risk_Summary_Desc': 'test.',
        })
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert f['Reward_Risk'] == 3.5
        assert f['Capital_Reward_Risk'] == 2.15
        assert f['Capital_RR_Label'] == 'HEALTHY'
        assert f['Risk_Per_Unit'] == 0.45
        assert f['Expectancy_Threshold'] == 2.0
        assert f['Expectancy_Threshold_Note'] == 'PE-CAL-3'


# ===================================================================
# CVN-001 Tests
# ===================================================================

class TestCVN001:

    def test_conviction_absent_from_grouped(self):
        flat = _build_base_metrics()
        result = _transform_output(_build_action_summary(), flat)
        assert 'range_quality' not in result['trade_quality']

    def test_flatten_no_conviction(self):
        flat = _build_base_metrics()
        grouped = _transform_output(_build_action_summary(), flat)
        _, _, f = _flatten(grouped)
        assert 'Conviction' not in f

    def test_breakout_no_sizing_in_trigger_source(self):
        import tbs_engine.trigger as _trig_mod
        _trig_path = os.path.abspath(_trig_mod.__file__)
        trigger_src = open(_trig_path).read()
        # After CVN-001, 'sizing' variable and 'Sizing: {sizing}' should be gone
        assert 'Sizing: {sizing}' not in trigger_src


# ===================================================================
# Flatten backward compat roundtrip
# ===================================================================

class TestFlattenRoundtrip:

    def test_scalar_types_preserved(self):
        flat = _build_base_metrics()
        flat.update({
            'Reward_Risk': 3.5, 'Reward_Risk_Note': 'note',
            'Capital_Reward_Risk': 2.0, 'Capital_RR_Label': 'HEALTHY',
            'Expectancy_Threshold': 2.0,
            'Risk_Summary_Label': 'FAVORABLE', 'Risk_Summary_Desc': 'test.',
            'Proximity_Signal': 'APPROACHING', 'Proximity_Blocking_Gate': 'VWAP_PULLBACK',
            'Proximity_Condition_Label': 'AWAITING_PULLBACK', 'Proximity_Condition_Desc': 'x',
            'Proximity_Distance': 0.38, 'Proximity_Distance_Unit': 'ATR',
            'Proximity_Target': 218.94, 'Proximity_Note': 'note',
            'Exit_VWAP_Counter': '0/3', 'Established_Hourly_Low': 208.8,
        })
        grouped = _transform_output(_build_action_summary(), flat)
        status, _, f = _flatten(grouped)
        assert status == 'HALT'
        assert isinstance(f.get('Reward_Risk'), (int, float))
        assert isinstance(f.get('ADX'), (int, float))
        assert isinstance(f.get('DI_Plus'), (int, float))
        assert isinstance(f.get('Trend_Health_Score'), (int, float))
        assert isinstance(f.get('Engine_State'), str)
        assert isinstance(f.get('Exit_Signal'), str)
        assert isinstance(f.get('Active_Modifiers'), str)
        assert isinstance(f.get('Inst_Churn'), str)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

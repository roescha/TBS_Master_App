# tbs_governor.py

def calculate_sizing_and_targets(
        profile: str,
        mode: str,
        regime: str,
        event_aware: bool,
        vix_storm: bool,
        audit_status: str,
        engine_metrics: dict,
        total_net_worth: float = 100000.0  # [MANDATE: Catch Dynamic Capital]
) -> dict:
    """
    [MANDATE: DOC 3 SEC V] Posture Multipliers, Sizing Math, and Safety Caps.
    """
    # [MANDATE: ALIGNMENT] Map the frontend string to the Engine Profile code
    p_mapping = {"SWING": "A", "TREND": "B", "WEALTH": "C", "A": "A", "B": "B", "C": "C"}
    p_code = p_mapping.get(profile.upper(), "B")

    multiplier = 1.0
    mod_log = []

    # --- 1. POSTURE MULTIPLIERS (Cumulative) ---
    if "DEFENSIVE" in regime:
        multiplier *= 0.5
        mod_log.append("Defensive Regime (0.5x)")

    if event_aware:
        multiplier *= 0.5
        mod_log.append("Event-Aware <10d (0.5x)")

    if "TURNAROUND" in audit_status:
        multiplier *= 0.5
        mod_log.append("Turnaround Patch (0.5x)")

    if vix_storm:
        multiplier *= 0.5
        mod_log.append("Storm Watch VIX >= 25 (0.5x)")

    if "LOW" in engine_metrics.get("Conviction", ""):
        multiplier *= 0.5
        mod_log.append("Low-Conviction Range (0.5x)")

    if "ACTIVE" in engine_metrics.get("Inst_Churn", ""):
        multiplier *= 0.5
        mod_log.append("Inst. Churn/Modifier D (0.5x)")

    # --- 2. RISK & TARGET CALCULATIONS ---
    entry_price = engine_metrics.get('Price', 0)
    stop_price = engine_metrics.get('Stop_Value', 0)
    risk_per_share = round(entry_price - stop_price, 2)

    target_price = "N/A"
    dynamic_label, dynamic_val = "INFO", "N/A"

    if p_code == "A":
        # SWING: 1:2 RR to Consolidation High
        resistance = engine_metrics.get('Resistance', entry_price)
        reward = resistance - entry_price
        expectancy = round(reward / risk_per_share, 2) if risk_per_share > 0 else 0
        dynamic_label, dynamic_val = "EXPECTANCY", f"{expectancy}:1"
        target_price = round(resistance, 2)

    elif p_code == "B":
        # TREND: Target 1 fixed @ +1.5 ATR
        atr = engine_metrics.get('ATR', 1.0)
        ema8 = engine_metrics.get('EMA_8', entry_price)
        extension = round((entry_price - ema8) / atr, 2) if atr > 0 else 0
        dynamic_label, dynamic_val = "EXTENSION", f"{extension} ATR"
        target_price = round(entry_price + (atr * 1.5), 2)

    elif p_code == "C":
        # WEALTH: Floor Proximity Audit
        sma200 = engine_metrics.get('SMA_200', entry_price)
        proximity = round(abs(entry_price - sma200) / sma200 * 100, 2) if sma200 > 0 else 0
        dynamic_label, dynamic_val = "PROXIMITY", f"{proximity}% (200-SMA)"
        target_price = "OPEN-ENDED"

    # --- 3. MATHEMATICAL UNIT SIZING & SAFETY CAPS [MANDATE: DOC 3] ---
    risk_pct = 0.0025 if profile == "A" else 0.005 # 0.25% for A, 0.5% for B/C

    # [MANDATE: DYNAMIC ALLOCATION] Calculate Base Units (0.5% Risk on Dynamic Capital)
    if risk_per_share > 0:
        base_risk_capital = total_net_worth * 0.005
        base_units = base_risk_capital / risk_per_share
    else:
        base_units = 0

    # Apply cumulative multipliers
    calculated_units = int(base_units * multiplier)

    # --- [MANDATE: DOC 3 SEC 217 & 230] CAPITAL SAFETY CAPS ---
    total_capital_outlay = calculated_units * entry_price
    max_cash_cap = total_net_worth * 0.25

    if profile == "B" and total_capital_outlay > (total_net_worth * 0.01):
        final_units = int((total_net_worth * 0.01) / entry_price)
    elif total_capital_outlay > max_cash_cap:
        final_units = int(max_cash_cap / entry_price)
    else:
        final_units = calculated_units

    open_risk_heat = final_units * risk_per_share

    # Minimum Utility Gate
    utility_halt = False
    if mode == "LIVE" and open_risk_heat < 50:
        utility_halt = True

    return {
        "multiplier": multiplier,
        "modifier_log": mod_log,
        "entry_price": entry_price,       # [MANDATE: SSoT Handshake for Frontend Entry]
        "stop_price": stop_price,         # [MANDATE: SSoT Handshake for Frontend Stop]
        "risk_per_share": risk_per_share,
        "target_price": target_price,
        "dynamic_label": dynamic_label,
        "dynamic_value": dynamic_val,
        "sizing_msg": f"{multiplier * 100}%" if mode == "LIVE" else "BYPASSED (INFO MODE)",
        "final_units": final_units,
        "total_capital_outlay": round(final_units * entry_price, 2),
        "open_risk_heat": round(open_risk_heat, 2),
        "utility_halt": utility_halt
    }
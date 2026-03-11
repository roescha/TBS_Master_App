__all__ = ['_exit_profile_a', '_exit_profile_b', '_exit_profile_c', '_compute_exit_signals']

def _exit_profile_a(state, df, last, i0, price_scaler, metrics):
    """Profile A exit: VWAP 3-bar counter, strict close, no grace buffer.

    Section X exit condition logic [MANDATE: DOC 2 TABLE 1]:
      Profile A: Price below hourly low OR consecutive closes below VWAP.

    All Exit_Signal values cast to native Python types.
    pandas comparisons return numpy.bool_ which json.dumps cannot serialize.
    [PE-28] Exit_Signal graduated from boolean to "WARNING" / "EXIT" / false.
      WARNING: Early deterioration -- single trigger. Tighten awareness, no
               mechanical action mandated. R:R and Profit_Target remain visible.
      EXIT:    Structural break -- multiple triggers or sustained VWAP violation.
               Full mechanical exit mandate. R:R and Profit_Target suppressed.

    Returns: False | "WARNING" | "EXIT"
    """
    est_hourly_low_raw = float(df['low'].iloc[-12:-2].min())
    exit_a_low    = bool(last['close'] < est_hourly_low_raw)
    # [PE-27] Surface computed reference so operator can verify the trigger.
    metrics["Established_Hourly_Low"] = round(est_hourly_low_raw / price_scaler, 2)
    # [MANDATE: DOC 2 SEC X] 3 consecutive hourly closes STRICTLY below VWAP.
    # This counter is DECOUPLED from the entry-side consec_below counter
    # (which applies the §4.1 grace buffer of 0.15 ATR). The grace buffer
    # exists to prevent micro-wicks from triggering false violated/reclaim
    # states on the ENTRY side. On the EXIT side, the risk asymmetry is
    # inverted: the operator already holds the position, and sustained closes
    # below VWAP -- even by small amounts -- represent structural deterioration.
    # §X defines "closes below VWAP" with no grace qualifier. Applying the
    # entry-side grace here would delay exit signals on deteriorating positions.
    # [R-2 DESIGN NOTE] Exit counter intentionally uses NO grace buffer (Doc 2 §X).
    # Entry counter uses 0.15 ATR grace (Doc 2 §4.1). These can disagree on bar counts.
    # PE-25 override ensures is_floor_failure always takes precedence when entry-side
    # detects structural break, regardless of exit counter state.
    _exit_consec = 0
    for _eoff in range(0, 5):  # [R-3 FIX] Was range(0,4) -- now matches entry counter depth
        if df['close'].iloc[i0 - _eoff] < df['ANCHOR'].iloc[i0 - _eoff]:
            _exit_consec += 1
        else:
            break
    exit_a_vwap   = bool(_exit_consec >= 3)
    # [PE-28] Graduated severity:
    #   - VWAP 3-bar alone        → EXIT (sustained structural deterioration)
    #   - Both triggers            → EXIT
    #   - Hourly low breach alone  → WARNING (could be single volatile bar)
    #   - Neither                  → false
    _exit_triggers = []
    if exit_a_low:
        _exit_triggers.append("Hourly_Low_Breach")
    if exit_a_vwap:
        _exit_triggers.append("VWAP_3Bar_Violation")
    if exit_a_vwap:
        exit_signal = "EXIT"
    elif exit_a_low:
        exit_signal = "WARNING"
    else:
        exit_signal = False
    metrics["Exit_Signal"]       = exit_signal
    metrics["Exit_Triggers"]     = _exit_triggers if _exit_triggers else "None"
    metrics["Exit_VWAP_Counter"] = f"{min(_exit_consec, 3)}/3"
    metrics["Exit_Reason"]       = (
        f"VWAP Violation ({_exit_consec} consecutive bar(s) below floor -- strict Sec X counter)"
        if exit_a_vwap else
        "Close below established Hourly Low" if exit_a_low
        else "None"
    )
    return exit_signal


def _exit_profile_b(state, df, last, _is_c3, target_1_b, i0, price_scaler, metrics):
    """Profile B exit: SMA 50 standard + EMA 8 convexity (is_resolving gated).

    Section X exit condition logic [MANDATE: DOC 2 TABLE 1]:
      Profile B: Daily close below SMA 50 OR EMA 8 (convexity protocol).

    [PE-28] Exit_Signal graduated from boolean to "WARNING" / "EXIT" / false.
      WARNING: Early deterioration -- single trigger.
      EXIT:    Structural break -- multiple triggers.

    Returns: False | "WARNING" | "EXIT"
    """
    exit_b_std   = bool(last['close'] < last['SMA_50'])
    exit_b_conv  = bool(state.is_resolving and not state.is_trending and (last['close'] < last['EMA_8']))
    # [PE-28] Profile B graduation:
    #   - Close < SMA_50           → EXIT (structural floor break)
    #   - Close < EMA_8 only       → WARNING (Convexity tightening, floor intact)
    #   - Neither                  → false
    _exit_triggers = []
    if exit_b_std:
        _exit_triggers.append("SMA_50_Breach")
    if exit_b_conv:
        _exit_triggers.append("EMA_8_Convexity_Breach")
    if exit_b_std:
        exit_signal = "EXIT"
    elif exit_b_conv:
        # [CONVEXITY] C-3 EMA 8 EXIT escalation (Redesign Proposal §6.2 / Execution Map §VI)
        # For C-3 positions, EMA 8 IS the structural floor. A breach is thesis
        # invalidation, not a caution flag. Escalate from WARNING → EXIT.
        # For C-1/C-2, EMA 8 breach remains WARNING (floor intact at SMA 50).
        exit_signal = "EXIT" if _is_c3 else "WARNING"
    else:
        exit_signal = False
    metrics["Exit_Signal"]       = exit_signal
    metrics["Exit_Triggers"]     = _exit_triggers if _exit_triggers else "None"
    metrics["Exit_Reason"]       = (
        "Close below EMA 8 (Convexity active) -- C-3 EXIT: thesis invalidation" if exit_b_conv and _is_c3 and not exit_b_std else
        "Close below EMA 8 (Convexity active)" if exit_b_conv and not exit_b_std else
        "Close below 50-SMA" if exit_b_std
        else "None"
    )
    return exit_signal


def _exit_profile_c(state, df, last, i0, price_scaler, metrics):
    """Profile C exit: SMA 200 weekly.

    Section X exit condition logic [MANDATE: DOC 2 TABLE 1]:
      Profile C: Weekly close below SMA 200.

    Profile C has a single structural trigger -- always EXIT when breached.

    Returns: False | "WARNING" | "EXIT"
    """
    exit_c  = bool(last['close'] < last['SMA_200'])
    exit_signal  = "EXIT" if exit_c else False
    metrics["Exit_Signal"]       = exit_signal
    metrics["Exit_Triggers"]     = ["SMA_200_Breach"] if exit_c else "None"
    metrics["Exit_Reason"]       = "Close below 200-SMA" if exit_c else "None"
    return exit_signal


def _compute_exit_signals(state, p_code, df, last, _is_c3, target_1_b,
                          i0, price_scaler, metrics):
    """Dispatcher: route to per-profile exit handler, apply shared post-exit logic.

    RFT-004 Phase 1: Exit signal decomposition. Per-profile regime logic is
    owned by _exit_profile_a/b/c. This dispatcher owns the contract and
    applies shared PE-25 floor failure override, Bug #33 Profit_Target_Synthetic
    suppression, and PE-7b Reward_Risk suppression.

    Returns: False | "WARNING" | "EXIT"
    """
    # --- Per-profile exit signal ---
    if p_code == "A":
        exit_signal = _exit_profile_a(state, df, last, i0, price_scaler, metrics)
    elif p_code == "B":
        exit_signal = _exit_profile_b(state, df, last, _is_c3, target_1_b, i0, price_scaler, metrics)
    elif p_code == "C":
        exit_signal = _exit_profile_c(state, df, last, i0, price_scaler, metrics)
    else:
        exit_signal = False
        metrics["Exit_Signal"] = False
        metrics["Exit_Triggers"] = "None"
        metrics["Exit_Reason"] = "None"

    # --- [PE-25 FIX] Floor failure override ---
    # Structural break (threshold+ consecutive bars below floor) cannot be reset
    # by a single reclaim bar. is_floor_failure (entry-side) always takes precedence.
    # [3-BAR RECLAIM MANDATE] _reclaim_run tracks recovery progress (1/3, 2/3).
    if state.is_floor_failure and exit_signal != "EXIT":
        exit_signal = "EXIT"
        metrics["Exit_Signal"] = "EXIT"
        _existing_triggers = metrics.get("Exit_Triggers", [])
        if isinstance(_existing_triggers, str):
            _existing_triggers = []
        _existing_triggers.append("Floor_Failure_Override")
        metrics["Exit_Triggers"] = _existing_triggers
        metrics["Exit_Reason"] = (
            f"FLOOR FAILURE OVERRIDE: {state.consec_below} consecutive completed bars below floor. "
            f"Reclaim progress: {state._reclaim_run}/3 bars above floor. "
            f"3 consecutive closes above floor required to reset structural break."
        )
        metrics["Floor_Failure_Reclaim"] = f"{state._reclaim_run}/3"

    # --- [BUG #33 FIX] Profit_Target_Synthetic suppression ---
    # [PE-28] Suppression only on EXIT. WARNING preserves forward metrics.
    if target_1_b is not None and exit_signal == "EXIT":
        target_1_b = None
        metrics["Profit_Target_Synthetic_Note"] = "SUPPRESSED: Exit_Signal EXIT -- floor broken, no entry context"
    if target_1_b is not None:
        metrics["Profit_Target_Synthetic"] = target_1_b   # Profile B only: Floor + 1.5 ATR

    # --- [PE-7b FIX] Reward_Risk suppression ---
    # [PE-28] WARNING preserves R:R and Profit_Target -- operator needs context.
    if exit_signal == "EXIT" and metrics.get("Reward_Risk") is not None:
        metrics["Reward_Risk"]      = None
        metrics["Profit_Target"]    = None
        metrics["Reward_Risk_Note"] = (
            f"SUPPRESSED: Exit_Signal EXIT -- floor violated "
            f"({metrics.get('Exit_Reason', 'structural break')}). "
            f"No entry context. Await confirmed close above floor for reclaim evaluation."
        )
    return exit_signal

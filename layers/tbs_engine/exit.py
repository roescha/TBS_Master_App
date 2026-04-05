import pandas as pd

__all__ = ['_exit_profile_a', '_exit_profile_b', '_exit_profile_c', '_compute_exit_signals']

def _exit_profile_a(state, df, last, i0, price_scaler, metrics, cfg):
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
    est_hourly_low_raw = float(df['low'].iloc[cfg.resistance_slice_start:cfg.resistance_slice_end].min())  # PE-43: was hardcoded iloc[-12:-2]
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
    metrics["Exit_Signal"]       = exit_signal if exit_signal else "CLEAR"
    metrics["Exit_Triggers"]     = _exit_triggers if _exit_triggers else []
    metrics["Exit_VWAP_Counter"] = f"{min(_exit_consec, 3)}/3"
    metrics["Exit_Reason"]       = (
        f"VWAP Violation ({_exit_consec} consecutive bar(s) below floor -- strict Sec X counter)"
        if exit_a_vwap else
        "Close below established Hourly Low" if exit_a_low
        else None
    )
    return exit_signal


def _exit_profile_b(state, df, last, _is_c3, target_1_b, i0, price_scaler, metrics, df_ctx=None):
    """Profile B exit: SMA 50 standard + EMA 8 convexity (is_resolving gated).

    Section X exit condition logic [MANDATE: DOC 2 TABLE 1]:
      Profile B: Daily close below SMA 50 OR EMA 8 (convexity protocol).

    [PE-28] Exit_Signal graduated from boolean to "WARNING" / "EXIT" / false.
      WARNING: Early deterioration -- single trigger.
      EXIT:    Structural break -- multiple triggers.

    [CVX-003] C-3 Three-Tier Exit Model:
      Priority 1: SMA 200 catastrophic backstop → EXIT
      Priority 2: EMA 8 counter >= 2 (state-independent) → EXIT
      Priority 3: SMA 50 breach (downgraded for C-3) → WARNING
      Priority 4: EMA 8 counter = 1 → WARNING
      C-1/C-2 behavior unchanged (guarded by _is_c3).

    Returns: False | "WARNING" | "EXIT"
    """
    # ── Standard checks (unchanged) ──
    exit_b_std = bool(last['close'] < last['SMA_50'])

    # ── C-3 SMA 200 catastrophic backstop (PRIORITY 1) ──
    # NaN guard: SMA 200 may be NaN with insufficient history.
    # Same defensive pattern as gates.py:20-21.
    exit_b_sma200 = bool(
        _is_c3
        and not pd.isna(last['SMA_200'])
        and last['close'] < last['SMA_200']
    )

    # ── EMA 8 logic: state-independent for C-3, gated for C-1/C-2 ──
    if _is_c3:
        # Sub-item A: remove state gate for C-3
        _ema8_below = bool(last['close'] < last['EMA_8'])
        # Sub-item B: 2-bar counter (same pattern as Profile A VWAP counter,
        # exit.py:36-41). Iterate backward from evaluated bar, count
        # consecutive closes below EMA 8, break on first bar above.
        _ema8_consec = 0
        for _eoff in range(0, 3):  # check last 3 bars, need 2 consecutive
            idx = len(df) - 1 - _eoff
            if idx >= 0 and df['close'].iloc[idx] < df['EMA_8'].iloc[idx]:
                _ema8_consec += 1
            else:
                break
    else:
        # C-1/C-2: original gated check, no counter
        _ema8_below = bool(
            state.is_resolving and not state.is_trending
            and (last['close'] < last['EMA_8'])
        )
        _ema8_consec = 1 if _ema8_below else 0  # no counter for C-1/C-2

    # ── Priority cascade (first match wins) ──
    _exit_triggers = []

    # [CVX-003-OBS-1 Option B] Weekly context cross-check for Priority 1.
    # If weekly structure is intact (golden cross + SMA 50 rising),
    # this is likely a parabolic artifact (inverted daily MAs from
    # extended peak), not a genuine catastrophe. Skip to Priority 2/3/4.
    # If weekly data unavailable or weekly structure broken → fire EXIT.
    _weekly_intact = False
    if (df_ctx is not None
            and len(df_ctx) >= 2
            and 'SMA_50' in df_ctx.columns
            and 'SMA_200' in df_ctx.columns):
        _wk = df_ctx.iloc[-1]
        _wk_prior = df_ctx.iloc[-2]
        _has_sma50 = not pd.isna(_wk['SMA_50']) and not pd.isna(_wk_prior['SMA_50'])
        _has_sma200 = not pd.isna(_wk['SMA_200'])
        if _has_sma50 and _has_sma200:
            _wk_gc = bool(_wk['SMA_50'] > _wk['SMA_200'])
            _wk_rising = bool(_wk['SMA_50'] > _wk_prior['SMA_50'])
            _weekly_intact = _wk_gc and _wk_rising

    if _is_c3 and exit_b_sma200 and not _weekly_intact:
        # PRIORITY 1: SMA 200 catastrophic backstop (weekly confirms breakdown)
        exit_signal = "EXIT"
        _exit_triggers.append("SMA_200_Catastrophic")
        exit_reason = "Close below 200-SMA -- C-3 catastrophic backstop"

    elif _is_c3 and _ema8_consec >= 2:
        # PRIORITY 2: EMA 8 counter >= 2 (thesis invalidation)
        exit_signal = "EXIT"
        _exit_triggers.append("EMA_8_Counter_Exit")
        exit_reason = "Close below EMA 8 (2 consecutive) -- C-3 thesis invalidation"

    elif exit_b_std and _is_c3:
        # PRIORITY 3: SMA 50 downgraded to WARNING for C-3
        exit_signal = "WARNING"
        _exit_triggers.append("SMA_50_Downgrade")
        exit_reason = "Close below 50-SMA -- C-3 WARNING: structural floor intact at SMA 200"

    elif exit_b_std and not _is_c3:
        # C-1/C-2: SMA 50 remains EXIT (unchanged)
        exit_signal = "EXIT"
        _exit_triggers.append("SMA_50_Breach")
        exit_reason = "Close below 50-SMA"

    elif _is_c3 and _ema8_consec == 1:
        # PRIORITY 4: EMA 8 counter = 1 (early deterioration)
        exit_signal = "WARNING"
        _exit_triggers.append("EMA_8_Counter_Warning")
        exit_reason = "Close below EMA 8 (1/2 counter) -- monitor for 2nd consecutive close"

    elif _ema8_below and not _is_c3:
        # C-1/C-2: EMA 8 single-bar WARNING (unchanged)
        exit_signal = "WARNING"
        _exit_triggers.append("EMA_8_Convexity_Breach")
        exit_reason = "Close below EMA 8 (Convexity active)"

    else:
        exit_signal = False
        exit_reason = None

    # ── Metrics ──
    metrics["Exit_Signal"]   = exit_signal if exit_signal else "CLEAR"
    metrics["Exit_Triggers"] = _exit_triggers if _exit_triggers else []
    metrics["Exit_Reason"]   = exit_reason
    if _is_c3:
        metrics["Exit_EMA8_Counter"] = f"{min(_ema8_consec, 2)}/2"

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
    metrics["Exit_Signal"]       = exit_signal if exit_signal else "CLEAR"
    metrics["Exit_Triggers"]     = ["SMA_200_Breach"] if exit_c else []
    metrics["Exit_Reason"]       = "Close below 200-SMA" if exit_c else None
    return exit_signal


def _compute_exit_signals(state, p_code, df, last, _is_c3, target_1_b,
                          i0, price_scaler, metrics, cfg, df_ctx=None, _ff_threshold=4):
    """Dispatcher: route to per-profile exit handler, apply shared post-exit logic.

    RFT-004 Phase 1: Exit signal decomposition. Per-profile regime logic is
    owned by _exit_profile_a/b/c. This dispatcher owns the contract and
    applies shared PE-25 floor failure override, Bug #33 Profit_Target_Synthetic
    suppression, and PE-7b Reward_Risk suppression.

    Returns: False | "WARNING" | "EXIT"
    """
    # --- Per-profile exit signal ---
    if p_code == "A":
        exit_signal = _exit_profile_a(state, df, last, i0, price_scaler, metrics, cfg)
    elif p_code == "B":
        exit_signal = _exit_profile_b(state, df, last, _is_c3, target_1_b, i0, price_scaler, metrics, df_ctx=df_ctx)
    elif p_code == "C":
        exit_signal = _exit_profile_c(state, df, last, i0, price_scaler, metrics)
    else:
        exit_signal = False
        metrics["Exit_Signal"] = "CLEAR"
        metrics["Exit_Triggers"] = []
        metrics["Exit_Reason"] = None

    # --- [PE-25 FIX] Floor failure override + [FFD-001] BREACH/FAILURE bifurcation ---
    # Structural break (threshold+ consecutive bars below floor) cannot be reset
    # by a single reclaim bar. is_floor_failure (entry-side) always takes precedence.
    # [3-BAR RECLAIM MANDATE] _reclaim_run tracks recovery progress (1/3, 2/3).
    # [FFD-001] If composite conditions indicate CONSOLIDATION (FLOOR BREACH),
    # escalate to WARNING only (not EXIT). Per-profile EXIT signals are preserved.
    if state.is_floor_failure and exit_signal != "EXIT":
        _ffd_context = metrics.get("Floor_Failure_Context")
        if _ffd_context == "CONSOLIDATION":
            # FLOOR BREACH: higher-frame intact → WARNING (PE-28 graduation)
            exit_signal = "WARNING"
            metrics["Exit_Signal"] = "WARNING"
            _existing_triggers = metrics.get("Exit_Triggers", [])
            if isinstance(_existing_triggers, str):
                _existing_triggers = []
            if "Floor_Breach" not in _existing_triggers:
                _existing_triggers.append("Floor_Breach")
            metrics["Exit_Triggers"] = _existing_triggers
            metrics["Exit_Reason"] = (
                f"FLOOR BREACH: {state.consec_below}/{_ff_threshold} consecutive bars below floor "
                f"(threshold reached, higher-frame intact). Monitor for 3-bar reclaim. "
                f"Reclaim progress: {state._reclaim_run}/3 bars above floor."
            )
            metrics["Floor_Failure_Reclaim"] = f"{state._reclaim_run}/3"
        else:
            # FLOOR FAILURE: structural breakdown → EXIT (unchanged behaviour)
            exit_signal = "EXIT"
            metrics["Exit_Signal"] = "EXIT"
            _existing_triggers = metrics.get("Exit_Triggers", [])
            if isinstance(_existing_triggers, str):
                _existing_triggers = []
            _existing_triggers.append("Floor_Failure_Override")
            metrics["Exit_Triggers"] = _existing_triggers
            metrics["Exit_Reason"] = (
                f"FLOOR FAILURE OVERRIDE: {state.consec_below}/{_ff_threshold} consecutive bars below floor "
                f"(threshold reached, higher-frame broken). "
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

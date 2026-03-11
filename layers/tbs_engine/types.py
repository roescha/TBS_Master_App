from collections import namedtuple
from dataclasses import dataclass, field

__all__ = ['GRACE_BUFFER_ATR_PCT', 'FloorState', 'MetricsResult', '_DeepReclaimResult', 'ProfileConfig', 'StateBundle', 'RunContext']
GRACE_BUFFER_ATR_PCT = 0.15  # Doc 2 §4.1: price within 15% ATR of floor is floor-hugging

FloorState = namedtuple('FloorState', [
    'consec_below',        # int: consecutive bars below floor
    'is_violated',         # bool: 1 <= consec_below < threshold
    'is_reclaim',          # bool: is_violated AND current bar above floor
    'is_floor_failure',    # bool: consec_below >= threshold
    'current_above_floor', # bool: evaluated bar is above floor
])

MetricsResult = namedtuple('MetricsResult', [
    'target_1_b',             # Profile B synthetic profit target (or None)
    'floor_price',            # Display-scaled structural floor
    'hard_stop',              # Display-scaled hard stop
    'floor_prox_pct',         # Profile C floor proximity % (or None)
    'engine_state',           # Display label string
    'anchor_label',           # Display label string
    'resistance_display',     # Display-scaled 10-bar resistance high
    'resistance_suppressed',  # bool: price above resistance (target invalid)
])

_DeepReclaimResult = namedtuple('_DeepReclaimResult', [
    'reclaim_run',       # int: consecutive above-floor bars from i0 backward
    'hist_below',        # int: consecutive below-floor bars behind the reclaim streak
    'is_recent_failure', # bool: hist_below >= threshold AND reclaim_run <= 2
])

# RFT-001 PHASE 4: ProfileConfig Dataclass + Factory + Data Layer Extraction
# Spec §III.2 (ProfileConfig), §III.3 (Layer 1 - Data Fetch & Indicator Computation)
# ======================================================================


@dataclass(frozen=True)
class ProfileConfig:
    """Read-only profile-specific parameter configuration.

    Constructed once per run_tbs_engine() invocation via _build_config().
    Gates consume it; they never modify it. Collapses parameter-selection
    branches in the data layer into cfg.attribute lookups.

    RFT-001 Phase 4 | Spec §III.2
    """
    iq: int                       # indicator query index (-2 for A, -1 for B/C)
    min_bars_required: int        # data sufficiency threshold
    window_limit: int             # execution window staleness limit
    ff_threshold: int             # floor failure consecutive bar threshold
    ext_limit_trending: float     # extension limit when TRENDING (ATR multiplier)
    ext_limit_resolving: float    # extension limit when RESOLVING (ATR multiplier)
    ext_limit_etf: float          # extension limit for ETF (Profiles B/C)
    resistance_slice_start: int   # iloc start for resistance/focus window
    resistance_slice_end: int     # iloc end for resistance/focus window
    tf_resolution: str            # primary timeframe bar size
    tf_duration: str              # primary timeframe lookback
    ctx_resolution: str           # context chart bar size
    ctx_duration: str             # context chart lookback
    fb_max: float                 # THS Floor Buffer max
    ta_max: int                   # THS Trend Age max
    prev_bar_offset: int          # offset for morphology prev_high/prev_low
    required_ma_cols: tuple       # required MA columns for existence guard
    pb_upper_col: str             # column for pullback zone upper bound anchor


@dataclass
class StateBundle:
    """All state classification results as a single typed object.

    Downstream layers receive this instead of loose local variables.
    ETF Logic Lock snapshots are fields of StateBundle, not loose
    variables that could be shadowed or incorrectly scoped.
    """
    # --- Core state classification ---
    is_trending: bool
    is_resolving: bool
    ma_stack_full: bool
    ma_squeeze: bool
    ema_stacked: bool

    # --- Scalars (from raw_metrics, included for downstream convenience) ---
    adx_t: float
    adx_t1: float
    di_plus: float
    di_minus: float
    atr_raw: float

    # --- ETF Logic Lock snapshots + composite entry flags ---
    _etf_entry_trending: bool
    _etf_entry_resolving: bool
    _entry_trending: bool
    _entry_resolving: bool

    # --- Derived classification flags ---
    _resolving_is_bearish: bool

    # --- Set after violated state detection (require post-convexity ANCHOR) ---
    is_reclaim: bool = False
    is_ambiguous: bool = False
    is_violated: bool = False
    is_floor_failure: bool = False
    floor_raw: float = 0.0
    consec_below: int = 0
    _reclaim_run: int = 0


@dataclass
class RunContext:
    """Shared evaluation context passed between engine layers.

    Constructed once in run_tbs_engine after Layer 1 + Layer 2.
    Passed by reference to Layers 3–5. Fields are set progressively
    as the engine computes them. Read-only after initial assignment
    (no layer should mutate a field set by a prior layer).

    RFT-003 Finding F3 | Spec §III.3
    """
    # Identity
    state: 'StateBundle'
    cfg: 'ProfileConfig'
    p_code: str
    is_etf: bool
    _is_c3: bool
    # Data
    df: 'pd.DataFrame'
    last: 'pd.Series'
    metrics: dict
    # Scalars (set after Layer 1 + state classification)
    price_scaler: float
    actual_price: float
    structural_floor_raw: float
    hard_stop_raw: float
    resistance_raw: float
    # --- Fields with defaults (set progressively) ---
    atr_dist: float = 0.0
    ext_limit: float = 0.0
    floor_prox_pct: float = 0.0
    adx_accel: float = 0.0
    adx_accel_state: str = ""
    vol_confirm_ratio: float = 0.0
    vol_confirm_state: str = ""
    exit_signal: object = False  # Tri-state: False | "WARNING" | "EXIT"
    window_count: int = 0
    window_limit: int = 0
    conviction_state: str = ""
    # Display / diagnostic (set during metrics population)
    floor_price: float = None
    hard_stop: float = None
    resistance_display: float = None
    _resistance_suppressed: bool = False
    # Chart reference
    chart_ref: str = ""
    # Profit target (Profile A)
    cons_high_raw: float = None
    risk_a: float = None
    reward_a: float = None
    # Morphology (set by inline code, consumed by gates and trigger)
    prev_high: float = 0.0
    prox_anchor: float = 0.0
    # Proximity audit context
    _prx_ctx: dict = None
    # Chart infrastructure
    chart_dir: str = ""
    clean_ticker: str = ""
    adx_col: str = ""
    dmp_col: str = ""
    dmn_col: str = ""
    profile: str = ""
    # SSG fields
    _ssg_adjusted: bool = False
    _ssg_original_raw: float = 0.0
    _ssg_reason: str = ""
    # Context data (set during run_tbs_engine, consumed by _compute_early_capital_rr)
    _df_ctx: 'pd.DataFrame' = None

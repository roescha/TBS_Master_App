"""IVR-001-BUG-4 / IVR-001-BUG-4-SUB-1: IV Fetch Fix — Unit Tests.

Covers the streaming-mode fix for IBKR Error 321 (snapshot=True + genericTickList
rejected). Both Profile A and Profile B/C IV blocks now call the extracted helper
`_fetch_iv_streaming()` which uses streaming mode (snapshot=False) with a poll-loop.

Original tests (IVR-001-BUG-4):
  T1  test_profile_a_iv_fetch_uses_streaming_helper  (renamed from snapshot)
  T2  test_profile_a_primary_call_has_no_tick_106
  T3  test_profile_a_iv_exception_does_not_affect_price
  T4  test_profile_a_primary_exception_does_not_block_iv_fetch
  T5  test_ivr_unavailable_desc_includes_tick_106_cause

New tests (IVR-001-BUG-4-SUB-1):
  T6  test_iv_helper_uses_streaming_mode
  T7  test_iv_helper_early_exit_on_initial_sleep
  T8  test_iv_helper_poll_loop_finds_iv
  T9  test_iv_helper_timeout_returns_none
  T10 test_iv_helper_nan_treated_as_missing
  T11 test_iv_helper_exception_cancels_and_returns_none
  T12 test_profile_b_c_uses_streaming_helper
"""

import ast
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# ── Path setup ───────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, str(_PROJECT_ROOT))

_DATA_PY_PATH = _PROJECT_ROOT / "tbs_engine" / "data.py"


# ── AST helpers (T1, T2, T6, T12) ────────────────────────────────────────────

def _load_data_py_ast():
    """Parse tbs_engine/data.py and return the AST."""
    src = _DATA_PY_PATH.read_text()
    return src, ast.parse(src, filename=str(_DATA_PY_PATH))


def _find_fetch_and_compute(tree):
    """Return the FunctionDef node for _fetch_and_compute."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_and_compute":
            return node
    raise AssertionError("_fetch_and_compute function not found in data.py")


def _find_fetch_iv_streaming(tree):
    """Return the FunctionDef node for _fetch_iv_streaming."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_iv_streaming":
            return node
    raise AssertionError("_fetch_iv_streaming function not found in data.py")


def _is_profile_a_branch(if_node: ast.If) -> bool:
    """True if the If's test is the expression `p_code == "A"`."""
    t = if_node.test
    return (
        isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "p_code"
        and len(t.ops) == 1
        and isinstance(t.ops[0], ast.Eq)
        and len(t.comparators) == 1
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value == "A"
    )


def _branch_contains_reqmktdata(if_node: ast.If) -> bool:
    """True iff the If's True-branch body contains an ib.reqMktData(...) call."""
    for stmt in if_node.body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "reqMktData"
                and isinstance(f.value, ast.Name)
                and f.value.id == "ib"
            ):
                return True
    return False


def _branch_contains_helper_call(stmts, helper_name="_fetch_iv_streaming") -> bool:
    """True iff the statement list contains a call to the named helper function."""
    for stmt in stmts:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Name) and f.id == helper_name:
                return True
    return False


def _find_profile_a_block(fn_node: ast.FunctionDef) -> ast.If:
    """Return the `if p_code == "A":` If node inside _fetch_and_compute that
    contains ib.reqMktData calls OR _fetch_iv_streaming calls. _fetch_and_compute
    has multiple `p_code == "A"` branches; only the one that issues reqMktData
    or calls the IV helper is the one we care about."""
    candidates = [
        node for node in ast.walk(fn_node)
        if isinstance(node, ast.If) and _is_profile_a_branch(node)
    ]
    if not candidates:
        raise AssertionError('no `if p_code == "A":` branch found inside _fetch_and_compute')

    matching = [c for c in candidates
                if _branch_contains_reqmktdata(c) or _branch_contains_helper_call(c.body)]
    if len(matching) == 0:
        raise AssertionError(
            '`if p_code == "A":` branch with reqMktData or _fetch_iv_streaming calls not found'
        )
    if len(matching) > 1:
        lines = [c.lineno for c in matching]
        raise AssertionError(
            f'more than one `if p_code == "A":` branch contains reqMktData/'
            f'_fetch_iv_streaming (at lines {lines}) — ambiguous'
        )
    return matching[0]


def _find_reqmktdata_calls(if_node: ast.If) -> list[ast.Call]:
    """Return all `ib.reqMktData(...)` Call nodes inside the Profile A branch body
    (i.e. the True-branch). Out-of-order relative to source — the caller must
    sort by lineno. The Profile B/C else-branch is intentionally excluded."""
    calls: list[ast.Call] = []
    for stmt in if_node.body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "reqMktData"
                and isinstance(f.value, ast.Name)
                and f.value.id == "ib"
            ):
                calls.append(node)
    return sorted(calls, key=lambda c: c.lineno)


def _const(node):
    """Extract a constant value, or raise if node isn't a Constant."""
    assert isinstance(node, ast.Constant), f"expected ast.Constant, got {type(node).__name__}"
    return node.value


# ── Helper: load _fetch_iv_streaming from source ─────────────────────────────

def _load_fetch_iv_streaming_func():
    """Extract and compile _fetch_iv_streaming from data.py source so it can
    be injected into exec() namespaces and tested directly."""
    src = _DATA_PY_PATH.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_fetch_iv_streaming":
            lines = src.splitlines(keepends=True)
            func_src = "".join(lines[node.lineno - 1: node.end_lineno])
            ns = {"math": math}
            exec(compile(func_src, "<_fetch_iv_streaming>", "exec"), ns)
            return ns["_fetch_iv_streaming"]
    raise AssertionError("_fetch_iv_streaming not found in data.py")


# ── T1: Profile A uses streaming helper (updated from snapshot assertion) ─────

def test_profile_a_iv_fetch_uses_streaming_helper():
    """Post-SUB-1: Profile A branch must issue ONE direct reqMktData call
    (primary price/volume, genericTickList='', snapshot=False) and delegate
    IV fetching to _fetch_iv_streaming (not a direct ib.reqMktData with '106').
    """
    _, tree = _load_data_py_ast()
    fn = _find_fetch_and_compute(tree)
    profile_a = _find_profile_a_block(fn)

    # Only ONE direct ib.reqMktData call remains (the primary)
    calls = _find_reqmktdata_calls(profile_a)
    assert len(calls) == 1, (
        f"Expected exactly 1 direct reqMktData call in Profile A branch (primary only), "
        f"found {len(calls)}. IV should be delegated to _fetch_iv_streaming."
    )

    # Primary call shape: contract, '', False, False
    c1 = calls[0]
    assert len(c1.args) >= 3, f"primary reqMktData has too few positional args: {len(c1.args)}"
    assert _const(c1.args[1]) == "", (
        f"primary reqMktData 2nd arg (genericTickList) must be '' (no tick 106), "
        f"got {_const(c1.args[1])!r}"
    )
    assert _const(c1.args[2]) is False, (
        f"primary reqMktData 3rd arg (snapshot) must be False (streaming), "
        f"got {_const(c1.args[2])!r}"
    )

    # Profile A body must call _fetch_iv_streaming
    assert _branch_contains_helper_call(profile_a.body), (
        "Profile A branch must call _fetch_iv_streaming for IV fetch"
    )


# ── T2: narrow assertion — primary call has no tick 106 ──────────────────────

def test_profile_a_primary_call_has_no_tick_106():
    """Narrower assertion: the first reqMktData call's genericTickList argument
    does not contain '106'. Independent from T1."""
    _, tree = _load_data_py_ast()
    fn = _find_fetch_and_compute(tree)
    profile_a = _find_profile_a_block(fn)
    calls = _find_reqmktdata_calls(profile_a)

    assert len(calls) >= 1, "no reqMktData calls found in Profile A branch"
    primary = calls[0]
    generic_tick_list = _const(primary.args[1])
    assert "106" not in generic_tick_list, (
        f"primary reqMktData genericTickList must not contain '106', got {generic_tick_list!r}"
    )


# ── exec()-based runtime harness for T3/T4 ───────────────────────────────────

def _extract_profile_a_block_source() -> str:
    """Return the source text of the `if p_code == "A":` branch body as a
    standalone statement block (dedented, with the `if ...:` header replaced
    by the body at the same indentation level)."""
    src, tree = _load_data_py_ast()
    fn = _find_fetch_and_compute(tree)
    profile_a = _find_profile_a_block(fn)

    # The branch's True-body covers from the first body stmt's lineno through
    # (but not including) the `else:` branch's first stmt lineno.
    body_start_line = profile_a.body[0].lineno
    # end_lineno of last body stmt covers the full body
    body_end_line = profile_a.body[-1].end_lineno

    lines = src.splitlines(keepends=True)
    # slice inclusive
    block_lines = lines[body_start_line - 1: body_end_line]
    block_text = "".join(block_lines)

    # The body is indented at the branch's body level. Find leading indent and
    # strip it uniformly so the block can exec() at module scope.
    # First non-empty line determines indent.
    first_line = next((ln for ln in block_lines if ln.strip()), "")
    leading = len(first_line) - len(first_line.lstrip(" "))
    if leading == 0:
        return block_text

    dedented = []
    for ln in block_lines:
        if ln.strip() == "":
            dedented.append(ln)
        else:
            # Strip up to `leading` spaces
            dedented.append(ln[leading:] if ln.startswith(" " * leading) else ln)
    return "".join(dedented)


def _make_exec_namespace(ib_mock, *, price_scaler=1.0, tz_name="America/New_York"):
    """Build a namespace with every name the Profile A block reads, then
    return it. Callers can inspect post-exec state via the returned dict."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    # df_ctx is read only by the post-PE-42 fallback block; stub as None so
    # the daily-close fallback path is the one taken when live_price is nan.
    ns = {
        "ib": ib_mock,
        "contract": SimpleNamespace(),  # opaque
        "p_code": "A",
        "math": math,
        "datetime": datetime,
        "timedelta": timedelta,
        "ZoneInfo": ZoneInfo,
        "tz_name": tz_name,
        "price_scaler": price_scaler,
        "df_ctx": None,
        # pre-block initialisations (mirrors data.py lines 766-769)
        "live_price": float("nan"),
        "snapshot_time_str": None,
        "price_source": "BAR",
        "_iv_raw_from_mktdata": None,
        # IVR-001-BUG-4-SUB-1: inject the helper function
        "_fetch_iv_streaming": _load_fetch_iv_streaming_func(),
    }
    return ns


def _exec_profile_a_block(ib_mock, *, price_scaler=1.0, tz_name="America/New_York"):
    """Exec the extracted Profile A block against the supplied mock. Returns
    the post-exec namespace for assertion."""
    ns = _make_exec_namespace(ib_mock, price_scaler=price_scaler, tz_name=tz_name)
    block_src = _extract_profile_a_block_source()
    exec(compile(block_src, "<profile_a_block>", "exec"), ns, ns)
    return ns


def _make_primary_ticker(*, market_price=150.0, volume=1_234_567.0, iv=None):
    """Build a MagicMock simulating a primary ticker_obj returned by
    reqMktData(..., '', False, False). marketPrice() is callable; `volume`
    and `impliedVolatility` are attributes."""
    t = MagicMock(name="primary_ticker")
    t.marketPrice.return_value = market_price
    t.volume = volume
    # impliedVolatility should NOT be read from the primary ticker post-fix,
    # but we set it so we can detect if the code accidentally reads from it.
    t.impliedVolatility = iv
    return t


def _make_iv_ticker(*, iv=0.4275):
    """Build a MagicMock simulating an IV ticker returned by
    reqMktData(..., '106', False, False). Only impliedVolatility matters."""
    t = MagicMock(name="iv_ticker")
    t.impliedVolatility = iv
    return t


class _IBMock:
    """Thin helper around MagicMock(). Records reqMktData calls in order.
    `reqMktData_side_effect` is a list of return-values-or-exceptions applied
    per call."""

    def __init__(self, reqmktdata_sequence):
        self.reqmktdata_sequence = list(reqmktdata_sequence)
        self._call_index = 0
        self.reqMktData_calls = []  # list of (args, kwargs)
        self.cancelMktData_calls = []

    def reqMktData(self, *args, **kwargs):
        self.reqMktData_calls.append((args, kwargs))
        if self._call_index >= len(self.reqmktdata_sequence):
            raise AssertionError(
                f"reqMktData called more than expected ({len(self.reqmktdata_sequence)} times)"
            )
        result = self.reqmktdata_sequence[self._call_index]
        self._call_index += 1
        if isinstance(result, BaseException):
            raise result
        return result

    def cancelMktData(self, *args, **kwargs):
        self.cancelMktData_calls.append((args, kwargs))

    def sleep(self, _):
        pass


# ── T3: IV exception does not affect price/volume ────────────────────────────

def test_profile_a_iv_exception_does_not_affect_price():
    """The IV fetch (via _fetch_iv_streaming) is the SECOND reqMktData call.
    If it raises, Live_Price (from the first call's marketPrice()) and
    Session_Volume (from the first call's volume attribute) must still be
    populated. _iv_raw_from_mktdata ends as None."""
    primary = _make_primary_ticker(market_price=150.25, volume=1_500_000.0, iv=99.9)
    # Second call (inside _fetch_iv_streaming) raises
    ib = _IBMock([primary, RuntimeError("IBKR tick 106 timeout")])

    ns = _exec_profile_a_block(ib, price_scaler=1.0)

    # Two reqMktData calls were attempted (primary + helper)
    assert len(ib.reqMktData_calls) == 2, (
        f"expected 2 reqMktData calls, got {len(ib.reqMktData_calls)}"
    )
    # First call shape: (contract, '', False, False)
    args1, _ = ib.reqMktData_calls[0]
    assert args1[1] == "" and args1[2] is False, (
        f"first reqMktData must be ('', False), got ({args1[1]!r}, {args1[2]!r})"
    )
    # Second call shape: (contract, '106', False, False) — streaming, not snapshot
    args2, _ = ib.reqMktData_calls[1]
    assert args2[1] == "106" and args2[2] is False, (
        f"second reqMktData must be ('106', False), got ({args2[1]!r}, {args2[2]!r})"
    )

    # Live_Price populated (from primary marketPrice / scaler = 150.25)
    assert ns["live_price"] == pytest.approx(150.25), (
        f"live_price must populate from primary marketPrice(), got {ns['live_price']!r}"
    )
    # price_source is LIVE (populated from live call, not daily fallback)
    assert ns["price_source"] == "LIVE", (
        f"price_source must be LIVE when primary call succeeded, got {ns['price_source']!r}"
    )
    # Session_Volume populated (primary volume was 1_500_000)
    assert ns["_session_vol"] == 1_500_000, (
        f"_session_vol must populate from primary volume attr, got {ns['_session_vol']!r}"
    )
    # IV ends as None (helper caught the exception and returned None)
    assert ns["_iv_raw_from_mktdata"] is None, (
        f"_iv_raw_from_mktdata must be None when IV fetch raised, "
        f"got {ns['_iv_raw_from_mktdata']!r}"
    )


# ── T4: primary exception does not block IV fetch ────────────────────────────

def test_profile_a_primary_exception_does_not_block_iv_fetch():
    """If the first reqMktData raises, the IV fetch via _fetch_iv_streaming
    must still execute (it is called after the primary try/except). This is
    what makes IV fetch reliable after hours — price fetch failure is non-fatal
    for IV."""
    iv_ticker = _make_iv_ticker(iv=0.5125)
    ib = _IBMock([ConnectionError("primary stream failed"), iv_ticker])

    ns = _exec_profile_a_block(ib, price_scaler=1.0)

    # Both reqMktData calls were attempted
    assert len(ib.reqMktData_calls) == 2, (
        f"IV fetch must run even after primary raise; got "
        f"{len(ib.reqMktData_calls)} call(s)"
    )
    # Verify the second call was the IV one (streaming mode)
    args2, _ = ib.reqMktData_calls[1]
    assert args2[1] == "106" and args2[2] is False, (
        f"second call must be the IV streaming ('106', False), got "
        f"({args2[1]!r}, {args2[2]!r})"
    )

    # live_price failed over to nan (primary exception path)
    # After df_ctx=None fallback, price_source should be UNAVAILABLE.
    assert math.isnan(ns["live_price"]), (
        f"live_price must be nan after primary exception + no df_ctx fallback, "
        f"got {ns['live_price']!r}"
    )
    assert ns["price_source"] == "UNAVAILABLE", (
        f"price_source must be UNAVAILABLE, got {ns['price_source']!r}"
    )
    # But IV was still fetched via helper
    assert ns["_iv_raw_from_mktdata"] == pytest.approx(0.5125), (
        f"_iv_raw_from_mktdata must be populated by IV streaming helper, "
        f"got {ns['_iv_raw_from_mktdata']!r}"
    )


# ── T5: UNAVAILABLE desc contains tick 106 cause ─────────────────────────────

def test_ivr_unavailable_desc_includes_tick_106_cause():
    """gates.py _IVR_REGIME_DESC["UNAVAILABLE"] must mention 'IBKR tick 106
    not populated' as a possible cause — so the Operator isn't misled into
    thinking an after-hours liquid-chain ticker is non-optionable."""
    from tbs_engine.gates import _IVR_REGIME_DESC

    desc = _IVR_REGIME_DESC["UNAVAILABLE"]
    assert "IBKR tick 106 not populated" in desc, (
        f"UNAVAILABLE desc must include 'IBKR tick 106 not populated' as a "
        f"cause. Got: {desc!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# IVR-001-BUG-4-SUB-1: New tests T6–T12
# ══════════════════════════════════════════════════════════════════════════════


# ── Helper mock for direct _fetch_iv_streaming tests (T7-T11) ────────────────

class _IVHelperMock:
    """Minimal ib mock for testing _fetch_iv_streaming directly.

    `iv_schedule` maps sleep-call index to the impliedVolatility value
    that the ticker should have AFTER that sleep completes.
    Index 0 = after initial sleep, index 1 = after 1st poll sleep, etc.
    Values not in the schedule leave impliedVolatility unchanged from its
    initial value (None by default).
    """

    def __init__(self, *, iv_schedule=None, reqmktdata_raises=None):
        self.iv_schedule = iv_schedule or {}
        self.reqmktdata_raises = reqmktdata_raises
        self._ticker = SimpleNamespace(impliedVolatility=None)
        self._sleep_count = 0
        self.cancel_called = False
        self.reqMktData_calls = []

    def reqMktData(self, *args, **kwargs):
        self.reqMktData_calls.append((args, kwargs))
        if self.reqmktdata_raises:
            raise self.reqmktdata_raises
        return self._ticker

    def sleep(self, seconds):
        # After each sleep, update IV if schedule has an entry for this index
        idx = self._sleep_count
        self._sleep_count += 1
        if idx in self.iv_schedule:
            self._ticker.impliedVolatility = self.iv_schedule[idx]

    def cancelMktData(self, *args, **kwargs):
        self.cancel_called = True


# ── T6: helper uses streaming mode (AST) ─────────────────────────────────────

def test_iv_helper_uses_streaming_mode():
    """_fetch_iv_streaming must call reqMktData with 3rd positional arg False
    (streaming, not snapshot). Verified via AST inspection."""
    _, tree = _load_data_py_ast()
    fn = _find_fetch_iv_streaming(tree)

    # Find the reqMktData call inside the helper
    calls = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr == "reqMktData"):
            calls.append(node)

    assert len(calls) == 1, (
        f"Expected exactly 1 reqMktData call in _fetch_iv_streaming, found {len(calls)}"
    )
    call = calls[0]
    # 3rd positional arg (index 2) must be False (snapshot=False)
    assert len(call.args) >= 3, f"reqMktData has too few args: {len(call.args)}"
    snapshot_arg = call.args[2]
    assert isinstance(snapshot_arg, ast.Constant) and snapshot_arg.value is False, (
        f"reqMktData 3rd arg (snapshot) must be False, got {ast.dump(snapshot_arg)}"
    )


# ── T7: early exit on initial sleep ──────────────────────────────────────────

def test_iv_helper_early_exit_on_initial_sleep():
    """If IV is populated after the initial sleep (before any polling),
    the helper returns immediately without entering the poll loop."""
    _fetch_iv = _load_fetch_iv_streaming_func()
    contract = SimpleNamespace()

    # IV populated at sleep index 0 (initial sleep)
    ib = _IVHelperMock(iv_schedule={0: 0.35})
    result = _fetch_iv(ib, contract)

    assert result == pytest.approx(0.35), (
        f"Helper should return IV on initial sleep, got {result!r}"
    )
    assert ib.cancel_called, "cancelMktData must be called after successful fetch"
    # Only 1 sleep call (the initial_sleep) — no polls needed
    assert ib._sleep_count == 1, (
        f"Expected 1 sleep (initial only, no polls), got {ib._sleep_count}"
    )


# ── T8: poll loop finds IV ───────────────────────────────────────────────────

def test_iv_helper_poll_loop_finds_iv():
    """IV not populated on initial check → poll loop finds it on 2nd poll.
    Total sleeps: 1 (initial) + 2 (polls) = 3."""
    _fetch_iv = _load_fetch_iv_streaming_func()
    contract = SimpleNamespace()

    # Initial sleep (idx 0) → None; poll 1 (idx 1) → None; poll 2 (idx 2) → 0.42
    ib = _IVHelperMock(iv_schedule={2: 0.42})
    result = _fetch_iv(ib, contract)

    assert result == pytest.approx(0.42), (
        f"Helper should return IV found on 2nd poll, got {result!r}"
    )
    assert ib.cancel_called, "cancelMktData must be called"
    # 1 initial sleep + 2 poll sleeps = 3 total
    assert ib._sleep_count == 3, (
        f"Expected 3 sleeps (initial + 2 polls), got {ib._sleep_count}"
    )


# ── T9: timeout returns None ─────────────────────────────────────────────────

def test_iv_helper_timeout_returns_none():
    """IV never populated → helper exhausts full budget and returns None.
    Total sleeps: 1 (initial) + 4 (max_polls) = 5."""
    _fetch_iv = _load_fetch_iv_streaming_func()
    contract = SimpleNamespace()

    # No IV ever set
    ib = _IVHelperMock(iv_schedule={})
    result = _fetch_iv(ib, contract)

    assert result is None, f"Helper should return None on timeout, got {result!r}"
    assert ib.cancel_called, "cancelMktData must be called even on timeout"
    # 1 initial sleep + 4 poll sleeps = 5 total
    assert ib._sleep_count == 5, (
        f"Expected 5 sleeps (initial + 4 polls), got {ib._sleep_count}"
    )


# ── T10: NaN treated as missing ──────────────────────────────────────────────

def test_iv_helper_nan_treated_as_missing():
    """If impliedVolatility is float('nan'), it should be treated as
    not-populated and the poll loop should continue."""
    _fetch_iv = _load_fetch_iv_streaming_func()
    contract = SimpleNamespace()

    # Initial sleep (idx 0) → NaN; poll 1 (idx 1) → NaN; poll 2 (idx 2) → 0.28
    ib = _IVHelperMock(iv_schedule={0: float('nan'), 1: float('nan'), 2: 0.28})
    result = _fetch_iv(ib, contract)

    assert result == pytest.approx(0.28), (
        f"NaN should be treated as missing; helper should find 0.28 on poll 2, got {result!r}"
    )


# ── T11: exception cancels and returns None ──────────────────────────────────

def test_iv_helper_exception_cancels_and_returns_none():
    """If reqMktData raises, the helper must still call cancelMktData
    (exception safety) and return None."""
    _fetch_iv = _load_fetch_iv_streaming_func()
    contract = SimpleNamespace()

    ib = _IVHelperMock(reqmktdata_raises=RuntimeError("IBKR timeout"))
    result = _fetch_iv(ib, contract)

    assert result is None, f"Helper should return None on exception, got {result!r}"
    assert ib.cancel_called, "cancelMktData must be called even when reqMktData raises"


# ── T12: Profile B/C uses streaming helper (AST) ─────────────────────────────

def test_profile_b_c_uses_streaming_helper():
    """The else-branch (Profile B/C) of the `if p_code == "A":` block must
    call _fetch_iv_streaming — not the old snapshot reqMktData pattern."""
    _, tree = _load_data_py_ast()
    fn = _find_fetch_and_compute(tree)
    profile_a = _find_profile_a_block(fn)

    # The else-branch is profile_a.orelse
    assert profile_a.orelse, (
        "Profile A block must have an else branch (Profile B/C)"
    )

    # else branch must call _fetch_iv_streaming
    assert _branch_contains_helper_call(profile_a.orelse), (
        "Profile B/C else-branch must call _fetch_iv_streaming for IV fetch"
    )

    # else branch must NOT contain any direct ib.reqMktData calls
    direct_calls = []
    for stmt in profile_a.orelse:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "reqMktData"
                    and isinstance(f.value, ast.Name) and f.value.id == "ib"):
                direct_calls.append(node)
    assert len(direct_calls) == 0, (
        f"Profile B/C else-branch should NOT have direct ib.reqMktData calls "
        f"(found {len(direct_calls)}). IV must use _fetch_iv_streaming helper."
    )

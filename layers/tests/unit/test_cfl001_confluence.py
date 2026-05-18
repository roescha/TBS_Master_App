"""CFL-001 -- Floor and Target Level Confluence Detection -- unit tests.

Spec: CFL001_Level_Confluence_Detection_Spec_v1_0.md (v1.0, S157)

Covers the 7 test classes enumerated in spec §6.1:

     1. TestCFL001ClusterDetection      (10) -- core greedy clustering algorithm
     2. TestCFL001ThresholdScaling       (3) -- DQ-1: floor (0.25x) vs target (0.5x)
     3. TestCFL001DescGeneration         (9) -- DQ-6: side-aware strength-aware desc
     4. TestCFL001DefensiveBehaviour     (6) -- DQ-5: empty / null ATR / null price
     5. TestCFL001NotInGatesFile         (1) -- SIR §11.2 negative assertion
     6. TestCFL001NotAFlatKey            (2) -- output contract: no new flat key
     7. TestCFL001SortDeterminism        (2) -- DQ-4: caller's sort order preserved

Construction notes:
    - Helper-only unit tests. No engine end-to-end run; no flat_metrics
      construction. _detect_level_confluence is called directly with
      synthetic entry lists and ATR values.
    - Safe spec_from_file_location dynamic-module-load pattern per
      TEST-HRN-001 (no sys.modules[name] = mod registration).
    - Implementation deviation note (vs spec §3.2): helper sorts a
      defensive local copy ascending before the greedy walk and skips
      None-priced entries entirely (instead of "null breaks chain").
      Caller's list order on the entries argument is untouched. See
      CFL001_Implementation_HandBack_v1_0.md §5 for the rationale.
      One test (`test_null_price_in_middle_does_not_crash_and_clusters_valid_pair`)
      is renamed and re-asserted vs the spec table to reflect this.
"""

import ast
import os
import sys
import inspect
import importlib.util


# ---------------------------------------------------------------------------
# Path setup -- repository root + safe dynamic module load (TEST-HRN-001)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(__file__)
_LAYERS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_TRANSFORM_PY_PATH = os.path.join(_LAYERS_ROOT, "tbs_engine", "transform.py")
_GATES_PY_PATH = os.path.join(_LAYERS_ROOT, "tbs_engine", "gates.py")

# Ensure `layers/` is on sys.path so any package-import inside loaded modules
# (e.g. gates.py -> tbs_engine.helpers) resolves. pytest.ini already adds
# this, but be explicit so direct invocation also works.
if _LAYERS_ROOT not in sys.path:
    sys.path.insert(0, _LAYERS_ROOT)


def _load_module_safe(name, path):
    """TEST-HRN-001 safe dynamic loader: spec_from_file_location WITHOUT
    sys.modules[name] = mod registration. Returns the module object."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_transform = _load_module_safe("_cfl001_transform_under_test", _TRANSFORM_PY_PATH)
_gates = _load_module_safe("_cfl001_gates_under_test", _GATES_PY_PATH)

_detect_level_confluence = _transform._detect_level_confluence
_CFL_FLOOR_THRESHOLD_ATR_MULT = _transform._CFL_FLOOR_THRESHOLD_ATR_MULT
_CFL_TARGET_THRESHOLD_ATR_MULT = _transform._CFL_TARGET_THRESHOLD_ATR_MULT
_CFL_STRENGTH_DESC_MAP = _transform._CFL_STRENGTH_DESC_MAP
_CFL_BOUNDARY_TOLERANCE = _transform._CFL_BOUNDARY_TOLERANCE
MAPPED_FLAT_KEYS = _transform.MAPPED_FLAT_KEYS


def _entry(price, label, **extras):
    """Build a minimal hierarchy entry dict with the two fields the helper
    reads (price + label) plus any caller-supplied extras."""
    e = {"price": price, "label": label}
    e.update(extras)
    return e


# ===========================================================================
# 1. TestCFL001ClusterDetection (10 tests) -- core algorithm
# ===========================================================================

class TestCFL001ClusterDetection:
    """Spec §3.2 + §6.1: greedy adjacent clustering produces correct
    cluster identity, member_count, and strength bands."""

    ATR = 10.0  # threshold = 0.5 * 10 = 5.0 (target side default in these tests)

    def test_single_entry_no_confluence(self):
        entries = [_entry(100.0, "DAILY_HIGH")]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]

    def test_two_entries_within_threshold_moderate(self):
        # gap = 2.5 = 0.5 * threshold (threshold = 5.0)
        entries = [_entry(100.0, "DAILY_HIGH"), _entry(102.5, "MEASURED_MOVE")]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" in entries[0]
        assert "confluence" in entries[1]
        assert entries[0]["confluence"]["strength"] == "MODERATE"
        assert entries[0]["confluence"]["id"] == 1
        assert entries[0]["confluence"]["member_count"] == 2

    def test_three_entries_within_threshold_strong(self):
        # adjacent gaps each = 2.5
        entries = [
            _entry(100.0, "DAILY_HIGH"),
            _entry(102.5, "MEASURED_MOVE"),
            _entry(105.0, "ANALYST_CONSENSUS"),
        ]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        for e in entries:
            assert "confluence" in e
            assert e["confluence"]["strength"] == "STRONG"
            assert e["confluence"]["member_count"] == 3

    def test_four_entries_within_threshold_exceptional(self):
        entries = [
            _entry(100.0, "A"), _entry(102.5, "B"),
            _entry(105.0, "C"), _entry(107.5, "D"),
        ]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        for e in entries:
            assert e["confluence"]["strength"] == "EXCEPTIONAL"
            assert e["confluence"]["member_count"] == 4

    def test_five_entries_exceptional_label_correct(self):
        entries = [_entry(100.0 + i * 2.5, f"L{i}") for i in range(5)]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        for e in entries:
            assert e["confluence"]["strength"] == "EXCEPTIONAL"
            assert e["confluence"]["member_count"] == 5

    def test_two_entries_beyond_threshold_no_cluster(self):
        # gap = 6.0 > threshold (5.0)
        entries = [_entry(100.0, "A"), _entry(106.0, "B")]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]

    def test_transitive_clustering(self):
        # threshold = 1.0 (atr=2, mult=0.5)
        # A=100, B=100.5, C=101.5: A-B=0.5<=1.0, B-C=1.0<=1.0, A-C=1.5>1.0
        # Transitive: all three share one cluster.
        entries = [_entry(100.0, "A"), _entry(100.5, "B"), _entry(101.5, "C")]
        _detect_level_confluence(entries, 2.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        cid = entries[0]["confluence"]["id"]
        for e in entries:
            assert e["confluence"]["id"] == cid
            assert e["confluence"]["member_count"] == 3

    def test_two_separate_clusters(self):
        # {100, 100.3} + {110.0, 110.3}, threshold = 5.0
        entries = [
            _entry(100.0, "A"), _entry(100.3, "B"),
            _entry(110.0, "C"), _entry(110.3, "D"),
        ]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        ids = sorted({e["confluence"]["id"] for e in entries})
        assert ids == [1, 2]
        # Each cluster has 2 members
        for e in entries:
            assert e["confluence"]["member_count"] == 2

    def test_cluster_after_isolated_entry(self):
        # {100 isolated, 105, 105.3} with threshold = 1.0 (atr=2, mult=0.5)
        # 100 stands alone (gap to 105 = 5 > 1.0); 105+105.3 cluster.
        entries = [_entry(100.0, "ISO"), _entry(105.0, "A"), _entry(105.3, "B")]
        _detect_level_confluence(entries, 2.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert entries[1]["confluence"]["id"] == 1
        assert entries[2]["confluence"]["id"] == 1
        assert entries[1]["confluence"]["member_count"] == 2

    def test_shared_object_reference(self):
        # All members of a cluster receive the SAME dict reference per §3.4
        entries = [_entry(100.0, "A"), _entry(102.5, "B"), _entry(105.0, "C")]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        ref = entries[0]["confluence"]
        assert entries[1]["confluence"] is ref
        assert entries[2]["confluence"] is ref


# ===========================================================================
# 2. TestCFL001ThresholdScaling (3 tests) -- DQ-1
# ===========================================================================

class TestCFL001ThresholdScaling:
    """Spec §3.1 + DQ-1: floor 0.25x / target 0.5x; floor is tighter."""

    def test_floor_threshold_constant_value(self):
        assert _CFL_FLOOR_THRESHOLD_ATR_MULT == 0.25

    def test_target_threshold_constant_value(self):
        assert _CFL_TARGET_THRESHOLD_ATR_MULT == 0.5

    def test_floor_call_uses_tighter_threshold(self):
        # Spread = 0.4 * ATR. ATR=10 -> spread=4.0.
        # Floor threshold = 0.25*10 = 2.5 -> 4.0 > 2.5 -> NO cluster.
        # Target threshold = 0.5*10 = 5.0 -> 4.0 <= 5.0 -> cluster.
        floor_entries = [_entry(100.0, "A"), _entry(104.0, "B")]
        _detect_level_confluence(
            floor_entries, 10.0, _CFL_FLOOR_THRESHOLD_ATR_MULT, "floor",
        )
        assert "confluence" not in floor_entries[0]
        assert "confluence" not in floor_entries[1]

        target_entries = [_entry(100.0, "A"), _entry(104.0, "B")]
        _detect_level_confluence(
            target_entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target",
        )
        assert target_entries[0]["confluence"]["strength"] == "MODERATE"
        assert target_entries[1]["confluence"]["strength"] == "MODERATE"


# ===========================================================================
# 3. TestCFL001DescGeneration (9 tests) -- DQ-6
# ===========================================================================

class TestCFL001DescGeneration:
    """Spec §3.1 + §5.2 + DQ-6: side-aware strength-aware desc strings;
    timing-neutral per SIR §10."""

    ATR = 10.0  # target threshold = 5.0; floor threshold = 2.5

    def _floor_cluster(self, n):
        # Adjacent gaps each 1.0 ATR fraction -> well within floor 0.25x = 2.5 abs
        entries = [_entry(100.0 + i * 1.0, f"F{i}") for i in range(n)]
        _detect_level_confluence(entries, self.ATR, _CFL_FLOOR_THRESHOLD_ATR_MULT, "floor")
        return entries

    def _target_cluster(self, n):
        # Adjacent gaps each 2.0 -> within target 0.5x = 5.0 abs
        entries = [_entry(200.0 + i * 2.0, f"T{i}") for i in range(n)]
        _detect_level_confluence(entries, self.ATR, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        return entries

    def test_floor_moderate_desc_substring(self):
        e = self._floor_cluster(2)
        d = e[0]["confluence"]["desc"]
        assert "MODERATE support cluster" in d
        assert "anchors within" in d
        assert "ATR of $" in d

    def test_floor_strong_desc_substring(self):
        e = self._floor_cluster(3)
        d = e[0]["confluence"]["desc"]
        assert "STRONG support cluster" in d
        assert "institutional-grade convergence" in d

    def test_floor_exceptional_desc_substring(self):
        e = self._floor_cluster(4)
        d = e[0]["confluence"]["desc"]
        assert "EXCEPTIONAL support cluster" in d
        assert "rare multi-anchor convergence" in d

    def test_target_moderate_desc_substring(self):
        e = self._target_cluster(2)
        d = e[0]["confluence"]["desc"]
        assert "MODERATE resistance cluster" in d

    def test_target_strong_desc_substring(self):
        e = self._target_cluster(3)
        d = e[0]["confluence"]["desc"]
        assert "STRONG resistance cluster" in d
        assert "institutional-grade convergence" in d

    def test_target_exceptional_desc_substring(self):
        e = self._target_cluster(4)
        d = e[0]["confluence"]["desc"]
        assert "EXCEPTIONAL resistance cluster" in d
        assert "rare multi-anchor convergence" in d

    def test_desc_includes_computed_spread_atr(self):
        # ATR=10. Cluster {100.0, 102.0}: spread=2.0; spread_atr = 0.2
        entries = [_entry(100.0, "A"), _entry(102.0, "B")]
        _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "0.2 ATR" in entries[0]["confluence"]["desc"]

    def test_desc_includes_anchor_price_mean(self):
        # Mean of {100.0, 102.5, 105.0} = 102.5
        entries = [_entry(100.0, "A"), _entry(102.5, "B"), _entry(105.0, "C")]
        _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "$102.5" in entries[0]["confluence"]["desc"]

    def test_desc_no_first_test_language(self):
        # SIR §10: no temporal-prediction phrases. Check every desc template.
        forbidden = ("first test", "will test", "will hold", "should hold",
                     "expect", "next test", "soon", "imminent")
        for (_side, _strength), tmpl in _CFL_STRENGTH_DESC_MAP.items():
            lower = tmpl.lower()
            for phrase in forbidden:
                assert phrase not in lower, (
                    f"CFL-001 desc template {(_side, _strength)} contains "
                    f"forbidden timing-language phrase: {phrase!r}"
                )


# ===========================================================================
# 4. TestCFL001DefensiveBehaviour (6 tests) -- DQ-5 and edge cases
# ===========================================================================

class TestCFL001DefensiveBehaviour:
    """Spec §3.2 docstring + DQ-5: no-op on degenerate inputs."""

    def test_empty_entries_no_op(self):
        entries = []
        result = _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert result is entries
        assert entries == []

    def test_atr_none_no_op(self):
        entries = [_entry(100.0, "A"), _entry(100.1, "B")]
        _detect_level_confluence(entries, None, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]

    def test_atr_zero_no_op(self):
        entries = [_entry(100.0, "A"), _entry(100.1, "B")]
        _detect_level_confluence(entries, 0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]

    def test_atr_negative_no_op(self):
        entries = [_entry(100.0, "A"), _entry(100.1, "B")]
        _detect_level_confluence(entries, -5, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]

    def test_null_price_in_middle_does_not_crash_and_clusters_valid_pair(self):
        """Spec table test renamed: with the sort-local-copy implementation
        (hand-back §5), None-priced entries are excluded from the greedy
        walk entirely. The remaining valid pair clusters normally.

        Original spec expectation (null breaks chain -> no cluster) is a
        documented deviation. Defensive intent is preserved: no crash, no
        spurious annotation on the None entry."""
        entries = [_entry(100.0, "A"), _entry(None, "BAD"), _entry(100.1, "C")]
        _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        # No crash, no annotation on the null entry, valid pair clusters.
        assert "confluence" not in entries[1]
        assert "confluence" in entries[0]
        assert "confluence" in entries[2]
        assert entries[0]["confluence"]["member_count"] == 2

    def test_null_price_in_otherwise_clusterable_pair(self):
        entries = [_entry(None, "BAD"), _entry(100.0, "A")]
        _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]


# ===========================================================================
# 4b. TestCFL001BoundaryTolerance (3 tests) -- post-v1.0 epsilon fix
#     Surfaced by the CRWD-A live-cohort run: gap displayed as 2.01 vs
#     threshold displayed as 2.01, but the underlying floats diverged by
#     ~1e-13, causing the inclusive `<=` to silently NOT cluster. The
#     `_CFL_BOUNDARY_TOLERANCE` constant absorbs that noise without
#     widening the threshold at any operator-meaningful scale.
# ===========================================================================

class TestCFL001BoundaryTolerance:
    """Post-spec-v1.0 boundary-inclusivity behaviour. See the
    _CFL_BOUNDARY_TOLERANCE constant's commentary in transform.py."""

    def test_tolerance_constant_is_small_enough_to_be_invisible_at_penny_scale(self):
        # Tolerance must be << penny ($0.01). Anything <= 1e-6 is safe.
        assert _CFL_BOUNDARY_TOLERANCE > 0
        assert _CFL_BOUNDARY_TOLERANCE < 1e-6

    def test_crwd_a_float_near_miss_now_clusters(self):
        """Reproduces the CRWD-A live finding exactly: ATR=8.04, two
        entries displayed as 558.68 and 560.69 (gap visually equals
        threshold 0.25*8.04=2.01). Pre-fix: no cluster (float diff
        ~1e-13 over threshold). Post-fix: cluster forms."""
        atr = 8.04
        entries = [_entry(558.68, "HARD_STOP"), _entry(560.69, "ESTABLISHED_LOW")]
        # Sanity: the raw comparison without tolerance would have failed.
        raw_diff = abs(560.69 - 558.68)
        raw_threshold = 0.25 * atr
        assert raw_diff > raw_threshold  # confirms the float-precision near-miss
        assert (raw_diff - raw_threshold) < _CFL_BOUNDARY_TOLERANCE  # within tolerance

        _detect_level_confluence(entries, atr, _CFL_FLOOR_THRESHOLD_ATR_MULT, "floor")
        assert "confluence" in entries[0]
        assert "confluence" in entries[1]
        assert entries[0]["confluence"]["strength"] == "MODERATE"
        assert entries[0]["confluence"]["member_count"] == 2

    def test_tolerance_does_not_cluster_beyond_meaningful_gap(self):
        """A gap that is 100x the tolerance ($1e-7) must NOT cause a
        false-positive cluster. Guards against accidentally widening the
        tolerance to a price-meaningful magnitude."""
        atr = 10.0
        threshold = _CFL_TARGET_THRESHOLD_ATR_MULT * atr  # = 5.0
        # Gap = threshold + 100 * tolerance (well beyond noise; still tiny)
        entries = [_entry(100.0, "A"), _entry(100.0 + threshold + 100 * _CFL_BOUNDARY_TOLERANCE, "B")]
        _detect_level_confluence(entries, atr, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        assert "confluence" not in entries[0]
        assert "confluence" not in entries[1]


# ===========================================================================
# 5. TestCFL001NotInGatesFile (1 test) -- SIR §11.2 negative assertion
# ===========================================================================

_GATE_FUNCTION_NAMES = [n for n in dir(_gates) if n.startswith("_gate_") and callable(getattr(_gates, n))]


class TestCFL001NotInGatesFile:
    """Spec §7 + §6.1: 'confluence' substring never appears in the body
    of any _gate_* function in gates.py. Mirrors TestWKC001NotInGatesFile
    precedent (file-text scan); the spec specifies inspect.getsource on
    each _gate_* function, used here."""

    def test_no_gate_function_references_confluence(self):
        # Sanity: gate function set is non-empty (avoids vacuous pass).
        assert _GATE_FUNCTION_NAMES, "No _gate_* functions discovered in gates.py"

        offenders = []
        for fn_name in _GATE_FUNCTION_NAMES:
            fn = getattr(_gates, fn_name)
            src = inspect.getsource(fn)
            if "confluence" in src.lower():
                offenders.append(fn_name)
        assert not offenders, (
            "CFL-001 invariant violated: 'confluence' found in gate function(s): "
            + ", ".join(offenders)
        )


# ===========================================================================
# 6. TestCFL001NotAFlatKey (2 tests) -- output contract
# ===========================================================================

class TestCFL001NotAFlatKey:
    """Spec §2.2 + §5.3 + §7: confluence is a nested sub-object only;
    never a flat-metrics key."""

    def test_no_new_flat_metrics_key(self):
        # AST-walk the helper body and assert no Subscript-Store on a
        # `flat_metrics` target exists. Substring grep would false-positive
        # on the docstring's `flat_metrics["ATR"]` reference. The intent
        # (spec §6.1) is "helper writes no flat_metrics key" — reads (in
        # the call sites, not the helper) are fine.
        src = inspect.getsource(_detect_level_confluence)
        tree = ast.parse(src)
        writes = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if (isinstance(t, ast.Subscript)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "flat_metrics"):
                        writes.append(ast.dump(node))
        assert writes == [], (
            "CFL-001 invariant violated: helper writes to flat_metrics: "
            f"{writes}"
        )
        # Helper writes exactly one new key on entry dicts:
        assert 'm["confluence"]' in src or "m['confluence']" in src

    def test_mapped_flat_keys_unchanged(self):
        # No CFL-001-specific entry registered in the flat-key registry.
        # Spec §2.2 / §5.3 / §7: confluence is nested-only, never flat.
        # Pre-existing keys with "confluence" in the name (e.g. ENG-003
        # Fib_Confluence, Fib_A_Confluence) are unrelated to CFL-001 and
        # are explicitly tolerated by this assertion.
        cfl_keys = {
            k for k in MAPPED_FLAT_KEYS
            if k.lower().startswith("cfl")
            or "level_confluence" in k.lower()
        }
        assert cfl_keys == set(), (
            "CFL-001 invariant violated: MAPPED_FLAT_KEYS contains CFL-001 "
            f"keys: {sorted(cfl_keys)}"
        )


# ===========================================================================
# 7. TestCFL001SortDeterminism (2 tests) -- DQ-4
# ===========================================================================

class TestCFL001SortDeterminism:
    """Spec §3.3 + DQ-4: invoking _detect_level_confluence does not
    mutate the caller's list order. Sort keys (price/label) are not
    modified by the helper."""

    def test_target_sort_order_unchanged_pre_post_cfl(self):
        entries = [
            _entry(100.0, "DAILY_HIGH"),
            _entry(102.5, "MEASURED_MOVE"),
            _entry(95.0, "ANALYST_CONSENSUS"),  # out-of-order on purpose
            _entry(110.0, "PSYCHOLOGICAL"),
        ]
        before = [(e["price"], e["label"]) for e in entries]
        _detect_level_confluence(entries, 10.0, _CFL_TARGET_THRESHOLD_ATR_MULT, "target")
        after = [(e["price"], e["label"]) for e in entries]
        assert before == after

    def test_floor_sort_order_unchanged_pre_post_cfl(self):
        entries = [
            _entry(95.0, "EMA_21"),
            _entry(94.8, "PSYCHOLOGICAL"),
            _entry(90.0, "TIGHT_STOP"),
            _entry(85.0, "CATASTROPHIC_STOP"),
        ]
        before = [(e["price"], e["label"]) for e in entries]
        _detect_level_confluence(entries, 10.0, _CFL_FLOOR_THRESHOLD_ATR_MULT, "floor")
        after = [(e["price"], e["label"]) for e in entries]
        assert before == after
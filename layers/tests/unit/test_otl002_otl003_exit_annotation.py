"""
SUPERSEDED by DIAG-001 Phase 2B.

_annotate_exit_signal has been removed from output.py.
OTL-002 (exit suffix) is replaced by action_summary.exit_warning on VALID paths.
OTL-003 (floor counter correction) is eliminated — mandate and context are
constructed cleanly from GateResult fields, not by post-hoc string surgery.

Replacement tests:
  - test_dd5_exit_warning.py (DD-5: exit_warning + fixed note)
  - test_dd2_exit_forces_invalid.py (DD-2: EXIT forces INVALID)
  - test_action_summary_valid.py (VALID path structure)
  - test_action_summary_invalid.py (INVALID path structure)
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="SUPERSEDED: _annotate_exit_signal removed in DIAG-001 Phase 2B. "
           "See test_dd5_exit_warning.py and test_dd2_exit_forces_invalid.py."
)


class TestOTL002ExitSuffix:
    def test_placeholder(self):
        pass


class TestOTL003FloorCounterCorrection:
    def test_placeholder(self):
        pass

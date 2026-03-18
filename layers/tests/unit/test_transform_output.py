"""
SUPERSEDED by DIAG-001 Phase 2B.

_transform_output signature changed from (status, diagnostic, flat_metrics)
to (action_summary, flat_metrics). status/diagnostic top-level keys removed.
entry_strategy removed from trade_snapshot (DD-3).

Replacement: test_transform_output_diag001.py
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="SUPERSEDED: _transform_output signature changed in DIAG-001 Phase 2B. "
           "See test_transform_output_diag001.py."
)


class TestPlaceholder:
    def test_placeholder(self):
        pass

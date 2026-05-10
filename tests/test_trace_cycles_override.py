"""Tests for trace_cycles override logic in SKILL.md Stage 3.

Verifies that the Python one-liner heredoc correctly resolves cycle count:
  1. constraints.verification.trace_cycles (explicit override)
  2. max(pipeline_delay_cycles) + 4 (derived from modules)
  3. 16 (fallback default)
"""

import json
import unittest
from pathlib import Path


def _resolve_cycles(spec: dict) -> int:
    """Mirror the logic from SKILL.md Stage 3 heredoc."""
    try:
        explicit = spec.get("constraints", {}).get("verification", {}).get("trace_cycles")
        if isinstance(explicit, int):
            return explicit
        delays = []
        for m in spec.get("modules", []):
            d = m.get("timing_contract", {}).get("pipeline_delay_cycles")
            if isinstance(d, (int, float)):
                delays.append(int(d))
        return max(delays) + 4 if delays else 16
    except Exception:
        return 16


class TestTraceCyclesOverride(unittest.TestCase):
    """Resolution priority: explicit > derived > default."""

    def test_explicit_override_used(self):
        spec = {
            "constraints": {
                "verification": {"trace_cycles": 32}
            },
            "modules": [
                {"timing_contract": {"pipeline_delay_cycles": 5}}
            ],
        }
        self.assertEqual(_resolve_cycles(spec), 32)

    def test_derived_when_no_explicit(self):
        spec = {
            "constraints": {},
            "modules": [
                {"timing_contract": {"pipeline_delay_cycles": 3}},
                {"timing_contract": {"pipeline_delay_cycles": 8}},
            ],
        }
        self.assertEqual(_resolve_cycles(spec), 12)  # 8 + 4

    def test_fallback_default(self):
        spec = {"constraints": {}, "modules": []}
        self.assertEqual(_resolve_cycles(spec), 16)

    def test_missing_constraints_verification(self):
        spec = {
            "modules": [
                {"timing_contract": {"pipeline_delay_cycles": 2}}
            ],
        }
        self.assertEqual(_resolve_cycles(spec), 6)  # 2 + 4

    def test_explicit_zero_allowed(self):
        """trace_cycles=0 is valid (e.g. combinational-only check)."""
        spec = {
            "constraints": {
                "verification": {"trace_cycles": 0}
            },
            "modules": [],
        }
        self.assertEqual(_resolve_cycles(spec), 0)

    def test_derived_ignores_non_numeric(self):
        """pipeline_delay_cycles="variable" should be skipped, not crash."""
        spec = {
            "constraints": {},
            "modules": [
                {"timing_contract": {"pipeline_delay_cycles": "variable"}},
                {"timing_contract": {"pipeline_delay_cycles": 5}},
            ],
        }
        self.assertEqual(_resolve_cycles(spec), 9)  # 5 + 4

    def test_no_modules_key(self):
        spec = {"constraints": {"verification": {}}}
        self.assertEqual(_resolve_cycles(spec), 16)


if __name__ == "__main__":
    unittest.main()

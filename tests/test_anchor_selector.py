"""Tests for anchor selector dynamic inference.

Verifies priority: explicit hints > auto-inference > generic fallback.
"""

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "claude_skills" / "vf-rtl" / "anchors"))

from _selector import select_anchors, _infer_features, ANCHORS_DIR


class TestSelectAnchorsPriority(unittest.TestCase):
    """Selection priority chain."""

    def test_explicit_hints_take_priority(self):
        spec = {
            "anchor_hints": ["fsm_4state", "shift_register"],
            "module_type": "processing",
            "ports": [],
            "cycle_timing": {},
        }
        result = select_anchors(spec)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "fsm_4state")
        self.assertEqual(result[1].name, "shift_register")

    def test_missing_hint_fallback_to_inference(self):
        """No hints + fsm_states present -> fsm_4state inferred."""
        spec = {
            "anchor_hints": [],
            "module_type": "control",
            "ports": [{"name": "clk", "direction": "input", "width": 1}],
            "cycle_timing": {
                "fsm_states": [
                    {"name": "IDLE"},
                    {"name": "RUN"},
                ]
            },
        }
        result = select_anchors(spec)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "fsm_4state")

    def test_generic_fallback_control(self):
        """No hints, no recognizable features, module_type=control -> fsm_4state."""
        spec = {
            "module_type": "control",
            "ports": [],
            "cycle_timing": {},
        }
        result = select_anchors(spec)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "fsm_4state")

    def test_generic_fallback_processing(self):
        """No hints, no recognizable features, module_type=processing -> pipeline_register."""
        spec = {
            "module_type": "processing",
            "ports": [],
            "cycle_timing": {},
        }
        result = select_anchors(spec)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "pipeline_register")

    def test_nonexistent_hint_ignored(self):
        """Invalid hint names are silently dropped, falling back to inference."""
        spec = {
            "anchor_hints": ["nonexistent_anchor"],
            "module_type": "control",
            "cycle_timing": {
                "fsm_states": [{"name": "A"}, {"name": "B"}]
            },
        }
        result = select_anchors(spec)
        # hint doesn't exist -> falls through to inference
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "fsm_4state")

    def test_max_two_anchors(self):
        """Never return more than 2 anchors."""
        spec = {
            "anchor_hints": ["fsm_4state", "shift_register", "pipeline_register"],
        }
        result = select_anchors(spec)
        self.assertEqual(len(result), 2)


class TestInferFeatures(unittest.TestCase):
    """Feature inference from module_spec contents."""

    def test_fsm_states_detected(self):
        spec = {
            "ports": [],
            "cycle_timing": {"fsm_states": [{"name": "S0"}, {"name": "S1"}]},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_states"])

    def test_shift_register_by_port(self):
        spec = {
            "ports": [{"name": "shift_en", "direction": "input", "width": 1}],
            "cycle_timing": {},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_shift_register"])

    def test_pipeline_by_latency(self):
        spec = {
            "ports": [],
            "cycle_timing": {
                "pipeline_timing": {"input_to_output_latency_cycles": 3}
            },
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_pipeline"])

    def test_pipeline_by_delay_cycles(self):
        spec = {
            "ports": [],
            "cycle_timing": {},
            "timing_contract": {"pipeline_delay_cycles": 2},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_pipeline"])

    def test_hash_round_by_description(self):
        spec = {
            "module_name": "sha256_round",
            "description": "One round of SHA-256 compression",
            "ports": [],
            "cycle_timing": {},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_hash_round"])

    def test_handshake_hold_by_ports(self):
        spec = {
            "ports": [
                {"name": "valid", "direction": "output", "width": 1},
                {"name": "ready", "direction": "input", "width": 1},
            ],
            "cycle_timing": {},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_handshake_hold"])

    def test_handshake_pulse_by_lifetime(self):
        spec = {
            "ports": [
                {"name": "valid", "direction": "output", "width": 1,
                 "signal_lifetime": "pulse"},
                {"name": "ack", "direction": "input", "width": 1},
            ],
            "cycle_timing": {},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_handshake_pulse"])
        self.assertFalse(feats["has_handshake_hold"])

    def test_variable_rotation_by_port(self):
        spec = {
            "ports": [{"name": "rotate_amount", "direction": "input", "width": 5}],
            "cycle_timing": {},
        }
        feats = _infer_features(spec)
        self.assertTrue(feats["has_variable_rotation"])

    def test_no_false_positives(self):
        """A plain counter has none of the specialized features."""
        spec = {
            "module_name": "counter",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst", "direction": "input", "width": 1},
                {"name": "en", "direction": "input", "width": 1},
                {"name": "count", "direction": "output", "width": 8},
            ],
            "cycle_timing": {},
            "timing_contract": {"pipeline_delay_cycles": 0},
        }
        feats = _infer_features(spec)
        self.assertFalse(feats["has_states"])
        self.assertFalse(feats["has_shift_register"])
        self.assertFalse(feats["has_pipeline"])
        self.assertFalse(feats["has_hash_round"])
        self.assertFalse(feats["has_handshake_hold"])
        self.assertFalse(feats["has_handshake_pulse"])
        self.assertFalse(feats["has_variable_rotation"])


if __name__ == "__main__":
    unittest.main()

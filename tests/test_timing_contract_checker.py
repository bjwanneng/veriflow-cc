"""Tests for timing_contract_checker."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
sys.path.insert(0, str(_SKILLS_DIR))

from timing_contract_checker import (  # noqa: E402
    check_spec_consistency,
    check_latency_consistency,
    check_port_semantic_completeness,
    check_golden_trace_alignment,
)


def _minimal_spec(**overrides):
    """Build a minimal valid spec.json structure."""
    spec = {
        "modules": [
            {
                "module_name": "top_mod",
                "module_type": "top",
                "ports": [],
                "cycle_timing": {
                    "pipeline_timing": {
                        "input_to_output_latency_cycles": 2,
                    }
                },
            }
        ],
        "module_connectivity": [],
    }
    spec.update(overrides)
    return spec


def _write_spec(tmp: str, spec: dict) -> str:
    path = Path(tmp) / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return str(path)


def _write_golden(tmp: str, body: str) -> str:
    path = Path(tmp) / "golden_model.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_registered_sequential_consistent():
    spec = _minimal_spec(module_connectivity=[{
        "source": "mod1.data_out", "destination": "mod2.data_in",
        "timing_contract": {
            "producer_type": "registered", "consumer_type": "sequential",
            "same_cycle_visible": False, "pipeline_delay_cycles": 1,
        }
    }])
    errors, _ = check_spec_consistency(spec)
    assert errors == []


def test_registered_sequential_contradiction():
    spec = _minimal_spec(module_connectivity=[{
        "source": "mod1.data_out", "destination": "mod2.data_in",
        "timing_contract": {
            "producer_type": "registered", "consumer_type": "sequential",
            "same_cycle_visible": True, "pipeline_delay_cycles": 1,
        }
    }])
    errors, _ = check_spec_consistency(spec)
    assert len(errors) == 1
    assert "same_cycle_visible=True" in errors[0]


def test_combinational_sequential_wrong_delay():
    spec = _minimal_spec(module_connectivity=[{
        "source": "mod1.data_out", "destination": "mod2.data_in",
        "timing_contract": {
            "producer_type": "combinational", "consumer_type": "sequential",
            "same_cycle_visible": True, "pipeline_delay_cycles": 2,
        }
    }])
    errors, _ = check_spec_consistency(spec)
    assert len(errors) == 1
    assert "pipeline_delay_cycles=2" in errors[0]


def test_bypass_required_but_no_signal():
    spec = _minimal_spec(module_connectivity=[{
        "source": "mod1.data_out", "destination": "mod2.data_in",
        "timing_contract": {
            "producer_type": "registered", "consumer_type": "sequential",
            "same_cycle_visible": False, "pipeline_delay_cycles": 1,
            "bypass_required": True, "bypass_signal": "",
        }
    }])
    errors, _ = check_spec_consistency(spec)
    assert any("bypass" in e for e in errors)


def test_delay_zero_but_same_cycle_false():
    spec = _minimal_spec(module_connectivity=[{
        "source": "mod1.data_out", "destination": "mod2.data_in",
        "timing_contract": {
            "producer_type": "combinational", "consumer_type": "sequential",
            "same_cycle_visible": False, "pipeline_delay_cycles": 0,
        }
    }])
    errors, _ = check_spec_consistency(spec)
    assert any("contradiction" in e for e in errors)


def test_port_reset_missing_polarity():
    spec = _minimal_spec()
    spec["modules"][0]["ports"] = [{"name": "rst", "protocol": "reset"}]
    errors, _ = check_port_semantic_completeness(spec)
    assert any("reset_polarity" in e for e in errors)


def test_port_valid_missing_handshake():
    spec = _minimal_spec()
    spec["modules"][0]["ports"] = [{"name": "data_valid", "protocol": "valid"}]
    errors, _ = check_port_semantic_completeness(spec)
    assert any("handshake" in e for e in errors)


def test_latency_mismatch():
    spec = _minimal_spec(module_connectivity=[
        {"source": "m1.a", "destination": "top_mod.b",
         "timing_contract": {"producer_type": "registered", "pipeline_delay_cycles": 2}},
        {"source": "top_mod.c", "destination": "m2.d",
         "timing_contract": {"producer_type": "registered", "pipeline_delay_cycles": 2}},
    ])
    errors, _ = check_latency_consistency(spec)
    assert any("latency=2" in e for e in errors)


def test_golden_trace_alignment_ok():
    with tempfile.TemporaryDirectory() as tmp:
        spec = _minimal_spec()
        spec["modules"][0]["ports"] = [{"name": "data_out"}]
        spec_path = _write_spec(tmp, spec)
        golden_path = _write_golden(tmp,
            "def run(test_vector_index=0):\n"
            "    return [{'data_out': 42}, {'data_out': 99}]\n"
        )
        errors, warnings = check_golden_trace_alignment(spec, golden_path)
        assert errors == []


def test_golden_trace_signals_unmatched():
    with tempfile.TemporaryDirectory() as tmp:
        spec = _minimal_spec()
        spec["modules"][0]["ports"] = [{"name": "data_out"}]
        spec_path = _write_spec(tmp, spec)
        golden_path = _write_golden(tmp,
            "def run(test_vector_index=0):\n"
            "    return [{'weird_signal': 42}]\n"
        )
        errors, warnings = check_golden_trace_alignment(spec, golden_path)
        assert any("weird_signal" in w for w in warnings)


def test_cli_no_spec_returns_2():
    result = subprocess.run(
        [sys.executable, str(_SKILLS_DIR / "timing_contract_checker.py"),
         "--spec", "/nonexistent/spec.json"],
        capture_output=True, text=True
    )
    assert result.returncode == 2


def test_cli_valid_spec_returns_0():
    with tempfile.TemporaryDirectory() as tmp:
        spec = _minimal_spec()
        spec_path = _write_spec(tmp, spec)
        result = subprocess.run(
            [sys.executable, str(_SKILLS_DIR / "timing_contract_checker.py"),
             "--spec", spec_path],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["passed"] is True

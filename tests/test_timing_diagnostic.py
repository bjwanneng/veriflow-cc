"""Tests for timing_diagnostic.py — parsing, classification, and fix suggestion."""

import json
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from timing_diagnostic import (
    Divergence, SignalDiagnosis, TimingDiagnosis,
    parse_divergence, _classify_signal, find_timing_context, diagnose,
)


# --- Helpers ---

def _write_temp(content, suffix):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def _make_spec():
    return {
        "timing_convention": {
            "golden_model": "software_instantaneous",
            "rtl": "post_nba_registered",
            "golden_to_rtl_offset_cycles": 1,
        },
        "module_connectivity": [
            {
                "source": "fsm.hash_valid",
                "destination": "core.hash_valid_out",
                "timing_contract": {
                    "producer_type": "registered",
                    "consumer_type": "sequential",
                    "pipeline_delay_cycles": 1,
                },
            },
            {
                "source": "fsm.update_v_en",
                "destination": "compress.update_v_en",
                "timing_contract": {
                    "producer_type": "registered",
                    "consumer_type": "sequential",
                    "pipeline_delay_cycles": 1,
                },
            },
        ],
        "fanout_groups": [
            {
                "name": "done_outputs",
                "signals": [
                    {"name": "hash_valid", "path": "fsm.hash_valid -> core.hash_valid_out"},
                    {"name": "update_v_en", "path": "fsm.update_v_en -> compress.update_v_en"},
                ],
                "constraint": "same_arrival",
                "max_delay_skew_cycles": 0,
            },
        ],
    }


def _make_golden_trace():
    """Simulated golden model that produces a trace."""
    return (
        "TEST_VECTORS = [{'name': 'basic', 'inputs': {}, 'expected': {}}]\n"
        "\n"
        "def run(test_vector_index=0):\n"
        "    trace = []\n"
        "    for i in range(10):\n"
        "        entry = {\n"
        "            'hash_valid': 1 if i >= 5 else 0,\n"
        "            'update_v_en': 1 if i >= 5 else 0,\n"
        "            'state_reg': 3 if i >= 5 else 0,\n"
        "        }\n"
        "        trace.append(entry)\n"
        "    return trace\n"
    )


# --- Tests ---

def test_parse_cocotb_divergence():
    """Parse [LAYERED] FIRST DIVERGENCE from cocotb log (multi-line format)."""
    log = _write_temp(
        "[LAYERED] FIRST DIVERGENCE at cycle=67 signal=hash_valid (width=1b):\n"
        "  expected = 0x1\n"
        "  actual   = 0x0\n"
        "  xor diff = 0x1\n",
        ".log",
    )
    div = parse_divergence(log)
    assert div is not None
    assert div.cycle == 67
    assert div.signal == "hash_valid"
    assert div.expected == 1
    assert div.actual == 0
    log.unlink()


def test_parse_internal_divergence():
    """Parse [INTERNAL] FIRST DIVERGENCE from cocotb log (multi-line format)."""
    log = _write_temp(
        "[INTERNAL] FIRST DIVERGENCE at cycle=5 signal=state_reg (width=8b):\n"
        "  expected = 0x3\n"
        "  actual   = 0x0\n"
        "  xor diff = 0x3\n",
        ".log",
    )
    div = parse_divergence(log)
    assert div is not None
    assert div.cycle == 5
    assert div.signal == "state_reg"
    assert div.expected == 3
    assert div.actual == 0
    log.unlink()


def test_parse_internal_divergence_with_kind_tag():
    """Parse INTERNAL divergence with kind=stimulus_mismatch."""
    log = _write_temp(
        "[INTERNAL] FIRST DIVERGENCE at cycle=2 signal=msg_block (width=512b) kind=stimulus_mismatch:\n"
        "  expected = 0x61626380\n"
        "  actual   = 0x00000000\n"
        "  xor diff = 0x61626380\n",
        ".log",
    )
    div = parse_divergence(log)
    assert div is not None
    assert div.cycle == 2
    assert div.signal == "msg_block"
    assert div.expected == 0x61626380
    assert div.actual == 0
    log.unlink()


def test_no_divergence():
    """No FIRST DIVERGENCE in log → None."""
    log = _write_temp("All tests passed.\n", ".log")
    div = parse_divergence(log)
    assert div is None
    log.unlink()


def test_classify_b_late():
    """Signal expected at cycle 5 but actually at cycle 6 → B_late.

    At cycle 5: golden says hash_valid=1, RTL says hash_valid=0.
    actual=0 matches golden[4]=0 (offset=1 behind) → B_late.
    """
    trace = [
        {"hash_valid": 0, "state_reg": 0},
        {"hash_valid": 0, "state_reg": 0},
        {"hash_valid": 0, "state_reg": 0},
        {"hash_valid": 0, "state_reg": 0},
        {"hash_valid": 0, "state_reg": 0},  # cycle 4: actual=0 matches here
        {"hash_valid": 1, "state_reg": 3},  # cycle 5: expected=1
        {"hash_valid": 1, "state_reg": 3},
        {"hash_valid": 1, "state_reg": 3},
    ]
    # At cycle 5, golden says 1, RTL says 0. actual=0 matches golden[4]=0 → B_late offset=1
    result = _classify_signal("hash_valid", 5, expected=1, actual=0, golden_trace=trace)
    assert result.classification == "B_late"
    assert result.offset_cycles == 1


def test_classify_d_initialization():
    """Expected non-zero but actual is 0, and 0 never appears in golden → D."""
    trace = [
        {"data": 0xABCD},
        {"data": 0x1234},
        {"data": 0x5678},
    ]
    # At cycle 1: expected=0x1234, actual=0x No match for 0 in golden → D
    result = _classify_signal("data", 1, expected=0x1234, actual=0, golden_trace=trace)
    assert result.classification == "D"


def test_find_timing_context():
    """Find timing_contract edges for hash_valid signal."""
    spec = _make_spec()
    ctx = find_timing_context("hash_valid", spec)
    assert len(ctx) >= 1
    sources = [c.get("source", "") for c in ctx]
    assert any("hash_valid" in s for s in sources)


def test_find_fanout_context():
    """Find fanout_group context for hash_valid."""
    spec = _make_spec()
    ctx = find_timing_context("hash_valid", spec)
    fanout_entries = [c for c in ctx if "fanout_group" in c]
    assert len(fanout_entries) >= 1
    assert fanout_entries[0]["fanout_group"] == "done_outputs"


def test_full_diagnosis():
    """End-to-end: synthesize log + golden + spec → diagnosis."""
    log = _write_temp(
        "[LAYERED] FIRST DIVERGENCE at cycle=5 signal=hash_valid (width=1b):\n"
        "  expected = 0x1\n"
        "  actual   = 0x0\n"
        "  xor diff = 0x1\n",
        ".log",
    )
    golden = _write_temp(_make_golden_trace(), ".py")
    spec = _write_temp(json.dumps(_make_spec()), ".json")

    result = diagnose(log, golden, spec)
    assert result is not None
    assert result.divergence.signal == "hash_valid"
    assert result.divergence.cycle == 5
    assert "hash_valid" in result.fix_suggestion
    assert len(result.timing_contract_context) > 0

    # Clean up
    log.unlink()
    golden.unlink()
    spec.unlink()


def test_no_divergence_returns_none():
    """Log without divergence → None."""
    log = _write_temp("PASS\n", ".log")
    golden = _write_temp(_make_golden_trace(), ".py")
    spec = _write_temp(json.dumps(_make_spec()), ".json")

    result = diagnose(log, golden, spec)
    assert result is None

    log.unlink()
    golden.unlink()
    spec.unlink()


# --- BUG-1 regression: vcd2table pattern parsing ---


def test_parse_vcd2table_summary_divergence():
    """Parse FIRST DIVERGENCE SUMMARY from vcd2table output (rich format)."""
    log = _write_temp(
        "FIRST DIVERGENCE SUMMARY: cycle=14 signal=A_reg "
        "golden=0x1234 rtl=0x0000 type=data-or-initialization\n",
        ".log",
    )
    div = parse_divergence(log)
    assert div is not None
    assert div.cycle == 14
    assert div.signal == "A_reg"
    assert div.expected == 0x1234
    assert div.actual == 0x0000
    assert div.degraded is False
    log.unlink()


def test_parse_vcd2table_basic_degraded():
    """Parse basic vcd2table format (only cycle) — should be marked degraded."""
    log = _write_temp(
        "Some output...\n"
        "FIRST DIVERGENCE: cycle 42\n"
        "More output...\n",
        ".log",
    )
    div = parse_divergence(log)
    assert div is not None
    assert div.cycle == 42
    assert div.signal == "unknown_from_vcd2table"
    assert div.expected == 0
    assert div.actual == 0
    assert div.degraded is True
    log.unlink()


# --- BUG-3 regression: unclassifiable when expected==actual ---


def test_classify_unclassifiable():
    """When expected==actual, classification should be 'unclassifiable' not 'A'."""
    trace = [
        {"data": 0x1000},
        {"data": 0x2000},
    ]
    result = _classify_signal("data", 1, expected=0x2000, actual=0x2000, golden_trace=trace)
    assert result.classification == "unclassifiable"
    assert result.offset_cycles == 0


def test_classify_degraded_divergence_unclassifiable():
    """Degraded Divergence (from vcd2table basic) with expected==actual=0 → unclassifiable."""
    from timing_diagnostic import classify_all_signals
    div = Divergence(cycle=5, signal="unknown_from_vcd2table", expected=0, actual=0, degraded=True)
    trace = [
        {"hash_valid": 0},
        {"hash_valid": 1},
        {"hash_valid": 1},
    ]
    result = classify_all_signals(div, trace)
    assert len(result) == 1
    assert result[0].classification == "unclassifiable"


# --- Coverage gap: B_early classification ---


def test_classify_b_early():
    """Signal expected at cycle 2 but RTL shows value from cycle 3 → B_early.

    At cycle 2: golden says data=0x2000, RTL says data=0x3000.
    actual=0x3000 matches golden[3]=0x3000 (offset=1 ahead) → B_early.
    """
    trace = [
        {"data": 0x1000},
        {"data": 0x1000},
        {"data": 0x2000},
        {"data": 0x3000},
        {"data": 0x4000},
    ]
    result = _classify_signal("data", 2, expected=0x2000, actual=0x3000, golden_trace=trace)
    assert result.classification == "B_early"
    assert result.offset_cycles == 1


# --- Full diagnosis with degraded divergence ---


def test_full_diagnosis_degraded():
    """Degraded vcd2table divergence produces unclassifiable diagnosis."""
    log = _write_temp("FIRST DIVERGENCE: cycle 5\n", ".log")
    golden = _write_temp(_make_golden_trace(), ".py")
    spec = _write_temp(json.dumps(_make_spec()), ".json")

    result = diagnose(log, golden, spec)
    assert result is not None
    assert result.divergence.degraded is True
    assert result.divergence.signal == "unknown_from_vcd2table"
    assert any(s.classification == "unclassifiable" for s in result.all_signals)
    assert result.severity == "low"

    log.unlink()
    golden.unlink()
    spec.unlink()


if __name__ == "__main__":
    test_parse_cocotb_divergence()
    test_parse_internal_divergence()
    test_parse_internal_divergence_with_kind_tag()
    test_no_divergence()
    test_classify_b_late()
    test_classify_d_initialization()
    test_find_timing_context()
    test_find_fanout_context()
    test_full_diagnosis()
    test_no_divergence_returns_none()
    test_parse_vcd2table_summary_divergence()
    test_parse_vcd2table_basic_degraded()
    test_classify_unclassifiable()
    test_classify_degraded_divergence_unclassifiable()
    test_classify_b_early()
    test_full_diagnosis_degraded()
    print("All timing_diagnostic tests passed.")

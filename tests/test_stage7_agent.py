"""Tests for Stage 7 inline simulation (cocotb-first integration test).

Covers:
- stage_7.md is inline (no sub-agent dispatch)
- Required parameters are present in stage_7.md
- Hook has 3-layer verification
- cocotb-first path documented
- Verilog fallback path documented
- Waveform analysis documented
"""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE7_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_7.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


# -- stage_7.md structure (inline execution) ---

def test_stage7_is_inline():
    """stage_7.md must declare inline execution, not sub-agent dispatch."""
    content = read_file(STAGE7_PATH)
    assert "inline" in content.lower(), \
        "stage_7.md must document inline execution pattern"


def test_stage7_prompt_has_required_params():
    """Inline stage must reference required paths."""
    content = read_file(STAGE7_PATH)
    required_params = ["PROJECT_DIR", "PYTHON_EXE", "SKILL_DIR"]
    for param in required_params:
        assert param in content, \
            f"stage_7.md missing required parameter: {param}"
    # EDA env is sourced from known path, not passed as parameter
    assert "eda_env.sh" in content, \
        "stage_7.md must source eda_env.sh"


def test_stage7_has_cocotb_path():
    """stage_7.md must have cocotb-first simulation path."""
    content = read_file(STAGE7_PATH)
    assert "cocotb" in content.lower(), \
        "stage_7.md must describe cocotb-first simulation path"
    assert "COCOTB_AVAILABLE" in content, \
        "stage_7.md must check COCOTB_AVAILABLE"


def test_stage7_has_verilog_fallback():
    """stage_7.md must have Verilog fallback when cocotb unavailable."""
    content = read_file(STAGE7_PATH)
    assert "Verilog fallback" in content or "7c" in content, \
        "stage_7.md must have Verilog fallback section (7c)"


def test_stage7_has_waveform_analysis():
    """stage_7.md must have waveform analysis on failure."""
    content = read_file(STAGE7_PATH)
    assert "vcd2table" in content or "Waveform" in content, \
        "stage_7.md must reference waveform analysis (vcd2table)"


def test_stage7_has_golden_model_comparison():
    """stage_7.md must have golden model comparison section."""
    content = read_file(STAGE7_PATH)
    assert "golden" in content.lower() or "Golden" in content, \
        "stage_7.md must have golden model comparison"


def test_stage7_has_phases():
    """stage_7.md must describe simulation phases."""
    content = read_file(STAGE7_PATH)
    # The new structure uses 7b (cocotb), 7c (Verilog fallback), 7d (waveform)
    assert "7b" in content, "stage_7.md must have section 7b (cocotb path)"
    assert "7c" in content, "stage_7.md must have section 7c (Verilog fallback)"


# -- stage_7.md hook ---

def test_stage7_hook_3_layer():
    """stage_7.md hook must have all 3 verification layers."""
    content = read_file(STAGE7_PATH)
    assert "tb.vvp" in content, \
        "stage_7.md hook must check for tb.vvp (Layer 0)"
    assert "FAIL" in content, \
        "stage_7.md hook must check for test failures (Layer 2)"
    assert "PASS" in content, \
        "stage_7.md hook must check for PASS summary (Layer 3)"


if __name__ == "__main__":
    tests = [
        test_stage7_is_inline,
        test_stage7_prompt_has_required_params,
        test_stage7_has_cocotb_path,
        test_stage7_has_verilog_fallback,
        test_stage7_has_waveform_analysis,
        test_stage7_has_golden_model_comparison,
        test_stage7_has_phases,
        test_stage7_hook_3_layer,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
    if failed:
        raise SystemExit(1)

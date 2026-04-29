"""Tests for Stage 7 agent prompt format and vf-simulator.md configuration.

Covers:
- vf-simulator.md tools field is comma-separated (not YAML list)
- Required prompt parameters are present in stage_7.md
- Fallback section (7b-fallback) contains simulation phases
- Hook has 3-layer verification
"""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE7_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_7.md"
VF_SIMULATOR_PATH = PROJECT_DIR / "src/claude_agents/vf-simulator.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


# -- vf-simulator.md agent configuration ---

def test_vf_simulator_tools_comma_separated():
    """tools field must be comma-separated, NOT a YAML list (GitHub #12392)."""
    content = read_file(VF_SIMULATOR_PATH)
    assert "\ntools:\n  -" not in content, \
        "vf-simulator.md tools field must not use YAML list format"
    assert "\ntools:\n- " not in content, \
        "vf-simulator.md tools field must not use YAML list format"

def test_vf_simulator_tools_contains_required_tools():
    """tools field must include Read, Write, Glob, Grep, Bash."""
    content = read_file(VF_SIMULATOR_PATH)
    match = re.search(r'^tools:\s*(.+)$', content, re.MULTILINE)
    assert match, "vf-simulator.md must have a 'tools:' line"
    tools_line = match.group(1)
    for tool in ["Read", "Write", "Glob", "Grep", "Bash"]:
        assert tool in tools_line, \
            f"vf-simulator.md tools field missing '{tool}': {tools_line}"

def test_vf_simulator_has_subagent_type():
    """vf-simulator.md must have name field set."""
    content = read_file(VF_SIMULATOR_PATH)
    assert "name: vf-simulator" in content, \
        "vf-simulator.md must have 'name: vf-simulator' in frontmatter"


# -- stage_7.md prompt format ---

def test_stage7_prompt_has_required_params():
    """Agent prompt must include all required path parameters."""
    content = read_file(STAGE7_PATH)
    required_params = ["PROJECT_DIR", "SPEC", "EDA_ENV", "PYTHON_EXE", "SKILL_DIR"]
    for param in required_params:
        assert param in content, \
            f"stage_7.md agent prompt missing required parameter: {param}"

def test_stage7_uses_subagent():
    """stage_7.md must dispatch to vf-simulator subagent."""
    content = read_file(STAGE7_PATH)
    assert "vf-simulator" in content, \
        "stage_7.md must reference vf-simulator subagent"

def test_stage7_retry_on_zero_tool_uses():
    """stage_7.md must have retry logic for 0 tool uses."""
    content = read_file(STAGE7_PATH)
    assert "0 tool uses" in content or "zero tool" in content.lower(), \
        "stage_7.md must handle the case where agent returns 0 tool uses"

def test_stage7_fallback_exists():
    """stage_7.md must have a fallback section when retry also fails."""
    content = read_file(STAGE7_PATH)
    assert "7b-fallback" in content, \
        "stage_7.md must have a 7b-fallback section"

def test_stage7_fallback_has_phases():
    """stage_7.md fallback must include Phase 1 and Phase 2."""
    content = read_file(STAGE7_PATH)
    assert "Phase 1" in content, \
        "stage_7.md fallback must mention Phase 1 (per-module sim)"
    assert "Phase 2" in content, \
        "stage_7.md fallback must mention Phase 2 (integration sim)"


# -- stage_7.md hook ---

def test_stage7_hook_3_layer():
    """stage_7.md hook must have all 3 verification layers."""
    content = read_file(STAGE7_PATH)
    assert "tb.vvp" in content, \
        "stage_7.md hook must check for tb.vvp (Layer 0)"
    assert "FAIL_COUNT" in content or "FAIL" in content, \
        "stage_7.md hook must check for test failures (Layer 2)"
    assert "PASS" in content, \
        "stage_7.md hook must check for PASS summary (Layer 3)"


if __name__ == "__main__":
    tests = [
        test_vf_simulator_tools_comma_separated,
        test_vf_simulator_tools_contains_required_tools,
        test_vf_simulator_has_subagent_type,
        test_stage7_prompt_has_required_params,
        test_stage7_uses_subagent,
        test_stage7_retry_on_zero_tool_uses,
        test_stage7_fallback_exists,
        test_stage7_fallback_has_phases,
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

"""Tests for Stage 6 agent prompt format and vf-linter.md configuration."""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE6_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_6.md"
VF_LINTER_PATH = PROJECT_DIR / "src/claude_agents/vf-linter.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


def test_vf_linter_tools_comma_separated():
    content = read_file(VF_LINTER_PATH)
    assert "\ntools:\n  -" not in content
    assert "\ntools:\n- " not in content

def test_vf_linter_tools_contains_required_tools():
    content = read_file(VF_LINTER_PATH)
    match = re.search(r'^tools:\s*(.+)$', content, re.MULTILINE)
    assert match, "vf-linter.md must have a 'tools:' line"
    tools_line = match.group(1)
    for tool in ["Read", "Bash"]:
        assert tool in tools_line, f"vf-linter.md missing '{tool}'"

def test_vf_linter_has_subagent_type():
    content = read_file(VF_LINTER_PATH)
    assert "name: vf-linter" in content

def test_vf_linter_has_result_format():
    content = read_file(VF_LINTER_PATH)
    assert "LINT_RESULT: PASS" in content
    assert "LINT_RESULT: FAIL" in content

def test_stage6_prompt_has_required_params():
    content = read_file(STAGE6_PATH)
    for param in ["PROJECT_DIR", "EDA_ENV"]:
        assert param in content, f"stage_6.md missing parameter: {param}"

def test_stage6_uses_subagent():
    content = read_file(STAGE6_PATH)
    assert "vf-linter" in content

def test_stage6_retry_on_zero_tool_uses():
    content = read_file(STAGE6_PATH)
    assert "0 tool uses" in content

def test_stage6_fallback_exists():
    content = read_file(STAGE6_PATH)
    assert "6b-fallback" in content

def test_stage6_hook():
    content = read_file(STAGE6_PATH)
    assert "iverilog" in content


if __name__ == "__main__":
    tests = [
        test_vf_linter_tools_comma_separated,
        test_vf_linter_tools_contains_required_tools,
        test_vf_linter_has_subagent_type,
        test_vf_linter_has_result_format,
        test_stage6_prompt_has_required_params,
        test_stage6_uses_subagent,
        test_stage6_retry_on_zero_tool_uses,
        test_stage6_fallback_exists,
        test_stage6_hook,
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

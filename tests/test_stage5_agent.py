"""Tests for Stage 5 agent prompt format and vf-reviewer.md configuration.

Covers:
- vf-reviewer.md tools field is comma-separated (not YAML list)
- Required prompt parameters are present in stage_5.md
- Fallback section (5b-fallback) contains 7-category analysis
- Hook checks static_report.json
"""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE5_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_5.md"
VF_REVIEWER_PATH = PROJECT_DIR / "src/claude_agents/vf-reviewer.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


# -- vf-reviewer.md agent configuration ---

def test_vf_reviewer_tools_comma_separated():
    """tools field must be comma-separated, NOT a YAML list (GitHub #12392)."""
    content = read_file(VF_REVIEWER_PATH)
    assert "\ntools:\n  -" not in content, \
        "vf-reviewer.md tools field must not use YAML list format"
    assert "\ntools:\n- " not in content, \
        "vf-reviewer.md tools field must not use YAML list format"

def test_vf_reviewer_tools_contains_required_tools():
    """tools field must include Read, Write, Glob, Grep, Bash."""
    content = read_file(VF_REVIEWER_PATH)
    match = re.search(r'^tools:\s*(.+)$', content, re.MULTILINE)
    assert match, "vf-reviewer.md must have a 'tools:' line"
    tools_line = match.group(1)
    for tool in ["Read", "Write", "Glob", "Grep", "Bash"]:
        assert tool in tools_line, \
            f"vf-reviewer.md tools field missing '{tool}': {tools_line}"

def test_vf_reviewer_has_subagent_type():
    """vf-reviewer.md must have name field set."""
    content = read_file(VF_REVIEWER_PATH)
    assert "name: vf-reviewer" in content, \
        "vf-reviewer.md must have 'name: vf-reviewer' in frontmatter"


# -- stage_5.md prompt format ---

def test_stage5_prompt_has_required_params():
    """Agent prompt must include all required path parameters."""
    content = read_file(STAGE5_PATH)
    required_params = ["PROJECT_DIR", "SPEC", "OUTPUT"]
    for param in required_params:
        assert param in content, \
            f"stage_5.md agent prompt missing required parameter: {param}"

def test_stage5_uses_subagent():
    """stage_5.md must dispatch to vf-reviewer subagent."""
    content = read_file(STAGE5_PATH)
    assert "vf-reviewer" in content, \
        "stage_5.md must reference vf-reviewer subagent"
    assert 'subagent_type: "vf-reviewer"' in content or "subagent_type: 'vf-reviewer'" in content or "vf-reviewer" in content, \
        "stage_5.md must call Agent with vf-reviewer"

def test_stage5_retry_on_zero_tool_uses():
    """stage_5.md must have retry logic for 0 tool uses."""
    content = read_file(STAGE5_PATH)
    assert "0 tool uses" in content or "zero tool" in content.lower(), \
        "stage_5.md must handle the case where agent returns 0 tool uses"

def test_stage5_fallback_exists():
    """stage_5.md must have a fallback section when retry also fails."""
    content = read_file(STAGE5_PATH)
    assert "5b-fallback" in content, \
        "stage_5.md must have a 5b-fallback section"

def test_stage5_fallback_has_all_categories():
    """stage_5.md fallback must include all 7 analysis categories."""
    content = read_file(STAGE5_PATH)
    categories = ["Static Checks", "Deep Code Review", "Logic Depth", "Resource Estimate",
                   "Constraint Compliance", "Functional Completeness", "Array Bounds"]
    for cat in categories:
        assert cat in content, \
            f"stage_5.md fallback missing analysis category: '{cat}'"


# -- stage_5.md hook ---

def test_stage5_hook_checks_report():
    """stage_5.md hook must verify static_report.json exists."""
    content = read_file(STAGE5_PATH)
    assert "static_report.json" in content, \
        "stage_5.md hook must check for static_report.json"


if __name__ == "__main__":
    tests = [
        test_vf_reviewer_tools_comma_separated,
        test_vf_reviewer_tools_contains_required_tools,
        test_vf_reviewer_has_subagent_type,
        test_stage5_prompt_has_required_params,
        test_stage5_uses_subagent,
        test_stage5_retry_on_zero_tool_uses,
        test_stage5_fallback_exists,
        test_stage5_fallback_has_all_categories,
        test_stage5_hook_checks_report,
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

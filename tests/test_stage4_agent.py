"""Tests for Stage 4 agent prompt format and vf-coder.md configuration.

Covers:
- vf-coder.md tools field is comma-separated (not YAML list)
- Required prompt parameters are present in stage_4.md
- Fallback section (4c-fallback) contains Step 3.5 verification
- Sub-module ordering: non-top modules before top module
"""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE4_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_4.md"
VF_CODER_PATH = PROJECT_DIR / "src/claude_agents/vf-coder.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


# ── vf-coder.md agent configuration ───────────────────────────────────────

def test_vf_coder_tools_comma_separated():
    """tools field must be comma-separated, NOT a YAML list (GitHub #12392)."""
    content = read_file(VF_CODER_PATH)
    # Must NOT have YAML list format
    assert "\ntools:\n  -" not in content, \
        "vf-coder.md tools field must not use YAML list format"
    assert "\ntools:\n- " not in content, \
        "vf-coder.md tools field must not use YAML list format"

def test_vf_coder_tools_contains_required_tools():
    """tools field must include Read, Write, Glob, Grep, Bash."""
    content = read_file(VF_CODER_PATH)
    # Find the tools line
    match = re.search(r'^tools:\s*(.+)$', content, re.MULTILINE)
    assert match, "vf-coder.md must have a 'tools:' line"
    tools_line = match.group(1)
    for tool in ["Read", "Write", "Glob", "Grep", "Bash"]:
        assert tool in tools_line, \
            f"vf-coder.md tools field missing '{tool}': {tools_line}"

def test_vf_coder_has_subagent_type():
    """vf-coder.md must have name field set."""
    content = read_file(VF_CODER_PATH)
    assert "name: vf-coder" in content, \
        "vf-coder.md must have 'name: vf-coder' in frontmatter"


# ── stage_4.md prompt format ───────────────────────────────────────────────

def test_stage4_prompt_has_required_params():
    """Agent prompt must include all required path parameters."""
    content = read_file(STAGE4_PATH)
    required_params = [
        "CODING_STYLE",
        "SPEC",
        "BEHAVIOR_SPEC",
        "MICRO_ARCH",
        "MODULE_NAME",
        "OUTPUT_DIR",
    ]
    for param in required_params:
        assert param in content, \
            f"stage_4.md agent prompt missing required parameter: {param}"

def test_stage4_top_module_last():
    """stage_4.md must instruct sub-modules to be generated before top module."""
    content = read_file(STAGE4_PATH)
    assert "non-top" in content.lower() or "sub-module" in content.lower() or "skip top" in content.lower(), \
        "stage_4.md must mention generating sub-modules before top module"
    assert "top module last" in content.lower() or "top last" in content.lower() or "process it last" in content.lower(), \
        "stage_4.md must mention processing top module last"

def test_stage4_retry_on_zero_tool_uses():
    """stage_4.md must have retry logic for 0 tool uses."""
    content = read_file(STAGE4_PATH)
    assert "0 tool uses" in content or "zero tool" in content.lower(), \
        "stage_4.md must handle the case where agent returns 0 tool uses"

def test_stage4_fallback_exists():
    """stage_4.md must have a fallback section when retry also fails."""
    content = read_file(STAGE4_PATH)
    assert "4c-fallback" in content, \
        "stage_4.md must have a 4c-fallback section"

def test_stage4_fallback_has_step35_verification():
    """stage_4.md fallback section must include Step 3.5 internal verification."""
    content = read_file(STAGE4_PATH)
    assert "Step 3.5" in content or "3.5" in content, \
        "stage_4.md fallback must include Step 3.5 self-check"
    # Verify the 5 checks are mentioned
    checks = ["Timing table", "Register delay", "Control timing", "FSM sync", "Counter range"]
    for check in checks:
        assert check in content, \
            f"stage_4.md fallback Step 3.5 missing check: '{check}'"

def test_stage4_no_parallel_agent_calls():
    """Agent calls must be sequential (top module last, not parallelized)."""
    content = read_file(STAGE4_PATH)
    assert "sequentially" in content.lower() or "sequential" in content.lower(), \
        "stage_4.md must specify sequential agent execution"
    # Must NOT say to parallelize
    assert "parallelize" not in content.lower() or "do NOT parallelize" in content or "not parallelize" in content.lower(), \
        "stage_4.md must not allow parallelizing coder agent calls"


# ── stage_4.md hook ────────────────────────────────────────────────────────

def test_stage4_hook_checks_endmodule():
    """stage_4.md hook must verify endmodule is present in each .v file."""
    content = read_file(STAGE4_PATH)
    assert "endmodule" in content, \
        "stage_4.md hook must check for endmodule in generated RTL files"


if __name__ == "__main__":
    tests = [
        test_vf_coder_tools_comma_separated,
        test_vf_coder_tools_contains_required_tools,
        test_vf_coder_has_subagent_type,
        test_stage4_prompt_has_required_params,
        test_stage4_top_module_last,
        test_stage4_retry_on_zero_tool_uses,
        test_stage4_fallback_exists,
        test_stage4_fallback_has_step35_verification,
        test_stage4_no_parallel_agent_calls,
        test_stage4_hook_checks_endmodule,
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

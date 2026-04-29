"""Tests for Stage 8 agent prompt format and vf-synthesizer.md configuration."""

import re
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
STAGE8_PATH = PROJECT_DIR / "src/claude_skills/vf-pipeline/stages/stage_8.md"
VF_SYNTH_PATH = PROJECT_DIR / "src/claude_agents/vf-synthesizer.md"


def read_file(path):
    return path.read_text(encoding="utf-8")


def test_vf_synthesizer_tools_comma_separated():
    content = read_file(VF_SYNTH_PATH)
    assert "\ntools:\n  -" not in content
    assert "\ntools:\n- " not in content

def test_vf_synthesizer_tools_contains_required_tools():
    content = read_file(VF_SYNTH_PATH)
    match = re.search(r'^tools:\s*(.+)$', content, re.MULTILINE)
    assert match, "vf-synthesizer.md must have a 'tools:' line"
    tools_line = match.group(1)
    for tool in ["Read", "Bash"]:
        assert tool in tools_line, f"vf-synthesizer.md missing '{tool}'"

def test_vf_synthesizer_has_subagent_type():
    content = read_file(VF_SYNTH_PATH)
    assert "name: vf-synthesizer" in content

def test_vf_synthesizer_has_result_format():
    content = read_file(VF_SYNTH_PATH)
    assert "SYNTH_RESULT: PASS" in content
    assert "SYNTH_RESULT: FAIL" in content

def test_stage8_prompt_has_required_params():
    content = read_file(STAGE8_PATH)
    for param in ["PROJECT_DIR", "SPEC", "EDA_ENV"]:
        assert param in content, f"stage_8.md missing parameter: {param}"

def test_stage8_uses_subagent():
    content = read_file(STAGE8_PATH)
    assert "vf-synthesizer" in content

def test_stage8_retry_on_zero_tool_uses():
    content = read_file(STAGE8_PATH)
    assert "0 tool uses" in content

def test_stage8_fallback_exists():
    content = read_file(STAGE8_PATH)
    assert "8b-fallback" in content

def test_stage8_hook():
    content = read_file(STAGE8_PATH)
    assert "synth_report.txt" in content


if __name__ == "__main__":
    tests = [
        test_vf_synthesizer_tools_comma_separated,
        test_vf_synthesizer_tools_contains_required_tools,
        test_vf_synthesizer_has_subagent_type,
        test_vf_synthesizer_has_result_format,
        test_stage8_prompt_has_required_params,
        test_stage8_uses_subagent,
        test_stage8_retry_on_zero_tool_uses,
        test_stage8_fallback_exists,
        test_stage8_hook,
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

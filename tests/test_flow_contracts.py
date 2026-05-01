"""Static contract tests for pipeline prompts and templates."""

from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILL_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
_AGENTS_DIR = _PROJECT_DIR / "src" / "claude_agents"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_spec_template_has_explicit_timing_contract_fields():
    content = _read(_SKILL_DIR / "templates" / "spec_template.json")

    for field in (
        "producer_cycle",
        "visible_cycle",
        "consumer_cycle",
        "sample_phase",
        "bypass_required",
        "bypass_signal",
    ):
        assert field in content


def test_cocotb_runner_uses_verilog_2005_mode():
    content = _read(_SKILL_DIR / "cocotb_runner.py")

    assert '"-g2005"' in content
    assert '"-g2012"' not in content


def test_stage1_uses_spec_timing_as_golden_input():
    skill = _read(_SKILL_DIR / "SKILL.md")
    golden_agent = _read(_AGENTS_DIR / "vf-golden-gen.md")

    assert "Run **vf-spec-gen** first" in skill
    assert "SPEC_JSON" in golden_agent
    assert "cycle_timing in spec.json is the timing source of truth" in golden_agent


def test_skill_init_does_not_require_preexisting_python_exe():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert 'PY_INIT="${PYTHON_EXE:-python}"' in skill


def test_design_rules_reset_polarity_is_consistent():
    content = _read(_SKILL_DIR / "design_rules.md")

    assert 'reset_polarity`: `"active_high"` only' in content
    assert 'reset_polarity`: `"active_high"` or `"active_low"`' not in content

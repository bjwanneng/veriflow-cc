"""Static contract tests for pipeline prompts and templates."""

from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILL_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
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


def test_iverilog_runner_uses_verilog_2005_mode():
    content = _read(_SKILL_DIR / "iverilog_runner.py")

    assert '"-g2005"' in content
    assert '"-g2012"' not in content


def test_stage1_spec_golden_agent_aligns_timing():
    skill = _read(_SKILL_DIR / "SKILL.md")
    agent = _read(_AGENTS_DIR / "vf-spec-golden.md")

    assert "vf-spec-golden" in skill
    assert "Timing alignment" in agent  # merged agent does timing alignment internally
    assert "cycle_timing" in skill
    assert "cycle_timing" in agent


def test_skill_init_does_not_require_preexisting_python_exe():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert 'PY_INIT="${PYTHON_EXE:-python}"' in skill


def test_design_rules_reset_polarity_is_consistent():
    content = _read(_SKILL_DIR / "design_rules.md")

    assert 'reset_polarity`: `"active_high"` only' in content
    assert 'reset_polarity`: `"active_high"` or `"active_low"`' not in content


def test_architect_receives_spec_and_golden_as_inputs():
    architect = _read(_AGENTS_DIR / "vf-architect.md")

    assert "SPEC_JSON" in architect
    assert "GOLDEN_MODEL" in architect
    assert "timing_model.py only" in architect.lower()
    assert "do NOT regenerate them" in architect


def test_agents_do_not_have_websearch():
    """WebSearch moved to main session — sub-agents must not have it."""
    for agent_name in ("vf-spec-golden.md", "vf-coder.md"):
        content = _read(_AGENTS_DIR / agent_name)
        assert "WebSearch" not in content, f"{agent_name} still has WebSearch in tools"


def test_stage1_websearch_in_main_session():
    skill = _read(_SKILL_DIR / "SKILL.md")

    # SKILL.md must have WebSearch in the Stage 1 pre-stage section
    assert "Web Research" in skill
    assert "web_research.md" in skill


def test_stage1_single_spec_golden_dispatch():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "vf-spec-golden" in skill
    assert "spec.json" in skill
    assert "golden_model.py" in skill


def test_stage1_templates_preread():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "SPEC_TEMPLATE" in skill
    assert "GOLDEN_TEMPLATE" in skill


def test_step0_auto_approves_subagent_tools():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "Bash(python*)" in skill
    assert "Permission Check" in skill

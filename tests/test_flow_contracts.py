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


def test_architect_receives_spec_and_golden_as_inputs():
    architect = _read(_AGENTS_DIR / "vf-architect.md")

    assert "SPEC_JSON" in architect
    assert "GOLDEN_MODEL" in architect
    assert "timing_model.py only" in architect.lower()
    # Should NOT generate spec.json or golden_model.py
    assert "do NOT regenerate them" in architect


def test_spec_gen_and_golden_gen_have_websearch():
    spec_gen = _read(_AGENTS_DIR / "vf-spec-gen.md")
    golden_gen = _read(_AGENTS_DIR / "vf-golden-gen.md")

    assert "WebSearch" in spec_gen
    assert "WebSearch" in golden_gen


def test_stage1_is_sequential_pipeline():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "Run **vf-spec-gen** first" in skill
    assert "Agent 2: vf-golden-gen" in skill
    assert "Agent 3: vf-architect" in skill
    assert "timing_model.py ONLY" in skill


def test_coder_has_websearch():
    coder = _read(_AGENTS_DIR / "vf-coder.md")

    assert "WebSearch" in coder
    assert "Web Research" in coder


def test_step0_auto_approves_subagent_tools():
    skill = _read(_SKILL_DIR / "SKILL.md")

    # Step 0 must auto-add WebSearch and Bash(python*) to avoid sub-agent hangs
    assert "WebSearch" in skill
    assert "Bash(python*)" in skill
    assert "Permission Check" in skill

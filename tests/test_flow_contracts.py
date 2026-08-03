"""Static contract tests for pipeline prompts and templates."""

from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILL_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
_AGENTS_DIR = _PROJECT_DIR / "src" / "claude_agents" / "vf-rtl"


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
    content = _read(_SKILL_DIR / "runners" / "iverilog_runner.py")

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


def test_architect_role_merged_into_spec_golden():
    """vf-architect.md was removed when its outputs (spec + golden) were merged
    into vf-spec-golden in commit e940f47. This test guards against accidental
    resurrection of the stale file.
    """
    assert not (_AGENTS_DIR / "vf-architect.md").exists()
    assert not (_AGENTS_DIR / "vf-spec-gen.md").exists()
    assert not (_AGENTS_DIR / "vf-golden-gen.md").exists()


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


def test_stage1_templates_handed_to_subagent():
    """Stage 1 passes TEMPLATES_DIR to the spec-golden subagent and does NOT
    pre-read or embed template content in the prompt — the subagent reads the
    templates itself. (Earlier "preread SPEC_TEMPLATE/GOLDEN_TEMPLATE inline"
    behavior was intentionally removed; this guards the current contract.)
    """
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "TEMPLATES_DIR" in skill
    assert "DO NOT embed template content" in skill


def test_step0_auto_approves_subagent_tools():
    skill = _read(_SKILL_DIR / "SKILL.md")

    assert "Bash(python*)" in skill
    assert "Permission Check" in skill


def test_stage_reference_files_exist():
    """SKILL.md uses progressive disclosure: each stage's full execution bash
    lives in a per-stage reference file that SKILL.md tells the orchestrator to
    Read on entry. Guards the slim structure + deployability (install.py globs
    root *.md, so these must be at the skill root to be symlinked)."""
    skill = _read(_SKILL_DIR / "SKILL.md")
    for ref in (
        "stage1_spec_golden.md",
        "stage2_codegen.md",
        "stage3_verify_fix.md",
        "stage4_lint_synth.md",
    ):
        assert ref in skill, f"SKILL.md must reference {ref}"
        assert (_SKILL_DIR / ref).exists(), f"{ref} missing at skill root"


def test_stage4_equiv_combines_multifile_rtl():
    """HIGH#7: the HARD equivalence gate must feed yosys_equiv a COMBINED ref
    of all RTL files (leaf-first, top-last), not just the single top file —
    otherwise prep -top errors on undefined submodules and every hierarchical
    design false-fails. yosys_equiv accepts exactly one --ref."""
    stage4 = _read(_SKILL_DIR / "stage4_lint_synth.md")
    # Must NOT pass the single top file directly as --ref
    assert '--ref "workspace/rtl/${TOP_MODULE}.v"' not in stage4
    # Must build a combined ref that concatenates the leaf modules
    assert "rtl_ref_combined.v" in stage4
    assert "workspace/rtl/*.v" in stage4


def test_stage_docs_use_named_agent_dispatch():
    """HIGH#1: stage docs must dispatch the skill's named sub-agents
    (vf-spec-golden / vf-coder / vf-tb-gen / vf-linter / vf-synthesizer), NOT
    `subagent_type: general-purpose`. The general-purpose catch-all loads none
    of the agent system prompts (mini-patterns, bans, self-checks, maxTurns),
    making the whole agent layer dead weight."""
    named = {"vf-spec-golden", "vf-coder", "vf-tb-gen", "vf-linter", "vf-synthesizer"}
    for ref in ("stage1_spec_golden.md", "stage2_codegen.md", "stage4_lint_synth.md"):
        content = _read(_SKILL_DIR / ref)
        # Every dispatch line must reference a named agent, never general-purpose
        assert "subagent_type: general-purpose" not in content, (
            f"{ref} still uses subagent_type: general-purpose — bypasses agent prompts")
        # And at least one named agent is referenced
        assert any(name in content for name in named), f"{ref} references no named agent"


def test_multi_block_contract_is_consistent():
    """HIGH#9: the MULTI_BLOCK contract must be consistent end-to-end.
    - vf-spec-golden MUST document the exports it produces
    - golden_model_template MUST define the export names
    - vf-tb-gen MUST NOT tell a sub-agent to 'request' them from another
      sub-agent (impossible) — it must stop and surface an error instead.
    """
    spec_golden = _read(_AGENTS_DIR / "vf-spec-golden.md")
    template = (_SKILL_DIR / "templates" / "golden_model_template.py").read_text(encoding="utf-8")
    tb_gen = _read(_AGENTS_DIR / "vf-tb-gen.md")
    for name in ("MULTI_BLOCK_INPUTS", "MULTI_BLOCK_EXPECTED_DIGEST"):
        assert name in spec_golden, f"vf-spec-golden must document {name}"
        assert name in template, f"golden_model_template must define {name}"
        assert name in tb_gen, f"vf-tb-gen must consume {name}"
    # vf-tb-gen must not instruct an impossible cross-agent 'request'
    assert "request them from vf-spec-golden" not in tb_gen
    assert "STOP" in tb_gen or "stop" in tb_gen or "error to the orchestrator" in tb_gen


def test_no_bare_python_in_bash_blocks():
    """MED: agent/stage bash blocks must invoke the discovered interpreter
    ($PYTHON_EXE / ${PYTHON_EXE:-python3}), never bare `python` — macOS has no
    `python` on PATH, so a bare invocation silently fails (and false-fails
    hooks like the cocotb syntax check)."""
    import re
    files = list((_AGENTS_DIR).glob("*.md")) + list((_SKILL_DIR).glob("stage*.md"))
    bad = []
    for f in files:
        for ln in f.read_text(encoding="utf-8").splitlines():
            # bare `python -c`, `python -` (stdin), or `python "` at bash-line start
            if re.match(r"\s*python\s+-(c|vtkzY)?\b", ln) or re.match(r'\s*python\s+"', ln) \
                    or re.search(r"\|\s*python\s+-(c|vtkzY)?\b", ln):
                bad.append(f"{f.name}: {ln.strip()}")
    assert not bad, "bare `python` bash invocations remain:\n" + "\n".join(bad)


def test_no_gnu_only_grep_in_stage_docs():
    """MED: `grep -oP` (PCRE) is GNU-only and errors on macOS/BSD grep, silently
    disabling the coverage warning. Use `grep -oE` (ERE, portable) instead."""
    files = list((_SKILL_DIR).glob("stage*.md")) + list((_AGENTS_DIR).glob("*.md"))
    for f in files:
        content = f.read_text(encoding="utf-8")
        assert "grep -oP" not in content, f"{f.name} uses GNU-only `grep -oP`"


def test_templates_compile():
    """Templates must be syntactically valid Python (codegen pastes from them)."""
    import ast
    for name in ("cocotb_template.py", "golden_model_template.py"):
        src = (_SKILL_DIR / "templates" / name).read_text(encoding="utf-8")
        ast.parse(src)

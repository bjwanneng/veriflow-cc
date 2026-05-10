#!/usr/bin/env python3
"""
VeriFlow-CC Installer

Symlinks to ~/.claude/:
  - skills/vf-rtl/SKILL.md   — Pipeline orchestration skill (/vf-rtl)
  - agents/vf-architect.md        — Specification + golden model generation (Stage 1)
  - agents/vf-coder.md            — RTL code generation sub-agent (Stage 2)
  - agents/vf-linter.md           — Lint sub-agent (Stage 4)
  - agents/vf-synthesizer.md      — Synthesis sub-agent (Stage 4)

Pipeline: spec_golden → codegen → verify_fix → lint_synth

After installation, use /vf-rtl <project_dir> in Claude Code to drive the full RTL design pipeline.
"""

import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CLAUDE_DIR = Path.home() / ".claude"

# --- Skill ---
SKILL_SRC_DIR = PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
SKILL_DST_DIR = CLAUDE_DIR / "skills" / "vf-rtl"
SKILL_FILES = ["SKILL.md", "state.py", "init.py", "vcd2table.py", "cocotb_runner.py", "iverilog_runner.py", "timing_contract_checker.py", "bug_patterns.md", "design_rules.md", "error_recovery.md"]
TEMPLATES_DIR = "templates"

# --- veriflow_dsl Python package ---
# Symlinked into SKILL_DST_DIR/veriflow_dsl so that skill scripts and the
# user's project (which sources eda_env.sh, exporting PYTHONPATH=$SKILL_DIR)
# can `from veriflow_dsl import ...` and `python -m veriflow_dsl.trace_export`.
VERIFLOW_DSL_SRC = PROJECT_DIR / "src" / "veriflow_dsl"
VERIFLOW_DSL_DST_NAME = "veriflow_dsl"

# Source for coding_style.md is now in the skill directory itself
CODING_STYLE_SRC = PROJECT_DIR / "src" / "claude_skills" / "vf-rtl" / "coding_style.md"
CODING_STYLE_DST_NAME = "coding_style.md"

# --- Sub-agents ---
AGENTS_DST_DIR = CLAUDE_DIR / "agents"
AGENTS_SRC_DIR = PROJECT_DIR / "src" / "claude_agents"

AGENT_FILES = [
    "vf-architect.md",
    "vf-spec-gen.md",
    "vf-golden-gen.md",
    "vf-coder.md",
    "vf-tb-gen.md",
    "vf-linter.md",
    "vf-synthesizer.md",
]


def main():
    if "--uninstall" in sys.argv:
        removed = 0

        # Remove old stage files (cleanup from 8-stage era)
        stages_dst = SKILL_DST_DIR / "stages"
        if stages_dst.exists():
            for f in stages_dst.iterdir():
                f.unlink()
                print(f"  Removed stage: {f.name}")
                removed += 1
            stages_dst.rmdir()

        # Remove skill (symlinks or copies)
        for name in SKILL_FILES + [CODING_STYLE_DST_NAME]:
            dst = SKILL_DST_DIR / name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
                print(f"  Removed skill: vf-rtl/{name}")
                removed += 1
        # Remove templates
        templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
        if templates_dst.exists():
            for f in templates_dst.iterdir():
                if f.is_file() or f.is_symlink():
                    f.unlink()
                    print(f"  Removed template: {f.name}")
                    removed += 1
            templates_dst.rmdir()

        # Remove veriflow_dsl/ symlink (or directory copy fallback)
        dsl_dst = SKILL_DST_DIR / VERIFLOW_DSL_DST_NAME
        if dsl_dst.is_symlink() or dsl_dst.exists():
            if dsl_dst.is_symlink() or dsl_dst.is_file():
                dsl_dst.unlink()
            else:
                # Directory copy fallback (Windows without symlink permission)
                import shutil as _sh
                _sh.rmtree(dsl_dst)
            print(f"  Removed package: veriflow_dsl/")
            removed += 1

        if SKILL_DST_DIR.exists():
            try:
                SKILL_DST_DIR.rmdir()
                skills_dir = CLAUDE_DIR / "skills"
                if skills_dir.exists() and not any(skills_dir.iterdir()):
                    skills_dir.rmdir()
                    print("  Removed empty ~/.claude/skills/ directory")
            except OSError:
                pass

        # Remove agents (symlinks or copies)
        for name in AGENT_FILES:
            dst = AGENTS_DST_DIR / name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
                print(f"  Removed agent: {name}")
                removed += 1

        if removed == 0:
            print("Nothing to uninstall.")
        else:
            print(f"\nUninstalled {removed} items from {CLAUDE_DIR}/")
        return 0

    # --- Install ---
    print(f"Installing to {CLAUDE_DIR}/\n")

    # 0. Clean up old agents that are no longer used
    LEGACY_AGENTS = [
        "vf-skill-d.md", "vf-lint.md", "vf-sim.md", "vf-synth.md",
        "vf-debugger.md", "vf-simulator.md",
        "vf-reviewer.md", "vf-microarch.md", "vf-timing.md",
    ]
    cleaned = 0
    for name in LEGACY_AGENTS:
        dst = AGENTS_DST_DIR / name
        if dst.exists():
            dst.unlink()
            print(f"  [clean]  Removed legacy agent: {name}")
            cleaned += 1
    if cleaned:
        print()

    # 0b. Clean up old stage files from 8-stage era
    old_stages_dst = SKILL_DST_DIR / "stages"
    if old_stages_dst.exists():
        for f in old_stages_dst.iterdir():
            f.unlink()
            print(f"  [clean]  Removed old stage: {f.name}")
            cleaned += 1
        old_stages_dst.rmdir()
        if cleaned:
            print()

    def _symlink(src: Path, dst: Path, label: str):
        """Create or overwrite a symlink from dst → src."""
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        dst.symlink_to(src.resolve())
        print(f"  [{label}]  {src.name}  →  {dst}")

    # 1. Install skill (symlink: SKILL.md + state.py + support files)
    SKILL_DST_DIR.mkdir(parents=True, exist_ok=True)
    skill_installed = 0
    for name in SKILL_FILES:
        src = SKILL_SRC_DIR / name
        dst = SKILL_DST_DIR / name
        if src.exists():
            _symlink(src, dst, "skill")
            skill_installed += 1
        else:
            print(f"  [skip]   vf-rtl/{name} not found at {src}")

    # 1b. Install coding_style.md (symlink)
    if CODING_STYLE_SRC.exists():
        dst = SKILL_DST_DIR / CODING_STYLE_DST_NAME
        _symlink(CODING_STYLE_SRC, dst, "skill")
        skill_installed += 1
    else:
        print(f"  [skip]   vf-rtl/{CODING_STYLE_DST_NAME} not found at {CODING_STYLE_SRC}")

    # 1c. Install templates (symlink each template file)
    templates_src = SKILL_SRC_DIR / TEMPLATES_DIR
    templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
    if templates_src.exists():
        templates_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(templates_src.iterdir()):
            if f.is_file():
                dst = templates_dst / f.name
                _symlink(f, dst, "tmpl")
                skill_installed += 1
    else:
        print(f"  [skip]   vf-rtl/{TEMPLATES_DIR}/ not found at {templates_src}")

    # 1d. Install veriflow_dsl/ as a sibling package under SKILL_DST_DIR.
    # `python -m veriflow_dsl.<x>` must resolve once SKILL_DST_DIR is on
    # PYTHONPATH (init.py wires that into eda_env.sh).
    dsl_dst = SKILL_DST_DIR / VERIFLOW_DSL_DST_NAME
    if VERIFLOW_DSL_SRC.is_dir():
        # Remove anything previously placed here (file, symlink, or stale dir).
        if dsl_dst.is_symlink() or dsl_dst.is_file():
            dsl_dst.unlink()
        elif dsl_dst.is_dir():
            import shutil as _sh
            _sh.rmtree(dsl_dst)
        try:
            dsl_dst.symlink_to(VERIFLOW_DSL_SRC.resolve(), target_is_directory=True)
            print(f"  [pkg]    veriflow_dsl/  →  {dsl_dst}")
            skill_installed += 1
        except (OSError, NotImplementedError) as e:
            # Windows non-admin: fall back to directory copy.
            import shutil as _sh
            _sh.copytree(VERIFLOW_DSL_SRC, dsl_dst)
            print(f"  [pkg]    veriflow_dsl/  copied to {dsl_dst} (symlink unavailable: {e})")
            skill_installed += 1
    else:
        print(f"  [skip]   veriflow_dsl/ source missing at {VERIFLOW_DSL_SRC}")

    # 2. Install sub-agents (symlink)
    AGENTS_DST_DIR.mkdir(parents=True, exist_ok=True)
    installed = 0
    missing = 0
    for name in AGENT_FILES:
        src = AGENTS_SRC_DIR / name
        dst = AGENTS_DST_DIR / name
        if not src.exists():
            print(f"  [skip]   {name}  (source not found)")
            missing += 1
            continue
        _symlink(src, dst, "agent")
        installed += 1

    print(f"\n{'='*50}")
    print(f"  Installed: {skill_installed} skill files + {installed} agents")
    if missing:
        print(f"  Skipped: {missing} (source files missing)")
    print(f"{'='*50}")

    # 3. Post-install verification
    print(f"\n[verify] Running post-install checks...")
    verify_errors = []

    # 3a. Check agent tools field format (must be comma-separated, not YAML list)
    for agent_name in AGENT_FILES:
        agent_dst = AGENTS_DST_DIR / agent_name
        if agent_dst.exists():
            content = agent_dst.read_text(encoding="utf-8")
            # Detect YAML list format (bad): "tools:\n  - read"
            if "\ntools:\n  -" in content or "\ntools:\n- " in content:
                verify_errors.append(
                    f"  [FAIL] {agent_name}: 'tools' field uses YAML list format — "
                    f"must be comma-separated (e.g. 'tools: Read, Write, Glob, Grep, Bash'). "
                    f"See GitHub #12392."
                )
            elif re.search(r'tools:\s*\w+.*,\s*\w+', content):
                print(f"  [OK]   {agent_name}: tools field format correct")
            else:
                verify_errors.append(
                    f"  [WARN] {agent_name}: could not confirm 'tools' field format — "
                    f"verify manually that it is comma-separated"
                )
        else:
            verify_errors.append(f"  [FAIL] {agent_name} not found at {agent_dst}")

    # 3b. Check templates directory
    expected_templates = [
        "spec_template.json",
        "golden_model_template.py",
        "tb_integration_template.v",
        "cocotb_template.py",
    ]
    for tname in expected_templates:
        tfile = templates_dst / tname
        if tfile.exists():
            print(f"  [OK]   templates/{tname} present")
        else:
            verify_errors.append(f"  [FAIL] templates/{tname} missing at {tfile}")

    # 3c. Check state.py is present
    state_dst = SKILL_DST_DIR / "state.py"
    if state_dst.exists():
        print(f"  [OK]   state.py present")
    else:
        verify_errors.append(f"  [FAIL] state.py missing at {state_dst}")

    # 3d. Check vcd2table.py is present
    vcd2table_dst = SKILL_DST_DIR / "vcd2table.py"
    if vcd2table_dst.exists():
        print(f"  [OK]   vcd2table.py present")
    else:
        verify_errors.append(f"  [FAIL] vcd2table.py missing at {vcd2table_dst}")

    # 3e. Check cocotb_runner.py is present
    cocotb_runner_dst = SKILL_DST_DIR / "cocotb_runner.py"
    if cocotb_runner_dst.exists():
        print(f"  [OK]   cocotb_runner.py present")
    else:
        verify_errors.append(f"  [FAIL] cocotb_runner.py missing at {cocotb_runner_dst}")

    # 3f. Check iverilog_runner.py is present
    iverilog_runner_dst = SKILL_DST_DIR / "iverilog_runner.py"
    if iverilog_runner_dst.exists():
        print(f"  [OK]   iverilog_runner.py present")
    else:
        verify_errors.append(f"  [FAIL] iverilog_runner.py missing at {iverilog_runner_dst}")

    # 3g. Check veriflow_dsl/__init__.py reachable through skill dir
    dsl_init = SKILL_DST_DIR / VERIFLOW_DSL_DST_NAME / "__init__.py"
    dsl_trace = SKILL_DST_DIR / VERIFLOW_DSL_DST_NAME / "trace_export.py"
    if dsl_init.exists() and dsl_trace.exists():
        print(f"  [OK]   veriflow_dsl/ package present")
    else:
        verify_errors.append(
            f"  [FAIL] veriflow_dsl/ package missing under {SKILL_DST_DIR}/ "
            f"(__init__.py={dsl_init.exists()}, trace_export.py={dsl_trace.exists()})"
        )

    if verify_errors:
        print(f"\n[verify] Issues found:")
        for err in verify_errors:
            print(err)
        print(f"\n[verify] Fix the above issues before running /vf-rtl")
    else:
        print(f"\n[verify] All checks passed.")

    print(f"\nUsage: /vf-rtl <project_dir>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

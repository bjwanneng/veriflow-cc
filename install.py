#!/usr/bin/env python3
"""
VeriFlow-CC Installer

Installs to ~/.claude/:
  - skills/vf-pipeline/SKILL.md   — Pipeline orchestration skill (/vf-pipeline)
  - agents/vf-coder.md            — RTL code generation sub-agent (Stage 4)
  - agents/vf-reviewer.md         — Static analysis sub-agent (Stage 5)
  - agents/vf-linter.md           — Lint sub-agent (Stage 6)
  - agents/vf-synthesizer.md      — Synthesis sub-agent (Stage 8)

After installation, use /vf-pipeline <project_dir> in Claude Code to drive the full RTL design pipeline.
"""

import re
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CLAUDE_DIR = Path.home() / ".claude"

# --- Skill ---
SKILL_SRC_DIR = PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
SKILL_DST_DIR = CLAUDE_DIR / "skills" / "vf-pipeline"
SKILL_FILES = ["SKILL.md", "state.py", "vcd2table.py", "cocotb_runner.py", "bug_patterns.md", "design_rules.md"]
STAGES_DIR = "stages"
TEMPLATES_DIR = "templates"

# Source for coding_style.md is now in the skill directory itself
CODING_STYLE_SRC = PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline" / "coding_style.md"
CODING_STYLE_DST_NAME = "coding_style.md"

# --- Sub-agents ---
AGENTS_DST_DIR = CLAUDE_DIR / "agents"
AGENTS_SRC_DIR = PROJECT_DIR / "src" / "claude_agents"

AGENT_FILES = [
    "vf-architect.md",
    "vf-microarch.md",
    "vf-timing.md",
    "vf-coder.md",
    "vf-reviewer.md",
    "vf-linter.md",
    "vf-synthesizer.md",
]


def main():
    if "--uninstall" in sys.argv:
        removed = 0

        # Remove stage files
        stages_dst = SKILL_DST_DIR / STAGES_DIR
        if stages_dst.exists():
            for f in stages_dst.iterdir():
                f.unlink()
                print(f"  Removed stage: {f.name}")
                removed += 1
            stages_dst.rmdir()

        # Remove skill
        for name in SKILL_FILES + [CODING_STYLE_DST_NAME]:
            dst = SKILL_DST_DIR / name
            if dst.exists():
                dst.unlink()
                print(f"  Removed skill: vf-pipeline/{name}")
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

        # Remove agents
        for name in AGENT_FILES:
            dst = AGENTS_DST_DIR / name
            if dst.exists():
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
        "vf-debugger.md",
        "vf-simulator.md",
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

    # 1. Install skill (SKILL.md + state.py)
    SKILL_DST_DIR.mkdir(parents=True, exist_ok=True)
    skill_installed = 0
    for name in SKILL_FILES:
        src = SKILL_SRC_DIR / name
        dst = SKILL_DST_DIR / name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  [skill]  vf-pipeline/{name}  →  {dst}")
            skill_installed += 1
        else:
            print(f"  [skip]   vf-pipeline/{name} not found at {src}")

    # 1b. Install coding_style.md to skill directory
    if CODING_STYLE_SRC.exists():
        dst = SKILL_DST_DIR / CODING_STYLE_DST_NAME
        shutil.copy2(CODING_STYLE_SRC, dst)
        print(f"  [skill]  vf-pipeline/{CODING_STYLE_DST_NAME}  →  {dst}")
        skill_installed += 1
    else:
        print(f"  [skip]   vf-pipeline/{CODING_STYLE_DST_NAME} not found at {CODING_STYLE_SRC}")

    # 1c. Install stage files
    stages_src = SKILL_SRC_DIR / STAGES_DIR
    stages_dst = SKILL_DST_DIR / STAGES_DIR
    if stages_src.exists():
        stages_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(stages_src.glob("stage_*.md")):
            dst = stages_dst / f.name
            shutil.copy2(f, dst)
            print(f"  [stage]  vf-pipeline/{STAGES_DIR}/{f.name}  →  {dst}")
            skill_installed += 1
    else:
        print(f"  [skip]   vf-pipeline/{STAGES_DIR}/ not found at {stages_src}")

    # 1d. Install templates
    templates_src = SKILL_SRC_DIR / TEMPLATES_DIR
    templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
    if templates_src.exists():
        templates_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(templates_src.iterdir()):
            if f.is_file():
                dst = templates_dst / f.name
                shutil.copy2(f, dst)
                print(f"  [tmpl]   vf-pipeline/{TEMPLATES_DIR}/{f.name}  →  {dst}")
                skill_installed += 1
    else:
        print(f"  [skip]   vf-pipeline/{TEMPLATES_DIR}/ not found at {templates_src}")

    # 2. Install sub-agents
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
        shutil.copy2(src, dst)
        print(f"  [agent]  {name}  →  {dst}")
        installed += 1

    print(f"\n{'='*50}")
    print(f"  Installed: {skill_installed} skill files + {installed} agent/support")
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

    # 3b. Check stage files (4-8 are active; 1-3 are deprecated stubs)
    for i in range(1, 9):
        stage_file = SKILL_DST_DIR / STAGES_DIR / f"stage_{i}.md"
        if stage_file.exists():
            if i <= 3:
                # Check if it's a deprecated stub
                content = stage_file.read_text(encoding="utf-8")
                if "DEPRECATED" in content:
                    print(f"  [OK]   stage_{i}.md present (deprecated stub)")
                else:
                    print(f"  [WARN] stage_{i}.md is NOT a deprecated stub — should be replaced")
            else:
                print(f"  [OK]   stage_{i}.md present")
        else:
            if i <= 3:
                print(f"  [OK]   stage_{i}.md absent (deprecated)")
            else:
                verify_errors.append(f"  [FAIL] stage_{i}.md missing at {stage_file}")

    # 3b2. Check templates directory
    templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
    expected_templates = [
        "spec_template.json",
        "behavior_spec_template.md",
        "golden_model_template.py",
        "timing_model_template.yaml",
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

    if verify_errors:
        print(f"\n[verify] Issues found:")
        for err in verify_errors:
            print(err)
        print(f"\n[verify] Fix the above issues before running /vf-pipeline")
    else:
        print(f"\n[verify] All checks passed.")

    print(f"\nUsage: /vf-pipeline <project_dir>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

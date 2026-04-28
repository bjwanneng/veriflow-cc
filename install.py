#!/usr/bin/env python3
"""
VeriFlow-CC Installer

Installs to ~/.claude/:
  - skills/pipeline/SKILL.md   — Pipeline orchestration skill (/pipeline)
  - agents/vf-coder.md         — RTL code generation sub-agent

After installation, use /pipeline <project_dir> in Claude Code to drive the full RTL design pipeline.
"""

import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CLAUDE_DIR = Path.home() / ".claude"

# --- Skill ---
SKILL_SRC_DIR = PROJECT_DIR / ".claude" / "skills" / "vf-pipeline"
SKILL_DST_DIR = CLAUDE_DIR / "skills" / "vf-pipeline"
SKILL_FILES = ["SKILL.md", "state.py", "vcd2table.py"]
STAGES_DIR = "stages"

# Source for coding_style.md is in claude_agents/, but installed to skill dir
CODING_STYLE_SRC = PROJECT_DIR / "claude_agents" / "coding_style.md"
CODING_STYLE_DST_NAME = "coding_style.md"

# --- Sub-agents ---
AGENTS_DST_DIR = CLAUDE_DIR / "agents"
AGENTS_SRC_DIR = PROJECT_DIR / "claude_agents"

AGENT_FILES = [
    "vf-coder.md",
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
        "vf-architect.md", "vf-microarch.md", "vf-timing.md",
        "vf-skill-d.md", "vf-lint.md", "vf-sim.md", "vf-synth.md",
        "vf-debugger.md",
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

    # 3a. Check vf-coder.md tools field format (must be comma-separated, not YAML list)
    vf_coder_dst = AGENTS_DST_DIR / "vf-coder.md"
    if vf_coder_dst.exists():
        content = vf_coder_dst.read_text(encoding="utf-8")
        # Detect YAML list format (bad): "tools:\n  - read"
        if "\ntools:\n  -" in content or "\ntools:\n- " in content:
            verify_errors.append(
                f"  [FAIL] vf-coder.md: 'tools' field uses YAML list format — "
                f"must be comma-separated (e.g. 'tools: Read, Write, Glob, Grep, Bash'). "
                f"See GitHub #12392."
            )
        elif "tools: Read, Write" in content or "tools: Read,Write" in content:
            print(f"  [OK]   vf-coder.md: tools field format correct")
        else:
            verify_errors.append(
                f"  [WARN] vf-coder.md: could not confirm 'tools' field format — "
                f"verify manually that it is comma-separated"
            )
    else:
        verify_errors.append(f"  [FAIL] vf-coder.md not found at {vf_coder_dst}")

    # 3b. Check all 8 stage files are present
    for i in range(1, 9):
        stage_file = SKILL_DST_DIR / STAGES_DIR / f"stage_{i}.md"
        if stage_file.exists():
            print(f"  [OK]   stage_{i}.md present")
        else:
            verify_errors.append(f"  [FAIL] stage_{i}.md missing at {stage_file}")

    # 3c. Check state.py is present
    state_dst = SKILL_DST_DIR / "state.py"
    if state_dst.exists():
        print(f"  [OK]   state.py present")
    else:
        verify_errors.append(f"  [FAIL] state.py missing at {state_dst}")

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

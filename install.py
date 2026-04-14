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
SKILL_FILES = ["SKILL.md", "state.py"]

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
                (CLAUDE_DIR / "skills").rmdir()
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
    print(f"\nUsage: /pipeline <project_dir>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

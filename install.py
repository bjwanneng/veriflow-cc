#!/usr/bin/env python3
"""
VeriFlow-CC 安装脚本

将 claude_agents/ 下的所有 agent 定义文件安装到 ~/.claude/agents/。
安装后可在 Claude Code 中使用 /vf-pipeline 驱动完整 RTL 设计流水线。
"""

import shutil
import sys
from pathlib import Path

AGENTS_DIR = Path.home() / ".claude" / "agents"
SRC_DIR = Path(__file__).parent / "claude_agents"

# 所有 agent 定义文件
AGENT_FILES = [
    "vf-pipeline.md",    # 主控 agent
    "vf-architect.md",
    "vf-microarch.md",
    "vf-timing.md",
    "vf-coder.md",
    "vf-skill-d.md",
    "vf-lint.md",
    "vf-sim.md",
    "vf-synth.md",
    "vf-debugger.md",
]


def main():
    if "--uninstall" in sys.argv:
        removed = 0
        for name in AGENT_FILES:
            dst = AGENTS_DIR / name
            if dst.exists():
                dst.unlink()
                print(f"  Removed: {name}")
                removed += 1
        if removed == 0:
            print("No agents installed.")
        else:
            print(f"\nUninstalled {removed} agents.")
        return 0

    if not SRC_DIR.exists():
        print(f"Error: {SRC_DIR} not found")
        return 1

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    installed = 0
    missing = 0
    for name in AGENT_FILES:
        src = SRC_DIR / name
        dst = AGENTS_DIR / name
        if not src.exists():
            print(f"  SKIP: {name} (source file not found)")
            missing += 1
            continue
        shutil.copy2(src, dst)
        print(f"  OK: {name}")
        installed += 1

    print(f"\nInstalled {installed} agents to {AGENTS_DIR}/")
    if missing:
        print(f"Warning: {missing} agents skipped (source files missing)")

    print("\nUsage: in Claude Code, type /vf-pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())

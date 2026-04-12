#!/usr/bin/env python3
"""
VeriFlow-CC 安装脚本

将 vf-pipeline.md 安装到 ~/.claude/agents/，之后在 Claude Code 中
使用 /vf-pipeline 命令即可驱动完整 RTL 设计流水线。
"""

import shutil
import sys
from pathlib import Path

AGENTS_DIR = Path.home() / ".claude" / "agents"
AGENT_FILE = "vf-pipeline.md"
SRC = Path(__file__).parent / "claude_agents" / AGENT_FILE


def main():
    if not SRC.exists():
        print(f"Error: {SRC} not found")
        return 1

    if "--uninstall" in sys.argv:
        dst = AGENTS_DIR / AGENT_FILE
        if dst.exists():
            dst.unlink()
            print(f"Uninstalled: {dst}")
        else:
            print("Not installed")
        return 0

    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    dst = AGENTS_DIR / AGENT_FILE
    shutil.copy2(SRC, dst)
    print(f"Installed: {dst}")
    print(f"\nUsage: in Claude Code, type /vf-pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())

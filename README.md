# VeriFlow-CC

**Claude Code-driven RTL design pipeline** — zero Python dependencies, Claude Code main session is the driver.

## What It Is

VeriFlow-CC treats Claude Code as the pipeline brain: the main Claude Code session controls stage transitions, calls sub-agents to execute tasks, and handles errors and rollbacks.

Differences from the full VeriFlow-Agent:
- No LangGraph / LangChain / Streamlit
- No `pip install` required
- Claude Code itself is the interaction and decision layer
- State persisted to JSON, recoverable after `/clear`

## Architecture

```
User types /pipeline <project_dir>
     ↓
Main Claude (skill prompt injected)
     │
     ├→ Agent(vf-architect)  → Bash Hook verify spec.json
     ├→ Agent(vf-microarch)  → Bash Hook verify micro_arch.md
     ├→ Agent(vf-timing)     → Bash Hook verify timing_model.yaml + tb_*.v
     ├→ Agent(vf-coder)      → Bash Hook verify rtl/*.v
     ├→ Agent(vf-skill-d)    → Bash Hook verify static_report.json
     ├→ Agent(vf-lint)       → Bash Hook verify iverilog pass
     ├→ Agent(vf-sim)        → Bash Hook verify simulation pass
     └→ Agent(vf-synth)      → Bash Hook verify synth_report.txt
          │
          └→ Hook fail → Agent(vf-debugger) fix → retry
```

**1-layer nesting**: Main Claude calls sub-agents directly, no intermediate pipeline agent.

## Quick Start

### 1. Install

```bash
python install.py
```

Installs to `~/.claude/`:
- `skills/pipeline/SKILL.md` — Pipeline orchestration skill
- `agents/vf-*.md` — 9 sub-agent definitions

### 2. Prepare Project Directory

```
my_alu/
└── requirement.md    # Write design requirements
```

### 3. Run in Claude Code

```
/pipeline /path/to/my_alu
```

## Pipeline Stages

Strict sequential execution, no skipping:

```
architect -> microarch -> timing -> coder -> skill_d -> lint -> sim -> synth
     1           2          3         4         5        6     7      8
```

| Stage | Type | Input | Output |
|-------|------|-------|--------|
| architect | LLM | requirement.md | spec.json |
| microarch | LLM | spec.json | micro_arch.md |
| timing | LLM | spec.json, micro_arch.md | timing_model.yaml, testbench |
| coder | LLM | spec + timing + microarch | rtl/*.v |
| skill_d | LLM | rtl/*.v | Quality score |
| lint | EDA | rtl/*.v | Syntax check |
| sim | EDA | rtl/*.v, tb/*.v | Simulation results |
| synth | EDA | rtl/*.v | Synthesis report |

## Error Recovery

```
stage fails
  |-- 1st failure -> debugger fixes -> retry stage
  |-- 2nd failure -> debugger -> rollback to earlier stage -> re-run
  +-- 3rd failure -> pause, notify user
```

Rollback rules: syntax errors → coder, logic errors → microarch, timing errors → timing.

## Session Recovery

After `/clear` or a new session, `/pipeline <project_dir>` automatically restores from `pipeline_state.json`:
- `stages_completed` — list of completed stages
- `stage_summaries` — one-line summary per stage
- `next_stage()` — the next stage to execute

## File Structure

```
veriflow-cc/
├── .claude/
│   └── skills/
│       └── pipeline/
│           └── SKILL.md        # Pipeline orchestration skill (/pipeline)
├── state.py                    # State management (JSON persistence + order validation)
├── install.py                  # Install agents + skill to ~/.claude/
├── claude_agents/              # Sub-agent definitions
│   ├── vf-architect.md
│   ├── vf-microarch.md
│   ├── vf-timing.md
│   ├── vf-coder.md
│   ├── vf-skill-d.md
│   ├── vf-lint.md
│   ├── vf-sim.md
│   ├── vf-synth.md
│   └── vf-debugger.md
├── tests/
│   └── test_state.py           # Tests: ordering, summaries, rollback, persistence
└── my_project/
    └── requirement.md          # Sample project
```

## Dependencies

- Python 3.10+ (for state.py only)
- Claude Code (logged in)
- `iverilog` / `vvp` (optional, skip sim if unavailable)
- `yosys` (optional, skip synth if unavailable)

**No pip install required.**

## Tests

```bash
python tests/test_state.py
```

## Uninstall

```bash
python install.py --uninstall
```

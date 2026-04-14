# VeriFlow-CC

**Claude Code-driven RTL design pipeline** — zero Python dependencies, Claude Code main session is the driver.

## What It Is

VeriFlow-CC treats Claude Code as the pipeline brain: the main Claude Code session controls stage transitions, calls a sub-agent for RTL generation, and handles errors and rollbacks.

Differences from the full VeriFlow-Agent:
- No LangGraph / LangChain / Streamlit
- No `pip install` required
- Claude Code itself is the interaction and decision layer
- State persisted to JSON, recoverable after session restart

## Architecture

```
User types /vf-pipeline <project_dir>
     ↓
Main Claude (skill prompt injected)
     │
     ├→ Stage 1: architect   (inline) → spec.json
     ├→ Stage 2: microarch   (inline) → micro_arch.md
     ├→ Stage 3: timing      (inline) → timing_model.yaml + testbench
     ├→ Stage 4: coder       (vf-coder sub-agent) → rtl/*.v
     ├→ Stage 5: skill_d     (inline) → static_report.json
     ├→ Stage 6: lint        (inline, iverilog) → logs/lint.log
     ├→ Stage 7: sim         (inline, iverilog+vvp) → logs/sim.log
     └→ Stage 8: synth       (inline, yosys) → workspace/synth/synth_report.txt
```

**1-layer nesting**: Only Stage 4 (coder) calls the vf-coder sub-agent. All other stages execute inline in the main session.

## Quick Start

### 1. Install

```bash
python install.py
```

Installs to `~/.claude/`:
- `skills/vf-pipeline/SKILL.md` — Pipeline orchestration skill
- `skills/vf-pipeline/state.py` — State management
- `skills/vf-pipeline/coding_style.md` — Verilog coding style rules
- `agents/vf-coder.md` — RTL code generation sub-agent

### 2. Prepare Project Directory

```
my_alu/
└── requirement.md    # Write design requirements
```

### 3. Run in Claude Code

```
/vf-pipeline /path/to/my_alu
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
| coder | LLM (sub-agent) | spec + coding_style | rtl/*.v |
| skill_d | LLM | rtl/*.v | static_report.json |
| lint | EDA (iverilog) | rtl/*.v | logs/lint.log |
| sim | EDA (iverilog+vvp) | rtl/*.v, tb/*.v | logs/sim.log |
| synth | EDA (yosys) | rtl/*.v | workspace/synth/synth_report.txt |

## Key Features

### Status Bar Progress
Pipeline stages appear as a todo list in Claude Code's status bar. Current stage shows a spinner, completed stages get checkmarks.

### Requirements Clarification (Stage 1)
The pipeline checks a 9-item clarity checklist before generating spec.json. If any item is ambiguous, it asks the user one question at a time using AskUserQuestion.

### Persistent EDA Environment
EDA tool paths (iverilog, vvp, yosys) are discovered once in Step 0 and saved to `.veriflow/eda_env.sh`. Every subsequent EDA command sources this file, avoiding the "PATH doesn't persist between Bash calls" issue.

### Structured Logging
All EDA outputs are saved to log files for post-run analysis:
- `logs/lint.log` — iverilog syntax check output
- `logs/compile.log` — compilation output
- `logs/sim.log` — simulation output
- `workspace/synth/synth_report.txt` — yosys synthesis report

### Sim Hook Verification
The simulation hook checks `logs/sim.log` for actual PASS/FAIL strings. It does not pass when simulations had assertion failures (prevents false-positive pipeline completion).

### Error Recovery
- **3-retry budget**: Stops after 3 failed fix attempts and asks user for help
- **Testbench rule**: TB infrastructure bugs may be fixed; assertions must not be weakened
- Rollback: syntax errors → coder, logic errors → microarch, timing errors → timing

## Project Output Structure

```
my_project/
├── requirement.md
├── .veriflow/
│   ├── pipeline_state.json      # Pipeline state (resumable)
│   └── eda_env.sh               # EDA tool paths (auto-generated)
├── logs/
│   ├── lint.log                 # iverilog lint output
│   ├── compile.log              # Compilation output
│   └── sim.log                  # Simulation output
└── workspace/
    ├── docs/
    │   ├── spec.json            # Design specification
    │   ├── micro_arch.md        # Microarchitecture document
    │   ├── timing_model.yaml    # Timing scenarios
    │   └── static_report.json   # Static analysis report
    ├── rtl/                     # Generated Verilog files
    ├── tb/                      # Testbench (generated in Stage 3)
    ├── sim/                     # Compiled simulation (tb.vvp)
    └── synth/
        └── synth_report.txt     # Yosys synthesis report
```

## File Structure (Source)

```
veriflow-cc/
├── .claude/
│   └── skills/
│       └── vf-pipeline/
│           ├── SKILL.md          # Pipeline orchestration skill
│           ├── state.py          # State machine (JSON persistence)
│           └── coding_style.md   # Verilog-2005 coding rules
├── claude_agents/
│   ├── vf-coder.md              # RTL code generation sub-agent
│   └── coding_style.md          # Coding style reference
├── install.py                   # Install skill + agent to ~/.claude/
├── tests/
│   └── test_state.py            # State machine tests
├── CLAUDE.md                    # Claude Code project instructions
└── README.md                    # This file
```

## Dependencies

- Python 3.10+ (for state.py only, no pip packages)
- Claude Code (logged in)
- `iverilog` / `vvp` (optional, for lint/sim stages)
- `yosys` (optional, for synth stage)

**No pip install required.**

## Tests

```bash
python tests/test_state.py
```

## Uninstall

```bash
python install.py --uninstall
```

## Troubleshooting

### Sub-agent returns "0 tool uses"
Ensure the agent's `tools` field uses **comma-separated capitalized names**:
```yaml
# WRONG — causes silent tool permission failure
tools:
  - read
  - write

# CORRECT
tools: Read, Write, Glob, Grep, Bash
```
See [GitHub Issue #12392](https://github.com/anthropics/claude-code/issues/12392) for details.

### iverilog returns exit code 127
iverilog needs its internal drivers (`ivlpp.exe`, `ivl.exe`) which live in `lib/ivl/`. The pipeline auto-discovers and saves these paths. Verify with:
```bash
source .veriflow/eda_env.sh && iverilog -V
```

### Simulation passes but pipeline reports FAIL
The sim hook checks `logs/sim.log` for `FAIL` or `Error` strings. If your testbench prints those words in passing messages, rename them.

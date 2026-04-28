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
     ├→ Stage 1: architect   (inline) → spec.json + behavior_spec.md
     ├→ Stage 2: microarch   (inline) → micro_arch.md
     ├→ Stage 3: timing      (inline) → timing_model.yaml + testbenches (one per module)
     ├→ Stage 4: coder       (vf-coder sub-agent) → rtl/*.v
     ├→ Stage 5: skill_d     (inline) → static_report.json
     ├→ Stage 6: lint        (inline, iverilog) → logs/lint.log
     ├→ Stage 7: sim         (inline, iverilog+vvp) → two-phase bottom-up verification
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
├── requirement.md        # Functional requirements (required)
├── constraints.md        # Design constraints (optional)
├── design_intent.md      # Preliminary design ideas (optional)
└── context/              # Reference materials (optional)
    └── reference.md
```

**Input files**:

| File | Required | Description |
|------|----------|-------------|
| `requirement.md` | Yes | Functional requirements: what the design does |
| `constraints.md` | No | Timing, area, power, IO constraints |
| `design_intent.md` | No | Architecture preferences, IP reuse, design decisions |
| `context/*.md` | No | Reference materials, IP docs, datasheets |

If optional files are missing, the pipeline asks targeted clarification questions during Stage 1.

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
| architect | LLM | requirement.md, constraints.md, design_intent.md, context/ | spec.json + behavior_spec.md |
| microarch | LLM | spec.json, behavior_spec.md, requirement.md, design_intent.md | micro_arch.md |
| timing | LLM | spec.json, micro_arch.md, behavior_spec.md, context/*.py | timing_model.yaml, tb/*.v (one per module) |
| coder | LLM (sub-agent) | spec + behavior_spec + coding_style + micro_arch | rtl/*.v |
| skill_d | LLM | rtl/*.v, spec.json | static_report.json |
| lint | EDA (iverilog) | rtl/*.v | logs/lint.log |
| sim | EDA (iverilog+vvp) | rtl/*.v, tb/*.v | Phase 1: per-module unit sims → Phase 2: integration sim → logs/sim*.log |
| synth | EDA (yosys) | rtl/*.v | workspace/synth/synth_report.txt |

## Key Features

### Status Bar Progress
Pipeline stages appear as a todo list in Claude Code's status bar. Current stage shows a spinner, completed stages get checkmarks.

### Requirements Clarification (Stage 1)
The pipeline checks a structured clarity checklist in **seven categories** before generating spec.json and behavior_spec.md:
- **A. Functional**: module behavior, protocols, data format, FSM, clock domains
- **B. Constraints**: clock frequency, target device, area/power budget, IO standards
- **C. Design intent**: architecture style, module partitioning, interface preferences, IP reuse
- **D. Algorithm & Protocol**: algorithm references, pseudocode, key formulas, test vectors
- **E. Timing Completeness**: cycle-level behavior, latency, throughput, interface timing, reset recovery, backpressure
- **F. Domain Knowledge**: design domain, standard references, prerequisite concepts, test vectors
- **G. Information Completeness**: implicit assumptions, missing scenarios (meta-check)

Each item must be explicitly confirmed — no section-level skip. If any item is ambiguous, the pipeline asks the user one question at a time using AskUserQuestion.

### Behavior Specification (behavior_spec.md)
Stage 1 now produces a second artifact: `behavior_spec.md`. This document captures behavioral requirements that downstream stages (especially the coder) need:
- **Domain Knowledge**: background, key concepts, references, glossary
- **Cycle-Accurate Behavior**: per-module, per-cycle operation tables
- **FSM Specification**: states, transitions, initial state, outputs per state
- **Register Requirements**: name, width, reset value, purpose
- **Timing Contracts**: latency, throughput, backpressure, reset recovery
- **Algorithm Pseudocode**: verbatim from user input
- **Protocol Details**: signal sequence, setup/hold, error recovery
- **Cross-Module Timing**: pipeline stages, module-to-module latency, critical path

### Readiness Check Gate
Before proceeding past Stage 1, a **readiness_check** validates both spec.json and behavior_spec.md for completeness. If any check fails, the pipeline stops and asks the user for the missing information. This ensures the pipeline never proceeds with incomplete requirements.

### Persistent EDA Environment
EDA tool paths (iverilog, vvp, yosys) are discovered once in Step 0 and saved to `.veriflow/eda_env.sh`. Every subsequent EDA command sources this file, avoiding the "PATH doesn't persist between Bash calls" issue.

### Structured Logging
All EDA outputs are saved to log files for post-run analysis:
- `logs/lint.log` — iverilog syntax check output
- `logs/compile.log` — integration compilation output
- `logs/compile_<module>.log` — per-module compilation output (Phase 1)
- `logs/sim_<module>.log` — per-module simulation output (Phase 1)
- `logs/sim.log` — integration simulation output (Phase 2)
- `workspace/synth/synth_report.txt` — yosys synthesis report

### Sim Hook Verification
The simulation hook uses strict 3-layer verification on `logs/sim.log`:
1. File must exist and be non-empty
2. No lines matching `[FAIL]` or `FAILED:` prefix
3. Must contain an explicit `ALL TESTS PASSED` summary line

This prevents false-positive "all green" when sim.log contains both passing and failing tests, or is empty.

### Bottom-Up Simulation (Two-Phase)
Stage 7 runs in two phases with explicit per-module progress reporting:
- **Phase 1 — Per-module unit simulation**: Each submodule is compiled and simulated independently with its own testbench. Results are reported module-by-module. All modules must pass before Phase 2.
- **Phase 2 — Integration simulation**: Top-level testbench verifies the full design end-to-end.

Each module's simulation log is saved separately as `logs/sim_<module_name>.log`.

### Per-Module Testbenches (Stage 3)
Stage 3 generates a testbench for **every module** in spec.json, not just the top:
- Submodule testbenches test each module in isolation with known inputs/outputs
- Top module testbench does integration testing
- If a Python golden model exists in `context/*.py`, it is used to generate expected values

### Interface Lock
spec.json port definitions are locked after Stage 1. Port semantic fields enforce consistent interpretation across all stages:
- `reset_polarity`: `"active_high"` or `"active_low"` (reset ports must declare this)
- `handshake`: `"hold_until_ack"` | `"single_cycle"` | `"pulse"` (valid ports must declare this)
- `ack_port`: name of the associated ack input (required for `hold_until_ack`)

### Golden Model Integration
If a Python reference implementation exists in `context/*.py`:
- Stage 3 uses it to generate concrete expected values for testbenches
- Error recovery (Step 1.5) runs the golden model to extract step-by-step intermediate values for root cause comparison

### Pipeline Timing Discipline (coding_style.md Section 23)
The coding style guide includes a mandatory cycle-accurate timing table template and 6 key rules about register delays, control signal timing, FSM synchronization, counter ranges, and handshake behavior. The vf-coder sub-agent performs an internal 5-point self-check before writing any module.

### Error Recovery
- **Step 1.5 Structured Root Cause Analysis**: Before modifying any file, must complete a 5-point analysis (error location → signal trace → root cause hypothesis → minimal fix plan → impact scope) written to `stage_journal.md`
- **Golden model comparison**: If available, run golden model with failing test inputs and compare intermediate values with RTL output
- **3-retry budget**: Stops after 3 failed fix attempts and asks user for help
- **File control**: No new `.v` files during error recovery; debug artifacts cleaned up after each attempt
- **Testbench rule**: TB infrastructure bugs may be fixed; assertions must not be weakened
- Rollback: syntax errors → coder, logic errors → microarch, timing errors → timing

## Project Output Structure

```
my_project/
├── requirement.md               # Functional requirements (required)
├── constraints.md               # Timing, area, power, IO constraints (optional)
├── design_intent.md             # Architecture preferences, IP reuse (optional)
├── context/                     # Reference materials (optional)
├── .veriflow/
│   ├── pipeline_state.json      # Pipeline state (resumable)
│   └── eda_env.sh               # EDA tool paths (auto-generated)
├── logs/
│   ├── lint.log                 # iverilog lint output
│   ├── compile.log              # Integration compilation output
│   ├── compile_<module>.log     # Per-module compile output (Phase 1)
│   ├── sim_<module>.log         # Per-module simulation output (Phase 1)
│   └── sim.log                  # Integration simulation output (Phase 2)
└── workspace/
    ├── docs/
    │   ├── spec.json            # Interface specification (ports, constraints, connectivity)
	    │   ├── behavior_spec.md     # Behavioral specification (cycle behavior, FSM, timing contracts)
    │   ├── micro_arch.md        # Microarchitecture document
    │   ├── timing_model.yaml    # Timing scenarios
    │   └── static_report.json   # Static analysis report
    ├── rtl/                     # Generated Verilog files
    ├── tb/                      # Testbenches (one per module + top-level integration)
    ├── sim/                     # Compiled simulation (.vvp files)
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
│           ├── coding_style.md   # Verilog-2005 coding rules (22+ sections + timing discipline)
│           └── stages/           # Per-stage instruction files
│               ├── stage_1.md    # architect (spec.json + behavior_spec.md)
│               ├── stage_2.md    # microarch (micro_arch.md)
│               ├── stage_3.md    # timing (per-module testbenches)
│               ├── stage_4.md    # coder (vf-coder sub-agent dispatch)
│               ├── stage_5.md    # skill_d (static analysis)
│               ├── stage_6.md    # lint (iverilog)
│               ├── stage_7.md    # sim (two-phase bottom-up verification)
│               └── stage_8.md    # synth (yosys)
├── claude_agents/
│   ├── vf-coder.md              # RTL code generation sub-agent
│   └── coding_style.md          # Coding style reference (source, installed to skill dir)
├── install.py                   # Install skill + agent to ~/.claude/
├── tests/
│   ├── test_state.py            # State machine tests
│   └── test_behavior_spec.py    # behavior_spec.md and readiness check tests
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
python tests/test_behavior_spec.py
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
The sim hook uses strict 3-layer verification: (1) sim.log must be non-empty, (2) no `[FAIL]` or `FAILED:` lines, (3) must contain `ALL TESTS PASSED`. If your testbench prints `[FAIL]` in passing messages (e.g., "checking FAIL case"), use a different format to avoid triggering Layer 2.

## Contact

Add WeChat for more details and discussion:
<p align="center">
  <img src="images/Weixin-laozhang.jpg" width="300" alt="微信二维码">
</p>

### Email:bjzhangwn@gmail.com
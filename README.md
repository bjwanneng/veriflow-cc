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
User types /vf-rtl <project_dir>
     ↓
Main Claude (skill prompt injected)
     │
     ├→ Step 0: init + clarification → eda_env.sh, clarifications.md
     ├→ Stage 1: spec_golden  (vf-spec-golden merged agent)
     │            → spec.json + golden_model.py
     ├→ Stage 2: codegen      (vf-coder AI assembly per module, parallel)
     │            → rtl/*.v
     ├→ Stage 3: verify_fix   (inline sim + error recovery, 3-retry budget)
     │            → logs/sim.log, expected_trace_*.md, VCD analysis
     └→ Stage 4: lint_synth   (vf-linter + vf-synthesizer, parallel)
                  → logs/lint.log + synth_report.txt
```

**4 stages**: spec_golden → codegen → verify_fix → lint_synth. Sub-agents handle specialist work (RTL coding, lint, synthesis). Main session handles orchestration and error recovery.

## Quick Start

### 1. Install from Source

```bash
git clone https://github.com/bjwanneng/veriflow-cc.git
cd veriflow-cc
python install.py
```

Installs to `~/.claude/`:
- `skills/vf-rtl/SKILL.md` — Pipeline orchestration skill
- `skills/vf-rtl/state.py` — State management
- `skills/vf-rtl/vcd2table.py` — VCD waveform analysis
- `skills/vf-rtl/coding_style.md` — Verilog coding style rules
- `skills/vf-rtl/cocotb_runner.py` — Cocotb simulation runner
- `skills/vf-rtl/iverilog_runner.py` — Pure-Verilog simulation runner
- `skills/vf-rtl/timing_contract_checker.py` — Timing contract validator
- `agents/vf-coder.md` — RTL code generation sub-agent
- `agents/vf-spec-golden.md` — Spec + golden model generation sub-agent
- `agents/vf-tb-gen.md` — Testbench generation sub-agent
- `agents/vf-linter.md` — Lint sub-agent
- `agents/vf-synthesizer.md` — Synthesis sub-agent

Uninstall: `python install.py --uninstall`

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

If optional files are missing, the pipeline asks targeted clarification questions during Step 0.

### 3. Run in Claude Code

```
/vf-rtl /path/to/my_alu
```

## Pipeline Stages

Strict sequential execution, no skipping:

```
spec_golden → codegen → verify_fix → lint_synth
     1            2          3            4
```

| Stage | Type | Input | Output |
|-------|------|-------|--------|
| spec_golden | LLM (vf-spec-golden) | requirement.md, constraints.md, design_intent.md, context/ | spec.json + golden_model.py |
| codegen | vf-coder sub-agent (AI assembly per module, parallel) | spec.json, golden_model.py, coding_style.md | rtl/*.v |
| verify_fix | EDA (iverilog+vvp or cocotb) + error recovery | rtl/*.v, tb/*.v, golden_model.py | logs/sim.log, VCD waveform analysis, expected_trace_*.md |
| lint_synth | EDA (iverilog + yosys, parallel) | rtl/*.v | logs/lint.log + synth_report.txt |

## Key Features

### Golden Model (golden_model.py)

Stage 1 produces `golden_model.py` which serves as both reference model and test vector generator:
- Algorithm implementation with cycle-accurate trace output
- Test vectors validated against spec.json timing contracts
- Used by vcd2table.py for waveform diff during error recovery

### Inline Verilog Mini-Patterns

The vf-coder sub-agent includes 5 inline Verilog-2005 mini-patterns:
- **FSM** (three-block: state-reg + next-state + outputs)
- **Hash round** (single-cycle registered)
- **Pipeline register** (2-stage with valid passthrough)
- **Handshake** (hold_until_ack)
- **Barrel shifter** (variable-distance rotation, Verilog-2005 legal)

These give the LLM concrete register-transfer skeletons to adapt, eliminating the need for external reference implementations.

### Common Pitfalls + Pre-Write Self-Check

vf-coder.md includes 7 common pitfalls (P1–P7) from SM3 retrospective:
1. Combinational latches from incomplete `always @*`
2. `valid` pulse cleared one cycle too early
3. Missing `default` in FSM `case`
4. Counter rollover via implicit overflow
5. `valid` and `data` updated in different cycles
6. Using `_next` value as if it were a register
7. Reset polarity mix-up

Mandatory 7-point pre-write self-check ensures every module is verified before writing.

### Readiness Check Gate

Before proceeding past Stage 1, a readiness check validates spec.json and golden_model.py for completeness.

### Persistent EDA Environment

EDA tool paths (iverilog, vvp, yosys) are discovered once in Step 0 and saved to `.veriflow/eda_env.sh`. Every subsequent EDA command sources this file, avoiding the "PATH doesn't persist between Bash calls" issue. `eda_env.sh` also exports `PYTHONPATH` pointing at the installed skill directory, so helper scripts can import `state.py` without per-call `PYTHONPATH` prefixes.

### Structured Logging

All EDA outputs are saved to log files for post-run analysis:
- `logs/lint.log` — iverilog syntax check output
- `logs/sim.log` — integration simulation output
- `logs/sim.raw.log` — raw simulation output (iverilog_runner --save-raw-log)
- `logs/wave_diff.txt` — VCD vs golden model comparison
- `logs/wave_table.txt` — VCD waveform cycle table
- `logs/expected_trace_golden.md` — per-cycle register traces from golden_model.py (Stage 3 error recovery)
- `logs/timing_diagnostic.json` — bug classification + fix suggestions
- `logs/prev_failure_summary.md` — concise failure summary injected to next vf-coder retry
- `workspace/synth/synth_report.txt` — yosys synthesis report

### Sim Hook Verification

The simulation hook uses strict 3-layer verification on `logs/sim.log`:
1. File must exist and be non-empty
2. No lines matching `[FAIL]` or `FAILED:` prefix
3. Must contain an explicit `ALL TESTS PASSED` summary line

This prevents false-positive "all green" when sim.log contains both passing and failing tests, or is empty.

### Cocotb-First Integration Simulation

Stage 3 (verify_fix) uses cocotb (Python co-simulation) as the primary simulation path when available:
- cocotb's `await RisingEdge(dut.clk)` fires via VPI callback AFTER the NBA region, eliminating all Verilog TB-DUT race conditions
- Per-cycle internal register comparison against golden model trace
- Cycle-level timing contract assertions (registered output stability, pipeline delay)
- Falls back to Verilog `$display`-based testbenches when cocotb is unavailable

### Failure Feedback Loop

When simulation fails:
1. `timing_diagnostic.py` classifies the bug (A=computation, B=timing offset, D=initialization)
2. A concise `prev_failure_summary.md` is built with cycle, signal, expected, actual, and fix suggestion
3. This summary is injected into the next vf-coder retry via `PREV_FAILURE` field
4. The retry addresses the exact divergence before any other rewriting

### Interface Lock

spec.json port definitions are locked after Stage 1. Port semantic fields enforce consistent interpretation across all stages:
- `reset_polarity`: `"active_high"` only (reset ports must declare this)
- `handshake`: `"hold_until_ack"` | `"single_cycle"` | `"pulse"` (valid ports must declare this)
- `ack_port`: name of the associated ack input (required for `hold_until_ack`)

### Timing Contracts

spec.json includes machine-verifiable timing contracts for every inter-module connection:
- `producer_cycle`, `visible_cycle`, `consumer_cycle` — exact cycle relationships
- `same_cycle_visible`, `pipeline_delay_cycles` — registered vs combinational semantics
- `sample_phase` — posedge or negedge sampling, preventing TB/DUT races

### Error Recovery

- **Structured Root Cause Analysis**: Before modifying any file, must complete a 5-point analysis (error location → signal trace → root cause hypothesis → minimal fix plan → impact scope) written to `stage_journal.md`
- **Golden model comparison**: Run golden model with failing test inputs and compare intermediate values with RTL output
- **Per-cycle trace diff**: `logs/expected_trace_golden.md` (from golden_model.py) vs VCD-derived actual values — the fastest way to localise the wrong NBA assignment
- **Failure feedback injection**: `prev_failure_summary.md` is passed to next vf-coder retry targeting the exact divergence
- **3-retry budget**: Stops after 3 failed fix attempts and asks user for help
- **File control**: No new `.v` files during error recovery; debug artifacts cleaned up after each attempt
- **Testbench rule**: TB infrastructure bugs may be fixed; assertions must not be weakened

## Project Output Structure

```
my_project/
├── requirement.md               # Functional requirements (required)
├── constraints.md               # Timing, area, power, IO constraints (optional)
├── design_intent.md             # Architecture preferences, IP reuse (optional)
├── context/                     # Reference materials (optional)
├── .veriflow/
│   ├── pipeline_state.json      # Pipeline state (resumable)
│   └── eda_env.sh               # EDA tool paths + PYTHONPATH (auto-generated)
├── logs/
│   ├── lint.log                 # iverilog lint output
│   ├── sim.log                  # Integration simulation output
│   ├── sim.raw.log              # Raw simulation log
│   ├── wave_diff.txt            # VCD vs golden model comparison
│   ├── wave_table.txt           # VCD waveform cycle table
│   ├── expected_trace_golden.md # Per-cycle register traces from golden_model.py
│   ├── timing_diagnostic.json   # Bug classification + fix suggestions
│   └── prev_failure_summary.md  # Concise failure summary for retry
└── workspace/
    ├── docs/
    │   ├── spec.json            # Interface spec (ports, constraints, timing contracts)
    │   └── golden_model.py      # Reference model with cycle-accurate trace
    ├── rtl/                     # Generated Verilog files
    ├── tb/                      # Testbenches (one per module + integration)
    ├── sim/                     # Compiled simulation (.vvp files)
    └── synth/
        └── synth_report.txt     # Yosys synthesis report
```

## File Structure (Source)

```
veriflow-cc/
├── src/
│   ├── claude_skills/
│   │   └── vf-rtl/
│   │       ├── SKILL.md           # Pipeline orchestration skill
│   │       ├── state.py           # State machine (JSON persistence)
│   │       ├── init.py            # Project init (discovers EDA, writes eda_env.sh)
│   │       ├── vcd2table.py       # VCD waveform to cycle table converter
│   │       ├── iverilog_runner.py # Pure-Verilog simulation runner
│   │       ├── cocotb_runner.py   # Cocotb simulation runner
│   │       ├── timing_diagnostic.py  # Bug classification + fix suggestions
│   │       ├── timing_contract_checker.py
│   │       ├── error_recovery.md  # Stage 3 error recovery procedure
│   │       ├── design_rules.md    # Design rules for all stages
│   │       ├── coding_style.md    # Verilog-2005 coding rules
│   │       └── templates/         # Template files for sub-agents
│   │           ├── spec_template.json
│   │           ├── golden_model_template.py
│   │           ├── cocotb_template.py
│   │           └── tb_integration_template.v
│   └── claude_agents/
│       ├── vf-spec-golden.md      # Spec + golden model generation (Stage 1)
│       ├── vf-coder.md            # RTL code generation (Stage 2)
│       ├── vf-tb-gen.md           # Testbench generation
│       ├── vf-linter.md           # Lint sub-agent (Stage 4)
│       └── vf-synthesizer.md      # Synthesis sub-agent (Stage 4)
├── install.py                     # Python installer (symlinks to ~/.claude/)
├── tests/                         # Test suite (pytest + unittest)
├── CLAUDE.md                      # Claude Code project instructions
└── README.md                      # This file
```

## Dependencies

- Python 3.10+ (for state.py, no pip packages)
- Claude Code (logged in)
- `iverilog` / `vvp` (optional, for lint/sim stages)
- `yosys` (optional, for synth stage)

**No pip install required.**

## Tests

Run all tests:

```bash
python -m pytest tests/ -q
```

Or with unittest:

```bash
python -m unittest discover tests -v
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
iverilog needs its internal drivers (`ivlpp`, `ivl`) which live in `lib/ivl/`. The pipeline auto-discovers and saves these paths. Verify with:
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

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
     ├→ Stage 1: spec_golden  (vf-spec-gen → vf-golden-gen → vf-architect)
     │            → spec.json + timing_model.py + golden_model.py
     ├→ Stage 2: codegen      (dual-path: DSL emit or vf-coder AI assembly)
     │            → rtl/*.v
     ├→ Stage 3: verify_fix   (inline sim + error recovery, 3-retry budget)
     │            → logs/sim.log, expected_trace_*.md, VCD analysis
     └→ Stage 4: lint_synth   (vf-linter + vf-synthesizer, parallel)
                  → logs/lint.log + synth_report.txt
```

**4 stages**: spec_golden → codegen → lint_synth. Sub-agents handle specialist work (RTL coding, lint, synthesis). Main session handles orchestration and error recovery.

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
- `skills/vf-rtl/veriflow_dsl/` — Python DSL package (RegT/WireT protocol, emitter, simulator, trace exporter)
- `skills/vf-rtl/anchors/` — Reference implementations (timing_model.py + module.v + trace.md triples)
- `agents/vf-coder.md` — RTL code generation sub-agent

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
| spec_golden | LLM (vf-spec-gen → vf-golden-gen) | requirement.md, constraints.md, design_intent.md, context/ | spec.json + timing_model.py + golden_model.py |
| codegen | Dual-path: DSL emitter (zero AI) for simple modules; vf-coder sub-agent (AI assembly) for complex modules | spec.json, timing_model.py, golden_model.py, coding_style.md | rtl/*.v |
| verify_fix | EDA (iverilog+vvp or cocotb) + error recovery | rtl/*.v, tb/*.v, golden_model.py, timing_model.py | logs/sim.log, VCD waveform analysis, expected_trace_*.md |
| lint_synth | EDA (iverilog + yosys, parallel) | rtl/*.v | logs/lint.log + synth_report.txt |

## Key Features

### Timing Model (timing_model.py)

Stage 1 produces `timing_model.py` — a **machine-executable timing contract** written with typed NBA primitives (`RegT`, `WireT`, `RegAssign`):

- `RegT` — read-only register value at cycle T
- `WireT` — combinational signal, same-cycle visible
- `reg_next(target, next_value, en=cond)` — explicit NBA assignment

The structure enforces NBA timing at the Python level: it is impossible to return a `RegT` directly; register updates MUST go through `reg_next()`. This eliminates entire classes of timing bugs before RTL is even generated.

The `veriflow_spec` translatable subset is documented in `_spec.py` with 5 strict rules that keep the adapter lowering deterministic.

### Per-Cycle Trace Anchors

Every anchor under `anchors/` ships as a **triple**: `timing_model.py` + `module.v` + `trace.md`.

The `trace.md` is produced by running the timing_model through the DSL simulator and exporting a markdown cycle table. This gives the LLM:

- Concrete register values each cycle (not just code shape)
- Observable reset state and NBA delay behavior
- A direct few-shot mapping from Python expressions to Verilog constructs

vf-coder consumes these traces in Step 1.5 to ground its Python→Verilog translation in data, not just abstract rules.

### Golden Model (golden_model.py)

Stage 1 produces `golden_model.py` which serves as both reference model and test vector generator:
- Algorithm implementation with cycle-accurate trace output
- Test vectors validated against spec.json timing contracts
- Used by vcd2table.py for waveform diff during error recovery

### Readiness Check Gate

Before proceeding past Stage 1, a readiness check validates spec.json and golden_model.py for completeness.

### Persistent EDA Environment

EDA tool paths (iverilog, vvp, yosys) are discovered once in Step 0 and saved to `.veriflow/eda_env.sh`. Every subsequent EDA command sources this file, avoiding the "PATH doesn't persist between Bash calls" issue. `eda_env.sh` also exports `PYTHONPATH` pointing at the installed skill directory, so `python -m veriflow_dsl.trace_export` works without per-call `PYTHONPATH=src` prefixes.

### Structured Logging

All EDA outputs are saved to log files for post-run analysis:
- `logs/lint.log` — iverilog syntax check output
- `logs/sim.log` — integration simulation output
- `logs/sim.raw.log` — raw simulation output (iverilog_runner --save-raw-log)
- `logs/wave_diff.txt` — VCD vs golden model comparison
- `logs/wave_table.txt` — VCD waveform cycle table
- `logs/expected_trace_*.md` — per-cycle register traces from timing_model.py (Stage 3 error recovery)
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
- Only top-level integration test runs (no per-module unit tests) — catches cross-module timing bugs that unit tests miss
- Falls back to Verilog `$display`-based testbenches when cocotb is unavailable

### Per-Module Testbenches

Testbenches are generated for **every module** in spec.json, not just the top:
- Submodule testbenches test each module in isolation with known inputs/outputs
- Top module testbench does integration testing
- If a Python golden model exists in `context/*.py`, it is used to generate expected values

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

### Golden Model Integration

If a Python reference implementation exists in `context/*.py`:
- Stage 3 uses it to generate concrete expected values for testbenches
- Error recovery runs the golden model to extract step-by-step intermediate values for root cause comparison

### Pipeline Timing Discipline (coding_style.md Section 23)

The coding style guide includes a mandatory cycle-accurate timing table template and 6 key rules about register delays, control signal timing, FSM synchronization, counter ranges, and handshake behavior. The vf-coder sub-agent performs an internal 5-point self-check before writing any module.

### Error Recovery

- **Structured Root Cause Analysis**: Before modifying any file, must complete a 5-point analysis (error location → signal trace → root cause hypothesis → minimal fix plan → impact scope) written to `stage_journal.md`
- **Golden model comparison**: If available, run golden model with failing test inputs and compare intermediate values with RTL output
- **Per-cycle trace diff**: `logs/expected_trace_*.md` (from timing_model.py) vs VCD-derived actual values — the fastest way to localise the wrong NBA assignment
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
│   └── expected_trace_*.md      # Per-cycle register traces from timing_model.py
└── workspace/
    ├── docs/
    │   ├── spec.json            # Interface spec (ports, constraints, timing contracts)
    │   ├── timing_model.py      # Machine-executable NBA timing contract
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
│   ├── veriflow_dsl/              # Python DSL package (zero deps beyond Python 3.10+)
│   │   ├── __init__.py
│   │   ├── _spec.py               # RegT / WireT / RegAssign protocol
│   │   ├── _types.py              # Signal, Const, Cat, Mux
│   │   ├── _module.py             # Module / Domain / DomainCollection
│   │   ├── _adapter.py            # from_timing_model: @vf_block → DSL Module
│   │   ├── _emitter.py            # VerilogEmitter
│   │   ├── _simulator.py          # CycleSimulator
│   │   ├── trace_export.py        # Markdown trace exporter (lib + CLI)
│   │   └── lint_nba.py            # NBA static checker for Verilog-2005
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
│   │       ├── anchors/           # Reference triples (timing_model + module.v + trace.md)
│   │       │   ├── fsm_4state/
│   │       │   ├── shift_register/
│   │       │   ├── pipeline_register/
│   │       │   ├── hash_round_one_cycle/
│   │       │   ├── handshake_hold_until_ack/
│   │       │   ├── handshake_single_cycle/
│   │       │   └── barrel_shifter_var_n/
│   │       └── templates/         # Template files for sub-agents
│   │           ├── spec_template.json
│   │           ├── golden_model_template.py
│   │           ├── cocotb_template.py
│   │           └── tb_integration_template.v
│   └── claude_agents/
│       ├── vf-architect.md        # Spec + timing_model + golden model generation (Stage 1)
│       ├── vf-spec-gen.md
│       ├── vf-golden-gen.md
│       ├── vf-coder.md            # RTL code generation (Stage 2)
│       ├── vf-tb-gen.md           # Testbench generation
│       ├── vf-linter.md           # Lint sub-agent (Stage 4)
│       └── vf-synthesizer.md      # Synthesis sub-agent (Stage 4)
├── install.py                     # Python installer (symlinks to ~/.claude/)
├── tests/
│   ├── test_trace_export.py       # Trace exporter tests (unittest)
│   ├── test_anchor_traces.py      # Anchor trace drift guards (unittest)
│   ├── test_deployment_layout.py  # Install + init layout tests (unittest)
│   ├── test_lint_nba.py           # NBA lint tests (unittest)
│   ├── test_state.py              # State machine tests (pytest)
│   ├── test_vcd2table.py          # VCD table and golden diff tests (pytest)
│   ├── test_golden_model.py       # Golden model integration tests (pytest)
│   ├── test_sim_hook.py           # Sim hook verification tests (pytest)
│   └── test_flow_contracts.py     # Static contract tests for pipeline (pytest)
├── examples/
│   ├── counter_dsl.py             # Counter via DSL Module → Verilog emitter
│   └── counter_timing_model.py    # Counter via @vf_block → adapter → emitter
├── CLAUDE.md                      # Claude Code project instructions
└── README.md                      # This file
```

## Dependencies

- Python 3.10+ (for state.py and veriflow_dsl, no pip packages)
- Claude Code (logged in)
- `iverilog` / `vvp` (optional, for lint/sim stages)
- `yosys` (optional, for synth stage)

**No pip install required.**

## Tests

Run all unittest-discoverable tests (the primary test suite):

```bash
python -m unittest discover tests -v
```

Individual unittest test files:
```bash
python -m unittest tests.test_trace_export
python -m unittest tests.test_anchor_traces
python -m unittest tests.test_deployment_layout
python -m unittest tests.test_lint_nba
```

If `pytest` is available, the additional pytest-style tests can also be run:
```bash
python -m pytest tests/ -q
```

## Uninstall

```bash
python install.py --uninstall
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'veriflow_dsl'`

Run `init.py` (Step 0) in your project directory. It writes `.veriflow/eda_env.sh` with `PYTHONPATH` pointing at the installed skill directory. Every SKILL.md command sources this file, so `python -m veriflow_dsl.<x>` works automatically. Do not manually set `PYTHONPATH=src`.

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

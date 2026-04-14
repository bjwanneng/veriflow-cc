---
name: vf-pipeline
description: Use this skill to start or resume the VeriFlow RTL hardware design pipeline (architect to synth). Trigger this when the user asks to "run the RTL flow", "design hardware", or "start the pipeline". Pass the project directory path as the argument.
---

# RTL Pipeline Orchestrator

This skill IS the plan — execute each stage immediately using Read/Write/Bash tools. Do NOT plan before executing.

Project directory path: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user for it.

---

## Step 0: Initialization

Execute immediately:

```bash
PROJECT_DIR="$ARGUMENTS"
ls -la "$PROJECT_DIR/requirement.md" || { echo "ERROR: requirement.md not found"; exit 1; }
cd "$PROJECT_DIR" && mkdir -p workspace/docs workspace/rtl workspace/tb workspace/sim workspace/synth .veriflow logs

# Report available input files
echo "[INPUT] requirement.md: $(test -f requirement.md && echo YES || echo NO)"
echo "[INPUT] constraints.md: $(test -f constraints.md && echo YES || echo NO)"
echo "[INPUT] design_intent.md: $(test -f design_intent.md && echo YES || echo NO)"
echo "[INPUT] context/: $(ls context/*.md 2>/dev/null | wc -l) file(s)"
ls context/*.md 2>/dev/null || true

# Discover Python
PYTHON_EXE=$(which python3 2>/dev/null || which python 2>/dev/null || true)
if [ -z "$PYTHON_EXE" ]; then
    PYTHON_EXE=$(ls /c/Python*/python.exe /c/Users/*/AppData/Local/Programs/Python/*/python.exe 2>/dev/null | head -1)
fi
echo "[ENV] Python: ${PYTHON_EXE:-NOT FOUND}"

# Discover EDA tools — must include bin + lib + lib/ivl (iverilog needs ivlpp.exe and ivl.exe)
EDA_BIN=""
EDA_LIB=""
for base in /c/oss-cad-suite "/c/Program Files/iverilog" "/c/Program Files (x86)/iverilog"; do
    if [ -d "$base/bin" ]; then
        EDA_BIN="$base/bin"
        [ -d "$base/lib" ] && EDA_LIB="$base/lib"
        [ -d "$base/lib/ivl" ] && EDA_LIB="$base/lib:$base/lib/ivl"
        break
    fi
done

# Save env to file so every subsequent Bash call can source it
cat > "$PROJECT_DIR/.veriflow/eda_env.sh" << ENVEOF
export PYTHON_EXE="$PYTHON_EXE"
export EDA_BIN="$EDA_BIN"
export EDA_LIB="$EDA_LIB"
export PATH="$EDA_BIN:$EDA_LIB:\$PATH"
ENVEOF
echo "[ENV] Saved EDA env to .veriflow/eda_env.sh"
echo "[ENV] EDA_BIN=$EDA_BIN  EDA_LIB=$EDA_LIB"

# Verify tools
source "$PROJECT_DIR/.veriflow/eda_env.sh"
which yosys iverilog vvp 2>/dev/null || echo "[WARN] Some EDA tools not found"

# Quick smoke test — exit 127 means iverilog can't find its sub-tools
iverilog -V 2>&1 | head -1 || echo "[WARN] iverilog smoke test failed — check EDA_LIB path"

# Check existing state
if [ -f "$PROJECT_DIR/.veriflow/pipeline_state.json" ]; then
    echo "[STATUS] Existing state — resume from next incomplete stage:"
    cat "$PROJECT_DIR/.veriflow/pipeline_state.json"
else
    echo "[STATUS] New project, starting from Stage 1."
fi
```

If resuming, check `stages_completed` in pipeline_state.json and skip those stages.

### 0b. Create pipeline task list (status bar progress)

Use **TaskCreate** to create one task per pipeline stage. Call all 8 in sequence:

```
TaskCreate: subject="Stage 1: Architect — generate spec.json", activeForm="Generating spec.json"
TaskCreate: subject="Stage 2: Microarch — generate micro_arch.md", activeForm="Generating microarchitecture"
TaskCreate: subject="Stage 3: Timing — generate timing model + testbench", activeForm="Generating timing model"
TaskCreate: subject="Stage 4: Coder — generate RTL via sub-agent", activeForm="Generating RTL modules"
TaskCreate: subject="Stage 5: Skill_D — static analysis", activeForm="Running static analysis"
TaskCreate: subject="Stage 6: Lint — iverilog syntax check", activeForm="Running lint"
TaskCreate: subject="Stage 7: Sim — compile and simulate", activeForm="Running simulation"
TaskCreate: subject="Stage 8: Synth — yosys synthesis", activeForm="Running synthesis"
```

If resuming from a previous run, only create tasks for stages NOT in `stages_completed`. Mark already-completed stages' tasks as **completed** using TaskUpdate.

**IMPORTANT**: Every Bash call that uses EDA tools (iverilog, vvp, yosys) MUST start with:
```
source "$PROJECT_DIR/.veriflow/eda_env.sh"
```
Do NOT use bare `iverilog` or `yosys` without sourcing this file first — the PATH does not persist between Bash calls.

---

## State Update Command

After each stage hook passes:

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "STAGE_NAME"
```

Replace `STAGE_NAME` with: architect, microarch, timing, coder, skill_d, lint, sim, synth.

---

## Design Rules (Apply to ALL stages)

- All modules use **asynchronous reset, active-low, with synchronous release** (`posedge clk or negedge rst_n`)
  - The reset input `rst_n` must pass through a **2-stage synchronizer** before use:
  ```verilog
  // Reset synchronizer (in top module or each clock domain)
  reg rst_n_meta, rst_n_sync;
  always @(posedge clk or negedge rst_n) begin
      if (!rst_n) begin
          rst_n_meta <= 1'b0;
          rst_n_sync <= 1'b0;
      end else begin
          rst_n_meta <= 1'b1;
          rst_n_sync <= rst_n_meta;
      end
  end
  // Use rst_n_sync (not raw rst_n) as reset for all internal logic
  ```
  - External `rst_n` pin connects to the synchronizer only. All internal modules use the synchronized reset.
- Port naming: `_n` suffix for active-low, `_i`/`_o` for direction
- Parameterized design: use `parameter` for widths and depths
- Clock domains must be explicitly declared
- **Verilog-2005 only** — NO SystemVerilog (`logic`, `always_ff`, `assert property`, `|->`, `##`)

---

## Stage 1: architect (inline)

**Goal**: Read all input files, generate spec.json.

Mark Stage 1 task as **in_progress** using TaskUpdate.

### 1a. Read inputs

Use **Read** tool on every available input file:
- `$PROJECT_DIR/requirement.md` (required — functional requirements)
- `$PROJECT_DIR/constraints.md` (optional — timing, area, power, IO constraints)
- `$PROJECT_DIR/design_intent.md` (optional — preliminary architecture, IP reuse, design decisions)
- Any `$PROJECT_DIR/context/*.md` files (optional — reference materials)

Use Bash `ls` to check which optional files exist before reading.

### 1b. Clarify requirements (MUST do before generating spec)

After reading all input files, systematically check for missing or ambiguous information. You **MUST** ask the user using AskUserQuestion **one question at a time** for each unclear item below. Do NOT proceed to 1c until all questions are resolved.

#### A. Functional clarity (from requirement.md)

- **Module functionality**: What exactly does the module do? Any special modes or edge cases?
- **Interface protocol**: Handshake type (valid/ready? pulse? level?), bus widths, signal directions
- **Data format**: Bit width, byte order (MSB/LSB first), encoding
- **FSM behavior**: States, transitions, error handling
- **Clock domain crossings**: Multiple clocks? Need synchronizers?

#### B. Constraint clarity (from constraints.md — ask if missing or incomplete)

- **Clock frequency**: Target clock frequency in MHz
- **Target platform**: FPGA family/part number, ASIC node, or technology-agnostic?
- **Area budget**: Maximum LUTs, FFs, BRAMs (FPGA) or gate count (ASIC)
- **Power budget**: Power envelope in mW
- **Reset strategy**: Synchronous or asynchronous? Active-high or active-low?
- **IO standards**: IO voltage levels, external interface specifications

#### C. Design intent clarity (from design_intent.md — ask if missing or incomplete)

- **Architecture style**: Pipelined (fast, large) vs iterative (small, slow) vs folded?
- **Module partitioning**: Any preferred submodule breakdown or hierarchy?
- **Interface preferences**: Internal handshake protocol (valid/ready, pulse, register-based)?
- **IP reuse**: Any existing modules or IPs to integrate?
- **Key design decisions**: Algorithm choices, memory strategy, error handling approach?

**Rule**: If the provided files already answer all items in a section clearly, skip that section entirely. If even one item within a section is ambiguous, ask about it. Ask ONE question at a time, wait for the user's answer, then ask the next if needed.

### 1c. Write spec.json

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/spec.json`.

Must follow this exact structure:

```json
{
  "design_name": "design_name",
  "description": "Brief description",
  "target_frequency_mhz": 200,
  "data_width": 32,
  "byte_order": "MSB_FIRST",
  "constraints": {
    "timing": {
      "target_frequency_mhz": 200,
      "critical_path_ns": 5.0,
      "jitter_ns": 0.1,
      "clock_domains": [
        {
          "name": "clk_core",
          "frequency_mhz": 200,
          "source": "external"
        }
      ]
    },
    "area": {
      "target_device": "XC7A35T",
      "target_device_family": "Artix-7",
      "max_luts": 8000,
      "max_ffs": 5000,
      "max_brams": 16,
      "max_cells": 5000
    },
    "power": {
      "budget_mw": 200,
      "clock_gating": true
    },
    "io": {
      "standard": "LVCMOS33",
      "external_interfaces": [
        {
          "name": "uart",
          "type": "UART",
          "params": "115200 baud, 8N1"
        }
      ]
    },
    "verification": {
      "coverage_target_pct": 95,
      "formal_verification": false
    }
  },
  "design_intent": {
    "architecture_style": "iterative",
    "pipeline_stages": 2,
    "resource_strategy": "distributed_ram",
    "interface_preferences": {
      "internal": "valid/ready",
      "register": "apb-like"
    },
    "ip_reuse": [],
    "key_decisions": [
      "Decision and rationale"
    ]
  },
  "critical_path_budget": 50,
  "modules": [
    {
      "module_name": "module_name",
      "description": "What this module does",
      "module_type": "top|processing|control|memory|interface",
      "hierarchy_level": 0,
      "parent": null,
      "submodules": [],
      "clock_domains": [
        {
          "name": "clk_domain_name",
          "clock_port": "clk",
          "reset_port": "rst_n",
          "frequency_mhz": 200,
          "reset_type": "async_active_low"
        }
      ],
      "ports": [
        {
          "name": "port_name",
          "direction": "input|output",
          "width": 1,
          "protocol": "clock|reset|data|valid|ready|flag",
          "description": "Port description"
        }
      ],
      "fsm_spec": null,
      "parameters": [
        {
          "name": "PARAM_NAME",
          "default_value": 16,
          "description": "Parameter description"
        }
      ]
    }
  ],
  "module_connectivity": [
    {
      "source": "module1.port1",
      "destination": "module2.port1",
      "bus_width": 32,
      "connection_type": "direct"
    }
  ],
  "data_flow_sequences": [
    {
      "name": "main_flow",
      "steps": ["input -> processing -> output"],
      "latency_cycles": 2
    }
  ]
}
```

Constraints:
- One module MUST have `"module_type": "top"`
- Every module must have complete port definitions
- `constraints` block is REQUIRED — populate from constraints.md or from clarification answers
- `design_intent` block is REQUIRED — populate from design_intent.md or from clarification answers
- `critical_path_budget` = floor(1000 / target_frequency_mhz / 0.1)
- `resource_strategy` must be `"distributed_ram"` or `"block_ram"`
- Do NOT generate any Verilog files

### 1c-math. Validate spec (math checks)

After writing spec.json, verify these calculations:

1. **Counter width check**: For any module with counters or dividers, verify the declared width can hold the max value. Formula: `min_width = ceil(log2(max_count))`. If `max_count` is an exact power of 2, add 1 bit.

2. **Clock divider accuracy**: If the design involves frequency division (baud rate, PWM, timer), calculate the actual achieved frequency vs target. Error formula: `error_pct = abs(actual - target) / target * 100`. If error > 2%, add a note to the spec and suggest alternatives (fractional accumulator, different divisor).

3. **Latency sanity**: Verify `latency_cycles` in `data_flow_sequences` is consistent with pipeline_stages and module connectivity.

4. **Constraint consistency**: Verify `constraints.timing.target_frequency_mhz` matches `target_frequency_mhz` at the top level. Verify `constraints.area.max_cells` is consistent with the sum of module complexities. Verify `critical_path_budget` = floor(1000 / target_frequency_mhz / 0.1).

5. **Resource feasibility**: If `constraints.area` specifies a target device, verify the combined resource estimate (LUTs, FFs, BRAMs) fits within device limits.

If any check fails, fix spec.json immediately.

### 1d. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/spec.json" && grep -q "module_name" "$PROJECT_DIR/workspace/docs/spec.json" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

If FAIL → fix and rewrite spec.json immediately.

### 1e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "architect"
```

Mark Stage 1 task as **completed** using TaskUpdate.

---

## Stage 2: microarch (inline)

**Goal**: Read spec.json + requirement.md + design_intent.md, generate micro_arch.md.

Mark Stage 2 task as **in_progress** using TaskUpdate.

### 2a. Read inputs

Use **Read** tool:
- `$PROJECT_DIR/workspace/docs/spec.json`
- `$PROJECT_DIR/requirement.md`
- `$PROJECT_DIR/design_intent.md` (if exists — preliminary architecture ideas)
- `$PROJECT_DIR/constraints.md` (if exists — for timing-driven partitioning)

### 2b. Write micro_arch.md

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/micro_arch.md`.

Must contain these sections:

- **Module partitioning**: top module and submodule list with responsibilities — MUST align with `design_intent.ip_reuse` and `design_intent.interface_preferences` if provided
- **Datapath**: key data flow descriptions
- **Control logic**: FSM state diagram (if any) or control signal descriptions
- **Interface protocol**: inter-module handshake/communication protocols — MUST align with `design_intent.interface_preferences` if provided
- **Timing closure plan**: critical path identification and mitigation strategies referencing `constraints.timing` if provided
- **Resource plan**: estimated resource usage per module referencing `constraints.area` if provided
- **Key design decisions**: rationale for partitioning, trade-off explanations — MUST reference `design_intent.key_decisions` if provided

Guidelines:
- Each submodule should have a single responsibility
- Clearly define inter-module interfaces (signal name, width, protocol)
- If FSMs exist, list all states and transition conditions
- Annotate critical paths and timing constraints
- If design_intent.md was provided, the micro_arch MUST respect the stated preferences unless they conflict with constraints (in which case, document the override and rationale)
- If ip_reuse lists existing modules, include them in the module partitioning and define their interfaces

### 2c. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/micro_arch.md" && wc -l "$PROJECT_DIR/workspace/docs/micro_arch.md" | awk '$1 >= 10 {print "[HOOK] PASS"; exit 0} {print "[HOOK] FAIL"; exit 1}'
```

If FAIL → fix and rewrite immediately.

### 2d. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "microarch"
```

Mark Stage 2 task as **completed** using TaskUpdate.

---

## Stage 3: timing (inline)

**Goal**: Read spec.json + micro_arch.md, generate timing_model.yaml + testbench.

Mark Stage 3 task as **in_progress** using TaskUpdate.

### 3a. Read inputs

Use **Read** tool:
- `$PROJECT_DIR/workspace/docs/spec.json`
- `$PROJECT_DIR/workspace/docs/micro_arch.md`

### 3b. Write timing_model.yaml

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/timing_model.yaml`.

Format:

```yaml
design: <design_name>
scenarios:
  - name: <scenario_name>
    description: "<what this scenario tests>"
    assertions:
      - "<signal_A> |-> ##[min:max] <signal_B>"
      - "<condition> |-> ##<n> <expected>"
    stimulus:
      - {cycle: 0, <port>: <value>, <port>: <value>}
      - {cycle: 1, <port>: <value>}
```

Requirements:
- At least 3 scenarios: reset behavior + basic operation + at least one edge case
- Cover every functional requirement in the spec
- Stimulus must be self-consistent with assertions
- Use hex values for data buses (e.g., `0xDEADBEEF`)

### 3c. Write testbench

Use **Write** tool to write `$PROJECT_DIR/workspace/tb/tb_<design_name>.v`.

Get `<design_name>` from spec.json `design_name` field.

**iverilog Compatibility Rules (CRITICAL)**:
- NO `assert property`, `|->`, `|=>`, `##` delay operator (SVA)
- NO `logic` type (use `reg`/`wire`)
- NO `always_ff`/`always_comb` (use `always`)
- YES `$display`, `$monitor`, `$finish`, `$dumpfile`

Testbench must:
- Use `$dumpfile`/`$dumpvars` for waveform capture
- Track a `fail_count` integer
- Print `ALL TESTS PASSED` or `FAILED: N assertion(s) failed`
- Call `$finish` after all test cases complete
- Convert all YAML assertions to standard Verilog `$display` checks

**Serial/Baud-rate Designs**: Calculate exact clock cycles:
```
wait_cycles = divisor_value * oversampling_factor * frame_bits
```
NEVER use a fixed small constant for timing-sensitive operations.

Minimum: `max(3, number of functional requirements)` scenarios. Every data-write scenario must read back with a `fail_count` check.

### 3d. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/timing_model.yaml" && ls "$PROJECT_DIR/workspace/tb/"tb_*.v >/dev/null 2>&1 && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

If FAIL → fix and rewrite immediately.

### 3e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "timing"
```

Mark Stage 3 task as **completed** using TaskUpdate.

---

## Stage 4: coder (sub-agent per module)

**Goal**: Read spec.json, loop through each module, call vf-coder agent once per module to generate workspace/rtl/*.v.

Mark Stage 4 task as **in_progress** using TaskUpdate.

### 4a. Read spec and extract module list

Use **Read** tool to read `$PROJECT_DIR/workspace/docs/spec.json`.

Extract the list of modules from the `"modules"` array. For each module, note:
- `module_name`
- `module_type` (top, processing, control, memory, interface)

### 4b. Resolve coding_style path

```bash
echo "$HOME/.claude/skills/vf-pipeline/coding_style.md"
```

Save the output as `CODING_STYLE_PATH`.

### 4c. Call vf-coder agent for each module (non-top first, top last)

**IMPORTANT**: Generate sub-modules first, top module last. This ensures the top module knows all sub-module ports.

For each module in the list (skip top module initially, process it last):

Call Agent with:
- `subagent_type`: `vf-coder`
- `prompt`: `CODING_STYLE={CODING_STYLE_PATH} SPEC={PROJECT_DIR}/workspace/docs/spec.json MICRO_ARCH={PROJECT_DIR}/workspace/docs/micro_arch.md MODULE_NAME={module_name} OUTPUT_DIR={PROJECT_DIR}/workspace/rtl. Read CODING_STYLE then Read SPEC then Read MICRO_ARCH then Write {PROJECT_DIR}/workspace/rtl/{module_name}.v. Follow coding_style.md and micro_arch.md strictly.`

Replace all `{...}` placeholders with actual values. Do NOT use shell variables in the prompt — use resolved absolute paths.

After all sub-modules are done, call Agent for the top module (same prompt format).

**Run all agent calls sequentially** — do NOT parallelize, as each call is independent but the top module should be last.

### 4c-retry. If agent returns 0 tool uses

After each agent call, check the result. If the agent completed with **0 tool uses**:

1. **Retry once** — call the same agent again with the exact same prompt
2. If retry also returns 0 tool uses → fall back to 4c-fallback

### 4c-fallback. If retry also fails (0 tool uses)

If a module's agent still fails after retry, generate that module inline:
1. Read `${CLAUDE_SKILL_DIR}/coding_style.md`
2. Read `$PROJECT_DIR/workspace/docs/spec.json`
3. Read `$PROJECT_DIR/workspace/docs/micro_arch.md`
4. Use **Write** to create the failed module's .v file

### 4b. Hook

```bash
v_files=$(ls "$PROJECT_DIR/workspace/rtl/"*.v 2>/dev/null)
if [ -n "$v_files" ]; then
    for f in $v_files; do grep -q "endmodule" "$f" 2>/dev/null || echo "[HOOK] MISSING endmodule in $(basename $f)"; done
    echo "[HOOK] PASS"
else
    echo "[HOOK] FAIL"
fi
```

### 4c. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "coder"
```

Mark Stage 4 task as **completed** using TaskUpdate.

---

## Stage 5: skill_d (inline)

**Goal**: Read RTL files, perform quality checks, write static_report.json.

Mark Stage 5 task as **in_progress** using TaskUpdate.

### 5a. Read inputs

Use **Read** tool to read every file in `$PROJECT_DIR/workspace/rtl/*.v` and `$PROJECT_DIR/workspace/docs/spec.json`.

### 5b. Perform checks

Check for (do NOT run EDA tools):

**A. Static Checks**:
1. `initial` blocks in RTL files
2. Empty or near-empty files
3. Missing `endmodule`
4. Obvious syntax issues

**B. Deep Code Review**:
1. Latch inference: missing `case`/`if` branches in combinational logic
2. Combinational loops: feedback paths in combinational logic
3. Uninitialized registers: registers used before assignment in reset path
4. Non-synthesizable constructs: `$display`, `#delay` (non-TB), `initial` (non-TB)
5. Clock domain crossing: multi-clock-domain signals without synchronizers

**C. Logic Depth Estimate**:
- Each gate/operator = 1 level
- Multiplier trees = ~log2(width) levels
- Adder carries = ~log2(width)/2 levels
- Compare against `critical_path_budget` from spec.json

**D. Resource Estimate**:
- Each flip-flop = 1 cell
- Each 2-input logic gate = 0.5 cells
- Each mux = 1 cell per bit
- Each adder = 1 cell per bit
- Compare against `constraints.area.max_cells` (or `max_luts`/`max_ffs` if specified) from spec.json

**E. Constraint Compliance**:
- Verify logic depth fits within `constraints.timing.critical_path_ns`
- Verify estimated resources fit within `constraints.area` limits
- Verify clock gating is present if `constraints.power.clock_gating` is true
- Flag any violations as error-level issues

### 5c. Write static_report.json

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/static_report.json`.

Format:
```json
{
  "design": "<design_name>",
  "analyzed_files": ["<file1.v>", "<file2.v>"],
  "logic_depth_estimate": {
    "max_levels": 0,
    "budget": 0,
    "status": "OK|OVER_BUDGET|UNKNOWN",
    "worst_path": "<description>"
  },
  "resource_estimate": {
    "cells": 0,
    "luts": 0,
    "ffs": 0,
    "brams": 0,
    "status": "OK|OVER_BUDGET|UNKNOWN",
    "budget": {}
  },
  "cdc_risks": [],
  "latch_risks": [],
  "constraint_violations": [],
  "recommendation": "<single most important suggestion>"
}
```

Quality score (0-1). Pass threshold: 0.5. Auto-fail if any error-level issues exist. Severity per issue: error / warning / info.

### 5d. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/static_report.json" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

If FAIL → rewrite immediately.

### 5e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "skill_d"
```

Mark Stage 5 task as **completed** using TaskUpdate.

---

## Stage 6: lint (inline)

**Goal**: Run iverilog syntax check on RTL files.

Mark Stage 6 task as **in_progress** using TaskUpdate.

### 6a. Confirm files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

### 6b. Run lint

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && iverilog -Wall -tnull workspace/rtl/*.v 2>&1 | tee logs/lint.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
```

### 6c. Analyze results

Read `logs/lint.log`. Categorize errors:
- **syntax error**: missing semicolons, typos
- **port mismatch**: port connection errors
- **undeclared**: undeclared signals
- **other**: unclassified errors

If errors found → go to Error Recovery below.

### 6d. Hook

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && iverilog -Wall -tnull workspace/rtl/*.v > /dev/null 2>&1; echo "EXIT_CODE: $?"
```

If exit code != 0 → fix errors, re-run.

### 6e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "lint"
```

Mark Stage 6 task as **completed** using TaskUpdate.

---

## Stage 7: sim (inline)

**Goal**: Compile and simulate RTL + testbench.

Mark Stage 7 task as **in_progress** using TaskUpdate.

### 7a. Confirm inputs

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v "$PROJECT_DIR/workspace/tb/"tb_*.v
```

### 7b. Compile

```bash
cd "$PROJECT_DIR" && mkdir -p workspace/sim logs && source .veriflow/eda_env.sh && iverilog -o workspace/sim/tb.vvp workspace/rtl/*.v workspace/tb/tb_*.v 2>&1 | tee logs/compile.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
```

### 7c. Run simulation (only if compilation succeeded)

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
# Cleanup VCD from project root (can be large)
rm -f "$PROJECT_DIR"/*.vcd 2>/dev/null
```

### 7d. Analyze output

Read `logs/sim.log`. Pass/Fail criteria:
- Output contains `PASS`/`pass`/`All tests passed` → pass
- Output contains `FAIL`/`fail`/`Error` → fail
- Simulation exits abnormally → fail

If sim fails → go to Error Recovery below. Still complete self-check.

### 7e. Hook

```bash
test -f "$PROJECT_DIR/workspace/sim/tb.vvp" || { echo "[HOOK] FAIL — tb.vvp not found"; exit 1; }
grep -qiE "FAIL|error" "$PROJECT_DIR/logs/sim.log" && { echo "[HOOK] FAIL — simulation has failures, check logs/sim.log"; exit 1; }
grep -qiE "PASS|All tests passed" "$PROJECT_DIR/logs/sim.log" && echo "[HOOK] PASS" || echo "[HOOK] FAIL — no PASS found in sim output"
```

If FAIL → go to Error Recovery. Do NOT mark sim as completed.

### 7f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "sim"
```

Mark Stage 7 task as **completed** using TaskUpdate.

---

## Stage 8: synth (inline)

**Goal**: Run yosys synthesis.

Mark Stage 8 task as **in_progress** using TaskUpdate.

### 8a. Read spec for top module name

Use **Read** tool to read `$PROJECT_DIR/workspace/docs/spec.json`. Extract `design_name`.

### 8b. Confirm RTL files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

### 8c. Run synthesis

```bash
cd "$PROJECT_DIR" && mkdir -p workspace/synth && source .veriflow/eda_env.sh && yosys -p "read_verilog workspace/rtl/*.v; synth -top {top_module}; stat" 2>&1 | tee workspace/synth/synth_report.txt
```

Replace `{top_module}` with `design_name` from spec.json.

### 8d. Analyze report

Read `workspace/synth/synth_report.txt`. Extract:
- Whether synthesis succeeded
- Number of cells
- Maximum frequency (if available)
- Area estimate
- Warnings (list top 3)

### 8e. Hook

```bash
test -f "$PROJECT_DIR/workspace/synth/synth_report.txt" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

### 8f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "synth"
```

Mark Stage 8 task as **completed** using TaskUpdate.

---

## Error Recovery

When any stage fails (lint errors, sim failure, synth failure):

### Step 1: Diagnose
- Read the error output from the failed stage
- Read the relevant RTL files from `workspace/rtl/`

### Step 2: Classify
- **syntax** (lint): typos, missing declarations, port mismatches
- **logic** (sim): incorrect functionality, timing issues, FSM errors
- **timing** (synth): non-synthesizable constructs, timing violations

### Step 3: Fix

Common error patterns:

| Error Pattern | Cause | Fix |
|--------------|-------|-----|
| `cannot be driven by continuous assignment` | `reg` used with `assign` | Change to `wire` or use `always` |
| `Unable to bind wire/reg/memory` | Forward reference or typo | Move declaration or fix typo |
| `Variable declaration in unnamed block` | Variable in `always` without named block | Move to module level |
| `Width mismatch` | Assignment between different widths | Add explicit width cast |
| `is not declared` | Typo or missing declaration | Fix typo or add declaration |
| `Multiple drivers` | Two assignments to same signal | Remove duplicate |
| `Latch inferred` | Incomplete case/if without default | Add default case or else branch |

Fix rules:
- Only modify files that have issues
- Preserve original coding style and design intent
- Do NOT change module interfaces (ports)
- **RTL fixes**: Do NOT modify any file in `workspace/tb/`
- **TB bugs**: If simulation fails due to a testbench bug (not an RTL bug), you MAY fix the testbench. But do NOT weaken assertions — only fix TB infrastructure (signal types, timing, connectivity)
- Do NOT add new functionality or remove existing functionality
- Make minimal changes
- Fix one error at a time
- **Debug budget**: If you spend more than 3 fix-and-retry cycles on the same error without progress, STOP and ask the user for help. Do NOT go in circles

After fixing, re-run the failed stage's Bash command to verify.

### Step 4: Sync upstream documents

If the fix changes architectural behavior (FSM states, timing parameters, sampling points, signal definitions), update the affected upstream documents:
- **Logic fix** → update `workspace/docs/micro_arch.md` to match the actual RTL behavior
- **Timing fix** → update `workspace/docs/timing_model.yaml` if scenarios/assertions are affected
- Always update `micro_arch.md` if FSM states, datapath, or control logic changed

### Retry Policy

1. **1st fail**: Fix RTL, retry the stage
2. **2nd fail**: Rollback to earlier stage and re-run sequentially
3. **3rd fail**: STOP and notify user

Rollback targets by error type:

| Error Type | Rollback To | Re-run Path |
|-----------|-------------|-------------|
| syntax | coder | coder → skill_d → lint → sim → synth |
| logic | microarch | microarch → timing → coder → skill_d → lint → sim → synth |
| timing | timing | timing → coder → skill_d → lint → sim → synth |

---

## Strict Constraints

1. Stages must be executed sequentially. Skip stages already completed in pipeline_state.json.
2. Every stage MUST use tools (Read/Write/Bash). No text-only responses.
3. NO trusting output without Bash hook verification.
4. Do NOT modify any file in `workspace/tb/` — testbench is strictly read-only.

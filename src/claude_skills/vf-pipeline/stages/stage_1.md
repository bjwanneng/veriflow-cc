# Stage 1: architect

**Goal**: Read all input files, generate spec.json + behavior_spec.md.

Mark Stage 1 task as **in_progress** using TaskUpdate.

## 1a. Read inputs

Use **Read** tool on every available input file:
- `$PROJECT_DIR/requirement.md` (required — functional requirements)
- `$PROJECT_DIR/constraints.md` (optional — timing, area, power, IO constraints)
- `$PROJECT_DIR/design_intent.md` (optional — preliminary architecture, IP reuse, design decisions)
- Any `$PROJECT_DIR/context/*.md` files (optional — reference materials)

Use Bash `ls` to check which optional files exist before reading.

## 1b. Clarify requirements (MUST do before generating spec)

After reading all input files, systematically check for missing or ambiguous information. You **MUST** ask the user using AskUserQuestion **one question at a time** for each unclear item below. Do NOT proceed to 1c until all questions are resolved.

### A. Functional clarity (from requirement.md)

- **Module functionality**: What exactly does the module do? Any special modes or edge cases?
- **Interface protocol**: Handshake type (valid/ready? pulse? level?), bus widths, signal directions
- **Data format**: Bit width, byte order (MSB/LSB first), encoding
- **FSM behavior**: States, transitions, error handling
- **Clock domain crossings**: Multiple clocks? Need synchronizers?

### B. Constraint clarity (from constraints.md — ask if missing or incomplete)

- **Clock frequency**: Target clock frequency in MHz
- **Target platform**: FPGA family/part number, ASIC node, or technology-agnostic?
- **Area budget**: Maximum LUTs, FFs, BRAMs (FPGA) or gate count (ASIC)
- **Power budget**: Power envelope in mW
- **Reset strategy**: Synchronous or asynchronous? Active-high or active-low?
- **IO standards**: IO voltage levels, external interface specifications

### C. Design intent clarity (from design_intent.md — ask if missing or incomplete)

- **Architecture style**: Pipelined (fast, large) vs iterative (small, slow) vs folded?
- **Module partitioning**: Any preferred submodule breakdown or hierarchy?
- **Interface preferences**: Internal handshake protocol (valid/ready, pulse, register-based)?
- **IP reuse**: Any existing modules or IPs to integrate?
- **Key design decisions**: Algorithm choices, memory strategy, error handling approach?

### D. Algorithm & Protocol clarity (ask for any module with complex algorithms or protocols)

- **Algorithm reference**: Is there a standard or document (e.g., FIPS, IEEE, 3GPP) describing the algorithm? If yes, provide the document or section number.
- **Pseudocode**: Can you provide pseudocode or step-by-step description for the key algorithm in each module?
- **Key formulas**: Any mathematical formulas (e.g., GF(2^8) multiplication, CRC polynomial, filter coefficients) that must be implemented exactly?
- **Test vectors**: Do you have known-answer test vectors (e.g., NIST KAT, protocol conformance tests) for verification?

### E. Timing Completeness (MUST ask for every module with a clock)

- **Cycle-level behavior**: For each module, describe what happens on each clock cycle during normal operation. Example: "Cycle 0: sample input data; Cycle 1: compute XOR with round key; Cycle 2: output result and assert valid"
- **Latency**: How many clock cycles from valid input to valid output?
- **Throughput**: Can the module accept new data every cycle (1 result/cycle) or does it need N cycles between inputs?
- **Interface timing**: For each handshake interface, how many cycles between valid assertion and ready response? Is ready always-high or conditional?
- **Reset recovery**: How many cycles after de-asserting reset before the module can accept valid data?
- **Backpressure**: What happens when the module has valid output but downstream is not ready (ready is low)? Does it stall, buffer, or drop?

### F. Domain Knowledge (MUST ask if design involves any specialized domain)

- **Design domain**: What field does this design belong to? (e.g., cryptography/AES, communication/SPI, DSP/FIR filter, memory controller/DDR, etc.)
- **Standard reference**: Does this implement a specific standard? If yes, provide the standard name, version, and relevant section numbers (e.g., "FIPS-197 Section 4.2" or "IEEE 802.3 Clause 4")
- **Prerequisite concepts**: What concepts must the implementer understand? List any non-obvious concepts (e.g., "Galois Field multiplication in GF(2^8)" for AES, "Manchester encoding" for 10BASE-T Ethernet)
- **Test vectors**: Do you have known-answer test vectors for verification? If yes, provide at least 2 input→output pairs with expected cycle counts.

### G. Information Completeness (meta-check — always ask)

- **Implicit assumptions**: Are there any assumptions in the requirements that might not be obvious to someone unfamiliar with this design? (e.g., "input data is always valid on reset de-assertion" or "backpressure never lasts more than 16 cycles")
- **Missing scenarios**: Are there any corner cases, error conditions, or rare operating modes that haven't been mentioned?

**Rule**: For each section (A-G), the pipeline MUST explicitly confirm each item. If the input files clearly and unambiguously answer an item, note it as "confirmed from input" and move to the next item. Do NOT skip an entire section without checking each item. If ANY item in ANY section cannot be resolved from input files or user answers, STOP and ask the user using AskUserQuestion before proceeding. Ask ONE question at a time, wait for the user's answer, then ask the next if needed.

## 1c1. Write spec.json

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
          "reset_port": "rst",
          "frequency_mhz": 200,
          "reset_type": "sync_active_high"
        }
      ],
      "ports": [
        {
          "name": "port_name",
          "direction": "input|output",
          "width": 1,
          "protocol": "clock|reset|data|valid|ready|flag",
          "reset_polarity": "active_high",
          "handshake": "single_cycle",
          "ack_port": "",
          "signal_lifetime": "pulse",
          "description": "Port description"
        }
      ],
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
- **Port semantic fields (interface lock)**:
  - Ports with `protocol: "reset"` MUST declare `reset_polarity`: `"active_high"` or `"active_low"`
  - Ports with `protocol: "valid"` MUST declare `handshake`: `"hold_until_ack"` | `"single_cycle"` | `"pulse"`
  - If `handshake: "hold_until_ack"`, MUST also declare `ack_port` with the name of the corresponding ack input port
  - All ports MUST declare `signal_lifetime`: `"pulse"` or `"hold_until_used"`:
    - `"pulse"` — signal is asserted for 1 cycle and consumed immediately by the receiver (default, most handshake/data signals)
    - `"hold_until_used"` — signal is sampled at most once, arrives as a short pulse but is consumed many cycles later by a downstream module. The receiver MUST latch this signal. **Classic bug**: `is_last` flag on a multi-block hash/checksum — asserted with msg_valid on cycle 0, consumed by FSM at the last round 67 cycles later. Without latching, the signal is 0 when finally sampled.
  - These fields are locked after Stage 1 and MUST NOT be changed by subsequent stages

## 1c2. Write behavior_spec.md

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/behavior_spec.md`.

This document captures **behavioral requirements** — what each module does cycle-by-cycle, FSM transitions, timing contracts, domain knowledge, and algorithm pseudocode. This is distinct from spec.json (interface contract) and micro_arch.md (implementation decisions).

Required template:

```markdown
# Behavior Specification: {design_name}

## 1. Domain Knowledge

### 1.1 Background
{2-5 sentences explaining the design's domain, purpose, and where it fits in a larger system.
Assume the reader has NO prior knowledge of this domain.}

### 1.2 Key Concepts
{List and explain every domain-specific concept the implementer must understand.
Each concept gets a name and a 1-2 sentence explanation.
If no specialized domain knowledge is needed, state: "No specialized domain knowledge required — [one sentence explaining what the module does]."}

### 1.3 References
{List any standards, specifications, or documents referenced.
Include full name, version, and relevant section numbers.}

### 1.4 Glossary
| Term | Definition |
|------|-----------|
| ... | ... |

## 2. Module Behavior: {module_name}
{Repeat section 2 for each module defined in spec.json}

### 2.1 Cycle-Accurate Behavior

#### Normal Operation
| Cycle | Condition | Action | Output Change | Next State |
|-------|-----------|--------|---------------|------------|
| 0 | reset de-asserted | ... | ... | ... |
| 1 | ... | ... | ... | ... |

#### Reset Behavior
| Cycle | Condition | Action | Output Change |
|-------|-----------|--------|---------------|
| -1 | rst asserted | clear all registers | all outputs = 0 |
| 0 | rst de-asserted | ... | ... |

{If the module is purely combinational (no clock), state: "This module is combinational.
Output changes immediately based on input. No cycle behavior applicable."}

### 2.2 FSM Specification
{Skip this section if module has no FSM.}

#### States
| State Name | Description | Outputs |
|-----------|-------------|---------|
| IDLE | Waiting for input | valid_o = 0 |
| ... | ... | ... |

#### Transitions
| From | To | Condition |
|------|----|-----------|
| IDLE | PROCESS | valid_i && ready_o |
| ... | ... | ... |

#### Initial State: {state_name}

### 2.3 Register Requirements
| Register | Width (bits) | Reset Value | Purpose |
|----------|-------------|-------------|---------|
| data_reg | 32 | 0x0 | Holds input data during processing |
| cnt | 4 | 0 | Cycle counter for round operations |

### 2.4 Timing Contracts
- **Latency**: {N} cycles (from valid_i assertion to valid_o assertion)
- **Throughput**: 1 result per {M} cycles
- **Backpressure behavior**: {stall / buffer / drop}
- **Reset recovery**: {N} cycles after rst de-assertion

### 2.5 Algorithm Pseudocode
{Step-by-step pseudocode for each complex operation. If user provided pseudocode in Stage 1D,
reproduce it EXACTLY here. If no complex algorithm, state: "No complex algorithm — direct datapath."}

INPUT: data_in[WIDTH-1:0], start
OUTPUT: data_out[WIDTH-1:0], done

Step 1: [description of what happens]
Step 2: ...
Step N: [final output]

### 2.6 Protocol Details

#### 2.6.1 Signal Groups
{Group related signals by function. Every port in spec.json must appear in exactly one group.}

| Group | Signals | Relationship |
|-------|---------|--------------|
| Clock/Reset | clk, rst | Synchronous active-high reset |
| Data Input | data_i[N:0], valid_i, ready_o | valid/ready handshake on input |
| Data Output | data_o[M:0], valid_o, ready_i | valid/ready handshake on output |
| Control | start_i, done_o | Single-pulse start, done flag |
| Status | busy_o, error_o | Status flags |

#### 2.6.2 Control Truth Table
{For each module with control/status/handshake signals, enumerate every valid input combination
and the resulting output behavior. Use '-' for "don't care". This table is the authoritative
reference for RTL implementation — every row must be implemented exactly.}

| State | start_i | din_valid | dout_ready | → ready_o | dout_valid | busy_o | done_o | Notes |
|-------|---------|-----------|------------|-----------|------------|--------|--------|-------|
| RESET | - | - | - | 0 | 0 | 0 | 0 | All outputs quiescent |
| IDLE | 0 | - | - | 1 | 0 | 0 | 0 | Ready for new input |
| IDLE | 1 | - | - | 0 | 0 | 1 | 0 | Start processing |
| PROCESS | - | - | - | 0 | 0 | 1 | 0 | Computation in progress |
| PROCESS | - | - | - | 0 | 1 | 0 | 1 | Computation complete, output valid |
| WAIT | - | - | 0 | 0 | 1 | 0 | 0 | Output held until ack |
| WAIT | - | - | 1 | 0 | 1 | 0 | 0 | Output consumed |
| IDLE | - | - | - | 1 | 0 | 0 | 0 | Return to idle |

#### 2.6.3 Signal Conflicts
{Declare which signals MUST NOT be co-asserted, and what the RTL must do if they are.}

| Signal A | Signal B | Rule | Violation Behavior |
|----------|----------|------|-------------------|
| start_i | busy_o | MUST NOT co-assert | Ignore start_i while busy |
| valid_o | rst | valid_o MUST be 0 during reset | Hardware enforced |
| done_o | start_i | done_o takes priority | Acknowledge done before new start |

#### 2.6.4 Protocol Timing
{For each interface protocol (SPI, UART, AXI-Stream, custom handshake):
- Signal sequence diagram (text-based cycle-by-cycle)
- Setup/hold requirements
- Error conditions and recovery}

## 3. Cross-Module Timing

### 3.1 Pipeline Stage Assignment
| Pipeline Stage | Module | Duration (cycles) |
|---------------|--------|-------------------|
| ... | ... | ... |

### 3.2 Module-to-Module Timing
| Source | Destination | Signal | Latency (cycles) |
|--------|------------|--------|------------------|
| module_A.data_out | module_B.data_in | valid chain | 2 |

### 3.3 Critical Path Description
{Describe the longest combinational path and why it might be tight.}
```

Constraints:
- **Every module in spec.json MUST have a corresponding Section 2** in behavior_spec.md
- **Domain Knowledge section is mandatory** — if truly N/A (e.g., simple counter), explicitly state "This design has no specialized domain knowledge requirements" with a one-sentence explanation of what it does
- **Cycle-Accurate Behavior is mandatory for sequential modules** — if the module has a clock port, it must have cycle behavior
- **FSM Specification is mandatory for modules with FSM** — if module description mentions states, control flow, or sequencing, this must be filled
- **Algorithm Pseudocode must be reproduced verbatim** if user provided it in Stage 1D — no paraphrasing
- **Cross-Module Timing (Section 3) is mandatory for multi-module designs** — skip only for single-module designs

## 1c2b. Cross-Module Timing Consistency Check (multi-module designs ONLY)

Skip this step for single-module designs (only one module in spec.json with `module_type: "top"` and no submodules).

After writing behavior_spec.md, perform the following consistency analysis. This check catches contradictions between the FSM module's control signal timing and consumer modules' expected timing — before any RTL is generated.

Read behavior_spec.md and spec.json. For each pair of connected modules (from spec.json `module_connectivity`), extract and verify:

### Check A: Control Signal Co-assertion Consistency

1. From the FSM/control module's behavior spec (Section 2.X), list all control signals (load_en, calc_en, update_en, valid, ready, enable, etc.) and note which are asserted simultaneously (co-asserted) on the same clock cycle
2. For each consumer module that receives these control signals, check: does the consumer's behavior spec handle co-assertion correctly? Specifically:
   - If the FSM asserts `load_en=1 AND calc_en=1` on the same cycle, does the consumer's pseudocode use `if/else if` (which ignores calc_en when load_en is active) or `if/if` (which processes both)?
   - Is the consumer's cycle-accurate behavior table consistent with the FSM's actual assertion pattern?
   - Does the consumer's algorithm pseudocode explicitly state what happens when multiple control signals are active simultaneously?
3. Flag any mismatch with the exact section numbers and cycle numbers from behavior_spec.md

### Check B: Signal Latency Consistency

1. From Cross-Module Timing Section 3.2, extract each signal's stated latency
2. For registered outputs driven by `always @(posedge clk)`, verify latency=1 is stated; for combinational passthrough driven by `assign`, verify latency=0
3. Cross-check: if Module A outputs a registered signal and Module B expects it on the same cycle (latency 0), flag the contradiction

### Check C: Counter/State Range Overlap

1. If the FSM has a round/step counter (round_cnt, step_cnt, iter_cnt, etc.), verify all consumer modules reference the same range (e.g., 0-63 vs 1-64)
2. Check for off-by-one: does the FSM count from 0 to N-1 or 1 to N? Do consumers expect the same?
3. Verify the total number of iterations matches: FSM says 64 rounds, consumer expects 64 processing cycles

### Check D: Signal Lifetime Mismatch

1. From spec.json, identify all ports with `signal_lifetime: "hold_until_used"`
2. For each such port:
   - Which module produces this signal? (source module)
   - Which module consumes it? (destination module, from `module_connectivity`)
   - How many cycles elapse between signal assertion (source) and signal sampling (consumer)? (from behavior_spec.md cycle tables)
3. If the latency from assertion to sampling exceeds 1 clock cycle, verify the consumer explicitly latches the signal. Flag any case where:
   - `signal_lifetime: "hold_until_used"` but no latch register exists in the consumer
   - The signal is connected directly to a consumer port without intermediate storage
   - The consumer's cycle table shows sampling at a cycle far from assertion

**Example of what this check catches**:
- `is_last` port: `signal_lifetime: "hold_until_used"`, produced by testbench as a 1-cycle pulse with `msg_valid`, consumed by FSM 67 cycles later in DONE state
- Without latching in the top wrapper, the FSM sees `is_last=0` when it finally samples
- Fix: add `is_last_latched_reg` in the wrapper, set on msg_valid, read by FSM

### Check E: Shift Register / Window Alignment

1. If any consumer module uses a shift register, sliding window, or circular buffer, verify:
   - At what cycle does the first valid element appear at the output position?
   - Is there an off-by-one between when the FSM asserts `load_en` / `calc_en` and when the shift register output aligns with the consumer's expected round?
2. Specifically check: does the shift register output element W[j] at round j, or W[j-1] or W[j+1]?
3. Flag if the load cycle loads data without simultaneously shifting, which would cause a one-round offset in subsequent cycles

**If ANY check flags a contradiction:**

1. List the contradiction with exact section/cycle references
2. Ask the user via AskUserQuestion: "Cross-Module Timing Consistency Check found a potential issue: [details]. How should the timing be aligned? Options: (a) Signals should be co-asserted — all consumers must handle simultaneous assertion, (b) Signals should be sequential — add a separate load cycle before calc, (c) This is intentional — no change needed"
3. Update behavior_spec.md with the user's answer
4. Re-run this check (1c2b only)
5. Repeat until all checks pass

**Example of what this check catches (from real failure):**
- FSM Section 3.5 pseudocode: `load_en <- 1, calc_en <- 1` (co-asserted on IDLE->CALC transition)
- W-gen Section 4.1 table: Cycle 1 = `load_en=1` only, Cycle 2 = `calc_en=1` (treated as sequential)
- W-gen Section 4.5 pseudocode: `if load_en: load; else if calc_en: shift` (else-if means calc_en ignored during load)
- Result: W shift register is one round behind from round 1 onwards, causing hash mismatch

## 1c3. Readiness Check (gate — MUST pass before proceeding)

After writing both spec.json and behavior_spec.md, verify completeness. If ANY check fails, STOP and ask the user using AskUserQuestion.

**spec.json checks:**
- [ ] `design_name` is non-empty
- [ ] At least one module with `module_type: "top"` exists
- [ ] Every module has at least one port
- [ ] Every port has `signal_lifetime` declared (`"pulse"` or `"hold_until_used"`)
- [ ] All ports with `signal_lifetime: "hold_until_used"` are documented in behavior_spec.md Section 2.6.1 with latch requirement
- [ ] `constraints` block is populated (timing at minimum has `target_frequency_mhz`)
- [ ] `design_intent` block is populated
- [ ] `module_connectivity` has at least one entry for multi-module designs

**behavior_spec.md checks:**
- [ ] Section 1 (Domain Knowledge) is present
- [ ] Every module in spec.json has a corresponding Section 2
- [ ] Every sequential module (has clock port) has Section 2.1 (Cycle-Accurate Behavior) with at least 2 cycle rows
- [ ] Every module with FSM has Section 2.2 filled (States + Transitions + Initial State)
- [ ] Every sequential module has Section 2.4 (Timing Contracts) with latency and throughput specified
- [ ] Every module with control/handshake ports has Section 2.6.2 (Control Truth Table) with at least 3 rows covering reset, idle, and active states
- [ ] Section 2.6.3 (Signal Conflicts) lists all conflicting signal pairs from spec.json ports
- [ ] Section 3 (Cross-Module Timing) exists for multi-module designs

**If readiness_check fails:**
1. Identify which specific items failed
2. Ask the user via AskUserQuestion with the exact missing items listed
3. Update the relevant file(s) with the user's answer
4. Re-run readiness_check
5. Repeat until all checks pass (or user explicitly says "I can't provide this — proceed anyway")

## 1c4. Write golden_model.py (conditional — only for modules with algorithm pseudocode)

Read each module's Section 2.5 (Algorithm Pseudocode) from `behavior_spec.md`.

**Decision**: Check if ANY module has substantive algorithm pseudocode (not "No complex algorithm — direct datapath" or equivalent). If none, print `[GOLDEN] No algorithm pseudocode found — golden model not applicable` and skip to 1c-math.

If at least one module has pseudocode, use **Write** to create `$PROJECT_DIR/workspace/docs/golden_model.py`.

### Golden model template structure:

```python
"""golden_model.py — Auto-generated from behavior_spec.md Section 2.5

Pure Python reference implementation. No external dependencies.
Standard interface: run() -> list[dict] for cycle-by-cycle expected values.
"""

# --- Module: <module_name_with_pseudocode> ---

def _module_<module_name>(inputs: dict) -> list[dict]:
    """Execute the algorithm for <module_name>.
    
    Args:
        inputs: dict mapping input port names to integer values.
    
    Returns:
        list of dicts, one per clock cycle. Each dict maps signal_name -> int.
        For combinational modules, returns a single-element list.
    """
    results = []
    # --- Translated from behavior_spec.md Section X.5 Algorithm Pseudocode ---
    # ... literal translation of pseudocode to Python ...
    return results


# --- Module: <other_module_with_pseudocode> ---
# ... repeat per module ...


# --- Standard Interface ---

def run() -> list[dict]:
    """Run all module algorithms with standard test vectors.
    
    Returns:
        list indexed by cycle number, each entry is {signal_name: value}.
        For multi-module designs, keys are '<module_name>.<signal_name>'.
    """
    all_results = {}
    # Run each module that has pseudocode
    # for module_name, module_fn in MODULE_FUNCTIONS.items():
    #     module_results = module_fn(TEST_INPUTS[module_name])
    #     for i, entry in enumerate(module_results):
    #         if i not in all_results:
    #             all_results[i] = {}
    #         for sig, val in entry.items():
    #             all_results[i][f"{module_name}.{sig}"] = val
    # Convert dict to sorted list
    if not all_results:
        return []
    max_cycle = max(all_results.keys())
    return [all_results.get(i, {}) for i in range(max_cycle + 1)]


if __name__ == "__main__":
    import json
    results = run()
    for i, entry in enumerate(results):
        if entry:
            parts = [f"{k}={hex(v) if isinstance(v, int) else v}" for k, v in entry.items()]
            print(f"cycle {i}: {' '.join(parts)}")
```

### Rules:
- **Literal translation**: Translate pseudocode exactly as written — do not optimize or reinterpret
- **Standard test vectors**: Use vectors from Section 1.3 References when available (e.g., NIST KAT vectors, RFC test vectors)
- **Combinational modules**: Return a single-element list `[{output_signals}]`
- **Sequential modules**: Return one entry per clock cycle, tracking register states
- **Pure Python**: No external dependencies (no numpy, no cryptography libraries)
- **Deterministic**: Same inputs must always produce same outputs
- **Modules without pseudocode**: Skip them — they don't get a helper function in the golden model

## 1c-math. Validate spec (math checks)

After writing spec.json, verify these calculations:

1. **Counter width check**: For any module with counters or dividers, verify the declared width can hold the max value. Formula: `min_width = ceil(log2(max_count))`. If `max_count` is an exact power of 2, add 1 bit.

2. **Clock divider accuracy**: If the design involves frequency division (baud rate, PWM, timer), calculate the actual achieved frequency vs target. Error formula: `error_pct = abs(actual - target) / target * 100`. If error > 2%, add a note to the spec and suggest alternatives (fractional accumulator, different divisor).

3. **Latency sanity**: Verify timing contracts in behavior_spec.md Section 2.4 are consistent with clock frequency and module connectivity.

4. **Constraint consistency**: Verify `constraints.timing.target_frequency_mhz` matches `target_frequency_mhz` at the top level. Verify `constraints.area.max_cells` is consistent with the sum of module complexities. Verify `critical_path_budget` = floor(1000 / target_frequency_mhz / 0.1).

5. **Resource feasibility**: If `constraints.area` specifies a target device, verify the combined resource estimate (LUTs, FFs, BRAMs) fits within device limits.

If any check fails, fix spec.json or behavior_spec.md immediately.

## 1d. Hook

```bash
# Mandatory checks
test -f "$PROJECT_DIR/workspace/docs/spec.json" && grep -q "module_name" "$PROJECT_DIR/workspace/docs/spec.json" && test -f "$PROJECT_DIR/workspace/docs/behavior_spec.md" && grep -q "Domain Knowledge" "$PROJECT_DIR/workspace/docs/behavior_spec.md" || { echo "[HOOK] FAIL"; exit 1; }

# Optional golden model check (only if file was generated)
if [ -f "$PROJECT_DIR/workspace/docs/golden_model.py" ]; then
    python3 -c "import py_compile; py_compile.compile('$PROJECT_DIR/workspace/docs/golden_model.py', doraise=True)" 2>/dev/null && echo "[HOOK] golden_model.py: syntax OK" || echo "[HOOK] WARN: golden_model.py has syntax errors"
fi

echo "[HOOK] PASS"
```

If FAIL → fix and rewrite the failing file(s) immediately.

## 1e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "architect"
```

Mark Stage 1 task as **completed** using TaskUpdate.

## 1f. Journal

```bash
GOLDEN_NOTE=""
if [ -f "$PROJECT_DIR/workspace/docs/golden_model.py" ]; then
    GOLDEN_NOTE=", workspace/docs/golden_model.py"
fi
printf "\n## Stage: architect\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/spec.json, workspace/docs/behavior_spec.md${GOLDEN_NOTE}\n**Notes**: Specification and behavior spec generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

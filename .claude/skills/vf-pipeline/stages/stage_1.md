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
| -1 | rst_n asserted | clear all registers | all outputs = 0 |
| 0 | rst_n de-asserted | ... | ... |

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
- **Reset recovery**: {N} cycles after rst_n de-assertion

### 2.5 Algorithm Pseudocode
{Step-by-step pseudocode for each complex operation. If user provided pseudocode in Stage 1D,
reproduce it EXACTLY here. If no complex algorithm, state: "No complex algorithm — direct datapath."}

INPUT: data_in[WIDTH-1:0], start
OUTPUT: data_out[WIDTH-1:0], done

Step 1: [description of what happens]
Step 2: ...
Step N: [final output]

### 2.6 Protocol Details
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

## 1c3. Readiness Check (gate — MUST pass before proceeding)

After writing both spec.json and behavior_spec.md, verify completeness. If ANY check fails, STOP and ask the user using AskUserQuestion.

**spec.json checks:**
- [ ] `design_name` is non-empty
- [ ] At least one module with `module_type: "top"` exists
- [ ] Every module has at least one port
- [ ] `constraints` block is populated (timing at minimum has `target_frequency_mhz`)
- [ ] `design_intent` block is populated
- [ ] `module_connectivity` has at least one entry for multi-module designs

**behavior_spec.md checks:**
- [ ] Section 1 (Domain Knowledge) is present
- [ ] Every module in spec.json has a corresponding Section 2
- [ ] Every sequential module (has clock port) has Section 2.1 (Cycle-Accurate Behavior) with at least 2 cycle rows
- [ ] Every module with FSM has Section 2.2 filled (States + Transitions + Initial State)
- [ ] Every sequential module has Section 2.4 (Timing Contracts) with latency and throughput specified
- [ ] Section 3 (Cross-Module Timing) exists for multi-module designs

**If readiness_check fails:**
1. Identify which specific items failed
2. Ask the user via AskUserQuestion with the exact missing items listed
3. Update the relevant file(s) with the user's answer
4. Re-run readiness_check
5. Repeat until all checks pass (or user explicitly says "I can't provide this — proceed anyway")

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
test -f "$PROJECT_DIR/workspace/docs/spec.json" && grep -q "module_name" "$PROJECT_DIR/workspace/docs/spec.json" && test -f "$PROJECT_DIR/workspace/docs/behavior_spec.md" && grep -q "Domain Knowledge" "$PROJECT_DIR/workspace/docs/behavior_spec.md" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

If FAIL → fix and rewrite the failing file(s) immediately.

## 1e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "architect"
```

Mark Stage 1 task as **completed** using TaskUpdate.

## 1f. Journal

```bash
printf "\n## Stage: architect\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/spec.json, workspace/docs/behavior_spec.md\n**Notes**: Specification and behavior spec generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

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

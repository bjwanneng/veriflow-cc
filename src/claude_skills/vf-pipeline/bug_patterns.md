# VeriFlow Known Bug Patterns

Catalog of recurring RTL bug patterns discovered in real projects.
Referenced by SKILL.md Error Recovery Step 1.5 for rapid root-cause matching.

Each pattern includes: symptom, root cause, fix, and **prevention rule** for
earlier-stage detection.

---

## Pattern 1: Latch-Then-Load Race (Cross-Module)

**Discovered in**: Cryptographic hash core (top-wrapper latches input, submodule loads same cycle)

### Symptom

First data block produces wrong output. Subsequent blocks may or may not be
correct depending on whether the latched register happens to hold valid data
from a previous operation.

### Root Cause

A top-level module latches an input into a register on `posedge N`. On the
**same** `posedge N`, a submodule reads that register as its load data. Due to
NBA semantics, the submodule sees the OLD (pre-latch) value — typically the
reset default (zero).

```
posedge N:  top.latch_reg   <= input_data    (NBA scheduled)
posedge N:  sub.load_en=1, sub.data_in=top.latch_reg  (sees OLD value!)
```

### Fix

Connect the submodule directly to the **external input** (combinational path),
not the latched register. The latch is unnecessary if the submodule consumes
the data on the same cycle.

```verilog
// WRONG — race condition
u_submodule (.data_port(latched_reg), ...);

// CORRECT — direct combinational path
u_submodule (.data_port(input_signal), ...);
```

### Prevention

**Stage 3 (Timing)**: In the cross-module timing table, if a signal is marked
"0 (combinational)" from producer to consumer, verify the RTL does NOT route
it through a registered latch.

**Stage 5 (Review)**: Check for this pattern:
- Signal X is an input port of module M
- Module M contains a register `X_latched` updated on `posedge clk`
- A submodule of M connects to `X_latched` (not `X` directly)
- The submodule's load enable fires on the same cycle as the latch write
→ Flag as **potential race condition**

---

## Pattern 2: Shift Register Window Drain

**Discovered in**: Cryptographic hash core (message expansion module)

### Symptom

Shift register outputs are correct for the first N rounds (where N = register
depth), then all outputs become zero or stale for all subsequent rounds.

### Root Cause

A shift register shifts every cycle (consuming one element from position 0),
but the **replenishment** (new element appended at the end) is gated by a
conditional that suppresses injection during early rounds.

```verilog
// WRONG — window drains when round_cnt < THRESHOLD
wire [31:0] next_elem = (round_cnt < THRESHOLD) ? 32'd0 : expansion_func(...);
```

After THRESHOLD shifts with zero injection, all original data has been shifted
out, leaving the register full of zeros. The expansion formula then has no
valid inputs to work with.

### Fix

**Always compute and inject the next element**, regardless of whether it's
"needed" this round. For a sliding-window algorithm, the window must remain
full at all times.

```verilog
// CORRECT — always replenish
wire [31:0] next_elem = expansion_func(...);
```

### Prevention

**Stage 4 (Coder)**: When generating shift-register-based message expansion,
the coder MUST follow this rule:

> **Sliding Window Replenishment Rule**: If a shift register shifts every
> active cycle, the next-element computation MUST NOT be gated by a round
> counter or conditional. Always compute and inject. The round counter only
> determines whether the injected element is consumed externally, not whether
> it's computed.

**Stage 5 (Review)**: Flag any shift register where:
- `reg[i] <= reg[i+1]` (shift) happens unconditionally during active cycles
- `reg[N-1] <= next_elem` where `next_elem` is gated by a condition
- The gate condition depends on `round_cnt < THRESHOLD` where THRESHOLD ≤ N

---

## Pattern 3: Algorithm Initial State Incomplete

**Discovered in**: Cryptographic hash core (chaining value registers not initialized)

### Symptom

Output is off by a constant XOR — specifically, the output equals the raw
computation result instead of `initial_value ^ computation_result` (or vice
versa). Multi-block messages may work for block 2+ but fail on block 1.

### Root Cause

The algorithm defines two sets of initial state:
1. Working registers — loaded from algorithm constants (e.g., IV) for first block
2. Chaining/accumulation registers — also initialized to algorithm constants for first block

The coder correctly initialized set 1 but missed set 2. The chaining registers
remained at their reset value (0), so `output = chaining_reg(=0) ^ result = result`
instead of `IV ^ result`.

### Fix

During the load phase for the first block, initialize ALL registers that
participate in the final output computation.

```verilog
if (load_en && is_first_block) begin
    // Working registers
    work_A_next = INIT_CONST_A; ... work_H_next = INIT_CONST_H;
    // Chaining registers — ALSO initialize
    chain_V0_next = INIT_CONST_A; ... chain_V7_next = INIT_CONST_H;
end
```

### Prevention

**Stage 3 (Timing)**: Add an "Initial State Completeness Check" to the timing
model. For each output signal, trace backwards through the computation:

1. List all registers that contribute to the output expression
2. For each register, verify it has a defined initial value for the first
   operational cycle (not just "reset to 0")
3. If a register feeds into an XOR/ADD chain where 0 is NOT a safe default,
   flag it as "requires explicit initialization"

**Stage 4 (Coder)**: The coder prompt must include this rule:

> **Initial State Completeness**: For hash/cipher algorithms, list ALL
> registers from the algorithm specification's initialization section.
> Cross-check: for every register that feeds into the final output
> (e.g., `data_out = chain_reg ^ work_reg`), verify that BOTH operand register
> sets are initialized correctly. Do NOT assume "reset to 0" is safe for
> XOR-based output paths.

**Stage 5 (Review)**: Check for registers where:
- The register is read in an expression that contributes to a module output
- The register's only initialization path is the reset block (value = 0)
- The output expression is XOR-based (where 0 is a meaningful but potentially
  wrong operand)
→ Flag as **potential initialization gap**

---

## Pattern 4: Off-By-One Pipeline Delay

*(From SKILL.md Pattern A)*

### Symptom

Output data is correct but arrives one cycle late (or early). Simulation shows
the expected value at cycle N+1 instead of cycle N.

### Prevention

**Stage 3 (Timing)**: For every output assertion in the timing model, specify
both the expected value AND the expected cycle. If the value appears one cycle
off, check for an extra register stage in the output path.

---

## Pattern 5: Reset Not Clearing Output Register

*(From SKILL.md Pattern B)*

### Prevention

**Stage 5 (Review)**: Verify that every output port is driven by a register
(or combinational logic derived from a register) that is included in the
reset block.

---

## Pattern 6: FSM Stuck / Missing Transition

*(From SKILL.md Pattern C)*

### Prevention

**Stage 5 (Review)**: For every FSM state, verify that all transition
conditions are reachable and that every state has a defined next-state for
all input combinations (explicit `default` branch).

---

## Pattern 7: Handshake Violation

*(From SKILL.md Pattern D)*

### Prevention

**Stage 3 (Timing)**: Verify that the timing model's handshake scenarios
include: (a) valid asserted before ready, (b) valid held until ready, (c)
valid deasserted after ready. For `hold_until_ack` protocols, verify valid
persistence.

---

## Pattern 8: Counter Range Off-By-One

*(From SKILL.md Pattern E)*

### Prevention

**Stage 4 (Coder)**: Use `integer` for loop counters in testbenches and
simulation-only code. For synthesis, use sufficiently wide register widths
and verify terminal condition uses the correct comparison (`<` vs `<=`).

**Stage 5 (Review)**: For every counter with `reg [N:0]`, verify the terminal
value is reachable without overflow. If the terminal value equals `2^N - 1`,
the counter wraps correctly. If it equals `2^N`, the counter overflows.

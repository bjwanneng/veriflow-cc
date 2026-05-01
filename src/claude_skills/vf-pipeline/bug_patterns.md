# VeriFlow Known Bug Patterns

Catalog of recurring RTL bug patterns discovered in real projects.
Referenced by SKILL.md Error Recovery Step 1.5 for rapid root-cause matching.

Each pattern includes: symptom, root cause, fix, and **prevention rule** for
earlier-stage detection.

---

## Pattern 1: Latch-Then-Load Race (Cross-Module)

**Discovered in**: Multi-module design (top-wrapper latches input, submodule loads same cycle)

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
posedge N:  top.latch_reg  <= input_data     (NBA scheduled)
posedge N:  sub.data_en=1, sub.data_in=top.latch_reg  (sees OLD value!)
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

**verify_fix stage**: In the cross-module timing analysis, if a signal is marked
"0 (combinational)" from producer to consumer, verify the RTL does NOT route
it through a registered latch.

**codegen stage**: Check for this pattern:
- Signal X is an input port of module M
- Module M contains a register `X_latched` updated on `posedge clk`
- A submodule of M connects to `X_latched` (not `X` directly)
- The submodule's load enable fires on the same cycle as the latch write
→ Flag as **potential race condition**

---

## Pattern 2: Shift Register Window Drain

**Discovered in**: Data expansion module (sliding-window shift register)

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

**codegen stage**: When generating shift-register-based data expansion,
the coder MUST follow this rule:

> **Sliding Window Replenishment Rule**: If a shift register shifts every
> active cycle, the next-element computation MUST NOT be gated by a step
> counter or conditional. Always compute and inject. The step counter only
> determines whether the injected element is consumed externally, not whether
> it's computed.

**verify_fix stage**: Flag any shift register where:
- `reg[i] <= reg[i+1]` (shift) happens unconditionally during active cycles
- `reg[N-1] <= next_elem` where `next_elem` is gated by a condition
- The gate condition depends on `round_cnt < THRESHOLD` where THRESHOLD ≤ N

---

## Pattern 3: Algorithm Initial State Incomplete

**Discovered in**: Iterative datapath (accumulator registers not initialized)

### Symptom

Output is off by a constant XOR — specifically, the output equals the raw
computation result instead of `initial_value ^ computation_result` (or vice
versa). Multi-block messages may work for block 2+ but fail on block 1.

### Root Cause

The algorithm defines two sets of initial state:
1. Working registers — loaded from algorithm-defined initial values for first operation
2. Accumulator/feedback registers — also initialized to algorithm-defined values for first operation

The coder correctly initialized set 1 but missed set 2. The accumulator registers
remained at their reset value (0), so `output = accum_reg(=0) ^ result = result`
instead of `INIT_VALUE ^ result`.

### Fix

During the load phase for the first block, initialize ALL registers that
participate in the final output computation.

```verilog
if (init_en && is_first_operation) begin
    // Working registers
    work_reg_A_next = INIT_VAL_A;
    work_reg_B_next = INIT_VAL_B;
    // Accumulator registers — ALSO initialize
    accum_reg_A_next = INIT_VAL_A;
    accum_reg_B_next = INIT_VAL_B;
end
```

### Prevention

**codegen stage**: Add an "Initial State Completeness Check" during code generation.
For each output signal, trace backwards through the computation:

1. List all registers that contribute to the output expression
2. For each register, verify it has a defined initial value for the first
   operational cycle (not just "reset to 0")
3. If a register feeds into an XOR/ADD chain where 0 is NOT a safe default,
   flag it as "requires explicit initialization"

**verify_fix stage**: Check for registers where:
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

**verify_fix stage**: For every output assertion in the testbench, specify
both the expected value AND the expected cycle. If the value appears one cycle
off, check for an extra register stage in the output path.

---

## Pattern 5: Reset Not Clearing Output Register

*(From SKILL.md Pattern B)*

### Prevention

**verify_fix stage**: Verify that every output port is driven by a register
(or combinational logic derived from a register) that is included in the
reset block.

---

## Pattern 6: FSM Stuck / Missing Transition

*(From SKILL.md Pattern C)*

### Prevention

**verify_fix stage**: For every FSM state, verify that all transition
conditions are reachable and that every state has a defined next-state for
all input combinations (explicit `default` branch).

---

## Pattern 7: Handshake Violation

*(From SKILL.md Pattern D)*

### Prevention

**verify_fix stage**: Verify that the testbench's handshake scenarios
include: (a) valid asserted before ready, (b) valid held until ready, (c)
valid deasserted after ready. For `hold_until_ack` protocols, verify valid
persistence.

---

## Pattern 8: Counter Range Off-By-One

*(From SKILL.md Pattern E)*

### Prevention

**codegen stage**: Use `integer` for loop counters in testbenches and
simulation-only code. For synthesis, use sufficiently wide register widths
and verify terminal condition uses the correct comparison (`<` vs `<=`).

**verify_fix stage**: For every counter with `reg [N:0]`, verify the terminal
value is reachable without overflow. If the terminal value equals `2^N - 1`,
the counter wraps correctly. If it equals `2^N`, the counter overflows.

---

## Pattern 9: Premature Timing Hypothesis

**Discovered in**: Multiple projects — debuggers assume timing/pipeline issues
when the real cause is a logic error (wrong formula, wrong condition, wrong index).

### Symptom

Debug session spends significant time modifying FSM timing, adding delay
registers, or adjusting pipeline stages, without resolving the failure.

### Root Cause

When computation output is wrong, the default assumption is often "pipeline
alignment" or "register timing." But most RTL bugs in synchronous
single-clock-domain designs are **logic errors** — incorrect formulas,
wrong conditional guards, missing initial values, or incorrect array indices.
Timing issues are rare in fully synchronous designs with a single clock domain.

### Fix

Before investigating timing:
1. Run golden model cycle-by-cycle comparison (algorithm designs) or
   protocol compliance check (interface designs)
2. Classify: is the wrong value **(A) data-wrong** or **(B) timing-wrong**?
3. Data-wrong → trace the signal's computation logic (formula, condition, index)
4. Timing-wrong → then investigate pipeline alignment

**Key discriminator**: If the divergent value is zero or a constant when the
golden model expects a computed value, it is almost certainly a logic error
(conditional gating to zero, missing initialization, wrong formula), not a
timing issue. Zero is never a timing symptom.

### Prevention

**verify_fix stage**: When a simulation fails, the mandatory data collection
step (Error Recovery Step 0) prevents this pattern:

1. Run golden model diff to find first divergence cycle
2. Examine the divergent value:
   - Zero or constant → logic error (Type A or D)
   - Correct value, wrong cycle → timing error (Type B)
3. Never skip to "timing fix" without completing data-driven classification

**Rule**: Never assume timing issues without data. If the golden model diff
shows a zero or constant at the divergence point, it's a LOGIC error, not
a timing error.

---

## Pattern 10: Finalize-State Combinational Leak

**Discovered in**: SM3 hash core (DONE state reading `_new` wires instead of `_reg`)

### Symptom

Hash/digest output is completely wrong — values are off by one full round of
computation. The output appears to be the result of N+1 rounds instead of N
rounds. Multi-block messages may also fail because chaining values are computed
from the wrong state.

### Root Cause

In an iterative computation FSM (IDLE → CALC → DONE), combinational `_new` wires
represent the **next** cycle's register values — i.e., what registers WILL become
after the current round's computation is applied. In the DONE/finalize state, the
designer incorrectly used these combinational wires instead of the actual registered
values.

```verilog
// WRONG — reads next-state (combinational) values in DONE state
STATE_DONE: begin
    V0 <= V0 ^ a_new;   // a_new = TT1 (an extra compression round!)
    V1 <= V1 ^ b_new;
    hash_out_r <= {V0 ^ a_new, V1 ^ b_new, ...};
end

// CORRECT — reads current registered values in DONE state
STATE_DONE: begin
    V0 <= V0 ^ A_reg;   // A_reg holds the result after 64 rounds
    V1 <= V1 ^ B_reg;
    hash_out_r <= {V0 ^ A_reg, V1 ^ B_reg, ...};
end
```

The `_new` wires are fed by the combinational logic that computes the next round.
When the FSM transitions to DONE (after round 63), these wires hold what round 64
WOULD produce — but round 64 was never meant to execute. The registered `_reg`
values hold the correct result of 64 completed rounds.

### Fix

In DONE/finalize states, use ONLY `_reg` (registered) values. Never use `_new`
(combinational next-state) wires. The `_new` wires are valid ONLY inside the
CALC state's sequential block for updating registers.

### Prevention

**codegen stage**: Add this rule to the coder's checklist:

> **Finalize-State Register Read Rule**: In DONE/finalize FSM states, ALL output
> computations and register updates MUST use `_reg` (registered) values only.
> Never use `_new` (combinational next-state) wires — they represent the NEXT
> computation round, not the current state.

**verify_fix stage**: Flag any DONE/finalize state where:
- An expression references a `_new` wire (combinational next-state signal)
- The `_new` wire is derived from the same combinational logic as the CALC state
→ This applies an extra unintended computation round.

---

## Pattern 11: Merkle-Damgård Chaining Register Reset

**Discovered in**: SM3 hash core (V0-V7 not re-initialized for new messages)

### Symptom

First message hashes correctly. Second message produces wrong output. Specifically,
test 2 fails after test 1 passes in the same simulation run.

### Root Cause

In Merkle-Damgård hash constructions, chaining registers (V0-V7) accumulate
intermediate results across blocks. When a new message starts, these registers
MUST be re-initialized to IV — but the code only initialized the working registers
(A-H), leaving V registers with stale values from the previous message.

```verilog
// WRONG — V registers retain stale values from previous message
if (is_first_block) begin
    A_reg <= IV0; B_reg <= IV1; ... H_reg <= IV7;
    // V0-V7 NOT re-initialized!
end

// CORRECT — re-initialize BOTH working and chaining registers
if (is_first_block) begin
    A_reg <= IV0; B_reg <= IV1; ... H_reg <= IV7;
    V0 <= IV0; V1 <= IV1; ... V7 <= IV7;  // ALSO re-init chaining values
end
```

### Fix

For iterated hash constructions (Merkle-Damgård, sponge, etc.), when starting a
new message, re-initialize ALL state registers that persist across blocks — both
working registers AND chaining/accumulator registers.

### Prevention

**codegen stage**: For hash/digest designs with dual register sets (working +
chaining), verify that the `is_first_block` initialization path covers BOTH sets.

**verify_fix stage**: Flag designs where:
- Two sets of registers exist (working A-H and chaining V0-V7)
- The `is_first_block` init path only covers one set
→ The other set retains stale state from previous messages.

---

## Pattern 12: FSM Latch-on-Transition Race

**Discovered in**: Generic FSM designs where pre-NBA state values are used to
make decisions during the same cycle the state is transitioning.

### Symptom

An FSM control signal appears to be "one cycle late" or fails to assert on the
expected cycle. Specifically, a signal that should be latched when the FSM
transitions from STATE_A to STATE_B is never captured, because the latch logic
checks `state_reg == STATE_A` but `state_reg` has already been scheduled to
update via NBA.

### Root Cause

In a single always block, the FSM updates `state_reg <= next_state` at the
bottom. All `case (state_reg)` branches above it run with the PRE-NBA value.
This is normally correct. However, if the designer uses `case (state_reg)` to
detect a transition (e.g., "when in IDLE and transitioning to CALC, latch the
input"), the `STATE_IDLE` branch fires with the OLD state value — which IS
correct for the current cycle. But if the state was already transitioned by a
combinational `next_state` assignment that ran before the case statement, the
branch may not match.

The more subtle variant: the designer writes `if (state_reg == STATE_IDLE)`
inside the sequential block, expecting it to fire on the IDLE→CALC transition
cycle. It does fire — but `state_reg` still holds STATE_IDLE because the NBA
hasn't applied yet. The problem arises when the designer ALSO writes the same
condition in a SECOND sequential block (or expects it NOT to fire in a
subsequent cycle when state_reg has already advanced).

### Fix

Detect state transitions explicitly using both `state_reg` and `next_state`
before the state register update:

```verilog
always @(posedge clk) begin
    if (rst) begin
        state_reg <= STATE_IDLE;
        latched_input <= 'd0;
    end else begin
        // Detect transition BEFORE state_reg updates
        if (state_reg == STATE_IDLE && next_state == STATE_CALC) begin
            latched_input <= data_input;  // captures input on transition cycle
        end

        case (state_reg)
            STATE_IDLE:  counter_reg <= 'd0;
            STATE_CALC:  counter_reg <= counter_reg + 1'b1;
            default:     ;
        endcase

        state_reg <= next_state;
    end
end
```

**Alternative approach** (Mealy-style combinational latch):
```verilog
// Combinational block — no registration delay
wire transition_to_calc = (state_reg == STATE_IDLE) && start_valid;
```

### Prevention

**codegen stage**: When building the cycle timing table, for each FSM state
transition A→B where an input must be latched:
1. Mark the latch as happening "at the A→B boundary"
2. Use explicit transition detection: `(state_reg == STATE_A && next_state == STATE_B)`
3. Do NOT rely on `case (state_reg) STATE_A:` alone for transition-time actions

**verify_fix stage**: For any FSM that latches inputs on state transitions:
- Verify the latch condition uses both `state_reg` and `next_state`
- Flag conditions that only check `state_reg` for one-shot capture actions
→ These will either fire at the wrong time or never fire depending on NBA ordering

# VeriFlow Bug Pattern Knowledge Base

Common RTL bug patterns discovered across VeriFlow pipeline projects. Reference this file during Error Recovery (SKILL.md Step 1.5) to accelerate root cause analysis.

---

## Pattern 1: NBA Cross-Module Race (same-cycle produce-and-consume)

**Severity**: Critical — causes silent data corruption.

**What happens**: Module A produces a registered signal at `posedge N` (via NBA `<=`). Module B, running at the same `posedge N`, reads the signal in its active region — before NBA applies. Module B sees the OLD value from cycle N-1.

**Example (SM3 project)**:
```
Cycle N (posedge):
  sm3_core: first_block_latched_reg <= is_first_block_reg  // NBA scheduled
  sm3_compress: reads first_block_i                         // active region — sees OLD value!
  sm3_compress: loads from zeroed V instead of IV constants
  → hash_out = 0x00...00 (wrong)
```

**Root cause**: `first_block_latched_reg` is updated via NBA at `posedge N`, but `sm3_compress` reads `first_block_i` in its combinational or sequential block at the same `posedge N`. The NBA hasn't applied yet.

**Detection**:
- Waveform table: signal is correct 1 cycle after [FAIL]
- At [FAIL] cycle: producer's `_reg` has old value in consumer's always block
- Pattern A in SKILL.md Error Recovery

**Fix — Approach A (preferred): Combinational bypass**. Expose the producer's next-state value as a wire, bypassing the register. Consumer reads the combinational signal directly — it sees the value that WILL be registered at the next posedge.

```verilog
// Producer: expose next-state value as combinational wire
wire flag_next;
assign flag_next = (msg_valid && ready) ? input_pulse : flag_reg;

always @(posedge clk) begin
    flag_reg <= flag_next;
    if (rst) flag_reg <= 1'b0;
end

// Consumer: reads flag_next (combinational), not flag_reg
// flag_next is valid in the SAME cycle msg_valid fires
sm3_compress u_compress (
    .flag_i (flag_next)  // combinational — no NBA delay
);
```

**Fix — Approach B: Accept pipeline delay**. If one-cycle latency is acceptable, keep both producer and consumer on `@(posedge clk)`, and the consumer reads the registered output. The consumer must be designed to expect the signal one cycle later.

```verilog
// Producer: standard posedge register
always @(posedge clk) begin
    if (msg_valid && ready)
        flag_reg <= input_pulse;
end

// Consumer: reads flag_reg — value arrives one cycle after msg_valid
// Consumer FSM must account for this one-cycle delay in its timing
```

**Approach selection guide**:
| Condition | Approach |
|-----------|----------|
| Consumer needs value in same cycle as msg_valid | A: Combinational bypass |
| Consumer can tolerate 1-cycle delay | B: Accept pipeline delay |
| Signal changes infrequently, consumer is deep pipeline | A or B both work |

**WARNING — DO NOT use `@(negedge clk)` in synthesizable RTL**:
- Creates half-cycle paths — makes timing closure extremely difficult
- Depends on clock duty cycle — fragile across PVT corners
- Synthesis tools may ignore or misinterpret the negedge sensitivity
- This is a simulation-only workaround that causes simulation-synthesis mismatch

**Prevention**:
- `coding_style.md` Section 24.1 (Producer-Consumer Cycle Annotation) — annotate every cross-module signal with producer/consumer cycle
- Stage 1 Cross-Module Timing Check (Check B: Signal Latency Consistency)
- When a signal must be consumed same-cycle: use combinational bypass, not negedge clock

---

## Pattern 2: Signal Lifetime Mismatch (pulse consumed late)

**Severity**: Critical — causes FSM to hang or produce no output.

**What happens**: A signal arrives as a 1-cycle pulse (e.g., `is_last` with `msg_valid` on cycle 0) but is consumed many cycles later (e.g., FSM reads `is_last` in DONE state at cycle 67). Without latching, the consumer sees the deasserted value.

**Example (SM3 project)**:
```
Cycle 0:  msg_valid=1, is_last=1  ← signal asserted as pulse
Cycle 1:  msg_valid=0, is_last=0  ← signal deasserted (testbench cleanup)
...
Cycle 67: FSM in DONE, checks is_last → 0 (STALE!)
          → hash_valid not asserted, wait(hash_valid) hangs forever
```

**Root cause**: `is_last` is a 1-cycle pulse input but the consumer (FSM) samples it 67 cycles later. No latch register stores the value.

**Detection**:
- Waveform: `hash_valid` never asserts, simulation hangs at `wait(hash_valid)`
- FSM stays in CALC or DONE without transitioning
- Pattern C in SKILL.md Error Recovery (FSM stuck)
- Golden model comparison: expected hash_valid at cycle ~70, got never

**Fix**: Add latch register in wrapper module, set on signal assertion, clear after consumption.

```verilog
reg is_last_latched_reg;

// Standard posedge latch — by the time FSM samples is_last (tens of cycles later),
// the NBA has long since applied. No negedge needed.
always @(posedge clk) begin
    if (rst)
        is_last_latched_reg <= 1'b0;
    else if (hash_valid)                    // consumed — clear for next message
        is_last_latched_reg <= 1'b0;
    else if (msg_valid && ready)            // signal asserted — latch it
        is_last_latched_reg <= is_last;
end
// FSM now reads is_last_latched_reg instead of raw is_last
```

**Why `@(posedge clk)` is correct here**: The `is_last` flag, once latched, is consumed tens of cycles later (FSM DONE state). The NBA has long since applied. The only requirement is that the latch captures the pulse before it disappears — standard posedge is sufficient since the hold_until_used signal's consumer reads it far in the future.

**If the consumer needs the latched value on the very next posedge** (same-cycle produce-and-consume), use Pattern 1 Approach A (combinational bypass), not negedge clock.

**Prevention**:
- Stage 1: `signal_lifetime: "hold_until_used"` field in spec.json port definition
- Stage 1 Cross-Module Timing Check (Check D: Signal Lifetime Mismatch)
- `coding_style.md` Section 24.3 (Signal Lifetime)

---

## Pattern 3: Counter Width Overflow (N-bit counter, 2^N iterations)

**Severity**: Critical — causes infinite simulation loops.

**What happens**: A counter declared as `reg [N-1:0]` counts from 0 to `2^N - 1`. When incremented at `2^N - 1`, it wraps to 0. If a termination condition checks for a specific value that was skipped, or if the loop variable itself overflows...

**Example (SM3 project — testbench)**:
```verilog
// BUG: infinite loop in testbench
reg [5:0] round_cnt;  // 6-bit counter, max value = 63
for (round_cnt = 0; round_cnt < 64; round_cnt = round_cnt + 1) begin
    @(posedge clk);
end
// At round_cnt=63: 63 < 64 → execute body, round_cnt++ → 63+1 = 0 (6-bit wrap) → 0 < 64 → loop forever!
```

**Root cause**: `reg [5:0]` wraps from 63+1 → 0. The loop termination `round_cnt < 64` is always true after wrap.

**Detection**:
- Simulation runs forever without `$finish`
- Waveform shows counter cycling 0→63→0→63... indefinitely

**Fix**: Use `integer` for loop counters, or add explicit overflow check.

```verilog
// Fix: integer has unlimited range
integer j;
for (j = 0; j < 64; j = j + 1) begin
    @(posedge clk);
end
```

**Better (SystemVerilog)**: Declare the loop variable inline — scoped to the loop, no global pollution.

```systemverilog
// SystemVerilog: inline declaration, limited scope
for (int i = 0; i < 64; i++) begin
    @(posedge clk);
end
// 'i' is not visible outside the for loop
```

**Prevention**:
- `coding_style.md` Section 17a (Array Index Bounds Safety)
- Stage 1 math check: `min_width = ceil(log2(max_count+1))` — verify declared width ≥ required
- Prefer `integer` or inline-declared `int` for all loop counters — never use fixed-width `reg [N-1:0]`

---

## Pattern 4: Shift Register Load/Shift Alignment

**Severity**: High — causes all subsequent computation to be off by one position.

**What happens**: When `load_en` and `calc_en` are co-asserted (both 1 on the same cycle), and the shift register uses `if/else-if` priority, one operation silently wins and the other is skipped. This causes the shift register output to be shifted by one position relative to the expected round.

**Example (SM3 project)**:
```verilog
// sm3_w_gen: shift register with if/else-if priority
always @(posedge clk) begin
    if (load_en) begin
        w_reg[0:15] <= msg_block_words;  // load takes priority
    end else if (calc_en) begin
        // shift: w_reg[0] ← w_reg[1], ..., w_reg[15] ← next_W
    end
end

// FSM: co-asserts load_en + calc_en on IDLE→CALC transition
// Result: load executes, shift is SKIPPED → shift register is one position behind
// At round 0: output = W[0] ✓ (loaded correctly)
// At round 1: output = W[0] ✗ (should be W[1] — shift was skipped!)
```

**Root cause**: FSM co-asserts `load_en=1, calc_en=1` on transition cycle. Shift register uses `if/else-if`, so `else if (calc_en)` never executes when `load_en=1`. The shift that should push W[1] to the output never happens.

**Detection**:
- Waveform: shift register output at round j shows W[j-1] instead of W[j]
- Golden model: computation diverges from round 1 onwards
- Pattern F in SKILL.md Error Recovery (Data value mismatch)
- Per-round golden comparison shows first deviation at round 1 (not round 0)

**Fix**: FSM must NOT co-assert `load_en` and `calc_en`. Add a dedicated load cycle before calc.

```verilog
// FSM fix: separate LOAD state
STATE_IDLE: if (msg_valid && ready) next_state = STATE_LOAD;  // load only
STATE_LOAD: next_state = STATE_CALC;                           // calc only, no load
```

Alternatively, use parallel `if` (not `else-if`) in the shift register, so both operations execute:
```verilog
if (load_en) w_reg[0:15] <= msg_block_words;
if (calc_en) begin /* shift logic */ end  // separate if — both can execute
```

**Prevention**:
- `coding_style.md` Section 24.6 (Shift Register Alignment)
- Stage 1 Cross-Module Timing Check (Check A: Control Signal Co-assertion Consistency)
- Stage 1 behavior_spec.md Section 2.6.3 (Signal Conflicts) — must declare `load_en`/`calc_en` exclusion
- **SVA assertion** (SystemVerilog, for simulation only — not synthesizable): catch co-assertion immediately at the source rather than debugging downstream symptoms
  ```systemverilog
  // In the FSM module or top-level wrapper:
  assert property (@(posedge clk) disable iff (rst)
      !(load_en && calc_en))
  else $error("[%0t] load_en and calc_en co-asserted!", $time);
  ```

---

## Pattern 5: Testbench NBA Sampling Race

**Severity**: Medium — causes false test failures (test fails but RTL is correct).

**What happens**: Verilog testbench checks registered DUT outputs at `@(posedge clk)`. Both the testbench process and DUT `always @(posedge clk)` blocks execute in the same active region. The execution order is non-deterministic. If the testbench checks first, it reads stale values.

**Example (SM3 project)**:
```verilog
// Testbench: checks at posedge — RACE!
@(posedge clk);
if (data_out !== expected) $display("[FAIL] ...");  // may read stale value!

// DUT: NBA schedules update at same posedge
always @(posedge clk) begin
    data_out_reg <= new_value;  // NBA — applies AFTER active region
end
assign data_out = data_out_reg;
```

**Detection**:
- Intermittent failures: test passes sometimes, fails sometimes (order-dependent)
- Signal value at [FAIL] is correct one cycle later (off-by-one)
- Pattern A in SKILL.md Error Recovery (Off-by-one pipeline delay)

**Fix in Verilog TB**: Sample at `@(negedge clk)` after the relevant posedge.

```verilog
// Fix: wait for NBA to settle at negedge
data_in = value;
@(posedge clk);   // DUT samples input
@(negedge clk);   // NBA has applied, outputs stable
if (data_out !== expected) $display("[FAIL] ...");  // correct value
```

**Fix in cocotb** (preferred): `await RisingEdge(dut.clk)` uses VPI callbacks that fire AFTER NBA. No race condition exists.

```python
dut.data_in.value = value
await RisingEdge(dut.clk)  # VPI callback — NBA has applied
assert dut.data_out.value == expected  # always correct
```

**Prevention**:
- Use cocotb (preferred) — `await RisingEdge(dut.clk)` fires AFTER NBA, eliminating the race at the mechanism level
- For Verilog TBs: use `@(negedge clk)` pattern documented in stage_3.md template
- **SystemVerilog Clocking Block** (for SV testbenches): `clocking cb @(posedge clk); ... endclocking` defines a skew that cleanly separates DUT sampling from TB driving, eliminating the race at the language level. This is the IEEE-standardized solution for the TB-DUT race condition.

  ```systemverilog
  // Clocking block defines 1ns output skew (drive after posedge)
  // and 1ns input skew (sample before posedge)
  clocking cb @(posedge clk);
      default input #1ns output #1ns;
      output msg_valid, msg_block, is_last;
      input  ready, hash_valid, hash_out;
  endclocking
  ```

---

## Pattern 6: iverilog Memory Array NBA Address Race

**Severity**: Medium — iverilog-specific. Simulation passes, but writes to wrong address.

**What happens**: `iverilog` evaluates the array index for `ram[addr] <= wdata` at NBA application time, not scheduling time. If `addr` changes via NBA in the same cycle, the write targets the NEW address instead of the old one.

**Example**:
```verilog
always @(posedge clk) begin
    addr_reg <= new_addr;        // NBA: addr changes
    ram[addr_reg] <= wdata;      // BUG: iverilog uses new_addr (post-NBA), not old_addr
end
```

**Root cause**: iverilog evaluates `addr_reg` in the NBA region, where it has already been updated.

**Fix**: Pre-compute the write address as a combinational `wire`, then use that wire as the array index with standard NBA (`<=`). The wire captures the address value BEFORE NBA applies, eliminating the race without violating the "no blocking assignment in sequential blocks" rule.

```verilog
// Combinational address pre-computation — evaluated in active region
wire [ADDR_W-1:0] write_addr;
assign write_addr = addr_next;  // or: addr_reg + offset, decoded address, etc.

always @(posedge clk) begin
    addr_reg <= write_addr;         // NBA: register update
    ram[write_addr] <= wdata;       // NBA: uses combinational wire — correct address
    if (rst) addr_reg <= 'd0;
end
```

**Why this works**: `write_addr` is a wire, so its value is evaluated in the active region — before any NBA updates. `ram[write_addr] <= wdata` captures the correct address during NBA scheduling. The `addr_reg <= write_addr` NBA update does not affect `write_addr` because it's a separate combinational signal.

**Why NOT blocking assignment**: Using `=` inside `always @(posedge clk)` for register/memory writes causes:
- Simulation-synthesis mismatch across simulators (VCS, Xcelium, iverilog may behave differently)
- Synthesis tools may infer unexpected latches or non-standard RAM structures
- Violates the fundamental Verilog coding rule: sequential blocks use `<=`, combinational blocks use `=`

**Prevention**: `coding_style.md` Section 11 — use combinational pre-computation rather than blocking assignment in sequential blocks.

---

## Pattern 7: FSM Registered Output — Stale in Same-Cycle Consumer

**Severity**: High — consumer module operates on wrong control state for one cycle.

**What happens**: FSM outputs are registered (`_reg` + `assign`). When the FSM transitions state and asserts a control signal in the same cycle, any consumer module's combinational block sees the PREVIOUS value for that cycle.

**Example**:
```
Cycle 5 (posedge): FSM transitions IDLE→CALC, calc_en_reg <= 1 (NBA)
                   Consumer combinational @*: calc_en = 0 (sees old _reg value!)
Cycle 6 (posedge): NBA applied, calc_en = 1
                   Consumer combinational @*: calc_en = 1 (correct)
```

**Impact**: Consumer misses the first cycle of the enable — processes N-1 iterations instead of N.

**Detection**: Counter reaches N-2 iterations when N were expected (off by one, one cycle late start).

**Fix**: Assert control signal one cycle early in FSM (in the state BEFORE transition), or add combinational passthrough (`assign calc_en = (state_reg == STATE_CALC)`).

**Prevention**:
- `coding_style.md` Section 24.1 (Producer-Consumer Cycle Annotation)
- Cross-module timing table verification

---

## Pattern 8: msg_valid Hold Through Cycle

**Severity**: Medium — testbench pattern, causes missed input in simulation.

**What happens**: Testbench asserts `msg_valid=1`, then at `@(posedge clk)` deasserts it immediately. If the DUT's `always @(posedge clk)` block runs AFTER the testbench process in the active region, the DUT sees `msg_valid=1`. If the DUT runs BEFORE, it sees `msg_valid=0` — the pulse was missed.

**Example**:
```verilog
// Testbench — fragile pattern
msg_valid = 1;
@(posedge clk);      // DUT may or may not see msg_valid=1 here
msg_valid = 0;       // deasserted before DUT's block runs?
```

**Fix**: Hold `msg_valid` through negedge before deasserting.

```verilog
// Fix — hold through entire cycle
msg_valid = 1;
@(posedge clk);      // DUT samples msg_valid=1 (guaranteed)
@(negedge clk);      // hold through the cycle
msg_valid = 0;       // safe to deassert now
```

**Prevention**:
- `stage_3.md` Verilog TB template — all input pulses held through `@(negedge clk)`
- **SystemVerilog Clocking Block**: `clocking cb` with output skew eliminates the need for manual `@(negedge clk)` holding — the clocking block drives outputs at a defined time offset after the clock edge, ensuring hold time. See Pattern 5 Prevention for the clocking block example.

---

## Cross-Reference: Pattern → Fix → Prevention

| Pattern | Fix Location | Prevention |
|---------|-------------|------------|
| 1. NBA Cross-Module Race | Combinational bypass (Approach A) or accept pipeline delay (Approach B) | coding_style.md 24.1 |
| 2. Signal Lifetime Mismatch | Wrapper: `@(posedge clk)` latch register | spec.json `signal_lifetime`, stage 1 Check D |
| 3. Counter Width Overflow | `integer` or `for (int i=0;...)` for loop vars | stage 1 math check, coding_style.md 17a |
| 4. Shift Register Alignment | FSM: separate load/calc cycles + SVA mutual exclusion assertion | stage 1 Check A, coding_style.md 24.6 |
| 5. TB NBA Sampling Race | cocotb `await RisingEdge` or SV Clocking Block | stage_3.md TB template |
| 6. iverilog Memory NBA Race | Combinational `wire` address pre-computation + NBA `<=` | coding_style.md 11 |
| 7. FSM Output Stale | Assert one cycle early or combinational passthrough | coding_style.md 24.1, 24.4 |
| 8. msg_valid Hold | Hold through `@(negedge clk)` | stage_3.md TB template |

# Stage 3: timing

**Goal**: Read spec.json + micro_arch.md, generate timing_model.yaml + testbench.

Mark Stage 3 task as **in_progress** using TaskUpdate.

## 3a. Read inputs

Use **Read** tool:
- `$PROJECT_DIR/workspace/docs/spec.json`
- `$PROJECT_DIR/workspace/docs/micro_arch.md`
- `$PROJECT_DIR/workspace/docs/behavior_spec.md` (for cycle-accurate expected behavior)

Also detect and run any golden model / reference implementation:

```bash
# Auto-detect golden model Python files
GOLDEN_FILES=$(ls "$PROJECT_DIR/context/"*.py 2>/dev/null)
if [ -n "$GOLDEN_FILES" ]; then
    echo "[GOLDEN] Found golden model(s):"
    ls "$PROJECT_DIR/context/"*.py
    echo "[GOLDEN] Running golden model to extract expected outputs..."
    for gf in "$PROJECT_DIR/context/"*.py; do
        echo "--- Running: $(basename $gf) ---"
        python3 "$gf" 2>&1 | tee "$PROJECT_DIR/logs/golden_$(basename $gf .py).log" || true
    done
    echo "[GOLDEN] Golden model outputs saved to logs/golden_*.log"
    echo "[GOLDEN] Use these values as expected outputs in testbenches."
else
    echo "[GOLDEN] No context/*.py found — expected values must come from spec or manual computation"
fi

# Also check for test vectors or reference in context/*.md
ls "$PROJECT_DIR/context/"*.md 2>/dev/null && echo "[GOLDEN] Found context/*.md — read these for additional test vectors" || true
```

Use the golden model outputs from `logs/golden_*.log` (if any) as the **authoritative source** for expected values in test scenarios. Never use self-computed or approximate values.

## 3a2. Run pipeline-generated golden model (if available)

```bash
# Priority 1: Pipeline-generated golden model from Stage 1
if [ -f "$PROJECT_DIR/workspace/docs/golden_model.py" ]; then
    echo "[GOLDEN] Found pipeline-generated golden model: workspace/docs/golden_model.py"
    echo "[GOLDEN] Running golden model to generate expected_vectors.json..."
    cd "$PROJECT_DIR" && python3 -c "
import json, sys
sys.path.insert(0, 'workspace/docs')
from golden_model import run
results = run()
with open('workspace/docs/expected_vectors.json', 'w') as f:
    json.dump(results, f, indent=2)
print(f'[GOLDEN] Generated expected_vectors.json with {len(results)} cycles')
" 2>&1
    if [ $? -eq 0 ]; then
        echo "[GOLDEN] expected_vectors.json generated successfully"
        echo "[GOLDEN] Use values from workspace/docs/expected_vectors.json as highest priority expected values"
    else
        echo "[GOLDEN] WARNING: golden model execution failed — expected values from spec/standards only"
    fi
else
    echo "[GOLDEN] No workspace/docs/golden_model.py found"
    echo "[GOLDEN] Checking context/*.py for user-provided golden models..."
    # Fall through to existing context/*.py detection above
fi
```

**Expected value priority order (highest to lowest)**:
1. `workspace/docs/expected_vectors.json` — auto-generated from `golden_model.py`
2. `logs/golden_*.log` — from user-provided `context/*.py` golden models
3. Standard document test vectors (from `requirement.md` or `context/*.md`)
4. Manual computation documented in `behavior_spec.md`

When `expected_vectors.json` exists: **Read it** using the Read tool, then use its values EXACTLY in testbench assertions. Do not recompute. Add a comment in the testbench: `// Expected values from: workspace/docs/expected_vectors.json`

## 3b. Write timing_model.yaml

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

## 3c. Write testbenches (one per module)

For **each module** in spec.json `modules` array, generate a testbench file: `workspace/tb/tb_<module_name>.v`.

The top module testbench does integration testing. Submodule testbenches test each module in isolation, enabling bottom-up verification in Stage 7.

### 3c-i. Submodule testbenches (non-top modules)

For each module where `module_type != "top"`, use **Write** to create `workspace/tb/tb_<module_name>.v`.

Submodule testbench characteristics:
- Instantiates only the target submodule — no other RTL modules needed
- Drives all input ports directly with test stimulus
- Tests the module's core computation or control logic in isolation
- Expected values should come from the golden model (if available) or manual computation documented in behavior_spec.md
- Must print `ALL TESTS PASSED` or `FAILED: N assertion(s) failed` and `$finish`
- At minimum: reset behavior + 1 functional test case with known expected output
- If the module is purely combinational (no clock), test it with direct input changes and immediate output checks

**CRITICAL — NBA timing discipline for ALL Verilog testbenches**:

Registered DUT outputs (`_reg` → `assign` → output port) update via NBA (`<=`) at `@(posedge clk)`. The NBA region executes AFTER the active region. Checking these outputs at `@(posedge clk)` (in the active region) reads **stale** values — the NBA hasn't applied yet.

**Correct pattern for checking registered outputs**:
1. Drive inputs at or before `@(posedge clk)` — DUT samples them via NBA
2. Wait `@(negedge clk)` — at this point, NBA has applied and outputs are stable
3. Check outputs now — values reflect the DUT's response to the inputs

```verilog
// CORRECT — wait for negedge before checking registered outputs
data_in = 32'hDEAD_BEEF;
@(posedge clk);           // DUT samples data_in
@(negedge clk);           // NBA has settled — data_out is now valid
if (data_out !== expected) $display("[FAIL] ...");  // check at negedge

// WRONG — checks at posedge, before NBA applies
data_in = 32'hDEAD_BEEF;
@(posedge clk);
if (data_out !== expected) $display("[FAIL] ...");  // reads stale value!
```

For multi-cycle operations, sample on `@(negedge clk)` after each `@(posedge clk)` where an output change is expected.

**Example testbench structure for a submodule**:
```verilog
// tb_<module_name>.v — unit test for <module_name>
module tb_<module_name>;
    // Declare wires/regs matching ALL ports of the DUT
    reg clk, rst;
    reg [31:0] data_in;
    wire [31:0] data_out;

    // Cycle counter — used in ALL $display calls for waveform correlation
    integer cycle_count = 0;
    integer fail_count  = 0;

    // Instantiate DUT
    <module_name> uut (
        .clk(clk), .rst(rst),
        .data_in(data_in), .data_out(data_out)
    );

    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;

    // Cycle counter — increment every posedge
    always @(posedge clk) cycle_count = cycle_count + 1;

    // VCD capture — REQUIRED for waveform analysis
    initial begin
        $dumpfile("tb_<module_name>.vcd");
        $dumpvars(0, tb_<module_name>);
    end

    // Helper macro pattern — use inline in always/initial
    // CHECK: $display("[FAIL] cycle=%0d <signal>=0x%0h expected=0x%0h got=0x%0h", cycle_count, <signal>, <expected>, <actual>)
    //        fail_count = fail_count + 1;

    // Test cases (example structure)
    initial begin
        // --- Reset ---
        rst = 1; data_in = 0;
        @(posedge clk); @(posedge clk);
        rst = 0;
        @(negedge clk);  // wait for NBA to settle after rst deassert
        $display("[TRACE] cycle=%0d rst released", cycle_count);

        // --- Test case 1: <description> ---
        // Drive inputs at negedge so they're stable before next posedge
        data_in = 32'hDEAD_BEEF;
        @(posedge clk);   // DUT samples data_in
        @(negedge clk);   // NBA settled — registered outputs now valid
        $display("[TRACE] cycle=%0d data_in=0x%0h data_out=0x%0h", cycle_count, data_in, data_out);
        if (data_out !== 32'hEXPECTED) begin
            $display("[FAIL] cycle=%0d data_out expected=0x%0h got=0x%0h",
                     cycle_count, 32'hEXPECTED, data_out);
            fail_count = fail_count + 1;
        end else
            $display("[PASS] cycle=%0d data_out=0x%0h", cycle_count, data_out);

        // --- Test case 2: multi-cycle operation ---
        // For each cycle where output is expected to change:
        //   @(posedge clk);  // DUT processes
        //   @(negedge clk);  // NBA settled
        //   check outputs

        // --- Summary ---
        if (fail_count == 0) $display("ALL TESTS PASSED");
        else $display("FAILED: %0d assertion(s) failed", fail_count);
        $finish;
    end
endmodule
```

**CRITICAL `$display` format rules (required for VCD waveform correlation)**:
- Every `[FAIL]` line **MUST** include `cycle=%0d` using the `cycle_count` integer
- Every `[FAIL]` line **MUST** include both `expected=0x%0h` and `got=0x%0h` (or `expected=%0d got=%0d`)
- Use `[TRACE]` prefix for informational prints (state transitions, input changes)
- Use `[PASS]` prefix for passing assertions
- The `cycle_count` value correlates directly to the VCD waveform table row

**VCD capture is MANDATORY** — every testbench must have `$dumpfile` / `$dumpvars` in an `initial` block. The VCD file name must be `tb_<module_name>.vcd` so the waveform tool can find it.

### 3c-ii. Top module testbench (integration test)

For the module where `module_type == "top"`, use **Write** to create `workspace/tb/tb_<design_name>.v`.

Get `<design_name>` from spec.json `design_name` field.

This is the integration testbench that verifies the full design end-to-end:
- Instantiates the top module only (submodules are included via RTL files)
- Tests the complete functional flow from input to output
- Must cover all scenarios from the timing_model.yaml

**iverilog Compatibility Rules (CRITICAL for ALL testbenches)**:
- NO `assert property`, `|->`, `|=>`, `##` delay operator (SVA)
- NO `logic` type (use `reg`/`wire`)
- NO `always_ff`/`always_comb` (use `always`)
- YES `$display`, `$monitor`, `$finish`, `$dumpfile`

All testbenches must:
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

Minimum: `max(3, number of functional requirements)` scenarios per testbench. Every data-write scenario must read back with a `fail_count` check.

### Test Vector Requirements

- If standard test vectors are provided in `requirement.md` or `context/` files, the testbench MUST cover **all** provided vectors
- If the standard document (e.g., FIPS, IEEE, GM/T) contains appendix test vectors, cover at least **3** of them
- Required test scenarios (if applicable to the design):
  1. **Reset behavior** — verify all outputs are quiescent during and after reset
  2. **Happy path** — at least one standard test vector with known-good expected output
  3. **Boundary conditions** — empty input, maximum-length input, single/multi-block boundaries, boundary values
  4. **Protocol behavior** — backpressure, back-to-back operations, error recovery, handshake edge cases
- Every test vector MUST have a concrete expected value — never check only "non-zero" or "changed"
- All expected values MUST come from the standard document, user-provided reference, or golden model output — never self-computed by the model

### Golden Model Usage (if available)

If `context/*.py` contains a Python reference implementation:
- Read the golden model and understand its input/output interface
- Run the golden model (via Bash) with the same inputs used in test scenarios to extract expected outputs
- If the golden model can output intermediate computation steps, use those values as additional check points in submodule testbenches (e.g., verify internal register values at specific cycles)
- Document which golden model was used and how expected values were derived in a testbench comment block

### 3c-ii-bis. Interface Contract Tests (multi-module designs ONLY)

For designs with 3+ modules connected via control signals from a control/FSM module, generate
an additional testbench: `workspace/tb/tb_<design_name>_interface.v`.

Skip this step if the design has only 2 modules (top + one submodule) — the top-level testbench already covers the interface.

This testbench verifies that the control signal sequences produced by the FSM module are correctly handled by consumer modules. It is specifically designed to catch the class of bugs where:
- The FSM co-asserts multiple control signals (e.g., load_en + calc_en)
- Consumer modules use if/else-if priority that silently ignores one signal during co-assertion
- Shift register alignment is off by one round due to load/shift timing mismatch (algorithmic designs)

**Interface Contract Test structure**:
1. Instantiate the FSM/control module AND one or more consumer datapath modules
2. Drive the FSM inputs as in the integration testbench, but also probe internal control signals
3. For each control signal pair identified in behavior_spec.md Cross-Module Timing:
   - Verify co-asserted signals are both active on the expected cycle
   - Verify the consumer module produces correct output when co-asserted signals arrive simultaneously
4. Specifically test these edge cases:
   - **First cycle after reset**: Do all enables behave correctly? Are initial values loaded?
   - **Transition cycle**: Where load_en de-asserts and calc_en continues — does the consumer see the correct data?
   - **Back-to-back operations**: Second msg_valid immediately after first completes
   - **Counter alignment**: At each round, does the consumer see the correct round_cnt value?
5. Use `$display` with `cycle=%0d` format and check against expected values from behavior_spec.md cycle tables
6. If a golden model exists in `context/*.py`, use its intermediate values as expected outputs for each round

### 3c-iii. Generate cocotb testbenches (preferred — always generate when cocotb available)

cocotb testbenches are the **preferred** simulation path. `await RisingEdge(dut.clk)` uses VPI callbacks that fire AFTER the NBA region completes, eliminating the Verilog NBA race condition at the mechanism level. No `@(negedge clk)` workarounds needed.

Check if cocotb is available:

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
if [ "$COCOTB_AVAILABLE" = "true" ]; then
    echo "[COCOTB] cocotb available — generating Python testbenches (preferred sim path)"
else
    echo "[COCOTB] cocotb not available — Verilog TBs only (expect NBA timing workarounds)"
fi
```

**Only proceed with 3c-iii-a and 3c-iii-b if `COCOTB_AVAILABLE=true`.**

#### 3c-iii-a. Python testbench per module

For **each module** in spec.json `modules` array, generate a cocotb testbench file: `workspace/tb/test_<module_name>.py`.

The cocotb testbench provides richer verification than Verilog `$display`-based testbenches:
- Python `assert` statements produce tracebacks with file + line number + actual values
- Golden model can be imported directly for on-the-fly expected value computation
- Async coroutines (`await RisingEdge(dut.clk)`) map cleanly to cycle-accurate timing

**Testbench structure** (use **Write** tool for each module):

```python
"""cocotb testbench for <module_name> — golden model cross-check.
Generated by VeriFlow-CC Stage 3.

Uses await RisingEdge(dut.clk) which fires AFTER NBA region completes.
No @(negedge clk) workarounds needed — registered outputs are always
stable when the coroutine resumes.
"""

import os, sys
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer

CLK_PERIOD_NS = 5   # 200 MHz default (half-period = 2.5 ns)
TIMEOUT_CYCLES = 500
FAIL_COUNT = 0

# ─── Golden model import (if available) ─────────────────────────────────
GOLDEN_AVAILABLE = False
GM_PATH = Path(__file__).parent.parent / "docs" / "golden_model.py"
if GM_PATH.exists():
    sys.path.insert(0, str(GM_PATH.parent))
    try:
        from golden_model import run as golden_run
        GOLDEN_AVAILABLE = True
    except ImportError:
        pass

# ─── Helpers ────────────────────────────────────────────────────────────

async def reset_dut(dut):
    """Apply synchronous reset and verify quiescent outputs."""
    dut.rst.value = 1
    # Set all input ports to 0 during reset
    for name in [p for p in dir(dut) if not p.startswith('_') and p not in ('clk','rst')]:
        try:
            sig = getattr(dut, name)
            if hasattr(sig, 'value') and hasattr(sig, 'setimmediatevalue'):
                sig.value = 0
        except Exception:
            pass
    await ClockCycles(dut.clk, 3)
    dut.rst.value = 0
    await RisingEdge(dut.clk)  # rst deassert sampled, outputs stable

def check(dut, expected, signal, test_name, cycle):
    """Raise AssertionError on mismatch. signal is a dut handle (e.g., dut.data_out)."""
    global FAIL_COUNT
    actual = int(signal.value)
    if expected != actual:
        FAIL_COUNT += 1
        msg = (
            f"[FAIL] {test_name} cycle={cycle} {signal._name}: "
            f"expected=0x{expected:08x} got=0x{actual:08x}"
        )
        dut._log.error(msg)
        raise AssertionError(msg)

def check_dut(dut, expected, signal, test_name, cycle):
    """Convenience: check_dut(dut, 0x1234, dut.data_out, 'test1', 5)."""
    check(dut, expected, signal, test_name, cycle)

# ─── Tests ──────────────────────────────────────────────────────────────

@cocotb.test()
async def test_reset(dut):
    """Test 1: Reset behavior — outputs quiescent, ready=1 after reset."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)
    # After reset: await RisingEdge for post-NBA stable values
    # Example: assert dut.ready.value == 1, "ready not asserted after reset"
    dut._log.info("PASS — reset behavior correct")

# ─── Cycle-accurate test pattern ────────────────────────────────────────
# Each test follows this cycle pattern:
#
#   # Drive inputs
#   dut.data_in.value = 0xDEADBEEF
#   await RisingEdge(dut.clk)    # DUT samples inputs, NBA applies
#   # Outputs are NOW stable — check immediately after RisingEdge returns
#   check_dut(dut, 0xEXPECTED, dut.data_out, 'test_name', cycle)
#
# Key insight: RisingEdge returns AFTER the NBA region. No delay needed.
# This is the fundamental advantage of cocotb over Verilog testbenches.
#
# For multi-cycle operations:
#   for cycle in range(N):
#       await RisingEdge(dut.clk)         # posedge + NBA
#       check_dut(dut, expected[cycle], dut.data_out, 'test', cycle)

# Additional per-scenario tests are generated from timing_model.yaml scenarios.
# Each scenario maps to an @cocotb.test() coroutine that:
#  1. Calls reset_dut(dut)
#  2. Drives input stimulus cycle-by-cycle per the scenario's stimulus table
#  3. Awaits RisingEdge(dut.clk) after each input change
#  4. Checks expected values from golden model or spec.json

@cocotb.test()
async def test_summary(dut):
    """Final test: reports overall pass/fail."""
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())
    await RisingEdge(dut.clk)
    global FAIL_COUNT
    if FAIL_COUNT == 0:
        dut._log.info("ALL TESTS PASSED")
    else:
        dut._log.error(f"FAILED: {FAIL_COUNT} assertion(s) failed")
```

**CRITICAL requirements for all cocotb testbenches**:
- Use `Clock(dut.clk, CLK_PERIOD_NS, unit="ns")` (cocotb 2.0+ uses `unit=` not `units=`)
- Use `dut.signal.value.to_unsigned()` to read integer values from DUT signals (not `.integer`)
- Do NOT import `TestSuccess`/`TestFailure` from `cocotb.result` (removed in cocotb 2.0+)
- Include comments referencing which scenario from timing_model.yaml each test covers
- Every test MUST use `await RisingEdge(dut.clk)` (or `ClockCycles`) for cycle alignment
- If golden model is available, import `run()` and use returned `list[dict]` as expected values
- Test module must be importable from the cocotb build directory

**Per-module test coverage** (minimum):
1. `test_reset` — reset behavior, ready signal, output quiescence
2. One test per timing_model.yaml scenario — drive stimulus, check expected outputs
3. `test_summary` — reports aggregate pass/fail

#### 3c-iii-b. Golden model reference

If `workspace/docs/golden_model.py` exists (generated in Stage 1), the cocotb testbench imports it via `from golden_model import run`. The `run()` function contract:
- Returns `list[dict]` where each dict maps output signal names (short names, no scope) to expected integer values
- Each list entry corresponds to one cycle
- This is the same contract used by `vcd2table.py --golden-model`

If `run()` does not exist or returns an incompatible format, fall back to expected values from:
1. `workspace/docs/expected_vectors.json` (Stage 1 generated)
2. Spec.json field values
3. Manual computation documented in behavior_spec.md

## 3d. Hook

```bash
# Verify timing model exists
test -f "$PROJECT_DIR/workspace/docs/timing_model.yaml" || { echo "[HOOK] FAIL — timing_model.yaml not found"; exit 1; }

# Verify at least one testbench exists
TB_COUNT=$(ls "$PROJECT_DIR/workspace/tb/"tb_*.v 2>/dev/null | wc -l)
[ "$TB_COUNT" -ge 1 ] || { echo "[HOOK] FAIL — no testbench files found"; exit 1; }

# Report testbench inventory
echo "[HOOK] Found $TB_COUNT testbench file(s):"
ls "$PROJECT_DIR/workspace/tb/"tb_*.v | xargs -I{} basename {}

echo "[HOOK] PASS"
```

If FAIL → fix and rewrite immediately.

## 3e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "timing"
```

Mark Stage 3 task as **completed** using TaskUpdate.

## 3e-checksum. Save testbench checksum

```bash
md5sum "$PROJECT_DIR/workspace/tb/"tb_*.v "$PROJECT_DIR/workspace/tb/"test_*.py > "$PROJECT_DIR/.veriflow/tb_checksum" 2>/dev/null
echo "[CHECKPOINT] TB checksum saved (Verilog + cocotb testbenches)"
```

This checksum will be verified in Stage 7 to detect unauthorized testbench modifications. Covers both Verilog (`tb_*.v`) and cocotb (`test_*.py`) testbenches when present.

## 3f. Journal

```bash
printf "\n## Stage: timing\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/timing_model.yaml, workspace/tb/tb_*.v$(test -f "$PROJECT_DIR/workspace/docs/expected_vectors.json" && echo ', workspace/docs/expected_vectors.json')\n**Notes**: Timing model and testbench generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

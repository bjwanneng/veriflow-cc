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
        $display("[TRACE] cycle=%0d rst released", cycle_count);

        // --- Test case 1: <description> ---
        data_in = 32'hDEAD_BEEF;
        @(posedge clk);
        $display("[TRACE] cycle=%0d data_in=0x%0h", cycle_count, data_in);
        @(posedge clk);
        if (data_out !== 32'hEXPECTED) begin
            $display("[FAIL] cycle=%0d data_out expected=0x%0h got=0x%0h",
                     cycle_count, 32'hEXPECTED, data_out);
            fail_count = fail_count + 1;
        end else
            $display("[PASS] cycle=%0d data_out=0x%0h", cycle_count, data_out);

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
md5sum "$PROJECT_DIR/workspace/tb/"tb_*.v > "$PROJECT_DIR/.veriflow/tb_checksum"
echo "[CHECKPOINT] TB checksum saved"
```

This checksum will be verified in Stage 7 to detect unauthorized testbench modifications.

## 3f. Journal

```bash
printf "\n## Stage: timing\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/timing_model.yaml, workspace/tb/tb_*.v\n**Notes**: Timing model and testbench generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

# Stage 7: sim (inline cocotb-first integration test)

**Goal**: Compile and simulate the top-level integration test. cocotb-first (no NBA race conditions). Integration-only (no per-module unit tests). Inline execution (no sub-agent — main session runs and diagnoses directly).

Mark Stage 7 task as **in_progress** using TaskUpdate.

## 7a. Confirm inputs

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
echo "=== Stage 7: Simulation (inline cocotb-first) ==="
echo "[SIM] RTL files:"
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
echo "[SIM] Testbench files:"
ls -la "$PROJECT_DIR/workspace/tb/"tb_*.v "$PROJECT_DIR/workspace/tb/"test_*.py 2>/dev/null || true
echo "[SIM] COCOTB_AVAILABLE=$COCOTB_AVAILABLE"
```

## 7b. cocotb simulation (primary path)

If `COCOTB_AVAILABLE=true`, run cocotb **first**. cocotb uses `await RisingEdge(dut.clk)` which fires via VPI callback AFTER NBA region completes — this eliminates all Verilog NBA race conditions at the source. No `#1` delays or `@(negedge clk)` workarounds needed.

### 7b-1. Check for Python testbenches

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

if [ "$COCOTB_AVAILABLE" = "true" ] && ls workspace/tb/test_*.py 2>/dev/null | head -1 >/dev/null 2>&1; then
    echo "[COCOTB] Python testbenches found — running cocotb simulation"
else
    echo "[COCOTB] cocotb not available or no Python testbenches — skip to 7c (Verilog fallback)"
fi
```

If no `test_*.py` files or cocotb unavailable, skip to **7c**.

### 7b-2. Run cocotb integration test

Only run the **top-level integration test** — no per-module unit tests. The top-level cocotb testbench exercises the full design end-to-end, which is sufficient for catching all bug classes (FSM timing, cross-module signal alignment, algorithmic correctness).

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh
mkdir -p workspace/sim/cocotb_build logs

DESIGN_NAME=$($PYTHON_EXE -c "import json; print(json.load(open('workspace/docs/spec.json'))['design_name'])" 2>/dev/null || echo "")

if [ -f "workspace/tb/test_${DESIGN_NAME}.py" ]; then
    echo "============================================"
    echo "[COCOTB] Integration test: $DESIGN_NAME"
    echo "============================================"

    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/cocotb_runner.py" \
        --rtl-dir "$PROJECT_DIR/workspace/rtl" \
        --tb-dir "$PROJECT_DIR/workspace/tb" \
        --module "$DESIGN_NAME" \
        --build-dir "$PROJECT_DIR/workspace/sim/cocotb_build/$DESIGN_NAME" \
        --results-file "$PROJECT_DIR/logs/cocotb_${DESIGN_NAME}_results.xml" \
        2>&1 | tee "$PROJECT_DIR/logs/sim.log"

    COCOTB_EXIT=${PIPESTATUS[0]}
else
    echo "[COCOTB] No top-level cocotb testbench (test_${DESIGN_NAME}.py) — skip to 7c"
    COCOTB_EXIT=1
fi
```

### 7b-3. Analyze cocotb results

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

XML_FILE="$PROJECT_DIR/logs/cocotb_${DESIGN_NAME}_results.xml"

if [ -f "$XML_FILE" ] && [ "$COCOTB_EXIT" -eq 0 ]; then
    # Parse xUnit XML for detailed pass/fail
    $PYTHON_EXE -c "
import xml.etree.ElementTree as ET

tree = ET.parse('$XML_FILE')
failed = 0
passed = 0
for suite in tree.iter('testsuite'):
    for tc in suite.iter('testcase'):
        fail_elem = tc.find('failure')
        if fail_elem is not None:
            failed += 1
            msg = fail_elem.get('message', '')
            text = (fail_elem.text or '')[:500]
            print(f'  [FAIL] {tc.get(\"name\")} — {msg}')
            print(f'    Traceback: {text}')
        else:
            passed += 1
            print(f'  [PASS] {tc.get(\"name\")}')

print(f'')
print(f'[COCOTB] Results: {passed} passed, {failed} failed, {passed + failed} total')

if failed > 0:
    print(f'[COCOTB] FAIL — {failed} test(s) failed')
    import sys; sys.exit(1)
else:
    print(f'[COCOTB] PASS — all tests passed')
"

    COCOTB_RESULT=$?
else
    COCOTB_RESULT=1
fi
```

**If COCOTB_RESULT = 0**: cocotb passed. Skip Verilog fallback entirely, write a minimal sim.log for hook compatibility, and proceed to **7e (Hook)**.

```bash
if [ "$COCOTB_RESULT" -eq 0 ]; then
    echo "cocotb integration test: ALL TESTS PASSED" > "$PROJECT_DIR/logs/sim.log"
    echo "Method: cocotb (Python-based co-simulation)" >> "$PROJECT_DIR/logs/sim.log"
    echo "[COCOTB] All tests passed. Skipping Verilog fallback."
    # Jump directly to 7e (Hook), skip 7c and 7d
fi
```

**If COCOTB_RESULT != 0**: cocotb failure provides Python tracebacks with expected vs actual values. Read the traceback output above to understand what failed, then use **Read** tool to read the RTL file of the failing module. Go directly to Error Recovery Step 1.5 in SKILL.md (no waveform table needed — the Python traceback IS the diagnostic).

cocotb failures are **authoritative** — do NOT fall back to Verilog simulation expecting different results. The bug is real. Fix the RTL and re-run 7b.

## 7c. Verilog fallback (only if cocotb unavailable)

Only run this path if `COCOTB_AVAILABLE=false` or no `test_*.py` files exist.

### 7c-1. Compile top-level integration test

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

echo "============================================"
echo "[SIM] Verilog fallback: Integration test"
echo "============================================"

mkdir -p workspace/sim logs

# Compile all RTL + all Verilog testbenches together
iverilog -o workspace/sim/tb.vvp workspace/rtl/*.v workspace/tb/tb_*.v 2>&1 | tee logs/compile.log
COMPILE_EXIT=${PIPESTATUS[0]}
echo "[SIM] Compile exit code: $COMPILE_EXIT"

if [ "$COMPILE_EXIT" -ne 0 ]; then
    echo "[SIM] COMPILE FAILED — see logs/compile.log"
    echo "[SIM] Read logs/compile.log with Read tool, fix RTL, re-run 7c"
    # Go to Error Recovery in SKILL.md
fi
```

### 7c-2. Run simulation

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

if [ -f "workspace/sim/tb.vvp" ]; then
    vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim.log
    SIM_EXIT=${PIPESTATUS[0]}
    echo "[SIM] Simulation exit code: $SIM_EXIT"

    # Move VCD files to workspace/sim/
    for vcd_f in "$PROJECT_DIR"/*.vcd; do
        [ -f "$vcd_f" ] && mv "$vcd_f" "$PROJECT_DIR/workspace/sim/" 2>/dev/null || true
    done
fi
```

### 7c-3. Analyze Verilog simulation log

Read `logs/sim.log` using **Read** tool. Pass/Fail criteria (strict — ALL three must be satisfied):

1. **File non-empty**: sim.log exists and contains output
2. **No test failures**: No lines matching `[FAIL]` or `FAILED:` prefix
3. **Explicit PASS summary**: Must contain `ALL TESTS PASSED` or similar

If all three pass → proceed to **7e (Hook)**.

If any criterion fails → go to **7d (Waveform Analysis)**, then Error Recovery.

## 7d. Waveform Analysis (Verilog failure only)

Only run if Verilog simulation failed. cocotb failures skip this step (Python traceback is sufficient).

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

VCD_FILE=$(ls workspace/sim/*.vcd logs/*.vcd *.vcd 2>/dev/null | head -1)

if [ -z "$VCD_FILE" ]; then
    echo "[WAVE] No VCD found — re-running simulation to generate VCD..."
    vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim_rerun.log
    VCD_FILE=$(ls workspace/sim/*.vcd logs/*.vcd *.vcd 2>/dev/null | head -1)
fi

if [ -n "$VCD_FILE" ]; then
    echo "[WAVE] Generating waveform table from: $VCD_FILE"
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/vcd2table.py" \
        "$VCD_FILE" \
        --sim-log    "$PROJECT_DIR/logs/sim.log" \
        --timing-yaml "$PROJECT_DIR/workspace/docs/timing_model.yaml" \
        --window     30 \
        --output     "$PROJECT_DIR/logs/wave_table.txt"
    echo "[WAVE] Waveform table written to logs/wave_table.txt"
else
    echo "[WAVE] WARNING: No VCD file found."
fi
```

### Golden Model Comparison (if available)

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

GOLDEN_SCRIPT=""
if [ -f "workspace/docs/golden_model.py" ]; then
    GOLDEN_SCRIPT="workspace/docs/golden_model.py"
else
    for gf in context/*.py; do
        if [ -f "$gf" ]; then
            GOLDEN_SCRIPT="$gf"
            break
        fi
    done
fi

VCD_FILE=$(ls workspace/sim/*.vcd logs/*.vcd *.vcd 2>/dev/null | head -1)
if [ -n "$GOLDEN_SCRIPT" ] && [ -n "$VCD_FILE" ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/vcd2table.py" \
        "$VCD_FILE" \
        --sim-log    "$PROJECT_DIR/logs/sim.log" \
        --timing-yaml "$PROJECT_DIR/workspace/docs/timing_model.yaml" \
        --golden-model "$GOLDEN_SCRIPT" \
        --window     30 \
        --output     "$PROJECT_DIR/logs/wave_golden.txt"
    echo "[GOLDEN] Golden model comparison written to logs/wave_golden.txt"
fi
```

**After generating tables**: Use **Read** tool to read `logs/wave_table.txt`. Then proceed to Error Recovery Step 1.5 in SKILL.md.

## 7e. Hook

```bash
# --- Sim Hook: dual-path (cocotb XML or Verilog sim.log) ---

# Determine which simulation path was used
COCOTB_XML=$(ls "$PROJECT_DIR/logs/"cocotb_*_results.xml 2>/dev/null | head -1)

if [ -n "$COCOTB_XML" ]; then
    # --- cocotb path: parse xUnit XML ---
    echo "[HOOK] cocotb results detected — checking xUnit XML"

    $PYTHON_EXE -c "
import xml.etree.ElementTree as ET
import sys, glob

total = 0
failed = 0
for xml_f in sorted(glob.glob('$PROJECT_DIR/logs/cocotb_*_results.xml')):
    tree = ET.parse(xml_f)
    for suite in tree.iter('testsuite'):
        for tc in suite.iter('testcase'):
            total += 1
            fail_elem = tc.find('failure')
            if fail_elem is not None:
                failed += 1
                msg = fail_elem.get('message', '')
                text = (fail_elem.text or '')[:200]
                print(f'  [FAIL] {tc.get(\"name\")} — {msg} {text}')

print(f'[HOOK] cocotb: {total} tests, {total - failed} passed, {failed} failed')
if failed > 0:
    print('[HOOK] FAIL — cocotb tests failed (see tracebacks above)')
    sys.exit(1)
elif total == 0:
    print('[HOOK] FAIL — no test results found in cocotb XML')
    sys.exit(1)
else:
    print('[HOOK] PASS')
" || { echo "[HOOK] FAIL — cocotb simulation did not pass"; exit 1; }

elif [ -s "$PROJECT_DIR/logs/sim.log" ]; then
    # --- Verilog path ---
    LOG="$PROJECT_DIR/logs/sim.log"

    test -f "$PROJECT_DIR/workspace/sim/tb.vvp" || { echo "[HOOK] FAIL — tb.vvp not found"; exit 1; }

    FAIL_COUNT=$(grep -cE '^\s*\[FAIL\]|^FAILED:' "$LOG" 2>/dev/null || echo 0)
    [ "$FAIL_COUNT" -eq 0 ] || { echo "[HOOK] FAIL — $FAIL_COUNT test assertion(s) failed in sim.log"; exit 1; }

    grep -qiE 'ALL TESTS PASSED|All tests passed|all tests passed' "$LOG" && echo "[HOOK] PASS" || { echo "[HOOK] FAIL — no PASS summary found in sim.log"; exit 1; }

else
    echo "[HOOK] FAIL — no simulation output found (no cocotb XML, no sim.log)"
    exit 1
fi
```

If FAIL → go to Error Recovery in SKILL.md. Do NOT mark sim as completed.

## 7f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "sim"
```

Mark Stage 7 task as **completed** using TaskUpdate.

## 7g. Journal

```bash
printf "\n## Stage: sim\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/sim/tb.vvp, logs/sim.log\n**Notes**: Simulation via cocotb (Python co-simulation, no NBA race conditions) or Verilog fallback. Integration-only test — no per-module unit tests.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

---

## Design Rationale

### Why inline (not sub-agent)

Simulation debug requires accurate information transfer between the error artifact and the fix author. Sub-agents lose context: the sub-agent sees simulation output but doesn't know the design intent from behavior_spec.md; the main session sees a text summary but not the raw traceback. Inline execution eliminates this round-trip information loss — the same entity that reads the spec also reads the traceback and applies the fix.

### Why cocotb-first

Verilog `$display`-based testbenches have a fundamental NBA race condition: testbench processes and DUT `always` blocks both execute at `@(posedge clk)` in the active region, in non-deterministic order. Workarounds (`#1` delay, `@(negedge clk)` sampling) add complexity and are fragile across simulators.

cocotb's `await RisingEdge(dut.clk)` uses the VPI callback mechanism which fires AFTER the NBA region completes. At the moment the coroutine resumes, all registered outputs have settled to their final values. This eliminates the race condition at the mechanism level — no workarounds needed.

### Why integration-only (no per-module unit tests)

For designs with 3-4 modules and strong cross-module coupling (shared control signals, aligned counters, synchronized shift registers):
- Per-module unit tests require the test author to replicate the exact timing contract of the FSM module. This is the same problem as writing the RTL itself — the unit test can have the same bug as the RTL (wrong expected value), producing false negatives.
- The most common bugs are cross-module: signal lifetime mismatch, shift register alignment off-by-one, FSM sampling signal too early/late. These are invisible in isolation.
- Integration test with a golden model provides ground-truth expected values — no manual computation needed.

Per-module unit tests remain useful for designs with >10 modules, independently-testable datapath blocks (FIFOs, arbiters, encoders), or modules with no shared control dependencies. For the typical 3-5 module iterative design, integration-only is more efficient.

# Stage 7: sim (bottom-up verification)

**Goal**: Compile and simulate RTL + testbenches, bottom-up per-module then integration.

Mark Stage 7 task as **in_progress** using TaskUpdate.

## 7a. Confirm inputs

```bash
echo "=== Stage 7: Simulation ==="
echo "[SIM] RTL files:"
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
echo "[SIM] Testbench files:"
ls -la "$PROJECT_DIR/workspace/tb/"tb_*.v
echo ""
```

## 7b. Phase 1 — Per-module unit simulation

For **each** testbench file in `workspace/tb/`, compile and simulate independently. This catches bugs at the module level before integration.

**IMPORTANT**: Report each module's result explicitly. The user must see which module passed or failed.

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && mkdir -p workspace/sim logs

# Identify submodule testbenches (all tb_*.v except the top-level one)
DESIGN_NAME=$(python3 -c "import json; print(json.load(open('workspace/docs/spec.json'))['design_name'])" 2>/dev/null || echo "")
TOP_TB="tb_${DESIGN_NAME}.v"

echo "============================================"
echo "[SIM] Phase 1: Bottom-up per-module verification"
echo "============================================"

UNIT_FAIL=0
UNIT_PASS=0
UNIT_TOTAL=0

for tb in workspace/tb/tb_*.v; do
    TB_NAME=$(basename "$tb" .v)
    MODULE_NAME=${TB_NAME#tb_}

    # Skip top-level TB (handled in Phase 2)
    if [ "$(basename $tb)" = "$TOP_TB" ]; then
        echo "[SIM] Skipping top-level TB '$TB_NAME' (Phase 2)"
        continue
    fi

    UNIT_TOTAL=$((UNIT_TOTAL + 1))
    echo ""
    echo "--------------------------------------------"
    echo "[SIM] Module $UNIT_TOTAL: $MODULE_NAME"
    echo "  Testbench: $tb"

    # Find which RTL file contains this module
    RTL_FILE=""
    for v in workspace/rtl/*.v; do
        if grep -q "module ${MODULE_NAME}" "$v" 2>/dev/null; then
            RTL_FILE="$v"
            break
        fi
    done

    if [ -z "$RTL_FILE" ]; then
        # Module might be inside another RTL file — compile all RTL + this TB
        echo "  [SIM] Compiling: all RTL + $TB_NAME"
        iverilog -o "workspace/sim/${TB_NAME}.vvp" workspace/rtl/*.v "$tb" 2>"logs/compile_${MODULE_NAME}.log"
    else
        echo "  [SIM] Compiling: $(basename $RTL_FILE) + $TB_NAME"
        iverilog -o "workspace/sim/${TB_NAME}.vvp" "$RTL_FILE" "$tb" 2>"logs/compile_${MODULE_NAME}.log"
    fi

    if [ $? -ne 0 ]; then
        echo "  [SIM] COMPILE FAILED for $MODULE_NAME — see logs/compile_${MODULE_NAME}.log"
        UNIT_FAIL=$((UNIT_FAIL + 1))
        continue
    fi

    # Run simulation
    echo "  [SIM] Running simulation..."
    vvp "workspace/sim/${TB_NAME}.vvp" > "logs/sim_${MODULE_NAME}.log" 2>&1

    # Check result
    if grep -qE 'ALL TESTS PASSED|All tests passed' "logs/sim_${MODULE_NAME}.log" 2>/dev/null; then
        FAIL_N=$(grep -cE '^\s*\[FAIL\]|^FAILED:' "logs/sim_${MODULE_NAME}.log" 2>/dev/null || echo 0)
        if [ "$FAIL_N" -eq 0 ]; then
            echo "  [SIM] $MODULE_NAME: PASS"
            UNIT_PASS=$((UNIT_PASS + 1))
        else
            echo "  [SIM] $MODULE_NAME: FAIL ($FAIL_N assertion(s) failed)"
            UNIT_FAIL=$((UNIT_FAIL + 1))
        fi
    else
        echo "  [SIM] $MODULE_NAME: FAIL (no PASS summary found)"
        UNIT_FAIL=$((UNIT_FAIL + 1))
    fi
done

echo ""
echo "============================================"
echo "[SIM] Phase 1 Summary: $UNIT_PASS/$UNIT_TOTAL modules passed"
if [ "$UNIT_FAIL" -gt 0 ]; then
    echo "[SIM] Phase 1: $UNIT_FAIL module(s) FAILED — fix before Phase 2"
fi
echo "============================================"
```

**If Phase 1 has failures**: Read the failing module's sim log, go to Error Recovery in SKILL.md, fix the RTL, then re-run only the failing module using the snippet below. Do NOT proceed to Phase 2 until all unit tests pass.

**Per-module re-run** (substitute `<MODULE_NAME>` with the actual module name):
```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh
MODULE_NAME="<MODULE_NAME>"
TB_FILE="workspace/tb/tb_${MODULE_NAME}.v"

# Try compiling with only this module's RTL first; fall back to all RTL if not found
RTL_FILE=""
for v in workspace/rtl/*.v; do
    grep -q "module ${MODULE_NAME}" "$v" 2>/dev/null && RTL_FILE="$v" && break
done

if [ -n "$RTL_FILE" ]; then
    iverilog -o "workspace/sim/tb_${MODULE_NAME}.vvp" "$RTL_FILE" "$TB_FILE" 2>"logs/compile_${MODULE_NAME}.log"
else
    iverilog -o "workspace/sim/tb_${MODULE_NAME}.vvp" workspace/rtl/*.v "$TB_FILE" 2>"logs/compile_${MODULE_NAME}.log"
fi

if [ $? -eq 0 ]; then
    vvp "workspace/sim/tb_${MODULE_NAME}.vvp" > "logs/sim_${MODULE_NAME}.log" 2>&1
    cat "logs/sim_${MODULE_NAME}.log"
else
    echo "[RE-RUN] Compile failed — see logs/compile_${MODULE_NAME}.log"
    cat "logs/compile_${MODULE_NAME}.log"
fi
```

## 7c. Phase 2 — Integration simulation

Once all unit tests pass, compile and simulate the top-level testbench.

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

echo ""
echo "============================================"
echo "[SIM] Phase 2: Integration test (top-level)"
echo "============================================"

# Compile all RTL + all testbenches
iverilog -o workspace/sim/tb.vvp workspace/rtl/*.v workspace/tb/tb_*.v 2>&1 | tee logs/compile.log
echo "[SIM] Compile exit code: ${PIPESTATUS[0]}"

# Run simulation
vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim.log
echo "[SIM] Simulation exit code: ${PIPESTATUS[0]}"

# Move VCD files from project root into workspace/sim/ (keep for waveform analysis)
for vcd_f in "$PROJECT_DIR"/*.vcd; do
    [ -f "$vcd_f" ] && mv "$vcd_f" "$PROJECT_DIR/workspace/sim/" 2>/dev/null || true
done

echo ""
echo "============================================"
echo "[SIM] Phase 2 complete. See logs/sim.log for details."
echo "============================================"
```

## 7d. Analyze output

Read `logs/sim.log`. Pass/Fail criteria (strict — must satisfy ALL three):

1. **File non-empty**: sim.log must exist and contain output
2. **No test failures**: No lines matching `[FAIL]` or `FAILED:` prefix (more precise than matching any "fail" substring, which could appear in signal names or comments)
3. **Explicit PASS summary**: Must contain a clear summary line like `ALL TESTS PASSED`, `All tests passed`, or similar final verdict

If any criterion fails → go to **7d-wave** before Error Recovery.

Also review Phase 1 logs if not already checked:
- `logs/sim_<module_name>.log` for each submodule
- All must show PASS

## 7d-wave. Waveform analysis (run on ANY simulation failure)

When simulation fails, generate a cycle-accurate waveform table before attempting any fix.
This converts the VCD file into a text table the LLM can reason about directly.

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

# Find the VCD file (testbench writes it via $dumpfile)
VCD_FILE=$(ls workspace/sim/*.vcd logs/*.vcd *.vcd 2>/dev/null | head -1)

# Re-run simulation with VCD output preserved (don't delete yet)
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
    echo "[WAVE] WARNING: No VCD file found. Ensure testbench uses \$dumpfile/\$dumpvars."
fi
```

Then for each **Phase 1 module failure**, also generate a per-module table:

```bash
# Replace <MODULE_NAME> with the failing module
MODULE_NAME="<MODULE_NAME>"
VCD_MOD=$(ls workspace/sim/tb_${MODULE_NAME}.vcd \
              logs/tb_${MODULE_NAME}.vcd \
              *.vcd 2>/dev/null | head -1)
if [ -n "$VCD_MOD" ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/vcd2table.py" \
        "$VCD_MOD" \
        --sim-log    "$PROJECT_DIR/logs/sim_${MODULE_NAME}.log" \
        --timing-yaml "$PROJECT_DIR/workspace/docs/timing_model.yaml" \
        --module     "$MODULE_NAME" \
        --window     30 \
        --output     "$PROJECT_DIR/logs/wave_${MODULE_NAME}.txt"
    echo "[WAVE] Module table: logs/wave_${MODULE_NAME}.txt"
fi
```

**After generating tables**: Use **Read** tool to read `logs/wave_table.txt` (or `logs/wave_<module>.txt`).
**Do NOT skip this step** — the waveform table is the primary evidence for timing root cause analysis.
Then proceed to Error Recovery Step 1.5 in SKILL.md, using the table as input to the 5-point analysis.

## 7e. Hook

```bash
# --- Sim Hook: strict 3-layer verification ---
LOG="$PROJECT_DIR/logs/sim.log"

# Layer 0: compiled binary must exist
test -f "$PROJECT_DIR/workspace/sim/tb.vvp" || { echo "[HOOK] FAIL — tb.vvp not found"; exit 1; }

# TB integrity check — detect unauthorized modifications
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    md5sum -c "$PROJECT_DIR/.veriflow/tb_checksum" >/dev/null 2>&1 || { echo "[HOOK] FAIL — testbench was modified after Stage 3!"; exit 1; }
fi

# Layer 1: sim.log must exist and be non-empty
[ -s "$LOG" ] || { echo "[HOOK] FAIL — sim.log missing or empty (simulation may not have run)"; exit 1; }

# Layer 2: count explicit test failures ([FAIL] or FAILED: prefix)
FAIL_COUNT=$(grep -cE '^\s*\[FAIL\]|^FAILED:' "$LOG" 2>/dev/null || echo 0)
[ "$FAIL_COUNT" -eq 0 ] || { echo "[HOOK] FAIL — $FAIL_COUNT test assertion(s) failed in sim.log"; exit 1; }

# Layer 3: must find explicit PASS summary
grep -qiE 'ALL TESTS PASSED|All tests passed|all tests passed' "$LOG" && echo "[HOOK] PASS" || { echo "[HOOK] FAIL — no PASS summary found in sim.log"; exit 1; }
```

If FAIL → go to Error Recovery. Do NOT mark sim as completed.

## 7f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "sim"
```

Mark Stage 7 task as **completed** using TaskUpdate.

## 7g. Journal

```bash
printf "\n## Stage: sim\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/sim/*.vvp, logs/sim*.log\n**Notes**: Bottom-up simulation passed (Phase 1: unit tests + Phase 2: integration).\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

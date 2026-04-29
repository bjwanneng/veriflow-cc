# Stage 7: sim (sub-agent)

**Goal**: Compile and simulate RTL + testbenches, bottom-up per-module then integration.

Mark Stage 7 task as **in_progress** using TaskUpdate.

## 7a-0. Verify testbench integrity

```bash
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    cd "$PROJECT_DIR" && md5sum -c .veriflow/tb_checksum >/dev/null 2>&1 \
        && echo "[INTEGRITY] Testbench checksum OK" \
        || { echo "[INTEGRITY] FAIL — testbench was modified after Stage 3!"; exit 1; }
else
    echo "[INTEGRITY] No checksum file found — skipping TB integrity check"
fi
```

## 7a. Confirm inputs

```bash
echo "=== Stage 7: Simulation ==="
echo "[SIM] RTL files:"
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
echo "[SIM] Testbench files:"
ls -la "$PROJECT_DIR/workspace/tb/"tb_*.v
echo ""
```

## 7b. Call vf-simulator agent

Call the **Agent** tool with `subagent_type: "vf-simulator"` and the following prompt (replace placeholders with absolute paths):

```
PROJECT_DIR={PROJECT_DIR} SPEC={PROJECT_DIR}/workspace/docs/spec.json EDA_ENV={PROJECT_DIR}/.veriflow/eda_env.sh PYTHON_EXE={PYTHON_EXE} SKILL_DIR={CLAUDE_SKILL_DIR} TIMING_YAML={PROJECT_DIR}/workspace/docs/timing_model.yaml. Source EDA_ENV, Read SPEC, run Phase 1 (per-module unit sim), Phase 2 (integration sim), analyze logs for PASS/FAIL, generate waveform tables on failure, run golden model comparison if available. Output a final SIM_RESULT: PASS or SIM_RESULT: FAIL summary with details of which phase failed, failing modules, and artifact paths.
```

Replace:
- `{PROJECT_DIR}` with the absolute project directory path
- `{PYTHON_EXE}` with the Python executable path
- `{CLAUDE_SKILL_DIR}` with the installed skill directory path

## 7b-diagnose. If agent reports failure

The agent's text output contains a `SIM_RESULT:` line. Check it:

- **`SIM_RESULT: PASS`** → proceed to **7c. Hook**
- **`SIM_RESULT: FAIL`** → the agent has generated diagnostic artifacts on disk. Proceed to Error Recovery in SKILL.md:
  1. The agent's output tells you which phase failed and where to find logs
  2. Use **Read** tool to read `logs/sim.log` (Phase 2 failure) or `logs/sim_<module>.log` (Phase 1 failure)
  3. Use **Read** tool to read `logs/wave_table.txt` (Phase 2) or `logs/wave_<module>.txt` (Phase 1)
  4. If `logs/wave_golden.txt` exists, read it too
  5. Follow SKILL.md Error Recovery Step 1.5 (structured root cause analysis) → Step 3 (fix RTL) → re-dispatch vf-simulator by going back to **7b**

**Error recovery flow for subagent stages**:
```
7b (dispatch vf-simulator) → 7b-diagnose (read agent report)
  → if FAIL: Error Recovery (SKILL.md)
    → read artifacts from disk
    → fix RTL in main session
    → go back to 7b (re-dispatch vf-simulator)
    → repeat (3-retry budget from SKILL.md)
  → if PASS: proceed to 7c (hook)
```

**Who does what**:
| Responsibility | Who | Details |
|---------------|-----|---------|
| Run simulation & generate artifacts | vf-simulator subagent | Own context, fresh each dispatch |
| Report pass/fail summary | vf-simulator subagent | Via text output (`SIM_RESULT:`) |
| Read waveform & diagnose root cause | Main session (Error Recovery) | Reads artifacts from disk |
| Fix RTL code | Main session | Has full design context |
| Re-test after fix | Re-dispatch vf-simulator | Back to 7b |

## 7b-retry. If agent returns 0 tool uses

If the agent made **0 tool calls** (empty response), retry once with the exact same prompt.

## 7b-fallback. Inline fallback

If the retry also returns 0 tool uses, perform simulation inline:

### Phase 1 — Per-module unit simulation

For **each** testbench file in `workspace/tb/`, compile and simulate independently:

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && mkdir -p workspace/sim logs

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

    if [ "$(basename $tb)" = "$TOP_TB" ]; then
        echo "[SIM] Skipping top-level TB '$TB_NAME' (Phase 2)"
        continue
    fi

    UNIT_TOTAL=$((UNIT_TOTAL + 1))
    echo ""
    echo "--------------------------------------------"
    echo "[SIM] Module $UNIT_TOTAL: $MODULE_NAME"
    echo "  Testbench: $tb"

    RTL_FILE=""
    for v in workspace/rtl/*.v; do
        if grep -q "module ${MODULE_NAME}" "$v" 2>/dev/null; then
            RTL_FILE="$v"
            break
        fi
    done

    if [ -z "$RTL_FILE" ]; then
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

    echo "  [SIM] Running simulation..."
    vvp "workspace/sim/${TB_NAME}.vvp" > "logs/sim_${MODULE_NAME}.log" 2>&1

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

**If Phase 1 has failures**: Read the failing module's sim log, go to Error Recovery in SKILL.md, fix the RTL, then re-run only the failing module. Do NOT proceed to Phase 2 until all unit tests pass.

### Phase 2 — Integration simulation

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh

echo ""
echo "============================================"
echo "[SIM] Phase 2: Integration test (top-level)"
echo "============================================"

iverilog -o workspace/sim/tb.vvp workspace/rtl/*.v workspace/tb/tb_*.v 2>&1 | tee logs/compile.log
echo "[SIM] Compile exit code: ${PIPESTATUS[0]}"

vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim.log
echo "[SIM] Simulation exit code: ${PIPESTATUS[0]}"

for vcd_f in "$PROJECT_DIR"/*.vcd; do
    [ -f "$vcd_f" ] && mv "$vcd_f" "$PROJECT_DIR/workspace/sim/" 2>/dev/null || true
done

echo ""
echo "============================================"
echo "[SIM] Phase 2 complete. See logs/sim.log for details."
echo "============================================"
```

### Analyze output

Read `logs/sim.log`. Pass/Fail criteria (strict — must satisfy ALL three):

1. **File non-empty**: sim.log must exist and contain output
2. **No test failures**: No lines matching `[FAIL]` or `FAILED:` prefix
3. **Explicit PASS summary**: Must contain `ALL TESTS PASSED`, `All tests passed`, or similar

If any criterion fails → go to **Waveform Analysis** before Error Recovery.

### Waveform Analysis (run on ANY simulation failure)

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

Then for each Phase 1 module failure:

```bash
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

**After generating tables**: Use **Read** tool to read `logs/wave_table.txt`. Then proceed to Error Recovery Step 1.5 in SKILL.md.

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

## 7c. Hook

```bash
# --- Sim Hook: strict 3-layer verification ---
LOG="$PROJECT_DIR/logs/sim.log"

# Layer 0: compiled binary must exist
test -f "$PROJECT_DIR/workspace/sim/tb.vvp" || { echo "[HOOK] FAIL — tb.vvp not found"; exit 1; }

# TB integrity check
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    md5sum -c "$PROJECT_DIR/.veriflow/tb_checksum" >/dev/null 2>&1 || { echo "[HOOK] FAIL — testbench was modified after Stage 3!"; exit 1; }
fi

# Layer 1: sim.log must exist and be non-empty
[ -s "$LOG" ] || { echo "[HOOK] FAIL — sim.log missing or empty"; exit 1; }

# Layer 2: count explicit test failures
FAIL_COUNT=$(grep -cE '^\s*\[FAIL\]|^FAILED:' "$LOG" 2>/dev/null || echo 0)
[ "$FAIL_COUNT" -eq 0 ] || { echo "[HOOK] FAIL — $FAIL_COUNT test assertion(s) failed in sim.log"; exit 1; }

# Layer 3: must find explicit PASS summary
grep -qiE 'ALL TESTS PASSED|All tests passed|all tests passed' "$LOG" && echo "[HOOK] PASS" || { echo "[HOOK] FAIL — no PASS summary found in sim.log"; exit 1; }
```

If FAIL → go to Error Recovery. Do NOT mark sim as completed.

## 7d. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "sim"
```

Mark Stage 7 task as **completed** using TaskUpdate.

## 7e. Journal

```bash
printf "\n## Stage: sim\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/sim/*.vvp, logs/sim*.log\n**Notes**: Bottom-up simulation passed (Phase 1: unit tests + Phase 2: integration).\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

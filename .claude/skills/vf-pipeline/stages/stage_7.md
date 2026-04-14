# Stage 7: sim

**Goal**: Compile and simulate RTL + testbench.

Mark Stage 7 task as **in_progress** using TaskUpdate.

## 7a. Confirm inputs

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v "$PROJECT_DIR/workspace/tb/"tb_*.v
```

## 7b. Compile

```bash
cd "$PROJECT_DIR" && mkdir -p workspace/sim logs && source .veriflow/eda_env.sh && iverilog -o workspace/sim/tb.vvp workspace/rtl/*.v workspace/tb/tb_*.v 2>&1 | tee logs/compile.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
```

## 7c. Run simulation (only if compilation succeeded)

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && vvp workspace/sim/tb.vvp 2>&1 | tee logs/sim.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
# Cleanup VCD from project root (can be large)
rm -f "$PROJECT_DIR"/*.vcd 2>/dev/null
```

## 7d. Analyze output

Read `logs/sim.log`. Pass/Fail criteria:
- Output contains `PASS`/`pass`/`All tests passed` → pass
- Output contains `FAIL`/`fail`/`Error` → fail
- Simulation exits abnormally → fail

If sim fails → go to Error Recovery in the main SKILL.md. Still complete self-check.

## 7e. Hook

```bash
test -f "$PROJECT_DIR/workspace/sim/tb.vvp" || { echo "[HOOK] FAIL — tb.vvp not found"; exit 1; }
# TB integrity check — detect unauthorized modifications
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    md5sum -c "$PROJECT_DIR/.veriflow/tb_checksum" >/dev/null 2>&1 || { echo "[HOOK] FAIL — testbench was modified after Stage 3!"; exit 1; }
fi
grep -qiE "FAIL|error" "$PROJECT_DIR/logs/sim.log" && { echo "[HOOK] FAIL — simulation has failures, check logs/sim.log"; exit 1; }
grep -qiE "PASS|All tests passed" "$PROJECT_DIR/logs/sim.log" && echo "[HOOK] PASS" || echo "[HOOK] FAIL — no PASS found in sim output"
```

If FAIL → go to Error Recovery. Do NOT mark sim as completed.

## 7f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "sim"
```

Mark Stage 7 task as **completed** using TaskUpdate.

## 7g. Journal

```bash
printf "\n## Stage: sim\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/sim/tb.vvp, logs/sim.log\n**Notes**: Simulation passed.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

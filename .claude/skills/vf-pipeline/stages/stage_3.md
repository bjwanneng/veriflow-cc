# Stage 3: timing

**Goal**: Read spec.json + micro_arch.md, generate timing_model.yaml + testbench.

Mark Stage 3 task as **in_progress** using TaskUpdate.

## 3a. Read inputs

Use **Read** tool:
- `$PROJECT_DIR/workspace/docs/spec.json`
- `$PROJECT_DIR/workspace/docs/micro_arch.md`

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

## 3c. Write testbench

Use **Write** tool to write `$PROJECT_DIR/workspace/tb/tb_<design_name>.v`.

Get `<design_name>` from spec.json `design_name` field.

**iverilog Compatibility Rules (CRITICAL)**:
- NO `assert property`, `|->`, `|=>`, `##` delay operator (SVA)
- NO `logic` type (use `reg`/`wire`)
- NO `always_ff`/`always_comb` (use `always`)
- YES `$display`, `$monitor`, `$finish`, `$dumpfile`

Testbench must:
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

Minimum: `max(3, number of functional requirements)` scenarios. Every data-write scenario must read back with a `fail_count` check.

## 3d. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/timing_model.yaml" && ls "$PROJECT_DIR/workspace/tb/"tb_*.v >/dev/null 2>&1 && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
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

# Stage 8: synth

**Goal**: Run yosys synthesis.

Mark Stage 8 task as **in_progress** using TaskUpdate.

## 8a. Read spec for top module name

Use **Read** tool to read `$PROJECT_DIR/workspace/docs/spec.json`. Extract `design_name`.

## 8b. Confirm RTL files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

## 8c. Run synthesis

```bash
cd "$PROJECT_DIR" && mkdir -p workspace/synth && source .veriflow/eda_env.sh
RTL_FILES=$(ls workspace/rtl/*.v | xargs printf 'read_verilog %s; ')
yosys -p "${RTL_FILES} synth -top {top_module}; stat" 2>&1 | tee workspace/synth/synth_report.txt
```

Replace `{top_module}` with `design_name` from spec.json. Using bash `ls` expansion avoids yosys glob issues on Windows.

## 8d. Analyze report

Read `workspace/synth/synth_report.txt`. Extract:
- Whether synthesis succeeded
- Number of cells
- Maximum frequency (if available)
- Area estimate
- Warnings (list top 3)

## 8e. Hook

```bash
test -f "$PROJECT_DIR/workspace/synth/synth_report.txt" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## 8f. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "synth"
```

Mark Stage 8 task as **completed** using TaskUpdate.

## 8g. Journal

```bash
printf "\n## Stage: synth\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/synth/synth_report.txt\n**Notes**: Synthesis complete.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

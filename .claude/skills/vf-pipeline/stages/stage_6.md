# Stage 6: lint

**Goal**: Run iverilog syntax check on RTL files.

Mark Stage 6 task as **in_progress** using TaskUpdate.

## 6a. Confirm files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

## 6b. Run lint

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && iverilog -Wall -tnull workspace/rtl/*.v 2>&1 | tee logs/lint.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
```

## 6c. Analyze results

Read `logs/lint.log`. Categorize errors:
- **syntax error**: missing semicolons, typos
- **port mismatch**: port connection errors
- **undeclared**: undeclared signals
- **other**: unclassified errors

If errors found → go to Error Recovery in the main SKILL.md.

## 6d. Hook

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && iverilog -Wall -tnull workspace/rtl/*.v > /dev/null 2>&1; echo "EXIT_CODE: $?"
```

If exit code != 0 → fix errors, re-run.

## 6e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "lint"
```

Mark Stage 6 task as **completed** using TaskUpdate.

## 6f. Journal

```bash
printf "\n## Stage: lint\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: logs/lint.log\n**Notes**: Syntax check passed.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

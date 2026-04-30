# Stage 6: lint (sub-agent)

**NOTE: This stage runs in PARALLEL with Stage 5 (review). Both are dispatched in a single message with two Agent tool calls.**

**Goal**: Run iverilog syntax check on RTL files.

Mark Stage 6 task as **in_progress** using TaskUpdate.

## 6a-0. Verify testbench integrity

Confirm testbenches were not modified since Stage 3 locked them:

```bash
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    cd "$PROJECT_DIR" && md5sum -c .veriflow/tb_checksum >/dev/null 2>&1 \
        && echo "[INTEGRITY] Testbench checksum OK" \
        || { echo "[INTEGRITY] FAIL — testbench file(s) modified after Stage 3!"; \
             echo "[INTEGRITY] Differences:"; \
             md5sum -c .veriflow/tb_checksum 2>/dev/null | grep FAILED; \
             exit 1; }
else
    echo "[INTEGRITY] No checksum file found — skipping TB integrity check"
fi
```

## 6a. Confirm files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

## 6b. Call vf-linter agent

Call the **Agent** tool with `subagent_type: "vf-linter"` and the following prompt (replace placeholders with absolute paths):

```
PROJECT_DIR={PROJECT_DIR} EDA_ENV={PROJECT_DIR}/.veriflow/eda_env.sh PYTHON_EXE={PYTHON_EXE} SKILL_DIR={CLAUDE_SKILL_DIR}. Source EDA_ENV, run iverilog -Wall -tnull on workspace/rtl/*.v, categorize errors, output LINT_RESULT summary.
```

Replace:
- `{PROJECT_DIR}` with the absolute project directory path
- `{PYTHON_EXE}` with the Python executable path
- `{CLAUDE_SKILL_DIR}` with the installed skill directory path

## 6b-diagnose. If agent reports failure

The agent's text output contains a `LINT_RESULT:` line. Check it:

- **`LINT_RESULT: PASS`** → proceed to **6d. Hook**
- **`LINT_RESULT: FAIL`** → the agent has categorized the errors. Proceed to Error Recovery in SKILL.md:
  1. Use **Read** tool to read `logs/lint.log` for full error details
  2. Follow SKILL.md Error Recovery → fix RTL → re-dispatch vf-linter by going back to **6b**

## 6b-retry. If agent returns 0 tool uses

If the agent made **0 tool calls** (empty response), retry once with the exact same prompt.

## 6b-fallback. Inline fallback

If the retry also returns 0 tool uses, run lint inline:

```bash
cd "$PROJECT_DIR" && source .veriflow/eda_env.sh && iverilog -Wall -tnull workspace/rtl/*.v 2>&1 | tee logs/lint.log; echo "EXIT_CODE: ${PIPESTATUS[0]}"
```

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

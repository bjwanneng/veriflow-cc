# Stage 8: synth (sub-agent)

**Goal**: Run yosys synthesis.

Mark Stage 8 task as **in_progress** using TaskUpdate.

## 8a. Confirm RTL files

```bash
ls -la "$PROJECT_DIR/workspace/rtl/"*.v
```

## 8b. Call vf-synthesizer agent

Call the **Agent** tool with `subagent_type: "vf-synthesizer"` and the following prompt (replace placeholders with absolute paths):

```
PROJECT_DIR={PROJECT_DIR} SPEC={PROJECT_DIR}/workspace/docs/spec.json EDA_ENV={PROJECT_DIR}/.veriflow/eda_env.sh PYTHON_EXE={PYTHON_EXE} SKILL_DIR={CLAUDE_SKILL_DIR}. Source EDA_ENV, Read SPEC for design_name, run yosys synthesis, analyze report, output SYNTH_RESULT summary.
```

Replace:
- `{PROJECT_DIR}` with the absolute project directory path
- `{PYTHON_EXE}` with the Python executable path
- `{CLAUDE_SKILL_DIR}` with the installed skill directory path

## 8b-diagnose. If agent reports failure

The agent's text output contains a `SYNTH_RESULT:` line. Check it:

- **`SYNTH_RESULT: PASS`** → proceed to **8d. Hook**
- **`SYNTH_RESULT: FAIL`** → the agent has summarized the error. Proceed to Error Recovery in SKILL.md:
  1. Use **Read** tool to read `workspace/synth/synth_report.txt` for full details
  2. Follow SKILL.md Error Recovery → fix RTL → re-dispatch vf-synthesizer by going back to **8b**

## 8b-retry. If agent returns 0 tool uses

If the agent made **0 tool calls** (empty response), retry once with the exact same prompt.

## 8b-fallback. Inline fallback

If the retry also returns 0 tool uses, run synthesis inline:

Use **Read** tool to read `$PROJECT_DIR/workspace/docs/spec.json`. Extract `design_name`.

```bash
cd "$PROJECT_DIR" && mkdir -p workspace/synth && source .veriflow/eda_env.sh
RTL_FILES=$(ls workspace/rtl/*.v | xargs printf 'read_verilog %s; ')
yosys -p "${RTL_FILES} synth -top {top_module}; stat" 2>&1 | tee workspace/synth/synth_report.txt
```

Replace `{top_module}` with `design_name` from spec.json.

Read `workspace/synth/synth_report.txt`. Extract:
- Whether synthesis succeeded
- Number of cells
- Maximum frequency (if available)
- Area estimate
- Warnings (list top 3)

## 8d. Hook

```bash
test -f "$PROJECT_DIR/workspace/synth/synth_report.txt" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## 8e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "synth"
```

Mark Stage 8 task as **completed** using TaskUpdate.

## 8f. Journal

```bash
printf "\n## Stage: synth\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/synth/synth_report.txt\n**Notes**: Synthesis complete.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

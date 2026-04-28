# Stage 4: coder (sub-agent per module)

**Goal**: Read spec.json, loop through each module, call vf-coder agent once per module to generate workspace/rtl/*.v.

Mark Stage 4 task as **in_progress** using TaskUpdate.

## 4a. Read spec and extract module list

Use **Read** tool to read `$PROJECT_DIR/workspace/docs/spec.json`.

Extract the list of modules from the `"modules"` array. For each module, note:
- `module_name`
- `module_type` (top, processing, control, memory, interface)

## 4b. Resolve coding_style path

```bash
echo "$HOME/.claude/skills/vf-pipeline/coding_style.md"
```

Save the output as `CODING_STYLE_PATH`.

## 4c. Call vf-coder agent for each module (non-top first, top last)

**IMPORTANT**: Generate sub-modules first, top module last. This ensures the top module knows all sub-module ports.

For each module in the list (skip top module initially, process it last):

Call Agent with:
- `subagent_type`: `vf-coder`
- `prompt`: `CODING_STYLE={CODING_STYLE_PATH} SPEC={PROJECT_DIR}/workspace/docs/spec.json BEHAVIOR_SPEC={PROJECT_DIR}/workspace/docs/behavior_spec.md MICRO_ARCH={PROJECT_DIR}/workspace/docs/micro_arch.md MODULE_NAME={module_name} OUTPUT_DIR={PROJECT_DIR}/workspace/rtl. Read CODING_STYLE then Read SPEC then Read BEHAVIOR_SPEC then Read MICRO_ARCH then Write {PROJECT_DIR}/workspace/rtl/{module_name}.v. Follow coding_style.md, behavior_spec.md, and micro_arch.md strictly.`

Replace all `{...}` placeholders with actual values. Do NOT use shell variables in the prompt — use resolved absolute paths.

After all sub-modules are done, call Agent for the top module (same prompt format).

**Run all agent calls sequentially** — do NOT parallelize, as each call is independent but the top module should be last.

## 4c-retry. If agent returns 0 tool uses

After each agent call, check the result. If the agent completed with **0 tool uses**:

1. **Retry once** — call the same agent again with the exact same prompt
2. If retry also returns 0 tool uses → fall back to 4c-fallback

## 4c-fallback. If retry also fails (0 tool uses)

If a module's agent still fails after retry, generate that module inline:
1. Read `${CLAUDE_SKILL_DIR}/coding_style.md`
2. Read `$PROJECT_DIR/workspace/docs/spec.json`
3. Read `$PROJECT_DIR/workspace/docs/behavior_spec.md`
4. Read `$PROJECT_DIR/workspace/docs/micro_arch.md`
5. **Step 3.5 Internal Verification** — Before writing the .v file, perform the 5-point self-check:
   - **Timing table**: Does the module have a cycle-accurate timing table in comments?
   - **Register delay**: Are all outputs driven by registers (not combinational from inputs)?
   - **Control timing**: Do control signals (valid, ready, enable) align with data timing?
   - **FSM sync**: Are FSM state transitions and outputs both registered?
   - **Counter range**: Do counters cover the full required range (e.g., 0 to N-1 for N cycles)?
   If any check fails, revise the design before proceeding.
6. Use **Write** to create the failed module's .v file

## 4d. Hook

```bash
v_files=$(ls "$PROJECT_DIR/workspace/rtl/"*.v 2>/dev/null)
if [ -n "$v_files" ]; then
    for f in $v_files; do grep -q "endmodule" "$f" 2>/dev/null || echo "[HOOK] MISSING endmodule in $(basename $f)"; done
    echo "[HOOK] PASS"
else
    echo "[HOOK] FAIL"
fi
```

## 4e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "coder"
```

Mark Stage 4 task as **completed** using TaskUpdate.

## 4f. Journal

```bash
printf "\n## Stage: coder\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/rtl/*.v\n**Notes**: RTL modules generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

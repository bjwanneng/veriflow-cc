# Stage 4: coder (sub-agent per module)

**Goal**: Read spec.json, loop through each module, call vf-coder agent once per module to generate workspace/rtl/*.v.

Mark Stage 4 task as **in_progress** using TaskUpdate.

## 4a. Pre-read all design documents (ONCE)

Use **Read** tool to read these files exactly once:

1. `$PROJECT_DIR/workspace/docs/spec.json`
2. `$PROJECT_DIR/workspace/docs/behavior_spec.md`
3. `$PROJECT_DIR/workspace/docs/micro_arch.md`
4. `${CLAUDE_SKILL_DIR}/coding_style.md`

After reading all 4 files, extract from spec.json:
- The `modules` array — list of all modules with their `module_name` and `module_type`
- The `design_name` field

**Design rationale**: Pre-reading here eliminates the sub-agent's need to read these files individually. The main session reads once (~30s total), and passes extracted per-module context inline to each agent call. This saves ~4 tool round-trips per module and reduces per-call context from ~25K tokens to ~8K tokens.

## 4b. Assemble prompts for ALL modules, then dispatch in parallel

### 4b-i. Extract per-module context

From the files already read in 4a, extract context for **each** module (including top):

**From spec.json** — the single module entry for `module_name`:
```json
{"module_name": "...", "module_type": "...", "ports": [...], "parameters": [...], ...}
```

**From behavior_spec.md** — the section for this module (typically Section 2.x matching the module name). Include:
- Cycle-accurate timing tables
- FSM state definitions and transitions
- Timing contracts
- Algorithm pseudocode

**From micro_arch.md** — the section for this module. Include:
- Datapath structure
- Control logic description
- Signal names and FSM states
- Register requirements

**From coding_style.md** — NOT needed in the prompt. The agent definition (vf-coder.md) already contains the condensed key rules.

### 4b-ii. Construct agent prompts

#### Sub-module prompt template

Call Agent with:
- `subagent_type`: `vf-coder`
- `prompt`: (replace ALL placeholders with actual content)

```
MODULE_NAME={module_name}
OUTPUT_FILE={PROJECT_DIR}/workspace/rtl/{module_name}.v

## Module Spec (from spec.json)
{paste the single module JSON entry here}

## Module Behavior (from behavior_spec.md)
{paste the extracted section for this module here}

## Module Micro-Architecture (from micro_arch.md)
{paste the extracted section for this module here}

Write the file at OUTPUT_FILE. Follow the coding rules in your system prompt. Follow the behavior and micro-architecture above strictly.
```

#### Top module prompt template

The top module prompt is the same format, but MUST also include an extra section with all submodule port definitions. This information comes from **spec.json** (design definition), not from reading generated .v files:

```
MODULE_NAME={top_module_name}
OUTPUT_FILE={PROJECT_DIR}/workspace/rtl/{top_module_name}.v

## Module Spec (from spec.json)
{paste the top module JSON entry here}

## Submodule Port Definitions (from spec.json)
For each sub-module, paste its full module entry from spec.json (module_name, ports, parameters).
This is the canonical port definition — instantiate submodules using these ports exactly.

{sub1_module_entry}
{sub2_module_entry}
...

## Module Behavior (from behavior_spec.md)
{paste the extracted section for the top module here}

## Module Micro-Architecture (from micro_arch.md)
{paste the extracted section for the top module here}

Write the file at OUTPUT_FILE. Follow the coding rules in your system prompt. Follow the behavior and micro-architecture above strictly.
```

**Prompt construction rules**:
- Do NOT use shell variables — use resolved absolute paths
- Sub-module prompts: only include that module's own sections
- Top module prompt: include the extra "Submodule Port Definitions" section with ALL sub-module entries from spec.json
- Do NOT include the full file content — extract only the relevant section
- If a section is very long (>200 lines), include it in full — do NOT summarize or truncate

### 4b-iii. Dispatch all agents in parallel

Call **Agent** for ALL modules (sub-modules AND top module) in a **single message** with multiple Agent tool calls. All prompts are pre-assembled from 4a — there are no runtime dependencies between modules.

After all agents complete, check results:
- If agent returned `Module {module_name}.v generated successfully.` → OK
- If agent returned 0 tool uses → retry once with the exact same prompt (4c-retry)

## 4c-retry. If agent returns 0 tool uses

1. **Retry once** — call the same agent again with the exact same prompt
2. If retry also returns 0 tool uses → fall back to 4c-fallback

## 4c-fallback. If retry also fails (0 tool uses)

Generate the module inline using the context already read in 4a:

1. Use the spec, behavior_spec, and micro_arch sections already in memory from 4a
2. **Step 3.5 Internal Verification** — Before writing the .v file, perform the self-check from the coding agent definition
3. Use **Write** to create the failed module's .v file

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
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "coder"
```

Mark Stage 4 task as **completed** using TaskUpdate.

## 4f. Journal

```bash
printf "\n## Stage: coder\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/rtl/*.v\n**Notes**: RTL modules generated.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

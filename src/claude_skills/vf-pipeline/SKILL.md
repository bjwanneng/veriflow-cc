---
name: vf-pipeline
description: Use this skill to start or resume the VeriFlow RTL hardware design pipeline (architect to synth). Trigger this when the user asks to "run the RTL flow", "design hardware", or "start the pipeline". Pass the project directory path as the argument.
---

# RTL Pipeline Orchestrator

This skill IS the plan — execute each stage immediately using Read/Write/Bash/Agent tools. Do NOT plan before executing.

Project directory path: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user for it.

**Variable**: `${CLAUDE_SKILL_DIR}` is set by Claude Code to the skill's installed directory.

---

## Step 0: Initialization

Execute immediately:

```bash
PROJECT_DIR="$ARGUMENTS"
ls -la "$PROJECT_DIR/requirement.md" || echo "[FATAL ERROR] requirement.md not found. STOP and ask the user for the file."
cd "$PROJECT_DIR" && mkdir -p workspace/docs workspace/rtl workspace/tb workspace/sim workspace/synth .veriflow logs

# Report available input files
echo "[INPUT] requirement.md: $(test -f requirement.md && echo YES || echo NO)"
echo "[INPUT] constraints.md: $(test -f constraints.md && echo YES || echo NO)"
echo "[INPUT] design_intent.md: $(test -f design_intent.md && echo YES || echo NO)"
echo "[INPUT] context/: $(ls context/*.md 2>/dev/null | wc -l) file(s)"
ls context/*.md 2>/dev/null || true

# Discover Python (cross-platform: smoke-test each candidate)
_discover_python() {
    local candidates=(
        "$(which python3 2>/dev/null)"
        "$(which python 2>/dev/null)"
        /c/Python*/python.exe
        /c/Users/*/AppData/Local/Programs/Python/*/python.exe
        /usr/bin/python3
        /usr/local/bin/python3
    )
    for p in "${candidates[@]}"; do
        [ -z "$p" ] && continue
        [ -f "$p" ] || continue
        if echo "$p" | grep -q "WindowsApps"; then continue; fi
        if "$p" --version >/dev/null 2>&1; then
            echo "$p"
            return 0
        fi
    done
    return 1
}
PYTHON_EXE=$(_discover_python) || true
echo "[ENV] Python: ${PYTHON_EXE:-NOT FOUND}"

# Discover cocotb
COCOTB_AVAILABLE="false"
if [ -n "$PYTHON_EXE" ] && $PYTHON_EXE -c "import cocotb; import cocotb_tools.runner" 2>/dev/null; then
    COCOTB_AVAILABLE="true"
    echo "[ENV] cocotb: AVAILABLE"
else
    echo "[ENV] cocotb: NOT AVAILABLE"
fi

# Discover EDA tools
EDA_BIN=""
EDA_LIB=""
for base in "/c/oss-cad-suite" "/c/Program Files/iverilog" "/c/Program Files (x86)/iverilog" "/opt/oss-cad-suite" "/usr/local" "/usr" "$HOME/.local"; do
    if [ -d "$base/bin" ] && { [ -f "$base/bin/iverilog" ] || [ -f "$base/bin/iverilog.exe" ]; }; then
        EDA_BIN="$base/bin"
        [ -d "$base/lib" ] && EDA_LIB="$base/lib"
        [ -d "$base/lib/ivl" ] && EDA_LIB="$base/lib:$base/lib/ivl"
        break
    fi
done
if [ -z "$EDA_BIN" ] && command -v iverilog >/dev/null 2>&1; then
    EDA_BIN=$(dirname "$(command -v iverilog)")
    if [ "$EDA_BIN" = "/usr/bin" ]; then EDA_LIB="/usr/lib:/usr/lib/ivl"; fi
fi

cat > "$PROJECT_DIR/.veriflow/eda_env.sh" << ENVEOF
export PYTHON_EXE="$PYTHON_EXE"
export EDA_BIN="$EDA_BIN"
export EDA_LIB="$EDA_LIB"
export COCOTB_AVAILABLE="$COCOTB_AVAILABLE"
export PATH="$EDA_BIN:$EDA_LIB:\$PATH"
ENVEOF
echo "[ENV] EDA_BIN=$EDA_BIN  EDA_LIB=$EDA_LIB"

source "$PROJECT_DIR/.veriflow/eda_env.sh"
which yosys iverilog vvp 2>/dev/null || echo "[WARN] Some EDA tools not found"
iverilog -V 2>&1 | head -1 || echo "[WARN] iverilog smoke test failed"

# Check existing state
if [ -f "$PROJECT_DIR/.veriflow/pipeline_state.json" ]; then
    echo "[STATUS] Existing state — resume from next incomplete stage:"
    cat "$PROJECT_DIR/.veriflow/pipeline_state.json"
else
    echo "[STATUS] New project, starting from Stage 1."
fi
```

If cocotb is not installed, ask the user if they want to install it. If resuming, check `stages_completed` and skip those stages.

### 0a. Initialize stage journal

```bash
if [ -f "$PROJECT_DIR/workspace/docs/stage_journal.md" ]; then
    printf "\n---\n\n**Session resumed** at $(date -Iseconds)\n\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
else
    cat > "$PROJECT_DIR/workspace/docs/stage_journal.md" << 'EOF'
# VeriFlow Pipeline Stage Journal

This file records the progress, outputs, and key decisions for each pipeline stage.
EOF
fi
```

### 0b. Batch Requirements Clarification

Read ALL input files in parallel (single message with multiple Read calls):
- `$PROJECT_DIR/requirement.md` (required)
- `$PROJECT_DIR/constraints.md` (optional)
- `$PROJECT_DIR/design_intent.md` (optional)
- `$PROJECT_DIR/context/*.md` files

After reading, systematically check for missing/ambiguous information across these sections:

**A. Functional clarity**: Module functionality, interface protocol, data format, FSM behavior, clock domain crossings
**B. Constraint clarity**: Clock frequency, target platform, area/power budget, reset strategy, IO standards
**C. Design intent**: Architecture style, module partitioning, interface preferences, IP reuse, key decisions
**D. Algorithm & protocol**: Algorithm reference, pseudocode, key formulas, test vectors
**E. Timing completeness**: Cycle-level behavior, latency, throughput, interface timing, reset recovery, backpressure
**F. Domain knowledge**: Design domain, standard reference, prerequisite concepts, test vectors
**G. Information completeness**: Implicit assumptions, missing scenarios

**Smart filtering**: For each item in A-G, check if input files already answer it. If answered → note "confirmed from input" and skip. Only ask about what's truly missing or ambiguous.

**Batch questions**: Use AskUserQuestion with up to 4 questions per call. Group related questions together. Repeat until all sections are resolved.

### 0c. Write clarifications.md

After all questions are resolved, use Write to create `$PROJECT_DIR/.veriflow/clarifications.md`:

```markdown
# Requirements Clarifications
## A. Functional Clarity
- Module functionality: [answer or "confirmed from requirement.md"]
- Interface protocol: [answer]
...
## B. Constraint Clarity
...
```

### 0d. Create pipeline task list

Use TaskCreate to create one task per pipeline stage. If resuming, only create tasks for stages NOT in `stages_completed`.

**IMPORTANT**: Every Bash call that uses EDA tools MUST start with:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
```

---

## Design Rules

See `${CLAUDE_SKILL_DIR}/design_rules.md` for full rules. Summary:
- Synchronous active-high reset named `rst`
- Port naming: `_n` suffix for active-low, `_i`/`_o` for direction
- **Verilog-2005 only** — NO SystemVerilog
- Interface Lock: port names, handshake protocols, and module hierarchy are frozen after Stage 1

---

## Combined State + Hook + Journal Command

After each subagent completes, run ONE combined command:

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "<STAGE>" --start
```

Then after subagent returns:

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "<STAGE>" --hook="<HOOK_COMMAND>" --journal-outputs="<OUTPUT_FILES>" --journal-notes="<NOTES>"
```

---

## Stage Dispatch

### Stage 1: Architect (subagent — vf-architect)

1. Record start time:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "architect" --start
```

2. Dispatch vf-architect subagent via Agent tool (subagent_type: general-purpose):
   - **Prompt must include**: PROJECT_DIR path, CLARIFICATIONS path, TEMPLATES_DIR path
   - **Inline in prompt**: Full contents of requirement.md, constraints.md (if exists), design_intent.md (if exists), context/*.md (if any)
   - The agent reads templates on demand and generates spec.json + behavior_spec.md + golden_model.py

3. After agent returns, run combined hook + state + journal:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "architect" --hook="test -f workspace/docs/spec.json && grep -q module_name workspace/docs/spec.json && test -f workspace/docs/behavior_spec.md && grep -q 'Domain Knowledge' workspace/docs/behavior_spec.md" --journal-outputs="workspace/docs/spec.json, workspace/docs/behavior_spec.md" --journal-notes="Specification and behavior spec generated"
```

4. Mark Stage 1 task as completed via TaskUpdate.

### Stage 2: Microarch (subagent — vf-microarch)

1. Record start time:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "microarch" --start
```

2. Read spec.json and behavior_spec.md (parallel Read calls) to include inline in prompt.

3. Dispatch vf-microarch subagent via Agent tool:
   - **Prompt must include**: PROJECT_DIR path
   - **Inline in prompt**: spec.json content, behavior_spec.md content, requirement.md content, design_intent.md content (if exists)

4. After agent returns, run combined hook + state + journal:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "microarch" --hook="test -f workspace/docs/micro_arch.md && wc -l workspace/docs/micro_arch.md | awk '\$1 >= 10 {exit 0} {exit 1}'" --journal-outputs="workspace/docs/micro_arch.md" --journal-notes="Microarchitecture documented"
```

5. Mark Stage 2 task as completed via TaskUpdate.

### Stage 3: Timing (subagent — vf-timing)

1. Record start time:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "timing" --start
```

2. Read spec.json, micro_arch.md, and behavior_spec.md (parallel Read calls) to include inline in prompt.

3. Dispatch vf-timing subagent via Agent tool:
   - **Prompt must include**: PROJECT_DIR path, TEMPLATES_DIR path, SKILL_DIR path, PYTHON_EXE path, COCOTB_AVAILABLE value
   - **Inline in prompt**: spec.json content, micro_arch.md content, behavior_spec.md content

4. After agent returns, run combined hook + state + journal:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "timing" --hook="test -f workspace/docs/timing_model.yaml" --journal-outputs="workspace/docs/timing_model.yaml, workspace/tb/tb_*.v" --journal-notes="Timing model and testbenches generated"
```

5. Mark Stage 3 task as completed via TaskUpdate.

### Stage 4: Coder (subagent — vf-coder)

Use **Read** tool to open `${CLAUDE_SKILL_DIR}/stages/stage_4.md`, then execute its instructions (pre-read docs, dispatch vf-coder per module in parallel).

### Stage 5 + 6: Review + Lint (parallel subagents)

1. Record start times:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "review" --start
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "lint" --start
```

2. Dispatch BOTH agents in a **single message** with two Agent tool calls:
   - Agent 1: vf-reviewer (subagent_type from agent definition)
   - Agent 2: vf-linter (subagent_type from agent definition)

3. After BOTH return, run combined hook + state for each (sequential — no race condition):
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "review" --hook="test -f workspace/rtl/static_report.json" --journal-outputs="workspace/rtl/static_report.json" --journal-notes="Static analysis complete"
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "lint" --hook="test -f logs/lint.log" --journal-outputs="logs/lint.log" --journal-notes="Lint complete"
```

4. Mark Stage 5 and Stage 6 tasks as completed via TaskUpdate.

### Stage 7: Simulation (inline)

Use **Read** tool to open `${CLAUDE_SKILL_DIR}/stages/stage_7.md`, then execute its instructions inline. This is the only stage that runs inline — it needs main session context for error recovery.

### Stage 8: Synth (subagent — vf-synthesizer)

Use **Read** tool to open `${CLAUDE_SKILL_DIR}/stages/stage_8.md`, then execute its instructions.

---

## Error Recovery

When any stage fails (lint errors, sim failure, synth failure):

### Subagent Stage Error Recovery

For stages that use subagents, the error recovery flow:

1. **Subagent runs and reports** — returns a text summary. All artifacts written to disk.
2. **Main session reads artifacts** — reads diagnostic files (sim.log, wave_table.txt, static_report.json, etc.)
3. **Main session diagnoses** — Error Recovery Step 1.5 runs in main session, which has full design context.
4. **Main session fixes RTL** — Edit tool modifies the relevant RTL file(s).
5. **Re-dispatch subagent** — go back to the failed stage's dispatch step.
6. **Retry budget** — 3-retry policy applies at orchestrator level.

**Key principle**: Subagents are **stateless workers** — they generate artifacts but do NOT diagnose or fix. The main session is the **only entity that modifies RTL**.

### Step 1: Diagnose
- Read the error output from the failed stage
- Read the relevant RTL files from `workspace/rtl/`
- **Reference `bug_patterns.md`** for a catalog of known bug patterns

### Step 1.5: Structured Root Cause Analysis (MANDATORY)

Before modifying ANY file, complete the analysis and write it to `stage_journal.md`.

#### Step 1.5-A: Read the waveform table (timing errors ONLY)

```bash
ls "$PROJECT_DIR/logs/wave_table.txt" "$PROJECT_DIR/logs/wave_"*.txt 2>/dev/null
```

Use Read tool to read `logs/wave_table.txt`. Answer:

| Question | Where to look |
|----------|--------------|
| At the `[FAIL]` cycle, what is the FSM state? | `state_reg` / `state` column |
| Is the FSM in the expected state per timing_model.yaml? | Compare with scenario assertions |
| What is the value of the failing signal at `[FAIL]` cycle? | Named column |
| When did the failing signal LAST CHANGE before `[FAIL]`? | Scan backwards from `[FAIL]` row |
| Is the error an off-by-one? | Compare cycle N-1 vs N vs N+1 |
| Is `rst` still asserted at `[FAIL]`? | `rst` column |

**Common timing patterns**:

```
Pattern A — Off-by-one pipeline delay:
  Cycle N:   input valid, data_out = 0x00   ← [FAIL] expected 0xAB
  Cycle N+1: input valid, data_out = 0xAB   ← correct value arrived one cycle late
  → Fix: sample output one cycle later, OR remove extra register stage

Pattern B — Reset not clearing output register:
  Cycle 0: rst=1, data_out = 0xFF   ← [FAIL] expected 0x00 during reset
  → Fix: add output_reg to reset block

Pattern C — FSM stuck / missing transition:
  Cycle N:   state=CALC, done_flag=1    ← should transition to DONE
  Cycle N+1: state=CALC, done_flag=1   ← stuck
  → Fix: check FSM transition condition

Pattern D — Handshake violation (valid deasserted too early):
  → Fix: hold valid until ready is seen

Pattern E — Counter range error (N vs N-1):
  → Fix: change loop terminal condition, check for integer vs reg overflow

Pattern F — Data value mismatch (algorithm error):
  → Diagnose: compare RTL with golden model cycle-by-cycle
  → Find FIRST divergence cycle, trace back to formula/shift alignment
```

#### Step 1.5-B: 5-point root cause analysis

1. **Error location**: Which `[FAIL]` line? Which cycle? Which signal?
2. **Signal trace**: Which module drives it? Which `always` block?
3. **Root cause hypothesis**: Exact RTL line that is wrong. Reference pattern A-F.
4. **Minimal fix plan**: File, lines, exact change.
5. **Impact scope**: Which other signals/modules affected?

If you cannot form a hypothesis, STOP and ask the user. Do NOT guess-and-fix.

### Step 2: Classify
- **syntax** (lint): typos, missing declarations, port mismatches
- **logic** (sim): incorrect functionality, timing issues, FSM errors
- **timing** (synth): non-synthesizable constructs, timing violations

### Step 3: Fix

Common error patterns:

| Error Pattern | Cause | Fix |
|--------------|-------|-----|
| `cannot be driven by continuous assignment` | `reg` used with `assign` | Change to `wire` or use `always` |
| `Unable to bind wire/reg/memory` | Forward reference or typo | Move declaration or fix typo |
| `Variable declaration in unnamed block` | Variable in `always` without named block | Move to module level |
| `Width mismatch` | Assignment between different widths | Add explicit width cast |
| `is not declared` | Typo or missing declaration | Fix typo or add declaration |
| `Multiple drivers` | Two assignments to same signal | Remove duplicate |
| `Latch inferred` | Incomplete case/if without default | Add default case or else branch |

Fix rules:
- Only modify files that have issues
- Preserve original coding style and design intent
- Do NOT change module interfaces (ports) — Interface Lock
- Do NOT add/remove functionality
- **Functional integrity**: fix must NOT remove, disable, or stub out existing functionality
- Make minimal changes, fix one error at a time
- **Debug budget**: 3 fix-and-retry cycles max, then STOP and ask user
- **Spec-level rollback**: If behavior_spec has internal contradiction, ask user about rolling back to Stage 1

After fixing, re-run the failed stage to verify.

### Step 4: Sync upstream documents

If fix changes architectural behavior, update:
- **Logic fix** → update `micro_arch.md`
- **Timing fix** → update `timing_model.yaml`

### Step 5: Log recovery to journal

```bash
printf "\n### Recovery: <stage_name>\n**Timestamp**: $(date -Iseconds)\n**Attempt**: <N>\n**Error type**: <syntax|logic|timing>\n**Fix summary**: <description>\n**Result**: <PASS|FAIL|PENDING>\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

### Retry Policy

1. **1st fail**: Fix RTL, retry the stage
2. **2nd fail**: Rollback to earlier stage and re-run sequentially
3. **3rd fail**: STOP and notify user

Rollback targets by error type:

| Error Type | Rollback To | Re-run Path |
|-----------|-------------|-------------|
| syntax | coder | coder → review → lint → sim → synth |
| logic | microarch | microarch → timing → coder → review → lint → sim → synth |
| timing | timing | timing → coder → review → lint → sim → synth |

To perform a rollback:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" --reset <target_stage>
```

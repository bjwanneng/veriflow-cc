---
name: vf-rtl
description: Use this skill to start or resume the VeriFlow RTL hardware design pipeline (architect to synth). Trigger this when the user asks to "run the RTL flow", "design hardware", or "start the pipeline". Pass the project directory path as the argument.
---

# RTL Pipeline Orchestrator

This skill IS the plan — execute each stage immediately using Read/Write/Bash/Agent tools. Do NOT plan before executing.

Project directory path: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user for it.

**Variable**: `${CLAUDE_SKILL_DIR}` is set by Claude Code to the skill's installed directory.

---

## Step 0: Initialization

Run the initialization script:

```bash
PY_INIT="${PYTHON_EXE:-python}"
cd "$ARGUMENTS" && "$PY_INIT" "${CLAUDE_SKILL_DIR}/init.py" "$ARGUMENTS"
source "$ARGUMENTS/.veriflow/eda_env.sh"
```

Read the output to determine: new project or resuming. If resuming, skip stages in `stages_completed`.

### Permission Check (sub-agent tools)

Sub-agents cannot interact with the user — any permission prompt will hang the pipeline.
Check that the following tools are pre-approved in the project's `.claude/settings.json`:

```bash
SETTINGS=".claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
    echo '{"permissions":{"allow":[]}}' > "$SETTINGS"
fi
python3 -c "
import json
s = json.load(open('$SETTINGS'))
allow = s.setdefault('permissions', {}).setdefault('allow', [])
# Tools that sub-agents need (must not trigger permission dialog):
# - WebSearch: main session only (sub-agents do not have it)
# - Bash(python*): all agents run python for hook validation
# - Bash(test*): agents run 'test -f ...' for file existence checks
# - Write: agents write output files (spec.json, golden_model.py, etc.)
needed = [
    'Bash(python*)',
    'Bash(python3*)',
    'Bash(test*)',
]
added = []
for tool in needed:
    if not any(tool in rule for rule in allow):
        allow.append(tool)
        added.append(tool)
if added:
    json.dump(s, open('$SETTINGS','w'), indent=2)
    print(f'[PERM] Added to allowlist: {added}')
else:
    print('[PERM] All sub-agent tools already allowed')
"
```

## Step 0b: Requirements Clarification

Read ALL input files in parallel (single message with multiple Read calls):
- `$ARGUMENTS/requirement.md` (required)
- `$ARGUMENTS/constraints.md` (optional)
- `$ARGUMENTS/design_intent.md` (optional)
- `$ARGUMENTS/context/*.md` files

Check each category below. If input files already answer it → note "confirmed" and skip. Only ask about what's missing or ambiguous. Use AskUserQuestion with up to 4 questions per call.

**A.** Functional clarity: module functionality, interface protocol, data format, FSM behavior, clock domain crossings
**B.** Constraint clarity: clock frequency, target platform, area/power budget, reset strategy, IO standards
**C.** Design intent: architecture style, module partitioning, interface preferences, IP reuse, key decisions
**D.** Algorithm & protocol: algorithm reference, pseudocode, key formulas, test vectors
**E.** Timing completeness: cycle-level behavior, latency, throughput, interface timing, reset recovery, backpressure
**F.** Domain knowledge: design domain, standard reference, prerequisite concepts, test vectors
**G.** Information completeness: implicit assumptions, missing scenarios

After resolved, write `$ARGUMENTS/.veriflow/clarifications.md` with all answers.

## Step 0c: Create task list

Create one task per pipeline stage (skip if resuming and already completed):

- `Stage 1: spec_golden`
- `Stage 2: codegen`
- `Stage 3: verify_fix`
- `Stage 4: lint_synth`

---

## Stage Pattern (ALL stages follow this)

Every stage MUST execute these 3 steps in order:

**Pre-stage:**
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "<STAGE>" --start
```

**Execute:** dispatch agents (Stages 1/2/4) or run inline (Stage 3)

**Post-stage:**
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "<STAGE>" --hook="<HOOK_CMD>" --journal-outputs="<FILES>" --journal-notes="<NOTES>"
```
Then: `TaskUpdate` mark the stage task as completed.

---

## Stage 1: spec_golden

### Pre-stage: Web Research + Template Pre-read

**Read all input files first** (run in main session, parallel Read calls):
- `${CLAUDE_SKILL_DIR}/templates/spec_template.json` → passed as `SPEC_TEMPLATE`
- `${CLAUDE_SKILL_DIR}/templates/golden_model_template.py` → passed as `GOLDEN_TEMPLATE`
- `$PROJECT_DIR/requirement.md`
- `$PROJECT_DIR/constraints.md` (if exists)
- `$PROJECT_DIR/design_intent.md` (if exists)
- `$PROJECT_DIR/context/*.md` (if exists)
- `$PROJECT_DIR/.veriflow/clarifications.md`

**Web Research** (run in main session, results passed inline to sub-agents):

After reading all input files above, judge whether WebSearch is needed:
- If `requirement.md` + `context/*.md` already contain: algorithm specification, test vectors,
  pin/protocol definitions, and enough detail to build spec.json and golden_model.py →
  **skip WebSearch**. Write a note to `$PROJECT_DIR/.veriflow/web_research.md`:
  ```
  # Web research skipped — input files provide sufficient detail
  Algorithm: <name>, source: <which files had the info>
  ```
- Otherwise, extract the algorithm/design name from `requirement.md`, then use WebSearch:
  - `"<algorithm_name> specification test vectors"` — for spec.json constraints
  - `"<algorithm_name> Verilog RTL reference"` — for coder patterns
  Store results in `$PROJECT_DIR/.veriflow/web_research.md`

### Agent Dispatch: Single spec-golden agent

**Run vf-spec-golden** (single Agent call):

- **vf-spec-golden** (subagent_type: general-purpose)
  - Prompt includes: PROJECT_DIR, CLARIFICATIONS path, SPEC_TEMPLATE content,
    GOLDEN_TEMPLATE content, WEB_RESEARCH content, all input file contents inline
  - The agent generates **both** spec.json and golden_model.py in one pass,
    with timing alignment done internally (it writes spec.json first, then uses
    its cycle_timing to align golden_model.py trace cycles).

After it returns:

1. Read `workspace/docs/spec.json` and `workspace/docs/golden_model.py` to verify.

**Timing contract check** (pre-verification, before codegen):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/timing_contract_checker.py" \
    --spec workspace/docs/spec.json \
    --golden workspace/docs/golden_model.py \
    --output logs/timing_check.json
```
If this reports errors, **auto-fix first** — the checker can correct most common timing contract mistakes (registered→combinational delays, missing handshake fields, latency mismatches):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/timing_contract_checker.py" \
    --fix \
    --spec workspace/docs/spec.json \
    --golden workspace/docs/golden_model.py \
    --output logs/timing_check.json
```
Re-run the checker after `--fix` to confirm all errors are resolved. Only if errors remain after auto-fix, review `logs/timing_check.json` and manually fix spec.json or golden_model.py. Errors indicate timing contradictions that will cause RTL bugs.

**Golden model self-check** (pre-codegen gate):

Before proceeding to Stage 2, verify that golden_model.py passes its own test
vectors. This catches algorithmic bugs before RTL is generated.

```bash
cd "$PROJECT_DIR"
if [ -f workspace/docs/golden_model.py ]; then
    $PYTHON_EXE workspace/docs/golden_model.py 2>&1 | tee logs/golden_selfcheck.log
    if grep -q "FAIL" logs/golden_selfcheck.log; then
        echo "[GOLDEN] Self-check FAILED — fix golden_model.py before proceeding."
        # Do NOT proceed to Stage 2
    fi
fi
```

```bash
state.py "$PROJECT_DIR" "spec_golden" --hook="test -f workspace/docs/spec.json && test -f workspace/docs/golden_model.py" --journal-outputs="workspace/docs/spec.json, workspace/docs/golden_model.py" --journal-notes="spec.json interface + golden_model.py behavior; no timing_model.py"
```
TaskUpdate complete.

---

## Stage 2: codegen

Read spec.json, golden_model.py, and coding_style.md (parallel Read calls) to include inline in prompts.

**Single-path dispatch**: All modules go through AI Assembly (vf-coder).

### AI Assembly

- **One vf-coder per module** in spec.json (subagent_type: general-purpose)
  - Prompt includes: MODULE_NAME, OUTPUT_FILE path
  - `GOLDEN_MODEL`: the relevant Python functions from golden_model.py that
    describe this module's behavior. The orchestrator extracts these by matching
    the module name against function names/classes in golden_model.py. Include
    the full Python implementation — vf-coder translates it into Verilog.
  - `MODULE_SPEC`: this module's ports/parameters/timing_contract from spec.json
  - `TIMING_TABLE`: main session builds a cycle-accurate timing table from
    spec.json `cycle_timing` and `timing_contract`, showing:
    - Registered outputs (use `output wire` + `reg` + `assign`)
    - Combinational outputs (use `output wire` + `assign` directly)
    - Pipeline stages and latency
  - `WEB_RESEARCH`: content from `.veriflow/web_research.md` — **only if the file
    has substantive content** (more than just "skipped" or "unavailable"). If
    minimal, omit this field entirely to save prompt tokens.
  - `ANCHOR_1`: auto-selected by `${CLAUDE_SKILL_DIR}/anchors/_selector.py`.
    Priority: (1) explicit `anchor_hints` in spec.json, (2) auto-inferred from
    module ports/cycle_timing (fsm, shift, pipeline, hash, handshake, barrel),
    (3) generic fallback (`fsm_4state` for control, `pipeline_register` for data-path).
    **Inline the contents of both files**: `module.v` AND `trace.md`.
    The trace.md gives concrete cycle values that anchor the expected behavior.
    Example block:
    ```
    ANCHOR_1: hash_round_one_cycle
    --- module.v ---
    <contents of anchors/hash_round_one_cycle/module.v>
    --- trace.md ---
    <contents of anchors/hash_round_one_cycle/trace.md>
    ```
  - `ANCHOR_2`: second anchor (same format as ANCHOR_1). **Only provide for
    modules with FSM or multi-cycle timing_contract** — simple combinational
    or single-stage modules need only ANCHOR_1.
  - Condensed coding_style.md content
  - For top modules: include submodule port definitions from spec.json

### TB Generation + All Agent Dispatch

Dispatch ALL agents in parallel (single message):

- One vf-coder agent per module
- **One vf-tb-gen** (subagent_type: general-purpose)
  - Prompt includes: PROJECT_DIR, DESIGN_NAME, spec.json content, golden_model.py content, COCOTB_AVAILABLE flag, `${CLAUDE_SKILL_DIR}/templates` path
  - **DRIVE_PHASE_CYCLES**: Read from `spec.json timing_convention.golden_to_rtl_offset_cycles`. If not set, fall back to `max(pipeline_delay_cycles)` from timing_contract.
  - **CRITICAL**: The Verilog testbench MUST respect input hold time derived from spec.json `module_connectivity` timing_contract. Data inputs MUST remain stable for at least `DRIVE_PHASE_CYCLES + 1` cycles after the valid pulse.

After ALL return, verify outputs exist:
```bash
ls "$PROJECT_DIR/workspace/rtl/"*.v "$PROJECT_DIR/workspace/tb/"*.v "$PROJECT_DIR/workspace/tb/"*.py 2>/dev/null
```
```bash
state.py "$PROJECT_DIR" "codegen" --hook="ls workspace/rtl/*.v >/dev/null 2>&1 && (test -f workspace/tb/test_*.py || test -f workspace/tb/tb_*.v)" --journal-outputs="workspace/rtl/*.v, workspace/tb/test_*.py, workspace/tb/tb_*.v" --journal-notes="RTL and testbench generated in parallel"
```
TaskUpdate complete.

---

## Stage 3: verify_fix (inline — runs in main session)

**IMPORTANT**: This stage runs inline because error recovery needs main session context for Edit tool.

Pre-stage:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "verify_fix" --start
```

### Golden Model Self-Check (BEFORE simulation)

If golden_model.py exists, verify it passes its own test vectors first.
This catches golden model bugs BEFORE wasting time on RTL debugging.

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
cd "$PROJECT_DIR"
if [ -f workspace/docs/golden_model.py ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/iverilog_runner.py" \
        --golden-check workspace/docs/golden_model.py 2>&1 | tee logs/golden_selfcheck.log
    if [ $? -ne 0 ]; then
        echo "[GOLDEN] Self-check FAILED — the reference model has bugs."
        echo "[GOLDEN] Fix golden_model.py FIRST. The problem is NOT in the RTL."
        # Do NOT consume retry budget — this is a golden model issue
        state.py "$PROJECT_DIR" "verify_fix" \
            --hook="test -f workspace/docs/golden_model.py" \
            --journal-outputs="logs/golden_selfcheck.log" \
            --journal-notes="Golden model self-check failed — golden model has bugs"
        # STOP and notify user to fix the golden model before retrying
    fi
fi
```

### Cocotb per-cycle verification (if cocotb available)

Before running Verilog simulation, run cocotb with per-cycle internal signal
comparison. This is the PRIMARY debugging tool — it finds the FIRST divergence
point automatically, instead of only checking final outputs.

```bash
if command -v cocotb-config &>/dev/null; then
    cd "$PROJECT_DIR/workspace/tb"
    make SIM=icarus 2>&1 | tee "$PROJECT_DIR/logs/cocotb.log"
    cd "$PROJECT_DIR"
    if grep -q "FIRST DIVERGENCE" logs/cocotb.log; then
        echo "[COCOTB] Internal signal mismatch found — see cocotb.log for details"
        # Extract first divergence info — this is the PRIMARY diagnostic
        # for error_recovery.md. Do NOT guess the root cause.
    fi
fi
```

If cocotb is not available, proceed with Verilog simulation as before.

### Run simulation

```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
cd "$PROJECT_DIR"
TOP_MODULE=$($PYTHON_EXE -c "
import json
for m in json.load(open('workspace/docs/spec.json')).get('modules', []):
    if m.get('module_type') == 'top': print(m['module_name']); break
")
VERILOG_TB=$(ls workspace/tb/tb_*.v 2>/dev/null | head -1)
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/iverilog_runner.py" \
    --module $TOP_MODULE --rtl-dir workspace/rtl --tb-file "$VERILOG_TB" \
    --build-dir workspace/sim --verbose 2>&1 | tee logs/sim.log
```

### If PASS

```bash
state.py "$PROJECT_DIR" "verify_fix" --hook="grep -q 'ALL TESTS PASSED' logs/sim.log" --journal-outputs="logs/sim.log" --journal-notes="Simulation passed"
```
TaskUpdate complete. Go to Stage 4.

### If FAIL

1. **Run timing diagnostic + expected trace** (BEFORE manual analysis):
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
LOG_FILE=$(test -f logs/cocotb.log && echo logs/cocotb.log || echo logs/sim.log)
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/timing_diagnostic.py" \
    --log "$LOG_FILE" \
    --golden workspace/docs/golden_model.py \
    --spec workspace/docs/spec.json \
    --output logs/timing_diagnostic.json
```

   Then, generate the expected per-cycle register trace from golden_model.py.
   This complements the bug-class output of `timing_diagnostic.py` with
   concrete `expected[cycle][reg]` values to compare against the VCD-derived
   `actual[cycle][reg]` table. Cycle count is derived from `spec.json`
   (max `pipeline_delay_cycles + 4`, fallback 16):
```bash
cd "$PROJECT_DIR"
EXPECTED_TRACE_CYCLES=$($PYTHON_EXE -c "
import json
try:
    spec = json.load(open('workspace/docs/spec.json'))
    explicit = spec.get('constraints', {}).get('verification', {}).get('trace_cycles')
    if isinstance(explicit, int):
        print(explicit)
    else:
        delays = []
        for m in spec.get('modules', []):
            d = m.get('timing_contract', {}).get('pipeline_delay_cycles')
            if isinstance(d, (int, float)):
                delays.append(int(d))
        print(max(delays) + 4 if delays else 16)
except Exception:
    print(16)
")
EXPECTED_TRACE_CYCLES=$EXPECTED_TRACE_CYCLES $PYTHON_EXE - <<'PY' 2>&1 | tee logs/expected_trace_gen.log
import importlib.util, sys, os, json
sys.path.insert(0, "workspace/docs")
spec = importlib.util.spec_from_file_location("_gm", "workspace/docs/golden_model.py")
gm = importlib.util.module_from_spec(spec); spec.loader.exec_module(gm)
cycles = int(os.environ.get("EXPECTED_TRACE_CYCLES", 16))
print(f"[expected-trace] cycles={cycles}")

trace = None

# Try multiple golden model interfaces (not all projects use the same names)
try:
    # Interface 1: compute(inputs_dict, trace=True) + TEST_VECTORS
    if hasattr(gm, "compute") and hasattr(gm, "TEST_VECTORS"):
        tv = gm.TEST_VECTORS[0]
        inputs = tv.get("inputs", tv)
        trace = gm.compute(inputs, trace=True)
        print("[expected-trace] used gm.compute(inputs, trace=True)")
except Exception as e:
    print(f"[expected-trace] compute() failed: {e}")

if trace is None:
    try:
        # Interface 2: run(index) -> list of per-cycle dicts
        if hasattr(gm, "run"):
            trace = gm.run(0)
            print("[expected-trace] used gm.run(0)")
    except Exception as e:
        print(f"[expected-trace] run() failed: {e}")

if trace is None:
    try:
        # Interface 3: simulate(inputs, trace=True)
        if hasattr(gm, "simulate") and hasattr(gm, "TEST_VECTORS"):
            tv = gm.TEST_VECTORS[0]
            inputs = tv.get("inputs", tv)
            trace = gm.simulate(inputs, trace=True)
            print("[expected-trace] used gm.simulate(inputs, trace=True)")
    except Exception as e:
        print(f"[expected-trace] simulate() failed: {e}")

if trace:
    with open("logs/expected_trace_golden.md", "w") as f:
        f.write("## Golden Model Expected Trace\n\n")
        f.write("| cycle | signals |\n")
        f.write("|------:|---------|\n")
        for i, entry in enumerate(trace[:cycles]):
            signals = " ".join(f"{k}=0x{v:x}" if isinstance(v, int) and v > 9 else f"{k}={v}" for k, v in entry.items())
            f.write(f"| {i} | {signals} |\n")
    print(f"[expected-trace] -> logs/expected_trace_golden.md ({len(trace)} cycles)")
else:
    print("[expected-trace] could not generate trace — golden_model.py interface not recognized")
PY
```
   Read `logs/expected_trace_golden.md` along with the simulation divergence
   report — `expected[cycle][reg] vs actual[cycle][reg]` is the fastest way
   to localise the wrong NBA assignment in the RTL.

2. **Read** `logs/timing_diagnostic.json` — this contains the classification
   (B_late/B_early/A/D) and `fix_suggestion` with precise instructions.
   **Follow the fix_suggestion directly** — you do NOT need to understand NBA timing.

3. **If no diagnosis** (tool returns "No FIRST DIVERGENCE found"):
   **Read** `${CLAUDE_SKILL_DIR}/error_recovery.md` — follow the full procedure
   **Collect data**: read `logs/sim.log`, run vcd2table diff, classify bug type
   **5-point root cause analysis** → write to `stage_journal.md`

4. **Fix RTL** using Edit tool

5. **Re-run simulation** (go back to "Run simulation" above)

6. **Retry budget**: 3 attempts total
   - 1st fail: fix RTL, retry
   - 2nd fail: `state.py --reset codegen`, restart from Stage 2
   - 3rd fail: STOP, notify user

---

## Stage 4: lint_synth

Dispatch 2 parallel agents (single message):

- **vf-linter** (subagent_type: general-purpose) — include PROJECT_DIR, EDA_ENV path, PYTHON_EXE, SKILL_DIR
- **vf-synthesizer** (subagent_type: general-purpose) — include PROJECT_DIR, SPEC path, EDA_ENV path, PYTHON_EXE, SKILL_DIR

After BOTH return:

If lint failed → fix syntax errors in main session, re-run lint only.
If synth failed → check report, fix if needed.

```bash
state.py "$PROJECT_DIR" "lint_synth" --hook="test -f logs/lint.log && test -f workspace/synth/synth_report.txt" --journal-outputs="logs/lint.log, workspace/synth/synth_report.txt" --journal-notes="Lint and synthesis complete"
```
TaskUpdate complete. Pipeline done.

---

## Design Rules Summary

See `${CLAUDE_SKILL_DIR}/design_rules.md` for full rules.

- Synchronous active-high reset named `rst`
- Port naming: `_n` suffix for active-low, `_i`/`_o` for direction
- **Verilog-2005 only** — NO SystemVerilog
- Interface Lock: port names, handshake protocols, and module hierarchy are frozen after Stage 1

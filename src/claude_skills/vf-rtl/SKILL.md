---
name: vf-rtl
description: Use this skill to start or resume the VeriFlow RTL hardware design pipeline (architect to synth). Trigger this when the user asks to "run the RTL flow", "design hardware", or "start the pipeline". Pass the project directory path as the argument. Optional: append `--benchmark` to auto-generate a benchmark report after the pipeline completes.
---

# RTL Pipeline Orchestrator

This skill IS the plan — execute each stage immediately using Read/Write/Bash/Agent tools. Do NOT plan before executing.

Project directory path: `$PROJECT_DIR`

If `$PROJECT_DIR` is empty, ask the user for it.

**Optional flags**:
- `--benchmark` — After the pipeline completes, automatically run `benchmark_runner.py`
  and generate a JSON report at `logs/benchmark_report.json`.

**Variable**: `${CLAUDE_SKILL_DIR}` is set by Claude Code to the skill's installed directory.

**Argument parsing** (run once at the top):
```bash
# Parse $ARGUMENTS: project_dir [flags]
# e.g. "/path/to/project" or "/path/to/project --benchmark"
PROJECT_DIR="${ARGUMENTS%%--*}"
PROJECT_DIR="$(echo "$PROJECT_DIR" | xargs)"  # trim trailing space
RUN_BENCHMARK=""
if echo "$ARGUMENTS" | grep -q "\-\-benchmark"; then
    RUN_BENCHMARK="1"
fi
```

---

## Step 0: Initialization

Run the initialization script:

```bash
PY_INIT="${PYTHON_EXE:-python}"
cd "$PROJECT_DIR" && "$PY_INIT" "${CLAUDE_SKILL_DIR}/core/init.py" "$PROJECT_DIR"
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh"
```

Read the output to determine: new project or resuming. If resuming, skip stages in `stages_completed`.

### Stale-Stage Recovery (resume only)

When resuming, if a stage is STARTED but not COMPLETE, the pipeline may have been
interrupted or crashed. Before re-dispatching that stage, check if the output files
already exist by looking for completion markers (`.veriflow/done_<stage>*`):

```bash
cd "$PROJECT_DIR"
# For spec_golden: check if both outputs exist and marker is present
if [ -f ".veriflow/done_spec_golden" ] && [ -f "workspace/docs/spec.json" ] && [ -f "workspace/docs/golden_model.py" ]; then
    echo "[RECOVERY] spec_golden outputs exist — running hook to mark complete"
    python3 "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "spec_golden" \
        --hook='{"all":[{"exists":"workspace/docs/spec.json"},{"exists":"workspace/docs/golden_model.py"}]}'
fi

# For codegen: check if ALL module .v files and TB files exist
if ls .veriflow/done_codegen_* >/dev/null 2>&1; then
    echo "[RECOVERY] codegen completion markers found — verifying outputs"
    python3 "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "codegen" \
        --hook='{"all":[{"glob":"workspace/rtl/*.v","min":1},{"any":[{"glob":"workspace/tb/test_*.py","min":1},{"glob":"workspace/tb/tb_*.v","min":1}]}]}' \
        --journal-outputs="workspace/rtl/*.v, workspace/tb/test_*.py, workspace/tb/tb_*.v" \
        --journal-notes="Recovered from interrupted codegen via completion markers"
fi
```

If the hook passes, the stage is marked COMPLETE and the pipeline advances. If it
fails, stale markers are cleaned up and the stage is re-dispatched normally:

```bash
rm -f .veriflow/done_codegen_* .veriflow/done_spec_golden .veriflow/done_tb_gen
```

### Permission Check (sub-agent tools)

Sub-agents cannot interact with the user — any permission prompt will hang the pipeline.
Check that the following tools are pre-approved in the project's `.claude/settings.json`:

> **Heads-up — the allow-list below is the minimum.** Sub-agents also run shell
> commands like `source`, `cd`, `iverilog`, `vvp`, `yosys`, `mkdir`, `ls`,
> `xargs`. Those are NOT auto-added here because the right scope is environment-
> dependent. Two ways to keep the pipeline from hanging on a permission prompt:
>
> 1. Launch Claude Code with `--permission-mode acceptEdits` (or rely on
>    `~/.claude/settings.json` setting `skipDangerousModePermissionPrompt: true`).
> 2. Or, extend `.claude/settings.json` allow-list with the patterns above
>    (e.g. `"Bash(source*)"`, `"Bash(iverilog*)"`, `"Bash(yosys*)"`).
>
> If Stage 2/3/4 hangs silently, the cause is almost always one of these
> unlisted commands waiting on an invisible permission dialog.

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
- `$PROJECT_DIR/requirement.md` (required)
- `$PROJECT_DIR/constraints.md` (optional)
- `$PROJECT_DIR/design_intent.md` (optional)
- `$PROJECT_DIR/context/*.md` files

Check each category below. If input files already answer it → note "confirmed" and skip. Only ask about what's missing or ambiguous. Use AskUserQuestion with up to 4 questions per call.

**A.** Functional clarity: module functionality, interface protocol, data format, FSM behavior, clock domain crossings
**B.** Constraint clarity: clock frequency, target platform, area/power budget, reset strategy, IO standards
**C.** Design intent: architecture style, module partitioning, interface preferences, IP reuse, key decisions
**D.** Algorithm & protocol: algorithm reference, pseudocode, key formulas, test vectors
**E.** Timing completeness: cycle-level behavior, latency, throughput, interface timing, reset recovery, backpressure
**F.** Domain knowledge: design domain, standard reference, prerequisite concepts, test vectors
**G.** Information completeness: implicit assumptions, missing scenarios

After resolved, write `$PROJECT_DIR/.veriflow/clarifications.md` with all answers.

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
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "<STAGE>" --start
```

**Execute:** dispatch agents (Stages 1/2/4) or run inline (Stage 3)

**Post-stage:**
```bash
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "<STAGE>" --hook="<HOOK_CMD>" --journal-outputs="<FILES>" --journal-notes="<NOTES>"
```
Then: `TaskUpdate` mark the stage task as completed.

---


## Stage 1: spec_golden

**Produces**: `workspace/docs/spec.json` + `workspace/docs/golden_model.py`.
**Full execution bash**: Read `stage1_spec_golden.md` when entering this stage.

1. Record start: `state.py "$PROJECT_DIR" "spec_golden" --start`.
2. **Pre-stage: Web Research** (main session): read `requirement.md`; if algorithm/spec/vectors already covered, write a note to `.veriflow/web_research.md` and skip WebSearch; else WebSearch, store in `web_research.md`.
3. **Dispatch vf-spec-golden** (single agent): prompt includes PROJECT_DIR, TEMPLATES_DIR (path to `${CLAUDE_SKILL_DIR}/templates`), INPUT_FILES paths, CLARIFICATIONS. **DO NOT embed template content** or input file content - the agent reads files itself. It writes spec.json first, then aligns golden_model.py trace cycles using its `cycle_timing`.
4. Golden self-check + timing contract check + streaming-fill check (bash in `stage1_spec_golden.md`).
5. Mark complete:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "spec_golden" --hook='{"all":[{"exists":"workspace/docs/spec.json"},{"exists":"workspace/docs/golden_model.py"}]}'
```

---

## Stage 2: codegen

**Consumes**: spec.json + golden_model.py. **Produces**: `workspace/rtl/*.v` + `workspace/tb/test_*.py` (cocotb) or `tb_*.v` (Verilog).
**Full execution bash**: Read `stage2_codegen.md` when entering this stage.

1. Record start: `state.py "$PROJECT_DIR" "codegen" --start`.
2. Read spec.json + golden_model.py + `coding_style.md` inline into prompts (parallel Read calls).
3. **AI Assembly**: dispatch one **vf-coder** per module (K=3 candidates default, `candidate_selector.py` picks best). **TB Generation**: dispatch **vf-tb-gen** (cocotb + Verilog TB). Full dispatch + candidate-selection bash in `stage2_codegen.md`.
4. Mark complete:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "codegen" --hook='{"all":[{"glob":"workspace/rtl/*.v","min":1},{"any":[{"glob":"workspace/tb/test_*.py","min":1},{"glob":"workspace/tb/tb_*.v","min":1}]}]}'
```

---

## Stage 3: verify_fix (inline - runs in main session)

**Consumes**: RTL + testbench. **Produces**: `logs/sim.log` (PASS).
**Full execution bash**: Read `stage3_verify_fix.md` when entering this stage.

1. Record start: `state.py "$PROJECT_DIR" "verify_fix" --start`.
2. **cocotb FIRST** (if available): per-cycle VPI compare + FIRST DIVERGENCE. Verilog TB second / fallback. Golden self-check -> run simulation -> coverage check. Full bash in `stage3_verify_fix.md`.
3. Mark complete:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" --hook='{"contains":"logs/sim.log","text":"ALL TESTS PASSED"}'
```

**On FAIL**: Read `error_recovery.md` (data collection, bug classification, root-cause, 3-retry budget per stage then escalate user). Execution bash (timing_diagnostic, expected_trace, prev_failure summary) in `stage3_verify_fix.md`.

---

## Stage 4: lint_synth

**Consumes**: verified RTL. **Produces**: `logs/lint.log` + `workspace/synth/synth_report.txt`.
**Full execution bash**: Read `stage4_lint_synth.md` when entering this stage.

1. Record start: `state.py "$PROJECT_DIR" "lint_synth" --start`.
2. Dispatch **vf-linter** + **vf-synthesizer** in parallel (single message). Full bash in `stage4_lint_synth.md`.
3. Formal equivalence check (`yosys_equiv.py`) + optional formal property proving + KB auto-record.
4. Mark complete:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "lint_synth" --hook='{"all":[{"exists":"logs/lint.log"},{"exists":"workspace/synth/synth_report.txt"}]}'
```
5. Optional: `benchmark_runner.py --report "$PROJECT_DIR"` generates `pipeline_report.md` (or pass `--benchmark` to `/vf-rtl`).

---

## Design Rules Summary

See `${CLAUDE_SKILL_DIR}/design_rules.md` for full rules.

- Synchronous active-high reset named `rst`
- Port naming: `_n` suffix for active-low, `_i`/`_o` for direction
- **Verilog-2005 only** — NO SystemVerilog
- Interface Lock: port names, handshake protocols, and module hierarchy are frozen after Stage 1

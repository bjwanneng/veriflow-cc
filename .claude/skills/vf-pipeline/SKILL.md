---
name: vf-pipeline
description: Use this skill to start or resume the VeriFlow RTL hardware design pipeline (architect to synth). Trigger this when the user asks to "run the RTL flow", "design hardware", or "start the pipeline". Pass the project directory path as the argument.
disable-model-invocation: true
---

# RTL Pipeline Orchestrator

You orchestrate the RTL pipeline sequentially through 8 stages. For each stage you must invoke the sub-agent, then use Bash to verify the output files.

Project directory path: `$ARGUMENTS`

If `$ARGUMENTS` is empty, ask the user for it.

---

## Step 0: Initialization (Mandatory)

Execute immediately without emitting text plans:

```bash
PROJECT_DIR="$ARGUMENTS"
ls -la "$PROJECT_DIR/requirement.md" || { echo "ERROR: requirement.md not found"; exit 1; }
cd "$PROJECT_DIR" && mkdir -p workspace/docs workspace/rtl workspace/tb workspace/sim workspace/synth .veriflow
```

---

## Execution Loop

For each stage, execute these 4 strict steps:
1. **Agent Call**: Invoke sub-agent for the stage.
2. **Hook**: Use Bash to verify expected output files.
3. **State Save (If Hook Passes)**: Run state update script.
4. **Fix (If Hook Fails)**: Call `vf-debugger` to fix, then rerun stage.

**State Update Command (Step 3)**:
```bash
python "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "STAGE_NAME"
```
*(Replace 'STAGE_NAME' with architect, microarch, etc.)*
`state.py` is co-located with SKILL.md in the skill directory. When installed globally it lives at `~/.claude/skills/vf-pipeline/state.py`.

---

## Stage 1: architect
**1 (Agent)**: `subagent_type`: `vf-architect`, `prompt`: `Execute architect stage for $ARGUMENTS. Read requirement.md, generate workspace/docs/spec.json.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/docs/spec.json" && grep -q "module_name" "$ARGUMENTS/workspace/docs/spec.json" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 2: microarch
**1 (Agent)**: `subagent_type`: `vf-microarch`, `prompt`: `Execute microarch stage for $ARGUMENTS. Read spec.json & requirement.md, generate workspace/docs/micro_arch.md.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/docs/micro_arch.md" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 3: timing
**1 (Agent)**: `subagent_type`: `vf-timing`, `prompt`: `Execute timing stage for $ARGUMENTS. Read spec.json & micro_arch.md, generate workspace/docs/timing_model.yaml and workspace/tb/tb_*.v.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/docs/timing_model.yaml" && ls "$ARGUMENTS/workspace/tb/"tb_*.v >/dev/null 2>&1 && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 4: coder
**1 (Agent)**: `subagent_type`: `vf-coder`, `prompt`: `Execute coder stage for $ARGUMENTS. Read specs and generate workspace/rtl/*.v.`
**2 (Hook)**:
```bash
v_files=$(ls "$ARGUMENTS/workspace/rtl/"*.v 2>/dev/null)
if [ -n "$v_files" ]; then
    for f in $v_files; do grep -q "endmodule" "$f" 2>/dev/null || echo "[HOOK] MISSING endmodule in $(basename $f)"; done
    echo "[HOOK] PASS"
else
    echo "[HOOK] FAIL"
fi
```

## Stage 5: skill_d
**1 (Agent)**: `subagent_type`: `vf-skill-d`, `prompt`: `Execute skill_d stage for $ARGUMENTS. Verify workspace/rtl/*.v code quality, generate workspace/docs/static_report.json.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/docs/static_report.json" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 6: lint
**1 (Agent)**: `subagent_type`: `vf-lint`, `prompt`: `Execute lint stage for $ARGUMENTS. Check workspace/rtl/*.v syntax using iverilog.`
**2 (Hook)**:
```bash
cd "$ARGUMENTS" && iverilog -Wall -tnull workspace/rtl/*.v 2>&1 && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 7: sim
**1 (Agent)**: `subagent_type`: `vf-sim`, `prompt`: `Execute sim stage for $ARGUMENTS. Compile and test workspace/rtl/*.v with workspace/tb/tb_*.v.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/sim/tb.vvp" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

## Stage 8: synth
**1 (Agent)**: `subagent_type`: `vf-synth`, `prompt`: `Execute synth stage for $ARGUMENTS. Synthesize using yosys, generate workspace/docs/synth_report.txt.`
**2 (Hook)**:
```bash
test -f "$ARGUMENTS/workspace/docs/synth_report.txt" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

---

## Error Recovery (Hook Failures)
1. **1st Fail**: Call `Agent` -> `vf-debugger` to fix, retry stage.
2. **2nd Fail**: Rollback to earlier stage and rerun sequentially (e.g. syntax->coder, logic->microarch).
3. **3rd Fail**: STOP and notify user.

## Strict Constraints
1. NO chat without tool invocation.
2. NO skipping stages (Must go 1->8 sequentially).
3. NO trusting agent text output without Bash verification.

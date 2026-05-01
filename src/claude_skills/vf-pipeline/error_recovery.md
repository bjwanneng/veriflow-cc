# Error Recovery Procedure

This file is loaded by the main session ONLY when simulation fails.
Read this file with the Read tool, then follow the steps below.

---

## Step 0: Data Collection + Bug Type Classification (MANDATORY)

Before forming ANY root cause hypothesis, collect objective diagnostic data.

### 0a. Collect data

1. Read `logs/sim.log` — extract all `[FAIL]` lines with cycle numbers

2. Extract VCD path and top module:
```bash
source "$PROJECT_DIR/.veriflow/eda_env.sh"
cd "$PROJECT_DIR"
TOP_MODULE=$($PYTHON_EXE -c "
import json
spec = json.load(open('workspace/docs/spec.json'))
for m in spec.get('modules', []):
    if m.get('module_type') == 'top':
        print(m['module_name']); break
")
VCD_FILE=$(ls workspace/sim/*.vcd 2>/dev/null | head -1)
```

3. Run vcd2table golden model diff:
```bash
if [ -f workspace/docs/golden_model.py ] && [ -n "$VCD_FILE" ] && [ -f "$VCD_FILE" ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/vcd2table.py" \
        --vcd "$VCD_FILE" \
        --golden-model workspace/docs/golden_model.py \
        --module $TOP_MODULE 2>&1 | tee logs/wave_diff.txt
elif [ -n "$VCD_FILE" ] && [ -f "$VCD_FILE" ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/vcd2table.py" \
        --vcd "$VCD_FILE" \
        --module $TOP_MODULE 2>&1 | tee logs/wave_table.txt
else
    echo "[VERIFY] No VCD file — relying on sim.log only."
fi
```

4. Read the diff/table output — identify first divergence cycle and signal

### 0b. Classify bug type

| Type | Symptom | Direction |
|------|---------|-----------|
| **A. Computation** | Output wrong (not zero) or zero when expected non-zero | Trace datapath: formula, condition, index |
| **B. Timing** | Correct value but wrong cycle | Check pipeline alignment, register stages |
| **C. Protocol** | valid/ready timing violates handshake spec | Check handshake protocol, FSM transitions |
| **D. Initialization** | First output offset by constant | Check register init values, algorithm IV loading |

**Anti-pattern warning**: Do NOT assume timing issues without data.
- Zero or constant at divergence → Type A or D (logic/init), NOT timing.
- Correct value, wrong cycle → Type B
- Most bugs in single-clock-domain designs are Type A or D.

---

## Step 1: Diagnose

- Read the error output from the failed stage
- Read the relevant RTL files from `workspace/rtl/`
- Reference `bug_patterns.md` for a catalog of known bug patterns

---

## Step 1.5: Structured Root Cause Analysis (MANDATORY)

Before modifying ANY file, complete the analysis and write to `stage_journal.md`.

### 5-point root cause analysis

1. **Error location**: Which `[FAIL]` line? Which cycle? Which signal?
2. **Signal trace**: Which module drives it? Which `always` block?
3. **Root cause hypothesis**: Exact RTL line that is wrong.
4. **Minimal fix plan**: File, lines, exact change.
5. **Impact scope**: Which other signals/modules affected?

If you cannot form a hypothesis, STOP and ask the user. Do NOT guess-and-fix.

---

## Step 2: Fix

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
- Make minimal changes, fix one error at a time
- **Debug budget**: 3 fix-and-retry cycles max, then STOP and ask user

After fixing, re-run simulation to verify.

---

## Step 3: Log recovery to journal

```bash
printf "\n### Recovery: <stage_name>\n**Timestamp**: $(date -Iseconds)\n**Attempt**: <N>\n**Error type**: <syntax|logic|timing>\n**Fix summary**: <description>\n**Result**: <PASS|FAIL|PENDING>\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

---

## Retry Policy

1. **1st fail**: Fix RTL, retry simulation
2. **2nd fail**: Rollback to codegen and re-run from Stage 2
3. **3rd fail**: STOP and notify user

Rollback command:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" --reset codegen
```

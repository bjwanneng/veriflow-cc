# Stage 3: verify_fix - execution detail

Loaded by SKILL.md when entering Stage 3. Full execution bash; SKILL.md holds the compact dispatch entry.

---

## Stage 3: verify_fix (inline — runs in main session)

**IMPORTANT**: This stage runs inline because error recovery needs main session context for Edit tool.

**Verification order (project policy — do NOT reverse):**
1. cocotb runs FIRST when `cocotb-config` is on PATH — it is the primary
   verification path. The per-cycle VPI comparison and FIRST DIVERGENCE
   report are the main diagnostic signal for error recovery.
2. The pure-Verilog testbench runs SECOND as a fallback / cross-check.
   When cocotb is unavailable, it is the only path.

Pre-stage:
```bash
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh" && $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" --start
```

### Golden Model Self-Check (BEFORE simulation)

If golden_model.py exists, verify it passes its own test vectors first.
This catches golden model bugs BEFORE wasting time on RTL debugging.

```bash
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh"
cd "$PROJECT_DIR"
if [ -f workspace/docs/golden_model.py ]; then
    # Redirect to the log (portable sh — no tee/PIPESTATUS); $? is the runner's
    # own exit code, and the file stays on disk for the orchestrator to read.
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/runners/iverilog_runner.py" \
        --golden-check workspace/docs/golden_model.py > logs/golden_selfcheck.log 2>&1
    GOLDEN_RC=$?
    cat logs/golden_selfcheck.log  # echo to console for visibility
    if [ "$GOLDEN_RC" -ne 0 ]; then
        echo "[GOLDEN] Self-check FAILED — the reference model has bugs."
        echo "[GOLDEN] Fix golden_model.py FIRST. The problem is NOT in the RTL."
        # Do NOT consume retry budget — this is a golden model issue.
        # Mark stage failed AND abort so the main session is forced to fix
        # golden_model.py before any RTL debugging.
        $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" --fail
        echo "[GOLDEN] verify_fix marked failed. Main session: fix golden_model.py, then re-run /vf-rtl."
        exit 1
    fi
fi
```

### Cocotb per-cycle verification (if cocotb available)

Before running Verilog simulation, run cocotb with per-cycle internal signal
comparison. This is the PRIMARY debugging tool — it finds the FIRST divergence
point automatically, instead of only checking final outputs.

Uses `cocotb_runner.py` (no Makefile required) — it handles build, test,
VCD capture, and JSON result output via `cocotb_tools.runner.Icarus`.

```bash
if command -v cocotb-config &>/dev/null; then
    TOP_MODULE=$($PYTHON_EXE -c "
import json
for m in json.load(open('workspace/docs/spec.json')).get('modules', []):
    if m.get('module_type') == 'top': print(m['module_name']); break
")
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/runners/cocotb_runner.py" \
        --rtl-dir workspace/rtl \
        --tb-dir workspace/tb \
        --module $TOP_MODULE \
        --build-dir workspace/sim_cocotb \
        --results-file logs/cocotb_results.xml \
        --verbose 2>&1 | tee logs/cocotb.log
    # cocotb_runner.py exits 0=pass, 1=fail, 2=env error
    # JSON summary is on stdout (last line), details in cocotb.log
    if grep -q "FIRST DIVERGENCE" logs/cocotb.log; then
        echo "[COCOTB] Internal signal mismatch found — see cocotb.log for details"
        # Extract first divergence info — this is the PRIMARY diagnostic
        # for error_recovery.md. Do NOT guess the root cause.
    fi
fi
```

If cocotb is not available, proceed with Verilog simulation as before.

### Parameter consistency check (before simulation)

When the DUT has Verilog parameters (e.g., `DATA_WIDTH`, `IMG_WIDTH`, `DEPTH`)
that may differ from test vector dimensions, verify that the cocotb testbench
has set `VERILOG_PARAMS` correctly. This catches the "0 outputs" failure mode
where the DUT compiles with wrong dimensions.

```bash
# Check if DUT has parameters and test file has VERILOG_PARAMS
cd "$PROJECT_DIR"
HAS_PARAMS=$($PYTHON_EXE -c "
import json
spec = json.load(open('workspace/docs/spec.json'))
params = []
for m in spec.get('modules', []):
    params.extend(p['name'] for p in m.get('parameters', []))
print(' '.join(params) if params else '')
")
if [ -n "$HAS_PARAMS" ]; then
    # DUT has parameters — check that cocotb test file defines VERILOG_PARAMS
    TB_FILE=$(ls workspace/tb/test_*.py 2>/dev/null | head -1)
    if [ -n "$TB_FILE" ] && ! grep -q "VERILOG_PARAMS" "$TB_FILE"; then
        echo "[WARN] DUT has parameters ($HAS_PARAMS) but cocotb test file has no VERILOG_PARAMS."
        echo "[WARN] If test vector dimensions differ from default parameters, cocotb will get 0 outputs."
        echo "[WARN] Add VERILOG_PARAMS = {\"PARAM_NAME\": value, ...} to the cocotb test file."
    fi
fi
```

### Run simulation

```bash
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh"
cd "$PROJECT_DIR"
TOP_MODULE=$($PYTHON_EXE -c "
import json
for m in json.load(open('workspace/docs/spec.json')).get('modules', []):
    if m.get('module_type') == 'top': print(m['module_name']); break
")
VERILOG_TB=$(ls workspace/tb/tb_*.v 2>/dev/null | head -1)
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/runners/iverilog_runner.py" \
    --module $TOP_MODULE --rtl-dir workspace/rtl --tb-file "$VERILOG_TB" \
    --build-dir workspace/sim --verbose \
    --golden-model workspace/docs/golden_model.py \
    2>&1 | tee logs/sim.log
```

### If PASS

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" --hook='{"contains":"logs/sim.log","text":"ALL TESTS PASSED"}' --journal-outputs="logs/sim.log" --journal-notes="Simulation passed"
```

### Coverage check (soft gate — warn but don't fail in Phase 1)

Parse the simulation result for coverage metrics. If the testbench exercised
fewer test vectors than golden_model.py provides, flag a warning:

```bash
COV=$($PYTHON_EXE -c "
import json, pathlib, re, sys, importlib.util
# The runners print a JSON summary as their last stdout line, tee'd into the
# sim log. Parse exercised = pass_count + failed from whichever log exists.
exercised = None
for log_name in ('logs/sim.log', 'logs/cocotb.log'):
    p = pathlib.Path(log_name)
    if not p.exists():
        continue
    for line in reversed(p.read_text(errors='ignore').splitlines()):
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 'passed' in d or 'pass_count' in d or 'failed' in d:
                exercised = (d.get('pass_count', d.get('passed', 0))
                             + d.get('failed', d.get('fail_count', 0)))
                break
    if exercised is not None:
        break
# Total = number of TEST_VECTORS in golden_model.py
total = 0
gm = pathlib.Path('workspace/docs/golden_model.py')
if gm.exists():
    try:
        spec = importlib.util.spec_from_file_location('_gm', gm)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        total = len(getattr(mod, 'TEST_VECTORS', []))
    except Exception:
        pass
if exercised is not None and total > 0:
    print(f'{exercised}/{total}={exercised/total:.0%}')
else:
    print('N/A')
")
echo "[COVERAGE] Test vector coverage: $COV"
if [ "$COV" != "N/A" ]; then
    RATIO=$(echo "$COV" | grep -oE '[0-9]+%' | tr -d '%' || echo "100")
    if [ "$RATIO" -lt 80 ] 2>/dev/null; then
        echo "[WARN] Coverage below 80% — testbench may miss corner cases"
    fi
fi
```

### Functional coverage loop (coverage-driven verification)

After a PASSING simulation, score functional coverage (FSM states + handshake
combos exercised) and, if below threshold, generate directed tests and re-sim
once. Bounded to one extra round. Skipped automatically when the spec declares
no cover goals (returns ratio N/A).
```bash
cd "$PROJECT_DIR"
COV_FILE=$(ls workspace/sim_cocotb/coverage.json workspace/sim/coverage.json 2>/dev/null | head -1)
MIN_FUNC=$($PYTHON_EXE -c "
import json
s = json.load(open('workspace/docs/spec.json'))
print(s.get('constraints',{}).get('verification',{}).get('min_functional_coverage', 0.85))
")
if [ -n "$COV_FILE" ]; then
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/analysis/coverage_analyzer.py" \
        --coverage "$COV_FILE" --spec workspace/docs/spec.json --module "$TOP_MODULE" \
        > logs/functional_coverage.json
    FRATIO=$($PYTHON_EXE -c "import json;print(json.load(open('logs/functional_coverage.json'))['ratio'])")
    echo "[FCOV] Functional coverage: $FRATIO (min $MIN_FUNC)"
    if [ "$FRATIO" != "None" ] && [ "$(echo "$FRATIO < $MIN_FUNC" | bc -l 2>/dev/null || echo 0)" = "1" ]; then
        echo "[FCOV] Below threshold — re-dispatch vf-tb-gen with the coverage directive below, then re-run Stage 3 sim ONCE."
        $PYTHON_EXE -c "import json;print(json.load(open('logs/functional_coverage.json'))['directives'])"
    fi
fi
```
If the directive fired: read the uncovered goals, add directed `TEST_VECTORS`
that hit them (or re-dispatch vf-tb-gen with the directive), re-run the sim,
then proceed. Do not loop more than once.

TaskUpdate complete. Go to Stage 4.

### If FAIL

1. **Run timing diagnostic + expected trace** (BEFORE manual analysis):
```bash
[ -f "$PROJECT_DIR/.veriflow/eda_env.sh" ] && source "$PROJECT_DIR/.veriflow/eda_env.sh"
LOG_FILE=$(test -f logs/cocotb.log && echo logs/cocotb.log || echo logs/sim.log)
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/analysis/timing_diagnostic.py" \
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
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/analysis/expected_trace_gen.py" \
    --golden workspace/docs/golden_model.py \
    --cycles "$EXPECTED_TRACE_CYCLES" \
    --skip-cycles 1 \
    --output logs/expected_trace_golden.md \
    2>&1 | tee logs/expected_trace_gen.log
```

   Post-check: verify expected trace was generated:
```bash
if [ ! -s "$PROJECT_DIR/logs/expected_trace_golden.md" ]; then
    echo "[WARN] Expected trace not generated — error recovery will lack per-cycle reference"
fi
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
   **5-point root cause analysis** → write to `logs/stage_journal.md`

4. **Fix RTL** using Edit tool

5. **Record this failure signature** before re-running (lets the loop detector
   see repeats):
```bash
SIG=$($PYTHON_EXE -c "
import json, pathlib
p = pathlib.Path('logs/timing_diagnostic.json')
if p.exists():
    d = json.loads(p.read_text())
    div = d.get('divergence', {})
    cls = d.get('bug_class', 'A')
    sig = div.get('signal', '?')
    # Structured signature: (classification, signal_root, cycle_offset)
    # Robust to line-number changes after fix attempts.
    sig_root = sig.rsplit('.', 1)[-1].split('[')[0]
    offset = d.get('timing_offset_cycles', 0)
    print(f\"({cls!r}, {sig_root!r}, {offset})\")
else:
    print('no-diagnostic')
")
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" \
    --fail --error-sig="$SIG"
```

5b. **Build the failure-summary file** for the next vf-coder retry.
This MUST be a **prescriptive fix directive** — not just a description of what
went wrong. The main session MUST diagnose the root cause and write concrete
fix steps (file, line number, exact code change) before rolling back to codegen.

**Format** (vf-coder expects this exact structure):
```
PREV_FAILURE:
  ROOT CAUSE: <one-sentence diagnosis referencing specific file and line>
  BUG CLASS: <timing_diagnostic bug_class>
  DIVERGENCE: cycle <N>, signal <name>, expected=<hex>, actual=<hex>
  FIX (mandatory — do NOT explore alternatives):
  1. <file:line> — <exact change description>
  2. <file:line> — <exact change description>
  CONSTRAINTS: <any constraints on the fix, e.g. "only modify FSM logic">
```

The main session generates this by:
1. Running the diagnostic script below to extract raw divergence data
2. Reading the RTL file(s) at the divergence point to identify the root cause
3. Writing the concrete FIX steps — this is the main session's diagnosis, not
   the agent's job. The agent should ONLY execute.

```bash
$PYTHON_EXE - <<'PY' 2>&1 | tee logs/prev_failure_summary_raw.md
import json, pathlib

diag = pathlib.Path("logs/timing_diagnostic.json")
expected = pathlib.Path("logs/expected_trace_golden.md")

print("# Raw failure data (main session: add ROOT CAUSE and FIX steps below)")
print()

if not diag.exists():
    print("(no logs/timing_diagnostic.json — `timing_diagnostic.py` did not produce a report)")
else:
    d = json.loads(diag.read_text())
    div = d.get("divergence", {}) or {}
    print(f"- **First divergence cycle**: {div.get('cycle', '?')}")
    print(f"- **Signal**: `{div.get('signal', '?')}`")
    print(f"- **Expected**: `{div.get('expected', '?')}`")
    print(f"- **Actual**: `{div.get('actual', '?')}`")
    print(f"- **Bug class**: {d.get('bug_class', '?')}  ({d.get('confidence', '?')})")
    fix = d.get("fix_suggestion")
    if fix:
        print()
        print("## Suggested fix direction (from timing_diagnostic.py)")
        if isinstance(fix, dict):
            for k, v in fix.items():
                print(f"- **{k}**: {v}")
        else:  # fix_suggestion is a multi-line text block
            print(fix)

if expected.exists():
    print()
    print("## Expected trace (first 8 cycles, from golden_model.py)")
    lines = expected.read_text().splitlines()
    body = [ln for ln in lines if ln.strip() and not ln.startswith("##")][:10]
    print("\n".join(body))

print()
print("---")
print("## MAIN SESSION: Fill in ROOT CAUSE and FIX below before passing to vf-coder")
print()
print("ROOT CAUSE: <diagnose by reading the RTL at the divergence point>")
print("FIX:")
print("1. <file>:<line> — <specific change>")
print("2. <file>:<line> — <specific change>")
PY
```

**CRITICAL**: The raw data above is NOT sufficient as PREV_FAILURE. The main
session MUST read the RTL file(s), identify the root cause, and write concrete
FIX steps in the `logs/prev_failure_summary.md` file before any rollback to
codegen. The filled-in `prev_failure_summary.md` is what gets passed as
PREV_FAILURE to vf-coder. If the main session cannot determine the root cause,
ask the user rather than rolling back with a vague description.

6. **Check whether we are looping on the same bug** BEFORE consuming another
   retry slot. If the same divergence signature has fired 2+ times, fixing
   RTL is not converging — rollback to codegen instead of burning more attempts:
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "verify_fix" \
    --check-loop="$SIG"
LOOP_STATUS=$?
if [ "$LOOP_STATUS" -eq 2 ]; then
    echo "[STAGE3] Detected fix-loop on '$SIG' — rolling back to codegen."
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" --reset codegen
    # Main session: BEFORE re-dispatching Stage 2, read the RTL at the
    # divergence point, diagnose root cause, write concrete FIX steps into
    # logs/prev_failure_summary.md. Then pass it as PREV_FAILURE — the agent
    # should ONLY execute the fix, not explore alternatives.
fi
```

7. **Re-run simulation** (go back to "Run simulation" above)

8. **Retry budget**: 3 attempts total
   - 1st fail: fix RTL, retry
   - 2nd fail: `state.py --reset codegen`, restart from Stage 2
   - 3rd fail: STOP, notify user
   - At ANY attempt: if step 6's loop detector returns 2, jump straight to
     `state.py --reset codegen` and re-run Stage 2 without waiting for the
     3rd attempt.

---


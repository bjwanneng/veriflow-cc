# Stage 1: spec_golden - execution detail

Loaded by SKILL.md when entering Stage 1. Full execution bash; SKILL.md holds the compact dispatch entry.

---

## Stage 1: spec_golden

**Stage timing** — record start (before any stage work, so `duration_s` is captured):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "spec_golden" --start
```

### Pre-stage: Web Research

**Read requirement.md** (run in main session) to decide if WebSearch is needed.
Do NOT read templates or other input files — the agent will read them itself.

**Web Research** (run in main session, only if needed):

After reading requirement.md, judge whether WebSearch is needed:
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

**Build INPUT_FILES list** (paths only, no content):
```
INPUT_FILES:
- $PROJECT_DIR/requirement.md
- $PROJECT_DIR/constraints.md (if exists)
- $PROJECT_DIR/design_intent.md (if exists)
- $PROJECT_DIR/context/*.md (if any)
- $PROJECT_DIR/.veriflow/clarifications.md
- $PROJECT_DIR/.veriflow/web_research.md (if exists)
```

**Run vf-spec-golden** (single Agent call):

- **vf-spec-golden** (subagent_type: vf-spec-golden)
  - Prompt includes: PROJECT_DIR, TEMPLATES_DIR (path to `${CLAUDE_SKILL_DIR}/templates`),
    INPUT_FILES (list of paths), CLARIFICATIONS path
  - DO NOT embed template content or input file content in the prompt.
  - The agent reads all files itself using its Read tool, then generates
    **both** spec.json and golden_model.py in one pass,
    with timing alignment done internally (it writes spec.json first, then uses
    its cycle_timing to align golden_model.py trace cycles).

After it returns:

1. Read `workspace/docs/spec.json` and `workspace/docs/golden_model.py` to verify.

**Golden model self-check** (pre-codegen gate — run FIRST to catch syntax errors):

Before proceeding to Stage 2, verify that golden_model.py passes its own test
vectors. This catches algorithmic and syntax bugs before RTL is generated.

```bash
cd "$PROJECT_DIR"
if [ -f workspace/docs/golden_model.py ]; then
    # Redirect to the log (portable sh — no tee/PIPESTATUS); the file stays on
    # disk for the orchestrator to read, and $? is the runner's own exit code.
    $PYTHON_EXE "${CLAUDE_SKILL_DIR}/runners/iverilog_runner.py" \
        --golden-check workspace/docs/golden_model.py > logs/golden_selfcheck.log 2>&1
    GOLDEN_RC=$?
    cat logs/golden_selfcheck.log  # echo to console for visibility
    if [ "$GOLDEN_RC" -ne 0 ]; then
        echo "[GOLDEN] Self-check FAILED — fix golden_model.py before proceeding."
        $PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "spec_golden" --fail
        echo "[GOLDEN] Stage 1 marked failed; Stage 2 will not run. Main session: fix golden_model.py and re-run Stage 1."
        exit 1
    fi
fi
```

**Timing contract check** (pre-verification, before codegen):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/analysis/timing_contract_checker.py" \
    --spec workspace/docs/spec.json \
    --golden workspace/docs/golden_model.py \
    --output logs/timing_check.json
```
If this reports errors, **auto-fix first** — the checker can correct most common timing contract mistakes (registered→combinational delays, missing handshake fields, latency mismatches):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/analysis/timing_contract_checker.py" \
    --fix \
    --spec workspace/docs/spec.json \
    --golden workspace/docs/golden_model.py \
    --output logs/timing_check.json
```
Re-run the checker after `--fix` to confirm all errors are resolved. Only if errors remain after auto-fix, review `logs/timing_check.json` and manually fix spec.json or golden_model.py. Errors indicate timing contradictions that will cause RTL bugs.


**Streaming fill latency check** (pre-codegen gate):

If any module in spec.json has a non-zero `pipeline_delay_cycles` but is missing
`streaming_fill_latency_cycles`, verify whether the module has a fill/buffering
phase (line buffer, FIFO, shift-register window). If it does, the orchestrator
MUST ensure that downstream delay-matching paths use `total_latency_cycles`
(= `pipeline_delay_cycles + streaming_fill_latency_cycles`), not just the raw
`pipeline_delay_cycles`.

```bash
$PYTHON_EXE -c "
import json
spec = json.load(open('workspace/docs/spec.json'))
for m in spec.get('modules', []):
    tc = m.get('timing_contract', {})
    pd = tc.get('pipeline_delay_cycles', 0)
    sf = tc.get('streaming_fill_latency_cycles')
    name = m.get('module_name', '')
    if sf is None:
        print(f'[INFO] {name}: pipeline_delay_cycles={pd}, no streaming_fill_latency_cycles declared')
    else:
        print(f'[OK] {name}: pipeline_delay_cycles={pd}, streaming_fill={sf}')
    if sf is None and pd > 0:
        print(f'[CHECK] {name}: verify whether this module has a fill phase before first output. If yes, add streaming_fill_latency_cycles to its timing_contract.')
"
```
If any module has `pd > 0` and no `streaming_fill_latency_cycles`, the
orchestrator reviews its architecture to determine whether a fill phase exists.
Do NOT proceed to Stage 2 with shortcut/delay paths that ignore fill latency.



```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "spec_golden" --hook='{"all":[{"exists":"workspace/docs/spec.json"},{"exists":"workspace/docs/golden_model.py"}]}' --journal-outputs="workspace/docs/spec.json, workspace/docs/golden_model.py" --journal-notes="spec.json interface + golden_model.py behavior"
```
TaskUpdate complete.

---


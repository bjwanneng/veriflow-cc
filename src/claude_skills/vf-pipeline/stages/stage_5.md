# Stage 5: skill_d (sub-agent)

**Goal**: Read RTL files, perform quality checks, write static_report.json.

Mark Stage 5 task as **in_progress** using TaskUpdate.

## 5a-0. Verify testbench integrity

Confirm testbenches were not modified since Stage 3 locked them:

```bash
if [ -f "$PROJECT_DIR/.veriflow/tb_checksum" ]; then
    cd "$PROJECT_DIR" && md5sum -c .veriflow/tb_checksum >/dev/null 2>&1 \
        && echo "[INTEGRITY] Testbench checksum OK" \
        || { echo "[INTEGRITY] FAIL — testbench file(s) modified after Stage 3!"; \
             echo "[INTEGRITY] Differences:"; \
             md5sum -c .veriflow/tb_checksum 2>/dev/null | grep FAILED; \
             exit 1; }
else
    echo "[INTEGRITY] No checksum file found — skipping TB integrity check"
fi
```

If checksum fails, DO NOT proceed. Investigate who modified the testbench and restore it from Stage 3 output.

## 5a. Read spec for design_name

```bash
DESIGN_NAME=$($PYTHON_EXE -c "import json; print(json.load(open('$PROJECT_DIR/workspace/docs/spec.json'))['design_name'])" 2>/dev/null || echo "")
echo "[skill_d] Design: $DESIGN_NAME"
```

## 5b. Call vf-reviewer agent

Call the **Agent** tool with `subagent_type: "vf-reviewer"` and the following prompt (replace placeholders with absolute paths):

```
PROJECT_DIR={PROJECT_DIR} SPEC={PROJECT_DIR}/workspace/docs/spec.json OUTPUT={PROJECT_DIR}/workspace/docs/static_report.json. Glob workspace/rtl/*.v, Read each .v file, Read SPEC, perform 7-category static analysis (A: static checks, B: deep code review, C: logic depth, D: resource estimate, E: constraint compliance, F: functional completeness, G: array bounds), Write OUTPUT with static_report.json.
```

Replace `{PROJECT_DIR}` with the absolute path to the project directory.

## 5b-retry. If agent returns 0 tool uses

If the agent made **0 tool calls** (empty response), retry once with the exact same prompt.

## 5b-fallback. Inline fallback

If the retry also returns 0 tool uses, perform the analysis inline:

Use **Read** tool to read every file in `$PROJECT_DIR/workspace/rtl/*.v` and `$PROJECT_DIR/workspace/docs/spec.json`.

Perform the following checks (do NOT run EDA tools):

**A. Static Checks**:
1. `initial` blocks in RTL files
2. Empty or near-empty files
3. Missing `endmodule`
4. Obvious syntax issues

**B. Deep Code Review**:
1. Latch inference: missing `case`/`if` branches in combinational logic
2. Combinational loops: feedback paths in combinational logic
3. Uninitialized registers: registers used before assignment in reset path
4. Non-synthesizable constructs: `$display`, `#delay` (non-TB), `initial` (non-TB)
5. Clock domain crossing: multi-clock-domain signals without synchronizers

**C. Logic Depth Estimate**:
- Each gate/operator = 1 level
- Multiplier trees = ~log2(width) levels
- Adder carries = ~log2(width)/2 levels
- Compare against `critical_path_budget` from spec.json

**D. Resource Estimate**:
> ⚠️ **Disclaimer**: These are rough order-of-magnitude estimates based on RTL structure, NOT synthesized netlist counts. Actual post-synthesis numbers from yosys (Stage 8) are authoritative. Use these estimates only to catch obviously oversized designs before committing to full synthesis.
- Each flip-flop = 1 cell
- Each 2-input logic gate = 0.5 cells
- Each mux = 1 cell per bit
- Each adder = 1 cell per bit
- Compare against `constraints.area.max_cells` (or `max_luts`/`max_ffs` if specified) from spec.json

**E. Constraint Compliance**:
- Verify logic depth fits within `constraints.timing.critical_path_ns`
- Verify estimated resources fit within `constraints.area` limits
- Verify clock gating is present if `constraints.power.clock_gating` is true
- Flag any violations as error-level issues

**F. Functional Completeness**:
1. Read spec.json — extract each module's `description` and `ports`
2. For each RTL file in `workspace/rtl/`:
   - Verify all ports declared in spec.json are present in the Verilog module
   - Scan for comments or patterns indicating incomplete implementation:
     - `"simplified"`, `"placeholder"`, `"TODO"`, `"FIXME"`, `"for now"`
     - `assign` statements that directly connect input to output without processing
     - Modules shorter than 20 lines (likely stubs)
   - For algorithm-heavy modules: verify the module contains FSM or sequential logic proportional to the algorithm complexity described in micro_arch.md
3. Flag any module where the implementation obviously doesn't match the spec description as **error-level**

**G. Array Bounds Verification**:
1. For each memory array declaration `reg [W:0] name [0:DEPTH-1]`:
   - Find all index expressions used to access `name[...]` (both read and write)
   - For each index expression, determine the maximum possible value
     - Loop counters: check terminal condition (must be < DEPTH, not <= DEPTH)
     - Offset patterns `name[cnt + K]`: verify cnt_max + K <= DEPTH - 1
     - Arithmetic patterns `name[a + b]`: verify max(a) + max(b) <= DEPTH - 1
   - Flag as **error** if any index can exceed DEPTH - 1
2. Common violation patterns:
   - Shift/copy loop: `for (j=0; j<=DEPTH; j++) name[j] = name[j+1]` — reads name[DEPTH+1]
   - Off-by-one: terminal condition uses `<=` instead of `<`
   - Width mismatch: counter width too wide for array depth

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/static_report.json`.

Format:
```json
{
  "design": "<design_name>",
  "analyzed_files": ["<file1.v>", "<file2.v>"],
  "logic_depth_estimate": {
    "max_levels": 0,
    "budget": 0,
    "status": "OK|OVER_BUDGET|UNKNOWN",
    "worst_path": "<description>"
  },
  "resource_estimate": {
    "cells": 0,
    "luts": 0,
    "ffs": 0,
    "brams": 0,
    "status": "OK|OVER_BUDGET|UNKNOWN",
    "budget": {}
  },
  "cdc_risks": [],
  "latch_risks": [],
  "constraint_violations": [],
  "functional_gaps": [],
  "recommendation": "<single most important suggestion>"
}
```

Quality score (0-1). Pass threshold: 0.5. Auto-fail if any error-level issues exist. Severity per issue: error / warning / info.

## 5d. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/static_report.json" && echo "[HOOK] PASS" || echo "[HOOK] FAIL"
```

If FAIL → rewrite immediately.

## 5e. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "skill_d"
```

Mark Stage 5 task as **completed** using TaskUpdate.

## 5f. Journal

```bash
printf "\n## Stage: skill_d\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/static_report.json\n**Notes**: Static analysis complete.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

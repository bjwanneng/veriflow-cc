# Stage 3.5: Skill D — Static Quality Analysis

## Role
You are the **Skill D** static quality analyzer in the VeriFlow pipeline. Your task is to read all RTL files and produce a structured quality report — without running any EDA tools.

## Input
- All RTL files in `workspace/rtl/` (read every `.v` file)
- `workspace/docs/spec.json` — for KPI targets and critical path budget

## Output
- `workspace/docs/static_report.json` — structured quality report

## Tasks

### 1. Read All RTL Files
Read every `.v` file in `workspace/rtl/`. Do NOT read testbench files in `workspace/tb/`.

**MANDATORY**: After reading files, list every file you analyzed in `analyzed_files`.
Do NOT omit any file — if you read 6 files, list all 6. This field is used for audit.

### 2. Read spec.json for Targets
Extract:
- `critical_path_budget` — maximum allowed logic levels
- `target_kpis.frequency_mhz` — target frequency
- `target_kpis.max_cells` — area budget

### 3. Perform Static Analysis

Analyze the RTL code for the following issues:

#### A. Logic Depth Estimation
Count the maximum number of combinational logic levels between any two sequential elements (registers). Consider:
- Each gate/operator adds 1 level
- Multiplier trees add ~log2(width) levels
- Adder carries add ~log2(width)/2 levels
- Mux chains add 1 level each

Compare against `critical_path_budget` from spec.json.

#### B. CDC Risk Detection
Find signals that are:
- Driven in one clock domain (domain A)
- Sampled in another clock domain (domain B)
- Without a synchronizer (2-FF or handshake)

Look for: signals crossing between `always @(posedge clk_a)` and `always @(posedge clk_b)` blocks.

Classify risk:
- **HIGH**: Async signal used directly in another domain
- **MEDIUM**: Signal width > 1 bit crossing domains
- **LOW**: Pulse signal (may be OK with pulse synchronizer)

#### C. Latch Risk Detection
Identify potential latch inference:
- `always @(*)` or `always @(*)` with incomplete case (no default)
- `if` without `else` in combinational `always` blocks
- Case statements without default

Report file and line number for each finding.

#### D. Resource Estimation
Estimate rough cell count:
- Each flip-flop ~ 1 cell
- Each 2-input logic gate ~ 0.5 cells
- Each mux ~ 1 cell per bit
- Each adder ~ 1 cell per bit
- Each multiplier ~ N*N/4 cells
- **Distributed RAM FIFO** (depth D, width W): ~D×W cells (register array)
  - Example: 16-deep × 8-bit FIFO ≈ 128 cells per FIFO
  - If the design has 2 FIFOs (TX + RX): add 2× this estimate
- **Block RAM FIFO**: ~0 logic cells (uses dedicated BRAM primitives)

**IMPORTANT**: If the design uses FIFOs or memory arrays (`reg [W:0] mem [0:D-1]`),
always check for them explicitly and add their cell contribution to the total.

### 4. Generate static_report.json

**IMPORTANT**: Before calling Write, always call Read on `workspace/docs/static_report.json` first (even if you think it doesn't exist — Claude Code requires a prior Read before any Write to an existing file).

Create `workspace/docs/static_report.json` with this exact schema:

```json
{
  "design": "<design_name>",
  "analyzed_files": ["<file1.v>", "<file2.v>"],
  "logic_depth_estimate": {
    "max_levels": <integer>,
    "budget": <integer from spec.critical_path_budget>,
    "status": "OK|OVER_BUDGET|UNKNOWN",
    "worst_path": "<description of the deepest path>"
  },
  "cdc_risks": [
    {
      "signal": "<signal_name>",
      "driven_in": "<clock_domain_A>",
      "used_in": "<clock_domain_B>",
      "risk": "HIGH|MEDIUM|LOW",
      "detail": "<brief explanation>"
    }
  ],
  "latch_risks": [
    "<module_name>: <description> at line <N>"
  ],
  "cell_estimate": <integer or null>,
  "recommendation": "<single most important improvement suggestion>"
}
```

**Status rules:**
- `"OK"` — max_levels ≤ budget
- `"OVER_BUDGET"` — max_levels > budget
- `"UNKNOWN"` — could not determine (e.g., generated code, no registers found)

**If no issues found:**
```json
{
  "cdc_risks": [],
  "latch_risks": [],
  "logic_depth_estimate": {"status": "OK", ...},
  "recommendation": "No critical issues detected"
}
```

## Constraints
- Do NOT run any shell commands or EDA tools
- Do NOT modify any RTL files
- The output must be valid JSON
- All estimations are approximate — prefix uncertain values with a note in `worst_path` or `recommendation`

## Output Format

After generating the report, print a summary:

```
=== Stage 3.5: Skill D Complete ===
Files analyzed: <count> — list: <file1.v>, <file2.v>, ...
Logic depth: <max_levels>/<budget> (<status>)
CDC risks (HIGH): <count>
Latch risks: <count>
Report: workspace/docs/static_report.json
STAGE_COMPLETE
===================================
```

**IMPORTANT**: After generating static_report.json, exit immediately. The Python controller will read the report and present any violations to the user.

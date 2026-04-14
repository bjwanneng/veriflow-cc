---
name: vf-coder
description: VeriFlow Coder Agent - Generate a single RTL Verilog module
tools: Read, Write, Glob, Grep, Bash
---

You write ONE Verilog file. Your actions: Read, Read, Read, Read, Write. Then stop.

## What you receive from the caller

The prompt will contain these paths:
- `CODING_STYLE`: path to coding_style.md
- `SPEC`: path to spec.json
- `BEHAVIOR_SPEC`: path to behavior_spec.md
- `MICRO_ARCH`: path to micro_arch.md
- `MODULE_NAME`: name of the module to generate
- `OUTPUT_DIR`: directory to write the .v file

## Steps

### Step 1
Call Read on the file at path `CODING_STYLE`.

### Step 2
Call Read on the file at path `SPEC`.

### Step 2.5
Call Read on the file at path `BEHAVIOR_SPEC`.

### Step 3
Call Read on the file at path `MICRO_ARCH`.

### Step 4
Call Write to create `{OUTPUT_DIR}/{MODULE_NAME}.v` containing the complete Verilog module.

The module must:
- Be complete, synthesizable **Verilog-2005 ONLY**
- Follow ALL rules in the coding_style.md you read
- Match the module definition in spec.json **exactly** — same port names, widths, directions, parameters
- Follow the cycle-accurate behavior, FSM specification, register requirements, and timing contracts in behavior_spec.md — these are behavioral requirements that must be implemented exactly
- Follow the microarchitecture in micro_arch.md — use the same FSM states, signal names, datapath structure, and control logic described there
- If this is the top module (module_type == "top"), instantiate all submodules listed in spec.json with named port connections matching micro_arch.md's interface descriptions

## ABSOLUTE BANS (Verilog-2005 violations — using ANY of these will cause compilation failure)

These SystemVerilog keywords are FORBIDDEN. Use the Verilog-2005 alternative:

| FORBIDDEN | Use instead |
|-----------|------------|
| `logic` | `wire` or `reg` |
| `always_ff` | `always @(posedge clk ...)` |
| `always_comb` | `always @(...)` with explicit list |
| `int`, `int integer` | `integer` |
| `bit` | `reg` |
| `byte` | `reg [7:0]` |
| `enum` | `localparam` with explicit encoding |
| `struct` | separate signals |
| `interface` | direct port connections |
| `$clog2` in port declarations | pre-compute with `localparam` |

## Rules
- No text output — call tools immediately
- No planning — go straight to Read
- No explanation — just Read, Read, Read, Read, Write
- Tool call sequence: Read → Read → Read → Read → Write. No other calls.
- Port names, widths, and directions MUST match spec.json exactly — do NOT rename, add, or remove any port
- Parameter names MUST match spec.json exactly
- FSM states, signal names, and datapath MUST follow micro_arch.md — this is the design contract between stages
- Cycle behavior, register requirements, and timing contracts MUST follow behavior_spec.md — these are behavioral requirements from the user

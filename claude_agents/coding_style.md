# Verilog-2001 Coding Style Guide

## 1. File Structure

**MUST** Every `.v` file must be organized strictly in this order:

```verilog
// -----------------------------------------------------------------------------
// File   : <filename>.v
// Author : <author name>
// Date   : YYYY-MM-DD
// -----------------------------------------------------------------------------
// Description:
//   <One or more lines describing the module's purpose and key behavior.>
// -----------------------------------------------------------------------------
// Change Log:
//   YYYY-MM-DD  <Author>  <version>  <Description of change>
//   YYYY-MM-DD  <Author>  <version>  <Description of change>
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module xxx #( ... )( ... );
// ... module body ...
endmodule

`resetall
```

### File header rules

- **MUST** include a file header as the very first content in every `.v` file, before all compiler directives
- **MUST** fill in all fields: `File`, `Author`, `Date`, `Description`, `Change Log`
- **MUST** use `YYYY-MM-DD` format for all dates
- **MUST** add a new `Change Log` entry for every non-trivial modification, including: the date, author, a short version tag or commit ID, and a one-line description of what changed
- **MUST NOT** leave any field blank or as a placeholder (no `<TBD>`, `TODO`, `???`)
- `Description` may span multiple lines; each continuation line begins with `//`
- The separator line is exactly 79 `-` characters (fits within 80-column terminals)

Example of a filled-in header:

```verilog
// -----------------------------------------------------------------------------
// File   : axi_fifo_rd.v
// Author : Zhang Wei
// Date   : 2026-03-26
// -----------------------------------------------------------------------------
// Description:
//   AXI4 read-channel FIFO. Buffers AR/R channel transactions between a
//   master and a slave operating at different burst lengths. Depth and
//   data width are parameterizable.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-03-26  Zhang Wei  v1.0  Initial release
//   2026-04-01  Zhang Wei  v1.1  Fix RVALID de-assertion timing
// -----------------------------------------------------------------------------
```

---

- One module per file; filename must match module name (`foo.v` → `module foo`)
- `resetall`, `timescale 1ns / 1ps`, and `default_nettype none` at the top, in that order
- `resetall` at the end (after `endmodule`) to clear all compiler directive states
- **MUST NOT** use any `` `define `` macros inside the module body
- ASCII characters only, UNIX line endings (`\n`); every non-empty file ends with `\n`

---

## 2. Formatting

| Rule | Value |
|------|-------|
| Indentation | **4 spaces** per level `[BASE]` |
| Line continuation indent | 4 spaces |
| Max line length | 100 characters |
| Tabs | Never — spaces only |
| Trailing whitespace | None |

### begin / end

- Use `begin`/`end` unless the **entire** semicolon-terminated statement fits on one line
- `begin` on the same line as the preceding keyword; ends that line
- `end` starts a new line
- `end else begin` must all appear on one line

```verilog
// correct
if (condition) begin
    foo = bar;
end else begin
    foo = bum;
end

// correct single-line
if (condition) foo = bar;
else           foo = bum;
```

### Spacing

- At least one space after each comma
- Whitespace on both sides of all binary operators
- No space between function/task name and `(`
- Tabular alignment required for port expressions in instantiations and consecutive `assign` statements

---

## 3. Naming Conventions

| Construct | Style |
|-----------|-------|
| Modules | `lower_snake_case` |
| Instances | `lower_snake_case` with `_inst` suffix preferred `[BASE]` |
| Signals (nets, ports) | `lower_snake_case` |
| `parameter` | `ALL_CAPS` `[BASE]` |
| `localparam` | `ALL_CAPS` `[BASE]` |
| `` `define `` macros | `ALL_CAPS` |

- Signal names must be descriptive — use whole words, avoid abbreviations
- Signal names must NOT end with underscore + number (no `foo_1`, `foo_2`) `[LOWRISC]`
- Include units in constant names: `FOO_LENGTH_BYTES`, `SYSTEM_CLOCK_HZ` `[LOWRISC]`
- **MUST NOT** use Verilog/SystemVerilog reserved keywords as signal names

```verilog
// correct
module priority_encoder #( ... )( ... );
parameter DATA_WIDTH = 32;
localparam VALID_ADDR_WIDTH = ADDR_WIDTH - $clog2(STRB_WIDTH);

// incorrect
module PriorityEncoder #( ... )( ... );
parameter dataWidth = 32;
localparam valid_addr_width = 10;
```

---

## 4. Signal Suffixes

| Suffix | Meaning |
|--------|---------|
| `_reg` | Register (current state, clocked) `[BASE]` |
| `_next` | Combinational next-state signal `[BASE]` |
| `_pipe_reg` | Additional pipeline stage register `[BASE]` |
| `temp_` (prefix) | Temporary / skid-buffer register `[BASE]` |
| `_n` | Active-low signal `[LOWRISC]` |
| `_p` / `_n` | Differential pair `[LOWRISC]` |
| `_i` | Module input port `[LOWRISC]` |
| `_o` | Module output port `[LOWRISC]` |
| `_io` | Bidirectional port `[LOWRISC]` |

**Suffix ordering** `[LOWRISC]`: `_n` (active-low) comes first; `_i`/`_o` come last. Concatenated without extra underscores: `_ni`, not `_n_i`.

```verilog
// register pair
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;

// pipeline register
reg [DATA_WIDTH-1:0] s_axi_rdata_pipe_reg = {DATA_WIDTH{1'b0}};

// temporary / skid buffer
reg [7:0] temp_m_axi_arlen_reg = 8'd0;
```

---

## 5. Clocks

- All clock signals begin with `clk`; main clock is named exactly `clk` `[LOWRISC]`
- Additional clocks: `clk_<domain>` (e.g., `clk_dram`) `[LOWRISC]`

---

## 6. Reset Strategy `[BASE]`

**MUST** Use **synchronous active-high** reset named `rst`.
**MUST NOT** use asynchronous active-low `rst_n`.

```verilog
// correct
input wire rst,

if (rst) begin
    state_reg <= STATE_IDLE;
end

// incorrect
input wire rst_n,
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin ...
```

### Reset block placement

**MUST** Place the `if (rst)` block at the **end** of the `always @(posedge clk)` block, leveraging last-assignment-wins for reset priority.

```verilog
// correct — reset at end
always @(posedge clk) begin
    write_state_reg   <= write_state_next;
    s_axi_awready_reg <= s_axi_awready_next;
    s_axi_bvalid_reg  <= s_axi_bvalid_next;

    if (rst) begin
        write_state_reg   <= WRITE_STATE_IDLE;
        s_axi_awready_reg <= 1'b0;
        s_axi_bvalid_reg  <= 1'b0;
    end
end

// incorrect — if-else structure at beginning
always @(posedge clk) begin
    if (rst) begin
        write_state_reg <= WRITE_STATE_IDLE;
    end else begin
        write_state_reg <= write_state_next;
    end
end
```

### Selective reset

**SHOULD** reset only control-path signals (state, valid, ready, handshake). Pure data-path signals (payload data, addr) may be left without reset to reduce fanout. When in doubt, reset it.

---

## 7. Module Declaration `[BASE]`

**MUST** Use Verilog-2001 ANSI style. Parameter block and port block are **separate**, each with `(` on its own line.

```verilog
module axi_ram #
(
    // Width of data bus in bits
    parameter DATA_WIDTH = 32,
    // Width of address bus in bits
    parameter ADDR_WIDTH = 16
)
(
    input  wire                   clk,
    input  wire                   rst,
    input  wire [DATA_WIDTH-1:0]  s_axi_wdata,
    output wire                   s_axi_wready
);
```

- Port order: clocks first → reset → all other ports
- **MUST** explicitly declare `wire` type on all ports
- **MUST** add a brief comment above or inline for each `parameter`
- **MUST** vertically align direction (`input`/`output`), type (`wire`), width, and signal name

```verilog
// correct — aligned
input  wire [ID_WIDTH-1:0]    s_axi_awid,
input  wire [ADDR_WIDTH-1:0]  s_axi_awaddr,
input  wire [7:0]             s_axi_awlen,
input  wire                   s_axi_awvalid,
output wire                   s_axi_awready,

// incorrect — not aligned
input wire [ID_WIDTH-1:0] s_axi_awid,
input wire [ADDR_WIDTH-1:0] s_axi_awaddr,
```

---

## 8. Parameters and Constants

- Use `parameter` in module declaration for user-tunable values
- Use `localparam` for derived or internal constants
- **MUST** provide reasonable defaults for all parameters
- **MUST NOT** use `` `define `` or `defparam` to parameterize a module
- **MUST** add a brief comment for each parameter (above or inline)

```verilog
module my_mod #
(
    // Depth of the FIFO in entries
    parameter DEPTH      = 2048,
    // Derived: address width
    localparam ADDR_WIDTH = $clog2(DEPTH)
)
( ... );
```

### Parameter validation `[BASE]`

**SHOULD** use an `initial begin` block to assert critical parameter constraints:

```verilog
initial begin
    if (WORD_SIZE * STRB_WIDTH != DATA_WIDTH) begin
        $error("Error: data width not evenly divisible (instance %m)");
        $finish;
    end
end
```

---

## 9. Signal Declarations

**MUST** declare all signals before use — no implicit net declarations.

| Driven by | Declare as |
|-----------|------------|
| `always` block | `reg` |
| `assign` / combinational output | `wire` |

**MUST NOT** drive a `reg` with `assign`. **MUST NOT** drive a `wire` with `always`.

### Register initialization at declaration `[BASE]`

**MUST** assign initial values to all `reg` variables at declaration.

```verilog
// correct
reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
reg       s_axi_awready_reg = 1'b0, s_axi_awready_next;
reg [7:0] read_count_reg = 8'd0, read_count_next;

// incorrect
reg [1:0] write_state_reg;
reg       s_axi_awready_reg;
```

**SHOULD** declare `_reg` and its corresponding `_next` on the same line, separated by a comma.

### Parameterized width initialization

**MUST** use the replication operator for parameterized-width registers:

```verilog
// correct
reg [ID_WIDTH-1:0]   read_id_reg   = {ID_WIDTH{1'b0}};
reg [DATA_WIDTH-1:0] s_axi_rdata_reg = {DATA_WIDTH{1'b0}};

// incorrect
reg [ID_WIDTH-1:0]   read_id_reg   = 0;
```

### Register declaration alignment `[BASE]`

**SHOULD** vertically align widths and names within a group of register declarations:

```verilog
reg [ID_WIDTH-1:0]   read_id_reg    = {ID_WIDTH{1'b0}},   read_id_next;
reg [ADDR_WIDTH-1:0] read_addr_reg  = {ADDR_WIDTH{1'b0}}, read_addr_next;
reg [7:0]            read_count_reg = 8'd0,                read_count_next;
```

---

## 10. Output Port Driving `[BASE]`

**MUST** all `output` ports are declared as `output wire` and driven via `assign` from internal `_reg` signals.
**MUST NOT** use `output reg` or assign outputs directly in `always` blocks.

```verilog
// correct
output wire s_axi_awready,
// ...
reg  s_axi_awready_reg = 1'b0, s_axi_awready_next;
assign s_axi_awready = s_axi_awready_reg;

// incorrect
output reg s_axi_awready,
always @(posedge clk) begin
    s_axi_awready <= ...;
end
```

---

## 11. Two-Block Logic Separation `[BASE]`

**MUST** separate combinational (next-state) logic and sequential (register update) logic into distinct `always` blocks.

```verilog
// Block 1: combinational — compute all _next signals
always @* begin
    state_next = state_reg;
    data_next  = data_reg;
    // ... conditional logic ...
end

// Block 2: sequential — register sampling
always @(posedge clk) begin
    state_reg <= state_next;
    data_reg  <= data_next;

    if (rst) begin
        state_reg <= STATE_IDLE;
    end
end
```

**MUST NOT** mix next-state computation and register updates in a single `always` block.

### Sensitivity list `[BASE]`

**MUST** use `always @*` (without parentheses) for combinational blocks.
**MUST NOT** use explicit sensitivity lists or `always @(*)`.

```verilog
// correct
always @* begin ... end

// incorrect
always @(a or b or c) begin ... end
always @(*) begin ... end
```

### Assignment rules

- Combinational blocks (`always @*`): **blocking** (`=`) only
- Sequential blocks (`always @(posedge clk)`): **non-blocking** (`<=`) only
- **MUST NOT** mix `=` and `<=` for the same signal in the same `always` block

### iverilog memory array write rule

Memory array writes (`ram[idx] = val`) inside `always @(posedge clk)` **MUST** use blocking assignment (`=`), not NBA (`<=`).

**Why**: iverilog evaluates the array index at NBA **application** time rather than **scheduling** time. When the index signal is a combinational `_next` or changes via NBA in the same cycle, NBA writes to the **wrong address**. Blocking assignment captures the index immediately in the active region.

**MUST** add a comment on each such line: `// blocking: iverilog index race`

This is a **targeted exception** to the "sequential = NBA only" rule. It applies ONLY to declared memory arrays (`reg [W:0] name [0:DEPTH-1]`), not to scalar or vector registers.

```verilog
// correct — memory array write uses blocking
always @(posedge clk) begin
    if (wr_en) begin
        ram[addr] = wdata;  // blocking: iverilog index race
    end
end

// incorrect — NBA causes wrong address in iverilog
always @(posedge clk) begin
    if (wr_en) begin
        ram[addr] <= wdata;  // BUG: iverilog uses updated addr
    end
end
```

---

## 12. Latch Elimination — Default Values `[BASE]`

**MUST** assign default values to all output signals at the **very top** of every `always @*` block, before any conditional branches.

```verilog
// correct — default values at top prevent latches
always @* begin
    write_state_next   = WRITE_STATE_IDLE;
    mem_wr_en          = 1'b0;
    write_addr_next    = write_addr_reg;
    s_axi_awready_next = 1'b0;

    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            // only override signals that need to change
        end
        default: ;
    endcase
end

// incorrect — missing defaults cause latch inference
always @* begin
    case (write_state_reg)
        WRITE_STATE_IDLE:  mem_wr_en = 1'b0;
        WRITE_STATE_BURST: write_state_next = WRITE_STATE_IDLE;
        // mem_wr_en not assigned in BURST → latch!
    endcase
end
```

---

## 13. Case Statements

- Use `case` for exact matching; `casez` with `?` for wildcard matching
- **MUST** always include a `default` branch — even if all cases are covered
- **MUST NOT** use `casex`, `full_case`, or `parallel_case` pragmas

```verilog
case (state_reg)
    STATE_IDLE: begin
        state_next = STATE_WORK;
    end
    STATE_WORK: state_next = STATE_IDLE;
    default:    state_next = STATE_IDLE;
endcase
```

### Single driver rule `[BASE]`

**MUST** any `_next` signal is assigned in exactly one `always @*` block.
**MUST** any `_reg` signal is assigned in exactly one `always @(posedge clk)` block.

---

## 14. Finite State Machines

Three required components:

1. `localparam` with explicitly-specified width for state encoding
2. Combinational `always @*` block — next-state decode and all outputs, with defaults at top
3. Sequential `always @(posedge clk)` block — state register only (+ reset at end)

### State encoding `[BASE]`

**MUST** use `localparam` with explicit width and values.
State names use `ALL_CAPS` with a descriptive prefix matching the register name.

```verilog
localparam [1:0]
    WRITE_STATE_IDLE  = 2'd0,
    WRITE_STATE_BURST = 2'd1,
    WRITE_STATE_RESP  = 2'd2;

reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;
```

**MUST** state register width matches the `localparam` width.

### Full FSM example

```verilog
localparam [1:0]
    WRITE_STATE_IDLE  = 2'd0,
    WRITE_STATE_BURST = 2'd1,
    WRITE_STATE_RESP  = 2'd2;

reg [1:0] write_state_reg = WRITE_STATE_IDLE, write_state_next;

// Combinational block
always @* begin
    write_state_next   = write_state_reg;  // default: hold
    mem_wr_en          = 1'b0;
    s_axi_awready_next = 1'b0;

    case (write_state_reg)
        WRITE_STATE_IDLE: begin
            s_axi_awready_next = 1'b1;
            if (s_axi_awvalid) begin
                write_state_next = WRITE_STATE_BURST;
            end
        end
        WRITE_STATE_BURST: begin
            mem_wr_en = 1'b1;
            if (last_beat) write_state_next = WRITE_STATE_RESP;
        end
        default: write_state_next = WRITE_STATE_IDLE;
    endcase
end

// Sequential block
always @(posedge clk) begin
    write_state_reg   <= write_state_next;
    s_axi_awready_reg <= s_axi_awready_next;

    if (rst) begin
        write_state_reg   <= WRITE_STATE_IDLE;
        s_axi_awready_reg <= 1'b0;
    end
end
```

---

## 15. Module Instantiation

- **MUST** use named port connections exclusively — no positional arguments
- Each connection on its own line
- All declared ports must appear in the instantiation
- Unconnected outputs: `.output_port()`
- Unused inputs: `.unused_input_port(8'd0)`
- Port expressions must use tabular alignment
- **MUST NOT** use `defparam`; no recursive instantiation

```verilog
// correct
priority_encoder #(
    .WIDTH               (PORTS),
    .LSB_HIGH_PRIORITY   (ARB_LSB_HIGH_PRIORITY)
)
priority_encoder_inst (
    .input_unencoded  (request),
    .output_valid     (request_valid),
    .output_encoded   (request_index),
    .output_unencoded (request_mask)
);

// incorrect — positional
priority_encoder #(PORTS, ARB_LSB_HIGH_PRIORITY)
priority_encoder_inst (request, request_valid, request_index, request_mask);
```

---

## 16. Generate Constructs

- **MUST** name every generated block (`lower_snake_case`)
- **MUST** declare `genvar` inside the `generate` block `[BASE]`
- **MUST** all `generate for` loop `begin` blocks have a named label

```verilog
generate
    genvar ii;
    for (ii = 0; ii < NUM_BUSES; ii = ii + 1) begin : my_buses
        my_bus #(.Index(ii)) my_bus_inst (.foo(foo), .bar(bar[ii]));
    end
endgenerate

generate
    if (TYPE_IS_A) begin : type_a
        // ...
    end else begin : type_b
        // ...
    end
endgenerate
```

---

## 17. Memory Arrays `[BASE]`

**MUST** declare two-dimensional memory as `reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0]`.
**MUST NOT** initialize memory at declaration or clear it in the reset block.
**SHOULD** add synthesis attribute for inferred RAM type.
Initialize with `initial` block or `$readmemh`/`$readmemb`.

```verilog
(* ramstyle = "no_rw_check" *)
reg [DATA_WIDTH-1:0] mem[(2**ADDR_WIDTH)-1:0];

initial begin
    $readmemh("init_data.hex", mem);
end
```

### 17a. Array Index Bounds Safety `[BASE]`

**MUST** ensure every array index expression is provably within the declared range.

Rules:
- For loop counters that index arrays: the terminal condition **MUST** be `< DEPTH` or `<= DEPTH - 1`, never `<= DEPTH`
- For expressions like `idx + offset`: verify `idx_max + offset <= DEPTH - 1`
- Prefer index masking: `ram[cnt[ADDR_W-1:0]]` to guarantee bounds

```verilog
// WRONG: ram_t has indices [0:32], shift_cnt=32 reads ram_t[33] = X
for (j = 0; j <= DEPTH; j = j + 1)  // j max = DEPTH
    ram[j] = ram[j + 1];             // ram[DEPTH+1] = OUT OF BOUNDS!

// CORRECT: only shift valid indices
for (j = 0; j < DEPTH; j = j + 1)   // j max = DEPTH-1
    ram[j] = ram[j + 1];             // ram[DEPTH] = valid
```

---

## 18. Number Literals

- **MUST** always be explicit about widths: `4'd4`, `8'h2a`, `1'b0`
- **MUST** use `{WIDTH{1'b0}}` for parameterized-width zero — `'0` is not Verilog-2005
- Use underscores for readability in long literals

```verilog
reg [15:0] val  = 16'b0010_0011_0000_1101;
reg [39:0] addr = 40'h00_1fc0_0000;
```

### Width matching `[LOWRISC]`

- Widths of connected ports must match; use explicit padding:

```verilog
.thirty_two_bit_input ({16'd0, sixteen_bit_word})  // correct
.thirty_two_bit_input (sixteen_bit_word)            // incorrect
```

### Arithmetic and carry `[BASE]`

**MUST** handle carry and width explicitly — do not rely on implicit Verilog width extension:

```verilog
// correct — explicit carry capture
assign {carry_out, sum[7:0]} = a[7:0] + b[7:0];

// incorrect — carry silently truncated
wire [7:0] sum = a[7:0] + b[7:0];
```

**SHOULD** use `+:` / `-:` for variable-offset part selection:

```verilog
// correct
mem[addr][WORD_SIZE*i +: WORD_SIZE] <= wdata[WORD_SIZE*i +: WORD_SIZE];
```

---

## 19. Signed Arithmetic

Use `$signed()` for unsigned-to-signed conversion:

```verilog
sum = a + $signed({1'b0, incr});  // correct
sum = a + incr;                   // incorrect
```

---

## 20. AXI-Stream Handshake `[LOWRISC]`

Applies when an AXI-Stream interface is present:

- `valid` **MUST** be held HIGH until `ready` acknowledges: `if (valid && ready)`
- `tdata` **MUST NOT** change while `valid=1` and `ready=0`
- **MUST NOT** deassert `valid` before `ready` is seen

---

## 21. Comments

- Prefer `//` style; `/* */` permitted
- A comment on its own line describes the code following it
- A comment on the same line describes that line
- Section headers:

```verilog
/////////////////
// Controller  //
/////////////////
```

---

## 22. Prohibited Constructs

| Construct | Status |
|-----------|--------|
| SystemVerilog (`logic`, `always_ff`, `always_comb`, `interface`, `unique case`) | Prohibited |
| `casex` | Prohibited |
| `full_case` / `parallel_case` pragmas | Prohibited |
| `defparam` | Prohibited |
| Recursive module instantiation | Prohibited |
| `#delay` in synthesizable code | Prohibited |
| Implicit net declarations | Prohibited |
| Latches | Prohibited — use flip-flops |
| 3-state (`Z`) for on-chip muxing | Prohibited |
| `$display`, `$finish`, `$monitor` in synthesizable code | Prohibited |
| Placeholder code (`// TODO`, empty module bodies) | Prohibited |
| `output reg` | Prohibited — use `output wire` + internal `_reg` |
| Explicit sensitivity lists | Prohibited — use `always @*` |
| Asynchronous / active-low reset (`rst_n`) | Prohibited — use synchronous `rst` |

---

## Appendix: Adaptation Map

| lowRISC / SV original | This guide equivalent |
|---|---|
| `logic` | `reg` (always-driven) or `wire` (assign-driven) |
| `always_ff @(posedge clk ...)` | `always @(posedge clk)` + reset at end |
| `always_comb` | `always @*` |
| `always_latch` | Prohibited — avoid latches |
| `unique case` | `case` + mandatory `default` |
| `case inside` | `casez` with `?` wildcards |
| `typedef enum logic [N:0] {...}` | `localparam [N:0] STATE_X = N'd0, ...` |
| `signed'(x)` | `$signed(x)` |
| `'0` | `{WIDTH{1'b0}}` |
| `endmodule : name` | `endmodule` |
| `_d` / `_q` register suffixes | `_next` / `_reg` |
| `UpperCamelCase` parameters | `ALL_CAPS` |
| Asynchronous active-low `rst_n` | Synchronous active-high `rst` |

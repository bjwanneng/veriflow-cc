# Verilog-2005 Coding Style Guide

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

**Target architecture note**: Synchronous active-high reset is optimal for modern FPGA architectures (Xilinx 7-Series/UltraScale, Intel/Altera) where the flop's synchronous set/reset maps efficiently to SLICE/ALM resources. For **ASIC** tapeouts, standard cell libraries and DFT (Design for Test) scan-chain insertion traditionally favor **asynchronous active-low** resets (`rst_n`). If porting to ASIC, evaluate the target foundry's standard cell characteristics and DFT flow — asynchronous reset may be preferable for testability and area.

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

Memory array writes MUST use **combinational address pre-computation** to avoid an iverilog-specific NBA address evaluation race. Do NOT use blocking assignment (`=`) inside sequential blocks — it causes simulation-synthesis mismatch across tools.

**The problem**: iverilog evaluates the array index for `ram[addr] <= wdata` at NBA **application** time rather than **scheduling** time. If `addr` changes via NBA in the same cycle, the write targets the **new** address instead of the old one.

**The fix — combinational address pre-computation**:

```verilog
// Combinational wire — evaluated in active region, before any NBA
wire [ADDR_W-1:0] write_addr;
assign write_addr = addr_next;  // or: addr_reg + offset, etc.

always @(posedge clk) begin
    if (wr_en) begin
        ram[write_addr] <= wdata;  // standard NBA, iverilog-safe, synthesis-safe
    end
    addr_reg <= write_addr;
    if (rst) addr_reg <= 'd0;
end
```

**Why this works**: `write_addr` is a wire — its value is computed in the active region, before any NBA updates. When `ram[write_addr] <= wdata` is scheduled in the NBA region, it captures the pre-NBA address. The `addr_reg <= write_addr` NBA update does not affect `write_addr` since it's a separate combinational signal.

**Why NOT blocking assignment**: Using `=` inside `always @(posedge clk)` for memory or register writes:
- Causes simulation-synthesis mismatch: commercial tools (Vivado, Design Compiler, Genus) may fail to infer block RAM (BRAM/SRAM), synthesizing inefficient flip-flop grids instead
- Violates the fundamental Verilog rule: sequential blocks use `<=`
- Behavior varies across simulators (VCS vs Xcelium vs iverilog)

**This applies ONLY to declared memory arrays** (`reg [W:0] name [0:DEPTH-1]`). Scalar and vector registers always use standard NBA (`<=`) and do not require address pre-computation.

### 11.1 Anti-Pattern: Blocking Assignment in Sequential Blocks `[CRITICAL]`

**PROHIBITED** — using blocking assignments (`=`) inside `always @(posedge clk)` blocks for register updates.

**Incorrect (causes simulation/synthesis mismatch)**:
```verilog
always @(posedge clk) begin
    data_reg[0] = data_reg[0] ^ input_a;  // blocking: takes effect immediately
    data_reg[1] = data_reg[1] ^ input_b;  // reads the ALREADY-UPDATED data_reg[0]
end
```

**Consequences**:
1. Simulator executes sequentially — `data_reg[0]` update affects subsequent line reads
2. Synthesis tool may infer different register structure than simulation shows
3. Behavior differs across simulators (iverilog vs VCS vs ModelSim)
4. This is the hardest bug to locate — simulation passes but silicon behavior is wrong

**Correct approach A — named scalar registers + non-blocking**:
```verilog
always @(posedge clk) begin
    D0_reg <= D0_reg ^ A_reg;  // non-blocking: takes effect NEXT clock edge
    D1_reg <= D1_reg ^ B_reg;  // both read OLD values
end
```

**Correct approach B — combinational next-state + sequential update**:
```verilog
always @(*) begin
    next_data[0] = data_reg[0] ^ input_a;  // blocking in combinational is correct
    next_data[1] = data_reg[1] ^ input_b;
end
always @(posedge clk) begin
    data_reg[0] <= next_data[0];  // non-blocking in sequential
    data_reg[1] <= next_data[1];
end
```

**For memory arrays**: Use combinational address pre-computation (see "iverilog memory array write rule" above). Never use blocking assignment in sequential blocks — the wire pre-computation method is safe for all simulators AND all synthesis tools.

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

**Glitch warning**: Outputs produced in the combinational block (e.g., `mem_wr_en`) are inherently **glitch-prone**. As the state register transitions, the combinational logic may produce transient intermediate values before settling. If these signals drive **glitch-sensitive endpoints** — memory write enables, asynchronous FIFOs, clock gating cells, or any edge-sensitive receivers — they **MUST** be registered:

```verilog
// Inside sequential block: register the glitch-prone output
mem_wr_en_reg <= mem_wr_en;  // Glitch-free registered output
// Consumer uses mem_wr_en_reg, not mem_wr_en
```

**Rule of thumb**: Control signals that fan out to datapath modules (write enables, load strobes, calculation enables) should always be registered. Pure status indicators (ready, valid) are typically safe as direct combinational outputs.

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
- **MUST** declare `genvar` outside the `generate` block (strict Verilog-2001; declaring `genvar` inside `generate` is a SystemVerilog relaxation)
- **MUST** all `generate for` loop `begin` blocks have a named label

```verilog
// genvar declared BEFORE generate (strict Verilog-2001)
genvar ii;
generate
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

### Hex literal digit count `[IMPORTANT]`

For `N'h...` hex constants, the digit count MUST equal `ceil(N/4)` = `(N+3)/4`.
Iverilog silently truncates or zero-pads mismatched constants — bugs from wrong
digit counts are hard to detect.

Common widths:
- 32-bit → 8 hex digits
- 128-bit → 32 hex digits
- 256-bit → 64 hex digits
- 512-bit → 128 hex digits

```verilog
// WRONG — 133 hex digits for a 512-bit constant (5 extra digits)
localparam [511:0] MSG = 512'h616263800000...018;
// iverilog truncates MSBs — data corruption!

// CORRECT — exactly 128 hex digits for 512-bit constant
localparam [511:0] MSG = 512'h0061626380000...0018;
```

**Validation**: When writing wide hex constants in localparam, count digits and
verify `digit_count == width / 4`. Use Python to validate:
```python
digits = len(hex_str.lstrip('0').rstrip()) or 1
assert digits <= width // 4, f"Too many hex digits: {digits} > {width//4}"
```

### Width matching `[LOWRISC]`

- Widths of connected ports must match; use explicit padding:

```verilog
// correct — explicit zero-padding with replication operator
.thirty_two_bit_input ({ {16{1'b0}}, sixteen_bit_word })
// also correct — hex literal
.thirty_two_bit_input ({16'h0000, sixteen_bit_word})

// incorrect — implicit width mismatch
.thirty_two_bit_input (sixteen_bit_word)
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

---

## 23. Pipeline Timing Discipline `[IMPORTANT]`

Before implementing any module with multi-cycle operations or pipeline stages, build a **cycle-accurate timing table** showing signal values per clock cycle. This prevents the most common class of RTL bugs: wrong data at the wrong cycle.

**Template** (adapt column names to your design):

```
Cycle | FSM State | process_en | counter | data_source | output_valid
------|-----------|------------|---------|-------------|-------------
  0   | IDLE      |     0      |    -    |      -      |      0
  1   | LOAD      |     0      |    0    |   input     |      0
  2   | PROCESS   |     1      |    0    |  reg_file   |      0
  3   | PROCESS   |     1      |    1    |  reg_file   |      0
  ... | PROCESS   |     1      |   N-1   |  reg_file   |      0
 N+1  | DONE      |     0      |    -    |      -      |      1
```

**Key rules**:
1. Register values update at `posedge clk`. The new value is visible starting the **next** clock edge — never on the same cycle the assignment happens.
2. A control signal (e.g., `process_en`) asserted on cycle N produces its first effect on cycle N+1.
3. FSM state transitions and control signal assertions MUST be in the same `always` block to avoid cycle skew.
4. Counter range must be exactly N iterations: count from 0 to N-1, producing exactly N assertions of the enable signal.
5. For `handshake: "hold_until_ack"` ports: valid MUST stay high across cycles until ack is received. Do NOT pulse valid for one cycle.
6. For `handshake: "single_cycle"` ports: valid MUST be high for exactly one cycle, then auto-deassert on the next clock edge.

---

## 24. Cross-Module Timing Rules `[CRITICAL]`

Rules for designs where a control module (FSM) drives control signals to consumer datapath modules, and signals must be aligned across module boundaries.

### 24.1 Producer-Consumer Cycle Annotation

Every signal crossing a module boundary must be annotated with its **producer cycle** and **consumer cycle**. This annotation lives in the module's behavior spec (Section 2.1 cycle table) and the cross-module timing (Section 3.2).

**Template** (add to module header comments):

```verilog
// Signal:  data_en
// Producer: top_fsm, always @(posedge clk), registered (data_en_reg)
// Produced: cycle N   — FSM state=IDLE, input_valid=1
// Consumer: datapath_a, always @(posedge clk)
// Consumed: cycle N   — same posedge (NBA: consumer sees value from cycle N-1!)
// Consumer: datapath_b, always @(posedge clk)
// Consumed: cycle N+1 — next posedge (NBA has applied, sees correct value)
```

**Key insight**: When a registered signal is produced at `posedge N` (NBA scheduled), it is STALE for any consumer running in the same `posedge N` active region. The consumer sees the OLD value. The new value is visible at `posedge N+1`.

**Rule**: If a signal is produced AND consumed on the same `posedge`, the consumer sees the PRODUCER'S PREVIOUS value. This is the Verilog NBA cross-module race.

### 24.2 Same-Cycle Produce-and-Consume: Combinational Bypass

When a signal must be produced and consumed in the same clock cycle (e.g., a configuration flag latched on `input_valid` must be stable before `data_en` fires at the same posedge), use a **combinational bypass** — expose the producer's next-state value as a wire. The consumer reads the wire (combinational), not the registered output.

**Correct pattern — combinational bypass**:

```verilog
// Producer: expose next-state value as combinational wire
wire flag_next;
assign flag_next = (input_valid && ready) ? input_flag : flag_reg;

always @(posedge clk) begin
    flag_reg <= flag_next;
    if (rst) flag_reg <= 1'b0;
end

// Consumer: reads flag_next (combinational), not flag_reg
// flag_next is valid in the SAME cycle input_valid fires — no NBA delay
u_submodule (
    .flag_i(flag_next)  // combinational — no NBA delay
);
```

**Alternative — accept pipeline delay**: If one cycle of latency is acceptable, keep the producer on `@(posedge clk)` with registered output, and design the consumer to expect the signal one cycle later. This is simpler and always synthesizable.

**Approach selection guide**:
| Condition | Approach |
|-----------|----------|
| Consumer needs value in same cycle as producer asserts it | Combinational bypass (`assign _next` wire) |
| Consumer can tolerate 1-cycle delay | Standard posedge register (simpler, lower fanout) |
| Signal is hold_until_used, consumed far in the future | Standard posedge latch (Section 24.3) |

**WARNING — DO NOT use `@(negedge clk)` in synthesizable RTL**:
- Creates half-cycle timing paths — makes timing closure extremely difficult across PVT corners
- Depends on clock duty cycle — fragile and non-portable
- Synthesis tools may produce unexpected results (some ignore negedge sensitivity on data paths)
- This is a simulation-only workaround that causes **simulation-synthesis mismatch**

**When NOT to use combinational bypass**: Signals with high fanout (the combinational wire adds load), or when the producer's next-state logic is complex (adds combinational path length). In these cases, prefer accepting the one-cycle pipeline delay.

### 24.3 Signal Lifetime: Pulse vs Hold-Until-Used

Ports with `signal_lifetime: "hold_until_used"` in spec.json require special handling. These signals arrive as short pulses (1-2 cycles) but are consumed many cycles later by a downstream module.

**Bug pattern**: `done_flag` on multi-cycle processing designs:
- `done_flag` asserted with `input_valid` on cycle 0 (1-cycle pulse)
- FSM samples `done_flag` in COMPLETE state, many cycles later
- Without latching, FSM sees 0 — operation never completes

**Required pattern** — Add a latch register in the connecting wrapper:

```verilog
reg done_latched_reg;

// Standard posedge latch — by the time FSM reads done_latched (tens of cycles later),
// NBA has long since applied. No negedge needed.
always @(posedge clk) begin
    if (rst) begin
        done_latched_reg <= 1'b0;
    end else if (complete_flag) begin
        done_latched_reg <= 1'b0;  // clear for next operation
    end else if (input_valid && fsm_ready) begin
        done_latched_reg <= done_flag;  // capture the pulse at posedge
    end
end
```

**Why `@(posedge clk)` is correct**: The latched value is consumed far in the future (e.g., FSM DONE state many cycles later). The NBA has long since applied. Standard posedge is sufficient.

**If the consumer needs the value on the immediate next posedge**: Use combinational bypass (Section 24.2), not negedge clock.

**Checklist for `hold_until_used` signals**:
1. [ ] Latch register exists in the wrapper or consumer module
2. [ ] Latch is set on the signal's assertion cycle (input_valid pulse)
3. [ ] Latch is cleared when the consumer has finished using it (done_flag)
4. [ ] Consumer reads the LATCHED register, not the raw input port
5. [ ] If the consumer samples at the very next posedge, use a **Combinational Bypass** (Section 24.2) instead of a latch — standard `@(posedge clk)` latch is one cycle too slow for same-cycle produce-and-consume

### 24.4 FSM Output Restriction

FSM registered outputs (`_reg` + `assign`) can only be consumed starting the posedge AFTER they are produced. When a consumer module's combinational block evaluates at the same posedge the FSM updates its outputs, the consumer sees stale values.

**Validation**: For each FSM output signal, verify in the timing table that no consumer reads it on the same cycle it's produced. If this is unavoidable, the FSM must produce it one cycle earlier (registered in the previous state).

### 24.5 Counter Range Consistency

All modules sharing a round/step counter must agree on the range:

```
FSM:          step_cnt = 0, 1, 2, ..., N-1  (N values, 0 to N-1)
datapath_a:   expects step_cnt = 0..N-1     (processes element data[step_cnt])
datapath_b:   expects step_cnt = 0..N-1     (parameter lookup depends on step)

Agreement: All use 0..N-1 → OK
Mismatch:  FSM uses 0..N-1, datapath_b expects data[N-1] at step=N → data[N-1] never produced
```

**Rule**: Counter range must be verified in golden_model.py and spec.json module_connectivity. Document the agreed range in each module's port and connectivity definitions.

### 24.6 Shift Register Alignment

For shift-register-based data processing (sliding windows, FIR filters, data expansion):

**Critical alignment question**: At step j, is the output element `data[j]` or `data[j-1]`?

This depends on whether the load cycle shifts simultaneously:

```
Pattern A — load without shift:
  fill_en=1:  buf[0] ← data[0],   buf[1..M-1] unchanged
  shift_en=1: buf[0] ← buf[1],    shifts → data[1] at output
  Result: at step=0, output = data[0] ✓ (but shift not yet asserted)

Pattern B — load with simultaneous shift:
  fill_en=1 + shift_en=1: buf[0] ← data[1] (shifted BEFORE load!)
  Result: at step=0, output = data[1] ✗ — one step ahead, data[0] lost
```

**Rule**: `fill_en` and `shift_en` MUST NOT be co-asserted if the shift register uses `if/else-if` priority. The FSM must provide a dedicated load cycle (IDLE→LOAD→PROCESS, not IDLE→PROCESS with co-asserted enables).

**Validation**: Verify that `fill_en` and `shift_en` are mutually exclusive in the FSM's transition table — the FSM must show separate load and process cycles.

### 24.7 Shift Register Window Replenishment `[CRITICAL]`

When a shift register shifts every active cycle (unconditional shift during `proc_en`), the next-element injected at the end of the register MUST NOT be gated to zero by a step counter condition.

**WRONG** — window drains during early steps:
```verilog
wire [DATA_W-1:0] next_elem = (step_cnt < THRESHOLD) ? {DATA_W{1'b0}} : transform(temp) ^ ...;
// After THRESHOLD shifts with zero injection, original data is fully drained
```

**CORRECT** — always replenish:
```verilog
wire [DATA_W-1:0] next_elem = transform(temp) ^ buf[OFFSET_A] ^ buf[OFFSET_B];
```

**Rule**: For sliding-window data processing (data expansion, FIR filters,
CRC accumulators), the next-element computation must be **unconditional** during
all active cycles. The step counter controls external consumption only, not
internal replenishment.

**Validation**: Search for the pattern `buf[N-1] <= ... next_elem ...` where
`next_elem` contains a ternary `(step_cnt < THRESHOLD) ? 0 :`. Flag as defect.

---

## 25. Algorithm Initial State Completeness `[CRITICAL]`

For designs with defined initial register values (e.g., iterative algorithms,
accumulator chains, DSP datapaths), the specification defines a set of initial
register values. The RTL must initialize **every** register that participates
in the final output expression.

### 25.1 Output Trace-Back Rule

For each output port of a datapath module:

1. Write the output expression (e.g., `data_out = accum_reg ^ result_reg`)
2. List **all** registers that appear in this expression
3. For each register, verify it has a correct initial value for the first
   operational cycle (not just "reset to 0")

If any register feeds into an XOR/ADD chain where 0 is NOT the algorithmically
correct initial value, it MUST be explicitly initialized (via init path,
separate init state, or reset block).

### 25.2 Selective Reset Caveat for Algorithmic Designs

Section 6 (Selective Reset) says "pure data-path signals may be left without
reset." For algorithmic datapaths, this guidance has a critical exception:

**Registers that participate in output XOR/ADD chains are NOT pure data-path.**
Even though their operational values are computed data, their initial values
directly affect correctness. If `data_out = A ^ B`, and A=0 at start, the
first output will be `0 ^ B = B` instead of `INIT_A ^ B`.

**Rule**: For algorithmic designs, treat ALL registers in the output expression
as requiring explicit initialization. Do NOT rely on "reset to 0" being correct
for XOR-based output paths.

**Validation**: In the verify_fix stage, check for registers where:
- The register is read in an expression contributing to a module output
- The register's reset value is 0
- The output expression is an XOR chain
→ Flag as "potential initialization gap — verify algorithm spec requires 0"

### 25.3 Merkle-Damgård Dual Register Initialization `[CRITICAL]`

For hash/digest cores using Merkle-Damgård or similar iterated constructions:

- **Working registers** (A-H): loaded from IV for first block, from chaining values for subsequent blocks
- **Chaining registers** (V0-V7): accumulate results across blocks via `V_new = V_old ^ result`
- **Both sets MUST be re-initialized to IV when starting a new message**

```verilog
// WRONG — only working registers initialized
if (is_first_block) begin
    A_reg <= IV0; B_reg <= IV1; ... H_reg <= IV7;
    // V0-V7 retain stale values from previous message!
end

// CORRECT — both sets initialized
if (is_first_block) begin
    A_reg <= IV0; B_reg <= IV1; ... H_reg <= IV7;
    V0 <= IV0; V1 <= IV1; ... V7 <= IV7;  // re-init chaining values
end
```

**Rule**: When `is_first_block` is used to distinguish new-message start, ALL
persistent state registers (working + chaining) must be set to their algorithm-defined
initial values — not just the working set.

---

## 26. Finalize-State Register Read Rule `[CRITICAL]`

In iterative computation FSMs (IDLE → CALC → DONE), the DONE/finalize state
MUST read registered values only, never combinational next-state wires.

### Invariant

**DONE/finalize states MUST use `_reg` values. NEVER use `_new` (combinational)
wires for output computation or register updates in finalize states.**

### Rationale

Combinational `_new` wires (e.g., `a_new`, `b_new`) represent what the registers
WILL become on the next clock edge — i.e., the result of applying one more round
of computation. When the FSM reaches DONE after N rounds, using `_new` values
effectively applies round N+1, producing wrong results.

### Correct Pattern

```verilog
// CALC state: update registers from combinational next-state wires
STATE_CALC: begin
    A_reg <= a_new;  // correct — registers take next-state values
    B_reg <= b_new;
    // ...
end

// DONE state: use registered values (result of all completed rounds)
STATE_DONE: begin
    V0 <= V0 ^ A_reg;   // correct — reads registered state
    V1 <= V1 ^ B_reg;
    hash_out_r <= {V0 ^ A_reg, V1 ^ B_reg, ...};
end
```

### Counter-Example (Bug Pattern)

```verilog
// WRONG — DONE state reads combinational next-state wires
STATE_DONE: begin
    V0 <= V0 ^ a_new;   // BUG: a_new = result of round 64 (never executed!)
    hash_out_r <= {V0 ^ a_new, ...};
end
```

### Detection

In verify_fix stage, flag any DONE/finalize state that references a `_new`
combinational signal. These signals are valid ONLY inside CALC-state sequential
blocks for register updates.

---

## 27. Cycle-First Design Methodology `[CRITICAL]`

### 27.1 The Problem: Software Brain Meets Hardware Clock

LLMs and human developers trained on software naturally think in sequential
execution: "statement B follows statement A, so B sees A's result." Hardware
does not work this way.

In hardware with synchronous registers:
- At posedge T: ALL registers sample their inputs simultaneously
- A register written at posedge T (`reg_x <= new_val`) does NOT make `new_val`
  available until posedge T+1
- Any logic evaluating at posedge T sees the register's value from posedge T-1

This creates a fundamental impedance mismatch between sequential thinking and
clocked hardware behavior.

### 27.2 The Solution: T/T+1 Thinking

Replace "sequential execution" with "clock-tick propagation":

| Software Thinking (WRONG)          | Hardware Thinking (CORRECT)                |
|-------------------------------------|--------------------------------------------|
| "After A is computed, B uses A"    | "A is computed at T, B reads A at T+1"    |
| "Signal is asserted, module sees it"| "Signal asserted at T, module sees at T+1"|
| "Load then calculate"               | "Load at T, calculate sees loaded data at T+1"|
| "if/else if for two enables"        | "Two enables are simultaneous — use two `if` blocks"|

### 27.3 Mandatory Pre-Code Step: Build the Cycle Table

Before writing ANY combinational or sequential always block, the designer MUST
produce a cycle timing table:

```
T    | FSM State  | load_en | calc_en | register_X | register_Y | output_valid
-----|------------|---------|---------|------------|------------|-------------
T+0  | IDLE       |    0    |    0    |     -      |     -      |      0
T+1  | LOAD       |    1    |    0    |  input_val |     -      |      0
T+2  | CALC[0]    |    0    |    1    |  f(input)  |  loaded    |      0
T+3  | CALC[1]    |    0    |    1    |  f(prev)   |  loaded    |      0
...  | CALC[N-1]  |    0    |    1    |  f(prev)   |  loaded    |      0
T+N+1| DONE       |    0    |    0    |  result    |  result    |      1
```

For each row, verify:
1. Registered signals: value in this row is what the register HOLDS at this
   posedge (it was WRITTEN at the previous posedge)
2. Combinational signals: value in this row is what the wire evaluates to
   at this posedge (it depends on the current registered values)
3. Output ports: driven from `_reg` signals — visible to external modules
   starting the NEXT posedge

### 27.4 Rules Derived From T/T+1 Thinking

1. **`<=` means "next cycle visible"**: Every `<=` assignment in a sequential
   block defers the value change to the next posedge. Plan accordingly.

2. **Co-asserted load and calc need bypass mux**: If `load_en` and `calc_en`
   are both high on the same cycle, the datapath must select:
   `working_data = load_en ? input_data : computed_result`
   Do NOT use `if/else if` — both paths execute simultaneously.

3. **Co-asserted enables need independent `if` blocks**: If `module_a_en` and
   `module_b_en` are both asserted by the same FSM state, they MUST appear in
   separate `if` blocks, not in an `if/else if` chain.

4. **Cross-module registered signals have 1-cycle delay**: If module A produces
   a registered output and module B consumes it on the same posedge, module B
   sees the PREVIOUS value. Use combinational bypass (assign from `_next` wire)
   if same-cycle visibility is required.

5. **FSM output assertion timing**: If a registered output must be active during
   STATE_B, assert it during STATE_A's transition to STATE_B (one cycle earlier).
   The register will sample it at the same posedge that transitions to STATE_B,
   making it visible at STATE_B's first cycle.

### 27.5 Validation Checklist

After completing the cycle timing table and writing the Verilog code:

- [ ] For each registered signal, verify its value in each row matches what the
      Verilog `<=` assignment would produce
- [ ] For each cross-module signal, verify the `timing_contract.same_cycle_visible`
      matches the actual implementation (registered = false, combinational bypass = true)
- [ ] For each co-asserted pair of enables, verify they are in independent `if` blocks
- [ ] For the DONE/finalize state, verify only `_reg` signals are used (no `_new` wires)
- [ ] For the first operational cycle, verify ALL output-path registers have correct
      initial values (not just "reset to 0")
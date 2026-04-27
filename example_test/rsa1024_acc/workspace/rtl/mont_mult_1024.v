// -----------------------------------------------------------------------------
// File   : mont_mult_1024.v
// Author : AI Coder
// Date   : 2026-04-26
// -----------------------------------------------------------------------------
// Description:
//   1024-bit Montgomery modular multiplier using CIOS (Coarsely Integrated
//   Operand Scanning) algorithm. Controls mont_word_engine through 32 outer
//   loop iterations. Contains internal BRAMs for operands A, B, modulus N,
//   and distributed RAM for the t[] accumulator (33 words).
//
//   Operands are loaded via the memory-write interface before starting.
//   After completion, the result is read via the result read interface.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-26  AI Coder  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module mont_mult_1024 #
(
    // Bit width of each word
    parameter WORD_WIDTH = 32,
    // Number of words per 1024-bit operand
    parameter NUM_WORDS  = 32
)
(
    input  wire                  clk,
    input  wire                  rst,
    input  wire                  start_i,
    output wire                  done_o,
    input  wire                  mem_wr_en_i,
    input  wire [1:0]            mem_sel_i,
    input  wire [4:0]            mem_addr_i,
    input  wire [WORD_WIDTH-1:0] mem_wdata_i,
    input  wire [WORD_WIDTH-1:0] n_prime_i,
    input  wire [4:0]            result_addr_i,
    output wire [WORD_WIDTH-1:0] result_data_o
);

    // ----------------------------------------------------------------
    // Parameters
    // ----------------------------------------------------------------
    localparam WORD_IDX_WIDTH = 5;
    localparam T_DEPTH        = NUM_WORDS + 1;
    localparam T_IDX_WIDTH    = 6;

    // FSM states
    localparam [2:0]
        STATE_IDLE = 3'd0,
        STATE_INIT = 3'd1,
        STATE_RUN  = 3'd2,
        STATE_WAIT = 3'd3,
        STATE_COPY = 3'd4,
        STATE_DONE = 3'd5;

    // ----------------------------------------------------------------
    // Internal registers
    // ----------------------------------------------------------------
    reg [2:0]              state_reg    = STATE_IDLE, state_next;
    reg [WORD_IDX_WIDTH:0] i_cnt_reg    = {WORD_IDX_WIDTH+1{1'b0}}, i_cnt_next;
    reg [WORD_IDX_WIDTH:0] copy_cnt_reg = {WORD_IDX_WIDTH+1{1'b0}}, copy_cnt_next;

    // Engine start pulse register
    reg                    engine_start_reg = 1'b0, engine_start_next;

    // B word register: latched when engine is started
    reg [WORD_WIDTH-1:0]   b_word_reg = {WORD_WIDTH{1'b0}}, b_word_next;

    // Done output register
    reg                    done_reg = 1'b0, done_next;

    // ----------------------------------------------------------------
    // Operand RAMs: 32 x 32 synchronous write, 1-cycle read latency
    // ----------------------------------------------------------------
    (* ramstyle = "no_rw_check" *)
    reg [WORD_WIDTH-1:0] ram_op_a [0:NUM_WORDS-1];
    (* ramstyle = "no_rw_check" *)
    reg [WORD_WIDTH-1:0] ram_op_b [0:NUM_WORDS-1];
    (* ramstyle = "no_rw_check" *)
    reg [WORD_WIDTH-1:0] ram_n    [0:NUM_WORDS-1];

    // T accumulator: 33 x 32 distributed RAM
    (* ramstyle = "distributed" *)
    reg [WORD_WIDTH-1:0] ram_t [0:T_DEPTH-1];

    // Result RAM: 32 x 32 for combinational read by parent
    reg [WORD_WIDTH-1:0] ram_result [0:NUM_WORDS-1];

    // ----------------------------------------------------------------
    // Wires from engine
    // ----------------------------------------------------------------
    wire [WORD_IDX_WIDTH-1:0] addr_rd;
    wire [T_IDX_WIDTH-1:0]    t_rd_addr;
    wire [T_IDX_WIDTH-1:0]    t_wr_addr;
    wire [WORD_WIDTH-1:0]     t_wr_data;
    wire                      t_wr_en;
    wire                      engine_done;

    // RAM read data outputs (1-cycle latency synchronous read)
    reg [WORD_WIDTH-1:0]      ram_a_rd_data_reg = {WORD_WIDTH{1'b0}};
    reg [WORD_WIDTH-1:0]      ram_n_rd_data_reg = {WORD_WIDTH{1'b0}};
    reg [WORD_WIDTH-1:0]      t_rd_data_reg     = {WORD_WIDTH{1'b0}};

    // T init clear write enable
    reg                       t_init_wr_en_reg  = 1'b0;

    // T init clear address
    reg [T_IDX_WIDTH-1:0]     t_init_addr_reg   = {T_IDX_WIDTH{1'b0}};

    // Result copy enable
    reg                       result_copy_en_reg = 1'b0;

    // ----------------------------------------------------------------
    // Result read: combinational from ram_result
    // ----------------------------------------------------------------
    assign result_data_o = ram_result[result_addr_i];

    // ----------------------------------------------------------------
    // Output assignment
    // ----------------------------------------------------------------
    assign done_o = done_reg;

    // ----------------------------------------------------------------
    // RAM write logic
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        // External operand write port — blocking assignment avoids
        // iverilog race condition on array-index evaluation with NBA.
        if (mem_wr_en_i) begin
            case (mem_sel_i)
                2'b00: ram_op_a[mem_addr_i] = mem_wdata_i;
                2'b01: ram_op_b[mem_addr_i] = mem_wdata_i;
                2'b10: ram_n[mem_addr_i]    = mem_wdata_i;
                default: ;
            endcase
        end

        // T accumulator write from engine (priority over init clear)
        // Blocking assignment avoids iverilog NBA array-index race condition
        if (t_wr_en) begin
            ram_t[t_wr_addr] = t_wr_data;
        end else if (t_init_wr_en_reg) begin
            ram_t[t_init_addr_reg] = {WORD_WIDTH{1'b0}};
        end

        // Result copy from t[] to ram_result
        if (result_copy_en_reg) begin
            ram_result[copy_cnt_reg[WORD_IDX_WIDTH-1:0]] = ram_t[copy_cnt_reg];
        end
    end

    // ----------------------------------------------------------------
    // RAM synchronous read: 1-cycle latency
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            ram_a_rd_data_reg <= {WORD_WIDTH{1'b0}};
            ram_n_rd_data_reg <= {WORD_WIDTH{1'b0}};
            t_rd_data_reg     <= {WORD_WIDTH{1'b0}};
        end else begin
            ram_a_rd_data_reg <= ram_op_a[addr_rd];
            ram_n_rd_data_reg <= ram_n[addr_rd];
            t_rd_data_reg     <= ram_t[t_rd_addr];
        end
    end

    // ----------------------------------------------------------------
    // Combinational FSM: next-state and control signal decode
    // ----------------------------------------------------------------
    always @* begin
        // Defaults — hold state, no pulses
        state_next        = state_reg;
        i_cnt_next        = i_cnt_reg;
        copy_cnt_next     = copy_cnt_reg;
        engine_start_next = 1'b0;
        b_word_next       = b_word_reg;
        done_next         = 1'b0;
        t_init_wr_en_reg  = 1'b0;
        t_init_addr_reg   = copy_cnt_reg;
        result_copy_en_reg = 1'b0;

        case (state_reg)
            STATE_IDLE: begin
                if (start_i) begin
                    state_next    = STATE_INIT;
                    i_cnt_next    = {WORD_IDX_WIDTH+1{1'b0}};
                    copy_cnt_next = {WORD_IDX_WIDTH+1{1'b0}};
                end
            end

            STATE_INIT: begin
                // Clear t[0..32] one word per cycle
                t_init_wr_en_reg = 1'b1;
                t_init_addr_reg  = copy_cnt_reg;
                if (copy_cnt_reg == T_DEPTH[WORD_IDX_WIDTH:0] - 1'b1) begin
                    copy_cnt_next = {WORD_IDX_WIDTH+1{1'b0}};
                    state_next    = STATE_RUN;
                end else begin
                    copy_cnt_next = copy_cnt_reg + {{WORD_IDX_WIDTH{1'b0}}, 1'b1};
                end
            end

            STATE_RUN: begin
                // Load B[i] and start engine
                b_word_next       = ram_op_b[i_cnt_reg[WORD_IDX_WIDTH-1:0]];
                engine_start_next = 1'b1;
                state_next        = STATE_WAIT;
            end

            STATE_WAIT: begin
                if (engine_done) begin
                    if (i_cnt_reg == NUM_WORDS[WORD_IDX_WIDTH:0] - 1'b1) begin
                        // All 32 outer iterations complete
                        state_next    = STATE_COPY;
                        copy_cnt_next = {WORD_IDX_WIDTH+1{1'b0}};
                    end else begin
                        i_cnt_next = i_cnt_reg + {{WORD_IDX_WIDTH{1'b0}}, 1'b1};
                        state_next = STATE_RUN;
                    end
                end
            end

            STATE_COPY: begin
                // Copy t[0..31] to ram_result, one per cycle
                result_copy_en_reg = 1'b1;
                if (copy_cnt_reg == NUM_WORDS[WORD_IDX_WIDTH:0] - 1'b1) begin
                    state_next = STATE_DONE;
                end else begin
                    copy_cnt_next = copy_cnt_reg + {{WORD_IDX_WIDTH{1'b0}}, 1'b1};
                end
            end

            STATE_DONE: begin
                done_next  = 1'b1;
                state_next = STATE_IDLE;
            end

            default: state_next = STATE_IDLE;
        endcase
    end

    // ----------------------------------------------------------------
    // Sequential block: register updates
    // ----------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            state_reg        <= STATE_IDLE;
            i_cnt_reg        <= {WORD_IDX_WIDTH+1{1'b0}};
            copy_cnt_reg     <= {WORD_IDX_WIDTH+1{1'b0}};
            engine_start_reg <= 1'b0;
            b_word_reg       <= {WORD_WIDTH{1'b0}};
            done_reg         <= 1'b0;
        end else begin
            state_reg        <= state_next;
            i_cnt_reg        <= i_cnt_next;
            copy_cnt_reg     <= copy_cnt_next;
            engine_start_reg <= engine_start_next;
            b_word_reg       <= b_word_next;
            done_reg         <= done_next;
        end
    end

    // ----------------------------------------------------------------
    // Submodule instantiation: mont_word_engine
    // ----------------------------------------------------------------
    mont_word_engine #
    (
        .WORD_WIDTH (WORD_WIDTH),
        .NUM_WORDS  (NUM_WORDS)
    )
    mont_word_engine_inst
    (
        .clk          (clk),
        .rst          (rst),
        .start_i      (engine_start_reg),
        .done_o       (engine_done),
        .b_i          (b_word_reg),
        .n_prime_i    (n_prime_i),
        .addr_rd_o    (addr_rd),
        .a_j_i        (ram_a_rd_data_reg),
        .n_j_i        (ram_n_rd_data_reg),
        .t_rd_addr_o  (t_rd_addr),
        .t_rd_data_i  (t_rd_data_reg),
        .t_wr_addr_o  (t_wr_addr),
        .t_wr_data_o  (t_wr_data),
        .t_wr_en_o    (t_wr_en)
    );

endmodule

`resetall

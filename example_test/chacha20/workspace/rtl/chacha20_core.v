// -----------------------------------------------------------------------------
// File   : chacha20_core.v
// Author : VeriFlow-CC
// Date   : 2026-04-24
// -----------------------------------------------------------------------------
// Description:
//   ChaCha20 block computation core. Maintains 4x4 state matrix, performs
//   10 double-rounds (20 rounds) using 4 parallel quarter-round units,
//   then adds initial state for final 512-bit keystream output.
//   Latency: 22 cycles (1 init + 20 rounds + 1 finalize).
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-24  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module chacha20_core
(
    input  wire          clk_i,
    input  wire          rst_n_i,
    input  wire [255:0]  key_i,
    input  wire [95:0]   nonce_i,
    input  wire [31:0]   counter_i,
    input  wire          start_i,
    output wire [511:0]  state_o,
    output wire          done_o,
    output wire          busy_o
);

    //-------------------------------------------------------------------------
    // FSM state encoding
    //-------------------------------------------------------------------------
    localparam [1:0]
        CORE_IDLE     = 2'd0,
        CORE_ROUND    = 2'd1,
        CORE_FINALIZE = 2'd2;

    //-------------------------------------------------------------------------
    // ChaCha20 constants (little-endian "expand 32-byte k")
    //-------------------------------------------------------------------------
    localparam [31:0] CONST_EXPA = 32'h6170_7865;
    localparam [31:0] CONST_ND_3 = 32'h3320_646e;
    localparam [31:0] CONST_2_BY = 32'h7962_2d32;
    localparam [31:0] CONST_TE_K = 32'h6b20_6574;

    //-------------------------------------------------------------------------
    // Byte-swap function: big-endian bus word -> little-endian state word
    //-------------------------------------------------------------------------
    function [31:0] bswap32;
        input [31:0] val;
        begin
            bswap32 = {val[7:0], val[15:8], val[23:16], val[31:24]};
        end
    endfunction

    //-------------------------------------------------------------------------
    // Internal state registers
    //-------------------------------------------------------------------------
    reg [31:0] state_00_reg  = 32'd0, state_00_next;
    reg [31:0] state_01_reg  = 32'd0, state_01_next;
    reg [31:0] state_02_reg  = 32'd0, state_02_next;
    reg [31:0] state_03_reg  = 32'd0, state_03_next;
    reg [31:0] state_04_reg  = 32'd0, state_04_next;
    reg [31:0] state_05_reg  = 32'd0, state_05_next;
    reg [31:0] state_06_reg  = 32'd0, state_06_next;
    reg [31:0] state_07_reg  = 32'd0, state_07_next;
    reg [31:0] state_08_reg  = 32'd0, state_08_next;
    reg [31:0] state_09_reg  = 32'd0, state_09_next;
    reg [31:0] state_10_reg  = 32'd0, state_10_next;
    reg [31:0] state_11_reg  = 32'd0, state_11_next;
    reg [31:0] state_12_reg  = 32'd0, state_12_next;
    reg [31:0] state_13_reg  = 32'd0, state_13_next;
    reg [31:0] state_14_reg  = 32'd0, state_14_next;
    reg [31:0] state_15_reg  = 32'd0, state_15_next;

    // Saved initial state for final addition
    reg [31:0] init_00_reg = 32'd0;
    reg [31:0] init_01_reg = 32'd0;
    reg [31:0] init_02_reg = 32'd0;
    reg [31:0] init_03_reg = 32'd0;
    reg [31:0] init_04_reg = 32'd0;
    reg [31:0] init_05_reg = 32'd0;
    reg [31:0] init_06_reg = 32'd0;
    reg [31:0] init_07_reg = 32'd0;
    reg [31:0] init_08_reg = 32'd0;
    reg [31:0] init_09_reg = 32'd0;
    reg [31:0] init_10_reg = 32'd0;
    reg [31:0] init_11_reg = 32'd0;
    reg [31:0] init_12_reg = 32'd0;
    reg [31:0] init_13_reg = 32'd0;
    reg [31:0] init_14_reg = 32'd0;
    reg [31:0] init_15_reg = 32'd0;

    // Round counter (0..20)
    reg [4:0] round_cnt_reg = 5'd0, round_cnt_next;

    // FSM state
    reg [1:0] core_fsm_reg = CORE_IDLE, core_fsm_next;

    // Done pulse register
    reg done_reg = 1'b0, done_next;

    // Finalized output registers
    reg [511:0] state_out_reg = {512{1'b0}};

    //-------------------------------------------------------------------------
    // QR instance wires
    //-------------------------------------------------------------------------
    // QR inputs (muxed between column and diagonal)
    wire [31:0] qr0_a_in, qr0_b_in, qr0_c_in, qr0_d_in;
    wire [31:0] qr1_a_in, qr1_b_in, qr1_c_in, qr1_d_in;
    wire [31:0] qr2_a_in, qr2_b_in, qr2_c_in, qr2_d_in;
    wire [31:0] qr3_a_in, qr3_b_in, qr3_c_in, qr3_d_in;

    // QR outputs
    wire [31:0] qr0_a_out, qr0_b_out, qr0_c_out, qr0_d_out;
    wire [31:0] qr1_a_out, qr1_b_out, qr1_c_out, qr1_d_out;
    wire [31:0] qr2_a_out, qr2_b_out, qr2_c_out, qr2_d_out;
    wire [31:0] qr3_a_out, qr3_b_out, qr3_c_out, qr3_d_out;

    // Round type: 0 = column, 1 = diagonal
    wire round_is_diagonal = round_cnt_reg[0];

    //-------------------------------------------------------------------------
    // QR input muxing (column vs diagonal)
    //-------------------------------------------------------------------------
    // QR0: Column => (0,4,8,12)  Diagonal => (0,5,10,15)
    assign qr0_a_in = state_00_reg;
    assign qr0_b_in = round_is_diagonal ? state_05_reg : state_04_reg;
    assign qr0_c_in = round_is_diagonal ? state_10_reg : state_08_reg;
    assign qr0_d_in = round_is_diagonal ? state_15_reg : state_12_reg;

    // QR1: Column => (1,5,9,13)  Diagonal => (1,6,11,12)
    assign qr1_a_in = state_01_reg;
    assign qr1_b_in = round_is_diagonal ? state_06_reg : state_05_reg;
    assign qr1_c_in = round_is_diagonal ? state_11_reg : state_09_reg;
    assign qr1_d_in = round_is_diagonal ? state_12_reg : state_13_reg;

    // QR2: Column => (2,6,10,14)  Diagonal => (2,7,8,13)
    assign qr2_a_in = state_02_reg;
    assign qr2_b_in = round_is_diagonal ? state_07_reg : state_06_reg;
    assign qr2_c_in = round_is_diagonal ? state_08_reg : state_10_reg;
    assign qr2_d_in = round_is_diagonal ? state_13_reg : state_14_reg;

    // QR3: Column => (3,7,11,15)  Diagonal => (3,4,9,14)
    assign qr3_a_in = state_03_reg;
    assign qr3_b_in = round_is_diagonal ? state_04_reg : state_07_reg;
    assign qr3_c_in = round_is_diagonal ? state_09_reg : state_11_reg;
    assign qr3_d_in = round_is_diagonal ? state_14_reg : state_15_reg;

    //-------------------------------------------------------------------------
    // Instantiate 4 quarter-round units
    //-------------------------------------------------------------------------
    chacha20_qr qr_inst_0
    (
        .a_i (qr0_a_in),
        .b_i (qr0_b_in),
        .c_i (qr0_c_in),
        .d_i (qr0_d_in),
        .a_o (qr0_a_out),
        .b_o (qr0_b_out),
        .c_o (qr0_c_out),
        .d_o (qr0_d_out)
    );

    chacha20_qr qr_inst_1
    (
        .a_i (qr1_a_in),
        .b_i (qr1_b_in),
        .c_i (qr1_c_in),
        .d_i (qr1_d_in),
        .a_o (qr1_a_out),
        .b_o (qr1_b_out),
        .c_o (qr1_c_out),
        .d_o (qr1_d_out)
    );

    chacha20_qr qr_inst_2
    (
        .a_i (qr2_a_in),
        .b_i (qr2_b_in),
        .c_i (qr2_c_in),
        .d_i (qr2_d_in),
        .a_o (qr2_a_out),
        .b_o (qr2_b_out),
        .c_o (qr2_c_out),
        .d_o (qr2_d_out)
    );

    chacha20_qr qr_inst_3
    (
        .a_i (qr3_a_in),
        .b_i (qr3_b_in),
        .c_i (qr3_c_in),
        .d_i (qr3_d_in),
        .a_o (qr3_a_out),
        .b_o (qr3_b_out),
        .c_o (qr3_c_out),
        .d_o (qr3_d_out)
    );

    //-------------------------------------------------------------------------
    // Output muxing: map QR outputs back to state registers
    //-------------------------------------------------------------------------
    // In column mode, the mapping is straightforward:
    //   QR0 writes (0,4,8,12), QR1 writes (1,5,9,13),
    //   QR2 writes (2,6,10,14), QR3 writes (3,7,11,15)
    // In diagonal mode:
    //   QR0 writes (0,5,10,15), QR1 writes (1,6,11,12),
    //   QR2 writes (2,7,8,13),  QR3 writes (3,4,9,14)

    wire [31:0] next_00 = round_is_diagonal ? qr0_a_out : qr0_a_out;
    wire [31:0] next_01 = round_is_diagonal ? qr1_a_out : qr1_a_out;
    wire [31:0] next_02 = round_is_diagonal ? qr2_a_out : qr2_a_out;
    wire [31:0] next_03 = round_is_diagonal ? qr3_a_out : qr3_a_out;

    wire [31:0] next_04 = round_is_diagonal ? qr3_b_out : qr0_b_out;
    wire [31:0] next_05 = round_is_diagonal ? qr0_b_out : qr1_b_out;
    wire [31:0] next_06 = round_is_diagonal ? qr1_b_out : qr2_b_out;
    wire [31:0] next_07 = round_is_diagonal ? qr2_b_out : qr3_b_out;

    wire [31:0] next_08 = round_is_diagonal ? qr2_c_out : qr0_c_out;
    wire [31:0] next_09 = round_is_diagonal ? qr3_c_out : qr1_c_out;
    wire [31:0] next_10 = round_is_diagonal ? qr0_c_out : qr2_c_out;
    wire [31:0] next_11 = round_is_diagonal ? qr1_c_out : qr3_c_out;

    wire [31:0] next_12 = round_is_diagonal ? qr1_d_out : qr0_d_out;
    wire [31:0] next_13 = round_is_diagonal ? qr2_d_out : qr1_d_out;
    wire [31:0] next_14 = round_is_diagonal ? qr3_d_out : qr2_d_out;
    wire [31:0] next_15 = round_is_diagonal ? qr0_d_out : qr3_d_out;

    //-------------------------------------------------------------------------
    // Combinational logic: next-state decode
    //-------------------------------------------------------------------------
    always @* begin
        // Default: hold all state
        core_fsm_next  = core_fsm_reg;
        round_cnt_next = round_cnt_reg;
        done_next      = 1'b0;

        state_00_next = state_00_reg;
        state_01_next = state_01_reg;
        state_02_next = state_02_reg;
        state_03_next = state_03_reg;
        state_04_next = state_04_reg;
        state_05_next = state_05_reg;
        state_06_next = state_06_reg;
        state_07_next = state_07_reg;
        state_08_next = state_08_reg;
        state_09_next = state_09_reg;
        state_10_next = state_10_reg;
        state_11_next = state_11_reg;
        state_12_next = state_12_reg;
        state_13_next = state_13_reg;
        state_14_next = state_14_reg;
        state_15_next = state_15_reg;

        case (core_fsm_reg)
            CORE_IDLE: begin
                if (start_i) begin
                    // Initialize state matrix
                    state_00_next = CONST_EXPA;
                    state_01_next = CONST_ND_3;
                    state_02_next = CONST_2_BY;
                    state_03_next = CONST_TE_K;
                    state_04_next = bswap32(key_i[255:224]);
                    state_05_next = bswap32(key_i[223:192]);
                    state_06_next = bswap32(key_i[191:160]);
                    state_07_next = bswap32(key_i[159:128]);
                    state_08_next = bswap32(key_i[127:96]);
                    state_09_next = bswap32(key_i[95:64]);
                    state_10_next = bswap32(key_i[63:32]);
                    state_11_next = bswap32(key_i[31:0]);
                    state_12_next = counter_i;
                    state_13_next = bswap32(nonce_i[95:64]);
                    state_14_next = bswap32(nonce_i[63:32]);
                    state_15_next = bswap32(nonce_i[31:0]);

                    round_cnt_next = 5'd0;
                    core_fsm_next  = CORE_ROUND;
                end
            end

            CORE_ROUND: begin
                // Apply QR results to state
                state_00_next = next_00;
                state_01_next = next_01;
                state_02_next = next_02;
                state_03_next = next_03;
                state_04_next = next_04;
                state_05_next = next_05;
                state_06_next = next_06;
                state_07_next = next_07;
                state_08_next = next_08;
                state_09_next = next_09;
                state_10_next = next_10;
                state_11_next = next_11;
                state_12_next = next_12;
                state_13_next = next_13;
                state_14_next = next_14;
                state_15_next = next_15;

                if (round_cnt_reg == 5'd19) begin
                    core_fsm_next = CORE_FINALIZE;
                end else begin
                    round_cnt_next = round_cnt_reg + 5'd1;
                end
            end

            CORE_FINALIZE: begin
                done_next = 1'b1;
                core_fsm_next = CORE_IDLE;
            end

            default: begin
                core_fsm_next = CORE_IDLE;
            end
        endcase
    end

    //-------------------------------------------------------------------------
    // Sequential logic: register updates
    //-------------------------------------------------------------------------
    always @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            core_fsm_reg  <= CORE_IDLE;
            round_cnt_reg <= 5'd0;
            done_reg      <= 1'b0;
            state_00_reg  <= 32'd0;
            state_01_reg  <= 32'd0;
            state_02_reg  <= 32'd0;
            state_03_reg  <= 32'd0;
            state_04_reg  <= 32'd0;
            state_05_reg  <= 32'd0;
            state_06_reg  <= 32'd0;
            state_07_reg  <= 32'd0;
            state_08_reg  <= 32'd0;
            state_09_reg  <= 32'd0;
            state_10_reg  <= 32'd0;
            state_11_reg  <= 32'd0;
            state_12_reg  <= 32'd0;
            state_13_reg  <= 32'd0;
            state_14_reg  <= 32'd0;
            state_15_reg  <= 32'd0;
            state_out_reg <= {512{1'b0}};
        end else begin
            core_fsm_reg  <= core_fsm_next;
            round_cnt_reg <= round_cnt_next;
            done_reg      <= done_next;
            state_00_reg  <= state_00_next;
            state_01_reg  <= state_01_next;
            state_02_reg  <= state_02_next;
            state_03_reg  <= state_03_next;
            state_04_reg  <= state_04_next;
            state_05_reg  <= state_05_next;
            state_06_reg  <= state_06_next;
            state_07_reg  <= state_07_next;
            state_08_reg  <= state_08_next;
            state_09_reg  <= state_09_next;
            state_10_reg  <= state_10_next;
            state_11_reg  <= state_11_next;
            state_12_reg  <= state_12_next;
            state_13_reg  <= state_13_next;
            state_14_reg  <= state_14_next;
            state_15_reg  <= state_15_next;

            // Latch initial state on transition from IDLE to ROUND
            if (core_fsm_reg == CORE_IDLE && core_fsm_next == CORE_ROUND) begin
                init_00_reg <= CONST_EXPA;
                init_01_reg <= CONST_ND_3;
                init_02_reg <= CONST_2_BY;
                init_03_reg <= CONST_TE_K;
                init_04_reg <= bswap32(key_i[255:224]);
                init_05_reg <= bswap32(key_i[223:192]);
                init_06_reg <= bswap32(key_i[191:160]);
                init_07_reg <= bswap32(key_i[159:128]);
                init_08_reg <= bswap32(key_i[127:96]);
                init_09_reg <= bswap32(key_i[95:64]);
                init_10_reg <= bswap32(key_i[63:32]);
                init_11_reg <= bswap32(key_i[31:0]);
                init_12_reg <= counter_i;
                init_13_reg <= bswap32(nonce_i[95:64]);
                init_14_reg <= bswap32(nonce_i[63:32]);
                init_15_reg <= bswap32(nonce_i[31:0]);
            end

            // In FINALIZE, compute state + init_state and output
            if (core_fsm_next == CORE_FINALIZE) begin
                state_out_reg <= {
                    state_15_next + init_15_reg,
                    state_14_next + init_14_reg,
                    state_13_next + init_13_reg,
                    state_12_next + init_12_reg,
                    state_11_next + init_11_reg,
                    state_10_next + init_10_reg,
                    state_09_next + init_09_reg,
                    state_08_next + init_08_reg,
                    state_07_next + init_07_reg,
                    state_06_next + init_06_reg,
                    state_05_next + init_05_reg,
                    state_04_next + init_04_reg,
                    state_03_next + init_03_reg,
                    state_02_next + init_02_reg,
                    state_01_next + init_01_reg,
                    state_00_next + init_00_reg
                };
            end
        end
    end

    //-------------------------------------------------------------------------
    // Output assignments
    //-------------------------------------------------------------------------
    assign state_o = state_out_reg;
    assign done_o  = done_reg;
    assign busy_o  = (core_fsm_reg != CORE_IDLE) ? 1'b1 : 1'b0;

endmodule

`resetall

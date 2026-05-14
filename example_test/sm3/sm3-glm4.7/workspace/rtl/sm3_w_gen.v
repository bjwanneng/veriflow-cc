// ============================================================
// sm3_w_gen - SM3 message expansion (16-deep shift register)
//   - load_en: w_regs[0..15] <= msg_block (big-endian)
//   - calc_en: shift left by 1, insert P1(W0^W7^ROL(W13,15))^ROL(W3,7)^W10
//   - outputs: w_j = W_regs[0], w_prime_j = W_regs[0] ^ W_regs[4]
//   - SYNC active-LOW reset rst_n
// ============================================================
`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_w_gen (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]   round_cnt,
    output wire [31:0]  w_j,
    output wire [31:0]  w_prime_j
);

    // ------------------------------------------------------------
    // 16-deep shift register holding W[0..15]
    // ------------------------------------------------------------
    reg [31:0] w_regs [0:15];

    // ------------------------------------------------------------
    // Combinational: next_w = P1(W0 ^ W7 ^ ROL(W13,15)) ^ ROL(W3,7) ^ W10
    //   ROL(a, 15) = {a[16:0], a[31:17]}
    //   ROL(a, 23) = {a[ 8:0], a[31: 9]}
    //   ROL(a,  7) = {a[24:0], a[31:25]}
    // ------------------------------------------------------------
    wire [31:0] rol13_15;
    wire [31:0] x_w;
    wire [31:0] p1_x_w;
    wire [31:0] rol3_7;
    wire [31:0] next_w;

    assign rol13_15 = {w_regs[13][16:0], w_regs[13][31:17]};
    assign x_w      = w_regs[0] ^ w_regs[7] ^ rol13_15;
    assign p1_x_w   = x_w
                    ^ {x_w[16:0], x_w[31:17]}
                    ^ {x_w[ 8:0], x_w[31: 9]};
    assign rol3_7   = {w_regs[3][24:0], w_regs[3][31:25]};
    assign next_w   = p1_x_w ^ rol3_7 ^ w_regs[10];

    // ------------------------------------------------------------
    // Sequential: load wins over shift on the same cycle.
    // SYNCHRONOUS active-LOW reset.
    // ------------------------------------------------------------
    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1)
                w_regs[i] <= 32'h0000_0000;
        end else if (load_en) begin
            // Big-endian load: w_regs[0] = msg_block[511:480], ...
            for (i = 0; i < 16; i = i + 1)
                w_regs[i] <= msg_block[511 - 32*i -: 32];
        end else if (calc_en) begin
            for (i = 0; i < 15; i = i + 1)
                w_regs[i] <= w_regs[i+1];
            w_regs[15] <= next_w;
        end
    end

    // ------------------------------------------------------------
    // Combinational outputs
    // ------------------------------------------------------------
    assign w_j       = w_regs[0];
    assign w_prime_j = w_regs[0] ^ w_regs[4];

    // round_cnt is part of the interface contract but not used by the
    // recurrence; tied off here to keep the port visible.
    /* verilator lint_off UNUSED */
    wire [5:0] unused_round_cnt = round_cnt;
    /* verilator lint_on UNUSED */

endmodule

`resetall

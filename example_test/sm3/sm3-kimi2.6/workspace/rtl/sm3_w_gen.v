// -----------------------------------------------------------------------------
// File   : sm3_w_gen.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 message expansion module. Uses a 16-stage 32-bit shift register to
//   dynamically generate W_j and W'_j for each of the 64 compression rounds.
//   Loads a 512-bit message block on load_en, then shifts and computes next_W
//   using the P1 permutation on each calc_en cycle.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_w_gen
(
    input  wire              clk,
    input  wire              rst,
    input  wire              load_en,
    input  wire              calc_en,
    input  wire [511:0]      msg_block,
    input  wire [5:0]        round_cnt,
    output wire [31:0]       w_j,
    output wire [31:0]       w_prime_j
);

    // -------------------------------------------------------------------------
    // Internal signals
    // -------------------------------------------------------------------------
    reg [31:0] w_reg [0:15];
    reg [31:0] next_w_reg [0:15];

    reg [31:0] w_j_next;
    reg [31:0] w_prime_j_next;

    integer    i;
    reg [31:0] next_W;
    reg [31:0] p1_in;
    reg [31:0] p1_out;

    // -------------------------------------------------------------------------
    // Combinational logic: compute next state of shift register and outputs
    // -------------------------------------------------------------------------
    always @* begin
        // Default: hold current values
        for (i = 0; i < 16; i = i + 1) begin
            next_w_reg[i] = w_reg[i];
        end

        if (load_en) begin
            // Load 512-bit msg_block as 16 big-endian 32-bit words
            next_w_reg[0]  = msg_block[511:480];
            next_w_reg[1]  = msg_block[479:448];
            next_w_reg[2]  = msg_block[447:416];
            next_w_reg[3]  = msg_block[415:384];
            next_w_reg[4]  = msg_block[383:352];
            next_w_reg[5]  = msg_block[351:320];
            next_w_reg[6]  = msg_block[319:288];
            next_w_reg[7]  = msg_block[287:256];
            next_w_reg[8]  = msg_block[255:224];
            next_w_reg[9]  = msg_block[223:192];
            next_w_reg[10] = msg_block[191:160];
            next_w_reg[11] = msg_block[159:128];
            next_w_reg[12] = msg_block[127:96];
            next_w_reg[13] = msg_block[95:64];
            next_w_reg[14] = msg_block[63:32];
            next_w_reg[15] = msg_block[31:0];
        end else if (calc_en) begin
            // Compute next_W using SM3 message expansion formula
            // P1(X) = X ^ ROL(X, 15) ^ ROL(X, 23)
            p1_in  = w_reg[0] ^ w_reg[7] ^ {w_reg[13][16:0], w_reg[13][31:17]};
            p1_out = p1_in ^ {p1_in[16:0], p1_in[31:17]} ^ {p1_in[8:0], p1_in[31:9]};
            next_W = p1_out ^ {w_reg[3][24:0], w_reg[3][31:25]} ^ w_reg[10];

            // Shift left: w_reg[i] = w_reg[i+1] for i = 0..14
            for (i = 0; i < 15; i = i + 1) begin
                next_w_reg[i] = w_reg[i + 1];
            end
            next_w_reg[15] = next_W;
        end
    end

    // -------------------------------------------------------------------------
    // Sequential logic: register updates with synchronous active-high reset
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        for (i = 0; i < 16; i = i + 1) begin
            w_reg[i] = next_w_reg[i];
        end

        if (rst) begin
            for (i = 0; i < 16; i = i + 1) begin
                w_reg[i] = 32'd0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // Combinational outputs: current register head BEFORE shift
    // -------------------------------------------------------------------------
    assign w_j       = w_reg[0];
    assign w_prime_j = w_reg[0] ^ w_reg[4];

endmodule

`resetall

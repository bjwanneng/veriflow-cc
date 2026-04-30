// -----------------------------------------------------------------------------
// File   : sm3_w_gen.v
// Author : Zhang Wei
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 message expansion module. Uses a 16-entry shift register (w_reg[0:15])
//   to dynamically generate W_j and W'_j for each round per GM/T 0004-2012.
//   On load_en, loads 512-bit msg_block in big-endian order. On calc_en,
//   shifts left and computes next W_j using the SM3 recurrence relation for
//   rounds j >= 16. Outputs w_j = w_reg[0] and w_prime_j = w_reg[0] ^ w_reg[4]
//   combinatorially each cycle.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  Zhang Wei  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_w_gen
(
    input  wire         clk,
    input  wire         rst,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]   round_cnt,
    output wire [31:0]  w_j,
    output wire [31:0]  w_prime_j
);

    /////////////////
    //  Registers  //
    /////////////////

    // 16-entry shift register for W expansion
    reg [31:0] w_reg[0:15];

    /////////////////
    //    Wires    //
    /////////////////

    // Combinational intermediate signals for next_W computation
    wire [31:0] t0;
    wire [31:0] t1;
    wire [31:0] t2;
    wire [31:0] next_w;

    // Loop variable for procedural for-loops
    integer i;

    //////////////////////////////
    //  Combinational Outputs   //
    //////////////////////////////

    assign w_j       = w_reg[0];
    assign w_prime_j = w_reg[0] ^ w_reg[4];

    //////////////////////////////
    //  next_W Computation      //
    //////////////////////////////

    // t0 = w_reg[0] ^ w_reg[7] ^ ROL(w_reg[13], 15)
    assign t0 = w_reg[0] ^ w_reg[7] ^ {w_reg[13][16:0], w_reg[13][31:17]};

    // t1 = P1(t0) = t0 ^ ROL(t0, 15) ^ ROL(t0, 23)
    assign t1 = t0 ^ {t0[16:0], t0[31:17]} ^ {t0[8:0], t0[31:9]};

    // t2 = ROL(w_reg[3], 7)
    assign t2 = {w_reg[3][24:0], w_reg[3][31:25]};

    // next_W = t1 ^ t2 ^ w_reg[10] — always compute W_{j+16} for j=0..62
    assign next_w = t1 ^ t2 ^ w_reg[10];

    //////////////////////////////
    //  Sequential w_reg Update //
    //////////////////////////////

    always @(posedge clk) begin
        if (load_en) begin
            // Load 16 big-endian 32-bit words from msg_block
            w_reg[0]  = msg_block[511:480]; // blocking: iverilog index race
            w_reg[1]  = msg_block[479:448]; // blocking: iverilog index race
            w_reg[2]  = msg_block[447:416]; // blocking: iverilog index race
            w_reg[3]  = msg_block[415:384]; // blocking: iverilog index race
            w_reg[4]  = msg_block[383:352]; // blocking: iverilog index race
            w_reg[5]  = msg_block[351:320]; // blocking: iverilog index race
            w_reg[6]  = msg_block[319:288]; // blocking: iverilog index race
            w_reg[7]  = msg_block[287:256]; // blocking: iverilog index race
            w_reg[8]  = msg_block[255:224]; // blocking: iverilog index race
            w_reg[9]  = msg_block[223:192]; // blocking: iverilog index race
            w_reg[10] = msg_block[191:160]; // blocking: iverilog index race
            w_reg[11] = msg_block[159:128]; // blocking: iverilog index race
            w_reg[12] = msg_block[127:96];  // blocking: iverilog index race
            w_reg[13] = msg_block[95:64];   // blocking: iverilog index race
            w_reg[14] = msg_block[63:32];   // blocking: iverilog index race
            w_reg[15] = msg_block[31:0];    // blocking: iverilog index race
        end else if (calc_en) begin
            // Shift left: w_reg[0:14] <= w_reg[1:15]
            for (i = 0; i < 15; i = i + 1) begin
                w_reg[i] = w_reg[i+1]; // blocking: iverilog index race
            end
            // Insert computed next_W at position 15
            w_reg[15] = next_w; // blocking: iverilog index race
        end

        if (rst) begin
            for (i = 0; i < 16; i = i + 1) begin
                w_reg[i] = 32'd0; // blocking: iverilog index race
            end
        end
    end

endmodule

`resetall

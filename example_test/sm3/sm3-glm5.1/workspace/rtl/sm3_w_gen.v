//=============================================================================
// sm3_w_gen — SM3 Message Expansion (16-entry sliding window)
//
// Expands a 512-bit message block into W_j and W'_j words over 64 rounds.
// Uses a 16-entry shift register. On load_en, the full 512-bit block is
// loaded big-endian into w_reg[0:15]. On each calc_en cycle, outputs
// w_j = w_reg[0], w'_j = w_reg[0] ^ w_reg[4], computes the next W via
// the SM3 recurrence P1(W[j]^W[j+7]^ROL(W[j+13],15)) ^ ROL(W[j+3],7) ^ W[j+10],
// and shifts the window.
//
// Clock domain: clk_core @ 150 MHz, sync active-low reset
//=============================================================================

`resetall
`timescale 1ns/1ps
`default_nettype none

module sm3_w_gen (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        load_en,
    input  wire        calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]  round_cnt,
    output wire [31:0] w_j,
    output wire [31:0] w_prime_j
);

    //-------------------------------------------------------------------------
    // 16-entry shift register (sliding window over W[0..67])
    //-------------------------------------------------------------------------
    reg [31:0] w_reg [0:15];

    //-------------------------------------------------------------------------
    // Combinational outputs
    //-------------------------------------------------------------------------
    assign w_j       = w_reg[0];
    assign w_prime_j = w_reg[0] ^ w_reg[4];

    //-------------------------------------------------------------------------
    // Next-W computation (combinational)
    //
    // next_W = P1( w_reg[0] ^ w_reg[7] ^ ROL(w_reg[13],15) )
    //          ^ ROL( w_reg[3], 7 )
    //          ^ w_reg[10]
    //
    // P1(x) = x ^ ROL(x,15) ^ ROL(x,23)
    //-------------------------------------------------------------------------
    wire [31:0] t_xor_in;
    wire [31:0] t_p1_in;
    wire [31:0] t_rol3_7;
    wire [31:0] next_w;

    // t_xor_in = w_reg[0] ^ w_reg[7] ^ ROL(w_reg[13], 15)
    assign t_xor_in = w_reg[0]
                    ^ w_reg[7]
                    ^ {w_reg[13][16:0], w_reg[13][31:17]};

    // t_p1_in = P1(t_xor_in) = t_xor_in ^ ROL(t_xor_in,15) ^ ROL(t_xor_in,23)
    assign t_p1_in = t_xor_in
                   ^ {t_xor_in[16:0], t_xor_in[31:17]}
                   ^ {t_xor_in[8:0],  t_xor_in[31:9]};

    // t_rol3_7 = ROL(w_reg[3], 7)
    assign t_rol3_7 = {w_reg[3][24:0], w_reg[3][31:25]};

    assign next_w = t_p1_in ^ t_rol3_7 ^ w_reg[10];

    //-------------------------------------------------------------------------
    // Sequential: load / shift
    //-------------------------------------------------------------------------
    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1) begin
                w_reg[i] <= 32'd0;
            end
        end
        else if (load_en) begin
            // Big-endian parse: msg_block[511:480] → w_reg[0], … , msg_block[31:0] → w_reg[15]
            for (i = 0; i < 16; i = i + 1) begin
                w_reg[i] <= msg_block[511 - 32*i -: 32];
            end
        end
        else if (calc_en) begin
            // Shift left by one: w_reg[0..14] <= w_reg[1..15]
            for (i = 0; i < 15; i = i + 1) begin
                w_reg[i] <= w_reg[i+1];
            end
            w_reg[15] <= next_w;
        end
    end

endmodule

`default_nettype wire

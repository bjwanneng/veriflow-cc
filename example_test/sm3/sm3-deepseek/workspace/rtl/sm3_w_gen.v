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

    // 16-entry x 32-bit shift register stored as flat 512-bit register.
    // w_reg[511:480] = W_{j}    (oldest, consumed this cycle)
    // w_reg[479:448] = W_{j+1}
    // ...
    // w_reg[ 31:0  ] = W_{j+15} (newest)
    reg [511:0] w_reg = 512'd0;

    // Combinational decomposition: individual 32-bit words for readability
    wire [31:0] w0  = w_reg[511:480];
    wire [31:0] w1  = w_reg[479:448];
    wire [31:0] w2  = w_reg[447:416];
    wire [31:0] w3  = w_reg[415:384];
    wire [31:0] w4  = w_reg[383:352];
    wire [31:0] w5  = w_reg[351:320];
    wire [31:0] w6  = w_reg[319:288];
    wire [31:0] w7  = w_reg[287:256];
    wire [31:0] w8  = w_reg[255:224];
    wire [31:0] w9  = w_reg[223:192];
    wire [31:0] w10 = w_reg[191:160];
    wire [31:0] w11 = w_reg[159:128];
    wire [31:0] w12 = w_reg[127:96];
    wire [31:0] w13 = w_reg[95:64];
    wire [31:0] w14 = w_reg[63:32];
    wire [31:0] w15 = w_reg[31:0];

    // ========================================================================
    // Combinational: next_W computation (SM3 message expansion formula)
    //
    // For j >= 16 (shift register holds W_{j-16}..W_{j-1}):
    //   W_{j-16} = w0,  W_{j-9}  = w7,  W_{j-3}  = w13
    //   W_{j-13} = w3,  W_{j-6}  = w10
    //
    // term   = W_{j-16} ^ W_{j-9} ^ ROL(W_{j-3}, 15)
    //        = w0 ^ w7 ^ ROL(w13, 15)
    // P1(X)  = X ^ ROL(X, 15) ^ ROL(X, 23)
    // next_W = P1(term) ^ ROL(W_{j-13}, 7) ^ W_{j-6}
    //        = P1(term) ^ ROL(w3, 7) ^ w10
    // ========================================================================

    // ROL by 7:  {data[24:0], data[31:25]}
    wire [31:0] rol_w3_7   = {w3[24:0],  w3[31:25]};

    // ROL by 15: {data[16:0], data[31:17]}
    wire [31:0] rol_w13_15 = {w13[16:0], w13[31:17]};

    // term = w0 ^ w7 ^ ROL(w13, 15)
    wire [31:0] term;
    assign term = w0 ^ w7 ^ rol_w13_15;

    // ROL(term, 15) = {term[16:0], term[31:17]}
    wire [31:0] rol_term_15 = {term[16:0], term[31:17]};

    // ROL(term, 23) = {term[8:0], term[31:9]}
    wire [31:0] rol_term_23 = {term[8:0],  term[31:9]};

    // P1(term) = term ^ ROL(term, 15) ^ ROL(term, 23)
    wire [31:0] p1_result;
    assign p1_result = term ^ rol_term_15 ^ rol_term_23;

    // next_W = P1(term) ^ ROL(w3, 7) ^ w10
    wire [31:0] next_w;
    assign next_w = p1_result ^ rol_w3_7 ^ w10;

    // Shifted register for next cycle: discard w0, shift left, insert next_w
    // {w_reg[479:0], next_w} = {w1,w2,...,w15, next_w}
    wire [511:0] w_shifted;
    assign w_shifted = {w_reg[479:0], next_w};

    // ========================================================================
    // Sequential: w_reg update
    //
    // load_en:  load msg_block (big-endian) into w_reg
    // calc_en:  shift left by one 32-bit word, fill w_reg[31:0] with next_w
    // Reset:    clear w_reg to zero (active-low synchronous, overrides all)
    // ========================================================================
    always @(posedge clk) begin
        if (load_en)
            w_reg <= msg_block;
        else if (calc_en)
            w_reg <= w_shifted;
        if (!rst_n)
            w_reg <= 512'd0;
    end

    // ========================================================================
    // Combinational outputs (same-cycle visible)
    //   w_j       = W_j          = w_reg[511:480] = w0
    //   w_prime_j = W_j ^ W_{j+4} = w0 ^ w4
    // ========================================================================
    assign w_j       = w_reg[511:480];
    assign w_prime_j = w_reg[511:480] ^ w_reg[383:352];

endmodule

`resetall

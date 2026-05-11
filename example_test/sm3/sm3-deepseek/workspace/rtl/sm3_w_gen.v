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
    // 16-entry x 32-bit shift register stored as flat 512-bit register
    reg [511:0] w_reg;

    // Decompose w_reg into individual 32-bit words for combinational logic
    wire [31:0] w0, w1, w2, w3, w4, w5, w6, w7, w8, w9, w10, w11, w12, w13, w14, w15;
    assign {w0, w1, w2, w3, w4, w5, w6, w7, w8, w9, w10, w11, w12, w13, w14, w15} = w_reg;

    // ROL(w_reg[13], 15) = {w13[16:0], w13[31:17]}
    wire [31:0] rol_w13_15;
    assign rol_w13_15 = {w13[16:0], w13[31:17]};

    // X = w0 ^ w7 ^ ROL(w_reg[13], 15)
    wire [31:0] p1_input;
    assign p1_input = w0 ^ w7 ^ rol_w13_15;

    // P1(X) = X ^ ROL(X, 15) ^ ROL(X, 23)
    //   ROL(X, 15) = {X[16:0], X[31:17]}
    //   ROL(X, 23) = {X[8:0], X[31:9]}
    wire [31:0] p1_result;
    assign p1_result = p1_input ^ {p1_input[16:0], p1_input[31:17]} ^ {p1_input[8:0], p1_input[31:9]};

    // ROL(w_reg[3], 7) = {w3[24:0], w3[31:25]}
    wire [31:0] rol_w3_7;
    assign rol_w3_7 = {w3[24:0], w3[31:25]};

    // next_W = P1_result ^ ROL(w_reg[3], 7) ^ w_reg[10]
    wire [31:0] next_w;
    assign next_w = p1_result ^ rol_w3_7 ^ w10;

    // Shifted register: {w_reg[1:15], next_W}
    wire [511:0] w_shifted;
    assign w_shifted = {w_reg[479:0], next_w};

    // Sequential block: register update
    always @(posedge clk) begin
        if (load_en)
            w_reg <= msg_block;
        else if (calc_en)
            w_reg <= w_shifted;
        if (!rst_n)
            w_reg <= 512'd0;
    end

    // Combinational outputs
    assign w_j       = w_reg[511:480];
    assign w_prime_j = w_reg[511:480] ^ w_reg[383:352];

endmodule

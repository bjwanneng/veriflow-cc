`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_key_expansion (
    input  wire [127:0] key_in,
    input  wire [3:0]   round_num,
    output wire [127:0] round_key_out
);

    // -----------------------------------------------------------------------
    // Round constants (FIPS 197 Section 5.2)
    // -----------------------------------------------------------------------
    localparam [7:0] RCON_0  = 8'h00;
    localparam [7:0] RCON_1  = 8'h01;
    localparam [7:0] RCON_2  = 8'h02;
    localparam [7:0] RCON_3  = 8'h04;
    localparam [7:0] RCON_4  = 8'h08;
    localparam [7:0] RCON_5  = 8'h10;
    localparam [7:0] RCON_6  = 8'h20;
    localparam [7:0] RCON_7  = 8'h40;
    localparam [7:0] RCON_8  = 8'h80;
    localparam [7:0] RCON_9  = 8'h1b;
    localparam [7:0] RCON_10 = 8'h36;

    // -----------------------------------------------------------------------
    // Rcon lookup function: returns 8'h00 for index 0, appropriate constant
    // for 1..10, and 8'h00 for anything else.
    // -----------------------------------------------------------------------
    function [7:0] rcon_lookup;
        input [3:0] idx;
        begin
            case (idx)
                4'd0:  rcon_lookup = RCON_0;
                4'd1:  rcon_lookup = RCON_1;
                4'd2:  rcon_lookup = RCON_2;
                4'd3:  rcon_lookup = RCON_3;
                4'd4:  rcon_lookup = RCON_4;
                4'd5:  rcon_lookup = RCON_5;
                4'd6:  rcon_lookup = RCON_6;
                4'd7:  rcon_lookup = RCON_7;
                4'd8:  rcon_lookup = RCON_8;
                4'd9:  rcon_lookup = RCON_9;
                4'd10: rcon_lookup = RCON_10;
                default: rcon_lookup = 8'h00;
            endcase
        end
    endfunction

    // -----------------------------------------------------------------------
    // Extract initial 4 x 32-bit words from the 128-bit key
    //   w0 = key_in[127:96], w1 = key_in[95:64],
    //   w2 = key_in[63:32],  w3 = key_in[31:0]
    // -----------------------------------------------------------------------
    wire [31:0] w0_init = key_in[127:96];
    wire [31:0] w1_init = key_in[95:64];
    wire [31:0] w2_init = key_in[63:32];
    wire [31:0] w3_init = key_in[31:0];

    // -----------------------------------------------------------------------
    // Iteratively compute key expansion for rounds 1..10.
    // Each round produces 4 new words (w0..w3) from the previous round's
    // words via: RotWord -> SubWord -> Rcon XOR -> chained XOR.
    //
    // Since this is combinational, all 10 rounds are computed in parallel
    // and a final mux selects the output based on round_num.
    //
    // 40 S-Box instances total (4 per round for SubWord).
    // -----------------------------------------------------------------------

    // Per-round intermediate wires
    wire [31:0] rotw     [1:10];
    wire [7:0]  sb_out_0 [1:10];
    wire [7:0]  sb_out_1 [1:10];
    wire [7:0]  sb_out_2 [1:10];
    wire [7:0]  sb_out_3 [1:10];
    wire [31:0] subw     [1:10];
    wire [31:0] tempw    [1:10];
    wire [31:0] w0_r     [1:10];
    wire [31:0] w1_r     [1:10];
    wire [31:0] w2_r     [1:10];
    wire [31:0] w3_r     [1:10];

    // Previous round's w0, w1, w2, w3 (chained across rounds)
    wire [31:0] w0_prev [1:10];
    wire [31:0] w1_prev [1:10];
    wire [31:0] w2_prev [1:10];
    wire [31:0] w3_prev [1:10];

    assign w0_prev[1]  = w0_init;
    assign w1_prev[1]  = w1_init;
    assign w2_prev[1]  = w2_init;
    assign w3_prev[1]  = w3_init;

    assign w0_prev[2]  = w0_r[1];
    assign w1_prev[2]  = w1_r[1];
    assign w2_prev[2]  = w2_r[1];
    assign w3_prev[2]  = w3_r[1];

    assign w0_prev[3]  = w0_r[2];
    assign w1_prev[3]  = w1_r[2];
    assign w2_prev[3]  = w2_r[2];
    assign w3_prev[3]  = w3_r[2];

    assign w0_prev[4]  = w0_r[3];
    assign w1_prev[4]  = w1_r[3];
    assign w2_prev[4]  = w2_r[3];
    assign w3_prev[4]  = w3_r[3];

    assign w0_prev[5]  = w0_r[4];
    assign w1_prev[5]  = w1_r[4];
    assign w2_prev[5]  = w2_r[4];
    assign w3_prev[5]  = w3_r[4];

    assign w0_prev[6]  = w0_r[5];
    assign w1_prev[6]  = w1_r[5];
    assign w2_prev[6]  = w2_r[5];
    assign w3_prev[6]  = w3_r[5];

    assign w0_prev[7]  = w0_r[6];
    assign w1_prev[7]  = w1_r[6];
    assign w2_prev[7]  = w2_r[6];
    assign w3_prev[7]  = w3_r[6];

    assign w0_prev[8]  = w0_r[7];
    assign w1_prev[8]  = w1_r[7];
    assign w2_prev[8]  = w2_r[7];
    assign w3_prev[8]  = w3_r[7];

    assign w0_prev[9]  = w0_r[8];
    assign w1_prev[9]  = w1_r[8];
    assign w2_prev[9]  = w2_r[8];
    assign w3_prev[9]  = w3_r[8];

    assign w0_prev[10] = w0_r[9];
    assign w1_prev[10] = w1_r[9];
    assign w2_prev[10] = w2_r[9];
    assign w3_prev[10] = w3_r[9];

    // -----------------------------------------------------------------------
    // Generate 10 rounds of key expansion
    // -----------------------------------------------------------------------
    genvar r;
    generate
        for (r = 1; r <= 10; r = r + 1) begin : gen_round

            // RotWord: rotate w3_prev left by 8 bits
            assign rotw[r] = {w3_prev[r][23:0], w3_prev[r][31:24]};

            // SubWord: 4 S-Box lookups on each byte of RotWord result
            aes_sbox u_sbox_0 (
                .addr (rotw[r][31:24]),
                .dout (sb_out_0[r])
            );

            aes_sbox u_sbox_1 (
                .addr (rotw[r][23:16]),
                .dout (sb_out_1[r])
            );

            aes_sbox u_sbox_2 (
                .addr (rotw[r][15:8]),
                .dout (sb_out_2[r])
            );

            aes_sbox u_sbox_3 (
                .addr (rotw[r][7:0]),
                .dout (sb_out_3[r])
            );

            // Reassemble SubWord result
            assign subw[r] = {sb_out_0[r], sb_out_1[r], sb_out_2[r], sb_out_3[r]};

            // XOR with Rcon (only affects top byte)
            assign tempw[r] = subw[r] ^ {rcon_lookup(r[3:0]), 24'h0};

            // Key schedule XOR chain
            assign w0_r[r] = w0_prev[r] ^ tempw[r];
            assign w1_r[r] = w1_prev[r] ^ w0_r[r];
            assign w2_r[r] = w2_prev[r] ^ w1_r[r];
            assign w3_r[r] = w3_prev[r] ^ w2_r[r];

        end
    endgenerate

    // -----------------------------------------------------------------------
    // Output mux: select round key based on round_num
    //   round_num=0  => key_in (initial key = round key 0)
    //   round_num=N  => {w0_r[N], w1_r[N], w2_r[N], w3_r[N]} for N=1..10
    // -----------------------------------------------------------------------
    reg [127:0] round_key_next;

    always @(*) begin
        case (round_num)
            4'd0:  round_key_next = key_in;
            4'd1:  round_key_next = {w0_r[1],  w1_r[1],  w2_r[1],  w3_r[1]};
            4'd2:  round_key_next = {w0_r[2],  w1_r[2],  w2_r[2],  w3_r[2]};
            4'd3:  round_key_next = {w0_r[3],  w1_r[3],  w2_r[3],  w3_r[3]};
            4'd4:  round_key_next = {w0_r[4],  w1_r[4],  w2_r[4],  w3_r[4]};
            4'd5:  round_key_next = {w0_r[5],  w1_r[5],  w2_r[5],  w3_r[5]};
            4'd6:  round_key_next = {w0_r[6],  w1_r[6],  w2_r[6],  w3_r[6]};
            4'd7:  round_key_next = {w0_r[7],  w1_r[7],  w2_r[7],  w3_r[7]};
            4'd8:  round_key_next = {w0_r[8],  w1_r[8],  w2_r[8],  w3_r[8]};
            4'd9:  round_key_next = {w0_r[9],  w1_r[9],  w2_r[9],  w3_r[9]};
            4'd10: round_key_next = {w0_r[10], w1_r[10], w2_r[10], w3_r[10]};
            default: round_key_next = key_in;
        endcase
    end

    assign round_key_out = round_key_next;

endmodule

`resetall

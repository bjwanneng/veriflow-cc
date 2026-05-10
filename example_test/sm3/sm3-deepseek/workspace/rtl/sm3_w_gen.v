//=============================================================================
// sm3_w_gen - SM3 Message Expansion (W generation)
// 16-deep x 32-bit shift register with recurrence computation
//=============================================================================

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

    // 16-entry shift register
    reg [31:0] w_reg [0:15];

    // Extract words from msg_block (big-endian: word[0] at [511:480])
    wire [31:0] msg_w0  = msg_block[511:480];
    wire [31:0] msg_w1  = msg_block[479:448];
    wire [31:0] msg_w2  = msg_block[447:416];
    wire [31:0] msg_w3  = msg_block[415:384];
    wire [31:0] msg_w4  = msg_block[383:352];
    wire [31:0] msg_w5  = msg_block[351:320];
    wire [31:0] msg_w6  = msg_block[319:288];
    wire [31:0] msg_w7  = msg_block[287:256];
    wire [31:0] msg_w8  = msg_block[255:224];
    wire [31:0] msg_w9  = msg_block[223:192];
    wire [31:0] msg_w10 = msg_block[191:160];
    wire [31:0] msg_w11 = msg_block[159:128];
    wire [31:0] msg_w12 = msg_block[127:96];
    wire [31:0] msg_w13 = msg_block[95:64];
    wire [31:0] msg_w14 = msg_block[63:32];
    wire [31:0] msg_w15 = msg_block[31:0];

    // ROL function (combinational)
    function [31:0] rol;
        input [31:0] data;
        input [5:0]  n;
    begin
        rol = (data << n) | (data >> (32 - n));
    end
    endfunction

    // Recurrence formula (combinational)
    wire [31:0] recur_inner  = w_reg[0] ^ w_reg[7] ^ rol(w_reg[13], 6'd15);
    wire [31:0] p1_recur     = recur_inner ^ rol(recur_inner, 6'd15)
                                           ^ rol(recur_inner, 6'd23);
    wire [31:0] recur_result = p1_recur ^ rol(w_reg[3], 6'd7) ^ w_reg[10];

    // Combinational w_j bypass mux (round_cnt-based:
    //   rounds 0-15 use msg_block word directly, rounds 16+ use w_reg[0])
    reg [31:0] w_j_bypass;
    always @* begin
        case (round_cnt[3:0])
            4'd0:  w_j_bypass = msg_w0;
            4'd1:  w_j_bypass = msg_w1;
            4'd2:  w_j_bypass = msg_w2;
            4'd3:  w_j_bypass = msg_w3;
            4'd4:  w_j_bypass = msg_w4;
            4'd5:  w_j_bypass = msg_w5;
            4'd6:  w_j_bypass = msg_w6;
            4'd7:  w_j_bypass = msg_w7;
            4'd8:  w_j_bypass = msg_w8;
            4'd9:  w_j_bypass = msg_w9;
            4'd10: w_j_bypass = msg_w10;
            4'd11: w_j_bypass = msg_w11;
            4'd12: w_j_bypass = msg_w12;
            4'd13: w_j_bypass = msg_w13;
            4'd14: w_j_bypass = msg_w14;
            4'd15: w_j_bypass = msg_w15;
        endcase
    end

    // Combinational w_prime_j bypass mux (selects word at round_cnt+4)
    // For round_cnt 0-11: msg_w{round_cnt+4} (M_{4..15})
    // For round_cnt 12-15: w_reg[4] (W_{16..19} already computed)
    reg [31:0] w_prime_j_bypass;
    always @* begin
        case (round_cnt[3:0])
            4'd0:  w_prime_j_bypass = msg_w4;
            4'd1:  w_prime_j_bypass = msg_w5;
            4'd2:  w_prime_j_bypass = msg_w6;
            4'd3:  w_prime_j_bypass = msg_w7;
            4'd4:  w_prime_j_bypass = msg_w8;
            4'd5:  w_prime_j_bypass = msg_w9;
            4'd6:  w_prime_j_bypass = msg_w10;
            4'd7:  w_prime_j_bypass = msg_w11;
            4'd8:  w_prime_j_bypass = msg_w12;
            4'd9:  w_prime_j_bypass = msg_w13;
            4'd10: w_prime_j_bypass = msg_w14;
            4'd11: w_prime_j_bypass = msg_w15;
            4'd12: w_prime_j_bypass = w_reg[5];
            4'd13: w_prime_j_bypass = w_reg[5];
            4'd14: w_prime_j_bypass = w_reg[5];
            4'd15: w_prime_j_bypass = w_reg[5];
        endcase
    end

    // Combinational outputs
    // For j>=16: w_reg[1] holds W_j (shift reg is 1 position behind w_reg[0])
    assign w_j       = (round_cnt < 6'd16) ? w_j_bypass  : w_reg[1];
    assign w_prime_j = w_j ^ ((round_cnt < 6'd16) ? w_prime_j_bypass : w_reg[5]);

    // Sequential block: shift register update
    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            for (i = 0; i < 16; i = i + 1)
                w_reg[i] <= 32'd0;
        end else if (load_en) begin
            w_reg[0]  <= msg_w0;
            w_reg[1]  <= msg_w1;
            w_reg[2]  <= msg_w2;
            w_reg[3]  <= msg_w3;
            w_reg[4]  <= msg_w4;
            w_reg[5]  <= msg_w5;
            w_reg[6]  <= msg_w6;
            w_reg[7]  <= msg_w7;
            w_reg[8]  <= msg_w8;
            w_reg[9]  <= msg_w9;
            w_reg[10] <= msg_w10;
            w_reg[11] <= msg_w11;
            w_reg[12] <= msg_w12;
            w_reg[13] <= msg_w13;
            w_reg[14] <= msg_w14;
            w_reg[15] <= msg_w15;
        end else if (calc_en) begin
            for (i = 0; i < 15; i = i + 1)
                w_reg[i] <= w_reg[i+1];
            w_reg[15] <= recur_result;
        end
    end

endmodule

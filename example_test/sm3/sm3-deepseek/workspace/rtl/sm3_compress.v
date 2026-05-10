// sm3_compress.v — SM3 Compression Function Datapath
// Verilog-2001

module sm3_compress (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire         update_v_en,
    input  wire [5:0]   round_cnt,
    input  wire [31:0]  w_j,
    input  wire [31:0]  w_prime_j,
    output wire [255:0] hash_out
);

    //==========================================================================
    // SM3 IV constants
    //==========================================================================
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    //==========================================================================
    // T_j constants
    //==========================================================================
    localparam [31:0] T_EARLY = 32'h79cc4519;  // j <= 15
    localparam [31:0] T_LATE  = 32'h7a879d8a;  // j >= 16

    //==========================================================================
    // Working registers A-H
    //==========================================================================
    reg [31:0] a_reg;
    reg [31:0] b_reg;
    reg [31:0] c_reg;
    reg [31:0] d_reg;
    reg [31:0] e_reg;
    reg [31:0] f_reg;
    reg [31:0] g_reg;
    reg [31:0] h_reg;

    //==========================================================================
    // IV chaining registers V0-V7
    //==========================================================================
    reg [31:0] v0_reg;
    reg [31:0] v1_reg;
    reg [31:0] v2_reg;
    reg [31:0] v3_reg;
    reg [31:0] v4_reg;
    reg [31:0] v5_reg;
    reg [31:0] v6_reg;
    reg [31:0] v7_reg;

    //==========================================================================
    // hash_out register
    //==========================================================================
    reg [255:0] hash_out_reg;

    //==========================================================================
    // ROL function
    //==========================================================================
    function [31:0] rol;
        input [31:0] data;
        input [5:0]  n;
    begin
        rol = (data << n) | (data >> (6'd32 - n));
    end
    endfunction

    //==========================================================================
    // T_j selection
    //==========================================================================
    wire [31:0] tj = (round_cnt <= 6'd15) ? T_EARLY : T_LATE;

    //==========================================================================
    // Input bypass mux: load_en=1 uses V values as A-H inputs (for round 0)
    //==========================================================================
    wire [31:0] a_in = load_en ? v0_reg : a_reg;
    wire [31:0] b_in = load_en ? v1_reg : b_reg;
    wire [31:0] c_in = load_en ? v2_reg : c_reg;
    wire [31:0] d_in = load_en ? v3_reg : d_reg;
    wire [31:0] e_in = load_en ? v4_reg : e_reg;
    wire [31:0] f_in = load_en ? v5_reg : f_reg;
    wire [31:0] g_in = load_en ? v6_reg : g_reg;
    wire [31:0] h_in = load_en ? v7_reg : h_reg;

    //==========================================================================
    // Boolean functions FF_j and GG_j (using bypassed inputs)
    //==========================================================================
    wire [31:0] ff_j = (round_cnt <= 6'd15) ?
                        (a_in ^ b_in ^ c_in) :
                        ((a_in & b_in) | (a_in & c_in) | (b_in & c_in));

    wire [31:0] gg_j = (round_cnt <= 6'd15) ?
                        (e_in ^ f_in ^ g_in) :
                        ((e_in & f_in) | (~e_in & g_in));

    //==========================================================================
    // Intermediate computations (using bypassed inputs)
    //==========================================================================
    wire [31:0] rol_a12  = rol(a_in, 6'd12);
    wire [31:0] rol_tj_j = rol(tj, round_cnt[4:0]);  // j mod 32
    wire [31:0] ss1      = rol(rol_a12 + e_in + rol_tj_j, 6'd7);
    wire [31:0] ss2      = ss1 ^ rol_a12;

    // Balanced addition trees for critical path optimization
    wire [31:0] tt1 = (ff_j + d_in) + (ss2 + w_prime_j);
    wire [31:0] tt2 = (gg_j + h_in) + (ss1 + w_j);

    // P0(TT2) = TT2 ^ ROL(TT2,9) ^ ROL(TT2,17)
    wire [31:0] e_next = tt2 ^ rol(tt2, 6'd9) ^ rol(tt2, 6'd17);

    //==========================================================================
    // A-H next values (combinational)
    //==========================================================================
    wire [31:0] a_next = tt1;
    wire [31:0] b_next = a_in;
    wire [31:0] c_next = rol(b_in, 6'd9);
    wire [31:0] d_next = c_in;
    wire [31:0] f_next = e_in;
    wire [31:0] g_next = rol(f_in, 6'd19);
    wire [31:0] h_next = g_in;

    //==========================================================================
    // V next values (for hash_out capture, computed from XOR)
    //==========================================================================
    wire [31:0] v0_next = v0_reg ^ a_reg;
    wire [31:0] v1_next = v1_reg ^ b_reg;
    wire [31:0] v2_next = v2_reg ^ c_reg;
    wire [31:0] v3_next = v3_reg ^ d_reg;
    wire [31:0] v4_next = v4_reg ^ e_reg;
    wire [31:0] v5_next = v5_reg ^ f_reg;
    wire [31:0] v6_next = v6_reg ^ g_reg;
    wire [31:0] v7_next = v7_reg ^ h_reg;

    //==========================================================================
    // Sequential: A-H registers
    // calc_en triggers all 64 rounds (round 0 uses V bypass inputs)
    // Reset at end of block for highest priority
    //==========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            a_reg <= 32'd0;
            b_reg <= 32'd0;
            c_reg <= 32'd0;
            d_reg <= 32'd0;
            e_reg <= 32'd0;
            f_reg <= 32'd0;
            g_reg <= 32'd0;
            h_reg <= 32'd0;
        end else if (calc_en) begin
            a_reg <= a_next;
            b_reg <= b_next;
            c_reg <= c_next;
            d_reg <= d_next;
            e_reg <= e_next;
            f_reg <= f_next;
            g_reg <= g_next;
            h_reg <= h_next;
        end
    end

    //==========================================================================
    // Sequential: V registers (IV chaining)
    // IV initialization on reset; XOR with A-H on update_v_en
    // Reset at end of block for highest priority
    //==========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v0_reg <= IV0;
            v1_reg <= IV1;
            v2_reg <= IV2;
            v3_reg <= IV3;
            v4_reg <= IV4;
            v5_reg <= IV5;
            v6_reg <= IV6;
            v7_reg <= IV7;
        end else if (update_v_en) begin
            v0_reg <= v0_next;
            v1_reg <= v1_next;
            v2_reg <= v2_next;
            v3_reg <= v3_next;
            v4_reg <= v4_next;
            v5_reg <= v5_next;
            v6_reg <= v6_next;
            v7_reg <= v7_next;
        end
    end

    //==========================================================================
    // Sequential: hash_out register (captures XOR'd V on update_v_en)
    // Reset at end of block for highest priority
    //==========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            hash_out_reg <= 256'd0;
        end else if (update_v_en) begin
            hash_out_reg <= {v0_next, v1_next, v2_next, v3_next,
                             v4_next, v5_next, v6_next, v7_next};
        end
    end

    //==========================================================================
    // Output
    //==========================================================================
    assign hash_out = hash_out_reg;

endmodule

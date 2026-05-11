//=============================================================================
// sm3_compress -- SM3 compression function datapath
// Verilog-2005, synthesizable. Implements SM3 round compression per GM/T 0004-2012.
// 8x32-bit V registers (cumulative hash state) + 8x32-bit A~H working registers.
//=============================================================================

`resetall
`timescale 1ns / 1ps
`default_nettype none

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

    // SM3 Initial Values (IV) -- GM/T 0004-2012
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    // Active-high reset derived from active-low rst_n
    wire rst = ~rst_n;

    // ── Working registers A~H (per-round) ───────────────────────────────
    reg [31:0] a_reg_reg;
    reg [31:0] b_reg_reg;
    reg [31:0] c_reg_reg;
    reg [31:0] d_reg_reg;
    reg [31:0] e_reg_reg;
    reg [31:0] f_reg_reg;
    reg [31:0] g_reg_reg;
    reg [31:0] h_reg_reg;

    // ── V registers (cumulative hash state) ─────────────────────────────
    reg [31:0] v0_reg_reg;
    reg [31:0] v1_reg_reg;
    reg [31:0] v2_reg_reg;
    reg [31:0] v3_reg_reg;
    reg [31:0] v4_reg_reg;
    reg [31:0] v5_reg_reg;
    reg [31:0] v6_reg_reg;
    reg [31:0] v7_reg_reg;

    // ── Hash output (combinational - reflects V register state immediately) ──

    // ── Combinational logic ─────────────────────────────────────────────

    // round_cnt >= 16 selects FF_j/GG_j variant and T_j constant
    wire _vf_tmp_0;
    assign _vf_tmp_0 = (round_cnt >= 6'd16);

    // FF_j: (A & B) | (A & C) | (B & C) for j>=16; A ^ B ^ C for j<16
    wire [31:0] _vf_tmp_1;
    assign _vf_tmp_1 = (a_reg_reg & b_reg_reg);
    wire [31:0] _vf_tmp_2;
    assign _vf_tmp_2 = (a_reg_reg & c_reg_reg);
    wire [31:0] _vf_tmp_3;
    assign _vf_tmp_3 = (_vf_tmp_1 | _vf_tmp_2);
    wire [31:0] _vf_tmp_4;
    assign _vf_tmp_4 = (b_reg_reg & c_reg_reg);
    wire [31:0] _vf_tmp_5;
    assign _vf_tmp_5 = (_vf_tmp_3 | _vf_tmp_4);
    wire [31:0] _vf_tmp_6;
    assign _vf_tmp_6 = (a_reg_reg ^ b_reg_reg);
    wire [31:0] _vf_tmp_7;
    assign _vf_tmp_7 = (_vf_tmp_6 ^ c_reg_reg);

    // TT1 partial: FF_j(A,B,C) + D
    wire [32:0] _vf_tmp_8;
    assign _vf_tmp_8 = ((_vf_tmp_0 ? _vf_tmp_5 : _vf_tmp_7) + d_reg_reg);

    // T_j constant selection and ROL(T_j, j)
    // T_j = 0x79cc4519 for j<=15, 0x7a879d8a for j>=16
    wire [31:0] t_j_raw;
    assign t_j_raw = (_vf_tmp_0 ? 32'h7a879d8a : 32'h79cc4519);

    // ROL(T_j, j): rotate T_j left by round_cnt[4:0] (lower 5 bits of j)
    wire [4:0] rot_amt = round_cnt[4:0];
    wire [31:0] t_j_rot;
    assign t_j_rot = (t_j_raw << rot_amt) | (t_j_raw >> (6'd32 - rot_amt));

    // SS1 intermediate: ROL(A,12) + E + ROL(T_j, j)
    wire [33:0] _vf_tmp_10;
    assign _vf_tmp_10 = ({a_reg_reg[19:0], a_reg_reg[31:20]} + e_reg_reg + t_j_rot);

    // SS1 = ROL(sum[31:0], 7) — ROTATE LOWER 32 BITS ONLY
    wire [31:0] ss1;
    assign ss1 = {_vf_tmp_10[24:0], _vf_tmp_10[31:25]};

    // SS2 = SS1 ^ ROL(A, 12)
    wire [31:0] ss2;
    assign ss2 = ss1 ^ {a_reg_reg[19:0], a_reg_reg[31:20]};

    // TT1 = FF_j(A,B,C) + D + SS2 + W'_j  (all 32-bit, result mod 2^32)
    wire [33:0] _vf_tmp_13;
    assign _vf_tmp_13 = (_vf_tmp_8 + ss2 + w_prime_j);

    // GG_j: (E & F) | (~E & G) for j>=16; E ^ F ^ G for j<16
    wire [31:0] _vf_tmp_14;
    assign _vf_tmp_14 = (e_reg_reg & f_reg_reg);
    wire [31:0] _vf_tmp_15;
    assign _vf_tmp_15 = (~e_reg_reg);
    wire [31:0] _vf_tmp_16;
    assign _vf_tmp_16 = (_vf_tmp_15 & g_reg_reg);
    wire [31:0] _vf_tmp_17;
    assign _vf_tmp_17 = (_vf_tmp_14 | _vf_tmp_16);
    wire [31:0] _vf_tmp_18;
    assign _vf_tmp_18 = (e_reg_reg ^ f_reg_reg);
    wire [31:0] _vf_tmp_19;
    assign _vf_tmp_19 = (_vf_tmp_18 ^ g_reg_reg);

    // TT2 partial: GG_j(E,F,G) + H
    wire [32:0] _vf_tmp_20;
    assign _vf_tmp_20 = ((_vf_tmp_0 ? _vf_tmp_17 : _vf_tmp_19) + h_reg_reg);

    // TT2 = GG_j(E,F,G) + H + SS1 + W_j  (all 32-bit, result mod 2^32)
    wire [33:0] _vf_tmp_22;
    assign _vf_tmp_22 = (_vf_tmp_20 + ss1 + w_j);

    // P0(TT2[31:0]) = TT2[31:0] ^ ROL(TT2[31:0],9) ^ ROL(TT2[31:0],17)
    // ROTATE LOWER 32 BITS ONLY
    wire [31:0] tt2_32;
    assign tt2_32 = _vf_tmp_22[31:0];
    wire [31:0] e_next;
    assign e_next = tt2_32 ^ {tt2_32[22:0], tt2_32[31:23]} ^ {tt2_32[14:0], tt2_32[31:15]};

    // V register update: V_i = V_i XOR {A,B,C,D,E,F,G,H}_i (on update_v_en)
    // At update_v_en time, load_en=calc_en=0, so A~H hold final round values.
    // Simplified: the mux chain always evaluates to a_reg_reg / b_reg_reg / ... at DONE time.
    wire [31:0] v0_next;
    assign v0_next = v0_reg_reg ^ a_reg_reg;
    wire [31:0] v1_next;
    assign v1_next = v1_reg_reg ^ b_reg_reg;
    wire [31:0] v2_next;
    assign v2_next = v2_reg_reg ^ c_reg_reg;
    wire [31:0] v3_next;
    assign v3_next = v3_reg_reg ^ d_reg_reg;
    wire [31:0] v4_next;
    assign v4_next = v4_reg_reg ^ e_reg_reg;
    wire [31:0] v5_next;
    assign v5_next = v5_reg_reg ^ f_reg_reg;
    wire [31:0] v6_next;
    assign v6_next = v6_reg_reg ^ g_reg_reg;
    wire [31:0] v7_next;
    assign v7_next = v7_reg_reg ^ h_reg_reg;

    // ── Sequential logic ─────────────────────────────────────────────────

    always @(posedge clk) begin
        a_reg_reg <= (load_en ? v0_reg_reg : (calc_en ? _vf_tmp_13[31:0] : a_reg_reg));
        b_reg_reg <= (load_en ? v1_reg_reg : (calc_en ? a_reg_reg : b_reg_reg));
        c_reg_reg <= (load_en ? v2_reg_reg : (calc_en ? {b_reg_reg[22:0], b_reg_reg[31:23]} : c_reg_reg));
        d_reg_reg <= (load_en ? v3_reg_reg : (calc_en ? c_reg_reg : d_reg_reg));
        e_reg_reg <= (load_en ? v4_reg_reg : (calc_en ? e_next : e_reg_reg));
        f_reg_reg <= (load_en ? v5_reg_reg : (calc_en ? e_reg_reg : f_reg_reg));
        g_reg_reg <= (load_en ? v6_reg_reg : (calc_en ? {f_reg_reg[12:0], f_reg_reg[31:13]} : g_reg_reg));
        h_reg_reg <= (load_en ? v7_reg_reg : (calc_en ? g_reg_reg : h_reg_reg));

        v0_reg_reg <= (update_v_en ? v0_next : v0_reg_reg);
        v1_reg_reg <= (update_v_en ? v1_next : v1_reg_reg);
        v2_reg_reg <= (update_v_en ? v2_next : v2_reg_reg);
        v3_reg_reg <= (update_v_en ? v3_next : v3_reg_reg);
        v4_reg_reg <= (update_v_en ? v4_next : v4_reg_reg);
        v5_reg_reg <= (update_v_en ? v5_next : v5_reg_reg);
        v6_reg_reg <= (update_v_en ? v6_next : v6_reg_reg);
        v7_reg_reg <= (update_v_en ? v7_next : v7_reg_reg);

        if (rst) begin
            a_reg_reg  <= 32'd0;
            b_reg_reg  <= 32'd0;
            c_reg_reg  <= 32'd0;
            d_reg_reg  <= 32'd0;
            e_reg_reg  <= 32'd0;
            f_reg_reg  <= 32'd0;
            g_reg_reg  <= 32'd0;
            h_reg_reg  <= 32'd0;

            // V registers initialize to SM3 IV values on reset
            v0_reg_reg <= IV0;
            v1_reg_reg <= IV1;
            v2_reg_reg <= IV2;
            v3_reg_reg <= IV3;
            v4_reg_reg <= IV4;
            v5_reg_reg <= IV5;
            v6_reg_reg <= IV6;
            v7_reg_reg <= IV7;
        end
    end

    assign hash_out = {v0_reg_reg, v1_reg_reg, v2_reg_reg, v3_reg_reg,
                       v4_reg_reg, v5_reg_reg, v6_reg_reg, v7_reg_reg};

endmodule

`default_nettype wire

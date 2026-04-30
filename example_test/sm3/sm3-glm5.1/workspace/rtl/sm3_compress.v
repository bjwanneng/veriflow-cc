// -----------------------------------------------------------------------------
// File   : sm3_compress.v
// Author : AI Coder
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 compression function datapath. Computes SS1, SS2, TT1, TT2 each
//   round, updates A~H working registers, and maintains V0~V7 state registers
//   with IV initialization on reset. Uses tree-structured addition for TT1
//   and TT2 to reduce critical path depth. ROL(Tj, j) implemented as a
//   32-to-1 MUX based on round_cnt[4:0].
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  AI Coder  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_compress
(
    input  wire                   clk,
    input  wire                   rst_n,
    input  wire                   load_en,
    input  wire                   calc_en,
    input  wire                   update_v_en,
    input  wire [5:0]             round_cnt,
    input  wire [31:0]            w_j,
    input  wire [31:0]            w_prime_j,
    output wire [255:0]           hash_out
);

    //-------------------------------------------------------------------------
    // IV Constants (reset values for V0~V7)
    //-------------------------------------------------------------------------
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    // Round constants
    localparam [31:0] TJ_LOW  = 32'h79cc4519;  // j < 16
    localparam [31:0] TJ_HIGH = 32'h7a879d8a;  // j >= 16

    //-------------------------------------------------------------------------
    // Working registers: A~H (32-bit each)
    //-------------------------------------------------------------------------
    reg [31:0] a_reg = {32{1'b0}}, a_next;
    reg [31:0] b_reg = {32{1'b0}}, b_next;
    reg [31:0] c_reg = {32{1'b0}}, c_next;
    reg [31:0] d_reg = {32{1'b0}}, d_next;
    reg [31:0] e_reg = {32{1'b0}}, e_next;
    reg [31:0] f_reg = {32{1'b0}}, f_next;
    reg [31:0] g_reg = {32{1'b0}}, g_next;
    reg [31:0] h_reg = {32{1'b0}}, h_next;

    //-------------------------------------------------------------------------
    // State registers: V0~V7 (32-bit each, init=IV)
    //-------------------------------------------------------------------------
    reg [31:0] v0_reg = IV0, v0_next;
    reg [31:0] v1_reg = IV1, v1_next;
    reg [31:0] v2_reg = IV2, v2_next;
    reg [31:0] v3_reg = IV3, v3_next;
    reg [31:0] v4_reg = IV4, v4_next;
    reg [31:0] v5_reg = IV5, v5_next;
    reg [31:0] v6_reg = IV6, v6_next;
    reg [31:0] v7_reg = IV7, v7_next;

    //-------------------------------------------------------------------------
    // Output assignment: hash_out = {V0, V1, ..., V7}
    //-------------------------------------------------------------------------
    assign hash_out = {v0_reg, v1_reg, v2_reg, v3_reg,
                       v4_reg, v5_reg, v6_reg, v7_reg};

    //-------------------------------------------------------------------------
    // Combinational logic: ROL helpers
    //-------------------------------------------------------------------------
    // ROL(X, k): circular left rotate of 32-bit value X by k positions
    // Implemented as concatenation for constant shift amounts (wiring only)

    // ROL(A, 12)
    wire [31:0] rol_a_12 = {a_reg[19:0], a_reg[31:20]};

    // ROL(B, 9)
    wire [31:0] rol_b_9 = {b_reg[22:0], b_reg[31:23]};

    // ROL(F, 19)
    wire [31:0] rol_f_19 = {f_reg[12:0], f_reg[31:13]};

    //-------------------------------------------------------------------------
    // ROL(Tj, j) — 32-to-1 MUX using round_cnt[4:0]
    //-------------------------------------------------------------------------
    wire [31:0] tj_val = (round_cnt < 6'd16) ? TJ_LOW : TJ_HIGH;

    // Barrel shift: rotate Tj left by round_cnt[4:0] positions
    // Stage 1: shift by 0 or 16 based on bit 4
    wire [31:0] rol_tj_stage1;
    assign rol_tj_stage1 = (round_cnt[4] == 1'b0) ? tj_val :
                           {tj_val[15:0], tj_val[31:16]};

    // Stage 2: shift by 0 or 8 based on bit 3
    wire [31:0] rol_tj_stage2;
    assign rol_tj_stage2 = (round_cnt[3] == 1'b0) ? rol_tj_stage1 :
                           {rol_tj_stage1[23:0], rol_tj_stage1[31:24]};

    // Stage 3: shift by 0 or 4 based on bit 2
    wire [31:0] rol_tj_stage3;
    assign rol_tj_stage3 = (round_cnt[2] == 1'b0) ? rol_tj_stage2 :
                           {rol_tj_stage2[27:0], rol_tj_stage2[31:28]};

    // Stage 4: shift by 0 or 2 based on bit 1
    wire [31:0] rol_tj_stage4;
    assign rol_tj_stage4 = (round_cnt[1] == 1'b0) ? rol_tj_stage3 :
                           {rol_tj_stage3[29:0], rol_tj_stage3[31:30]};

    // Stage 5: shift by 0 or 1 based on bit 0
    wire [31:0] rol_tj;
    assign rol_tj = (round_cnt[0] == 1'b0) ? rol_tj_stage4 :
                    {rol_tj_stage4[30:0], rol_tj_stage4[31]};

    //-------------------------------------------------------------------------
    // Combinational compression datapath
    //-------------------------------------------------------------------------
    // Round constant Tj selection
    wire round_is_low = (round_cnt < 6'd16);

    // SS1 = ROL((ROL(A,12) + E + ROL(Tj, j)), 7)
    wire [31:0] ss1_sum = rol_a_12 + e_reg + rol_tj;
    wire [31:0] ss1 = {ss1_sum[24:0], ss1_sum[31:25]};

    // SS2 = SS1 ^ ROL(A, 12)
    wire [31:0] ss2 = ss1 ^ rol_a_12;

    // FF_j: (j < 16) ? (A^B^C) : ((A&B)|(A&C)|(B&C))
    wire [31:0] ff_val;
    assign ff_val = round_is_low ? (a_reg ^ b_reg ^ c_reg) :
                                 ((a_reg & b_reg) | (a_reg & c_reg) | (b_reg & c_reg));

    // GG_j: (j < 16) ? (E^F^G) : ((E&F)|(~E&G))
    wire [31:0] gg_val;
    assign gg_val = round_is_low ? (e_reg ^ f_reg ^ g_reg) :
                                 ((e_reg & f_reg) | (~e_reg & g_reg));

    // TT1 = (FF + D) + (SS2 + w_prime_j) — tree-structured addition
    wire [31:0] tt1_part0 = ff_val + d_reg;
    wire [31:0] tt1_part1 = ss2 + w_prime_j;
    wire [31:0] tt1 = tt1_part0 + tt1_part1;

    // TT2 = (GG + H) + (SS1 + w_j) — tree-structured addition
    wire [31:0] tt2_part0 = gg_val + h_reg;
    wire [31:0] tt2_part1 = ss1 + w_j;
    wire [31:0] tt2 = tt2_part0 + tt2_part1;

    // P0(X) = X ^ ROL(X, 9) ^ ROL(X, 17)
    wire [31:0] p0_tt2 = tt2 ^ {tt2[22:0], tt2[31:23]} ^
                         {tt2[14:0], tt2[31:15]};

    //-------------------------------------------------------------------------
    // Combinational next-state logic
    //-------------------------------------------------------------------------
    always @* begin
        // Default: hold current values
        a_next = a_reg;
        b_next = b_reg;
        c_next = c_reg;
        d_next = d_reg;
        e_next = e_reg;
        f_next = f_reg;
        g_next = g_reg;
        h_next = h_reg;
        v0_next = v0_reg;
        v1_next = v1_reg;
        v2_next = v2_reg;
        v3_next = v3_reg;
        v4_next = v4_reg;
        v5_next = v5_reg;
        v6_next = v6_reg;
        v7_next = v7_reg;

        if (load_en) begin
            // Load V registers into A~H working registers
            a_next = v0_reg;
            b_next = v1_reg;
            c_next = v2_reg;
            d_next = v3_reg;
            e_next = v4_reg;
            f_next = v5_reg;
            g_next = v6_reg;
            h_next = v7_reg;
        end

        if (calc_en) begin
            // Compression round register updates
            a_next = tt1;
            b_next = a_reg;
            c_next = rol_b_9;
            d_next = c_reg;
            e_next = p0_tt2;
            f_next = e_reg;
            g_next = rol_f_19;
            h_next = g_reg;
        end

        if (update_v_en) begin
            // XOR A~H with V0~V7
            v0_next = v0_reg ^ a_reg;
            v1_next = v1_reg ^ b_reg;
            v2_next = v2_reg ^ c_reg;
            v3_next = v3_reg ^ d_reg;
            v4_next = v4_reg ^ e_reg;
            v5_next = v5_reg ^ f_reg;
            v6_next = v6_reg ^ g_reg;
            v7_next = v7_reg ^ h_reg;
        end
    end

    //-------------------------------------------------------------------------
    // Sequential logic: register updates with synchronous active-low reset
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        a_reg <= a_next;
        b_reg <= b_next;
        c_reg <= c_next;
        d_reg <= d_next;
        e_reg <= e_next;
        f_reg <= f_next;
        g_reg <= g_next;
        h_reg <= h_next;
        v0_reg <= v0_next;
        v1_reg <= v1_next;
        v2_reg <= v2_next;
        v3_reg <= v3_next;
        v4_reg <= v4_next;
        v5_reg <= v5_next;
        v6_reg <= v6_next;
        v7_reg <= v7_next;

        // Synchronous active-low reset (last-assignment-wins)
        if (!rst_n) begin
            a_reg  <= {32{1'b0}};
            b_reg  <= {32{1'b0}};
            c_reg  <= {32{1'b0}};
            d_reg  <= {32{1'b0}};
            e_reg  <= {32{1'b0}};
            f_reg  <= {32{1'b0}};
            g_reg  <= {32{1'b0}};
            h_reg  <= {32{1'b0}};
            v0_reg <= IV0;
            v1_reg <= IV1;
            v2_reg <= IV2;
            v3_reg <= IV3;
            v4_reg <= IV4;
            v5_reg <= IV5;
            v6_reg <= IV6;
            v7_reg <= IV7;
        end
    end

endmodule

`resetall

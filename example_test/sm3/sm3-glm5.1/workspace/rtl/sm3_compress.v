//=============================================================================
// sm3_compress — SM3 Compression Function Datapath
//
// Maintains two register groups:
//   1. V0~V7  (8 x 32-bit) : Persistent hash state across blocks.
//      Initialized to SM3 IV on reset.  XOR-updated with A~H on update_v_en.
//   2. A~H    (8 x 32-bit) : Working registers for the current 512-bit block.
//      Loaded from V on load_en.  Updated every calc_en cycle with one round
//      of the SM3 compression function.
//
// Compression round (combinational):
//   T_j   = j<16 ? 0x79cc4519 : 0x7a879d8a
//   SS1   = ROL( ROL(A,12) + E + ROL(T_j, j%32), 7 )
//   SS2   = SS1 ^ ROL(A,12)
//   TT1   = FF(A,B,C) + D + SS2 + w'_j
//   TT2   = GG(E,F,G) + H + SS1 + w_j
//   A_new = TT1,  B_new = A,  C_new = ROL(B,9),  D_new = C
//   E_new = P0(TT2),  F_new = E,  G_new = ROL(F,19),  H_new = G
//
// Clock domain: clk_core @ 150 MHz, sync active-low reset
//=============================================================================

`resetall
`timescale 1ns/1ps
`default_nettype none

module sm3_compress (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        load_en,
    input  wire        calc_en,
    input  wire        update_v_en,
    input  wire [5:0]  round_cnt,
    input  wire [31:0] w_j,
    input  wire [31:0] w_prime_j,
    output wire [255:0] hash_out
);

    //-------------------------------------------------------------------------
    // SM3 Initialization Vector (IV)
    //-------------------------------------------------------------------------
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    //-------------------------------------------------------------------------
    // T constants
    //-------------------------------------------------------------------------
    localparam [31:0] T_EARLY = 32'h79cc4519;   // rounds 0..15
    localparam [31:0] T_LATE  = 32'h7a879d8a;   // rounds 16..63

    //-------------------------------------------------------------------------
    // State registers: V (persistent) and A~H (working)
    //-------------------------------------------------------------------------
    reg [31:0] v0_reg, v1_reg, v2_reg, v3_reg, v4_reg, v5_reg, v6_reg, v7_reg;
    reg [31:0] a_reg,  b_reg,  c_reg,  d_reg,  e_reg,  f_reg,  g_reg,  h_reg;

    //-------------------------------------------------------------------------
    // Combinational next-state signals
    //-------------------------------------------------------------------------
    reg [31:0] a_next, b_next, c_next, d_next, e_next, f_next, g_next, h_next;

    //-------------------------------------------------------------------------
    // Combinational wires
    //-------------------------------------------------------------------------
    wire [4:0]  j5;         // round_cnt mod 32 (shift amount for ROL(T_j, j))
    wire [31:0] tj;         // T_j selected by round
    wire        is_early;   // 1 for rounds 0..15, 0 for rounds 16..63

    assign j5       = round_cnt[4:0];
    assign is_early = (round_cnt[5:4] == 2'b00);
    assign tj       = is_early ? T_EARLY : T_LATE;

    //-------------------------------------------------------------------------
    // Combinational: compression round datapath
    //-------------------------------------------------------------------------
    reg [31:0] rol12_a, rol_tj, sum1, ss1, ss2;
    reg [31:0] ff_out, gg_out;
    reg [31:0] tt1, tt2, p0_tt2;

    always @* begin
        // Defaults (prevent latches)
        rol12_a = 32'd0;
        rol_tj  = 32'd0;
        sum1    = 32'd0;
        ss1     = 32'd0;
        ss2     = 32'd0;
        ff_out  = 32'd0;
        gg_out  = 32'd0;
        tt1     = 32'd0;
        tt2     = 32'd0;
        p0_tt2  = 32'd0;
        a_next  = 32'd0;
        b_next  = 32'd0;
        c_next  = 32'd0;
        d_next  = 32'd0;
        e_next  = 32'd0;
        f_next  = 32'd0;
        g_next  = 32'd0;
        h_next  = 32'd0;

        // ROL(A, 12) = {A[19:0], A[31:20]}
        rol12_a = {a_reg[19:0], a_reg[31:20]};

        // ROL(T_j, j % 32) — dynamic barrel rotate
        // Guard j5==0 to avoid >>32 (undefined in Verilog)
        if (j5 == 5'd0)
            rol_tj = tj;
        else
            rol_tj = (tj << j5) | (tj >> (6'd32 - j5));

        // SS1 = ROL( ROL(A,12) + E + ROL(T_j, j), 7 )
        sum1 = rol12_a + e_reg + rol_tj;
        ss1  = {sum1[24:0], sum1[31:25]};

        // SS2 = SS1 ^ ROL(A, 12)
        ss2 = ss1 ^ rol12_a;

        // FF(A, B, C):  j<16 → xor,  j>=16 → majority
        if (is_early)
            ff_out = a_reg ^ b_reg ^ c_reg;
        else
            ff_out = (a_reg & b_reg) | (a_reg & c_reg) | (b_reg & c_reg);

        // GG(E, F, G):  j<16 → xor,  j>=16 → select
        if (is_early)
            gg_out = e_reg ^ f_reg ^ g_reg;
        else
            gg_out = (e_reg & f_reg) | ((~e_reg) & g_reg);

        // TT1 = FF(A,B,C) + D + SS2 + w_prime_j
        tt1 = ff_out + d_reg + ss2 + w_prime_j;

        // TT2 = GG(E,F,G) + H + SS1 + w_j
        tt2 = gg_out + h_reg + ss1 + w_j;

        // P0(TT2) = TT2 ^ ROL(TT2, 9) ^ ROL(TT2, 17)
        p0_tt2 = tt2 ^ {tt2[22:0], tt2[31:23]} ^ {tt2[14:0], tt2[31:15]};

        // Next-state A~H
        a_next = tt1;
        b_next = a_reg;
        c_next = {b_reg[22:0], b_reg[31:23]};   // ROL(B, 9)
        d_next = c_reg;
        e_next = p0_tt2;
        f_next = e_reg;
        g_next = {f_reg[12:0], f_reg[31:13]};   // ROL(F, 19)
        h_next = g_reg;
    end

    //-------------------------------------------------------------------------
    // Sequential: register update
    //-------------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            // V registers reset to IV
            v0_reg <= IV0;
            v1_reg <= IV1;
            v2_reg <= IV2;
            v3_reg <= IV3;
            v4_reg <= IV4;
            v5_reg <= IV5;
            v6_reg <= IV6;
            v7_reg <= IV7;
            // Working registers reset to 0
            a_reg  <= 32'd0;
            b_reg  <= 32'd0;
            c_reg  <= 32'd0;
            d_reg  <= 32'd0;
            e_reg  <= 32'd0;
            f_reg  <= 32'd0;
            g_reg  <= 32'd0;
            h_reg  <= 32'd0;
        end
        else begin
            // Load: A~H ← V0~V7
            if (load_en) begin
                a_reg <= v0_reg;
                b_reg <= v1_reg;
                c_reg <= v2_reg;
                d_reg <= v3_reg;
                e_reg <= v4_reg;
                f_reg <= v5_reg;
                g_reg <= v6_reg;
                h_reg <= v7_reg;
            end
            // Calc: one compression round
            else if (calc_en) begin
                a_reg <= a_next;
                b_reg <= b_next;
                c_reg <= c_next;
                d_reg <= d_next;
                e_reg <= e_next;
                f_reg <= f_next;
                g_reg <= g_next;
                h_reg <= h_next;
            end

            // Update V: V_i ← V_i ^ A_i  (XOR working state back into persistent state)
            if (update_v_en) begin
                v0_reg <= v0_reg ^ a_reg;
                v1_reg <= v1_reg ^ b_reg;
                v2_reg <= v2_reg ^ c_reg;
                v3_reg <= v3_reg ^ d_reg;
                v4_reg <= v4_reg ^ e_reg;
                v5_reg <= v5_reg ^ f_reg;
                v6_reg <= v6_reg ^ g_reg;
                v7_reg <= v7_reg ^ h_reg;
            end
        end
    end

    //-------------------------------------------------------------------------
    // Output: combinational concatenation of V registers
    //-------------------------------------------------------------------------
    assign hash_out = {v0_reg, v1_reg, v2_reg, v3_reg,
                       v4_reg, v5_reg, v6_reg, v7_reg};

endmodule

`default_nettype wire

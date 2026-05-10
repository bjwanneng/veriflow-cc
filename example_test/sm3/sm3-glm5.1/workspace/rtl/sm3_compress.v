// -----------------------------------------------------------------------------
// File   : sm3_compress.v
// Author : vf-coder
// Date   : 2026-05-09
// -----------------------------------------------------------------------------
// Description: SM3 compression function data path. Computes SS1, SS2, TT1, TT2
//              per round and updates A~H working registers. Contains V0~V7
//              state registers updated at update_v_en.
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_compress
(
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

    // ---------------------------------------------------------------------
    // SM3 initial vector constants (GM/T 0004-2012 Section 5.3.2)
    // ---------------------------------------------------------------------
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    // Round constants Tj (GM/T 0004-2012 Section 5.3.2)
    localparam [31:0] TJ_0_15  = 32'h79cc4519;
    localparam [31:0] TJ_16_63 = 32'h7a879d8a;

    // ---------------------------------------------------------------------
    // Internal registers — V0~V7 state registers (initialized to SM3 IV)
    // ---------------------------------------------------------------------
    reg [31:0] V0_reg = IV0, V0_next;
    reg [31:0] V1_reg = IV1, V1_next;
    reg [31:0] V2_reg = IV2, V2_next;
    reg [31:0] V3_reg = IV3, V3_next;
    reg [31:0] V4_reg = IV4, V4_next;
    reg [31:0] V5_reg = IV5, V5_next;
    reg [31:0] V6_reg = IV6, V6_next;
    reg [31:0] V7_reg = IV7, V7_next;

    // Working registers A~H
    reg [31:0] A_reg = 32'h00000000, A_next;
    reg [31:0] B_reg = 32'h00000000, B_next;
    reg [31:0] C_reg = 32'h00000000, C_next;
    reg [31:0] D_reg = 32'h00000000, D_next;
    reg [31:0] E_reg = 32'h00000000, E_next;
    reg [31:0] F_reg = 32'h00000000, F_next;
    reg [31:0] G_reg = 32'h00000000, G_next;
    reg [31:0] H_reg = 32'h00000000, H_next;

    // ---------------------------------------------------------------------
    // Output assignment — mux V_next when update_v_en active (read-before-update)
    // ---------------------------------------------------------------------
    assign hash_out = update_v_en ? {V0_next, V1_next, V2_next, V3_next,
                                     V4_next, V5_next, V6_next, V7_next}
                                  : {V0_reg, V1_reg, V2_reg, V3_reg,
                                     V4_reg, V5_reg, V6_reg, V7_reg};

    // ---------------------------------------------------------------------
    // Combinational helper wires
    // ---------------------------------------------------------------------

    // --- Tj selection based on round_cnt ---
    wire [31:0] Tj = (round_cnt <= 6'd15) ? TJ_0_15 : TJ_16_63;

    // --- ROL(A, 12) via concatenation ---
    wire [31:0] rol_A_12 = {A_reg[19:0], A_reg[31:20]};

    // --- ROL(Tj, round_cnt % 32) via 32-to-1 MUX ---
    // round_cnt[4:0] gives round_cnt % 32 for 6-bit round_cnt (0..63)
    wire [4:0]  tj_shift = round_cnt[4:0];
    wire [31:0] rol_Tj;

    // 32-to-1 MUX for variable rotation of Tj
    assign rol_Tj = (tj_shift == 5'd0)  ? Tj                          :
                    (tj_shift == 5'd1)  ? {Tj[30:0], Tj[31]}          :
                    (tj_shift == 5'd2)  ? {Tj[29:0], Tj[31:30]}       :
                    (tj_shift == 5'd3)  ? {Tj[28:0], Tj[31:29]}       :
                    (tj_shift == 5'd4)  ? {Tj[27:0], Tj[31:28]}       :
                    (tj_shift == 5'd5)  ? {Tj[26:0], Tj[31:27]}       :
                    (tj_shift == 5'd6)  ? {Tj[25:0], Tj[31:26]}       :
                    (tj_shift == 5'd7)  ? {Tj[24:0], Tj[31:25]}       :
                    (tj_shift == 5'd8)  ? {Tj[23:0], Tj[31:24]}       :
                    (tj_shift == 5'd9)  ? {Tj[22:0], Tj[31:23]}       :
                    (tj_shift == 5'd10) ? {Tj[21:0], Tj[31:22]}       :
                    (tj_shift == 5'd11) ? {Tj[20:0], Tj[31:21]}       :
                    (tj_shift == 5'd12) ? {Tj[19:0], Tj[31:20]}       :
                    (tj_shift == 5'd13) ? {Tj[18:0], Tj[31:19]}       :
                    (tj_shift == 5'd14) ? {Tj[17:0], Tj[31:18]}       :
                    (tj_shift == 5'd15) ? {Tj[16:0], Tj[31:17]}       :
                    (tj_shift == 5'd16) ? {Tj[15:0], Tj[31:16]}       :
                    (tj_shift == 5'd17) ? {Tj[14:0], Tj[31:15]}       :
                    (tj_shift == 5'd18) ? {Tj[13:0], Tj[31:14]}       :
                    (tj_shift == 5'd19) ? {Tj[12:0], Tj[31:13]}       :
                    (tj_shift == 5'd20) ? {Tj[11:0], Tj[31:12]}       :
                    (tj_shift == 5'd21) ? {Tj[10:0], Tj[31:11]}       :
                    (tj_shift == 5'd22) ? {Tj[9:0],  Tj[31:10]}       :
                    (tj_shift == 5'd23) ? {Tj[8:0],  Tj[31:9]}        :
                    (tj_shift == 5'd24) ? {Tj[7:0],  Tj[31:8]}        :
                    (tj_shift == 5'd25) ? {Tj[6:0],  Tj[31:7]}        :
                    (tj_shift == 5'd26) ? {Tj[5:0],  Tj[31:6]}        :
                    (tj_shift == 5'd27) ? {Tj[4:0],  Tj[31:5]}        :
                    (tj_shift == 5'd28) ? {Tj[3:0],  Tj[31:4]}        :
                    (tj_shift == 5'd29) ? {Tj[2:0],  Tj[31:3]}        :
                    (tj_shift == 5'd30) ? {Tj[1:0],  Tj[31:2]}        :
                                          {Tj[0],    Tj[31:1]}        ;

    // --- SS1 = ROL((ROL(A,12) + E + ROL(Tj, round_cnt%32)), 7) mod 2^32 ---
    wire [31:0] ss1_sum = rol_A_12 + E_reg + rol_Tj;  // natural 32-bit wrap
    wire [31:0] SS1 = {ss1_sum[24:0], ss1_sum[31:25]};  // ROL by 7

    // --- SS2 = SS1 ^ ROL(A, 12) ---
    wire [31:0] SS2 = SS1 ^ rol_A_12;

    // --- FFj: Boolean function ---
    wire [31:0] FFj = (round_cnt <= 6'd15)
                      ? (A_reg ^ B_reg ^ C_reg)
                      : ((A_reg & B_reg) | (A_reg & C_reg) | (B_reg & C_reg));

    // --- GGj: Boolean function ---
    wire [31:0] GGj = (round_cnt <= 6'd15)
                      ? (E_reg ^ F_reg ^ G_reg)
                      : ((E_reg & F_reg) | (~E_reg & G_reg));

    // --- TT1 = (FFj(A,B,C) + D) + (SS2 + w_prime_j) [tree structure] ---
    wire [31:0] tt1_left  = FFj + D_reg;
    wire [31:0] tt1_right = SS2 + w_prime_j;
    wire [31:0] TT1 = tt1_left + tt1_right;

    // --- TT2 = (GGj(E,F,G) + H) + (SS1 + w_j) [tree structure] ---
    wire [31:0] tt2_left  = GGj + H_reg;
    wire [31:0] tt2_right = SS1 + w_j;
    wire [31:0] TT2 = tt2_left + tt2_right;

    // --- P0(TT2) = TT2 ^ ROL(TT2,9) ^ ROL(TT2,17) ---
    wire [31:0] rol_TT2_9  = {TT2[22:0], TT2[31:23]};
    wire [31:0] rol_TT2_17 = {TT2[14:0], TT2[31:15]};
    wire [31:0] P0_TT2 = TT2 ^ rol_TT2_9 ^ rol_TT2_17;

    // --- ROL(B, 9) and ROL(F, 19) for register updates ---
    wire [31:0] rol_B_9  = {B_reg[22:0], B_reg[31:23]};
    wire [31:0] rol_F_19 = {F_reg[12:0], F_reg[31:13]};

    // ---------------------------------------------------------------------
    // Block 1: Combinational — compute all _next signals
    // ---------------------------------------------------------------------
    always @* begin
        // Default: hold current values
        V0_next = V0_reg;
        V1_next = V1_reg;
        V2_next = V2_reg;
        V3_next = V3_reg;
        V4_next = V4_reg;
        V5_next = V5_reg;
        V6_next = V6_reg;
        V7_next = V7_reg;

        A_next = A_reg;
        B_next = B_reg;
        C_next = C_reg;
        D_next = D_reg;
        E_next = E_reg;
        F_next = F_reg;
        G_next = G_reg;
        H_next = H_reg;

        // load_en: copy V registers into A~H working registers
        if (load_en) begin
            A_next = V0_reg;
            B_next = V1_reg;
            C_next = V2_reg;
            D_next = V3_reg;
            E_next = V4_reg;
            F_next = V5_reg;
            G_next = V6_reg;
            H_next = V7_reg;
        end

        // calc_en: per-round compression (independent if block per 23.9)
        if (calc_en) begin
            A_next = TT1;
            B_next = A_reg;
            C_next = rol_B_9;
            D_next = C_reg;
            E_next = P0_TT2;
            F_next = E_reg;
            G_next = rol_F_19;
            H_next = G_reg;
        end

        // update_v_en: V[i] = V[i] ^ {A,B,C,D,E,F,G,H}[i]
        if (update_v_en) begin
            V0_next = V0_reg ^ A_reg;
            V1_next = V1_reg ^ B_reg;
            V2_next = V2_reg ^ C_reg;
            V3_next = V3_reg ^ D_reg;
            V4_next = V4_reg ^ E_reg;
            V5_next = V5_reg ^ F_reg;
            V6_next = V6_reg ^ G_reg;
            V7_next = V7_reg ^ H_reg;
        end
    end

    // ---------------------------------------------------------------------
    // Block 2: Sequential — register sampling with async active-low reset
    // ---------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            V0_reg <= IV0;
            V1_reg <= IV1;
            V2_reg <= IV2;
            V3_reg <= IV3;
            V4_reg <= IV4;
            V5_reg <= IV5;
            V6_reg <= IV6;
            V7_reg <= IV7;
            A_reg  <= 32'h00000000;
            B_reg  <= 32'h00000000;
            C_reg  <= 32'h00000000;
            D_reg  <= 32'h00000000;
            E_reg  <= 32'h00000000;
            F_reg  <= 32'h00000000;
            G_reg  <= 32'h00000000;
            H_reg  <= 32'h00000000;
        end else begin
            V0_reg <= V0_next;
            V1_reg <= V1_next;
            V2_reg <= V2_next;
            V3_reg <= V3_next;
            V4_reg <= V4_next;
            V5_reg <= V5_next;
            V6_reg <= V6_next;
            V7_reg <= V7_next;
            A_reg  <= A_next;
            B_reg  <= B_next;
            C_reg  <= C_next;
            D_reg  <= D_next;
            E_reg  <= E_next;
            F_reg  <= F_next;
            G_reg  <= G_next;
            H_reg  <= H_next;
        end
    end

endmodule

`resetall

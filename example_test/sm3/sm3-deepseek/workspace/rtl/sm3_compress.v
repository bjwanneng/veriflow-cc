// ============================================================================
// sm3_compress -- SM3 compression function datapath
// Verilog-2001, synthesizable. Implements SM3 round compression per GM/T 0004-2012.
// 8x32-bit V registers (cumulative hash state) + 8x32-bit A~H working registers.
// ============================================================================

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

    // =========================================================================
    // Internal state registers
    // =========================================================================
    reg [31:0] A_reg;
    reg [31:0] B_reg;
    reg [31:0] C_reg;
    reg [31:0] D_reg;
    reg [31:0] E_reg;
    reg [31:0] F_reg;
    reg [31:0] G_reg;
    reg [31:0] H_reg;

    reg [31:0] V0_reg;
    reg [31:0] V1_reg;
    reg [31:0] V2_reg;
    reg [31:0] V3_reg;
    reg [31:0] V4_reg;
    reg [31:0] V5_reg;
    reg [31:0] V6_reg;
    reg [31:0] V7_reg;

    // =========================================================================
    // Round control: j <= 15 selects early-round FF_j, GG_j, and Tj
    // =========================================================================
    wire is_early_round;
    assign is_early_round = (round_cnt <= 6'd15);

    // =========================================================================
    // Tj constant: Tj = 0x79cc4519 (j<=15) or 0x7a879d8a (j>=16)
    // =========================================================================
    wire [31:0] Tj;
    assign Tj = is_early_round ? 32'h79cc4519 : 32'h7a879d8a;

    // =========================================================================
    // Barrel shifter: ROL(Tj, round_cnt % 32)
    // 5-stage cascaded mux for variable-distance left rotation.
    // Each stage conditionally rotates by a power-of-2 amount (1,2,4,8,16).
    // =========================================================================
    wire [4:0] shamt;
    assign shamt = round_cnt[4:0];

    wire [31:0] bsh_s1;
    wire [31:0] bsh_s2;
    wire [31:0] bsh_s4;
    wire [31:0] bsh_s8;
    wire [31:0] Tj_rol;

    assign bsh_s1 = shamt[0] ? {Tj[30:0], Tj[31]}            : Tj;
    assign bsh_s2 = shamt[1] ? {bsh_s1[29:0], bsh_s1[31:30]} : bsh_s1;
    assign bsh_s4 = shamt[2] ? {bsh_s2[27:0], bsh_s2[31:28]} : bsh_s2;
    assign bsh_s8 = shamt[3] ? {bsh_s4[23:0], bsh_s4[31:24]} : bsh_s4;
    assign Tj_rol = shamt[4] ? {bsh_s8[15:0], bsh_s8[31:16]} : bsh_s8;

    // =========================================================================
    // Boolean functions FF_j and GG_j (32-bit inputs)
    //   FF_j: j<=15 -> X^Y^Z;  j>=16 -> (X&Y)|(X&Z)|(Y&Z)
    //   GG_j: j<=15 -> X^Y^Z;  j>=16 -> (X&Y)|(~X&Z)
    // =========================================================================
    wire [31:0] FF_j;
    wire [31:0] GG_j;

    assign FF_j = is_early_round
        ? (A_reg ^ B_reg ^ C_reg)
        : ((A_reg & B_reg) | (A_reg & C_reg) | (B_reg & C_reg));

    assign GG_j = is_early_round
        ? (E_reg ^ F_reg ^ G_reg)
        : ((E_reg & F_reg) | (~E_reg & G_reg));

    // =========================================================================
    // Constant-distance rotations
    //   ROL(A,12): {A[19:0], A[31:20]}
    //   ROL(B, 9): {B[22:0], B[31:23]}
    //   ROL(F,19): {F[12:0], F[31:13]}
    // =========================================================================
    wire [31:0] A_rol12;
    wire [31:0] B_rol9;
    wire [31:0] F_rol19;

    assign A_rol12 = {A_reg[19:0], A_reg[31:20]};
    assign B_rol9  = {B_reg[22:0], B_reg[31:23]};
    assign F_rol19 = {F_reg[12:0], F_reg[31:13]};

    // =========================================================================
    // SS1 = ROL( ROL(A,12) + E + ROL(Tj, j%32) , 7)
    // SS2 = SS1 ^ ROL(A,12)
    // =========================================================================
    wire [31:0] SS1;
    wire [31:0] SS2;

    wire [31:0] ss1_intermediate;
    assign ss1_intermediate = A_rol12 + E_reg + Tj_rol;
    assign SS1 = {ss1_intermediate[24:0], ss1_intermediate[31:25]};
    assign SS2 = SS1 ^ A_rol12;

    // =========================================================================
    // TT1 = FF_j(A,B,C) + D + SS2 + W'_j
    //   Balanced tree: (FF_j + D) + (SS2 + W'_j)
    // TT2 = GG_j(E,F,G) + H + SS1 + W_j
    //   Balanced tree: (GG_j + H) + (SS1 + W_j)
    // =========================================================================
    wire [31:0] TT1;
    wire [31:0] TT2;

    wire [31:0] tt1_part1;
    wire [31:0] tt1_part2;
    assign tt1_part1 = FF_j + D_reg;
    assign tt1_part2 = SS2 + w_prime_j;
    assign TT1 = tt1_part1 + tt1_part2;

    wire [31:0] tt2_part1;
    wire [31:0] tt2_part2;
    assign tt2_part1 = GG_j + H_reg;
    assign tt2_part2 = SS1 + w_j;
    assign TT2 = tt2_part1 + tt2_part2;

    // =========================================================================
    // P0(X) = X ^ ROL(X,9) ^ ROL(X,17)
    // =========================================================================
    wire [31:0] P0_TT2;
    assign P0_TT2 = TT2 ^ {TT2[22:0], TT2[31:23]} ^ {TT2[14:0], TT2[31:15]};

    // =========================================================================
    // Compression round next-state values
    //   A_next = TT1, B_next = A, C_next = ROL(B,9), D_next = C
    //   E_next = P0(TT2), F_next = E, G_next = ROL(F,19), H_next = G
    // =========================================================================
    wire [31:0] A_next;
    wire [31:0] B_next;
    wire [31:0] C_next;
    wire [31:0] D_next;
    wire [31:0] E_next;
    wire [31:0] F_next;
    wire [31:0] G_next;
    wire [31:0] H_next;

    assign A_next = TT1;
    assign B_next = A_reg;
    assign C_next = B_rol9;
    assign D_next = C_reg;
    assign E_next = P0_TT2;
    assign F_next = E_reg;
    assign G_next = F_rol19;
    assign H_next = G_reg;

    // =========================================================================
    // V register update: V_i_next = V_i_reg XOR {A,B,C,D,E,F,G,H}_reg
    // =========================================================================
    wire [31:0] V0_next;
    wire [31:0] V1_next;
    wire [31:0] V2_next;
    wire [31:0] V3_next;
    wire [31:0] V4_next;
    wire [31:0] V5_next;
    wire [31:0] V6_next;
    wire [31:0] V7_next;

    assign V0_next = V0_reg ^ A_reg;
    assign V1_next = V1_reg ^ B_reg;
    assign V2_next = V2_reg ^ C_reg;
    assign V3_next = V3_reg ^ D_reg;
    assign V4_next = V4_reg ^ E_reg;
    assign V5_next = V5_reg ^ F_reg;
    assign V6_next = V6_reg ^ G_reg;
    assign V7_next = V7_reg ^ H_reg;

    // =========================================================================
    // Sequential block: register updates (synchronous reset, active-low rst_n)
    //   load_en:     A~H <= V
    //   calc_en:     A~H <= compression round result
    //   update_v_en: V <= V XOR {A~H}
    //   !rst_n:      reset V to IV, A~H to 0  (at end, overrides all NBA)
    // =========================================================================
    always @(posedge clk) begin
        if (load_en) begin
            A_reg <= V0_reg;
            B_reg <= V1_reg;
            C_reg <= V2_reg;
            D_reg <= V3_reg;
            E_reg <= V4_reg;
            F_reg <= V5_reg;
            G_reg <= V6_reg;
            H_reg <= V7_reg;
        end else if (calc_en) begin
            A_reg <= A_next;
            B_reg <= B_next;
            C_reg <= C_next;
            D_reg <= D_next;
            E_reg <= E_next;
            F_reg <= F_next;
            G_reg <= G_next;
            H_reg <= H_next;
        end
        if (update_v_en) begin
            V0_reg <= V0_next;
            V1_reg <= V1_next;
            V2_reg <= V2_next;
            V3_reg <= V3_next;
            V4_reg <= V4_next;
            V5_reg <= V5_next;
            V6_reg <= V6_next;
            V7_reg <= V7_next;
        end
        if (!rst_n) begin
            A_reg <= 32'd0;
            B_reg <= 32'd0;
            C_reg <= 32'd0;
            D_reg <= 32'd0;
            E_reg <= 32'd0;
            F_reg <= 32'd0;
            G_reg <= 32'd0;
            H_reg <= 32'd0;
            V0_reg <= 32'h7380166f;
            V1_reg <= 32'h4914b2b9;
            V2_reg <= 32'h172442d7;
            V3_reg <= 32'hda8a0600;
            V4_reg <= 32'ha96f30bc;
            V5_reg <= 32'h163138aa;
            V6_reg <= 32'he38dee4d;
            V7_reg <= 32'hb0fb0e4e;
        end
    end

    // =========================================================================
    // Output: hash_out = {V0, V1, ..., V7}  (combinational from V registers)
    // =========================================================================
    assign hash_out = {V0_reg, V1_reg, V2_reg, V3_reg,
                       V4_reg, V5_reg, V6_reg, V7_reg};

endmodule

`resetall

// -----------------------------------------------------------------------------
// File   : sm3_compress.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 compression function datapath. Computes one round of SM3 compression
//   (FF, GG, P0, P1, SS1, SS2, TT1, TT2) per cycle and updates A~H working
//   registers. Maintains V0~V7 chaining value registers with SM3 IV as reset
//   default. Responds to load_en, calc_en, and update_v_en from sm3_fsm.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_compress
(
    input  wire         clk,
    input  wire         rst,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire         update_v_en,
    input  wire [5:0]   round_cnt,
    input  wire [31:0]  w_j,
    input  wire [31:0]  w_prime_j,
    output wire [255:0] hash_out
);

    ////////////////////////////////////////////////////////////////////////////////
    // Constants                                                                   //
    ////////////////////////////////////////////////////////////////////////////////

    // SM3 Initial Value (IV) per GM/T 0004-2012
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    // Round constants T_j
    localparam [31:0] T_EARLY = 32'h79cc4519;
    localparam [31:0] T_LATE  = 32'h7a879d8a;

    ////////////////////////////////////////////////////////////////////////////////
    // Registers                                                                   //
    ////////////////////////////////////////////////////////////////////////////////

    // Chaining value registers V0~V7
    reg [31:0] V0_reg = IV0, V0_next;
    reg [31:0] V1_reg = IV1, V1_next;
    reg [31:0] V2_reg = IV2, V2_next;
    reg [31:0] V3_reg = IV3, V3_next;
    reg [31:0] V4_reg = IV4, V4_next;
    reg [31:0] V5_reg = IV5, V5_next;
    reg [31:0] V6_reg = IV6, V6_next;
    reg [31:0] V7_reg = IV7, V7_next;

    // Working registers A~H
    reg [31:0] A_reg = 32'd0, A_next;
    reg [31:0] B_reg = 32'd0, B_next;
    reg [31:0] C_reg = 32'd0, C_next;
    reg [31:0] D_reg = 32'd0, D_next;
    reg [31:0] E_reg = 32'd0, E_next;
    reg [31:0] F_reg = 32'd0, F_next;
    reg [31:0] G_reg = 32'd0, G_next;
    reg [31:0] H_reg = 32'd0, H_next;

    ////////////////////////////////////////////////////////////////////////////////
    // Combinational signals                                                       //
    ////////////////////////////////////////////////////////////////////////////////

    // Intermediate round computation signals
    reg [31:0] a_rot12;
    reg [31:0] b_rot9;
    reg [31:0] f_rot19;
    reg [31:0] ff_result;
    reg [31:0] gg_result;
    reg [31:0] T_sel;
    reg [31:0] T_rot;
    reg [5:0]  rot_amt;
    reg [31:0] sum_ae;
    reg [31:0] sum_aet;
    reg [31:0] ss1;
    reg [31:0] ss2;
    reg [31:0] sum_ff_d;
    reg [31:0] sum_ss2_wp;
    reg [31:0] sum_gg_h;
    reg [31:0] sum_ss1_wj;
    reg [31:0] tt1;
    reg [31:0] tt2;
    reg [31:0] a_new,  b_new,  c_new,  d_new;
    reg [31:0] e_new,  f_new,  g_new,  h_new;

    ////////////////////////////////////////////////////////////////////////////////
    // Combinational logic: compute all _next signals                              //
    ////////////////////////////////////////////////////////////////////////////////

    always @* begin
        // Defaults: hold current values
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

        // Intermediate signal defaults (don't-care when not in calc_en)
        a_rot12    = {32{1'b0}};
        b_rot9     = {32{1'b0}};
        f_rot19    = {32{1'b0}};
        ff_result  = {32{1'b0}};
        gg_result  = {32{1'b0}};
        T_sel      = {32{1'b0}};
        T_rot      = {32{1'b0}};
        rot_amt    = 6'd0;
        sum_ae     = {32{1'b0}};
        sum_aet    = {32{1'b0}};
        ss1        = {32{1'b0}};
        ss2        = {32{1'b0}};
        sum_ff_d   = {32{1'b0}};
        sum_ss2_wp = {32{1'b0}};
        sum_gg_h   = {32{1'b0}};
        sum_ss1_wj = {32{1'b0}};
        tt1        = {32{1'b0}};
        tt2        = {32{1'b0}};
        a_new      = {32{1'b0}};
        b_new      = {32{1'b0}};
        c_new      = {32{1'b0}};
        d_new      = {32{1'b0}};
        e_new      = {32{1'b0}};
        f_new      = {32{1'b0}};
        g_new      = {32{1'b0}};
        h_new      = {32{1'b0}};

        if (load_en) begin
            // Load working registers from current chaining value
            A_next = V0_reg;
            B_next = V1_reg;
            C_next = V2_reg;
            D_next = V3_reg;
            E_next = V4_reg;
            F_next = V5_reg;
            G_next = V6_reg;
            H_next = V7_reg;
        end else if (calc_en) begin
            // ---- Select round constant T_j ----
            if (round_cnt < 6'd16) begin
                T_sel = T_EARLY;
            end else begin
                T_sel = T_LATE;
            end

            // ---- ROL(T_sel, round_cnt mod 32) ----
            rot_amt = {1'b0, round_cnt[4:0]};
            T_rot   = (T_sel << rot_amt) | (T_sel >> (6'd32 - rot_amt));

            // ---- Fixed ROL operations (wiring) ----
            a_rot12 = {A_reg[19:0], A_reg[31:20]};    // ROL(A, 12)
            b_rot9  = {B_reg[22:0], B_reg[31:23]};    // ROL(B, 9)
            f_rot19 = {F_reg[12:0], F_reg[31:13]};    // ROL(F, 19)

            // ---- Boolean functions FF and GG ----
            if (round_cnt < 6'd16) begin
                ff_result = A_reg ^ B_reg ^ C_reg;
                gg_result = E_reg ^ F_reg ^ G_reg;
            end else begin
                ff_result = (A_reg & B_reg) | (A_reg & C_reg) | (B_reg & C_reg);
                gg_result = (E_reg & F_reg) | ((~E_reg) & G_reg);
            end

            // ---- SS1 = ROL(A_rot12 + E + T_rot, 7) ----
            sum_ae  = a_rot12 + E_reg;
            sum_aet = sum_ae + T_rot;
            ss1     = {sum_aet[24:0], sum_aet[31:25]};   // ROL(..., 7)

            // ---- SS2 = SS1 XOR A_rot12 ----
            ss2 = ss1 ^ a_rot12;

            // ---- TT1 = FF + D + SS2 + w_prime_j (adder tree balanced) ----
            sum_ff_d   = ff_result + D_reg;
            sum_ss2_wp = ss2 + w_prime_j;
            tt1 = sum_ff_d + sum_ss2_wp;

            // ---- TT2 = GG + H + SS1 + w_j (adder tree balanced) ----
            sum_gg_h   = gg_result + H_reg;
            sum_ss1_wj = ss1 + w_j;
            tt2 = sum_gg_h + sum_ss1_wj;

            // ---- Next working register values ----
            a_new = tt1;
            b_new = A_reg;
            c_new = b_rot9;
            d_new = C_reg;
            e_new = tt2 ^ {tt2[22:0], tt2[31:23]} ^ {tt2[14:0], tt2[31:15]}; // P0(TT2)
            f_new = E_reg;
            g_new = f_rot19;
            h_new = G_reg;

            // Drive next-state outputs
            A_next = a_new;
            B_next = b_new;
            C_next = c_new;
            D_next = d_new;
            E_next = e_new;
            F_next = f_new;
            G_next = g_new;
            H_next = h_new;
        end else if (update_v_en) begin
            // Update chaining value: V_new = V_old XOR {A,B,C,D,E,F,G,H}
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

    ////////////////////////////////////////////////////////////////////////////////
    // Sequential logic: register update                                           //
    ////////////////////////////////////////////////////////////////////////////////

    always @(posedge clk) begin
        V0_reg <= V0_next;
        V1_reg <= V1_next;
        V2_reg <= V2_next;
        V3_reg <= V3_next;
        V4_reg <= V4_next;
        V5_reg <= V5_next;
        V6_reg <= V6_next;
        V7_reg <= V7_next;

        A_reg <= A_next;
        B_reg <= B_next;
        C_reg <= C_next;
        D_reg <= D_next;
        E_reg <= E_next;
        F_reg <= F_next;
        G_reg <= G_next;
        H_reg <= H_next;

        if (rst) begin
            V0_reg <= IV0;
            V1_reg <= IV1;
            V2_reg <= IV2;
            V3_reg <= IV3;
            V4_reg <= IV4;
            V5_reg <= IV5;
            V6_reg <= IV6;
            V7_reg <= IV7;

            A_reg <= 32'd0;
            B_reg <= 32'd0;
            C_reg <= 32'd0;
            D_reg <= 32'd0;
            E_reg <= 32'd0;
            F_reg <= 32'd0;
            G_reg <= 32'd0;
            H_reg <= 32'd0;
        end
    end

    ////////////////////////////////////////////////////////////////////////////////
    // Output assignment                                                           //
    ////////////////////////////////////////////////////////////////////////////////

    assign hash_out = {V0_reg, V1_reg, V2_reg, V3_reg, V4_reg, V5_reg, V6_reg, V7_reg};

endmodule

`resetall

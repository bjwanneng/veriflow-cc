// -----------------------------------------------------------------------------
// File   : sm3_compress.v
// Author : VeriFlow-CC
// Date   : 2026-04-27
// -----------------------------------------------------------------------------
// Description:
//   SM3 compression datapath. Computes single-round A~H update using FF, GG,
//   P0 functions and 32-bit adders. Stores chaining variable V and produces
//   256-bit hash_out.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-27  VeriFlow-CC  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module sm3_compress
(
    input  wire        clk,
    input  wire        rst,
    input  wire        load_en,
    input  wire        calc_en,
    input  wire        update_v_en,
    input  wire [5:0]  round_cnt,
    input  wire [31:0] w_j,
    input  wire [31:0] w_prime_j,
    output wire [255:0] hash_out
);

    // -------------------------------------------------------------------------
    // Constants
    // -------------------------------------------------------------------------
    localparam [31:0] IV0 = 32'h7380166f;
    localparam [31:0] IV1 = 32'h4914b2b9;
    localparam [31:0] IV2 = 32'h172442d7;
    localparam [31:0] IV3 = 32'hda8a0600;
    localparam [31:0] IV4 = 32'ha96f30bc;
    localparam [31:0] IV5 = 32'h163138aa;
    localparam [31:0] IV6 = 32'he38dee4d;
    localparam [31:0] IV7 = 32'hb0fb0e4e;

    localparam [31:0] TJ_0_15  = 32'h79cc4519;
    localparam [31:0] TJ_16_63 = 32'h7a879d8a;

    // -------------------------------------------------------------------------
    // Registers
    // -------------------------------------------------------------------------
    reg [31:0] a_reg = IV0, a_next;
    reg [31:0] b_reg = IV1, b_next;
    reg [31:0] c_reg = IV2, c_next;
    reg [31:0] d_reg = IV3, d_next;
    reg [31:0] e_reg = IV4, e_next;
    reg [31:0] f_reg = IV5, f_next;
    reg [31:0] g_reg = IV6, g_next;
    reg [31:0] h_reg = IV7, h_next;

    reg [31:0] v_reg [0:7];

    // -------------------------------------------------------------------------
    // Combinational signals
    // -------------------------------------------------------------------------
    reg [31:0] tj_val;
    reg [31:0] rol_tj_round;
    reg [31:0] rol_a_12;
    reg [31:0] ss1_raw;
    reg [31:0] ss1;
    reg [31:0] ss2;
    reg [31:0] ff_val;
    reg [31:0] gg_val;
    reg [31:0] tt1;
    reg [31:0] tt2;
    reg [31:0] p0_tt2;
    reg [31:0] rol_b_9;
    reg [31:0] rol_f_19;

    // -------------------------------------------------------------------------
    // ROL helper: rotate left by k bits on 32-bit value
    // -------------------------------------------------------------------------
    function [31:0] rol32;
        input [31:0] x;
        input [5:0]  k;
        begin
            case (k[4:0])
                5'd0:  rol32 = x;
                5'd1:  rol32 = {x[30:0], x[31]};
                5'd2:  rol32 = {x[29:0], x[31:30]};
                5'd3:  rol32 = {x[28:0], x[31:29]};
                5'd4:  rol32 = {x[27:0], x[31:28]};
                5'd5:  rol32 = {x[26:0], x[31:27]};
                5'd6:  rol32 = {x[25:0], x[31:26]};
                5'd7:  rol32 = {x[24:0], x[31:25]};
                5'd8:  rol32 = {x[23:0], x[31:24]};
                5'd9:  rol32 = {x[22:0], x[31:23]};
                5'd10: rol32 = {x[21:0], x[31:22]};
                5'd11: rol32 = {x[20:0], x[31:21]};
                5'd12: rol32 = {x[19:0], x[31:20]};
                5'd13: rol32 = {x[18:0], x[31:19]};
                5'd14: rol32 = {x[17:0], x[31:18]};
                5'd15: rol32 = {x[16:0], x[31:17]};
                5'd16: rol32 = {x[15:0], x[31:16]};
                5'd17: rol32 = {x[14:0], x[31:15]};
                5'd18: rol32 = {x[13:0], x[31:14]};
                5'd19: rol32 = {x[12:0], x[31:13]};
                5'd20: rol32 = {x[11:0], x[31:12]};
                5'd21: rol32 = {x[10:0], x[31:11]};
                5'd22: rol32 = {x[9:0],  x[31:10]};
                5'd23: rol32 = {x[8:0],  x[31:9]};
                5'd24: rol32 = {x[7:0],  x[31:8]};
                5'd25: rol32 = {x[6:0],  x[31:7]};
                5'd26: rol32 = {x[5:0],  x[31:6]};
                5'd27: rol32 = {x[4:0],  x[31:5]};
                5'd28: rol32 = {x[3:0],  x[31:4]};
                5'd29: rol32 = {x[2:0],  x[31:3]};
                5'd30: rol32 = {x[1:0],  x[31:2]};
                5'd31: rol32 = {x[0],    x[31:1]};
            endcase
        end
    endfunction

    // -------------------------------------------------------------------------
    // P0 helper: X ^ ROL(X,9) ^ ROL(X,17)
    // -------------------------------------------------------------------------
    function [31:0] p0;
        input [31:0] x;
        begin
            p0 = x ^ rol32(x, 6'd9) ^ rol32(x, 6'd17);
        end
    endfunction

    // -------------------------------------------------------------------------
    // Combinational logic block
    // -------------------------------------------------------------------------
    always @* begin
        // Default next-state: hold current values
        a_next = a_reg;
        b_next = b_reg;
        c_next = c_reg;
        d_next = d_reg;
        e_next = e_reg;
        f_next = f_reg;
        g_next = g_reg;
        h_next = h_reg;

        // Default combinational intermediates
        tj_val     = TJ_0_15;
        rol_tj_round = 32'd0;
        rol_a_12   = 32'd0;
        ss1_raw    = 32'd0;
        ss1        = 32'd0;
        ss2        = 32'd0;
        ff_val     = 32'd0;
        gg_val     = 32'd0;
        tt1        = 32'd0;
        tt2        = 32'd0;
        p0_tt2     = 32'd0;
        rol_b_9    = 32'd0;
        rol_f_19   = 32'd0;

        if (load_en) begin
            a_next = v_reg[0];
            b_next = v_reg[1];
            c_next = v_reg[2];
            d_next = v_reg[3];
            e_next = v_reg[4];
            f_next = v_reg[5];
            g_next = v_reg[6];
            h_next = v_reg[7];
        end else if (calc_en) begin
            // Tj selection
            if (round_cnt < 6'd16) begin
                tj_val = TJ_0_15;
            end else begin
                tj_val = TJ_16_63;
            end

            rol_tj_round = rol32(tj_val, round_cnt);
            rol_a_12     = rol32(a_reg, 6'd12);

            // SS1 = ROL(ROL(A,12) + E + ROL(Tj, round_cnt), 7)
            ss1_raw = rol_a_12 + e_reg + rol_tj_round;
            ss1     = rol32(ss1_raw, 6'd7);

            // SS2 = SS1 ^ ROL(A, 12)
            ss2 = ss1 ^ rol_a_12;

            // FF and GG
            if (round_cnt < 6'd16) begin
                ff_val = a_reg ^ b_reg ^ c_reg;
                gg_val = e_reg ^ f_reg ^ g_reg;
            end else begin
                ff_val = (a_reg & b_reg) | (a_reg & c_reg) | (b_reg & c_reg);
                gg_val = (e_reg & f_reg) | ((~e_reg) & g_reg);
            end

            // TT1 = FF + D + SS2 + w_prime_j
            tt1 = ff_val + d_reg + ss2 + w_prime_j;

            // TT2 = GG + H + SS1 + w_j
            tt2 = gg_val + h_reg + ss1 + w_j;

            // P0(TT2)
            p0_tt2 = p0(tt2);

            // Rotations for C and G
            rol_b_9  = rol32(b_reg, 6'd9);
            rol_f_19 = rol32(f_reg, 6'd19);

            // Update working variables
            d_next = c_reg;
            c_next = rol_b_9;
            b_next = a_reg;
            a_next = tt1;
            h_next = g_reg;
            g_next = rol_f_19;
            f_next = e_reg;
            e_next = p0_tt2;
        end else if (update_v_en) begin
            // V = V xor {A,B,C,D,E,F,G,H}
            // These are combinational values for V update, but since update_v_en
            // is a one-cycle pulse, we compute the xor here and let the seq block
            // capture it. However V is a memory array, so we handle it in the
            // sequential block directly. We leave a_next..h_next as hold.
        end
    end

    // -------------------------------------------------------------------------
    // Sequential block
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        a_reg <= a_next;
        b_reg <= b_next;
        c_reg <= c_next;
        d_reg <= d_next;
        e_reg <= e_next;
        f_reg <= f_next;
        g_reg <= g_next;
        h_reg <= h_next;

        if (update_v_en) begin
            v_reg[0] = v_reg[0] ^ a_reg;
            v_reg[1] = v_reg[1] ^ b_reg;
            v_reg[2] = v_reg[2] ^ c_reg;
            v_reg[3] = v_reg[3] ^ d_reg;
            v_reg[4] = v_reg[4] ^ e_reg;
            v_reg[5] = v_reg[5] ^ f_reg;
            v_reg[6] = v_reg[6] ^ g_reg;
            v_reg[7] = v_reg[7] ^ h_reg;
        end

        if (rst) begin
            a_reg <= IV0;
            b_reg <= IV1;
            c_reg <= IV2;
            d_reg <= IV3;
            e_reg <= IV4;
            f_reg <= IV5;
            g_reg <= IV6;
            h_reg <= IV7;

            v_reg[0] = IV0;
            v_reg[1] = IV1;
            v_reg[2] = IV2;
            v_reg[3] = IV3;
            v_reg[4] = IV4;
            v_reg[5] = IV5;
            v_reg[6] = IV6;
            v_reg[7] = IV7;
        end
    end

    // -------------------------------------------------------------------------
    // Output assignment
    // -------------------------------------------------------------------------
    assign hash_out = {v_reg[0], v_reg[1], v_reg[2], v_reg[3],
                       v_reg[4], v_reg[5], v_reg[6], v_reg[7]};

endmodule

`resetall

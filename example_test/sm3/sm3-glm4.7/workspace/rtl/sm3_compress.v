// ============================================================
// sm3_compress -- SM3 compression datapath (A..H + V0..V7 regs)
//   - Active-low SYNC reset rst_n
//   - Cycle 1: A..H <= V              (load_en)
//   - Cycles 2..65: 64 rounds         (calc_en)
//   - Cycle 66: V <= V XOR {A..H}     (update_v_en)
//   - hash_out = {V_regs[0..7]}, V_regs[0] is MSB
// ============================================================
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

    // -------------------------------------------------------------
    // State registers
    // -------------------------------------------------------------
    reg [31:0] a_reg, b_reg, c_reg, d_reg;
    reg [31:0] e_reg, f_reg, g_reg, h_reg;
    reg [31:0] v_regs [0:7];

    // -------------------------------------------------------------
    // Constant T_j
    // -------------------------------------------------------------
    wire        j_lt_16 = (round_cnt < 6'd16);
    wire [31:0] t_j     = j_lt_16 ? 32'h79CC4519 : 32'h7A879D8A;

    // -------------------------------------------------------------
    // ROL T_j by (round_cnt mod 32) -- 32:1 mux
    // -------------------------------------------------------------
    wire [4:0] rot_k = round_cnt[4:0];
    reg  [31:0] rol_t;
    always @* begin
        case (rot_k)
            5'd0:  rol_t = t_j;
            5'd1:  rol_t = {t_j[30:0], t_j[31:31]};
            5'd2:  rol_t = {t_j[29:0], t_j[31:30]};
            5'd3:  rol_t = {t_j[28:0], t_j[31:29]};
            5'd4:  rol_t = {t_j[27:0], t_j[31:28]};
            5'd5:  rol_t = {t_j[26:0], t_j[31:27]};
            5'd6:  rol_t = {t_j[25:0], t_j[31:26]};
            5'd7:  rol_t = {t_j[24:0], t_j[31:25]};
            5'd8:  rol_t = {t_j[23:0], t_j[31:24]};
            5'd9:  rol_t = {t_j[22:0], t_j[31:23]};
            5'd10: rol_t = {t_j[21:0], t_j[31:22]};
            5'd11: rol_t = {t_j[20:0], t_j[31:21]};
            5'd12: rol_t = {t_j[19:0], t_j[31:20]};
            5'd13: rol_t = {t_j[18:0], t_j[31:19]};
            5'd14: rol_t = {t_j[17:0], t_j[31:18]};
            5'd15: rol_t = {t_j[16:0], t_j[31:17]};
            5'd16: rol_t = {t_j[15:0], t_j[31:16]};
            5'd17: rol_t = {t_j[14:0], t_j[31:15]};
            5'd18: rol_t = {t_j[13:0], t_j[31:14]};
            5'd19: rol_t = {t_j[12:0], t_j[31:13]};
            5'd20: rol_t = {t_j[11:0], t_j[31:12]};
            5'd21: rol_t = {t_j[10:0], t_j[31:11]};
            5'd22: rol_t = {t_j[9:0],  t_j[31:10]};
            5'd23: rol_t = {t_j[8:0],  t_j[31:9]};
            5'd24: rol_t = {t_j[7:0],  t_j[31:8]};
            5'd25: rol_t = {t_j[6:0],  t_j[31:7]};
            5'd26: rol_t = {t_j[5:0],  t_j[31:6]};
            5'd27: rol_t = {t_j[4:0],  t_j[31:5]};
            5'd28: rol_t = {t_j[3:0],  t_j[31:4]};
            5'd29: rol_t = {t_j[2:0],  t_j[31:3]};
            5'd30: rol_t = {t_j[1:0],  t_j[31:2]};
            5'd31: rol_t = {t_j[0:0],  t_j[31:1]};
            default: rol_t = t_j;
        endcase
    end

    // -------------------------------------------------------------
    // Fixed rotations on current A..H state
    // -------------------------------------------------------------
    // ROL(A, 12)
    wire [31:0] rol_a_12 = {a_reg[19:0], a_reg[31:20]};
    // ROL(B, 9)
    wire [31:0] rol_b_9  = {b_reg[22:0], b_reg[31:23]};
    // ROL(F, 19)
    wire [31:0] rol_f_19 = {f_reg[12:0], f_reg[31:13]};

    // -------------------------------------------------------------
    // SS1 = ROL((ROL(A,12) + E + ROL(Tj, j%32)), 7)
    // -------------------------------------------------------------
    wire [31:0] ss1_pre = rol_a_12 + e_reg + rol_t;
    wire [31:0] ss1     = {ss1_pre[24:0], ss1_pre[31:25]};
    wire [31:0] ss2     = ss1 ^ rol_a_12;

    // -------------------------------------------------------------
    // FF / GG
    // -------------------------------------------------------------
    wire [31:0] ff_xor  = a_reg ^ b_reg ^ c_reg;
    wire [31:0] ff_maj  = (a_reg & b_reg) | (a_reg & c_reg) | (b_reg & c_reg);
    wire [31:0] ff_j    = j_lt_16 ? ff_xor : ff_maj;

    wire [31:0] gg_xor  = e_reg ^ f_reg ^ g_reg;
    wire [31:0] gg_ch   = (e_reg & f_reg) | ((~e_reg) & g_reg);
    wire [31:0] gg_j    = j_lt_16 ? gg_xor : gg_ch;

    // -------------------------------------------------------------
    // TT1 / TT2
    // -------------------------------------------------------------
    wire [31:0] tt1 = ff_j + d_reg + ss2 + w_prime_j;
    wire [31:0] tt2 = gg_j + h_reg + ss1 + w_j;

    // -------------------------------------------------------------
    // P0(TT2) = TT2 ^ ROL(TT2,9) ^ ROL(TT2,17)
    // -------------------------------------------------------------
    wire [31:0] rol_tt2_9  = {tt2[22:0], tt2[31:23]};
    wire [31:0] rol_tt2_17 = {tt2[14:0], tt2[31:15]};
    wire [31:0] p0_tt2     = tt2 ^ rol_tt2_9 ^ rol_tt2_17;

    // -------------------------------------------------------------
    // Next-state A..H
    // -------------------------------------------------------------
    wire [31:0] a_next = tt1;
    wire [31:0] b_next = a_reg;
    wire [31:0] c_next = rol_b_9;
    wire [31:0] d_next = c_reg;
    wire [31:0] e_next = p0_tt2;
    wire [31:0] f_next = e_reg;
    wire [31:0] g_next = rol_f_19;
    wire [31:0] h_next = g_reg;

    // -------------------------------------------------------------
    // Sequential: A..H register update
    // Priority: rst_n > load_en > calc_en
    // -------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            a_reg <= 32'd0;
            b_reg <= 32'd0;
            c_reg <= 32'd0;
            d_reg <= 32'd0;
            e_reg <= 32'd0;
            f_reg <= 32'd0;
            g_reg <= 32'd0;
            h_reg <= 32'd0;
        end else if (load_en) begin
            a_reg <= v_regs[0];
            b_reg <= v_regs[1];
            c_reg <= v_regs[2];
            d_reg <= v_regs[3];
            e_reg <= v_regs[4];
            f_reg <= v_regs[5];
            g_reg <= v_regs[6];
            h_reg <= v_regs[7];
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

    // -------------------------------------------------------------
    // Sequential: V_regs update
    // Reset to IV; on update_v_en, V <= V XOR {A..H}
    // -------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            v_regs[0] <= 32'h7380166F;
            v_regs[1] <= 32'h4914B2B9;
            v_regs[2] <= 32'h172442D7;
            v_regs[3] <= 32'hDA8A0600;
            v_regs[4] <= 32'hA96F30BC;
            v_regs[5] <= 32'h163138AA;
            v_regs[6] <= 32'hE38DEE4D;
            v_regs[7] <= 32'hB0FB0E4E;
        end else if (update_v_en) begin
            v_regs[0] <= v_regs[0] ^ a_reg;
            v_regs[1] <= v_regs[1] ^ b_reg;
            v_regs[2] <= v_regs[2] ^ c_reg;
            v_regs[3] <= v_regs[3] ^ d_reg;
            v_regs[4] <= v_regs[4] ^ e_reg;
            v_regs[5] <= v_regs[5] ^ f_reg;
            v_regs[6] <= v_regs[6] ^ g_reg;
            v_regs[7] <= v_regs[7] ^ h_reg;
        end
    end

    // -------------------------------------------------------------
    // Output: hash_out = {V0, V1, ..., V7}, V0 in MSBs
    // -------------------------------------------------------------
    assign hash_out = {v_regs[0], v_regs[1], v_regs[2], v_regs[3],
                       v_regs[4], v_regs[5], v_regs[6], v_regs[7]};

endmodule

`resetall

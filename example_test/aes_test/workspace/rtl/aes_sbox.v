// -----------------------------------------------------------------------------
// File   : aes_sbox.v
// Author : Auto-generated
// Date   : 2026-04-18
// -----------------------------------------------------------------------------
// Description:
//   AES S-Box (Substitution Box) 查找表模块。
//   本模块实现了 FIPS-197 标准中定义的 AES S-Box，是一个纯组合逻辑的
//   8-bit 输入到 8-bit 输出的查找表。S-Box 是 AES 加密算法中提供非线性
//   变换的核心组件，用于 SubBytes 和 SubWord 操作。
//
//   AES S-Box 的数学构造基于两步运算：
//     1. 在有限域 GF(2^8)（不可约多项式 x^8+x^4+x^3+x+1，即 0x11B）
//        中对输入字节求乘法逆元（0 映射到自身）
//     2. 对逆元结果施加一个仿射变换（矩阵乘法 + 常量 0x63 异或）
//
//   本实现采用 256 条 case 语句直接硬编码所有预计算值，综合后映射为
//   查找表 LUT 资源，无需 BRAM，延迟为纯组合逻辑延迟。
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-18  Auto-generated  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_sbox
(
    // 8-bit S-Box 地址输入（待替换的字节值）
    input  wire [7:0] addr,
    // 8-bit S-Box 数据输出（替换后的字节值）
    output wire [7:0] dout
);

// -------------------------------------------------------------------------
// S-Box 查找表（纯组合逻辑）
// 输入 addr 的范围是 0x00 ~ 0xFF，共 256 个条目。
// 每个条目对应 FIPS-197 Figure 7 中定义的替换值。
//
// S-Box 按照标准以 16 行 x 16 列的矩阵形式呈现：
//   addr 高 4 位 (addr[7:4]) 选择行号 (y)
//   addr 低 4 位 (addr[3:0]) 选择列号 (x)
//   输出值 = SBox[y][x]
// -------------------------------------------------------------------------

// 内部寄存器，用于在组合逻辑 always 块中计算输出
reg [7:0] dout_next = 8'h00;

always @* begin
    // 默认值：防止产生锁存器
    dout_next = 8'h00;

    case (addr)
        // -----------------------------------------------------------------
        // 行 0x0: addr = 0x00 ~ 0x0F
        // -----------------------------------------------------------------
        // 这些值是 AES S-Box 的第 0 行。例如 addr=0x00 时输出 0x63，
        // 0x63 的二进制为 0110_0011，这是仿射变换中常量异或值本身，
        // 因为 0 的乘法逆元仍为 0，仿射变换后得到 0x63。
        8'h00: dout_next = 8'h63;
        8'h01: dout_next = 8'h7C;
        8'h02: dout_next = 8'h77;
        8'h03: dout_next = 8'h7B;
        8'h04: dout_next = 8'hF2;
        8'h05: dout_next = 8'h6B;
        8'h06: dout_next = 8'h6F;
        8'h07: dout_next = 8'hC5;
        8'h08: dout_next = 8'h30;
        8'h09: dout_next = 8'h01;
        8'h0A: dout_next = 8'h67;
        8'h0B: dout_next = 8'h2B;
        8'h0C: dout_next = 8'hFE;
        8'h0D: dout_next = 8'hD7;
        8'h0E: dout_next = 8'hAB;
        8'h0F: dout_next = 8'h76;

        // -----------------------------------------------------------------
        // 行 0x1: addr = 0x10 ~ 0x1F
        // -----------------------------------------------------------------
        8'h10: dout_next = 8'hCA;
        8'h11: dout_next = 8'h82;
        8'h12: dout_next = 8'hC9;
        8'h13: dout_next = 8'h7D;
        8'h14: dout_next = 8'hFA;
        8'h15: dout_next = 8'h59;
        8'h16: dout_next = 8'h47;
        8'h17: dout_next = 8'hF0;
        8'h18: dout_next = 8'hAD;
        8'h19: dout_next = 8'hD4;
        8'h1A: dout_next = 8'hA2;
        8'h1B: dout_next = 8'hAF;
        8'h1C: dout_next = 8'h9C;
        8'h1D: dout_next = 8'hA4;
        8'h1E: dout_next = 8'h72;
        8'h1F: dout_next = 8'hC0;

        // -----------------------------------------------------------------
        // 行 0x2: addr = 0x20 ~ 0x2F
        // -----------------------------------------------------------------
        8'h20: dout_next = 8'hB7;
        8'h21: dout_next = 8'hFD;
        8'h22: dout_next = 8'h93;
        8'h23: dout_next = 8'h26;
        8'h24: dout_next = 8'h36;
        8'h25: dout_next = 8'h3F;
        8'h26: dout_next = 8'hF7;
        8'h27: dout_next = 8'hCC;
        8'h28: dout_next = 8'h34;
        8'h29: dout_next = 8'hA5;
        8'h2A: dout_next = 8'hE5;
        8'h2B: dout_next = 8'hF1;
        8'h2C: dout_next = 8'h71;
        8'h2D: dout_next = 8'hD8;
        8'h2E: dout_next = 8'h31;
        8'h2F: dout_next = 8'h15;

        // -----------------------------------------------------------------
        // 行 0x3: addr = 0x30 ~ 0x3F
        // -----------------------------------------------------------------
        8'h30: dout_next = 8'h04;
        8'h31: dout_next = 8'hC7;
        8'h32: dout_next = 8'h23;
        8'h33: dout_next = 8'hC3;
        8'h34: dout_next = 8'h18;
        8'h35: dout_next = 8'h96;
        8'h36: dout_next = 8'h05;
        8'h37: dout_next = 8'h9A;
        8'h38: dout_next = 8'h07;
        8'h39: dout_next = 8'h12;
        8'h3A: dout_next = 8'h80;
        8'h3B: dout_next = 8'hE2;
        8'h3C: dout_next = 8'hEB;
        8'h3D: dout_next = 8'h27;
        8'h3E: dout_next = 8'hB2;
        8'h3F: dout_next = 8'h75;

        // -----------------------------------------------------------------
        // 行 0x4: addr = 0x40 ~ 0x4F
        // -----------------------------------------------------------------
        8'h40: dout_next = 8'h09;
        8'h41: dout_next = 8'h83;
        8'h42: dout_next = 8'h2C;
        8'h43: dout_next = 8'h1A;
        8'h44: dout_next = 8'h1B;
        8'h45: dout_next = 8'h6E;
        8'h46: dout_next = 8'h5A;
        8'h47: dout_next = 8'hA0;
        8'h48: dout_next = 8'h52;
        8'h49: dout_next = 8'h3B;
        8'h4A: dout_next = 8'hD6;
        8'h4B: dout_next = 8'hB3;
        8'h4C: dout_next = 8'h29;
        8'h4D: dout_next = 8'hE3;
        8'h4E: dout_next = 8'h2F;
        8'h4F: dout_next = 8'h84;

        // -----------------------------------------------------------------
        // 行 0x5: addr = 0x50 ~ 0x5F
        // -----------------------------------------------------------------
        8'h50: dout_next = 8'h53;
        8'h51: dout_next = 8'hD1;
        8'h52: dout_next = 8'h00;
        8'h53: dout_next = 8'hED;
        8'h54: dout_next = 8'h20;
        8'h55: dout_next = 8'hFC;
        8'h56: dout_next = 8'hB1;
        8'h57: dout_next = 8'h5B;
        8'h58: dout_next = 8'h6A;
        8'h59: dout_next = 8'hCB;
        8'h5A: dout_next = 8'hBE;
        8'h5B: dout_next = 8'h39;
        8'h5C: dout_next = 8'h4A;
        8'h5D: dout_next = 8'h4C;
        8'h5E: dout_next = 8'h58;
        8'h5F: dout_next = 8'hCF;

        // -----------------------------------------------------------------
        // 行 0x6: addr = 0x60 ~ 0x6F
        // -----------------------------------------------------------------
        8'h60: dout_next = 8'hD0;
        8'h61: dout_next = 8'hEF;
        8'h62: dout_next = 8'hAA;
        8'h63: dout_next = 8'hFB;
        8'h64: dout_next = 8'h43;
        8'h65: dout_next = 8'h4D;
        8'h66: dout_next = 8'h33;
        8'h67: dout_next = 8'h85;
        8'h68: dout_next = 8'h45;
        8'h69: dout_next = 8'hF9;
        8'h6A: dout_next = 8'h02;
        8'h6B: dout_next = 8'h7F;
        8'h6C: dout_next = 8'h50;
        8'h6D: dout_next = 8'h3C;
        8'h6E: dout_next = 8'h9F;
        8'h6F: dout_next = 8'hA8;

        // -----------------------------------------------------------------
        // 行 0x7: addr = 0x70 ~ 0x7F
        // -----------------------------------------------------------------
        8'h70: dout_next = 8'h51;
        8'h71: dout_next = 8'hA3;
        8'h72: dout_next = 8'h40;
        8'h73: dout_next = 8'h8F;
        8'h74: dout_next = 8'h92;
        8'h75: dout_next = 8'h9D;
        8'h76: dout_next = 8'h38;
        8'h77: dout_next = 8'hF5;
        8'h78: dout_next = 8'hBC;
        8'h79: dout_next = 8'hB6;
        8'h7A: dout_next = 8'hDA;
        8'h7B: dout_next = 8'h21;
        8'h7C: dout_next = 8'h10;
        8'h7D: dout_next = 8'hFF;
        8'h7E: dout_next = 8'hF3;
        8'h7F: dout_next = 8'hD2;

        // -----------------------------------------------------------------
        // 行 0x8: addr = 0x80 ~ 0x8F
        // -----------------------------------------------------------------
        8'h80: dout_next = 8'hCD;
        8'h81: dout_next = 8'h0C;
        8'h82: dout_next = 8'h13;
        8'h83: dout_next = 8'hEC;
        8'h84: dout_next = 8'h5F;
        8'h85: dout_next = 8'h97;
        8'h86: dout_next = 8'h44;
        8'h87: dout_next = 8'h17;
        8'h88: dout_next = 8'hC4;
        8'h89: dout_next = 8'hA7;
        8'h8A: dout_next = 8'h7E;
        8'h8B: dout_next = 8'h3D;
        8'h8C: dout_next = 8'h64;
        8'h8D: dout_next = 8'h5D;
        8'h8E: dout_next = 8'h19;
        8'h8F: dout_next = 8'h73;

        // -----------------------------------------------------------------
        // 行 0x9: addr = 0x90 ~ 0x9F
        // -----------------------------------------------------------------
        8'h90: dout_next = 8'h60;
        8'h91: dout_next = 8'h81;
        8'h92: dout_next = 8'h4F;
        8'h93: dout_next = 8'hDC;
        8'h94: dout_next = 8'h22;
        8'h95: dout_next = 8'h2A;
        8'h96: dout_next = 8'h90;
        8'h97: dout_next = 8'h88;
        8'h98: dout_next = 8'h46;
        8'h99: dout_next = 8'hEE;
        8'h9A: dout_next = 8'hB8;
        8'h9B: dout_next = 8'h14;
        8'h9C: dout_next = 8'hDE;
        8'h9D: dout_next = 8'h5E;
        8'h9E: dout_next = 8'h0B;
        8'h9F: dout_next = 8'hDB;

        // -----------------------------------------------------------------
        // 行 0xA: addr = 0xA0 ~ 0xAF
        // -----------------------------------------------------------------
        8'hA0: dout_next = 8'hE0;
        8'hA1: dout_next = 8'h32;
        8'hA2: dout_next = 8'h3A;
        8'hA3: dout_next = 8'h0A;
        8'hA4: dout_next = 8'h49;
        8'hA5: dout_next = 8'h06;
        8'hA6: dout_next = 8'h24;
        8'hA7: dout_next = 8'h5C;
        8'hA8: dout_next = 8'hC2;
        8'hA9: dout_next = 8'hD3;
        8'hAA: dout_next = 8'hAC;
        8'hAB: dout_next = 8'h62;
        8'hAC: dout_next = 8'h91;
        8'hAD: dout_next = 8'h95;
        8'hAE: dout_next = 8'hE4;
        8'hAF: dout_next = 8'h79;

        // -----------------------------------------------------------------
        // 行 0xB: addr = 0xB0 ~ 0xBF
        // -----------------------------------------------------------------
        8'hB0: dout_next = 8'hE7;
        8'hB1: dout_next = 8'hC8;
        8'hB2: dout_next = 8'h37;
        8'hB3: dout_next = 8'h6D;
        8'hB4: dout_next = 8'h8D;
        8'hB5: dout_next = 8'hD5;
        8'hB6: dout_next = 8'h4E;
        8'hB7: dout_next = 8'hA9;
        8'hB8: dout_next = 8'h6C;
        8'hB9: dout_next = 8'h56;
        8'hBA: dout_next = 8'hF4;
        8'hBB: dout_next = 8'hEA;
        8'hBC: dout_next = 8'h65;
        8'hBD: dout_next = 8'h7A;
        8'hBE: dout_next = 8'hAE;
        8'hBF: dout_next = 8'h08;

        // -----------------------------------------------------------------
        // 行 0xC: addr = 0xC0 ~ 0xCF
        // -----------------------------------------------------------------
        8'hC0: dout_next = 8'hBA;
        8'hC1: dout_next = 8'h78;
        8'hC2: dout_next = 8'h25;
        8'hC3: dout_next = 8'h2E;
        8'hC4: dout_next = 8'h1C;
        8'hC5: dout_next = 8'hA6;
        8'hC6: dout_next = 8'hB4;
        8'hC7: dout_next = 8'hC6;
        8'hC8: dout_next = 8'hE8;
        8'hC9: dout_next = 8'hDD;
        8'hCA: dout_next = 8'h74;
        8'hCB: dout_next = 8'h1F;
        8'hCC: dout_next = 8'h4B;
        8'hCD: dout_next = 8'hBD;
        8'hCE: dout_next = 8'h8B;
        8'hCF: dout_next = 8'h8A;

        // -----------------------------------------------------------------
        // 行 0xD: addr = 0xD0 ~ 0xDF
        // -----------------------------------------------------------------
        8'hD0: dout_next = 8'h70;
        8'hD1: dout_next = 8'h3E;
        8'hD2: dout_next = 8'hB5;
        8'hD3: dout_next = 8'h66;
        8'hD4: dout_next = 8'h48;
        8'hD5: dout_next = 8'h03;
        8'hD6: dout_next = 8'hF6;
        8'hD7: dout_next = 8'h0E;
        8'hD8: dout_next = 8'h61;
        8'hD9: dout_next = 8'h35;
        8'hDA: dout_next = 8'h57;
        8'hDB: dout_next = 8'hB9;
        8'hDC: dout_next = 8'h86;
        8'hDD: dout_next = 8'hC1;
        8'hDE: dout_next = 8'h1D;
        8'hDF: dout_next = 8'h9E;

        // -----------------------------------------------------------------
        // 行 0xE: addr = 0xE0 ~ 0xEF
        // -----------------------------------------------------------------
        8'hE0: dout_next = 8'hE1;
        8'hE1: dout_next = 8'hF8;
        8'hE2: dout_next = 8'h98;
        8'hE3: dout_next = 8'h11;
        8'hE4: dout_next = 8'h69;
        8'hE5: dout_next = 8'hD9;
        8'hE6: dout_next = 8'h8E;
        8'hE7: dout_next = 8'h94;
        8'hE8: dout_next = 8'h9B;
        8'hE9: dout_next = 8'h1E;
        8'hEA: dout_next = 8'h87;
        8'hEB: dout_next = 8'hE9;
        8'hEC: dout_next = 8'hCE;
        8'hED: dout_next = 8'h55;
        8'hEE: dout_next = 8'h28;
        8'hEF: dout_next = 8'hDF;

        // -----------------------------------------------------------------
        // 行 0xF: addr = 0xF0 ~ 0xFF
        // -----------------------------------------------------------------
        8'hF0: dout_next = 8'h8C;
        8'hF1: dout_next = 8'hA1;
        8'hF2: dout_next = 8'h89;
        8'hF3: dout_next = 8'h0D;
        8'hF4: dout_next = 8'hBF;
        8'hF5: dout_next = 8'hE6;
        8'hF6: dout_next = 8'h42;
        8'hF7: dout_next = 8'h68;
        8'hF8: dout_next = 8'h41;
        8'hF9: dout_next = 8'h99;
        8'hFA: dout_next = 8'h2D;
        8'hFB: dout_next = 8'h0F;
        8'hFC: dout_next = 8'hB0;
        8'hFD: dout_next = 8'h54;
        8'hFE: dout_next = 8'hBB;
        8'hFF: dout_next = 8'h16;

        // 默认分支：所有 256 个值已覆盖，但按照编码规范必须包含 default
        default: dout_next = 8'h00;
    endcase
end

// 输出赋值：将内部组合逻辑结果连接到输出端口
assign dout = dout_next;

endmodule

`resetall

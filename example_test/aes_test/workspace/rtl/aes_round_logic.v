// -----------------------------------------------------------------------------
// File   : aes_round_logic.v
// Author : AES Design Team
// Date   : 2026-04-18
// -----------------------------------------------------------------------------
// Description:
//   AES 组合逻辑轮函数模块。执行完整的 AES 轮变换操作：
//   SubBytes（16 个并行 S-Box 查表）、ShiftRows（字节行移位重排）、
//   MixColumns（GF(2^8) 有限域列混合，使用 xtime 实现）以及
//   AddRoundKey（与轮密钥异或）。当 round_num=10 时跳过 MixColumns。
//   本模块为纯组合逻辑，不包含任何寄存器或时钟。
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-18  AES Design Team  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_round_logic
(
    // 当前 128 位 AES 状态输入
    input  wire [127:0] state_in,
    // 128 位轮密钥，用于 AddRoundKey 操作
    input  wire [127:0] round_key,
    // 当前轮次编号 (0-10)，round_num=10 时跳过 MixColumns
    input  wire [3:0]   round_num,
    // 经过完整轮变换后的 128 位状态输出
    output wire [127:0] state_out
);

    // ========================================================================
    // 内部信号声明
    // ========================================================================

    // SubBytes 阶段：16 个 S-Box 查表输出字节
    // sub_bytes 数组，每个元素 8 位，共 16 个字节
    // 索引方式：sub_bytes[i] 对应 state_in 的第 i 个字节 (从低位到高位)
    wire [7:0] sub_bytes_00;
    wire [7:0] sub_bytes_01;
    wire [7:0] sub_bytes_02;
    wire [7:0] sub_bytes_03;
    wire [7:0] sub_bytes_04;
    wire [7:0] sub_bytes_05;
    wire [7:0] sub_bytes_06;
    wire [7:0] sub_bytes_07;
    wire [7:0] sub_bytes_08;
    wire [7:0] sub_bytes_09;
    wire [7:0] sub_bytes_10;
    wire [7:0] sub_bytes_11;
    wire [7:0] sub_bytes_12;
    wire [7:0] sub_bytes_13;
    wire [7:0] sub_bytes_14;
    wire [7:0] sub_bytes_15;

    // ShiftRows 阶段：行移位后的 16 个字节
    // 按列主序排列：byte[行号 + 4*列号]
    // 行 0 不移位，行 1 左移 1 列，行 2 左移 2 列，行 3 左移 3 列
    wire [7:0] shift_rows_00;
    wire [7:0] shift_rows_01;
    wire [7:0] shift_rows_02;
    wire [7:0] shift_rows_03;
    wire [7:0] shift_rows_04;
    wire [7:0] shift_rows_05;
    wire [7:0] shift_rows_06;
    wire [7:0] shift_rows_07;
    wire [7:0] shift_rows_08;
    wire [7:0] shift_rows_09;
    wire [7:0] shift_rows_10;
    wire [7:0] shift_rows_11;
    wire [7:0] shift_rows_12;
    wire [7:0] shift_rows_13;
    wire [7:0] shift_rows_14;
    wire [7:0] shift_rows_15;

    // MixColumns 阶段：列混合后的中间结果
    // 仅在 round_num != 10 时使用；round_num=10 时直接使用 ShiftRows 结果
    wire [7:0] mix_cols_00;
    wire [7:0] mix_cols_01;
    wire [7:0] mix_cols_02;
    wire [7:0] mix_cols_03;
    wire [7:0] mix_cols_04;
    wire [7:0] mix_cols_05;
    wire [7:0] mix_cols_06;
    wire [7:0] mix_cols_07;
    wire [7:0] mix_cols_08;
    wire [7:0] mix_cols_09;
    wire [7:0] mix_cols_10;
    wire [7:0] mix_cols_11;
    wire [7:0] mix_cols_12;
    wire [7:0] mix_cols_13;
    wire [7:0] mix_cols_14;
    wire [7:0] mix_cols_15;

    // MixColumns 多路选择后的结果（根据 round_num 选择 MixColumns 或直通）
    wire [127:0] mix_or_pass;

    // xtime 辅助信号：GF(2^8) 中乘以 0x02 的中间结果
    // 每列有 4 个字节，每个字节可能需要 xtime 运算
    // xtime(a) = {a[6:0], 1'b0} ^ (a[7] ? 8'h1B : 8'h00)

    // 第 0 列的 xtime 结果
    wire [7:0] xt_col0_s0;  // xtime(shift_rows_00)
    wire [7:0] xt_col0_s1;  // xtime(shift_rows_01)
    wire [7:0] xt_col0_s2;  // xtime(shift_rows_02)
    wire [7:0] xt_col0_s3;  // xtime(shift_rows_03)

    // 第 1 列的 xtime 结果
    wire [7:0] xt_col1_s0;  // xtime(shift_rows_04)
    wire [7:0] xt_col1_s1;  // xtime(shift_rows_05)
    wire [7:0] xt_col1_s2;  // xtime(shift_rows_06)
    wire [7:0] xt_col1_s3;  // xtime(shift_rows_07)

    // 第 2 列的 xtime 结果
    wire [7:0] xt_col2_s0;  // xtime(shift_rows_08)
    wire [7:0] xt_col2_s1;  // xtime(shift_rows_09)
    wire [7:0] xt_col2_s2;  // xtime(shift_rows_10)
    wire [7:0] xt_col2_s3;  // xtime(shift_rows_11)

    // 第 3 列的 xtime 结果
    wire [7:0] xt_col3_s0;  // xtime(shift_rows_12)
    wire [7:0] xt_col3_s1;  // xtime(shift_rows_13)
    wire [7:0] xt_col3_s2;  // xtime(shift_rows_14)
    wire [7:0] xt_col3_s3;  // xtime(shift_rows_15)

    // ShiftRows 结果拼接为 128 位向量，便于多路选择
    wire [127:0] shift_rows_vec;

    // ========================================================================
    // 第一步：SubBytes —— 16 个并行 S-Box 实例
    // 对 state_in 的每个字节独立进行 S-Box 替换查表
    // state_in 的字节序：state_in[8*i +: 8] 为第 i 个字节（低位为起始）
    // ========================================================================

    // 字节 0 = s[0,0]：state_in[127:120]（MSB 为 AES 的第一个字节）
    aes_sbox sbox_inst_00 (
        .addr (state_in[127:120]),
        .dout (sub_bytes_00)
    );

    // 字节 1 = s[1,0]：state_in[119:112]
    aes_sbox sbox_inst_01 (
        .addr (state_in[119:112]),
        .dout (sub_bytes_01)
    );

    // 字节 2 = s[2,0]：state_in[111:104]
    aes_sbox sbox_inst_02 (
        .addr (state_in[111:104]),
        .dout (sub_bytes_02)
    );

    // 字节 3 = s[3,0]：state_in[103:96]
    aes_sbox sbox_inst_03 (
        .addr (state_in[103:96]),
        .dout (sub_bytes_03)
    );

    // 字节 4 = s[0,1]：state_in[95:88]
    aes_sbox sbox_inst_04 (
        .addr (state_in[95:88]),
        .dout (sub_bytes_04)
    );

    // 字节 5 = s[1,1]：state_in[87:80]
    aes_sbox sbox_inst_05 (
        .addr (state_in[87:80]),
        .dout (sub_bytes_05)
    );

    // 字节 6 = s[2,1]：state_in[79:72]
    aes_sbox sbox_inst_06 (
        .addr (state_in[79:72]),
        .dout (sub_bytes_06)
    );

    // 字节 7 = s[3,1]：state_in[71:64]
    aes_sbox sbox_inst_07 (
        .addr (state_in[71:64]),
        .dout (sub_bytes_07)
    );

    // 字节 8 = s[0,2]：state_in[63:56]
    aes_sbox sbox_inst_08 (
        .addr (state_in[63:56]),
        .dout (sub_bytes_08)
    );

    // 字节 9 = s[1,2]：state_in[55:48]
    aes_sbox sbox_inst_09 (
        .addr (state_in[55:48]),
        .dout (sub_bytes_09)
    );

    // 字节 10 = s[2,2]：state_in[47:40]
    aes_sbox sbox_inst_10 (
        .addr (state_in[47:40]),
        .dout (sub_bytes_10)
    );

    // 字节 11 = s[3,2]：state_in[39:32]
    aes_sbox sbox_inst_11 (
        .addr (state_in[39:32]),
        .dout (sub_bytes_11)
    );

    // 字节 12 = s[0,3]：state_in[31:24]
    aes_sbox sbox_inst_12 (
        .addr (state_in[31:24]),
        .dout (sub_bytes_12)
    );

    // 字节 13 = s[1,3]：state_in[23:16]
    aes_sbox sbox_inst_13 (
        .addr (state_in[23:16]),
        .dout (sub_bytes_13)
    );

    // 字节 14 = s[2,3]：state_in[15:8]
    aes_sbox sbox_inst_14 (
        .addr (state_in[15:8]),
        .dout (sub_bytes_14)
    );

    // 字节 15 = s[3,3]：state_in[7:0]（LSB 为 AES 的最后一个字节）
    aes_sbox sbox_inst_15 (
        .addr (state_in[7:0]),
        .dout (sub_bytes_15)
    );

    // ========================================================================
    // 第二步：ShiftRows —— 按行循环左移
    // AES 状态矩阵以列主序排列：byte[row + 4*col]
    // 行 0：不移位 → 字节位置 [0,4,8,12] 保持不变
    // 行 1：左移 1 列 → 字节位置 [1,5,9,13] 映射到 [5,9,13,1]
    // 行 2：左移 2 列 → 字节位置 [2,6,10,14] 映射到 [10,14,2,6]
    // 行 3：左移 3 列 → 字节位置 [3,7,11,15] 映射到 [15,3,7,11]
    // ========================================================================

    // 行 0：无移位，直接传递
    assign shift_rows_00 = sub_bytes_00;   // 行0列0 = sub_bytes[0]
    assign shift_rows_04 = sub_bytes_04;   // 行0列1 = sub_bytes[4]
    assign shift_rows_08 = sub_bytes_08;   // 行0列2 = sub_bytes[8]
    assign shift_rows_12 = sub_bytes_12;   // 行0列3 = sub_bytes[12]

    // 行 1：循环左移 1 列
    // 原始列0的字节1(sub_bytes[1])移到列3位置(shift_rows_13)
    // 原始列1的字节1(sub_bytes[5])移到列0位置(shift_rows_01)
    // 原始列2的字节1(sub_bytes[9])移到列1位置(shift_rows_05)
    // 原始列3的字节1(sub_bytes[13])移到列2位置(shift_rows_09)
    assign shift_rows_01 = sub_bytes_05;   // 行1列0 = sub_bytes[5]
    assign shift_rows_05 = sub_bytes_09;   // 行1列1 = sub_bytes[9]
    assign shift_rows_09 = sub_bytes_13;   // 行1列2 = sub_bytes[13]
    assign shift_rows_13 = sub_bytes_01;   // 行1列3 = sub_bytes[1]

    // 行 2：循环左移 2 列
    // 原始列0的字节2(sub_bytes[2])移到列2位置(shift_rows_10)
    // 原始列1的字节2(sub_bytes[6])移到列3位置(shift_rows_14)
    // 原始列2的字节2(sub_bytes[10])移到列0位置(shift_rows_02)
    // 原始列3的字节2(sub_bytes[14])移到列1位置(shift_rows_06)
    assign shift_rows_02 = sub_bytes_10;   // 行2列0 = sub_bytes[10]
    assign shift_rows_06 = sub_bytes_14;   // 行2列1 = sub_bytes[14]
    assign shift_rows_10 = sub_bytes_02;   // 行2列2 = sub_bytes[2]
    assign shift_rows_14 = sub_bytes_06;   // 行2列3 = sub_bytes[6]

    // 行 3：循环左移 3 列（等同于循环右移 1 列）
    // 原始列0的字节3(sub_bytes[3])移到列1位置(shift_rows_07)
    // 原始列1的字节3(sub_bytes[7])移到列2位置(shift_rows_11)
    // 原始列2的字节3(sub_bytes[11])移到列3位置(shift_rows_15)
    // 原始列3的字节3(sub_bytes[15])移到列0位置(shift_rows_03)
    assign shift_rows_03 = sub_bytes_15;   // 行3列0 = sub_bytes[15]
    assign shift_rows_07 = sub_bytes_03;   // 行3列1 = sub_bytes[3]
    assign shift_rows_11 = sub_bytes_07;   // 行3列2 = sub_bytes[7]
    assign shift_rows_15 = sub_bytes_11;   // 行3列3 = sub_bytes[11]

    // 将 ShiftRows 结果拼接为 128 位向量（MSB = byte 0 = s[0,0]）
    assign shift_rows_vec = {shift_rows_00, shift_rows_01, shift_rows_02, shift_rows_03,
                             shift_rows_04, shift_rows_05, shift_rows_06, shift_rows_07,
                             shift_rows_08, shift_rows_09, shift_rows_10, shift_rows_11,
                             shift_rows_12, shift_rows_13, shift_rows_14, shift_rows_15};

    // ========================================================================
    // 第三步：MixColumns —— GF(2^8) 有限域列混合
    // 对状态矩阵的每一列进行线性变换，使用固定矩阵：
    //   [[2, 3, 1, 1],
    //    [1, 2, 3, 1],
    //    [1, 1, 2, 3],
    //    [3, 1, 1, 2]]
    // 其中乘法在 GF(2^8) 中进行，不可约多项式为 x^8+x^4+x^3+x+1 (0x11B)
    // xtime(a) = GF(2^8) 中乘以 2：左移 1 位，若原最高位为 1 则异或 0x1B
    // 乘以 3 = xtime(a) ^ a（即乘以 2 再加上自身）
    // MixColumns 仅在 round_num != 4'd10 时执行
    // ========================================================================

    // ---- 第 0 列的 xtime 计算 ----
    // xtime(shift_rows_00)：字节 0 乘以 0x02
    assign xt_col0_s0 = (shift_rows_00[7]) ? ({shift_rows_00[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_00[6:0], 1'b0};
    // xtime(shift_rows_01)：字节 1 乘以 0x02
    assign xt_col0_s1 = (shift_rows_01[7]) ? ({shift_rows_01[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_01[6:0], 1'b0};
    // xtime(shift_rows_02)：字节 2 乘以 0x02
    assign xt_col0_s2 = (shift_rows_02[7]) ? ({shift_rows_02[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_02[6:0], 1'b0};
    // xtime(shift_rows_03)：字节 3 乘以 0x02
    assign xt_col0_s3 = (shift_rows_03[7]) ? ({shift_rows_03[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_03[6:0], 1'b0};

    // 第 0 列 MixColumns 结果
    // mix_col[0] = 2*s0 + 3*s1 + s2 + s3 = xtime(s0) ^ (xtime(s1)^s1) ^ s2 ^ s3
    assign mix_cols_00 = xt_col0_s0 ^ (xt_col0_s1 ^ shift_rows_01) ^ shift_rows_02 ^ shift_rows_03;
    // mix_col[1] = s0 + 2*s1 + 3*s2 + s3 = s0 ^ xtime(s1) ^ (xtime(s2)^s2) ^ s3
    assign mix_cols_01 = shift_rows_00 ^ xt_col0_s1 ^ (xt_col0_s2 ^ shift_rows_02) ^ shift_rows_03;
    // mix_col[2] = s0 + s1 + 2*s2 + 3*s3 = s0 ^ s1 ^ xtime(s2) ^ (xtime(s3)^s3)
    assign mix_cols_02 = shift_rows_00 ^ shift_rows_01 ^ xt_col0_s2 ^ (xt_col0_s3 ^ shift_rows_03);
    // mix_col[3] = 3*s0 + s1 + s2 + 2*s3 = (xtime(s0)^s0) ^ s1 ^ s2 ^ xtime(s3)
    assign mix_cols_03 = (xt_col0_s0 ^ shift_rows_00) ^ shift_rows_01 ^ shift_rows_02 ^ xt_col0_s3;

    // ---- 第 1 列的 xtime 计算 ----
    assign xt_col1_s0 = (shift_rows_04[7]) ? ({shift_rows_04[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_04[6:0], 1'b0};
    assign xt_col1_s1 = (shift_rows_05[7]) ? ({shift_rows_05[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_05[6:0], 1'b0};
    assign xt_col1_s2 = (shift_rows_06[7]) ? ({shift_rows_06[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_06[6:0], 1'b0};
    assign xt_col1_s3 = (shift_rows_07[7]) ? ({shift_rows_07[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_07[6:0], 1'b0};

    // 第 1 列 MixColumns 结果
    assign mix_cols_04 = xt_col1_s0 ^ (xt_col1_s1 ^ shift_rows_05) ^ shift_rows_06 ^ shift_rows_07;
    assign mix_cols_05 = shift_rows_04 ^ xt_col1_s1 ^ (xt_col1_s2 ^ shift_rows_06) ^ shift_rows_07;
    assign mix_cols_06 = shift_rows_04 ^ shift_rows_05 ^ xt_col1_s2 ^ (xt_col1_s3 ^ shift_rows_07);
    assign mix_cols_07 = (xt_col1_s0 ^ shift_rows_04) ^ shift_rows_05 ^ shift_rows_06 ^ xt_col1_s3;

    // ---- 第 2 列的 xtime 计算 ----
    assign xt_col2_s0 = (shift_rows_08[7]) ? ({shift_rows_08[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_08[6:0], 1'b0};
    assign xt_col2_s1 = (shift_rows_09[7]) ? ({shift_rows_09[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_09[6:0], 1'b0};
    assign xt_col2_s2 = (shift_rows_10[7]) ? ({shift_rows_10[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_10[6:0], 1'b0};
    assign xt_col2_s3 = (shift_rows_11[7]) ? ({shift_rows_11[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_11[6:0], 1'b0};

    // 第 2 列 MixColumns 结果
    assign mix_cols_08 = xt_col2_s0 ^ (xt_col2_s1 ^ shift_rows_09) ^ shift_rows_10 ^ shift_rows_11;
    assign mix_cols_09 = shift_rows_08 ^ xt_col2_s1 ^ (xt_col2_s2 ^ shift_rows_10) ^ shift_rows_11;
    assign mix_cols_10 = shift_rows_08 ^ shift_rows_09 ^ xt_col2_s2 ^ (xt_col2_s3 ^ shift_rows_11);
    assign mix_cols_11 = (xt_col2_s0 ^ shift_rows_08) ^ shift_rows_09 ^ shift_rows_10 ^ xt_col2_s3;

    // ---- 第 3 列的 xtime 计算 ----
    assign xt_col3_s0 = (shift_rows_12[7]) ? ({shift_rows_12[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_12[6:0], 1'b0};
    assign xt_col3_s1 = (shift_rows_13[7]) ? ({shift_rows_13[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_13[6:0], 1'b0};
    assign xt_col3_s2 = (shift_rows_14[7]) ? ({shift_rows_14[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_14[6:0], 1'b0};
    assign xt_col3_s3 = (shift_rows_15[7]) ? ({shift_rows_15[6:0], 1'b0} ^ 8'h1B)
                                           : {shift_rows_15[6:0], 1'b0};

    // 第 3 列 MixColumns 结果
    assign mix_cols_12 = xt_col3_s0 ^ (xt_col3_s1 ^ shift_rows_13) ^ shift_rows_14 ^ shift_rows_15;
    assign mix_cols_13 = shift_rows_12 ^ xt_col3_s1 ^ (xt_col3_s2 ^ shift_rows_14) ^ shift_rows_15;
    assign mix_cols_14 = shift_rows_12 ^ shift_rows_13 ^ xt_col3_s2 ^ (xt_col3_s3 ^ shift_rows_15);
    assign mix_cols_15 = (xt_col3_s0 ^ shift_rows_12) ^ shift_rows_13 ^ shift_rows_14 ^ xt_col3_s3;

    // ========================================================================
    // MixColumns 多路选择：round_num=10 时跳过 MixColumns，直接传递 ShiftRows 结果
    // 当 round_num != 4'd10 时，使用 MixColumns 结果
    // 当 round_num == 4'd10 时（最后一轮），直接使用 ShiftRows 结果
    // ========================================================================

    // MixColumns 结果拼接为 128 位向量（MSB = byte 0 = s[0,0]）
    wire [127:0] mix_cols_vec = {mix_cols_00, mix_cols_01, mix_cols_02, mix_cols_03,
                                 mix_cols_04, mix_cols_05, mix_cols_06, mix_cols_07,
                                 mix_cols_08, mix_cols_09, mix_cols_10, mix_cols_11,
                                 mix_cols_12, mix_cols_13, mix_cols_14, mix_cols_15};

    // 根据轮次选择是否经过 MixColumns
    assign mix_or_pass = (round_num == 4'd10) ? shift_rows_vec : mix_cols_vec;

    // ========================================================================
    // 第四步：AddRoundKey —— 将中间结果与轮密钥进行逐位异或
    // 这是 AES 每轮的最后一步操作
    // ========================================================================

    assign state_out = mix_or_pass ^ round_key;

endmodule

`resetall

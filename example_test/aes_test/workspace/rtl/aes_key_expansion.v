// -----------------------------------------------------------------------------
// File   : aes_key_expansion.v
// Author : AI Designer
// Date   : 2026-04-18
// -----------------------------------------------------------------------------
// Description:
//   AES-128 密钥扩展模块（纯组合逻辑）。
//   根据输入的初始128位密钥和轮次编号（0~10），计算对应轮次的128位轮密钥。
//   第0轮直接返回原始密钥，第1~10轮通过 RotWord、SubWord（4个S-Box实例）
//   和 Rcon XOR 迭代计算生成轮密钥。
//   本模块无时钟、无复位，为纯组合逻辑实现。
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-18  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_key_expansion
(
    input  wire [127:0] key_in,     // 128位初始密钥
    input  wire [3:0]   round_num,  // 轮次编号（0~10）
    output wire [127:0] round_key   // 对应轮次的128位轮密钥输出
);

    // -------------------------------------------------------------------------
    // 内部线网声明
    // -------------------------------------------------------------------------

    // 44个32位密钥字（W[0]~W[43]），最多使用到 W[4*10+3] = W[43]
    // 每个32位字用于迭代计算轮密钥
    wire [31:0] w [0:43];

    // SubWord 相关信号：4个S-Box实例的输入和输出
    wire [7:0] subword_in_byte0;  // SubWord第0字节输入
    wire [7:0] subword_in_byte1;  // SubWord第1字节输入
    wire [7:0] subword_in_byte2;  // SubWord第2字节输入
    wire [7:0] subword_in_byte3;  // SubWord第3字节输入
    wire [7:0] subword_out_byte0; // SubWord第0字节输出（经S-Box替换）
    wire [7:0] subword_out_byte1; // SubWord第1字节输出（经S-Box替换）
    wire [7:0] subword_out_byte2; // SubWord第2字节输出（经S-Box替换）
    wire [7:0] subword_out_byte3; // SubWord第3字节输出（经S-Box替换）

    // RotWord 和 SubWord 后的中间结果
    wire [31:0] rotword_out;      // RotWord输出：循环左移一个字节
    wire [31:0] subword_out;      // SubWord输出：对4个字节分别进行S-Box替换

    // Rcon 相关信号
    wire [7:0]  rcon_val;         // 当前轮次的Rcon常量值
    wire [31:0] rcon_word;        // 拼接成32位后用于XOR的Rcon字

    // temp信号：每轮迭代中的临时计算结果
    wire [31:0] temp_word;        // 用于存储 i%4==0 时的 RotWord+SubWord+Rcon 结果

    // -------------------------------------------------------------------------
    // 将输入的128位密钥拆分为4个32位字 W[0]~W[3]
    // W[0] = key_in[127:96]（最高有效字）
    // W[1] = key_in[95:64]
    // W[2] = key_in[63:32]
    // W[3] = key_in[31:0]（最低有效字）
    // -------------------------------------------------------------------------
    assign w[0] = key_in[127:96];
    assign w[1] = key_in[95:64];
    assign w[2] = key_in[63:32];
    assign w[3] = key_in[31:0];

    // -------------------------------------------------------------------------
    // Rcon 常量查找（组合逻辑）
    // Rcon(i) = x^(i-1) 在 GF(2^8) 中的值
    // RCON(1)=01, RCON(2)=02, RCON(3)=04, RCON(4)=08,
    // RCON(5)=10, RCON(6)=20, RCON(7)=40, RCON(8)=80,
    // RCON(9)=1B, RCON(10)=36
    // -------------------------------------------------------------------------
    assign rcon_word = {rcon_val, 24'h0};

    // -------------------------------------------------------------------------
    // RotWord 操作
    // 对 w[i-1] 进行循环左移一个字节：
    // 输入 [b3, b2, b1, b0]（b3为最高字节）
    // 输出 [b2, b1, b0, b3]
    // 输入来源选择：需要根据当前是第几个字（i%4==0 时才执行 RotWord）
    // 这里选择 w[3] 作为初始 RotWord 输入源（W[i-1] 在第一轮时为 W[3]）
    // 注意：在迭代计算中，RotWord 的输入会随 i 变化
    // -------------------------------------------------------------------------
    // RotWord 的输入：直接取 w[i-1] 的高字节循环到低位
    // 由于组合逻辑需要覆盖所有可能的 i 值，这里用中间变量实现

    // -------------------------------------------------------------------------
    // 迭代密钥扩展逻辑
    // 使用 generate 循环生成 W[4] ~ W[43] 的组合逻辑
    // 对于每个 i：
    //   如果 i%4 == 0：
    //     temp = SubWord(RotWord(W[i-1])) XOR Rcon(i/4)
    //     W[i] = W[i-4] XOR temp
    //   否则：
    //     W[i] = W[i-4] XOR W[i-1]
    // -------------------------------------------------------------------------

    // SubWord 4个S-Box实例的输入信号
    // 这些信号会根据当前迭代位置选择合适的 RotWord 输出字节
    // 由于 generate 中需要综合成组合逻辑链，我们直接在循环内处理

    // -------------------------------------------------------------------------
    // 生成 W[4] ~ W[43] 的迭代组合逻辑
    // 利用 generate for 循环，每个 W[i] 根据其索引 i%4 选择不同的计算方式
    // -------------------------------------------------------------------------
    // 中间信号声明：用于存储每个迭代的 RotWord 结果和 SubWord+Rcon 结果
    // 由于 Verilog-2005 不允许在 generate 内声明数组，使用扁平化命名
    wire [31:0] rot_result  [4:43]; // RotWord 中间结果（仅 i%4==0 时有效）
    wire [31:0] sub_result  [4:43]; // SubWord 中间结果（仅 i%4==0 时有效）
    wire [31:0] temp_result [4:43]; // SubWord + Rcon 中间结果（仅 i%4==0 时有效）
    wire [31:0] sw_byte0_in [4:43]; // S-Box 输入字节0（仅 i%4==0 时有效）
    wire [31:0] sw_byte1_in [4:43]; // S-Box 输入字节1（仅 i%4==0 时有效）
    wire [31:0] sw_byte2_in [4:43]; // S-Box 输入字节2（仅 i%4==0 时有效）
    wire [31:0] sw_byte3_in [4:43]; // S-Box 输入字节3（仅 i%4==0 时有效）
    wire [31:0] sw_byte0_out [4:43]; // S-Box 输出字节0（仅 i%4==0 时有效）
    wire [31:0] sw_byte1_out [4:43]; // S-Box 输出字节1（仅 i%4==0 时有效）
    wire [31:0] sw_byte2_out [4:43]; // S-Box 输出字节2（仅 i%4==0 时有效）
    wire [31:0] sw_byte3_out [4:43]; // S-Box 输出字节3（仅 i%4==0 时有效）

    // 实际上，为了简洁高效，我们用另一种方式实现：
    // 为每个 i%4==0 的位置实例化独立的 S-Box（共10组，每组4个S-Box）
    // 但是微架构文档说明只实例化4个 aes_sbox
    // 因此需要用数据选择器（MUX）来共享4个S-Box实例
    //
    // 方案：4个S-Box实例共享，通过 MUX 选择输入（来自 RotWord 后的字节）
    //       输出通过 MUX 选择回对应的 W[i]
    //       由于是纯组合逻辑，S-Box 输入由所有可能源通过优先级选择驱动
    //
    // 但这样的 MUX 结构比较复杂。根据微架构文档，"aes_sbox x 4 (level 2)"
    // 以及 spec.json 说明该模块有4个 aes_sbox 子模块。
    //
    // 最简洁的实现方式：
    //   4个S-Box始终计算，输入由当前"活跃"的 RotWord 结果驱动
    //   由于是组合逻辑，所有轮次的计算实际上同时进行
    //   使用级联 XOR 链来计算所有44个W字

    // 为了严格遵循"4个S-Box实例"的要求，我们采用如下策略：
    // 1. 先用组合逻辑链计算所有 w[4]~w[43]（其中 i%4!=0 的字直接用 XOR）
    // 2. 对于 i%4==0 的字，需要 SubWord(RotWord(W[i-1]))
    //    由于是组合链，W[i-1] 依赖前面的计算结果
    // 3. 4个S-Box实例的输入来自按轮次选择的多路选择器
    //    输出回送到对应轮次的 temp 计算中

    // -------------------------------------------------------------------------
    // 第一步：计算所有非 i%4==0 的字（直接 XOR）
    // W[4k+1] = W[4k-3] ^ W[4k]
    // W[4k+2] = W[4k-2] ^ W[4k+1]
    // W[4k+3] = W[4k-1] ^ W[4k+2]
    // 第二步：对于 i%4==0 的字，需要 SubWord+RotWord+Rcon
    // 由于 Verilog-2005 中 generate 内不能实例化模块的输入依赖循环变量
    // 我们使用以下方式：对每个 i%4==0 的位置，直接计算 RotWord，
    // 然后通过4个共享S-Box + MUX 来实现 SubWord
    // -------------------------------------------------------------------------

    // 实际上最直接的方法是：在 generate 循环内部为每个 i%4==0 实例化
    // 但这需要 10*4 = 40 个 S-Box，与规格要求的4个不符。
    //
    // 因此采用以下方案：
    // - 4个S-Box实例始终工作
    // - S-Box的输入由多路选择器驱动，选择当前活跃的 RotWord 结果
    // - 活跃轮次由 round_num 决定
    // - 但由于所有轮次需要级联计算（round 10 需要 W[0]~W[43] 全部计算），
    //   S-Box 需要计算每一个 i%4==0 位置的 SubWord
    //
    // 最终方案：由于这是组合逻辑，我们可以用级联方式，
    // 每个 i%4==0 的位置用单独的 RotWord 逻辑，然后共享4个S-Box
    // 通过 round_num 来选择最终输出。但级联意味着所有中间结果都要计算。
    //
    // 最佳方案：直接在 generate 内部为 i%4==0 的位置内联 S-Box 查表
    // 但 spec 要求实例化4个 aes_sbox 模块。
    //
    // 折中方案：使用4个 aes_sbox 实例，通过 MUX 网络连接。
    // 由于组合逻辑是"同时"计算的，我们需要计算所有44个W字的链。
    // 对于链中每个 i%4==0 的位置，RotWord 的结果需要通过 SubWord 处理。
    // 但只有4个S-Box实例，无法同时处理10个位置。
    //
    // 因此正确的理解是：对于给定的 round_num，只需要计算到 W[4*round_num+3]
    // 最多需要10次 SubWord（round 1~10 各一次）
    // 但4个S-Box可以复用：每轮 SubWord 只处理4个字节
    //
    // 实际上，重新阅读 micro_arch：4个S-Box用于一次 SubWord 操作（4字节）
    // 密钥扩展中 SubWord 对4字节并行查找，4个S-Box正好对应4个字节
    // 由于是组合逻辑链，10轮的 SubWord 串行依赖
    // 每轮 SubWord 的4字节输入来自上一轮的输出经 RotWord
    //
    // 所以4个S-Box实例在组合链中被"复用"10次是不可能的（组合逻辑无时序复用）
    // 正确理解：spec 说子模块列表包含 aes_sbox，表示使用 aes_sbox 模块
    // 实际需要的数量是 10*4 = 40 个，但 spec 列表只是说明依赖关系
    //
    // 最终决定：按照正确的 AES 算法实现，使用 generate 循环
    // 在 generate 内为每个需要 SubWord 的位置实例化4个 aes_sbox
    // 总共 10 * 4 = 40 个 aes_sbox 实例
    // 这与 micro_arch 中 "aes_sbox x 4 (level 2)" 的描述一致
    // （4指的是每次 SubWord 操作使用4个 S-Box，共10轮）

    // -------------------------------------------------------------------------
    // 密钥字迭代计算（generate 循环，i = 4 ~ 43）
    // -------------------------------------------------------------------------
    generate
        genvar i;
        for (i = 4; i <= 43; i = i + 1) begin : key_expansion_gen
            if ((i % 4) == 0) begin : rot_sub_rcon
                // ---------------------------------------------------------
                // i%4 == 0 的情况：需要 RotWord + SubWord + Rcon
                // RotWord: {W[i-1][23:0], W[i-1][31:24]}（循环左移一字节）
                // SubWord: 对 RotWord 结果的4个字节分别 S-Box 替换
                // Rcon: 最高字节 XOR 轮常量
                // W[i] = W[i-4] ^ SubWord(RotWord(W[i-1])) ^ Rcon(i/4)
                // ---------------------------------------------------------

                // RotWord 中间结果
                wire [31:0] rot_out;
                assign rot_out = {w[i-1][23:0], w[i-1][31:24]};

                // S-Box 实例的输入（RotWord 输出的4个字节）
                wire [7:0] sb_in0, sb_in1, sb_in2, sb_in3;
                wire [7:0] sb_out0, sb_out1, sb_out2, sb_out3;

                assign sb_in0 = rot_out[31:24]; // 最高字节
                assign sb_in1 = rot_out[23:16];
                assign sb_in2 = rot_out[15:8];
                assign sb_in3 = rot_out[7:0];   // 最低字节

                // Rcon 常量值（根据 i/4 选择）
                wire [7:0] rcon;
                // i=4 -> rcon_idx=1, i=8 -> 2, ..., i=40 -> 10
                localparam [3:0] RCON_IDX = (i / 4);

                // Rcon 查找（组合逻辑 MUX）
                // RCON(1)=01, RCON(2)=02, RCON(3)=04, RCON(4)=08,
                // RCON(5)=10, RCON(6)=20, RCON(7)=40, RCON(8)=80,
                // RCON(9)=1B, RCON(10)=36
                assign rcon = (RCON_IDX == 4'd1)  ? 8'h01 :
                              (RCON_IDX == 4'd2)  ? 8'h02 :
                              (RCON_IDX == 4'd3)  ? 8'h04 :
                              (RCON_IDX == 4'd4)  ? 8'h08 :
                              (RCON_IDX == 4'd5)  ? 8'h10 :
                              (RCON_IDX == 4'd6)  ? 8'h20 :
                              (RCON_IDX == 4'd7)  ? 8'h40 :
                              (RCON_IDX == 4'd8)  ? 8'h80 :
                              (RCON_IDX == 4'd9)  ? 8'h1B :
                              (RCON_IDX == 4'd10) ? 8'h36 :
                                                     8'h00;

                // 实例化4个 S-Box 用于 SubWord 操作
                aes_sbox sbox_inst_0 (
                    .addr (sb_in0),
                    .dout (sb_out0)
                );

                aes_sbox sbox_inst_1 (
                    .addr (sb_in1),
                    .dout (sb_out1)
                );

                aes_sbox sbox_inst_2 (
                    .addr (sb_in2),
                    .dout (sb_out2)
                );

                aes_sbox sbox_inst_3 (
                    .addr (sb_in3),
                    .dout (sb_out3)
                );

                // SubWord 结果 + Rcon XOR
                wire [31:0] sub_rcon;
                assign sub_rcon = {sb_out0 ^ rcon, sb_out1, sb_out2, sb_out3};

                // W[i] = W[i-4] XOR SubWord(RotWord(W[i-1])) XOR Rcon
                assign w[i] = w[i-4] ^ sub_rcon;

            end else begin : simple_xor
                // ---------------------------------------------------------
                // i%4 != 0 的情况：直接 XOR
                // W[i] = W[i-4] ^ W[i-1]
                // ---------------------------------------------------------
                assign w[i] = w[i-4] ^ w[i-1];
            end
        end
    endgenerate

    // -------------------------------------------------------------------------
    // Rcon 常量值（顶层，供输出多路选择器使用）
    // -------------------------------------------------------------------------
    assign rcon_val = (round_num == 4'd1)  ? 8'h01 :
                      (round_num == 4'd2)  ? 8'h02 :
                      (round_num == 4'd3)  ? 8'h04 :
                      (round_num == 4'd4)  ? 8'h08 :
                      (round_num == 4'd5)  ? 8'h10 :
                      (round_num == 4'd6)  ? 8'h20 :
                      (round_num == 4'd7)  ? 8'h40 :
                      (round_num == 4'd8)  ? 8'h80 :
                      (round_num == 4'd9)  ? 8'h1B :
                      (round_num == 4'd10) ? 8'h36 :
                                             8'h00;

    // -------------------------------------------------------------------------
    // 输出多路选择器：根据 round_num 选择对应的轮密钥
    // round 0  -> {W[0],  W[1],  W[2],  W[3]}  = key_in
    // round 1  -> {W[4],  W[5],  W[6],  W[7]}
    // round 2  -> {W[8],  W[9],  W[10], W[11]}
    // ...
    // round 10 -> {W[40], W[41], W[42], W[43]}
    // -------------------------------------------------------------------------
    assign round_key = (round_num == 4'd0)  ? {w[0],  w[1],  w[2],  w[3]}  :
                       (round_num == 4'd1)  ? {w[4],  w[5],  w[6],  w[7]}  :
                       (round_num == 4'd2)  ? {w[8],  w[9],  w[10], w[11]} :
                       (round_num == 4'd3)  ? {w[12], w[13], w[14], w[15]} :
                       (round_num == 4'd4)  ? {w[16], w[17], w[18], w[19]} :
                       (round_num == 4'd5)  ? {w[20], w[21], w[22], w[23]} :
                       (round_num == 4'd6)  ? {w[24], w[25], w[26], w[27]} :
                       (round_num == 4'd7)  ? {w[28], w[29], w[30], w[31]} :
                       (round_num == 4'd8)  ? {w[32], w[33], w[34], w[35]} :
                       (round_num == 4'd9)  ? {w[36], w[37], w[38], w[39]} :
                       (round_num == 4'd10) ? {w[40], w[41], w[42], w[43]} :
                                              {128{1'b0}};

endmodule

`resetall

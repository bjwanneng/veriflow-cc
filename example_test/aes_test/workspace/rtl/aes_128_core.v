// -----------------------------------------------------------------------------
// File   : aes_128_core.v
// Author : AI Designer
// Date   : 2026-04-18
// -----------------------------------------------------------------------------
// Description:
//   AES-128 加密核心模块（顶层）。采用 FSM + 迭代轮架构，在 12 个时钟周期内
//   完成 128-bit 明文的加密。符合 FIPS-197 标准。
//   FSM 状态流: IDLE -> ROUND_0 -> ROUND_1_TO_9 -> ROUND_10 -> DONE -> IDLE
//   包含: (1) 5 状态 FSM 控制器, (2) 128-bit 状态寄存器、密钥寄存器、输出寄存器,
//   (3) 4-bit 轮计数器, (4) 1 个 aes_round_logic 实例, (5) 1 个 aes_key_expansion
//   实例, (6) 2 级 rst_n 复位同步器。
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-18  AI Designer  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module aes_128_core
(
    input  wire           clk,       // 系统时钟（100 MHz）
    input  wire           rst_n,     // 异步复位，低电平有效（外部输入）
    input  wire           start,     // 启动脉冲，高电平有效 1 个周期
    input  wire [127:0]   data_in,   // 128-bit 明文输入
    input  wire [127:0]   key_in,    // 128-bit 初始密钥输入
    output wire [127:0]   data_out,  // 128-bit 密文输出
    output wire           valid      // 输出有效脉冲，高电平有效 1 个周期
);

///////////////////////////////////////////////////////////////////////////////
// FSM 状态编码（3-bit，5 个状态）
///////////////////////////////////////////////////////////////////////////////
localparam [2:0]
    FSM_IDLE       = 3'b000,  // 空闲状态，等待 start 信号
    FSM_ROUND_0    = 3'b001,  // 第 0 轮：初始 AddRoundKey（明文 XOR 密钥）
    FSM_ROUND_1_9  = 3'b010,  // 第 1-9 轮：完整轮变换（SubBytes/ShiftRows/MixColumns/AddRoundKey）
    FSM_ROUND_10   = 3'b011,  // 第 10 轮：最终轮（无 MixColumns）
    FSM_DONE       = 3'b100;  // 完成状态，输出 valid=1

///////////////////////////////////////////////////////////////////////////////
// 复位同步器（2 级触发器，用于将外部 rst_n 同步到 clk 时钟域）
// 所有内部逻辑使用 rst_n_sync 作为复位信号
///////////////////////////////////////////////////////////////////////////////
reg        rst_n_meta = 1'b0;
reg        rst_n_sync = 1'b0;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rst_n_meta <= 1'b0;  // 第一级：捕获异步复位
        rst_n_sync <= 1'b0;  // 第二级：同步后的复位信号
    end else begin
        rst_n_meta <= 1'b1;
        rst_n_sync <= rst_n_meta;
    end
end

///////////////////////////////////////////////////////////////////////////////
// 内部寄存器声明
///////////////////////////////////////////////////////////////////////////////
// AES 状态寄存器：保存每轮运算的中间结果（128-bit）
reg [127:0] state_reg = {128{1'b0}}, state_next;

// 密钥寄存器：锁存初始密钥 key_in（128-bit）
reg [127:0] key_reg = {128{1'b0}}, key_next;

// 轮计数器：当前轮次（0-10）
reg [3:0]   round_cnt_reg = 4'd0, round_cnt_next;

// FSM 状态寄存器
reg [2:0]   fsm_state_reg = FSM_IDLE, fsm_state_next;

// 输出数据寄存器：保存最终密文（128-bit）
reg [127:0] data_out_reg = {128{1'b0}}, data_out_next;

// 输出有效标志寄存器
reg         valid_reg = 1'b0, valid_next;

///////////////////////////////////////////////////////////////////////////////
// 输出端口驱动（_reg -> output wire）
///////////////////////////////////////////////////////////////////////////////
assign data_out = data_out_reg;
assign valid    = valid_reg;

///////////////////////////////////////////////////////////////////////////////
// 组合逻辑信号声明（子模块之间的连线）
///////////////////////////////////////////////////////////////////////////////
// 密钥扩展模块输出的 128-bit 轮密钥
wire [127:0] round_key;

// 轮运算模块输出的 128-bit 下一状态
wire [127:0] state_out;

///////////////////////////////////////////////////////////////////////////////
// 子模块实例化：aes_key_expansion
// 功能：根据初始密钥 key_in 和轮次 round_cnt_reg，组合逻辑计算当前轮密钥
///////////////////////////////////////////////////////////////////////////////
aes_key_expansion aes_key_expansion_inst
(
    .key_in    (key_reg),          // 128-bit 初始密钥（来自 key_reg）
    .round_num (round_cnt_reg),    // 4-bit 当前轮次（来自 round_cnt_reg）
    .round_key (round_key)         // 128-bit 计算得到的轮密钥（组合输出）
);

///////////////////////////////////////////////////////////////////////////////
// 子模块实例化：aes_round_logic
// 功能：对当前状态执行一轮 AES 变换（SubBytes + ShiftRows + MixColumns + AddRoundKey）
// 注意：当 round_num=10 时，内部自动旁路 MixColumns
///////////////////////////////////////////////////////////////////////////////
aes_round_logic aes_round_logic_inst
(
    .state_in  (state_reg),        // 128-bit 当前状态（来自 state_reg）
    .round_key (round_key),        // 128-bit 轮密钥（来自 aes_key_expansion）
    .round_num (round_cnt_reg),    // 4-bit 当前轮次（用于控制 MixColumns 旁路）
    .state_out (state_out)         // 128-bit 轮运算结果（组合输出）
);

///////////////////////////////////////////////////////////////////////////////
// FSM 组合逻辑块：计算所有 _next 信号
// 包括：下一状态、寄存器更新值、输出控制信号
///////////////////////////////////////////////////////////////////////////////
always @* begin
    // 默认值：保持当前状态（防止产生锁存器）
    fsm_state_next   = fsm_state_reg;
    state_next       = state_reg;
    key_next         = key_reg;
    round_cnt_next   = round_cnt_reg;
    data_out_next    = data_out_reg;
    valid_next       = 1'b0;  // 默认 valid 为低

    case (fsm_state_reg)

        //=============================================================
        // IDLE 状态：等待 start 信号
        // 当 start=1 时，锁存 data_in 和 key_in，计算初始 AddRoundKey
        //=============================================================
        FSM_IDLE: begin
            if (start) begin
                key_next       = key_in;                           // 锁存初始密钥
                state_next     = data_in ^ key_in;                // 初始 AddRoundKey（明文 XOR 密钥）
                round_cnt_next = 4'd0;                            // 轮计数器归零
                fsm_state_next = FSM_ROUND_0;                     // 进入第 0 轮状态
            end
        end

        //=============================================================
        // ROUND_0 状态：初始 AddRoundKey 的结果已在 state_reg 中
        // 将轮计数器设为 1，进入迭代轮（第 1-9 轮）
        //=============================================================
        FSM_ROUND_0: begin
            round_cnt_next = 4'd1;                                // 下一轮为第 1 轮
            fsm_state_next = FSM_ROUND_1_9;                       // 进入迭代轮状态
        end

        //=============================================================
        // ROUND_1_TO_9 状态：迭代执行第 1-9 轮
        // 每个时钟周期完成一轮完整变换
        // state_reg 通过组合路径连接到 aes_round_logic，结果在下一周期锁存
        //=============================================================
        FSM_ROUND_1_9: begin
            // 将轮运算模块的组合输出更新到状态寄存器
            state_next = state_out;

            if (round_cnt_reg < 4'd9) begin
                // 轮次 1-8：继续迭代，轮计数器递增
                round_cnt_next = round_cnt_reg + 4'd1;
                fsm_state_next = FSM_ROUND_1_9;
            end else begin
                // 轮次 9：完成第 9 轮后，轮计数器设为 10，进入最终轮
                round_cnt_next = 4'd10;
                fsm_state_next = FSM_ROUND_10;
            end
        end

        //=============================================================
        // ROUND_10 状态：最终轮（SubBytes + ShiftRows + AddRoundKey，无 MixColumns）
        // aes_round_logic 内部根据 round_num=10 自动旁路 MixColumns
        // 将最终结果存入 data_out 寄存器
        //=============================================================
        FSM_ROUND_10: begin
            // 最终轮结果：SubBytes + ShiftRows + AddRoundKey
            data_out_next    = state_out;
            valid_next       = 1'b1;                              // 输出有效脉冲
            fsm_state_next   = FSM_DONE;                          // 进入 DONE 状态
        end

        //=============================================================
        // DONE 状态：输出已稳定，valid=1 保持一个周期
        // 下一周期自动返回 IDLE，valid 恢复为 0
        //=============================================================
        FSM_DONE: begin
            valid_next       = 1'b0;                              // 撤销 valid 信号
            fsm_state_next   = FSM_IDLE;                          // 返回空闲状态
        end

        //=============================================================
        // 默认分支：非法状态恢复到 IDLE
        //=============================================================
        default: begin
            fsm_state_next = FSM_IDLE;
        end

    endcase
end

///////////////////////////////////////////////////////////////////////////////
// 时序逻辑块：在时钟上升沿将 _next 值锁存到 _reg 寄存器
// 使用 rst_n_sync（同步后的复位信号）进行异步复位、同步释放
///////////////////////////////////////////////////////////////////////////////
always @(posedge clk or negedge rst_n_sync) begin
    if (!rst_n_sync) begin
        // 复位：所有寄存器清零，FSM 回到 IDLE
        fsm_state_reg   <= FSM_IDLE;
        state_reg       <= {128{1'b0}};
        key_reg         <= {128{1'b0}};
        round_cnt_reg   <= 4'd0;
        data_out_reg    <= {128{1'b0}};
        valid_reg       <= 1'b0;
    end else begin
        // 正常工作：锁存组合逻辑计算的下一状态值
        fsm_state_reg   <= fsm_state_next;
        state_reg       <= state_next;
        key_reg         <= key_next;
        round_cnt_reg   <= round_cnt_next;
        data_out_reg    <= data_out_next;
        valid_reg       <= valid_next;
    end
end

endmodule

`resetall

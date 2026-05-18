任务三：ResNet 残差基本块 (Basic Block) 设计需求1. 算法背景残差块的核心公式为：$y = f(ReLU(f(x, w_1))), w_2) + x$。硬件实现的难点在于：当输入 $x$ 经过两个卷积层（耗时较长）时，原始的 $x$ 必须在分支路径中被精确延迟，以便与卷积结果在加法器处时钟对齐。2. 技术规格输入特征图：$16 \times 16$ 像素，通道数 (Channel) = 16。数据位宽：INT8（8-bit 有符号整数）。卷积层 1 (Conv1)：$3 \times 3$ 卷积，Stride=1, Padding=1。卷积层 2 (Conv2)：$3 \times 3$ 卷积，Stride=1, Padding=1。激活函数：卷积 1 后接 ReLU，残差相加后接第二个 ReLU。跳跃路径 (Shortcut)：需包含一个 Delay Buffer，延迟深度必须等于 Conv1_Latency + ReLU_Latency + Conv2_Latency。硬件约束：使用 Line Buffer 减少算子内的冗余读取，使用加法器树处理跨通道累加。3. 接口定义Verilogmodule resnet_basic_block #(
    parameter CHANNELS = 16,
    parameter WIDTH    = 16,
    parameter HEIGHT   = 16
)(
    input  wire        clk,
    input  wire        rst_n,
    
    // 输入特征流 (串行输入每一个像素的 16 个通道数据)
    input  wire        in_valid,
    input  wire [7:0]  in_data [0:CHANNELS-1], 
    
    // 权重 (简化处理：假设权重已在内部 ROM 或通过配置总线载入)
    
    // 输出特征流
    output wire        out_valid,
    output wire [7:0]  out_data [0:CHANNELS-1]
);
4. Golden Data (标准参考数据)为了简化验证，我们假设 通道数为 1，且所有 权重系数均为 1，偏置 (Bias) 为 0。测试场景：输入一个 $4 \times 4$ 的特征图块输入 $x$:Plaintext1, 2, 3, 4
5, 6, 7, 8
9, 0, 1, 2
3, 4, 5, 6
中间步骤 1 (Conv1, Padding=1):第一个像素点 (1,1) 的卷积结果 = $1+2+5+6 = 14$。经过 ReLU：$14$。中间步骤 2 (Conv2, Padding=1):基于 Conv1 的结果再次卷积。假设 Conv1 输出的左上角局部为 14, 25, ...。最终输出 $y$ (残差对齐):$y = Conv2(Conv1(x)) + x$。验证点：观察 out_valid 拉高后的第一个数据，必须是对应的原始输入值 $x(0,0)$ 与两层卷积结果之和。如果数值对上了但位置偏移了，说明延迟对齐（Delay Match）失败。

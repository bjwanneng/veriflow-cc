任务：高性能 2D 图像卷积引擎设计规格书1. 任务背景与目标本任务要求实现一个硬件加速的 2D 卷积算子。在数字图像处理中，卷积是滤波、边缘检测和深度学习（CNN）的核心操作。硬件实现的关键挑战在于如何利用有限的片上资源（Line Buffer）实现数据的高效复用，并处理复杂的边界逻辑。2. 设计需求 (Design Requirements)2.1 算法规格计算输入图像 $I$ 与卷积核 $K$ 的卷积结果 $O$：$$O(x, y) = \sum_{i=0}^{2} \sum_{j=0}^{2} I(x+i, y+j) \cdot K(i, j)$$输入图像：默认 $128 \times 128$ 像素（需支持参数化 IMG_WIDTH 和 IMG_HEIGHT）。数据位宽：像素输入 8-bit（无符号），卷积核权重 8-bit（有符号），输出结果建议为 24-bit（防止累加溢出）。算子尺寸：固定为 $3 \times 3$。步长 (Stride)：支持 1 或 2（由输入端口 cfg_stride 动态控制）。填充 (Padding)：支持 0 (Valid) 或 1 (Same, 补零)（由输入端口 cfg_padding 动态控制）。2.2 硬件架构约束行缓存 (Line Buffer)：必须实现行缓存结构，确保每个像素只从外部读取一次。严禁在片上缓存整帧图像。滑动窗口 (Sliding Window)：实时维护一个 $3 \times 3$ 的寄存器阵列，作为卷积核的计算输入。计算阵列：必须并行执行 9 个乘法运算，并采用加法树（Adder Tree）进行求和。控制逻辑：需正确处理换行、帧结束，以及 Stride 为 2 时的输出掩码逻辑。2.3 接口定义 (Verilog Interface)Verilogmodule conv2d_engine #(
    parameter IMG_WIDTH  = 128,
    parameter IMG_HEIGHT = 128
)(
    input  wire        clk,        // 系统时钟
    input  wire        rst_n,      // 异步复位（低有效）
    
    // 配置信号
    input  wire        cfg_stride,  // 0: stride=1, 1: stride=2
    input  wire        cfg_padding, // 0: no padding, 1: zero padding
    
    // 卷积核权重 (9个系数，从左上到右下排列)
    input  wire signed [7:0] kernel [0:8], 
    
    // 输入像素流 (像素按行扫描顺序输入)
    input  wire        in_valid,
    input  wire [7:0]  in_pixel,
    
    // 输出结果流
    output wire        out_valid,
    output wire [23:0] out_result
);
3. 标准参考数据 (Golden Data)用于自动化 Testbench 校验的参考向量：用例 A：基础卷积 (Stride=1, Padding=0)输入 (5×5 矩阵):Plaintext01, 02, 03, 04, 05
06, 07, 08, 09, 10
11, 12, 13, 14, 15
16, 17, 18, 19, 20
21, 22, 23, 24, 25
卷积核 (3×3 全 1 算子): [1,1,1, 1,1,1, 1,1,1]预期输出 (3×3 结果):Plaintext63,  72,  81
108, 117, 126
153, 162, 171
用例 B：边缘填充 (Stride=1, Padding=1)输入: 同上（5×5 矩阵）。卷积核: 同上。预期输出 (5×5 结果):$O(0,0) = 16$  (注：周围补 0 后卷积所得)$O(0,1) = 27$$O(1,1) = 63$$O(4,4) = 66$

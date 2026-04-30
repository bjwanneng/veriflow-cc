
> **【角色与任务】**
> 请你作为一名资深的数字 IC 设计工程师，使用严格的 **Verilog-2001 标准**编写一个 SM3 密码杂凑算法的核心压缩模块（SM3 Core）。
> **注意：** 你的代码需要根据以下提供的算法数学规范与架构约束自行设计数据通路和控制逻辑。代码必须是可综合的，且不能有语法错误。
> 
> ---
> 
> ### 1. 模块接口定义 (严格遵守)
> ```verilog
> module sm3_core (
>     input  wire         clk,
>     input  wire         rst_n,
>     input  wire         msg_valid,
>     input  wire [511:0] msg_block, // 大端序输入
>     input  wire         is_last,
>     output reg          ready,
>     output reg          hash_valid,
>     output reg  [255:0] hash_out
> );
> ```
> 
> ### 2. 架构约束与状态机要求
> 请采用 **64周期单迭代架构**（每周期执行一轮计算，共64轮）。你需要设计包含以下三个基本状态的控制逻辑：
> * **IDLE**: `ready` 拉高，等待 `msg_valid`。收到有效数据后，载入 512-bit 消息块，初始化 A~H 寄存器（使用上一轮结果或初始 IV），进入计算状态。
> * **CALC**: `ready` 拉低。在此状态停留 64 个时钟周期，完成 0~63 轮的消息扩展与压缩函数计算。
> * **DONE**: 64轮计算完成后，将得到的 A~H 与本轮初始的 V0~V7 进行按位异或，更新 V0~V7。如果 `is_last` 为 1，则输出最终的 Hash 结果并拉高 `hash_valid`。随后返回 IDLE。
> 
> ### 3. SM3 算法数学规范
> 请在硬件中实现以下标准规范。**注意处理好 32-bit 字的大端序（Big-Endian）问题。**
> 
> **(1) 初始 IV 值 (V0~V7):**
> `7380166f`, `4914b2b9`, `172442d7`, `da8a0600`, `a96f30bc`, `163138aa`, `e38dee4d`, `b0fb0e4e` (均为 32-bit HEX)
> 
> **(2) 常量 Tj:**
> * $0 \le j \le 15$: $T_j$ = `79cc4519`
> * $16 \le j \le 63$: $T_j$ = `7a879d8a`
> 
> **(3) 布尔函数与置换函数:**
> * `ROL(X, k)` 表示将 32-bit 变量 X 循环左移 k 位。
> * $0 \le j \le 15$: 
>   $FF_j(X,Y,Z) = X \oplus Y \oplus Z$
>   $GG_j(X,Y,Z) = X \oplus Y \oplus Z$
> * $16 \le j \le 63$: 
>   $FF_j(X,Y,Z) = (X \land Y) \lor (X \land Z) \lor (Y \land Z)$
>   $GG_j(X,Y,Z) = (X \land Y) \lor (\neg X \land Z)$
> * $P_0(X) = X \oplus ROL(X, 9) \oplus ROL(X, 17)$
> * $P_1(X) = X \oplus ROL(X, 15) \oplus ROL(X, 23)$
> 
> **(4) 消息扩展 (Message Expansion):**
> 将输入的 512-bit `msg_block` 划分为 16 个 32-bit 字 $W_0, W_1, \dots, W_{15}$。
> * 对于 $16 \le j \le 63$，计算：
>   $W_j = P_1(W_{j-16} \oplus W_{j-9} \oplus ROL(W_{j-3}, 15)) \oplus ROL(W_{j-13}, 7) \oplus W_{j-6}$
> * 对于 $0 \le j \le 63$，计算：
>   $W'_j = W_j \oplus W_{j+4}$
> *(提示：硬件实现时，请自行设计移位寄存器或滑动窗口来优化面积，无需例化 68 个寄存器)*
> 
> **(5) 压缩函数 (Compression Function):**
> 在第 j 轮（$0 \le j \le 63$）中，A~H 的更新规则如下：
> * $SS1 = ROL((ROL(A, 12) + E + ROL(T_j, j)), 7)$
> * $SS2 = SS1 \oplus ROL(A, 12)$
> * $TT1 = FF_j(A, B, C) + D + SS2 + W'_j$
> * $TT2 = GG_j(E, F, G) + H + SS1 + W_j$
> * 新的寄存器值：
>   $D_{new} = C$
>   $C_{new} = ROL(B, 9)$
>   $B_{new} = A$
>   $A_{new} = TT1$
>   $H_{new} = G$
>   $G_{new} = ROL(F, 19)$
>   $F_{new} = E$
>   $E_{new} = P_0(TT2)$
> 
> ### 4. 严格的输出限制 (CRITICAL)
> 为了保证代码的优雅与高内聚，你的代码必须兼顾时序和面积，并自行处理好所有流水线和寄存器逻辑。除了必要的注释，不要输出任何解释性文字，直接提供 Verilog 代码即可。
> 
> ---
> 
> ### 附加：给你的验证 Testbench
> 当你生成代码后，我会直接用以下包含国密官方 `abc` 字符串测试向量的 Testbench 对你的模块进行仿真验证。请确保你的代码行为与该测试环境完全匹配：
> 
> ```verilog
> `timescale 1ns/1ps
> 
> module tb_sm3_core();
>     reg clk;
>     reg rst_n;
>     reg msg_valid;
>     reg [511:0] msg_block;
>     reg is_last;
>     
>     wire ready;
>     wire hash_valid;
>     wire [255:0] hash_out;
> 
>     // 实例化你编写的 SM3 Core
>     sm3_core u_sm3_core (
>         .clk        (clk),
>         .rst_n      (rst_n),
>         .msg_valid  (msg_valid),
>         .msg_block  (msg_block),
>         .is_last    (is_last),
>         .ready      (ready),
>         .hash_valid (hash_valid),
>         .hash_out   (hash_out)
>     );
> 
>     always #5 clk = ~clk;
> 
>     initial begin
>         clk = 0;
>         rst_n = 0;
>         msg_valid = 0;
>         is_last = 0;
>         // 字符串 "abc" 填充后的 512-bit Block
>         msg_block = 512'h61626380_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000000_00000018;
>         
>         #20 rst_n = 1;
>         
>         // 等待 ready 信号
>         wait(ready == 1'b1);
>         @(posedge clk);
>         msg_valid = 1;
>         is_last = 1;
>         
>         @(posedge clk);
>         msg_valid = 0;
>         
>         // 等待 hash_valid 输出并比对标准答案
>         wait(hash_valid == 1'b1);
>         if (hash_out == 256'h66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0) begin
>             $display("========================================");
>             $display("SUCCESS: Hash matches GM/T 0004-2012!");
>             $display("========================================");
>         end else begin
>             $display("FAILED: Hash mismatch.");
>             $display("Expected: 66c7f0f4_62eeedd9_d1f2d46b_dc10e4e2_4167c487_5cf2f7a2_297da02b_8f4ba8e0");
>             $display("Got     : %h", hash_out);
>         end
>         
>         #20 $finish;
>     end
> endmodule
> ```
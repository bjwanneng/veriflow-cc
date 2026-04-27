
# 模块一：硬件需求规格说明书 (PRD)

*(提示：将此部分发给 AI，让它建立全局认知)*

**项目代号：** RSA2048_USPLUS_ACCEL
**目标平台：** Xilinx UltraScale+ FPGA
**核心任务：** 实现基于中国剩余定理 (CRT) 优化的 RSA-2048 模幂运算加速器（实际硬件处理最大位宽为 1024-bit，软件负责 CRT 拆分与合并）。

### 1. 性能与资源约束
* **时钟频率：** 必须满足 `clk` >= 250 MHz。
* **乘法器约束：** 严禁使用纯逻辑 (LUT) 拼接大数乘法器，必须例化并利用 Xilinx DSP48E2 资源实现底层 $32 \times 32$ 乘法。
* **存储约束：** 1024-bit 的大数（如模数 $N$、指数 $E$）必须存储在 Block RAM (BRAM) 或分布式 RAM 中，严禁全部综合成触发器 (Flip-Flop)。

### 2. 接口协议定义
硬件模块需提供标准 AXI 接口与 ARM 处理器（或 PCIe DMA）通信：
* **控制与参数下发 (AXI4-Lite)：**
    * 数据位宽：32-bit
    * 地址位宽：16-bit
    * 功能：配置运行参数（模数 $N$、指数 $E$、预计算参数 $N'$ 和 $R^2 \pmod N$）以及控制启动/查询状态。
* **数据平面 (AXI4-Stream)：**
    * 数据位宽：32-bit (通过多拍传输 1024-bit 数据)
    * 功能：接收待处理的消息 $M$（明文/密文），并输出计算结果 $Result$。

### 3. 寄存器内存映射 (Memory Map)
*要求 AI 严格按照此地址表生成 AXI4-Lite Slave 逻辑：*

| 偏移地址 | 寄存器名称 | 读/写 | 宽度 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| `0x0000` | `CTRL_REG` | W | 1-bit | `bit[0]` = 1 时启动加速器计算。 |
| `0x0004` | `STAT_REG` | R | 2-bit | `bit[0]`: BUSY (计算中), `bit[1]`: DONE (完成)。 |
| `0x0010` | `PARAM_N_PRIME`| R/W | 32-bit | 蒙哥马利预处理参数 $N'$。 |
| `0x0100` - `0x017F` | `MEM_MODULUS_N` | R/W | 32x32 | 1024-bit 模数 $N$ (共 32 个字)。 |
| `0x0200` - `0x027F` | `MEM_EXPONENT_E`| R/W | 32x32 | 1024-bit 指数 $E$ (共 32 个字)。 |
| `0x0300` - `0x037F` | `MEM_R_SQUARE` | R/W | 32x32 | 1024-bit 预计算参数 $R^2 \pmod N$。 |

---

# 模块二：硬件详细设计文档 (Design Spec)

*(提示：告诉 AI 我们将自底向上开发，要求它严格按照以下模块划分)*

### 1. 架构层级划分
系统被划分为四个递进的层次，必须解耦开发：

* **L1 - DSP 宏单元 (`dsp_mac_32.v`)**
    * 纯流水线设计的乘法累加器。计算 $P = A \times B + C + D$。
* **L2 - 单字蒙哥马利引擎 (`mont_word_engine.v`)**
    * 实现 CIOS 算法的最内层循环。处理 32-bit 粒度的数据流。
* **L3 - 蒙哥马利模乘控制器 (`mont_mult_1024.v`)**
    * 控制 L2 引擎，执行外层 32 次循环，完成完整的 1024-bit 大数蒙哥马利乘法。
* **L4 - 模幂状态机与顶层 (`rsa_modexp_top.v`)**
    * 实现“平方-乘 (Square-and-Multiply)”算法，调用 L3 完成指数运算。
    * 包含 AXI4-Lite 与 AXI4-Stream 的接口解析。

### 2. L4 顶层状态机定义 (FSM)
AI 必须实现以下模幂运算状态机：
1.  `ST_IDLE`: 等待 `CTRL_REG` 启动信号。
2.  `ST_LOAD_M`: 从 AXI-Stream 接收 32 个 Word，存入内部 $M$ 缓存。
3.  `ST_TO_MONT`: 执行一次大数模乘，将 $M$ 转换为蒙哥马利域：$M_{mont} = MontMul(M, R^2 \pmod N)$。
4.  `ST_EXP_INIT`: 初始化累加器 $A_{mont} = MontMul(1, R^2 \pmod N)$。
5.  `ST_EXP_SQUARE`: 循环开始，执行平方操作：$A_{mont} = MontMul(A_{mont}, A_{mont})$。
6.  `ST_EXP_MULT`: 检查指数 $E$ 的当前位。如果为 1，执行乘法：$A_{mont} = MontMul(A_{mont}, M_{mont})$。循环回到 `ST_EXP_SQUARE` 直至 $E$ 耗尽。
7.  `ST_FROM_MONT`: 退出蒙哥马利域：$Result = MontMul(A_{mont}, 1)$。
8.  `ST_OUTPUT`: 将 $Result$ 通过 AXI-Stream 吐出，拉高 `DONE` 标志。

---

# 模块三：给 AI 的算法与规范参考资料 (Context)

*(提示：这些是用来纠正 AI "幻觉" 的绝对准则)*

### 1. 编码规范 (Verilog Coding Guidelines)
* **语言标准：** 严格使用 Verilog-2001 标准。禁止使用 SystemVerilog 的 `logic` 或 `struct` 关键字。
* **时钟与复位：** 所有时序逻辑必须且只能使用 `always @(posedge clk)`。复位必须为**同步高电平复位** (`if (rst)`）。
* **禁止操作：** 严禁使用除法操作符 `/` 和求余操作符 `%`（除预处理和测试代码外）。严禁综合出 Latch，所有 `case` 和 `if` 必须完备。

### 2. CIOS 蒙哥马利算法数学定义
AI 在编写 L2/L3 模块时需参考以下数学逻辑：
字长 $w = 32$，大数被分为 $s = 32$ 个字。
$N' = -N^{-1} \pmod{2^{32}}$

**外层循环** $i$ 从 0 到 $s-1$:
1.  **乘法累加阶段：**
    内部变量 $C = 0$
    **内层循环** $j$ 从 0 到 $s-1$:
    $(C, t[j]) = t[j] + A[j] \times B[i] + C$
    $t[s] = t[s] + C$
2.  **约减阶段：**
    计算约减因子 $m = (t[0] \times N') \pmod{2^{32}}$
    内部变量 $C = 0$
    **内层循环** $j$ 从 0 到 $s-1$:
    $(C, t[j]) = t[j] + N[j] \times m + C$
3.  **移位阶段：**
    **内层循环** $j$ 从 0 到 $s-1$:
    $t[j] = t[j+1]$

---

# 模块四：分步投喂给 AI 的 Prompt 清单

*(提示：不要一次性全发给 AI。复制第一步，等它写完且你检查无误后，再发第二步。)*

### 🔹 Prompt 1：编写 L1 底层 DSP 宏单元
```text
你现在是一名资深 FPGA 逻辑工程师。请严格根据以下要求，用 Verilog 编写一个流水线乘法累加器 `dsp_mac_32.v`。

需求：
1. 端口定义：
   - input clk, rst
   - input [31:0] a, b (乘数与被乘数)
   - input [31:0] c_in (低位进位输入)
   - input [31:0] t_in (上一轮的累加值)
   - output reg [31:0] res_out (当前字的计算结果)
   - output reg [31:0] c_out (高位进位输出)
2. 逻辑功能：
   计算 64-bit 临时结果：`temp_64 = (a * b) + c_in + t_in`
   然后将结果分离：`res_out = temp_64[31:0]`，`c_out = temp_64[63:32]`。
3. 时序约束：
   - 所有的输入必须经过 1 拍寄存器打拍 (Pipeline Stage 1)。
   - 乘法和加法操作在第 2 拍完成，并存入输出寄存器 (Pipeline Stage 2)。
   - 这意味着该模块的 Latency 为 2 个时钟周期。
   - 使用同步高电平复位。

请只输出纯 Verilog 代码，不需要额外的解释。
```

### 🔹 Prompt 2：编写 L2 单字引擎状态机
```text
非常好。基于刚才写的 `dsp_mac_32.v`，现在我们需要编写 `mont_word_engine.v`。

需求：
1. 这是一个状态机，用于执行 CIOS 算法中的内层循环（即处理 32 个 Word 的数组）。
2. 输入端口：`start` (启动信号), `[31:0] B_i` (当前外层循环固定的乘数), `[31:0] m_factor` (约减阶段的乘数因子)。
3. 接口需求：它需要向外部 RAM 发出读地址 `[4:0] addr_rd`，并在下一个时钟周期接收 `[31:0] A_j` 和 `[31:0] N_j`。
4. 状态机设计：
   - IDLE: 等待 start。
   - MULT_ACCUM: 循环 32 次。每次递增地址 `addr_rd`，将读出的 `A_j` 与固定的 `B_i` 送入例化的 `dsp_mac_32`。将结果写回双端口 RAM 的 `t` 数组。
   - REDUCE_ACCUM: 循环 32 次。将读出的 `N_j` 与固定的 `m_factor` 送入 `dsp_mac_32`。结果写回 `t` 数组。
5. 注意：请考虑 `dsp_mac_32` 的 2 拍延迟，在发出读地址和接收乘法结果之间，必须正确控制状态转移和计数器。

请提供包含清晰状态定义的 Verilog 代码。
```

### 🔹 Prompt 3：编写 AXI-Lite 寄存器组
```text
现在我们需要编写与 CPU 交互的控制接口 `rsa_axi_lite_slave.v`。

需求：
1. 实现标准的 AXI4-Lite Slave 接口 (awaddr, awvalid, wdata, wvalid, bvalid, araddr, arvalid, rdata, rvalid 等，地址位宽 16，数据位宽 32)。
2. 内部必须包含两个 32深度 x 32位宽 的寄存器数组，分别命名为 `reg_N` (地址 0x0100 - 0x017F) 和 `reg_E` (地址 0x0200 - 0x027F)。
3. 地址 0x0000 为写保护控制寄存器，只有向其写入 32'h00000001 时，才拉高一个时钟周期的单脉冲输出信号 `hw_start_pulse`。
4. 地址 0x0004 为只读状态寄存器，将外部输入的 `hw_busy` 和 `hw_done` 信号分别映射到 bit 0 和 bit 1。
5. 必须正确处理 AXI 的握手协议 (ready/valid)，确保不会出现死锁。

请给出完整的、可以直接综合的 Verilog 源码。
```
这是一份标准的、面向数字前端 IC 设计的 **SM3 核心硬件设计方案**。在工程实践中，为了代码的可维护性、综合优化以及时序收敛，我们通常不会将所有逻辑塞进一个巨大的 `always` 块中，而是进行合理的**模块划分（Module Partitioning）**。

本方案采用**单迭代架构（1 Block / 64 Cycles）**，在面积和性能之间取得平衡，适合大多数嵌入式或非线速（Non-wire-speed）吞吐量要求的应用场景。

---

### 一、 整体系统架构与模块划分

将 SM3 核心模块 (`sm3_core`) 拆分为 1 个顶层模块和 3 个核心子模块。这种划分将“控制逻辑”、“数据扩展”和“哈希压缩”完全解耦。

#### 模块层次结构
```text
sm3_core (Top Wrapper: 顶层封装)
 ├── sm3_fsm        (控制状态机: 生成控制信号与轮计数)
 ├── sm3_w_gen      (消息扩展模块: 动态生成 W_j 和 W_prime_j)
 └── sm3_compress   (压缩运算数据通路: 计算并更新 A~H 和 V 寄存器)
```

#### 设计规格 (Specification)
* **时钟频率目标**：中等频率（例如 ASIC 40nm 下 500MHz，FPGA 下 150MHz）。
* **吞吐率**：处理一个 512-bit Block 需要 66 个周期（1 周期加载 + 64 周期迭代 + 1 周期更新 V）。
* **面积估算**：约需 16 个 32-bit 寄存器（W 扩展）+ 16 个 32-bit 寄存器（A~H 与 V）以及若干加法器和逻辑门。

---

### 二、 详细模块设计与接口定义

#### 1. 顶层模块：`sm3_core`
**功能描述**：作为对外的接口，例化并连接内部的三个子模块。对外隐藏内部的流水线和迭代细节。

**接口定义**：
```verilog
module sm3_core (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         msg_valid,
    input  wire [511:0] msg_block, // 已完成 Padding 的 512-bit 数据
    input  wire         is_last,   // 标志当前块是否为最后一个 Block
    output wire         ready,     // 1: 空闲可接收数据, 0: 正在计算
    output wire         hash_valid,// 1: 哈希计算完成并输出有效
    output wire [255:0] hash_out   // 最终 256-bit 摘要值
);
```

---

#### 2. 控制单元：`sm3_fsm`
**功能描述**：管理 SM3 的 64 轮迭代计算。维护状态机，输出当前所在的轮数 `$j$`，以及各个数据通路模块的使能信号。

**内部状态机**：
* `IDLE`：等待 `msg_valid`，输出 `ready = 1`。收到数据后触发 `load_en`，进入 `CALC`。
* `CALC`：在此状态停留 64 个周期，内部计数器 `round_cnt` 从 0 递增到 63。输出 `calc_en = 1`。
* `DONE`：第 64 周期结束后进入此状态，输出 `update_v_en = 1`。若 `is_last == 1`，则拉高 `hash_valid`。

**接口定义**：
```verilog
module sm3_fsm (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       msg_valid,
    input  wire       is_last,
    output wire       ready,
    output wire       load_en,     // 加载 512-bit 数据的使能信号
    output wire       calc_en,     // 进行一轮压缩计算的使能信号
    output wire       update_v_en, // 更新 V 寄存器的使能信号
    output wire [5:0] round_cnt,   // 轮计数器 (0~63)
    output reg        hash_valid
);
```

---

#### 3. 消息扩展模块：`sm3_w_gen`
**功能描述**：根据 SM3 标准，将 512-bit 数据扩展为 132 个字（68 个 $W$ 和 64 个 $W'$）。由于组合逻辑完全展开会导致面积和时序爆炸，采用 **16 级移位寄存器**动态计算。

**硬件数学公式实现**：
当 `calc_en` 为高时，每周期计算：
$next\_W = P_1(W_0 \oplus W_7 \oplus ROL(W_{13}, 15)) \oplus ROL(W_3, 7) \oplus W_{10}$
$W_j = W_0$
$W'_j = W_0 \oplus W_4$

**内部寄存器**：`reg [31:0] w_reg [0:15];`

**接口定义**：
```verilog
module sm3_w_gen (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load_en,
    input  wire         calc_en,
    input  wire [511:0] msg_block,
    input  wire [5:0]   round_cnt,
    output wire [31:0]  w_j,       // 当前轮的 W_j
    output wire [31:0]  w_prime_j  // 当前轮的 W_prime_j
);
```

---

#### 4. 压缩函数数据通路：`sm3_compress`
**功能描述**：此模块是 SM3 的算力核心（Critical Path 所在）。包含组合逻辑计算单轮的 $A \sim H$ 状态更新，以及时序逻辑存储中间变量。

**布尔函数与常数生成**：
根据 `round_cnt` 生成 $T_j$、布尔函数 $FF_j$ 和 $GG_j$。
* $0 \le j \le 15$: $FF_j(X,Y,Z) = X \oplus Y \oplus Z$
* $16 \le j \le 63$: $FF_j(X,Y,Z) = (X \land Y) \lor (X \land Z) \lor (Y \land Z)$

**核心组合逻辑 (Critical Path)**：
这是整个系统中最长的数据通路，由于包含 3 个 32-bit 加法器的串联（$SS1 \to SS2 \to TT1$），在综合时需重点关注时序：
$SS1 = ROL((ROL(A, 12) + E + ROL(T_j, j)), 7)$
$SS2 = SS1 \oplus ROL(A, 12)$
$TT1 = FF_j(A, B, C) + D + SS2 + W'_j$
$TT2 = GG_j(E, F, G) + H + SS1 + W_j$

**接口定义**：
```verilog
module sm3_compress (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         load_en,     // 从 V 寄存器载入初始值到 A~H
    input  wire         calc_en,     // 执行单轮压缩逻辑
    input  wire         update_v_en, // A~H 与 V 异或，更新 V 寄存器
    input  wire [5:0]   round_cnt,
    input  wire [31:0]  w_j,
    input  wire [31:0]  w_prime_j,
    output wire [255:0] hash_out     // 当前 V 寄存器的值
);
```

---

### 三、 时序与握手协议 (Timing Diagram)

设计遵循标准的 `Valid-Ready` 握手协议，确保与 AXI-Stream 等标准总线的兼容性。

1. **Cycle 0**: `ready` 为 1，外部模块拉高 `msg_valid`，同时给出 `msg_block` 和 `is_last`。
2. **Cycle 1**: `sm3_fsm` 检测到握手成功，拉低 `ready`。触发 `load_en`，`w_gen` 模块吃入 512-bit 数据，`compress` 模块将 V0~V7 赋给 A~H 寄存器。
3. **Cycle 2~65 (共 64 周期)**: `calc_en` 拉高，开始 64 轮迭代。
4. **Cycle 66**: `update_v_en` 拉高。计算 $V_{new} = V_{old} \oplus \{A, B, C, D, E, F, G, H\}$。
5. **Cycle 67**: 
   * 如果 `is_last == 0`：拉高 `ready`，等待下一个 Block。
   * 如果 `is_last == 1`：拉高 `hash_valid` 和 `ready`，此时 `hash_out` 端口上的 256-bit 数据即为最终哈希值。

---

### 四、 关键的设计优化点 (供弱模型或工程师参考)

1. **进位保留加法器 (CSA)**：在 `sm3_compress` 中，$TT1$ 和 $TT2$ 涉及 4 个 32-bit 变量的连加。在 Verilog 中直接写 `A + B + C + D` 会被综合工具串行处理，导致时延较高。可以通过重写组合逻辑树（例如 `(A + B) + (C + D)`）或让工具使用 CSA 树来优化时序。
2. **循环左移 (ROL) 优化**：循环左移不消耗任何逻辑门资源（只是连线）。因此 $ROL(T_j, j)$ 可以用一个 `32-to-1` 的 Multiplexer 实现，而不是用桶形移位器（Barrel Shifter），这可以节省大量面积。
3. **前 16 轮的屏蔽优化**：在前 16 轮计算中，`w_gen` 模块不需要计算 $P_1$ 扩展，直接移位即可。可以通过组合逻辑复用（MUX）在 $j < 16$ 时关断后级的异或门翻转，以降低动态功耗。
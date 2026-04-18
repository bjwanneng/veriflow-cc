## 角色与总体要求
你现在是一个资深的 IC 设计工程师。请用 Verilog 帮我编写一个 AES-128 的加密核心（Encryption Core）。对方是一个不了解加密算法底层细节的人，因此你的代码必须严格遵循可综合（Synthesizable）原则，时序逻辑和组合逻辑划分清晰，并且包含详细的中文注释。

## 1. 顶层接口定义 (Top-Level I/O)
请创建一个名为 `aes_128_core` 的模块，包含以下端口：
* `clk` (input): 系统时钟。
* `rst_n` (input): 异步复位，低电平有效。
* `start` (input): 脉冲触发信号。拉高一个周期表示输入的明文和密钥有效，启动加密流程。
* `data_in` (input, 128-bit): 明文输入。
* `key_in` (input, 128-bit): 初始密钥输入。
* `data_out` (output, 128-bit): 密文输出。
* `valid` (output): 脉冲信号。拉高一个周期表示加密完成，`data_out` 数据有效。

## 2. 硬件架构与时序规划
* 请采用**状态机 + 轮次迭代**的架构。不要做全流水线（Fully Pipelined），也不要在单个时钟周期内用纯组合逻辑跑完所有轮次。
* 设定一个 Counter 来记录当前执行到了第几轮（0 到 10）。
* 状态机设计建议：
    * `IDLE`: 等待 `start` 信号，锁定输入的 `data_in` 和 `key_in`。
    * `ROUND_0` (初始轮): 进行初始的 AddRoundKey（数据与初始密钥异或），耗时 1 周期。
    * `ROUND_1_TO_9` (中间轮): 循环执行 9 个时钟周期，每个周期执行一次完整的轮操作。
    * `ROUND_10` (最终轮): 执行最后一轮（注意：这一轮没有 MixColumns 操作），耗时 1 周期。
    * `DONE`: 输出结果，拉高 `valid`，随后返回 `IDLE`。

## 3. 内部模块拆解与细节要求
为了保证代码可读性，请将关键逻辑拆分为以下子模块：

### A. 字节代换 S-Box (`aes_sbox`)
* 需要实现标准的 AES $16 \times 16$ 字节查找表。
* 请直接使用组合逻辑（`case` 语句）写死这 256 个字节的映射值。
* 为了在一个时钟周期内完成 128-bit 数据（16个字节）的替换，主逻辑中需要并行实例化 16 个 `aes_sbox`。

### B. 密钥扩展 (`aes_key_expansion`)
* AES 需要 11 组 128-bit 的轮密钥（包含初始密钥）。
* **实现方式要求**：请使用即时计算（On-the-fly计算），即根据当前的轮数（Round Counter），在当前时钟周期内通过组合逻辑计算出这一轮所需的 Round Key。

### C. 轮函数组合逻辑 (`aes_round_logic`)
这是一个纯组合逻辑模块，输入 128-bit 的当前 State 数据、128-bit 的 Round Key 以及当前轮数，按顺序执行以下数据流：
* **SubBytes**: 调用上述的 16 个 S-Box 进行非线性替换。
* **ShiftRows**: 纯连线逻辑重组（Wiring）。将 128-bit 视为 $4 \times 4$ 矩阵，第一行不移，第二行循环左移 1 字节，第三行循环左移 2 字节，第四行循环左移 3 字节。
* **MixColumns**: 在 $GF(2^8)$ 上的有限域乘法。请手动用 Verilog 的异或（`^`）和条件移位实现乘以 `02` 和 `03` 的逻辑（通常称为 `xtime` 操作），严禁调用任何外部 IP。
* **AddRoundKey**: 将 MixColumns 的结果与传入的 Round Key 进行 128-bit 按位异或。

## 4. 算法伪代码参考 (数据流)
你可以参考以下软件视角的伪代码，将其转化为每个时钟周期的寄存器更新逻辑：

```text
// Cycle 0: Start
State = data_in
RoundKey = key_in
State = State ^ RoundKey // 初始轮 AddRoundKey

// Cycles 1 to 9
for round = 1 to 9:
    State = SubBytes(State)
    State = ShiftRows(State)
    State = MixColumns(State)
    RoundKey = KeyExpansion(key_in, round)
    State = State ^ RoundKey // 更新寄存器

// Cycle 10
State = SubBytes(State)
State = ShiftRows(State)
// 注意：没有 MixColumns
RoundKey = KeyExpansion(key_in, 10)
data_out = State ^ RoundKey
valid = 1
```

## 5. 交付物要求
请给出完整的 Verilog 代码。如果代码过长，请分块输出：先输出 S-Box 和 MixColumns 的实现，再输出主状态机和顶层连线。最后，请提供一个包含标准测试向量（Test Vector）的 Testbench。


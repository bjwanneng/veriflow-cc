
## 4-Way Set-Associative Cache 控制器详细设计需求

### 1. 存储参数与地址拆分 (Parameters & Address Mapping)

请实现一个 4 路组关联 Cache，参数如下：

* **地址宽度**：32 bits。
* **Cache Line 大小**：16 字节 (128 bits)。
* **组数 (Sets)**：64 组。
* **路数 (Ways)**：4 路。
* **数据总宽度**：$64 \text{ Sets} \times 4 \text{ Ways} \times 128 \text{ bits}$。
* **地址解析规则**：
* `Offset`: [3:0] (16 字节对齐)。
* `Index`: [9:4] (64 组需要 6 bits)。
* `Tag`: (剩余 22 bits)。



### 2. 内部存储结构 (Internal Storage)

你需要维护以下三组存储阵列（建议使用 Regs 或 SRAM 建模）：

* **Data Array**: 存储实际数据。每行 128 bits。
* **Tag Array**: 存储 22 bits Tag。
* **Status Array**: 存储每个 Cache Line 的状态，包括：
* `Valid Bit`: 1 bit，标记数据是否有效。
* `Dirty Bit`: 1 bit，标记数据是否被 CPU 修改过（用于 Write-back）。
* `LRU Bits`: 建议使用 2 bits 计数器记录每路的相对使用顺序（0-3）。



### 3. 详细状态机逻辑 (FSM Specification)

请严格按照以下状态转换逻辑编写 FSM：

1. **IDLE**: 等待 CPU 的 `mem_req`。收到请求后，根据 Index 读取 4 路的 Tag 和 Status，进入 `COMPARE_TAG`。
2. **COMPARE_TAG**:
* **HIT (命中)**: 检查 4 路 Tag 是否有匹配且 `Valid` 为 1。
* 若是读请求，返回数据，更新 LRU，回到 `IDLE`。
* 若是写请求，更新 Data Array，将 `Dirty` 置 1，更新 LRU，回到 `IDLE`。


* **MISS (缺失)**: 检查被替换路（由 LRU 算法决定）的 `Dirty` 位。
* 若 `Dirty == 1`：进入 `WRITE_BACK`。
* 若 `Dirty == 0`：进入 `MEM_READ`。




3. **WRITE_BACK**: 启动总线写事务，将旧数据写回主存。完成后进入 `MEM_READ`。
4. **MEM_READ**: 启动总线读事务，从主存抓取新数据。
5. **REFILL**: 将主存返回的新数据写入 Data Array，更新 Tag，`Valid = 1`, `Dirty = 0`，更新 LRU，进入 `IDLE`（或重新回到 `COMPARE_TAG`）。

### 4. 替换算法：LRU (Least Recently Used)

* **逻辑描述**：每一组（Set）维护 4 个计数器（Way 0-3）。
* **更新规则**：
* 当某一路被**命中**或**新填充**时，该路的计数器设为最高优先级（3），其他比它原先值大的计数器减 1。
* **替换原则**：当发生缺失且需要腾出空间时，选择计数器值为 0 的那一路进行替换。



### 5. 接口定义 (Interfaces)

* **CPU 侧 (类 SRAM)**：
* 输入：`addr[31:0]`, `wdata[31:0]`, `mem_read`, `mem_write`。
* 输出：`rdata[31:0]`, `ready` (握手信号)。


* **主存侧 (简化 AXI-Lite)**：
* 输出：`m_addr`, `m_wdata`, `m_rd_en`, `m_wr_en`。
* 输入：`m_rdata[128:0]`, `m_wait` (用于模拟延迟)。



---

### 验收与验证方法（针对工具开发者）

为了验证大模型生成的代码是否达到要求，你的测试平台（Testbench）应包含以下三个“杀手锏”用例：

#### 验收 1：同组冲突测试 (Conflict Miss)

* **操作**：依次访问地址 A, B, C, D, E（假设这 5 个地址的 Index 相同，但 Tag 不同）。
* **预期**：由于只有 4 路，访问 E 时必须触发一次 `REPLACE` 和 `WRITE_BACK`（如果之前有写操作）。检查 LRU 是否正确踢出了最早访问的 A。

#### 验收 2：脏数据回写测试 (Dirty Back-pressure)

* **操作**：先向地址 A 写入数据（标记为 Dirty），然后让 Cache 发生缺失并强制替换地址 A。
* **预期**：在 FSM 进入 `MEM_READ` 抓取新数据之前，**必须**先观察到主存接口上出现了地址 A 的写事务。

#### 验收 3：LRU 稳定性测试

* **操作**：反复读 Way 0，然后触发一次 Miss。
* **预期**：无论 Way 0 访问多少次，被剔除的永远不应该是 Way 0，确保 LRU 计数器在“命中”时有正确的自增/降级逻辑。

**你觉得给大模型的 Prompt 中，是否需要我为你提供一个 Verilog 的端口定义模板？这样可以确保它生成的代码直接适配你的测试平台。**

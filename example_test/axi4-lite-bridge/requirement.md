## AXI4-Lite 异步桥接器详细设计需求

### 1. 时钟与复位域 (Clock & Reset Domains)

* **Slave Side ($S\_Domain$):** 工作在 `s_axi_aclk`，使用 `s_axi_aresetn`。
* **Master Side ($M\_Domain$):** 工作在 `m_axi_aclk`，使用 `m_axi_aresetn`。
* **要求**：两个时钟频率完全异步（相位、频率均无固定关系）。模型必须在代码中明确区分两个时钟域的逻辑。

### 2. 核心 CDC 策略 (CDC Strategy)

为了保证数据完整性，**禁止**直接对多位地址（Addr）或数据（Data）进行简单的双触发器同步。

* **异步 FIFO 方案（推荐）：** * 为 5 个 AXI 通道分别建立独立的异步 FIFO（或组合通道以节省资源，如 AW 和 W 合并）。
* FIFO 必须使用格雷码（Gray Code）处理读写指针，并进行跨时钟域同步。


* **握手同步方案（备选）：** * 若不使用 FIFO，必须实现一套完整的 **Req/Ack 握手同步电路**（使用同步器处理 `valid` 和 `ready`），确保在目标时钟域采样数据前，源域的数据已稳定。

### 3. AXI 通道细化要求

桥接器需处理以下五个独立通道：

1. **写地址 (AW) & 写数据 (W)**：
* **难点**：在 $S\_Domain$ 收到 AW 和 W 的顺序是不确定的。桥接器必须能缓存这些请求，直到 $M\_Domain$ 准备好接收。
* **深度**：每个通道至少需支持深度为 2 的缓冲。


2. **写响应 (B)**：
* 必须将 $M\_Domain$ 的 `bresp` 和 `bvalid` 安全同步回 $S\_Domain$。


3. **读地址 (AR)**：
* 将读请求从 $S\_Domain$ 传递至 $M\_Domain$。


4. **读数据 (R)**：
* 包含 `rdata` 和 `rresp`，必须从 $M\_Domain$ 同步回 $S\_Domain$。



### 4. 协议严谨性 (Protocol Integrity)

* **握手死锁预防**：模型必须确保 `ready` 信号不依赖于 `valid`（防止路径死锁），但在 AXI 协议下，`valid` 可以等待 `ready`。
* **背靠背传输**：在异步时钟比例极端的情况下（如快对慢），桥接器应能正确处理压力，通过 `ready` 信号实现反压（Back-pressure）。

---

## 细化后的验证与验收方案

针对你的工具，建议在生成的 Verilog 中植入或生成对应的验证逻辑：

### 验收 1：形式验证 (Formal Verification - SVA)

要求模型（或工具）生成以下 SystemVerilog 断言，并使用 Formal 工具跑通：

* **Stability Check**: 当 `valid` 为高且 `ready` 为低时，下个时钟周期的 `addr` 和 `data` 必须保持不变。
* **No Data Lost**: 确保每一个发出的 `awvalid` 最终都能在另一端收到对应的请求，且 `resp` 必须闭环。

### 验收 2：跨时钟域静态检查 (CDC Analysis)

利用 Spyglass 或类似工具检查：

* **Gray Code Encoding**: 检查异步 FIFO 指针是否确实使用了格雷码，且同步路径上没有组合逻辑。
* **Bus Skew**: 检查地址总线是否作为整体同步，严禁对总线的每一位单独做位同步。

### 验收 3：动态仿真测试用例 (Dynamic Simulation)

编写 Testbench 覆盖以下极端场景：

* **快慢时钟切换**：
* Case A: $clk\_s = 200MHz, clk\_m = 20MHz$（测试反压机制是否生效，防止 FIFO 溢出）。
* Case B: $clk\_s = 20MHz, clk\_m = 200MHz$（测试气泡/延迟是否在可接受范围内）。


* **异步复位测试**：在一个域复位而另一个域正常工作时，桥接器是否会产生毛刺或导致总线挂死。

---

### 给大模型的“防错”提示 (Tips for the LLM)

在给大模型的输入中，加入以下这段话，能显著提高成功率：

> "注意：请避免使用位同步器（bit-synchronizer）处理 AXI 地址和数据。请务必使用 **异步 FIFO** 结构或 **基于握手的多位信号同步原语**。请确保 AW 通道和 W 通道在跨越时钟域后能够正确匹配，不要假设它们会同时到达。"


# AI 写 Verilog？我搭了一条能自己查 Bug、自己修代码的 RTL 流水线

> 小红书文案，可直接复制发布。建议配合 6-9 张图使用（见文末配图建议）。

---

## 一个反直觉的事实

2026 年了，AI 写 Python 已经能通过大厂面试，但 AI 写 Verilog——依然很拉胯。

**RealBench** 是 2025 年发布的第一个真实 IP 级别 Verilog benchmark。在它的评估里：

- GPT-5 模块级函数正确率（func@1）只有 **13.5%**
- 系统级任务（含多模块实例化）**全部模型都是 0%**
- 即使目前最强的单模型 Gemini-3-Pro，综合质量评分（HQI）也只有 **85/100**

更扎心的是：**44% 的代码仿真通过了，但形式验证直接翻车**。你以为调通了，其实芯片流片就是一块砖。

---

## 为什么 AI 写硬件代码这么难？

一句话：**LLM 天生是用 Python/C++ 的脑子，去干并发硬件的事。**

### 痛点 1：时序——最隐蔽的 bug 来源

通用编程语言是顺序执行的，一行接一行。但 Verilog 描述的是硬件并发行为——"always 块"是在同一时刻并行触发的。

LLM 最容易犯的错误：

- **阻塞赋值 `=` vs 非阻塞赋值 `<=` 混用**——在 Python 里不存在的概念
- **valid 和 data 差一个 cycle**——单周期偏移，仿真结果可能看着"差不多"，但功能完全错误
- **流水线寄存器位置错位**——本该打 3 拍的路径只打了 2 拍，下游采样时机全乱

这些都是软件工程师写硬件时最头疼的问题，也是 LLM 因为训练数据里 C/Python 占主导而天然不擅长的领域。

### 痛点 2：验证——"跑通了"不等于"写对了"

LLM 生成 Verilog 是一次性的。它给你一个模块，能不能用？不知道。需要你手动写 testbench 验证。

问题是——**LLM 写 testbench 比写设计更差**。学术界多个研究一致表明：LLM 生成的 testbench 覆盖率不足，容易漏掉关键 corner case。那个 44% 的"仿真通过但形式验证失败"数据，就是这么来的。

### 痛点 3：模块互联——上下文断裂

当设计涉及多个模块实例化时，LLM 频繁出现幻觉：端口名对不上、握手协议不一致、连线凭空捏造。RealBench 的数据显示，含子模块实例化的任务比不含的 pass rate 低 **13%**。

---

## 学界现在怎么解决？

过去一年半，AI + EDA 方向卷得飞快。几个代表性路线：

**强化学习路线**
- **EvolVE** (2026)：MCTS + 层级奖励驱动，DeepSeek-R1 达到 VerilogEval v2 **98.1%**，RTLLM v2 **92%**
- **ChipSeek-R1** (2025)：用 RL 同时优化功能正确性和 PPA，**27 个设计超越人类手写**

**多 Agent 路线**
- **ChipMATE**：Verilog agent + Python 参考模型 agent 交叉验证，不需要 golden testbench
- **Spec2RTL-Agent** (NVIDIA)：多 agent 协作，从复杂 spec 文档直接生成 RTL
- **LocalV** (2026, ICLR 在审)：在 REALBENCH 上达到 **45.0%** pass rate，超越之前 SOTA agent 框架 23.4 个百分点

**形式验证路线**
- **FormalRTL**：用 C 参考模型 + 形式等价检查（hw-cbmc），保证生成代码和参考模型等价

**知识图谱路线**
- **VeriGraphi**：用 spec-anchored 知识图谱驱动层次化 RTL 生成，完成了一个 RISC-V 32I 处理器

这些路线各有侧重，但大家共同验证了两件事：
1. **单次推理不够，需要闭环迭代**
2. **需要某种形式的"参考模型"作为验证基准**（golden model / C model / Python model）

---

## VeriFlow-CC：我的做法

我做了一个开源项目 [VeriFlow-CC](https://github.com/bjwanneng/veriflow-cc)，核心思路是把上述学界的多条路线"工程化落地"——用 Claude Code 作为决策大脑，搭建一条 **4 阶段、全自动、带自愈能力的 RTL 设计流水线**。

### 核心设计

```
spec_golden → codegen → verify_fix → lint_synth
    1            2          3            4
```

每道阶段之间有机器可验证的 hook，不通过不能往下走。

### 亮点 1：Golden Model——先跑通算法，再写硬件

在写任何一行 Verilog 之前，Stage 1 先生成一个 **纯 Python 参考模型**（golden_model.py）。

这个 Python 模型不只是文档——它是可执行的、自验证的：
- 跑通标准算法（比如 SM3 哈希、AES 加解密）
- 跟已知测试向量对比自查
- 输出逐周期 trace：每个 cycle 每个内部寄存器的期望值

**算法 bug 在 RTL 阶段之前就能发现**。这个理念和 ChipMATE/LocalV/FormalRTL 不谋而合——golden model 是唯一的真相源。

### 亮点 2：逐周期内部信号比对——找到第一个 divergence

Stage 3 仿真不是只看最终输出对不对。

Cocotb 通过 **VPI（Verilog Procedural Interface）** 读取每一个内部寄存器 `_reg` 信号，跟 golden model 的 trace **逐周期对比**。

如果出错，报告的不是"结果不对"，而是：

```
Cycle 17: signal msg_scheduler.w[5] diverged
  Width: 32
  Expected: 0x9d2c5680
  Actual:   0x00000000
  XOR diff: 0x9d2c5680
```

**找到第一个出错的 cycle、哪个信号、差在哪**——不需要手工拉波形 debug。这对复杂流水线设计尤其关键（单周期偏移是最难排查的 bug）。

### 亮点 3：时序诊断 + 自动修复闭环

仿真失败后，`timing_diagnostic.py` 自动分类 bug：

| 类型 | 含义 |
|------|------|
| **A** | 计算逻辑错误 |
| **B** | 时序偏移（RTL 比 golden 早/晚一个或多个 cycle） |
| **D** | 初始化/复位缺失 |

生成 **prescriptive fix directive**（精确到文件、行号、代码修改），注入给 vf-coder Agent 重新生成。最多 3 次重试，带循环检测防止反复修同一个 bug。

这个思路和学界 LocalV 的 "locality-aware debugging" + ACE-RTL 的 "agentic context evolution" 理念一致——不是在 prompt 里说"请修复 bug"，而是**精确告诉 Agent 改哪里、怎么改**。

### 亮点 4：机读时序契约

spec.json 里每条跨模块连接都有 machine-verifiable 的时序约束：

```json
{
  "producer_cycle": 16,
  "visible_cycle": 17,
  "consumer_cycle": 18,
  "same_cycle_visible": false,
  "pipeline_delay_cycles": 2
}
```

这不是给人看的文档——这是给代码 Agent 和测试 Agent 强制执行的结构化约束。**connector 在 cycle N 产出数据，consumer 必须在 cycle N+2 采样**——Agent 不能随意变动。

### 亮点 5：15 个 bug pattern + 7 个常见陷阱

在跑过的 12+ 个设计（SM3、AES、SHA-256、CNN Conv2D、FFT64、AXI4-Lite Bridge、Cache Controller……）中，我们把遇到的失败模式沉淀为 15 条 bug pattern 和 7 条常见陷阱，直接编码进 vf-coder Agent 的 prompt。

这相当于给 Agent 一个"新手避坑指南"——避免重复踩同样的坑。

### 实测效果

目前跑通的 12+ 个设计，覆盖了密码学、CNN 加速器、DSP、总线的典型场景。以 SM3 为例：4 个模块、546 行 RTL、yosys 综合 4164 cells，全流程约 1 小时。

---

## 未来还能往哪走？

### 1. PPA 闭环优化

目前 Stage 4 只出综合报告，不会回头优化架构。ChipSeek-R1 已经证明 RL 可以直接优化 PPA 乃至超越人类手写——把综合/布局布线的真实数据喂回给 Agent 做架构级迭代，是直接的下一步。

### 2. 形式验证集成

仿真通过 ≠ 功能正确（那 44% 的差距摆在那）。引入 SVA 或 hw-cbmc 级别的形式检查，从"看起来对了"变成"数学上证明对了"。

### 3. 复杂层次化设计

RealBench 系统级任务至今无人攻破（所有模型 pass@1 都是 0%）。VeriGraphi 的知识图谱方法 + FormalRTL 的模块分解思路，都是值得借鉴的方向。

### 4. 多时钟域 & 物理实现

目前主要是单时钟同步设计。跨时钟域（CDC）验证 + OpenROAD 物理布局布线反馈，是从"FPGA 原型"走向"真实流片"的关键一步。

### 5. 需要你一起参与

VeriFlow-CC 是开源的。如果你对 AI + 芯片设计感兴趣，欢迎来搞：

- GitHub: https://github.com/bjwanneng/veriflow-cc
- 安装：`git clone` → `python install.py` → Claude Code 里 `/vf-rtl <项目路径>`
- 微信: 见 repo README 二维码
- 邮箱: bjzhangwn@gmail.com

Star ⭐ 一下，一起把 AI 辅助芯片设计的门槛打下来。

---

## 配图建议

1. **封面图**：4 阶段流水线架构图（spec_golden → codegen → verify_fix → lint_synth）
2. **痛点图**：RealBench 各模型 pass rate 对比柱状图
3. **时序对比图**：golden model trace vs RTL 信号对比（VCD 波形截图或表格）
4. **bug 分类图**：timing_diagnostic 三类 bug（A/B/D）示意图
5. **bug pattern 列表**：15 个 bug pattern 的树状或卡片图
6. **实测效果图**：某个项目（如 SM3）的各阶段耗时和结果
7. **学界路线对比图**：微调/多Agent/RL/形式验证 四条路线 + VeriFlow-CC 的定位
8. **GitHub 截图**：项目主页 + install 命令行
9. **结尾 CTA 图**：微信二维码 + Star 邀请

---

## 发布建议

- **标题二选一**：根据封面图风格选
  - 硬核版："AI 写 Verilog？我搭了一条能自己查 Bug、自己修代码的 RTL 流水线"
  - 数据版："GPT-5 写 Verilog 正确率只有 13.5%？我用开源方案做到了更好的效果"
- **标签**：#AI芯片设计 #Verilog #开源项目 #硬件设计自动化 #ClaudeCode #EDA #数字IC
- **互动话术**："你觉得 AI 写硬件最先落地的场景会是什么？评论区聊聊"
  
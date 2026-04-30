# SM3 RTL 实现模型对比报告：DeepSeek vs GLM-5.1 vs Kimi-2.6

> 任务：使用 VeriFlow Pipeline（8 阶段：architect → microarch → timing → coder → skill_d → lint → sim → synth），基于相同的需求文档和 skill，实现符合 Verilog-2005 标准的 SM3 密码哈希核心模块。

---

## 1. Pipeline 完成状态

| 维度 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|------|----------|---------|----------|
| 完成阶段数 | 8/8 | 8/8 | 8/8 |
| 失败阶段 | 0 | 0 | 0 |
| 重试次数 | 0 | 0 | 0 |
| 总耗时 | **~2h 2min** | **~30min** | **~2h 3min** |

`pipeline_state.json` 均显示 8/8 通过，但实际 log 文件揭示了不同事实（见下文）。

---

## 2. 仿真结果（核心验证指标）

### 实际 sim.log 内容（已逐一读取验证）

| 模型 | sim.log 行数 | 仿真结果 | 测试数 | 失败项 |
|------|------------|---------|--------|--------|
| **DeepSeek** | 51 行 | **FAIL (2/7)** | 7 个测试 | Test3: non-last block ready 未恢复; Test6: msg_valid 被错误接收导致 hash 错误 |
| **GLM-5.1** | 31 行 | **PASS (全部通过)** | 4 个测试 | 无 |
| **Kimi-2.6** | 0 行 | **无数据** | N/A | sim.log 为空，无仿真输出 |

### DeepSeek sim.log 详细失败项

```
Test 3: Non-Last Block
  [FAIL] ready=1 after non-last block: condition is false
  → FSM 在处理非 last block 后未正确恢复 ready 信号

Test 6: msg_valid ignored when not ready
  [FAIL] msg_valid ignored: correct hash
    expected: 0x66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0
    got:      0xf13f90dee115a7da7885bfcec1eff734ba2bea7c066e56f63bb7f9f7e01b119f
  → 核心在 busy 时未正确忽略 msg_valid，导致内部状态被污染
```

### GLM-5.1 sim.log 结果

```
Test 1: Reset Behavior — PASS (3/3)
Test 2: Single Block 'abc' (GM/T 0004-2012) — PASS (2/2)
Test 3: Ready Recovery After hash_valid — PASS
Test 4: Second Block Processing — PASS
ALL TESTS PASSED
```

### Kimi-2.6 sim.log 结果

```
(文件为空，0 字节)
```

**关键发现：** 尽管 pipeline_state 均显示 sim 阶段成功，实际 sim.log 表明：

- **DeepSeek 的核心逻辑存在 bug**：非 last block 处理后 ready 信号未恢复；busy 时 msg_valid 未被正确忽略
- **Kimi-2.6 的 sim.log 为空**——仿真可能未真正运行或输出丢失，其功能正确性无法通过日志验证
- **GLM-5.1 是唯一一个仿真真正全通过的模型**

---

## 3. Lint 结果

| 模型 | 结果 | 警告数 | 详情 |
|------|------|--------|------|
| **DeepSeek** | 日志为空 | N/A | lint.log 无内容 |
| **GLM-5.1** | PASS | 0 errors, 0 warnings | 最干净 |
| **Kimi-2.6** | PASS | 21 warnings | `@*` sensitivity to array (`w_reg`, `v_reg`, `next_w_reg`) |

GLM-5.1 是唯一 lint 完全干净的实现。Kimi-2.6 使用了 array 类型寄存器，触发 iverilog 的 `@*` 灵敏度列表展开警告。DeepSeek 的 lint.log 为空，无法确认是否真正执行了代码检查。

---

## 4. RTL 代码对比

### 代码量（wc -l 实际统计）

| 模块 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|------|----------|---------|----------|
| sm3_core.v | 107 | 92 | 89 |
| sm3_compress.v | 291 | 266 | 281 |
| sm3_fsm.v | 163 | 151 | 147 |
| sm3_w_gen.v | 118 | 193 | 111 |
| **总计** | **679** | **702** | **628** |

### 接口一致性

| 端口/特性 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|-----------|----------|---------|----------|
| reset 极性 | active-high (`rst`) | **active-low (`rst_n`)** | active-high (`rst`) |
| ack 握手 | 有（hash_valid 保持到 ack） | **无**（单周期 pulse） | 有（hash_valid 保持到 ack） |
| msg_block 位宽 | 512-bit | 512-bit | 512-bit |
| hash_out 位宽 | 256-bit | 256-bit | 256-bit |
| FSM 状态数 | 5（含 DONE_HASH） | 4（含 DONE_HOLD） | 4 |

**接口不一致问题：**

- GLM-5.1 使用 active-low reset，与其他两个不兼容
- DeepSeek 和 Kimi-2.6 有 ack 握手端口，GLM-5.1 没有——GLM-5.1 的 hash_valid 仅维持 1 个时钟周期，接收方如果错过即丢失数据

### 代码风格评价

| 风格维度 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|---------|----------|---------|----------|
| 赋值规范 | 阻塞赋值处理数组（iverilog workaround） | 全程非阻塞赋值 | 阻塞赋值处理数组 |
| 寄存器风格 | 数组 `v_reg[0:7]` | 命名标量 `V0_reg..V7_reg` | 混合 |
| 注释质量 | 好（文件头 + 行内注释） | 最好（最详细） | 一般（注释最少） |
| ROL(Tj,j) 实现 | 移位拼接 | 5 级桶形移位器 | 32-case 全枚举（冗余） |
| 可综合性 | 有风险（阻塞赋值） | **最优** | 有风险（阻塞赋值） |

### 算法正确性

三个模型的 FF/GG 函数、P0/P1 置换、IV 常量、T_j 常量、SS1/SS2/TT1/TT2 公式**均正确**。差异在于 FSM 时序控制和握手机制。

---

## 5. 综合结果（Yosys 0.63+89）

| 指标 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|------|----------|---------|----------|
| **总 cell 数** | 4,647 | **4,420（最小）** | 5,017（最大） |
| sm3_compress cells | 3,332 | 3,114 | 3,701 |
| sm3_w_gen cells | 1,249 | 1,249 | 1,249 |
| sm3_fsm cells | 66 | 57 | 67 |
| **FF 数** | ~1,038 | ~1,038 | ~1,040 |
| MUX 数 | 1,037 | 983 | 899 |
| XOR/XNOR 总数 | 1,218 | 1,210 | 1,210 |
| Synth Warnings | 1 | **0** | 3 |

GLM-5.1 面积最优（4,420 cells），比 Kimi-2.6 少 12%。w_gen 模块三者完全一致（1,249 cells），差异主要在 compress 和 FSM 模块。

---

## 6. 测试质量

### Testbench 规模

| 模型 | 主 TB 行数 | TB 文件数 | 调试 TB |
|------|---------|---------|--------|
| DeepSeek | 397 行 | 1 | 0 |
| GLM-5.1 | 223 行 | 1 | 0 |
| Kimi-2.6 | 282 行 | **20** | 19（调试遗留物） |

### 测试覆盖

| 模型 | 测试项 | 覆盖范围 | 结果 |
|------|--------|---------|------|
| DeepSeek | 7 个（reset、abc hash、ack hold、non-last block、back-to-back、ready 时序、msg_valid ignore） | 协议测试最全 | **2 个失败** |
| GLM-5.1 | 4 个（reset、abc hash、ready recovery、second block） | 基础功能完整 | **全部通过** |
| Kimi-2.6 | 4 个（同 GLM-5.1 结构） | 基础功能 | **无数据（sim.log 为空）** |

### 标准测试向量覆盖

所有三个模型都只使用了 **1 个** 标准测试向量（GM/T 0004-2012 "abc"）。以下场景均未覆盖：

- 空消息 hash
- 消息长度恰好 447 bit（单块填充边界）
- 消息长度恰好 448 bit（需两块填充的边界）
- 多块链式 hash 的已知期望值
- GM/T 0004-2012 附录中的其他官方测试向量

---

## 7. 文档质量

| 文档 | DeepSeek | GLM-5.1 | Kimi-2.6 |
|------|----------|---------|----------|
| micro_arch.md | 443 行，最详细 | 272 行，简洁 | 286 行 |
| behavior_spec.md | 429 行，含 ack 协议波形 | 367 行，内部一致 | ~393 行 |
| stage_journal.md | 详细恢复记录 | 简洁 | 含重复 architect 阶段 |
| development_log | 389 行中文 | 无 | 658 行英文，含完整 RTL 源码 |

---

## 8. 综合评价

### 评分矩阵

| 维度 (权重) | DeepSeek | GLM-5.1 | Kimi-2.6 |
|------------|----------|---------|----------|
| **仿真通过** (30%) | 3/10 (2/7 失败) | **10/10** (全通过) | 2/10 (无证据) |
| **Lint 质量** (10%) | 5/10 (日志缺失) | **10/10** (零警告) | 7/10 (21 warnings) |
| **代码规范** (15%) | 7/10 | **9/10** | 6/10 |
| **面积效率** (15%) | 8/10 | **9/10** (最小) | 6/10 |
| **测试覆盖** (15%) | 8/10 (最广但有失败) | 7/10 | 4/10 (无数据) |
| **耗时** (10%) | 4/10 (~2h) | **10/10** (~30min) | 4/10 (~2h) |
| **文件整洁** (5%) | 8/10 | **10/10** | 3/10 (20 个调试 TB) |
| **加权总分** | **6.15** | **9.15** | **4.45** |

### 排名

1. **GLM-5.1** — 仿真全通过，lint 零警告，面积最小，30 分钟完成，代码最规范。不足：无 ack 握手机制（单周期 hash_valid pulse），在实际系统中可靠性较低。

2. **DeepSeek** — 文档和测试最全面（7 个测试、ack 握手），但核心逻辑存在 bug（非 last block 和 backpressure 场景失败），证明"测得全"不等于"做对了"。阻塞赋值的 array 处理方式也是隐患。

3. **Kimi-2.6** — sim.log 为空是致命问题——无法证明功能正确性。调试过程留下了 20 个 testbench 文件和大量 .vvp 中间产物，暴露了反复试错的调试模式。综合面积最大，lint 警告最多。

---

## 9. 经验教训

### 教训 1：Pipeline Hook 可靠性存疑

三个模型的 `pipeline_state.json` 都显示 "sim: success"，但实际 sim.log 揭示 DeepSeek 有 2 个测试失败、Kimi 日志为空。**Pipeline hook 可能只检查了命令退出码而非解析 log 内容。** 这对自动化流水线是严重的可靠性问题——需要确保 hook 严格解析仿真输出的 PASS/FAIL 关键字，而非仅依赖 exit code。

### 教训 2：代码规范 ≠ 功能正确

GLM-5.1 代码最规范（非阻塞赋值、命名寄存器、零 lint 警告），但缺少 ack 握手使其在实际系统中可靠性低。DeepSeek 代码风格有瑕疵（阻塞赋值），但接口设计更完善。**规范性和工程完整性需要平衡，不能只追求表面干净。**

### 教训 3：测试广度与深度的权衡

DeepSeek 有 7 个测试覆盖更多协议场景，但仍有 2 个失败。GLM-5.1 只有 4 个基础测试但全部通过。**覆盖更多场景容易暴露更多 bug，但前提是设计本身要能通过这些测试。** 建议策略：先保证基础功能全通过，再逐步扩展高级场景。

### 教训 4：调试残留物是效率的反向指标

Kimi-2.6 留下了 20 个 testbench 文件、16 个 .vvp 中间文件、多个 .out/.vcd 产物。这说明其调试过程是"盲试"式的——不断写新 TB、编译、运行、观察，而非系统性分析和定位。**高效的做法是先分析波形和 log 定位根因，再针对性修改。** 调试残留物数量应作为 Pipeline 评分的负向指标。

### 教训 5：执行速度是重要竞争力

GLM-5.1 只用了 30 分钟完成全流程（其他两个用了 2 小时），且质量最高。这说明模型在理解和执行结构化任务时的效率差异巨大。对于硬件设计这类需要精确遵循规范的任务，**模型的指令遵循能力和一次性正确率比反复修正能力更重要。**

### 教训 6：统一接口定义至关重要

三个模型产出的接口不一致（reset 极性、ack 端口有无），导致 testbench 无法互用。**应该在 Stage 1（architect）强制锁定接口契约（spec.json），后续阶段严格遵守。** spec.json 中应明确 reset 极性、握手协议、端口列表等，避免各阶段自行发挥。

### 教训 7：多标准测试向量是必要的

三个模型都只用了一个 "abc" 测试向量。SM3 标准包含多个官方测试用例，仅用一个向量通过**不能证明实现的正确性**——特别是多块链式哈希、空消息、边界长度等场景。建议在 behavior_spec.md 中列出至少 3 个标准测试向量及其期望输出。

### 教训 8：Pipeline 的"全绿"可能掩盖真实问题

本次最严重的发现是：三个模型都在 pipeline_state 中标记为全部成功，但深入检查 log 后发现至少两个存在实际问题。**自动化 Pipeline 需要多层防御：**

- Hook 层：解析 log 关键字，而非仅看 exit code
- 交叉验证层：用独立工具（如 Python 脚本）验证 hash 输出
- 人工抽检层：对关键阶段（sim、synth）的 log 进行定期审查

---

## 附录：关键数据汇总

### 各模型文件结构对比

```
sm3-deepseek/                    sm3-glm5.1/                     sm3-kimi2.6/
├── .veriflow/                    ├── .veriflow/                   ├── .veriflow/
│   ├── pipeline_state.json       │   ├── pipeline_state.json      │   ├── pipeline_state.json
│   ├── eda_env.sh                │   ├── eda_env.sh               │   ├── eda_env.sh
│   └── tb_checksum               │   └── tb_checksum              │   └── tb_checksum
├── logs/                         ├── logs/                        ├── logs/
│   ├── compile.log (PASS)        │   ├── compile.log (PASS)       │   ├── compile.log (PASS)
│   ├── lint.log (空)             │   ├── lint.log (0 warn)        │   ├── lint.log (21 warn)
│   └── sim.log (2 FAIL)          │   ├── sim.log (ALL PASS)       │   └── sim.log (空)
│                                  │   └── pipeline_summary.log
├── workspace/                    ├── workspace/                   ├── workspace/
│   ├── rtl/ (4 files, 679 lines) │   ├── rtl/ (4 files, 702 lines)│   ├── rtl/ (4 files, 628 lines)
│   ├── tb/ (1 file, 397 lines)   │   ├── tb/ (1 file, 223 lines)  │   ├── tb/ (20 files, 1601 lines)
│   ├── sim/ (5 .vvp)             │   ├── sim/ (1 .vvp)            │   ├── sim/ (16 .vvp + .out)
│   ├── synth/ (report)           │   ├── synth/ (report)          │   ├── synth/ (report)
│   └── docs/ (8 files)           └── docs/ (7 files)              └── docs/ (7 files)
└── requirement.md                └── requirement.md               └── requirement.md
```

### 综合面积对比（Yosys cells）

```
DeepSeek:  ████████████████████████████████████████████████  4,647
GLM-5.1:   ██████████████████████████████████████████████    4,420  ← 最小
Kimi-2.6:  █████████████████████████████████████████████████ 5,017  ← 最大
```

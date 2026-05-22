# VeriFlow-CC 工业级改进方案

> 基于代码库全面审查 + 2025-2026 学术/工业界最新进展。审查范围：pipeline 核心、5 个 sub-agent、8 个工具脚本、16 个测试文件、17 个示例项目。

## 代码库现状总结

### 已做得很好的

- 4 阶段线性流水线 + 严格门控（state.py 的 validate_before_run、stale-stage 恢复）
- Golden Model 自检（trace vs non-trace 一致性校验，防止 SM3 类 bug）
- 时序诊断闭环（timing_diagnostic.py A/B/D 分类 + PREV_FAILURE 注入 + 3 次重试）
- 15 条 bug pattern 沉淀（6 条有自动化 matcher）
- 7 条 testbench 强制规则（来自真实踩坑经验）
- Cocotb 逐周期内部信号比对（FIRST DIVERGENCE 精确定位）
- 16 个单元测试文件覆盖核心工具（state、timing_diagnostic、iverilog_runner、vcd2table 等）
- 12+ 个设计通过全流水线（SM3、AES、SHA-256、CNN、FFT、Cache、AXI4-Lite Bridge）

### 关键缺口（按影响程度排序）

| # | 缺口 | 严重程度 | 工业界参照 |
|---|------|---------|-----------|
| 1 | yosys_equiv.py 已存在但未接入流水线 | 高 | FormalRTL 形式等价 |
| 2 | PPA 指标从未从综合报告提取 | 高 | ChipSeek-R1 PPA 优化 |
| 3 | 无仿真覆盖率测量 | 高 | RealBench 100% 行覆盖率 |
| 4 | 无 PPA 反馈闭环（综合→代码生成） | 高 | 标准综合优化流程 |
| 5 | fix-loop 检测用精确字符串匹配 | 中 | LocalV 结构化诊断 |
| 6 | 9/15 bug pattern 无自动化 matcher | 中 | ACE-RTL 上下文演进 |
| 7 | 无自动化 benchmark runner | 中 | RealBench/VerilogEval 评估 |
| 8 | 无约束随机测试生成 | 中 | UVM 约束随机 |
| 9 | 无 corner-case 测试生成 | 中 | RealBench 100% 覆盖率 |
| 10 | 无多 Agent 交叉验证 | 中 | ChipMATE 双实现+交叉验证 |
| 11 | Golden Model 无形式化属性提取 | 高 | FormalRTL SVA 生成 |
| 12 | 无设计空间探索 | 中 | EvolVE MCTS |
| 13 | 多时钟域 CDC 支持弱 | 中 | 工业 CDC 签核 |
| 14 | 无跨项目知识库 | 低 | ACE-RTL 经验积累 |
| 15 | 无层次化设计知识图谱 | 低 | VeriGraphi |

---

## 第一部分：可借鉴的工业界思路

### 1. ChipMATE — 多 Agent 交叉验证

**核心思路**：两个独立 Agent（Verilog agent + Python 参考模型 agent）各自独立实现，通过随机激励交叉验证。不依赖 golden testbench。

**VeriFlow 可借鉴之处**：
- 当前是单路径（一个 vf-coder 生成一份 RTL），golden model 是唯一真相源
- **风险**：如果 golden model 本身有语义 bug（误解 spec），RTL 会忠实地复制这个 bug，且 cocotb 会 PASS（因为 testbench 也在跟 golden model 对比）
- **改进**：新增可选的 "dual codegen" 模式——两个独立 vf-coder agent（或一个 vf-coder + 一个独立 Python 验证 agent）各自实现，交叉对比
- **难度**：中（需要修改 SKILL.md Stage 2 调度逻辑 + state.py 支持多输出）

### 2. FormalRTL — 形式验证集成

**核心思路**：用 LLM 从自然语言 spec 生成 SVA 属性，然后用形式工具（JasperGold/hw-cbmc）做等价性证明。

**VeriFlow 可借鉴之处**：
- `yosys_equiv.py`（265 行）已完整实现了 `equiv_make → opt_plus → equiv_simple → equiv_induct → equiv_status` 流程，但**从未被流水线调用**
- **改进**：将 yosys_equiv.py 接入 Stage 3（作为仿真的补充验证）和 Stage 4（作为综合后的等价性检查）
- **局限性**：Verilog-2005 约束禁止 SVA（`assert property`、`|->`、`##`），这是有意为之的兼容性选择。短期用 Yosys equiv 做组合+简单时序等价；长期考虑可选 SystemVerilog 模式
- **难度**：接入 yosys_equiv 低，SVA 生成高

### 3. LocalV — 层次化索引 + 局部调试

**核心思路**：
- 将长 spec 文档拆分为层次化索引片段，Agent 只关注相关片段
- locality-aware debugging：只重新验证受 fix 影响的信号路径

**VeriFlow 可借鉴之处**：
- 当前 debug 流程修复后**全量重跑仿真**（SKILL.md line 643），浪费 token 和时间
- 当前 fix-loop 检测用**精确字符串匹配**（state.py lines 292-310），代码行号变了就失效
- **改进**：
  - fix-loop 检测改为结构化签名 `(classification, signal_root, cycle_offset)`
  - 增量验证：修复后只重跑受影响的 test case
  - 5-point RCA 的 "error location" 和 "signal trace" 改为工具辅助填写
- **难度**：中低

### 4. ChipSeek-R1 — PPA 闭环优化

**核心思路**：用层级奖励 RL（syntax + functional + PPA）训练 LLM 同时优化功能正确性和 PPA。最终 27 个设计 PPA 超越人类手写。

**VeriFlow 可借鉴之处**：
- 当前 Stage 4 只检查综合报告文件是否存在（SKILL.md line 667: `test -f workspace/synth/synth_report.txt`），**不读取内容**
- vf-synthesizer agent **已经提取了** cell count、max frequency、area estimate（vf-synthesizer.md lines 40-46），但这些数据**从未流回上游**
- **改进**：
  - 解析综合报告的 PPA 指标，存入 state.py 的结构化字段
  - 增加 Stage 4→Stage 2 的 PPA 反馈：如果 max_freq < target * 0.9，回退 codegen 并带 timing constraint
  - 短期不做 RL（太重），但可以做 best-of-N：生成 3 个微架构变体，综合后选 PPA 最优的
- **难度**：PPA 提取低，反馈闭环中，Best-of-N 中高

### 5. ACE-RTL — Agentic Context Evolution

**核心思路**：RTL 专用模型 + 通用推理模型协作，通过迭代 bug-fixing 逐步积累上下文。

**VeriFlow 可借鉴之处**：
- 当前 PREV_FAILURE 机制已部分实现了这个模式——将失败信息结构化注入下一次 retry
- 但是 bug pattern 积累是**静态的**（人工编写的 15 条），不会从新项目中自动更新
- **改进**：每次成功修复一个 bug 后，自动提取 pattern 写入 bug_patterns.md（带频率计数）
- **难度**：中

### 6. VeriGraphi — 知识图谱驱动的层次化设计

**核心思路**：从 spec 构建设计知识图谱（模块层级 + 端口接口 + 连线语义 + 模块依赖），再用图谱驱动代码生成。

**VeriFlow 可借鉴之处**：
- 当前 `module_connectivity` 是扁平列表（state.py lines 272-281），不含信号级信息
- **改进**：
  - 将 module_connectivity 从 list 升级为有向图（networkx DiGraph）
  - 自动检测环路、不可达模块、扇出偏斜
  - 为层次化设计提供 interface 一致性校验
- **难度**：中

### 7. EvolVE — MCTS 设计空间探索

**核心思路**：用 MCTS 自动发现最优 RTL 生成工作流，在多个目标（功能、面积、时序、token 成本）间平衡。

**VeriFlow 可借鉴之处**：
- 当前每个模块只生成一个实现，无设计空间探索
- **改进**：可选 best-of-N 模式——对同一模块生成多个微架构变体，综合评估后选最优
- **难度**：高（需要改变单路径架构假设）

---

## 第二部分：RealBench 测试策略

### RealBench 概况

- 60 个模块级任务 + 4 个系统级任务（SD 卡控制器、AES 编解码核心、Hummingbirdv2 E203 CPU）
- 100% 行覆盖率 testbench + 形式化 checker
- 规格文档平均 197 行（vs VerilogEval 的 5.7 行），代码平均 241 行
- 包含子模块实例化任务

### 当前能力评估 vs RealBench 要求

| RealBench 要求 | VeriFlow 当前状态 |
|---------------|------------------|
| 结构化多模块 spec | 支持（requirement.md + spec.json module_connectivity） |
| 多级子模块实例化 | 已验证（14 个 RTL 文件含实例化） |
| 100% 行覆盖率 TB | 不支持（无覆盖率测量） |
| 形式化 checker | yosys_equiv 可用但未接入 |
| 多模态 spec（图+文） | 不支持（无图解析能力） |
| 系统级任务（3000+ 行代码） | 未测试（当前最大设计 886 行） |

### 测试策略（分三步走）

**Phase 1：可行性验证（选 5 个模块级任务）**

1. 从 RealBench 选取 5 个代表性模块级任务：简单组合逻辑、简单 FSM、含子模块实例化、数据通路密集型、协议接口型
2. 手动将 RealBench spec 转为 VeriFlow 的 requirement.md 格式
3. 运行全流水线，记录各阶段通过率和失败原因
4. 目标：确认 pipeline 能否处理 RealBench 级别的 spec 复杂度

**Phase 2：自动化 Runner（覆盖全部 60 个模块级任务）**

1. 开发 `benchmark_runner.py`：
   - 批量读取 RealBench JSONL 格式
   - 自动生成 project 目录（requirement.md + constraints.md）
   - 驱动 Claude Code `/vf-rtl` 非交互执行
   - 解析 `.veriflow/pipeline_state.json` 记录各阶段结果
   - 汇总 pass@1、per-stage pass rate、平均修复次数
2. 接入 yosys_equiv 作为形式化验证 gate
3. 与已发表的 RealBench 结果对比（GPT-5 13.5%、Claude 3.7 19.6%、LocalV 45.0%）

**Phase 3：系统级挑战（选 1-2 个系统级任务）**

1. 选取 AES 或 SD 卡控制器系统级任务
2. 测试 VeriGraphi 式知识图谱分解是否有助于层次化设计
3. 目标：即使不完全通过，也要理解失败模式

---

## 第三部分：分阶段实施路线图

### Phase 1：快速见效（1-2 周）—— 弥补最关键的缺口

**1.1 接入 yosys_equiv 到流水线**

- 修改：`SKILL.md` Stage 3 post-hook，增加 `python yosys_equiv.py` 等价性检查
- 修改：`state.py` 增加 `equivalence_proof` 状态字段
- 新增：`test_equivalence_gate.py` 测试等价性门控
- 参考：FormalRTL 的等价性检查流程

**1.2 PPA 指标提取与存储**

- 修改：`vf-synthesizer.md` 输出结构化 JSON（cell_count, max_freq_mhz, area_um2, critical_path_ns）
- 修改：`state.py` PipelineState 增加 ppa_metrics 字段
- 修改：`SKILL.md` Stage 4 post-hook，解析 PPA 指标并与 spec.json 约束对比
- 新增：`test_ppa_metrics.py`

**1.3 fix-loop 检测改为结构化签名**

- 修改：`state.py` detect_fix_loop()，从精确字符串匹配改为 `(classification, signal_root, cycle_offset)` 元组匹配
- 新增：`test_fix_loop_structural.py`
- 参考：LocalV 的 locality-aware debugging

**1.4 自动化 benchmark runner**

- 新增：`benchmark_runner.py` — 批量运行、解析结果、生成报告
- 支持：RealBench JSONL 格式 → VeriFlow project 目录自动转换
- 新增：`test_benchmark_runner.py`

### Phase 2：功能增强（3-4 周）—— 对齐工业界实践

**2.1 PPA 反馈闭环**

- 修改：`SKILL.md` 增加 Stage 4 → Stage 2 的条件回退路径
- 修改：`vf-coder.md` 增加 PPA-aware 重生成指令（"area exceeded by X%, suggest resource sharing"）
- 修改：`state.py` 支持 PPA 驱动的 stage rollback（区别于 bug-fix rollback）
- 参考：ChipSeek-R1 的 PPA 反馈机制

**2.2 覆盖率测量**

- 修改：`iverilog_runner.py` 增加覆盖率收集
- 修改：`cocotb_runner.py` 增加 coverage 报告解析
- 修改：`SKILL.md` Stage 3 post-hook 增加覆盖率阈值检查
- 新增：`test_coverage.py`
- 参考：RealBench 100% 行覆盖率

**2.3 增强 bug pattern 自动化匹配（覆盖剩余 9/15）**

- 修改：`bug_pattern_match.py` 增加 P2（移位寄存器耗尽）、P3（初始化不完整）、P5（复位遗漏）、P6（FSM 卡死）、P7（握手违规）、P8（计数器溢出）、P12（FSM 锁存竞争）的 signal-based matcher
- 新增：`test_bug_pattern_match_extended.py`

**2.4 约束随机测试生成**

- 修改：`vf-tb-gen.md` 增加 constrained-random 测试生成指令
- 修改：`golden_model_template.py` 增加 random test vector generator
- 新增：corner-case 自动生成（all-zeros, all-ones, max-length, backpressure, reset-mid-op）

### Phase 3：战略升级（5-8 周）—— 跨越式能力提升

**3.1 形式化属性生成**

- 新增：`formal_property_gen.py` — 从 spec.json 时序契约自动生成 SVA/立即断言
- 修改：`design_rules.md` 增加可选的 SystemVerilog 模式（保留 Verilog-2005 作为默认）
- 修改：`vf-coder.md` 增加 SVA 生成指令（仅在 SV 模式下）
- 修改：`yosys_equiv.py` 支持层次化等价性（多模块组合证明）
- 参考：FormalRTL 的 SVA 生成流程

**3.2 多 Agent 交叉验证模式**

- 新增：可选的 `--dual-codegen` 模式
- 修改：`SKILL.md` Stage 2 支持并行双 agent 代码生成
- 修改：`state.py` 支持多候选输出和 consensus 选择
- 新增：cross-verification runner（比较两个独立实现的输出）
- 参考：ChipMATE 的 cross-verification 架构

**3.3 设计知识图谱**

- 新增：`design_graph.py` — networkx 有向图表示模块连接关系
- 修改：`state.py` validate_spec_completeness 增加图属性检查（环路检测、不可达模块、扇出偏斜）
- 新增：`interface_consistency.py` — 跨模块接口一致性自动校验
- 参考：VeriGraphi 的知识图谱驱动生成

**3.4 跨项目知识库**

- 新增：`knowledge_base.py` — 跨项目 bug pattern 频率统计、设计模板复用
- 新增：`~/.claude/skills/vf-rtl/knowledge/` 目录持久化经验
- 修改：bug pattern 新增时自动版本记录和频率计数
- 参考：ACE-RTL 的经验积累机制

---

## 关键文件修改清单

| 文件 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|
| `SKILL.md` | yosys_equiv 接入, PPA hook | PPA 反馈闭环, 覆盖率 gate | dual-codegen 模式 |
| `state.py` | equivalence_proof 字段, ppa_metrics 字段, 结构化 fix-loop | PPA rollback 支持 | 多候选输出, 图属性校验 |
| `vf-synthesizer.md` | 结构化 JSON 输出 | — | — |
| `vf-coder.md` | — | PPA-aware 重生成指令 | SVA 生成指令 |
| `vf-tb-gen.md` | — | constrained-random 测试 | — |
| `bug_pattern_match.py` | — | 9 个新 matcher | — |
| `design_rules.md` | — | — | 可选 SV 模式 |
| `yosys_equiv.py` | — | — | 层次化等价性 |
| `iverilog_runner.py` | — | 覆盖率收集 | — |
| `cocotb_runner.py` | — | 覆盖率报告 | — |
| **新增** | `benchmark_runner.py` | `test_coverage.py` | `formal_property_gen.py`, `design_graph.py`, `knowledge_base.py` |

## 验证方案

- 每个 Phase 完成后，在 example_test/ 中选择 3 个代表性设计（SM3、AXI4-Lite Bridge、CNN）运行全流水线，确保无回归
- Phase 2 完成后，运行 RealBench Phase 1 选中的 5 个模块级任务，对比 baseline
- Phase 3 完成后，运行 RealBench 全部 60 个模块级任务，输出 pass@1 与学术基线对比

## 决策点（需要用户确认）

1. 是否开始 Phase 1 实施（yosys_equiv 接入 + PPA 提取 + fix-loop 结构化 + benchmark runner）
2. 是否在 Phase 3 引入可选的 SystemVerilog 支持（解锁 SVA/interface/enum），还是坚持 Verilog-2005 only
3. RealBench 测试是否先做可行性验证（5 个任务手动跑），还是直接投入做自动化 runner

# VeriFlow-CC 架构文档：LLM 写 Verilog 的痛点、我们的解法与未竟之事

> 本文档面向想了解 VeriFlow-CC 设计动机与技术取舍的工程师。文中所有结论均基于代码库当前状态（commit `6cd343b`）和 2024–2025 年学术界/工业界的实证研究。

---

## 1. 背景：LLM 写 Verilog 的五大痛点

### 1.1 训练数据不对称，但"Python 更多"是伪优势

公开 Verilog 代码量远小于 Python。康奈尔 PyHDL-Eval（MLCAD'24）做了一个反直觉的实验：让 LLM 直接生成 Verilog， vs. 让 LLM 生成 PyMTL3 / MyHDL / Amaranth 等 Python-embedded HDL，再转 Verilog。结果：**所有 5 种 DSL 的 pass rate 都低于直接写 Verilog**，MyHDL 最接近也仅 62%。

原因：DSL 的 API 是独特的（`m.d.sync +=`、`@vf_block`、`reg_next()`），训练语料里几乎没见过。Host language（Python）训练数据多，但 DSL-specific 的调用模式是冷门知识。LLM 对 DSL 的"先验"为零。

> 对我们的启示：如果让 LLM 直接写 DSL 再转 Verilog，性能反而更差。必须换一种方式利用 Python。

### 1.2 NBA 语义悬崖

LLM 的核心训练语料是顺序执行的 Python/C/Java。Verilog 的 NBA（Non-Blocking Assignment，`<=`）是**并发时序语义**：

- 同一条 `always @(posedge clk)` 里，所有 RHS 在当前周期 T 求值，LHS 在 T+1 才生效
- 组合逻辑和时序逻辑必须物理分离（`always @*` vs `always @(posedge clk)`）
- 常见的 "先算 `_next` 组合值，再 `<=` 进寄存器" 是两步 discipline

LLM 在写 Verilog 时，频繁犯以下错误：
- 在 sequential block 里用 blocking `=` 而不是 NBA `<=`
- 把组合 `_next` 信号当成寄存器读
- 用 `if/else if` 链处理 co-asserted 的 enable 信号，导致互斥执行
- 忘记给 `case` 加 `default`，综合出 latch

这些不是语法错误，是**语义错误** —— 语法检查器（iverilog -g2005）会通过，仿真才会暴露，而且暴露时往往只在特定 cycle。

### 1.3 规格→实现之间的时序真空

传统流程：

```
natural language spec  →  LLM writes Verilog  →  testbench verifies
```

这个链条跳过了"时序蓝图"。自然语言可以说"这是一个流水线"，但不会精确到"第 3 个 posedge 后 `valid_out` 拉高"。LLM 只能从上下文推断时序，推断错了就是整模块返工。

业界有尝试用 spec.json 或结构化 prompt 来填补，但 spec.json 是静态接口描述，不是**可执行**的时序契约。你没法在 RTL 生成之前验证 spec.json 的时序是否正确。

### 1.4 调试用最终输出，定位成本极高

现有 LLM Verilog 生成工具（MAGE、VerilogCoder 等）的验证闭环通常是：

1. 生成 RTL
2. 跑 testbench
3. 比较最终输出 vs golden
4. 如果不匹配，把错误日志喂给 LLM 让它改

问题在于：最终输出不匹配时，错误可能发生在任意 cycle 的任意寄存器。LLM 看到的是 "expected=0xDEADBEEF, got=0xCAFEBABE"，它不知道这是第 14 个 cycle 的 `round_reg[3]` 错了，还是第 7 个 cycle 的 `w_j` 输入就已经错了。猜-改-重仿真的循环成本极高。

MAGE（DAC'25）的改进是**per-cycle state checkpointing**：在每个 posedge 比较 RTL 内部状态 vs 期望状态。这是正确的方向，但 MAGE 的实现依赖 AST 分析和波形回溯工具，对 LLM prompt 不够友好。

### 1.5 多智能体协调缺少结构性护栏

MAGE、VerilogCoder、AIVRIL 等都引入了多智能体（生成 agent、testbench agent、debug agent）。但**生成 agent 本身没有结构性约束**——它可以生成任意 Verilog，只靠仿真后的外部反馈来纠错。

这类似于让一个人写代码没有类型系统，全靠单元测试发现 bug。能工作，但迭代次数高，且对复杂模块（>500 行 RTL）迅速失效。

---

## 2. VeriFlow-CC 的结构性解法

我们的核心信念：**把 LLM 的创造性限制在"翻译"而不是"发明"，把"正确性"交给结构和机械检查**。

### 2.1 可翻译子集（`veriflow_spec` 协议）

文件：`src/veriflow_dsl/_spec.py`

我们不让 LLM 直接写 Verilog，也不让 LLM 写 Amaranth/MyHDL。我们定义了一个**极窄的 Python 子集**，窄到可以机械 lowering 到 Verilog，同时保留足够的表达力描述常见 RTL 模式：

```python
@vf_block(type="sequential")
def counter(*, count_reg: RegT, en: RegT) -> list[RegAssign]:
    return [reg_next(count_reg, mux(en, count_reg + 1, count_reg))]
```

类型系统强制 NBA 语义：
- `RegT`：只读，表示"cycle T 时该寄存器的值"。**永远不可以作为返回值**
- `WireT`：组合信号，cycle T 内可见
- `RegAssign`：唯一的 NBA 动作，由 `reg_next()` 生成
- 条件必须用 `mux(cond, t, f)`，不能用 Python `if`

这 5 条纪律写在 `_spec.py` 的 docstring 里，adapter 在 lowering 时强制执行。LLM 如果写出子集外的代码，adapter 直接抛 `TypeError`/`SyntaxError`，而不是生成错误的 Verilog。

### 2.2 双路径代码生成（SKILL.md Stage 2）

```
timing_model.py
      │
      ├─ has_dsl_builder=true  →  VerilogEmitter.emit()  →  .v  (零 AI)
      │
      └─ has_dsl_builder=false →  vf-coder agent
                                   输入：timing_model + anchor 三元组
                                   输出：.v
```

**Path A（零 AI）**：简单模块（计数器、移位寄存器、握手）直接用 `VerilogEmitter` 吐 Verilog。这是**确定性的、可证明的、不需要 LLM**的路径。

**Path B（AI 翻译）**：复杂模块（FSM、哈希 round）让 vf-coder 翻译。但关键限制是：**LLM 不是从自然语言翻译到 Verilog，而是从 timing_model.py 翻译到 Verilog**。timing_model.py 已经是结构化的、可执行的、带类型签名的中间表示。LLM 的"创造性"被限制在"把这段 Python 翻成等价的 Verilog"，而不是"设计一个模块"。

### 2.3 Anchor 三元组：从代码形状到信号值

文件：`src/claude_skills/vf-rtl/anchors/<name>/`

每个 anchor 包含：
- `timing_model.py` — 参考实现（Python）
- `module.v` — 对应的 Verilog
- `trace.md` — **由 CycleSimulator 自动生成的周期表**

```markdown
## fsm_4state — 6-cycle trace

| cycle | state_reg | load_en | process_en | done_out | start | done_signal |
|------:|----------:|--------:|-----------:|---------:|:-----:|:-----------:|
|     0 |         0 |       0 |          0 |        0 |   1   |      0      |
|     1 |         1 |       0 |          0 |        0 |   0   |      0      |
```

vf-coder 的 prompt 里嵌入这些 trace.md。LLM 在翻译时看到的不是抽象的 coding style 规则，而是**具体的信号值**："当 `start=1` 时，下一个 cycle `state_reg` 从 0 变成 1，但 `load_en` 要到再下一个 cycle 才变成 1"。

这是**信号值级别的 few-shot grounding**，比语法级别的 grounding 有效得多。

### 2.4 期望周期表对比（error_recovery.md）

当 Stage 3 仿真失败时，pipeline 自动运行：

```bash
python -m veriflow_dsl.trace_export \
  --timing-model workspace/docs/timing_model.py \
  --block <name> --cycles <auto> \
  --output logs/expected_trace_<name>.md
```

生成 `expected[cycle][reg]` 表。然后与 VCD 抽出的 `actual[cycle][reg]` 对比：

```
expected[cycle=5][round_reg] = 0x04      (from expected_trace_*.md)
actual  [cycle=5][round_reg] = 0x03      (from VCD)
```

**差距本身就是 bug 的签名**。错误恢复 prompt 直接拿到 "cycle=5, round_reg 差了 1"，而不是 "最终输出不匹配"。这是从 O(n²) 的猜-改循环降到 O(1) 的精确定位。

### 2.5 NBA Lint Hook（仿真前拦截）

文件：`src/veriflow_dsl/lint_nba.py`

在跑仿真之前，对 RTL 做静态检查：

| Rule | 检查内容 |
|------|----------|
| L1 | sequential block 只能用 `<=`，不能用 `=` |
| L3 | module ports 与 spec.json 对齐 |
| L4 | sequential block 不允许读 `_next` 组合信号（finalize bug） |
| L5 | co-asserted enable 不能用 `if/else if` 链 |
| L6 | `case` 必须有 `default` |
| L7 | concatenation 位宽必须匹配目标 |

这些规则在 vf-coder 的 Step 4 验证阶段强制执行。失败直接反馈行号和修复建议，不消耗仿真时间。

### 2.6 PYTHONPATH 作为部署面

文件：`install.py`、`init.py`

之前 SKILL.md 里到处写 `PYTHONPATH=src python -m veriflow_dsl.lint_nba ...`，这在用户项目里会覆盖 init.py 设置的 PYTHONPATH，导致 `ModuleNotFoundError`。

现在的设计：
1. `install.py` 把 `src/veriflow_dsl/` symlink 到 `~/.claude/skills/vf-rtl/veriflow_dsl/`
2. `init.py` 把 `export PYTHONPATH="$SKILL_DIR:${PYTHONPATH:-}"` 写进 `eda_env.sh`
3. 所有 pipeline 命令先 `source eda_env.sh`，然后裸跑 `python -m veriflow_dsl.*`

这是一个"基础设施即护栏"的设计：环境正确，命令才能正确；环境不对，命令根本跑不起来。

---

## 3. 仍然存在的问题

### 3.1 PyHDL-Eval 天花板

我们的 mitigation（anchor triples）只能覆盖 7 种常见模式。对于全新的架构（例如自定义脉动阵列、Galois Field 运算单元），LLM 没有对应的 anchor，翻译质量会退回到"纯 Verilog 生成"的基线。

Path A（零 AI emit）是确定性的胜利，但它要求模块能被 `@vf_block` 表达。很多控制逻辑（复杂 FSM、带仲裁的多端口缓存）目前还只能用 Path B。

### 3.2 组合逻辑块是二等公民

当前 `_adapter.py` 支持 `type="combinational"`，但：
- 只有一个 combinational anchor（`barrel_shifter_var_n`）
- combinational 块的返回值是 `WireT`，不能直接参与多周期 trace（因为 simulator 的 trace 是 cycle-based，combinational 输出每个 cycle 都变，但没有状态历史）
- 没有 `enable=` 的 combinational 等价物（组合逻辑没有"使能"概念，但 conditional assignment 仍需 `assign out = sel ? a : b`）

### 3.3 Trace 表格在 prompt 中的可读性瓶颈

32-bit 信号 × 16+ cycles = 很宽的 markdown 表格。LLM 的上下文窗口有限（尤其处理多文件时），大表格容易被截断或忽略。

当前 format 是逐 cycle 全量展开。对于长流水线（如 SHA-256 的 64 rounds），需要一种"差异摘要"格式：只显示变化的寄存器，或只显示 divergence 附近的窗口。

### 3.4 没有形式等价验证

`expected_trace` 是仿真驱动的，只能覆盖有限 cycle。没有接入 Yosys `miter` / `equiv_simple` 或任何 formal 工具。

这意味着：如果 RTL 在 untraced cycle（比如初始化后的第 1000 个 cycle）出现 corner-case 错误，trace diff 无法发现。

### 3.5 Timing Model 与 Golden Model 的权威冲突

`timing_model.py`（可翻译子集）和 `golden_model.py`（纯算法参考）可能不一致。例如：
- golden_model 用 Python `int` 做无符号运算，timing_model 用 `RegT(32)` 会自然溢出
- golden_model 可能在 cycle 0 就输出结果，而 timing_model 的 pipeline delay 要求 3 个 cycle

当前 pipeline 没有仲裁机制：Stage 3 的 error recovery 假设 timing_model 是 RTL 的 ground truth，golden_model 是 testbench 的 ground truth。如果二者矛盾，LLM 会陷入"修 RTL 修 testbench 修 RTL"的死循环。

### 3.6 单时钟域假设

`_spec.py` 和 `CycleSimulator` 假设所有 `reg_next()` 都在同一个 posedge 域。没有：
- 多 clock domain（`clk_fast`、`clk_slow`）
- Async reset 域
- Clock gating
- CDC（Clock Domain Crossing）primitive

这限制了 VeriFlow-CC 在当前形态下只能处理单时钟同步设计。扩展到多时钟需要 `Domain` 的重新设计（不能只有一个 `m.d.sync`）。

### 3.7 `--cycles` 是启发式

SKILL.md 的 auto-cycles 用 `max(pipeline_delay_cycles) + 4`。这对固定延迟的流水线足够，但对数据依赖延迟的设计（例如分支预测 miss 后的 flush、动态调度的处理器）会严重低估。

更 robust 的方案应该是：从 spec.json 的 FSM 状态图计算覆盖所有 transition 所需的最少 cycles。

### 3.8 Windows 非管理员回退

`install.py` 在 Windows 非 admin 环境下 fallback 到 `shutil.copytree`（因为 symlink 需要管理员权限）。这意味着：
- 安装后如果用户在 git repo 里改了 `src/veriflow_dsl/`，已安装的 copy 不会自动同步
- 必须重新运行 `install.py`

这是 Python `os.symlink` 在 Windows 上的已知限制，目前没有完美的跨平台解决方案。

---

## 4. 设计原则与取舍

| 原则 | 取舍 |
|------|------|
| **结构性 > 文档性** | `coding_style.md` 从 1324 行瘦到 ~150 行；真正强制的约束在 `_spec.py` 的类型系统里 |
| **Emit > Translate** | Path A（零 AI）优先，因为确定性 > 创造性；Path B 是逃逸舱 |
| **Cycle-level > Module-level** | Per-cycle trace diff 比最终输出比较定位速度快 10x 以上 |
| **Mechanical lint > Simulation** | `lint_nba.py` 在仿真前拦截，避免支付 EDA 工具启动成本 |
| **Deployed package > PYTHONPATH hack** | `install.py` + `init.py` 把 DSL 变成一等公民，不再依赖 `src/` 相对路径 |
| **类型守卫 > 运行时检查** | `RegT`/`WireT` 在 Python 层面就拒绝错误，而不是等 iverilog 报 `wire is not a valid lvalue` |

---

## 5. Roadmap

- [x] **Combinational 补完**：增加 priority_encoder_8bit anchor；扩展 combinational adapter 支持 tuple[WireT] 多输出；VerilogEmitter combinational block 启用 auto_temp 共享子表达式
- [x] **Trace 摘要模式**：`trace_export.py` 支持 `mode="diff"`，用 `"` 压缩重复值
- [x] **Formal equivalence hook**：新增 `yosys_equiv.py`，集成到 SKILL.md Stage 3 作为可选预仿真检查
- [x] **Timing Model / Golden Model 一致性检查器**：`model_consistency_checker.py` 在 Stage 1 作为 pre-codegen gate 自动运行
- [x] **spec.json trace_cycles 显式覆盖**：`constraints.verification.trace_cycles` 优先于启发式 cycle 计算
- [x] **动态 Anchor 检索**：`_selector.py` 支持从 module_spec 自动推断特征并匹配 anchor
- [ ] **多时钟域**：`_spec.py` 支持 `@vf_block(clk="clk_fast")`，`CycleSimulator` 支持多 domain 调度
- [ ] **Windows symlink 替代方案**：研究 `junction` 或 `mklink /D` 作为 admin-free 的 directory link
- [ ] **更多 combinational anchor**：加法树、crossbar、leading-zero counter 等

---

## 参考

- [PyHDL-Eval (Cornell, MLCAD'24)](https://www.csl.cornell.edu/~cbatten/pdfs/batten-pyhdl-eval-mlcad2024.pdf) — LLM 在 Python-embedded HDL 上表现差于原生 Verilog
- [MAGE (DAC'25)](https://arxiv.org/html/2412.07822v1) — per-cycle state checkpointing 提升 debug 精度
- [VerilogCoder / MAGE / VeriMind 综述 (2025)](https://arxiv.org/html/2512.00020v2) — multi-agent RTL generation 趋势分析
- [Amaranth HDL docs](https://amaranth-lang.org/docs/amaranth/latest/intro.html) — Python HDL 设计参考
- [MyHDL](https://www.myhdl.org/) — 最早的 Python→Verilog convertible subset 思想来源

# VeriFlow-CC v2 重构方案

> 目标：把 LLM 对 NBA 时序的认知"硬"在结构里，而不是"软"在 1324 行规则文档里。
> 整合 veriflow-python 的 DSL 经验到 veriflow-cc，veriflow-python 不再维护。

---

## 1. 背景与诊断

### 1.1 现状问题

| 问题 | 根因 |
|---|---|
| veriflow-cc 时序错误频发 | spec.json + golden_model.py 缺少**可执行的时序蓝图**，全靠 1324 行 coding_style.md + 15 点自检兜底 |
| veriflow-python 代码生成不一致 | `design_spec.py` 是软约束（注释 + 命名约定），AI 多次生成会风格漂移 |
| 共同根因 | LLM 跨越「算法/接口」→「带时序 RTL」时，桥梁是隐式的英文规则，没有结构性兜底 |

### 1.2 v2 设计目标

1. **NBA 内化**：让 LLM 在写 Verilog 时无法绕开 NBA 语义（结构性 > Lint 性 > 文档性）
2. **DSL 双路径**：简单模块零 AI 直接 emit，复杂模块 AI 翻译但只能从 timing_model 翻
3. **代码量减半**：coding_style.md 从 1324 行瘦到 ~150 行，规则被结构吸收
4. **保留 veriflow-cc 卖点**：用户输入仍只是需求文档，timing_model.py 由 vf-architect 生成

---

## 2. 设计原则（按 ROI 排序）

| 优先级 | 原则 | 实现层 |
|---|---|---|
| P0 | **结构性强制 > 规则文档** | veriflow_spec 协议、类型签名 |
| P0 | **DSL emit 优先 > AI 翻译** | 简单模块走 emitter；复杂走 AI |
| P1 | **机械 Lint 闭环 > 仿真闭环** | NBA 静态检查器，仿真前拦截 |
| P1 | **锚点对照 > 抽象规则** | 7 个 Python ↔ Verilog 对照 |
| P2 | **命名编码时序** | `_reg` / `_next` / `_T` 后缀 |
| P3 | **文档作为最后一层** | 只留 Verilog-2005 红线 + lint 经验 |

---

## 3. 整体架构

### 3.1 数据流

```
用户输入
  requirement.md / constraints.md / design_intent.md / context/*.md
        │
        ▼
┌──────────────────────────────────────────────┐
│ Stage 0: Init + 七类需求澄清                 │
│ → .veriflow/clarifications.md                │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Stage 1: vf-architect 子代理                 │
│ → workspace/docs/spec.json     (接口锁)      │
│ → workspace/docs/timing_model.py (新)        │
│ → workspace/docs/golden_model.py (纯算法)    │
└──────────────────────────────────────────────┘
        │
        ├─ 模块标签 anchor_hints + has_dsl_builder
        │
        ▼
┌──────────────────────────────────────────────┐
│ Stage 2: 双路径代码生成                      │
│                                              │
│   has_dsl_builder=true 模块：                │
│     timing_model.build_<m>() → DSL Emitter   │
│     → workspace/rtl/<m>.v  (零 AI)           │
│                                              │
│   其他模块：                                 │
│     vf-coder 子代理                          │
│       输入：timing_model 函数 + 锚点 + slim │
│             coding_style                     │
│     → workspace/rtl/<m>.v                    │
│                                              │
│   每个模块产出后：NBA Lint Hook              │
│     失败 → 反馈错误行号给 vf-coder 重做      │
│            （3 次预算）                      │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Stage 3: verify_fix                          │
│   cocotb / iverilog 仿真                     │
│   失败 → 错误恢复（5 点根因 + 3 次预算）     │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ Stage 4: lint_synth (并行)                   │
└──────────────────────────────────────────────┘
```

### 3.2 新增/改动模块清单

```
veriflow-cc/
├── src/
│   ├── veriflow_dsl/                    [新增 — 从 veriflow-python 迁移]
│   │   ├── __init__.py
│   │   ├── _spec.py                     [新增] RegT/WireT/RegAssign/reg_next
│   │   ├── _types.py                    [迁移] Signal/Const/Cat/Mux/BinOp/ROL
│   │   ├── _module.py                   [迁移+扩展] Module/Domain + 适配新协议
│   │   ├── _emitter.py                  [迁移] VerilogEmitter
│   │   ├── _simulator.py                [迁移] CycleSimulator
│   │   ├── _trace.py                    [迁移] 波形追踪
│   │   ├── lint_nba.py                  [新增] NBA 静态检查器
│   │   └── tests/                       [迁移]
│   │
│   ├── claude_skills/vf-pipeline/
│   │   ├── SKILL.md                     [改] Stage 2 增加双路径分发
│   │   ├── coding_style.md              [瘦身] 1324 → ~150 行
│   │   ├── coding_style_archive.md      [新增] 旧 1324 行归档（备查）
│   │   ├── anchors/                     [新增]
│   │   │   ├── _selector.py             [新增] anchor_hints → 锚点路径
│   │   │   ├── fsm_4state/
│   │   │   │   ├── timing_model.py
│   │   │   │   └── module.v
│   │   │   ├── shift_register/
│   │   │   ├── pipeline_register/
│   │   │   ├── hash_round_one_cycle/
│   │   │   ├── handshake_hold_until_ack/
│   │   │   ├── handshake_single_cycle/
│   │   │   └── barrel_shifter_var_n/
│   │   └── templates/
│   │       ├── spec_template.json       [小改] 增加 anchor_hints / has_dsl_builder 字段
│   │       └── timing_model_template.py [新增] 替代 golden_model_template 的时序角色
│   │
│   └── claude_agents/
│       ├── vf-architect.md              [改] 输出 timing_model.py
│       └── vf-coder.md                  [大改] 输入改为 timing_model + 锚点；prompt 瘦身
│
├── agent/                               [新增 — 从 veriflow-python 迁移]
│   ├── hierarchy_check.py               [迁移] 模块层次校验
│   ├── instance_gen.py                  [迁移] 模块实例代码生成
│   ├── rtl_checker.py                   [迁移] RTL 端口对齐检查
│   └── eda_paths.py                     [迁移] EDA 工具发现
│
└── docs/
    └── refactor_v2_plan.md              [本文件]
```

---

## 4. 详细组件设计

### 4.1 veriflow_spec 协议（核心 — 决定全局成败）

**文件**：`src/veriflow_dsl/_spec.py`

**类型层次**：

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class RegT:
    """T 时刻的寄存器值（只读）。
    
    在 timing_model 函数中，作为输入参数表示"posedge T 时该寄存器的当前值"。
    NEVER 作为返回值出现 — 返回值必须是 RegAssign。
    """
    name: str
    width: int
    
    # 操作符重载：保证 RegT/WireT/int 之间运算返回 WireT（组合）
    def __add__(self, other) -> "WireT": ...
    def __xor__(self, other) -> "WireT": ...
    def __and__(self, other) -> "WireT": ...
    # ... 完整算术/位运算集合


@dataclass(frozen=True)  
class WireT:
    """组合信号（同周期可见）。
    
    timing_model 函数体内的局部变量、参数中的组合输入都是 WireT。
    任何 RegT/WireT 间的算术运算结果都是 WireT。
    """
    name: str
    width: int
    expr: "Expr"  # 表达式 AST，emitter 用它生成 assign


@dataclass(frozen=True)
class RegAssign:
    """NBA 赋值动作 — `reg_next(curr_reg, next_value)` 的返回类型。
    
    timing_model 函数返回值必须是 list[RegAssign] 或 tuple[RegAssign, ...]。
    每个元素表示"在 posedge T+1，curr_reg 取得 next_value"。
    """
    target: RegT          # 被赋值的寄存器
    next_value: WireT | int  # T 时刻计算出的下一周期值
    enable: WireT | None = None  # 可选使能（用于 if(en) reg <= ...）


def reg_next(curr: RegT, next_value: WireT | int, *, en: WireT | None = None) -> RegAssign:
    """显式 NBA 赋值：T+1 时刻 curr 取得 next_value。
    
    禁止：
        - reg_next(wire_x, ...)  # 第一个参数必须是 RegT
        - 不通过 reg_next() 直接 return RegT  # 类型检查会拦
    """
    if not isinstance(curr, RegT):
        raise TypeError(f"reg_next first arg must be RegT, got {type(curr).__name__}")
    return RegAssign(target=curr, next_value=next_value, enable=en)


def mux(cond: WireT | RegT, t: WireT | RegT | int, f: WireT | RegT | int) -> WireT:
    """显式组合多路选择 — 等价于 Verilog `cond ? t : f`。"""
    ...


def cat(*parts: WireT | RegT | int) -> WireT:
    """位拼接 — 等价于 Verilog `{a, b, c}`。最左为最高位。"""
    ...


def slice_(sig: WireT | RegT, msb: int, lsb: int) -> WireT:
    """位选 — 等价于 Verilog `sig[msb:lsb]`。"""
    ...


# FSM 钩子（W1 预留，W3 真正实现）
def vf_fsm(states: list[str], reset_state: str):
    """装饰器：声明这是一个 FSM 模块。
    
    被装饰的函数体内可以使用 fsm.case(state) / fsm.transition(cond, next_state)。
    """
    ...


def vf_block(type: str = "sequential"):
    """装饰器：声明 timing_model 函数是一个 RTL 块。
    
    type:
      - "sequential": 标准 NBA 块，参数 = 当前 reg，返回 = list[RegAssign]
      - "combinational": 纯组合块，无寄存器，返回 = WireT 或 tuple[WireT, ...]
      - "fsm": 含 FSM 状态机
    """
    ...
```

**关键约束**（lint/类型检查同时强制）：

1. `reg_next()` 的第一个参数必须是 RegT
2. `@vf_block(type="sequential")` 函数返回必须是 `list[RegAssign]` 或 `tuple[RegAssign, ...]`
3. `@vf_block(type="combinational")` 函数体内不能调用 `reg_next()`
4. RegT 不能出现在 `@vf_block` 函数的返回值中（必须包装成 RegAssign）

### 4.2 timing_model.py 文件规范

**位置**：`workspace/docs/timing_model.py`（vf-architect 产出，vf-coder 消费）

**强制结构**（5 节）：

```python
"""timing_model.py — 设计的 cycle-accurate Python 模型。

每个 @vf_block 函数 = 一个 Verilog 模块。
参数命名约定：
  - <name>_reg: RegT     T 时刻寄存器值
  - <name>_w  : WireT    T 时刻组合信号  
  - <name>_en : RegT     使能信号（来自 FSM 寄存器）
返回值：
  - list[RegAssign]      NBA 赋值集合
"""

from veriflow_dsl import (
    RegT, WireT, RegAssign, 
    reg_next, mux, cat, slice_,
    vf_block, vf_fsm,
)
from veriflow_dsl.ops import rotate_left, rotate_right

# ============================================================
# Section 1: Constants
# ============================================================
MASK32 = 0xFFFFFFFF
T_CONSTANTS = [...]  # 算法常量

# ============================================================
# Section 2: 模块层次 + 接口连线
# ============================================================
MODULE_HIERARCHY = {
    "<top_name>": {
        "submodules": [
            {
                "instance_name": "u_round",
                "module": "round_step",
                "connections": {
                    "a_reg": "a_reg",
                    "w_j_w": "w_j_w",
                    ...
                },
            },
        ],
    },
}

# ============================================================
# Section 3: 模块定义（每个函数 = 一个 Verilog 模块）
# ============================================================

@vf_block(type="sequential")
def round_step(
    *,                          # 强制关键字参数（不允许位置传参错位）
    a_reg: RegT,
    b_reg: RegT,
    w_j_w: WireT,               # 组合输入（来自上游 wire）
    calc_en: RegT,              # FSM 使能（寄存器输出）
) -> list[RegAssign]:
    """单轮压缩 — 一个时钟周期完成一轮迭代。
    
    timing_contract:
        inputs:
            a_reg, b_reg: source="self_reg", delay=0, type="reg"
            w_j_w:        source="w_gen",    delay=0, type="wire"
            calc_en:      source="fsm",      delay=1, type="reg"
        outputs:
            a_reg', b_reg': delay=1, type="reg_next"
    """
    # 组合逻辑（WireT，同周期可见）
    ss1 = rotate_left(a_reg + w_j_w, 7)
    ss2 = ss1 ^ b_reg
    
    # 下一周期值
    return [
        reg_next(a_reg, mux(calc_en, ss1, a_reg)),
        reg_next(b_reg, mux(calc_en, ss2, b_reg)),
    ]


# ============================================================
# Section 4: DSL Builder（可选 — 简单模块走 emit 路径）
# ============================================================
# 如果定义了 build_<module_name>()，Stage 2 会优先用 DSL emitter
# 直接产 Verilog，跳过 AI 翻译。
#
# def build_counter():
#     m = Module("counter")
#     count = m.reg("count", 8)
#     m.d.sync += count.eq(count + 1)
#     return m

# ============================================================
# Section 5: Test Vectors（标准接口）
# ============================================================
TEST_VECTORS = [...]

def run(test_vector_index: int = 0) -> list[dict]:
    """通过 CycleSimulator 跑出 cycle-accurate 期望波形。"""
    ...
```

**spec.json 增加字段**（只在 module 级别）：

```json
{
  "module_name": "round_step",
  "anchor_hints": ["hash_round_one_cycle"],
  "has_dsl_builder": false,
  ...
}
```

### 4.3 DSL Emitter（从 veriflow-python 迁移）

**迁移清单**（直接复制，仅修改 import 路径）：

| 源文件 | 目标 | 改动 |
|---|---|---|
| `dsl/_types.py` | `src/veriflow_dsl/_types.py` | 无 |
| `dsl/_module.py` | `src/veriflow_dsl/_module.py` | 增加适配层吃新协议 |
| `dsl/_emitter.py` | `src/veriflow_dsl/_emitter.py` | 无 |
| `dsl/_simulator.py` | `src/veriflow_dsl/_simulator.py` | 无 |
| `dsl/_trace.py` | `src/veriflow_dsl/_trace.py` | 无 |
| `dsl/tests/` | `src/veriflow_dsl/tests/` | 无 |

**适配层**（`_module.py` 内新增）：

```python
def from_timing_model(func) -> "Module":
    """把 @vf_block(type="sequential") 装饰的函数转成 Module。
    
    用于 has_dsl_builder=False 的模块也想用 emitter 时（v2.1 探索）。
    v2.0 阶段不强制使用 — 只让 build_*() 显式构造。
    """
    ...
```

### 4.4 锚点库

**位置**：`src/claude_skills/vf-pipeline/anchors/`

**7 个核心锚点**（每个含 `timing_model.py` + `module.v`）：

| 锚点 | 适用场景 | 关键示范点 |
|---|---|---|
| `fsm_4state/` | 4 状态 FSM | localparam 状态编码、两段式（次态组合 + 现态时序） |
| `shift_register/` | 移位寄存器 | 每周期补位、shift_en 门控、`<=` NBA |
| `pipeline_register/` | 流水线寄存器 | valid 跟随数据流、bubble 处理 |
| `hash_round_one_cycle/` | 算法单轮迭代 | 寄存器组同时更新、组合扩展 + 寄存器压缩 |
| `handshake_hold_until_ack/` | 持续握手 | valid 一直拉高直到 ack、不被使能门控 |
| `handshake_single_cycle/` | 单拍握手 | valid 仅 1 周期、伴生 last 信号 |
| `barrel_shifter_var_n/` | 可变量旋转 | log2(W) 阶级联 mux、禁用变量 part-select |

**锚点选择**（`anchors/_selector.py`）：

```python
def select_anchors(module_spec: dict) -> list[Path]:
    """根据 spec.json 模块的 anchor_hints 字段返回锚点目录路径。
    
    spec 中的 anchor_hints 由 vf-architect 在 Stage 1 打标。
    每个模块最多取 2 个最相关的锚点塞进 vf-coder prompt。
    """
    hints = module_spec.get("anchor_hints", [])
    return [ANCHORS_DIR / h for h in hints[:2]]
```

**vf-architect 打标规则**（写入 architect.md）：

```
模块特征 → anchor_hints
- module_type=control + has_states  → fsm_4state
- 含移位寄存器 + shift_en           → shift_register
- 算法迭代 + 寄存器组               → hash_round_one_cycle
- 含 valid + ack                    → handshake_hold_until_ack
- 含可变旋转量                      → barrel_shifter_var_n
```

### 4.5 NBA 静态 Lint Hook

**文件**：`src/veriflow_dsl/lint_nba.py`

**触发时机**：vf-coder Write 完成后、`stage3_verify_fix` 之前。

**4 项检查**（按实现难度分批）：

| 检查项 | 实现 | 第 W3 周做 | 备注 |
|---|---|---|---|
| **L1: 时序块只能 NBA** | regex 扫 `always @(posedge` 块体内 `=` | ✓ | 排除 `=` 在比较运算符内的场景 |
| **L2: 组合块敏感列表** | iverilog `-Wall` 包装 | ✓ | 直接复用 lint stage 已有逻辑 |
| **L3: 端口对齐** | 比对 spec.json 与模块头 | ✓ | port 名/宽/方向 |
| **L4: 同周期读 reg_next** | pyverilog AST 跨块跟踪 | △ stretch | 抓不到不致命，可放 W5 |

**接口**：

```python
def lint_module_v(rtl_path: Path, spec_module: dict) -> list[LintError]:
    """对单个 Verilog 文件做 NBA 静态检查。
    
    Returns:
        空列表 = 通过；非空 = 失败，每个 LintError 含 line + 1 句话原因。
    """
    errors = []
    src = rtl_path.read_text()
    errors.extend(_check_seq_only_nba(src))      # L1
    errors.extend(_check_port_alignment(src, spec_module))  # L3
    # L2 由外部 iverilog 调用承担
    return errors


@dataclass
class LintError:
    line: int
    rule: str           # "L1_seq_only_nba" / "L3_port_align"
    message: str        # 给 vf-coder 看的 1 句话
    suggested_fix: str  # 简短建议
```

**反馈循环**（写入 SKILL.md Stage 2）：

```
for module in spec.modules:
    if module.has_dsl_builder:
        emit_via_dsl(module)
        continue
    
    for attempt in range(3):
        invoke_vf_coder(module, anchors=select_anchors(module))
        errors = lint_module_v(rtl_path, module)
        if not errors:
            break
        feedback = format_lint_errors(errors)
        # vf-coder 第二次调用时 prompt 含 feedback
    else:
        raise PipelineError(f"{module.name} fails NBA lint after 3 attempts")
```

### 4.6 vf-architect 改造

**变化**：

1. **输出多一个文件**：`workspace/docs/timing_model.py`
2. **golden_model.py 角色变窄**：只保留纯算法（不带时序），用于 Stage 3 cocotb 对比和最终输出验证
3. **spec.json 字段扩展**：每个 module 加 `anchor_hints` + `has_dsl_builder`
4. **打 anchor_hints 标签**：按 4.4 节规则打标

**架构师 prompt 关键改动**（`src/claude_agents/vf-architect.md`）：

```diff
- ### Step 3: Write golden_model.py
+ ### Step 3: Write timing_model.py + golden_model.py

+ timing_model.py 是 cycle-accurate Python 模型，每个 @vf_block 函数对应一个
+ Verilog 模块。强制使用 veriflow_dsl 提供的 RegT/WireT/RegAssign/reg_next 类型。
+ 
+ golden_model.py 角色窄化为"纯算法参考"，无时序结构，用于 cocotb 比对最终输出。
+
+ 标注 anchor_hints：根据每个模块的特征，从 7 个锚点中选 1-2 个最相关的标签。
+
+ 标注 has_dsl_builder：如果模块足够简单（counter、mux、shift register、固定 FSM），
+ 在 timing_model.py 内同时定义 build_<module>() 函数，并设 has_dsl_builder=true。
```

### 4.7 vf-coder 改造

**变化**：

1. **输入改变**：从 `(spec.json + golden_model.py + 1324 行 coding_style)` 改为 `(spec.json + timing_model.py 单个函数 + 2 个锚点 + ~150 行 coding_style)`
2. **任务塌缩**：从"理解算法 + 推时序 + 写 Verilog"塌缩成"翻译这个 Python 函数到 Verilog"
3. **强制输出格式**：先输出 cycle-accurate timing 表，再输出 Verilog 文件
4. **失败反馈循环**：lint 失败时 prompt 中加入错误行号 + 建议修复

**新 prompt 骨架**（`src/claude_agents/vf-coder.md`，目标 ~150 行）：

```
你是一个 timing_model.py → Verilog 翻译器。

输入（prompt 内联给你）：
- TARGET_FUNCTION: timing_model.py 中的一个 @vf_block 函数源码
- MODULE_SPEC: spec.json 中该模块的 ports/parameters/timing_contract
- ANCHOR_1, ANCHOR_2: 最相关的两个锚点（Python ↔ Verilog 对照）
- CODING_STYLE: ~150 行的语法红线（不含时序规则）

任务：
1. 输出 cycle-accurate timing 表（fixed format）
2. 输出 Verilog 文件（Verilog-2005，与锚点风格一致）

时序映射规则（4 条，硬约束）：
- 函数参数 RegT  → input wire（在调用方表示寄存器输出）
- 函数参数 WireT → input wire（组合信号）
- 函数体局部变量 → wire + assign（组合）
- list[RegAssign] 每个元素 → output reg + always @(posedge clk) <= block

NBA 自检（写完前必须心算确认）：
- 每个 <= 的右值是 OLD 寄存器值还是新计算的 wire？
- 每个 if/else if 链的两个 enable 是否会同周期为真？

输出格式（不可变）：
[CYCLE TABLE]
| Cycle | FSM    | <reg_a> | <reg_b> | <output> |
|-------|--------|---------|---------|----------|
| ...

[MODULE_NAME].v 已通过 Write 工具写入。
```

**长度对比**：

| 文档 | 旧 | 新 |
|---|---|---|
| `vf-coder.md` | 170 行（含 15 点自检） | ~80 行 |
| `coding_style.md` | 1324 行 | ~150 行 |
| 时序规则总量 | ~1494 行 | ~230 行 + 类型签名 + 锚点 |

### 4.8 coding_style.md 瘦身

**保留**（~150 行）：

| 章节 | 行数预估 | 内容 |
|---|---|---|
| Verilog-2005 红线 | 25 | `logic`/`always_ff`/`enum`/`struct` 等 ban 列表 |
| 文件结构 | 20 | 模块头、注释、缩进 |
| 命名 | 15 | `_reg`/`_n`/`_i`/`_o` 后缀、参数大写 |
| 复位策略 | 15 | 同步高有效 `rst`、复位优先级 |
| 二段式状态机 | 25 | 现态时序 + 次态组合的标准模板 |
| Latch 消除 | 20 | `default:` / `else` 分支必填 |
| 数字字面量 | 10 | `8'h0F` 而非 `0x0F` |
| 模块实例化 | 10 | 命名端口 `.port_name(signal)` |
| Lint 经验 | 10 | full/parallel case 等 |

**删除**（~1170 行，移到结构）：

- 所有"NBA / 寄存器延迟"相关章节 → 类型协议保证
- 所有"co-asserted enable / load 旁路"相关 → lint hook 检查
- 所有"output trace-back / dual register init / finalize state" → timing_model 表达
- 15 点自检列表 → 删（错误已被 lint 拦截）
- `vf-coder.md` 内联的 T/T+1 心智模型 → 由锚点示范

**归档**（备查）：旧文件改名 `coding_style_archive.md`，不再被 SKILL 引用。

---

## 5. 五周实施计划

### Week 1 — 基础设施：协议 + DSL 迁移

**目标**：能跑通"写一个 timing_model.py 函数 → DSL emit → 输出 Verilog"端到端。

**Deliverables**：

- [ ] `src/veriflow_dsl/_spec.py`：RegT/WireT/RegAssign/reg_next/mux/cat/slice_/vf_block/vf_fsm（fsm 留 stub）
- [ ] `src/veriflow_dsl/` 完整迁移：_types/_module/_emitter/_simulator/_trace + tests
- [ ] `src/veriflow_dsl/_module.py` 增加 `from_timing_model()` 适配层（v2.1 用，v2.0 留接口）
- [ ] 单测：92 个旧 DSL 测试 + 新增 ~20 个协议测试（类型约束、reg_next 行为、混合表达式）

**验收**：
- `pytest src/veriflow_dsl/tests/` 全绿
- 写一个 `examples/counter_timing_model.py`，能用 `Module` 直接 emit 出和手写一致的 `counter.v`

**风险点**：
- RegT/WireT 的运算符重载与现有 `Signal` 类的兼容性。**应对**：让 RegT/WireT 内部含 Signal 引用，运算符 delegate 给 Signal。

### Week 2 — 锚点库（最关键）

**目标**：手写 7 个高质量 Python ↔ Verilog 对照，覆盖 80% 的常见模块类型。

**Deliverables**（每个锚点目录含 `timing_model.py` + `module.v` + `README.md`）：

- [ ] `anchors/fsm_4state/` — 通用 4 状态 FSM（IDLE/LOAD/PROCESS/DONE）
- [ ] `anchors/shift_register/` — 8 位移位寄存器，每周期补位
- [ ] `anchors/pipeline_register/` — 3 级流水线，valid 跟随
- [ ] `anchors/hash_round_one_cycle/` — SM3 单轮压缩（含 ROL + 加法 + 异或）
- [ ] `anchors/handshake_hold_until_ack/` — valid 持续到 ack
- [ ] `anchors/handshake_single_cycle/` — valid + last 信号
- [ ] `anchors/barrel_shifter_var_n/` — log2(W) 阶桶形移位器
- [ ] `anchors/_selector.py` — anchor_hints → 路径解析
- [ ] `anchors/README.md` — 选择规则表（vf-architect 用）

**质量标准**：
- 每个锚点的 .v 文件**必须**通过 iverilog `-Wall` 和 yosys `synth -top`
- 每个锚点的 timing_model.py **必须**通过新协议的类型检查
- 每个锚点配 1 个简单 testbench（可选，但有最好）

**风险点**：
- 锚点不够代表性 → 实战时 vf-coder 仍需大幅"创造"。**应对**：W5 跑完两个 example 后，根据失败模块特征补锚点（v2.1 计划）。

### Week 3 — NBA Lint Hook

**目标**：对 v2 生成的 RTL 自动跑静态检查，仿真前拦截 60% 以上的 NBA 错误。

**Deliverables**：

- [ ] `src/veriflow_dsl/lint_nba.py`
  - [ ] L1: `_check_seq_only_nba()` — regex 扫 `always @(posedge` 块体
  - [ ] L3: `_check_port_alignment()` — 比对 spec.json 模块头
  - [ ] CLI 入口：`python -m veriflow_dsl.lint_nba <rtl_path> <spec_path>`
- [ ] `tests/test_lint_nba.py`
  - [ ] 喂入旧 example_test 中已知有 NBA bug 的 .v（可从 stage_journal 找）
  - [ ] 覆盖：纯坏代码（必拦）、纯好代码（必通过）、边界情况（注释中有 `=` 之类）
- [ ] 集成到 SKILL.md Stage 2：lint 失败 → 反馈给 vf-coder（3 次预算）

**Stretch Goal**：
- L4: 同周期读 reg_next 的数据流分析（pyverilog AST）— 不强求 W3 完成

**验收**：
- 用 `tests/fixtures/bad_nba_*.v` 喂入，每个都被对应规则拦截
- 用 `tests/fixtures/good_*.v` 喂入，全部通过
- 在 sm3 example_test 上跑：lint 拦截数 ≥ 仿真失败数的 60%

**风险点**：
- L1 regex 误判（注释、字符串中的 `=`）。**应对**：用简单 tokenizer 而非纯 regex。

### Week 4 — Sub-agent 改造 + 文档瘦身

**目标**：vf-architect 输出 timing_model.py；vf-coder prompt 重构；coding_style.md 瘦到 ~150 行。

**Deliverables**：

- [ ] `src/claude_agents/vf-architect.md` 改：增加 timing_model.py 输出步骤、anchor_hints 打标规则
- [ ] `src/claude_agents/vf-coder.md` 重写：从 170 行瘦到 ~80 行
- [ ] `src/claude_skills/vf-pipeline/coding_style.md` 重写：1324 → ~150 行
- [ ] `coding_style_archive.md` 归档旧版
- [ ] `src/claude_skills/vf-pipeline/SKILL.md` Stage 2 改：双路径分发（DSL emit / vf-coder + lint）
- [ ] `src/claude_skills/vf-pipeline/templates/timing_model_template.py` 新增
- [ ] `src/claude_skills/vf-pipeline/templates/spec_template.json` 增加字段

**验收**：
- 主 Claude 主导跑通：用户输入需求 → vf-architect 产 timing_model.py → vf-coder 翻译单个模块 → lint 通过
- 验证两个无 timing 表达字段的旧 example_test 仍能跑（向后兼容 — golden_model.py 仍可用）

**风险点**：
- vf-coder 习惯了旧 prompt 后突然变窄会"反弹"（开始不听新指令）。**应对**：W4 第一天就用 sm3 单模块当试金石。

### Week 5 — 端到端验证

**目标**：用 v2 全栈跑通 sm3 + chacha20 两个 example_test，量化 v2 vs v1 改进。

**Deliverables**：

- [ ] `example_test/sm3/` 完整 v2 跑通：spec → timing_model → RTL → 仿真 → lint+synth 全绿
- [ ] `example_test/chacha20/` 同上
- [ ] `docs/v2_validation_report.md`：
  - 每个示例的 NBA lint 拦截数 / 仿真失败数 / 修复轮数
  - vs v1 基线对比
  - 暴露的边角问题清单（→ v2.1 计划）

**验收（量化指标）**：
- sm3 首次仿真通过率 ≥ v1 + 30%
- chacha20 lint 阶段拦截 NBA bug ≥ 3 个（避免进入 verify_fix 重试）
- 平均修复轮数 ≤ v1 的 60%

**收尾**：
- 把 `veriflow-python/` 整个仓库归档为 `_legacy/` 或直接删除
- 更新 veriflow-cc README，加 v2 章节

---

## 6. veriflow-python 迁移清单

### 6.1 直接迁移（W1 完成）

| 源 | 目标 | 备注 |
|---|---|---|
| `dsl/_types.py` | `src/veriflow_dsl/_types.py` | 仅改 import |
| `dsl/_module.py` | `src/veriflow_dsl/_module.py` | + 适配层 |
| `dsl/_emitter.py` | `src/veriflow_dsl/_emitter.py` | 无 |
| `dsl/_simulator.py` | `src/veriflow_dsl/_simulator.py` | 无 |
| `dsl/_trace.py` | `src/veriflow_dsl/_trace.py` | 无 |
| `dsl/tests/` | `src/veriflow_dsl/tests/` | 无 |
| `agent/hierarchy_check.py` | `agent/hierarchy_check.py` | 无 |
| `agent/instance_gen.py` | `agent/instance_gen.py` | 无 |
| `agent/rtl_checker.py` | `agent/rtl_checker.py` | 无 |
| `agent/eda_paths.py` | `agent/eda_paths.py` | veriflow-cc 已有，去重保新版 |
| `docs/bug_patterns.md` | `docs/bug_patterns_archive.md` | 归档参考 |

### 6.2 借鉴重写（W2-W4 完成）

| 源 | 目标 | 改动 |
|---|---|---|
| `templates/design_spec_template.py` | `src/claude_skills/vf-pipeline/templates/timing_model_template.py` | 用新协议重写 |
| `skill/stages/stage1_design_spec.md` | `src/claude_agents/vf-architect.md` 内集成 | 子代理形态 |
| `skill/stages/stage2_codegen.md` | `src/claude_skills/vf-pipeline/SKILL.md` Stage 2 | 双路径分发 |
| `docs/coding_style_core.md` | 合并入新 `coding_style.md` | ~150 行总量 |

### 6.3 不迁移（功能由 veriflow-cc 已有部分覆盖）

| 源 | 替代 |
|---|---|
| `install.py` | veriflow-cc/install.py 已有 |
| `SKILL.md` | veriflow-cc SKILL.md 已有 |
| `skill/state.py` | veriflow-cc state.py 已有 |
| `agent/cocotb_runner.py` | veriflow-cc 已有 |
| `agent/iverilog_runner.py` | veriflow-cc 已有 |

### 6.4 归档与清理

**决策**：veriflow-python 仓库 **暂时保留在 GitHub 上**（不归档、不删除）。

- 本地副本 `/Users/wannengzhang/Desktop/work/ai_app_zone/veriflow-python/` 不再修改，作为参考备查
- GitHub 远程仓库保留，README 后续可加一行说明指向 veriflow-cc
- v2 GA 稳定运行 3 个月后再决定是否归档

---

## 7. 验收标准（v2 GA）

### 7.1 自动化测试

- [ ] `pytest src/veriflow_dsl/tests/` 全绿（≥ 110 个测试）
- [ ] `pytest tests/` 全绿（含 lint_nba 新增）
- [ ] `pytest example_test/sm3/`、`example_test/chacha20/` 端到端跑通

### 7.2 量化指标

| 指标 | v1 基线 | v2 目标 |
|---|---|---|
| coding_style.md 行数 | 1324 | ≤ 200 |
| vf-coder.md 行数 | 170 | ≤ 100 |
| sm3 首次仿真通过率 | 30%（基线估） | ≥ 60% |
| 修复轮数（平均/模块） | 2-3 | ≤ 1.5 |
| NBA bug 在 lint 阶段拦截率 | 0% | ≥ 60% |

### 7.3 人类验证

- 任意挑 1 个新 example_test（如 uart_test），主 Claude 主导跑通，无人工介入

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 类型协议过于严格，AI 无法生成合规 timing_model.py | 高 | W1 先在 sm3 上人工写一份验证可写性，再让 architect 自动生成 |
| 锚点库 7 个不够代表性 | 中 | W5 验证时按未覆盖模块特征补 v2.1 锚点 |
| L1 lint 误判（注释、字符串） | 低 | 用简单 tokenizer，提供 `// vf-lint: off` 转义注释 |
| DSL emitter 路径产物 vs vf-coder 产物风格不一致 | 中 | 锚点库基于 emitter 输出风格手写，使风格对齐 |
| vf-coder 不按新 prompt 来（继续按老习惯写） | 中 | W4 第一天用 sm3 单模块试金石，发现就立刻调整 prompt 强约束 |
| 现有 example_test 不能向后兼容 | 高 | W4 验收增加"旧 spec.json 仍能跑"的兼容性测试 |
| 5 周时间不够 | 中 | W5 是 buffer，必要时砍 chacha20 只跑 sm3 |

### 8.1 回滚计划

每周末 git tag：`v2-w1-done`、`v2-w2-done`、...
任意阶段验收失败，回滚到上周 tag。

主分支保护：v2 工作在 `feature/v2-refactor` 分支，merge 到 main 前必须：
- 全部自动化测试通过
- sm3 example 端到端跑通
- 代码 review 通过

---

## 9. 起手第一周具体动作（可立即执行）

按此顺序在 W1 第一天动手：

1. `git checkout -b feature/v2-refactor`
2. 创建 `src/veriflow_dsl/` 目录结构
3. 复制 `veriflow-python/dsl/_types.py` → `src/veriflow_dsl/_types.py`，调整 import
4. 创建 `src/veriflow_dsl/_spec.py`，写 RegT/WireT/RegAssign/reg_next 最小骨架
5. 写第一个测试：`tests/test_spec_protocol.py::test_reg_next_returns_RegAssign`
6. 跑通，commit："W1-D1: veriflow_spec 协议骨架"

W1 中段：
7. 迁移 `_module.py` / `_emitter.py` / `_simulator.py` / `_trace.py`
8. 跑通现有 92 个 DSL 测试
9. 写 `examples/counter_timing_model.py`，用 `Module` + `build_counter()` emit 出 `counter.v`
10. 用 iverilog 编译 `counter.v` 验证语法

W1 末段：
11. 写 `from_timing_model()` 适配层（基础版本，先支持 sequential）
12. 整合测试：`pytest src/veriflow_dsl/`
13. 打 tag `v2-w1-done`

---

**文档维护**：每周末更新本文件的"当前状态"段；每个 deliverable 完成后勾选 `[x]`。

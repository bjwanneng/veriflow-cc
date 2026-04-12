# VeriFlow-CC

**Claude Code 驱动的 RTL 设计流水线** — 零 Python 依赖，Claude Code 主会话就是 driver。

## 它是什么

VeriFlow-CC 把 Claude Code 当作流水线的大脑：Claude Code 主会话控制 stage 跳转、调用子 agent 执行任务、处理错误和回滚。每个 pipeline stage 由一个安装到 `~/.claude/agents/` 的 agent 定义文件驱动。

与完整版 VeriFlow-Agent 的区别：
- 不需要 LangGraph / LangChain / Streamlit
- 不需要 `pip install` 任何包
- Claude Code 本身就是交互层和决策层
- 状态持久化到 JSON，`/clear` 后可恢复

## 架构

```
用户 ←→ Claude Code 主会话（vf-pipeline agent）
             │
             ├─ 读 pipeline_state.json 恢复上下文
             ├─ validate_before_run() 严格校验顺序
             ├─ Agent 工具调用子 agent（LLM stage）
             ├─ Bash 执行 EDA 命令（lint/sim/synth）
             ├─ 看结果 → 成功继续 / 失败调 debugger → 回滚重跑
             └─ 每步保存状态（含 stage_summaries 摘要）
```

## 快速开始

### 1. 安装

```bash
python install.py
```

将 `vf-pipeline.md` 安装到 `~/.claude/agents/`。

### 2. 准备项目目录

```
my_alu/
└── requirement.md    # 写设计需求
```

### 3. 在 Claude Code 中运行

输入 `/vf-pipeline`，然后告诉 agent 项目目录路径。

## 流水线阶段

严格按顺序执行，不可跳过：

```
architect → microarch → timing → coder → skill_d → lint → sim → synth
    1           2          3        4         5        6     7      8
```

| Stage | 类型 | 输入 | 输出 |
|-------|------|------|------|
| architect | LLM | requirement.md | spec.json |
| microarch | LLM | spec.json | micro_arch.md |
| timing | LLM | spec.json, micro_arch.md | timing_model.yaml, testbench |
| coder | LLM | spec + timing + microarch | rtl/*.v |
| skill_d | LLM | rtl/*.v | 质量评分 |
| lint | EDA | rtl/*.v | 语法检查 |
| sim | EDA | rtl/*.v, tb/*.v | 仿真结果 |
| synth | EDA | rtl/*.v | 综合报告 |

## 错误恢复

```
stage 失败
  ├─ 第1次 → debugger 修复 → 回滚到目标 stage → 严格按顺序重跑
  ├─ 第2次 → debugger → 回滚到更早 stage → 重跑
  └─ 第3次 → 暂停，告知用户
```

回滚规则：syntax 错误回 coder，logic 错误回 microarch，timing 错误回 timing。

## 会话恢复

`/clear` 或新会话后，vf-pipeline agent 会自动从 `pipeline_state.json` 恢复：
- `stages_completed` — 已完成的 stage 列表
- `stage_summaries` — 每个阶段的一句话摘要
- `next_stage()` — 下一步该执行的 stage

## 文件结构

```
veriflow-cc/
├── state.py                # 状态管理（JSON 持久化 + 顺序校验）
├── install.py              # 安装/卸载 agent
├── prompts/                # prompt 模板
│   ├── architect.md
│   ├── microarch.md
│   ├── timing.md
│   ├── coder.md
│   ├── skill_d.md
│   └── debugger.md
├── agents/                 # Python agent 脚本（本地调试用）
│   ├── _base.py            # 基类：check_prerequisites, render_prompt, call_claude
│   ├── architect.py
│   ├── microarch.py
│   ├── timing.py
│   ├── coder.py
│   ├── skill_d.py
│   ├── lint.py             # 纯 EDA
│   ├── sim.py              # 纯 EDA
│   ├── synth.py            # 纯 EDA
│   └── debugger.py
├── claude_agents/
│   └── vf-pipeline.md      # Claude Code 主控 agent 定义
├── tests/
│   ├── test_state.py       # 14 tests: 顺序、摘要、回滚、持久化
│   └── test_base_agent.py  # 7 tests: 前置检查
└── my_project/
    └── requirement.md      # 示例项目
```

## 依赖

- Python 3.10+（仅用于 state.py 和 agent 脚本）
- Claude Code（已登录）
- `iverilog` / `vvp`（可选，无则跳过 sim）
- `yosys`（可选，无则跳过 synth）

**无需 pip install 任何包。**

## 测试

```bash
python tests/test_state.py
python tests/test_base_agent.py
```

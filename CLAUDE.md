# CLAUDE.md

## Project: VeriFlow-CC

Claude Code 驱动的 RTL 设计流水线。Claude Code 主会话是 driver，子 agent 执行各 stage。

## Mandatory: Plan Before Code

Before modifying any file, you MUST:

1. **Output a plan** — state what you are going to change, why, and which files are affected.
2. **Wait for approval** — do not start coding until the user confirms the plan.
3. **If the change is trivial** (typo, rename, single-line fix), a one-sentence plan is sufficient.

## Mandatory: TDD (Test-Driven Development)

All non-trivial changes must follow this cycle:

1. **Write a failing test first** — define the expected behavior before implementation.
2. **Show the test failing** — run it, confirm it fails for the right reason.
3. **Implement the minimum fix** — write only enough code to make the test pass.
4. **Show the test passing** — run it again, confirm green.
5. **Refactor if needed** — clean up while keeping tests green.

### Test location

- Tests go in `tests/` at the project root.
- One test file per source file: `tests/test_state.py` for `state.py`, etc.
- Use only `assert` and `subprocess` — no pytest dependency required, but pytest is fine if available.

### What to test

- **Happy path**: normal input produces expected output.
- **Edge cases**: empty input, missing files, boundary values.
- **Error cases**: invalid stage names, out-of-order execution, missing prerequisites.
- **State transitions**: `mark_complete` → `next_stage` → `mark_complete` sequence.

## Architecture Notes

- `state.py` — 状态机 + JSON 持久化。STAGE_ORDER 和 STAGE_PREREQUISITES 定义严格顺序。
- `agents/_base.py` — 基类。`check_prerequisites()` 在执行前检查输入文件，`run()` 自动调用。
- `claude_agents/vf-pipeline.md` — Claude Code agent 定义，安装到 `~/.claude/agents/`。
- LLM agent 结果中必须包含 `summary` 字段，用于会话恢复。

## File Hygiene

- Put temporary scripts and debug logs in `.claude/scratch/`.
- Never leave `print()` debugging statements in committed code.

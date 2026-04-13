# CLAUDE.md

## Project: VeriFlow-CC

Claude Code-driven RTL design pipeline. The main Claude Code session is the driver; sub-agents execute each stage.

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

- `state.py` — Pipeline state machine with JSON persistence. `STAGE_ORDER` and `STAGE_PREREQUISITES` enforce strict execution order.
- `.claude/skills/pipeline/SKILL.md` — Pipeline orchestration skill (project source), installed to `~/.claude/skills/pipeline/SKILL.md`. Invoked via `/pipeline <project_dir>`.
- `claude_agents/vf-*.md` — 9 sub-agent definitions (project source), installed to `~/.claude/agents/`.
- `install.py` — Installs 1 skill + 9 agents to `~/.claude/`.
- Pipeline flow: Main Claude (skill) → Agent(vf-architect) → Bash Hook verification → next stage.
- 1-layer nesting: Main Claude calls sub-agents directly, no intermediate pipeline agent.
- LLM agent results must include a `summary` field for session recovery.

## File Hygiene

- Put temporary scripts and debug logs in `.claude/scratch/`.
- Never leave `print()` debugging statements in committed code.

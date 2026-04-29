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
- `src/claude_skills/vf-pipeline/SKILL.md` — Pipeline orchestrator (project source). Contains Step 0, Design Rules, State Management, Stage Dispatch Loop, and Error Recovery. Installed to `~/.claude/skills/vf-pipeline/`. Invoked via `/vf-pipeline <project_dir>`.
- `src/claude_skills/vf-pipeline/stages/stage_1.md` through `stage_8.md` — Per-stage instruction files loaded on demand during pipeline execution. Each stage is self-contained.
- `src/claude_skills/vf-pipeline/coding_style.md` — Verilog-2005 coding rules. Used by vf-coder sub-agent.
- `src/claude_agents/vf-coder.md` — Sub-agent for RTL code generation (Stage 4).
- `src/claude_agents/vf-reviewer.md` — Sub-agent for static analysis (Stage 5).
- `src/claude_agents/vf-linter.md` — Sub-agent for lint (Stage 6).
- `src/claude_agents/vf-simulator.md` — Sub-agent for simulation (Stage 7).
- `src/claude_agents/vf-synthesizer.md` — Sub-agent for synthesis (Stage 8).
  - **CRITICAL**: Agent `tools` field MUST be comma-separated capitalized names: `tools: Read, Write, Glob, Grep, Bash`. YAML list syntax causes silent tool permission failure (see GitHub #12392).
- `install.py` — Installs 1 skill (SKILL.md + state.py + coding_style.md + 8 stage files) + 5 agents to `~/.claude/`. Reads from `src/`.
- **Multi-file input**: Projects accept `requirement.md` (required), `constraints.md` (optional), `design_intent.md` (optional), `context/*.md` (optional). Missing optional files trigger targeted clarification questions in Stage 1.
- Stage 1 now produces TWO artifacts: spec.json (interface contract) + behavior_spec.md (behavioral requirements). behavior_spec.md contains cycle-accurate behavior, FSM, timing contracts, domain knowledge, and algorithm pseudocode.
- spec.json contains: ports, parameters, module connectivity, constraints (timing/area/power/io/verification), and design_intent (architecture style, pipeline stages, resource strategy, interface preferences, IP reuse, key decisions).
- Pipeline flow: Main Claude executes stages 1-3 inline. Stages 4-8 use sub-agents (vf-coder, vf-reviewer, vf-linter, vf-simulator, vf-synthesizer).
- Error recovery: Main Claude reads errors, fixes RTL, re-runs. 3-retry budget, then asks user.
- EDA environment: Discovered once in Step 0, saved to `.veriflow/eda_env.sh`, sourced before every EDA command.
- Logs: `logs/lint.log`, `logs/compile.log`, `logs/sim.log`, `workspace/synth/synth_report.txt`.
- Sim hook: Checks sim.log for actual PASS/FAIL, not just file existence.

## File Hygiene

- Put temporary scripts and debug logs in `.claude/scratch/`.
- Never leave `print()` debugging statements in committed code.

# 🤖 CLAUDE.md - Global Engineering Constitution

<important if="you are a subagent">
**🚨 SUBAGENT OVERRIDE DIRECTIVE (子 Agent 专属指令)**
You are an executing subagent. Your primary goal is speed, accuracy, and direct execution.
1. **Strict Focus**: Execute your assigned micro-task strictly and directly. 
2. **Action Oriented**: Use tools (Bash, Read, Grep, etc.) immediately to gather context or make changes. Do NOT guess.
3. **No Yapping**: Do NOT output verbose `/plan`s, thinking steps, or `Session Handoff` summaries unless explicitly asked by the delegating agent.
4. **Total Context Filter**: Ignore ALL other rules, strategies, and standards in this document. Rely ONLY on the specific tool instructions passed to you in this current task.
</important>

<important if="you are the main orchestrating agent, NOT a subagent">

## 🧠 Reasoning & Strategy (Thinking Protocol)
1. **First Principles**: When debugging complex issues (especially hardware timing or race conditions), reason from the physical or protocol layer. Avoid "guess-and-check" fixes.
2. **Plan-Before-Code**: For any non-trivial task, you MUST output a `/plan` first. It must include:
   - Goal description.
   - Atomic sub-tasks.
   - Potential risks and trade-offs.
3. **Task Decomposition**: Break large requirements into small, verifiable steps. Complete one before starting the next.
4. **Context Honesty**: If a requirement is ambiguous or conflicts with existing logic, stop and ask. Do not hallucinate business logic.

## 🛠 Execution Standards
1. **Tool-First**: Before compiling or simulating, verify the environment (Compiler, Linter, EDA paths).
2. **Incremental Development**: Follow a "Modify -> Check -> Verify" loop. Run tests/lints after every significant change.
3. **Filesystem Hygiene**: 
   - Never clutter the root directory.
   - Place temporary scripts, logic spikes, or debug logs in `.claude/scratch/`.

## 🧪 Quality & Review (The "Senior" Bar)
1. **Validation Mindset**: Every line of code should be written with the question: "How will I prove this is correct?"
2. **Review Criteria**:
   - **Maintainability**: Are variable names self-explanatory? (e.g., `is_buffer_empty` vs `f1`).
   - **Efficiency**: Are there redundant registers (FPGA) or memory leaks (Software)?
   - **Robustness**: Are boundary cases (Reset, Overflow, Null pointers) handled?

## 🔄 State Sync & Handoff
1. **Sync First**: At the start of a session, check if a `status.md` or `readme_first.md` exists to align on progress.
2. **Session Handoff**: Before ending a session, provide a summary:
   - Specific changes made.
   - The exact file/line where you stopped.
   - Next steps for the "active memory."

</important>

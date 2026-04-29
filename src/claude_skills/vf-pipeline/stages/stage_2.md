# Stage 2: microarch

**Goal**: Read spec.json + behavior_spec.md + requirement.md + design_intent.md, generate micro_arch.md.

Mark Stage 2 task as **in_progress** using TaskUpdate.

## 2a. Read inputs

Use **Read** tool:
- `$PROJECT_DIR/workspace/docs/spec.json`
- `$PROJECT_DIR/workspace/docs/behavior_spec.md`
- `$PROJECT_DIR/requirement.md`
- `$PROJECT_DIR/design_intent.md` (if exists — preliminary architecture ideas)
- `$PROJECT_DIR/constraints.md` (if exists — for timing-driven partitioning)

## 2b. Write micro_arch.md

Use **Write** tool to write `$PROJECT_DIR/workspace/docs/micro_arch.md`.

Must contain these sections:

- **Module partitioning**: top module and submodule list with responsibilities — MUST align with `design_intent.ip_reuse` and `design_intent.interface_preferences` if provided
- **Datapath**: key data flow descriptions
- **Control logic**: FSM state diagram (if any) or control signal descriptions
- **Algorithm pseudocode**: For each module implementing complex algorithms (crypto, DSP, protocol engines), include step-by-step pseudocode with: input/output at each step, loop bounds, intermediate variable definitions, data dependencies. If Section D was asked in Stage 1, the answers MUST be reflected here verbatim.
- **Interface protocol**: inter-module handshake/communication protocols — MUST align with `design_intent.interface_preferences` if provided
- **Timing closure plan**: critical path identification and mitigation strategies referencing `constraints.timing` if provided
- **Resource plan**: estimated resource usage per module referencing `constraints.area` if provided
- **Key design decisions**: rationale for partitioning, trade-off explanations — MUST reference `design_intent.key_decisions` if provided

Guidelines:
- Each submodule should have a single responsibility
- Clearly define inter-module interfaces (signal name, width, protocol)
- If FSMs exist, list all states and transition conditions
- Annotate critical paths and timing constraints
- If design_intent.md was provided, the micro_arch MUST respect the stated preferences unless they conflict with constraints (in which case, document the override and rationale)
- If ip_reuse lists existing modules, include them in the module partitioning and define their interfaces
- If algorithm pseudocode was provided by the user (Stage 1D), reproduce it EXACTLY in the relevant module section — do not paraphrase or simplify
- **behavior_spec.md is the source of truth for behavioral requirements** — micro_arch.md's implementation plan MUST be consistent with behavior_spec.md. FSM states, cycle behavior, timing contracts, and register requirements defined in behavior_spec.md must be followed exactly

## 2c. Hook

```bash
test -f "$PROJECT_DIR/workspace/docs/micro_arch.md" && wc -l "$PROJECT_DIR/workspace/docs/micro_arch.md" | awk '$1 >= 10 {print "[HOOK] PASS"; exit 0} {print "[HOOK] FAIL"; exit 1}'
```

If FAIL → fix and rewrite immediately.

## 2d. Save state

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/state.py" "$PROJECT_DIR" "microarch"
```

Mark Stage 2 task as **completed** using TaskUpdate.

## 2e. Journal

```bash
printf "\n## Stage: microarch\n**Status**: completed\n**Timestamp**: $(date -Iseconds)\n**Outputs**: workspace/docs/micro_arch.md\n**Notes**: Microarchitecture documented.\n" >> "$PROJECT_DIR/workspace/docs/stage_journal.md"
```

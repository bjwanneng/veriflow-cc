# Stage 2: codegen - execution detail

Loaded by SKILL.md when entering Stage 2. Full execution bash; SKILL.md holds the compact dispatch entry.

---

## Stage 2: codegen

**Stage timing** — record start (before any stage work, so `duration_s` is captured):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "codegen" --start
```

Read spec.json, golden_model.py, and coding_style.md (parallel Read calls) to include inline in prompts.

**Multi-candidate dispatch**: All modules go through AI Assembly (vf-coder).
By default **K=3 candidates per module** are generated and the best is selected by
`candidate_selector.py` (passing + fewest cells) — set
`spec.constraints.verification.candidate_count: 1` to disable (legacy single-path).

### AI Assembly

- **One vf-coder per module** in spec.json (subagent_type: vf-coder)
  - Prompt includes: MODULE_NAME, OUTPUT_FILE path, **PROJECT_DIR** (needed for
    the completion-marker bash), **GOLDEN_MODEL_PATH** (absolute path to the
    full golden_model.py — vf-coder runs it to cross-check the trace; see
    vf-coder.md Step 1.5 and self-check #6)
  - `GOLDEN_MODEL`: the relevant Python functions from golden_model.py that
    describe this module's behavior. The orchestrator extracts these by matching
    the module name against function names/classes in golden_model.py. Include
    the full Python implementation — vf-coder translates it into Verilog.
  - `MODULE_SPEC`: this module's ports/parameters/timing_contract from spec.json
  - `TIMING_TABLE`: main session builds a cycle-accurate timing table from
    spec.json `cycle_timing` and `timing_contract`, showing:
    - Registered outputs (use `output wire` + `reg` + `assign`)
    - Combinational outputs (use `output wire` + `assign` directly)
    - Pipeline stages and latency
  - `WEB_RESEARCH`: content from `.veriflow/web_research.md` — **only if the file
    has substantive content** (more than just "skipped" or "unavailable"). If
    minimal, omit this field entirely to save prompt tokens.
  - `REFERENCES` (optional): type-matched reference Verilog from the reference
    KB. Build it before dispatching vf-coder:
    ```bash
    REFS_JSON=$($PYTHON_EXE "${CLAUDE_SKILL_DIR}/kb/reference_kb.py" \
        --spec workspace/docs/spec.json --module "$MODULE_NAME" 2>/dev/null || echo "")
    ```
    Parse `references[].code` and include as structural idioms (not to copy).
    Omit the field if retrieval returns nothing.
  - `PREV_FAILURE` (only on Stage 3 retry — see Stage 3 step 5b): a
    **prescriptive** fix directive containing ROOT CAUSE + concrete FIX steps
    (file, line, exact change). When present, vf-coder MUST execute the fix
    directly — no analysis, no exploring alternatives. See vf-coder.md for rules.
  - Condensed coding_style.md content
  - For top modules: include submodule port definitions from spec.json

### TB Generation + All Agent Dispatch

Dispatch ALL agents in parallel (single message):

- **K vf-coder agents per module** — K from `spec.constraints.verification.candidate_count`
  (default **3**; set to `1` for the legacy single-path behavior). Each candidate
  writes to `workspace/rtl/.candidates/<module>_cand{i}.v` (i = 0..K-1) with
  `OUTPUT_FILE` set accordingly; vary the microarchitecture emphasis per candidate
  (e.g. cand0: area-minimal, cand1: balanced, cand2: timing-relaxed) so the
  selector has real diversity to choose from. Falls back to K=1 if cocotb is
  unavailable (selection needs sim).
- **One vf-tb-gen** (subagent_type: vf-tb-gen)
  - Prompt includes: PROJECT_DIR, DESIGN_NAME, spec.json content, golden_model.py content, COCOTB_AVAILABLE flag, `${CLAUDE_SKILL_DIR}/templates` path
  - **DRIVE_PHASE_CYCLES**: Read from `spec.json timing_convention.golden_to_rtl_offset_cycles`. If not set, fall back to `max(pipeline_delay_cycles)` from timing_contract.
  - **RESET_CYCLE_SKIP**: Read from `spec.json timing_convention.reset_cycle_skip` (default 1). This is the golden cycle index where post-reset comparison begins (cycle 0 is the reset state). Set it in the generated `test_<module>.py` (`RESET_CYCLE_SKIP = ...`); if omitted, the template falls back to the spec value at import time.
  - **CRITICAL**: The Verilog testbench MUST respect input hold time derived from spec.json `module_connectivity` timing_contract. Data inputs MUST remain stable for at least `DRIVE_PHASE_CYCLES + 1` cycles after the valid pulse.

After ALL return, verify outputs exist:
```bash
ls "$PROJECT_DIR/workspace/rtl/"*.v "$PROJECT_DIR/workspace/tb/"*.v "$PROJECT_DIR/workspace/tb/"*.py 2>/dev/null
```

### Candidate selection (only if K > 1)

For each module that has candidates under `workspace/rtl/.candidates/`, run the
selector — it sims each candidate against the golden cocotb TB and scores
synthesis quality (fewest cells wins among those that pass):
```bash
cd "$PROJECT_DIR"
CAND_K=$($PYTHON_EXE -c "
import json
s = json.load(open('workspace/docs/spec.json'))
print(s.get('constraints',{}).get('verification',{}).get('candidate_count', 3))
")
if [ "${CAND_K:-3}" -gt 1 ] && ls workspace/rtl/.candidates/*_cand*.v >/dev/null 2>&1; then
    for M in $(ls workspace/rtl/.candidates/ 2>/dev/null | sed -E 's/_cand[0-9]+\.v//' | sort -u); do
        $PYTHON_EXE "${CLAUDE_SKILL_DIR}/verify/candidate_selector.py" \
            --module "$M" \
            --candidates-dir workspace/rtl/.candidates \
            --tb-dir workspace/tb \
            --rtl-out workspace/rtl \
            --build-dir workspace/sim_cand 2>&1 | tee -a logs/candidate_select.log
    done
fi
```
If no candidate passes, the fewest-fails one is kept so Stage 3 can still try to fix it.

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "codegen" --hook='{"all":[{"glob":"workspace/rtl/*.v","min":1},{"any":[{"glob":"workspace/tb/test_*.py","min":1},{"glob":"workspace/tb/tb_*.v","min":1}]}]}' --journal-outputs="workspace/rtl/*.v, workspace/tb/test_*.py, workspace/tb/tb_*.v" --journal-notes="RTL and testbench generated in parallel"
```
TaskUpdate complete.

---


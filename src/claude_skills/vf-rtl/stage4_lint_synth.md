# Stage 4: lint_synth - execution detail

Loaded by SKILL.md when entering Stage 4. Full execution bash; SKILL.md holds the compact dispatch entry.

---

## Stage 4: lint_synth

**Stage timing** — record start (before any stage work, so `duration_s` is captured):
```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "lint_synth" --start
```

Dispatch 2 parallel agents (single message):

- **vf-linter** (subagent_type: vf-linter) — include PROJECT_DIR, EDA_ENV path, PYTHON_EXE, SKILL_DIR
- **vf-synthesizer** (subagent_type: vf-synthesizer) — include PROJECT_DIR, SPEC path, EDA_ENV path, PYTHON_EXE, SKILL_DIR

After BOTH return:

If lint failed → fix syntax errors in main session, re-run lint only.
If synth failed → check report, fix if needed.

```bash
$PYTHON_EXE "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "lint_synth" --hook='{"all":[{"exists":"logs/lint.log"},{"exists":"workspace/synth/synth_report.txt"}]}' --journal-outputs="logs/lint.log, workspace/synth/synth_report.txt" --journal-notes="Lint and synthesis complete"
```

### Formal Equivalence Check (post-synthesis)

If synthesis produced a netlist and yosys is available, run a lightweight
formal equivalence check between the original RTL and the synthesized netlist.

**This is now a HARD gate.** If equivalence is NOT proved, the pipeline
marks lint_synth as FAILED and enters error recovery.

```bash
TOP_MODULE=$("$PYTHON_EXE" -c "
import json
for m in json.load(open('workspace/docs/spec.json')).get('modules', []):
    if m.get('module_type') == 'top': print(m['module_name']); break
")
SYNTH_V="workspace/synth/${TOP_MODULE}_synth.v"
EQUIV="SKIP"
if [ -f "$SYNTH_V" ] && command -v yosys &>/dev/null; then
    # yosys_equiv accepts exactly ONE --ref file. coding_style.md mandates one
    # module per file, so a hierarchical design's top file references undefined
    # submodules → prep -top errors and the HARD gate false-fails. Concatenate
    # every leaf module first, then the top module last, into a combined ref.
    RTL_REF="workspace/synth/rtl_ref_combined.v"
    : > "$RTL_REF"
    for _f in workspace/rtl/*.v; do
        [ -f "$_f" ] || continue
        [ "$_f" = "workspace/rtl/${TOP_MODULE}.v" ] && continue
        cat "$_f" >> "$RTL_REF"
    done
    # top module last (if its file exists)
    [ -f "workspace/rtl/${TOP_MODULE}.v" ] && cat "workspace/rtl/${TOP_MODULE}.v" >> "$RTL_REF"
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/runners/yosys_equiv.py" \
        --ref "$RTL_REF" \
        --impl "$SYNTH_V" \
        --top "$TOP_MODULE" \
        --json > logs/yosys_equiv_synth.json 2>&1
    EQUIV=$("$PYTHON_EXE" -c "
import json, pathlib
p = pathlib.Path('logs/yosys_equiv_synth.json')
if p.exists():
    d = json.loads(p.read_text())
    print('PASS' if d.get('equivalent') else 'FAIL')
else:
    print('SKIP')
")
    echo "[EQUIV] Synthesis equivalence check: $EQUIV"
    if [ "$EQUIV" = "FAIL" ]; then
        echo "[FAIL] Synthesized netlist is NOT equivalent to original RTL."
        echo "[FAIL] Unproven signals:"
        "$PYTHON_EXE" -c "
import json
with open('logs/yosys_equiv_synth.json') as f:
    d = json.load(f)
    for sig in d.get('unproven', []):
        print(f'  {sig}')
"
        # Mark stage as failed and abort pipeline
        "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" "lint_synth" \
            --fail --error-sig="equiv_check_failed"
        exit 1
    fi
else
    echo "[EQUIV] Skipped (yosys or netlist not available)"
fi
```

### Formal Property Proving (post-synthesis)

Prove spec-derived invariants (handshake valid-stability, etc.) with
SymbiYosys. This is **report-only** in v1: a FAIL with a counterexample is
surfaced for review, not a hard gate. Generates the property file even if sby
is unavailable (useful artifact). Skips cleanly when sby is absent.
```bash
if command -v sby &>/dev/null; then
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/verify/formal_prove.py" \
        --spec workspace/docs/spec.json \
        --module "$TOP_MODULE" \
        --rtl-dir workspace/rtl \
        --output "workspace/docs/${TOP_MODULE}_formal.v" \
        --prove --timeout 120 > logs/formal.json 2> logs/formal.log
    FORMAL=$("$PYTHON_EXE" -c "
import json, pathlib
p = pathlib.Path('logs/formal.json')
d = json.loads(p.read_text()) if p.exists() else {}
print(d.get('status') or 'SKIP')
")
    echo "[FORMAL] Property proving: $FORMAL"
    if [ "$FORMAL" = "FAIL" ]; then
        echo "[FORMAL] CEX found — review logs/formal.log (report-only, not a hard gate in v1)."
    fi
else
    # Still generate the property file as an artifact (no prove).
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/verify/formal_prove.py" \
        --spec workspace/docs/spec.json --module "$TOP_MODULE" \
        --rtl-dir workspace/rtl \
        --output "workspace/docs/${TOP_MODULE}_formal.v" 2>/dev/null || true
    echo "[FORMAL] Skipped (sby not available) — property file generated."
fi
```

### Knowledge Base Auto-Record (post-success)

After a successful pipeline run, record outcomes to the cross-project
knowledge base for future pattern learning:

```bash
# Record project outcome if pipeline completed successfully
if "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/core/state.py" "$PROJECT_DIR" lint_synth --check-loop=dummy 2>/dev/null; then
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/kb/knowledge_base.py" \
        --record-fix logs/timing_diagnostic.json \
        --project "$(basename $PROJECT_DIR)" \
        --fix-attempts "$(cat .veriflow/pipeline_state.json | $PYTHON_EXE -c 'import sys,json;print(sum(json.load(sys.stdin).get(\"retry_count\",{}).values()))')" 2>/dev/null || true

    # Self-improvement: append structured per-module observations (runs.jsonl)
    # for offline mining. Best-effort, append-only, never blocks the pipeline.
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/kb/self_improve.py" record --project-dir "$PROJECT_DIR" \
        >> logs/self_improve.log 2>&1 || true
fi
```

TaskUpdate complete. Pipeline done.

### Optional: Benchmark report (if --benchmark flag was passed)

If the user invoked `/vf-rtl` with `--benchmark`, generate an evaluation report:

```bash
if [ -n "$RUN_BENCHMARK" ]; then
    "$PYTHON_EXE" "${CLAUDE_SKILL_DIR}/runners/benchmark_runner.py" \
        --project "$PROJECT_DIR" \
        --output "logs/benchmark_report.json" \
        --markdown
    echo "[BENCHMARK] Report saved to logs/benchmark_report.json"
fi
```

---


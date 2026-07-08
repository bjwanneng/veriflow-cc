# SKILL_INDEX.md — VeriFlow-CC Navigation Map

Quick-reference map from **pipeline role** to the **tool/agent/file** that owns it.
All paths are relative to the skill root (`~/.claude/skills/vf-rtl/` in production,
`src/claude_skills/vf-rtl/` in source). Use this to find the right artifact fast
without grepping SKILL.md.

## Layout at a glance

| Subdir      | Holds                                                                 |
|-------------|-----------------------------------------------------------------------|
| `core/`     | `state.py` (state machine), `rtl_utils.py` (shared helpers), `init.py` (env bootstrap) |
| `runners/`  | simulators + equivalence + benchmark (`cocotb_runner`, `iverilog_runner`, `yosys_equiv`, `benchmark_runner`) |
| `analysis/` | VCD/timing/coverage/graph/pattern tools (`vcd2table`, `timing_diagnostic`, `timing_contract_checker`, `design_graph`, `coverage_analyzer`, `bug_pattern_match`, `corner_case_generator`, `expected_trace_gen`) |
| `verify/`   | candidate selection + scoring + formal (`candidate_selector`, `synth_score`, `formal_prove`) |
| `kb/`       | cross-run learning (`knowledge_base`, `reference_kb`, `self_improve`) |
| `templates/`| spec / golden_model / tb / cocotb templates (data, loaded on demand)   |
| `references/`| curated reference RTL snippets (data, for `reference_kb.py`)          |
| *(root)*    | `SKILL.md` (orchestrator), `coding_style.md`, `error_recovery.md`, `design_rules.md`, `bug_patterns.md`, `SELF_IMPROVE.md` |

## By pipeline stage

### Stage 1 — `spec_golden`
| Role | Artifact | Notes |
|------|----------|-------|
| Spec + golden model generation | agent `vf-spec-golden.md` | Produces `workspace/docs/spec.json` + `golden_model.py` |
| Env + workspace bootstrap | `core/init.py` | Discovers EDA tools, writes `.veriflow/eda_env.sh` (exports `PYTHONPATH` = root + all subdirs) |
| Templates | `templates/spec_template.json`, `templates/golden_model_template.py` | Loaded on demand |

### Stage 2 — `codegen`
| Role | Artifact | Notes |
|------|----------|-------|
| RTL code generation | agent `vf-coder.md` | Per-module, parallel |
| Coding rules | `coding_style.md` | Verilog-2005 constraints |
| Reference RTL retrieval | `kb/reference_kb.py` + `references/` | Type-matched structural examples for vf-coder |
| Multi-candidate selection | `verify/candidate_selector.py` | Generate-K-then-select; calls `runners/cocotb_runner.py` + `verify/synth_score.py` |

### Stage 2 → 3 handoff
| Role | Artifact | Notes |
|------|----------|-------|
| Testbench generation | agent `vf-tb-gen.md` | Cocotb + Verilog TBs |
| Corner-case vectors | `analysis/corner_case_generator.py` | 8 boundary vectors from spec ports |
| Templates | `templates/cocotb_template.py`, `templates/tb_integration_template.v` | |

### Stage 3 — `verify_fix` (inline, main session)
| Role | Artifact | Notes |
|------|----------|-------|
| Cocotb simulation | `runners/cocotb_runner.py` | Imports `rtl_utils` (core/), `timing_diagnostic` + `bug_pattern_match` (analysis/) |
| Pure-Verilog simulation | `runners/iverilog_runner.py` | Fallback / second run |
| Expected-trace table | `analysis/expected_trace_gen.py` | Per-cycle golden register values |
| VCD → cycle table | `analysis/vcd2table.py` | Waveform diff |
| Timing diagnosis | `analysis/timing_diagnostic.py` | Classifies bug (A/B/D) + fix hints |
| Bug-pattern match | `analysis/bug_pattern_match.py` | Matches divergence signature to catalog (`bug_patterns.md`) |
| Timing-contract check | `analysis/timing_contract_checker.py` | spec.json timing contracts |
| Error recovery loop | `error_recovery.md` | 3-retry budget, reads errors, fixes RTL |
| State transitions | `core/state.py` | `mark_complete` / `next_stage` / `--reset` |

### Stage 4 — `lint_synth` (parallel)
| Role | Artifact | Notes |
|------|----------|-------|
| Lint | agent `vf-linter.md` | iverilog syntax check |
| Synthesis | agent `vf-synthesizer.md` | yosys synthesis report |
| Equivalence proof | `runners/yosys_equiv.py` | SAT-based equiv (hard gate: abort on mismatch) |
| Synth-quality scoring | `verify/synth_score.py` | cells/FFs/MUX from yosys report |
| Formal properties | `verify/formal_prove.py` | SymbiYosys generate + prove |
| Functional coverage | `analysis/coverage_analyzer.py` | coverage-driven verification |
| Connectivity graph | `analysis/design_graph.py` | module_connectivity DAG validation |

### Cross-cutting
| Role | Artifact | Notes |
|------|----------|-------|
| Shared helpers | `core/rtl_utils.py` | golden-trace loader, `collect_rtl_sources`, `find_executable`, etc. |
| Cross-project KB | `kb/knowledge_base.py` | bug-pattern frequencies, templates, outcomes (`~/.claude/skills/vf-rtl/knowledge/`) |
| Self-improvement | `kb/self_improve.py` | observe → stage → validate → promote (gated, reversible) |
| Batch benchmark | `runners/benchmark_runner.py` | variant comparison, RealBench JSONL, reports |

## Import resolution contract

Scripts that are **subprocessed** (cocotb_runner, iverilog_runner, expected_trace_gen,
timing_diagnostic, candidate_selector, self_improve) carry a marker-walk bootstrap:
they locate the skill root by walking up to `SKILL.md`, then put the root + every
subdir on `sys.path`. So bare imports (`from rtl_utils import ...`,
`from synth_score import ...`) resolve whether the script runs under pytest,
via `eda_env.sh`, or directly with no `PYTHONPATH` set.

`core/init.py` writes the same root + every subdir into the `PYTHONPATH` export of
`eda_env.sh`, so any shell command that sources it gets the same resolution for free.

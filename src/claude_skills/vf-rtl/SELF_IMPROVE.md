# Self-Improvement Loop

`self_improve.py` lets VeriFlow-CC learn from its own runs **safely**: it is an
**offline, measurable, reversible** loop, NOT a live self-modifying system.

```
Observe → Stage → Validate → Promote (gated) → Measure (rollback)
                                                   │
                          benchmark_runner.pass_rate is the referee
```

The non-negotiable rule: **no learned artifact ever reaches the hot path
silently.** Every promotion is gated, logged, and reversible.

## State

All under `~/.claude/skills/vf-rtl/knowledge/`:

| Path | Meaning |
|------|---------|
| `runs.jsonl` | Append-only per-module observations (written by `record`) |
| `run_artifacts/*.v` | Snapshotted passing-first-try RTL |
| `staging/{reference,pattern}/*.json` | Candidates with a `validation` field |
| `promotion_log.jsonl` | Append-only promotion records (for rollback) |
| `promotion_requests/*.json` | Dry-run proposals |

`record` runs automatically at the end of every successful pipeline run (Stage 4).
The rest are **operator-run, offline**.

## Operator runbook

```bash
SI="python3 ~/.claude/skills/vf-rtl/self_improve.py"

# 1. See what's accumulated
$SI status

# 2. Mine candidates from accumulated runs (writes staging/, never the hot path)
$SI mine

# 3. Validate them (references must synthesize; patterns checked for form)
$SI validate

# 4a. REVIEW the dry-run first (default — touches nothing):
$SI promote

# 4b. Promote ONE candidate you've reviewed (human-approved):
$SI promote --apply <candidate_id>

# 4c. Or auto-promote all validated — ONLY with a benchmark gate configured:
export VF_BENCHMARK_CMD="python3 ~/.claude/skills/vf-rtl/benchmark_runner.py \
    --all-projects <your_benchmark_root> --output /tmp/bench.json"
$SI promote --auto     # refuses if VF_BENCHMARK_CMD unset; rolls back on regression

# 5. Undo a promotion
$SI rollback --promotion-id <id>
```

For the **first N** promotions, prefer `--apply` (human review). Move to
`--auto` only once a frozen benchmark set is wired and you trust the gate.

## The five guardrails (why this is safe)

1. **"Passed sim" ≠ "correct".** A golden-model bug is copied faithfully and the
   TB still passes. So reference candidates are gated on **coverage ≥ 0.9**, and
   the goal is to also tie them to the formal prover. Never promote on sim-pass
   alone.
2. **Compounding corruption.** One bad reference poisons every future generation
   of that type. Mitigations: each candidate is independently validated;
   `--auto` requires benchmark non-regression; everything is reversible.
3. **Measurability.** "We improved" is only real against a **frozen** benchmark.
   `benchmark_runner.pass_rate` is the referee. Don't let the learned artifacts
   contaminate the benchmark set itself.
4. **Determinism → pass@k.** LLM runs are noisy; a single before/after is not
   evidence. For high-stakes auto-promotion, run the benchmark multiple times
   and require a statistically real delta (v2).
5. **No RL.** ChipSeek-R1-style weight updates need training infra + a model you
   can fine-tune — VeriFlow drives a hosted model. The transferable idea is the
   **multi-objective reward** (functional + synth + coverage), already used for
   candidate *selection*, not weight updates.

## What v1 learns (and what it deliberately does NOT)

- **Learns**: (a) reference implementations (passing-first-try modules →
  `references/<type>_learned_*.v`, retrievable by `reference_kb`); (b) bug-pattern
  documentation entries appended to `bug_patterns.md` for recurring signatures.
- **Does NOT** auto-generate matcher code (patterns are code in
  `bug_pattern_match.py`; injecting LLM-written matchers is unsafe — a promoted
  pattern is advisory docs + a signature spec until a human adds the matcher).
- **Deferred**: prompt/rule self-tuning (largest blast radius).

"""Pipeline state management - zero external dependencies."""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# Strict execution order — no stage may be skipped
STAGE_ORDER = ["architect", "microarch", "timing", "coder", "skill_d", "lint", "sim", "synth"]

# Prerequisite stages that must all complete before a given stage can run
STAGE_PREREQUISITES = {
    "architect": [],                                          # no prerequisites
    "microarch": ["architect"],                               # needs spec.json
    "timing":    ["architect", "microarch"],                  # needs spec + micro_arch
    "coder":     ["architect", "microarch", "timing"],        # needs spec + microarch + timing
    "skill_d":   ["coder"],                                   # needs RTL code
    "lint":      ["coder"],                                   # needs RTL code
    "sim":       ["coder", "lint"],                           # needs RTL + lint pass
    "synth":     ["coder", "sim"],                            # needs RTL + sim pass
}


def next_pending_stage(stages_completed: list) -> str | None:
    """Return the first stage not yet completed. Strict STAGE_ORDER, no skipping."""
    for stage in STAGE_ORDER:
        if stage not in stages_completed:
            return stage
    return None  # all complete


def can_execute(stage: str, stages_completed: list) -> tuple[bool, str]:
    """Check whether a stage can execute (all prerequisites met).

    Returns:
        (can_run, reason) — can_run=True means OK to execute
    """
    prereqs = STAGE_PREREQUISITES.get(stage, [])
    missing = [p for p in prereqs if p not in stages_completed]
    if missing:
        return False, f"Prerequisite stages not completed: {missing}"
    return True, ""


@dataclass
class PipelineState:
    """Pipeline state - serializable to JSON, driven by Claude Code main session."""

    project_dir: str

    current_stage: str = ""
    stages_completed: list = field(default_factory=list)
    stages_failed: list = field(default_factory=list)

    # Per-stage output summaries
    architect_output: Optional[dict] = None
    microarch_output: Optional[dict] = None
    timing_output: Optional[dict] = None
    coder_output: Optional[dict] = None
    skill_d_output: Optional[dict] = None
    lint_output: Optional[dict] = None
    sim_output: Optional[dict] = None
    synth_output: Optional[dict] = None

    # Error recovery
    retry_count: dict = field(default_factory=dict)
    error_history: dict = field(default_factory=dict)
    feedback_source: str = ""
    max_retries_per_stage: int = 3

    # Persistent context summary — new sessions read this field to recover state
    stage_summaries: dict = field(default_factory=dict)

    # Metadata
    start_time: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def __post_init__(self):
        if isinstance(self.project_dir, Path):
            self.project_dir = str(self.project_dir)

    def mark_complete(self, stage: str, result: dict):
        """Mark a stage as complete. Saves summary for context recovery."""
        if stage in STAGE_PREREQUISITES:
            ok, reason = can_execute(stage, self.stages_completed)
            if not ok:
                import sys
                print(f"[WARNING] Stage '{stage}' prerequisites not met: {reason}", file=sys.stderr)
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)
        setattr(self, f"{stage}_output", result)
        self.current_stage = stage
        self.last_updated = time.time()
        # Save summary for context recovery
        summary = result.get("summary", "")
        if summary:
            self.stage_summaries[stage] = summary

    def mark_failed(self, stage: str, result: dict):
        """Mark a stage as failed."""
        if stage not in self.stages_failed:
            self.stages_failed.append(stage)
        if stage not in self.error_history:
            self.error_history[stage] = []
        self.error_history[stage].append({
            "time": time.time(),
            "errors": result.get("errors", []),
        })
        setattr(self, f"{stage}_output", result)
        self.current_stage = stage
        self.feedback_source = stage
        self.last_updated = time.time()

    def inc_retry(self, stage: str):
        self.retry_count[stage] = self.retry_count.get(stage, 0) + 1
        if self.retry_count[stage] >= self.max_retries_per_stage:
            import sys
            print(f"[BUDGET] Stage '{stage}' exhausted {self.max_retries_per_stage} retries. Escalating to user.", file=sys.stderr)

    def is_retry_exhausted(self, stage: str) -> bool:
        """Check if the retry budget has been exhausted for a stage."""
        return self.retry_count.get(stage, 0) >= self.max_retries_per_stage

    def get_output(self, stage: str) -> Optional[dict]:
        return getattr(self, f"{stage}_output", None)

    def is_done(self, stage: str) -> bool:
        return stage in self.stages_completed

    def is_pipeline_complete(self) -> bool:
        return "synth" in self.stages_completed

    # -- Persistence ---------------------------------------------------------

    def save(self) -> Path:
        """Save state to .veriflow/pipeline_state.json"""
        d = Path(self.project_dir) / ".veriflow"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "pipeline_state.json"
        p.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")
        return p

    @classmethod
    def load(cls, project_dir: str) -> "PipelineState":
        """Load from file, create new state if file does not exist."""
        p = Path(project_dir) / ".veriflow" / "pipeline_state.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(**data)
        return cls(project_dir=project_dir)

    @classmethod
    def reset_stage(cls, state: "PipelineState", stage: str) -> "PipelineState":
        """Clear a stage and all subsequent completion records, for rollback."""
        if stage not in STAGE_ORDER:
            return state
        idx = STAGE_ORDER.index(stage)
        to_remove = STAGE_ORDER[idx:]
        state.stages_completed = [s for s in state.stages_completed if s not in to_remove]
        state.stages_failed = [s for s in state.stages_failed if s not in to_remove]
        for s in to_remove:
            setattr(state, f"{s}_output", None)
            state.stage_summaries.pop(s, None)
        state.save()
        return state

    def next_stage(self) -> str | None:
        """Return the next stage to execute (strict order, no skipping)."""
        return next_pending_stage(self.stages_completed)

    def validate_before_run(self, stage: str) -> tuple[bool, str]:
        """Pre-execution validation. Must be called before every stage execution."""
        # 1. Check strict ordering
        expected = next_pending_stage(self.stages_completed)
        if stage != expected:
            return False, f"Order violation: expected '{expected}', but attempted '{stage}'. Stages cannot be skipped."

        # 2. Check prerequisites
        return can_execute(stage, self.stages_completed)

    def validate_spec_completeness(self, project_dir: str) -> tuple[bool, list[str]]:
        """Validate spec.json and behavior_spec.md completeness after Stage 1.

        Returns:
            (is_complete, missing_items) — is_complete=True means ready to proceed
        """
        from pathlib import Path
        import json

        missing = []
        spec_path = Path(project_dir) / "workspace/docs/spec.json"
        behavior_path = Path(project_dir) / "workspace/docs/behavior_spec.md"

        # Check spec.json
        if not spec_path.exists():
            missing.append("spec.json file missing")
        else:
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                if not spec.get("design_name"):
                    missing.append("spec.json: design_name missing")
                if not spec.get("modules"):
                    missing.append("spec.json: modules array missing")
                else:
                    for m in spec["modules"]:
                        if not m.get("module_name"):
                            missing.append(f"spec.json: module missing module_name")
                        if not m.get("ports"):
                            missing.append(f"spec.json: module {m.get('module_name', '?')} missing ports")
            except (json.JSONDecodeError, KeyError) as e:
                missing.append(f"spec.json: parse error - {e}")

        # Check behavior_spec.md
        if not behavior_path.exists():
            missing.append("behavior_spec.md file missing")
        else:
            content = behavior_path.read_text(encoding="utf-8")
            required_sections = ["Domain Knowledge", "Cycle-Accurate Behavior", "Timing Contracts"]
            for sec in required_sections:
                if sec not in content:
                    missing.append(f"behavior_spec.md: section '{sec}' missing")

        return (len(missing) == 0, missing)

    def detect_fix_loop(self, stage: str, error_signature: str) -> bool:
        """Detect if error recovery is cycling on the same error.

        Args:
            stage: Current stage name
            error_signature: A short string identifying the error (e.g., "lint:line42:syntax")

        Returns:
            True if this exact error has been seen 2+ times in recent history
        """
        if stage not in self.error_history:
            return False

        recent_errors = self.error_history[stage][-3:]  # Last 3 attempts
        signature_count = sum(1 for e in recent_errors if error_signature in str(e.get("errors", [])))

        return signature_count >= 2


# -- CLI entry point (called by SKILL.md state update command) -----------------

if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 3:
        print("Usage: python state.py <project_dir> <stage_name> [--fail]")
        _sys.exit(1)

    _project_dir = _sys.argv[1]
    _stage = _sys.argv[2]
    _is_fail = "--fail" in _sys.argv

    _state = PipelineState.load(_project_dir)

    if _is_fail:
        _state.mark_failed(_stage, {"success": False, "errors": ["Hook failed"]})
        _state.save()
        print(f"[STATE] {_stage} → FAILED")
    else:
        _state.mark_complete(_stage, {"success": True, "summary": "Hook passed"})
        _state.save()
        print(f"[STATE] {_stage} → COMPLETE")

    _next = _state.next_stage()
    print(f"[STATE] Next: {_next}" if _next else "[STATE] Pipeline complete")

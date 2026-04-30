"""Pipeline state management - zero external dependencies."""

import json
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# Strict execution order — no stage may be skipped
STAGE_ORDER = ["spec_golden", "codegen", "verify_fix", "lint_synth"]

# Prerequisite stages that must all complete before a given stage can run
STAGE_PREREQUISITES = {
    "spec_golden":  [],                     # no prerequisites
    "codegen":      ["spec_golden"],        # needs spec.json + golden_model.py
    "verify_fix":   ["codegen"],            # needs RTL + testbench
    "lint_synth":   ["verify_fix"],         # needs verified RTL
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
    spec_golden_output: Optional[dict] = None
    codegen_output: Optional[dict] = None
    verify_fix_output: Optional[dict] = None
    lint_synth_output: Optional[dict] = None

    # Error recovery
    retry_count: dict = field(default_factory=dict)
    error_history: dict = field(default_factory=dict)
    feedback_source: str = ""
    max_retries_per_stage: int = 3

    # Persistent context summary — new sessions read this field to recover state
    stage_summaries: dict = field(default_factory=dict)

    # Per-stage timing
    stage_timings: dict = field(default_factory=dict)  # {"spec_golden": {"start": ts, "end": ts, "duration_s": float}, ...}

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
        # Record end time
        self._record_end(stage)

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
        # Record end time
        self._record_end(stage)

    def mark_started(self, stage: str):
        """Record the start time of a stage."""
        now = time.time()
        if stage not in self.stage_timings:
            self.stage_timings[stage] = {}
        self.stage_timings[stage]["start"] = now
        self.current_stage = stage
        self.last_updated = now
        # Auto-fix: if start is an ISO string from older data, overwrite with float
        self.save()

    def _record_end(self, stage: str):
        """Record the end time and compute duration for a stage."""
        now = time.time()
        if stage not in self.stage_timings:
            self.stage_timings[stage] = {}
        self.stage_timings[stage]["end"] = now
        start = self.stage_timings[stage].get("start")
        if start and isinstance(start, (int, float)):
            self.stage_timings[stage]["duration_s"] = round(now - start, 1)

    def inc_retry(self, stage: str):
        self.retry_count[stage] = self.retry_count.get(stage, 0) + 1
        if self.retry_count[stage] >= self.max_retries_per_stage:
            print(f"[BUDGET] Stage '{stage}' exhausted {self.max_retries_per_stage} retries. Escalating to user.", file=sys.stderr)

    def is_retry_exhausted(self, stage: str) -> bool:
        """Check if the retry budget has been exhausted for a stage."""
        return self.retry_count.get(stage, 0) >= self.max_retries_per_stage

    def get_output(self, stage: str) -> Optional[dict]:
        return getattr(self, f"{stage}_output", None)

    def is_done(self, stage: str) -> bool:
        return stage in self.stages_completed

    def is_pipeline_complete(self) -> bool:
        return "lint_synth" in self.stages_completed

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
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return cls(**data)
            except (TypeError, json.JSONDecodeError) as e:
                print(f"[WARNING] Corrupted pipeline_state.json, starting fresh: {e}", file=sys.stderr)
        return cls(project_dir=project_dir)

    def reset_stage(self, stage: str):
        """Clear a stage and all subsequent completion records, for rollback."""
        if stage not in STAGE_ORDER:
            return
        idx = STAGE_ORDER.index(stage)
        to_remove = STAGE_ORDER[idx:]
        self.stages_completed = [s for s in self.stages_completed if s not in to_remove]
        self.stages_failed = [s for s in self.stages_failed if s not in to_remove]
        for s in to_remove:
            setattr(self, f"{s}_output", None)
            self.stage_summaries.pop(s, None)
            self.stage_timings.pop(s, None)
        self.save()

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
        """Validate spec.json completeness after Stage 1.

        Returns:
            (is_complete, missing_items) — is_complete=True means ready to proceed
        """
        missing = []
        spec_path = Path(project_dir) / "workspace/docs/spec.json"

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
                    has_top = False
                    for m in spec["modules"]:
                        if not m.get("module_name"):
                            missing.append("spec.json: module missing module_name")
                        if not m.get("ports"):
                            missing.append(f"spec.json: module {m.get('module_name', '?')} missing ports")
                        if m.get("module_type") == "top":
                            has_top = True
                    if not has_top:
                        missing.append("spec.json: no module with module_type 'top'")
                if not spec.get("constraints", {}).get("timing", {}).get("target_frequency_mhz"):
                    missing.append("spec.json: constraints.timing.target_frequency_mhz missing")
                if len(spec.get("modules", [])) > 1 and not spec.get("module_connectivity"):
                    missing.append("spec.json: module_connectivity missing for multi-module design")
            except (json.JSONDecodeError, KeyError) as e:
                missing.append(f"spec.json: parse error - {e}")

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
        signature_count = sum(
            1 for e in recent_errors
            if error_signature in str(e.get("errors", []))
        )
        return signature_count >= 2

    def validate_golden_model(self, project_dir: str) -> tuple[bool, list[str]]:
        """Validate golden_model.py after Stage 1 generation.

        Returns:
            (is_valid, issues) — is_valid=True means golden model is usable.
            Returns (True, []) if golden_model.py does not exist (it is optional).
        """
        import py_compile

        issues = []
        gm_path = Path(project_dir) / "workspace/docs" / "golden_model.py"

        if not gm_path.exists():
            return (True, [])  # golden model is optional

        # Check syntax
        try:
            py_compile.compile(str(gm_path), doraise=True)
        except py_compile.PyCompileError as e:
            issues.append(f"golden_model.py syntax error: {e}")
            return (False, issues)

        # Check it defines run()
        content = gm_path.read_text(encoding="utf-8")
        if "def run(" not in content:
            issues.append("golden_model.py missing run() function")
            return (False, issues)

        return (True, [])


# -- CLI entry point (called by SKILL.md state update command) -----------------

def _get_arg(argv: list, flag: str) -> str | None:
    """Extract value for --flag=value or --flag value from argv."""
    for a in argv:
        if a.startswith(f"--{flag}="):
            return a.split("=", 1)[1]
    idx = None
    for i, a in enumerate(argv):
        if a == f"--{flag}":
            idx = i
            break
    if idx is not None and idx + 1 < len(argv):
        return argv[idx + 1]
    return None


def _append_journal(project_dir: str, stage: str, outputs: str = "", notes: str = "",
                    status: str = "completed"):
    """Append a stage journal entry to workspace/docs/stage_journal.md."""
    journal_path = Path(project_dir) / "workspace" / "docs" / "stage_journal.md"
    from datetime import datetime
    ts = datetime.now().isoformat()
    entry = f"\n## Stage: {stage}\n**Status**: {status}\n**Timestamp**: {ts}\n"
    if outputs:
        entry += f"**Outputs**: {outputs}\n"
    if notes:
        entry += f"**Notes**: {notes}\n"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(entry)


def _print_usage():
    print("Usage:")
    print("  python state.py <project_dir> <stage_name>            Mark stage complete")
    print("  python state.py <project_dir> <stage_name> --start    Record stage start time")
    print("  python state.py <project_dir> <stage_name> --fail     Mark stage failed")
    print("  python state.py <project_dir> --reset <stage_name>    Rollback from stage onward")
    print("")
    print("  Combined (hook + state + journal in one call):")
    print("  python state.py <project_dir> <stage_name> \\")
    print('    --hook="test -f workspace/docs/spec.json" \\')
    print('    --journal-outputs="spec.json, golden_model.py" \\')
    print('    --journal-notes="Specification generated"')
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        _print_usage()

    _project_dir = sys.argv[1]

    # --reset mode: rollback from target stage
    if "--reset" in sys.argv:
        idx = sys.argv.index("--reset")
        if idx + 1 >= len(sys.argv):
            print("ERROR: --reset requires a stage name", file=sys.stderr)
            _print_usage()
        _target = sys.argv[idx + 1]
        if _target not in STAGE_ORDER:
            print(f"ERROR: Unknown stage '{_target}'. Valid stages: {STAGE_ORDER}", file=sys.stderr)
            sys.exit(1)
        _state = PipelineState.load(_project_dir)
        _state.reset_stage(_target)
        print(f"[STATE] Rolled back to '{_target}' — cleared it and all subsequent stages")
        print(f"[STATE] stages_completed: {_state.stages_completed}")
        _next = _state.next_stage()
        print(f"[STATE] Next: {_next}" if _next else "[STATE] Pipeline complete")
        sys.exit(0)

    _stage = sys.argv[2]

    if _stage not in STAGE_ORDER:
        print(f"ERROR: Unknown stage '{_stage}'. Valid stages: {STAGE_ORDER}", file=sys.stderr)
        sys.exit(1)

    _is_start = "--start" in sys.argv
    _is_fail = "--fail" in sys.argv
    _hook_cmd = _get_arg(sys.argv, "hook")
    _journal_outputs = _get_arg(sys.argv, "journal-outputs")
    _journal_notes = _get_arg(sys.argv, "journal-notes")

    _state = PipelineState.load(_project_dir)

    if _is_start:
        _state.mark_started(_stage)
        _append_journal(_project_dir, _stage, status="started")
        print(f"[STATE] {_stage} → STARTED")
    elif _is_fail:
        _state.mark_failed(_stage, {"success": False, "errors": ["Hook failed"]})
        _state.save()
        _append_journal(_project_dir, _stage, status="failed")
        print(f"[STATE] {_stage} → FAILED")
    else:
        # Run hook if provided
        _hook_passed = True
        if _hook_cmd:
            import subprocess
            _hook_cmd_resolved = _hook_cmd.replace("$PROJECT_DIR", _project_dir)
            try:
                result = subprocess.run(
                    _hook_cmd_resolved, shell=True, capture_output=True, text=True, cwd=_project_dir
                )
                if result.stdout.strip():
                    print(result.stdout.strip())
                if result.returncode != 0:
                    _hook_passed = False
                    print(f"[HOOK] FAIL (exit code {result.returncode})")
                    if result.stderr.strip():
                        print(result.stderr.strip(), file=sys.stderr)
            except Exception as e:
                _hook_passed = False
                print(f"[HOOK] FAIL (exception: {e})", file=sys.stderr)

        if _hook_passed:
            _state.mark_complete(_stage, {"success": True, "summary": "Hook passed"})
            _state.save()
            print(f"[STATE] {_stage} → COMPLETE")
            # Print timing summary
            if _stage in _state.stage_timings:
                t = _state.stage_timings[_stage]
                dur = t.get("duration_s", "?")
                print(f"[STATE] {_stage} duration: {dur}s")
            # Append journal entry if requested
            if _journal_outputs or _journal_notes:
                _append_journal(_project_dir, _stage, _journal_outputs or "", _journal_notes or "")
                print(f"[JOURNAL] {_stage} entry appended")
        else:
            _state.mark_failed(_stage, {"success": False, "errors": ["Hook failed"]})
            _state.save()
            print(f"[STATE] {_stage} → FAILED (hook)")

    _next = _state.next_stage()
    print(f"[STATE] Next: {_next}" if _next else "[STATE] Pipeline complete")

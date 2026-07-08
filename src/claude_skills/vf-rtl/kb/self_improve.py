#!/usr/bin/env python3
"""Self-improvement loop for VeriFlow-CC (cross-run, benchmark-gated, reversible).

A SAFE learning loop, NOT a live self-modifying system:

    Observe → Stage → Validate → Promote(gated) → Measure(rollback)

Nothing learned ever reaches the hot path silently: promotion is gated and
reversible, with `benchmark_runner.pass_rate` as the referee. See SELF_IMPROVE.md.

State lives under ~/.claude/skills/vf-rtl/knowledge/:
  runs.jsonl                 append-only observations (record)
  run_artifacts/*.v          snapshotted passing-first-try RTL
  staging/{reference,pattern}/*.json   candidates (mine → validate)
  promotion_log.jsonl        append-only promotion records (for rollback)
  promotion_requests/*.json dry-run proposals

Usage:
    python self_improve.py record --project-dir <dir>
    python self_improve.py mine
    python self_improve.py validate
    python self_improve.py promote [--apply ID | --auto]
    python self_improve.py rollback --promotion-id ID
    python self_improve.py status
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

_SKILL_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SKILL_DIR
while not (_SKILL_ROOT / "SKILL.md").exists() and _SKILL_ROOT.parent != _SKILL_ROOT:
    _SKILL_ROOT = _SKILL_ROOT.parent
# reference_kb is a sibling (kb/); synth_score lives in verify/. Put the skill
# root + every subdir on sys.path so cross-subdir imports resolve on direct
# invocation (self_improve is subprocessed from SKILL.md Stage 4).
for _d in [*_SKILL_ROOT.iterdir(), _SKILL_ROOT]:
    if _d.is_dir() and _d.name not in {"templates", "references", "docs", "__pycache__"} \
            and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from reference_kb import classify_module  # noqa: E402

DEFAULT_KB_DIR = Path.home() / ".claude" / "skills" / "vf-rtl" / "knowledge"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SelfImprover:
    """Drives the Observe→Stage→Validate→Promote→Rollback loop."""

    def __init__(self, kb_dir: str | Path | None = None,
                 references_dir: str | Path | None = None,
                 bug_patterns_path: str | Path | None = None):
        self.kb_dir = Path(kb_dir) if kb_dir else DEFAULT_KB_DIR
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.runs_file = self.kb_dir / "runs.jsonl"
        self.artifacts_dir = self.kb_dir / "run_artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)
        self.staging_dir = self.kb_dir / "staging"
        (self.staging_dir / "reference").mkdir(parents=True, exist_ok=True)
        (self.staging_dir / "pattern").mkdir(parents=True, exist_ok=True)
        self.log_file = self.kb_dir / "promotion_log.jsonl"
        self.requests_dir = self.kb_dir / "promotion_requests"
        self.requests_dir.mkdir(exist_ok=True)
        # Hot path targets (where promotions land).
        self.references_dir = Path(references_dir) if references_dir else (_SKILL_ROOT / "references")
        self.bug_patterns_path = (Path(bug_patterns_path)
                                  if bug_patterns_path else (_SKILL_ROOT / "bug_patterns.md"))
        # Benchmark gate (opt-in). Override on the instance for testing.
        self.benchmark_cmd = os.environ.get("VF_BENCHMARK_CMD")

    # -- low-level: locked append / atomic write --------------------------

    @contextlib.contextmanager
    def _locked(self, path: Path):
        lock_path = path.with_suffix(path.suffix + ".lock")
        lf = open(lock_path, "w", encoding="utf-8")  # noqa: SIM115
        try:
            if _HAS_FCNTL:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if _HAS_FCNTL:
                with contextlib.suppress(OSError):
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
            lf.close()

    def _append_jsonl(self, path: Path, obj: dict) -> None:
        line = json.dumps(obj, default=str)
        with self._locked(path), open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        out = []
        with contextlib.suppress(OSError, json.JSONDecodeError):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def _atomic_write_json(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked(path):
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps(obj, indent=2, default=str))
                os.replace(tmp, path)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise

    def _read_staging(self, kind: str) -> list[dict]:
        d = self.staging_dir / kind
        out = []
        for f in sorted(d.glob("*.json")):
            with contextlib.suppress(json.JSONDecodeError, OSError):
                out.append(json.loads(f.read_text(encoding="utf-8")))
        return out

    def _write_staging(self, kind: str, cand: dict) -> None:
        path = self.staging_dir / kind / (cand["id"] + ".json")
        if path.exists():
            return  # don't clobber an existing candidate's validation state
        self._atomic_write_json(path, cand)

    # -- Observe: record ---------------------------------------------------

    def _snapshot_rtl(self, project: str, module: str, rtl: Path) -> None:
        dst = self.artifacts_dir / f"{project}__{module}.v"
        with contextlib.suppress(OSError):
            dst.write_text(rtl.read_text(encoding="utf-8"), encoding="utf-8")

    def record(self, project_dir: str) -> int:
        """Append one observation per module to runs.jsonl. Best-effort, never raises."""
        project_dir = Path(project_dir)
        state_path = project_dir / ".veriflow" / "pipeline_state.json"
        if not state_path.exists():
            return 0
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        project = project_dir.name
        retry = state.get("retry_count", {}) or {}
        vf_retry = int(retry.get("verify_fix", 0) or 0)
        stages = state.get("stages_completed", []) or []
        verify_done = "verify_fix" in stages
        passed_first_try = verify_done and vf_retry == 0

        bug_class = signal_root = sig_module = None
        diag = project_dir / "logs" / "timing_diagnostic.json"
        if diag.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                d = json.loads(diag.read_text(encoding="utf-8"))
                bug_class = d.get("bug_class")
                sig = (d.get("divergence") or {}).get("signal")
                if sig:
                    sig_module = sig.split(".")[0] if "." in sig else None
                    signal_root = sig.rsplit(".", 1)[-1].split("[")[0]

        coverage = None
        cov = project_dir / "logs" / "functional_coverage.json"
        if cov.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                coverage = json.loads(cov.read_text(encoding="utf-8")).get("ratio")

        synth_cells = None
        report = project_dir / "workspace" / "synth" / "synth_report.txt"
        if report.exists():
            with contextlib.suppress(Exception):
                from synth_score import parse_synth_report
                synth_cells = parse_synth_report(report.read_text(encoding="utf-8")).get("cells") or None

        modules = []
        spec = project_dir / "workspace" / "docs" / "spec.json"
        if spec.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                s = json.loads(spec.read_text(encoding="utf-8"))
                mods = s.get("modules", [])
                if isinstance(mods, dict):
                    mods = list(mods.values())
                modules = mods or []

        ts = _now_iso()
        n = 0
        for m in modules:
            mname = m.get("module_name", "?")
            hit = (sig_module == mname)
            rec = {
                "timestamp": ts,
                "project": project,
                "module": mname,
                "module_type": classify_module(m),
                "passed_first_try": passed_first_try,
                "attempts_to_fix": vf_retry,
                "bug_class": bug_class if hit else None,
                "signal_root": signal_root if hit else None,
                "fix_directive": None,
                "coverage_ratio": coverage,
                "synth_cells": synth_cells,
            }
            self._append_jsonl(self.runs_file, rec)
            if passed_first_try:
                rtl = project_dir / "workspace" / "rtl" / f"{mname}.v"
                if rtl.exists():
                    self._snapshot_rtl(project, mname, rtl)
            n += 1
        return n

    # -- Stage: mine -------------------------------------------------------

    @staticmethod
    def _pattern_md(bug_class: str | None, signal_root: str | None,
                    recs: list[dict]) -> str:
        projects = sorted({r.get("project", "?") for r in recs})
        return (
            f"## Learned Pattern: {bug_class} on `{signal_root or 'signal'}`\n\n"
            f"**Discovered in**: self-improve mining across {len(recs)} runs "
            f"in projects {projects}.\n\n"
            "### Symptom\n\n"
            f"Recurring `{bug_class}` divergence on signal "
            f"`{signal_root or '?'}`.\n\n"
            "### Note\n\n"
            "Auto-mined candidate — REVIEW before trusting. If it generalizes, "
            "add a concrete fix and a matcher in `bug_pattern_match.py`.\n"
        )

    def mine(self, min_coverage: float = 0.9, min_occurrences: int = 3,
             min_projects: int = 2) -> dict:
        """Scan runs.jsonl → write reference + pattern candidates to staging."""
        runs = self._read_jsonl(self.runs_file)
        references: list[dict] = []

        for r in runs:
            if not r.get("passed_first_try"):
                continue
            cov = r.get("coverage_ratio")
            if cov is not None and cov < min_coverage:
                continue
            mtype = r.get("module_type") or "generic"
            project, module = r.get("project", "?"), r.get("module", "?")
            cid = f"{mtype}__{project}__{module}"
            artifact = self.artifacts_dir / f"{project}__{module}.v"
            if not artifact.exists():
                continue
            cand = {
                "id": cid, "type": mtype, "source_project": project,
                "source_module": module, "artifact": str(artifact),
                "coverage_ratio": cov, "validation": "pending",
            }
            self._write_staging("reference", cand)
            references.append(cand)

        groups: dict[tuple, list[dict]] = {}
        for r in runs:
            bc = r.get("bug_class")
            if not bc:
                continue
            groups.setdefault((bc, r.get("signal_root")), []).append(r)

        patterns: list[dict] = []
        for (bc, sr), recs in groups.items():
            projects = {r.get("project") for r in recs}
            if len(recs) >= min_occurrences and len(projects) >= min_projects:
                cand = {
                    "id": f"pat__{bc}__{sr or 'sig'}",
                    "signature": {"bug_class": bc, "signal_root": sr},
                    "recurrence": len(recs),
                    "projects": sorted(projects),
                    "proposed_md_entry": self._pattern_md(bc, sr, recs),
                    "validation": "pending",
                }
                self._write_staging("pattern", cand)
                patterns.append(cand)

        return {"references": references, "patterns": patterns}

    # -- Validate ----------------------------------------------------------

    def validate(self) -> dict:
        """Check staged candidates: references must synthesize; patterns must be well-formed."""
        import shutil
        has_yosys = shutil.which("yosys") is not None
        results = {"reference": {}, "pattern": {}}

        for cand in self._read_staging("reference"):
            if cand.get("validation") not in (None, "pending"):
                continue
            if not has_yosys:
                cand["validation"] = "skipped"
                cand["reason"] = "yosys not available"
            else:
                from synth_score import quick_synth
                with tempfile.TemporaryDirectory() as td:
                    s = quick_synth(cand["artifact"], cand.get("source_module", "top"), td)
                if "error" in s or s.get("cells", 0) <= 0:
                    cand["validation"] = "rejected"
                    cand["reason"] = s.get("error", "synth produced no cells")
                else:
                    cand["validation"] = "validated"
                    cand["cells"] = s["cells"]
            self._atomic_write_json(self.staging_dir / "reference" / (cand["id"] + ".json"), cand)
            results["reference"][cand["id"]] = cand["validation"]

        for cand in self._read_staging("pattern"):
            if cand.get("validation") not in (None, "pending"):
                continue
            ok = cand.get("recurrence", 0) >= 3 and bool(cand.get("proposed_md_entry"))
            cand["validation"] = "validated" if ok else "rejected"
            self._atomic_write_json(self.staging_dir / "pattern" / (cand["id"] + ".json"), cand)
            results["pattern"][cand["id"]] = cand["validation"]

        return results

    # -- Promote (gated) + Measure (rollback) -----------------------------

    def _next_learned_index(self, type_: str) -> int:
        idxs = []
        for p in self.references_dir.glob(f"{type_}_learned_*.v"):
            try:
                idxs.append(int(p.stem.rsplit("_", 1)[-1]))
            except ValueError:
                continue
        return (max(idxs) + 1) if idxs else 1

    def _apply_one(self, kind: str, cand: dict) -> dict:
        """Apply ONE validated candidate to the hot path + log it (reversible)."""
        ts = _now_iso()
        cid = cand["id"]
        if kind == "reference":
            self.references_dir.mkdir(parents=True, exist_ok=True)
            mtype = cand.get("type", "generic")
            idx = self._next_learned_index(mtype)
            target = self.references_dir / f"{mtype}_learned_{idx}.v"
            artifact = Path(cand["artifact"])
            content = artifact.read_text(encoding="utf-8") if artifact.exists() else ""
            target.write_text(content, encoding="utf-8")
            is_new, previous = True, None
        else:  # pattern → append to bug_patterns.md
            target = self.bug_patterns_path
            existed = target.exists()
            previous = target.read_text(encoding="utf-8") if existed else None
            tail = "" if (previous and previous.endswith("\n")) else "\n"
            target.write_text((previous or "") + tail + cand.get("proposed_md_entry", ""),
                              encoding="utf-8")
            is_new = not existed

        entry = {
            "promotion_id": f"{kind}_{cid}_{ts.replace(':', '-')}",
            "kind": kind, "candidate_id": cid, "target_path": str(target),
            "is_new": is_new, "previous_content": previous, "mode": "manual",
            "timestamp": ts,
        }
        self._append_jsonl(self.log_file, entry)
        return entry

    def _undo(self, entry: dict) -> None:
        target = Path(entry["target_path"])
        if entry.get("is_new") or entry.get("previous_content") is None:
            with contextlib.suppress(OSError):
                target.unlink()
        else:
            target.write_text(entry["previous_content"], encoding="utf-8")
        self._append_jsonl(self.log_file, {
            "promotion_id": entry["promotion_id"], "kind": "rollback",
            "timestamp": _now_iso(),
        })

    def _run_benchmark(self):
        """Run VF_BENCHMARK_CMD and parse pass_rate. Returns float or None."""
        if not self.benchmark_cmd:
            return None
        with contextlib.suppress(Exception):
            proc = subprocess.run(self.benchmark_cmd, shell=True,
                                  capture_output=True, text=True, timeout=1800)
            m = re.search(r'"pass_rate"\s*:\s*([\d.]+)', proc.stdout)
            return float(m.group(1)) if m else None
        return None

    def promote(self, apply_id: str | None = None, auto: bool = False) -> dict:
        validated = [
            (kind, cand)
            for kind in ("reference", "pattern")
            for cand in self._read_staging(kind)
            if cand.get("validation") == "validated"
        ]
        if auto:
            return self._promote_auto(validated)
        if apply_id:
            for kind, cand in validated:
                if cand["id"] == apply_id:
                    entry = self._apply_one(kind, cand)
                    return {"mode": "manual", "promotion_id": entry["promotion_id"],
                            "candidate_id": apply_id}
            return {"mode": "manual", "error": f"no validated candidate '{apply_id}'"}

        # Dry-run (default): propose, do NOT touch the hot path.
        proposed = []
        for kind, cand in validated:
            self._atomic_write_json(self.requests_dir / (cand["id"] + ".json"), {
                "kind": kind, "candidate_id": cand["id"],
                "summary": {k: cand.get(k) for k in ("type", "signature", "recurrence")},
            })
            proposed.append(cand["id"])
        return {"mode": "dry-run", "proposed": proposed}

    def _promote_auto(self, validated: list[tuple[str, dict]]) -> dict:
        if not self.benchmark_cmd:
            return {"mode": "auto", "refused": True,
                    "reason": "VF_BENCHMARK_CMD not set — refusing (fail-safe)"}
        baseline = self._run_benchmark()
        if baseline is None:
            return {"mode": "auto", "refused": True,
                    "reason": "benchmark produced no pass_rate — refusing"}
        applied = [self._apply_one(kind, cand) for kind, cand in validated]
        after = self._run_benchmark()
        if after is not None and after < baseline:
            for entry in applied:
                self._undo(entry)
            return {"mode": "auto", "rolled_back": [e["promotion_id"] for e in applied],
                    "baseline": baseline, "after": after, "reason": "regression"}
        return {"mode": "auto", "applied": [e["promotion_id"] for e in applied],
                "baseline": baseline, "after": after}

    def rollback(self, promotion_id: str) -> dict:
        for entry in reversed(self._read_jsonl(self.log_file)):
            if entry.get("promotion_id") == promotion_id and entry.get("kind") != "rollback":
                self._undo(entry)
                return {"rolled_back": promotion_id}
        return {"error": f"promotion '{promotion_id}' not found"}

    def status(self) -> dict:
        runs = self._read_jsonl(self.runs_file)
        ref = self._read_staging("reference")
        pat = self._read_staging("pattern")
        log = self._read_jsonl(self.log_file)
        return {
            "runs": len(runs),
            "staged": {"reference": len(ref), "pattern": len(pat)},
            "validated": {
                "reference": sum(1 for c in ref if c.get("validation") == "validated"),
                "pattern": sum(1 for c in pat if c.get("validation") == "validated"),
            },
            "promotions": sum(1 for e in log if e.get("kind") != "rollback"),
            "rollbacks": sum(1 for e in log if e.get("kind") == "rollback"),
            "benchmark_cmd": self.benchmark_cmd or "(unset)",
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriFlow-CC self-improvement loop")
    parser.add_argument("--kb-dir", help="Knowledge-base directory (default: ~/.claude/...)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="Observe: append a run outcome")
    p_rec.add_argument("--project-dir", required=True)

    sub.add_parser("mine", help="Stage: mine candidates from runs.jsonl")
    sub.add_parser("validate", help="Validate staged candidates")

    p_promote = sub.add_parser("promote", help="Promote validated candidates (gated)")
    p_promote.add_argument("--apply", help="Apply ONE validated candidate id (manual)")
    p_promote.add_argument("--auto", action="store_true",
                           help="Apply all validated IF benchmark non-regression")

    p_rb = sub.add_parser("rollback", help="Undo a promotion")
    p_rb.add_argument("--promotion-id", required=True)

    sub.add_parser("status", help="Inventory of staged / promoted state")

    args = parser.parse_args(argv)
    si = SelfImprover(kb_dir=args.kb_dir)

    if args.cmd == "record":
        n = si.record(args.project_dir)
        print(json.dumps({"recorded": n}))
        return 0
    if args.cmd == "mine":
        out = si.mine()
        print(json.dumps({"references": len(out["references"]),
                          "patterns": len(out["patterns"])}, indent=2))
        return 0
    if args.cmd == "validate":
        print(json.dumps(si.validate(), indent=2))
        return 0
    if args.cmd == "promote":
        print(json.dumps(si.promote(apply_id=args.apply, auto=args.auto), indent=2))
        return 0
    if args.cmd == "rollback":
        print(json.dumps(si.rollback(args.promotion_id), indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(si.status(), indent=2))
        return 0
    parser.error(f"subcommand '{args.cmd}' not implemented yet")
    return 2


if __name__ == "__main__":
    sys.exit(main())

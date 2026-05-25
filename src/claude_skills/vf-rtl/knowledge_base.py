#!/usr/bin/env python3
"""Cross-project knowledge base for VeriFlow-CC.

Persists bug pattern frequencies, design templates, and project outcomes
across runs. Enables institutional learning: patterns that frequently
cause failures are prioritized in agent prompts.

Storage: ~/.claude/skills/vf-rtl/knowledge/

Usage:
    python knowledge_base.py --record-fix logs/timing_diagnostic.json
    python knowledge_base.py --top-patterns --count 10
    python knowledge_base.py --stats
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


DEFAULT_KB_DIR = Path.home() / ".claude" / "skills" / "vf-rtl" / "knowledge"


@dataclass
class BugPatternRecord:
    pattern_id: int
    title: str
    count: int = 0
    projects: list[str] = None
    avg_fix_attempts: float = 0.0

    def __post_init__(self):
        if self.projects is None:
            self.projects = []


@dataclass
class ProjectRecord:
    project_name: str
    design_type: str
    stages_completed: list[str]
    retry_count: int
    overall_pass: bool
    timestamp: str
    bug_patterns_hit: list[int] = None

    def __post_init__(self):
        if self.bug_patterns_hit is None:
            self.bug_patterns_hit = []


class KnowledgeBase:
    """Persistent knowledge base for cross-project learning."""

    def __init__(self, kb_dir: Path | str | None = None):
        self.kb_dir = Path(kb_dir) if kb_dir else DEFAULT_KB_DIR
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_file = self.kb_dir / "bug_patterns.json"
        self.projects_file = self.kb_dir / "projects.json"
        self.templates_dir = self.kb_dir / "templates"
        self.templates_dir.mkdir(exist_ok=True)

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return default

    def _save_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------------
    # Bug patterns
    # ------------------------------------------------------------------

    def record_bug_pattern(
        self,
        pattern_id: int,
        title: str,
        project_name: str,
        fix_attempts: int,
    ) -> None:
        """Record a bug pattern occurrence from a project."""
        patterns = self._load_json(self.patterns_file, {})
        key = str(pattern_id)

        if key not in patterns:
            patterns[key] = {
                "pattern_id": pattern_id,
                "title": title,
                "count": 0,
                "projects": [],
                "total_fix_attempts": 0,
            }

        p = patterns[key]
        p["count"] += 1
        if project_name not in p["projects"]:
            p["projects"].append(project_name)
        p["total_fix_attempts"] += fix_attempts
        p["avg_fix_attempts"] = round(
            p["total_fix_attempts"] / p["count"], 2
        )

        self._save_json(self.patterns_file, patterns)

    def get_top_patterns(self, n: int = 10) -> list[dict]:
        """Return the most frequently occurring bug patterns."""
        patterns = self._load_json(self.patterns_file, {})
        sorted_patterns = sorted(
            patterns.values(),
            key=lambda p: p.get("count", 0),
            reverse=True,
        )
        return sorted_patterns[:n]

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def record_project(self, record: ProjectRecord) -> None:
        """Record a completed project outcome."""
        projects = self._load_json(self.projects_file, [])
        projects.append(asdict(record))
        self._save_json(self.projects_file, projects)

    def get_project_stats(self) -> dict:
        """Aggregate statistics across all recorded projects."""
        projects = self._load_json(self.projects_file, [])
        if not projects:
            return {"total": 0, "pass_rate": 0}

        total = len(projects)
        passed = sum(1 for p in projects if p.get("overall_pass"))
        total_retries = sum(p.get("retry_count", 0) for p in projects)

        return {
            "total_projects": total,
            "pass_rate": round(passed / total, 2),
            "avg_retries": round(total_retries / total, 2),
            "design_types": list(set(
                p.get("design_type", "unknown") for p in projects
            )),
        }

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def save_template(self, name: str, content: str, tags: list[str]) -> None:
        """Save a reusable design template."""
        template_file = self.templates_dir / f"{name}.json"
        self._save_json(template_file, {
            "name": name,
            "content": content,
            "tags": tags,
        })

    def find_templates(self, tag: str) -> list[dict]:
        """Find templates by tag."""
        results = []
        for f in self.templates_dir.glob("*.json"):
            try:
                t = json.loads(f.read_text(encoding="utf-8"))
                if tag in t.get("tags", []):
                    results.append(t)
            except Exception:
                pass
        return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriFlow knowledge base")
    parser.add_argument("--kb-dir", help="Knowledge base directory")
    parser.add_argument("--record-fix", help="Path to timing_diagnostic.json to record")
    parser.add_argument("--project", help="Project name for --record-fix")
    parser.add_argument("--fix-attempts", type=int, default=1)
    parser.add_argument("--top-patterns", action="store_true",
                        help="Show most frequent bug patterns")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--stats", action="store_true",
                        help="Show aggregate project statistics")
    parser.add_argument("--save-template", help="Save a template file")
    parser.add_argument("--template-name", help="Name for saved template")
    parser.add_argument("--template-tags", default="",
                        help="Comma-separated tags for template")
    args = parser.parse_args(argv)

    kb = KnowledgeBase(args.kb_dir)

    if args.record_fix:
        diag_path = Path(args.record_fix)
        if not diag_path.exists():
            print(f"File not found: {diag_path}", file=sys.stderr)
            return 2
        try:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            return 2

        bug_class = diag.get("bug_class", "A")
        # Map bug class to pattern ID (simplified mapping)
        class_to_pattern = {
            "A": 3, "B_late": 4, "B_early": 4, "D": 5,
        }
        pattern_id = class_to_pattern.get(bug_class, 0)
        kb.record_bug_pattern(
            pattern_id=pattern_id,
            title=f"Bug class {bug_class}",
            project_name=args.project or "unknown",
            fix_attempts=args.fix_attempts,
        )
        print(f"[kb] Recorded pattern {pattern_id} for project {args.project}")

    elif args.top_patterns:
        patterns = kb.get_top_patterns(args.count)
        print(f"[kb] Top {len(patterns)} bug patterns:")
        for p in patterns:
            print(f"  #{p['pattern_id']}: {p['title']} — "
                  f"count={p['count']} avg_fixes={p.get('avg_fix_attempts', 0)}")

    elif args.stats:
        stats = kb.get_project_stats()
        print(json.dumps(stats, indent=2))

    elif args.save_template:
        if not args.template_name:
            print("--template-name required", file=sys.stderr)
            return 2
        content = Path(args.save_template).read_text(encoding="utf-8")
        tags = [t.strip() for t in args.template_tags.split(",") if t.strip()]
        kb.save_template(args.template_name, content, tags)
        print(f"[kb] Saved template '{args.template_name}' with tags {tags}")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for knowledge_base.py — atomic writes, locking, path safety."""

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))

from knowledge_base import KnowledgeBase  # noqa: E402


# --- C1: atomic write + locking -------------------------------------------


def test_save_json_is_atomic_and_leaves_no_tmp():
    """_save_json writes via temp+os.replace: target is valid JSON, no .tmp left."""
    with tempfile.TemporaryDirectory() as tmp:
        kb = KnowledgeBase(kb_dir=tmp)
        payload = {"1": {"pattern_id": 1, "title": "x", "count": 5}}
        kb._save_json(kb.patterns_file, payload)
        # target parses back to the exact payload
        assert json.loads(kb.patterns_file.read_text()) == payload
        # no leftover temp file in the dir
        assert list(Path(tmp).glob("*.tmp")) == []


def test_concurrent_record_bug_pattern_loses_nothing():
    """Concurrent record_bug_pattern calls must all persist (flock serializes RMW).

    Without a lock, the read-modify-write window loses records (last-writer-wins).
    """
    with tempfile.TemporaryDirectory() as tmp:
        def record(pid):
            kb = KnowledgeBase(kb_dir=tmp)
            kb.record_bug_pattern(pattern_id=pid, title=f"p{pid}",
                                  project_name="proj", fix_attempts=1)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        kb = KnowledgeBase(kb_dir=tmp)
        patterns = kb._load_json(kb.patterns_file, {})
        assert len(patterns) == 8, (
            f"expected 8 records, got {len(patterns)}: {sorted(patterns)}"
        )


# --- C2: path traversal + pattern_id mapping ------------------------------


def test_save_template_rejects_path_traversal():
    """save_template must refuse names that escape templates_dir."""
    with tempfile.TemporaryDirectory() as tmp:
        kb = KnowledgeBase(kb_dir=tmp)
        for bad in ("../evil", "..\\evil", "a/b", "", "a.b", "a b"):
            try:
                kb.save_template(bad, "content", ["tag"])
            except ValueError:
                continue
            raise AssertionError(f"save_template accepted unsafe name: {bad!r}")
        # a clean name works
        kb.save_template("good_name", "content", ["tag"])
        assert (kb.templates_dir / "good_name.json").exists()


_VALID_PATTERN_IDS = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}


def test_record_fix_uses_valid_category_not_phantom_id():
    """--record-fix must not record under nonexistent pattern_id 4.

    Regression: class_to_pattern mapped B_late/B_early -> 4, which is not a real
    bug_pattern_match.py pattern, creating phantom records.
    """
    with tempfile.TemporaryDirectory() as tmp:
        diag = Path(tmp) / "diag.json"
        diag.write_text(json.dumps({"bug_class": "B_late"}))
        result = subprocess.run(
            [sys.executable, str(_SKILLS_DIR / "knowledge_base.py"),
             "--record-fix", str(diag), "--project", "proj",
             "--kb-dir", tmp],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"record-fix failed: {result.stderr}"
        kb = KnowledgeBase(kb_dir=tmp)
        patterns = kb._load_json(kb.patterns_file, {})
        # No phantom "4" key.
        assert "4" not in patterns, f"phantom pattern_id 4 recorded: {patterns}"
        # Something was recorded (the B_late category).
        assert len(patterns) >= 1
        for key, rec in patterns.items():
            pid = int(key)
            # Either a real RTL pattern id, or the reserved bug-class range (>=100).
            assert pid in _VALID_PATTERN_IDS or pid >= 100, (
                f"recorded under invalid pattern_id {pid}: {rec}"
            )


if __name__ == "__main__":
    test_save_json_is_atomic_and_leaves_no_tmp()
    test_concurrent_record_bug_pattern_loses_nothing()
    test_save_template_rejects_path_traversal()
    test_record_fix_uses_valid_category_not_phantom_id()
    print("All knowledge_base tests passed.")

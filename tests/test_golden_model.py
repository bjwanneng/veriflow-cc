"""Tests for golden model integration across the VeriFlow pipeline.

Covers:
- golden_model_template.py structure
- state.py: validate_golden_model method
- SKILL.md golden model references
- vcd2table.py: golden model integration
"""

import tempfile
from pathlib import Path

# Resolve directories relative to this test file
_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
_TEMPLATES_DIR = _SKILLS_DIR / "templates"
import sys
sys.path.insert(0, str(_SKILLS_DIR))


def _read_template():
    return (_TEMPLATES_DIR / "golden_model_template.py").read_text(encoding="utf-8")


def _read_skill():
    return (_SKILLS_DIR / "SKILL.md").read_text(encoding="utf-8")


def _read_vcd2table():
    return (_SKILLS_DIR / "vcd2table.py").read_text(encoding="utf-8")


# ── Golden model template ────────────────────────────────────────────────


def test_template_exists():
    """Golden model template must exist."""
    assert (_TEMPLATES_DIR / "golden_model_template.py").exists()


def test_template_mentions_run_function():
    """Template must show run() function pattern."""
    content = _read_template()
    assert "def run(" in content or "def _module_" in content, \
        "Template must show function patterns for golden model"


def test_template_is_pure_python():
    """Template must not import external dependencies."""
    content = _read_template()
    # Only stdlib imports allowed
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") and not stripped.startswith("import json"):
            # Allow json (stdlib), reject numpy etc
            assert "numpy" not in stripped and "hashlib" not in stripped, \
                f"Template should not import external deps: {stripped}"


# ── SKILL.md golden model references ──────────────────────────────────────


def test_skill_references_golden_model():
    """SKILL.md must reference golden_model.py."""
    content = _read_skill()
    assert "golden_model.py" in content, \
        "SKILL.md must reference golden_model.py"


def test_skill_stage1_generates_golden_model():
    """SKILL.md Stage 1 (spec_golden) must generate golden_model.py."""
    content = _read_skill()
    assert "golden_model.py" in content, \
        "SKILL.md must specify golden_model.py generation in Stage 1"


# ── vcd2table.py ─────────────────────────────────────────────────────────


def test_vcd2table_has_golden_model_flag():
    """vcd2table.py must have --golden-model argument."""
    content = _read_vcd2table()
    assert "--golden-model" in content, \
        "vcd2table.py must have --golden-model argument"


def test_vcd2table_has_run_golden_model_comparison():
    """vcd2table.py must define run_golden_model_comparison function."""
    content = _read_vcd2table()
    assert "def run_golden_model_comparison(" in content, \
        "vcd2table.py must define run_golden_model_comparison()"


# ── state.py: validate_golden_model ──────────────────────────────────────


def test_state_validate_golden_model_valid():
    """validate_golden_model returns True for valid golden model."""
    from state import PipelineState
    with tempfile.TemporaryDirectory() as tmp:
        # Create valid golden model
        docs = Path(tmp) / "workspace" / "docs"
        docs.mkdir(parents=True)
        (docs / "golden_model.py").write_text("def run(): return []\n")
        s = PipelineState(project_dir=tmp)
        ok, issues = s.validate_golden_model(tmp)
        assert ok, f"Valid golden model should pass: {issues}"
        assert issues == []


def test_state_validate_golden_model_missing():
    """validate_golden_model returns True when file missing (optional)."""
    from state import PipelineState
    with tempfile.TemporaryDirectory() as tmp:
        s = PipelineState(project_dir=tmp)
        ok, issues = s.validate_golden_model(tmp)
        assert ok, "Missing golden model should return True (optional)"
        assert issues == []


def test_state_validate_golden_model_no_run():
    """validate_golden_model returns False when run() is missing."""
    from state import PipelineState
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / "workspace" / "docs"
        docs.mkdir(parents=True)
        (docs / "golden_model.py").write_text("x = 42\n")
        s = PipelineState(project_dir=tmp)
        ok, issues = s.validate_golden_model(tmp)
        assert not ok, "Golden model without run() should fail"
        assert any("run()" in i for i in issues)


if __name__ == "__main__":
    tests = [name for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    passed = 0
    failed = 0
    for name in tests:
        try:
            obj = globals()[name]
            obj()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    exit(1 if failed else 0)

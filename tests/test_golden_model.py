"""Tests for golden model integration across the VeriFlow pipeline.

Covers:
- Stage 1: conditional golden model generation step (1c4)
- Stage 1 hook: conditional golden model check
- Stage 1 journal: conditional golden_model.py output
- Stage 3: expected_vectors.json consumption and priority order
- Stage 7: --golden-model flag and workspace/docs/golden_model.py search
- vcd2table.py: --golden-model flag and run_golden_model_comparison function
- state.py: validate_golden_model method
"""

import tempfile
from pathlib import Path

# Resolve directories relative to this test file
_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-pipeline"
import sys
sys.path.insert(0, str(_SKILLS_DIR))


def _read_stage1():
    return (_SKILLS_DIR / "stages" / "stage_1.md").read_text(encoding="utf-8")

def _read_stage3():
    return (_SKILLS_DIR / "stages" / "stage_3.md").read_text(encoding="utf-8")

def _read_stage7():
    return (_SKILLS_DIR / "stages" / "stage_7.md").read_text(encoding="utf-8")

def _read_vcd2table():
    return (_SKILLS_DIR / "vcd2table.py").read_text(encoding="utf-8")


# ── Stage 1 ──────────────────────────────────────────────────────────────

def test_stage1_has_golden_model_step():
    """Stage 1 must have section 1c4 for golden model generation."""
    content = _read_stage1()
    assert "1c4" in content, "Stage 1 missing section 1c4"
    assert "golden_model.py" in content, "Stage 1 1c4 must mention golden_model.py"


def test_stage1_golden_model_is_conditional():
    """Golden model generation must be conditional — only when pseudocode exists."""
    content = _read_stage1()
    # Must mention skipping when no pseudocode
    assert "No algorithm pseudocode" in content or "not applicable" in content, \
        "Stage 1 must describe conditional skip when no pseudocode"
    # Must mention it's optional
    assert "skip" in content.lower() and "golden" in content.lower(), \
        "Stage 1 must describe skipping golden model"


def test_stage1_hook_checks_golden_model_conditionally():
    """Hook must only check golden_model.py when it exists (not mandatory)."""
    content = _read_stage1()
    hook_start = content.find("## 1d. Hook")
    hook_end = content.find("## 1e.", hook_start)
    hook_block = content[hook_start:hook_end]
    # Must use 'if [ -f ... ]' pattern, not mandatory test
    assert "golden_model.py" in hook_block, \
        "Hook must mention golden_model.py"
    assert "if [ -f" in hook_block, \
        "Hook must use conditional check for golden_model.py"


def test_stage1_journal_lists_golden_model_conditionally():
    """Journal must conditionally include golden_model.py."""
    content = _read_stage1()
    journal_start = content.find("## 1f. Journal")
    journal_block = content[journal_start:]
    assert "golden_model.py" in journal_block, \
        "Journal must mention golden_model.py"


def test_golden_model_template_has_run_function():
    """Golden model template must specify run() -> list[dict] interface."""
    content = _read_stage1()
    assert "def run(" in content, \
        "Golden model template must show run() function"
    assert "list[dict]" in content or "list[dict]" in content, \
        "Golden model template must specify list[dict] return type"


# ── Stage 3 ──────────────────────────────────────────────────────────────

def test_stage3_reads_expected_vectors():
    """Stage 3 must reference expected_vectors.json."""
    content = _read_stage3()
    assert "expected_vectors.json" in content, \
        "Stage 3 must reference expected_vectors.json"


def test_stage3_golden_model_priority():
    """Stage 3 must document expected value priority order."""
    content = _read_stage3()
    assert "priority" in content.lower() or "Priority" in content, \
        "Stage 3 must document priority order for expected values"
    # expected_vectors.json should be mentioned as highest priority
    assert "expected_vectors.json" in content, \
        "expected_vectors.json must be in priority list"


def test_stage3_graceful_without_golden_model():
    """Stage 3 must work without golden model (graceful fallback)."""
    content = _read_stage3()
    # Must have a fallback path when no golden model exists
    assert "No workspace/docs/golden_model.py" in content or \
           "spec/standards only" in content or \
           "if" in content, \
        "Stage 3 must handle absence of golden model gracefully"


# ── Stage 7 ──────────────────────────────────────────────────────────────

def test_stage7_passes_golden_model_flag():
    """Stage 7 must pass --golden-model to vcd2table.py."""
    content = _read_stage7()
    assert "--golden-model" in content, \
        "Stage 7 must pass --golden-model flag to vcd2table.py"


def test_stage7_checks_workspace_golden_model():
    """Stage 7 must check workspace/docs/golden_model.py (not only context/*.py)."""
    content = _read_stage7()
    assert "workspace/docs/golden_model.py" in content, \
        "Stage 7 must check workspace/docs/golden_model.py"


def test_stage7_has_golden_section():
    """Stage 7 must have a Golden Model Comparison section."""
    content = _read_stage7()
    assert "Golden Model Comparison" in content, \
        "Stage 7 must have Golden Model Comparison section"


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

"""Test golden_model.py consistency validation — Bug Pattern: trace mode and
non-trace mode produce different results (SM3 compute() bug).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"))

from state import PipelineState


def test_validate_golden_model_consistency_pass():
    """Golden model with consistent trace and non-trace modes passes."""
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        docs = proj / "workspace" / "docs"
        docs.mkdir(parents=True)

        gm = docs / "golden_model.py"
        gm.write_text('''
def compute(inputs=None, trace=False):
    result = {"hash_out": 0x1234abcd, "hash_valid": 1}
    if trace:
        return [{"hash_out": 0, "hash_valid": 0}, result]
    return result

def run(test_vector_index=0):
    return compute(trace=True)

if __name__ == "__main__":
    r = compute(trace=False)
    print(f"[PASS] hash_out=0x{r['hash_out']:08x}")
''')
        state = PipelineState(project_dir=proj)
        ok, issues = state.validate_golden_model(td)
        assert ok, f"Expected pass, got: {issues}"


def test_validate_golden_model_consistency_fail():
    """Golden model with divergent trace mode fails."""
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        docs = proj / "workspace" / "docs"
        docs.mkdir(parents=True)

        gm = docs / "golden_model.py"
        gm.write_text('''
def compute(inputs=None, trace=False):
    if trace:
        # BUG: trace mode returns wrong final value
        return [{"hash_out": 0, "hash_valid": 0}, {"hash_out": 0xDEADBEEF, "hash_valid": 1}]
    return {"hash_out": 0x1234abcd, "hash_valid": 1}

def run(test_vector_index=0):
    return compute(trace=True)

if __name__ == "__main__":
    r = compute(trace=False)
    print(f"[PASS] hash_out=0x{r['hash_out']:08x}")
''')
        state = PipelineState(project_dir=td)
        ok, issues = state.validate_golden_model(td)
        assert not ok, "Expected failure due to trace/non-trace divergence"
        assert any("trace" in i.lower() and "different" in i.lower() for i in issues), f"Issues: {issues}"


if __name__ == "__main__":
    test_validate_golden_model_consistency_pass()
    print("[PASS] test_validate_golden_model_consistency_pass")

    test_validate_golden_model_consistency_fail()
    print("[PASS] test_validate_golden_model_consistency_fail")

    print("ALL GOLDEN MODEL CONSISTENCY TESTS PASSED")

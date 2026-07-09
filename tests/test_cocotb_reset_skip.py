"""WS4: cocotb RESET_CYCLE_SKIP is spec-driven (mirrors DRIVE_PHASE_CYCLES).

cocotb_template.py imports cocotb at module top, so it cannot be imported in
the test env. Instead we exec the template's REAL fallback block (extracted via
unique markers) in isolation with a controlled spec.json — runtime coverage of
the actual codegen logic, no cocotb required.
"""

import json
import tempfile
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent.parent / "src" / "claude_skills" / "vf-rtl"
_SPEC_TEMPLATE = _SKILLS_DIR / "templates" / "spec_template.json"
_COCOTB_TEMPLATE = _SKILLS_DIR / "templates" / "cocotb_template.py"

_BEGIN = "# ─── RESET_CYCLE_SKIP resolution (begin) ───"
_END = "# ─── RESET_CYCLE_SKIP resolution (end) ───"


def test_spec_template_has_reset_cycle_skip_default_1():
    spec = json.loads(_SPEC_TEMPLATE.read_text())
    tc = spec.get("timing_convention", {})
    assert "reset_cycle_skip" in tc
    assert tc["reset_cycle_skip"] == 1


def _exec_fallback(spec_json_text, *, codegen_value=1):
    """Exec the template's real RESET_CYCLE_SKIP fallback block in isolation.

    `codegen_value` simulates what codegen set RESET_CYCLE_SKIP to before the
    fallback runs (1 = codegen left it at default → fallback engages).
    `spec_json_text=None` means no spec.json on disk.
    """
    src = _COCOTB_TEMPLATE.read_text()
    assert _BEGIN in src and _END in src, "fallback block markers missing"
    block = src.split(_BEGIN, 1)[1].split(_END, 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir(parents=True)
        if spec_json_text is not None:
            (docs / "spec.json").write_text(spec_json_text)
        # __file__ = tmp/tb/test_x.py → parent.parent/docs = tmp/docs
        ns = {"Path": Path,
              "__file__": str(Path(tmp) / "tb" / "test_x.py"),
              "RESET_CYCLE_SKIP": codegen_value}
        exec(compile(block, "<reset_skip_fallback>", "exec"), ns)  # noqa: S102
    return ns["RESET_CYCLE_SKIP"]


def test_fallback_reads_reset_cycle_skip_from_spec():
    assert _exec_fallback('{"timing_convention":{"reset_cycle_skip":3}}') == 3


def test_fallback_default_when_no_spec():
    assert _exec_fallback(None) == 1


def test_fallback_default_when_field_absent():
    assert _exec_fallback('{"timing_convention":{}}') == 1


def test_fallback_codegen_override_not_clobbered():
    """codegen set RESET_CYCLE_SKIP=5 → gate (==1) False → stays 5."""
    assert _exec_fallback('{"timing_convention":{"reset_cycle_skip":3}}',
                          codegen_value=5) == 5


def test_fallback_ignores_invalid_values():
    assert _exec_fallback('{"timing_convention":{"reset_cycle_skip":"x"}}') == 1
    assert _exec_fallback('{"timing_convention":{"reset_cycle_skip":-1}}') == 1


def test_fallback_accepts_zero():
    assert _exec_fallback('{"timing_convention":{"reset_cycle_skip":0}}') == 0


if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {name}")
                traceback.print_exc()
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    import sys
    sys.exit(1 if failed else 0)

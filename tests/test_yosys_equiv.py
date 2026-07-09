"""Tests for yosys_equiv.py — Yosys-based formal equivalence checker.

Tests script generation, output parsing, and graceful fallback when
Yosys is not installed.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "claude_skills" / "vf-rtl"))


class TestScriptGeneration(unittest.TestCase):
    """The Yosys script contains correct read_verilog and equiv commands."""

    def test_script_contains_read_verilog(self):
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "my_module")
        self.assertIn('read_verilog "ref.v"', script)
        self.assertIn('read_verilog "impl.v"', script)

    def test_script_contains_equiv_commands(self):
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "my_module")
        self.assertIn("equiv_make ref_top impl_top equiv", script)
        self.assertIn("equiv_simple", script)
        self.assertIn("equiv_status -assert", script)

    def test_script_uses_different_top_names(self):
        """If ref and impl have different top names, equiv_make must map them."""
        from yosys_equiv import _build_yosys_script
        script = _build_yosys_script("ref.v", "impl.v", "ref_top", "impl_top")
        self.assertIn("equiv_make ref_top impl_top", script)


class TestOutputParsing(unittest.TestCase):
    """Parsing Yosys equiv_status output."""

    def test_parse_pass(self):
        from yosys_equiv import _parse_equiv_output
        output = """
        Equivalence successfully proved!
        Found 0 unproven $equiv cells.
        """
        result = _parse_equiv_output(output)
        self.assertTrue(result["equivalent"])
        self.assertEqual(len(result["unproven"]), 0)

    def test_parse_fail(self):
        from yosys_equiv import _parse_equiv_output
        output = """
        Found 2 unproven $equiv cells:
        gold.y != gate.y
        gold.x != gate.x
        """
        result = _parse_equiv_output(output)
        self.assertFalse(result["equivalent"])
        self.assertGreaterEqual(len(result["unproven"]), 1)

    def test_parse_no_output(self):
        from yosys_equiv import _parse_equiv_output
        result = _parse_equiv_output("")
        self.assertIsNone(result["equivalent"])

    def test_parse_pass_reworded(self):
        """A yosys rewording (not the legacy 'successfully prove...') still PASSes.

        Regression: PASS detection hinged on the truncated literal
        'Equivalence successfully prove', so any rewording fell to UNKNOWN.
        """
        from yosys_equiv import _parse_equiv_output
        for output in (
            "Equivalence checking succeeded.\nFound 0 unproven $equiv cells.\n",
            "Equivalence checking was successful.\n",
            "Ready: proved equivalence.\n",
        ):
            result = _parse_equiv_output(output)
            self.assertTrue(
                result["equivalent"],
                f"should be PASS for: {output!r} (got {result['equivalent']})",
            )

    def test_parse_reworded_with_unproven_still_fails(self):
        """Conservative: a reworded message with unproven cells is still FAIL."""
        from yosys_equiv import _parse_equiv_output
        output = "Equivalence checking succeeded.\ngold.y != gate.y\n"
        result = _parse_equiv_output(output)
        self.assertFalse(result["equivalent"])


class TestCLIArgs(unittest.TestCase):
    """Command-line interface validation."""

    def test_missing_yosys_graceful(self):
        """If yosys is not in PATH, return a dict with yosys_available=False."""
        from yosys_equiv import check_equivalence
        result = check_equivalence(
            ref_path="/dev/null",
            impl_path="/dev/null",
            top_name="test",
            yosys_bin="/nonexistent/yosys",
        )
        self.assertFalse(result["yosys_available"])


class TestSameNameCollision(unittest.TestCase):
    """Both files defining the same module name must not poison each other.

    Regression for I9: the script uses `rename {top} ref_top` then
    `read_verilog impl` then `rename {top} impl_top`. If either
    rename silently failed or only renamed one of two same-named modules,
    the equiv check would compare a design against itself and trivially pass.
    Originally the script used `read_verilog -defer`, but deferred modules
    are stored as `$abstract\\name` and the rename pass can't find them.
    """

    @classmethod
    def setUpClass(cls):
        import shutil
        if shutil.which("yosys") is None:
            raise unittest.SkipTest("yosys not on PATH")

    def test_same_module_name_distinguished(self):
        """Two non-equivalent modules with the same name must report FAIL."""
        from yosys_equiv import check_equivalence

        ref_src = """
        module adder(input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = a + b;
        endmodule
        """
        impl_src = """
        module adder(input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = a - b;
        endmodule
        """

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ref_p = tmp_path / "ref.v"
            impl_p = tmp_path / "impl.v"
            ref_p.write_text(ref_src)
            impl_p.write_text(impl_src)

            result = check_equivalence(
                ref_path=str(ref_p),
                impl_path=str(impl_p),
                top_name="adder",
                timeout=60,
            )

            # If rename failed silently the two designs would collapse into
            # one and equiv would trivially pass. We assert FAIL to prove
            # the script kept them separated.
            self.assertTrue(result["yosys_available"])
            self.assertEqual(
                result["equivalent"], False,
                f"Expected FAIL for non-equivalent same-named modules. "
                f"Got equivalent={result['equivalent']}. Raw:\n{result.get('raw', '')[-500:]}"
            )

    def test_same_module_name_actually_equivalent(self):
        """Two equivalent modules with the same name must report PASS."""
        from yosys_equiv import check_equivalence

        src = """
        module mux2(input s, input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = s ? a : b;
        endmodule
        """
        src_alt = """
        module mux2(input s, input [3:0] a, input [3:0] b, output [3:0] y);
            assign y = ({4{s}} & a) | ({4{~s}} & b);
        endmodule
        """

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            ref_p = tmp_path / "ref.v"
            impl_p = tmp_path / "impl.v"
            ref_p.write_text(src)
            impl_p.write_text(src_alt)

            result = check_equivalence(
                ref_path=str(ref_p),
                impl_path=str(impl_p),
                top_name="mux2",
                timeout=60,
            )

            self.assertTrue(result["yosys_available"])
            self.assertEqual(
                result["equivalent"], True,
                f"Expected PASS. Got equivalent={result['equivalent']}. "
                f"Raw:\n{result.get('raw', '')[-500:]}"
            )


# ===========================================================================
# WS3: async-reset handling, strategy iteration, blackbox verdict.
# Pytest-style (uses monkeypatch + tmp_path fixtures); all mock yosys.
# ===========================================================================
import types as _types  # noqa: E402

import yosys_equiv as ye  # noqa: E402


def test_build_script_base_has_no_optional_cmds():
    s = ye._build_yosys_script("a.v", "b.v", "top")
    assert "clk2fflogic" not in s
    assert "async2sync" not in s
    assert "flatten" not in s


def test_build_script_emits_clk2fflogic():
    assert "clk2fflogic" in ye._build_yosys_script("a.v", "b.v", "top", clk2fflogic=True)


def test_build_script_flatten_after_equiv_make():
    s = ye._build_yosys_script("a.v", "b.v", "top", flatten=True)
    assert "flatten" in s
    assert s.index("equiv_make") < s.index("flatten")


def test_build_script_async2sync_present():
    assert "async2sync" in ye._build_yosys_script("a.v", "b.v", "top", async2sync=True)


def _attempt(name, flatten, equivalent, unproven=None):
    return {"name": name, "flatten": flatten,
            "equivalent": equivalent, "unproven": unproven or []}


def test_decide_proof_on_base_is_not_blackbox():
    r = ye._decide([_attempt("base", False, True)])
    assert r["equivalent"] is True
    assert r["is_blackbox_limitation"] is False
    assert r["strategy_used"] == "base"


def test_decide_blackbox_limitation_when_flatten_clears_unproven():
    tried = [_attempt("base", False, False, ["gold.x != gate.x"]),
             _attempt("flatten", True, True)]
    r = ye._decide(tried)
    assert r["equivalent"] is True
    assert r["is_blackbox_limitation"] is True
    assert "blackbox" in (r.get("message") or "").lower()


def test_decide_real_counterexample_persists_through_flatten():
    tried = [_attempt("base", False, False, ["gold.x != gate.x"]),
             _attempt("flatten", True, False, ["gold.x != gate.x"])]
    r = ye._decide(tried)
    assert r["equivalent"] is False
    assert r["is_blackbox_limitation"] is False
    assert r["unproven"]


def test_decide_unknown_when_nothing_definitive():
    r = ye._decide([_attempt("base", False, None)])
    assert r["equivalent"] is None
    assert r["is_blackbox_limitation"] is False


class _Seq:
    """Fake subprocess.run returning scripted (stdout, stderr, rc) per call.

    Captures each yosys script's content (the `-s <path>` file) while it still
    exists on disk, before _run_strategy's finally deletes it.
    """
    def __init__(self, outputs):
        self.outputs = outputs
        self.i = 0
        self.calls = []
        self.scripts = []

    def __call__(self, cmd, *a, **k):
        self.calls.append(cmd)
        if isinstance(cmd, list) and "-s" in cmd:
            try:
                self.scripts.append(Path(cmd[cmd.index("-s") + 1]).read_text())
            except OSError:
                self.scripts.append(None)
        else:
            self.scripts.append(None)
        out = self.outputs[self.i] if self.i < len(self.outputs) else ("", "", 1)
        self.i += 1
        return _types.SimpleNamespace(stdout=out[0], stderr=out[1], returncode=out[2])


def _patch_no_async(monkeypatch):
    monkeypatch.setattr(ye, "_detect_async_reset", lambda *a, **k: False)


def _make_files(tmp, body="module top; endmodule"):
    (tmp / "ref.v").write_text(body)
    (tmp / "impl.v").write_text(body)
    return tmp / "ref.v", tmp / "impl.v"


def test_check_proof_on_base(monkeypatch, tmp_path):
    _patch_no_async(monkeypatch)
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    seq = _Seq([("Equivalence successfully proved\n", "", 0)])
    monkeypatch.setattr(ye.subprocess, "run", seq)
    ref, impl = _make_files(tmp_path)
    r = ye.check_equivalence(ref, impl, "top")
    assert r["equivalent"] is True
    assert r["strategy_used"] == "base"
    assert r["is_blackbox_limitation"] is False
    assert len(seq.calls) == 1


def test_check_blackbox_limitation_path(monkeypatch, tmp_path):
    _patch_no_async(monkeypatch)
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    # base unproven -> clk2fflogic unknown -> flatten proves
    seq = _Seq([
        ("gold.x != gate.x\n", "", 1),
        ("irrelevant noise\n", "", 1),
        ("Equivalence successfully proved\n", "", 0),
    ])
    monkeypatch.setattr(ye.subprocess, "run", seq)
    ref, impl = _make_files(tmp_path)
    r = ye.check_equivalence(ref, impl, "top")
    assert r["equivalent"] is True
    assert r["is_blackbox_limitation"] is True
    assert r["strategy_used"] == "flatten"


def test_check_real_counterexample(monkeypatch, tmp_path):
    _patch_no_async(monkeypatch)
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    seq = _Seq([
        ("gold.x != gate.x\n", "", 1),       # base
        ("irrelevant noise\n", "", 1),        # clk2fflogic unknown
        ("gold.x != gate.x\n", "", 1),        # flatten still unproven -> real
    ])
    monkeypatch.setattr(ye.subprocess, "run", seq)
    ref, impl = _make_files(tmp_path)
    r = ye.check_equivalence(ref, impl, "top")
    assert r["equivalent"] is False
    assert r["is_blackbox_limitation"] is False


def test_check_yosys_unavailable_schema_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(ye.shutil, "which", lambda *a: None)
    ref, impl = _make_files(tmp_path)
    r = ye.check_equivalence(ref, impl, "top")
    assert r["equivalent"] is None
    assert r["yosys_available"] is False
    assert "strategy_used" in r
    assert "is_blackbox_limitation" in r
    assert r["is_blackbox_limitation"] is False


def test_detect_async_reset_true_on_adff(monkeypatch, tmp_path):
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    monkeypatch.setattr(ye.subprocess, "run", lambda *a, **k: _types.SimpleNamespace(
        stdout="   $_DFF_  10\n   $adff   4\n", stderr="", returncode=0))
    (tmp_path / "r.v").write_text("module top; endmodule")
    assert ye._detect_async_reset(tmp_path / "r.v", "top", "/fake/yosys") is True


def test_detect_async_reset_false_without_adff(monkeypatch, tmp_path):
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    monkeypatch.setattr(ye.subprocess, "run", lambda *a, **k: _types.SimpleNamespace(
        stdout="   $_DFF_  10\n", stderr="", returncode=0))
    (tmp_path / "r.v").write_text("module top; endmodule")
    assert ye._detect_async_reset(tmp_path / "r.v", "top", "/fake/yosys") is False


def test_detect_async_reset_error_returns_false(monkeypatch, tmp_path):
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    monkeypatch.setattr(ye.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    (tmp_path / "r.v").write_text("module top; endmodule")
    assert ye._detect_async_reset(tmp_path / "r.v", "top", "/fake/yosys") is False


def test_async_reset_reorders_clk2fflogic_first(monkeypatch, tmp_path):
    monkeypatch.setattr(ye, "_detect_async_reset", lambda *a, **k: True)
    monkeypatch.setattr(ye.shutil, "which", lambda *a: "/fake/yosys")
    seq = _Seq([("Equivalence successfully proved\n", "", 0)])
    monkeypatch.setattr(ye.subprocess, "run", seq)
    ref, impl = _make_files(tmp_path)
    ye.check_equivalence(ref, impl, "top")
    assert seq.scripts, "no yosys strategy ran"
    assert "clk2fflogic" in seq.scripts[0]


if __name__ == "__main__":
    unittest.main()
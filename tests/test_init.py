"""Tests for init.py — eda_env.sh shell quoting."""

import importlib.util
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


_PROJECT_DIR = Path(__file__).parent.parent
_SKILLS_DIR = _PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
sys.path.insert(0, str(_SKILLS_DIR))


def _load_init():
    spec = importlib.util.spec_from_file_location(
        "vf_init", str(_SKILLS_DIR / "init.py")
    )
    init = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init)
    return init


def test_eda_env_quoting_handles_spaces_and_dollars():
    """Paths with spaces / $ must round-trip through `source eda_env.sh`.

    Regression: values were interpolated into double-quoted shell strings with
    no escaping, so a space broke the export and a `$VAR` expanded (data loss /
    injection). shlex.quote single-quotes them so they survive verbatim.
    """
    init = _load_init()
    with tempfile.TemporaryDirectory() as tmp:
        env_path = Path(tmp) / "eda_env.sh"
        tricky_bin = "/opt/oss cad-suite/bin"          # contains a space
        tricky_lib = "/opt/oss cad-suite/lib$IVL_VAR"  # space + dollar
        tricky_skill = str(_SKILLS_DIR)                # may contain spaces

        init.write_eda_env(
            env_path,
            python_exe="/usr/local/bin/python3",
            eda_bin=tricky_bin,
            eda_lib=tricky_lib,
            ivl_home="",
            cocotb_available=False,
            skill_dir=tricky_skill,
        )

        # Source under plain POSIX sh and echo vars back — round-trip check.
        cmd = (
            f". {shlex.quote(str(env_path))} && "
            f"printf '%s\\n' \"$EDA_BIN\" \"$EDA_LIB\" \"$PYTHONPATH\""
        )
        proc = subprocess.run(
            ["sh", "-c", cmd], capture_output=True, text=True,
            env={**os.environ, "IVL_VAR": "SHOULD_NOT_LEAK"},
        )
        assert proc.returncode == 0, f"sourcing failed:\n{proc.stderr}"
        out = proc.stdout.rstrip("\n").split("\n")
        assert out[0] == tricky_bin, f"EDA_BIN mangled: {out[0]!r}"
        assert out[1] == tricky_lib, (
            f"EDA_LIB mangled (the $IVL_VAR leaked/expanded): {out[1]!r}"
        )
        # skill_dir must be the first PYTHONPATH entry (before the inherited one)
        assert out[2].startswith(tricky_skill), (
            f"PYTHONPATH skill dir mangled: {out[2]!r}"
        )


if __name__ == "__main__":
    test_eda_env_quoting_handles_spaces_and_dollars()
    print("All init tests passed.")

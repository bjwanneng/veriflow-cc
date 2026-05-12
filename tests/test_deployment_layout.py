"""Install layout + init eda_env.sh contracts.

These tests verify the deployment surface that user projects depend on:

  install.py — must symlink SKILL.md + state.py + support scripts + templates
               + 5 agents under ~/.claude/.

  init.py    — must export PYTHONPATH pointing at the skill directory in
               eda_env.sh, so any shell command that sources it can run
               `python -c "from state import ..."` and any helper scripts
               shipped alongside SKILL.md.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestInitWritesPythonpath(unittest.TestCase):
    """init.py must write a PYTHONPATH= line into eda_env.sh so that
    `source eda_env.sh` makes helper imports work without per-call
    `PYTHONPATH=src` prefixes."""

    def _make_project(self, project_dir: Path) -> None:
        (project_dir / "requirement.md").write_text("# stub requirement\n")

    def test_eda_env_exports_pythonpath_to_skill_dir(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "proj"
            project_dir.mkdir()
            self._make_project(project_dir)

            init_py = REPO_ROOT / "src" / "claude_skills" / "vf-rtl" / "init.py"
            result = subprocess.run(
                [sys.executable, str(init_py), str(project_dir)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0,
                             f"init.py failed: {result.stdout}\n{result.stderr}")

            eda_env = project_dir / ".veriflow" / "eda_env.sh"
            self.assertTrue(eda_env.exists(), f"eda_env.sh missing: {eda_env}")
            content = eda_env.read_text()
            # Must export PYTHONPATH (so that subsequent `python -c "from state import ..."`
            # commands work without callers prepending PYTHONPATH=src).
            self.assertIn("PYTHONPATH", content,
                          f"eda_env.sh has no PYTHONPATH export:\n{content}")

    def test_eda_env_pythonpath_points_at_init_py_dir(self):
        """The exported PYTHONPATH must point at the directory containing
        init.py — that is where state.py and helper scripts live."""
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "proj"
            project_dir.mkdir()
            self._make_project(project_dir)

            init_py = REPO_ROOT / "src" / "claude_skills" / "vf-rtl" / "init.py"
            subprocess.run(
                [sys.executable, str(init_py), str(project_dir)],
                capture_output=True, text=True, timeout=30, check=True,
            )
            content = (project_dir / ".veriflow" / "eda_env.sh").read_text()
            self.assertIn(
                str(init_py.parent), content,
                "PYTHONPATH does not include the skill directory "
                f"({init_py.parent}). Found:\n{content}",
            )


if __name__ == "__main__":
    unittest.main()

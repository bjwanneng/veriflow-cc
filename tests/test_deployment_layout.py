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

            init_py = REPO_ROOT / "src" / "claude_skills" / "vf-rtl" / "core" / "init.py"
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

            init_py = REPO_ROOT / "src" / "claude_skills" / "vf-rtl" / "core" / "init.py"
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


class TestInstallDeploysCodeSubdirs(unittest.TestCase):
    """install.py must deploy the code subdirs (core/, runners/, analysis/,
    verify/, kb/) under ~/.claude/skills/vf-rtl/, not just flat top-level files.

    Drives the directory-restructure: SKILL.md references scripts by
    ${CLAUDE_SKILL_DIR}/<subdir>/<script>.py, so a flat deploy would leave
    every Stage 3/4 invocation broken at runtime.

    Runs install.py with HOME redirected to a tempdir so the real ~/.claude
    is never touched.
    """

    def _run_install(self, home: Path) -> subprocess.CompletedProcess:
        install_py = REPO_ROOT / "install.py"
        env = {**os.environ, "HOME": str(home)}
        return subprocess.run(
            [sys.executable, str(install_py)],
            capture_output=True, text=True, timeout=60, env=env,
        )

    def test_deploys_all_code_subdirs(self):
        with tempfile.TemporaryDirectory() as home:
            result = self._run_install(Path(home))
            self.assertEqual(result.returncode, 0,
                             f"install.py failed:\n{result.stdout}\n{result.stderr}")
            skill_dst = Path(home) / ".claude" / "skills" / "vf-rtl"
            for sub in ("core", "runners", "analysis", "verify", "kb"):
                sub_dst = skill_dst / sub
                self.assertTrue(sub_dst.is_dir(),
                                f"{sub}/ not deployed under {skill_dst}")

    def test_moved_scripts_land_in_subdirs_not_root(self):
        with tempfile.TemporaryDirectory() as home:
            result = self._run_install(Path(home))
            self.assertEqual(result.returncode, 0,
                             f"install.py failed:\n{result.stdout}\n{result.stderr}")
            skill_dst = Path(home) / ".claude" / "skills" / "vf-rtl"
            # Moved scripts must be in their subdirs...
            for rel in ("core/state.py", "runners/cocotb_runner.py",
                        "runners/iverilog_runner.py", "analysis/vcd2table.py",
                        "verify/candidate_selector.py", "kb/self_improve.py"):
                self.assertTrue(
                    (skill_dst / rel).exists(),
                    f"{rel} not deployed (expected at {skill_dst / rel})",
                )
            # ...and NOT duplicated at the skill root (would shadow the subdir
            # copy and break ${CLAUDE_SKILL_DIR}/<subdir>/X.py resolution).
            for flat in ("state.py", "cocotb_runner.py", "iverilog_runner.py",
                         "vcd2table.py", "candidate_selector.py", "self_improve.py"):
                self.assertFalse(
                    (skill_dst / flat).exists(),
                    f"{flat} deployed flat at skill root (should be in a subdir)",
                )

    def test_skill_md_and_templates_still_deployed(self):
        with tempfile.TemporaryDirectory() as home:
            result = self._run_install(Path(home))
            self.assertEqual(result.returncode, 0,
                             f"install.py failed:\n{result.stdout}\n{result.stderr}")
            skill_dst = Path(home) / ".claude" / "skills" / "vf-rtl"
            self.assertTrue((skill_dst / "SKILL.md").exists(),
                            "SKILL.md not deployed to skill root")
            self.assertTrue((skill_dst / "templates").is_dir(),
                            "templates/ not deployed")


if __name__ == "__main__":
    unittest.main()

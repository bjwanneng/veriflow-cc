"""Install layout + init eda_env.sh contracts.

These tests verify the deployment surface that user projects depend on:

  install.py — must place veriflow_dsl/ under ~/.claude/skills/vf-rtl/ so
               that `python -m veriflow_dsl.<x>` works after install.

  init.py    — must export PYTHONPATH pointing at the skill directory in
               eda_env.sh, so any shell command that sources it can import
               veriflow_dsl without manual PATH wrangling.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestInstallSymlinksVeriflowDsl(unittest.TestCase):
    """install.py must place veriflow_dsl/ under the skill directory."""

    def _run_install(self, fake_home: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HOME"] = str(fake_home)
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "install.py")],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_veriflow_dsl_package_reachable_after_install(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            result = self._run_install(fake_home)
            self.assertEqual(
                result.returncode, 0,
                f"install.py failed: {result.stdout}\n{result.stderr}",
            )

            skill_dir = fake_home / ".claude" / "skills" / "vf-rtl"
            self.assertTrue(skill_dir.is_dir(), f"skill dir missing: {skill_dir}")

            dsl_dir = skill_dir / "veriflow_dsl"
            self.assertTrue(
                dsl_dir.exists(),
                f"veriflow_dsl/ not present at {dsl_dir} after install",
            )
            self.assertTrue(
                (dsl_dir / "__init__.py").exists(),
                f"veriflow_dsl/__init__.py not reachable at {dsl_dir}",
            )
            self.assertTrue(
                (dsl_dir / "trace_export.py").exists(),
                "trace_export.py not in installed veriflow_dsl/",
            )

    def test_python_can_import_veriflow_dsl_from_skill_dir(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            result = self._run_install(fake_home)
            self.assertEqual(result.returncode, 0)

            skill_dir = fake_home / ".claude" / "skills" / "vf-rtl"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(skill_dir)
            check = subprocess.run(
                [sys.executable, "-c",
                 "from veriflow_dsl import RegT, reg_next; "
                 "from veriflow_dsl.trace_export import export_trace; "
                 "print('OK')"],
                capture_output=True, text=True, env=env, timeout=10,
            )
            self.assertEqual(
                check.returncode, 0,
                f"veriflow_dsl import failed via PYTHONPATH={skill_dir}\n"
                f"stdout={check.stdout}\nstderr={check.stderr}",
            )

    def test_uninstall_removes_veriflow_dsl(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            self._run_install(fake_home)
            env = os.environ.copy()
            env["HOME"] = str(fake_home)
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "install.py"), "--uninstall"],
                capture_output=True, text=True, env=env, timeout=30,
            )
            self.assertEqual(result.returncode, 0,
                             f"uninstall failed: {result.stdout}\n{result.stderr}")
            dsl_dir = fake_home / ".claude" / "skills" / "vf-rtl" / "veriflow_dsl"
            self.assertFalse(
                dsl_dir.exists(),
                f"veriflow_dsl/ still present after --uninstall: {dsl_dir}",
            )


class TestInitWritesPythonpath(unittest.TestCase):
    """init.py must write a PYTHONPATH= line into eda_env.sh so that
    `source eda_env.sh` makes `import veriflow_dsl` work without per-call
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
            # Must export PYTHONPATH (so that subsequent `python -m veriflow_dsl.*`
            # commands work without callers prepending PYTHONPATH=src).
            self.assertIn("PYTHONPATH", content,
                          f"eda_env.sh has no PYTHONPATH export:\n{content}")

    def test_eda_env_pythonpath_points_at_init_py_dir(self):
        """The exported PYTHONPATH must point at the directory containing
        init.py — that is where install.py also drops veriflow_dsl/."""
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

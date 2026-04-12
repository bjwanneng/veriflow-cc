"""Lint Agent - 调用iverilog检查RTL语法，纯EDA，无LLM"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class LintAgent(BaseAgent):
    stage = "lint"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        rtl_dir = project_dir / "workspace" / "rtl"

        if not rtl_dir.exists():
            return {
                "success": False,
                "artifacts": [],
                "errors": [f"RTL目录不存在: {rtl_dir}"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
            }

        rtl_files = sorted(rtl_dir.glob("*.v"))
        if not rtl_files:
            return {
                "success": False,
                "artifacts": [],
                "errors": ["workspace/rtl/ 中没有找到 .v 文件"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
            }

        all_errors = []
        all_warnings = []
        checked = []

        for vfile in rtl_files:
            ok, stdout, stderr = self.run_eda(
                ["iverilog", "-Wall", "-tnull", str(vfile)],
                timeout=30,
            )
            checked.append(str(vfile))
            output = (stdout + stderr).strip()

            if not ok or "error" in output.lower():
                # 提取错误行
                for line in output.splitlines():
                    if "error" in line.lower():
                        all_errors.append(f"{vfile.name}: {line.strip()}")
                    elif "warning" in line.lower():
                        all_warnings.append(f"{vfile.name}: {line.strip()}")
            else:
                for line in output.splitlines():
                    if "warning" in line.lower():
                        all_warnings.append(f"{vfile.name}: {line.strip()}")

        success = len(all_errors) == 0
        return {
            "success": success,
            "artifacts": checked,
            "errors": all_errors,
            "warnings": all_warnings,
            "metrics": {
                "files_checked": len(rtl_files),
                "error_count": len(all_errors),
                "warning_count": len(all_warnings),
            },
            "raw_output": f"Checked {len(rtl_files)} files: {len(all_errors)} errors, {len(all_warnings)} warnings",
        }


if __name__ == "__main__":
    LintAgent().run()

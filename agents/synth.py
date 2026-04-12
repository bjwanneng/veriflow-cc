"""Synth Agent - 调用Yosys综合，纯EDA，无LLM"""

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class SynthAgent(BaseAgent):
    stage = "synth"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        rtl_dir = project_dir / "workspace" / "rtl"
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        rtl_files = sorted(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
        if not rtl_files:
            return {"success": False, "artifacts": [], "errors": ["无RTL文件"], "warnings": [], "metrics": {}, "raw_output": ""}

        # 构建Yosys脚本
        read_cmds = "\n".join(f"read_verilog {f}" for f in rtl_files)
        yosys_script = f"""{read_cmds}
synth -top {rtl_files[0].stem}
stat
"""
        report_path = docs_dir / "synth_report.json"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".ys", delete=False, encoding="utf-8") as f:
            f.write(yosys_script)
            script_path = f.name

        ok, stdout, stderr = self.run_eda(["yosys", "-p", yosys_script], timeout=120)
        output = stdout + stderr

        errors = []
        if not ok:
            for line in output.splitlines():
                if "error" in line.lower():
                    errors.append(line.strip())

        # 解析stat输出
        metrics = self._parse_stat(output)
        report = {"success": ok and not errors, "metrics": metrics, "raw_output": output[:3000]}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return {
            "success": ok and not errors,
            "artifacts": [str(report_path)],
            "errors": errors,
            "warnings": [],
            "metrics": metrics,
            "raw_output": output[:2000],
        }

    def _parse_stat(self, output: str) -> dict:
        metrics = {}
        for line in output.splitlines():
            m = re.search(r"Number of cells:\s+(\d+)", line)
            if m:
                metrics["num_cells"] = int(m.group(1))
            m = re.search(r"Number of wires:\s+(\d+)", line)
            if m:
                metrics["num_wires"] = int(m.group(1))
        return metrics


if __name__ == "__main__":
    SynthAgent().run()

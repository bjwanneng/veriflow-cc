"""Sim Agent - 调用iverilog+vvp仿真，纯EDA，无LLM"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class SimAgent(BaseAgent):
    stage = "sim"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        rtl_dir = project_dir / "workspace" / "rtl"
        tb_dir = project_dir / "workspace" / "tb"

        rtl_files = sorted(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
        tb_files = sorted(tb_dir.glob("tb_*.v")) if tb_dir.exists() else []

        if not rtl_files:
            return {"success": False, "artifacts": [], "errors": ["无RTL文件"], "warnings": [], "metrics": {}, "raw_output": ""}
        if not tb_files:
            return {"success": False, "artifacts": [], "errors": ["无testbench文件"], "warnings": [], "metrics": {}, "raw_output": ""}

        all_errors = []
        all_warnings = []
        sim_out_dir = project_dir / "workspace" / "sim"
        sim_out_dir.mkdir(parents=True, exist_ok=True)

        for tb in tb_files:
            vvp_out = sim_out_dir / f"{tb.stem}.vvp"

            # 编译
            compile_files = [str(f) for f in rtl_files] + [str(tb)]
            ok, stdout, stderr = self.run_eda(
                ["iverilog", "-o", str(vvp_out)] + compile_files,
                timeout=60,
            )
            if not ok:
                for line in (stdout + stderr).splitlines():
                    if "error" in line.lower():
                        all_errors.append(f"{tb.name}: {line.strip()}")
                continue

            # 仿真
            ok, stdout, stderr = self.run_eda(["vvp", str(vvp_out)], timeout=60)
            output = stdout + stderr
            if not ok or "FAIL" in output.upper():
                for line in output.splitlines():
                    if any(kw in line.upper() for kw in ("FAIL", "ERROR", "ASSERT")):
                        all_errors.append(f"{tb.name}: {line.strip()}")
            else:
                for line in output.splitlines():
                    if "warning" in line.lower():
                        all_warnings.append(f"{tb.name}: {line.strip()}")

        return {
            "success": len(all_errors) == 0,
            "artifacts": [str(f) for f in sim_out_dir.glob("*.vvp")],
            "errors": all_errors,
            "warnings": all_warnings,
            "metrics": {"tb_count": len(tb_files), "error_count": len(all_errors)},
            "raw_output": f"Simulated {len(tb_files)} testbenches",
        }


if __name__ == "__main__":
    SimAgent().run()

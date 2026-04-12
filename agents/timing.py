"""Timing Agent - 生成时序模型和testbench"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class TimingAgent(BaseAgent):
    stage = "timing"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        docs_dir = project_dir / "workspace" / "docs"
        tb_dir = project_dir / "workspace" / "tb"
        docs_dir.mkdir(parents=True, exist_ok=True)
        tb_dir.mkdir(parents=True, exist_ok=True)

        spec = self.read_file(docs_dir / "spec.json")

        if not spec:
            return {
                "success": False,
                "stage": "timing",
                "artifacts": [],
                "errors": ["spec.json不存在"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "microarch"
            }

        # 渲染prompt
        prompt = self.render_prompt("timing", SPEC_JSON=spec[:5000])

        try:
            output = self.call_claude(prompt)
        except Exception as e:
            return {
                "success": False,
                "stage": "timing",
                "artifacts": [],
                "errors": [str(e)],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "microarch"
            }

        artifacts = []
        errors = []

        # 提取并写入timing_model.yaml
        yaml_match = re.search(r"```yaml:(\S+)\n(.*?)```", output, re.DOTALL)
        if yaml_match:
            yaml_content = yaml_match.group(2).strip()
            yaml_path = project_dir / yaml_match.group(1)
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            self.write_file(yaml_path, yaml_content)
            artifacts.append(str(yaml_path))
        else:
            errors.append("未找到timing_model.yaml输出")

        # 提取并写入testbench
        tb_matches = re.findall(r"```verilog:(\S+\.v)\n(.*?)```", output, re.DOTALL)
        for rel_path, code in tb_matches:
            filename = Path(rel_path).name
            if re.match(r"^[\w.-]+\.v$", filename):
                tb_path = tb_dir / filename
                self.write_file(tb_path, code.strip())
                artifacts.append(str(tb_path))

        if not tb_matches:
            errors.append("未找到testbench输出")

        success = len(errors) == 0
        return {
            "success": success,
            "stage": "timing",
            "artifacts": artifacts,
            "errors": errors,
            "warnings": [],
            "metrics": {"artifact_count": len(artifacts)},
            "raw_output": f"Generated {len(artifacts)} files",
            "summary": f"Generated {len(artifacts)} files: {', '.join(Path(a).name for a in artifacts)}" if success else "",
            "next_stage": "coder" if success else "microarch"
        }


if __name__ == "__main__":
    TimingAgent().run()

"""MicroArch Agent - 设计模块微架构"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class MicroArchAgent(BaseAgent):
    stage = "microarch"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        spec = self.read_file(docs_dir / "spec.json")
        if not spec:
            return {
                "success": False,
                "stage": "microarch",
                "artifacts": [],
                "errors": ["spec.json不存在"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "architect"
            }

        requirement = self.read_file(project_dir / "requirement.md") or "(No requirement.md)"

        # 渲染prompt
        prompt = self.render_prompt(
            "microarch",
            SPEC_JSON=spec[:5000],
            REQUIREMENT=requirement[:3000],
            MODE="standard"
        )

        try:
            output = self.call_claude(prompt)
        except Exception as e:
            return {
                "success": False,
                "stage": "microarch",
                "artifacts": [],
                "errors": [str(e)],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "architect"
            }

        if len(output.strip()) < 50:
            return {
                "success": False,
                "stage": "microarch",
                "artifacts": [],
                "errors": ["LLM输出内容过少"],
                "warnings": [],
                "metrics": {},
                "raw_output": output,
                "next_stage": "architect"
            }

        out_path = docs_dir / "micro_arch.md"
        self.write_file(out_path, output)

        return {
            "success": True,
            "stage": "microarch",
            "artifacts": [str(out_path)],
            "errors": [],
            "warnings": [],
            "metrics": {"doc_length": len(output)},
            "raw_output": f"Generated micro_arch.md ({len(output)} chars)",
            "summary": f"micro_arch.md ({len(output)} chars): {output[:120].splitlines()[0].strip('# ')}",
            "next_stage": "timing"
        }


if __name__ == "__main__":
    MicroArchAgent().run()

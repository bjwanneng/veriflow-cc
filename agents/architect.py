"""Architect Agent - 分析需求，生成spec.json"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class ArchitectAgent(BaseAgent):
    stage = "architect"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        docs_dir = project_dir / "workspace" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        requirement = self.read_file(project_dir / "requirement.md")
        if not requirement:
            return {
                "success": False,
                "stage": "architect",
                "artifacts": [],
                "errors": ["requirement.md不存在"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "abort"
            }

        # 读取context/目录下的参考文档
        context_dir = project_dir / "context"
        context_docs = ""
        if context_dir.exists():
            for md_file in sorted(context_dir.glob("*.md")):
                content = self.read_file(md_file)
                context_docs += f"\n\n### {md_file.name}\n{content[:1000]}"

        # 渲染prompt
        prompt = self.render_prompt(
            "architect",
            REQUIREMENT=requirement[:5000],
            CONTEXT_DOCS=context_docs[:3000] if context_docs else "(No context files)",
            FREQUENCY_MHZ="100"
        )

        try:
            llm_output = self.call_claude(prompt)
        except Exception as e:
            return {
                "success": False,
                "stage": "architect",
                "artifacts": [],
                "errors": [str(e)],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "abort"
            }

        # 提取JSON
        spec = self._extract_json(llm_output)
        if not spec:
            return {
                "success": False,
                "stage": "architect",
                "artifacts": [],
                "errors": ["LLM输出无法解析为JSON"],
                "warnings": [],
                "metrics": {},
                "raw_output": llm_output[:300],
                "next_stage": "abort"
            }

        spec_path = docs_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "success": True,
            "stage": "architect",
            "artifacts": [str(spec_path)],
            "errors": [],
            "warnings": [],
            "metrics": {"module_name": spec.get("module_name", "")},
            "raw_output": f"Generated spec.json for {spec.get('module_name', '?')}",
            "summary": f"{spec.get('module_name', '?')}: {spec.get('description', 'RTL design spec generated')}",
            "next_stage": "microarch"
        }

    def _extract_json(self, text: str) -> dict | None:
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 提取```json```块
        m = re.search(r"```json\n(.*?)```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 提取第一个{...}
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None


if __name__ == "__main__":
    ArchitectAgent().run()

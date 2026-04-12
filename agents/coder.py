"""Coder Agent - 调用Claude生成RTL代码"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class CoderAgent(BaseAgent):
    stage = "coder"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        docs_dir = project_dir / "workspace" / "docs"
        rtl_dir = project_dir / "workspace" / "rtl"
        rtl_dir.mkdir(parents=True, exist_ok=True)

        spec = self.read_file(docs_dir / "spec.json")
        if not spec:
            return {
                "success": False,
                "stage": "coder",
                "artifacts": [],
                "errors": ["spec.json不存在"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "timing"
            }

        timing = self.read_file(docs_dir / "timing_model.yaml") or "(No timing model)"
        microarch = self.read_file(docs_dir / "micro_arch.md") or "(No microarch)"
        requirement = self.read_file(project_dir / "requirement.md") or "(No requirement)"

        # 获取supervisor hint（如果有）
        hint = context.get("supervisor_hint", "")
        if not hint:
            hint = ""

        # 渲染prompt
        prompt = self.render_prompt(
            "coder",
            SUPERVISOR_HINT=hint
        )

        # 由于coder.md没有其他变量占位符，需要在prompt后面附加输入文件内容
        # 将spec、timing、microarch、requirement内容附加到prompt后面
        prompt += f"""

## Reference Documents

### spec.json
{spec[:5000]}

### timing_model.yaml
{timing[:3000]}

### micro_arch.md
{microarch[:3000]}

### requirement.md
{requirement[:2000]}
"""

        try:
            llm_output = self.call_claude(prompt, timeout=300)
        except Exception as e:
            return {
                "success": False,
                "stage": "coder",
                "artifacts": [],
                "errors": [str(e)],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "debugger"
            }

        # 解析LLM输出，提取Verilog代码块
        artifacts = self._extract_and_write_verilog(llm_output, rtl_dir)

        if not artifacts:
            return {
                "success": False,
                "stage": "coder",
                "artifacts": [],
                "errors": ["LLM输出中未找到Verilog代码块"],
                "warnings": [],
                "metrics": {},
                "raw_output": llm_output[:500],
                "next_stage": "debugger"
            }

        return {
            "success": True,
            "stage": "coder",
            "artifacts": artifacts,
            "errors": [],
            "warnings": [],
            "metrics": {"modules_generated": len(artifacts)},
            "raw_output": f"Generated {len(artifacts)} RTL files",
            "summary": f"Generated {len(artifacts)} RTL modules: {', '.join(Path(a).name for a in artifacts)}",
            "next_stage": "skill_d"
        }

    def _extract_and_write_verilog(self, text: str, rtl_dir: Path) -> list[str]:
        """从LLM输出中提取Verilog代码块并写入文件"""
        artifacts = []

        # 匹配 ```verilog:path/to/file.v ... ``` 格式
        pattern = r"```verilog:(\S+\.v)\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)

        if matches:
            for rel_path, code in matches:
                # 只取文件名，忽略路径（安全考虑）
                filename = Path(rel_path).name
                out_path = rtl_dir / filename
                self.write_file(out_path, code.strip())
                artifacts.append(str(out_path))
            return artifacts

        # Fallback: 匹配普通 ```verilog ... ``` 块，按module名存文件
        pattern2 = r"```(?:verilog|systemverilog)\n(.*?)```"
        matches2 = re.findall(pattern2, text, re.DOTALL)
        for code in matches2:
            code = code.strip()
            m = re.search(r"module\s+(\w+)", code)
            if m:
                module_name = m.group(1)
                # 简单过滤：只保留合法模块名
                if re.match(r"^[a-zA-Z_]\w*$", module_name):
                    out_path = rtl_dir / f"{module_name}.v"
                    self.write_file(out_path, code)
                    artifacts.append(str(out_path))

        return artifacts


if __name__ == "__main__":
    CoderAgent().run()

"""Debugger Agent - 调用Claude分析错误并修复RTL"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent


class DebuggerAgent(BaseAgent):
    stage = "debugger"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        rtl_dir = project_dir / "workspace" / "rtl"
        docs_dir = project_dir / "workspace" / "docs"

        # 读取当前RTL文件
        rtl_contents = self._read_rtl_files(rtl_dir)
        if not rtl_contents:
            return {
                "success": False,
                "stage": "debugger",
                "artifacts": [],
                "warnings": [],
                "errors": ["workspace/rtl/中无RTL文件可修复"],
                "metrics": {},
                "raw_output": "",
                "next_stage": "abort"
            }

        # 整理错误历史
        error_history_map = context.get("error_history", {})
        source = context.get("feedback_source", "unknown")
        source_errors = error_history_map.get(source, [])
        history_text = "\n---\n".join(
            str(e.get("errors", e) if isinstance(e, dict) else e)
            for e in source_errors[-3:]
        )

        error_log = context.get("error_log", "")
        if not error_log and source_errors:
            last = source_errors[-1]
            error_log = str(last.get("errors", last) if isinstance(last, dict) else last)

        hint = context.get("supervisor_hint", "")

        # 读取timing_model.yaml（debugger需要）
        timing_yaml = self.read_file(docs_dir / "timing_model.yaml") or "(No timing model)"

        # 渲染prompt
        prompt = self.render_prompt(
            "debugger",
            ERROR_LOG=error_log[:5000],
            ERROR_TYPE=source,
            RTL_CONTENT=rtl_contents[:8000],
            TIMING_MODEL_YAML=timing_yaml[:2000],
            ERROR_HISTORY=history_text[:3000],
            SUPERVISOR_HINT=hint
        )

        try:
            llm_output = self.call_claude(prompt, timeout=300)
        except Exception as e:
            return {
                "success": False,
                "stage": "debugger",
                "artifacts": [],
                "errors": [str(e)],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
                "next_stage": "abort"
            }

        # 提取并写入修复后的代码
        fixed = self._extract_and_write_verilog(llm_output, rtl_dir)

        if not fixed:
            return {
                "success": False,
                "stage": "debugger",
                "artifacts": [],
                "errors": ["LLM输出中未找到修复后的Verilog代码"],
                "warnings": [],
                "metrics": {},
                "raw_output": llm_output[:500],
                "next_stage": "abort"
            }

        # 根据错误来源决定回滚目标
        # 这个决策可以由LLM在输出中指定，或者用机械规则
        from router import categorize_error, rollback_target
        error_category = categorize_error(context.get("error_log", "").split("\n"))
        rollback = rollback_target(error_category, source)

        return {
            "success": True,
            "stage": "debugger",
            "artifacts": fixed,
            "errors": [],
            "warnings": [],
            "metrics": {
                "files_fixed": len(fixed),
                "error_category": error_category,
                "rollback_target": rollback
            },
            "raw_output": f"Fixed {len(fixed)} RTL files",
            "summary": f"Fixed {len(fixed)} files ({error_category}), rollback to {rollback}",
            "next_stage": rollback  # 回滚到目标stage重跑
        }

    def _read_rtl_files(self, rtl_dir: Path) -> str:
        """读取所有RTL文件内容"""
        if not rtl_dir.exists():
            return ""
        parts = []
        for vfile in sorted(rtl_dir.glob("*.v")):
            content = self.read_file(vfile)
            parts.append(f"// === {vfile.name} ===\n{content}")
        return "\n\n".join(parts)

    def _extract_and_write_verilog(self, text: str, rtl_dir: Path) -> list[str]:
        artifacts = []

        pattern = r"```verilog:(\S+\.v)\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            for rel_path, code in matches:
                filename = Path(rel_path).name
                if re.match(r"^[\w.-]+\.v$", filename):
                    out_path = rtl_dir / filename
                    self.write_file(out_path, code.strip())
                    artifacts.append(str(out_path))
            return artifacts

        pattern2 = r"```(?:verilog|systemverilog)\n(.*?)```"
        matches2 = re.findall(pattern2, text, re.DOTALL)
        for code in matches2:
            code = code.strip()
            m = re.search(r"module\s+(\w+)", code)
            if m:
                module_name = m.group(1)
                if re.match(r"^[a-zA-Z_]\w*$", module_name):
                    out_path = rtl_dir / f"{module_name}.v"
                    self.write_file(out_path, code)
                    artifacts.append(str(out_path))

        return artifacts


if __name__ == "__main__":
    DebuggerAgent().run()

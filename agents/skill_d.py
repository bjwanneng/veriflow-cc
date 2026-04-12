"""SkillD Agent - RTL代码质量预检（静态+LLM），在EDA之前拦截低质量代码"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _base import BaseAgent

QUALITY_THRESHOLD = 0.5

PROMPT = """你是一名RTL代码审查专家。

## 任务
审查以下Verilog代码，识别硬件设计禁忌。

## RTL代码
{rtl_contents}

## 检查项
1. 锁存器推断（latch inference）- 组合逻辑中missing case/if分支
2. 组合逻辑环路（combinational loop）
3. 未初始化寄存器在复位路径中的使用
4. 不可综合构造（initial块用于逻辑、$display等）
5. 时钟域交叉问题（多时钟域无同步）

## 输出格式（JSON）
```json
{{
    "score": 0.85,
    "issues": [
        {{"severity": "error|warning|info", "description": "问题描述", "file": "文件名"}}
    ],
    "passed": true
}}
```

score范围0-1，issues为空时passed=true，有error时passed=false。
"""


class SkillDAgent(BaseAgent):
    stage = "skill_d"

    def execute(self, context: dict) -> dict:
        project_dir = Path(context["project_dir"])
        rtl_dir = project_dir / "workspace" / "rtl"

        rtl_files = sorted(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
        if not rtl_files:
            return {"success": False, "artifacts": [], "errors": ["无RTL文件"], "warnings": [], "metrics": {}, "raw_output": ""}

        # 静态分析（不需要LLM）
        static_score, static_issues = self._static_check(rtl_files)

        # 读取RTL内容供LLM分析
        rtl_contents = "\n\n".join(
            f"// === {f.name} ===\n{self.read_file(f)[:1500]}"
            for f in rtl_files
        )

        # LLM分析
        llm_score = static_score
        llm_issues = []
        try:
            llm_output = self.call_claude(PROMPT.format(rtl_contents=rtl_contents[:4000]), timeout=120)
            llm_result = self._extract_json(llm_output)
            if llm_result:
                llm_score = float(llm_result.get("score", static_score))
                llm_issues = llm_result.get("issues", [])
        except Exception:
            pass  # LLM失败时只用静态分析结果

        # 综合评分
        final_score = round(static_score * 0.4 + llm_score * 0.6, 3)
        all_issues = static_issues + llm_issues
        errors = [i["description"] for i in all_issues if i.get("severity") == "error"]
        warnings = [i["description"] for i in all_issues if i.get("severity") == "warning"]

        passed = final_score >= QUALITY_THRESHOLD and not errors

        return {
            "success": passed,
            "stage": "skill_d",
            "artifacts": [],
            "errors": errors if not passed else [],
            "warnings": warnings,
            "metrics": {
                "quality_score": final_score,
                "static_score": static_score,
                "llm_score": llm_score,
                "issue_count": len(all_issues),
            },
            "raw_output": f"Quality score: {final_score:.2f} ({'PASS' if passed else 'FAIL'})",
            "summary": f"Quality score: {final_score:.2f}, issues: {len(all_issues)}, {'PASS' if passed else 'FAIL'}",
            "next_stage": "lint" if passed else "coder"
        }

    def _static_check(self, rtl_files: list[Path]) -> tuple[float, list]:
        """快速静态分析，不需要LLM"""
        issues = []
        total_score = 1.0

        for vfile in rtl_files:
            content = self.read_file(vfile)
            lines = content.splitlines()

            # 检查initial块（非testbench中不应有）
            if "initial " in content and "tb_" not in vfile.name:
                issues.append({"severity": "warning", "description": f"initial块可能不可综合", "file": vfile.name})
                total_score -= 0.05

            # 检查文件非空
            if len(content.strip()) < 20:
                issues.append({"severity": "error", "description": f"文件内容过少或为空", "file": vfile.name})
                total_score -= 0.3

            # 检查module/endmodule配对
            module_count = content.count("endmodule")
            if module_count == 0:
                issues.append({"severity": "error", "description": "缺少endmodule", "file": vfile.name})
                total_score -= 0.3

        return max(0.0, min(1.0, total_score)), issues

    def _extract_json(self, text: str) -> dict | None:
        import json
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"```json\n(.*?)```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None


if __name__ == "__main__":
    SkillDAgent().run()

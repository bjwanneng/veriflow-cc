"""
Agent基类 - 所有stage agent继承此类。

每个agent脚本的使用方式：
  echo '{"project_dir": "...", ...}' | python agents/xxx.py

输入：stdin读取JSON上下文
输出：写入 {project_dir}/.veriflow/stage_result_{stage}.json
"""

import json
import sys
import time
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """Agent基类"""

    stage: str = ""

    def run(self):
        """从stdin读取上下文，执行任务，将结果写入文件"""
        # 读取上下文
        try:
            context = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            self._write_result({"success": False, "errors": [f"Context parse error: {e}"]}, context={})
            sys.exit(1)

        project_dir = Path(context.get("project_dir", "."))
        result_path = project_dir / ".veriflow" / f"stage_result_{self.stage}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()

        # 前置检查
        ok, reason = self.check_prerequisites(str(project_dir), context)
        if not ok:
            result = {
                "success": False,
                "stage": self.stage,
                "artifacts": [],
                "errors": [f"前置检查失败: {reason}"],
                "warnings": [],
                "metrics": {},
                "raw_output": "",
            }
        else:
            try:
                result = self.execute(context)
            except Exception as e:
                import traceback
                result = {
                    "success": False,
                    "stage": self.stage,
                    "errors": [f"Unhandled exception: {e}", traceback.format_exc()[:1000]],
                    "artifacts": [],
                    "warnings": [],
                    "metrics": {},
                    "raw_output": "",
                }

        result["duration_s"] = time.perf_counter() - t0
        result["stage"] = self.stage

        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # 打印摘要到stderr（不影响stdout，方便调试）
        status = "✓" if result.get("success") else "✗"
        print(f"[{self.stage}] {status} ({result['duration_s']:.1f}s)", file=sys.stderr)
        if not result.get("success"):
            for err in result.get("errors", [])[:2]:
                print(f"  {err[:100]}", file=sys.stderr)

    def check_prerequisites(self, project_dir: str, context: dict = {}) -> tuple[bool, str]:
        """检查前置文件是否存在且有效。在 execute() 前调用。

        Args:
            project_dir: 项目根目录
            context: 额外上下文（debugger 需要 error_log 等）

        Returns:
            (ok, reason) — ok=True 表示可以执行
        """
        base = Path(project_dir)
        stage = self.stage

        if stage == "architect":
            req = base / "requirement.md"
            if not req.exists() or req.stat().st_size == 0:
                return False, "requirement.md 不存在或为空"
            return True, ""

        if stage == "microarch":
            spec = base / "workspace" / "docs" / "spec.json"
            if not spec.exists():
                return False, "spec.json 不存在 (需要先完成 architect)"
            try:
                json.loads(spec.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError):
                return False, "spec.json 不是有效的 JSON"
            return True, ""

        if stage == "timing":
            spec = base / "workspace" / "docs" / "spec.json"
            micro = base / "workspace" / "docs" / "micro_arch.md"
            if not spec.exists():
                return False, "spec.json 不存在"
            if not micro.exists() or micro.stat().st_size < 50:
                return False, "micro_arch.md 不存在或太短"
            return True, ""

        if stage == "coder":
            spec = base / "workspace" / "docs" / "spec.json"
            micro = base / "workspace" / "docs" / "micro_arch.md"
            timing = base / "workspace" / "docs" / "timing_model.yaml"
            missing = []
            if not spec.exists():
                missing.append("spec.json")
            if not micro.exists():
                missing.append("micro_arch.md")
            if not timing.exists():
                missing.append("timing_model.yaml")
            if missing:
                return False, f"缺少输入文件: {missing}"
            return True, ""

        if stage in ("skill_d", "lint"):
            rtl_dir = base / "workspace" / "rtl"
            rtl_files = list(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
            if not rtl_files:
                return False, f"rtl 目录中没有 .v 文件 (需要先完成 coder)"
            return True, ""

        if stage == "sim":
            rtl_dir = base / "workspace" / "rtl"
            tb_dir = base / "workspace" / "tb"
            rtl_files = list(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
            tb_files = list(tb_dir.glob("tb_*.v")) if tb_dir.exists() else []
            if not rtl_files:
                return False, "rtl 目录中没有 .v 文件"
            if not tb_files:
                return False, "tb 目录中没有 tb_*.v 文件"
            return True, ""

        if stage == "synth":
            rtl_dir = base / "workspace" / "rtl"
            rtl_files = list(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
            if not rtl_files:
                return False, "rtl 目录中没有 .v 文件"
            return True, ""

        if stage == "debugger":
            rtl_dir = base / "workspace" / "rtl"
            rtl_files = list(rtl_dir.glob("*.v")) if rtl_dir.exists() else []
            if not rtl_files:
                return False, "rtl 目录中没有 .v 文件（没有可调试的代码）"
            if not context.get("error_log") and not context.get("feedback_source"):
                return False, "缺少错误上下文（error_log 或 feedback_source）"
            return True, ""

        # 未知 stage — 不阻塞
        return True, ""

    @abstractmethod
    def execute(self, context: dict) -> dict:
        """
        执行stage逻辑。

        Args:
            context: 包含project_dir等信息的上下文字典

        Returns:
            结果字典，包含: success, artifacts, errors, warnings, metrics, raw_output
        """

    def call_claude(self, prompt: str, timeout: int = 300) -> str:
        """调用Claude CLI获取LLM响应"""
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {proc.stderr[:300]}")
        return proc.stdout.strip()

    def run_eda(self, cmd: list[str], cwd: str = None, timeout: int = 60) -> tuple[bool, str, str]:
        """运行EDA工具命令，返回(success, stdout, stderr)"""
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return proc.returncode == 0, proc.stdout, proc.stderr

    def read_file(self, path: str | Path) -> str:
        """安全读取文件"""
        p = Path(path)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str | Path, content: str):
        """写入文件，自动创建目录"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def render_prompt(self, prompt_name: str, **vars) -> str:
        """
        读取prompts/{prompt_name}.md，替换{{VAR}}变量。

        Args:
            prompt_name: prompts/目录下的文件名（不含.md后缀）
            **vars: 要替换的变量，如 REQUIREMENT="...", CONTEXT_DOCS="..."

        Returns:
            渲染后的prompt字符串
        """
        prompt_dir = Path(__file__).parent.parent / "prompts"
        template_path = prompt_dir / f"{prompt_name}.md"

        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")

        # 替换所有 {{VAR}} 占位符
        for key, val in vars.items():
            placeholder = "{{" + key + "}}"
            template = template.replace(placeholder, str(val))

        return template

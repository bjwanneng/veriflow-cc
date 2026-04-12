"""Pipeline状态管理 - 无依赖版本"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# 严格的执行顺序 — 不可跳过任何 stage
STAGE_ORDER = ["architect", "microarch", "timing", "coder", "skill_d", "lint", "sim", "synth"]

# 每个 stage 的前置依赖（必须全部完成才能执行该 stage）
STAGE_PREREQUISITES = {
    "architect": [],                                          # 无前置
    "microarch": ["architect"],                               # 需要 spec.json
    "timing":    ["architect", "microarch"],                  # 需要 spec + micro_arch
    "coder":     ["architect", "microarch", "timing"],        # 需要 spec + microarch + timing
    "skill_d":   ["coder"],                                   # 需要 RTL 代码
    "lint":      ["coder"],                                   # 需要 RTL 代码
    "sim":       ["coder", "lint"],                           # 需要 RTL + lint 通过
    "synth":     ["coder", "sim"],                            # 需要 RTL + sim 通过
}


def next_pending_stage(stages_completed: list) -> str | None:
    """返回第一个未完成的 stage。严格按 STAGE_ORDER 顺序，不可跳过。"""
    for stage in STAGE_ORDER:
        if stage not in stages_completed:
            return stage
    return None  # 全部完成


def can_execute(stage: str, stages_completed: list) -> tuple[bool, str]:
    """检查某个 stage 是否可以执行（前置依赖是否全部满足）。

    Returns:
        (can_run, reason) — can_run=True 表示可以执行
    """
    prereqs = STAGE_PREREQUISITES.get(stage, [])
    missing = [p for p in prereqs if p not in stages_completed]
    if missing:
        return False, f"前置 stage 未完成: {missing}"
    return True, ""


@dataclass
class PipelineState:
    """Pipeline状态 - 可序列化为JSON，由Claude Code主会话驱动"""

    project_dir: str

    current_stage: str = ""
    stages_completed: list = field(default_factory=list)
    stages_failed: list = field(default_factory=list)

    # 各stage输出摘要
    architect_output: Optional[dict] = None
    microarch_output: Optional[dict] = None
    timing_output: Optional[dict] = None
    coder_output: Optional[dict] = None
    skill_d_output: Optional[dict] = None
    lint_output: Optional[dict] = None
    sim_output: Optional[dict] = None
    synth_output: Optional[dict] = None
    debugger_output: Optional[dict] = None

    # 错误恢复
    retry_count: dict = field(default_factory=dict)
    error_history: dict = field(default_factory=dict)
    feedback_source: str = ""

    # 持久化上下文摘要 — 新会话读此字段即可恢复
    stage_summaries: dict = field(default_factory=dict)

    # 元数据
    start_time: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    def __post_init__(self):
        if isinstance(self.project_dir, Path):
            self.project_dir = str(self.project_dir)

    def mark_complete(self, stage: str, result: dict):
        """标记阶段完成。保存摘要用于上下文恢复。"""
        if stage in STAGE_PREREQUISITES:
            ok, reason = can_execute(stage, self.stages_completed)
            if not ok:
                import sys
                print(f"[WARNING] Stage '{stage}' 前置依赖未满足: {reason}", file=sys.stderr)
        if stage not in self.stages_completed:
            self.stages_completed.append(stage)
        setattr(self, f"{stage}_output", result)
        self.current_stage = stage
        self.last_updated = time.time()
        # Save summary for context recovery
        summary = result.get("summary", "")
        if summary:
            self.stage_summaries[stage] = summary

    def mark_failed(self, stage: str, result: dict):
        """标记阶段失败"""
        if stage not in self.stages_failed:
            self.stages_failed.append(stage)
        if stage not in self.error_history:
            self.error_history[stage] = []
        self.error_history[stage].append({
            "time": time.time(),
            "errors": result.get("errors", []),
        })
        setattr(self, f"{stage}_output", result)
        self.current_stage = stage
        self.feedback_source = stage
        self.last_updated = time.time()

    def inc_retry(self, stage: str):
        self.retry_count[stage] = self.retry_count.get(stage, 0) + 1

    def get_output(self, stage: str) -> Optional[dict]:
        return getattr(self, f"{stage}_output", None)

    def is_done(self, stage: str) -> bool:
        return stage in self.stages_completed

    def is_pipeline_complete(self) -> bool:
        return "synth" in self.stages_completed

    # ── 持久化 ──────────────────────────────────────────────────────────

    def save(self) -> Path:
        """保存状态到 .veriflow/pipeline_state.json"""
        d = Path(self.project_dir) / ".veriflow"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "pipeline_state.json"
        p.write_text(json.dumps(asdict(self), indent=2, default=str), encoding="utf-8")
        return p

    @classmethod
    def load(cls, project_dir: str) -> "PipelineState":
        """从文件加载，不存在则创建新状态"""
        p = Path(project_dir) / ".veriflow" / "pipeline_state.json"
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(**data)
        return cls(project_dir=project_dir)

    @classmethod
    def reset_stage(cls, state: "PipelineState", stage: str) -> "PipelineState":
        """清除某个stage及之后的完成记录，用于回滚重跑"""
        if stage not in STAGE_ORDER:
            return state
        idx = STAGE_ORDER.index(stage)
        to_remove = STAGE_ORDER[idx:]
        state.stages_completed = [s for s in state.stages_completed if s not in to_remove]
        state.stages_failed = [s for s in state.stages_failed if s not in to_remove]
        for s in to_remove:
            setattr(state, f"{s}_output", None)
            state.stage_summaries.pop(s, None)
        state.save()
        return state

    def next_stage(self) -> str | None:
        """返回下一个应该执行的 stage（严格按顺序，不可跳过）。"""
        return next_pending_stage(self.stages_completed)

    def validate_before_run(self, stage: str) -> tuple[bool, str]:
        """执行 stage 前的校验。必须在每次执行 stage 前调用。"""
        # 1. 检查是否严格按顺序
        expected = next_pending_stage(self.stages_completed)
        if stage != expected:
            if stage == "debugger":
                return True, ""  # debugger 是特殊 stage，不受顺序限制
            return False, f"顺序错误: 期望执行 '{expected}'，但尝试执行 '{stage}'。不可跳过 stage。"

        # 2. 检查前置依赖
        return can_execute(stage, self.stages_completed)

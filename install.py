#!/usr/bin/env python3
"""
VeriFlow-CC Installer

Symlinks to ~/.claude/:
  - skills/vf-rtl/SKILL.md   — Pipeline orchestration skill (/vf-rtl)
  - agents/vf-spec-golden.md      — spec.json + golden_model.py generation (Stage 1)
  - agents/vf-coder.md            — RTL code generation sub-agent (Stage 2)
  - agents/vf-tb-gen.md           — Testbench generation (Stage 2)
  - agents/vf-linter.md           — Lint sub-agent (Stage 4)
  - agents/vf-synthesizer.md      — Synthesis sub-agent (Stage 4)

Pipeline: spec_golden → codegen → verify_fix → lint_synth

After installation, use /vf-rtl <project_dir> in Claude Code to drive the full RTL design pipeline.
"""

import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CLAUDE_DIR = Path.home() / ".claude"

# --- Skill ---
SKILL_SRC_DIR = PROJECT_DIR / "src" / "claude_skills" / "vf-rtl"
SKILL_DST_DIR = CLAUDE_DIR / "skills" / "vf-rtl"
# Auto-scan skill source directory for installable files.
# Excludes: templates/ (handled separately), __pycache__/, .DS_Store,
# coding_style.md (handled separately as CODING_STYLE_SRC).
_SKILL_EXCLUDE = {"templates", "__pycache__", ".DS_Store", "coding_style_archive.md"}
SKILL_FILES = sorted(
    f.name for f in SKILL_SRC_DIR.iterdir()
    if f.is_file()
    and f.name not in _SKILL_EXCLUDE
    and not f.name.endswith(".pyc")
    and f.name != "coding_style.md"
)
TEMPLATES_DIR = "templates"
REFERENCES_DIR = "references"  # curated reference RTL snippets (reference_kb.py)

# Code subdirs hold the .py modules referenced by SKILL.md as
# ${CLAUDE_SKILL_DIR}/<subdir>/<script>.py. Each is deployed recursively so the
# source and deployed layouts match (no path divergence). templates/ and
# references/ are deployed by their own sections below; the rest are skipped.
_DATA_DIRS = {"templates", "references", "docs", "__pycache__", ".DS_Store"}
CODE_SUBDIRS = sorted(
    d.name for d in SKILL_SRC_DIR.iterdir()
    if d.is_dir() and d.name not in _DATA_DIRS
)

# Scripts that moved from the skill root into subdirs (directory restructure).
# Old flat installs leave orphaned copies at the skill root that would shadow
# the subdir versions; clean them on install and uninstall. Idempotent.
_MOVED_SCRIPTS = {
    "state.py", "rtl_utils.py", "init.py",
    "iverilog_runner.py", "cocotb_runner.py", "yosys_equiv.py",
    "benchmark_runner.py",
    "timing_diagnostic.py", "timing_contract_checker.py", "design_graph.py",
    "coverage_analyzer.py", "bug_pattern_match.py", "corner_case_generator.py",
    "expected_trace_gen.py", "vcd2table.py",
    "candidate_selector.py", "synth_score.py", "formal_prove.py",
    "knowledge_base.py", "reference_kb.py", "self_improve.py",
}

# Source for coding_style.md is now in the skill directory itself
CODING_STYLE_SRC = PROJECT_DIR / "src" / "claude_skills" / "vf-rtl" / "coding_style.md"
CODING_STYLE_DST_NAME = "coding_style.md"

# --- Sub-agents ---
# Agents are namespaced per skill: src/claude_agents/<skill>/<agent>.md.
# This keeps a future 2nd skill's agents from colliding in source.
AGENTS_DST_DIR = CLAUDE_DIR / "agents"
AGENTS_SRC_DIR = PROJECT_DIR / "src" / "claude_agents" / "vf-rtl"

AGENT_FILES = [
    "vf-spec-golden.md",
    "vf-coder.md",
    "vf-tb-gen.md",
    "vf-linter.md",
    "vf-synthesizer.md",
]


def main():
    if "--uninstall" in sys.argv:
        removed = 0

        # Remove old stage files (cleanup from 8-stage era)
        stages_dst = SKILL_DST_DIR / "stages"
        if stages_dst.exists():
            for f in stages_dst.iterdir():
                f.unlink()
                print(f"  Removed stage: {f.name}")
                removed += 1
            stages_dst.rmdir()

        # Remove skill (symlinks or copies)
        for name in [*SKILL_FILES, CODING_STYLE_DST_NAME]:
            dst = SKILL_DST_DIR / name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
                print(f"  Removed skill: vf-rtl/{name}")
                removed += 1
        # Remove templates
        templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
        if templates_dst.exists():
            for f in templates_dst.iterdir():
                if f.is_file() or f.is_symlink():
                    f.unlink()
                    print(f"  Removed template: {f.name}")
                    removed += 1
            templates_dst.rmdir()

        # Remove references (curated RTL snippets)
        references_dst = SKILL_DST_DIR / REFERENCES_DIR
        if references_dst.exists():
            for f in references_dst.iterdir():
                if f.is_file() or f.is_symlink():
                    f.unlink()
                    print(f"  Removed reference: {f.name}")
                    removed += 1
            references_dst.rmdir()

        # Remove code subdirs (core/, runners/, analysis/, verify/, kb/)
        for sub in CODE_SUBDIRS:
            sub_dst = SKILL_DST_DIR / sub
            if sub_dst.exists():
                for f in sub_dst.iterdir():
                    if f.is_file() or f.is_symlink():
                        f.unlink()
                        print(f"  Removed code: {sub}/{f.name}")
                        removed += 1
                try:
                    sub_dst.rmdir()
                except OSError:
                    pass

        # Remove orphaned flat copies of scripts that moved into subdirs
        # (migration from pre-restructure installs).
        for name in _MOVED_SCRIPTS:
            flat_dst = SKILL_DST_DIR / name
            if flat_dst.is_symlink() or flat_dst.is_file():
                flat_dst.unlink()
                print(f"  Removed moved-script (was flat): {name}")
                removed += 1

        # Remove legacy veriflow_dsl/ symlink (if present from older installs)
        legacy_dsl_dst = SKILL_DST_DIR / "veriflow_dsl"
        if legacy_dsl_dst.is_symlink() or legacy_dsl_dst.exists():
            if legacy_dsl_dst.is_symlink() or legacy_dsl_dst.is_file():
                legacy_dsl_dst.unlink()
            else:
                import shutil as _sh
                _sh.rmtree(legacy_dsl_dst)
            print("  Removed legacy package: veriflow_dsl/")
            removed += 1

        # Remove legacy anchors/ directory (if present from older installs)
        legacy_anchors_dst = SKILL_DST_DIR / "anchors"
        if legacy_anchors_dst.is_symlink() or legacy_anchors_dst.exists():
            if legacy_anchors_dst.is_symlink() or legacy_anchors_dst.is_file():
                legacy_anchors_dst.unlink()
            else:
                import shutil as _sh
                _sh.rmtree(legacy_anchors_dst)
            print("  Removed legacy anchors: anchors/")
            removed += 1

        if SKILL_DST_DIR.exists():
            try:
                SKILL_DST_DIR.rmdir()
                skills_dir = CLAUDE_DIR / "skills"
                if skills_dir.exists() and not any(skills_dir.iterdir()):
                    skills_dir.rmdir()
                    print("  Removed empty ~/.claude/skills/ directory")
            except OSError:
                pass

        # Remove agents (symlinks or copies)
        for name in AGENT_FILES:
            dst = AGENTS_DST_DIR / name
            if dst.exists() or dst.is_symlink():
                dst.unlink()
                print(f"  Removed agent: {name}")
                removed += 1

        if removed == 0:
            print("Nothing to uninstall.")
        else:
            print(f"\nUninstalled {removed} items from {CLAUDE_DIR}/")
        return 0

    # --- Install ---
    print(f"Installing to {CLAUDE_DIR}/\n")

    # 0. Clean up old agents that are no longer used
    LEGACY_AGENTS = [
        "vf-skill-d.md", "vf-lint.md", "vf-sim.md", "vf-synth.md",
        "vf-debugger.md", "vf-simulator.md",
        "vf-reviewer.md", "vf-microarch.md", "vf-timing.md",
        "vf-architect.md", "vf-spec-gen.md", "vf-golden-gen.md",
    ]
    cleaned = 0
    for name in LEGACY_AGENTS:
        dst = AGENTS_DST_DIR / name
        if dst.exists():
            dst.unlink()
            print(f"  [clean]  Removed legacy agent: {name}")
            cleaned += 1
    if cleaned:
        print()

    # 0b. Clean up old stage files from 8-stage era
    old_stages_dst = SKILL_DST_DIR / "stages"
    if old_stages_dst.exists():
        for f in old_stages_dst.iterdir():
            f.unlink()
            print(f"  [clean]  Removed old stage: {f.name}")
            cleaned += 1
        old_stages_dst.rmdir()
        if cleaned:
            print()

    def _symlink(src: Path, dst: Path, label: str):
        """Create or overwrite a symlink from dst → src.

        Warns if the existing file differs from the source (user may have
        local modifications that would be overwritten).
        """
        if dst.exists() or dst.is_symlink():
            # Check if existing content differs from source
            if dst.is_file() and not dst.is_symlink() and src.is_file():
                try:
                    if dst.read_text(encoding="utf-8") != src.read_text(encoding="utf-8"):
                        print(f"  [warn]   Overwriting modified: {dst} (content differs from source)")
                except Exception:
                    pass  # binary file or encoding issue — just overwrite
            dst.unlink()
        dst.symlink_to(src.resolve())
        print(f"  [{label}]  {src.name}  →  {dst}")

    # 1. Install skill (symlink: SKILL.md + state.py + support files)
    SKILL_DST_DIR.mkdir(parents=True, exist_ok=True)
    skill_installed = 0
    for name in SKILL_FILES:
        src = SKILL_SRC_DIR / name
        dst = SKILL_DST_DIR / name
        if src.exists():
            _symlink(src, dst, "skill")
            skill_installed += 1
        else:
            print(f"  [skip]   vf-rtl/{name} not found at {src}")

    # 1b. Install coding_style.md (symlink)
    if CODING_STYLE_SRC.exists():
        dst = SKILL_DST_DIR / CODING_STYLE_DST_NAME
        _symlink(CODING_STYLE_SRC, dst, "skill")
        skill_installed += 1
    else:
        print(f"  [skip]   vf-rtl/{CODING_STYLE_DST_NAME} not found at {CODING_STYLE_SRC}")

    # 1c. Install templates (symlink each template file)
    templates_src = SKILL_SRC_DIR / TEMPLATES_DIR
    templates_dst = SKILL_DST_DIR / TEMPLATES_DIR
    if templates_src.exists():
        templates_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(templates_src.iterdir()):
            if f.is_file():
                dst = templates_dst / f.name
                _symlink(f, dst, "tmpl")
                skill_installed += 1
    else:
        print(f"  [skip]   vf-rtl/{TEMPLATES_DIR}/ not found at {templates_src}")

    # 1c-bis. Install references (curated RTL snippets for reference_kb.py)
    references_src = SKILL_SRC_DIR / REFERENCES_DIR
    references_dst = SKILL_DST_DIR / REFERENCES_DIR
    if references_src.exists():
        references_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(references_src.iterdir()):
            if f.is_file():
                dst = references_dst / f.name
                _symlink(f, dst, "ref")
                skill_installed += 1
    else:
        print(f"  [skip]   vf-rtl/{REFERENCES_DIR}/ not found at {references_src}")

    # 1c-ter. Install code subdirs (core/, runners/, analysis/, verify/, kb/).
    # Each subdir's modules are symlinked into ~/.claude/skills/vf-rtl/<subdir>/
    # so SKILL.md's ${CLAUDE_SKILL_DIR}/<subdir>/<script>.py refs resolve.
    for sub in CODE_SUBDIRS:
        sub_src = SKILL_SRC_DIR / sub
        sub_dst = SKILL_DST_DIR / sub
        sub_dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(sub_src.iterdir()):
            if f.is_file() and not f.name.endswith(".pyc") and f.name != ".DS_Store":
                _symlink(f, sub_dst / f.name, "code")
                skill_installed += 1

    # 1c-quater. Migration: remove orphaned flat copies of scripts that moved
    # into subdirs (from pre-restructure installs). Idempotent no-op on fresh
    # installs; prevents the old flat copy shadowing the new subdir version.
    for name in _MOVED_SCRIPTS:
        flat_dst = SKILL_DST_DIR / name
        if flat_dst.is_symlink() or flat_dst.is_file():
            flat_dst.unlink()
            print(f"  [clean]  Removed moved-script (was flat): {name}")

    # 1d. Clean up legacy veriflow_dsl/ and anchors/ from older installs.
    # These directories were part of the v2 DSL architecture that has been
    # retired; if they exist from a previous install they must go.
    for legacy_name in ("veriflow_dsl", "anchors"):
        legacy_dst = SKILL_DST_DIR / legacy_name
        if legacy_dst.is_symlink() or legacy_dst.is_file():
            legacy_dst.unlink()
            print(f"  [clean]  Removed legacy {legacy_name}/")
        elif legacy_dst.is_dir():
            import shutil as _sh
            _sh.rmtree(legacy_dst)
            print(f"  [clean]  Removed legacy {legacy_name}/")

    # 2. Install sub-agents (symlink)
    AGENTS_DST_DIR.mkdir(parents=True, exist_ok=True)
    installed = 0
    missing = 0
    for name in AGENT_FILES:
        src = AGENTS_SRC_DIR / name
        dst = AGENTS_DST_DIR / name
        if not src.exists():
            print(f"  [skip]   {name}  (source not found)")
            missing += 1
            continue
        _symlink(src, dst, "agent")
        installed += 1

    print(f"\n{'='*50}")
    print(f"  Installed: {skill_installed} skill files + {installed} agents")
    if missing:
        print(f"  Skipped: {missing} (source files missing)")
    print(f"{'='*50}")

    # 3. Post-install verification
    print("\n[verify] Running post-install checks...")
    verify_errors = []

    # 3a. Check agent tools field format (must be comma-separated, not YAML list)
    for agent_name in AGENT_FILES:
        agent_dst = AGENTS_DST_DIR / agent_name
        if agent_dst.exists():
            content = agent_dst.read_text(encoding="utf-8")
            # Detect YAML list format (bad): "tools:\n  - read"
            if "\ntools:\n  -" in content or "\ntools:\n- " in content:
                verify_errors.append(
                    f"  [FAIL] {agent_name}: 'tools' field uses YAML list format — "
                    f"must be comma-separated (e.g. 'tools: Read, Write, Glob, Grep, Bash'). "
                    f"See GitHub #12392."
                )
            elif re.search(r'tools:\s*\w+.*,\s*\w+', content):
                print(f"  [OK]   {agent_name}: tools field format correct")
            else:
                verify_errors.append(
                    f"  [WARN] {agent_name}: could not confirm 'tools' field format — "
                    f"verify manually that it is comma-separated"
                )
        else:
            verify_errors.append(f"  [FAIL] {agent_name} not found at {agent_dst}")

    # 3b. Check templates directory
    expected_templates = [
        "spec_template.json",
        "golden_model_template.py",
        "tb_integration_template.v",
        "cocotb_template.py",
    ]
    for tname in expected_templates:
        tfile = templates_dst / tname
        if tfile.exists():
            print(f"  [OK]   templates/{tname} present")
        else:
            verify_errors.append(f"  [FAIL] templates/{tname} missing at {tfile}")

    # 3c. Check critical scripts are present in their subdirs (post-restructure)
    critical_scripts = [
        ("core/state.py", "state.py"),
        ("analysis/vcd2table.py", "vcd2table.py"),
        ("runners/cocotb_runner.py", "cocotb_runner.py"),
        ("runners/iverilog_runner.py", "iverilog_runner.py"),
    ]
    for rel, label in critical_scripts:
        script_dst = SKILL_DST_DIR / rel
        if script_dst.exists():
            print(f"  [OK]   {rel} present")
        else:
            verify_errors.append(f"  [FAIL] {label} missing at {script_dst}")

    # 3d. Check every code subdir was deployed
    for sub in CODE_SUBDIRS:
        sub_dst = SKILL_DST_DIR / sub
        if sub_dst.is_dir() and any(sub_dst.iterdir()):
            print(f"  [OK]   {sub}/ deployed")
        else:
            verify_errors.append(f"  [FAIL] code subdir {sub}/ not deployed at {sub_dst}")

    if verify_errors:
        print("\n[verify] Issues found:")
        for err in verify_errors:
            print(err)
        print("\n[verify] Fix the above issues before running /vf-rtl")
    else:
        print("\n[verify] All checks passed.")

    print("\nUsage: /vf-rtl <project_dir>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

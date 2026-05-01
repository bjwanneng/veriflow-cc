#!/usr/bin/env python3
"""VeriFlow Pipeline Initialization - zero external dependencies.

Usage: python init.py <project_dir>

Creates workspace directories, discovers tools, writes eda_env.sh,
initializes stage journal, and outputs structured JSON result.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def discover_python() -> str:
    """Find a working Python executable."""
    candidates = []
    # PATH-based candidates
    for name in ("python3", "python"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    # Common Windows locations
    if sys.platform == "win32":
        for p in Path("C:/").glob("Python*/python.exe"):
            candidates.append(str(p))
        for p in Path(os.path.expanduser("~")).glob(
            "AppData/Local/Programs/Python/*/python.exe"
        ):
            candidates.append(str(p))
    # Unix locations
    for d in ("/usr/bin", "/usr/local/bin"):
        p = Path(d) / "python3"
        if p.exists():
            candidates.append(str(p))

    for p in candidates:
        # Skip Windows Store stub
        if "WindowsApps" in p:
            continue
        try:
            result = subprocess.run(
                [p, "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return p
        except (OSError, subprocess.TimeoutExpired):
            continue
    return ""


def discover_eda() -> tuple[str, str]:
    """Find EDA tools (iverilog, yosys). Returns (eda_bin, eda_lib)."""
    search_dirs = [
        "/c/oss-cad-suite",
        "/c/Program Files/iverilog",
        "/c/Program Files (x86)/iverilog",
        "/opt/oss-cad-suite",
        "/usr/local",
        "/usr",
        os.path.expanduser("~/.local"),
    ]

    for base in search_dirs:
        base_path = Path(base)
        bin_dir = base_path / "bin"
        if bin_dir.is_dir() and (bin_dir / "iverilog").exists() or (
            bin_dir / "iverilog.exe"
        ).exists():
            eda_bin = str(bin_dir)
            eda_lib = ""
            lib_dir = base_path / "lib"
            if lib_dir.is_dir():
                eda_lib = str(lib_dir)
            ivl_dir = base_path / "lib" / "ivl"
            if ivl_dir.is_dir():
                eda_lib = f"{eda_lib}:{ivl_dir}" if eda_lib else str(ivl_dir)
            return eda_bin, eda_lib

    # Fallback: check PATH
    iverilog = shutil.which("iverilog")
    if iverilog:
        eda_bin = str(Path(iverilog).parent)
        return eda_bin, ""
    return "", ""


def verify_iverilog(iverilog_path: str) -> tuple[bool, str]:
    """Actually run iverilog -V to verify it works (catches DLL issues on Windows).

    Returns (success, version_or_error).
    """
    if not iverilog_path:
        return False, "iverilog path is empty"
    try:
        result = subprocess.run(
            [iverilog_path, "-V"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = (result.stdout + result.stderr).split("\n")[0]
            return True, version
        else:
            return False, f"iverilog -V returned code {result.returncode}: {(result.stderr or '')[:200]}"
    except FileNotFoundError:
        return False, f"iverilog not found at {iverilog_path}"
    except OSError as e:
        # On Windows, this catches DLL loading failures (e.g., 0xC0000139)
        return False, f"Cannot execute iverilog (DLL/library error?): {e}"
    except subprocess.TimeoutExpired:
        return False, "iverilog -V timed out"


def check_cocotb(python_exe: str) -> bool:
    """Check if cocotb is available."""
    if not python_exe:
        return False
    try:
        result = subprocess.run(
            [python_exe, "-c", "import cocotb; import cocotb_tools.runner"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def init_journal(project_dir: Path, is_resume: bool) -> None:
    """Initialize or append to stage journal."""
    journal_path = project_dir / "workspace" / "docs" / "stage_journal.md"
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    from datetime import datetime

    ts = datetime.now().isoformat()

    if is_resume:
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(f"\n---\n\n**Session resumed** at {ts}\n\n")
    elif not journal_path.exists():
        with open(journal_path, "w", encoding="utf-8") as f:
            f.write(
                "# VeriFlow Pipeline Stage Journal\n\n"
                "This file records the progress, outputs, and key decisions for each pipeline stage.\n"
            )
            f.write(f"\n## Pipeline Start\n**Timestamp**: {ts}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python init.py <project_dir>", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()

    # Validate requirement.md
    req_file = project_dir / "requirement.md"
    if not req_file.exists():
        print(f"[FATAL] requirement.md not found in {project_dir}", file=sys.stderr)
        sys.exit(1)

    # Create directories
    for d in [
        "workspace/docs",
        "workspace/rtl",
        "workspace/tb",
        "workspace/sim",
        "workspace/synth",
        ".veriflow",
        "logs",
    ]:
        (project_dir / d).mkdir(parents=True, exist_ok=True)

    # Report input files
    inputs = {}
    for name in ("requirement.md", "constraints.md", "design_intent.md"):
        exists = (project_dir / name).exists()
        inputs[name] = exists
        print(f"[INPUT] {name}: {'YES' if exists else 'NO'}")

    context_dir = project_dir / "context"
    if context_dir.exists():
        ctx_files = list(context_dir.glob("*.md"))
        print(f"[INPUT] context/: {len(ctx_files)} file(s)")
        for f in ctx_files:
            print(f"  - {f.name}")
        inputs["context_files"] = [f.name for f in ctx_files]
    else:
        print("[INPUT] context/: 0 file(s)")
        inputs["context_files"] = []

    # Discover tools
    python_exe = discover_python()
    print(f"[ENV] Python: {python_exe or 'NOT FOUND'}")

    cocotb_available = check_cocotb(python_exe)
    print(f"[ENV] cocotb: {'AVAILABLE' if cocotb_available else 'NOT AVAILABLE'}")

    eda_bin, eda_lib = discover_eda()
    print(f"[ENV] EDA_BIN={eda_bin}  EDA_LIB={eda_lib}")

    # Detect IVL_HOME (iverilog needs this for its internal preprocessor)
    ivl_home = ""
    if eda_bin:
        eda_base = str(Path(eda_bin).parent)
        for candidate in [
            Path(eda_base) / "lib" / "ivl",
            Path(eda_bin) / ".." / "lib" / "ivl",
        ]:
            if candidate.is_dir():
                ivl_home = str(candidate.resolve())
                break

    # Write eda_env.sh
    veriflow_dir = project_dir / ".veriflow"
    eda_env_path = veriflow_dir / "eda_env.sh"
    with open(eda_env_path, "w", encoding="utf-8") as f:
        f.write(f'export PYTHON_EXE="{python_exe}"\n')
        f.write(f'export EDA_BIN="{eda_bin}"\n')
        f.write(f'export EDA_LIB="{eda_lib}"\n')
        f.write(f'export IVL_HOME="{ivl_home}"\n')
        f.write(f'export COCOTB_AVAILABLE="{"true" if cocotb_available else "false"}"\n')
        f.write(f'export PATH="{eda_bin}:{eda_lib}:$PATH"\n')
    print(f"[ENV] Wrote {eda_env_path}")
    if ivl_home:
        print(f"[ENV] IVL_HOME={ivl_home}")

    # Verify iverilog actually runs (catches DLL issues on Windows)
    if eda_bin:
        iverilog_path = ""
        for name in ("iverilog", "iverilog.exe"):
            p = Path(eda_bin) / name
            if p.exists():
                iverilog_path = str(p)
                break

        if iverilog_path:
            ok, msg = verify_iverilog(iverilog_path)
            if ok:
                print(f"[ENV] iverilog: {msg}")
            else:
                print(f"[WARN] iverilog found but verification failed: {msg}")
                print("[WARN] Simulation may fail. Check DLL/library dependencies.")
                if sys.platform == "win32":
                    print("[HINT] On Windows, ensure oss-cad-suite bin/ and lib/ are both on PATH")
        else:
            print("[WARN] iverilog binary not found in EDA_BIN")

    # Windows DLL check
    if sys.platform == "win32" and eda_bin:
        eda_bin_path = Path(eda_bin)
        dll_files = list(eda_bin_path.glob("*.dll"))
        if dll_files:
            print(f"[ENV] DLLs found in EDA_BIN: {len(dll_files)}")
        else:
            lib_dlls = []
            for lib_dir_str in (eda_lib.split(":") if eda_lib else []):
                lib_dir = Path(lib_dir_str)
                if lib_dir.is_dir():
                    lib_dlls.extend(lib_dir.glob("*.dll"))
            if lib_dlls:
                print(f"[WARN] DLLs found in EDA_LIB ({len(lib_dlls)}) but not in EDA_BIN")
                print("[HINT] Ensure EDA_LIB directories are on PATH for Windows DLL resolution")
            else:
                print("[WARN] No DLLs found near iverilog — may fail on Windows")

    # Check existing state
    state_path = veriflow_dir / "pipeline_state.json"
    state = {"is_resume": False, "stages_completed": [], "next_stage": "spec_golden"}
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            state["is_resume"] = True
            state["stages_completed"] = data.get("stages_completed", [])
            completed = state["stages_completed"]
            stages = ["spec_golden", "codegen", "verify_fix", "lint_synth"]
            for s in stages:
                if s not in completed:
                    state["next_stage"] = s
                    break
            else:
                state["next_stage"] = "complete"
            print(f"[STATUS] Resuming — next stage: {state['next_stage']}")
            print(f"[STATUS] Completed: {completed}")
        except json.JSONDecodeError:
            print("[STATUS] Corrupted state, starting fresh")
    else:
        print("[STATUS] New project, starting from Stage 1.")

    # Init journal
    init_journal(project_dir, state["is_resume"])

    # Output structured JSON for main session
    result = {
        "project_dir": str(project_dir),
        "python_exe": python_exe,
        "eda_bin": eda_bin,
        "eda_lib": eda_lib,
        "cocotb_available": cocotb_available,
        "is_resume": state["is_resume"],
        "stages_completed": state["stages_completed"],
        "next_stage": state["next_stage"],
        "inputs": inputs,
    }

    result_path = veriflow_dir / "init_result.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n[INIT] Complete. Result: {result_path}")


if __name__ == "__main__":
    main()

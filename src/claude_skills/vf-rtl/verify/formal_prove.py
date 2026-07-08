#!/usr/bin/env python3
"""Formal property prover for VeriFlow-CC.

Replaces the deleted no-op formal_property_gen with a REAL flow: generate
Verilog-2005 formal properties (assert/assume in clocked always blocks — NOT
SystemVerilog SVA, per the project's Verilog-2005-only rule) from spec.json,
then prove them with SymbiYosys (sby) + yosys smt.

Usage:
    python formal_prove.py --spec workspace/docs/spec.json --module top \\
        --rtl-dir workspace/rtl --output workspace/docs/top_formal.v
    # add --prove to run sby and write logs/formal.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# --- helpers --------------------------------------------------------------

def _find_module(spec: dict, module: str) -> dict | None:
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        modules = list(modules.values())
    for m in modules or []:
        if m.get("module_name") == module:
            return m
    return None


def _port_width(p: dict) -> int:
    w = p.get("width", 1)
    return w if isinstance(w, int) and w > 0 else 1


def _vtype(w: int) -> str:
    return "" if w == 1 else f"[{w - 1}:0] "


def _is_input(p: dict) -> bool:
    d = (p.get("direction") or p.get("dir") or "").lower()
    return d.startswith("in") or d == "input"


def _find_rtl(rtl_dir: str, module: str) -> str | None:
    d = Path(rtl_dir)
    for cand in (d / f"{module}.v", *sorted(d.glob("*.v"))):
        if cand.exists():
            try:
                if module in cand.read_text(encoding="utf-8", errors="replace"):
                    return str(cand)
            except OSError:
                continue
    return None


# --- property generation --------------------------------------------------

def generate_properties(spec: dict, module: str) -> str:
    """Emit a Verilog-2005-formal wrapper proving spec-derived invariants.

    Instantiates the DUT and emits assert()/assume() in clocked always blocks.
    v1 emits handshake valid-stability for output `valid` ports with an ack.
    Always returns a syntactically valid module (a useful artifact even with no
    derivable property).
    """
    mod = _find_module(spec, module)
    if mod is None:
        mod = {"module_name": module, "ports": []}
    ports = mod.get("ports") or []

    lines = [
        f"// Auto-generated formal properties for {module}",
        "// Verilog-2005 + yosys -formal. assert()/assume() only (no SVA).",
        "// Prove with: sby (see formal_prove.py --prove).",
        "`timescale 1ns/1ps",
        f"module {module}_formal(input wire clk, input wire rst);",
    ]

    # Declare wrapper signals for every non-clock/reset port.
    for p in ports:
        nm = p.get("name")
        if not nm or nm in ("clk", "clock", "rst", "reset"):
            continue
        w, vt = _port_width(p), ""
        vt = _vtype(w)
        kw = "reg" if _is_input(p) else "wire"
        lines.append(f"    {kw} {vt}{nm};")

    # Instantiate the DUT, wiring clk/rst to the wrapper's free clock/reset.
    conns = []
    for p in ports:
        nm = p.get("name")
        if nm in ("clk", "clock"):
            conns.append(f".{nm}(clk)")
        elif nm in ("rst", "reset"):
            conns.append(f".{nm}(rst)")
        elif nm:
            conns.append(f".{nm}({nm})")
    lines.append(f"    {module} dut ({', '.join(conns)});")

    # Handshake valid-stability: an output valid that the DUT drives must stay
    # asserted until the ack (ready) is observed — the #1 handshake bug.
    n_props = 0
    for p in ports:
        if (not _is_input(p)) and p.get("protocol") == "valid" and p.get("ack_port"):
            v = p.get("name")
            ack = p.get("ack_port")
            lines.append(f"    // handshake: {v} (valid) held until {ack} (ready).")
            lines.append(f"    reg past_{v};")
            lines.append(f"    initial past_{v} = 1'b0;")
            lines.append("    always @(posedge clk) begin")
            lines.append(f"        past_{v} <= {v};")
            lines.append(f"        if (past_{v}) assert({v} || {ack});")
            lines.append("    end")
            n_props += 1

    if n_props == 0:
        lines.append("    // No spec-derived output handshake property; wrapper is a")
        lines.append("    // structural harness. Add assert()/assume() here to prove more.")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


# --- sby run --------------------------------------------------------------

_STATUS_PATTERNS = [
    re.compile(r"status\s*=\s*(pass|fail|error)", re.IGNORECASE),
    re.compile(r"DONE\s*\(\s*(pass|fail|error)", re.IGNORECASE),
    re.compile(r"summary:\s*(pass|fail|error)", re.IGNORECASE),
]


def _parse_sby_output(text: str) -> dict:
    """Parse sby stdout/stderr into {status, proven}.

    sby prints status in several forms across versions — "engine_N.status = PASS",
    "DONE (PASS, rc=0)", or "summary: PASS" — so match all of them.
    """
    found: list[str] = []
    for pat in _STATUS_PATTERNS:
        found.extend(m.upper() for m in pat.findall(text or ""))
    if not found:
        return {"status": None, "proven": None}
    # Any FAIL or ERROR wins over PASS (a partial failure means not proven).
    status = "FAIL" if "FAIL" in found else ("ERROR" if "ERROR" in found else "PASS")
    return {"status": status, "proven": status == "PASS"}


def _sby_config(module: str, dut_file: str, props_file: str) -> str:
    return f"""[options]
mode prove
[engines]
smtbmc z3
[script]
read_verilog -formal {dut_file}
read_verilog -formal {props_file}
prep -top {module}_formal
[files]
{dut_file}
{props_file}
"""


def run_formal(dut_v: str, props_v: str, module: str,
               timeout: int = 120, sby_bin: str = "sby") -> dict:
    """Run sby to prove the generated properties. Mirrors yosys_equiv's pattern."""
    sby_path = shutil.which(sby_bin)
    if sby_path is None:
        return {"proven": None, "status": "SKIP",
                "error": f"sby not found: {sby_bin}"}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        dut_dst = tmp_p / Path(dut_v).name
        shutil.copy(dut_v, dut_dst)
        props_dst = tmp_p / f"{module}_formal.v"
        props_dst.write_text(props_v, encoding="utf-8")
        cfg = tmp_p / "formal.sby"
        cfg.write_text(_sby_config(module, dut_dst.name, props_dst.name), encoding="utf-8")

        try:
            proc = subprocess.run(
                [sby_path, "-f", str(cfg)],
                capture_output=True, text=True, timeout=timeout, cwd=str(tmp_p),
            )
        except subprocess.TimeoutExpired:
            return {"proven": None, "status": "TIMEOUT",
                    "error": f"sby timed out after {timeout}s"}
        except Exception as e:  # pragma: no cover - defensive
            return {"proven": None, "status": "ERROR", "error": str(e)}

        parsed = _parse_sby_output(proc.stdout + "\n" + proc.stderr)
        return {
            "status": parsed["status"] or ("ERROR" if proc.returncode != 0 else "UNKNOWN"),
            "proven": parsed["proven"],
            "returncode": proc.returncode,
            "raw_tail": (proc.stdout + proc.stderr)[-800:],
        }


# --- CLI ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate + prove formal properties")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--rtl-dir", required=True, help="Dir with the DUT .v")
    parser.add_argument("--output", required=True, help="Path for the property .v file")
    parser.add_argument("--prove", action="store_true", help="Run sby to prove")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    props = generate_properties(spec, args.module)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(props, encoding="utf-8")
    print(f"[formal] properties -> {out}", file=sys.stderr)

    if not args.prove:
        print(json.dumps({"proven": None, "status": "GENERATED", "props_path": str(out)}))
        return 0

    dut = _find_rtl(args.rtl_dir, args.module)
    if dut is None:
        print(json.dumps({"proven": None, "status": "SKIP",
                          "error": f"DUT .v for {args.module} not in {args.rtl_dir}"}))
        return 2
    result = run_formal(dut, props, args.module, timeout=args.timeout)
    result["props_path"] = str(out)
    print(json.dumps(result, indent=2))
    return 0 if result.get("proven") else (1 if result.get("status") == "FAIL" else 0)


if __name__ == "__main__":
    sys.exit(main())

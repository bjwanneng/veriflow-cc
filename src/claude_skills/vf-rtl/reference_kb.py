#!/usr/bin/env python3
"""Reference-implementation KB for VeriFlow-CC.

Holds a small curated set of correct Verilog-2005 reference modules and
retrieves the ones relevant to a module's detected type, so vf-coder gets
concrete structural examples (not just style rules) to learn from.

Usage:
    python reference_kb.py --spec workspace/docs/spec.json --module <name>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_REFERENCES_DIR = Path(__file__).parent / "references"

# classify_module() type -> reference filename (stem).
_TYPE_FILE = {
    "handshake_valid_ready": "handshake_valid_ready",
    "fifo": "fifo",
    "fsm": "fsm_moore",
    "arbiter": "arbiter_round_robin",
    "counter": "counter",
    "pipeline": "pipeline_aligner",
    "generic": "counter",  # basic structural example for unclassified modules
}


def _port_names(mod: dict) -> set[str]:
    return {(p.get("name") or "").lower() for p in (mod.get("ports") or [])}


def classify_module(mod: dict) -> str:
    """Detect a module's structural type from its spec.json entry.

    Order is by specificity (most specific signature first) so a FIFO isn't
    misread as a generic handshake etc.
    """
    names = _port_names(mod)
    has = lambda *keys: any(k in names for k in keys)
    params = {(p.get("name") or "").lower() for p in (mod.get("parameters") or [])}

    # FIFO: write/read enables + full/empty flags (optionally a DEPTH param).
    if (has("wr_en", "write_en", "wr") and has("rd_en", "read_en", "rd")
            and has("full", "empty")):
        return "fifo"
    if "depth" in params and has("wr_en", "write_en", "rd_en", "read_en"):
        return "fifo"

    # Arbiter: request/grant pair.
    if has("req", "request") and has("grant"):
        return "arbiter"

    # Handshake: a port tagged protocol=valid, or valid+ready names.
    if any((p.get("protocol") == "valid") for p in (mod.get("ports") or [])):
        return "handshake_valid_ready"
    if has("valid", "valid_in", "valid_out") and has("ready", "ready_in", "ready_out"):
        return "handshake_valid_ready"

    # FSM: cycle_timing entries with named states.
    ct = mod.get("cycle_timing") or []
    if isinstance(ct, list) and any(
        isinstance(c, dict) and c.get("state") for c in ct
    ):
        return "fsm"

    # Counter: a single count output and few ports.
    if has("count", "cnt", "counter") and len(names) <= 6:
        return "counter"

    # Pipeline: declared multi-cycle pipeline delay.
    tc = mod.get("timing_contract") or {}
    if isinstance(tc, dict):
        delay = tc.get("pipeline_delay_cycles")
        if isinstance(delay, (int, float)) and delay > 1:
            return "pipeline"

    return "generic"


def retrieve_references(mod: dict, top_k: int = 2) -> list[dict]:
    """Return up to `top_k` reference snippets relevant to the module.

    Each entry: {"type": str, "name": str, "code": str}. The primary match is
    the module's classified type; a pipeline-aligner is added as a secondary
    ref for FSM/handshake modules (a common source of B_late timing bugs).
    """
    primary = classify_module(mod)
    wanted: list[str] = [primary]
    if primary in ("fsm", "handshake_valid_ready"):
        wanted.append("pipeline")

    refs: list[dict] = []
    seen: set[str] = set()
    for t in wanted:
        stem = _TYPE_FILE.get(t)
        if stem and stem not in seen:
            path = _REFERENCES_DIR / f"{stem}.v"
            if path.exists():
                refs.append({
                    "type": t,
                    "name": path.stem,
                    "code": path.read_text(encoding="utf-8"),
                })
                seen.add(stem)
        # Self-improve: also pick up any learned (promoted) references of this type.
        for lp in sorted(_REFERENCES_DIR.glob(f"{t}_learned_*.v")):
            if len(refs) >= top_k:
                break
            if lp.stem in seen:
                continue
            refs.append({
                "type": t,
                "name": lp.stem,
                "code": lp.read_text(encoding="utf-8"),
            })
            seen.add(lp.stem)
        if len(refs) >= top_k:
            break
    return refs


def _find_module(spec: dict, module_name: str) -> dict | None:
    modules = spec.get("modules", [])
    if isinstance(modules, dict):
        modules = list(modules.values())
    for m in modules:
        if m.get("module_name") == module_name:
            return m
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve reference RTL snippets")
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--module", required=True, help="Module name to classify")
    parser.add_argument("--top-k", type=int, default=2)
    args = parser.parse_args(argv)

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    mod = _find_module(spec, args.module)
    if mod is None:
        print(json.dumps({"error": f"module '{args.module}' not in spec"}))
        return 2

    refs = retrieve_references(mod, top_k=args.top_k)
    print(json.dumps({
        "module": args.module,
        "type": classify_module(mod),
        "references": refs,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

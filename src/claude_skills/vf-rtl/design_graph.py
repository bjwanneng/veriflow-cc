#!/usr/bin/env python3
"""Design knowledge graph for VeriFlow-CC.

Builds a networkx DiGraph from spec.json module_connectivity for:
- Cycle detection (combinational loops)
- Unreachable module detection
- Fanout skew analysis
- Interface consistency checks

Usage:
    python design_graph.py --spec spec.json --output graph.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class DesignGraph:
    """Directed graph representation of module connectivity."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.nodes: set[str] = set()
        self.edges: list[tuple[str, str, dict]] = []  # (src, dst, attrs)
        self._build()

    def _build(self) -> None:
        """Build graph from spec.json module_connectivity."""
        modules = self.spec.get("modules", [])
        if isinstance(modules, dict):
            modules = list(modules.values())

        # Add all modules as nodes
        for mod in modules:
            name = mod.get("module_name")
            if name:
                self.nodes.add(name)

        # Add connectivity edges
        for conn in self.spec.get("module_connectivity", []):
            src = conn.get("source", "")
            dst = conn.get("destination", "")
            if not src or not dst:
                continue
            self.edges.append((src, dst, {
                "signal": conn.get("signal", ""),
                "timing_contract": conn.get("timing_contract", {}),
            }))

    def detect_cycles(self) -> list[list[str]]:
        """Find all cycles in the connectivity graph."""
        # DFS-based cycle detection
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}
        for src, dst, _ in self.edges:
            if src in adj and dst in adj:
                adj[src].append(dst)

        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found cycle — extract it
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node)

        # Deduplicate cycles
        unique: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for c in cycles:
            key = tuple(sorted(c))
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    def find_unreachable_modules(self, top_module: str | None = None) -> list[str]:
        """Find modules not reachable from the top module."""
        if not top_module:
            # Find top module from spec
            modules = self.spec.get("modules", [])
            if isinstance(modules, dict):
                modules = list(modules.values())
            for mod in modules:
                if mod.get("module_type") == "top":
                    top_module = mod.get("module_name")
                    break

        if not top_module or top_module not in self.nodes:
            return []

        # BFS from top module
        adj: dict[str, list[str]] = {n: [] for n in self.nodes}
        for src, dst, _ in self.edges:
            if src in adj and dst in adj:
                adj[src].append(dst)

        reachable: set[str] = set()
        queue = [top_module]
        while queue:
            node = queue.pop(0)
            if node in reachable:
                continue
            reachable.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in reachable:
                    queue.append(neighbor)

        return sorted(self.nodes - reachable)

    def check_fanout_skew(self) -> list[dict]:
        """Check fanout_groups for skew violations."""
        violations = []
        groups = self.spec.get("fanout_groups", [])
        for fg in groups:
            name = fg.get("name", "?")
            signals = fg.get("signals", [])
            max_skew = fg.get("max_skew_cycles", 0)
            same_arrival = fg.get("same_arrival", False)

            if same_arrival and len(signals) > 1:
                # Check that all signals in group arrive at same cycle
                # This is a structural check — actual timing verification
                # would need synthesis data
                violations.append({
                    "group": name,
                    "signals": signals,
                    "issue": "same_arrival=True requires all signals to arrive "
                             f"within {max_skew} cycle(s)",
                    "max_skew": max_skew,
                })
        return violations

    def to_dict(self) -> dict[str, Any]:
        """Serialize graph to dict."""
        return {
            "nodes": sorted(self.nodes),
            "edges": [
                {"source": src, "destination": dst, **attrs}
                for src, dst, attrs in self.edges
            ],
            "cycles": self.detect_cycles(),
            "unreachable": self.find_unreachable_modules(),
            "fanout_violations": self.check_fanout_skew(),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and analyze design knowledge graph from spec.json"
    )
    parser.add_argument("--spec", required=True, help="Path to spec.json")
    parser.add_argument("--output", "-o", required=True,
                        help="Output JSON file for graph analysis")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"spec.json not found: {spec_path}", file=sys.stderr)
        return 2

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {spec_path}: {e}", file=sys.stderr)
        return 2

    graph = DesignGraph(spec)
    result = graph.to_dict()

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Print summary
    print(f"[graph] Nodes: {len(result['nodes'])}")
    print(f"[graph] Edges: {len(result['edges'])}")
    print(f"[graph] Cycles: {len(result['cycles'])}")
    if result['cycles']:
        for c in result['cycles']:
            print(f"  [CYCLE] {' -> '.join(c)}")
    print(f"[graph] Unreachable modules: {len(result['unreachable'])}")
    if result['unreachable']:
        print(f"  {result['unreachable']}")
    print(f"[graph] Fanout violations: {len(result['fanout_violations'])}")
    print(f"[graph] Report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

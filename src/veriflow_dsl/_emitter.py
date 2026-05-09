"""VeriFlow DSL Verilog-2005 emitter.

Emits Verilog-2005 source from a VeriFlow DSL Module, following every rule
in docs/coding_style.md:

- Verilog-2001 ANSI-style module declaration
- Two-block pattern: combinational (always @*) + sequential (always @(posedge clk))
- Synchronous active-high reset via if/else in the sequential block
- _reg / _next naming convention for registered signals
- Default values at top of combinational block (latch prevention)
- Barrel shifter for variable rotation (Rule R5)
- Output wire + assign for all output ports
"""

from __future__ import annotations

import math
import re

from ._types import (
    Signal, Const, Value, Assignment,
    _BinOp, _UnaryOp, _Slice, _Concat, _Mux, _ROL, _mask,
)
from ._module import Module

__all__ = ["VerilogEmitter"]



def _expr_name_for_key(expr: Value) -> str:
    """Get a collision-resistant Verilog-safe name for barrel shifter key generation."""
    if isinstance(expr, Signal):
        return expr.name
    elif isinstance(expr, Const):
        return f"c{expr.value}"
    else:
        return f"e{abs(hash(repr(expr))) % 10000}"


# ---------------------------------------------------------------------------
# Expression → Verilog string converter
# ---------------------------------------------------------------------------

class _ExprEmitter:
    """Convert a DSL expression tree to a Verilog expression string."""

    def __init__(self, signal_names: dict[str, str] | None = None):
        # Maps DSL signal names to Verilog signal names (e.g., "counter" -> "counter_reg")
        self._renames = signal_names or {}

    def emit(self, expr: Value) -> str:
        """Convert expression tree to Verilog expression string."""
        if isinstance(expr, Const):
            return self._emit_const(expr)
        elif isinstance(expr, Signal):
            return self._renames.get(expr.name, expr.name)
        elif isinstance(expr, _BinOp):
            return self._emit_binop(expr)
        elif isinstance(expr, _UnaryOp):
            return self._emit_unaryop(expr)
        elif isinstance(expr, _Slice):
            return self._emit_slice(expr)
        elif isinstance(expr, _Concat):
            return self._emit_concat(expr)
        elif isinstance(expr, _Mux):
            return self._emit_mux(expr)
        elif isinstance(expr, _ROL):
            return self._emit_rol(expr)
        else:
            raise ValueError(f"Unknown expression type: {type(expr).__name__}")

    def _emit_const(self, c: Const) -> str:
        if c.width <= 32:
            return f"{c.width}'d{c.value}"
        else:
            return f"{c.width}'h{c.value:x}"

    def _emit_binop(self, op: _BinOp) -> str:
        # Comparison and logical operators need special handling
        verilog_ops = {
            "+": "+", "-": "-", "*": "*",
            "&": "&", "|": "|", "^": "^",
            "<<": "<<", ">>": ">>",
            "==": "==", "!=": "!=",
            "<": "<", "<=": "<=", ">": ">", ">=": ">=",
        }
        vop = verilog_ops.get(op._op)
        if vop is None:
            raise ValueError(f"Unsupported binary op: {op._op}")
        left = self.emit(op._left)
        right = self.emit(op._right)
        return f"({left} {vop} {right})"

    def _emit_unaryop(self, op: _UnaryOp) -> str:
        if op._op == "~":
            return f"(~{self.emit(op._operand)})"
        elif op._op == "-":
            return f"(-{self.emit(op._operand)})"
        else:
            raise ValueError(f"Unsupported unary op: {op._op}")

    def _emit_slice(self, s: _Slice) -> str:
        operand = self.emit(s._operand)
        if s._high == s._low:
            return f"{operand}[{s._high}]"
        return f"{operand}[{s._high}:{s._low}]"

    def _emit_concat(self, c: _Concat) -> str:
        parts = ", ".join(self.emit(p) for p in c._parts)
        return f"{{{parts}}}"

    def _emit_mux(self, m: _Mux) -> str:
        cond = self.emit(m._cond)
        t = self.emit(m._val_true)
        f = self.emit(m._val_false)
        return f"({cond} ? {t} : {f})"

    def _emit_rol(self, r: _ROL) -> str:
        operand = self.emit(r._operand)
        amount = r._amount
        w = r._width

        # Constant rotation: use bit-slice concatenation
        if isinstance(amount, Const):
            n = amount.value % w
            if n == 0:
                return operand
            return f"{{{operand}[{w-1-n}:{0}], {operand}[{w-1}:{w-n}]}}"

        # Variable rotation: emit barrel shifter reference
        # The barrel shifter itself is emitted separately by _emit_barrel_shifters()
        # Key includes operand and amount names to avoid collisions
        operand_name = self._signal_name_for_key(r._operand)
        amount_name = self._signal_name_for_key(r._amount)
        return f"_rol_{operand_name}_{amount_name}_{w}"

    def _signal_name_for_key(self, expr: Value) -> str:
        """Get a collision-resistant Verilog-safe name for barrel shifter key generation."""
        return _expr_name_for_key(expr)


# ---------------------------------------------------------------------------
# Verilog Emitter
# ---------------------------------------------------------------------------

class VerilogEmitter:
    """Emit Verilog-2005 from a VeriFlow DSL Module.

    Follows docs/coding_style.md formatting rules exactly:
    - Two-block pattern (combinational + sequential)
    - Synchronous active-high reset via if/else in sequential block
    - _reg / _next naming convention
    - Default values at top of comb block (latch prevention)
    """

    def __init__(self):
        self._indent = "    "

    def emit(self, module: Module) -> str:
        """Emit complete Verilog-2005 source for the module.

        Delegates to module.analyze() which caches internally.
        """
        analysis = module.analyze()
        signals = analysis["signals"]
        comb_asns = analysis["comb_assignments"]
        sync_asns = analysis["sync_assignments"]
        ports = module.ports()

        parts: list[str] = []

        # Header
        parts.append(f"// Auto-generated by VeriFlow DSL from module {module.name}")
        parts.append("`resetall")
        parts.append("`timescale 1ns / 1ps")
        parts.append("`default_nettype none")
        parts.append("")

        # Module declaration
        parts.append(self.emit_module_declaration(module))
        parts.append("")

        # Internal signal declarations
        internal_decls = self._emit_internal_declarations(analysis)
        if internal_decls:
            parts.extend(internal_decls)
            parts.append("")

        # Combinational block
        if comb_asns:
            parts.append(self.emit_combinational_block(module, analysis))
            parts.append("")

        # Sequential block
        if sync_asns:
            parts.append(self.emit_sequential_block(module, analysis))
            parts.append("")

        # Continuous assigns for output wires
        assigns = self._emit_output_assigns(module, analysis)
        if assigns:
            parts.extend(assigns)
            parts.append("")

        # Barrel shifters for variable rotations
        barrel = self._emit_barrel_shifters(module, analysis)
        if barrel:
            parts.extend(barrel)
            parts.append("")

        parts.append("endmodule")
        parts.append("")
        parts.append("`resetall")

        code = "\n".join(parts)

        # Self-check: verify timing contract is respected in emitted Verilog.
        # Catches Pattern 16 bugs (wire output implemented as reg) at generation
        # time instead of waiting for simulation to fail.
        issues = self._validate_timing_contract(code, analysis, module.ports())
        for issue in issues:
            import warnings
            warnings.warn(f"[VerilogEmitter] Timing contract violation in "
                          f"module {module.name}: {issue}", stacklevel=2)

        return code

    def emit_module_declaration(self, module: Module) -> str:
        """Emit Verilog-2001 ANSI-style module declaration."""
        ports = module.ports()
        analysis = module.analyze()
        signals = analysis["signals"]

        lines = [f"module {module.name}"]
        lines.append("(")

        port_strs = []
        port_names = {p.name for p in ports}

        # Auto-inject clk and rst when sync assignments exist
        has_sync = bool(analysis["sync_assignments"])
        if has_sync:
            if "clk" not in port_names:
                port_strs.append(f"    input  wire         clk")
            if "rst" not in port_names:
                port_strs.append(f"    input  wire         rst")

        for p in ports:
            sig_info = signals[p.name]
            width_str = "" if p.width == 1 else f"[{p.width-1}:0] "

            # Determine output type
            if p.direction == "input":
                port_strs.append(f"    input  wire {width_str}{p.name}")
            elif p.direction == "output":
                # Per coding_style.md Section 10: outputs are always output wire
                port_strs.append(f"    output wire {width_str}{p.name}")

        lines.append(",\n".join(port_strs))
        lines.append(");")
        return "\n".join(lines)

    def _build_signal_renames(self, analysis: dict) -> dict[str, str]:
        """Build signal rename map for expression emission.

        In the two-block pattern:
        - Input ports keep their original names (they are wires driven externally)
        - Sync-domain signals (reg_next) are read via _reg (current register value)
        - Comb-domain signals (wire) are read via _next (combinational output)
        - Undriven signals keep their original names
        """
        signals = analysis["signals"]
        renames = {}
        for name, info in signals.items():
            if info["direction"] == "input":
                renames[name] = name
            elif info["timing"] == "reg_next":
                renames[name] = f"{name}_reg"
            elif info["timing"] == "wire" and info["direction"] == "output":
                renames[name] = f"{name}_next"
            elif info["timing"] == "wire" and info["direction"] == "internal":
                renames[name] = f"{name}_next"
        return renames

    def emit_combinational_block(self, module: Module, analysis: dict) -> str:
        """Emit always @* block for comb-domain assignments."""
        comb_asns = analysis["comb_assignments"]
        signals = analysis["signals"]
        renames = self._build_signal_renames(analysis)
        ee = _ExprEmitter(signal_names=renames)

        lines = ["// Combinational logic"]
        lines.append("always @* begin")

        # Default values at top to prevent latches (Section 12)
        for target_name, _ in comb_asns:
            sig_info = signals[target_name]
            if sig_info["timing"] == "wire":
                lines.append(
                    f"{self._indent}{target_name}_next = {sig_info['width']}'d{sig_info['reset']};"
                )

        # Assignments
        for target_name, value_expr in comb_asns:
            sig_info = signals[target_name]
            verilog_expr = ee.emit(value_expr)
            # Wire outputs use _next (intermediate) naming
            next_name = f"{target_name}_next" if sig_info["timing"] == "wire" else target_name
            lines.append(
                f"{self._indent}{next_name} = {verilog_expr};"
            )

        lines.append("end")
        return "\n".join(lines)

    def emit_sequential_block(self, module: Module, analysis: dict) -> str:
        """Emit always @(posedge clk) block for sync-domain assignments.

        Uses if/else structure for synthesis safety (avoids last-assignment-wins
        ambiguity across different synthesis tools).
        reset_less signals are computed normally even during reset.
        """
        sync_asns = analysis["sync_assignments"]
        signals = analysis["signals"]
        renames = self._build_signal_renames(analysis)
        ee = _ExprEmitter(signal_names=renames)

        lines = ["// Sequential logic (register update)"]
        lines.append("always @(posedge clk) begin")

        lines.append(f"{self._indent}if (rst) begin")
        for target_name, value_expr in sync_asns:
            sig_info = signals[target_name]
            if sig_info["reset_less"]:
                # reset_less: still compute normally during reset
                verilog_expr = ee.emit(value_expr)
                lines.append(
                    f"{self._indent}{self._indent}{target_name}_reg <= {verilog_expr};"
                )
            else:
                lines.append(
                    f"{self._indent}{self._indent}{target_name}_reg <= {sig_info['width']}'d{sig_info['reset']};"
                )
        lines.append(f"{self._indent}end else begin")
        for target_name, value_expr in sync_asns:
            verilog_expr = ee.emit(value_expr)
            lines.append(
                f"{self._indent}{self._indent}{target_name}_reg <= {verilog_expr};"
            )
        lines.append(f"{self._indent}end")

        lines.append("end")
        return "\n".join(lines)

    def emit_timing_contract(self, module: Module) -> dict:
        """Produce timing_contract dict for cocotb GOLDEN_TO_PORT mapping.

        Delegates to module.analyze() which caches internally.

        Returns:
            {
                "signals": {...},
                "golden_to_port": {...},
                "port_widths": {...},
                "input_ports": {...},
            }
        """
        return module.analyze()

    # --- Internal helpers --------------------------------------------------

    def _emit_internal_declarations(self, analysis: dict) -> list[str]:
        """Emit reg/wire declarations for internal signals."""
        signals = analysis["signals"]
        comb_targets = {t for t, _ in analysis["comb_assignments"]}
        lines = []

        for name, info in signals.items():
            if info["is_port"]:
                # Ports are already declared in module header
                # But we need _reg and _next for internal use
                if info["timing"] == "reg_next" and info["direction"] == "output":
                    lines.append(
                        f"reg [{info['width']-1}:0] {name}_reg = {info['width']}'d{info['reset']};"
                    )
                    # _next is only needed if this signal is also driven in comb domain.
                    # analyze() forbids dual-domain assignment, so this is currently
                    # unreachable — kept for forward compatibility with mixed-timing ports.
                    if name in comb_targets:
                        lines.append(
                            f"wire [{info['width']-1}:0] {name}_next;"
                        )
                elif info["timing"] == "wire" and info["direction"] == "output":
                    lines.append(
                        f"reg [{info['width']-1}:0] {name}_next;"
                    )
                continue

            # Internal signals
            width_str = f"[{info['width']-1}:0] " if info['width'] > 1 else ""

            if info["timing"] == "reg_next":
                lines.append(
                    f"reg {width_str}{name}_reg = {info['width']}'d{info['reset']};"
                )
                # _next is only needed when there is a comb assignment driving it.
                if name in comb_targets:
                    lines.append(
                        f"wire {width_str}{name}_next;"
                    )
            elif info["timing"] == "wire":
                lines.append(
                    f"reg {width_str}{name}_next;"  # _next used in always @*
                )

        return lines

    def _emit_output_assigns(self, module: Module, analysis: dict) -> list[str]:
        """Emit continuous assign statements for output wires.

        Per coding_style.md Section 10: outputs are always output wire + assign.
        """
        signals = analysis["signals"]
        lines = ["// Output wire assignments"]

        for port in module.ports():
            info = signals[port.name]
            if info["direction"] != "output":
                continue

            if info["timing"] == "reg_next":
                lines.append(f"assign {port.name} = {port.name}_reg;")
            elif info["timing"] == "wire":
                lines.append(f"assign {port.name} = {port.name}_next;")

        return lines

    def _validate_timing_contract(
        self, code: str, analysis: dict, ports: list
    ) -> list[str]:
        """Verify emitted Verilog respects the DSL timing contract.

        Checks:
          - wire-timing output ports → driven by assign (not output reg)
          - reg_next-timing output ports → driven by NBA (<=) in always @(posedge clk)

        Returns list of issue strings (empty if all checks pass).
        """
        signals = analysis["signals"]
        issues = []

        for port in ports:
            name = port.name
            info = signals.get(name)
            if info is None or info["direction"] != "output":
                continue

            timing = info["timing"]

            if timing == "wire":
                # wire outputs must use continuous assignment
                # Pattern: assign <name> =
                if not re.search(rf'assign\s+{re.escape(name)}\s*=', code):
                    issues.append(
                        f"output port '{name}' has DSL timing='wire' but no "
                        f"'assign {name} = ...' found in emitted Verilog. "
                        f"If implemented as output reg, it adds a 1-cycle "
                        f"delay not present in the DSL model (Bug Pattern 16)."
                    )

            elif timing == "reg_next":
                # reg_next outputs must use NBA inside always @(posedge clk)
                # Pattern: <name>_reg <= ... inside an always @(posedge clk) block
                if not re.search(rf'{re.escape(name)}_reg\s*<=', code):
                    issues.append(
                        f"output port '{name}' has DSL timing='reg_next' but no "
                        f"'{name}_reg <= ...' found in emitted Verilog. "
                        f"The register may not be properly updated."
                    )

        return issues

    def _emit_barrel_shifters(self, module: Module, analysis: dict) -> list[str]:
        """Detect variable ROL expressions and emit barrel shifters.

        Rule R5: Variable rotation MUST use a barrel shifter, not variable
        part-select which is illegal in Verilog-2005.
        """
        lines: list[str] = []
        seen: set[str] = set()
        renames = self._build_signal_renames(analysis)

        for asn_list in [analysis["comb_assignments"], analysis["sync_assignments"]]:
            for _, value_expr in asn_list:
                self._collect_barrel_shifters(value_expr, lines, seen, renames)

        return lines

    def _collect_barrel_shifters(
        self, expr: Value, lines: list[str], seen: set[str],
        renames: dict[str, str] | None = None,
    ) -> None:
        """Recursively find _ROL nodes with variable amounts and emit barrel shifters."""
        if isinstance(expr, _ROL):
            if not isinstance(expr._amount, Const):
                # Variable rotation — need barrel shifter
                w = expr._width
                stages = math.ceil(math.log2(w)) if w > 1 else 1
                operand_name = self._get_signal_name(expr._operand, renames)
                amount_name = self._get_signal_name(expr._amount, renames)
                # Use same key scheme as _emit_rol for consistency
                operand_key = _expr_name_for_key(expr._operand)
                amount_key = _expr_name_for_key(expr._amount)
                key = f"_rol_{operand_key}_{amount_key}_{w}"
                if key not in seen:
                    seen.add(key)
                    lines.extend(self._barrel_shifter_code(
                        w, stages, operand_name, amount_name, key
                    ))
        elif isinstance(expr, _BinOp):
            self._collect_barrel_shifters(expr._left, lines, seen, renames)
            self._collect_barrel_shifters(expr._right, lines, seen, renames)
        elif isinstance(expr, _UnaryOp):
            self._collect_barrel_shifters(expr._operand, lines, seen, renames)
        elif isinstance(expr, _Mux):
            self._collect_barrel_shifters(expr._cond, lines, seen, renames)
            self._collect_barrel_shifters(expr._val_true, lines, seen, renames)
            self._collect_barrel_shifters(expr._val_false, lines, seen, renames)
        elif isinstance(expr, _Concat):
            for p in expr._parts:
                self._collect_barrel_shifters(p, lines, seen, renames)

    def _get_signal_name(
        self, expr: Value, renames: dict[str, str] | None = None
    ) -> str:
        """Get a verilog-compatible name for an expression.

        Uses the rename map to pick the correct suffix (_reg vs _next)
        based on the signal's actual timing domain.
        """
        if isinstance(expr, Signal):
            if renames and expr.name in renames:
                return renames[expr.name]
            return expr.name
        elif isinstance(expr, Const):
            return f"{expr.width}'d{expr.value}"
        else:
            return "expr"

    def _barrel_shifter_code(
        self, width: int, stages: int, operand: str, amount: str, result_name: str
    ) -> list[str]:
        """Generate barrel shifter Verilog code for variable rotation.

        Template from SKILL.md Rule R5.
        """
        lines = [f"// Barrel shifter for variable ROL({operand}, {amount})"]
        lines.append(f"reg [{width-1}:0] {result_name};")

        for stage in range(stages):
            shift_amount = 1 << stage
            if stage == 0:
                inp = operand
                s = f"{result_name}_s{stage}"
            else:
                inp = f"{result_name}_s{stage-1}"
                s = f"{result_name}_s{stage}"

            lines.append(f"reg [{width-1}:0] {s};")

        lines.append("always @(*) begin")
        for stage in range(stages):
            shift_amount = 1 << stage
            if stage == 0:
                inp = operand
            else:
                inp = f"{result_name}_s{stage-1}"
            s = f"{result_name}_s{stage}"

            # ROL by shift_amount: {x[W-1-shift:0], x[W-1:W-shift]}
            if shift_amount < width:
                hi = width - 1 - shift_amount
                lo = width - shift_amount
                concat = "{" + f"{inp}[{hi}:0], {inp}[{width-1}:{lo}]" + "}"
                lines.append(
                    f"{self._indent}{s} = {amount}[{stage}] ? "
                    f"{concat} : {inp};"
                )
            else:
                lines.append(f"{self._indent}{s} = {inp};")

        # Final stage: handle bit 4+ for 32-bit (shift by 16)
        last_stage = f"{result_name}_s{stages-1}"
        lines.append(f"{self._indent}{result_name} = {last_stage};")
        lines.append("end")

        return lines

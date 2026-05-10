"""Adapter: convert @vf_block timing_model functions to DSL Modules.

This is the bridge between the new veriflow_spec protocol (RegT/WireT)
and the existing DSL emitter (Module/Signal/VerilogEmitter).

Status: v2.0 basic version — supports sequential blocks with simple
expressions (binop, mux, cat, slice, const, signal references).
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

from ._types import Signal, Const, Cat, Mux, Value, _ROL
from ._module import Module
from ._spec import RegT, WireT, RegAssign, vf_block

__all__ = ["from_timing_model"]


def _name_to_value(name: str, signal_map: dict[str, Signal]) -> Value:
    """Convert a signal name to a DSL Value.

    If the name is in signal_map, return that Signal.
    If it looks like an integer literal, return a Const.
    """
    if name in signal_map:
        return signal_map[name]
    # Try to parse as integer (for coerced int literals)
    try:
        v = int(name)
        return Const(v)
    except ValueError:
        pass
    raise KeyError(f"Unknown signal or constant: {name!r}")


def _expr_to_dsl(expr, signal_map: dict[str, Signal]) -> Value:
    """Convert a veriflow_spec Expr (recursive) to a DSL Value."""
    from ._spec import Expr

    if isinstance(expr, (Signal, Const, Value)):
        return expr

    # If it's a string, treat as signal name or integer literal
    if isinstance(expr, str):
        return _name_to_value(expr, signal_map)

    if not isinstance(expr, Expr):
        raise TypeError(f"Expected Expr, got {type(expr).__name__}")

    if expr.op == "const":
        return Const(expr.parts[0], expr.width)

    if expr.op == "signal":
        return _name_to_value(expr.parts[0], signal_map)

    if expr.op == "binop":
        left = _expr_to_dsl(expr.parts[0], signal_map)
        right = _expr_to_dsl(expr.parts[2], signal_map)
        op = expr.parts[1]
        op_map = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "&": lambda a, b: a & b,
            "|": lambda a, b: a | b,
            "^": lambda a, b: a ^ b,
            "<<": lambda a, b: a << b,
            ">>": lambda a, b: a >> b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        if op not in op_map:
            raise NotImplementedError(f"Unsupported binary operator: {op}")
        return op_map[op](left, right)

    if expr.op == "unaryop":
        operand = _expr_to_dsl(expr.parts[1], signal_map)
        op = expr.parts[0]
        if op == "~":
            return ~operand
        if op == "-":
            return -operand
        raise NotImplementedError(f"Unsupported unary operator: {op}")

    if expr.op == "mux":
        cond = _expr_to_dsl(expr.parts[0], signal_map)
        t = _expr_to_dsl(expr.parts[1], signal_map)
        f = _expr_to_dsl(expr.parts[2], signal_map)
        return Mux(cond, t, f)

    if expr.op == "cat":
        parts = [_expr_to_dsl(p, signal_map) for p in expr.parts]
        return Cat(*parts)

    if expr.op == "slice":
        operand = _expr_to_dsl(expr.parts[0], signal_map)
        high = expr.parts[1]
        low = expr.parts[2]
        return operand[high:low]

    if expr.op in ("rol", "ror"):
        operand = _expr_to_dsl(expr.parts[0], signal_map)
        amount = int(expr.parts[1])
        amount_width = max(1, operand.width.bit_length())
        if expr.op == "rol":
            return _ROL(operand, Const(amount, amount_width), operand.width)
        else:  # ror
            actual_amount = (operand.width - amount) % operand.width
            return _ROL(operand, Const(actual_amount, amount_width), operand.width)

    raise NotImplementedError(f"Unsupported expr op: {expr.op}")


def _wire_to_dsl(wire: WireT, signal_map: dict[str, Signal]) -> Value:
    """Convert a WireT to a DSL Value.

    If the WireT has an expr, convert that. Otherwise look up by name.
    """
    if wire.expr is not None:
        return _expr_to_dsl(wire.expr, signal_map)
    return _name_to_value(wire.name, signal_map)


def from_timing_model(func) -> Module:
    """Convert a @vf_block(type='sequential') function to a DSL Module.

    The function must have default parameter values of type RegT/WireT
    so the adapter can extract signal names and widths.

    Port direction rules:
      - RegT that appears as a reg_next TARGET -> output port (module updates it)
      - RegT that does NOT appear as a target -> input port (module only reads it)
      - WireT -> input port

    Example:
        @vf_block(type="sequential")
        def counter(*, count_reg: RegT = RegT("count_reg", 8),
                          en: RegT = RegT("en", 1)) -> list[RegAssign]:
            return [reg_next(count_reg, mux(en, count_reg + 1, count_reg))]

        m = from_timing_model(counter)
        verilog = VerilogEmitter().emit(m)
    """
    if not hasattr(func, "_vf_block_type"):
        raise TypeError(f"{func.__name__} must be decorated with @vf_block")

    block_type = func._vf_block_type
    if block_type not in ("sequential", "combinational"):
        raise NotImplementedError(
            f"from_timing_model: block type {block_type!r} not yet supported"
        )

    hints = get_type_hints(func)
    sig = inspect.signature(func)

    # Step 1: Build parameter objects from defaults
    kwargs: dict[str, RegT | WireT] = {}
    param_meta: dict[str, dict] = {}  # name -> {type: "reg"|"wire", width, obj}
    for param_name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                          inspect.Parameter.VAR_KEYWORD):
            continue

        hint = hints.get(param_name)
        default = param.default

        if hint is RegT or isinstance(default, RegT):
            obj = default if isinstance(default, RegT) else RegT(param_name)
            kwargs[param_name] = obj
            param_meta[param_name] = {"kind": "reg", "width": obj.width, "obj": obj}

        elif hint is WireT or isinstance(default, WireT):
            obj = default if isinstance(default, WireT) else WireT(param_name, 32)
            kwargs[param_name] = obj
            param_meta[param_name] = {"kind": "wire", "width": obj.width, "obj": obj}

    # Step 2: Call the function to discover which registers are targets
    result = func(**kwargs)
    target_names: set[str] = set()
    if block_type == "sequential" and isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, RegAssign):
                target_names.add(item.target.name)

    # Step 3: Create Module with correct port directions
    m = Module(func.__name__)
    signal_map: dict[str, Signal] = {}

    if block_type == "combinational":
        # Combinational blocks have all inputs + one or more output wires.
        if isinstance(result, WireT):
            out_sig = Signal(result.width, name=f"{func.__name__}_out")
            m.add_output(out_sig)
            signal_map[f"{func.__name__}_out"] = out_sig
        elif isinstance(result, tuple):
            for i, r in enumerate(result):
                if isinstance(r, (WireT, RegT)):
                    out_sig = Signal(r.width, name=f"{func.__name__}_out_{i}")
                    m.add_output(out_sig)
                    signal_map[f"{func.__name__}_out_{i}"] = out_sig

    for param_name, meta in param_meta.items():
        s = Signal(meta["width"], name=param_name, reset=0 if meta["kind"] == "reg" else None)

        if meta["kind"] == "reg" and param_name in target_names:
            # Register this module updates -> output + internal signal
            m.add_output(s)
            m.add_signal(s)
        else:
            # Input-only (reg read-only or wire) -> input + internal signal
            m.add_input(s)
            m.add_signal(s)

        signal_map[param_name] = s

    # Step 4: Build domain assignments from result
    if block_type == "sequential":
        if not isinstance(result, (list, tuple)):
            raise TypeError(
                f"Sequential block must return list[RegAssign], got {type(result).__name__}"
            )
        for item in result:
            if not isinstance(item, RegAssign):
                raise TypeError(
                    f"Sequential block return items must be RegAssign, got {type(item).__name__}"
                )
            target_sig = signal_map.get(item.target.name)
            if target_sig is None:
                raise KeyError(f"Target signal {item.target.name!r} not found")

            # Convert next_value to DSL Value
            if isinstance(item.next_value, WireT):
                next_val = _wire_to_dsl(item.next_value, signal_map)
            elif isinstance(item.next_value, RegT):
                next_val = signal_map[item.next_value.name]
            elif isinstance(item.next_value, int):
                next_val = Const(item.next_value)
            else:
                raise TypeError(f"Unsupported next_value type: {type(item.next_value)}")

            # Handle enable: wrap in Mux if present
            if item.enable is not None:
                if isinstance(item.enable, (RegT, WireT)):
                    en_val = _wire_to_dsl(
                        item.enable if isinstance(item.enable, WireT)
                        else WireT(item.enable.name, item.enable.width),
                        signal_map,
                    )
                elif isinstance(item.enable, int):
                    en_val = Const(item.enable, 1)
                else:
                    raise TypeError(f"Unsupported enable type: {type(item.enable)}")
                next_val = Mux(en_val, next_val, target_sig)

            m.d.sync += target_sig.eq(next_val)

    elif block_type == "combinational":
        if isinstance(result, WireT):
            out_sig = signal_map[f"{func.__name__}_out"]
            val = _wire_to_dsl(result, signal_map)
            m.d.comb += out_sig.eq(val)
        elif isinstance(result, tuple):
            for i, r in enumerate(result):
                if isinstance(r, (WireT, RegT)):
                    out_sig = signal_map[f"{func.__name__}_out_{i}"]
                    val = _wire_to_dsl(r, signal_map)
                    m.d.comb += out_sig.eq(val)

    return m

"""veriflow_spec — Timing model protocol for v2 AI-to-RTL translation.

Provides typed primitives that encode NBA semantics structurally:
  RegT       — read-only register value at cycle T
  WireT      — combinational signal, same-cycle visible
  RegAssign  — NBA assignment action (reg_next() produces this)

AI agents write timing_model.py using these types. The structure
enforces NBA timing: it is impossible to return a RegT directly;
register updates MUST go through reg_next().

Usage in timing_model.py:
    @vf_block(type="sequential")
    def round_step(*, a_reg: RegT, b_reg: RegT, calc_en: RegT) -> list[RegAssign]:
        ss1 = rotate_left(a_reg + b_reg, 1)   # WireT
        return [reg_next(a_reg, ss1)]          # RegAssign

VeriFlow Translatable Subset
----------------------------
A timing_model.py @vf_block body is mechanically lowered to Verilog by the
adapter + emitter. To keep that lowering deterministic, restrict yourself
to the following five rules — anything outside this subset is rejected at
adapter time, not at simulation:

1. **Types only**: every parameter is annotated `RegT` or `WireT`; every
   return element of a sequential block is a `RegAssign` produced by
   `reg_next()`. Plain Python objects (lists, ints, strings) cannot cross
   the function boundary as signals — they are not lowerable.

2. **No Python control flow over runtime values**: `if`, `for`, `while` may
   appear ONLY when their condition / iterable depends on Python constants
   (e.g. `for stage in range(5):` to unroll cascaded muxes). Any branch on
   a `RegT`/`WireT` value must use `mux(cond, t, f)` instead.

3. **No comprehension producing variable-length signal lists**: list/dict
   comprehensions are fine for building constant tables, but the adapter
   walks parameters and `RegAssign` elements positionally, so the count
   must be statically known at adapter time.

4. **Bit-widths are int constants**: every `RegT(name, W)`, `WireT(name, W)`,
   and `slice_(sig, msb, lsb)` width/index must be a Python int literal or
   `Final[int]` constant. Widths derived from a signal value are not lowerable.

5. **Conditional updates use `enable=` OR `mux(cond, t, f)`, not Python `if`**:
   either `reg_next(target, value, en=cond)` or
   `reg_next(target, mux(cond, value, target))` is fine — the adapter
   lowers both. What you must NOT do is branch on `cond` and call
   `reg_next` from one side of an `if`; every `reg_next` must fire
   unconditionally so the adapter sees a deterministic list of updates.

Anything that breaks these rules belongs in `golden_model.py` (pure
algorithm reference), not in `timing_model.py` (the translatable contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

__all__ = [
    "RegT", "WireT", "RegAssign",
    "reg_next", "mux", "cat", "slice_",
    "vf_block", "vf_fsm",
    "Expr",
]


# ---------------------------------------------------------------------------
# Expression representation (internal, shared with DSL emitter)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Expr:
    """Hardware expression node — operator tree for later Verilog emission."""
    op: str
    width: int
    parts: tuple[Any, ...]

    def __repr__(self) -> str:
        if self.op == "const":
            return f"0x{self.parts[0]:x}"
        elif self.op == "signal":
            return str(self.parts[0])
        elif self.op == "binop":
            return f"({self.parts[0]} {self.parts[1]} {self.parts[2]})"
        elif self.op == "mux":
            return f"mux({self.parts[0]}, {self.parts[1]}, {self.parts[2]})"
        elif self.op == "cat":
            return f"cat({', '.join(str(p) for p in self.parts)})"
        elif self.op == "slice":
            return f"{self.parts[0]}[{self.parts[1]}:{self.parts[2]}]"
        else:
            return f"Expr({self.op})"


def _to_expr(obj: "RegT | WireT | _Coerced") -> Expr:
    """Convert a RegT, WireT, or _Coerced to an Expr for nested storage."""
    if isinstance(obj, RegT):
        return Expr("signal", obj.width, (obj.name,))
    if isinstance(obj, WireT):
        if obj.expr is not None:
            return obj.expr
        return Expr("signal", obj.width, (obj.name,))
    if isinstance(obj, _Coerced):
        return obj.expr
    raise TypeError(f"Cannot convert {type(obj).__name__} to Expr")


# ---------------------------------------------------------------------------
# Shared operator mixin (eliminates ~180 lines of duplication)
# ---------------------------------------------------------------------------

class _SignalOps:
    """Shared arithmetic/bitwise/comparison/slice operators for RegT and WireT.

    Both types delegate to WireT._from_binop / _from_slice / _from_unaryop.
    The mixin assumes subclasses provide `.width` and `.name` attributes.
    """

    # --- Arithmetic ---------------------------------------------------------

    def __add__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("+", self, other)

    def __radd__(self, other: int) -> "WireT":
        return WireT._from_binop("+", _coerce(other), self)

    def __sub__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("-", self, other)

    def __rsub__(self, other: int) -> "WireT":
        return WireT._from_binop("-", _coerce(other), self)

    def __mul__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("*", self, other)

    def __rmul__(self, other: int) -> "WireT":
        return WireT._from_binop("*", _coerce(other), self)

    # --- Bitwise ------------------------------------------------------------

    def __and__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("&", self, other)

    def __rand__(self, other: int) -> "WireT":
        return WireT._from_binop("&", _coerce(other), self)

    def __or__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("|", self, other)

    def __ror__(self, other: int) -> "WireT":
        return WireT._from_binop("|", _coerce(other), self)

    def __xor__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("^", self, other)

    def __rxor__(self, other: int) -> "WireT":
        return WireT._from_binop("^", _coerce(other), self)

    def __invert__(self) -> "WireT":
        return WireT._from_unaryop("~", self)

    # --- Shifts -------------------------------------------------------------

    def __lshift__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop("<<", self, other)

    def __rlshift__(self, other: int) -> "WireT":
        return WireT._from_binop("<<", _coerce(other), self)

    def __rshift__(self, other: "RegT | WireT | int") -> "WireT":
        return WireT._from_binop(">>", self, other)

    def __rrshift__(self, other: int) -> "WireT":
        return WireT._from_binop(">>", _coerce(other), self)

    # --- Comparison ---------------------------------------------------------

    def __eq__(self, other) -> "WireT":   # type: ignore[override]
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop("==", self, other)

    def __ne__(self, other) -> "WireT":   # type: ignore[override]
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop("!=", self, other)

    def __lt__(self, other: "RegT | WireT | int") -> "WireT":
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop("<", self, other)

    def __le__(self, other: "RegT | WireT | int") -> "WireT":
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop("<=", self, other)

    def __gt__(self, other: "RegT | WireT | int") -> "WireT":
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop(">", self, other)

    def __ge__(self, other: "RegT | WireT | int") -> "WireT":
        if not isinstance(other, (RegT, WireT, int)):
            return NotImplemented
        return WireT._from_binop(">=", self, other)

    # --- Slicing ------------------------------------------------------------

    def __getitem__(self, key: int | slice) -> "WireT":
        if isinstance(key, int):
            return WireT._from_slice(self, key, key)
        elif isinstance(key, slice):
            high = key.start if key.start is not None else self.width - 1  # type: ignore[attr-defined]
            low = key.stop if key.stop is not None else 0
            return WireT._from_slice(self, high, low)
        raise TypeError(f"unsupported index type: {type(key)}")

    # --- Identity hash + bool guard -----------------------------------------

    __hash__ = object.__hash__

    def __bool__(self) -> bool:
        raise TypeError(
            f"Cannot convert {type(self).__name__} to bool. Use explicit comparison."
        )


# ---------------------------------------------------------------------------
# RegT — read-only register value at cycle T
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegT(_SignalOps):
    """Read-only register value sampled at cycle T (posedge).

    In a timing_model function, parameters typed as RegT mean:
    "the value this register holds at the current clock edge".

    RegT must NEVER appear in a function's return value.
    Use reg_next() to express register updates.
    """
    name: str
    width: int = 32


# ---------------------------------------------------------------------------
# WireT — combinational signal, same-cycle visible
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WireT(_SignalOps):
    """Combinational signal visible in the same cycle it is computed.

    Created by:
      - arithmetic/bitwise operations on RegT/WireT
      - mux(), cat(), slice_() functions
      - explicit construction: WireT(name, width, expr)

    WireT is the ONLY type that can appear in a reg_next() second argument.
    """
    name: str
    width: int
    expr: Expr | None = None

    @classmethod
    def _from_binop(cls, op: str, left: "RegT | WireT", right: "RegT | WireT | int") -> "WireT":
        r = _coerce(right)
        w = _infer_binop_width(op, left.width, r.width)
        return cls(
            name=f"({left.name} {op} {r.name})",
            width=w,
            expr=Expr("binop", w, (_to_expr(left), op, _to_expr(r))),
        )

    @classmethod
    def _from_unaryop(cls, op: str, operand: "RegT | WireT") -> "WireT":
        w = operand.width
        return cls(
            name=f"({op}{operand.name})",
            width=w,
            expr=Expr("unaryop", w, (op, _to_expr(operand))),
        )

    @classmethod
    def _from_slice(cls, operand: "RegT | WireT", high: int, low: int) -> "WireT":
        w = high - low + 1
        return cls(
            name=f"{operand.name}[{high}:{low}]",
            width=w,
            expr=Expr("slice", w, (_to_expr(operand), high, low)),
        )

    @classmethod
    def _from_identity(cls, val: "RegT | WireT") -> "WireT":
        """Passthrough: return the WireT unchanged, or wrap a RegT as a WireT."""
        if isinstance(val, WireT):
            return val
        return cls(
            name=val.name,
            width=val.width,
            expr=Expr("signal", val.width, (val.name,)),
        )


# ---------------------------------------------------------------------------
# RegAssign — NBA assignment action
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegAssign:
    """NBA assignment: at T+1, target register takes next_value.

    Created exclusively via reg_next(). Must be returned from a
    @vf_block(type="sequential") function.
    """
    target: RegT
    next_value: WireT | int
    enable: WireT | RegT | int | None = None

    def __post_init__(self):
        # Validate: target must be RegT
        if not isinstance(self.target, RegT):
            raise TypeError(f"RegAssign target must be RegT, got {type(self.target).__name__}")


# ---------------------------------------------------------------------------
# Protocol functions
# ---------------------------------------------------------------------------

def reg_next(curr: RegT, next_value: "WireT | int", *, en: "WireT | RegT | int | None" = None) -> RegAssign:
    """Explicit NBA assignment: at posedge T+1, register `curr` takes `next_value`.

    Args:
        curr: the register being updated (RegT)
        next_value: value to commit next cycle (WireT or int)
        en: optional enable — when falsy, register holds its current value

    Returns:
        RegAssign — must appear in a @vf_block sequential function's return list.

    Raises:
        TypeError: if curr is not RegT or next_value is RegAssign.
    """
    if isinstance(next_value, RegAssign):
        raise TypeError("reg_next next_value must be WireT or int, not RegAssign")
    return RegAssign(target=curr, next_value=next_value, enable=en)


def mux(cond: "WireT | RegT | int", t: "WireT | RegT | int", f: "WireT | RegT | int") -> WireT:
    """Combinational multiplexer: cond ? t : f."""
    cond_v = _coerce(cond)
    t_v = _coerce(t)
    f_v = _coerce(f)
    w = max(t_v.width, f_v.width)
    return WireT(
        name=f"mux({cond_v.name}, {t_v.name}, {f_v.name})",
        width=w,
        expr=Expr("mux", w, (_to_expr(cond_v), _to_expr(t_v), _to_expr(f_v))),
    )


def cat(*parts: "RegT | WireT | int") -> WireT:
    """Bit concatenation — MSB-first, like Verilog {a, b, c}.

    Cat(a, b, c) means {a, b, c} with a as the MSB portion.
    """
    if not parts:
        raise ValueError("cat() requires at least one argument")
    coerced = [_coerce(p) for p in parts]
    w = sum(p.width for p in coerced)
    return WireT(
        name=f"cat({', '.join(p.name for p in coerced)})",
        width=w,
        expr=Expr("cat", w, tuple(_to_expr(p) for p in coerced)),
    )


def slice_(sig: "RegT | WireT", msb: int, lsb: int) -> WireT:
    """Bit slice: sig[msb:lsb]. Equivalent to Verilog part-select."""
    return WireT._from_slice(sig, msb, lsb)


def rotate_left(x: "RegT | WireT", n: int) -> WireT:
    """Left rotate by n bits: {x[W-1-n:0], x[W-1:W-n]}.

    n must be a constant integer (not a signal).
    Maps to Verilog concatenation for constant n.
    """
    w = x.width
    n = n % w
    if n == 0:
        return WireT._from_identity(x)
    return WireT(
        name=f"ROL({x.name}, {n})",
        width=w,
        expr=Expr("rol", w, (_to_expr(x), n)),
    )


def rotate_right(x: "RegT | WireT", n: int) -> WireT:
    """Right rotate by n bits: {x[n-1:0], x[W-1:n]}.

    n must be a constant integer (not a signal).
    """
    w = x.width
    n = n % w
    if n == 0:
        return WireT._from_identity(x)
    return WireT(
        name=f"ROR({x.name}, {n})",
        width=w,
        expr=Expr("ror", w, (_to_expr(x), n)),
    )


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

# Registry of registered timing_model functions
_TIMING_MODEL_REGISTRY: dict[str, Callable] = {}


def vf_block(type: str = "sequential") -> Callable:
    """Decorator that marks a function as a timing_model block.

    type="sequential": parameters are RegT/WireT, returns list[RegAssign].
    type="combinational": parameters are RegT/WireT, returns WireT.
    type="fsm": parameters include fsm state, body uses fsm.case().
    """
    def decorator(func: Callable) -> Callable:
        func._vf_block_type = type
        func._vf_block_name = func.__name__
        _TIMING_MODEL_REGISTRY[func.__name__] = func
        return func
    return decorator


def vf_fsm(states: list[str], reset_state: str) -> Callable:
    """Decorator for FSM modules (stub — full implementation in v2.1).

    Currently just records metadata on the decorated function.
    """
    def decorator(func: Callable) -> Callable:
        func._vf_fsm_states = states
        func._vf_fsm_reset = reset_state
        return vf_block(type="fsm")(func)
    return decorator


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Coerced:
    """Wrapper for coerced integer values."""
    name: str
    width: int
    expr: Expr


def _coerce(value: "RegT | WireT | int") -> "RegT | WireT | _Coerced":
    """Coerce a Python int to a coerced value (nameless, width-inferred)."""
    if isinstance(value, (RegT, WireT)):
        return value
    if isinstance(value, int):
        # Normalize bools to ints (Python bool is subclass of int)
        value = int(value)
        width = max(1, value.bit_length())
        return _Coerced(name=str(value), width=width, expr=Expr("const", width, (value,)))
    raise TypeError(f"Cannot coerce {type(value).__name__} — expected RegT, WireT, or int")


def _infer_binop_width(op: str, w1: int, w2: int) -> int:
    """Infer result width for binary operators."""
    if op in ("+", "-"):
        return max(w1, w2) + 1
    elif op == "*":
        return w1 + w2
    elif op in ("&", "|", "^"):
        return max(w1, w2)
    elif op in ("<<", ">>"):
        return w1
    elif op in ("==", "!=", "<", "<=", ">", ">="):
        return 1
    else:
        return max(w1, w2)

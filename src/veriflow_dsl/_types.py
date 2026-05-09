"""VeriFlow DSL Layer 0: Data types and operators.

Provides hardware-oriented value types that serve dual purpose:
  1. Description: represent hardware signals and their relationships
  2. Evaluation: carry concrete integer values for golden model simulation

Each expression node implements _eval(inputs) -> int for cycle-accurate
simulation. The expression tree can also be traversed for Verilog emission.

Inspired by Amaranth's Value/Signal/Const, but with concrete evaluation
built in (Amaranth separates description from simulation).
"""

from __future__ import annotations

__all__ = ["Value", "Const", "Signal", "Cat", "Mux", "Assignment"]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _mask(width: int) -> int:
    """Return a bitmask of *width* bits (e.g. _mask(32) == 0xFFFFFFFF)."""
    if width <= 0:
        raise ValueError(f"width must be > 0, got {width}")
    return (1 << width) - 1


def _bit_length(value: int) -> int:
    """Return minimum bit width to represent *value* (unsigned)."""
    if value < 0:
        raise ValueError(f"negative values not supported, got {value}")
    if value == 0:
        return 1
    return value.bit_length()


# ---------------------------------------------------------------------------
# Value — abstract base
# ---------------------------------------------------------------------------

class Value:
    """Abstract base for all DSL values (signals, constants, expressions).

    Properties:
        width: bit width of this value
        value: concrete integer value (None if unevaluated)
        name: human-readable name (empty string if unnamed)
    """

    # Subclasses override these
    _width: int = 0
    _value: int | None = None
    _name: str = ""

    @property
    def width(self) -> int:
        return self._width

    @property
    def value(self) -> int | None:
        return self._value

    @property
    def name(self) -> str:
        return self._name

    # --- Evaluation --------------------------------------------------------

    def _eval(self, inputs: dict) -> int:
        """Evaluate this expression tree given current signal state.

        Args:
            inputs: mapping from Signal.name -> current integer value.

        Returns:
            Concrete integer result.

        Raises:
            ValueError: if a required signal is not in *inputs*.
        """
        raise NotImplementedError

    # --- Arithmetic operators ----------------------------------------------

    def __add__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("+", self, other, max(self._width, other._width) + 1)

    def __radd__(self, other) -> "_BinOp":
        return _coerce(other).__add__(self)

    def __sub__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("-", self, other, max(self._width, other._width) + 1)

    def __rsub__(self, other) -> "_BinOp":
        return _coerce(other).__sub__(self)

    def __mul__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("*", self, other, self._width + other._width)

    def __rmul__(self, other) -> "_BinOp":
        return _coerce(other).__mul__(self)

    def __neg__(self) -> "_UnaryOp":
        return _UnaryOp("-", self, self._width + 1)

    # --- Bitwise operators -------------------------------------------------

    def __and__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("&", self, other, max(self._width, other._width))

    def __rand__(self, other) -> "_BinOp":
        return _coerce(other).__and__(self)

    def __or__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("|", self, other, max(self._width, other._width))

    def __ror__(self, other) -> "_BinOp":
        return _coerce(other).__or__(self)

    def __xor__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("^", self, other, max(self._width, other._width))

    def __rxor__(self, other) -> "_BinOp":
        return _coerce(other).__xor__(self)

    def __invert__(self) -> "_UnaryOp":
        return _UnaryOp("~", self, self._width)

    def __lshift__(self, other) -> "_BinOp":
        other = _coerce(other)
        shift_cap = min(other._width, 8)
        # Cap extra width to avoid explosion (shifting by > width produces zeros
        # in upper bits, so width * 2 is more than sufficient for hardware).
        extra = min(1 << shift_cap, self._width)
        return _BinOp("<<", self, other, self._width + extra)

    def __rlshift__(self, other) -> "_BinOp":
        return _coerce(other).__lshift__(self)

    def __rshift__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp(">>", self, other, self._width)

    def __rrshift__(self, other) -> "_BinOp":
        return _coerce(other).__rshift__(self)

    # --- Comparison operators (return 1-bit Value) --------------------------

    def __eq__(self, other) -> "_BinOp":   # type: ignore[override]
        if not isinstance(other, (Value, int)):
            return NotImplemented
        other = _coerce(other)
        return _BinOp("==", self, other, 1)

    def __ne__(self, other) -> "_BinOp":   # type: ignore[override]
        if not isinstance(other, (Value, int)):
            return NotImplemented
        other = _coerce(other)
        return _BinOp("!=", self, other, 1)

    def __lt__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("<", self, other, 1)

    def __le__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp("<=", self, other, 1)

    def __gt__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp(">", self, other, 1)

    def __ge__(self, other) -> "_BinOp":
        other = _coerce(other)
        return _BinOp(">=", self, other, 1)

    # --- Slicing -----------------------------------------------------------

    def __getitem__(self, key) -> "_Slice":
        if isinstance(key, int):
            return _Slice(self, key, key)
        elif isinstance(key, slice):
            high = key.start if key.start is not None else self._width - 1
            low = key.stop if key.stop is not None else 0
            return _Slice(self, high, low)
        else:
            raise TypeError(f"unsupported index type: {type(key)}")

    # --- Helper methods ----------------------------------------------------

    def rotate_left(self, n: int | Value) -> "_ROL":
        """Rotate left by *n* bits. Maps to Verilog {x[W-1-N:0], x[W-1:W-N]}."""
        if isinstance(n, int):
            n = Const(n, max(1, self._width.bit_length()))
        return _ROL(self, n, self._width)

    def rotate_right(self, n: int | Value) -> "_ROL":
        amount_width = max(1, self._width.bit_length())
        if isinstance(n, int):
            n = n % self._width
            n = Const(self._width - n, amount_width)
        else:
            n = Const(self._width, amount_width) - n
        return _ROL(self, n, self._width)

    def __repr__(self) -> str:
        cls = type(self).__name__
        return f"{cls}(name={self._name!r}, width={self._width}, value={self._value})"

    def __hash__(self) -> int:
        return id(self)

    # bool() must not trigger __eq__
    def __bool__(self) -> bool:
        raise TypeError(
            "Cannot convert DSL Value to bool. "
            "Use explicit comparison: if (sig == 1) instead of if sig."
        )


# ---------------------------------------------------------------------------
# Const — compile-time constant
# ---------------------------------------------------------------------------

class Const(Value):
    """Compile-time constant value.

    Width is inferred from the value if not specified.
    """

    def __init__(self, value: int, width: int | None = None):
        if value < 0:
            raise ValueError(f"Const value must be non-negative, got {value}")
        self._value = value
        self._width = width if width is not None else _bit_length(value)
        if self._value > _mask(self._width):
            raise ValueError(
                f"Value {value} does not fit in {self._width} bits "
                f"(max {_mask(self._width)})"
            )
        self._name = f"{self._value}"

    def _eval(self, inputs: dict) -> int:
        return self._value


# ---------------------------------------------------------------------------
# Signal — hardware signal placeholder
# ---------------------------------------------------------------------------

class Signal(Value):
    """Hardware signal — the fundamental wire/register placeholder.

    A Signal does NOT know whether it is combinational or registered.
    Timing is determined by which domain (comb or sync) assigns to it.

    Args:
        width: bit width (default 1)
        name: human-readable name (auto-generated if None)
        reset: value after reset (default 0)
        reset_less: if True, excluded from reset block
    """

    _auto_counter = 0

    def __init__(
        self,
        width: int = 1,
        *,
        name: str | None = None,
        reset: int = 0,
        reset_less: bool = False,
    ):
        if width <= 0:
            raise ValueError(f"Signal width must be > 0, got {width}")
        self._width = width
        if name is None:
            Signal._auto_counter += 1
            name = f"sig_{Signal._auto_counter}"
        self._name = name
        self._reset = reset
        self._reset_less = reset_less
        self._value = None  # unevaluated until simulation

    @property
    def reset(self) -> int:
        return self._reset

    @property
    def reset_less(self) -> bool:
        return self._reset_less

    def eq(self, value) -> "Assignment":
        """Create an assignment statement for use with m.d.comb/sync."""
        return Assignment(self, _coerce(value))

    def _eval(self, inputs: dict) -> int:
        if self._name in inputs:
            return inputs[self._name] & _mask(self._width)
        if self._value is not None:
            return self._value
        raise ValueError(f"Signal {self._name!r} has no value in inputs")


# ---------------------------------------------------------------------------
# Assignment — target.eq(value)
# ---------------------------------------------------------------------------

class Assignment:
    """Represents target_signal.eq(value_expression).

    Not bound to a domain yet — added to a domain via m.d.comb += or m.d.sync +=.
    """

    def __init__(self, target: Value, value: Value):
        if not isinstance(target, Signal):
            raise TypeError(
                f"Assignment target must be a Signal, got {type(target).__name__}"
            )
        self.target = target
        self.value = value


# ---------------------------------------------------------------------------
# Internal expression nodes
# ---------------------------------------------------------------------------

class _BinOp(Value):
    """Binary operator expression node."""

    _OP_FUNCS = {
        "+":  lambda a, b, w: (a + b) & _mask(w),
        "-":  lambda a, b, w: (a - b) & _mask(w),
        "*":  lambda a, b, w: (a * b) & _mask(w),
        "&":  lambda a, b, w: (a & b),
        "|":  lambda a, b, w: (a | b),
        "^":  lambda a, b, w: (a ^ b),
        "<<": lambda a, b, w: (a << b) & _mask(w),
        ">>": lambda a, b, w: (a >> b),
        "==": lambda a, b, w: int(a == b),
        "!=": lambda a, b, w: int(a != b),
        "<":  lambda a, b, w: int(a < b),
        "<=": lambda a, b, w: int(a <= b),
        ">":  lambda a, b, w: int(a > b),
        ">=": lambda a, b, w: int(a >= b),
    }

    def __init__(self, op: str, left: Value, right: Value, width: int):
        self._op = op
        self._left = left
        self._right = right
        self._width = width
        self._name = f"({left._name} {op} {right._name})"

    def _eval(self, inputs: dict) -> int:
        lv = self._left._eval(inputs)
        rv = self._right._eval(inputs)
        func = self._OP_FUNCS.get(self._op)
        if func is None:
            raise ValueError(f"unsupported binary op: {self._op}")
        return func(lv, rv, self._width)


class _UnaryOp(Value):
    """Unary operator expression node."""

    _OP_FUNCS = {
        "~": lambda a, w: (~a) & _mask(w),
        "-": lambda a, w: (-a) & _mask(w),
    }

    def __init__(self, op: str, operand: Value, width: int):
        self._op = op
        self._operand = operand
        self._width = width
        self._name = f"({op}{operand._name})"

    def _eval(self, inputs: dict) -> int:
        v = self._operand._eval(inputs)
        func = self._OP_FUNCS.get(self._op)
        if func is None:
            raise ValueError(f"unsupported unary op: {self._op}")
        return func(v, self._width)


class _Slice(Value):
    """Bit slice expression node: operand[high:low]."""

    def __init__(self, operand: Value, high: int, low: int):
        if low < 0 or high < low or high >= operand._width:
            raise ValueError(
                f"Invalid slice [{high}:{low}] for width {operand._width}"
            )
        self._operand = operand
        self._high = high
        self._low = low
        self._width = high - low + 1
        self._name = f"{operand._name}[{high}:{low}]"

    def _eval(self, inputs: dict) -> int:
        v = self._operand._eval(inputs)
        return (v >> self._low) & _mask(self._width)


class _Concat(Value):
    """Concatenation expression node: Cat(a, b, ...) → {a, b, ...}."""

    def __init__(self, parts: tuple[Value, ...]):
        self._parts = parts
        self._width = sum(p._width for p in parts)
        self._name = "Cat(" + ", ".join(p._name for p in parts) + ")"

    def _eval(self, inputs: dict) -> int:
        result = 0
        for p in self._parts:
            result = (result << p._width) | (p._eval(inputs) & _mask(p._width))
        return result


class _Mux(Value):
    """Multiplexer expression node: Mux(sel, val_true, val_false)."""

    def __init__(self, cond: Value, val_true: Value, val_false: Value):
        self._cond = cond
        self._val_true = val_true
        self._val_false = val_false
        self._width = max(val_true._width, val_false._width)
        self._name = f"Mux({cond._name}, {val_true._name}, {val_false._name})"

    def _eval(self, inputs: dict) -> int:
        c = self._cond._eval(inputs)
        if c:
            return self._val_true._eval(inputs) & _mask(self._width)
        else:
            return self._val_false._eval(inputs) & _mask(self._width)


class _ROL(Value):
    """Rotate-left expression node."""

    def __init__(self, operand: Value, amount: Value, width: int):
        self._operand = operand
        self._amount = amount
        self._width = width
        self._name = f"ROL({operand._name}, {amount._name})"

    def _eval(self, inputs: dict) -> int:
        v = self._operand._eval(inputs) & _mask(self._width)
        n = self._amount._eval(inputs) % self._width
        m = _mask(self._width)
        return ((v << n) | (v >> (self._width - n))) & m if n else v


# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------

def Cat(*values: Value) -> Value:
    """Concatenation — MSB-first, matching Verilog {a, b, ...}.

    Cat(a, b) produces {a, b} where 'a' occupies the MSB bits.
    """
    if not values:
        raise ValueError("Cat requires at least one argument")
    coerced = tuple(_coerce(v) for v in values)
    if len(coerced) == 1:
        return coerced[0]
    return _Concat(coerced)


def Mux(sel: Value, val_true: Value, val_false: Value) -> Value:
    """Multiplexer: returns *val_true* if *sel* != 0, else *val_false*."""
    return _Mux(_coerce(sel), _coerce(val_true), _coerce(val_false))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce(value) -> Value:
    """Coerce a Python int to a Const, or return a Value as-is."""
    if isinstance(value, Value):
        return value
    if isinstance(value, int):
        return Const(value)
    raise TypeError(
        f"Cannot coerce {type(value).__name__} to Value. "
        f"Expected int, Signal, Const, or expression."
    )

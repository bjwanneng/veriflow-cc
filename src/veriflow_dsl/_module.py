"""VeriFlow DSL Layer 1: Module, Domain, and timing semantics.

Implements the Amaranth-inspired domain model where timing is a property
of assignments, not signals:

    m.d.comb += wire_out.eq(a ^ b)   # combinational, same-cycle
    m.d.sync += counter.eq(counter + 1)  # registered, next-cycle

This replaces the informal # wire / # reg_next comment annotations with
structural guarantees enforced by the DSL.

Domain analysis after all assignments are collected:
    - comb-only assignments  → "wire" (always @* or assign)
    - sync-only assignments  → "reg_next" (always @(posedge clk) <=)
    - both domains           → SyntaxError (driver conflict)
"""

from __future__ import annotations

import warnings
from typing import Optional

from ._types import Signal, Assignment, Value

__all__ = ["Module", "Domain", "DomainCollection"]


# ---------------------------------------------------------------------------
# Port declaration
# ---------------------------------------------------------------------------

class _PortDecl:
    """Port declaration with direction, width, and timing metadata."""

    def __init__(
        self,
        name: str,
        direction: str,
        width: int,
        timing: str = "wire",
        reset: int = 0,
        reset_less: bool = False,
    ):
        self.name = name
        self.direction = direction  # "input" | "output"
        self.width = width
        self.timing = timing       # "wire" | "reg_next"
        self.reset = reset
        self.reset_less = reset_less


# ---------------------------------------------------------------------------
# Domain — named group of assignments with shared timing semantics
# ---------------------------------------------------------------------------

class Domain:
    """A named group of assignments sharing timing semantics.

    Do not construct directly — use Module.d.comb or Module.d.sync.
    """

    def __init__(self, name: str, invalidate_cb=None):
        if name not in ("comb", "sync"):
            raise ValueError(f"Domain name must be 'comb' or 'sync', got {name!r}")
        self._name = name
        self._assignments: list[Assignment] = []
        self._invalidate_cb = invalidate_cb

    @property
    def name(self) -> str:
        return self._name

    @property
    def assignments(self) -> list[Assignment]:
        return list(self._assignments)

    def __iadd__(self, assignment_or_list) -> "Domain":
        """Add assignment(s) to this domain.

        Usage:
            m.d.comb += wire_out.eq(a ^ b)
            m.d.sync += [counter.eq(counter + 1), state.eq(next_state)]
        """
        if isinstance(assignment_or_list, Assignment):
            self._assignments.append(assignment_or_list)
        elif isinstance(assignment_or_list, (list, tuple)):
            for item in assignment_or_list:
                if not isinstance(item, Assignment):
                    raise TypeError(
                        f"Expected Assignment, got {type(item).__name__}"
                    )
                self._assignments.append(item)
        else:
            raise TypeError(
                f"Expected Assignment or list of Assignments, "
                f"got {type(assignment_or_list).__name__}"
            )
        if self._invalidate_cb:
            self._invalidate_cb()
        return self


# ---------------------------------------------------------------------------
# DomainCollection — provides .comb and .sync on Module
# ---------------------------------------------------------------------------

class DomainCollection:
    """Provides .comb and .sync domain access on a Module.

    Uses regular attributes (not properties) so that += works correctly.
    Python's += on a property tries to reassign, which fails without a setter.
    """

    def __init__(self):
        self.comb: Domain = Domain("comb")
        """Combinational domain — same-cycle, maps to always @* or assign."""
        self.sync: Domain = Domain("sync")
        """Synchronous domain — next-cycle, maps to always @(posedge clk) <=."""
        self._invalidate_cb = None  # set by Module.__init__


    def _propagate_callback(self):
        """Forward invalidate callback to both domains."""
        if self._invalidate_cb:
            self.comb._invalidate_cb = self._invalidate_cb
            self.sync._invalidate_cb = self._invalidate_cb

    def __getitem__(self, name: str) -> Domain:
        """Access domain by name."""
        if name == "comb":
            return self.comb
        elif name == "sync":
            return self.sync
        raise KeyError(f"Unknown domain {name!r}")


# ---------------------------------------------------------------------------
# Module — central hardware module container
# ---------------------------------------------------------------------------

class Module:
    """Central container for a hardware module description.

    Directly inspired by Amaranth's Module class, adapted for VeriFlow's
    Python-golden-model-to-Verilog pipeline.

    Usage:
        m = Module("my_module")
        a = Signal(8, name="a")
        b = Signal(8, name="b")
        m.d.comb += out.eq(a + b)
    """

    def __init__(self, name: str):
        self._name = name
        self.d = DomainCollection()
        self.d._invalidate_cb = self.invalidate_analysis
        self.d._propagate_callback()
        self._ports: dict[str, _PortDecl] = {}
        self._submodules: list[tuple[str, "Module"]] = []
        self._all_signals: dict[str, Signal] = {}  # name -> Signal
        self._analysis_cache: dict | None = None

    @property
    def name(self) -> str:
        return self._name

    # --- Port management ---------------------------------------------------

    def add_input(self, signal: Signal) -> None:
        """Declare an input port."""
        if not isinstance(signal, Signal):
            raise TypeError(f"Expected Signal, got {type(signal).__name__}")
        self._ports[signal.name] = _PortDecl(
            name=signal.name,
            direction="input",
            width=signal.width,
        )
        self._all_signals[signal.name] = signal

    def add_output(self, signal: Signal) -> None:
        """Declare an output port. Timing is derived from domain analysis."""
        if not isinstance(signal, Signal):
            raise TypeError(f"Expected Signal, got {type(signal).__name__}")
        self._ports[signal.name] = _PortDecl(
            name=signal.name,
            direction="output",
            width=signal.width,
            reset=signal.reset,
            reset_less=signal.reset_less,
        )
        self._all_signals[signal.name] = signal

    def add_signal(self, signal: Signal) -> None:
        """Declare an internal signal (not a port)."""
        if not isinstance(signal, Signal):
            raise TypeError(f"Expected Signal, got {type(signal).__name__}")
        self._all_signals[signal.name] = signal

    def add_submodule(self, sub: "Module", name: str | None = None) -> None:
        """Add a submodule instance."""
        inst_name = name or sub.name
        self._submodules.append((inst_name, sub))

    def ports(self) -> list[_PortDecl]:
        """Return all port declarations in insertion order."""
        return list(self._ports.values())

    @property
    def signals(self) -> dict[str, Signal]:
        """All declared signals (ports + internal)."""
        return dict(self._all_signals)

    @property
    def submodules(self) -> list[tuple[str, "Module"]]:
        """All submodule instances: [(name, Module), ...]."""
        return list(self._submodules)

    # --- Domain analysis ---------------------------------------------------

    def analyze(self) -> dict:
        """Analyze domain assignments and return timing metadata.

        Results are cached; call invalidate_analysis() after modifying
        domain assignments or signals.

        Returns:
            {
                "signals": {
                    "sig_name": {
                        "timing": "wire" | "reg_next",
                        "width": int,
                        "is_port": bool,
                        "direction": "input" | "output" | "internal",
                        "reset": int,
                        "reset_less": bool,
                    },
                    ...
                },
                "comb_assignments": [(target_name, value_expr), ...],
                "sync_assignments": [(target_name, value_expr), ...],
                "golden_to_port": {"sig_reg": "port_name", ...},
                "port_widths": {"port_name": width, ...},
                "input_ports": {"port_name": width, ...},
            }

        Raises:
            SyntaxError: if a signal is assigned in both comb and sync domains.
        """
        if self._analysis_cache is not None:
            return self._analysis_cache
        # Collect assignment targets per domain
        comb_targets: dict[str, Assignment] = {}
        sync_targets: dict[str, Assignment] = {}

        for asn in self.d.comb.assignments:
            name = asn.target.name
            if name in comb_targets:
                raise SyntaxError(
                    f"Signal {name!r} has multiple drivers in comb domain"
                )
            comb_targets[name] = asn

        for asn in self.d.sync.assignments:
            name = asn.target.name
            if name in sync_targets:
                raise SyntaxError(
                    f"Signal {name!r} has multiple drivers in sync domain"
                )
            sync_targets[name] = asn

        # Check for driver conflicts
        conflicts = set(comb_targets.keys()) & set(sync_targets.keys())
        if conflicts:
            raise SyntaxError(
                f"Driver conflict: signals {conflicts} are assigned in "
                f"both comb and sync domains"
            )

        # Classify each signal
        all_assigned = set(comb_targets.keys()) | set(sync_targets.keys())
        result_signals: dict = {}
        golden_to_port: dict = {}
        port_widths: dict = {}
        input_ports: dict = {}

        for name, sig in self._all_signals.items():
            is_port = name in self._ports
            port_decl = self._ports.get(name)
            direction = port_decl.direction if port_decl else "internal"

            if name in comb_targets:
                timing = "wire"
            elif name in sync_targets:
                timing = "reg_next"
            else:
                timing = "wire"  # unassigned signals default to wire

            result_signals[name] = {
                "timing": timing,
                "width": sig.width,
                "is_port": is_port,
                "direction": direction,
                "reset": sig.reset,
                "reset_less": sig.reset_less,
            }

            if is_port and direction == "output":
                golden_to_port[name] = name
                port_widths[name] = sig.width
            elif is_port and direction == "input":
                input_ports[name] = sig.width

        # Warn about undriven output ports
        for name in self._ports:
            if self._ports[name].direction == "output" and name not in all_assigned:
                warnings.warn(
                    f"Output port {name!r} is never assigned in any domain. "
                    f"Generated Verilog will have a dangling output.",
                    stacklevel=2,
                )

        result = {
            "signals": result_signals,
            "comb_assignments": [
                (asn.target.name, asn.value) for asn in self.d.comb.assignments
            ],
            "sync_assignments": [
                (asn.target.name, asn.value) for asn in self.d.sync.assignments
            ],
            "golden_to_port": golden_to_port,
            "port_widths": port_widths,
            "input_ports": input_ports,
        }
        self._analysis_cache = result
        return result

    def invalidate_analysis(self) -> None:
        """Clear cached analysis. Call after modifying domain assignments."""
        self._analysis_cache = None

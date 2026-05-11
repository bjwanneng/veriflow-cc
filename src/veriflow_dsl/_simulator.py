"""VeriFlow DSL cycle-accurate simulator.

Produces list[dict] traces compatible with vcd2table.py and cocotb_template.py.
The trace format is identical to what design_spec.py compute(trace=True) produces,
so the downstream pipeline is completely unchanged.

Simulation algorithm (per step):
    1. Evaluate all m.d.comb assignments (combinational, same-cycle)
    2. Record trace snapshot (all signal values)
    3. Apply all m.d.sync assignments (registered, next-cycle, NBA semantics)

This implements the T/T+1 timing model from coding_style.md Section 27:
    - Combinational outputs are visible in the current cycle snapshot
    - Registered outputs are visible starting the NEXT cycle
"""

from __future__ import annotations

from ._types import Signal, Value, Const, _mask
from ._module import Module

__all__ = ["CycleSimulator"]


class CycleSimulator:
    """Cycle-accurate simulator for VeriFlow DSL modules.

    Produces list[dict] traces compatible with vcd2table.py and cocotb_template.py.
    """

    def __init__(self, module: Module):
        self._module = module
        self._state: dict[str, int] = {}
        self._inputs: dict[str, int] = {}
        self._trace: list[dict[str, int]] = []
        self._analysis = module.analyze()
        self.reset()

    def reset(self) -> None:
        """Initialize all registered signals to their reset values.

        Combinational signals are left unevaluated until the first step().
        """
        self._state = {}
        self._inputs = {}
        self._trace = []

        for name, info in self._analysis["signals"].items():
            if info["timing"] == "reg_next":
                self._state[name] = info["reset"]
            else:
                # Combinational signals start at 0 (will be computed)
                self._state[name] = 0

    def set_input(self, name: str, value: int) -> None:
        """Set an input signal value for the current cycle.

        Args:
            name: signal name (must be a declared input port)
            value: integer value
        """
        sig_info = self._analysis["signals"].get(name)
        if sig_info is None:
            raise KeyError(f"Unknown signal {name!r}")
        if sig_info["direction"] != "input":
            raise ValueError(f"Signal {name!r} is not an input (direction={sig_info['direction']})")
        self._inputs[name] = value & _mask(sig_info["width"])

    def step(self) -> dict[str, int]:
        """Advance one clock cycle.

        1. Evaluate all comb-domain assignments (same-cycle)
        2. Record trace snapshot
        3. Apply all sync-domain assignments (next-cycle register update)

        Returns:
            Per-cycle snapshot dict {signal_name: int_value}.
        """
        # Build evaluation context: merge state + inputs
        ctx = dict(self._state)
        ctx.update(self._inputs)

        # Step 1: Evaluate comb-domain assignments until convergence.
        # Iterative propagation handles arbitrarily deep combinational chains
        # (e.g., a -> b -> c -> d). Terminates when no new values are computed
        # or max iterations reached (guards against circular dependencies).
        n_comb = len(self._analysis["comb_assignments"])
        max_iter = n_comb * 2 + 1 if n_comb > 0 else 1
        converged = False
        first_eval_error: str | None = None
        for iteration in range(max_iter):
            changed = False
            for target_name, value_expr in self._analysis["comb_assignments"]:
                sig_info = self._analysis["signals"][target_name]
                try:
                    computed = value_expr._eval(ctx)
                    masked = computed & _mask(sig_info["width"])
                    if ctx.get(target_name) != masked:
                        ctx[target_name] = masked
                        changed = True
                except (ValueError, KeyError) as e:
                    # Record the first error for diagnostics; keep current value
                    # so other signals that don't depend on this one can still converge.
                    if first_eval_error is None:
                        first_eval_error = f"{target_name}: {e}"
            if not changed:
                converged = True
                break

        if not converged and n_comb > 0:
            raise RuntimeError(
                f"Combinational logic did not converge after {max_iter} "
                f"iterations — circular dependency detected. "
                f"Check for combinational loops in the design."
            )

        # Post-convergence: verify every comb target was successfully evaluated.
        # Permanent errors (undefined signals, type mismatches) would leave a
        # target unset after the loop, which we must not silently ignore.
        for target_name, _ in self._analysis["comb_assignments"]:
            if target_name not in ctx:
                hint = f" First error: {first_eval_error}" if first_eval_error else ""
                raise RuntimeError(
                    f"Combinational signal '{target_name}' could not be evaluated.{hint} "
                    f"Check that all referenced signals are defined and have valid values."
                )

        # Step 2: Record trace snapshot (all signal values at this cycle)
        snapshot: dict[str, int] = {}
        for name, info in self._analysis["signals"].items():
            snapshot[name] = ctx.get(name, info["reset"])

        self._trace.append(snapshot)

        # Step 3: Apply sync-domain assignments (NBA semantics).
        # Evaluate all RHS expressions BEFORE updating any state.
        # NOTE: RHS expressions read from `ctx`, which includes comb-domain
        # outputs computed in Step 1. This correctly models Verilog semantics
        # where always @(posedge clk) reads wire outputs from always @* that
        # have already stabilized in the same time step.
        pending_updates: dict[str, int] = {}
        for target_name, value_expr in self._analysis["sync_assignments"]:
            sig_info = self._analysis["signals"][target_name]
            try:
                computed = value_expr._eval(ctx)
                pending_updates[target_name] = computed & _mask(sig_info["width"])
            except (ValueError, KeyError) as e:
                raise RuntimeError(
                    f"Sync assignment to '{target_name}' failed to evaluate: {e}"
                ) from e

        # Apply all updates simultaneously (NBA)
        for name, value in pending_updates.items():
            self._state[name] = value

        # Clear one-cycle inputs
        self._inputs = {}

        return snapshot

    def run(
        self,
        num_cycles: int,
        input_sequence: list[dict[str, int]] | None = None,
    ) -> list[dict[str, int]]:
        """Run for *num_cycles*, optionally applying input values per cycle.

        Args:
            num_cycles: number of clock cycles to simulate
            input_sequence: optional list of input dicts, one per cycle.
                Each dict maps signal names to integer values.
                If shorter than num_cycles, remaining cycles have no inputs
                driven (all inputs default to 0 / previous state).

        Returns:
            list of per-cycle dicts, matching compute(trace=True) format.
        """
        self.reset()

        for cycle in range(num_cycles):
            # Apply inputs for this cycle
            if input_sequence and cycle < len(input_sequence):
                for name, value in input_sequence[cycle].items():
                    self.set_input(name, value)
            self.step()

        return self._trace

    @property
    def trace(self) -> list[dict[str, int]]:
        """Access accumulated trace."""
        return list(self._trace)

    @property
    def state(self) -> dict[str, int]:
        """Current register state (after last step)."""
        return dict(self._state)

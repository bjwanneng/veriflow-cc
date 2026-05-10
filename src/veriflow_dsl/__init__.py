"""VeriFlow DSL — Python hardware description framework.

Provides formal timing semantics for VeriFlow's Python-to-Verilog pipeline.
Inspired by Amaranth's domain model: timing is a property of assignments,
not signals.

v2 additions: veriflow_spec protocol (RegT, WireT, RegAssign) for
AI-to-RTL translation via timing_model.py.

Usage:
    from veriflow_dsl import Module, Signal, Const, Cat, Mux
    from veriflow_dsl import CycleSimulator, VerilogEmitter
    from veriflow_dsl import RegT, WireT, reg_next, mux, cat, slice_
"""

from ._types import Signal, Const, Cat, Mux, Value
from ._module import Module, Domain, DomainCollection
from ._simulator import CycleSimulator
from ._emitter import VerilogEmitter
from ._trace import diff_traces, TraceDiff
from ._spec import (
    RegT, WireT, RegAssign,
    reg_next, mux, cat, slice_, rotate_left, rotate_right,
    vf_block, vf_fsm,
)
from ._adapter import from_timing_model

__all__ = [
    # v1 DSL core
    "Signal", "Const", "Cat", "Mux", "Value",
    "Module", "Domain", "DomainCollection",
    "CycleSimulator",
    "VerilogEmitter",
    "diff_traces", "TraceDiff",
    # v2 spec protocol
    "RegT", "WireT", "RegAssign",
    "reg_next", "mux", "cat", "slice_", "rotate_left", "rotate_right",
    "vf_block", "vf_fsm",
    # v2 adapter
    "from_timing_model",
]

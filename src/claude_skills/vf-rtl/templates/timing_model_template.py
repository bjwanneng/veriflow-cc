"""timing_model.py — Cycle-accurate structural model for <design_name>.

Contains @vf_block functions that define computation kernels and register
updates. These are emitted as Verilog fragments and injected into the
module skeleton by vf-coder.

Two usage patterns:
  A. Full-module emission: has_dsl_builder=true → VerilogEmitter.emit()
  B. Block-level emission (most common): individual @vf_block functions
     are emitted as always @* / always @(posedge clk) fragments, then
     injected into a hand-written module skeleton by vf-coder.

Type signatures encode NBA timing structurally:
  - RegT inputs: register value at posedge T (read-only)
  - WireT inputs: combinational signal at T
  - RegAssign returns: register takes next_value at posedge T+1

The cocotb testbench uses DRIVE_PHASE_CYCLES from spec.json
timing_convention.golden_to_rtl_offset_cycles to align comparisons.
"""

from veriflow_dsl import (
    RegT, WireT, RegAssign,
    reg_next, mux, cat, slice_,
    vf_block,
)
from veriflow_dsl._spec import rotate_left, rotate_right

# ============================================================
# Section 1: Constants
# ============================================================
MASK32 = 0xFFFFFFFF
# Algorithm-specific constants here


# ============================================================
# Section 2: Module Hierarchy (for top-level instantiation)
# ============================================================
MODULE_HIERARCHY = {
    "<top_name>": {
        "submodules": [
            {
                "instance_name": "u_sub",
                "module": "sub_module_name",
                "connections": {
                    # "local_signal": "submodule_port"
                },
            },
        ],
    },
}


# ============================================================
# Section 3: Computation Kernels (block-level emission)
#
# Each @vf_block function is emitted as a Verilog fragment:
#   - combinational: always @* block + assign
#   - sequential: always @(posedge clk) block
#
# vf-coder injects these fragments into the module skeleton.
# ============================================================

# --- Example: combinational kernel (assign expression) ---

@vf_block(type="combinational")
def example_p0(x: WireT = WireT("x", 32)) -> WireT:
    """P0(x) = x ^ ROL(x, 9) ^ ROL(x, 17)"""
    return x ^ rotate_left(x, 9) ^ rotate_left(x, 17)


# --- Example: sequential kernel (register update) ---

@vf_block(type="sequential")
def example_step(
    *,
    a_reg: RegT = RegT("a_reg", 32),
    b_reg: RegT = RegT("b_reg", 32),
    calc_en: RegT = RegT("calc_en", 1),
) -> list[RegAssign]:
    """Single round step with enable-gated register update."""
    result = a_reg ^ b_reg
    return [
        reg_next(a_reg, mux(calc_en, result, a_reg)),
    ]


# ============================================================
# Section 4: DSL Builder (optional — simple modules)
# ============================================================
# For very simple modules, define build_<module_name>() and set
# has_dsl_builder=true in spec.json. Stage 2 emits the full module.
#
# def build_counter():
#     from veriflow_dsl import Module
#     m = Module("counter")
#     count = m.reg("count", 8)
#     m.d.sync += count.eq(count + 1)
#     return m


# ============================================================
# Section 5: Test Vectors
# ============================================================
TEST_VECTORS = [
    # {"name": "basic", "inputs": {...}, "expected": {...}}
]


def run(test_vector_index: int = 0) -> list[dict]:
    """Run cycle-accurate simulation via CycleSimulator."""
    if not TEST_VECTORS:
        return []
    return []

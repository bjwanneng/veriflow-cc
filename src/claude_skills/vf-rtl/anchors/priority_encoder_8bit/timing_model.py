#!/usr/bin/env python3
"""Anchor: 8-bit priority encoder (combinational).

Demonstrates:
  - Pure combinational logic with tuple[WireT] return (multi-output)
  - Priority resolution using bitwise operations
  - cat() for multi-bit output assembly

Python model -> Verilog mapping:
  data[7:0]      -> input wire [7:0] data
  out[2:0]       -> output wire [2:0] encoded
  valid          -> output wire valid
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "veriflow_dsl"))

from veriflow_dsl import (
    RegT, WireT, vf_block, from_timing_model, VerilogEmitter,
    cat,
)


@vf_block(type="combinational")
def priority_encoder_8bit(
    *,
    data: RegT = RegT("data", 8),
) -> tuple[WireT, WireT]:
    """8-bit priority encoder.

    Returns (encoded, valid) where:
      - encoded[2:0] = index of the highest set bit (0-7)
      - valid = 1 if any bit is set
    """
    # Priority bit 2: set if any of bits [7:4] is 1
    out2 = data[7] | data[6] | data[5] | data[4]

    # Priority bit 1: set if bits [7:6] are 1, OR if bit2 is 0 and bits [3:2] are 1
    out1 = data[7] | data[6] | (~out2 & (data[3] | data[2]))

    # Priority bit 0: complex priority chain
    out0 = (
        data[7]
        | (~data[6] & data[5])
        | (~out2 & data[3])
        | (~out1 & data[1])
    )

    # Concatenate bits into 3-bit encoded output (MSB-first)
    encoded = cat(out2, out1, out0)

    # Valid if any input bit is set
    valid = (
        data[7] | data[6] | data[5] | data[4]
        | data[3] | data[2] | data[1] | data[0]
    )

    return encoded, valid


def main():
    print("=" * 60)
    print("Anchor: priority_encoder_8bit")
    print("=" * 60)
    print("\nEmitted Verilog:")
    m = from_timing_model(priority_encoder_8bit)
    print(VerilogEmitter().emit(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())

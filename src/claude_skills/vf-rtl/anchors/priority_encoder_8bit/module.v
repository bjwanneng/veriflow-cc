// Anchor: 8-bit priority encoder (combinational)
// Style: pure combinational, priority resolution via bitwise operations
// Mapping: timing_model.py cat(out2, out1, out0) -> {out2, out1, out0} in Verilog

`resetall
`timescale 1ns / 1ps
`default_nettype none

module priority_encoder_8bit
(
    input  wire [7:0] data,
    output wire [2:0] encoded,
    output wire       valid
);

// Priority bit 2: set if any of bits [7:4] is 1
wire out2 = data[7] | data[6] | data[5] | data[4];

// Priority bit 1: set if bits [7:6] are 1,
// OR if out2 is 0 and bits [3:2] are 1
wire out1 = data[7] | data[6] | ((~out2) & (data[3] | data[2]));

// Priority bit 0: complex priority chain
wire out0 = data[7]
          | ((~data[6]) & data[5])
          | ((~out2) & data[3])
          | ((~out1) & data[1]);

// Assemble 3-bit encoded output (MSB-first)
assign encoded = {out2, out1, out0};

// Valid if any input bit is set
assign valid = data[7] | data[6] | data[5] | data[4]
             | data[3] | data[2] | data[1] | data[0];

endmodule

`resetall

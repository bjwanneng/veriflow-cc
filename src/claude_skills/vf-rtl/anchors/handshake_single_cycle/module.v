// Anchor: single-cycle handshake
// Style: single sequential block, synchronous active-high reset
// valid and last are combinational (wire) for same-cycle visibility.

`resetall
`timescale 1ns / 1ps
`default_nettype none

module handshake_single_cycle
(
    input  wire         clk,
    input  wire         rst,
    input  wire         trigger,
    output wire         valid,
    output wire         last
);

reg sent_reg = 1'b0;

// Sequential: state update
always @(posedge clk) begin
    if (rst) begin
        sent_reg <= 1'b0;
    end else begin
        if (trigger && !sent_reg)
            sent_reg <= 1'b1;
        else
            sent_reg <= 1'b0;
    end
end

// Combinational outputs (same-cycle visibility)
assign valid = trigger && !sent_reg;
assign last  = trigger && !sent_reg;

endmodule

`resetall

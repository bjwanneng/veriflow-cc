// Anchor: hold-until-ack handshake
// Style: single sequential block, synchronous active-high reset
// valid is combinational (= pending) for same-cycle visibility.

`resetall
`timescale 1ns / 1ps
`default_nettype none

module handshake_hold_until_ack
(
    input  wire         clk,
    input  wire         rst,
    input  wire         req,
    input  wire         ack,
    output wire         valid
);

reg pending = 1'b0;

always @(posedge clk) begin
    if (rst) begin
        pending <= 1'b0;
    end else begin
        if (req && !pending)
            pending <= 1'b1;
        else if (ack && pending)
            pending <= 1'b0;
        else
            pending <= pending;
    end
end

assign valid = pending;

endmodule

`resetall

// -----------------------------------------------------------------------------
// File   : dsp_mac_32.v
// Author : Zhang Wei
// Date   : 2026-04-26
// -----------------------------------------------------------------------------
// Description:
//   Pipeline 32x32 multiply-accumulate unit for CIOS Montgomery multiplication.
//   Computes P = (a * b) + c_in + t_in. Two-stage pipeline: Stage 1 registers
//   all inputs; Stage 2 performs 32x32 multiply + two 64-bit additions and
//   registers the result word and carry-out. Behavioral * operator maps to
//   DSP48E2 during synthesis. Synchronous active-high reset per design spec.
// -----------------------------------------------------------------------------
// Change Log:
//   2026-04-26  Zhang Wei  v1.0  Initial release
// -----------------------------------------------------------------------------

`resetall
`timescale 1ns / 1ps
`default_nettype none

module dsp_mac_32
(
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] a_i,
    input  wire [31:0] b_i,
    input  wire [31:0] c_in_i,
    input  wire [31:0] t_in_i,
    output wire [31:0] res_out_o,
    output wire [31:0] c_out_o
);

    // -------------------------------------------------------------------------
    // Pipeline Stage 1 registers
    // -------------------------------------------------------------------------
    reg [31:0] a_reg      = {32{1'b0}};
    reg [31:0] b_reg      = {32{1'b0}};
    reg [31:0] c_in_reg   = {32{1'b0}};
    reg [31:0] t_in_reg   = {32{1'b0}};

    // -------------------------------------------------------------------------
    // Pipeline Stage 2 computation and output registers
    // -------------------------------------------------------------------------
    reg [31:0] res_out_reg = {32{1'b0}};
    reg [31:0] c_out_reg   = {32{1'b0}};

    // Internal 64-bit product wire
    wire [63:0] temp_64;

    // Stage 2 combinational: multiply + two additions
    assign temp_64 = (a_reg * b_reg) + {32'd0, c_in_reg} + {32'd0, t_in_reg};

    // -------------------------------------------------------------------------
    // Sequential logic: Pipeline Stage 1 + Stage 2
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            a_reg        <= {32{1'b0}};
            b_reg        <= {32{1'b0}};
            c_in_reg     <= {32{1'b0}};
            t_in_reg     <= {32{1'b0}};
            res_out_reg  <= {32{1'b0}};
            c_out_reg    <= {32{1'b0}};
        end else begin
            // Stage 1: register inputs
            a_reg    <= a_i;
            b_reg    <= b_i;
            c_in_reg <= c_in_i;
            t_in_reg <= t_in_i;

            // Stage 2: register multiply-add result
            res_out_reg <= temp_64[31:0];
            c_out_reg   <= temp_64[63:32];
        end
    end

    // -------------------------------------------------------------------------
    // Output assignments
    // -------------------------------------------------------------------------
    assign res_out_o = res_out_reg;
    assign c_out_o   = c_out_reg;

endmodule

`resetall

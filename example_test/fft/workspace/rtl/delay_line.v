`resetall
`timescale 1ns / 1ps
`default_nettype none

// delay_line.v -- Shift register / delay line for SDF feedback.
//
// Parameterized depth.  Stores complex (real + imaginary) data.
// Data shifts in on posedge clk when shift_en is high.
// Parallel read of all locations for SDF butterfly access.
// Async active-low reset.

module delay_line #(
    parameter DATA_W = 16,
    parameter DEPTH  = 16
)(
    input  wire                      clk,
    input  wire                      rst_n,
    input  wire                      shift_en,
    input  wire signed [DATA_W-1:0]  din_re,
    input  wire signed [DATA_W-1:0]  din_im,
    output wire signed [DATA_W-1:0]  dout_re,
    output wire signed [DATA_W-1:0]  dout_im
);

    // -----------------------------------------------------------------------
    // Shift register array
    // -----------------------------------------------------------------------
    reg signed [DATA_W-1:0] mem_re [DEPTH-1:0];
    reg signed [DATA_W-1:0] mem_im [DEPTH-1:0];

    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                mem_re[i] <= {DATA_W{1'b0}};
                mem_im[i] <= {DATA_W{1'b0}};
            end
        end else if (shift_en) begin
            mem_re[0] <= din_re;
            mem_im[0] <= din_im;
            for (i = 1; i < DEPTH; i = i + 1) begin
                mem_re[i] <= mem_re[i-1];
                mem_im[i] <= mem_im[i-1];
            end
        end
    end

    // Output = last element (deepest sample)
    assign dout_re = mem_re[DEPTH-1];
    assign dout_im = mem_im[DEPTH-1];

endmodule

`resetall

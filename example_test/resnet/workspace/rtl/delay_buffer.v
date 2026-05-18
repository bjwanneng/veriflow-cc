`resetall
`timescale 1ns / 1ps
`default_nettype none

module delay_buffer #(
    parameter DATA_BITS    = 8,
    parameter DELAY_CYCLES = 7
)(
    input  wire clk,
    input  wire rst,
    input  wire in_valid_i,
    input  wire [DATA_BITS-1:0] in_data_i,
    output wire out_valid_o,
    output wire [DATA_BITS-1:0] out_data_o
);

    // Shift-register chain: each stage holds {valid, data}
    // Stage 0 samples input, stage DELAY_CYCLES-1 drives output.
    reg [DATA_BITS-1:0] data_reg [0:DELAY_CYCLES-1];
    reg                 valid_reg [0:DELAY_CYCLES-1];

    integer i;

    // Sequential block: shift on every posedge clk
    always @(posedge clk) begin
        if (rst) begin
            for (i = 0; i < DELAY_CYCLES; i = i + 1) begin
                data_reg[i]  <= {DATA_BITS{1'b0}};
                valid_reg[i] <= 1'b0;
            end
        end else begin
            // Stage 0 samples input
            data_reg[0]  <= in_data_i;
            valid_reg[0] <= in_valid_i;
            // Cascade: stage[N] <= stage[N-1]
            for (i = 1; i < DELAY_CYCLES; i = i + 1) begin
                data_reg[i]  <= data_reg[i-1];
                valid_reg[i] <= valid_reg[i-1];
            end
        end
    end

    // Output is the last stage (registered)
    assign out_valid_o = valid_reg[DELAY_CYCLES-1];
    assign out_data_o  = data_reg[DELAY_CYCLES-1];

endmodule

`resetall

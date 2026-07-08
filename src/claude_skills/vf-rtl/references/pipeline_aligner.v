// Reference: pipeline delay aligner (Verilog-2005).
// Delays a control/sideband signal by exactly N cycles to match a datapath
// pipeline of the same depth — the root cause of most "B_late" timing bugs.
module pipeline_aligner #(parameter N = 2) (
    input  wire clk,
    input  wire rst,
    input  wire in_valid,
    output wire out_valid
);
    // N-deep shift register; out_valid is in_valid delayed by N clocks.
    reg [N-1:0] pipe_r;
    integer i;
    always @(posedge clk) begin
        if (rst) begin
            pipe_r <= {N{1'b0}};
        end else begin
            for (i = N-1; i > 0; i = i - 1)
                pipe_r[i] <= pipe_r[i-1];
            pipe_r[0] <= in_valid;
        end
    end
    assign out_valid = pipe_r[N-1];
endmodule

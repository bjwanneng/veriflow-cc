// Reference: synchronous up-counter with enable (Verilog-2005).
// Canonical pattern: one state register, enable-gated increment, active-high rst.
module counter #(parameter WIDTH = 8) (
    input  wire             clk,
    input  wire             rst,
    input  wire             en,
    output wire [WIDTH-1:0] count
);
    reg [WIDTH-1:0] count_r;
    always @(posedge clk) begin
        if (rst)
            count_r <= {WIDTH{1'b0}};
        else if (en)
            count_r <= count_r + 1'b1;
    end
    assign count = count_r;
endmodule

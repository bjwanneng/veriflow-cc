// BAD: blocking assignment inside sequential block
// L1 should catch: count = count + 1 (should be <=)

module bad_counter
(
    input  wire clk,
    input  wire rst,
    input  wire en,
    output wire [7:0] count
);

reg [7:0] count_reg = 8'd0;

always @(posedge clk) begin
    if (rst) begin
        count_reg <= 8'd0;
    end else begin
        if (en)
            count_reg = count_reg + 1;   // BUG: blocking assignment in seq block
        else
            count_reg = count_reg;       // BUG: also blocking
    end
end

assign count = count_reg;

endmodule

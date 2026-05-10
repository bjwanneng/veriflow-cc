// GOOD: correct NBA usage, ports match spec

module good_counter
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
        count_reg <= en ? count_reg + 1 : count_reg;
    end
end

assign count = count_reg;

endmodule

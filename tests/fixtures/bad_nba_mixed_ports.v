// BAD: ports mismatch with spec (width wrong)
// L3 should catch: count is [3:0] but spec expects [7:0]

module bad_ports
(
    input  wire clk,
    input  wire rst,
    input  wire en,
    output wire [3:0] count    // WRONG: spec expects [7:0]
);

reg [3:0] count_reg = 4'd0;

always @(posedge clk) begin
    if (rst) begin
        count_reg <= 4'd0;
    end else begin
        count_reg <= en ? count_reg + 1 : count_reg;
    end
end

assign count = count_reg;

endmodule

// GOOD: two-segment FSM with combinational + sequential blocks
// L1 must NOT flag the = inside always @* (combinational block)

module good_fsm
(
    input  wire clk,
    input  wire rst,
    input  wire start,
    output wire [1:0] state,
    output wire done
);

localparam IDLE = 2'b00;
localparam WORK = 2'b01;

reg [1:0] state_reg = IDLE;
reg [1:0] next_state;

// Combinational block: blocking assignment is correct here
always @(*) begin
    case (state_reg)
        IDLE: next_state = start ? WORK : IDLE;
        WORK: next_state = WORK;
        default: next_state = IDLE;
    endcase
end

// Sequential block: must use NBA
always @(posedge clk) begin
    if (rst) begin
        state_reg <= IDLE;
    end else begin
        state_reg <= next_state;
    end
end

assign state = state_reg;
assign done  = (state_reg == WORK);

endmodule
